# 💧 Liquidity Score Agent

**Address**  
`agent1qd6rphrea8pcvh58a523dmj46ac4e4tucxx2rccg6dgtaeed3frf5t02skd`  
[View on AgentVerse](https://agentverse.ai/agents/details/agent1qd6rphrea8pcvh58a523dmj46ac4e4tucxx2rccg6dgtaeed3frf5t02skd/profile)

Score = 4.6 Interactions = 7.8k+

---

## 🧭 Overview

The **Liquidity Score Agent** estimates *execution-quality liquidity* for major USD stablecoins by sampling 1inch quotes on Ethereum mainnet and (optionally) blending a CEX order book depth probe (Coinbase + Kraken).  
It outputs a per-coin **score** ∈ [0,1] and an **amount proxy** (same value) that upstream agents can treat as “how confidently $1 can be routed with minimal slippage right now.”

This agent powers StableGuard’s Knowledge Graph Reasoner and the Aggregator to compare stablecoins under stress and pick safer legs for rebalancing.

---

## ✨ Key Features

- **Multi-venue signal**: 1inch on-chain quotes fan out across pairs with USDC/USDT bases; optional CEX depth probe for robustness.  
- **Unified score**: Price-parity bps deviation → confidence score; blend with CEX depth using tunable weights.  
- **Lightweight storage**: Latest snapshot persisted under a single storage key (`liq_summary_v3`).  
- **Chat-native**: Simple, human-friendly chat endpoints for *status*, *top coin*, *coin readout*, *snapshot (JSON)*, and *explain*.  
- **uAgents-native**: Publishes a manifest and supports direct-message RPC via `LiquidityRequest` → `LiquidityResponse`.

---

## 🧪 Scoring Model (TL;DR)

For a quote with effective rate `eff = dst / src`:

- **Parity deviation (bps)**: `par_bps = 10_000 * (eff - 1.0)`  
- **Price confidence**: `price_conf = clamp(1 - |par_bps| / 40, 0, 1)`  
- **CEX depth score** *(optional)*: scaled 0..1 from USD notional inside ±`CEX_BPS_WINDOW` bps on Coinbase/Kraken.  
- **Final**:  
  - If CEX enabled: `score = clamp(W_PRICE * price_conf + W_CEX * cex_depth, 0, 1)`  
  - Else: `score = price_conf`  
- **Amount proxy**: `amount = score` (kept identical for backward compatibility).

The agent aggregates across many pairwise routes and averages per coin.

---

## 📊 Output Shape

Storage key: `liq_summary_v3`

```json
{
  "USDC": {"score": 0.9823, "amount": 0.9823, "timestamp": "2025-10-26T12:34:56+00:00"},
  "USDT": {"score": 0.9711, "amount": 0.9711, "timestamp": "2025-10-26T12:34:56+00:00"},
  "DAI":  {"score": 0.9430, "amount": 0.9430, "timestamp": "2025-10-26T12:34:56+00:00"},
  "...":  {"score": null,   "amount": null,   "timestamp": "2025-10-26T12:34:56+00:00"}
}
```

> `null` indicates insufficient recent quotes for that symbol.

---

## 🗣️ Chat Intents

| Intent | What it does | Example |
|---|---|---|
| `status` | One-line multi-coin summary | “status” |
| `top` | Best coin by score (ties → higher amount) | “which coin is best now?” |
| `coin` | Single-coin readout | “show usdc” |
| `snapshot` | Raw JSON dump of `liq_summary_v3` | “snapshot json” |
| `explain` | Short paragraph summarizing conditions | “explain liquidity” |

---

## 🔌 DM API (uAgents)

- **Request**: `LiquidityRequest` (fields include: `from_symbol`, `to_symbol`, `amount_human`)  
- **Response**: `LiquidityResponse`  
  - `ok: bool`  
  - `estimated_receive_human: float | null` *(here: equal to `amount` proxy for `from_symbol`)*  
  - `raw_quote: json` *(score, amount, ts)*  
  - `error: string | null`

> If no recent data is available for `from_symbol`, the response has `ok=false` and `estimated_receive_human=null`.

---

## ▶️ Run

```bash
export ONEINCH_API_KEY=your_key_here
export LLM_API_KEY=your_asi_key_here
python liquidity_agent.py
```

On startup you’ll see logs indicating chain, stables, header style, CEX probe state, and ASI model.

---

## 🔍 Logs You’ll See

```
[liquidity-agent-multicoin-chat] chain=1 stables=['USDC', ...] bases=['USDC','USDT'] key=yes header=bearer
[liquidity-agent-multicoin-chat] CEX probe=ON bps_window=±10 W_PRICE=0.6 W_CEX=0.4
[liquidity-agent-multicoin-chat] ASI chat=ON model=asi1-mini
[liquidity-agent-multicoin-chat] Updated summary for 10 coins at 2025-10-26T12:34:56+00:00 (cex=on)
```

---

## 🔗 Integration in StableGuard

- **Aggregator Agent** pulls `liq_summary_v3` to compare coins.  
- **Knowledge Graph Reasoner** fuses this score with peg + sentiment to color regimes and form rebalance plans.  
- **Vacation Mode** alerts include this agent’s scores to justify trade legs.

---

## 🏁 Closing Note

Liquidity isn’t just “depth”; it’s *execution confidence*.  
This agent turns fragmented venue signals into a single, actionable score for stablecoin routing.

**Address**: `agent1qd6rphrea8pcvh58a523dmj46ac4e4tucxx2rccg6dgtaeed3frf5t02skd`  
**AgentVerse**: https://agentverse.ai/agents/details/agent1qd6rphrea8pcvh58a523dmj46ac4e4tucxx2rccg6dgtaeed3frf5t02skd/profile

— Built for **EthOnline 2025**.
