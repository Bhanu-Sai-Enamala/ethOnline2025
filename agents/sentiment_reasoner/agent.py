# # # # agent.py
# # # import os
# # # import json
# # # from typing import Optional, Dict, Any

# # # from uagents import Agent, Context

# # # from models import ReasonRequest, ReasonResponse

# # # AGENT_NAME = os.getenv("AGENT_NAME", "sentiment-reasoner")
# # # REASONER_SEED = os.getenv("REASONER_SEED", "reasoner-demo-seed")
# # # USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")

# # # # Path to your meTTa rules (used only if Hyperon is available)
# # # RULES_PATH = os.getenv("METTA_RULES", os.path.join("rules", "rebalance_rules.metta"))

# # # # Try to import Hyperon/MeTTa; if unavailable, we gracefully fall back.
# # # _METTA_OK = True
# # # try:
# # #     from hyperon import MeTTa  # type: ignore
# # # except Exception:
# # #     _METTA_OK = False
# # #     MeTTa = None  # type: ignore

# # # agent = Agent(
# # #     name=AGENT_NAME,
# # #     seed=REASONER_SEED,
# # #     mailbox=USE_MAILBOX,
# # #     publish_agent_details=True,
# # # )

# # # # --------------------------
# # # # Helpers
# # # # --------------------------
# # # def _clamp(x: float, lo: float, hi: float) -> float:
# # #     return max(lo, min(hi, x))

# # # def _extract_sentiment_risk(sentiment_json: Optional[str]) -> Optional[Dict[str, float]]:
# # #     """
# # #     Accepts either:
# # #       {"USDC": 0.xx, "USDT": 0.yy}
# # #     or the snapshot bundle you use (map coin -> JSON-string with .rolling.score in [-1,1]).
# # #     Returns normalized risk in [0..1] per coin (abs(score)), or None.
# # #     """
# # #     if not sentiment_json:
# # #         return None
# # #     try:
# # #         obj = json.loads(sentiment_json)

# # #         # Direct simple numeric map
# # #         if isinstance(obj, dict) and all(
# # #             k in obj for k in ("USDC", "USDT")
# # #         ) and isinstance(obj["USDC"], (int, float)):
# # #             return {"USDC": float(obj["USDC"]), "USDT": float(obj["USDT"])}

# # #         # Snapshot structure: each coin maps to JSON string or dict with rolling.score ∈ [-1,1]
# # #         out: Dict[str, float] = {}
# # #         for sym in ("USDC", "USDT"):
# # #             if sym in obj:
# # #                 snap = obj[sym]
# # #                 if isinstance(snap, str):
# # #                     snap = json.loads(snap)
# # #                 score = float(abs(snap.get("rolling", {}).get("score", 0.0)))
# # #                 out[sym] = _clamp(score, 0.0, 1.0)
# # #         return out or None
# # #     except Exception:
# # #         return None

# # # def _fallback_reason(
# # #     peg_payload_json: Optional[str],
# # #     liq_quote: Optional[float],
# # #     sentiment_json: Optional[str],
# # #     current_weights: Optional[Dict[str, float]],
# # # ) -> Dict[str, Any]:
# # #     # Parse peg risks
# # #     r_usdc, r_usdt = 0.40, 0.40
# # #     try:
# # #         peg = json.loads(peg_payload_json or "{}")
# # #         r = peg.get("risk", {})
# # #         r_usdc = float(r.get("USDC", r_usdc))
# # #         r_usdt = float(r.get("USDT", r_usdt))
# # #     except Exception:
# # #         pass

# # #     # Blend sentiment risk if present (30% weight)
# # #     s = _extract_sentiment_risk(sentiment_json)
# # #     if s:
# # #         r_usdc = 0.7 * r_usdc + 0.3 * float(s.get("USDC", 0.0))
# # #         r_usdt = 0.7 * r_usdt + 0.3 * float(s.get("USDT", 0.0))

# # #     # Simple tilt: base 50/50, tilt 10% max toward lower combined risk
# # #     tilt = _clamp(0.10 * (r_usdt - r_usdc), -0.10, 0.10)
# # #     w_usdc = _clamp(0.50 + tilt, 0.20, 0.80)

# # #     # Liquidity gate (if quote deviates from 1.0 by > 0.3%, halve the tilt)
# # #     if liq_quote is not None and abs(1.0 - float(liq_quote)) > 0.003:
# # #         w_usdc = 0.50 + 0.5 * (w_usdc - 0.50)

# # #     w_usdc = round(w_usdc, 4)
# # #     w_usdt = round(1.0 - w_usdc, 4)

# # #     worst = max(r_usdc, r_usdt)
# # #     if worst >= 0.60:
# # #         regime = "RED"
# # #     elif worst >= 0.35:
# # #         regime = "YELLOW"
# # #     else:
# # #         regime = "GREEN"

# # #     rationale = (
# # #         f"Fallback: combined risks USDC={r_usdc:.3f}, USDT={r_usdt:.3f}; regime {regime}; "
# # #         f"liquidity gate {'applied' if (liq_quote is not None and abs(1.0-float(liq_quote))>0.003) else 'not applied'}."
# # #     )
# # #     return dict(weights={"USDC": w_usdc, "USDT": w_usdt}, regime=regime, rationale=rationale)

# # # def _run_metta(peg_payload_json: str, liq_quote: Optional[float], sentiment_json: Optional[str]) -> Optional[Dict[str, Any]]:
# # #     """
# # #     If Hyperon/MeTTa is present and rules file exists, reason with rules.
# # #     Otherwise return None to trigger fallback.
# # #     """
# # #     if not _METTA_OK:
# # #         return None
# # #     if not os.path.exists(RULES_PATH):
# # #         return None

# # #     try:
# # #         m = MeTTa()  # type: ignore
# # #         # Load rules
# # #         m.run(f'!(load "{RULES_PATH}")')

# # #         # Parse inputs
# # #         peg = json.loads(peg_payload_json or "{}")
# # #         sent_risk = _extract_sentiment_risk(sentiment_json)

