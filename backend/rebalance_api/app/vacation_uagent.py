# vacation_uagent.py
import os, json, httpx
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from uagents import Agent, Context, Model
from uagents.setup import fund_agent_if_low

from telegram import Bot  # send-only usage

# ───────────────────────────────────────────────────────────────
# Config
# ───────────────────────────────────────────────────────────────
AGENT_NAME = os.getenv("VAC_AGENT_NAME", "vacation-uagent")
PORT = int(os.getenv("VAC_AGENT_PORT", "8091"))
USE_MAILBOX = str(os.getenv("USE_MAILBOX", "true")).lower() in ("1", "true", "yes", "y")

# If you want this agent to use its own local compute, set: PORT_AGENT_URL=local
PORT_AGENT_URL = os.getenv("PORT_AGENT_URL", "local").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "120"))
SUMMARY_TICK_SEC  = int(os.getenv("SUMMARY_TICK_SEC", "60"))

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "vacation_users.json"

bot = Bot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

# ───────────────────────────────────────────────────────────────
# Helpers (UTC times, JSON "DB")
# ───────────────────────────────────────────────────────────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def as_utc(x: Optional[str | datetime]) -> Optional[datetime]:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(x)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None

def load_db() -> Dict[str, Any]:
    if DB_PATH.exists():
        try:
            return json.loads(DB_PATH.read_text())
        except Exception:
            pass
    return {"seq": 0, "users": {}}

def save_db(db: Dict[str, Any]):
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, indent=2))
    tmp.replace(DB_PATH)

def next_id(db: Dict[str, Any]) -> int:
    db["seq"] += 1
    return db["seq"]

async def tg_send(chat_id: str | int, text: str):
    if not bot:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)

def to_alloc(bal: Dict[str, float]) -> Dict[str, float]:
    total = sum(bal.values()) or 1.0
    return {k: round(v / total, 4) for k, v in bal.items()}

def fmt_rebalance_msg(plan: Dict[str, Any], rationale: Optional[str]) -> str:
    base = plan.get("base", "USDC")
    sells = plan.get("sells_to_base", []) or []
    buys  = plan.get("buys_from_base", []) or []
    def legs(L): return "\n".join([f"• {x.get('src')} → {x.get('dst')}: {x.get('amount')}" for x in L]) or "• (none)"
    parts = [
        "🚨 <b>Rebalance Alert</b>",
        f"<b>Routing base:</b> {base}",
        "", "<b>Sells (to base):</b>", legs(sells),
        "", "<b>Buys (from base):</b>", legs(buys),
        "", f"<b>Base pool end:</b> {plan.get('base_pool_end', 0)}",
        f"<b>Shortfall:</b> {plan.get('shortfall', 0)}",
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

def parse_regime(resp: Dict[str, Any]) -> str:
    rat = resp.get("error") or resp.get("rationale") or ""
    for k in ("RED", "YELLOW", "GREEN"):
        if f"Regime={k}" in rat or f"regime={k}" in rat:
            return k
    return "UNKNOWN"

# ───────────────────────────────────────────────────────────────
# Local Port-Agent integration (swapPlanner)
# ───────────────────────────────────────────────────────────────
try:
    # must be next to this file (backend/rebalance_api/swapPlanner.py)
    from swapPlanner import build_swap_plan
except Exception:
    build_swap_plan = None  # guarded usage below

_LAST_PREVIEW: Dict[str, Any] | None = None

def compute_preview_from_balances(balances: Dict[str, float]) -> Dict[str, Any]:
    """
    Build a preview similar to your original port-agent:
    return {"ok": True/False, "plan": {...}, "rationale": "...", "error": "...?"}
    """
    global _LAST_PREVIEW
    try:
        if build_swap_plan is None:
            # Minimal fallback so the app still works without planner import
            plan = {
                "base": "USDC",
                "sells_to_base": [],
                "buys_from_base": [],
                "base_pool_end": 0.0,
                "shortfall": 0.0,
                "target_weights": {},
                "trade_deltas": {},
            }
            resp = {"ok": True, "plan": plan, "rationale": "Planner not available. Regime=GREEN"}
        else:
            plan = build_swap_plan(balances)  # expected to return your combined plan dict
            rationale = plan.get("rationale") or "Reasoner: MeTTa policy. Regime=GREEN"
            resp = {"ok": True, "plan": plan, "rationale": rationale}
        _LAST_PREVIEW = resp
        return resp
    except Exception as e:
        resp = {"ok": False, "error": f"planner error: {e}"}
        _LAST_PREVIEW = resp
        return resp

async def call_port_agent(payload: Dict[str, float]) -> Dict[str, Any]:
    """
    If PORT_AGENT_URL=local (default here), compute locally.
    Otherwise POST to PORT_AGENT_URL (remote service).
    """
    if PORT_AGENT_URL.lower() == "local":
        return compute_preview_from_balances(payload)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(PORT_AGENT_URL, json=payload)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"port-agent not ok: {data}")
        return data

