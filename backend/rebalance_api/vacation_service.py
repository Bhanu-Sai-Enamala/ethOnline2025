# vacation_service.py
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, JSON, Text
)
from sqlalchemy.orm import sessionmaker, declarative_base
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Bot  # python-telegram-bot (core Bot is fine for simple sends)
from swapPlanner import build_swap_plan  # must be in same directory, as you have

# ───────────────────────────────────────────────────────────────
# Config
# ───────────────────────────────────────────────────────────────
PORT_AGENT_URL = os.getenv("PORT_AGENT_URL", "http://127.0.0.1:8011/rebalance").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8455138511:AAE0-J6NdPag8U-va0OjE7F48-LFWYnDTok").strip()
DB_URL = os.getenv("VACATION_DB_URL", "sqlite:///./vacation.db")

CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "600"))             # alert checks
SUMMARY_CHECK_INTERVAL_SEC = int(os.getenv("SUMMARY_CHECK_INTERVAL_SEC", "600"))  # summary scheduler tick

if not TELEGRAM_BOT_TOKEN:
    print("WARNING: TELEGRAM_BOT_TOKEN not set. Telegram sends will fail.")

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

# ───────────────────────────────────────────────────────────────
# Time helpers (make everything UTC-aware)
# ───────────────────────────────────────────────────────────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

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
    created_at = Column(DateTime(timezone=True), default=now_utc)

    # “vacation mode”
    is_active = Column(Boolean, default=False)
    daily_summary_hour_utc = Column(Integer, default=9)  # 09:00 UTC default
    next_summary_at = Column(DateTime(timezone=True), nullable=True)

    # alert/summary prefs
    alert_threshold = Column(String, default="RED")  # RED|YELLOW|GREEN
    last_alert_at = Column(DateTime(timezone=True), nullable=True)

    # last submitted balances snapshot (for calling port agent)
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
    # try the RebalanceCheckResponse 'error' (used for rationale) or 'rationale'
    rat = data.get("error") or data.get("rationale") or ""
    for key in ("RED", "YELLOW", "GREEN"):
        if f"Regime={key}" in rat or f"regime={key}" in rat:
            return key
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
app = FastAPI(title="VacationMode Service", version="0.2.0")

@app.on_event("startup")
async def _startup():
    # Scheduler runs in UTC to match our timestamps
    sched = AsyncIOScheduler(timezone=timezone.utc)
    sched.add_job(periodic_alert_check, "interval", seconds=CHECK_INTERVAL_SEC)
    sched.add_job(periodic_summary_check, "interval", seconds=SUMMARY_CHECK_INTERVAL_SEC)
    sched.start()
    app.state.scheduler = sched
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
                now = now_utc()
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
            now = now_utc()
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
        now = now_utc()
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

# Optional: preview endpoint for the UI
@app.post("/preview", response_model=PreviewOut)
async def preview(balances: BalancesIn):
    data = await call_port_agent(balances.to_agent_payload())
    plan = data.get("plan", {})
    rationale = data.get("error") or data.get("rationale") or ""
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

# Manual triggers (handy for testing from frontend)
@app.post("/users/{user_id}/notify/alert")
async def manual_alert(user_id: int):
    s = SessionLocal()
    try:
        u = s.query(User).get(user_id)
        if not u:
            raise HTTPException(404, "user not found")
        if not u.balances_json:
            raise HTTPException(400, "balances not set for user")
        data = await call_port_agent(u.balances_json)
        plan = data.get("plan", {}) if isinstance(data.get("plan"), dict) else {}
        rationale = data.get("error") or data.get("rationale") or ""
        if bot:
            await send_telegram(u.telegram_chat_id, fmt_rebalance_msg(plan, rationale))
        # record last alert time
        u.last_alert_at = now_utc()
        s.commit()
        return {"ok": True}
    finally:
        s.close()

@app.post("/users/{user_id}/notify/summary")
async def manual_summary(user_id: int):
    s = SessionLocal()
    try:
        u = s.query(User).get(user_id)
        if not u:
            raise HTTPException(404, "user not found")
        if not u.balances_json or not u.last_plan_json:
            raise HTTPException(400, "need balances + at least one plan")
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
        if bot:
            await send_telegram(u.telegram_chat_id, fmt_summary_msg(current, suggested))
        return {"ok": True}
    finally:
        s.close()

# ───────────────────────────────────────────────────────────────
# Background jobs (UTC-aware)
# ───────────────────────────────────────────────────────────────
async def periodic_alert_check():
    s = SessionLocal()
    try:
        users = s.query(User).filter_by(is_active=True).all()
        for u in users:
            if not u.balances_json:
                continue
            # fresh plan
            try:
                data = await call_port_agent(u.balances_json)
            except Exception as e:
                print(f"[alert] user {u.id} port-agent error: {e}")
                continue

            plan = data.get("plan", {}) if isinstance(data.get("plan"), dict) else {}
            rationale = data.get("error") or data.get("rationale") or ""
            regime = parse_regime_from(data)

            # Save last snapshot
            u.last_plan_json = plan
            u.last_rationale = rationale
            u.last_regime = regime
            s.commit()

            # Decide alert: only send if regime >= user threshold (GREEN<YELLOW<RED)
            order = {"GREEN": 0, "YELLOW": 1, "RED": 2, "UNKNOWN": 3}
            if order.get(regime, 3) >= order.get(u.alert_threshold, 2):
                now = now_utc()
                last = as_utc(u.last_alert_at)
                if (last is None) or (now - last > timedelta(hours=1)):
                    if bot:
                        try:
                            await send_telegram(u.telegram_chat_id, fmt_rebalance_msg(plan, rationale))
                            u.last_alert_at = now
                            s.commit()
                        except Exception as e:
                            print(f"[alert] telegram send failed user {u.id}: {e}")
    finally:
        s.close()

async def periodic_summary_check():
    s = SessionLocal()
    try:
        now = now_utc()
        users = s.query(User).filter_by(is_active=True).all()
        for u in users:
            nxt = as_utc(u.next_summary_at)
            if (nxt is None) or (now < nxt):
                continue

            if not u.balances_json or not u.last_plan_json:
                # schedule next day even if nothing to summarize
                u.next_summary_at = now + timedelta(days=1)
                s.commit()
                continue

            # Send summary
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
                    await send_telegram(u.telegram_chat_id, fmt_summary_msg(current, suggested))
                except Exception as e:
                    print(f"[summary] telegram send failed user {u.id}: {e}")

            # schedule next day’s summary at same hour
            next_day = (nxt + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
            u.next_summary_at = next_day
            s.commit()
    finally:
        s.close()