# # #         # Assert peg risks
# # #         r = peg.get("risk", {})
# # #         r_usdc = float(r.get("USDC", 0.0))
# # #         r_usdt = float(r.get("USDT", 0.0))
# # #         m.run(f"(assert! (peg-risk USDC {r_usdc}))")
# # #         m.run(f"(assert! (peg-risk USDT {r_usdt}))")

# # #         # Sentiment risk (fallback to 0 if missing)
# # #         s_usdc = float((sent_risk or {}).get("USDC", 0.0))
# # #         s_usdt = float((sent_risk or {}).get("USDT", 0.0))
# # #         m.run(f"(assert! (sentiment-risk USDC {s_usdc}))")
# # #         m.run(f"(assert! (sentiment-risk USDT {s_usdt}))")

# # #         # Liquidity quote, if present
# # #         if liq_quote is not None:
# # #             m.run(f"(assert! (liq-quote {float(liq_quote)}))")

# # #         # Query weights (see rules file for these targets)
# # #         # USDC weight:
# # #         wu = m.run("(target-weight-adjusted USDC ?w)")
# # #         if not wu:
# # #             return None

# # #         # Very lightweight parse from the S-expression-like atom
# # #         try:
# # #             text = str(wu[0])  # like "(target-weight-adjusted USDC 0.603)"
# # #             w_usdc = float(text.split()[-1].rstrip(')'))
# # #         except Exception:
# # #             return None

# # #         w_usdc = _clamp(w_usdc, 0.0, 1.0)
# # #         w_usdt = 1.0 - w_usdc

# # #         # Get regime if present
# # #         regime = "GREEN"
# # #         if m.run("(regime RED)"):
# # #             regime = "RED"
# # #         elif m.run("(regime YELLOW)"):
# # #             regime = "YELLOW"

# # #         # Optional rationale
# # #         rationale = "Reasoned by MeTTa."
# # #         rat = m.run("(rationale ?s)")
# # #         if rat:
# # #             rationale = str(rat[0])

# # #         return dict(
# # #             weights={"USDC": round(w_usdc, 4), "USDT": round(w_usdt, 4)},
# # #             regime=regime,
# # #             rationale=rationale,
# # #         )
# # #     except Exception:
# # #         return None

# # # # --------------------------
# # # # Handlers
# # # # --------------------------
# # # @agent.on_event("startup")
# # # async def on_start(ctx: Context):
# # #     ctx.logger.info(f"[{AGENT_NAME}] started. Mailbox={USE_MAILBOX}. MeTTa={'ON' if _METTA_OK else 'OFF'}")
# # #     if _METTA_OK and os.path.exists(RULES_PATH):
# # #         ctx.logger.info(f"[{AGENT_NAME}] Rules loaded from: {RULES_PATH}")
# # #     elif _METTA_OK:
# # #         ctx.logger.warning(f"[{AGENT_NAME}] MeTTa available, but rules file missing: {RULES_PATH}")
# # #     else:
# # #         ctx.logger.warning(f"[{AGENT_NAME}] Hyperon/MeTTa not installed — will use fallback logic.")

# # # @agent.on_message(model=ReasonRequest, replies=ReasonResponse)
# # # async def on_reason(ctx: Context, sender: str, msg: ReasonRequest):
# # #     ctx.logger.info(f"[{AGENT_NAME}] 📩 Received ReasonRequest")
# # #     try:
# # #         # Try MeTTa first (if present)
# # #         result = _run_metta(msg.peg_payload_json, msg.liq_quote, msg.sentiment_json)
# # #         if result is None:
# # #             # Fallback logic
# # #             fb = _fallback_reason(
# # #                 peg_payload_json=msg.peg_payload_json,
# # #                 liq_quote=msg.liq_quote,
# # #                 sentiment_json=msg.sentiment_json,
# # #                 current_weights=msg.current_weights,
# # #             )
# # #             await ctx.send(sender, ReasonResponse(
# # #                 ok=True,
# # #                 target_weights=fb["weights"],
# # #                 alert_level=fb["regime"],
# # #                 rationale=fb["rationale"],
# # #             ))
# # #             return

# # #         await ctx.send(sender, ReasonResponse(
# # #             ok=True,
# # #             target_weights=result["weights"],
# # #             alert_level=result["regime"],
# # #             rationale=result["rationale"],
# # #         ))
# # #     except Exception as e:
# # #         await ctx.send(sender, ReasonResponse(ok=False, error=str(e)))

# # # agent.py
# # import os
# # import json
# # import logging
# # from typing import Optional, Dict, Any

# # from uagents import Agent, Context
# # from models import ReasonRequest, ReasonResponse

# # # -----------------------------------------------------------------------------
# # # Logging
# # # -----------------------------------------------------------------------------
# # logging.basicConfig(level=logging.INFO)
# # LOG = logging.getLogger("sentiment-reasoner")

# # # -----------------------------------------------------------------------------
# # # Config
# # # -----------------------------------------------------------------------------
# # AGENT_NAME = os.getenv("AGENT_NAME", "sentiment-reasoner")
# # REASONER_SEED = os.getenv("REASONER_SEED", "reasoner-demo-seed")
# # USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")

# # # Path to your MeTTa rules (used only if Hyperon is available)
# # RULES_PATH = os.getenv("METTA_RULES", os.path.join("rules", "rebalance_rules.metta"))

# # # -----------------------------------------------------------------------------
# # # Try to import Hyperon/MeTTa; if unavailable, we gracefully fall back.
# # # -----------------------------------------------------------------------------
# # _METTA_OK = True
# # try:
# #     from hyperon import MeTTa  # type: ignore
# #     LOG.info("🧠 MeTTa (Hyperon) import OK")
# # except Exception as e:
# #     _METTA_OK = False
# #     MeTTa = None  # type: ignore
# #     LOG.warning(f"⚠️ MeTTa (Hyperon) not available: {e}")

# # # -----------------------------------------------------------------------------
# # # Agent
# # # -----------------------------------------------------------------------------
# # agent = Agent(
# #     name=AGENT_NAME,
# #     seed=REASONER_SEED,
# #     mailbox=USE_MAILBOX,
# #     publish_agent_details=True,
# # )

