# # vacation_telegram_bot.py
# import os
# import logging
# from typing import Dict, Any, Optional, List

# from telegram import Update
# from telegram.constants import ParseMode
# from telegram.ext import Application, CommandHandler, ContextTypes

# BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8455138511:AAE0-J6NdPag8U-va0OjE7F48-LFWYnDTok").strip()
# TEST_CHAT_ID = os.getenv("TEST_CHAT_ID", "475651769").strip()  # optional

# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# LOG = logging.getLogger("vacation-telegram")
# if not BOT_TOKEN:
#     raise SystemExit("Set TELEGRAM_BOT_TOKEN env var first!")

# # ---------- formatting ----------
# def fmt_rebalance_alert(plan: Dict[str, Any], rationale: Optional[str] = None) -> str:
#     base = plan.get("base", "USDC")
#     sells = plan.get("sells_to_base", [])
#     buys  = plan.get("buys_from_base", [])
#     warnings = plan.get("warnings", [])

#     def _legs_to_lines(legs: List[Dict[str, Any]]) -> str:
#         lines = []
#         for leg in legs:
#             src = leg.get("src"); dst = leg.get("dst"); amt = leg.get("amount")
#             lines.append(f"• {src} → {dst}: {amt}")
#         return "\n".join(lines) if lines else "• (none)"

#     text = [
#         "🚨 <b>Rebalance Alert</b>",
#         f"<b>Routing base:</b> {base}",
#         "",
#         "<b>Sells (to base):</b>",
#         _legs_to_lines(sells),
#         "",
#         "<b>Buys (from base):</b>",
#         _legs_to_lines(buys),
#         "",
#         f"<b>Base pool end:</b> {plan.get('base_pool_end', 0)}",
#         f"<b>Shortfall:</b> {plan.get('shortfall', 0)}",
#     ]
#     if warnings:
#         text.append("")
#         text.append("<b>Warnings:</b>")
#         for w in warnings:
#             text.append(f"• {w}")
#     if rationale:
#         text.append("")
#         text.append(f"<b>Rationale:</b> {rationale}")
#     return "\n".join(text)

# def fmt_daily_summary(current_alloc: Dict[str, float], suggested_alloc: Dict[str, float]) -> str:
#     lines = ["📊 <b>Daily Summary</b>", "", "<b>Current Allocation</b>"]
#     for k, v in current_alloc.items():
#         lines.append(f"• {k}: {v:.2%}")
#     lines.append("")
#     lines.append("<b>Suggested Allocation</b>")
#     for k, v in suggested_alloc.items():
#         lines.append(f"• {k}: {v:.2%}")
#     return "\n".join(lines)

# # ---------- send helpers ----------
# async def tg_send_text(app: Application, chat_id: int | str, text: str) -> None:
#     await app.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# async def tg_send_rebalance(app: Application, chat_id: int | str, plan: Dict[str, Any], rationale: Optional[str] = None) -> None:
#     await tg_send_text(app, chat_id, fmt_rebalance_alert(plan, rationale))

# async def tg_send_summary(app: Application, chat_id: int | str, current_alloc: Dict[str, float], suggested_alloc: Dict[str, float]) -> None:
#     await tg_send_text(app, chat_id, fmt_daily_summary(current_alloc, suggested_alloc))

# # ---------- command handlers ----------
# async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_html(
#         "👋 Vacation mode bot ready.\n"
#         "Commands:\n"
#         "• /ping – quick check\n"
#         "• /rbtest – send a sample rebalance alert\n"
#         "• /sumtest – send a sample daily summary\n"
#         "• /stop – stop notifications (manual)\n"
#     )

# async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("pong ✅")

# async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("🔕 Stopping manual notifications (no-op demo).")

# async def cmd_rbtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     sample_plan = {
#         "base":"USDC",
#         "sells_to_base":[{"src":"DAI","dst":"USDC","amount":159.6},{"src":"USDD","dst":"USDC","amount":59.6}],
#         "buys_from_base":[{"src":"USDC","dst":"GUSD","amount":316.5},{"src":"USDC","dst":"USDT","amount":178.5}],
#         "base_pool_end":0.0,"shortfall":0.0,"warnings":[]
#     }
#     rationale = "Regime=YELLOW; MeTTa policy active; liquidity gate OK."
#     await tg_send_rebalance(context.application, update.effective_chat.id, sample_plan, rationale)