# ───────────────────────────────────────────────────────────────
# Request/Response Models (uAgents' pydantic Model)
# ───────────────────────────────────────────────────────────────
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

class PreviewResp(Model):
    ok: bool
    plan: Optional[Dict[str, Any]] = None
    rationale: Optional[str] = None
    error: Optional[str] = None

# ───────────────────────────────────────────────────────────────
# Agent
# ───────────────────────────────────────────────────────────────
agent = Agent(
    name=AGENT_NAME,
    seed=os.getenv("VAC_AGENT_SEED", "vacation-seed"),
    mailbox=USE_MAILBOX,
    publish_agent_details=True,
    port=PORT,
)

try:
    fund_agent_if_low(agent.wallet.address())
except Exception:
    pass

@agent.on_event("startup")
async def on_start(ctx: Context):
    ctx.logger.info(f"[{AGENT_NAME}] Address: {agent.address}")
    ctx.logger.info(f"Mailbox Enabled: {bool(USE_MAILBOX)}")
    ctx.logger.info(f"DB: {DB_PATH}")
    ctx.logger.info(f"Planner: {'local' if PORT_AGENT_URL.lower() == 'local' else PORT_AGENT_URL}")
    _ = load_db()

# ───────────────────────────────────────────────────────────────
# Unified Port-Agent routes (same service)
# ───────────────────────────────────────────────────────────────
@agent.on_rest_post("/rebalance/preview", Balances, PreviewResp)
async def rebalance_preview(ctx: Context, body: Balances) -> PreviewResp:
    resp = compute_preview_from_balances(body.dict())
    return PreviewResp(**resp)

@agent.on_rest_get("/rebalance/preview/cached", PreviewResp)
async def rebalance_preview_cached(ctx: Context) -> PreviewResp:
    global _LAST_PREVIEW
    if _LAST_PREVIEW is None:
        return PreviewResp(ok=False, error="no preview in cache yet")
    return PreviewResp(**_LAST_PREVIEW)

# ───────────────────────────────────────────────────────────────
# REST: onboarding & balances (body-style + path-style kept)
# ───────────────────────────────────────────────────────────────
@agent.on_rest_post("/users/onboard", Onboard, OnboardResp)
async def rest_onboard(ctx: Context, body: Onboard) -> OnboardResp:
    db = load_db()
    # dedupe by wallet
    for uid, u in db["users"].items():
        if u["wallet_address"].lower() == body.wallet_address.lower():
            u["telegram_chat_id"] = body.telegram_chat_id
            if body.nickname:
                u["nickname"] = body.nickname
            save_db(db)
            return OnboardResp(ok=True, user_id=int(uid))
    uid = next_id(db)
    db["users"][str(uid)] = {
        "wallet_address": body.wallet_address,
        "telegram_chat_id": body.telegram_chat_id,
        "nickname": body.nickname or "",
        "is_active": False,
        "daily_summary_hour_utc": 9,
        "alert_threshold": "RED",
        "next_summary_at": None,
        "last_alert_at": None,
        "balances_json": None,
        "last_plan_json": None,
        "last_rationale": None,
        "last_regime": None,
    }
    save_db(db)
    return OnboardResp(ok=True, user_id=uid)