# # # -----------------------------------------------------------------------------
# # # Helpers
# # # -----------------------------------------------------------------------------
# # def _clamp(x: float, lo: float, hi: float) -> float:
# #     return max(lo, min(hi, x))

# # def _extract_sentiment_risk(sentiment_json: Optional[str]) -> Optional[Dict[str, float]]:
# #     """
# #     Accepts either:
# #       {"USDC": 0.xx, "USDT": 0.yy}
# #     or your snapshot bundle map: coin -> JSON-string (or dict) with .rolling.score ∈ [-1,1].
# #     Returns normalized risk in [0..1] per coin (abs(score)), or None.
# #     """
# #     if not sentiment_json:
# #         LOG.info("📰 No sentiment_json provided")
# #         return None
# #     try:
# #         obj = json.loads(sentiment_json)

# #         # Direct simple numeric map
# #         if (
# #             isinstance(obj, dict)
# #             and "USDC" in obj
# #             and "USDT" in obj
# #             and isinstance(obj["USDC"], (int, float))
# #         ):
# #             out = {"USDC": float(obj["USDC"]), "USDT": float(obj["USDT"])}
# #             LOG.info(f"📰 Sentiment numeric map: {out}")
# #             return out

# #         # Snapshot structure
# #         out: Dict[str, float] = {}
# #         for sym in ("USDC", "USDT"):
# #             if sym in obj:
# #                 snap = obj[sym]
# #                 if isinstance(snap, str):
# #                     snap = json.loads(snap)
# #                 score = float(abs(snap.get("rolling", {}).get("score", 0.0)))
# #                 out[sym] = _clamp(score, 0.0, 1.0)
# #         if out:
# #             LOG.info(f"📰 Sentiment snapshot map -> risk: {out}")
# #         else:
# #             LOG.info("📰 Sentiment snapshot present but no scores found; treating as None")
# #         return out or None
# #     except Exception as e:
# #         LOG.warning(f"📰 Sentiment parse error: {e}; treating as None")
# #         return None

# # def _fallback_reason(
# #     peg_payload_json: Optional[str],
# #     liq_quote: Optional[float],
# #     sentiment_json: Optional[str],
# #     current_weights: Optional[Dict[str, float]],
# # ) -> Dict[str, Any]:
# #     # Parse peg risks
# #     r_usdc, r_usdt = 0.40, 0.40
# #     try:
# #         peg = json.loads(peg_payload_json or "{}")
# #         r = peg.get("risk", {})
# #         r_usdc = float(r.get("USDC", r_usdc))
# #         r_usdt = float(r.get("USDT", r_usdt))
# #     except Exception as e:
# #         LOG.warning(f"⚠️ Peg parse error: {e}; using defaults")

# #     # Blend sentiment risk if present (30% weight)
# #     s = _extract_sentiment_risk(sentiment_json)
# #     if s:
# #         r_before = (r_usdc, r_usdt)
# #         r_usdc = 0.7 * r_usdc + 0.3 * float(s.get("USDC", 0.0))
# #         r_usdt = 0.7 * r_usdt + 0.3 * float(s.get("USDT", 0.0))
# #         LOG.info(f"🧮 Combined risk (peg⊕sent): {r_before} -> {(r_usdc, r_usdt)}")
# #     else:
# #         LOG.info("🧮 No sentiment risk; using peg risks only")

# #     # Simple tilt: base 50/50, tilt 10% max toward lower combined risk
# #     tilt = _clamp(0.10 * (r_usdt - r_usdc), -0.10, 0.10)
# #     w_usdc = _clamp(0.50 + tilt, 0.20, 0.80)
# #     LOG.info(f"🎯 Fallback base weights before liquidity gate: USDC={w_usdc:.4f}, USDT={1.0-w_usdc:.4f}")

# #     # Liquidity gate (if quote deviates from 1.0 by > 0.3%, halve the tilt)
# #     if liq_quote is not None and abs(1.0 - float(liq_quote)) > 0.003:
# #         w_usdc = 0.50 + 0.5 * (w_usdc - 0.50)
# #         LOG.info(f"🚧 Liquidity gate applied (quote={liq_quote}); USDC={w_usdc:.4f}")

# #     w_usdc = round(w_usdc, 4)
# #     w_usdt = round(1.0 - w_usdc, 4)

# #     worst = max(r_usdc, r_usdt)
# #     if worst >= 0.60:
# #         regime = "RED"
# #     elif worst >= 0.35:
# #         regime = "YELLOW"
# #     else:
# #         regime = "GREEN"

# #     rationale = (
# #         f"Fallback: combined risks USDC={r_usdc:.3f}, USDT={r_usdt:.3f}; regime {regime}; "
# #         f"liquidity gate {'applied' if (liq_quote is not None and abs(1.0-float(liq_quote))>0.003) else 'not applied'}."
# #     )
# #     LOG.info(f"✅ Fallback result -> weights: USDC={w_usdc}, USDT={w_usdt}, regime={regime}")
# #     return dict(weights={"USDC": w_usdc, "USDT": w_usdt}, regime=regime, rationale=rationale)

# # def _run_metta(peg_payload_json: str, liq_quote: Optional[float], sentiment_json: Optional[str]) -> Optional[Dict[str, Any]]:
# #     """
# #     If Hyperon/MeTTa is present and rules file exists, reason with rules.
# #     Otherwise return None to trigger fallback.
# #     """
# #     if not _METTA_OK:
# #         LOG.info("⛔ Skipping MeTTa because Hyperon not available")
# #         return None
# #     if not os.path.exists(RULES_PATH):
# #         LOG.warning(f"⚠️ MeTTa available, but rules file missing: {RULES_PATH}")
# #         return None

# #     try:
# #         m = MeTTa()  # type: ignore
# #         LOG.info("🧩 MeTTa engine created")

# #         # Load rules
# #         LOG.info(f"📚 Loading rules from {RULES_PATH}")
# #         load_out = m.run(f'!(load "{RULES_PATH}")')
# #         LOG.info(f"📚 Rules load result: {load_out}")

# #         # Parse inputs
# #         peg = json.loads(peg_payload_json or "{}")
# #         sent_risk = _extract_sentiment_risk(sentiment_json)

