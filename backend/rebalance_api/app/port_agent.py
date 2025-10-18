# import os, json, time
# from typing import Optional, Dict, Any
# from uagents import Agent, Context
# from uagents.setup import fund_agent_if_low
# from app.rebalance_models import RebalanceCheckRequest, RebalanceCheckResponse
# from dotenv import load_dotenv
# import asyncio

# load_dotenv()

# PORT = int(os.getenv("PORT", "8010"))
# CLIENT_SEED = os.getenv("CLIENT_SEED", "ethOnlineseed")
# BALANCER_AGENT_ADDRESS = os.getenv("BALANCER_AGENT_ADDRESS", "").strip()
# USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")
# DEFAULT_TIMEOUT_SEC = float(os.getenv("DEFAULT_TIMEOUT_SEC", "12"))
# AGENT_NAME = "rebalance-api-client"

# # app/port_agent.py  (only this block changes)

# agent = Agent(
#     name="rebalance-rest-port",
#     seed=CLIENT_SEED,
#     mailbox=USE_MAILBOX,
#     publish_agent_details=True,
# )

# try:
#     fund_agent_if_low(agent.wallet.address())
# except Exception:
#     pass

# K_LATEST, K_LAST_TS = "latest_payload", "latest_ts"

# def _now() -> float: return time.time()

# def _save_latest(ctx: Context, resp: Dict[str, Any]):
#     ctx.storage.set(K_LATEST, json.dumps(resp))
#     ctx.storage.set(K_LAST_TS, _now())

# def _get_latest(ctx: Context) -> Optional[Dict[str, Any]]:
#     raw = ctx.storage.get(K_LATEST)
#     return json.loads(raw) if raw else None

# @agent.on_event("startup")
# async def on_start(ctx: Context):
#     ctx.logger.info(f"[{AGENT_NAME}] Address: {agent.address}")
#     ctx.logger.info(f"Balancer: {BALANCER_AGENT_ADDRESS or '<unset>'}, Mailbox={USE_MAILBOX}")

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

# @agent.on_rest_post("/rebalance", RebalanceCheckRequest, RebalanceCheckResponse)
# async def rebalance(ctx: Context, body: RebalanceCheckRequest) -> RebalanceCheckResponse:
#     if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
#         return RebalanceCheckResponse(ok=False, error="Balancer address not set")

#     await ctx.send(BALANCER_AGENT_ADDRESS, body)
#     ctx.logger.info("→ Sent request to balancer")

#     start = _now()
#     last = ctx.storage.get(K_LAST_TS) or 0.0
#     while _now() - start < DEFAULT_TIMEOUT_SEC:
#         await asyncio.sleep(0.2)
#         ts = ctx.storage.get(K_LAST_TS) or 0.0
#         if ts > last:
#             data = _get_latest(ctx)
#             return RebalanceCheckResponse(**data)
#     return RebalanceCheckResponse(ok=False, error="Timeout waiting for balancer response")

# @agent.on_rest_get("/rebalance/cached", RebalanceCheckResponse)
# async def cached(ctx: Context) -> RebalanceCheckResponse:
#     data = _get_latest(ctx)
#     return RebalanceCheckResponse(**data) if data else RebalanceCheckResponse(ok=False, error="No cache")

# @agent.on_rest_get("/health", RebalanceCheckResponse)
# async def health(_: Context) -> RebalanceCheckResponse:
#     return RebalanceCheckResponse(ok=True, diagnostics_json=json.dumps({"status": "ok", "agent": AGENT_NAME}))

# def run():
#     agent.run()

import os
import json
import time
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path

from dotenv import load_dotenv
from uagents import Agent, Context
from uagents.setup import fund_agent_if_low
from app.rebalance_models import RebalanceCheckRequest, RebalanceCheckResponse

# --- Load environment ---
load_dotenv()