# async def cmd_sumtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     current = {"USDC":0.30,"USDT":0.20,"DAI":0.125,"GUSD":0.025}
#     suggested = {"USDC":0.10,"USDT":0.233,"DAI":0.085,"GUSD":0.085}
#     await tg_send_summary(context.application, update.effective_chat.id, current, suggested)

# # ---------- post_init hook ----------
# async def _post_init(app: Application) -> None:
#     if TEST_CHAT_ID:
#         try:
#             await tg_send_text(app, TEST_CHAT_ID, "✅ VacationMode bot is live. Send /start here for commands.")
#             LOG.info("Sent startup test message.")
#         except Exception as e:
#             LOG.warning(f"Startup test failed: {e}")

# # ---------- entry ----------
# def main():
#     app = (
#         Application
#         .builder()
#         .token(BOT_TOKEN)
#         .post_init(_post_init)   # will run after init/start
#         .build()
#     )

#     app.add_handler(CommandHandler("start", cmd_start))
#     app.add_handler(CommandHandler("ping", cmd_ping))
#     app.add_handler(CommandHandler("stop", cmd_stop))
#     app.add_handler(CommandHandler("rbtest", cmd_rbtest))
#     app.add_handler(CommandHandler("sumtest", cmd_sumtest))

#     LOG.info("Bot polling…")
#     app.run_polling()  # <-- blocking; manages its own event loop

# if __name__ == "__main__":
#     main()

# vacation_service.py
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Float, JSON, Text
)
from sqlalchemy.orm import sessionmaker, declarative_base
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Bot
from ethOnline2025.backend.rebalance_api.app.swapPlanner import build_swap_plan  # in same directory

# ───────────────────────────────────────────────────────────────
# Config
# ───────────────────────────────────────────────────────────────
PORT_AGENT_URL = os.getenv("PORT_AGENT_URL", "http://127.0.0.1:8011/rebalance").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8455138511:AAE0-J6NdPag8U-va0OjE7F48-LFWYnDTok").strip()
DB_URL = os.getenv("VACATION_DB_URL", "sqlite:///./vacation.db")

ALERT_THRESHOLD = os.getenv("ALERT_THRESHOLD", "RED|YELLOW|GREEN")  # default: alert on all, override per user
CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "60"))    # 10 min periodic alert checks
SUMMARY_CHECK_INTERVAL_SEC = int(os.getenv("SUMMARY_CHECK_INTERVAL_SEC", "30"))  # 5 min, send if due

if not TELEGRAM_BOT_TOKEN:
    print("WARNING: TELEGRAM_BOT_TOKEN not set. Telegram sends will fail.")

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

