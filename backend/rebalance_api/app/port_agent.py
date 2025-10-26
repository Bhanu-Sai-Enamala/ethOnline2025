# # import os
# # import json
# # import time
# # import asyncio
# # from typing import Optional, Dict, Any
# # from pathlib import Path
# # import hashlib

# # from dotenv import load_dotenv
# # from uagents import Agent, Context
# # from uagents.setup import fund_agent_if_low
# # from app.rebalance_models import RebalanceCheckRequest, RebalanceCheckResponse
# # # try both import locations so it works in dev and on Render
# # try:
# #     from app.swapPlanner import build_swap_plan
# # except Exception:
# #     from swapPlanner import build_swap_plan  # fallback for local runs

# # # --- Load environment ---
# # load_dotenv()

# # PORT = int(os.getenv("PORT", "8011"))
# # CLIENT_SEED = os.getenv("CLIENT_SEED", "ethOnlineseed")
# # BALANCER_AGENT_ADDRESS = os.getenv("BALANCER_AGENT_ADDRESS", "").strip()
# # USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")
# # DEFAULT_TIMEOUT_SEC = float(os.getenv("DEFAULT_TIMEOUT_SEC", "60"))
# # AGENT_NAME = "rebalance-rest-port"

# # # --- Local cache setup (app/data/rebalance_latest.json) ---
# # APP_DIR = Path(__file__).resolve().parent
# # DATA_DIR = APP_DIR / "data"
# # DATA_DIR.mkdir(parents=True, exist_ok=True)
# # CACHE_PATH = DATA_DIR / "rebalance_latest.json"

# # # --- Helper functions ---
# # def _now() -> float:
# #     return time.time()

# # def _save_latest(ctx: Context, resp: Dict[str, Any]):
# #     """Save latest successful rebalance result both in ctx.storage and to file."""
# #     # Deduplicate identical payloads to avoid double cache logs
# #     payload_str = json.dumps(resp, sort_keys=True)
# #     new_hash = hashlib.sha1(payload_str.encode("utf-8")).hexdigest()
# #     last_hash = ctx.storage.get("latest_hash") or ""
# #     ctx.storage.set("latest_payload", payload_str)
# #     ctx.storage.set("latest_ts", _now())
# #     ctx.storage.set("latest_hash", new_hash)
# #     if new_hash != last_hash:
# #         payload = {
# #             "latest_payload": payload_str,
# #             "latest_ts": _now(),
# #         }
# #         try:
# #             CACHE_PATH.write_text(json.dumps(payload, indent=2))
# #             ctx.logger.info(f"💾 Cached to file: {CACHE_PATH}")
# #         except Exception as e:
# #             ctx.logger.warning(f"Failed to write cache file: {e}")
# #     else:
# #         # Quietly skip duplicate writes
# #         pass

# # def _get_latest(ctx: Context) -> Optional[Dict[str, Any]]:
# #     """Fetch latest cached result (prefer ctx.storage, fallback to file)."""
# #     raw = ctx.storage.get("latest_payload") or None
# #     if raw:
# #         return json.loads(raw)
# #     try:
# #         if CACHE_PATH.exists():
# #             data = json.loads(CACHE_PATH.read_text())
# #             return json.loads(data.get("latest_payload", "{}"))
# #     except Exception:
# #         pass
# #     return None

# # # --- Agent setup ---
# # agent = Agent(
# #     name=AGENT_NAME,
# #     seed=CLIENT_SEED,
# #     mailbox=USE_MAILBOX,
# #     publish_agent_details=True,
# #     port=PORT
# # )

# # try:
# #     fund_agent_if_low(agent.wallet.address())
# # except Exception:
# #     pass

# # # --- Events and Handlers ---
# # @agent.on_event("startup")
# # async def on_start(ctx: Context):
# #     ctx.logger.info(f"[{AGENT_NAME}] Address: {agent.address}")
# #     ctx.logger.info(f"Balancer Target: {BALANCER_AGENT_ADDRESS or '<unset>'}")
# #     ctx.logger.info(f"Mailbox Enabled: {USE_MAILBOX}")
# #     ctx.logger.info(f"Cache File Path: {CACHE_PATH}")

# # @agent.on_message(model=RebalanceCheckResponse)
# # async def on_reply(ctx: Context, sender: str, msg: RebalanceCheckResponse):
# #     data = {
# #         "ok": msg.ok,
# #         "error": msg.error,
# #         "plan": msg.plan.dict() if msg.plan else None,
# #         "diagnostics_json": msg.diagnostics_json,
# #     }
# #     _save_latest(ctx, data)
# #     ctx.logger.info("✅ Cached latest rebalance reply")

# # @agent.on_rest_post("/rebalance", RebalanceCheckRequest, RebalanceCheckResponse)
# # async def rebalance(ctx: Context, body: RebalanceCheckRequest) -> RebalanceCheckResponse:
# #     """Forward the rebalance request to Balancer agent and wait for the response."""
# #     if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
# #         return RebalanceCheckResponse(ok=False, error="Balancer address not set")

# #     # Suppress immediate duplicate requests with identical body (idempotency guard)
# #     body_sig = hashlib.sha1(json.dumps(body.dict(), sort_keys=True).encode("utf-8")).hexdigest()
# #     last_sig = ctx.storage.get("last_req_sig") or ""
# #     last_ts = ctx.storage.get("last_req_ts") or 0.0
# #     now_ts = _now()
# #     duplicate = (body_sig == last_sig) and ((now_ts - float(last_ts)) < 0.6)
# #     if duplicate:
# #         ctx.logger.info("↩︎ Duplicate REST request detected within 600ms — not re-sending upstream")
# #     else:
# #         await ctx.send(BALANCER_AGENT_ADDRESS, body)
# #         ctx.storage.set("last_req_sig", body_sig)
# #         ctx.storage.set("last_req_ts", now_ts)
# #         ctx.logger.info("→ Sent request to balancer")

