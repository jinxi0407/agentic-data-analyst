#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"
cd "$PROJECT_ROOT"

test -x .venv/bin/python || { echo "Create .venv and install requirements first."; exit 1; }
test -f .env || { echo "Configure this project's .env first."; exit 1; }
exec .venv/bin/python scripts/local_services.py start
