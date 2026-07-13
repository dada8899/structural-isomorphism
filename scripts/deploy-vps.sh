#!/usr/bin/env bash
# deploy-vps.sh — sync git source → deploy target SAFELY
#
# 防灾原则:
#   1. 默认 rsync -avu (update, NOT delete)
#   2. 必须传 --prune-with-safety-list 才会 delete
#   3. delete 前 dry-run 显示 list 并要求人工确认
#   4. excludes 包含 models/ + .env + 大数据，避免覆盖 deploy target 独有 fixture
#
# 事故复盘 (2026-05-14, prod 502 25min):
#   `rsync -av --delete --exclude=.git --exclude=.venv v4/ structural-isomorphism/`
#   删了 deploy target 独有 models/structural-v2/ → backend startup fail →
#   systemd loop → 502. 本脚本默认 update-only 杜绝该路径。

set -euo pipefail

[[ "$EUID" -eq 0 ]] || {
  echo "[deploy] ERROR: deployment must run as root before any files are changed" >&2
  exit 1
}

if [[ "${STRUCTURAL_DEPLOY_LOCK_HELD:-0}" != "1" ]]; then
  exec 9>/var/lock/structural-isomorphism-deploy.lock
  flock -w 900 9
fi

# CI=true tells pnpm (and most other JS tooling) to skip interactive prompts.
# Without it, pnpm hits ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY when it
# detects a modules dir change and asks the operator to confirm the purge —
# SSH sessions launched by GitHub Actions don't allocate a TTY, so the
# deploy aborts. Exporting here covers any pnpm invocation downstream
# (restore-models.sh, systemd unit PreStart, web/* installs, etc.).
# Mirrors session-10 W2-F 防灾 deploy three-piece: deploy must work
# non-interactive.
export CI=true

SOURCE="${SOURCE:-/root/Projects/structural-isomorphism-v4}"
TARGET="${TARGET:-/root/Projects/structural-isomorphism}"
SERVICE="${SERVICE:-structural-web}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/root/structural-artifacts/current}"
PREVIOUS_SHA="${PREVIOUS_SHA:-}"
DRY_RUN=0
PRUNE=0
RUNTIME_BACKUP=""
SYSTEMD_UNIT_BACKUP=""
SYSTEMD_UNIT_INSTALLED=0
BETA_ENV_FILE="${STRUCTURAL_BETA_ENV_FILE:-$TARGET/web/backend/.env}"
BETA_AUTH_ENV_FILE="${STRUCTURAL_BETA_AUTH_ENV_FILE:-/root/.config/structural-isomorphism/beta-auth.env}"
SYSTEMD_UNIT_SOURCE="${STRUCTURAL_SYSTEMD_UNIT_SOURCE:-$SOURCE/web/scripts/structural-web.service}"
SYSTEMD_UNIT_TARGET="${STRUCTURAL_SYSTEMD_UNIT_TARGET:-/etc/systemd/system/${SERVICE}.service}"

env_key_once() {
  local file="$1" key="$2"
  [[ "$(grep -cE "^${key}=" "$file" || true)" == "1" ]]
}

env_exact_once() {
  local file="$1" key="$2" expected="$3"
  env_key_once "$file" "$key" && grep -qx "${key}=${expected}" "$file"
}