# #         # Assert peg risks
# #         r = peg.get("risk", {})
# #         r_usdc = float(r.get("USDC", 0.0))
# #         r_usdt = float(r.get("USDT", 0.0))
# #         LOG.info(f"⚙️ Asserting peg risks: USDC={r_usdc}, USDT={r_usdt}")
# #         m.run(f"(assert! (peg-risk USDC {r_usdc}))")
# #         m.run(f"(assert! (peg-risk USDT {r_usdt}))")

# #         # Sentiment risk (fallback to 0 if missing)
# #         s_usdc = float((sent_risk or {}).get("USDC", 0.0))
# #         s_usdt = float((sent_risk or {}).get("USDT", 0.0))
# #         LOG.info(f"⚙️ Asserting sentiment risks: USDC={s_usdc}, USDT={s_usdt}")
# #         m.run(f"(assert! (sentiment-risk USDC {s_usdc}))")
# #         m.run(f"(assert! (sentiment-risk USDT {s_usdt}))")

# #         # Liquidity quote, if present
# #         if liq_quote is not None:
# #             LOG.info(f"⚙️ Asserting liquidity quote: {liq_quote}")
# #             m.run(f"(assert! (liq-quote {float(liq_quote)}))")

# #         # Query weights (see rules file for these targets)
# #         LOG.info("🔎 Query: (target-weight-adjusted USDC ?w)")
# #         wu = m.run("(target-weight-adjusted USDC ?w)")
# #         LOG.info(f"🔎 Raw MeTTa result for USDC weight: {wu}")

# #         if not wu:
# #             LOG.warning("❌ MeTTa returned no weight result; falling back")
# #             return None

# #         # Lightweight parse from S-expression-like atom
# #         try:
# #             text = str(wu[0])  # e.g., "(target-weight-adjusted USDC 0.603)"
# #             w_usdc = float(text.split()[-1].rstrip(')'))
# #         except Exception as e:
# #             LOG.warning(f"❌ Could not parse MeTTa weight result '{wu}': {e}; falling back")
# #             return None

# #         w_usdc = _clamp(w_usdc, 0.0, 1.0)
# #         w_usdt = 1.0 - w_usdc

# #         # Get regime if present
# #         regime = "GREEN"
# #         if m.run("(regime RED)"):
# #             regime = "RED"
# #         elif m.run("(regime YELLOW)"):
# #             regime = "YELLOW"
# #         LOG.info(f"🎛 Regime from MeTTa: {regime}")

# #         # Optional rationale
# #         rationale = "Reasoned by MeTTa."
# #         rat = m.run("(rationale ?s)")
# #         if rat:
# #             rationale = str(rat[0])
# #         LOG.info(f"📝 MeTTa rationale: {rationale}")

# #         LOG.info(f"✅ MeTTa success -> weights: USDC={round(w_usdc,4)}, USDT={round(w_usdt,4)}, regime={regime}")
# #         return dict(
# #             weights={"USDC": round(w_usdc, 4), "USDT": round(w_usdt, 4)},
# #             regime=regime,
# #             rationale=rationale,
# #         )
# #     except Exception as e:
# #         LOG.warning(f"⚠️ MeTTa runtime error: {e}; falling back")
# #         return None

# # # -----------------------------------------------------------------------------
# # # Handlers
# # # -----------------------------------------------------------------------------
# # @agent.on_event("startup")
# # async def on_start(ctx: Context):
# #     ctx.logger.info(f"[{AGENT_NAME}] started. Mailbox={USE_MAILBOX}. MeTTa={'ON' if _METTA_OK else 'OFF'}")
# #     if _METTA_OK and os.path.exists(RULES_PATH):
# #         ctx.logger.info(f"[{AGENT_NAME}] Rules path: {RULES_PATH}")
# #     elif _METTA_OK:
# #         ctx.logger.warning(f"[{AGENT_NAME}] MeTTa available, but rules file missing: {RULES_PATH}")
# #     else:
# #         ctx.logger.warning(f"[{AGENT_NAME}] Hyperon/MeTTa not installed — will use fallback logic.")

# # @agent.on_message(model=ReasonRequest, replies=ReasonResponse)
# # async def on_reason(ctx: Context, sender: str, msg: ReasonRequest):
# #     ctx.logger.info(f"[{AGENT_NAME}] 📩 Received ReasonRequest")
# #     ctx.logger.info(
# #         f"[{AGENT_NAME}] Input sizes: peg={len(msg.peg_payload_json or '')}, "
# #         f"liq={'set' if msg.liq_quote is not None else 'none'}, "
# #         f"sentiment={'set' if msg.sentiment_json else 'none'}"
# #     )
# #     try:
# #         # Try MeTTa first (if present)
# #         result = _run_metta(msg.peg_payload_json, msg.liq_quote, msg.sentiment_json)
# #         if result is None:
# #             ctx.logger.warning(f"[{AGENT_NAME}] ↩️ MeTTa unavailable/empty — using Python fallback rules")
# #             fb = _fallback_reason(
# #                 peg_payload_json=msg.peg_payload_json,
# #                 liq_quote=msg.liq_quote,
# #                 sentiment_json=msg.sentiment_json,
# #                 current_weights=msg.current_weights,
# #             )
# #             await ctx.send(sender, ReasonResponse(
# #                 ok=True,
# #                 target_weights=fb["weights"],
# #                 alert_level=fb["regime"],
# #                 rationale=fb["rationale"],
# #             ))
# #             return

# #         ctx.logger.info(f"[{AGENT_NAME}] 🔁 Sending MeTTa-derived response")
# #         await ctx.send(sender, ReasonResponse(
# #             ok=True,
# #             target_weights=result["weights"],
# #             alert_level=result["regime"],
# #             rationale=result["rationale"],
# #         ))
# #     except Exception as e:
# #         ctx.logger.error(f"[{AGENT_NAME}] 💥 Reason handler error: {e}")
# #         await ctx.send(sender, ReasonResponse(ok=False, error=str(e)))

# # agent.py — MeTTa-graph first, no external .metta rules file
# import os
# import json
# import logging
# from typing import Optional, Dict, Any

