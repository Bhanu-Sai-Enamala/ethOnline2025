

![defi](https://img.shields.io/badge/defi-blue)
![stablecoin](https://img.shields.io/badge/stablecoin-green)
![asi](https://img.shields.io/badge/asi-orange)
![innovationlab](https://img.shields.io/badge/innovationlab-brightgreen)
![chatprotocol](https://img.shields.io/badge/chatprotocol-blueviolet)
![finance](https://img.shields.io/badge/finance-grey)

# Peg+Liquidity+Sentiment Responder (10-coin)

**AI-assisted responder** that aggregates **peg, liquidity, and news sentiment** for 10 major stablecoins, then proposes a **10-coin rebalance plan**.  
Chat-enabled via **ASI:One Chat Protocol** with human-friendly commands; works **with or without an LLM**.
score = 4.5
interactions = 86.8k+

> Coins: **USDC, USDT, DAI, FDUSD, BUSD, TUSD, USDP, PYUSD, USDD, GUSD**

---

## What it does
- **Requests**:
  - Peg snapshot from the peg agent
  - Cross-stable **liquidity quotes** (USDC → each coin) from the liquidity agent
  - **Sentiment bundle** from the news-sentiment agent
- **Aggregates** the data into a `ReasonRequest` → sends to **Reasoner**
- **Builds a 10-coin RebalancePlan** from `ReasonResponse`
  - If reasoner is unavailable, **falls back** to inverse-risk weighting from peg payload
- **Chat** interface with short commands (`status`, `snapshot`, `help`)  
  Optional: pass the final string through an LLM for a polished explanation

---

## Chat Commands
Type these directly to the responder (ASI chat or Agentverse):

- `status` – one-line current → target weights (and note)
- `snapshot` – latest JSON snapshot (balances, liquidity map, plan, note)

**Example reply**
```
Plan ready. Current [USDC:30.00% USDT:20.00% ...] →
Target [USDC:10.00% USDT:10.00% ...]. Fallback: reasoner unavailable or error.
```

---

## Flow
1. Client sends `RebalanceCheckRequest` (balances) → **Responder**
2. Responder concurrently asks:
   - **Peg agent** → `PegSnapshotResponse`
   - **Liquidity agent** for each pair → `LiquidityResponse`
   - **Sentiment agent** → `NewsSentimentResponse`
3. Once peg + liquidity (and optionally sentiment) arrive, responder sends **`ReasonRequest`** to **Reasoner**
4. On **`ReasonResponse`** → builds `RebalancePlan` and replies
5. Chat users can ask `status`/`snapshot` at any time to see the latest plan/snapshot

---

## Minimal Programmatic Chat (Python)
```python
from datetime import datetime, timezone
import uuid
from uagents import Agent, Protocol
from uagents_core.contrib.protocols.chat import chat_protocol_spec, ChatMessage, TextContent

RESPONDER_ADDR = "agent1...responder"

client = Agent(name="tester", mailbox=True, seed="tester-seed")
chat_proto = Protocol(spec=chat_protocol_spec)
client.include(chat_proto)

@client.on_event("startup")
async def go(ctx):
    msg = ChatMessage(
        content=[TextContent(text="status")],
        msg_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
    )
    await ctx.send(RESPONDER_ADDR, msg)

client.run()
```

---

## Troubleshooting
- **`RuntimeError: Unable to lookup message handler in protocol`**  
  Ensure you created `chat_proto = Protocol(spec=chat_protocol_spec)` and `agent.include(chat_proto)` **after** defining chat handlers.
- **Reasoner not contacted**  
  Check `REASONER_AGENT_ADDRESS` is set and starts with `agent1...`. Also confirm both peg + liquidity arrived (the responder waits for them before sending `ReasonRequest`).
- **Always “Fallback: reasoner unavailable”**  
  Your reasoner might be down or returning `ok=false`. Inspect responder logs and reasoner logs to see errors.


