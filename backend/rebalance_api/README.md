# 🧭 Rebalance REST Port

This service runs a local REST bridge that connects to the hosted **Balancer Agent** on Agentverse.  
It exposes simple HTTP endpoints for the backend to fetch rebalance recommendations and diagnostics.

---

## ⚙️ Setup Instructions

### 1. Go to the folder
```bash
cd backend/rebalance_api
```

### 2. Create virtual environment & install requirements
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Create a `.env` file
with these exact values
```dotenv
BALANCER_AGENT_ADDRESS=agent1qtnzvd83zy89qg8mr63gpa3k9rz5u0dyjnrpnq5xmu4w62fw9agm538anv3
CLIENT_SEED=ethOnlineseed
USE_MAILBOX=true
PORT=8000
DEFAULT_TIMEOUT_SEC=12
```

---

## 🚀 Run the service
```bash
python3 run.py
```

When it starts, you’ll see:
```
[rebalance-rest-port] Address: agent1q09w...
[rebalance-rest-port] Balancer Target: agent1qtnzvd...
💾 Cached to file: app/data/rebalance_latest.json
```

---

## 🌐 Endpoints

### `POST /rebalance`
Sends USDC/USDT balances and returns a rebalance recommendation.

**Example Request**
```bash
curl -X POST http://127.0.0.1:8000/rebalance   -H "Content-Type: application/json"   -d '{"usdc_balance":450,"usdt_balance":350,"quote_amount":1.0}'
```

**Example Response**
```json
{
  "ok": true,
  "plan": {
    "trade_USDC_delta": 31.84,
    "trade_USDT_delta": -31.84,
    "target_weights": {"USDC": 0.6023, "USDT": 0.3977},
    "expected_quote": 1.33552
  },
  "diagnostics_json": "{...}"
}
```

---

### `GET /rebalance/cached`
Returns the **last successful** rebalance result from cache.

```bash
curl http://127.0.0.1:8000/rebalance/cached
```

---

### `GET /health`
Checks that the REST agent is running.
```bash
curl http://127.0.0.1:8000/health
```

---

## 💾 Cache File

Every successful response is saved to:
```
app/data/rebalance_latest.json
```

If the balancer doesn’t reply before timeout, the last cached plan is returned automatically.

---


- `/rebalance` → fetch new recommendation  
- `/rebalance/cached` → fallback or analytics  
- `/health` → check readiness  

No manual agent setup needed — everything runs locally with `python3 run.py`.
