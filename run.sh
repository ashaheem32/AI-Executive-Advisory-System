#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  PYTHON_BIN="${PYTHON_BIN:-python3.12}"
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN=python3
  fi
  "$PYTHON_BIN" -c 'import sys; sys.version_info >= (3,12) or sys.exit("Python 3.12 or newer is required. Install Python 3.12, then rerun this script.")'
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.lock
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
