#!/usr/bin/env bash
# deploy-vps.sh — sync git source → deploy target SAFELY
#
# 防灾原则:
#   1. 默认 rsync -av --delete-delay，Git SOURCE 对非排除路径权威
#   2. 删除受显式 runtime exclusion、Git ignore 和部署前完整快照保护
#   3. 每次同步后以 DEPLOY_COMMIT tracked manifest 校验目标字节
#   4. excludes 包含 models/ + .env + 大数据，避免覆盖 deploy target 独有 fixture
#
# 事故复盘 (2026-05-14, prod 502 25min):
#   `rsync -av --delete --exclude=.git --exclude=.venv v4/ structural-isomorphism/`
#   删了 deploy target 独有 models/structural-v2/ → backend startup fail →
#   systemd loop → 502. 本脚本以显式 runtime exclusions、事务快照和
#   tracked-manifest 校验防止该事故类重现。

set -euo pipefail

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  [[ "$EUID" -eq 0 ]] || {
    echo "[deploy] ERROR: deployment must run as root before any files are changed" >&2
    exit 1
  }
fi

# CI=true tells pnpm (and most other JS tooling) to skip interactive prompts.
# Without it, pnpm hits ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY when it
# detects a modules dir change and asks the operator to confirm the purge —
# SSH sessions launched by GitHub Actions don't allocate a TTY, so the
# deploy aborts. Exporting here covers any pnpm invocation downstream
# (runtime builds, web/* installs, etc.).
# Mirrors session-10 W2-F 防灾 deploy three-piece: deploy must work
# non-interactive.
export CI=true

SOURCE="${SOURCE:-/root/Projects/structural-isomorphism-v4}"
TARGET="${TARGET:-/root/Projects/structural-isomorphism}"
SERVICE="${SERVICE:-structural-web}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/root/structural-artifacts/current}"
PREVIOUS_SHA="${PREVIOUS_SHA:-}"
DEPLOY_COMMIT="${DEPLOY_COMMIT:-origin/main}"
SOURCE_HEAD_SHA=""
DRY_RUN=0
PRUNE=0
RUNTIME_BACKUP=""
RUNTIME_FINGERPRINT_BACKUP_READY=0
RUNTIME_FINGERPRINT_PREEXISTED=0
RUNTIME_FINGERPRINT_TMP=""
BETA_ENV_FILE="${STRUCTURAL_BETA_ENV_FILE:-$TARGET/web/backend/.env}"
BETA_AUTH_ENV_FILE="${STRUCTURAL_BETA_AUTH_ENV_FILE:-/root/.config/structural-isomorphism/beta-auth.env}"
BETA_AUTH_DATA_DIR=""
SYSTEMD_UNIT_SOURCE="${STRUCTURAL_SYSTEMD_UNIT_SOURCE:-$SOURCE/web/scripts/structural-web.service}"
SYSTEMD_UNIT_TARGET="${STRUCTURAL_SYSTEMD_UNIT_TARGET:-/etc/systemd/system/${SERVICE}.service}"
SYSTEMD_DROPIN_TARGET="${STRUCTURAL_LEGACY_SYSTEMD_AUTH_DROPIN:-/etc/systemd/system/${SERVICE}.service.d/auth.conf}"
NGINX_VHOST_TARGET="${STRUCTURAL_NGINX_VHOST_TARGET:-/etc/nginx/conf.d/beta-structural.conf}"
RUNTIME_ROOT="${STRUCTURAL_RUNTIME_ROOT:-/root/structural-runtime}"
RUNTIME_RELEASES="$RUNTIME_ROOT/releases"
RUNTIME_CURRENT="$RUNTIME_ROOT/current"
RUNTIME_PYTHON="${STRUCTURAL_RUNTIME_PYTHON:-/usr/bin/python3}"
RUNTIME_REQUIREMENTS="${STRUCTURAL_RUNTIME_REQUIREMENTS:-$SOURCE/web/backend/requirements.txt}"
DEPLOY_JOURNAL="${STRUCTURAL_DEPLOY_JOURNAL:-$RUNTIME_ROOT/deploy-journal.json}"
PUBLIC_RUNTIME_ATTESTATION="$TARGET/web/frontend/assets/runtime-attestation.json"
DEPLOY_MANIFEST_TARGET="$TARGET/.structural-deploy-manifest.json"
RUNTIME_FINGERPRINT_TARGET="$TARGET/web/backend/.env.runtime"
VERSIONED_RUNTIME_HELPER="$SOURCE/scripts/deploy-versioned-runtime.sh"
RETIRED_MODULE_HELPER="$SOURCE/scripts/deploy-retired-module.sh"
[[ -f "$VERSIONED_RUNTIME_HELPER" ]] || {
  echo "[deploy] ERROR: versioned-runtime transaction helper is missing" >&2
  exit 1
}
[[ -f "$RETIRED_MODULE_HELPER" ]] || {
  echo "[deploy] ERROR: retired-module transaction helper is missing" >&2
  exit 1
}
# shellcheck source=scripts/deploy-versioned-runtime.sh
source "$VERSIONED_RUNTIME_HELPER"
# shellcheck source=scripts/deploy-retired-module.sh
source "$RETIRED_MODULE_HELPER"