# #     start = _now()
# #     last = ctx.storage.get("latest_ts") or 0.0

# #     while _now() - start < DEFAULT_TIMEOUT_SEC:
# #         await asyncio.sleep(0.2)
# #         ts = ctx.storage.get("latest_ts") or 0.0
# #         if ts > last:
# #             data = _get_latest(ctx)
# #             return RebalanceCheckResponse(**data)

# #     # timeout fallback
# #     cached = _get_latest(ctx)
# #     if cached:
# #         ctx.logger.warning("⏱ Timeout — returning cached result")
# #         return RebalanceCheckResponse(**cached)
# #     return RebalanceCheckResponse(ok=False, error="Timeout waiting for balancer response")

# # @agent.on_rest_get("/rebalance/cached", RebalanceCheckResponse)
# # async def cached(ctx: Context) -> RebalanceCheckResponse:
# #     """Serve latest cached result."""
# #     data = _get_latest(ctx)
# #     return RebalanceCheckResponse(**data) if data else RebalanceCheckResponse(ok=False, error="No cache")

# # @agent.on_rest_get("/health", RebalanceCheckResponse)
# # async def health(_: Context) -> RebalanceCheckResponse:
# #     """Health check endpoint."""
# #     status = {"status": "ok", "agent": AGENT_NAME, "upstream": BALANCER_AGENT_ADDRESS or "<unset>"}
# #     return RebalanceCheckResponse(ok=True, diagnostics_json=json.dumps(status))

# # # --- Run Agent ---
# # def run():
# #     agent.run()

# # if __name__ == "__main__":
# #     run()

# # app/port_agent.py
# import os
# import json
# import time
# import asyncio
# from typing import Optional, Dict, Any
# from pathlib import Path
# import hashlib

# from dotenv import load_dotenv
# from uagents import Agent, Context, Model
# from uagents.setup import fund_agent_if_low

# from app.rebalance_models import RebalanceCheckRequest, RebalanceCheckResponse
# # try both import locations so it works in dev and on Render
# try:
#     from app.swapPlanner import build_swap_plan
# except Exception:
#     from swapPlanner import build_swap_plan  # fallback for local runs

# # --- Load environment ---
# load_dotenv()

# PORT = int(os.getenv("PORT", "8011"))
# CLIENT_SEED = os.getenv("CLIENT_SEED", "ethOnlineseed")
# BALANCER_AGENT_ADDRESS = os.getenv("BALANCER_AGENT_ADDRESS", "").strip()
# USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")
# DEFAULT_TIMEOUT_SEC = float(os.getenv("DEFAULT_TIMEOUT_SEC", "60"))
# AGENT_NAME = "rebalance-rest-port"

# # --- Local cache setup (app/data/...) ---
# APP_DIR = Path(__file__).resolve().parent
# DATA_DIR = APP_DIR / "data"
# DATA_DIR.mkdir(parents=True, exist_ok=True)
# CACHE_PATH = DATA_DIR / "rebalance_latest.json"        # raw balancer reply cache
# PREVIEW_CACHE_PATH = DATA_DIR / "rebalance_preview.json"  # combined preview cache

# # ─────────────────────────────────────────────────────────────
# # Models for the new preview route (uAgents Model = pydantic)
# # ─────────────────────────────────────────────────────────────
# class PreviewResponse(Model):
#     ok: bool
#     current_allocation: Dict[str, float] = {}
#     suggested_allocation: Dict[str, float] = {}
#     trade_deltas: Dict[str, float] = {}
#     swap_plan: Dict[str, Any] = {}
#     rationale: Optional[str] = None
#     error: Optional[str] = None

# # --- Helper functions ---
# def _now() -> float:
#     return time.time()

# def _save_latest(ctx: Context, resp: Dict[str, Any]):
#     """Save latest successful rebalance result both in ctx.storage and to file."""
#     payload_str = json.dumps(resp, sort_keys=True)
#     new_hash = hashlib.sha1(payload_str.encode("utf-8")).hexdigest()
#     last_hash = ctx.storage.get("latest_hash") or ""
#     ctx.storage.set("latest_payload", payload_str)
#     ctx.storage.set("latest_ts", _now())
#     ctx.storage.set("latest_hash", new_hash)
#     if new_hash != last_hash:
#         payload = {
#             "latest_payload": payload_str,
#             "latest_ts": _now(),
#         }
#         try:
#             CACHE_PATH.write_text(json.dumps(payload, indent=2))
#             ctx.logger.info(f"💾 Cached raw reply to file: {CACHE_PATH}")
#         except Exception as e:
#             ctx.logger.warning(f"Failed to write raw cache file: {e}")

# def _get_latest(ctx: Context) -> Optional[Dict[str, Any]]:
#     """Fetch latest cached result (prefer ctx.storage, fallback to file)."""
#     raw = ctx.storage.get("latest_payload") or None
#     if raw:
#         return json.loads(raw)
#     try:
#         if CACHE_PATH.exists():
#             data = json.loads(CACHE_PATH.read_text())
#             return json.loads(data.get("latest_payload", "{}"))
#     except Exception:
#         pass
#     return None

# def _save_preview(ctx: Context, preview: Dict[str, Any]):
#     """Cache the combined preview payload (storage + file)."""
#     s = json.dumps(preview, sort_keys=True)
#     ctx.storage.set("latest_preview_payload", s)
#     ctx.storage.set("latest_preview_ts", _now())
#     try:
#         PREVIEW_CACHE_PATH.write_text(s)
#     except Exception as e:
#         ctx.logger.warning(f"Failed to write preview cache file: {e}")

# def _get_preview(ctx: Context) -> Optional[Dict[str, Any]]:
#     raw = ctx.storage.get("latest_preview_payload")
#     if raw:
#         try:
#             return json.loads(raw)
#         except Exception:
#             return None
#     try:
#         if PREVIEW_CACHE_PATH.exists():
#             return json.loads(PREVIEW_CACHE_PATH.read_text())
#     except Exception:
#         pass
#     return None

