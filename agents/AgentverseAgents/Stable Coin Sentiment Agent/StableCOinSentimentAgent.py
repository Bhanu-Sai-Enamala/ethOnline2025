from __future__ import annotations

import os
import re
import json
import time
import math
import html
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse

import requests
import xml.etree.ElementTree as ET
from uagents import Agent, Context, Model, Protocol
from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
    EndSessionContent,
)

# =========================
# Config
# =========================

AGENT_NAME = "stablecoin-news-sentiment"
POLL_SECONDS = 300         # refresh every 5 minutes
CACHE_TTL_SECS = 300
HALF_LIFE_MIN = 120        # older headlines decay (half-life in minutes)
MAX_HEADLINES = 120
MAX_PER_SOURCE = 60

# 10-coin universe (same as peg/liquidity agents)
COINS: Dict[str, Dict[str, List[str]]] = {
    "USDT": {"synonyms": [r"\bUSDT\b", r"\bTether\b"]},
    "USDC": {"synonyms": [r"\bUSDC\b", r"\bUSD ?Coin\b", r"\bCircle\b"]},
    "DAI":  {"synonyms": [r"\bDAI\b", r"\bMakerDAO\b"]},
    "FDUSD":{"synonyms": [r"\bFDUSD\b", r"\bFirst Digital USD\b", r"\bFirst Digital\b"]},
    "BUSD": {"synonyms": [r"\bBUSD\b", r"\bBinance USD\b"]},
    "TUSD": {"synonyms": [r"\bTUSD\b", r"\bTrueUSD\b", r"\bTrue USD\b"]},
    "USDP": {"synonyms": [r"\bUSDP\b", r"\bPax Dollar\b", r"\bPaxos Standard\b"]},
    "PYUSD":{"synonyms": [r"\bPYUSD\b", r"\bPayPal USD\b", r"\bPayPal stablecoin\b"]},
    "USDD": {"synonyms": [r"\bUSDD\b", r"\bTRON stablecoin\b"]},
    "GUSD": {"synonyms": [r"\bGUSD\b", r"\bGemini Dollar\b"]},
}

RSS_SOURCES = [
    # Original set
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://cryptobriefing.com/feed/",
    "https://www.theblock.co/rss",

    # Extended set (added; still capped by MAX_PER_SOURCE and MAX_HEADLINES)
    "https://blockworks.co/feed",
    "https://thedefiant.io/feed",
    "https://bitcoinmagazine.com/.rss",
    "https://cryptoslate.com/feed/",
    "https://news.bitcoin.com/feed/",
    "https://ambcrypto.com/feed/",
    "https://u.today/rss",
    "https://www.coinspeaker.com/feed/",
    "https://coinjournal.net/news/feed/",
    "https://www.financemagnates.com/cryptocurrency/feed/",
]

USER_AGENT = AGENT_NAME
HTTP_TIMEOUT = 15

POS_WORDS = {
    "redeem", "redemption", "attestation", "audit", "audited", "reserves",
    "backed", "collateral", "mint", "minted", "approval", "license",
    "integration", "partnership", "onramp", "offramp", "support",
    "expanded", "upgrade", "stable", "peg restored", "repegs", "repeg",
}
NEG_WORDS = {
    "depeg", "depegs", "depegged", "off-peg", "under peg", "above peg",
    "halt", "paused", "freeze", "frozen", "blacklist", "blacklisted",
    "lawsuit", "probe", "investigation", "ban", "sanction", "fud",
    "redemption halt", "liquidity crunch", "shortfall", "bankruptcy",
    "insolvent", "breakdown", "exploit", "hack", "vulnerability",
    "contagion", "collapse", "run", "panic",
}
NEGATORS = {"no", "not", "never", "without", "hardly", "barely"}

# =========================
# ASI:One (LLM) settings — same style as your peg/liquidity agents
# =========================

ASI_API_KEY = os.getenv("LLM_API_KEY", "").strip()
ASI_BASE_URL = os.getenv("LLM_API_ENDPOINT", "https://api.asi1.ai/v1").rstrip("/")
ASI_HEADERS = (
    {"Authorization": f"Bearer {ASI_API_KEY}", "Content-Type": "application/json"}
    if ASI_API_KEY else None
)
STRUCT_MODEL = os.getenv("STRUCT_MODEL", "asi1-experimental").strip()
CHAT_MODEL   = os.getenv("CHAT_MODEL", "asi1-mini").strip()