# from uagents import Agent, Context
# from models import ReasonRequest, ReasonResponse

# # -----------------------------------------------------------------------------
# # Logging
# # -----------------------------------------------------------------------------
# logging.basicConfig(level=logging.INFO)
# LOG = logging.getLogger("sentiment-reasoner")

# # -----------------------------------------------------------------------------
# # Config
# # -----------------------------------------------------------------------------
# AGENT_NAME = os.getenv("AGENT_NAME", "sentiment-reasoner")
# REASONER_SEED = os.getenv("REASONER_SEED", "reasoner-demo-seed")
# USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")

# # -----------------------------------------------------------------------------
# # Try to import Hyperon/MeTTa; we will initialize a local knowledge graph
# # -----------------------------------------------------------------------------
# _METTA_OK = True
# try:
#     from hyperon import MeTTa  # type: ignore
#     # local knowledge base (next to this file)
#     try:
#         from knowledge import initialize_knowledge_graph  # type: ignore
#     except Exception as e:
#         initialize_knowledge_graph = None  # type: ignore
#         LOG.warning(f"⚠️ knowledge.py not found/loaded: {e}")
#     LOG.info("🧠 MeTTa (Hyperon) import OK")
# except Exception as e:
#     _METTA_OK = False
#     MeTTa = None  # type: ignore
#     initialize_knowledge_graph = None  # type: ignore
#     LOG.warning(f"⚠️ MeTTa (Hyperon) not available: {e}")

# # -----------------------------------------------------------------------------
# # Agent
# # -----------------------------------------------------------------------------
# agent = Agent(
#     name=AGENT_NAME,
#     seed=REASONER_SEED,
#     mailbox=USE_MAILBOX,
#     publish_agent_details=True,
# )

# # -----------------------------------------------------------------------------
# # Helpers
# # -----------------------------------------------------------------------------
# def _clamp(x: float, lo: float, hi: float) -> float:
#     return max(lo, min(hi, x))

# def _extract_sentiment_risk(sentiment_json: Optional[str]) -> Optional[Dict[str, float]]:
#     """
#     Accepts either:
#       {"USDC": 0.xx, "USDT": 0.yy}
#     or your snapshot bundle map: coin -> JSON-string (or dict) with .rolling.score ∈ [-1,1].
#     Returns normalized risk in [0..1] per coin (abs(score)), or None.
#     """
#     if not sentiment_json:
#         LOG.info("📰 No sentiment_json provided")
#         return None
#     try:
#         obj = json.loads(sentiment_json)

#         # Direct simple numeric map
#         if (
#             isinstance(obj, dict)
#             and "USDC" in obj
#             and "USDT" in obj
#             and isinstance(obj["USDC"], (int, float))
#         ):
#             out = {"USDC": float(obj["USDC"]), "USDT": float(obj["USDT"])}
#             LOG.info(f"📰 Sentiment numeric map: {out}")
#             return out

#         # Snapshot structure
#         out: Dict[str, float] = {}
#         for sym in ("USDC", "USDT"):
#             if sym in obj:
#                 snap = obj[sym]
#                 if isinstance(snap, str):
#                     snap = json.loads(snap)
#                 score = float(abs(snap.get("rolling", {}).get("score", 0.0)))
#                 out[sym] = _clamp(score, 0.0, 1.0)
#         if out:
#             LOG.info(f"📰 Sentiment snapshot map -> risk: {out}")
#         else:
#             LOG.info("📰 Sentiment snapshot present but no scores found; treating as None")
#         return out or None
#     except Exception as e:
#         LOG.warning(f"📰 Sentiment parse error: {e}; treating as None")
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
#     except Exception as e:
#         LOG.warning(f"⚠️ Peg parse error: {e}; using defaults")

#     # Blend sentiment risk if present (30% weight)
#     s = _extract_sentiment_risk(sentiment_json)
#     if s:
#         r_before = (r_usdc, r_usdt)
#         r_usdc = 0.7 * r_usdc + 0.3 * float(s.get("USDC", 0.0))
#         r_usdt = 0.7 * r_usdt + 0.3 * float(s.get("USDT", 0.0))
#         LOG.info(f"🧮 Combined risk (peg⊕sent): {r_before} -> {(r_usdc, r_usdt)}")
#     else:
#         LOG.info("🧮 No sentiment risk; using peg risks only")

#     # Simple tilt: base 50/50, tilt 10% max toward lower combined risk
#     tilt = _clamp(0.10 * (r_usdt - r_usdc), -0.10, 0.10)
#     w_usdc = _clamp(0.50 + tilt, 0.20, 0.80)
#     LOG.info(f"🎯 Fallback base weights before liquidity gate: USDC={w_usdc:.4f}, USDT={1.0-w_usdc:.4f}")

#     # Liquidity gate (if quote deviates from 1.0 by > 0.3%, halve the tilt)
#     if liq_quote is not None and abs(1.0 - float(liq_quote)) > 0.003:
#         w_usdc = 0.50 + 0.5 * (w_usdc - 0.50)
#         LOG.info(f"🚧 Liquidity gate applied (quote={liq_quote}); USDC={w_usdc:.4f}")

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
#     LOG.info(f"✅ Fallback result -> weights: USDC={w_usdc}, USDT={w_usdt}, regime={regime}")
#     return dict(weights={"USDC": w_usdc, "USDT": w_usdt}, regime=regime, rationale=rationale)

# # -----------------------------------------------------------------------------
# # MeTTa knowledge-graph path (no external rules file)
# # We initialize a graph and assert runtime facts for explainability and future use.
# # For now, the target weights are computed in Python (same as fallback), but we
# # still build the MeTTa space to satisfy the “knowledge base” requirement.
# # -----------------------------------------------------------------------------
# def _run_with_knowledge(
#     peg_payload_json: Optional[str],
#     liq_quote: Optional[float],
#     sentiment_json: Optional[str],
# ) -> Optional[Dict[str, Any]]:
#     if not _METTA_OK:
#         LOG.info("⛔ Skipping MeTTa because Hyperon not available")
#         return None

