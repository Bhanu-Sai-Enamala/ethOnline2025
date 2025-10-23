from typing import Optional, Dict
from uagents import Model

# rebalance_models.py
class RebalanceCheckRequest(Model):
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
    note: str = "rebalance_10coin"
    quote_amount: float = 1.0

# class RebalancePlan(Model):
#     trade_USDC_delta: float
#     trade_USDT_delta: float
#     target_weights: Dict[str, float]
#     current_weights: Dict[str, float]
#     expected_quote: Optional[float] = None


class RebalancePlan(Model):
    trade_deltas: Dict[str, float]        # per-coin delta (+ means buy, - means sell)
    target_weights: Dict[str, float]      # final target weights per coin
    current_weights: Dict[str, float]     # current weights derived from balances
    expected_quote: Optional[float] = None

class RebalanceCheckResponse(Model):
    ok: bool
    error: Optional[str] = None
    plan: Optional[RebalancePlan] = None
    diagnostics_json: Optional[str] = None