DEPLOY_TRANSACTION_ACTIVE=0
DEPLOY_ROLLBACK_DONE=0
DEPLOY_CLEANUP_DONE=0
DEPLOY_FAILURE_REASON=""
SYSTEMD_STATE_CAPTURED=0
SYSTEMD_SERVICE_WAS_ENABLED=0
SYSTEMD_SERVICE_WAS_ACTIVE=0

env_key_once() {
  local file="$1" key="$2"
  [[ "$(grep -cE "^${key}=" "$file" || true)" == "1" ]]
}

env_exact_once() {
  local file="$1" key="$2" expected="$3"
  env_key_once "$file" "$key" && grep -qx "${key}=${expected}" "$file"
}

private_env_file_mode() {
  if stat -Lc '%a' "$1" >/dev/null 2>&1; then
    stat -Lc '%a' "$1"
  else
    stat -L -f '%Lp' "$1"
  fi
}

validate_privacy_hmac_key() {
  local value="$1"
  # Canonical ASCII is intentionally stricter than generic entropy: systemd
  # EnvironmentFile parsing must yield the exact bytes validated here.
  printf '%s' "$value" | "$RUNTIME_PYTHON" -I -c '
import re
import sys

raw = sys.stdin.buffer.read()
valid = re.fullmatch(rb"[0-9a-f]{64}", raw) is not None and len(set(raw)) >= 12
raise SystemExit(0 if valid else 1)
'
}