# def _to_current_alloc(balances: Dict[str, float]) -> Dict[str, float]:
#     total = sum(balances.values()) or 1.0
#     return {k: round(v / total, 4) for k, v in balances.items()}

# # --- Agent setup ---
# agent = Agent(
#     name=AGENT_NAME,
#     seed=CLIENT_SEED,
#     mailbox=USE_MAILBOX,
#     publish_agent_details=True,
#     port=PORT
# )

# try:
#     fund_agent_if_low(agent.wallet.address())
# except Exception:
#     pass

# # --- Events and Handlers ---
# @agent.on_event("startup")
# async def on_start(ctx: Context):
#     ctx.logger.info(f"[{AGENT_NAME}] Address: {agent.address}")
#     ctx.logger.info(f"Balancer Target: {BALANCER_AGENT_ADDRESS or '<unset>'}")
#     ctx.logger.info(f"Mailbox Enabled: {USE_MAILBOX}")
#     ctx.logger.info(f"Raw Cache: {CACHE_PATH}")
#     ctx.logger.info(f"Preview Cache: {PREVIEW_CACHE_PATH}")

# @agent.on_message(model=RebalanceCheckResponse)
# async def on_reply(ctx: Context, sender: str, msg: RebalanceCheckResponse):
#     data = {
#         "ok": msg.ok,
#         "error": msg.error,
#         "plan": msg.plan.dict() if msg.plan else None,
#         "diagnostics_json": msg.diagnostics_json,
#     }
#     _save_latest(ctx, data)
#     ctx.logger.info("✅ Cached latest rebalance reply")

# # ─────────────────────────────────────────────────────────────
# # EXISTING: raw rebalance proxy & cache
# # ─────────────────────────────────────────────────────────────
# @agent.on_rest_post("/rebalance", RebalanceCheckRequest, RebalanceCheckResponse)
# async def rebalance(ctx: Context, body: RebalanceCheckRequest) -> RebalanceCheckResponse:
#     """Forward the rebalance request to Balancer agent and wait for the response."""
#     if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
#         return RebalanceCheckResponse(ok=False, error="Balancer address not set")

#     # idempotency guard (duplicate within 600ms)
#     body_sig = hashlib.sha1(json.dumps(body.dict(), sort_keys=True).encode("utf-8")).hexdigest()
#     last_sig = ctx.storage.get("last_req_sig") or ""
#     last_ts = ctx.storage.get("last_req_ts") or 0.0
#     now_ts = _now()
#     duplicate = (body_sig == last_sig) and ((now_ts - float(last_ts)) < 0.6)

#     if duplicate:
#         ctx.logger.info("↩︎ Duplicate REST request detected within 600ms — not re-sending upstream")
#     else:
#         await ctx.send(BALANCER_AGENT_ADDRESS, body)
#         ctx.storage.set("last_req_sig", body_sig)
#         ctx.storage.set("last_req_ts", now_ts)
#         ctx.logger.info("→ Sent request to balancer")

#     start = _now()
#     last = ctx.storage.get("latest_ts") or 0.0

#     while _now() - start < DEFAULT_TIMEOUT_SEC:
#         await asyncio.sleep(0.2)
#         ts = ctx.storage.get("latest_ts") or 0.0
#         if ts > last:
#             data = _get_latest(ctx)
#             return RebalanceCheckResponse(**data)

#     # timeout fallback
#     cached = _get_latest(ctx)
#     if cached:
#         ctx.logger.warning("⏱ Timeout — returning cached result")
#         return RebalanceCheckResponse(**cached)
#     return RebalanceCheckResponse(ok=False, error="Timeout waiting for balancer response")

# @agent.on_rest_get("/rebalance/cached", RebalanceCheckResponse)
# async def cached(ctx: Context) -> RebalanceCheckResponse:
#     """Serve latest cached raw result."""
#     data = _get_latest(ctx)
#     return RebalanceCheckResponse(**data) if data else RebalanceCheckResponse(ok=False, error="No cache")

# # ─────────────────────────────────────────────────────────────
# # NEW: preview (raw plan + computed swap_plan + helpful fields)
# # ─────────────────────────────────────────────────────────────
# @agent.on_rest_post("/rebalance/preview", RebalanceCheckRequest, PreviewResponse)
# async def rebalance_preview(ctx: Context, body: RebalanceCheckRequest) -> PreviewResponse:
#     """
#     Forward to balancer and, on reply, compute a swap plan from the returned deltas
#     and the balances provided in the request.
#     """
#     if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
#         return PreviewResponse(ok=False, error="Balancer address not set")

#     # forward (reuse duplicate guard)
#     body_sig = hashlib.sha1(json.dumps(body.dict(), sort_keys=True).encode("utf-8")).hexdigest()
#     last_sig = ctx.storage.get("last_req_sig_prev") or ""
#     last_ts = ctx.storage.get("last_req_ts_prev") or 0.0
#     now_ts = _now()
#     duplicate = (body_sig == last_sig) and ((now_ts - float(last_ts)) < 0.6)

#     if duplicate:
#         ctx.logger.info("↩︎ Duplicate PREVIEW request within 600ms — not re-sending upstream")
#     else:
#         await ctx.send(BALANCER_AGENT_ADDRESS, body)
#         ctx.storage.set("last_req_sig_prev", body_sig)
#         ctx.storage.set("last_req_ts_prev", now_ts)
#         ctx.logger.info("→ Sent PREVIEW request to balancer")

#     start = _now()
#     last = ctx.storage.get("latest_ts") or 0.0

#     while _now() - start < DEFAULT_TIMEOUT_SEC:
#         await asyncio.sleep(0.2)
#         ts = ctx.storage.get("latest_ts") or 0.0
#         if ts > last:
#             # got a fresh raw result
#             raw = _get_latest(ctx) or {}
#             if not raw.get("ok"):
#                 return PreviewResponse(ok=False, error=raw.get("error") or "balancer not ok")

