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
BETA_ENV_FILE="${STRUCTURAL_BETA_ENV_FILE:-$REPO/web/backend/.env}"
LOG_PREFIX="[deploy-phase-detector $(date -u +%FT%TZ)]"
PREVIOUS_SHA="${PHASE_PREVIOUS_SHA:-$(git -C "$REPO" rev-parse HEAD)}"
DEPLOY_COMPLETE=0

env_key_once() {
  local file="$1" key="$2"
  [[ "$(grep -cE "^${key}=" "$file" || true)" == "1" ]]
}

env_exact_once() {
  local file="$1" key="$2" expected="$3"
  env_key_once "$file" "$key" && grep -qx "${key}=${expected}" "$file"
}

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
env_exact_once "$WEB_DIR/.env.production" NEXT_PUBLIC_API_BASE /api || {
  echo "$LOG_PREFIX ERROR: public Phase API base must remain /api" >&2
  exit 1
}
env_exact_once "$WEB_DIR/.env.production" PHASE_API_INTERNAL_BASE http://127.0.0.1:8200 || {
  echo "$LOG_PREFIX ERROR: internal Phase API base missing or unsafe" >&2
  exit 1
}
AUTH_ENABLED_FOR_DEPLOY=false
env_key_once "$WEB_DIR/.env.production" NEXT_PUBLIC_AUTH_ENABLED || {
  echo "$LOG_PREFIX ERROR: NEXT_PUBLIC_AUTH_ENABLED must occur exactly once" >&2
  exit 1
}
if env_exact_once "$WEB_DIR/.env.production" NEXT_PUBLIC_AUTH_ENABLED true; then
  AUTH_ENABLED_FOR_DEPLOY=true
  [[ -f "$AUTH_ENV_FILE" ]] || {
    echo "$LOG_PREFIX ERROR: private Phase auth environment file missing" >&2
    exit 1
  }
  env_exact_once "$WEB_DIR/.env.production" NEXT_PUBLIC_STRUCTURAL_BETA_ORIGIN https://beta.structural.bytedance.city || {
    echo "$LOG_PREFIX ERROR: public beta callback origin must be canonical" >&2; exit 1;
  }
  auth_env_mode="$(stat -c '%a' "$AUTH_ENV_FILE")"
  [[ "$auth_env_mode" == "600" ]] || {
    echo "$LOG_PREFIX ERROR: private auth environment must have mode 600" >&2
    exit 1
  }
  for auth_key in AUTH_ENABLED STRUCTURAL_ENV JWT_SECRET AUTH_LINK_BASE_URL AUTH_DATA_DIR \
    SMTP_HOST SMTP_PORT SMTP_FROM_EMAIL ADMIN_NOTIFICATION_EMAIL STRUCTURAL_SSO_SECRET \
    STRUCTURAL_SSO_DATA_DIR STRUCTURAL_SSO_PHASE_ORIGIN STRUCTURAL_SSO_BETA_ORIGIN; do
    env_key_once "$AUTH_ENV_FILE" "$auth_key" || {
      echo "$LOG_PREFIX ERROR: private auth setting must occur exactly once: $auth_key" >&2
      exit 1
    }
  done
  env_exact_once "$AUTH_ENV_FILE" STRUCTURAL_SSO_PHASE_ORIGIN https://phase.bytedance.city || {
    echo "$LOG_PREFIX ERROR: Phase SSO origin must be canonical" >&2; exit 1;
  }
  env_exact_once "$AUTH_ENV_FILE" STRUCTURAL_SSO_BETA_ORIGIN https://beta.structural.bytedance.city || {
    echo "$LOG_PREFIX ERROR: beta SSO origin must be canonical" >&2; exit 1;
  }
  sso_secret="$(sed -n 's/^STRUCTURAL_SSO_SECRET=//p' "$AUTH_ENV_FILE" | tail -1)"
  [[ ${#sso_secret} -ge 32 ]] \
    && [[ ! "$sso_secret" =~ (replace|change-me|changeme|example|test-secret|dev-) ]] \
    && [[ "$(printf '%s' "$sso_secret" | fold -w1 | sort -u | wc -l)" -ge 12 ]] || {
      echo "$LOG_PREFIX ERROR: STRUCTURAL_SSO_SECRET must be high entropy" >&2; exit 1;
    }
  [[ -f "$BETA_ENV_FILE" ]] || {
    echo "$LOG_PREFIX ERROR: beta environment file missing for shared SSO validation" >&2; exit 1;
  }
  beta_env_mode="$(stat -c '%a' "$BETA_ENV_FILE")"
  [[ "$beta_env_mode" == "600" ]] || {
    echo "$LOG_PREFIX ERROR: private beta environment must have mode 600" >&2; exit 1;
  }
  env_exact_once "$BETA_ENV_FILE" STRUCTURAL_ENV prod || {
    echo "$LOG_PREFIX ERROR: beta STRUCTURAL_ENV must be prod" >&2; exit 1;
  }
  env_exact_once "$BETA_ENV_FILE" STRUCTURAL_SSO_PHASE_ORIGIN https://phase.bytedance.city || {
    echo "$LOG_PREFIX ERROR: beta Phase SSO origin must be canonical" >&2; exit 1;
  }
  env_exact_once "$BETA_ENV_FILE" STRUCTURAL_SSO_BETA_ORIGIN https://beta.structural.bytedance.city || {
    echo "$LOG_PREFIX ERROR: beta SSO origin must be canonical" >&2; exit 1;
  }
  beta_sso_secret="$(sed -n 's/^STRUCTURAL_SSO_SECRET=//p' "$BETA_ENV_FILE" | tail -1)"
  env_key_once "$BETA_ENV_FILE" STRUCTURAL_SSO_SECRET || {
    echo "$LOG_PREFIX ERROR: beta SSO secret must occur exactly once" >&2; exit 1;
  }
  [[ "$sso_secret" == "$beta_sso_secret" ]] || {
    echo "$LOG_PREFIX ERROR: Phase and beta SSO secrets differ" >&2; exit 1;
  }
  sso_data_dir="$(sed -n 's/^STRUCTURAL_SSO_DATA_DIR=//p' "$AUTH_ENV_FILE" | tail -1)"
  beta_sso_data_dir="$(sed -n 's/^STRUCTURAL_SSO_DATA_DIR=//p' "$BETA_ENV_FILE" | tail -1)"
  env_key_once "$BETA_ENV_FILE" STRUCTURAL_SSO_DATA_DIR || {
    echo "$LOG_PREFIX ERROR: beta SSO data directory must occur exactly once" >&2; exit 1;
  }
  sso_data_real="$(realpath -m "$sso_data_dir")"
  repo_real="$(realpath -m "$REPO")"
  [[ -n "$sso_data_dir" && "$sso_data_dir" == "$beta_sso_data_dir" && "$sso_data_real" != "$repo_real"* ]] || {
    echo "$LOG_PREFIX ERROR: Phase and beta require the same Git-external SSO data directory" >&2; exit 1;
  }
  mkdir -p "$sso_data_dir"
  test -w "$sso_data_dir" || {
    echo "$LOG_PREFIX ERROR: shared SSO data directory is not writable" >&2; exit 1;
  }
  env_exact_once "$AUTH_ENV_FILE" AUTH_ENABLED true || {
    echo "$LOG_PREFIX ERROR: AUTH_ENABLED must be true" >&2; exit 1;
  }
  env_exact_once "$AUTH_ENV_FILE" STRUCTURAL_ENV prod || {
    echo "$LOG_PREFIX ERROR: STRUCTURAL_ENV must be prod" >&2; exit 1;
  }
  jwt_secret="$(sed -n 's/^JWT_SECRET=//p' "$AUTH_ENV_FILE" | tail -1)"
  [[ ${#jwt_secret} -ge 32 ]] \
    && [[ ! "$jwt_secret" =~ (replace|change-me|changeme|example|test-secret|dev-jwt) ]] \
    && [[ "$(printf '%s' "$jwt_secret" | fold -w1 | sort -u | wc -l)" -ge 12 ]] || {
      echo "$LOG_PREFIX ERROR: JWT_SECRET must be a high-entropy non-placeholder value" >&2
      exit 1
    }
  env_exact_once "$AUTH_ENV_FILE" AUTH_LINK_BASE_URL https://phase.bytedance.city || {
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
  favorites_path="$(sed -n 's/^STRUCTURAL_FAVORITES_PATH=//p' "$AUTH_ENV_FILE" | tail -1)"
  if [[ -n "$favorites_path" ]]; then
    [[ "$favorites_path" != "$REPO"* ]] || {
      echo "$LOG_PREFIX ERROR: STRUCTURAL_FAVORITES_PATH must be outside the Git checkout" >&2
      exit 1
    }
    mkdir -p "$(dirname "$favorites_path")"
    test -w "$(dirname "$favorites_path")" || {
      echo "$LOG_PREFIX ERROR: favorites storage directory is not writable" >&2
      exit 1
    }
  fi
  systemctl cat phase-detector-api | grep -Fq "EnvironmentFile=$AUTH_ENV_FILE" || {
    echo "$LOG_PREFIX ERROR: phase-detector-api must load the private auth environment" >&2
    exit 1
  }
else
  env_exact_once "$WEB_DIR/.env.production" NEXT_PUBLIC_AUTH_ENABLED false || {
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
