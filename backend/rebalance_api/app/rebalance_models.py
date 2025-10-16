from typing import Optional, Dict
from uagents import Model

class RebalanceCheckRequest(Model):
    usdc_balance: float
    usdt_balance: float
    note: str = "rebalance_usdc_usdt"
    quote_amount: float = 1.0

class RebalancePlan(Model):
    trade_USDC_delta: float
    trade_USDT_delta: float
    target_weights: Dict[str, float]
    current_weights: Dict[str, float]
    expected_quote: Optional[float] = None

class RebalanceCheckResponse(Model):
    ok: bool
    error: Optional[str] = None
    plan: Optional[RebalancePlan] = None
    diagnostics_json: Optional[str] = None