#             plan = raw.get("plan") or {}
#             deltas = plan.get("trade_deltas", {}) or {}
#             target_weights = plan.get("target_weights", {}) or {}

#             # balances from the request body (convert to SYMBOL upper keys)
#             balances = {}
#             for k, v in body.dict().items():
#                 if k.endswith("_balance"):
#                     balances[k.replace("_balance", "").upper()] = float(v)

#             # compute helpful fields
#             try:
#                 swap_plan = build_swap_plan(
#                     balances=balances,
#                     deltas=deltas,
#                     base="USDC",
#                     wallet_base_available=0.0
#                 ).to_dict()
#             except Exception as e:
#                 swap_plan = {"warnings": [f"swapPlanner error: {e}"]}

#             current_alloc = _to_current_alloc(balances)
#             rationale = raw.get("error") or raw.get("diagnostics_json")

#             out = {
#                 "ok": True,
#                 "current_allocation": current_alloc,
#                 "suggested_allocation": target_weights,
#                 "trade_deltas": deltas,
#                 "swap_plan": swap_plan,
#                 "rationale": rationale,
#                 "error": None,
#             }
#             _save_preview(ctx, out)
#             return PreviewResponse(**out)

#     # timeout → try cached preview
#     cached = _get_preview(ctx)
#     if cached:
#         ctx.logger.warning("⏱ Timeout — returning cached PREVIEW")
#         return PreviewResponse(**cached)
#     return PreviewResponse(ok=False, error="Timeout waiting for balancer response")

# @agent.on_rest_get("/rebalance/preview/cached", PreviewResponse)
# async def rebalance_preview_cached(ctx: Context) -> PreviewResponse:
#     """Return last combined preview payload (swap plan included)."""
#     data = _get_preview(ctx)
#     if not data:
#         return PreviewResponse(ok=False, error="No preview cached")
#     return PreviewResponse(**data)

# # ─────────────────────────────────────────────────────────────
# # Health
# # ─────────────────────────────────────────────────────────────
# @agent.on_rest_get("/health", RebalanceCheckResponse)
# async def health(_: Context) -> RebalanceCheckResponse:
#     """Health check endpoint (kept as original response type)."""
#     status = {"status": "ok", "agent": AGENT_NAME, "upstream": BALANCER_AGENT_ADDRESS or "<unset>"}
#     return RebalanceCheckResponse(ok=True, diagnostics_json=json.dumps(status))

# # --- Run Agent ---
# def run():
#     agent.run()

# if __name__ == "__main__":
#     run()

import os
import json
import time
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path
import hashlib

from dotenv import load_dotenv
from uagents import Agent, Context, Model
from uagents.setup import fund_agent_if_low

# Balancer models
from app.rebalance_models import RebalanceCheckRequest, RebalanceCheckResponse
# try both import locations so it works in dev and on Render
try:
    from app.swapPlanner import build_swap_plan
except Exception:
    from swapPlanner import build_swap_plan  # fallback for local runs

# Telegram (send-only)
from telegram import Bot

# --- Load environment ---
load_dotenv()

PORT = int(os.getenv("PORT", "8000"))
CLIENT_SEED = os.getenv("CLIENT_SEED", "ethOnlineseed")
BALANCER_AGENT_ADDRESS = os.getenv("BALANCER_AGENT_ADDRESS", "").strip()
USE_MAILBOX = str(os.getenv("MAILBOX_ENABLED", os.getenv("USE_MAILBOX", "true"))).lower() in ("1", "true", "yes", "y")
DEFAULT_TIMEOUT_SEC = float(os.getenv("DEFAULT_TIMEOUT_SEC", "60"))
AGENT_NAME = "rebalance-rest-port"

# Vacation settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "120"))        # alert checks
SUMMARY_TICK_SEC   = int(os.getenv("SUMMARY_TICK_SEC", "60"))           # summary clock tick
DEFAULT_ALERT_THRESHOLD = os.getenv("DEFAULT_ALERT_THRESHOLD", "RED")   # per-user can override

bot = Bot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

# --- Local cache & DB setup (app/data/...) ---
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CACHE_PATH = DATA_DIR / "rebalance_latest.json"          # raw balancer reply cache (stringified)
PREVIEW_CACHE_PATH = DATA_DIR / "rebalance_preview.json" # combined preview cache
USERS_DB_PATH = DATA_DIR / "vacation_users.json"         # user store

# ─────────────────────────────────────────────────────────────
# Models for preview + vacation REST
# ─────────────────────────────────────────────────────────────
class PreviewResponse(Model):
    ok: bool
    current_allocation: Dict[str, float] = {}
    suggested_allocation: Dict[str, float] = {}
    trade_deltas: Dict[str, float] = {}
    swap_plan: Dict[str, Any] = {}
    rationale: Optional[str] = None
    error: Optional[str] = None

class OkResp(Model):
    ok: bool
    error: Optional[str] = None

class Onboard(Model):
    wallet_address: str
    telegram_chat_id: str
    nickname: Optional[str] = ""

class OnboardResp(Model):
    ok: bool
    user_id: Optional[int] = None
    error: Optional[str] = None

class Balances(Model):
    usdc_balance: float = 0.0
    usdt_balance: float = 0.0
    dai_balance: float = 0.0
    fdusd_balance: float = 0.0
    busd_balance: float = 0.0
    tusd_balance: float = 0.0
    usdp_balance: float = 0.0
    pyusd_balance: float = 0.0
    usdd_balance: float = 0.0
    gusd_balance: float = 0.0
    quote_amount: float = 1000.0

class BalancesWithId(Balances):
    user_id: int

class PrefsBody(Model):
    user_id: int
    active: Optional[bool] = None
    alert_threshold: Optional[str] = None  # RED|YELLOW|GREEN
    daily_summary_hour_utc: Optional[int] = None  # 0..23

class StartStopBody(Model):
    user_id: int

class NotifyBody(Model):
    user_id: int

class StatusBody(Model):
    user_id: int

