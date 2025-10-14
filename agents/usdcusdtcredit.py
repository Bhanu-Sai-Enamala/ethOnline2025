#!/usr/bin/env python3
"""
Risk-weighted stablecoin rebalancer (off-chain, CoinGecko source).

What it does:
1) Fetch price/market data (USDC, USDT, DAI, PYUSD) from CoinGecko.
2) Compute objective risk scores per coin (peg, liquidity, collateral, redemption, transparency).
3) Convert scores to target weights via inverse-risk^alpha.
4) Compare with your balances and output a rebalance plan.

Edit `EXAMPLE_BALANCES` to try different portfolios.
"""

from __future__ import annotations
import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
import math
import json

# -----------------------------
# Configuration
# -----------------------------

# Coins to score (symbol -> CoinGecko id)
CG_IDS = {
    "USDC": "usd-coin",
    "USDT": "tether",
    "DAI":  "dai",
    "PYUSD": "paypal-usd",
}

# Heuristic baseline attributes (objective-ish priors you can tweak later)
# These are NOT prices; they reflect qualitative realities until you add on-chain proofs.
BASELINES = {
    "USDC": {"collateral": 0.95, "redemption": 0.90, "transparency": 0.85},
    "USDT": {"collateral": 0.70, "redemption": 0.60, "transparency": 0.60},
    "DAI":  {"collateral": 0.85, "redemption": 0.80, "transparency": 0.75},
    "PYUSD":{"collateral": 0.93, "redemption": 0.90, "transparency": 0.80},
}

# Score weights (sum to 1.0)
WEIGHTS = {
    "peg": 0.35,
    "collateral": 0.25,
    "liquidity": 0.20,
    "redemption": 0.15,
    "transparency": 0.05,
}

# Risk aversion for inverse-risk weighting (higher = more aggressive tilt to safer coins)
ALPHA = 2.0

# Minimum % deviation (of portfolio) to trigger a trade for a token
REBALANCE_THRESHOLD = 0.02  # 2%

# Your example holdings (tokens in units, approx $1 each; we still value with market price)
EXAMPLE_BALANCES = {
    "USDC": 450.0,
    "USDT": 350.0,
    "DAI":  200.0,
    "PYUSD": 0.0,
}

# -----------------------------
# Data structures
# -----------------------------

@dataclass
class Market:
    price: float
    market_cap: float
    volume_24h: float
    circulating: float

@dataclass
class Scores:
    peg: float
    collateral: float
    liquidity: float
    redemption: float
    transparency: float
    final: float

# -----------------------------
# CoinGecko fetch
# -----------------------------

def fetch_cg_coin(coin_id: str) -> Market:
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    j = r.json()

    price = float(j["market_data"]["current_price"]["usd"])
    mcap = float(j["market_data"]["market_cap"]["usd"] or 0.0)
    vol = float(j["market_data"]["total_volume"]["usd"] or 0.0)
    circ = float(j["market_data"]["circulating_supply"] or 0.0)

    return Market(price=price, market_cap=mcap, volume_24h=vol, circulating=circ)

def fetch_all_markets(ids_map: Dict[str, str]) -> Dict[str, Market]:
    data: Dict[str, Market] = {}
    for sym, cid in ids_map.items():
        try:
            data[sym] = fetch_cg_coin(cid)
        except Exception as e:
            print(f"⚠️ Error fetching market for {sym}: {e}")
            data[sym] = Market(price=1.0, market_cap=0.0, volume_24h=0.0, circulating=0.0)  # keep going
    return data

# -----------------------------
# Scoring model
# -----------------------------

def score_peg(price: float) -> float:
    """
    Peg score: 1.0 when exactly $1; linearly down to 0 at ±2%.
    """
    dev = abs(price - 1.0)
    return float(max(0.0, 1.0 - (dev / 0.02)))  # 2% window

def minmax_norm(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))

def compute_scores(markets: Dict[str, Market]) -> Dict[str, Scores]:
    # Liquidity proxy via 24h volume min-max across the set
    vols = [m.volume_24h for m in markets.values()]
    vmin, vmax = (min(vols), max(vols)) if vols else (0.0, 1.0)

    scored: Dict[str, Scores] = {}
    for sym, m in markets.items():
        peg = score_peg(m.price)
        liquidity = minmax_norm(m.volume_24h, vmin, vmax)

        base = BASELINES.get(sym, {"collateral": 0.70, "redemption": 0.70, "transparency": 0.70})
        collateral = float(base["collateral"])
        redemption = float(base["redemption"])
        transparency = float(base["transparency"])

        final = (
            WEIGHTS["peg"] * peg +
            WEIGHTS["collateral"] * collateral +
            WEIGHTS["liquidity"] * liquidity +
            WEIGHTS["redemption"] * redemption +
            WEIGHTS["transparency"] * transparency
        )

        scored[sym] = Scores(
            peg=round(peg, 3),
            collateral=round(collateral, 3),
            liquidity=round(liquidity, 3),
            redemption=round(redemption, 3),
            transparency=round(transparency, 3),
            final=round(final, 3),
        )
    return scored

