# #!/usr/bin/env bash
# set -euo pipefail

# ### ─────────────────────────────────────────────────────────────────────────────
# ### Helpers
# ### ─────────────────────────────────────────────────────────────────────────────
# ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# cd "$ROOT_DIR"

# REASONER_DIR="$ROOT_DIR/agents/sentiment_reasoner"
# BACKEND_DIR="$ROOT_DIR/backend/rebalance_api"

# choose_python() {
#   # Prefer 3.11 (Hyperon wheels exist), then fall back.
#   for CAND in python3.11 python3.10 python3.9 python3; do
#     if command -v "$CAND" >/dev/null 2>&1; then
#       echo "$CAND"
#       return 0
#     fi
#   done
#   echo "python"
# }

# log()  { printf "\033[1;36m[run]\033[0m %s\n" "$*"; }
# warn() { printf "\033[1;33m[run]\033[0m %s\n" "$*"; }
# err()  { printf "\033[1;31m[run]\033[0m %s\n" "$*" >&2; }

# ensure_root_env() {
#   if [[ ! -f ".env" ]]; then
#     if [[ -f ".env.example" ]]; then
#       cp .env.example .env
#       warn "No root .env found — created one from .env.example. Edit it if needed."
#     else
#       err "No .env or .env.example at repo root. Please add a root .env and re-run."
#       exit 1
#     fi
#   fi
# }

# generate_envs() {
#   # load root .env into env vars
#   set -a
#   . ./.env
#   set +a

#   mkdir -p "$REASONER_DIR" "$BACKEND_DIR"

#   # agents/sentiment_reasoner/.env
#   cat > "$REASONER_DIR/.env" <<EOF
# AGENT_NAME=${AGENT_NAME}
# REASONER_SEED=${REASONER_SEED}
# USE_MAILBOX=${USE_MAILBOX}
# METTA_RULES=${METTA_RULES}
# EOF

#   # backend/rebalance_api/.env
#   cat > "$BACKEND_DIR/.env" <<EOF
# BALANCER_AGENT_ADDRESS=${BALANCER_AGENT_ADDRESS}
# MAILBOX_ENABLED=${MAILBOX_ENABLED}
# CLIENT_SEED=${CLIENT_SEED}
# API_HOST=${API_HOST}
# API_PORT=${API_PORT}
# DEFAULT_TIMEOUT_SEC=${DEFAULT_TIMEOUT_SEC}
# EOF

#   log "Generated service .env files from root .env"
# }

# ### ─────────────────────────────────────────────────────────────────────────────
# ### 1) Env files
# ### ─────────────────────────────────────────────────────────────────────────────
# ensure_root_env
# generate_envs

# ### ─────────────────────────────────────────────────────────────────────────────
# ### 2) Create/activate venv and install deps
# ### ─────────────────────────────────────────────────────────────────────────────
# PYBIN="$(choose_python)"
# VENV_DIR="$ROOT_DIR/venv"
# VENV_BIN="$VENV_DIR/bin"
# REQ_FILE="$ROOT_DIR/requirements.txt"

# if [[ ! -d "$VENV_DIR" ]]; then
#   log "Creating virtualenv with $PYBIN → $VENV_DIR"
#   "$PYBIN" -m venv "$VENV_DIR"
# fi

# # shellcheck disable=SC1091
# source "$VENV_BIN/activate"

# log "Python: $(python -V)"
# log "Upgrading pip/setuptools/wheel"
# python -m pip install --upgrade pip setuptools wheel >/dev/null

# if [[ -f "$REQ_FILE" ]]; then
#   log "Installing requirements from $REQ_FILE"
#   python -m pip install -r "$REQ_FILE"
# else
#   warn "No root requirements.txt found — skipping dependency install."
# fi

# ### ─────────────────────────────────────────────────────────────────────────────
# ### 3) Launch services
# ### ─────────────────────────────────────────────────────────────────────────────
# pids=()

# start_reasoner() {
#   log "Starting Sentiment Reasoner…"
#   (
#     cd "$REASONER_DIR"
#     exec python run.py
#   ) &
#   pids+=($!)
# }

# start_backend() {
#   log "Starting Rebalance API…"
#   (
#     cd "$BACKEND_DIR"
#     exec python run.py
#   ) &
#   pids+=($!)
# }

# cleanup() {
#   warn "Shutting down…"
#   for pid in "${pids[@]:-}"; do
#     if kill -0 "$pid" 2>/dev/null; then
#       kill "$pid" 2>/dev/null || true
#       wait "$pid" 2>/dev/null || true
#     fi
#   done
#   log "All processes stopped."
# }
# # NOTE: macOS bash (3.2) doesn't support `wait -n`, so don't trap on EXIT.
# trap cleanup INT TERM

# start_reasoner
# sleep 1   # let reasoner register before API starts
# start_backend

# ### ─────────────────────────────────────────────────────────────────────────────
# ### 4) Hints
# ### ─────────────────────────────────────────────────────────────────────────────
# echo
# log "Services are starting. Typical endpoints:"
# log "  Rebalance API:   http://127.0.0.1:${API_PORT:-8011}/health"
# log "  Quick test:"
# echo "    curl -s -X POST http://127.0.0.1:${API_PORT:-8011}/rebalance \\"
# echo '      -H "Content-Type: application/json" \\'
# echo '      -d "{\"usdc_balance\":450,\"usdt_balance\":350,\"quote_amount\":1.0,\"timeout_sec\":12}" | jq .'
# echo