class StatusResp(Model):
    ok: bool
    active: Optional[bool] = None
    last_regime: Optional[str] = None
    last_rationale: Optional[str] = None
    last_plan: Optional[Dict[str, Any]] = None
    next_summary_at: Optional[str] = None
    error: Optional[str] = None

class HealthResp(Model):
    ok: bool
    agent: str
    upstream: str
    telegram: bool

# ─────────────────────────────────────────────────────────────
# Helpers (time, cache, users DB)
# ─────────────────────────────────────────────────────────────
def _now() -> float:
    return time.time()

def now_utc_dt():
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc)

def iso(dt) -> Optional[str]:
    return dt.astimezone().isoformat() if dt else None

def as_utc(x: Optional[str]):
    if not x:
        return None
    try:
        import datetime as _dt
        d = _dt.datetime.fromisoformat(x)
        return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
    except Exception:
        return None

def _save_latest(ctx: Context, resp: Dict[str, Any]):
    payload_str = json.dumps(resp, sort_keys=True)
    new_hash = hashlib.sha1(payload_str.encode("utf-8")).hexdigest()
    last_hash = ctx.storage.get("latest_hash") or ""
    ctx.storage.set("latest_payload", payload_str)
    ctx.storage.set("latest_ts", _now())
    ctx.storage.set("latest_hash", new_hash)
    if new_hash != last_hash:
        payload = {"latest_payload": payload_str, "latest_ts": _now()}
        try:
            CACHE_PATH.write_text(json.dumps(payload, indent=2))
            ctx.logger.info(f"💾 Cached raw reply to file: {CACHE_PATH}")
        except Exception as e:
            ctx.logger.warning(f"Failed to write raw cache file: {e}")

def _get_latest(ctx: Context) -> Optional[Dict[str, Any]]:
    raw = ctx.storage.get("latest_payload") or None
    if raw:
        return json.loads(raw)
    try:
        if CACHE_PATH.exists():
            data = json.loads(CACHE_PATH.read_text())
            return json.loads(data.get("latest_payload", "{}"))
    except Exception:
        pass
    return None

def _save_preview(ctx: Context, preview: Dict[str, Any]):
    s = json.dumps(preview, sort_keys=True)
    ctx.storage.set("latest_preview_payload", s)
    ctx.storage.set("latest_preview_ts", _now())
    try:
        PREVIEW_CACHE_PATH.write_text(s)
    except Exception as e:
        ctx.logger.warning(f"Failed to write preview cache file: {e}")

def _get_preview(ctx: Context) -> Optional[Dict[str, Any]]:
    raw = ctx.storage.get("latest_preview_payload")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None
    try:
        if PREVIEW_CACHE_PATH.exists():
            return json.loads(PREVIEW_CACHE_PATH.read_text())
    except Exception:
        pass
    return None

def _to_current_alloc(balances: Dict[str, float]) -> Dict[str, float]:
    total = sum(balances.values()) or 1.0
    return {k: round(v / total, 4) for k, v in balances.items()}

def load_users() -> Dict[str, Any]:
    if USERS_DB_PATH.exists():
        try:
            return json.loads(USERS_DB_PATH.read_text())
        except Exception:
            pass
    return {"seq": 0, "users": {}}

def save_users(db: Dict[str, Any]):
    tmp = USERS_DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, indent=2))
    tmp.replace(USERS_DB_PATH)

def next_user_id(db: Dict[str, Any]) -> int:
    db["seq"] += 1
    return db["seq"]

def fmt_rebalance_msg(plan_like: Dict[str, Any], rationale: Optional[str]) -> str:
    base = plan_like.get("base", "USDC")
    sells = plan_like.get("sells_to_base", []) or []
    buys  = plan_like.get("buys_from_base", []) or []

    def legs(L):
        return "\n".join([f"• {x.get('src')} → {x.get('dst')}: {x.get('amount')}" for x in L]) or "• (none)"

    parts = [
        "🚨 <b>Rebalance Alert</b>",
        f"<b>Routing base:</b> {base}",
        "", "<b>Sells (to base):</b>", legs(sells),
        "", "<b>Buys (from base):</b>",  legs(buys),
        "", f"<b>Base pool end:</b> {plan_like.get('base_pool_end', 0)}",
        f"<b>Shortfall:</b> {plan_like.get('shortfall', 0)}",
    ]
    if rationale:
        parts += ["", f"<b>Rationale:</b> {rationale}"]
    return "\n".join(parts)

def fmt_summary_msg(current: Dict[str, float], suggested: Dict[str, float]) -> str:
    lines = ["📊 <b>Daily Summary</b>", "", "<b>Current Allocation</b>"]
    lines += [f"• {k}: {v:.2%}" for k, v in current.items()]
    lines += ["", "<b>Suggested Allocation</b>"]
    lines += [f"• {k}: {v:.2%}" for k, v in suggested.items()]
    return "\n".join(lines)

def parse_regime(resp_like: Dict[str, Any]) -> str:
    rat = (
        resp_like.get("error")
        or resp_like.get("rationale")
        or resp_like.get("diagnostics_json")
        or ""
    )
    for k in ("RED", "YELLOW", "GREEN"):
        if f"Regime={k}" in rat or f"regime={k}" in rat:
            return k
    return "UNKNOWN"

# ─────────────────────────────────────────────────────────────
# Agent setup
# ─────────────────────────────────────────────────────────────
agent = Agent(
    name=AGENT_NAME,
    seed=CLIENT_SEED,
    mailbox=USE_MAILBOX,
    publish_agent_details=True,
    port=PORT
)

try:
    fund_agent_if_low(agent.wallet.address())
except Exception:
    pass

