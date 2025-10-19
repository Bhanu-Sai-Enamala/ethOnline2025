#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REASONER_DIR="$ROOT_DIR/agents/sentiment_reasoner"
BACKEND_DIR="$ROOT_DIR/backend/rebalance_api"

log()  { printf "\033[1;36m[bootstrap]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[bootstrap]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[bootstrap]\033[0m %s\n" "$*" >&2; }

choose_python() {
  for CAND in python3.11 python3.10 python3.9 python3; do
    if command -v "$CAND" >/dev/null 2>&1; then
      echo "$CAND"; return 0
    fi
  done
  echo "python"
}

ensure_root_env() {
  if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
      cp .env.example .env
      warn "No root .env found — created one from .env.example. Review and edit if needed."
    else
      err "No .env or .env.example at repo root. Please add one and retry."
      exit 1
    fi
  fi
}

generate_envs() {
  set -a
  . ./.env
  set +a

  mkdir -p "$REASONER_DIR" "$BACKEND_DIR"

  cat > "$REASONER_DIR/.env" <<EOF
AGENT_NAME=${AGENT_NAME}
REASONER_SEED=${REASONER_SEED}
USE_MAILBOX=${USE_MAILBOX}
METTA_RULES=${METTA_RULES}
EOF

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

PYBIN="$(choose_python)"
VENV_DIR="$ROOT_DIR/venv"
VENV_BIN="$VENV_DIR/bin"
REQ_FILE="$ROOT_DIR/requirements.txt"

ensure_root_env
generate_envs

if [[ ! -d "$VENV_DIR" ]]; then
  log "Creating virtualenv with $PYBIN → $VENV_DIR"
  "$PYBIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_BIN/activate"

log "Python: $(python -V)"
log "Upgrading pip/setuptools/wheel"
python -m pip install --upgrade pip setuptools wheel >/dev/null

if [[ -f "$REQ_FILE" ]]; then
  log "Installing requirements from $REQ_FILE"
  python -m pip install -r "$REQ_FILE"
else
  warn "No root requirements.txt found — skipping dependency install."
fi

log "Bootstrap complete."