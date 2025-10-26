//This agent is hosted on agentverse with agent address agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq
from __future__ import annotations

import os
import time
import json
import uuid
import requests
from enum import Enum
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
    EndSessionContent,
)
from peg_models import PegSnapshotRequest, PegSnapshotResponse

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
AGENT_NAME = "peg-monitor-multicoin"
POLL_SECONDS = 45
WINDOW_N = 8

# ASI:One
ASI_API_KEY = os.getenv("LLM_API_KEY", "").strip()
ASI_BASE_URL = os.getenv("LLM_API_ENDPOINT", "https://api.asi1.ai/v1").rstrip("/")
ASI_HEADERS = (
    {"Authorization": f"Bearer {ASI_API_KEY}", "Content-Type": "application/json"}
    if ASI_API_KEY else None
)
STRUCT_MODEL = os.getenv("STRUCT_MODEL", "asi1-experimental").strip()
CHAT_MODEL = os.getenv("CHAT_MODEL", "asi1-mini").strip()
SYSTEM_PROMPT = (
    "You are Peggy, a peg stability analyst who explains stablecoin health clearly and concisely. "
    "Prefer short, natural language. If JSON is requested, respond only with JSON."
)

# CoinGecko IDs for top stablecoins
CG_BASE = "https://api.coingecko.com/api/v3"
CG_HEADERS = {"Accept": "application/json", "User-Agent": AGENT_NAME}
COINS = {
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
    "FDUSD": "first-digital-usd",
    "BUSD": "binance-usd",
    "TUSD": "true-usd",
    "USDP": "paxos-standard",
    "PYUSD": "paypal-usd",
    "USDD": "usdd",
    "GUSD": "gemini-dollar",
}

# Risk constants
PERSIST_THRESHOLD_BPS = 3
MAX_DEV_BPS_CAP = 200
DISP_CAP = 0.005
CROSS_CAP = 0.005
W_SPOT_TWAP = 0.50
W_PERSIST = 0.30
W_DISP = 0.10
W_CROSS = 0.10
NORM_BPS = 0.01
NORM_DISP = 0.005
NORM_CROSS = 0.005
DEV_HEALTHY_MAX_BPS = 5
DEV_CAUTION_MIN_BPS = 10
DEV_ALERT_MIN_BPS = 30
RISK_WATCH_MIN = 0.25
RISK_CAUTION_MIN = 0.50
RISK_ALERT_MIN = 0.75