# ─────────────────────────────────────────────────────────────
# Startup / message handlers (raw cache)
# ─────────────────────────────────────────────────────────────
@agent.on_event("startup")
async def on_start(ctx: Context):
    ctx.logger.info(f"[{AGENT_NAME}] Address: {agent.address}")
    ctx.logger.info(f"Balancer Target: {BALANCER_AGENT_ADDRESS or '<unset>'}")
    ctx.logger.info(f"Mailbox Enabled: {USE_MAILBOX}")
    ctx.logger.info(f"Raw Cache: {CACHE_PATH}")
    ctx.logger.info(f"Preview Cache: {PREVIEW_CACHE_PATH}")
    ctx.logger.info(f"Users DB: {USERS_DB_PATH}")
    _ = load_users()

@agent.on_message(model=RebalanceCheckResponse)
async def on_reply(ctx: Context, sender: str, msg: RebalanceCheckResponse):
    data = {
        "ok": msg.ok,
        "error": msg.error,
        "plan": msg.plan.dict() if msg.plan else None,
        "diagnostics_json": msg.diagnostics_json,
    }
    _save_latest(ctx, data)
    ctx.logger.info("✅ Cached latest rebalance reply")

# ─────────────────────────────────────────────────────────────
# EXISTING: raw rebalance proxy & cache
# ─────────────────────────────────────────────────────────────
@agent.on_rest_post("/rebalance", RebalanceCheckRequest, RebalanceCheckResponse)
async def rebalance(ctx: Context, body: RebalanceCheckRequest) -> RebalanceCheckResponse:
    if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
        return RebalanceCheckResponse(ok=False, error="Balancer address not set")

    # idempotency guard (duplicate within 600ms)
    body_sig = hashlib.sha1(json.dumps(body.dict(), sort_keys=True).encode("utf-8")).hexdigest()
    last_sig = ctx.storage.get("last_req_sig") or ""
    last_ts = ctx.storage.get("last_req_ts") or 0.0
    now_ts = _now()
    duplicate = (body_sig == last_sig) and ((now_ts - float(last_ts)) < 0.6)

    if duplicate:
        ctx.logger.info("↩︎ Duplicate REST request detected within 600ms — not re-sending upstream")
    else:
        await ctx.send(BALANCER_AGENT_ADDRESS, body)
        ctx.storage.set("last_req_sig", body_sig)
        ctx.storage.set("last_req_ts", now_ts)
        ctx.logger.info("→ Sent request to balancer")

    start = _now()
    last = ctx.storage.get("latest_ts") or 0.0

    while _now() - start < DEFAULT_TIMEOUT_SEC:
        await asyncio.sleep(0.2)
        ts = ctx.storage.get("latest_ts") or 0.0
        if ts > last:
            data = _get_latest(ctx)
            return RebalanceCheckResponse(**data)

    cached = _get_latest(ctx)
    if cached:
        ctx.logger.warning("⏱ Timeout — returning cached result")
        return RebalanceCheckResponse(**cached)
    return RebalanceCheckResponse(ok=False, error="Timeout waiting for balancer response")

@agent.on_rest_get("/rebalance/cached", RebalanceCheckResponse)
async def cached(ctx: Context) -> RebalanceCheckResponse:
    data = _get_latest(ctx)
    return RebalanceCheckResponse(**data) if data else RebalanceCheckResponse(ok=False, error="No cache")

# ─────────────────────────────────────────────────────────────
# NEW: preview (raw plan + computed swap_plan + helpful fields)
# ─────────────────────────────────────────────────────────────
async def _compute_preview_after_reply(ctx: Context, body: RebalanceCheckRequest) -> PreviewResponse:
    # balances from body
    balances = {}
    for k, v in body.dict().items():
        if k.endswith("_balance"):
            balances[k.replace("_balance", "").upper()] = float(v)

    # wait for fresh balancer reply (reused logic from /rebalance)
    start = _now()
    last = ctx.storage.get("latest_ts") or 0.0

    while _now() - start < DEFAULT_TIMEOUT_SEC:
        await asyncio.sleep(0.2)
        ts = ctx.storage.get("latest_ts") or 0.0
        if ts > last:
            raw = _get_latest(ctx) or {}
            if not raw.get("ok"):
                return PreviewResponse(ok=False, error=raw.get("error") or "balancer not ok")

            plan = raw.get("plan") or {}
            deltas = plan.get("trade_deltas", {}) or {}
            target_weights = plan.get("target_weights", {}) or {}

            try:
                swap_plan = build_swap_plan(
                    balances=balances,
                    deltas=deltas,
                    base="USDC",
                    wallet_base_available=0.0,
                ).to_dict()
            except Exception as e:
                swap_plan = {"warnings": [f"swapPlanner error: {e}"]}

            current_alloc = _to_current_alloc(balances)
            rationale = raw.get("error") or raw.get("diagnostics_json")

            out = {
                "ok": True,
                "current_allocation": current_alloc,
                "suggested_allocation": target_weights,
                "trade_deltas": deltas,
                "swap_plan": swap_plan,
                "rationale": rationale,
                "error": None,
            }
            _save_preview(ctx, out)
            return PreviewResponse(**out)

    cached = _get_preview(ctx)
    if cached:
        ctx.logger.warning("⏱ Timeout — returning cached PREVIEW")
        return PreviewResponse(**cached)
    return PreviewResponse(ok=False, error="Timeout waiting for balancer response")

@agent.on_rest_post("/rebalance/preview", RebalanceCheckRequest, PreviewResponse)
async def rebalance_preview(ctx: Context, body: RebalanceCheckRequest) -> PreviewResponse:
    if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
        return PreviewResponse(ok=False, error="Balancer address not set")

    # forward (with duplicate guard)
    body_sig = hashlib.sha1(json.dumps(body.dict(), sort_keys=True).encode("utf-8")).hexdigest()
    last_sig = ctx.storage.get("last_req_sig_prev") or ""
    last_ts = ctx.storage.get("last_req_ts_prev") or 0.0
    now_ts = _now()
    duplicate = (body_sig == last_sig) and ((now_ts - float(last_ts)) < 0.6)

    if duplicate:
        ctx.logger.info("↩︎ Duplicate PREVIEW request within 600ms — not re-sending upstream")
    else:
        await ctx.send(BALANCER_AGENT_ADDRESS, body)
        ctx.storage.set("last_req_sig_prev", body_sig)
        ctx.storage.set("last_req_ts_prev", now_ts)
        ctx.logger.info("→ Sent PREVIEW request to balancer")

    return await _compute_preview_after_reply(ctx, body)