# ───────────────────────────────────────────────────────────────
# DB setup
# ───────────────────────────────────────────────────────────────
Base = declarative_base()
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    wallet_address = Column(String, unique=True, index=True, nullable=False)
    telegram_chat_id = Column(String, nullable=False)
    nickname = Column(String, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # “vacation mode”
    is_active = Column(Boolean, default=False)
    daily_summary_hour_utc = Column(Integer, default=9)  # 09:00 UTC default
    next_summary_at = Column(DateTime, nullable=True)

    # alert/summary prefs
    alert_threshold = Column(String, default="RED")  # RED|YELLOW|GREEN
    last_alert_at = Column(DateTime, nullable=True)

    # last submitted balances snapshot (for calling port agent)
    # store human balances dict and last plan
    balances_json = Column(JSON, nullable=True)
    last_plan_json = Column(JSON, nullable=True)
    last_rationale = Column(Text, nullable=True)
    last_regime = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

# ───────────────────────────────────────────────────────────────
# Pydantic schemas
# ───────────────────────────────────────────────────────────────
class BalancesIn(BaseModel):
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

    def to_agent_payload(self) -> Dict[str, float]:
        return self.dict()

class OnboardIn(BaseModel):
    wallet_address: str
    telegram_chat_id: str
    nickname: Optional[str] = ""

class PrefsIn(BaseModel):
    active: Optional[bool] = None
    alert_threshold: Optional[str] = Field(None, description="RED|YELLOW|GREEN")
    daily_summary_hour_utc: Optional[int] = Field(None, ge=0, le=23)

class PreviewOut(BaseModel):
    current_allocation: Dict[str, float]
    suggested_allocation: Dict[str, float]
    trade_deltas: Dict[str, float]
    swap_plan: Dict[str, Any]
    rationale: str

class StatusOut(BaseModel):
    active: bool
    last_regime: Optional[str]
    last_rationale: Optional[str]
    last_plan: Optional[Dict[str, Any]]
    next_summary_at: Optional[datetime]

# ───────────────────────────────────────────────────────────────
# Utilities
# ───────────────────────────────────────────────────────────────
async def call_port_agent(balances: Dict[str, float]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(PORT_AGENT_URL, json=balances)
        if r.status_code != 200:
            raise HTTPException(502, detail=f"Port agent error {r.status_code}: {r.text}")
        data = r.json()
        if not data.get("ok"):
            raise HTTPException(502, detail=f"Port agent returned not ok: {data}")
        return data

def parse_regime_from(data: Dict[str, Any]) -> str:
    # Reasoner result may include 'rationale' like "Regime=YELLOW, ..."
    # or error field with rationale text. Prefer Reasoner field if present.
    # Our UI preview wrapper returns 'rationale' at top-level too.
    rat = data.get("error") or data.get("rationale") or ""
    # Try to detect "Regime=RED|YELLOW|GREEN"
    for key in ("RED", "YELLOW", "GREEN"):
        if f"Regime={key}" in rat or f"regime={key}" in rat:
            return key
    # last resort: if plan had alert_level in some versions
    plan_regime = data.get("alert_level")
    if plan_regime in ("RED", "YELLOW", "GREEN"):
        return plan_regime
    return "UNKNOWN"

async def send_telegram(chat_id: str | int, text: str) -> None:
    if not bot:
        raise RuntimeError("Telegram BOT not configured")
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)

def fmt_rebalance_msg(plan: Dict[str, Any], rationale: Optional[str]) -> str:
    sells = plan.get("sells_to_base", [])
    buys = plan.get("buys_from_base", [])
    base = plan.get("base", "USDC")
    def legs(lines):
        return "\n".join([f"• {l.get('src')} → {l.get('dst')}: {l.get('amount')}" for l in lines]) or "• (none)"
    msg = [
        "🚨 <b>Rebalance Alert</b>",
        f"<b>Routing base:</b> {base}",
        "",
        "<b>Sells (to base):</b>",
        legs(sells),
        "",
        "<b>Buys (from base):</b>",
        legs(buys),
        "",
        f"<b>Base pool end:</b> {plan.get('base_pool_end', 0)}",
        f"<b>Shortfall:</b> {plan.get('shortfall', 0)}",
    ]
    if rationale:
        msg += ["", f"<b>Rationale:</b> {rationale}"]
    return "\n".join(msg)

def fmt_summary_msg(current: Dict[str, float], suggested: Dict[str, float]) -> str:
    lines = ["📊 <b>Daily Summary</b>", "", "<b>Current Allocation</b>"]
    lines += [f"• {k}: {v:.2%}" for k, v in current.items()]
    lines += ["", "<b>Suggested Allocation</b>"]
    lines += [f"• {k}: {v:.2%}" for k, v in suggested.items()]
    return "\n".join(lines)

def to_current_alloc(balances: Dict[str, float]) -> Dict[str, float]:
    total = sum(balances.values()) or 1.0
    return {k: round(v/total, 4) for k, v in balances.items()}

# ───────────────────────────────────────────────────────────────
# FastAPI
# ───────────────────────────────────────────────────────────────
app = FastAPI(title="VacationMode Service", version="0.1.0")

@app.on_event("startup")
async def _startup():
    # Start scheduler
    app.state.scheduler = AsyncIOScheduler()
    app.state.scheduler.add_job(periodic_alert_check, "interval", seconds=CHECK_INTERVAL_SEC)
    app.state.scheduler.add_job(periodic_summary_check, "interval", seconds=SUMMARY_CHECK_INTERVAL_SEC)
    app.state.scheduler.start()
    print("[vacation] scheduler started.")

@app.on_event("shutdown")
async def _shutdown():
    sched = getattr(app.state, "scheduler", None)
    if sched:
        sched.shutdown(wait=False)

# ───────────────────────────────────────────────────────────────
# Public REST: onboarding & prefs
# ───────────────────────────────────────────────────────────────
@app.post("/users/onboard")
def onboard_user(payload: OnboardIn):
    s = SessionLocal()
    try:
        u = s.query(User).filter_by(wallet_address=payload.wallet_address).one_or_none()
        if u:
            # update chat id / nickname
            u.telegram_chat_id = payload.telegram_chat_id
            u.nickname = payload.nickname or u.nickname
        else:
            u = User(
                wallet_address=payload.wallet_address,
                telegram_chat_id=payload.telegram_chat_id,
                nickname=payload.nickname or "",
                is_active=False,
                daily_summary_hour_utc=9,
                alert_threshold="RED",
                next_summary_at=None,
            )
            s.add(u)
        s.commit()
        return {"ok": True, "user_id": u.id}
    finally:
        s.close()

@app.post("/users/{user_id}/balances")
def update_balances(user_id: int, balances: BalancesIn):
    s = SessionLocal()
    try:
        u = s.query(User).get(user_id)
        if not u:
            raise HTTPException(404, "user not found")
        u.balances_json = balances.to_agent_payload()
        s.commit()
        return {"ok": True}
    finally:
        s.close()

@app.post("/users/{user_id}/prefs")
def update_prefs(user_id: int, prefs: PrefsIn):
    s = SessionLocal()
    try:
        u = s.query(User).get(user_id)
        if not u:
            raise HTTPException(404, "user not found")
        if prefs.active is not None:
            u.is_active = bool(prefs.active)
            if u.is_active and not u.next_summary_at:
                # schedule next daily at next HH:00 UTC
                now = datetime.now(timezone.utc)
                target = now.replace(hour=u.daily_summary_hour_utc, minute=0, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                u.next_summary_at = target
        if prefs.alert_threshold:
            if prefs.alert_threshold not in ("RED", "YELLOW", "GREEN"):
                raise HTTPException(400, "alert_threshold must be RED|YELLOW|GREEN")
            u.alert_threshold = prefs.alert_threshold
        if prefs.daily_summary_hour_utc is not None:
            u.daily_summary_hour_utc = int(prefs.daily_summary_hour_utc)
            # reset next_summary_at to next occurrence
            now = datetime.now(timezone.utc)
            target = now.replace(hour=u.daily_summary_hour_utc, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            u.next_summary_at = target
        s.commit()
        return {"ok": True}
    finally:
        s.close()

@app.post("/users/{user_id}/vacation/start")
def start_vacation(user_id: int):
    s = SessionLocal()
    try:
        u = s.query(User).get(user_id)
        if not u:
            raise HTTPException(404, "user not found")
        u.is_active = True
        now = datetime.now(timezone.utc)
        target = now.replace(hour=u.daily_summary_hour_utc, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        u.next_summary_at = target
        s.commit()
        return {"ok": True}
    finally:
        s.close()

@app.post("/users/{user_id}/vacation/stop")
def stop_vacation(user_id: int):
    s = SessionLocal()
    try:
        u = s.query(User).get(user_id)
        if not u:
            raise HTTPException(404, "user not found")
        u.is_active = False
        s.commit()
        return {"ok": True}
    finally:
        s.close()

@app.get("/users/{user_id}/status", response_model=StatusOut)
def get_status(user_id: int):
    s = SessionLocal()
    try:
        u = s.query(User).get(user_id)
        if not u:
            raise HTTPException(404, "user not found")
        return StatusOut(
            active=u.is_active,
            last_regime=u.last_regime,
            last_rationale=u.last_rationale,
            last_plan=u.last_plan_json,
            next_summary_at=u.next_summary_at,
        )
    finally:
        s.close()

# Optional: preview endpoint like your /ui/preview but here for convenience
@app.post("/preview", response_model=PreviewOut)
async def preview(balances: BalancesIn):
    data = await call_port_agent(balances.to_agent_payload())
    plan = data.get("plan", {})
    rationale = data.get("error") or data.get("rationale") or ""
    # compute min_receive in your UI if needed; here we skip
    current_alloc = to_current_alloc({
        "USDC": balances.usdc_balance, "USDT": balances.usdt_balance, "DAI": balances.dai_balance,
        "FDUSD": balances.fdusd_balance, "BUSD": balances.busd_balance, "TUSD": balances.tusd_balance,
        "USDP": balances.usdp_balance, "PYUSD": balances.pyusd_balance, "USDD": balances.usdd_balance,
        "GUSD": balances.gusd_balance
    })
    return PreviewOut(
        current_allocation=current_alloc,
        suggested_allocation=plan.get("target_weights", {}),
        trade_deltas=plan.get("trade_deltas", {}),
        swap_plan=plan if isinstance(plan, dict) else {},
        rationale=rationale
    )

# ───────────────────────────────────────────────────────────────
# Background jobs
# ───────────────────────────────────────────────────────────────
async def periodic_alert_check():
    s = SessionLocal()
    try:
        users = s.query(User).filter_by(is_active=True).all()
        for u in users:
            if not u.balances_json:
                continue
            # Ask port agent for a fresh plan
            try:
                data = await call_port_agent(u.balances_json)
            except Exception as e:
                print(f"[alert] user {u.id} port-agent error: {e}")
                continue

            plan = data.get("plan", {})
            rationale = data.get("error") or data.get("rationale") or ""
            regime = parse_regime_from(data)

            # Save last
            u.last_plan_json = plan
            u.last_rationale = rationale
            u.last_regime = regime
            s.commit()

            # Decide alert: only send if regime >= user threshold
            order = {"GREEN": 0, "YELLOW": 1, "RED": 2, "UNKNOWN": 3}
            if order.get(regime, 3) >= order.get(u.alert_threshold, 2):
                # avoid spamming if same regime within 1 hr
                now = datetime.now(timezone.utc)
                if not u.last_alert_at or (now - u.last_alert_at) > timedelta(hours=1):
                    if bot:
                        try:
                            text = fmt_rebalance_msg(plan if isinstance(plan, dict) else {}, rationale)
                            await send_telegram(u.telegram_chat_id, text)
                            u.last_alert_at = now
                            s.commit()
                        except Exception as e:
                            print(f"[alert] telegram send failed user {u.id}: {e}")
    finally:
        s.close()

async def periodic_summary_check():
    s = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        users = s.query(User).filter_by(is_active=True).all()
        for u in users:
            if not u.next_summary_at or now < u.next_summary_at:
                continue
            if not u.balances_json or not u.last_plan_json:
                # nothing to summarize yet; schedule next day anyway
                u.next_summary_at = now + timedelta(days=1)
                s.commit()
                continue

            if bot:
                try:
                    current = to_current_alloc({
                        "USDC": u.balances_json.get("usdc_balance", 0.0),
                        "USDT": u.balances_json.get("usdt_balance", 0.0),
                        "DAI":  u.balances_json.get("dai_balance", 0.0),
                        "FDUSD":u.balances_json.get("fdusd_balance", 0.0),
                        "BUSD": u.balances_json.get("busd_balance", 0.0),
                        "TUSD": u.balances_json.get("tusd_balance", 0.0),
                        "USDP": u.balances_json.get("usdp_balance", 0.0),
                        "PYUSD":u.balances_json.get("pyusd_balance", 0.0),
                        "USDD": u.balances_json.get("usdd_balance", 0.0),
                        "GUSD": u.balances_json.get("gusd_balance", 0.0),
                    })
                    suggested = u.last_plan_json.get("target_weights", {}) if isinstance(u.last_plan_json, dict) else {}
                    text = fmt_summary_msg(current, suggested)
                    await send_telegram(u.telegram_chat_id, text)
                except Exception as e:
                    print(f"[summary] telegram send failed user {u.id}: {e}")

            # schedule next day’s summary
            u.next_summary_at = u.next_summary_at + timedelta(days=1)
            s.commit()
    finally:
        s.close()