# ──────────────────────────────────────────────────────────────────────────────
# Agent + Chat
# ──────────────────────────────────────────────────────────────────────────────
agent = Agent(name=AGENT_NAME, publish_agent_details=True)
chat_proto = Protocol(spec=chat_protocol_spec)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def now_iso() -> str: return datetime.now(timezone.utc).isoformat()
def clamp(x, lo, hi): return max(lo, min(hi, x))
def bps(x): return 10_000.0 * x
def norm(v, cap): return clamp(abs(v) / cap, 0.0, 1.0)
def safe_get(d: dict, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur
def fallback_summary(latest: dict) -> str:
    if not latest: return "No peg data cached yet. Try again later."
    return f"Regime: {latest.get('regime','UNKNOWN')} | Updated {latest.get('timestamp')}"

# ──────────────────────────────────────────────────────────────────────────────
# Fetchers
# ──────────────────────────────────────────────────────────────────────────────
def fetch_simple_prices() -> Dict[str, float]:
    ids = ",".join(COINS.values())
    url = f"{CG_BASE}/simple/price?ids={ids}&vs_currencies=usd"
    r = requests.get(url, headers=CG_HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    return {sym: float(safe_get(data, cid, "usd", default=1.0)) for sym, cid in COINS.items()}

# ──────────────────────────────────────────────────────────────────────────────
# Core Analytics
# ──────────────────────────────────────────────────────────────────────────────
def compute_window_stats(series: deque, persist_thr_bps: float):
    if not series: return {"spot_dev": 0.0, "twap_dev": 0.0, "persist": 0.0}
    spot = series[-1]
    spot_dev = min(abs(spot - 1.0), MAX_DEV_BPS_CAP / 10_000.0)
    twap = sum(series) / len(series)
    twap_dev = abs(twap - 1.0)
    thr = persist_thr_bps / 10_000.0
    persist = sum(1 for p in series if abs(p - 1.0) > thr) / len(series)
    return {"spot_dev": spot_dev, "twap_dev": twap_dev, "persist": persist}

def risk_score(spot_dev, twap_dev, persist):
    blended = 0.5 * spot_dev + 0.5 * twap_dev
    return W_SPOT_TWAP * norm(blended, NORM_BPS) + W_PERSIST * clamp(persist, 0.0, 1.0)

def classify_regime(total_risk, worst_dev_bps):
    if total_risk >= RISK_ALERT_MIN or worst_dev_bps >= DEV_ALERT_MIN_BPS: return "ALERT"
    if total_risk >= RISK_CAUTION_MIN or worst_dev_bps >= DEV_CAUTION_MIN_BPS: return "CAUTION"
    if total_risk >= RISK_WATCH_MIN or worst_dev_bps >= DEV_HEALTHY_MAX_BPS: return "WATCH"
    return "HEALTHY"

# ──────────────────────────────────────────────────────────────────────────────
# Monitor Loop (Scaled)
# ──────────────────────────────────────────────────────────────────────────────
@agent.on_interval(period=POLL_SECONDS)
async def monitor(ctx: Context):
    t0 = time.time()
    ts = now_iso()

    try:
        spot_map = fetch_simple_prices()
    except Exception as e:
        ctx.logger.error(f"[{ts}] fetch error: {e}")
        return

    risks, stats = {}, {}
    worst_dev_bps = 0.0

    for sym, px in spot_map.items():
        win = deque(ctx.storage.get(f"win_{sym}") or [], maxlen=WINDOW_N)
        win.append(px)
        ctx.storage.set(f"win_{sym}", list(win))

        m = compute_window_stats(win, PERSIST_THRESHOLD_BPS)
        r = risk_score(m["spot_dev"], m["twap_dev"], m["persist"])
        risks[sym] = round(r, 3)
        stats[sym] = {
            "spot_dev_bps": round(bps(m["spot_dev"]), 2),
            "twap_dev_bps": round(bps(m["twap_dev"]), 2),
            "persist": round(m["persist"], 3),
        }
        worst_dev_bps = max(worst_dev_bps, bps(m["spot_dev"]))

    total_risk = max(risks.values()) if risks else 0.0
    regime = classify_regime(total_risk, worst_dev_bps)
    latency_ms = int(1000 * (time.time() - t0))

    payload = {
        "timestamp": ts,
        "coins": list(COINS.keys()),
        "spot": spot_map,
        "stats": stats,
        "risk": risks,
        "total_risk": total_risk,
        "regime": regime,
        "latency_ms": latency_ms,
    }

    ctx.storage.set("peg_latest", json.dumps(payload))
    ctx.logger.info(f"[{ts}] Peg scan {len(COINS)} coins | Regime {regime} | MaxRisk {total_risk:.3f}")

# ──────────────────────────────────────────────────────────────────────────────
# Direct message handler (unchanged)
# ──────────────────────────────────────────────────────────────────────────────
@agent.on_message(model=PegSnapshotRequest, replies=PegSnapshotResponse)
async def handle_snapshot_request(ctx: Context, sender: str, msg: PegSnapshotRequest):
    raw = ctx.storage.get("peg_latest")
    if raw is None:
        await ctx.send(sender, PegSnapshotResponse(corr_id=msg.corr_id, ok=False, payload_json="{}"))
    else:
        await ctx.send(sender, PegSnapshotResponse(corr_id=msg.corr_id, ok=True, payload_json=raw))

# ──────────────────────────────────────────────────────────────────────────────
# Chat logic (same)
# ──────────────────────────────────────────────────────────────────────────────
class IntentEnum(str, Enum):
    status = "status"
    snapshot = "snapshot"
    explain = "explain"
    metric = "metric"

class PegIntent(BaseModel):
    intent: IntentEnum
    symbols: List[str] = Field(default_factory=list)
    symbol: Optional[str] = None
    metric: Optional[str] = None
    venue: Optional[str] = None

def extract_intent_with_asi(user_text: str) -> Optional[PegIntent]:
    if not ASI_HEADERS:
        return None
    schema = {
        "type": "json_schema",
        "json_schema": {"name": "PegIntent", "strict": True, "schema": PegIntent.model_json_schema()},
    }
    payload = {
        "model": STRUCT_MODEL,
        "messages": [{"role": "system", "content": "Extract user intent for stablecoin peg queries."},
                     {"role": "user", "content": user_text}],
        "response_format": schema,
        "temperature": 0,
    }
    try:
        r = requests.post(f"{ASI_BASE_URL}/chat/completions", headers=ASI_HEADERS, json=payload, timeout=30)
        data = r.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        return PegIntent.model_validate_json(content) if content.strip().startswith("{") else None
    except Exception:
        return None

def heuristic_intent(user_text: str) -> PegIntent:
    lt = user_text.lower()
    if "json" in lt or "snapshot" in lt: return PegIntent(intent=IntentEnum.snapshot)
    if "why" in lt or "explain" in lt: return PegIntent(intent=IntentEnum.explain)
    if any(k in lt for k in ("price", "risk", "regime")): return PegIntent(intent=IntentEnum.metric)
    return PegIntent(intent=IntentEnum.status)

def generate_response_with_asi(intent: str, latest: dict) -> str:
    # Always honor "snapshot" locally, regardless of ASI availability.
    if intent == "snapshot":
        try:
            return json.dumps(latest, indent=2)
        except Exception:
            return fallback_summary(latest)

    # For "status" / "explain", use ASI when available, otherwise fallback locally.
    if not ASI_HEADERS:
        return fallback_summary(latest)

    instruction = (
        "Summarize the current peg regime in one line." if intent == "status"
        else "Explain what is happening with the peg and why, in simple terms."
    )
    try:
        payload = {
            "model": CHAT_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{instruction}\n\nPeg snapshot:\n{json.dumps(latest)}"},
            ],
            "temperature": 0.4,
            "max_tokens": 350,
        }
        r = requests.post(f"{ASI_BASE_URL}/chat/completions", headers=ASI_HEADERS, json=payload, timeout=45)
        if not r.ok:
            return fallback_summary(latest)
        data = r.json()
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", fallback_summary(latest))
    except Exception:
        return fallback_summary(latest)

@chat_proto.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    # Acknowledge message
    await ctx.send(sender, ChatAcknowledgement(
        acknowledged_msg_id=msg.msg_id, timestamp=datetime.now(timezone.utc)
    ))

    # Collect user text
    texts = [c.text for c in msg.content if isinstance(c, TextContent)]
    user_text = ("\n".join(texts)).strip() or "Summarize the current peg regime."
    ctx.logger.info(f"[chat] user_text={user_text!r}")

    # Load latest snapshot
    raw = ctx.storage.get("peg_latest")
    latest = json.loads(raw) if isinstance(raw, str) else raw
    if not latest:
        await ctx.send(sender, ChatMessage(
            content=[TextContent(text="No peg data cached yet. Try again in ~1 minute.")],
            msg_id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc),
        ))
        return

    # === Build a direct ASI prompt ===
    system_prompt = (
        "You are Peggy, a stablecoin peg analyst. "
        "Explain data clearly in one or two sentences. "
        "Focus on peg health, risks, and anomalies. "
        "If the user asks anything else, still respond based on the data below."
    )
    user_prompt = (
        f"User message: {user_text}\n\n"
        f"Here is the latest peg snapshot JSON:\n{json.dumps(latest, indent=2)}"
    )

    # === Call ASI ===
    try:
        payload = {
            "model": CHAT_MODEL,  # e.g. "asi1-mini"
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 350,
        }
        r = requests.post(f"{ASI_BASE_URL}/chat/completions",
                          headers=ASI_HEADERS, json=payload, timeout=45)
        if not r.ok:
            ctx.logger.warning(f"[ASI] status={r.status_code} → fallback_summary")
            reply_text = fallback_summary(latest)
        else:
            data = r.json()
            reply_text = ((data.get("choices") or [{}])[0]
                          .get("message", {}).get("content", "")).strip() or fallback_summary(latest)
    except Exception as e:
        ctx.logger.exception(f"[ASI] chat call failed: {e}")
        reply_text = fallback_summary(latest)

    # Send back reply
    await ctx.send(sender, ChatMessage(
        content=[TextContent(text=reply_text)],
        msg_id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc),
    ))

@chat_proto.on_message(ChatAcknowledgement)
async def on_chat_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"[chat] ack from {sender[-10:]} for {msg.acknowledged_msg_id}")

agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()