SYSTEM_PROMPT = (
    "You are Sandy, a stablecoin news-sentiment analyst. "
    "Explain clearly in one or two sentences using plain language. "
    "Focus on per-coin sentiment (bullish/neutral/bearish), notable headlines, and confidence. "
    "If user asks anything else, still base answer on the provided snapshot."
)

# =========================
# Message API models (NO Optional[...] to avoid issubclass crash)
# =========================

class NewsSentimentRequest(Model):
    # Empty string means "all coins"
    coin: str = ""

class NewsSentimentResponse(Model):
    ok: bool
    results_json: str  # JSON string (single coin object or dict coin->obj)

# =========================
# Agent + Chat Protocol
# =========================

agent = Agent(
    name=AGENT_NAME,
    mailbox=True,
    publish_agent_details=True,
)
chat_proto = Protocol(spec=chat_protocol_spec)

# =========================
# Utilities
# =========================

def now_ts() -> float:
    return time.time()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def decay_weight(age_minutes: float, half_life_min: float) -> float:
    return math.pow(0.5, age_minutes / max(half_life_min, 1e-9))

def clean_text(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def tokenize(s: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z\-']+", s.lower())

def negation_adjusted_count(tokens: List[str], pos_set: set, neg_set: set) -> float:
    score = 0.0
    for i, tok in enumerate(tokens):
        is_pos = tok in pos_set
        is_neg = tok in neg_set
        if not (is_pos or is_neg):
            continue
        sign = 1.0 if is_pos else -1.0
        window_start = max(0, i - 3)
        if any(t in NEGATORS for t in tokens[window_start:i]):
            sign *= -1.0
        score += sign
    return score

def normalize_score(raw: float) -> float:
    return math.tanh(0.7 * raw)

def fetch_rss(url: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except Exception:
        return []
    try:
        root = ET.fromstring(resp.content)
    except Exception:
        return []
    items: List[Dict[str, Any]] = []
    for tag in root.iter():
        if tag.tag.endswith("item") or tag.tag.endswith("entry"):
            title = None
            link = None
            published = None
            for child in tag:
                name = child.tag.lower()
                if name.endswith("title"):
                    title = "".join(child.itertext())
                elif name.endswith("link"):
                    href = child.attrib.get("href")
                    link = href if href else "".join(child.itertext())
                elif name.endswith("pubdate") or name.endswith("updated"):
                    published = "".join(child.itertext())
            ts = time.time()
            if published:
                try:
                    from email.utils import parsedate_to_datetime
                    ts = parsedate_to_datetime(published).timestamp()
                except Exception:
                    pass
            if title:
                items.append({"title": clean_text(title), "link": (link or "").strip(), "ts": ts})
    return items

# =========================
# Core scoring
# =========================

def empty_coin_snapshot(ts_int: int) -> Dict[str, Any]:
    return {
        "ts": ts_int,
        "source_count": 0,
        "headline_count": 0,
        "matches": [],
        "rolling": {
            "raw_sum": 0.0,
            "weight_sum": 0.0,
            "score": 0.0,
            "label": "Neutral",
            "confidence": 0.0,
        },
    }

def filter_and_score_headlines(now_s: float) -> Dict[str, Dict[str, Any]]:
    # Precompile synonym regexes
    coin_patterns = {
        sym: [re.compile(pat, re.IGNORECASE) for pat in cfg["synonyms"]]
        for sym, cfg in COINS.items()
    }
    pos_set = set(w.lower() for w in POS_WORDS)
    neg_set = set(w.lower() for w in NEG_WORDS)

    # Fetch feeds
    headlines: List[Dict[str, Any]] = []
    for src in RSS_SOURCES:
        items = fetch_rss(src)[:MAX_PER_SOURCE]
        headlines.extend(items)
    headlines = sorted(headlines, key=lambda x: x["ts"], reverse=True)[:MAX_HEADLINES]

    # Start with a neutral snapshot for every coin (so we always persist something)
    per_coin: Dict[str, Dict[str, Any]] = {sym: empty_coin_snapshot(int(now_s)) for sym in COINS.keys()}

    # Score matches
    for h in headlines:
        title = h["title"]
        link = h["link"]
        ts = h["ts"]
        age_min = max(0.0, (now_s - ts) / 60.0)
        w = decay_weight(age_min, half_life_min=HALF_LIFE_MIN)
        dom = urlparse(link).netloc if link else ""

        tokens = tokenize(title)
        raw_sent = negation_adjusted_count(tokens, pos_set, neg_set)
        sent = normalize_score(raw_sent)  # [-1, 1]

        for sym, patterns in coin_patterns.items():
            if any(p.search(title) for p in patterns):
                pc = per_coin[sym]
                pc["source_count"] += 1
                pc["headline_count"] += 1
                pc["matches"].append({
                    "title": title,
                    "link": link,
                    "source": dom,
                    "age_minutes": round(age_min, 1),
                    "weight": round(w, 4),
                    "headline_score": round(sent, 4),
                })
                pc["rolling"]["raw_sum"] += sent * w
                pc["rolling"]["weight_sum"] += w

    # Finalize rolling
    for sym, pc in per_coin.items():
        rs = pc["rolling"]
        if rs["weight_sum"] > 0:
            avg = clamp(rs["raw_sum"] / rs["weight_sum"], -1.0, 1.0)
        else:
            avg = 0.0
        rs["score"] = round(avg, 4)
        rs["label"] = "Bullish" if avg > 0.25 else ("Bearish" if avg < -0.25 else "Neutral")

        unique_sources = len(set(m["source"] for m in pc["matches"] if m["source"]))
        conf = 0.0
        if pc["headline_count"] >= 5: conf += 0.4
        elif pc["headline_count"] >= 2: conf += 0.2
        if unique_sources >= 3: conf += 0.3
        elif unique_sources >= 2: conf += 0.15
        if pc["matches"]:
            ages = sorted(m["age_minutes"] for m in pc["matches"])
            med_age = ages[len(ages)//2]
            if med_age < 60: conf += 0.3
            elif med_age < 360: conf += 0.15
        rs["confidence"] = round(clamp(conf, 0.0, 1.0), 3)

    return per_coin

# =========================
# Storage helpers
# =========================

def _get_cache(ctx: Context) -> Dict[str, Any]:
    return ctx.storage.get("news_sentiment_cache_v1") or {}

def _set_cache(ctx: Context, d: Dict[str, Any]):
    ctx.storage.set("news_sentiment_cache_v1", d)

def _save_latest(ctx: Context, bundle: Dict[str, str]):
    payload = {"ts": int(now_ts()), "coins": bundle}
    ctx.storage.set("news_sentiment_latest", payload)

def _load_latest(ctx: Context):
    return ctx.storage.get("news_sentiment_latest")

def cache_put(ctx: Context, sym: str, obj: Dict[str, Any]):
    cache = _get_cache(ctx)
    cache[sym] = {"ts": now_ts(), "val_json": json.dumps(obj)}
    _set_cache(ctx, cache)

# =========================
# Refresh logic
# =========================

def _persist_bundle(ctx: Context, bundle_raw: Dict[str, Dict[str, Any]]):
    """
    Writes per-coin cache and a latest snapshot every time.
    Ensures *all* tracked coins are present (Neutral if absent).
    Optional allowlist via SENTIMENT_MIN_MATCH=USDC,USDT
    """
    allow = {c.strip().upper() for c in os.getenv("SENTIMENT_MIN_MATCH", "").split(",") if c.strip()}
    coins_to_write = [c for c in COINS.keys() if (not allow or c in allow)]

    nowi = int(now_ts())
    for c in coins_to_write:
        if c not in bundle_raw:
            bundle_raw[c] = empty_coin_snapshot(nowi)

    bundle_json: Dict[str, str] = {}
    for sym in coins_to_write:
        obj = bundle_raw[sym]
        cache_put(ctx, sym, obj)
        bundle_json[sym] = json.dumps(obj)

    _save_latest(ctx, bundle_json)

    cache_keys = list(_get_cache(ctx).keys())
    ctx.logger.info(f"[{now_iso()}] Stored sentiment for: {', '.join(coins_to_write)} | cache keys: {cache_keys}")

@agent.on_event("startup")
async def on_start(ctx: Context):
    ctx.logger.info(f"{AGENT_NAME} started. Coins: {', '.join(COINS.keys())}")
    ctx.logger.info(f"RSS sources: {len(RSS_SOURCES)}. Half-life {HALF_LIFE_MIN} min.")
    try:
        bundle = filter_and_score_headlines(now_ts())
        _persist_bundle(ctx, bundle)
    except Exception as e:
        ctx.logger.error(f"startup refresh error: {e}")

@agent.on_interval(period=POLL_SECONDS)
async def refresh_news_sentiment(ctx: Context):
    try:
        bundle = filter_and_score_headlines(now_ts())
        _persist_bundle(ctx, bundle)
    except Exception as e:
        ctx.logger.error(f"interval refresh error: {e}")

# =========================
# ---- Chat layer (peg-style, via ASI) ----
# =========================

def _load_summary(ctx: Context) -> Dict[str, Any]:
    """
    Returns a compact dict:
      { symbol: {score, label, confidence, headline_count, source_count, examples:[...]} }
    """
    latest = _load_latest(ctx)
    if not latest or "coins" not in latest:
        return {}
    out: Dict[str, Any] = {}
    for sym, val_json in latest["coins"].items():
        try:
            obj = json.loads(val_json)
            roll = obj.get("rolling", {}) or {}
            out[sym] = {
                "score": roll.get("score", 0.0),
                "label": roll.get("label", "Neutral"),
                "confidence": roll.get("confidence", 0.0),
                "headline_count": obj.get("headline_count", 0),
                "source_count": obj.get("source_count", 0),
                "examples": [
                    {"title": m.get("title", ""), "source": m.get("source", ""), "score": m.get("headline_score", 0.0)}
                    for m in (obj.get("matches") or [])[:3]
                ]
            }
        except Exception:
            continue
    return out

def _scores_line(summary: Dict[str, Any]) -> str:
    parts = []
    for sym in COINS.keys():
        if sym in summary:
            sc = summary[sym]["score"]
            parts.append(f"{sym}: {sc:+.3f}")
    return " | ".join(parts) if parts else "No sentiment yet."

def _best(summary: Dict[str, Any]) -> Tuple[str, float] | None:
    ranked = [(sym, v["score"]) for sym, v in summary.items()]
    if not ranked: return None
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[0]

def _worst(summary: Dict[str, Any]) -> Tuple[str, float] | None:
    ranked = [(sym, v["score"]) for sym, v in summary.items()]
    if not ranked: return None
    ranked.sort(key=lambda x: x[1])
    return ranked[0]

# ---- Intent extraction (ASI or heuristic) ----

def _extract_intent_asi(user_text: str):
    if not ASI_HEADERS:
        return None
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "SentimentIntent",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": ["status", "snapshot", "list", "best", "worst", "explain"]},
                    "symbols": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["intent"],
                "additionalProperties": False
            },
        },
    }
    payload = {
        "model": STRUCT_MODEL,
        "messages": [
            {"role": "system", "content": "Extract intent for stablecoin news sentiment queries."},
            {"role": "user", "content": user_text},
        ],
        "response_format": schema,
        "temperature": 0,
    }
    try:
        r = requests.post(f"{ASI_BASE_URL}/chat/completions", headers=ASI_HEADERS, json=payload, timeout=30)
        data = r.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        return json.loads(content) if content.strip().startswith("{") else None
    except Exception:
        return None

def _heuristic_intent(user_text: str) -> Dict[str, Any]:
    lt = user_text.lower()
    if "json" in lt or "snapshot" in lt: return {"intent": "snapshot", "symbols": []}
    if "why" in lt or "explain" in lt:   return {"intent": "explain", "symbols": []}
    if "best" in lt or "top" in lt:      return {"intent": "best", "symbols": []}
    if "worst" in lt or "lowest" in lt:  return {"intent": "worst", "symbols": []}
    if any(k in lt for k in ("scores", "list", "all")): return {"intent": "list", "symbols": []}
    return {"intent": "status", "symbols": []}

def _fallback_summary(summary: Dict[str, Any]) -> str:
    if not summary:
        return "No sentiment cached yet. Try again later."
    b = _best(summary)
    w = _worst(summary)
    line = _scores_line(summary)
    bits = []
    if b: bits.append(f"Best: {b[0]} ({b[1]:+.3f})")
    if w: bits.append(f"Worst: {w[0]} ({w[1]:+.3f})")
    return " | ".join(bits + ([line] if line else []))

def _summarize_with_asi(user_text: str, summary: Dict[str, Any], mode: str) -> str:
    if not ASI_HEADERS:
        return _fallback_summary(summary)
    try:
        instruction = (
            "Summarize current stablecoin news sentiment across all coins in one line."
            if mode == "status"
            else "Explain what the news sentiment implies for these stablecoins in simple terms."
        )
        payload = {
            "model": CHAT_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{instruction}\n\nSentiment snapshot:\n{json.dumps(summary, indent=2)}\n\nUser: {user_text}"},
            ],
            "temperature": 0.4,
            "max_tokens": 350,
        }
        r = requests.post(f"{ASI_BASE_URL}/chat/completions", headers=ASI_HEADERS, json=payload, timeout=45)
        if not r.ok:
            return _fallback_summary(summary)
        data = r.json()
        return ((data.get("choices") or [{}])[0].get("message", {}).get("content", "")).strip() or _fallback_summary(summary)
    except Exception:
        return _fallback_summary(summary)

