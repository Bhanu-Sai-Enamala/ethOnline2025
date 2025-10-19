import os
import json
import time
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path
import hashlib

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
DEFAULT_TIMEOUT_SEC = float(os.getenv("DEFAULT_TIMEOUT_SEC", "60"))
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
    # Deduplicate identical payloads to avoid double cache logs
    payload_str = json.dumps(resp, sort_keys=True)
    new_hash = hashlib.sha1(payload_str.encode("utf-8")).hexdigest()
    last_hash = ctx.storage.get("latest_hash") or ""
    ctx.storage.set("latest_payload", payload_str)
    ctx.storage.set("latest_ts", _now())
    ctx.storage.set("latest_hash", new_hash)
    if new_hash != last_hash:
        payload = {
            "latest_payload": payload_str,
            "latest_ts": _now(),
        }
        try:
            CACHE_PATH.write_text(json.dumps(payload, indent=2))
            ctx.logger.info(f"💾 Cached to file: {CACHE_PATH}")
        except Exception as e:
            ctx.logger.warning(f"Failed to write cache file: {e}")
    else:
        # Quietly skip duplicate writes
        pass

def _get_latest(ctx: Context) -> Optional[Dict[str, Any]]:
    """Fetch latest cached result (prefer ctx.storage, fallback to file)."""
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

    # Suppress immediate duplicate requests with identical body (idempotency guard)
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