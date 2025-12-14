<div align="center">
  <a href="https://ethglobal.com/showcase/stableguard-ai-fn85z">
    <img src="https://img.shields.io/badge/ETHGlobal-ETHOnline%202025-5E5BFF?style=for-the-badge&logo=ethereum&logoColor=white" alt="ETHOnline 2025" />
  </a>
  <a href="https://ethglobal.com/showcase/stableguard-ai-fn85z">
    <img src="https://img.shields.io/badge/Project-StableGuard.AI-f97316?style=for-the-badge&logo=opensourceinitiative&logoColor=white" alt="StableGuard.AI Showcase" />
  </a>
  <a href="https://ethglobal.b0bd725bc77a3ea7cd3826627d01fcb6.r2.cloudflarestorage.com/certificates/1247002/certificate.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Credential=dd28f7ba85ca3162a53d5c60b5f3dd05%2F20251214%2Fauto%2Fs3%2Faws4_request&X-Amz-Date=20251214T014439Z&X-Amz-Expires=3600&X-Amz-Signature=6e0952e4a217f571d1e4790ee6ee9b5fee3b13f09766d593a1b2584db10becda&X-Amz-SignedHeaders=host&x-amz-checksum-mode=ENABLED&x-id=GetObject">
    <img src="https://img.shields.io/badge/Award-Best%20Use%20of%20ASI%20Alliance-00C9A7?style=for-the-badge&logo=starship&logoColor=white" alt="Best use of ASI Alliance" />
  </a>
  <a href="https://www.linkedin.com/posts/fetch-ai-innovation-lab_hackathon-innovation-fetchai-activity-7390326776071290880-8nLg/?utm_source=social_share_send&utm_medium=android_app&rcm=ACoAAEHrS9gBFVHaOo1OoyfGfghAjEhRrKD_F8c&utm_campaign=whatsapp">
    <img src="https://img.shields.io/badge/LinkedIn-FetchAI%20Innovation%20Lab-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn Prize Announcement" />
  </a>
  <a href="https://x.com/fetch_ai_IL/status/1984561154883047708?t=v4ZePKZUBRAVRah8fAl15A&s=19">
    <img src="https://img.shields.io/badge/X-FetchAI%20Innovation%20Lab-111111?style=for-the-badge&logo=x&logoColor=white" alt="X Prize Announcement" />
  </a>
</div>

