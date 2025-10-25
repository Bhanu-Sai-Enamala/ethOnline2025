# ui_preview_api.py (snippet)
import os, json
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from ethOnline2025.backend.rebalance_api.app.swapPlanner import build_swap_plan  # <-- your planner

PORT_AGENT = os.getenv("PORT_AGENT_URL", "http://127.0.0.1:8011").rstrip("/")
HTTP_TIMEOUT = 20.0

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

app = FastAPI()

def _balances_dict(req: BalancesIn) -> Dict[str, float]:
    # programmatically collect *_balance fields -> {"USDC": ..., ...}
    d = req.dict()
    out = {}
    for k, v in d.items():
        if k.endswith("_balance"):
            out[k[:-8].upper()] = float(v)
    return out

def apply_slippage(plan: dict, slippage_bps: int = 30):
    s = slippage_bps / 10_000.0
    for leg in plan["sells_to_base"]:
        leg["min_receive"] = round(leg["amount"] * (1 - s), 2)
    for leg in plan["buys_from_base"]:
        leg["min_receive"] = round(leg["amount"] * (1 - s), 2)
    return plan

@app.post("/ui/preview")
async def ui_preview(body: BalancesIn):
    # 1) call the port agent
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(f"{PORT_AGENT}/rebalance", json=json.loads(body.json()))
    if r.status_code != 200:
        raise HTTPException(502, f"Port agent error HTTP {r.status_code}: {r.text[:200]}")
    agent_resp = r.json()
    if not agent_resp.get("ok"):
        raise HTTPException(502, agent_resp.get("error", "Unknown error from port agent"))

    plan = agent_resp.get("plan") or {}
    deltas = plan.get("trade_deltas") or {}            # <-- feed this into planner
    current_w = plan.get("current_weights") or {}
    target_w  = plan.get("target_weights") or {}
    rationale = agent_resp.get("error")                # reasoner puts human note here

    # 2) build swap plan locally
    balances = _balances_dict(body)
    swap_plan = build_swap_plan(
        balances=balances,
        deltas=deltas,
        base="USDC",                # keep consistent with your routing
        wallet_base_available=0.0,
    ).to_dict()
    swap_plan = apply_slippage(swap_plan, slippage_bps=30)

    # 3) respond with everything the frontend needs
    return {
        "current_allocation": current_w,
        "suggested_allocation": target_w,
        "trade_deltas": deltas,
        "swap_plan": swap_plan,
        "rationale": rationale,     # e.g., "Regime=YELLOW …"
    }