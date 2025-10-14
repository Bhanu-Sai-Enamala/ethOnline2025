#!/usr/bin/env python3
# credit.py — Simple stablecoin scorecard using ONLY CoinGecko

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import requests

# ---- Config ---------------------------------------------------------------

COINS = {
    "USDC": "usd-coin",
    "PYUSD": "paypal-usd",
    "DAI": "dai",
    "USDT": "tether",
}

# Static, explainable assumptions (you can tune these later or source from docs)
ASSUMED = {
    "USDC": {"collateral": 0.95, "redemption": 0.90, "transparency": 0.85},
    "PYUSD": {"collateral": 0.93, "redemption": 0.90, "transparency": 0.80},
    "DAI": {"collateral": 0.85, "redemption": 0.80, "transparency": 0.75},
    "USDT": {"collateral": 0.70, "redemption": 0.60, "transparency": 0.60},
}

WEIGHTS = {
    "peg": 0.40,
    "collateral": 0.20,
    "liquidity": 0.20,
    "redemption": 0.10,
    "transparency": 0.10,
}

# If CoinGecko rate limits (429), we’ll retry a few times
HTTP_RETRIES = 3
HTTP_BACKOFF_SEC = 1.5

# ---- Helpers --------------------------------------------------------------

def cg_coin_details(coin_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single coin’s details from CoinGecko."""
    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        "?localization=false&tickers=false&community_data=false"
        "&developer_data=false&sparkline=false"
    )
    for attempt in range(1, HTTP_RETRIES + 1):
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429 and attempt < HTTP_RETRIES:
            time.sleep(HTTP_BACKOFF_SEC * attempt)
            continue
        raise RuntimeError(f"CoinGecko error {r.status_code}: {r.text[:200]}")
    return None

def safe_get(dct, path, default=None):
    cur = dct
    try:
        for p in path:
            cur = cur[p]
        return cur
    except Exception:
        return default

def peg_score(price_usd: float) -> float:
    """
    Score 0..1 based on deviation from $1.
    Full score (1.0) at $1; linearly down to 0 at ±0.5%*2 (i.e., 1% band total).
    Tweak as needed.
    """
    deviation = abs(price_usd - 1.0)
    # 0.5% one-sided tolerance
    t = 0.005
    score = max(0.0, 1.0 - (deviation / t))
    return min(1.0, score)

def liquidity_scores(mcaps_usd: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize market caps to 0..1 across the set (min-max).
    If all equal or single item, assign 1.0.
    """
    vals = [v for v in mcaps_usd.values() if v and v > 0]
    if not vals:
        return {k: 0.0 for k in mcaps_usd}
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {k: 1.0 for k in mcaps_usd}
    return {k: max(0.0, min(1.0, (mcaps_usd[k] - lo) / (hi - lo))) if mcaps_usd[k] else 0.0
            for k in mcaps_usd}

def grade(score: float) -> str:
    if score >= 0.85: return "A"
    if score >= 0.70: return "B"
    if score >= 0.55: return "C"
    if score >= 0.40: return "D"
    return "F"

# ---- Main ---------------------------------------------------------------

def main():
    print("Fetching from CoinGecko…")
    raw: Dict[str, Dict[str, Any]] = {}
    for sym, cid in COINS.items():
        try:
            data = cg_coin_details(cid)
            raw[sym] = data or {}
        except Exception as e:
            print(f"⚠️  {sym}: {e}")
            raw[sym] = {}

    # Extract fields
    results: Dict[str, Any] = {}
    mcaps = {}
    for sym, data in raw.items():
        price = safe_get(data, ["market_data", "current_price", "usd"], None)
        mcap = safe_get(data, ["market_data", "market_cap", "usd"], None)
        circ = safe_get(data, ["market_data", "circulating_supply"], None)
        vol24 = safe_get(data, ["market_data", "total_volume", "usd"], None)

        mcaps[sym] = float(mcap) if mcap else 0.0

        results[sym] = {
            "price": float(price) if price is not None else None,
            "market_cap_usd": float(mcap) if mcap is not None else None,
            "circulating_supply": float(circ) if circ is not None else None,
            "volume_24h_usd": float(vol24) if vol24 is not None else None,
        }

    # Compute scores
    liq_scores = liquidity_scores(mcaps)

    summary: Dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat(), "stablecoins": {}}

    for sym in COINS.keys():
        price = results[sym]["price"]
        mcap = results[sym]["market_cap_usd"]
        liq = liq_scores.get(sym, 0.0)

        peg = peg_score(price) if price else 0.0

        # Use stated assumptions for the rest
        assumed = ASSUMED.get(sym, {"collateral": 0.6, "redemption": 0.6, "transparency": 0.6})
        col = assumed["collateral"]
        red = assumed["redemption"]
        trn = assumed["transparency"]

        final = (
            WEIGHTS["peg"] * peg
            + WEIGHTS["collateral"] * col
            + WEIGHTS["liquidity"] * liq
            + WEIGHTS["redemption"] * red
            + WEIGHTS["transparency"] * trn
        )

        summary["stablecoins"][sym] = {
            "price": price,
            "market_cap_usd": mcap,
            "circulating_supply": results[sym]["circulating_supply"],
            "volume_24h_usd": results[sym]["volume_24h_usd"],
            "scores": {
                "peg": round(peg, 3),
                "collateral": col,
                "liquidity": round(liq, 3),
                "redemption": red,
                "transparency": trn,
            },
            "final_score": round(final, 3),
            "grade": grade(final),
        }

    # Pretty print
    try:
        from tabulate import tabulate
        rows = []
        for sym, d in summary["stablecoins"].items():
            rows.append([
                sym,
                f'{d["price"]:.6f}' if d["price"] is not None else "—",
                f'{(d["market_cap_usd"] or 0)/1e9:.2f}B',
                d["scores"]["peg"],
                d["scores"]["liquidity"],
                d["final_score"],
                d["grade"],
            ])
        print("\nStablecoin Scorecard (CoinGecko)\n")
        print(tabulate(rows, headers=["Coin","Price","MCap","Peg","Liq","Score","Grade"]))
    except Exception:
        # Fallback to simple print if tabulate isn't installed
        print(json.dumps(summary, indent=2))

    # Write JSON
    with open("stablecoin_risk.json", "w") as f:
        json.dump(summary, f, indent=2)
    print('\n✅ Wrote stablecoin_risk.json')

if __name__ == "__main__":
    main()