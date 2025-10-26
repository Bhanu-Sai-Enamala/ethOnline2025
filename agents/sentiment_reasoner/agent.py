

import os
import json
import logging
from typing import Optional, Dict, Any

from uagents import Agent, Context
from models import ReasonRequest, ReasonResponse

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("reasoner-10coin")

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
AGENT_NAME = os.getenv("AGENT_NAME", "reasoner-10coin")
REASONER_SEED = os.getenv("REASONER_SEED", "reasoner-demo-seed")
USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")

# -----------------------------------------------------------------------------
# Hyperon/MeTTa import and KB
# -----------------------------------------------------------------------------
_METTA_OK = True
try:
    from hyperon import MeTTa  # type: ignore
    from knowledge import initialize_knowledge_graph, read_policy  # type: ignore
    LOG.info("🧠 MeTTa + knowledge.py import OK")
except Exception as e:
    _METTA_OK = False
    MeTTa = None  # type: ignore
    initialize_knowledge_graph = None  # type: ignore
    read_policy = None  # type: ignore
    LOG.warning(f"⚠️ MeTTa/knowledge unavailable: {e}")

# -----------------------------------------------------------------------------
# Agent init
# -----------------------------------------------------------------------------
agent = Agent(
    name=AGENT_NAME,
    seed=REASONER_SEED,
    mailbox=USE_MAILBOX,
    publish_agent_details=True,
)

# -----------------------------------------------------------------------------
# Coin universe
# -----------------------------------------------------------------------------
COINS = ["USDC", "USDT", "DAI", "FDUSD", "BUSD", "TUSD", "USDP", "PYUSD", "USDD", "GUSD"]

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _extract_sentiment_risk(sentiment_json: Optional[str]) -> Dict[str, float]:
    """Extract absolute sentiment scores [-1,1] → [0,1] for all coins."""
    risks: Dict[str, float] = {c: 0.0 for c in COINS}
    if not sentiment_json:
        return risks
    try:
        obj = json.loads(sentiment_json)
        for sym in COINS:
            snap = obj.get(sym)
            if not snap:
                continue
            if isinstance(snap, str):
                snap = json.loads(snap)
            score = float(abs(snap.get("rolling", {}).get("score", 0.0)))
            risks[sym] = _clamp(score, 0.0, 1.0)
    except Exception as e:
        LOG.warning(f"Sentiment parse failed: {e}")
    return risks

def _blend_risks(peg_json: Optional[str], sentiment_json: Optional[str], policy: Dict[str, float]) -> Dict[str, float]:
    """Weighted blend of peg + sentiment risk per coin."""
    risks: Dict[str, float] = {}
    sent_weight = policy.get("sentiment_weight", 0.3)
    try:
        peg = json.loads(peg_json or "{}")
        peg_risk = peg.get("risk", {})
    except Exception:
        peg_risk = {}

    sent_risk = _extract_sentiment_risk(sentiment_json)
    for c in COINS:
        pr = float(peg_risk.get(c, 0.0))
        sr = sent_risk.get(c, 0.0)
        combined = (1 - sent_weight) * pr + sent_weight * sr
        risks[c] = round(combined, 4)
    return risks

def _derive_weights(risks: Dict[str, float], liq_quote: Optional[float], policy: Dict[str, float]) -> Dict[str, float]:
    """Compute normalized weights inversely proportional to risk, adjusted by liquidity gate."""
    inv = {c: 1.0 / max(r, 1e-6) for c, r in risks.items()}
    total = sum(inv.values())
    base = {c: inv[c] / total for c in COINS}

    # liquidity gate dampens deviations if quote deviates > threshold
    if liq_quote is not None and abs(1.0 - liq_quote) > policy["liq_gate_threshold"]:
        mean_w = 1.0 / len(COINS)
        for c in COINS:
            base[c] = 0.5 * base[c] + 0.5 * mean_w

    # clamp to min/max
    w_min, w_max = policy["weight_min"], policy["weight_max"]
    normed = {}
    s = sum(_clamp(v, w_min, w_max) for v in base.values())
    for c in COINS:
        normed[c] = round(_clamp(base[c], w_min, w_max) / s, 4)
    return normed