> 🏆 **StableGuard.AI** won **Best Use of Artificial Superintelligence Alliance** at ETHOnline 2025, recognized by ETHGlobal co-founder Kartik Talwar.  
> 📜 [Official ETHGlobal Certificate](https://ethglobal.b0bd725bc77a3ea7cd3826627d01fcb6.r2.cloudflarestorage.com/certificates/1247002/certificate.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Credential=dd28f7ba85ca3162a53d5c60b5f3dd05%2F20251214%2Fauto%2Fs3%2Faws4_request&X-Amz-Date=20251214T014439Z&X-Amz-Expires=3600&X-Amz-Signature=6e0952e4a217f571d1e4790ee6ee9b5fee3b13f09766d593a1b2584db10becda&X-Amz-SignedHeaders=host&x-amz-checksum-mode=ENABLED&x-id=GetObject) • 📣 [LinkedIn Announcement](https://www.linkedin.com/posts/fetch-ai-innovation-lab_hackathon-innovation-fetchai-activity-7390326776071290880-8nLg/?utm_source=social_share_send&utm_medium=android_app&rcm=ACoAAEHrS9gBFVHaOo1OoyfGfghAjEhRrKD_F8c&utm_campaign=whatsapp) • 🐦 [X Announcement](https://x.com/fetch_ai_IL/status/1984561154883047708?t=v4ZePKZUBRAVRah8fAl15A&s=19)

#  Stabilize Your Stablecoins.

Welcome to **StableGuard**, your AI-powered sentinel for stablecoin health, balance, and peace of mind.

When the world sleeps, StableGuard watches.  
When markets panic, StableGuard alerts.  
When sentiment turns red, StableGuard whispers before chaos hits.

---

##  What Is StableGuard?

**StableGuard** is an intelligent, multi-agent system that monitors, scores, and dynamically guides your stablecoin portfolio — keeping your peg steady, liquidity optimal, and exposure balanced.

Built for **EthOnline 2025**, it fuses **autonomous AI agents**, **decentralized reasoning**, and **Telegram-integrated user control** to redefine how we defend stability in decentralized finance.

---

##  Architecture Overview

![StableGuard Architecture](./architecture.png)

> The dApp frontend interacts with the Local Port Agent (REST API), which connects to the Aggregator and Specialized Agents via uAgents Mailbox for real-time coordination.

### Agent Network

| Agent | Role | Description | Average Score | Address |
|-------|------|--------------|---------------|----------|
| 🧩 **Local Port Agent** | Gateway | Exposes REST API endpoints, stores local JSON state, and handles user sessions | — | — |
| ⚙️ **[Aggregator Agent](https://agentverse.ai/agents/details/agent1qtnzvd83zy89qg8mr63gpa3k9rz5u0dyjnrpnq5xmu4w62fw9agm538anv3/profile)** | Coordinator | Dispatches and aggregates responses from multiple specialized agents | — | `agent1qtnzvd83zy89qg8mr63gpa3k9rz5u0dyjnrpnq5xmu4w62fw9agm538anv3` |
| 🟢 **[Peg Stability Agent](https://agentverse.ai/agents/details/agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq/profile)** | Risk Monitor | Tracks deviations in stablecoin peg values across exchanges like Coinbase, Kraken, and Binance | **4.2 ⭐️ (18.3K interactions)** | `agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq` |
| 💧 **[Liquidity Score Agent](https://agentverse.ai/agents/details/agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq/profile)** | Depth Analyzer | Evaluates liquidity depth and execution quality across 1inch, Binance, Kraken | **4.6 ⭐️ (7.6K interactions)** | `agent1qvmenj8zn3u23v66scv8qw82hk43mtq3nvhaduhncqheypaqj5ny2qe87lq` |
| 📊 **[Sentiment Score Agent](https://agentverse.ai/agents/details/agent1q2nfkyc93matrqqu4cfph8aaqxx5mt0zztzw6jxnghhj7re6r6xw6csykph/profile)** | Mood Tracker | Analyzes on-chain chatter, headlines, and trader emotion to gauge market confidence | **3.8 ⭐️ (1.8K interactions)** | `agent1q2nfkyc93matrqqu4cfph8aaqxx5mt0zztzw6jxnghhj7re6r6xw6csykph` |
| 🧠 **Knowledge Graph Reasoner Agent** | Brain | Merges insights to determine the regime (GREEN, YELLOW, RED) and push alerts with reasoning | **5.0 ⭐️ (internal)** | — |

---

## 🏁 Why It Matters

In **March 2020**, DAI lost its peg — plunging below $0.90 when ETH crashed 40% in 24 hours.  
Thousands of vaults were liquidated because **users trusted automation, not awareness**.

StableGuard doesn’t auto-trade — it **empowers**.

When you toggle **Vacation Mode**, the system keeps watching your vaults and balances — feeding data from peg, liquidity, and sentiment agents into the Reasoner Agent.  
If risk escalates, StableGuard sends you a **Telegram alert** with a **complete rebalance plan**, rationale, and risk color code.

> You stay in control — no keys touched, no blind bots.

---

##  Knowledge Graph Reasoner Agent

The **Reasoner Agent** is the collective brain behind StableGuard.  
It correlates patterns across agents, past incidents, and live data streams — remembering the invisible signals that precede depegs.

For instance, before DAI’s 2020 crash, liquidity dried up, negative sentiment spiked, and peg dispersion widened.  
StableGuard detects such early tremors by combining all agent insights into a unified knowledge graph.

It classifies global system state into **three regimes**:

| Regime | Meaning | User Experience |
|--------|----------|----------------|
| 🟢 **GREEN** | Stable equilibrium | All clear — regular summaries only |
| 🟡 **YELLOW** | Mild systemic stress | Telegram alert with reasoning + suggested rebalance plan |
| 🔴 **RED** | Critical instability | Urgent alert + detailed rationale for manual action |

The Reasoner doesn’t just detect — it explains.

---

##  Vacation Mode (No Auto-Rebalance)

When “Vacation Mode” is toggled **ON**, your last-known balances and stablecoin exposures are saved.  
From then on:

1️⃣ StableGuard continuously monitors peg, liquidity, and sentiment metrics.  
2️⃣ If the regime turns YELLOW or RED, you receive a **Telegram summary** including:  
   - Current regime color and trigger reason  
   - Confidence score  
   - Suggested rebalance ratios (e.g., 60% USDC, 25% DAI, 15% USDT)  
3️⃣ You can review and rebalance manually — staying fully sovereign.

This lets you go off-grid or on vacation while your **AI sentinels guard your stability**.

---

##  Agent-to-Agent Communication

StableGuard’s backbone runs on **uAgents Mailbox** — a peer-to-peer message layer enabling decentralized coordination.  
Each agent signs and verifies messages cryptographically to ensure integrity.

**Flow:**  
1️⃣ Frontend → Local Port Agent → Aggregator Agent  
2️⃣ Aggregator → Specialized Agents (parallel requests)  
3️⃣ Specialized Agents → Aggregator (responses merged)  
4️⃣ Aggregator → Port Agent → Frontend (rebalance + rationale)

This ensures sub-second responsiveness while preserving modular isolation.

---

##  Telegram Integration

Stay informed with **real-time alerts** via Telegram:  
- Regime shifts (🟢→🟡→🔴)  
- Daily summaries  
- Swap recommendations and reasoning  

Your Telegram identity is cryptographically linked to your wallet address — keeping updates private yet trustless.

---

##  Tech Stack

- 🧱 **Backend:** Python, FastAPI-style uAgents REST server  
- 🤖 **Agents:** uAgents framework (Almanac 2.3.0)  
- 💾 **Storage:** JSON cache for offline durability (rebalance, preview, users)  
- 💬 **Messaging:** Mailbox-based async communication  
- 🖼️ **Frontend:** React / Next.js  
- 📱 **Notifications:** Telegram Bot API  

---

##  Repository Layout

```
├── agents/
│   ├── rebalance_api/         # Local Port Agent (REST)
│   ├── sentiment_reasoner/    # Knowledge-based risk reasoner
│   ├── liquidity_score/       # Liquidity depth analyzer
│   ├── peg_stability/         # Peg deviation monitor
│   └── aggregator/            # Multi-agent coordinator
│
├── frontend/                  # dApp UI (React + Wallet Connect)
├── README.md
└── architecture.png
```

---

##  Closing Note

StableGuard isn’t just automation — it’s vigilance turned into code.  
Every rebalance is a decision, every decision is **data-driven**.

> Stability isn’t an accident. It’s engineered.  

**Made with 🧠, ⚙️, and relentless obsession for stability — at EthOnline 2025.**
