#!/usr/bin/env bash
# Build an isolated Phase API environment, import the app, and exercise its
# public liveness/data-provenance endpoints through a real uvicorn process.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
TMP_DIR="$(mktemp -d)"
VENV_DIR="${PHASE_API_SMOKE_VENV:-$TMP_DIR/venv}"
PORT="${PHASE_API_SMOKE_PORT:-18200}"
PYTHON_BIN="${PHASE_API_PYTHON:-python3}"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check \
  -r "$REPO_ROOT/v4/product/d1_phase_detector/api/requirements.txt"

cd "$REPO_ROOT"
DB_URL="sqlite:///$TMP_DIR/phase.sqlite" \
  "$VENV_DIR/bin/python" -c \
  "from v4.product.d1_phase_detector.api.main import app; assert app.title"

DB_URL="sqlite:///$TMP_DIR/phase.sqlite" \
  "$VENV_DIR/bin/uvicorn" v4.product.d1_phase_detector.api.main:app \
  --host 127.0.0.1 --port "$PORT" >"$TMP_DIR/uvicorn.log" 2>&1 &
SERVER_PID="$!"

"$VENV_DIR/bin/python" - "$PORT" <<'PY'
import json
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

base = f"http://127.0.0.1:{sys.argv[1]}"
for attempt in range(30):
    try:
        with urlopen(f"{base}/health", timeout=1) as response:
            health = json.load(response)
        break
    except (URLError, TimeoutError):
        if attempt == 29:
            raise
        time.sleep(0.2)

assert health == {"status": "ok"}, health
with urlopen(f"{base}/api/ews/meta", timeout=2) as response:
    meta = json.load(response)
assert isinstance(meta.get("version"), str), meta
assert isinstance(meta.get("n_tickers"), int), meta
assert isinstance(meta.get("price_provenance"), str), meta
print("Phase API clean-environment smoke passed")
PY
