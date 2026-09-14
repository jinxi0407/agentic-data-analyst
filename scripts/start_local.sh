#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
  "$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required. Set PYTHON_BIN=/path/to/python3.12 and retry.")
PY
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

docker compose up -d mysql
python scripts/init_database.py
python data/seed_data.py
python scripts/set_readonly_user.py

uvicorn app.main:app --host 127.0.0.1 --port 8002 &
API_PID=$!
streamlit run ui/app.py --server.port 8502 --server.address 127.0.0.1
kill "$API_PID"