@agent.on_rest_get("/rebalance/preview/cached", PreviewResponse)
async def rebalance_preview_cached(ctx: Context) -> PreviewResponse:
    data = _get_preview(ctx)
    if not data:
        return PreviewResponse(ok=False, error="No preview cached")
    return PreviewResponse(**data)

# ─────────────────────────────────────────────────────────────
# Vacation: REST (body style)
# ─────────────────────────────────────────────────────────────
@agent.on_rest_post("/users/onboard", Onboard, OnboardResp)
async def rest_onboard(ctx: Context, body: Onboard) -> OnboardResp:
    db = load_users()
    # dedupe by wallet
    for uid, u in db["users"].items():
        if u["wallet_address"].lower() == body.wallet_address.lower():
            u["telegram_chat_id"] = body.telegram_chat_id
            if body.nickname:
                u["nickname"] = body.nickname
            save_users(db)
            return OnboardResp(ok=True, user_id=int(uid))
    uid = next_user_id(db)
    db["users"][str(uid)] = {
        "wallet_address": body.wallet_address,
        "telegram_chat_id": body.telegram_chat_id,
        "nickname": body.nickname or "",
        "is_active": False,
        "daily_summary_hour_utc": 9,
        "alert_threshold": DEFAULT_ALERT_THRESHOLD,
        "next_summary_at": None,
        "last_alert_at": None,
        "balances_json": None,
        "last_plan_json": None,
        "last_rationale": None,
        "last_regime": None,
    }
    save_users(db)
    return OnboardResp(ok=True, user_id=uid)

