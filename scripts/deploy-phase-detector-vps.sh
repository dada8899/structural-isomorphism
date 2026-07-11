#!/usr/bin/env bash
# Deploy both Phase Detector services from the VPS Git worktree.
set -euo pipefail

if [[ "${STRUCTURAL_DEPLOY_LOCK_HELD:-0}" != "1" ]]; then
  exec 9>/var/lock/structural-isomorphism-deploy.lock
  flock -w 900 9
fi

REPO="${PHASE_REPO:-/root/Projects/structural-isomorphism-v4}"
API_REQUIREMENTS="$REPO/v4/product/d1_phase_detector/api/requirements.txt"
API_PYTHON="$REPO/.venv/bin/python"
API_PIP="$REPO/.venv/bin/pip"
WEB_DIR="$REPO/web/phase-detector"
LOG_PREFIX="[deploy-phase-detector $(date -u +%FT%TZ)]"
PREVIOUS_SHA="${PHASE_PREVIOUS_SHA:-$(git -C "$REPO" rev-parse HEAD)}"
DEPLOY_COMPLETE=0

rollback_phase() {
  local code="${1:-$?}"
  local reason="${2:-command failed}"
  if [[ "$DEPLOY_COMPLETE" == "1" ]]; then return; fi
  trap - ERR
  set +e
  echo "$LOG_PREFIX ERROR: $reason; rolling back to $PREVIOUS_SHA" >&2
  git -C "$REPO" reset --hard "$PREVIOUS_SHA"
  if [[ -f "$REPO/v4/product/d1_phase_detector/api/requirements.txt" ]]; then
    "$API_PIP" install --disable-pip-version-check \
      -r "$REPO/v4/product/d1_phase_detector/api/requirements.txt"
  fi
  cd "$WEB_DIR"
  pnpm install --frozen-lockfile
  pnpm build
  systemctl restart phase-detector-api phase-detector-web
  exit "$code"
}

echo "$LOG_PREFIX start"
cd "$REPO"
git fetch origin main
git reset --hard origin/main
echo "$LOG_PREFIX repo synced to $(git rev-parse --short HEAD)"

[[ -f "$WEB_DIR/.env.production" ]] || {
  echo "$LOG_PREFIX ERROR: .env.production missing" >&2
  exit 1
}
[[ -x "$API_PYTHON" && -x "$API_PIP" ]] || {
  echo "$LOG_PREFIX ERROR: Phase API virtualenv missing" >&2
  exit 1
}
[[ -f "$API_REQUIREMENTS" ]] || {
  echo "$LOG_PREFIX ERROR: Phase API requirements missing" >&2
  exit 1
}

export NVM_DIR="/root/.nvm"
# shellcheck disable=SC1091
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
export CI=true
trap rollback_phase ERR

echo "$LOG_PREFIX installing Phase API dependencies"
"$API_PIP" install --disable-pip-version-check -r "$API_REQUIREMENTS"
PYTHONPATH="$REPO" "$API_PYTHON" -c \
  "from v4.product.d1_phase_detector.api.main import app; assert app.title"

cd "$WEB_DIR"
pnpm install --frozen-lockfile
pnpm build
echo "$LOG_PREFIX frontend build OK"

systemctl restart phase-detector-api phase-detector-web
for attempt in 1 2 3 4 5 6; do
  if curl -fsS --max-time 5 http://127.0.0.1:8200/health >/tmp/phase-health.json \
    && curl -fsS --max-time 5 http://127.0.0.1:8200/api/ews/meta >/tmp/phase-meta.json \
    && curl -fsS --max-time 5 http://127.0.0.1:3210/ >/dev/null; then
    break
  fi
  if [[ "$attempt" == "6" ]]; then
    echo "$LOG_PREFIX ERROR: service smoke failed" >&2
    systemctl status phase-detector-api phase-detector-web --no-pager -l >&2 || true
    rollback_phase 2 "service smoke failed"
  fi
  sleep 3
done

"$API_PYTHON" - <<'PY'
import json

health = json.load(open("/tmp/phase-health.json", encoding="utf-8"))
meta = json.load(open("/tmp/phase-meta.json", encoding="utf-8"))
assert health == {"status": "ok"}, health
assert isinstance(meta.get("version"), str) and meta["version"], meta
assert isinstance(meta.get("n_tickers"), int) and meta["n_tickers"] > 0, meta
assert meta.get("price_provenance") not in (None, "", "missing"), meta
print("Phase API smoke OK")
PY

systemctl is-active --quiet phase-detector-api
systemctl is-active --quiet phase-detector-web
DEPLOY_COMPLETE=1
trap - ERR
echo "$LOG_PREFIX deploy complete"