# -----------------------------
# Risk-weighted rebalancing
# -----------------------------

def risk_weighted_targets(scores_final: Dict[str, float], alpha: float = ALPHA) -> Dict[str, float]:
    """
    Convert final scores S in [0,1] to target weights via inverse-risk:
       R_i = 1 - S_i
       W_i ∝ 1 / R_i^alpha
    """
    # Guard against R=0 (perfect score): clamp tiny floor
    risk = {k: max(1e-6, 1.0 - s) for k, s in scores_final.items()}
    inv = {k: 1.0 / (risk[k] ** alpha) for k in risk}
    denom = sum(inv.values()) or 1.0
    return {k: inv[k] / denom for k in inv}

def value_portfolio_usd(balances_units: Dict[str, float], prices: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
    usd = {k: (balances_units.get(k, 0.0) * prices.get(k, 1.0)) for k in balances_units}
    total = sum(usd.values())
    return total, usd

def compute_rebalance(
    balances_units: Dict[str, float],
    prices: Dict[str, float],
    target_w: Dict[str, float],
    threshold: float = REBALANCE_THRESHOLD,
) -> Dict[str, Any]:
    total_usd, usd_vals = value_portfolio_usd(balances_units, prices)
    if total_usd <= 0:
        return {"action": "NO_OP", "reason": "Empty portfolio"}

    current_w = {k: (usd_vals.get(k, 0.0) / total_usd) for k in target_w.keys()}
    deltas = {k: (target_w[k] - current_w.get(k, 0.0)) * total_usd for k in target_w.keys()}

    # Only include trades above threshold share of portfolio
    plan_trades = {k: round(v, 2) for k, v in deltas.items() if abs(v) / total_usd > threshold}

    action = "REBALANCE" if plan_trades else "NO_OP"
    reason = "Deviations exceed threshold" if plan_trades else "All deviations below threshold"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "reason": reason,
        "portfolio": {
            "total_usd": round(total_usd, 2),
            "current_weights": {k: round(v, 4) for k, v in current_w.items()},
            "target_weights": {k: round(v, 4) for k, v in target_w.items()},
        },
        "trades_usd": plan_trades,  # +$ = buy that coin; -$ = sell that coin
    }

# -----------------------------
# Pretty print helpers
# -----------------------------

def grade_from_score(s: float) -> str:
    if s >= 0.85: return "A"
    if s >= 0.75: return "B"
    if s >= 0.65: return "C"
    if s >= 0.55: return "D"
    return "F"

def summarize(markets: Dict[str, Market], scores: Dict[str, Scores]) -> Dict[str, Any]:
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stablecoins": {}
    }
    for sym in markets:
        m, sc = markets[sym], scores[sym]
        out["stablecoins"][sym] = {
            "price": round(m.price, 6),
            "market_cap_usd": round(m.market_cap, 2),
            "circulating_supply": round(m.circulating, 6),
            "volume_24h_usd": round(m.volume_24h, 2),
            "scores": {
                "peg": sc.peg,
                "collateral": sc.collateral,
                "liquidity": sc.liquidity,
                "redemption": sc.redemption,
                "transparency": sc.transparency
            },
            "final_score": sc.final,
            "grade": grade_from_score(sc.final),
        }
    return out

# -----------------------------
# Main
# -----------------------------

def main():
    print("Fetching market data from CoinGecko …")
    markets = fetch_all_markets(CG_IDS)

    print("Computing scores …")
    scores = compute_scores(markets)

    # Build final-score dict for target computation
    final_scores = {k: v.final for k, v in scores.items()}

    # Prices dict for valuation
    prices = {k: markets[k].price for k in markets}

    # Targets from scores
    targets = risk_weighted_targets(final_scores, alpha=ALPHA)

    # Example rebalance using EXAMPLE_BALANCES
    print("\n=== EXAMPLE PORTFOLIO (units) ===")
    for k, v in EXAMPLE_BALANCES.items():
        print(f"  {k}: {v} units")

    plan = compute_rebalance(EXAMPLE_BALANCES, prices, targets, threshold=REBALANCE_THRESHOLD)

    # Output summary + plan
    summary = summarize(markets, scores)
    print("\n=== SCORE SUMMARY ===")
    print(json.dumps(summary, indent=2))

    print("\n=== REBALANCE PLAN (risk-weighted) ===")
    print(json.dumps(plan, indent=2))

    # Human-readable trade hints
    if plan["action"] == "REBALANCE":
        print("\nTrade hints (approx):")
        for sym, amt in plan["trades_usd"].items():
            if amt > 0:
                print(f"  BUY  ${amt:,.2f} {sym}")
            else:
                print(f"  SELL ${-amt:,.2f} {sym}")
        print("\nNote: Execute sells to fund buys (e.g., USDT → USDC), considering slippage/fees.")

if __name__ == "__main__":
    main()