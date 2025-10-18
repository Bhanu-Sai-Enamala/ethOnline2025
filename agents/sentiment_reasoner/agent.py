# # agent.py
# import os
# import json
# from typing import Optional, Dict, Any

# from uagents import Agent, Context

# from models import ReasonRequest, ReasonResponse

# AGENT_NAME = os.getenv("AGENT_NAME", "sentiment-reasoner")
# REASONER_SEED = os.getenv("REASONER_SEED", "reasoner-demo-seed")
# USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")

# # Path to your meTTa rules (used only if Hyperon is available)
# RULES_PATH = os.getenv("METTA_RULES", os.path.join("rules", "rebalance_rules.metta"))

# # Try to import Hyperon/MeTTa; if unavailable, we gracefully fall back.
# _METTA_OK = True
# try:
#     from hyperon import MeTTa  # type: ignore
# except Exception:
#     _METTA_OK = False
#     MeTTa = None  # type: ignore

# agent = Agent(
#     name=AGENT_NAME,
#     seed=REASONER_SEED,
#     mailbox=USE_MAILBOX,
#     publish_agent_details=True,
# )

# # --------------------------
# # Helpers
# # --------------------------
# def _clamp(x: float, lo: float, hi: float) -> float:
#     return max(lo, min(hi, x))

# def _extract_sentiment_risk(sentiment_json: Optional[str]) -> Optional[Dict[str, float]]:
#     """
#     Accepts either:
#       {"USDC": 0.xx, "USDT": 0.yy}
#     or the snapshot bundle you use (map coin -> JSON-string with .rolling.score in [-1,1]).
#     Returns normalized risk in [0..1] per coin (abs(score)), or None.
#     """
#     if not sentiment_json:
#         return None
#     try:
#         obj = json.loads(sentiment_json)

#         # Direct simple numeric map
#         if isinstance(obj, dict) and all(
#             k in obj for k in ("USDC", "USDT")
#         ) and isinstance(obj["USDC"], (int, float)):
#             return {"USDC": float(obj["USDC"]), "USDT": float(obj["USDT"])}

#         # Snapshot structure: each coin maps to JSON string or dict with rolling.score ∈ [-1,1]
#         out: Dict[str, float] = {}
#         for sym in ("USDC", "USDT"):
#             if sym in obj:
#                 snap = obj[sym]
#                 if isinstance(snap, str):
#                     snap = json.loads(snap)
#                 score = float(abs(snap.get("rolling", {}).get("score", 0.0)))
#                 out[sym] = _clamp(score, 0.0, 1.0)
#         return out or None
#     except Exception:
#         return None

# def _fallback_reason(
#     peg_payload_json: Optional[str],
#     liq_quote: Optional[float],
#     sentiment_json: Optional[str],
#     current_weights: Optional[Dict[str, float]],
# ) -> Dict[str, Any]:
#     # Parse peg risks
#     r_usdc, r_usdt = 0.40, 0.40
#     try:
#         peg = json.loads(peg_payload_json or "{}")
#         r = peg.get("risk", {})
#         r_usdc = float(r.get("USDC", r_usdc))
#         r_usdt = float(r.get("USDT", r_usdt))
#     except Exception:
#         pass

#     # Blend sentiment risk if present (30% weight)
#     s = _extract_sentiment_risk(sentiment_json)
#     if s:
#         r_usdc = 0.7 * r_usdc + 0.3 * float(s.get("USDC", 0.0))
#         r_usdt = 0.7 * r_usdt + 0.3 * float(s.get("USDT", 0.0))

#     # Simple tilt: base 50/50, tilt 10% max toward lower combined risk
#     tilt = _clamp(0.10 * (r_usdt - r_usdc), -0.10, 0.10)
#     w_usdc = _clamp(0.50 + tilt, 0.20, 0.80)

#     # Liquidity gate (if quote deviates from 1.0 by > 0.3%, halve the tilt)
#     if liq_quote is not None and abs(1.0 - float(liq_quote)) > 0.003:
#         w_usdc = 0.50 + 0.5 * (w_usdc - 0.50)

#     w_usdc = round(w_usdc, 4)
#     w_usdt = round(1.0 - w_usdc, 4)

#     worst = max(r_usdc, r_usdt)
#     if worst >= 0.60:
#         regime = "RED"
#     elif worst >= 0.35:
#         regime = "YELLOW"
#     else:
#         regime = "GREEN"

