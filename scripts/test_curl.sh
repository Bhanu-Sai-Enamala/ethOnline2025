#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load root env for API_HOST/API_PORT
set -a
. ./.env
set +a

HOST="${API_HOST:-127.0.0.1}"
PORT="${API_PORT:-8011}"

echo "[test] POST http://${HOST}:${PORT}/rebalance"
curl -s -X POST "http://${HOST}:${PORT}/rebalance" \
  -H "Content-Type: application/json" \
  -d '{"usdc_balance":450,"usdt_balance":350,"quote_amount":1.0,"timeout_sec":12}' | jq .