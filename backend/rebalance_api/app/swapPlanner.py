# swap_planner.py
"""
Build a concrete swap plan from (balances, deltas).
- Coins are stables (≈$1); no price lookups.
- Positive delta  => BUY that coin (spend base)
- Negative delta  => SELL that coin (receive base)
- 'base' is the routing asset (default USDC).
- Returns an ordered list of swaps you can feed to your backend swapper (1inch/0x/etc).

Example:
plan = build_swap_plan(
    balances={"USDC":1200,"USDT":800,"DAI":500},
    deltas={"USDC":-836.4,"USDT":-254.8,"DAI":-136.4,"FDUSD":63.6,"BUSD":113.6,"USDP":163.6,"TUSD":213.6,"PYUSD":263.6,"GUSD":263.6,"USDD":145.2},
    base="USDC",
    wallet_base_available=0.0,
)
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

@dataclass
class SwapLeg:
    src: str
    dst: str
    amount: float               # human units
    intent: str                 # "SELL" or "BUY"
    min_receive: Optional[float] = None  # set by backend using slippage bps
    note: Optional[str] = None

@dataclass
class SwapPlan:
    base: str
    sells_to_base: List[SwapLeg]   # coin->base
    buys_from_base: List[SwapLeg]  # base->coin
    base_funding:Dict[str, float]
    base_pool_start: float
    base_needed_for_buys: float
    base_delta_target: float
    base_pool_end: float
    shortfall: float               # >0 if not enough base to execute all buys + base target
    warnings: List[str]

    def to_dict(self):
        return {
            "base": self.base,
            "sells_to_base": [asdict(x) for x in self.sells_to_base],
            "buys_from_base": [asdict(x) for x in self.buys_from_base],
            "base_funding": self.base_funding,
            "base_pool_start": round(self.base_pool_start, 6),
            "base_needed_for_buys": round(self.base_needed_for_buys, 6),
            "base_delta_target": round(self.base_delta_target, 6),
            "base_pool_end": round(self.base_pool_end, 6),
            "shortfall": round(self.shortfall, 6),
            "warnings": self.warnings,
        }

def round2(x: float) -> float:
    return float(f"{x:.2f}")

def build_swap_plan(
    balances: Dict[str, float],
    deltas: Dict[str, float],
    base: str = "USDC",
    wallet_base_available: float = 0.0,
    tolerance: float = 1.0,       # dollar tolerance for sum(deltas) ≈ 0
) -> SwapPlan:
    """
    balances: current wallet balances per coin
    deltas:   desired changes per coin (+ buy, - sell)
    base:     routing/staging stable (USDC recommended)
    wallet_base_available: extra base liquidity outside 'balances[base]' (optional)
    tolerance: how much total delta mismatch we allow before warning
    """

    coins = sorted(set(balances) | set(deltas))
    balances = {c: float(balances.get(c, 0.0)) for c in coins}
    deltas = {c: float(deltas.get(c, 0.0)) for c in coins}
    if base not in coins:
        balances[base] = balances.get(base, 0.0)
        deltas[base] = deltas.get(base, 0.0)

    # sanity: total deltas should ~= 0 for dollar-neutral rebalance
    total_delta = sum(deltas.values())
    warnings: List[str] = []
    if abs(total_delta) > tolerance:
        warnings.append(f"Sum of deltas = {total_delta:.2f} (>|{tolerance}|). Plan will proceed but check upstream math.")

    # Partition SELL / BUY (exclude base for now; handle base via its own delta)
    sells = {c: -deltas[c] for c in coins if c != base and deltas[c] < 0}
    buys  = {c:  deltas[c] for c in coins if c != base and deltas[c] > 0}

    # Base delta requested by target portfolio
    base_delta_target = deltas.get(base, 0.0)  # + means we must end with more base; - means reduce base

    # Build SELL legs: coin -> base
    sells_to_base: List[SwapLeg] = []
    for c, amt in sells.items():
        if amt <= 0: 
            continue
        if balances.get(c, 0.0) + 1e-9 < amt:
            warnings.append(f"Balance of {c} ({balances.get(c,0):.2f}) < SELL amount ({amt:.2f}). Will sell what is available.")
            amt = max(0.0, balances.get(c, 0.0))
        if amt > 0:
            sells_to_base.append(SwapLeg(src=c, dst=base, amount=round2(amt), intent="SELL", note="fund base"))

    # Base pool accounting
    base_from_sells = sum(x.amount for x in sells_to_base)
    base_balance_start = float(balances.get(base, 0.0))
    base_pool_start = round2(base_balance_start + wallet_base_available + base_from_sells)

    # How much base we need to spend to complete all BUYS
    base_needed_for_buys = round2(sum(buys.values()))

    # If base_delta_target > 0, we must *retain* extra base at the end (i.e., need even more base).
    # If base_delta_target < 0, we intend to *reduce* base, which just increases what we can spend.
    # Effective base required = buys + max(0, base_delta_target)
    effective_base_required = base_needed_for_buys + max(0.0, base_delta_target)

    shortfall = round2(max(0.0, effective_base_required - base_pool_start))

    # Build BUY legs: base -> coin
    buys_from_base: List[SwapLeg] = []
    base_pool_after_buys = base_pool_start
    if shortfall > 0:
        warnings.append(f"Base shortfall of {shortfall:.2f} {base} to execute all buys + base target.")
        # In shortfall, still produce proportional buys fitting available pool (optional).
        # Here we scale down buys to what we have AFTER satisfying positive base delta requirement:
        spendable = max(0.0, base_pool_start - max(0.0, base_delta_target))
        scale = 0.0 if base_needed_for_buys == 0 else min(1.0, spendable / base_needed_for_buys)
    else:
        scale = 1.0

    for c, amt in buys.items():
        buy_amt = round2(amt * scale)
        if buy_amt <= 0:
            continue
        buys_from_base.append(SwapLeg(src=base, dst=c, amount=buy_amt, intent="BUY"))
        base_pool_after_buys -= buy_amt

    # Apply base delta target:
    # - If target is positive: reserve that much base (already accounted above); base_pool_end reduces by that reserve.
    # - If negative: we still need to reduce base; simplest is to *upsize* existing BUYS proportionally using leftover base.
    base_pool_end = base_pool_after_buys
    if base_delta_target > 0:
        base_pool_end = round2(base_pool_end - base_delta_target)
        if base_pool_end < -1e-6:
            # This would mean we tried to reserve more base than we had; it should have been caught as shortfall already.
            warnings.append("After reserving positive base delta, base went negative — check inputs.")
    elif base_delta_target < 0:
        # We want to reduce base by extra |base_delta_target| beyond what buys already consumed.
        extra_to_spend = round2(min(abs(base_delta_target), base_pool_end))
        if extra_to_spend > 0 and buys_from_base:
            # distribute across buy legs proportionally to their amounts
            total_buys = sum(l.amount for l in buys_from_base)
            if total_buys > 0:
                for leg in buys_from_base:
                    add = round2(extra_to_spend * (leg.amount / total_buys))
                    leg.amount = round2(leg.amount + add)
                base_pool_end = round2(base_pool_end - extra_to_spend)
        # If still base remains but we *must* reduce base more and no buy legs exist,
        # you could add a synthetic leg to the "safest" coin, or just warn:
        if base_pool_end > 0 and abs(base_delta_target) > 0 and not buys_from_base:
            warnings.append("Base is to be reduced but no BUY legs exist; consider swapping leftover base to the safest coin.")

    # Summarize funding view
    base_funding = {
        "base_balance_start": round2(base_balance_start),
        "wallet_base_available": round2(wallet_base_available),
        "from_sells": round2(base_from_sells),
    }

    return SwapPlan(
        base=base,
        sells_to_base=sells_to_base,
        buys_from_base=buys_from_base,
        base_funding=base_funding,
        base_pool_start=base_pool_start,
        base_needed_for_buys=base_needed_for_buys,
        base_delta_target=round2(base_delta_target),
        base_pool_end=round2(base_pool_end),
        shortfall=shortfall,
        warnings=warnings,
    )

# --- quick demo ---
if __name__ == "__main__":
    balances = {
        "USDC": 1200.0, "USDT": 800.0, "DAI": 500.0, "FDUSD": 300.0,
        "BUSD": 250.0, "TUSD": 150.0, "USDP": 200.0, "PYUSD": 100.0,
        "USDD": 400.0, "GUSD": 100.0,
    }
    deltas = {
        "USDC": -836.4, "USDT": -254.8, "DAI": -136.4, "FDUSD": 63.6,
        "BUSD": 113.6, "USDP": 163.6, "TUSD": 213.6, "PYUSD": 263.6,
        "GUSD": 263.6, "USDD": 145.2,
    }
    plan = build_swap_plan(balances, deltas, base="USDC", wallet_base_available=0.0)
    import json
    print(json.dumps(plan.to_dict(), indent=2))