# ui_service.py
"""
Lightweight REST API that combines:
- balances input from frontend
- calls local port agent (8011) to get rebalance result
- processes it through swapPlanner.py to create swap plan
"""

import json
import requests
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from swapPlanner import build_swap_plan

PORT_AGENT_URL = "http://127.0.0.1:8011/rebalance"

app = FastAPI(title="Rebalance UI Preview API", version="1.0")

# -------------------------------
# Input model
# -------------------------------
class BalancesInput(BaseModel):
    usdc_balance: float
    usdt_balance: float
    dai_balance: float = 0.0
    fdusd_balance: float = 0.0
    busd_balance: float = 0.0
    tusd_balance: float = 0.0
    usdp_balance: float = 0.0
    pyusd_balance: float = 0.0
    usdd_balance: float = 0.0
    gusd_balance: float = 0.0
    quote_amount: float = 1.0


# -------------------------------
# API route
# -------------------------------
@app.post("/ui/preview")
def ui_preview(balances: BalancesInput = Body(...)):
    """Combine port agent response with swap plan."""
    try:
        # 1️⃣ call the existing port agent
        resp = requests.post(PORT_AGENT_URL, json=balances.dict(), timeout=45)
        if not resp.ok:
            raise HTTPException(status_code=502, detail=f"Port agent unreachable: {resp.text}")

        data = resp.json()
        if not data.get("ok"):
            raise HTTPException(status_code=500, detail=f"Balancer error: {data.get('error')}")

        # 2️⃣ extract plan and deltas
        plan = data.get("plan", {})
        deltas = plan.get("trade_deltas", {})
        current_weights = plan.get("current_weights", {})
        target_weights = plan.get("target_weights", {})

        # 3️⃣ build swap plan
        swap_plan = build_swap_plan(
            balances={k.upper(): v for k, v in balances.dict().items() if "balance" in k},
            deltas=deltas,
            base="USDC",
            wallet_base_available=0.0
        ).to_dict()

        # 4️⃣ return all combined info
        return {
            "current_allocation": current_weights,
            "suggested_allocation": target_weights,
            "trade_deltas": deltas,
            "swap_plan": swap_plan,
            "rationale": data.get("error") or "Reasoner rationale unavailable"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating UI preview: {e}")


@app.get("/health")
def health():
    return {"status": "ok", "service": "ui-preview"}