#     try:
#         m = MeTTa()  # type: ignore
#         LOG.info("🧩 MeTTa engine created (knowledge graph mode)")
#         # Load our static domain knowledge if available
#         if initialize_knowledge_graph:
#             initialize_knowledge_graph(m)
#             LOG.info("📚 Local knowledge graph initialized from knowledge.py")
#         else:
#             LOG.warning("⚠️ initialize_knowledge_graph not available; proceeding with empty space")

#         # Parse inputs
#         peg = json.loads(peg_payload_json or "{}")
#         sent_risk = _extract_sentiment_risk(sentiment_json)

#         # Assert runtime facts into the space (for explainability/inspection)
#         r = peg.get("risk", {})
#         r_usdc = float(r.get("USDC", 0.0))
#         r_usdt = float(r.get("USDT", 0.0))
#         m.run(f"(assert! (peg-risk USDC {r_usdc}))")
#         m.run(f"(assert! (peg-risk USDT {r_usdt}))")
#         s_usdc = float((sent_risk or {}).get("USDC", 0.0))
#         s_usdt = float((sent_risk or {}).get("USDT", 0.0))
#         m.run(f"(assert! (sentiment-risk USDC {s_usdc}))")
#         m.run(f"(assert! (sentiment-risk USDT {s_usdt}))")
#         if liq_quote is not None:
#             m.run(f"(assert! (liq-quote {float(liq_quote)}))")

#         # Compute weights in Python (same as fallback) but mark that MeTTa graph is present.
#         fb = _fallback_reason(peg_payload_json, liq_quote, sentiment_json, None)
#         fb["rationale"] = ("Knowledge-graph mode: computed by Python policy with MeTTa graph initialized; "+ fb["rationale"])
#         return fb
#     except Exception as e:
#         LOG.warning(f"⚠️ MeTTa (knowledge mode) runtime error: {e}; falling back")
#         return None

# # -----------------------------------------------------------------------------
# # Handlers
# # -----------------------------------------------------------------------------
# @agent.on_event("startup")
# async def on_start(ctx: Context):
#     ctx.logger.info(f"[{AGENT_NAME}] started. Mailbox={USE_MAILBOX}. MeTTa={'ON' if _METTA_OK else 'OFF'}")
#     if _METTA_OK:
#         ctx.logger.info(f"[{AGENT_NAME}] Running in knowledge-graph mode (no external .metta rules)")

# @agent.on_message(model=ReasonRequest, replies=ReasonResponse)
# async def on_reason(ctx: Context, sender: str, msg: ReasonRequest):
#     ctx.logger.info(f"[{AGENT_NAME}] 📩 Received ReasonRequest")
#     ctx.logger.info(
#         f"[{AGENT_NAME}] Input sizes: peg={len(msg.peg_payload_json or '')}, "
#         f"liq={'set' if msg.liq_quote is not None else 'none'}, "
#         f"sentiment={'set' if msg.sentiment_json else 'none'}"
#     )
#     try:
#         # Try MeTTa-initialized path (for explainability + future graph queries)
#         result = _run_with_knowledge(msg.peg_payload_json, msg.liq_quote, msg.sentiment_json)
#         if result is None:
#             ctx.logger.warning(f"[{AGENT_NAME}] ↩️ MeTTa unavailable — using Python fallback rules only")
#             result = _fallback_reason(
#                 peg_payload_json=msg.peg_payload_json,
#                 liq_quote=msg.liq_quote,
#                 sentiment_json=msg.sentiment_json,
#                 current_weights=msg.current_weights,
#             )

#         ctx.logger.info(f"[{AGENT_NAME}] 🔁 Sending response")
#         await ctx.send(sender, ReasonResponse(
#             ok=True,
#             target_weights=result["weights"],
#             alert_level=result["regime"],
#             rationale=result["rationale"],
#         ))
#     except Exception as e:
#         ctx.logger.error(f"[{AGENT_NAME}] 💥 Reason handler error: {e}")
#         await ctx.send(sender, ReasonResponse(ok=False, error=str(e))) 

# agent.py — 10-coin MeTTa Reasoner Agent
# ----------------------------------------------------------------------
# Works with responder & agents: Peg, Liquidity, Sentiment.
# Uses knowledge.py for policy values (no external .metta files).
# Returns ReasonResponse with weights for 10 coins and rationale.
#working
# import os
# import json
# import logging
# from typing import Optional, Dict, Any

# from uagents import Agent, Context
# from models import ReasonRequest, ReasonResponse

# # -----------------------------------------------------------------------------
# # Logging
# # -----------------------------------------------------------------------------
# logging.basicConfig(level=logging.INFO)
# LOG = logging.getLogger("reasoner-10coin")

# # -----------------------------------------------------------------------------
# # Config
# # -----------------------------------------------------------------------------
# AGENT_NAME = os.getenv("AGENT_NAME", "reasoner-10coin")
# REASONER_SEED = os.getenv("REASONER_SEED", "reasoner-demo-seed")
# USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")

# # -----------------------------------------------------------------------------
# # Hyperon/MeTTa import and KB
# # -----------------------------------------------------------------------------
# _METTA_OK = True
# try:
#     from hyperon import MeTTa  # type: ignore
#     from knowledge import initialize_knowledge_graph, read_policy , read_event_penalties # type: ignore
#     LOG.info("🧠 MeTTa + knowledge.py import OK")
# except Exception as e:
#     _METTA_OK = False
#     MeTTa = None  # type: ignore
#     initialize_knowledge_graph = None  # type: ignore
#     read_policy = None  # type: ignore
#     LOG.warning(f"⚠️ MeTTa/knowledge unavailable: {e}")

# # -----------------------------------------------------------------------------
# # Agent init
# # -----------------------------------------------------------------------------
# agent = Agent(
#     name=AGENT_NAME,
#     seed=REASONER_SEED,
#     mailbox=USE_MAILBOX,
#     publish_agent_details=True,
# )

# # -----------------------------------------------------------------------------
# # Coin universe
# # -----------------------------------------------------------------------------
# COINS = ["USDC", "USDT", "DAI", "FDUSD", "BUSD", "TUSD", "USDP", "PYUSD", "USDD", "GUSD"]

