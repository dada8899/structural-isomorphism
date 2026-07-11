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
AUTH_ENV_FILE="${PHASE_AUTH_ENV_FILE:-/root/.config/structural-isomorphism/phase-auth.env}"
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
grep -qx 'NEXT_PUBLIC_API_BASE=/api' "$WEB_DIR/.env.production" || {
  echo "$LOG_PREFIX ERROR: public Phase API base must remain /api" >&2
  exit 1
}
grep -qx 'PHASE_API_INTERNAL_BASE=http://127.0.0.1:8200' "$WEB_DIR/.env.production" || {
  echo "$LOG_PREFIX ERROR: internal Phase API base missing or unsafe" >&2
  exit 1
}
AUTH_ENABLED_FOR_DEPLOY=false
if grep -qx 'NEXT_PUBLIC_AUTH_ENABLED=true' "$WEB_DIR/.env.production"; then
  AUTH_ENABLED_FOR_DEPLOY=true
  [[ -f "$AUTH_ENV_FILE" ]] || {
    echo "$LOG_PREFIX ERROR: private Phase auth environment file missing" >&2
    exit 1
  }
  auth_env_mode="$(stat -c '%a' "$AUTH_ENV_FILE")"
  [[ "$auth_env_mode" == "600" ]] || {
    echo "$LOG_PREFIX ERROR: private auth environment must have mode 600" >&2
    exit 1
  }
  for auth_key in AUTH_ENABLED STRUCTURAL_ENV JWT_SECRET AUTH_LINK_BASE_URL AUTH_DATA_DIR \
    SMTP_HOST SMTP_PORT SMTP_FROM_EMAIL ADMIN_NOTIFICATION_EMAIL; do
    grep -qE "^${auth_key}=.+" "$AUTH_ENV_FILE" || {
      echo "$LOG_PREFIX ERROR: required private auth setting missing: $auth_key" >&2
      exit 1
    }
  done
  grep -qx 'AUTH_ENABLED=true' "$AUTH_ENV_FILE" || {
    echo "$LOG_PREFIX ERROR: AUTH_ENABLED must be true" >&2; exit 1;
  }
  grep -qx 'STRUCTURAL_ENV=prod' "$AUTH_ENV_FILE" || {
    echo "$LOG_PREFIX ERROR: STRUCTURAL_ENV must be prod" >&2; exit 1;
  }
  jwt_secret="$(sed -n 's/^JWT_SECRET=//p' "$AUTH_ENV_FILE" | tail -1)"
  [[ ${#jwt_secret} -ge 32 ]] \
    && [[ ! "$jwt_secret" =~ (replace|change-me|changeme|example|test-secret|dev-jwt) ]] \
    && [[ "$(printf '%s' "$jwt_secret" | fold -w1 | sort -u | wc -l)" -ge 12 ]] || {
      echo "$LOG_PREFIX ERROR: JWT_SECRET must be a high-entropy non-placeholder value" >&2
      exit 1
    }
  grep -qx 'AUTH_LINK_BASE_URL=https://phase.bytedance.city' "$AUTH_ENV_FILE" || {
    echo "$LOG_PREFIX ERROR: AUTH_LINK_BASE_URL must use the canonical HTTPS origin" >&2
    exit 1
  }
  auth_data_dir="$(sed -n 's/^AUTH_DATA_DIR=//p' "$AUTH_ENV_FILE" | tail -1)"
  [[ -n "$auth_data_dir" && "$auth_data_dir" != "$REPO"* ]] || {
    echo "$LOG_PREFIX ERROR: AUTH_DATA_DIR must be outside the Git checkout" >&2
    exit 1
  }
  mkdir -p "$auth_data_dir"
  test -w "$auth_data_dir" || {
    echo "$LOG_PREFIX ERROR: AUTH_DATA_DIR is not writable" >&2
    exit 1
  }
  systemctl cat phase-detector-api | grep -Fq "EnvironmentFile=$AUTH_ENV_FILE" || {
    echo "$LOG_PREFIX ERROR: phase-detector-api must load the private auth environment" >&2
    exit 1
  }
else
  grep -qx 'NEXT_PUBLIC_AUTH_ENABLED=false' "$WEB_DIR/.env.production" || {
    echo "$LOG_PREFIX ERROR: NEXT_PUBLIC_AUTH_ENABLED must be explicit" >&2
    exit 1
  }
fi
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
    && auth_status="$(curl -sS --max-time 5 -o /tmp/phase-auth-me.json -w '%{http_code}' \
         http://127.0.0.1:8200/api/auth/me)" \
    && { [[ "$AUTH_ENABLED_FOR_DEPLOY" == true && "$auth_status" == 401 ]] \
         || [[ "$AUTH_ENABLED_FOR_DEPLOY" == false && "$auth_status" == 503 ]]; } \
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