#     rationale = (
#         f"Fallback: combined risks USDC={r_usdc:.3f}, USDT={r_usdt:.3f}; regime {regime}; "
#         f"liquidity gate {'applied' if (liq_quote is not None and abs(1.0-float(liq_quote))>0.003) else 'not applied'}."
#     )
#     return dict(weights={"USDC": w_usdc, "USDT": w_usdt}, regime=regime, rationale=rationale)

# def _run_metta(peg_payload_json: str, liq_quote: Optional[float], sentiment_json: Optional[str]) -> Optional[Dict[str, Any]]:
#     """
#     If Hyperon/MeTTa is present and rules file exists, reason with rules.
#     Otherwise return None to trigger fallback.
#     """
#     if not _METTA_OK:
#         return None
#     if not os.path.exists(RULES_PATH):
#         return None

#     try:
#         m = MeTTa()  # type: ignore
#         # Load rules
#         m.run(f'!(load "{RULES_PATH}")')

#         # Parse inputs
#         peg = json.loads(peg_payload_json or "{}")
#         sent_risk = _extract_sentiment_risk(sentiment_json)

#         # Assert peg risks
#         r = peg.get("risk", {})
#         r_usdc = float(r.get("USDC", 0.0))
#         r_usdt = float(r.get("USDT", 0.0))
#         m.run(f"(assert! (peg-risk USDC {r_usdc}))")
#         m.run(f"(assert! (peg-risk USDT {r_usdt}))")

#         # Sentiment risk (fallback to 0 if missing)
#         s_usdc = float((sent_risk or {}).get("USDC", 0.0))
#         s_usdt = float((sent_risk or {}).get("USDT", 0.0))
#         m.run(f"(assert! (sentiment-risk USDC {s_usdc}))")
#         m.run(f"(assert! (sentiment-risk USDT {s_usdt}))")

#         # Liquidity quote, if present
#         if liq_quote is not None:
#             m.run(f"(assert! (liq-quote {float(liq_quote)}))")

#         # Query weights (see rules file for these targets)
#         # USDC weight:
#         wu = m.run("(target-weight-adjusted USDC ?w)")
#         if not wu:
#             return None

#         # Very lightweight parse from the S-expression-like atom
#         try:
#             text = str(wu[0])  # like "(target-weight-adjusted USDC 0.603)"
#             w_usdc = float(text.split()[-1].rstrip(')'))
#         except Exception:
#             return None

#         w_usdc = _clamp(w_usdc, 0.0, 1.0)
#         w_usdt = 1.0 - w_usdc

#         # Get regime if present
#         regime = "GREEN"
#         if m.run("(regime RED)"):
#             regime = "RED"
#         elif m.run("(regime YELLOW)"):
#             regime = "YELLOW"

#         # Optional rationale
#         rationale = "Reasoned by MeTTa."
#         rat = m.run("(rationale ?s)")
#         if rat:
#             rationale = str(rat[0])

#         return dict(
#             weights={"USDC": round(w_usdc, 4), "USDT": round(w_usdt, 4)},
#             regime=regime,
#             rationale=rationale,
#         )
#     except Exception:
#         return None

# # --------------------------
# # Handlers
# # --------------------------
# @agent.on_event("startup")
# async def on_start(ctx: Context):
#     ctx.logger.info(f"[{AGENT_NAME}] started. Mailbox={USE_MAILBOX}. MeTTa={'ON' if _METTA_OK else 'OFF'}")
#     if _METTA_OK and os.path.exists(RULES_PATH):
#         ctx.logger.info(f"[{AGENT_NAME}] Rules loaded from: {RULES_PATH}")
#     elif _METTA_OK:
#         ctx.logger.warning(f"[{AGENT_NAME}] MeTTa available, but rules file missing: {RULES_PATH}")
#     else:
#         ctx.logger.warning(f"[{AGENT_NAME}] Hyperon/MeTTa not installed — will use fallback logic.")