# # -----------------------------------------------------------------------------
# # Helpers
# # -----------------------------------------------------------------------------
# def _clamp(x: float, lo: float, hi: float) -> float:
#     return max(lo, min(hi, x))

# def _extract_sentiment_risk(sentiment_json: Optional[str]) -> Dict[str, float]:
#     """Extract absolute sentiment scores [-1,1] → [0,1] for all coins."""
#     risks: Dict[str, float] = {c: 0.0 for c in COINS}
#     if not sentiment_json:
#         return risks
#     try:
#         obj = json.loads(sentiment_json)
#         for sym in COINS:
#             snap = obj.get(sym)
#             if not snap:
#                 continue
#             if isinstance(snap, str):
#                 snap = json.loads(snap)
#             score = float(abs(snap.get("rolling", {}).get("score", 0.0)))
#             risks[sym] = _clamp(score, 0.0, 1.0)
#     except Exception as e:
#         LOG.warning(f"Sentiment parse failed: {e}")
#     return risks

# def _blend_risks(peg_json: Optional[str], sentiment_json: Optional[str], policy: Dict[str, float]) -> Dict[str, float]:
#     """Weighted blend of peg + sentiment risk per coin."""
#     risks: Dict[str, float] = {}
#     sent_weight = policy.get("sentiment_weight", 0.3)
#     try:
#         peg = json.loads(peg_json or "{}")
#         peg_risk = peg.get("risk", {})
#     except Exception:
#         peg_risk = {}

#     sent_risk = _extract_sentiment_risk(sentiment_json)
#     for c in COINS:
#         pr = float(peg_risk.get(c, 0.0))
#         sr = sent_risk.get(c, 0.0)
#         combined = (1 - sent_weight) * pr + sent_weight * sr
#         risks[c] = round(combined, 4)
#     return risks

# def _derive_weights(risks: Dict[str, float], liq_quote: Optional[float], policy: Dict[str, float]) -> Dict[str, float]:
#     """Compute normalized weights inversely proportional to risk, adjusted by liquidity gate."""
#     inv = {c: 1.0 / max(r, 1e-6) for c, r in risks.items()}
#     total = sum(inv.values())
#     base = {c: inv[c] / total for c in COINS}

#     # liquidity gate dampens deviations if quote deviates > threshold
#     if liq_quote is not None and abs(1.0 - liq_quote) > policy["liq_gate_threshold"]:
#         mean_w = 1.0 / len(COINS)
#         for c in COINS:
#             base[c] = 0.5 * base[c] + 0.5 * mean_w

#     # clamp to min/max
#     w_min, w_max = policy["weight_min"], policy["weight_max"]
#     normed = {}
#     s = sum(_clamp(v, w_min, w_max) for v in base.values())
#     for c in COINS:
#         normed[c] = round(_clamp(base[c], w_min, w_max) / s, 4)
#     return normed

# def _detect_regime(risks: Dict[str, float], policy: Dict[str, float]) -> str:
#     """Regime based on worst risk."""
#     worst = max(risks.values()) if risks else 0.0
#     if worst >= policy["thr_red"]:
#         return "RED"
#     elif worst >= policy["thr_yellow"]:
#         return "YELLOW"
#     return "GREEN"

# # -----------------------------------------------------------------------------
# # Reasoning core
# # -----------------------------------------------------------------------------
# def _reason_with_knowledge(peg_json: str, liq_quote: Optional[float], sentiment_json: Optional[str]) -> Dict[str, Any]:
#     if not _METTA_OK or not initialize_knowledge_graph:
#         LOG.warning("⚠️ Running fallback reasoner (no MeTTa)")
#         return _fallback_reason(peg_json, liq_quote, sentiment_json, {})

#     m = MeTTa()  # type: ignore
#     initialize_knowledge_graph(m)
#     policy = read_policy(m)

#     # Blend peg + sentiment risks
#     risks = _blend_risks(peg_json, sentiment_json, policy)

#     # Compute weights inversely to risk
#     weights = _derive_weights(risks, liq_quote, policy)
#     regime = _detect_regime(risks, policy)

#     rationale = (
#         f"Knowledge-graph mode: MeTTa policy used. "
#         f"Combined risks derived from peg⊕sentiment. "
#         f"Regime={regime}, liquidity gate applied if deviation>{policy['liq_gate_threshold']*100:.2f}%."
#     )

#     return dict(weights=weights, regime=regime, rationale=rationale)

# def _fallback_reason(peg_json: str, liq_quote: Optional[float], sentiment_json: Optional[str], _: Dict) -> Dict[str, Any]:
#     """Simplified fallback: if MeTTa unavailable."""
#     try:
#         peg = json.loads(peg_json or "{}")
#         peg_risk = peg.get("risk", {})
#     except Exception:
#         peg_risk = {}
#     sent_risk = _extract_sentiment_risk(sentiment_json)
#     risks = {}
#     for c in COINS:
#         risks[c] = 0.7 * float(peg_risk.get(c, 0.0)) + 0.3 * sent_risk.get(c, 0.0)
#     s = sum(1.0 / max(r, 1e-6) for r in risks.values())
#     weights = {c: round((1.0 / max(r, 1e-6)) / s, 4) for c, r in risks.items()}
#     regime = "GREEN" if max(risks.values()) < 0.35 else ("YELLOW" if max(risks.values()) < 0.6 else "RED")
#     rationale = "Fallback: no MeTTa, simple inverse-risk weighting."
#     return dict(weights=weights, regime=regime, rationale=rationale)

# # -----------------------------------------------------------------------------
# # Handlers
# # -----------------------------------------------------------------------------
# @agent.on_event("startup")
# async def on_start(ctx: Context):
#     ctx.logger.info(f"[{AGENT_NAME}] started. Mailbox={USE_MAILBOX}. MeTTa={'ON' if _METTA_OK else 'OFF'}")
#     ctx.logger.info(f"[{AGENT_NAME}] 10-coin reasoner online. Coins: {', '.join(COINS)}")