@chat_proto.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    # Acknowledge first
    await ctx.send(sender, ChatAcknowledgement(
        acknowledged_msg_id=msg.msg_id, timestamp=datetime.now(timezone.utc)
    ))

    # Collect user text
    texts: List[str] = []
    for c in msg.content:
        if isinstance(c, (StartSessionContent, EndSessionContent)):
            continue
        if isinstance(c, TextContent):
            texts.append(c.text)
    user_text = ("\n".join(texts)).strip() or "status"
    ctx.logger.info(f"[chat] user_text={user_text!r}")

    # Load latest compact summary
    summary = _load_summary(ctx)
    if not summary:
        await ctx.send(sender, ChatMessage(
            content=[TextContent(text="No sentiment cached yet. Try again in ~1 minute.")],
            msg_id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc),
        ))
        return

    # Intent
    parsed = _extract_intent_asi(user_text) or _heuristic_intent(user_text)
    intent = parsed.get("intent", "status")

    # Route
    if intent == "snapshot":
        reply_text = json.dumps(summary, indent=2)
    elif intent == "list":
        reply_text = _scores_line(summary)
    elif intent == "best":
        b = _best(summary)
        reply_text = "No top coin yet." if not b else f"Best sentiment: {b[0]} ({b[1]:+.3f})."
    elif intent == "worst":
        w = _worst(summary)
        reply_text = "No bottom coin yet." if not w else f"Worst sentiment: {w[0]} ({w[1]:+.3f})."
    elif intent == "explain":
        reply_text = _summarize_with_asi(user_text, summary, mode="explain")
    else:
        reply_text = _summarize_with_asi(user_text, summary, mode="status")

    await ctx.send(sender, ChatMessage(
        content=[TextContent(text=reply_text)],
        msg_id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc),
    ))

