#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Ensure environment & deps are ready (idempotent)
./scripts/bootstrap.sh

# Start both services with logs + cleanup traps
exec ./run.sh