# @agent.on_message(model=ReasonRequest, replies=ReasonResponse)
# async def on_reason(ctx: Context, sender: str, msg: ReasonRequest):
#     ctx.logger.info(f"[{AGENT_NAME}] 📩 Received ReasonRequest")

#     try:
#         result = _reason_with_knowledge(msg.peg_payload_json, msg.liq_quote, msg.sentiment_json)
#         await ctx.send(sender, ReasonResponse(
#             ok=True,
#             target_weights=result["weights"],
#             alert_level=result["regime"],
#             rationale=result["rationale"],
#         ))
#         ctx.logger.info(f"[{AGENT_NAME}] ✅ Reply sent regime={result['regime']}")
#     except Exception as e:
#         ctx.logger.error(f"[{AGENT_NAME}] 💥 Error: {e}")
#         await ctx.send(sender, ReasonResponse(ok=False, error=str(e)))

# # -----------------------------------------------------------------------------
# # Run
# # -----------------------------------------------------------------------------
# if __name__ == "__main__":
#     print(f"Address: {agent.address}")
#     agent.run()

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
EVENT_ALPHA = float(os.getenv("EVENT_ALPHA", "0.5"))  # strength of past-event penalty [0..1]

# -----------------------------------------------------------------------------
# Hyperon/MeTTa import and KB
# -----------------------------------------------------------------------------
_METTA_OK = True
try:
    from hyperon import MeTTa  # type: ignore
    # patched imports: include read_event_penalties
    from knowledge import (
        initialize_knowledge_graph,
        read_policy,
        read_event_penalties,
    )  # type: ignore
    LOG.info("🧠 MeTTa + knowledge.py import OK")
except Exception as e:
    _METTA_OK = False
    MeTTa = None  # type: ignore
    initialize_knowledge_graph = None  # type: ignore
    read_policy = None  # type: ignore
    read_event_penalties = None  # type: ignore
    LOG.warning(f"⚠️ MeTTa/knowledge unavailable: {e}")

# -----------------------------------------------------------------------------
# Agent init
# -----------------------------------------------------------------------------
agent = Agent(
    name=AGENT_NAME,
    seed=REASONER_SEED,
    mailbox=USE_MAILBOX,
    publish_agent_details=True,
    port=None
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

def _norm_weights(d: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Normalize a weight dict to sum to 1 (or equal if None/empty)."""
    if not d:
        eq = 1.0 / len(COINS)
        return {c: eq for c in COINS}
    s = sum(max(float(d.get(c, 0.0)), 0.0) for c in COINS) or 1.0
    return {c: max(float(d.get(c, 0.0)), 0.0) / s for c in COINS}

# -----------------------------------------------------------------------------
# Reasoning core
# -----------------------------------------------------------------------------
def _reason_with_knowledge(
    peg_json: str,
    liq_quote: Optional[float],
    sentiment_json: Optional[str],
    current_weights: Optional[Dict[str, float]],
) -> Dict[str, Any]:
    if not _METTA_OK or not initialize_knowledge_graph or not read_policy:
        LOG.warning("⚠️ Running fallback reasoner (no MeTTa)")
        return _fallback_reason(peg_json, liq_quote, sentiment_json, current_weights)

    m = MeTTa()  # type: ignore
    initialize_knowledge_graph(m)
    policy = read_policy(m)

    # Blend peg + sentiment risks
    risks = _blend_risks(peg_json, sentiment_json, policy)

    # Apply past-event penalties from KB
    try:
        ev_pen = read_event_penalties(m) if read_event_penalties else {c: 0.0 for c in COINS}
    except Exception:
        ev_pen = {c: 0.0 for c in COINS}

    for c in COINS:
        base = risks.get(c, 0.0)
        risks[c] = _clamp(base + EVENT_ALPHA * ev_pen.get(c, 0.0), 0.0, 1.0)

    # Compute weights inversely to risk
    weights = _derive_weights(risks, liq_quote, policy)
    regime = _detect_regime(risks, policy)

    # Health scores (lower is better): weighted-average risk
    cur_w = _norm_weights(current_weights)
    tgt_w = _norm_weights(weights)
    health_before = sum(cur_w[c] * risks.get(c, 0.0) for c in COINS)
    health_after = sum(tgt_w[c] * risks.get(c, 0.0) for c in COINS)
    improve = health_before - health_after

    rationale = (
        f"Knowledge-graph mode: MeTTa policy used. "
        f"Past-event penalties applied where present. "
        f"Combined risks from peg⊕sentiment; liquidity gate={policy['liq_gate_threshold']:.4f}. "
        f"Regime={regime}. "
        f"HealthScore(before)={health_before:.3f}, after={health_after:.3f}"
        f"{' (↓'+format(improve, '.3f')+')' if improve > 0 else ''}."
    )

    return dict(weights=weights, regime=regime, rationale=rationale)

def _fallback_reason(
    peg_json: str,
    liq_quote: Optional[float],
    sentiment_json: Optional[str],
    current_weights: Optional[Dict[str, float]],
) -> Dict[str, Any]:
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

    # weights inverse to risk (no policy clamps in fallback)
    s = sum(1.0 / max(r, 1e-6) for r in risks.values())
    weights = {c: round((1.0 / max(r, 1e-6)) / s, 4) for c, r in risks.items()}
    regime = "GREEN" if max(risks.values()) < 0.35 else ("YELLOW" if max(risks.values()) < 0.6 else "RED")

    # health scores in fallback too
    cur_w = _norm_weights(current_weights)
    tgt_w = _norm_weights(weights)
    health_before = sum(cur_w[c] * risks.get(c, 0.0) for c in COINS)
    health_after = sum(tgt_w[c] * risks.get(c, 0.0) for c in COINS)
    improve = health_before - health_after

    rationale = (
        "Fallback: no MeTTa, simple inverse-risk weighting. "
        f"HealthScore(before)={health_before:.3f}, after={health_after:.3f}"
        f"{' (↓'+format(improve, '.3f')+')' if improve > 0 else ''}."
    )
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
        result = _reason_with_knowledge(
            msg.peg_payload_json,
            msg.liq_quote,
            msg.sentiment_json,
            getattr(msg, "current_weights", None),
        )
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