@agent.on_rest_post("/users/balances", BalancesWithId, OkResp)
async def rest_balances(ctx: Context, body: BalancesWithId) -> OkResp:
    db = load_users()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    payload = body.dict()
    payload.pop("user_id", None)
    u["balances_json"] = payload
    save_users(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/prefs", PrefsBody, OkResp)
async def prefs_body(ctx: Context, body: PrefsBody) -> OkResp:
    db = load_users()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")

    if body.active is not None:
        u["is_active"] = bool(body.active)
        if u["is_active"] and not u.get("next_summary_at"):
            now = now_utc_dt()
            target = now.replace(hour=int(u["daily_summary_hour_utc"]), minute=0, second=0, microsecond=0)
            if target <= now:
                import datetime as _dt
                target += _dt.timedelta(days=1)
            u["next_summary_at"] = iso(target)

    if body.alert_threshold:
        if body.alert_threshold not in ("RED", "YELLOW", "GREEN"):
            return OkResp(ok=False, error="alert_threshold must be RED|YELLOW|GREEN")
        u["alert_threshold"] = body.alert_threshold

    if body.daily_summary_hour_utc is not None:
        hour = int(body.daily_summary_hour_utc)
        if not (0 <= hour <= 23):
            return OkResp(ok=False, error="daily_summary_hour_utc must be 0..23")
        u["daily_summary_hour_utc"] = hour
        now = now_utc_dt()
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target <= now:
            import datetime as _dt
            target += _dt.timedelta(days=1)
        u["next_summary_at"] = iso(target)

    save_users(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/vacation/start", StartStopBody, OkResp)
async def vacation_start(ctx: Context, body: StartStopBody) -> OkResp:
    db = load_users()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    u["is_active"] = True
    now = now_utc_dt()
    target = now.replace(hour=int(u["daily_summary_hour_utc"]), minute=0, second=0, microsecond=0)
    if target <= now:
        import datetime as _dt
        target += _dt.timedelta(days=1)
    u["next_summary_at"] = iso(target)
    save_users(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/vacation/stop", StartStopBody, OkResp)
async def vacation_stop(ctx: Context, body: StartStopBody) -> OkResp:
    db = load_users()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    u["is_active"] = False
    save_users(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/notify/alert", NotifyBody, OkResp)
async def notify_alert(ctx: Context, body: NotifyBody) -> OkResp:
    db = load_users()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    if not u.get("balances_json"):
        return OkResp(ok=False, error="balances not set")

    # build a RebalanceCheckRequest from user's balances
    req = RebalanceCheckRequest(**{f"{k.lower()}_balance": v for k, v in u["balances_json"].items() if k != "quote_amount"},
                                quote_amount=float(u["balances_json"].get("quote_amount", 1000.0)))

    # send request
    if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
        return OkResp(ok=False, error="Balancer address not set")
    await ctx.send(BALANCER_AGENT_ADDRESS, req)

    # compute preview (includes swap legs)
    preview = await _compute_preview_after_reply(ctx, req)
    if not preview.ok:
        return OkResp(ok=False, error=preview.error or "upstream not ok")

    plan_for_summary = {
        "target_weights": preview.suggested_allocation,
        "trade_deltas": preview.trade_deltas,
        "base": (preview.swap_plan or {}).get("base", "USDC"),
    }
    rationale = preview.rationale or ""

    if bot:
        try:
            await bot.send_message(
                chat_id=u["telegram_chat_id"],
                text=fmt_rebalance_msg(preview.swap_plan or {}, rationale),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            return OkResp(ok=False, error=f"telegram send failed: {e}")

    # store snapshot for summaries
    u["last_alert_at"]  = iso(now_utc_dt())
    u["last_plan_json"] = plan_for_summary
    u["last_rationale"] = rationale
    u["last_regime"]    = parse_regime({"rationale": rationale})
    save_users(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/notify/summary", NotifyBody, OkResp)
async def notify_summary(ctx: Context, body: NotifyBody) -> OkResp:
    db = load_users()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    if not (u.get("balances_json") and u.get("last_plan_json")):
        return OkResp(ok=False, error="need balances + at least one plan")
    bal = u["balances_json"]
    current = _to_current_alloc({
        "USDC": bal.get("usdc_balance", 0.0), "USDT": bal.get("usdt_balance", 0.0),
        "DAI": bal.get("dai_balance", 0.0), "FDUSD": bal.get("fdusd_balance", 0.0),
        "BUSD": bal.get("busd_balance", 0.0), "TUSD": bal.get("tusd_balance", 0.0),
        "USDP": bal.get("usdp_balance", 0.0), "PYUSD": bal.get("pyusd_balance", 0.0),
        "USDD": bal.get("usdd_balance", 0.0), "GUSD": bal.get("gusd_balance", 0.0),
    })
    suggested = u["last_plan_json"].get("target_weights", {}) if isinstance(u["last_plan_json"], dict) else {}
    if bot:
        try:
            await bot.send_message(
                chat_id=u["telegram_chat_id"],
                text=fmt_summary_msg(current, suggested),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            return OkResp(ok=False, error=f"telegram send failed: {e}")
    return OkResp(ok=True)

@agent.on_rest_post("/users/status", StatusBody, StatusResp)
async def status_body(ctx: Context, body: StatusBody) -> StatusResp:
    db = load_users()
    u = db["users"].get(str(body.user_id))
    if not u:
        return StatusResp(ok=False, error="user not found")
    return StatusResp(
        ok=True,
        active=u["is_active"],
        last_regime=u.get("last_regime"),
        last_rationale=u.get("last_rationale"),
        last_plan=u.get("last_plan_json"),
        next_summary_at=u.get("next_summary_at"),
    )

# ─────────────────────────────────────────────────────────────
# Background loops (alerts + daily summaries)
# ─────────────────────────────────────────────────────────────
@agent.on_interval(period=CHECK_INTERVAL_SEC)
async def periodic_alert_check(ctx: Context):
    db = load_users()
    for uid, u in list(db["users"].items()):
        try:
            if not u.get("is_active") or not u.get("balances_json"):
                continue

            req = RebalanceCheckRequest(**{f"{k.lower()}_balance": v for k, v in u["balances_json"].items() if k != "quote_amount"},
                                        quote_amount=float(u["balances_json"].get("quote_amount", 1000.0)))

            if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
                continue
            await ctx.send(BALANCER_AGENT_ADDRESS, req)
            preview = await _compute_preview_after_reply(ctx, req)
            if not preview.ok:
                continue

            plan_for_summary = {
                "target_weights": preview.suggested_allocation,
                "trade_deltas": preview.trade_deltas,
                "base": (preview.swap_plan or {}).get("base", "USDC"),
            }
            rationale = preview.rationale or ""
            regime = parse_regime({"rationale": rationale})

            u["last_plan_json"] = plan_for_summary
            u["last_rationale"] = rationale
            u["last_regime"]    = regime

            order = {"GREEN": 0, "YELLOW": 1, "RED": 2, "UNKNOWN": 3}
            send_if = order.get(regime, 3) >= order.get(u.get("alert_threshold", DEFAULT_ALERT_THRESHOLD), 2)

            last = as_utc(u.get("last_alert_at"))
            import datetime as _dt
            ok_to_send = (last is None) or (now_utc_dt() - last > _dt.timedelta(hours=1))

            if send_if and ok_to_send and bot:
                try:
                    await bot.send_message(
                        chat_id=u["telegram_chat_id"],
                        text=fmt_rebalance_msg(preview.swap_plan or {}, rationale),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    u["last_alert_at"] = iso(now_utc_dt())
                except Exception as e:
                    ctx.logger.warning(f"[alert] telegram send failed user {uid}: {e}")
        except Exception as e:
            ctx.logger.warning(f"[alert] uid={uid} error: {e}")
    save_users(db)

@agent.on_interval(period=SUMMARY_TICK_SEC)
async def periodic_summary_check(ctx: Context):
    db = load_users()
    now = now_utc_dt()
    import datetime as _dt
    for uid, u in list(db["users"].items()):
        try:
            if not u.get("is_active"):
                continue
            nxt = as_utc(u.get("next_summary_at"))
            if (nxt is None) or (now < nxt):
                continue
            if not (u.get("balances_json") and u.get("last_plan_json")):
                u["next_summary_at"] = iso(now + _dt.timedelta(days=1))
                continue

            bal = u["balances_json"]
            current = _to_current_alloc({
                "USDC": bal.get("usdc_balance",0.0), "USDT": bal.get("usdt_balance",0.0),
                "DAI": bal.get("dai_balance",0.0), "FDUSD": bal.get("fdusd_balance",0.0),
                "BUSD": bal.get("busd_balance",0.0), "TUSD": bal.get("tusd_balance",0.0),
                "USDP": bal.get("usdp_balance",0.0), "PYUSD": bal.get("pyusd_balance",0.0),
                "USDD": bal.get("usdd_balance",0.0), "GUSD": bal.get("gusd_balance",0.0),
            })
            suggested = u["last_plan_json"].get("target_weights", {}) if isinstance(u["last_plan_json"], dict) else {}
            if bot:
                try:
                    await bot.send_message(
                        chat_id=u["telegram_chat_id"],
                        text=fmt_summary_msg(current, suggested),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    ctx.logger.warning(f"[summary] telegram send failed user {uid}: {e}")

            next_day = nxt.replace(minute=0, second=0, microsecond=0) + _dt.timedelta(days=1)
            u["next_summary_at"] = iso(next_day)
        except Exception as e:
            ctx.logger.warning(f"[summary] uid={uid} error: {e}")
    save_users(db)

# ─────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────
@agent.on_rest_get("/health", HealthResp)
async def health(_: Context) -> HealthResp:
    return HealthResp(ok=True, agent=AGENT_NAME, upstream=BALANCER_AGENT_ADDRESS or "<unset>", telegram=bool(bot))

# --- Run Agent ---
def run():
    agent.run()

if __name__ == "__main__":
    run()