validate_beta_sso_config() {
  [[ -f "$BETA_ENV_FILE" ]] || {
    echo "[deploy] ERROR: private beta environment is missing" >&2; return 1;
  }
  [[ "$(stat -c '%a' "$BETA_ENV_FILE")" == "600" ]] || {
    echo "[deploy] ERROR: private beta environment must have mode 600" >&2; return 1;
  }
  for setting in \
    'STRUCTURAL_ENV|prod' \
    'STRUCTURAL_SSO_PHASE_ORIGIN|https://phase.bytedance.city' \
    'STRUCTURAL_SSO_BETA_ORIGIN|https://beta.structural.bytedance.city'; do
    local key="${setting%%|*}" expected="${setting#*|}"
    env_exact_once "$BETA_ENV_FILE" "$key" "$expected" || {
      echo "[deploy] ERROR: beta SSO production setting is missing or non-canonical" >&2; return 1;
    }
  done
  local secret data_dir
  secret="$(sed -n 's/^STRUCTURAL_SSO_SECRET=//p' "$BETA_ENV_FILE" | tail -1)"
  data_dir="$(sed -n 's/^STRUCTURAL_SSO_DATA_DIR=//p' "$BETA_ENV_FILE" | tail -1)"
  env_key_once "$BETA_ENV_FILE" STRUCTURAL_SSO_SECRET \
    && env_key_once "$BETA_ENV_FILE" STRUCTURAL_SSO_DATA_DIR \
    && [[ ${#secret} -ge 32 ]] \
    && [[ ! "$secret" =~ (replace|change-me|changeme|example|test-secret|dev-) ]] \
    && [[ "$(printf '%s' "$secret" | fold -w1 | sort -u | wc -l)" -ge 12 ]] \
    && [[ "$data_dir" = /* ]] \
    && [[ "$(realpath -m "$data_dir")" != "$(realpath -m "$TARGET")"* ]] || {
    echo "[deploy] ERROR: beta SSO secret/data directory is unsafe" >&2; return 1;
  }
}

validate_beta_auth_config() {
  [[ -f "$BETA_AUTH_ENV_FILE" ]] || {
    echo "[deploy] ERROR: private beta auth environment is missing" >&2; return 1;
  }
  [[ "$(stat -Lc '%a' "$BETA_AUTH_ENV_FILE")" == "600" ]] || {
    echo "[deploy] ERROR: private beta auth environment must have mode 600" >&2; return 1;
  }
  local key
  for key in AUTH_ENABLED AUTH_SITE_ROLE JWT_SECRET AUTH_LINK_BASE_URL AUTH_DATA_DIR SMTP_HOST SMTP_PORT \
    SMTP_FROM_EMAIL SMTP_USERNAME SMTP_PASSWORD ADMIN_NOTIFICATION_EMAIL AUTH_TRUSTED_PROXY_IPS; do
    env_key_once "$BETA_AUTH_ENV_FILE" "$key" || {
      echo "[deploy] ERROR: beta auth environment has a missing or duplicate key" >&2; return 1;
    }
  done
  env_exact_once "$BETA_AUTH_ENV_FILE" AUTH_ENABLED true || {
    echo "[deploy] ERROR: beta auth must be explicitly enabled" >&2; return 1;
  }
  env_exact_once "$BETA_AUTH_ENV_FILE" AUTH_SITE_ROLE beta || {
    echo "[deploy] ERROR: beta auth role must be explicit" >&2; return 1;
  }
  env_exact_once "$BETA_AUTH_ENV_FILE" AUTH_LINK_BASE_URL https://beta.structural.bytedance.city || {
    echo "[deploy] ERROR: AUTH_LINK_BASE_URL must use canonical beta HTTPS" >&2; return 1;
  }
  local jwt_secret auth_data_dir smtp_port from_email admin_email
  jwt_secret="$(sed -n 's/^JWT_SECRET=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  auth_data_dir="$(sed -n 's/^AUTH_DATA_DIR=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  smtp_port="$(sed -n 's/^SMTP_PORT=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  from_email="$(sed -n 's/^SMTP_FROM_EMAIL=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  admin_email="$(sed -n 's/^ADMIN_NOTIFICATION_EMAIL=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  [[ ${#jwt_secret} -ge 32 ]] \
    && [[ ! "$jwt_secret" =~ (replace|change-me|changeme|example|test-secret|dev-) ]] \
    && [[ "$(printf '%s' "$jwt_secret" | fold -w1 | sort -u | wc -l)" -ge 12 ]] || {
    echo "[deploy] ERROR: beta JWT secret is unsafe" >&2; return 1;
  }
  [[ "$auth_data_dir" = /* ]] \
    && [[ "$(realpath -m "$auth_data_dir")" != "$(realpath -m "$TARGET")"* ]] || {
    echo "[deploy] ERROR: beta AUTH_DATA_DIR must be absolute and outside Git" >&2; return 1;
  }
  [[ "$smtp_port" =~ ^[0-9]+$ ]] && (( smtp_port >= 1 && smtp_port <= 65535 )) || {
    echo "[deploy] ERROR: beta SMTP_PORT is invalid" >&2; return 1;
  }
  [[ "$from_email" == *@* && "$admin_email" == *@* ]] || {
    echo "[deploy] ERROR: beta email identities are invalid" >&2; return 1;
  }
  mkdir -p "$auth_data_dir"
  [[ -w "$auth_data_dir" ]] || {
    echo "[deploy] ERROR: beta AUTH_DATA_DIR is not writable" >&2; return 1;
  }
}

install_structural_systemd_unit() {
  [[ -f "$SYSTEMD_UNIT_SOURCE" ]] || {
    echo "[deploy] ERROR: tracked structural-web systemd unit is missing" >&2; return 1;
  }
  grep -Fqx "EnvironmentFile=$BETA_AUTH_ENV_FILE" "$SYSTEMD_UNIT_SOURCE" || {
    echo "[deploy] ERROR: tracked systemd unit does not load beta auth environment" >&2; return 1;
  }
  grep -Fq 'ExecStartPost=' "$SYSTEMD_UNIT_SOURCE" || {
    echo "[deploy] ERROR: tracked systemd unit has no deep-readiness gate" >&2; return 1;
  }
  SYSTEMD_UNIT_BACKUP="$(mktemp)" || return 1
  if [[ -f "$SYSTEMD_UNIT_TARGET" ]]; then
    cp -a "$SYSTEMD_UNIT_TARGET" "$SYSTEMD_UNIT_BACKUP" || return 1
  else
    rm -f "$SYSTEMD_UNIT_BACKUP"
    SYSTEMD_UNIT_BACKUP=""
  fi
  SYSTEMD_UNIT_INSTALLED=1
  install -m 0644 "$SYSTEMD_UNIT_SOURCE" "$SYSTEMD_UNIT_TARGET" || return 1
  systemctl daemon-reload || return 1
  systemctl cat "$SERVICE" | grep -Fq "EnvironmentFile=$BETA_AUTH_ENV_FILE" || {
    echo "[deploy] ERROR: active systemd unit does not load beta auth environment" >&2; return 1;
  }
}

rollback_deploy() {
  local reason="$1"
  echo "[deploy] FAIL: $reason — rolling back" >&2
  set +e
  if [[ -n "$PREVIOUS_SHA" ]] && git -C "$SOURCE" cat-file -e "$PREVIOUS_SHA^{commit}" 2>/dev/null; then
    git -C "$SOURCE" reset --hard "$PREVIOUS_SHA"
    rsync -av "${EXCLUDES[@]}" "$SOURCE/" "$TARGET/"
  fi
  if [[ -n "$RUNTIME_BACKUP" && -f "$RUNTIME_BACKUP" ]]; then
    cp -a "$RUNTIME_BACKUP" "$TARGET/web/backend/.env.runtime"
  fi
  if [[ "$SYSTEMD_UNIT_INSTALLED" == "1" ]]; then
    if [[ -n "$SYSTEMD_UNIT_BACKUP" && -f "$SYSTEMD_UNIT_BACKUP" ]]; then
      cp -a "$SYSTEMD_UNIT_BACKUP" "$SYSTEMD_UNIT_TARGET"
    else
      rm -f "$SYSTEMD_UNIT_TARGET"
    fi
    systemctl daemon-reload
  fi
  systemctl restart "$SERVICE"
  systemctl is-active "$SERVICE" || true
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --prune-with-safety-list) PRUNE=1 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--dry-run] [--prune-with-safety-list]

Default: rsync -avu (update only, no delete). Safe.

Flags:
  --dry-run                   Show what would happen, do not write
  --prune-with-safety-list    Enable --delete, preview list, require confirm

Env vars (with defaults shown):
  SOURCE=$SOURCE
  TARGET=$TARGET
  SERVICE=$SERVICE
EOF
      exit 0 ;;
  esac
done

validate_beta_sso_config
validate_beta_auth_config

EXCLUDES=(
  --exclude=.git/
  --exclude=.venv/
  --exclude=venv/
  --exclude=__pycache__/
  --exclude=node_modules/
  --exclude=.next/
  --exclude=*.pyc
  --exclude=.env
  --exclude=.env.production
  --exclude=web/backend/data/       # Runtime DB/outbox/API-key state; never deploy over user data
  --exclude=models/                # CRITICAL: 大文件 fixture, restore-models.sh 维护
  --exclude=data/large_*
  --exclude=*.npy
  --exclude=*.bin
)

RSYNC_FLAGS="-avu"  # update only, NOT delete
if [[ "$PRUNE" == "1" ]]; then
  echo "[deploy] PRUNE mode — dry-run preview:"
  rsync -avn --delete "${EXCLUDES[@]}" "$SOURCE/" "$TARGET/" | grep '^deleting' || echo "  (no files would be deleted)"
  echo
  read -p "[deploy] Proceed with delete? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "[deploy] aborted"; exit 1; }
  RSYNC_FLAGS="$RSYNC_FLAGS --delete"
fi

CMD=(rsync $RSYNC_FLAGS "${EXCLUDES[@]}" "$SOURCE/" "$TARGET/")
if [[ "$DRY_RUN" == "1" ]]; then
  CMD=(rsync -avn "${EXCLUDES[@]}" "$SOURCE/" "$TARGET/")
fi

echo "[deploy] Running: ${CMD[*]}"
"${CMD[@]}" | tail -10

if [[ "$DRY_RUN" == "0" ]]; then
  echo "[deploy] Ensuring models exist..."
  bash "$TARGET/scripts/restore-models.sh"

  echo "[deploy] Validating production artifact bundle..."
  for required in \
    "$ARTIFACT_ROOT/manifest.json" \
    "$ARTIFACT_ROOT/kb-expanded.jsonl" \
    "$ARTIFACT_ROOT/kb_v2_embeddings.npy" \
    "$ARTIFACT_ROOT/structural-v2"; do
    [[ -e "$required" ]] || { echo "[deploy] FAIL: missing artifact $required" >&2; exit 1; }
  done
  (
    cd "$TARGET/web/backend"
    "$TARGET/venv/bin/python" - <<PY
from services.artifact_manifest import validate_artifact_bundle
print(validate_artifact_bundle(
    "$ARTIFACT_ROOT/manifest.json",
    kb_path="$ARTIFACT_ROOT/kb-expanded.jsonl",
    embeddings_path="$ARTIFACT_ROOT/kb_v2_embeddings.npy",
    model_path="$ARTIFACT_ROOT/structural-v2",
))
PY
  )

  # Session #16: write build/deploy fingerprint so /api/version returns real
  # values. Without this, prod returns git_sha="unknown" and dogfood scripts
  # can't fingerprint-check what code is actually running (session #15 root
  # cause: 5 days of stale-code deploys went undetected).
  echo "[deploy] Writing runtime fingerprint to web/backend/.env.runtime..."
  RUNTIME_BACKUP="$(mktemp)"
  if [[ -f "$TARGET/web/backend/.env.runtime" ]]; then
    cp -a "$TARGET/web/backend/.env.runtime" "$RUNTIME_BACKUP"
  else
    rm -f "$RUNTIME_BACKUP"
    RUNTIME_BACKUP=""
  fi
  # Validator session-#16 P2 — warn early if SOURCE has no .git, since
  # that's exactly when git_sha silently becomes 'unknown' and the
  # session-#15 incident class can re-emerge.
  if [[ ! -d "$SOURCE/.git" ]]; then
    echo "[deploy] WARN: $SOURCE has no .git directory; git_sha will be 'unknown'." >&2
  fi
  GIT_SHA="$(cd "$SOURCE" && git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
  DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat > "$TARGET/web/backend/.env.runtime" <<EOF
# Auto-generated by deploy-vps.sh on every deploy. DO NOT edit by hand —
# next deploy overwrites it. Loaded by main.py with override=True so it wins
# over anything in .env.
STRUCTURAL_GIT_SHA=$GIT_SHA
STRUCTURAL_BUILD_DATE=$DEPLOYED_AT
STRUCTURAL_DEPLOYED_AT=$DEPLOYED_AT
STRUCTURAL_ENV=prod
STRUCTURAL_ARTIFACT_MANIFEST=$ARTIFACT_ROOT/manifest.json
STRUCTURAL_DATA_DIR=$ARTIFACT_ROOT
STRUCTURAL_KB_FILE=kb-expanded.jsonl
STRUCTURAL_MODEL_PATH=$ARTIFACT_ROOT/structural-v2
STRUCTURAL_PRECOMPUTED_EMBEDDINGS=$ARTIFACT_ROOT/kb_v2_embeddings.npy
EOF
  echo "[deploy]   git_sha=$GIT_SHA"
  echo "[deploy]   deployed_at=$DEPLOYED_AT"

  echo "[deploy] Installing canonical systemd unit..."
  install_structural_systemd_unit || rollback_deploy "canonical systemd unit installation failed"
  echo "[deploy] Restarting $SERVICE..."
  systemctl restart "$SERVICE" || rollback_deploy "service restart failed"
  READY=0
  for attempt in $(seq 1 24); do
    if systemctl is-active --quiet "$SERVICE" \
      && HEALTH="$(curl -fsS --max-time 5 'http://127.0.0.1:5004/api/health?deep=1' 2>/dev/null)" \
      && HEALTH="$HEALTH" "$TARGET/venv/bin/python" - <<'PY'
import json
import os

body = json.loads(os.environ["HEALTH"])
assert body["status"] == "ok", body
assert body["kb_size"] == 4443, body
assert body["artifact_id"] == "structural-v2-kb4443-20260711", body
assert body["embedding_shape"] == [4443, 768], body
PY
    then
      READY=1
      break
    fi
    sleep 5
  done
  [[ "$READY" == "1" ]] || rollback_deploy "deep health not ready after 120 seconds"
  if ! AUTH_STATUS="$(curl -sS --max-time 5 -o /tmp/structural-beta-auth-me.json -w '%{http_code}' \
    'http://127.0.0.1:5004/api/auth/me')"; then
    rollback_deploy "beta account runtime request failed"
  fi
  [[ "$AUTH_STATUS" == "401" ]] || rollback_deploy "beta account runtime is not enabled"
  "$TARGET/venv/bin/python" - <<'PY' || rollback_deploy "beta account runtime response is invalid"
import json

with open("/tmp/structural-beta-auth-me.json", encoding="utf-8") as handle:
    body = json.load(handle)
assert body.get("error") == "no session", body
PY
  rm -f "$RUNTIME_BACKUP"
  if [[ -n "$SYSTEMD_UNIT_BACKUP" ]]; then
    rm -f "$SYSTEMD_UNIT_BACKUP"
  fi
  echo "[deploy] OK"
fi