@chat_proto.on_message(ChatAcknowledgement)
async def on_chat_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"[chat] ack from {sender[-10:]} for {msg.acknowledged_msg_id}")

# ──────────────────────────────────────────────────────────────────────────────
# DM add-on for Responder <-> Sentiment (drop-in)
# NOTE: If you already have a NewsSentimentRequest handler, remove it first.
# ──────────────────────────────────────────────────────────────────────────────

import os, json
from uagents import Context

# Storage key where this agent saves the latest bundle:
# expected shape: {"ts": <int>, "coins": {"USDC": "<json_str>", "USDT": "<json_str>", ...}}
SENTIMENT_STORAGE_KEY = os.getenv("SENTIMENT_STORAGE_KEY", "news_sentiment_latest")

@agent.on_message(model=NewsSentimentRequest, replies=NewsSentimentResponse)
async def dm_sentiment_bundle(ctx: Context, sender: str, msg: NewsSentimentRequest):
    """
    Returns:
      - full bundle (coin -> JSON-string) if msg.coin is empty/blank
      - single coin object (as JSON string) if msg.coin is provided
    """
    latest = ctx.storage.get(SENTIMENT_STORAGE_KEY)

    # Normalize latest to dict
    try:
        latest = json.loads(latest) if isinstance(latest, str) else latest
        if isinstance(latest, str):
            latest = json.loads(latest)
        if not isinstance(latest, dict):
            latest = {}
    except Exception:
        latest = {}

    coins_map = latest.get("coins") if isinstance(latest, dict) else None
    if not isinstance(coins_map, dict) or not coins_map:
        await ctx.send(sender, NewsSentimentResponse(ok=False, results_json="{}"))
        return

    coin = (msg.coin or "").strip().upper()
    if coin:
        # Single coin reply: results_json is that coin’s JSON string (or {} if missing)
        value = coins_map.get(coin)
        if value is None:
            await ctx.send(sender, NewsSentimentResponse(ok=False, results_json=json.dumps({"error": f"Unknown coin {coin}"})))
            return
        # value is already a JSON string per your writer; pass through
        await ctx.send(sender, NewsSentimentResponse(ok=True, results_json=value))
        return

    # Full bundle reply: results_json is a JSON string of {coin: "<json_str>", ...}
    await ctx.send(sender, NewsSentimentResponse(ok=True, results_json=json.dumps(coins_map)))

agent.include(chat_proto, publish_manifest=True)

# =========================
# Run
# =========================

if __name__ == "__main__":
    print(f"Address: {agent.address}")
    agent.run()