# @agent.on_message(model=ReasonRequest, replies=ReasonResponse)
# async def on_reason(ctx: Context, sender: str, msg: ReasonRequest):
#     ctx.logger.info(f"[{AGENT_NAME}] 📩 Received ReasonRequest")
#     try:
#         # Try MeTTa first (if present)
#         result = _run_metta(msg.peg_payload_json, msg.liq_quote, msg.sentiment_json)
#         if result is None:
#             # Fallback logic
#             fb = _fallback_reason(
#                 peg_payload_json=msg.peg_payload_json,
#                 liq_quote=msg.liq_quote,
#                 sentiment_json=msg.sentiment_json,
#                 current_weights=msg.current_weights,
#             )
#             await ctx.send(sender, ReasonResponse(
#                 ok=True,
#                 target_weights=fb["weights"],
#                 alert_level=fb["regime"],
#                 rationale=fb["rationale"],
#             ))
#             return

#         await ctx.send(sender, ReasonResponse(
#             ok=True,
#             target_weights=result["weights"],
#             alert_level=result["regime"],
#             rationale=result["rationale"],
#         ))
#     except Exception as e:
#         await ctx.send(sender, ReasonResponse(ok=False, error=str(e)))

# agent.py
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
LOG = logging.getLogger("sentiment-reasoner")

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
AGENT_NAME = os.getenv("AGENT_NAME", "sentiment-reasoner")
REASONER_SEED = os.getenv("REASONER_SEED", "reasoner-demo-seed")
USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")

# Path to your MeTTa rules (used only if Hyperon is available)
RULES_PATH = os.getenv("METTA_RULES", os.path.join("rules", "rebalance_rules.metta"))

# -----------------------------------------------------------------------------
# Try to import Hyperon/MeTTa; if unavailable, we gracefully fall back.
# -----------------------------------------------------------------------------
_METTA_OK = True
try:
    from hyperon import MeTTa  # type: ignore
    LOG.info("🧠 MeTTa (Hyperon) import OK")
except Exception as e:
    _METTA_OK = False
    MeTTa = None  # type: ignore
    LOG.warning(f"⚠️ MeTTa (Hyperon) not available: {e}")

