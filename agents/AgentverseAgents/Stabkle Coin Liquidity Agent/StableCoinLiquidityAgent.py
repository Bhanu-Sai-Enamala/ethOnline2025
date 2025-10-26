from __future__ import annotations
import os, time, json, uuid, requests
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum
from datetime import datetime, timezone
from collections import defaultdict

from pydantic import BaseModel
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
    EndSessionContent,
)

# Keep your existing DM models (unchanged)
from liquidity_models import LiquidityRequest, LiquidityResponse


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
AGENT_NAME = os.getenv("AGENT_NAME", "liquidity-agent-multicoin-chat")
POLL_SECONDS = int(os.getenv("LIQ_AGENT_POLL_SEC", "120"))
INTER_PAIR_SLEEP = float(os.getenv("LIQ_INTER_PAIR_SLEEP", "0.15"))

# Chain / 1inch
ONEINCH_API_KEY = (os.getenv("ONEINCH_API_KEY") or "").strip() or None
ONEINCH_HEADER_STYLE = (os.getenv("ONEINCH_HEADER_STYLE", "bearer") or "bearer").lower()  # "bearer" | "x-api-key"
ONEINCH_BASE = "https://api.1inch.dev/swap/v6.0"
CHAIN_ID = int(os.getenv("CHAIN_ID", "1"))  # Ethereum mainnet by default

def req_headers() -> Dict[str, str]:
    h = {"Accept": "application/json", "User-Agent": AGENT_NAME}
    if ONEINCH_API_KEY:
        if ONEINCH_HEADER_STYLE == "x-api-key":
            h["x-api-key"] = ONEINCH_API_KEY
        else:
            h["Authorization"] = f"Bearer {ONEINCH_API_KEY}"
    return h

def quote_url(chain_id: int) -> str:
    return f"{ONEINCH_BASE}/{chain_id}/quote"

# ASI:One (structured intent + chat); optional
ASI_API_KEY  = (os.getenv("LLM_API_KEY") or "").strip()
ASI_BASE_URL = os.getenv("LLM_API_ENDPOINT", "https://api.asi1.ai/v1").rstrip("/")
ASI_HEADERS  = {"Authorization": f"Bearer {ASI_API_KEY}", "Content-Type": "application/json"} if ASI_API_KEY else None
STRUCT_MODEL = os.getenv("STRUCT_MODEL", "asi1-experimental").strip()
CHAT_MODEL   = os.getenv("CHAT_MODEL", "asi1-mini").strip()
SYSTEM_PROMPT = (
    "You are Liqui, a stablecoin liquidity analyst. Be concise and clear. "
    "Prefer short answers. If JSON is requested, respond with JSON only."
)

# Optional CEX probe (keeps output shape identical; only affects score internally)
ENABLE_CEX_PROBE = os.getenv("ENABLE_CEX_PROBE", "1") == "1"
CEX_BPS_WINDOW = float(os.getenv("CEX_BPS_WINDOW", "10"))  # order book depth window ±bps
W_PRICE = float(os.getenv("W_PRICE", "0.6"))               # weight for 1inch price-derived confidence
W_CEX   = float(os.getenv("W_CEX", "0.4"))                 # weight for CEX depth term (if enabled)

# Storage key (unchanged)
STORAGE_KEY_SUMMARY = "liq_summary_v3"  # {SYMBOL: {score, amount, timestamp}}

# Universe (10 coins) + fanout bases (USDC, USDT)
STABLES: List[str] = json.loads(os.getenv("STABLES_JSON", '["USDC","USDT","DAI","FDUSD","BUSD","TUSD","USDP","PYUSD","USDD","GUSD"]'))
PAIR_BASES: List[str] = json.loads(os.getenv("PAIR_BASES_JSON", '["USDC","USDT"]'))