# ### ─────────────────────────────────────────────────────────────────────────────
# ### 5) Wait on children  (portable: waits for all PIDs, works on macOS bash 3.2)
# ### ─────────────────────────────────────────────────────────────────────────────
# wait "${pids[@]}" || true

#!/usr/bin/env bash
set -euo pipefail

### ─────────────────────────────────────────────────────────────────────────────
### Helpers
### ─────────────────────────────────────────────────────────────────────────────
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

REASONER_DIR="$ROOT_DIR/agents/sentiment_reasoner"
BACKEND_DIR="$ROOT_DIR/backend/rebalance_api"

log()  { printf "\033[1;36m[run]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[run]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[run]\033[0m %s\n" "$*" >&2; }

choose_python() {
  # On Render, don't try to create a new venv — use the platform's Python.
  if [[ "${RENDER:-}" != "" ]]; then
    if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
      echo "$ROOT_DIR/.venv/bin/python"
      return 0
    fi
    # Fall back to the default python on PATH
    command -v python3 >/dev/null 2>&1 && { echo python3; return 0; }
    command -v python >/dev/null 2>&1 && { echo python;  return 0; }
    err "No python available in Render environment"
    exit 1
  fi
  # Local dev: prefer commonly installed versions
  for CAND in python3.11 python3.10 python3.9 python3 python; do
    if command -v "$CAND" >/dev/null 2>&1; then
      echo "$CAND"
      return 0
    fi
  done
  err "No suitable Python found"
  exit 1
}

ensure_root_env() {
  if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
      cp .env.example .env
      warn "No root .env found — created one from .env.example. Edit it if needed."
    else
      err "No .env or .env.example at repo root. Please add a root .env and re-run."
      exit 1
    fi
  fi
}

generate_envs() {
  # load root .env into env vars
  set -a
  . ./.env
  set +a

  mkdir -p "$REASONER_DIR" "$BACKEND_DIR"

  # agents/sentiment_reasoner/.env
  cat > "$REASONER_DIR/.env" <<EOF
AGENT_NAME=${AGENT_NAME}
REASONER_SEED=${REASONER_SEED}
USE_MAILBOX=${USE_MAILBOX}
METTA_RULES=${METTA_RULES}
EOF

  # backend/rebalance_api/.env
  cat > "$BACKEND_DIR/.env" <<EOF
BALANCER_AGENT_ADDRESS=${BALANCER_AGENT_ADDRESS}
MAILBOX_ENABLED=${MAILBOX_ENABLED}
CLIENT_SEED=${CLIENT_SEED}
API_HOST=${API_HOST}
API_PORT=${API_PORT}
DEFAULT_TIMEOUT_SEC=${DEFAULT_TIMEOUT_SEC}
EOF

  log "Generated service .env files from root .env"
}

### ─────────────────────────────────────────────────────────────────────────────
### 1) Env files
### ─────────────────────────────────────────────────────────────────────────────
ensure_root_env
generate_envs

### ─────────────────────────────────────────────────────────────────────────────
### 2) Python env & deps
### ─────────────────────────────────────────────────────────────────────────────
PYBIN="$(choose_python)"
VENV_DIR="$ROOT_DIR/venv"
VENV_BIN="$VENV_DIR/bin"
REQ_FILE="$ROOT_DIR/requirements.txt"

if [[ "${RENDER:-}" != "" ]]; then
  # Render: DO NOT create a new venv. Use system python or .venv if present.
  log "Render detected; skipping venv creation"
else
  if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating virtualenv with $PYBIN → $VENV_DIR"
    "$PYBIN" -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1091
  source "$VENV_BIN/activate"
  PYBIN=python
fi

log "Python: $($PYBIN -V)"
log "Upgrading pip/setuptools/wheel"
$PYBIN -m pip install --upgrade pip setuptools wheel >/dev/null || true

if [[ -f "$REQ_FILE" ]]; then
  log "Installing requirements from $REQ_FILE"
  $PYBIN -m pip install -r "$REQ_FILE"
else
  warn "No root requirements.txt found — skipping dependency install."
fi

### ─────────────────────────────────────────────────────────────────────────────
### 3) Launch services
### ─────────────────────────────────────────────────────────────────────────────
pids=()

start_reasoner() {
  log "Starting Sentiment Reasoner…"
  (
    cd "$REASONER_DIR"
    exec $PYBIN run.py
  ) &
  pids+=($!)
}

start_backend() {
  log "Starting Rebalance API…"
  (
    cd "$BACKEND_DIR"
    exec $PYBIN run.py
  ) &
  pids+=($!)
}

cleanup() {
  warn "Shutting down…"
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  log "All processes stopped."
}
trap cleanup INT TERM

start_reasoner
sleep 1   # let reasoner register before API starts
start_backend

### ─────────────────────────────────────────────────────────────────────────────
### 4) Hints
### ─────────────────────────────────────────────────────────────────────────────
echo
log "Services are starting. Typical endpoints:"
log "  Rebalance API:   http://127.0.0.1:${API_PORT:8000}/health"
log "  Quick test:"
echo "    curl -s -X POST http://127.0.0.1:${API_PORT:-8000}/rebalance \\"
echo '      -H "Content-Type: application/json" \\'
echo '      -d "{\"usdc_balance\":450,\"usdt_balance\":350,\"quote_amount\":1.0,\"timeout_sec\":12}" | jq .'
echo

### ─────────────────────────────────────────────────────────────────────────────
### 5) Wait on children (portable)
### ─────────────────────────────────────────────────────────────────────────────
wait "${pids[@]}" || true