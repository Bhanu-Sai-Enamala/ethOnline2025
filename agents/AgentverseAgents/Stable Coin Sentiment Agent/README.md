# 📰 Stablecoin News & Sentiment Agent

**Address**  
`agent1q2nfkyc93matrqqu4cfph8aaqxx5mt0zztzw6jxnghhj7re6r6xw6csykph`  
[View on AgentVerse](https://agentverse.ai/agents/details/agent1q2nfkyc93matrqqu4cfph8aaqxx5mt0zztzw6jxnghhj7re6r6xw6csykph/profile)
Score 3.9
interactions 1.91k

---

## 🧭 Overview

The **Stablecoin News & Sentiment Agent** scans reputable crypto-news RSS feeds, detects headlines relevant to major USD stablecoins, and computes a **per-coin sentiment score** with freshness decay and confidence.  
It’s designed to plug directly into StableGuard’s Knowledge Graph Reasoner and Aggregator, helping color regimes (GREEN/YELLOW/RED) and justify rebalance alerts.

- Refresh cadence: **every 5 minutes** (configurable)  
- Universe: **10 stablecoins** — USDT, USDC, DAI, FDUSD, BUSD, TUSD, USDP, PYUSD, USDD, GUSD  
- Output: compact summary per coin (score, label, confidence, counts, and sample headlines)

---

## ✨ What It Does

1. **Fetch** RSS from multiple sources (CoinDesk, Cointelegraph, Decrypt, The Block, Blockworks, The Defiant, Bitcoin Magazine, CryptoSlate, etc.).  
2. **Filter** by coin-specific synonym regex (e.g., “USDC”, “USD Coin”, “Circle”).  
3. **Score** each headline using a token-based sentiment tally with **negation handling** and **tanh normalization** → range **[-1, 1]**.  
4. **Weight** by recency with an exponential **half-life** (default **120 min**).  
5. **Aggregate** per coin into a rolling sentiment score, **label** (Bullish/Neutral/Bearish), and **confidence** from coverage breadth + recency.  
6. **Expose** a compact snapshot for chat and a DM API for other agents.

---

## 🧪 Sentiment Model (TL;DR)

- Tokenize headline → count hits from `POS_WORDS` / `NEG_WORDS` with **negation-aware** sign flip in a 3-token window.  
- Normalize with `tanh(0.7 * raw)` → headline score in **[-1, 1]**.  
- Apply **time decay**: weight = `0.5 ** (age_minutes / HALF_LIFE_MIN)`  
- Per-coin rolling score = weighted average;  
  **Label**: `> +0.25 → Bullish`, `< -0.25 → Bearish`, else Neutral.  
- **Confidence** is derived from headline count, unique sources, and median age.

---

## 📦 Output Shapes

### 1) Compact summary used by chat / Reasoner

```json
{
  "USDC": {
    "score": 0.18,
    "label": "Neutral",
    "confidence": 0.45,
    "headline_count": 7,
    "source_count": 4,
    "examples": [
      {"title": "Circle expands...", "source": "coindesk.com", "score": 0.31},
      {"title": "USDC integration...", "source": "theblock.co", "score": 0.21}
    ]
  },
  "USDT": { "...": "..." }
}
```

### 2) Full per-coin raw snapshot (cached bundle)

```
news_sentiment_latest = {
  "ts": 1735234567,
  "coins": {
    "USDC": "<json string of full coin snapshot>",
    "USDT": "<json string>",
    "...": "..."
  }
}
```

Each full coin snapshot contains `matches` (title/link/source/age/weight/headline_score) and rolling stats.

---

## 🗣️ Chat Intents

| Intent | What it returns | Example |
|---|---|---|
| `status` | One-line overall summary | “status” |
| `list` | Scores line for all coins | “scores” |
| `best` | Highest-scoring coin | “best sentiment?” |
| `worst` | Lowest-scoring coin | “worst coin” |
| `snapshot` | Pretty JSON of compact summary | “snapshot json” |
| `explain` | Short natural-language takeaways | “explain today’s sentiment” |

The agent tries ASI intent parsing first; if unavailable, it falls back to heuristics.

---

## 📬 DM API (for other agents)

Message models:

- **`NewsSentimentRequest`**: `{ coin: string }` (empty `coin` → full bundle)  
- **`NewsSentimentResponse`**:  
  - `ok: bool`  
  - `results_json: string` — either:
    - a JSON string of `{coin: "<json_str>", ...}` when `coin==""`, or
    - that coin’s **JSON string** when `coin=="USDC"` etc.

Storage keys:

- Cache per-coin: `news_sentiment_cache_v1`  
- Latest bundle: `news_sentiment_latest` (override via `SENTIMENT_STORAGE_KEY`)

---


## 🔗 Integration in StableGuard

- **Knowledge Graph Reasoner** uses per-coin score + confidence to anticipate peg pressure.  
- **Aggregator** includes this alongside peg and liquidity scores.  
- **Vacation Mode alerts** include a sentiment line to justify the plan.

---

## 🔒 Notes on Safety & Bias

- Headlines can be noisy; the agent uses multiple sources, negation handling, and time decay to reduce whipsaws.  
- This is **headline sentiment**, not price prediction. It should be considered **context**, not a trading signal.

---

## 🏁 Closing Note

Signal beats noise when it’s **fresh, scoped, and explainable**.  
This agent distills the stablecoin news firehose into a compact, actionable score.

**Agent address**: `agent1q2nfkyc93matrqqu4cfph8aaqxx5mt0zztzw6jxnghhj7re6r6xw6csykph`  
**AgentVerse**: https://agentverse.ai/agents/details/agent1q2nfkyc93matrqqu4cfph8aaqxx5mt0zztzw6jxnghhj7re6r6xw6csykph/profile

— Built for **EthOnline 2025**.