PORT = int(os.getenv("PORT", "8011"))
CLIENT_SEED = os.getenv("CLIENT_SEED", "ethOnlineseed")
BALANCER_AGENT_ADDRESS = os.getenv("BALANCER_AGENT_ADDRESS", "").strip()
USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")
DEFAULT_TIMEOUT_SEC = float(os.getenv("DEFAULT_TIMEOUT_SEC", "12"))
AGENT_NAME = "rebalance-rest-port"

# --- Local cache setup (app/data/rebalance_latest.json) ---
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = DATA_DIR / "rebalance_latest.json"

# --- Helper functions ---
def _now() -> float:
    return time.time()

def _save_latest(ctx: Context, resp: Dict[str, Any]):
    """Save latest successful rebalance result both in ctx.storage and to file."""
    ctx.storage.set("latest_payload", json.dumps(resp))
    ctx.storage.set("latest_ts", _now())

    payload = {
        "latest_payload": json.dumps(resp),
        "latest_ts": _now(),
    }
    try:
        CACHE_PATH.write_text(json.dumps(payload, indent=2))
        ctx.logger.info(f"💾 Cached to file: {CACHE_PATH}")
    except Exception as e:
        ctx.logger.warning(f"Failed to write cache file: {e}")

def _get_latest(ctx: Context) -> Optional[Dict[str, Any]]:
    """Fetch latest cached result (prefer ctx.storage, fallback to file)."""
    raw = ctx.storage.get("latest_payload")
    if raw:
        return json.loads(raw)
    try:
        if CACHE_PATH.exists():
            data = json.loads(CACHE_PATH.read_text())
            return json.loads(data.get("latest_payload", "{}"))
    except Exception:
        pass
    return None

# --- Agent setup ---
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

# --- Events and Handlers ---
@agent.on_event("startup")
async def on_start(ctx: Context):
    ctx.logger.info(f"[{AGENT_NAME}] Address: {agent.address}")
    ctx.logger.info(f"Balancer Target: {BALANCER_AGENT_ADDRESS or '<unset>'}")
    ctx.logger.info(f"Mailbox Enabled: {USE_MAILBOX}")
    ctx.logger.info(f"Cache File Path: {CACHE_PATH}")

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

@agent.on_rest_post("/rebalance", RebalanceCheckRequest, RebalanceCheckResponse)
async def rebalance(ctx: Context, body: RebalanceCheckRequest) -> RebalanceCheckResponse:
    """Forward the rebalance request to Balancer agent and wait for the response."""
    if not BALANCER_AGENT_ADDRESS.startswith("agent1q"):
        return RebalanceCheckResponse(ok=False, error="Balancer address not set")

    await ctx.send(BALANCER_AGENT_ADDRESS, body)
    ctx.logger.info("→ Sent request to balancer")

    start = _now()
    last = ctx.storage.get("latest_ts") or 0.0

    while _now() - start < DEFAULT_TIMEOUT_SEC:
        await asyncio.sleep(0.2)
        ts = ctx.storage.get("latest_ts") or 0.0
        if ts > last:
            data = _get_latest(ctx)
            return RebalanceCheckResponse(**data)

    # timeout fallback
    cached = _get_latest(ctx)
    if cached:
        ctx.logger.warning("⏱ Timeout — returning cached result")
        return RebalanceCheckResponse(**cached)
    return RebalanceCheckResponse(ok=False, error="Timeout waiting for balancer response")

@agent.on_rest_get("/rebalance/cached", RebalanceCheckResponse)
async def cached(ctx: Context) -> RebalanceCheckResponse:
    """Serve latest cached result."""
    data = _get_latest(ctx)
    return RebalanceCheckResponse(**data) if data else RebalanceCheckResponse(ok=False, error="No cache")

@agent.on_rest_get("/health", RebalanceCheckResponse)
async def health(_: Context) -> RebalanceCheckResponse:
    """Health check endpoint."""
    status = {"status": "ok", "agent": AGENT_NAME, "upstream": BALANCER_AGENT_ADDRESS or "<unset>"}
    return RebalanceCheckResponse(ok=True, diagnostics_json=json.dumps(status))

# --- Run Agent ---
def run():
    agent.run()

if __name__ == "__main__":
    run()