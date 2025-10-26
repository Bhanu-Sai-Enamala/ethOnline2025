# 🟢 Peg Stability Agent

### **Address:**  
[`agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq`](https://agentverse.ai/agents/details/agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq/profile)

Score = 4.3
interactions = 18.4k+

---

## 🧭 Overview

The **Peg Stability Agent** is StableGuard’s market sentry — a continuously running AI process that monitors the real-time health of multiple stablecoins across venues.

It measures peg deviations, TWAP divergence, persistence of deviation, and assigns a risk regime (`HEALTHY`, `WATCH`, `CAUTION`, `ALERT`).  
Its job is to detect depegs before they spiral into system-wide risk — like what happened to DAI during “Black Wednesday.”

> Hosted live on [AgentVerse](https://agentverse.ai/agents/details/agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq/profile), this agent autonomously streams peg data for StableGuard’s Knowledge Graph Reasoner and Telegram alert system.

---

## ⚙️ Key Features

- **Multi-coin Peg Monitoring**  
  Tracks USDT, USDC, DAI, FDUSD, BUSD, TUSD, USDP, PYUSD, USDD, and GUSD using CoinGecko APIs.

- **Real-Time Risk Analytics**  
  Computes spot deviation, TWAP deviation, persistence ratio, and aggregate risk score.

- **Dynamic Regime Classification**  
  Automatically assigns a system state:  
  - 🟢 **HEALTHY** — stable peg  
  - 🟡 **WATCH** — mild deviation  
  - 🟠 **CAUTION** — persistent deviation  
  - 🔴 **ALERT** — severe depeg risk  

- **ASI Reasoning Integration**  
  Uses **ASI1 API** (`asi1-mini`, `asi1-experimental`) for human-like reasoning and explanation of peg movements.  
  Generates concise summaries for chat and reasoning protocols.

- **Chat Interface**  
  Supports direct messages and chat interactions through `uagents_core.contrib.protocols.chat`.

---

## 🧩 Core Architecture

| Component | Function |
|------------|-----------|
| **Monitor Loop** | Periodically polls CoinGecko every 45 seconds and updates rolling price windows. |
| **Risk Engine** | Calculates blended peg risk using spot + TWAP + persistence metrics. |
| **ASI Integration** | Uses ASI chat completions to interpret peg status in natural language. |
| **Storage System** | Caches latest peg snapshots (`peg_latest`) for downstream agents. |
| **Direct Protocol** | Responds to `PegSnapshotRequest` messages with `PegSnapshotResponse` JSON payloads. |

---

## 📡 Communication Protocols

- **`PegSnapshotRequest` / `PegSnapshotResponse`**  
  Allows other agents (e.g., Aggregator or Reasoner) to fetch latest peg state.

- **Chat Protocol (`chat_protocol_spec`)**  
  Enables human or AI agents to query current peg regime, ask for explanations, or request metrics.

---

## 📊 Metrics & Logic

| Metric | Meaning |
|--------|----------|
| `spot_dev_bps` | Latest price deviation in basis points |
| `twap_dev_bps` | Average deviation across sliding window |
| `persist` | Fraction of samples breaching threshold |
| `total_risk` | Weighted blend across all factors |
| `regime` | Classified system state (HEALTHY → ALERT) |

---

## 🔍 Example Output Snapshot

```json
{
  "timestamp": "2025-10-26T10:21:55Z",
  "coins": ["USDT", "USDC", "DAI"],
  "spot": {"USDT": 0.9998, "USDC": 1.0001, "DAI": 0.9989},
  "stats": {
    "USDT": {"spot_dev_bps": 2.0, "twap_dev_bps": 1.0, "persist": 0.05},
    "USDC": {"spot_dev_bps": 1.0, "twap_dev_bps": 0.8, "persist": 0.02},
    "DAI": {"spot_dev_bps": 5.5, "twap_dev_bps": 3.1, "persist": 0.25}
  },
  "risk": {"USDT": 0.12, "USDC": 0.08, "DAI": 0.33},
  "total_risk": 0.33,
  "regime": "WATCH",
  "latency_ms": 1198
}
```

---

## 🧠 ASI Reasoning Layer

Whenever queried in chat, the agent asks the **ASI1 reasoning API** to summarize or explain:  
- “What’s the current peg regime?”  
- “Why is DAI risky right now?”  
- “Give me a JSON snapshot of stablecoin health.”

The model responds concisely in plain English, often in the style of a financial analyst.

---

## 🪶 Example Chat Query

```
user: How healthy are stablecoins right now?
agent: Regime: HEALTHY | USDC ~1.0000 | USDT ~0.9998 | DAI ~0.9989
```

or:

```
user: Explain what’s happening with the peg.
agent: Market remains stable with mild DAI deviation, mostly due to reduced liquidity depth on Coinbase.
```

---

## 🧱 Tech Stack

- **Language:** Python  
- **Framework:** uAgents (Almanac 2.3.0)  
- **APIs:** CoinGecko, ASI1 AI Chat  
- **Storage:** JSON local storage via `ctx.storage`  
- **Interval:** 45s polling frequency  

---

## 🌐 Hosted Instance

Live agent profile:  
👉 [View on AgentVerse](https://agentverse.ai/agents/details/agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq/profile)

---

## 🧩 Integration

This agent feeds data into:
- **Aggregator Agent** — merges responses from all sub-agents.  
- **Knowledge Graph Reasoner** — correlates peg + liquidity + sentiment risk.  
- **Telegram Alert System** — pushes rebalance recommendations to users in vacation mode.

---

## 🏁 Closing Note

The **Peg Stability Agent** is StableGuard’s eyes — always watching the peg.  
It doesn’t react blindly; it reasons, explains, and alerts before it’s too late.

> Stability starts with visibility.  
> Peggy sees what the bots don’t.

---

### **Made with 🧠 and ⚙️ for EthOnline 2025.**