# -----------------------------------------------------------------------------
# Agent
# -----------------------------------------------------------------------------
agent = Agent(
    name=AGENT_NAME,
    seed=REASONER_SEED,
    mailbox=USE_MAILBOX,
    publish_agent_details=True,
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _extract_sentiment_risk(sentiment_json: Optional[str]) -> Optional[Dict[str, float]]:
    """
    Accepts either:
      {"USDC": 0.xx, "USDT": 0.yy}
    or your snapshot bundle map: coin -> JSON-string (or dict) with .rolling.score ∈ [-1,1].
    Returns normalized risk in [0..1] per coin (abs(score)), or None.
    """
    if not sentiment_json:
        LOG.info("📰 No sentiment_json provided")
        return None
    try:
        obj = json.loads(sentiment_json)

        # Direct simple numeric map
        if (
            isinstance(obj, dict)
            and "USDC" in obj
            and "USDT" in obj
            and isinstance(obj["USDC"], (int, float))
        ):
            out = {"USDC": float(obj["USDC"]), "USDT": float(obj["USDT"])}
            LOG.info(f"📰 Sentiment numeric map: {out}")
            return out

        # Snapshot structure
        out: Dict[str, float] = {}
        for sym in ("USDC", "USDT"):
            if sym in obj:
                snap = obj[sym]
                if isinstance(snap, str):
                    snap = json.loads(snap)
                score = float(abs(snap.get("rolling", {}).get("score", 0.0)))
                out[sym] = _clamp(score, 0.0, 1.0)
        if out:
            LOG.info(f"📰 Sentiment snapshot map -> risk: {out}")
        else:
            LOG.info("📰 Sentiment snapshot present but no scores found; treating as None")
        return out or None
    except Exception as e:
        LOG.warning(f"📰 Sentiment parse error: {e}; treating as None")
        return None

def _fallback_reason(
    peg_payload_json: Optional[str],
    liq_quote: Optional[float],
    sentiment_json: Optional[str],
    current_weights: Optional[Dict[str, float]],
) -> Dict[str, Any]:
    # Parse peg risks
    r_usdc, r_usdt = 0.40, 0.40
    try:
        peg = json.loads(peg_payload_json or "{}")
        r = peg.get("risk", {})
        r_usdc = float(r.get("USDC", r_usdc))
        r_usdt = float(r.get("USDT", r_usdt))
    except Exception as e:
        LOG.warning(f"⚠️ Peg parse error: {e}; using defaults")

    # Blend sentiment risk if present (30% weight)
    s = _extract_sentiment_risk(sentiment_json)
    if s:
        r_before = (r_usdc, r_usdt)
        r_usdc = 0.7 * r_usdc + 0.3 * float(s.get("USDC", 0.0))
        r_usdt = 0.7 * r_usdt + 0.3 * float(s.get("USDT", 0.0))
        LOG.info(f"🧮 Combined risk (peg⊕sent): {r_before} -> {(r_usdc, r_usdt)}")
    else:
        LOG.info("🧮 No sentiment risk; using peg risks only")

    # Simple tilt: base 50/50, tilt 10% max toward lower combined risk
    tilt = _clamp(0.10 * (r_usdt - r_usdc), -0.10, 0.10)
    w_usdc = _clamp(0.50 + tilt, 0.20, 0.80)
    LOG.info(f"🎯 Fallback base weights before liquidity gate: USDC={w_usdc:.4f}, USDT={1.0-w_usdc:.4f}")

    # Liquidity gate (if quote deviates from 1.0 by > 0.3%, halve the tilt)
    if liq_quote is not None and abs(1.0 - float(liq_quote)) > 0.003:
        w_usdc = 0.50 + 0.5 * (w_usdc - 0.50)
        LOG.info(f"🚧 Liquidity gate applied (quote={liq_quote}); USDC={w_usdc:.4f}")

    w_usdc = round(w_usdc, 4)
    w_usdt = round(1.0 - w_usdc, 4)

    worst = max(r_usdc, r_usdt)
    if worst >= 0.60:
        regime = "RED"
    elif worst >= 0.35:
        regime = "YELLOW"
    else:
        regime = "GREEN"

    rationale = (
        f"Fallback: combined risks USDC={r_usdc:.3f}, USDT={r_usdt:.3f}; regime {regime}; "
        f"liquidity gate {'applied' if (liq_quote is not None and abs(1.0-float(liq_quote))>0.003) else 'not applied'}."
    )
    LOG.info(f"✅ Fallback result -> weights: USDC={w_usdc}, USDT={w_usdt}, regime={regime}")
    return dict(weights={"USDC": w_usdc, "USDT": w_usdt}, regime=regime, rationale=rationale)

def _run_metta(peg_payload_json: str, liq_quote: Optional[float], sentiment_json: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    If Hyperon/MeTTa is present and rules file exists, reason with rules.
    Otherwise return None to trigger fallback.
    """
    if not _METTA_OK:
        LOG.info("⛔ Skipping MeTTa because Hyperon not available")
        return None
    if not os.path.exists(RULES_PATH):
        LOG.warning(f"⚠️ MeTTa available, but rules file missing: {RULES_PATH}")
        return None

    try:
        m = MeTTa()  # type: ignore
        LOG.info("🧩 MeTTa engine created")

        # Load rules
        LOG.info(f"📚 Loading rules from {RULES_PATH}")
        load_out = m.run(f'!(load "{RULES_PATH}")')
        LOG.info(f"📚 Rules load result: {load_out}")

        # Parse inputs
        peg = json.loads(peg_payload_json or "{}")
        sent_risk = _extract_sentiment_risk(sentiment_json)

        # Assert peg risks
        r = peg.get("risk", {})
        r_usdc = float(r.get("USDC", 0.0))
        r_usdt = float(r.get("USDT", 0.0))
        LOG.info(f"⚙️ Asserting peg risks: USDC={r_usdc}, USDT={r_usdt}")
        m.run(f"(assert! (peg-risk USDC {r_usdc}))")
        m.run(f"(assert! (peg-risk USDT {r_usdt}))")

        # Sentiment risk (fallback to 0 if missing)
        s_usdc = float((sent_risk or {}).get("USDC", 0.0))
        s_usdt = float((sent_risk or {}).get("USDT", 0.0))
        LOG.info(f"⚙️ Asserting sentiment risks: USDC={s_usdc}, USDT={s_usdt}")
        m.run(f"(assert! (sentiment-risk USDC {s_usdc}))")
        m.run(f"(assert! (sentiment-risk USDT {s_usdt}))")

        # Liquidity quote, if present
        if liq_quote is not None:
            LOG.info(f"⚙️ Asserting liquidity quote: {liq_quote}")
            m.run(f"(assert! (liq-quote {float(liq_quote)}))")

        # Query weights (see rules file for these targets)
        LOG.info("🔎 Query: (target-weight-adjusted USDC ?w)")
        wu = m.run("(target-weight-adjusted USDC ?w)")
        LOG.info(f"🔎 Raw MeTTa result for USDC weight: {wu}")

        if not wu:
            LOG.warning("❌ MeTTa returned no weight result; falling back")
            return None

        # Lightweight parse from S-expression-like atom
        try:
            text = str(wu[0])  # e.g., "(target-weight-adjusted USDC 0.603)"
            w_usdc = float(text.split()[-1].rstrip(')'))
        except Exception as e:
            LOG.warning(f"❌ Could not parse MeTTa weight result '{wu}': {e}; falling back")
            return None

        w_usdc = _clamp(w_usdc, 0.0, 1.0)
        w_usdt = 1.0 - w_usdc

        # Get regime if present
        regime = "GREEN"
        if m.run("(regime RED)"):
            regime = "RED"
        elif m.run("(regime YELLOW)"):
            regime = "YELLOW"
        LOG.info(f"🎛 Regime from MeTTa: {regime}")

        # Optional rationale
        rationale = "Reasoned by MeTTa."
        rat = m.run("(rationale ?s)")
        if rat:
            rationale = str(rat[0])
        LOG.info(f"📝 MeTTa rationale: {rationale}")

        LOG.info(f"✅ MeTTa success -> weights: USDC={round(w_usdc,4)}, USDT={round(w_usdt,4)}, regime={regime}")
        return dict(
            weights={"USDC": round(w_usdc, 4), "USDT": round(w_usdt, 4)},
            regime=regime,
            rationale=rationale,
        )
    except Exception as e:
        LOG.warning(f"⚠️ MeTTa runtime error: {e}; falling back")
        return None

# -----------------------------------------------------------------------------
# Handlers
# -----------------------------------------------------------------------------
@agent.on_event("startup")
async def on_start(ctx: Context):
    ctx.logger.info(f"[{AGENT_NAME}] started. Mailbox={USE_MAILBOX}. MeTTa={'ON' if _METTA_OK else 'OFF'}")
    if _METTA_OK and os.path.exists(RULES_PATH):
        ctx.logger.info(f"[{AGENT_NAME}] Rules path: {RULES_PATH}")
    elif _METTA_OK:
        ctx.logger.warning(f"[{AGENT_NAME}] MeTTa available, but rules file missing: {RULES_PATH}")
    else:
        ctx.logger.warning(f"[{AGENT_NAME}] Hyperon/MeTTa not installed — will use fallback logic.")

@agent.on_message(model=ReasonRequest, replies=ReasonResponse)
async def on_reason(ctx: Context, sender: str, msg: ReasonRequest):
    ctx.logger.info(f"[{AGENT_NAME}] 📩 Received ReasonRequest")
    ctx.logger.info(
        f"[{AGENT_NAME}] Input sizes: peg={len(msg.peg_payload_json or '')}, "
        f"liq={'set' if msg.liq_quote is not None else 'none'}, "
        f"sentiment={'set' if msg.sentiment_json else 'none'}"
    )
    try:
        # Try MeTTa first (if present)
        result = _run_metta(msg.peg_payload_json, msg.liq_quote, msg.sentiment_json)
        if result is None:
            ctx.logger.warning(f"[{AGENT_NAME}] ↩️ MeTTa unavailable/empty — using Python fallback rules")
            fb = _fallback_reason(
                peg_payload_json=msg.peg_payload_json,
                liq_quote=msg.liq_quote,
                sentiment_json=msg.sentiment_json,
                current_weights=msg.current_weights,
            )
            await ctx.send(sender, ReasonResponse(
                ok=True,
                target_weights=fb["weights"],
                alert_level=fb["regime"],
                rationale=fb["rationale"],
            ))
            return

        ctx.logger.info(f"[{AGENT_NAME}] 🔁 Sending MeTTa-derived response")
        await ctx.send(sender, ReasonResponse(
            ok=True,
            target_weights=result["weights"],
            alert_level=result["regime"],
            rationale=result["rationale"],
        ))
    except Exception as e:
        ctx.logger.error(f"[{AGENT_NAME}] 💥 Reason handler error: {e}")
        await ctx.send(sender, ReasonResponse(ok=False, error=str(e)))