# Ethereum mainnet token metadata (extend/override via env if needed)
TOKENS: Dict[str, Dict[str, Any]] = {
    "USDC":  {"address": "0xA0b86991C6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
    "USDT":  {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
    "DAI":   {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
    "FDUSD": {"address": "0xc5f0f7b66764f6ec8c8dff7ba683102295e16409", "decimals": 18},
    "BUSD":  {"address": "0x4fabb145d64652a948d72533023f6e7a623c7c53", "decimals": 18},
    "TUSD":  {"address": "0x0000000000085d4780b73119b644ae5ecd22b376", "decimals": 18},
    "USDP":  {"address": "0x1456688345527bE1f37E9e627DA0837D6f08C925", "decimals": 18},  # Pax Dollar
    "PYUSD": {"address": "0x6c3ea9036406852006290770bedfcaba0e23a0e8", "decimals": 6},
    "USDD":  {"address": "0x0c10bf8fcb7bf5412187a595ab97a3609160b5c6", "decimals": 18},
    "GUSD":  {"address": "0x056Fd409e1d7a124bd7017459dfea2f387b6d5cd", "decimals": 2},
}


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def human_to_base(amount_human: float, decimals: int) -> int:
    return int(round(float(amount_human) * (10 ** decimals)))

def base_to_human(amount_base: Optional[int], decimals: int) -> Optional[float]:
    if amount_base is None:
        return None
    return float(amount_base) / (10 ** decimals)

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def extract_dst_amount(q: Dict[str, Any]) -> Optional[int]:
    for k in ("dstAmount", "toAmount", "toTokenAmount", "to_token_amount"):
        v = q.get(k)
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 1inch Quotes
# ──────────────────────────────────────────────────────────────────────────────
def fetch_quote(chain_id: int, from_sym: str, to_sym: str, amount_human: float = 1.0, timeout: int = 12) -> Optional[float]:
    """Return eff_rate (dst/src) or None."""
    fmeta = TOKENS.get(from_sym.upper())
    tmeta = TOKENS.get(to_sym.upper())
    if not fmeta or not tmeta:
        return None

    amount_base = human_to_base(amount_human, fmeta["decimals"])
    try:
        r = requests.get(
            quote_url(chain_id),
            params={
                "fromTokenAddress": fmeta["address"],
                "toTokenAddress": tmeta["address"],
                "amount": str(amount_base),
                "includeTokensInfo": "false",
                "includeProtocols": "false",
            },
            headers=req_headers(),
            timeout=timeout,
        )
        if r.status_code == 429:
            # rate limited; treat as missing
            return None
        r.raise_for_status()
        data = r.json()
        dst = extract_dst_amount(data)
        if dst is None:
            return None
        dst_h = base_to_human(dst, tmeta["decimals"])
        if dst_h is None or amount_human <= 0:
            return None
        eff = float(dst_h) / float(amount_human)
        return eff
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Optional CEX depth probe (Coinbase + Kraken)
# Returns a single scalar cex_depth_score in [0,1] used in scoring.
# ──────────────────────────────────────────────────────────────────────────────
def _cex_probe_depth() -> Optional[float]:
    if not ENABLE_CEX_PROBE:
        return None
    try:
        # Coinbase — level 2 order books
        cb_usdc = requests.get("https://api.exchange.coinbase.com/products/USDC-USD/book?level=2", timeout=5).json()
        cb_usdt = requests.get("https://api.exchange.coinbase.com/products/USDT-USD/book?level=2", timeout=5).json()
        # Kraken — depth for USD pairs
        kr_usdc = requests.get("https://api.kraken.com/0/public/Depth?pair=USDCUSD&count=50", timeout=5).json()
        kr_usdt = requests.get("https://api.kraken.com/0/public/Depth?pair=USDTUSD&count=50", timeout=5).json()

        def mid_cb(book):
            bids = book.get("bids") or []; asks = book.get("asks") or []
            if not bids or not asks: return None
            return 0.5 * (float(asks[0][0]) + float(bids[0][0]))

        def depth_cb(book, mid, bps: float) -> float:
            if mid is None: return 0.0
            lo = mid*(1-bps/10000); hi = mid*(1+bps/10000)
            s = 0.0
            for px, qty, *_ in (book.get("bids") or []):
                px = float(px); qty = float(qty)
                if px >= lo: s += px*qty
            for px, qty, *_ in (book.get("asks") or []):
                px = float(px); qty = float(qty)
                if px <= hi: s += px*qty
            return s

        cb_depth = depth_cb(cb_usdc, mid_cb(cb_usdc), CEX_BPS_WINDOW) + depth_cb(cb_usdt, mid_cb(cb_usdt), CEX_BPS_WINDOW)

        def first_book(res: Dict[str, Any]):
            result = (res or {}).get("result") or {}
            return next(iter(result.values()), {})

        kr_book_usdc = first_book(kr_usdc); kr_book_usdt = first_book(kr_usdt)

        def mid_kr(book):
            bids = book.get("bids") or []; asks = book.get("asks") or []
            if not bids or not asks: return None
            return 0.5 * (float(asks[0][0]) + float(bids[0][0]))

        def depth_kr(book, mid, bps: float) -> float:
            if mid is None: return 0.0
            lo = mid*(1-bps/10000); hi = mid*(1+bps/10000)
            s = 0.0
            for px, qty, *_ in (book.get("bids") or []):
                px = float(px); qty = float(qty)
                if px >= lo: s += px*qty
            for px, qty, *_ in (book.get("asks") or []):
                px = float(px); qty = float(qty)
                if px <= hi: s += px*qty
            return s

        kr_depth = depth_kr(kr_book_usdc, mid_kr(kr_book_usdc), CEX_BPS_WINDOW) + depth_kr(kr_book_usdt, mid_kr(kr_book_usdt), CEX_BPS_WINDOW)

        total_depth_usd = max(cb_depth + kr_depth, 0.0)

        # Map USD depth to [0,1]; soft saturation around ~$1M total depth
        # score = 1 - (1 / (1 + depth / 1e6))  →  0 @ 0 depth, → ~0.5 @ 1M, → → 1
        cex_depth_score = 1.0 - (1.0 / (1.0 + total_depth_usd / 1_000_000.0))
        return float(clamp(cex_depth_score, 0.0, 1.0))
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Minimal storage (per-coin) — unchanged keys and shapes
# ──────────────────────────────────────────────────────────────────────────────
def _get_summary(ctx: Context) -> Dict[str, Any]:
    raw = ctx.storage.get(STORAGE_KEY_SUMMARY)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}

def _set_summary(ctx: Context, m: Dict[str, Any]):
    ctx.storage.set(STORAGE_KEY_SUMMARY, json.dumps(m))


# ──────────────────────────────────────────────────────────────────────────────
# Scoring
#   - eff_rate = (dst / src)
#   - par_bps  = 10_000 * (eff_rate - 1.0)
#   - price_conf = 1 - |par_bps|/40 (clip 0..1)
#   - if CEX enabled: score = W_PRICE*price_conf + W_CEX*cex_depth_score
#     else:           score = price_conf
#   - amount proxy = score  (unchanged from your previous version)
# ──────────────────────────────────────────────────────────────────────────────
def score_from_eff(eff_rate: float, cex_depth_score: Optional[float]) -> Tuple[float, float, float]:
    par_bps = 10000.0 * (eff_rate - 1.0)
    price_conf = clamp(1.0 - abs(par_bps) / 40.0, 0.0, 1.0)
    if cex_depth_score is not None:
        score = clamp(W_PRICE * price_conf + W_CEX * float(cex_depth_score), 0.0, 1.0)
    else:
        score = price_conf
    amount = score  # unchanged behavior
    return score, amount, par_bps


# ──────────────────────────────────────────────────────────────────────────────
# Agent & Poll loop
# ──────────────────────────────────────────────────────────────────────────────
agent = Agent(name=AGENT_NAME, publish_agent_details=True)
chat_proto = Protocol(spec=chat_protocol_spec)

@agent.on_event("startup")
async def boot(ctx: Context):
    ctx.logger.info(f"[{AGENT_NAME}] chain={CHAIN_ID} stables={STABLES} bases={PAIR_BASES} key={'yes' if ONEINCH_API_KEY else 'no'} header={ONEINCH_HEADER_STYLE}")
    ctx.logger.info(f"[{AGENT_NAME}] CEX probe={'ON' if ENABLE_CEX_PROBE else 'OFF'} bps_window=±{CEX_BPS_WINDOW:.0f} W_PRICE={W_PRICE} W_CEX={W_CEX}")
    ctx.logger.info(f"[{AGENT_NAME}] ASI chat={'ON' if ASI_HEADERS else 'OFF'} model={CHAT_MODEL if ASI_HEADERS else 'n/a'}")

@agent.on_interval(period=POLL_SECONDS)
async def poll(ctx: Context):
    ts = now_iso()
    cex_score = _cex_probe_depth()  # may be None
    scores: Dict[str, List[float]] = defaultdict(list)
    amts: Dict[str, List[float]] = defaultdict(list)

    # Fanout from PAIR_BASES to every stable, both directions
    for base in PAIR_BASES:
        for other in STABLES:
            if other == base:
                continue
            for frm, to in ((base, other), (other, base)):
                eff = fetch_quote(CHAIN_ID, frm, to, 1.0)
                if eff is None:
                    continue
                score, amount, _par = score_from_eff(eff, cex_score)
                # store contribution against both assets (symmetry)
                scores[frm].append(score); amts[frm].append(amount)
                scores[to].append(score);  amts[to].append(amount)
                if INTER_PAIR_SLEEP > 0:
                    time.sleep(INTER_PAIR_SLEEP)

    new_summary: Dict[str, Any] = {}
    for sym in STABLES:
        if scores.get(sym):
            s_avg = sum(scores[sym]) / len(scores[sym])
            a_avg = sum(amts[sym]) / len(amts[sym])
            new_summary[sym] = {"score": round(s_avg, 4), "amount": round(a_avg, 4), "timestamp": ts}
        else:
            # keep same shape; n/a as None
            new_summary[sym] = {"score": None, "amount": None, "timestamp": ts}

    _set_summary(ctx, new_summary)
    ctx.logger.info(f"[{AGENT_NAME}] Updated summary for {len(STABLES)} coins at {ts} (cex={'on' if cex_score is not None else 'off'})")


# ──────────────────────────────────────────────────────────────────────────────
# Direct Message Handler (unchanged schema)
#   We return 'estimated_receive_human' = proxy 'amount' for the from_symbol
# ──────────────────────────────────────────────────────────────────────────────
@agent.on_message(model=LiquidityRequest, replies=LiquidityResponse)
async def handle_req(ctx: Context, sender: str, msg: LiquidityRequest):
    summary = _get_summary(ctx)
    coin = (getattr(msg, "from_symbol", "") or "").upper()
    rec = summary.get(coin, {})
    amount = rec.get("amount")
    if amount is None:
        await ctx.send(sender, LiquidityResponse(
            ok=False,
            from_symbol=msg.from_symbol,
            to_symbol=msg.to_symbol,
            amount_human=msg.amount_human,
            estimated_receive_human=None,
            raw_quote=json.dumps({"score": None, "amount": None}),
            error="Insufficient liquidity info",
        ))
        return

    await ctx.send(sender, LiquidityResponse(
        ok=True,
        from_symbol=msg.from_symbol,
        to_symbol=msg.to_symbol,
        amount_human=msg.amount_human,
        estimated_receive_human=float(amount),
        raw_quote=json.dumps({"score": summary[coin]["score"], "amount": amount, "ts": summary[coin]["timestamp"]}),
        error=None
    ))


# ──────────────────────────────────────────────────────────────────────────────
# CHAT (ASI:One): intents + handlers (Peg-style). Output text unchanged.
# ──────────────────────────────────────────────────────────────────────────────
class IntentEnum(str, Enum):
    status   = "status"    # compact multi-coin line
    explain  = "explain"   # short paragraph
    top      = "top"       # best coin now
    coin     = "coin"      # single coin readout
    snapshot = "snapshot"  # raw JSON

class LiquiIntent(BaseModel):
    intent: IntentEnum
    coin: Optional[str] = None
    json: Optional[bool] = False

def _extract_intent_asi(user_text: str) -> Optional[LiquiIntent]:
    if not ASI_HEADERS:
        return None
    schema = {
        "type": "json_schema",
        "json_schema": {"name":"LiquiIntent","strict":True,"schema":LiquiIntent.model_json_schema()},
    }
    payload = {
        "model": STRUCT_MODEL,
        "messages": [
            {"role":"system","content":"Extract intent for liquidity chat. Return ONLY JSON matching the schema."},
            {"role":"user","content": user_text},
        ],
        "response_format": schema,
        "temperature": 0,
        "max_tokens": 128,
    }
    try:
        r = requests.post(f"{ASI_BASE_URL}/chat/completions", headers=ASI_HEADERS, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        if content and content.lstrip().startswith("{"):
            return LiquiIntent.model_validate_json(content)
    except Exception:
        return None
    return None

def _heuristic_intent(user_text: str) -> LiquiIntent:
    t = (user_text or "").lower()
    if any(k in t for k in ["snapshot", "raw", "json", "dump"]):
        return LiquiIntent(intent=IntentEnum.snapshot, json=True)
    if any(k in t for k in ["best", "top", "which coin", "leader"]):
        return LiquiIntent(intent=IntentEnum.top)
    for sym in STABLES:
        if sym.lower() in t:
            return LiquiIntent(intent=IntentEnum.coin, coin=sym.upper())
    if any(k in t for k in ["why", "explain", "because", "summary"]):
        return LiquiIntent(intent=IntentEnum.explain)
    return LiquiIntent(intent=IntentEnum.status)

def _get_summary_line(ctx: Context) -> str:
    s = _get_summary(ctx)
    if not s:
        return "No data yet. Try again shortly."
    parts = []
    for sym in STABLES:
        rec = s.get(sym, {})
        sc = rec.get("score"); am = rec.get("amount")
        if sc is None:
            parts.append(f"{sym}: n/a")
        else:
            parts.append(f"{sym}: score {sc:.3f}, amt {am:.3f}")
    return " | ".join(parts)

def _explain(ctx: Context) -> str:
    s = _get_summary(ctx)
    if not s:
        return "No data yet."
    if ASI_HEADERS:
        try:
            payload = {
                "model": CHAT_MODEL,
                "messages": [
                    {"role":"system","content":SYSTEM_PROMPT},
                    {"role":"user","content":f"Explain current stablecoin liquidity (score/amount) in ≤5 lines. Data:\n{json.dumps(s)}"},
                ],
                "temperature": 0.4,
                "max_tokens": 220,
            }
            r = requests.post(f"{ASI_BASE_URL}/chat/completions", headers=ASI_HEADERS, json=payload, timeout=25)
            if r.ok:
                return ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content", _get_summary_line(ctx))
        except Exception:
            pass
    return _get_summary_line(ctx)

def _top(ctx: Context) -> str:
    s = _get_summary(ctx)
    if not s:
        return "No data yet."
    best_sym, best_score, best_amt = None, -1.0, -1.0
    for sym in STABLES:
        rec = s.get(sym, {})
        sc = rec.get("score")
        am = rec.get("amount")
        if sc is None:
            continue
        if sc > best_score or (sc == best_score and (am or -1) > best_amt):
            best_sym, best_score, best_amt = sym, sc, (am or 0.0)
    if not best_sym:
        return "No usable entries yet."
    return f"Top: {best_sym} (score {best_score:.3f}, amt {best_amt:.3f})"

def _coin(ctx: Context, coin: str) -> str:
    s = _get_summary(ctx)
    rec = s.get(coin.upper(), {})
    sc = rec.get("score"); am = rec.get("amount"); ts = rec.get("timestamp")
    if sc is None:
        return f"{coin.upper()}: n/a"
    return f"{coin.upper()}: score {sc:.3f}, amt {am:.3f} @ {ts}"

@chat_proto.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    # ack first
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id, timestamp=datetime.now(timezone.utc)))

    texts: List[str] = []
    for c in msg.content:
        if isinstance(c, (StartSessionContent, EndSessionContent)):
            continue
        if isinstance(c, TextContent):
            texts.append(c.text)
    user_text = ("\n".join(texts)).strip() or "status"

    intent = _extract_intent_asi(user_text) or _heuristic_intent(user_text)

    if intent.intent == IntentEnum.snapshot:
        text = json.dumps(_get_summary(ctx), indent=2)
    elif intent.intent == IntentEnum.top:
        text = _top(ctx)
    elif intent.intent == IntentEnum.coin:
        text = _coin(ctx, intent.coin or "USDC")
    elif intent.intent == IntentEnum.explain:
        text = _explain(ctx)
    else:
        text = _get_summary_line(ctx)

    await ctx.send(sender, ChatMessage(
        content=[TextContent(text=text)],
        msg_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
    ))

@chat_proto.on_message(ChatAcknowledgement)
async def on_chat_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"[chat] ack from {sender[-10:]} for {msg.acknowledged_msg_id}")

# Include chat protocol
agent.include(chat_proto, publish_manifest=True)

# ──────────────────────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    agent.run()