@agent.on_rest_post("/users/{user_id}/balances", Balances, OkResp)
async def rest_balances_path(ctx: Context, user_id: str, body: Balances) -> OkResp:
    db = load_db()
    u = db["users"].get(user_id)  # use path param correctly
    if not u:
        return OkResp(ok=False, error="user not found")
    u["balances_json"] = body.dict()
    save_db(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/balances", BalancesWithId, OkResp)
async def rest_balances_body(ctx: Context, body: BalancesWithId) -> OkResp:
    db = load_db()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    payload = body.dict()
    payload.pop("user_id", None)
    u["balances_json"] = payload
    save_db(db)
    return OkResp(ok=True)

# ───────────────────────────────────────────────────────────────
# Body-style control (prefs/start/stop/notify/status)
# ───────────────────────────────────────────────────────────────
@agent.on_rest_post("/users/prefs", PrefsBody, OkResp)
async def prefs_body(ctx: Context, body: PrefsBody) -> OkResp:
    db = load_db()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")

    if body.active is not None:
        u["is_active"] = bool(body.active)
        if u["is_active"] and not u.get("next_summary_at"):
            now = now_utc()
            target = now.replace(hour=int(u["daily_summary_hour_utc"]), minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
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
        now = now_utc()
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        u["next_summary_at"] = iso(target)

    save_db(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/vacation/start", StartStopBody, OkResp)
async def vacation_start_body(ctx: Context, body: StartStopBody) -> OkResp:
    db = load_db()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    u["is_active"] = True
    now = now_utc()
    target = now.replace(hour=int(u["daily_summary_hour_utc"]), minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    u["next_summary_at"] = iso(target)
    save_db(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/vacation/stop", StartStopBody, OkResp)
async def vacation_stop_body(ctx: Context, body: StartStopBody) -> OkResp:
    db = load_db()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    u["is_active"] = False
    save_db(db)
    return OkResp(ok=True)

@agent.on_rest_post("/users/notify/alert", NotifyBody, OkResp)
async def notify_alert_body(ctx: Context, body: NotifyBody) -> OkResp:
    db = load_db()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    if not u.get("balances_json"):
        return OkResp(ok=False, error="balances not set")
    try:
        data = await call_port_agent(u["balances_json"])
        plan = data.get("plan", {}) if isinstance(data.get("plan"), dict) else {}
        rationale = data.get("error") or data.get("rationale") or ""
        if bot:
            await tg_send(u["telegram_chat_id"], fmt_rebalance_msg(plan, rationale))
        u["last_alert_at"] = iso(now_utc())
        u["last_plan_json"] = plan
        u["last_rationale"] = rationale
        u["last_regime"] = parse_regime(data)
        save_db(db)
        return OkResp(ok=True)
    except Exception as e:
        return OkResp(ok=False, error=str(e))

@agent.on_rest_post("/users/notify/summary", NotifyBody, OkResp)
async def notify_summary_body(ctx: Context, body: NotifyBody) -> OkResp:
    db = load_db()
    u = db["users"].get(str(body.user_id))
    if not u:
        return OkResp(ok=False, error="user not found")
    if not (u.get("balances_json") and u.get("last_plan_json")):
        return OkResp(ok=False, error="need balances + at least one plan")
    bal = u["balances_json"]
    current = to_alloc({
        "USDC": bal.get("usdc_balance", 0.0), "USDT": bal.get("usdt_balance", 0.0),
        "DAI": bal.get("dai_balance", 0.0), "FDUSD": bal.get("fdusd_balance", 0.0),
        "BUSD": bal.get("busd_balance", 0.0), "TUSD": bal.get("tusd_balance", 0.0),
        "USDP": bal.get("usdp_balance", 0.0), "PYUSD": bal.get("pyusd_balance", 0.0),
        "USDD": bal.get("usdd_balance", 0.0), "GUSD": bal.get("gusd_balance", 0.0),
    })
    suggested = u["last_plan_json"].get("target_weights", {}) if isinstance(u["last_plan_json"], dict) else {}
    if bot:
        await tg_send(u["telegram_chat_id"], fmt_summary_msg(current, suggested))
    return OkResp(ok=True)

@agent.on_rest_post("/users/status", StatusBody, StatusResp)
async def status_body(ctx: Context, body: StatusBody) -> StatusResp:
    db = load_db()
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

# ───────────────────────────────────────────────────────────────
# Background loops (agent timers)
# ───────────────────────────────────────────────────────────────
@agent.on_interval(period=CHECK_INTERVAL_SEC)
async def periodic_alert_check(ctx: Context):
    db = load_db()
    for uid, u in list(db["users"].items()):
        try:
            if not u.get("is_active") or not u.get("balances_json"):
                continue
            data = await call_port_agent(u["balances_json"])
            plan = data.get("plan", {}) if isinstance(data.get("plan"), dict) else {}
            rationale = data.get("error") or data.get("rationale") or ""
            regime = parse_regime(data)

            u["last_plan_json"] = plan
            u["last_rationale"] = rationale
            u["last_regime"] = regime

            order = {"GREEN": 0, "YELLOW": 1, "RED": 2, "UNKNOWN": 3}
            send_if = order.get(regime, 3) >= order.get(u.get("alert_threshold", "RED"), 2)

            last = as_utc(u.get("last_alert_at"))
            ok_to_send = (last is None) or (now_utc() - last > timedelta(hours=1))

            if send_if and ok_to_send and bot:
                await tg_send(u["telegram_chat_id"], fmt_rebalance_msg(plan, rationale))
                u["last_alert_at"] = iso(now_utc())
        except Exception as e:
            ctx.logger.warning(f"[alert] uid={uid} error: {e}")
    save_db(db)

@agent.on_interval(period=SUMMARY_TICK_SEC)
async def periodic_summary_check(ctx: Context):
    db = load_db()
    now = now_utc()
    for uid, u in list(db["users"].items()):
        try:
            if not u.get("is_active"):
                continue
            nxt = as_utc(u.get("next_summary_at"))
            if (nxt is None) or (now < nxt):
                continue
            if not (u.get("balances_json") and u.get("last_plan_json")):
                u["next_summary_at"] = iso(now + timedelta(days=1))
                continue

            bal = u["balances_json"]
            current = to_alloc({
                "USDC": bal.get("usdc_balance", 0.0), "USDT": bal.get("usdt_balance", 0.0),
                "DAI": bal.get("dai_balance", 0.0), "FDUSD": bal.get("fdusd_balance", 0.0),
                "BUSD": bal.get("busd_balance", 0.0), "TUSD": bal.get("tusd_balance", 0.0),
                "USDP": bal.get("usdp_balance", 0.0), "PYUSD": bal.get("pyusd_balance", 0.0),
                "USDD": bal.get("usdd_balance", 0.0), "GUSD": bal.get("gusd_balance", 0.0),
            })
            suggested = u["last_plan_json"].get("target_weights", {}) if isinstance(u["last_plan_json"], dict) else {}
            if bot:
                await tg_send(u["telegram_chat_id"], fmt_summary_msg(current, suggested))

            next_day = nxt.replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
            u["next_summary_at"] = iso(next_day)
        except Exception as e:
            ctx.logger.warning(f"[summary] uid={uid} error: {e}")
    save_db(db)

# ───────────────────────────────────────────────────────────────
# Health
# ───────────────────────────────────────────────────────────────
@agent.on_rest_get("/health", HealthResp)
async def rest_health(ctx: Context) -> HealthResp:
    return HealthResp(
        ok=True,
        agent=AGENT_NAME,
        upstream=("local" if PORT_AGENT_URL.lower() == "local" else PORT_AGENT_URL),
        telegram=bool(bot)
    )

# ───────────────────────────────────────────────────────────────
# Run
# ───────────────────────────────────────────────────────────────
def run():
    agent.run()

if __name__ == "__main__":
    run()