validate_beta_sso_config() {
  [[ -f "$BETA_ENV_FILE" ]] || {
    echo "[deploy] ERROR: private beta environment is missing" >&2; return 1;
  }
  [[ "$(private_env_file_mode "$BETA_ENV_FILE")" == "600" ]] || {
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
  [[ "$(private_env_file_mode "$BETA_AUTH_ENV_FILE")" == "600" ]] || {
    echo "[deploy] ERROR: private beta auth environment must have mode 600" >&2; return 1;
  }
  local key
  for key in AUTH_ENABLED AUTH_SITE_ROLE JWT_SECRET STRUCTURAL_PRIVACY_HMAC_KEY \
    AUTH_LINK_BASE_URL AUTH_DATA_DIR SMTP_HOST SMTP_PORT \
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
  local jwt_secret privacy_hmac_key auth_data_dir smtp_port from_email admin_email
  jwt_secret="$(sed -n 's/^JWT_SECRET=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  privacy_hmac_key="$(sed -n 's/^STRUCTURAL_PRIVACY_HMAC_KEY=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  auth_data_dir="$(sed -n 's/^AUTH_DATA_DIR=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  smtp_port="$(sed -n 's/^SMTP_PORT=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  from_email="$(sed -n 's/^SMTP_FROM_EMAIL=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  admin_email="$(sed -n 's/^ADMIN_NOTIFICATION_EMAIL=//p' "$BETA_AUTH_ENV_FILE" | tail -1)"
  [[ ${#jwt_secret} -ge 32 ]] \
    && [[ ! "$jwt_secret" =~ (replace|change-me|changeme|example|test-secret|dev-) ]] \
    && [[ "$(printf '%s' "$jwt_secret" | fold -w1 | sort -u | wc -l)" -ge 12 ]] || {
    echo "[deploy] ERROR: beta JWT secret is unsafe" >&2; return 1;
  }
  validate_privacy_hmac_key "$privacy_hmac_key" || {
    echo "[deploy] ERROR: STRUCTURAL_PRIVACY_HMAC_KEY is unsafe" >&2; return 1;
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
  BETA_AUTH_DATA_DIR="$auth_data_dir"
}

prepare_beta_auth_data_dir() {
  [[ -n "$BETA_AUTH_DATA_DIR" ]] || {
    echo "[deploy] ERROR: beta AUTH_DATA_DIR was not validated" >&2; return 1;
  }
  mkdir -p "$BETA_AUTH_DATA_DIR"
  [[ -w "$BETA_AUTH_DATA_DIR" ]] || {
    echo "[deploy] ERROR: beta AUTH_DATA_DIR is not writable" >&2; return 1;
  }
}

install_structural_systemd_unit() {
  systemd_validate_tracked_unit_contract \
    "$SYSTEMD_UNIT_SOURCE" "$RUNTIME_CURRENT" "$BETA_AUTH_ENV_FILE" \
    "$TARGET/web/backend" || return 1
  systemd_unit_install_transaction "$SYSTEMD_UNIT_SOURCE" "$SYSTEMD_UNIT_TARGET" \
    || return 1
  systemctl daemon-reload || return 1
  systemctl enable "$SERVICE" || return 1
  [[ "$(systemd_enabled_state 0)" == "1" ]] || return 1
  systemctl cat "$SERVICE" | grep -Fq "EnvironmentFile=$BETA_AUTH_ENV_FILE" || {
    echo "[deploy] ERROR: active systemd unit does not load beta auth environment" >&2; return 1;
  }
  systemctl cat "$SERVICE" | grep -Fqx 'Environment="PYTHONDONTWRITEBYTECODE=1"' || {
    echo "[deploy] ERROR: active systemd unit does not disable runtime bytecode" >&2; return 1;
  }
  systemctl cat "$SERVICE" | grep -Fqx 'Environment="SETUPTOOLS_USE_DISTUTILS=stdlib"' || {
    echo "[deploy] ERROR: active systemd unit does not disable the setuptools shim" >&2; return 1;
  }
  systemctl cat "$SERVICE" | grep -Fqx "Environment=\"STRUCTURAL_PROJECT_ROOT=$TARGET\"" || {
    echo "[deploy] ERROR: active systemd unit has a noncanonical project root" >&2; return 1;
  }
  systemctl cat "$SERVICE" | grep -Fqx "ExecStart=/usr/bin/env PYTHONDONTWRITEBYTECODE=1 SETUPTOOLS_USE_DISTUTILS=stdlib STRUCTURAL_PROJECT_ROOT=$TARGET $RUNTIME_CURRENT/bin/python -I -B -m uvicorn main:app --app-dir $TARGET/web/backend --host 127.0.0.1 --port 5004 --no-access-log" || {
    echo "[deploy] ERROR: active systemd unit does not use the attested current runtime" >&2
    return 1
  }
  local effective_fragment effective_dropins effective_exec
  effective_fragment="$(systemctl show "$SERVICE" --property=FragmentPath --value)" \
    || return 1
  effective_dropins="$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    || return 1
  effective_exec="$(systemctl show "$SERVICE" --property=ExecStart --value)" \
    || return 1
  [[ "$(readlink -f "$effective_fragment")" == "$(readlink -f "$SYSTEMD_UNIT_TARGET")" ]] || {
    echo "[deploy] ERROR: effective systemd FragmentPath is not canonical" >&2
    return 1
  }
  [[ -z "$effective_dropins" ]] || {
    echo "[deploy] ERROR: systemd drop-ins may override the tracked unit" >&2
    return 1
  }
  [[ "$effective_exec" == *"/usr/bin/env"* \
    && "$effective_exec" == *"PYTHONDONTWRITEBYTECODE=1"* \
    && "$effective_exec" == *"SETUPTOOLS_USE_DISTUTILS=stdlib"* \
    && "$effective_exec" == *"STRUCTURAL_PROJECT_ROOT=$TARGET"* \
    && "$effective_exec" == *"$RUNTIME_CURRENT/bin/python"* \
    && "$effective_exec" == *" -I -B -m uvicorn main:app --app-dir $TARGET/web/backend "* \
    && "$effective_exec" == *"--no-access-log"* \
    && "$effective_exec" != *"$TARGET/venv/bin/python"* ]] || {
    echo "[deploy] ERROR: effective systemd ExecStart is not private and attested" >&2
    return 1
  }
}

rollback_deep_readiness() {
  local body
  for _attempt in $(seq 1 12); do
    if body="$(curl -fsS --max-time 2 'http://127.0.0.1:5004/api/health?deep=1' 2>/dev/null)" \
      && BODY="$body" "$RUNTIME_PYTHON" - <<'PY'
import json
import os

body = json.loads(os.environ["BODY"])
assert body.get("status") == "ok", body
assert body.get("kb_size") == 4443, body
assert body.get("artifact_id") == "structural-v2-kb4443-20260711", body
assert body.get("embedding_shape") == [4443, 768], body
PY
    then
      return 0
    fi
    sleep 2
  done
  return 1
}

abort_deploy() {
  DEPLOY_FAILURE_REASON="$1"
  echo "[deploy] FAIL: $DEPLOY_FAILURE_REASON" >&2
  return 1
}

# Prove the candidate through the canonical TLS virtual host while the deploy
# transaction is still active.  DNS is deliberately bypassed: this gate tests
# the just-installed local Nginx/service pair, not whichever release public DNS
# happened to resolve while the host was switching versions.
beta_candidate_tls_gate() {
  local origin="https://beta.structural.bytedance.city"
  local resolve="beta.structural.bytedance.city:443:127.0.0.1"
  local snapshot_env="$DEPLOY_SYNC_SOURCE/web/backend/.env.example"
  local expected_model attestation version health auth_response auth_status auth_body
  local headers search_body cross_domain_result query payload
  local cross_domain_seen=0

  [[ -f "$snapshot_env" ]] || {
    echo "[deploy] ERROR: candidate snapshot .env.example is missing" >&2
    return 1
  }
  [[ "$(grep -c '^ASK_LLM_MODEL=' "$snapshot_env" || true)" == "1" ]] || {
    echo "[deploy] ERROR: candidate snapshot ASK_LLM_MODEL is missing or duplicate" >&2
    return 1
  }
  expected_model="$(sed -n 's/^ASK_LLM_MODEL=//p' "$snapshot_env")"
  [[ -n "$expected_model" && "$expected_model" != *$'\r'* ]] || {
    echo "[deploy] ERROR: candidate snapshot ASK_LLM_MODEL is noncanonical" >&2
    return 1
  }
  [[ "$SOURCE_HEAD_SHA" =~ ^[0-9a-f]{40}$ \
    && "$RUNTIME_REQUIREMENTS_SHA256" =~ ^[0-9a-f]{64}$ \
    && "$RUNTIME_ID" == "$EXPECTED_PYTHON_ABI-$RUNTIME_REQUIREMENTS_SHA256-$RUNTIME_FREEZE_SHA256" \
    && "$DEPLOYED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
    echo "[deploy] ERROR: candidate gate inputs are noncanonical" >&2
    return 1
  }

  if ! attestation="$(curl -q -fsS --noproxy '*' --max-time 15 \
    --resolve "$resolve" -H 'Cache-Control: no-cache' \
    "$origin/assets/runtime-attestation.json?sha=$SOURCE_HEAD_SHA")"; then
    echo "[deploy] ERROR: candidate runtime attestation request failed" >&2
    return 1
  fi
  if ! version="$(curl -q -fsS --noproxy '*' --max-time 15 \
    --resolve "$resolve" -H 'Cache-Control: no-cache' \
    "$origin/api/version?sha=$SOURCE_HEAD_SHA")"; then
    echo "[deploy] ERROR: candidate version request failed" >&2
    return 1
  fi
  if ! ATTESTATION="$attestation" VERSION="$version" \
    EXPECTED_SHA="$SOURCE_HEAD_SHA" EXPECTED_MODEL="$expected_model" \
    EXPECTED_ABI="$EXPECTED_PYTHON_ABI" \
    EXPECTED_REQUIREMENTS_SHA="$RUNTIME_REQUIREMENTS_SHA256" \
    EXPECTED_RUNTIME_ID="$RUNTIME_ID" EXPECTED_DEPLOYED_AT="$DEPLOYED_AT" \
    EXPECTED_FASTAPI="$EXPECTED_FASTAPI_VERSION" \
    EXPECTED_PYDANTIC="$EXPECTED_PYDANTIC_VERSION" \
    EXPECTED_STARLETTE="$EXPECTED_STARLETTE_VERSION" \
    EXPECTED_UVICORN="$EXPECTED_UVICORN_VERSION" \
    "$RUNTIME_PYTHON" -I -S -B - <<'PY'
import hashlib
import json
import os
import re

attestation = json.loads(os.environ["ATTESTATION"])
version = json.loads(os.environ["VERSION"])
expected_sha = os.environ["EXPECTED_SHA"]
expected_abi = os.environ["EXPECTED_ABI"]
requirements_sha = os.environ["EXPECTED_REQUIREMENTS_SHA"]
expected_runtime_id = os.environ["EXPECTED_RUNTIME_ID"]
expected_deployed_at = os.environ["EXPECTED_DEPLOYED_AT"]
expected_packages = {
    "fastapi": os.environ["EXPECTED_FASTAPI"],
    "pydantic": os.environ["EXPECTED_PYDANTIC"],
    "starlette": os.environ["EXPECTED_STARLETTE"],
    "uvicorn": os.environ["EXPECTED_UVICORN"],
}

assert isinstance(attestation, dict) and isinstance(version, dict)
assert attestation.get("schema_version") == 2
assert attestation.get("python_abi") == expected_abi
assert attestation.get("requirements_sha256") == requirements_sha
graph_sha = attestation.get("resolved_graph_sha256")
content_sha = attestation.get("runtime_content_sha256")
freeze_sha = attestation.get("installed_freeze_sha256")
for digest in (graph_sha, content_sha, freeze_sha):
    assert isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
composite = hashlib.sha256(
    (
        f"resolved_graph_sha256={graph_sha}\n"
        f"runtime_content_sha256={content_sha}\n"
    ).encode("ascii")
).hexdigest()
assert freeze_sha == composite
assert attestation.get("runtime_id") == expected_runtime_id
assert expected_runtime_id == f"{expected_abi}-{requirements_sha}-{freeze_sha}"
assert attestation.get("git_sha") == version.get("git_sha") == expected_sha
assert attestation.get("deployed_at") == version.get("deployed_at") == expected_deployed_at
assert version.get("semver") == "0.2.0"
assert version.get("env") == "prod"
assert version.get("model") == os.environ["EXPECTED_MODEL"]
assert isinstance(version.get("python_version"), str)
assert version["python_version"].startswith("3.11.")
assert version.get("python_version") == attestation.get("python_version")
for field in ("python_abi", "runtime_id", "requirements_sha256", "installed_freeze_sha256"):
    assert version.get(field) == attestation.get(field)
for package, expected in expected_packages.items():
    assert attestation.get(package) == version.get(package) == expected
PY
  then
    echo "[deploy] ERROR: candidate runtime/version identity is invalid" >&2
    return 1
  fi

  if ! health="$(curl -q -fsS --noproxy '*' --max-time 20 --resolve "$resolve" \
    "$origin/api/health?deep=1")"; then
    echo "[deploy] ERROR: candidate deep-health request failed" >&2
    return 1
  fi
  if ! HEALTH="$health" "$RUNTIME_PYTHON" -I -S -B - <<'PY'
import json
import os

body = json.loads(os.environ["HEALTH"])
assert body.get("status") == "ok"
assert body.get("kb_size") == 4443
assert body.get("artifact_id") == "structural-v2-kb4443-20260711"
assert body.get("embedding_shape") == [4443, 768]
checks = body.get("checks")
assert isinstance(checks, dict)
for field in ("search_service", "knowledge_base", "artifact_manifest"):
    assert checks.get(field) == "ok"
assert checks.get("history_db") in {"ok", "missing"}
assert checks.get("llm_env") in {"ok", "missing"}
PY
  then
    echo "[deploy] ERROR: candidate deep-health payload is invalid" >&2
    return 1
  fi

  if ! auth_response="$(curl -q -sS --noproxy '*' --max-time 15 --resolve "$resolve" \
    -w $'\n%{http_code}' "$origin/api/auth/me")"; then
    echo "[deploy] ERROR: candidate auth request failed" >&2
    return 1
  fi
  auth_status="${auth_response##*$'\n'}"
  auth_body="${auth_response%$'\n'*}"
  if ! AUTH_STATUS="$auth_status" AUTH_BODY="$auth_body" \
    "$RUNTIME_PYTHON" -I -S -B - <<'PY'
import json
import os

body = json.loads(os.environ["AUTH_BODY"])
assert os.environ["AUTH_STATUS"] == "401"
assert body.get("error") == "no session"
PY
  then
    echo "[deploy] ERROR: candidate auth boundary is invalid" >&2
    return 1
  fi

  if ! headers="$(curl -q -fsS --noproxy '*' --max-time 15 --resolve "$resolve" \
    -D - -o /dev/null "$origin/")"; then
    echo "[deploy] ERROR: candidate homepage request failed" >&2
    return 1
  fi
  if ! HEADERS="$headers" "$RUNTIME_PYTHON" -I -S -B - <<'PY'
import os
import re

headers = {}
for raw_line in os.environ["HEADERS"].replace("\r", "").splitlines():
    if ":" not in raw_line:
        continue
    name, value = raw_line.split(":", 1)
    headers.setdefault(name.strip().lower(), []).append(value.strip())
assert headers.get("referrer-policy") == ["no-referrer"]
request_ids = headers.get("x-request-id", [])
assert len(request_ids) == 1
assert re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", request_ids[0])
PY
  then
    echo "[deploy] ERROR: candidate privacy/request-id headers are invalid" >&2
    return 1
  fi

  for query in \
    '月活用户每月固定流失百分之七，应该如何干预？' \
    '为什么有些谣言会突然爆发并形成级联传播？' \
    '团队氛围崩溃后为什么很难恢复？' \
    '银行挤兑为什么会出现自我强化？' \
    '一个平台如何避免正反馈导致系统失控？'; do
    payload="$(printf '{\"query\":\"%s\",\"top_k\":5,\"rewrite\":false,\"lang\":\"zh\"}' "$query")"
    if ! search_body="$(curl -q -fsS --noproxy '*' --max-time 25 --resolve "$resolve" \
      -H 'Content-Type: application/json' --data-binary "$payload" \
      "$origin/api/search")"; then
      echo "[deploy] ERROR: candidate semantic-search request failed" >&2
      return 1
    fi
    if ! cross_domain_result="$(SEARCH_BODY="$search_body" \
      "$RUNTIME_PYTHON" -I -S -B - <<'PY'
import json
import os

body = json.loads(os.environ["SEARCH_BODY"])
rows = body.get("results")
assert body.get("out_of_scope") is False
assert isinstance(rows, list) and len(rows) > 0
assert body.get("count") == len(rows)
assert all(isinstance(row, dict) for row in rows)
print("1" if any(row.get("cross_domain") is True for row in rows) else "0")
PY
    )"; then
      echo "[deploy] ERROR: candidate semantic-search payload is invalid" >&2
      return 1
    fi
    [[ "$cross_domain_result" == "0" || "$cross_domain_result" == "1" ]] || {
      echo "[deploy] ERROR: candidate semantic-search proof is noncanonical" >&2
      return 1
    }
    if [[ "$cross_domain_result" == "1" ]]; then
      cross_domain_seen=1
    fi
  done
  [[ "$cross_domain_seen" == "1" ]] || {
    echo "[deploy] ERROR: candidate searches contain no cross-domain result" >&2
    return 1
  }
}

# The validation boundary is sourceable so fault-injection tests can execute
# the production function without requiring root or reaching deployment I/O.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

deploy_guard_install rollback_deploy deploy_cleanup_once

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --prune-with-safety-list) PRUNE=1 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--dry-run] [--prune-with-safety-list]

Default: source-authoritative rsync with controlled deletion outside protected runtime paths.

Flags:
  --dry-run                   Show what would happen, do not write
  --prune-with-safety-list    Legacy alias; controlled deletion is already enabled

Env vars (with defaults shown):
  SOURCE=$SOURCE
  TARGET=$TARGET
  SERVICE=$SERVICE
  DEPLOY_COMMIT=$DEPLOY_COMMIT
EOF
      exit 0 ;;
  esac
done

validate_beta_sso_config
validate_beta_auth_config
if [[ "${STRUCTURAL_DEPLOY_LOCK_HELD:-0}" != "1" ]]; then
  exec 9>/var/lock/structural-isomorphism-deploy.lock
  flock -w 2700 9
fi
prepare_beta_auth_data_dir
SOURCE_HEAD_SHA="$(deploy_validate_source_checkout "$SOURCE" "$DEPLOY_COMMIT")" || exit 1

EXCLUDES=("${DEPLOY_STATIC_RSYNC_EXCLUDES[@]}")

RSYNC_FLAGS="-av --delete-delay"  # source is authoritative outside explicit protected paths
if [[ "$PRUNE" == "1" ]]; then
  echo "[deploy] NOTE: --prune-with-safety-list is now an alias; controlled deletion is always enabled."
fi

if [[ "$DRY_RUN" == "1" ]]; then
  runtime_require_disk_space "$RUNTIME_ROOT" || exit 1
else
  # Dependency preparation is deliberately before the code sync. A failed
  # network install, pip check or import/version attestation leaves the live
  # code, current runtime symlink and running process completely untouched.
  recover_previous_deploy_if_needed || {
    echo "[deploy] ERROR: unfinished deployment journal could not be recovered" >&2
    exit 1
  }
  runtime_capture_current || exit 1
  runtime_recover_orphan_builds || {
    echo "[deploy] ERROR: unsafe or unrecoverable runtime build residue" >&2
    exit 1
  }
fi

deploy_source_snapshot_prepare "$SOURCE" "$SOURCE_HEAD_SHA" || {
  echo "[deploy] ERROR: could not materialize a safe DEPLOY_COMMIT snapshot" >&2
  exit 1
}
DEPLOY_SYNC_SOURCE="$DEPLOY_SOURCE_SNAPSHOT"
EXCLUDES+=("--exclude-from=$DEPLOY_RSYNC_EXCLUDES_FILE")
RUNTIME_REQUIREMENTS="$DEPLOY_SYNC_SOURCE/web/backend/requirements.txt"
SYSTEMD_UNIT_SOURCE="$DEPLOY_SYNC_SOURCE/web/scripts/structural-web.service"
deploy_validate_target_tree || {
  echo "[deploy] ERROR: deploy target contains an unsafe symlink boundary" >&2
  exit 1
}

if [[ "$DRY_RUN" == "1" ]]; then
  CMD=(rsync -avn --delete-delay "${EXCLUDES[@]}" "$DEPLOY_SYNC_SOURCE/" "$TARGET/")
else
  runtime_prepare "$RUNTIME_REQUIREMENTS" || {
    echo "[deploy] ERROR: immutable runtime build/attestation failed" >&2
    exit 1
  }
  deploy_code_snapshot || {
    echo "[deploy] ERROR: could not capture the pre-deploy code snapshot" >&2
    exit 1
  }
  systemd_unit_capture || {
    echo "[deploy] ERROR: could not capture the pre-deploy systemd unit" >&2
    exit 1
  }
  systemd_dropin_capture "$BETA_AUTH_ENV_FILE" || {
    echo "[deploy] ERROR: legacy/unknown systemd drop-in is unsafe" >&2
    exit 1
  }
  capture_systemd_service_state || {
    echo "[deploy] ERROR: could not capture the pre-deploy service state" >&2
    exit 1
  }
  runtime_fingerprint_capture || {
    echo "[deploy] ERROR: could not capture the pre-deploy runtime fingerprint" >&2
    exit 1
  }
  nginx_vhost_capture || {
    echo "[deploy] ERROR: could not capture the pre-deploy Nginx vhost" >&2
    exit 1
  }
  DEPLOY_TRANSACTION_ACTIVE=1
  deploy_journal_write snapshot || abort_deploy "could not persist transaction journal"
  CMD=(rsync $RSYNC_FLAGS "${EXCLUDES[@]}" "$DEPLOY_SYNC_SOURCE/" "$TARGET/")
fi

echo "[deploy] Running: ${CMD[*]}"
if ! "${CMD[@]}" | tail -10; then
  if [[ "$DRY_RUN" == "0" ]]; then
    abort_deploy "code synchronization failed"
  fi
  exit 1
fi
if [[ "$DRY_RUN" == "0" ]]; then
  deploy_verify_code_identity || abort_deploy "post-sync code identity mismatch"
  deploy_journal_write code_synced || abort_deploy "could not journal synchronized code"
fi

if [[ "$DRY_RUN" == "0" ]]; then
  echo "[deploy] Switching current runtime atomically to $RUNTIME_ID..."
  RUNTIME_SWITCHED=1
  deploy_journal_write runtime_switching || abort_deploy "could not journal runtime switch intent"
  runtime_switch || abort_deploy "runtime symlink switch failed"
  deploy_journal_write runtime_switched || abort_deploy "could not journal runtime switch"
  export SETUPTOOLS_USE_DISTUTILS=stdlib
  export PYTHONDONTWRITEBYTECODE=1

  echo "[deploy] Validating production artifact bundle..."
  for required in \
    "$ARTIFACT_ROOT/manifest.json" \
    "$ARTIFACT_ROOT/kb-expanded.jsonl" \
    "$ARTIFACT_ROOT/kb_v2_embeddings.npy" \
    "$ARTIFACT_ROOT/structural-v2"; do
    [[ -e "$required" ]] || abort_deploy "missing production artifact: $required"
  done
  if ! (
    cd "$TARGET/web/backend"
    ARTIFACT_ROOT="$ARTIFACT_ROOT" "$RUNTIME_CURRENT/bin/python" -B - <<'PY'
import os

from services.artifact_manifest import validate_artifact_bundle

artifact_root = os.environ["ARTIFACT_ROOT"]
print(validate_artifact_bundle(
    f"{artifact_root}/manifest.json",
    kb_path=f"{artifact_root}/kb-expanded.jsonl",
    embeddings_path=f"{artifact_root}/kb_v2_embeddings.npy",
    model_path=f"{artifact_root}/structural-v2",
))
PY
  ); then
    abort_deploy "production artifact validation failed"
  fi

  # Session #16: write build/deploy fingerprint so /api/version returns real
  # values. Without this, prod returns git_sha="unknown" and dogfood scripts
  # can't fingerprint-check what code is actually running (session #15 root
  # cause: 5 days of stale-code deploys went undetected).
  echo "[deploy] Writing runtime fingerprint to web/backend/.env.runtime..."
  deploy_journal_write fingerprinting || abort_deploy "could not journal fingerprint intent"
  GIT_SHA="$SOURCE_HEAD_SHA"
  DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  RUNTIME_FINGERPRINT_TMP="$RUNTIME_FINGERPRINT_TARGET.tmp.$$"
  cat > "$RUNTIME_FINGERPRINT_TMP" <<EOF
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
STRUCTURAL_RUNTIME_ID=$RUNTIME_ID
STRUCTURAL_RUNTIME_REQUIREMENTS_SHA256=$RUNTIME_REQUIREMENTS_SHA256
STRUCTURAL_RUNTIME_FREEZE_SHA256=$RUNTIME_FREEZE_SHA256
EOF
  chmod 0600 "$RUNTIME_FINGERPRINT_TMP"
  mv -f "$RUNTIME_FINGERPRINT_TMP" "$RUNTIME_FINGERPRINT_TARGET"
  RUNTIME_FINGERPRINT_TMP=""
  echo "[deploy]   git_sha=$GIT_SHA"
  echo "[deploy]   deployed_at=$DEPLOYED_AT"
  echo "[deploy]   runtime_id=$RUNTIME_ID"

  # Publish only non-sensitive runtime provenance. This is generated by the
  # candidate interpreter itself and lets CI/production smoke verify that the
  # HTTP service is no longer running from the legacy mutable TARGET/venv.
  runtime_publish_attestation "$PUBLIC_RUNTIME_ATTESTATION" "$GIT_SHA" "$DEPLOYED_AT" \
    || abort_deploy "public runtime attestation publication failed"
  deploy_journal_write fingerprinted || abort_deploy "could not journal runtime fingerprint"

  # Exclusions protect runtime-only data, but no-delete rsync cannot remove a
  # tracked module retired by this release. The exact file is backed up before
  # deletion so even a manual deploy without PREVIOUS_SHA can restore it.
  echo "[deploy] Removing retired tracked path if present: $RETIRED_TRACKED_RELATIVE_PATH"
  retired_module_capture "$TARGET" \
    || abort_deploy "retired tracked path preimage capture failed"
  deploy_journal_write retired_captured \
    || abort_deploy "could not journal retired tracked path preimage"
  if [[ "$RETIRED_TRACKED_WAS_PRESENT" == "1" ]]; then
    # Persist the removal intent before mutating the live target. Recovery may
    # safely restore the same bytes if SIGKILL lands between these two steps.
    RETIRED_TRACKED_REMOVED=1
    deploy_journal_write retired_removing \
      || abort_deploy "could not journal retired tracked path removal intent"
  fi
  retired_module_remove "$TARGET" \
    || abort_deploy "retired tracked path cleanup failed"
  deploy_journal_write retired_removed \
    || abort_deploy "could not journal retired tracked path cleanup"

  echo "[deploy] Installing canonical systemd unit..."
  install_structural_systemd_unit || abort_deploy "canonical systemd unit installation failed"
  deploy_journal_write unit_installed || abort_deploy "could not journal systemd unit installation"
  echo "[deploy] Restarting $SERVICE..."
  systemctl restart "$SERVICE" || abort_deploy "service restart failed"
  deploy_journal_write restarted || abort_deploy "could not journal service restart"
  READY=0
  for attempt in $(seq 1 24); do
    if systemctl is-active --quiet "$SERVICE" \
      && HEALTH="$(curl -fsS --max-time 5 'http://127.0.0.1:5004/api/health?deep=1' 2>/dev/null)" \
      && HEALTH="$HEALTH" "$RUNTIME_CURRENT/bin/python" -B - <<'PY'
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
  [[ "$READY" == "1" ]] || abort_deploy "deep health not ready after 120 seconds"
  if ! AUTH_STATUS="$(curl -sS --max-time 5 -o /tmp/structural-beta-auth-me.json -w '%{http_code}' \
    'http://127.0.0.1:5004/api/auth/me')"; then
    abort_deploy "beta account runtime request failed"
  fi
  [[ "$AUTH_STATUS" == "401" ]] || abort_deploy "beta account runtime is not enabled"
  "$RUNTIME_CURRENT/bin/python" -B - <<'PY' || abort_deploy "beta account runtime response is invalid"
import json

with open("/tmp/structural-beta-auth-me.json", encoding="utf-8") as handle:
    body = json.load(handle)
assert body.get("error") == "no session", body
PY
  if ! VERSION_JSON="$(curl -fsS --max-time 5 'http://127.0.0.1:5004/api/version')"; then
    abort_deploy "runtime fingerprint request failed"
  fi
  VERSION_JSON="$VERSION_JSON" EXPECTED_GIT_SHA="$GIT_SHA" \
    EXPECTED_RUNTIME_ID="$RUNTIME_ID" \
    PUBLIC_RUNTIME_ATTESTATION="$PUBLIC_RUNTIME_ATTESTATION" \
    "$RUNTIME_CURRENT/bin/python" -B - <<'PY' \
    || abort_deploy "runtime fingerprint does not match deployed code/runtime"
import json
import os
from pathlib import Path

version = json.loads(os.environ["VERSION_JSON"])
attestation = json.loads(
    Path(os.environ["PUBLIC_RUNTIME_ATTESTATION"]).read_text(encoding="utf-8")
)
expected_git_sha = os.environ["EXPECTED_GIT_SHA"]
expected_runtime_id = os.environ["EXPECTED_RUNTIME_ID"]
assert version.get("git_sha") == expected_git_sha, version
assert attestation.get("git_sha") == expected_git_sha, attestation
assert attestation.get("runtime_id") == expected_runtime_id, attestation
assert version.get("python_version") == attestation.get("python_version"), (version, attestation)
assert version.get("deployed_at") == attestation.get("deployed_at"), (version, attestation)
for field in (
    "python_abi", "runtime_id", "requirements_sha256", "installed_freeze_sha256",
    "fastapi", "pydantic", "starlette", "uvicorn",
):
    assert version.get(field) == attestation.get(field), (field, version, attestation)
PY
  NGINX_INSTALLER="$TARGET/scripts/install-nginx-privacy-vhost.sh"
  NGINX_VHOST_SOURCE="$TARGET/web/scripts/beta-structural.nginx.conf"
  [[ -f "$NGINX_INSTALLER" && -f "$NGINX_VHOST_SOURCE" ]] \
    || abort_deploy "canonical Nginx privacy installer/config is missing"
  NGINX_VHOST_INSTALLED=1
  deploy_journal_write nginx_installing || abort_deploy "could not journal Nginx install intent"
  bash "$NGINX_INSTALLER" \
    "$NGINX_VHOST_SOURCE" \
    "$NGINX_VHOST_TARGET" \
    beta.structural.bytedance.city \
    structural_beta_privacy \
    || abort_deploy "canonical private Nginx vhost installation failed"
  deploy_journal_write nginx_installed || abort_deploy "could not journal Nginx installation"
  beta_candidate_tls_gate \
    || abort_deploy "candidate failed canonical TLS pre-commit gate"
  deploy_journal_write ready || abort_deploy "could not journal readiness"
  deploy_journal_write success || abort_deploy "could not persist successful deployment journal"
  runtime_gc_releases || abort_deploy "safe runtime release GC failed"
  DEPLOY_TRANSACTION_ACTIVE=0
  deploy_cleanup_once || abort_deploy "terminal transaction cleanup failed"
  echo "[deploy] OK"
fi