def _detect_regime(risks: Dict[str, float], policy: Dict[str, float]) -> str:
    """Regime based on worst risk."""
    worst = max(risks.values()) if risks else 0.0
    if worst >= policy["thr_red"]:
        return "RED"
    elif worst >= policy["thr_yellow"]:
        return "YELLOW"
    return "GREEN"

# -----------------------------------------------------------------------------
# Reasoning core
# -----------------------------------------------------------------------------
def _reason_with_knowledge(peg_json: str, liq_quote: Optional[float], sentiment_json: Optional[str]) -> Dict[str, Any]:
    if not _METTA_OK or not initialize_knowledge_graph:
        LOG.warning("⚠️ Running fallback reasoner (no MeTTa)")
        return _fallback_reason(peg_json, liq_quote, sentiment_json, {})

    m = MeTTa()  # type: ignore
    initialize_knowledge_graph(m)
    policy = read_policy(m)

    # Blend peg + sentiment risks
    risks = _blend_risks(peg_json, sentiment_json, policy)

    # Compute weights inversely to risk
    weights = _derive_weights(risks, liq_quote, policy)
    regime = _detect_regime(risks, policy)

    rationale = (
        f"Knowledge-graph mode: MeTTa policy used. "
        f"Combined risks derived from peg⊕sentiment. "
        f"Regime={regime}, liquidity gate applied if deviation>{policy['liq_gate_threshold']*100:.2f}%."
    )

    return dict(weights=weights, regime=regime, rationale=rationale)

def _fallback_reason(peg_json: str, liq_quote: Optional[float], sentiment_json: Optional[str], _: Dict) -> Dict[str, Any]:
    """Simplified fallback: if MeTTa unavailable."""
    try:
        peg = json.loads(peg_json or "{}")
        peg_risk = peg.get("risk", {})
    except Exception:
        peg_risk = {}
    sent_risk = _extract_sentiment_risk(sentiment_json)
    risks = {}
    for c in COINS:
        risks[c] = 0.7 * float(peg_risk.get(c, 0.0)) + 0.3 * sent_risk.get(c, 0.0)
    s = sum(1.0 / max(r, 1e-6) for r in risks.values())
    weights = {c: round((1.0 / max(r, 1e-6)) / s, 4) for c, r in risks.items()}
    regime = "GREEN" if max(risks.values()) < 0.35 else ("YELLOW" if max(risks.values()) < 0.6 else "RED")
    rationale = "Fallback: no MeTTa, simple inverse-risk weighting."
    return dict(weights=weights, regime=regime, rationale=rationale)

# -----------------------------------------------------------------------------
# Handlers
# -----------------------------------------------------------------------------
@agent.on_event("startup")
async def on_start(ctx: Context):
    ctx.logger.info(f"[{AGENT_NAME}] started. Mailbox={USE_MAILBOX}. MeTTa={'ON' if _METTA_OK else 'OFF'}")
    ctx.logger.info(f"[{AGENT_NAME}] 10-coin reasoner online. Coins: {', '.join(COINS)}")

@agent.on_message(model=ReasonRequest, replies=ReasonResponse)
async def on_reason(ctx: Context, sender: str, msg: ReasonRequest):
    ctx.logger.info(f"[{AGENT_NAME}] 📩 Received ReasonRequest")

    try:
        result = _reason_with_knowledge(msg.peg_payload_json, msg.liq_quote, msg.sentiment_json)
        await ctx.send(sender, ReasonResponse(
            ok=True,
            target_weights=result["weights"],
            alert_level=result["regime"],
            rationale=result["rationale"],
        ))
        ctx.logger.info(f"[{AGENT_NAME}] ✅ Reply sent regime={result['regime']}")
    except Exception as e:
        ctx.logger.error(f"[{AGENT_NAME}] 💥 Error: {e}")
        await ctx.send(sender, ReasonResponse(ok=False, error=str(e)))

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Address: {agent.address}")
    agent.run()