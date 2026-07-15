#!/usr/bin/env bash
# Deploy both Phase Detector services from the VPS Git worktree.
set -Eeuo pipefail
umask 077

# Freeze the source-versus-production execution boundary exactly once. Tests
# source this file to exercise helpers; a caller must not be able to unset the
# public switch afterwards and turn those helpers into production mutators.
if [[ "${STRUCTURAL_PHASE_DEPLOY_LIBRARY_ONLY:-0}" == "1" ]]; then
  readonly PHASE_DEPLOY_LIBRARY_CONTEXT=1
else
  readonly PHASE_DEPLOY_LIBRARY_CONTEXT=0
fi

REPO="${PHASE_REPO:-/root/Projects/structural-isomorphism-v4}"
API_REQUIREMENTS="$REPO/v4/product/d1_phase_detector/api/requirements.txt"
API_PYTHON="$REPO/.venv/bin/python"
API_PIP="$REPO/.venv/bin/pip"
WEB_DIR="$REPO/web/phase-detector"
AUTH_ENV_FILE="${PHASE_AUTH_ENV_FILE:-/root/.config/structural-isomorphism/phase-auth.env}"
BETA_ENV_FILE="${STRUCTURAL_BETA_ENV_FILE:-$REPO/web/backend/.env}"
PHASE_PRIVACY_DROPIN_SOURCE="$REPO/web/phase-detector/phase-detector-api-privacy.conf"
PHASE_PRIVACY_DROPIN_TARGET="${PHASE_PRIVACY_DROPIN_TARGET:-/etc/systemd/system/phase-detector-api.service.d/20-privacy.conf}"
PHASE_NGINX_SOURCE="$REPO/web/phase-detector/phase.bytedance.city.nginx.conf"
PHASE_NGINX_TARGET="${PHASE_NGINX_TARGET:-/etc/nginx/conf.d/phase.bytedance.city.conf}"
PHASE_ENGINE_PATH="${BASH_SOURCE[0]}"
PHASE_ENGINE_DIR="${PHASE_ENGINE_PATH%/*}"
[[ "$PHASE_ENGINE_DIR" != "$PHASE_ENGINE_PATH" ]] || PHASE_ENGINE_DIR=.
# Recovery must use bytes installed atomically with this engine, never the
# privacy installer from a target checkout changed by an exact-SHA reset.
NGINX_PRIVACY_INSTALLER="$PHASE_ENGINE_DIR/install-nginx-privacy-vhost.sh"
PHASE_DEPLOY_STATE_DIR="${PHASE_DEPLOY_STATE_DIR:-/var/lib/structural-isomorphism/phase-deploy}"
PHASE_DEPLOY_JOURNAL="$PHASE_DEPLOY_STATE_DIR/privacy.journal"
PHASE_DEPLOY_DROPIN_BACKUP="$PHASE_DEPLOY_STATE_DIR/privacy-dropin.backup"
LOG_PREFIX="[deploy-phase-detector $(date -u +%FT%TZ)]"
PREVIOUS_SHA=""
DEPLOY_COMPLETE=0
PHASE_PRIVACY_DROPIN_INSTALLED=0
PHASE_PRIVACY_DROPIN_PREEXISTED=0
PHASE_PRIVACY_DROPIN_BACKUP=""
PHASE_NGINX_PREPARED=0
PHASE_OUTER_TRANSACTION_ACTIVE=0

export NVM_DIR="/root/.nvm"
# shellcheck disable=SC1091
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"

env_key_once() {
  local file="$1" key="$2"
  [[ "$(grep -cE "^${key}=" "$file" || true)" == "1" ]]
}

env_exact_once() {
  local file="$1" key="$2" expected="$3"
  env_key_once "$file" "$key" && grep -qx "${key}=${expected}" "$file"
}

validate_phase_privacy_hmac_key() {
  local value="$1"
  # Canonical ASCII is intentionally stricter than generic entropy: systemd
  # EnvironmentFile parsing must yield the exact bytes validated here.
  printf '%s' "$value" | /usr/bin/python3 -I -c '
import re
import sys

raw = sys.stdin.buffer.read()
valid = re.fullmatch(rb"[0-9a-f]{64}", raw) is not None and len(set(raw)) >= 12
raise SystemExit(0 if valid else 1)
'
}

validate_phase_privacy_hmac_preflight() {
  local privacy_hmac_key
  [[ -f "$AUTH_ENV_FILE" && ! -L "$AUTH_ENV_FILE" ]] || {
    echo "$LOG_PREFIX ERROR: private Phase environment file missing or unsafe" >&2
    return 1
  }
  [[ "$(phase_file_mode "$AUTH_ENV_FILE")" == "600" ]] || {
    echo "$LOG_PREFIX ERROR: private Phase environment must have mode 600" >&2
    return 1
  }
  env_key_once "$AUTH_ENV_FILE" STRUCTURAL_PRIVACY_HMAC_KEY || {
    echo "$LOG_PREFIX ERROR: STRUCTURAL_PRIVACY_HMAC_KEY must occur exactly once" >&2
    return 1
  }
  privacy_hmac_key="$(sed -n 's/^STRUCTURAL_PRIVACY_HMAC_KEY=//p' "$AUTH_ENV_FILE")" \
    || return 1
  validate_phase_privacy_hmac_key "$privacy_hmac_key" || {
    echo "$LOG_PREFIX ERROR: STRUCTURAL_PRIVACY_HMAC_KEY is unsafe" >&2
    return 1
  }
}

phase_destructive_repo_safe() {
  local test_root repo_root marker
  [[ "$PHASE_DEPLOY_LIBRARY_CONTEXT" == "1" ]] || return 0
  [[ -n "${STRUCTURAL_PHASE_TEST_ROOT:-}" \
     && -d "$STRUCTURAL_PHASE_TEST_ROOT" \
     && ! -L "$STRUCTURAL_PHASE_TEST_ROOT" \
     && -d "$REPO" \
     && ! -L "$REPO" ]] || return 1
  test_root="$(cd -P -- "$STRUCTURAL_PHASE_TEST_ROOT" && pwd)" || return 1
  repo_root="$(cd -P -- "$REPO" && pwd)" || return 1
  [[ "$test_root" != *$'\n'* && "$test_root" != *$'\r'* \
     && "$repo_root" != *$'\n'* && "$repo_root" != *$'\r'* \
     && "$repo_root" != "$test_root" ]] || return 1
  case "$repo_root" in
    "$test_root"/*) ;;
    *) return 1 ;;
  esac
  [[ -d "$repo_root/.git" && ! -L "$repo_root/.git" ]] || return 1
  marker="$repo_root/.git/structural-phase-test-isolation-v1"
  [[ -f "$marker" && ! -L "$marker" && -O "$marker" \
     && "$(phase_file_mode "$marker")" == "600" \
     && "$(wc -l <"$marker" | tr -d ' ')" == "3" \
     && "$(sed -n '1p' "$marker")" == "protocol=structural-phase-test-isolation-v1" \
     && "$(sed -n '2p' "$marker")" == "test_root=$test_root" \
     && "$(sed -n '3p' "$marker")" == "repo_root=$repo_root" ]]
}

phase_file_mode() {
  if stat -c '%a' "$1" >/dev/null 2>&1; then
    stat -c '%a' "$1"
  else
    stat -f '%Lp' "$1"
  fi
}

phase_fsync_file_and_parent() {
  local path="$1" label="${2:-file}"
  if [[ "$PHASE_DEPLOY_LIBRARY_CONTEXT" == "1" \
     && "${STRUCTURAL_PHASE_TEST_FSYNC_FAIL_AT:-}" == "$label" ]]; then
    return 1
  fi
  /usr/bin/python3 -I - "$path" <<'PY'
import os
import stat
import sys

path = os.path.abspath(sys.argv[1])
file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
file_fd = os.open(path, file_flags)
try:
    if not stat.S_ISREG(os.fstat(file_fd).st_mode):
        raise OSError("fsync target is not a regular file")
    os.fsync(file_fd)
finally:
    os.close(file_fd)

parent = os.path.dirname(path)
dir_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
dir_fd = os.open(parent, dir_flags)
try:
    if not stat.S_ISDIR(os.fstat(dir_fd).st_mode):
        raise OSError("fsync parent is not a directory")
    os.fsync(dir_fd)
finally:
    os.close(dir_fd)
PY
}

phase_fsync_parent() {
  local path="$1" label="${2:-parent}"
  if [[ "$PHASE_DEPLOY_LIBRARY_CONTEXT" == "1" \
     && "${STRUCTURAL_PHASE_TEST_FSYNC_FAIL_AT:-}" == "$label" ]]; then
    return 1
  fi
  /usr/bin/python3 -I - "$path" <<'PY'
import os
import stat
import sys

parent = os.path.dirname(os.path.abspath(sys.argv[1]))
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
directory_fd = os.open(parent, flags)
try:
    if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
        raise OSError("fsync parent is not a directory")
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY
}

phase_privacy_installer_safe() {
  [[ -f "$NGINX_PRIVACY_INSTALLER" && ! -L "$NGINX_PRIVACY_INSTALLER" ]]
}

phase_outer_state_init() {
  [[ "$PHASE_DEPLOY_STATE_DIR" == /* \
     && "$PHASE_DEPLOY_STATE_DIR" != *$'\n'* \
     && "$PHASE_DEPLOY_STATE_DIR" != *$'\r'* \
     && "$PHASE_DEPLOY_STATE_DIR" != */../* \
     && "$PHASE_DEPLOY_STATE_DIR" != */.. ]] || return 1
  mkdir -p "$PHASE_DEPLOY_STATE_DIR" || return 1
  [[ -d "$PHASE_DEPLOY_STATE_DIR" && ! -L "$PHASE_DEPLOY_STATE_DIR" ]] || return 1
  chmod 700 "$PHASE_DEPLOY_STATE_DIR" || return 1
  [[ "$(phase_file_mode "$PHASE_DEPLOY_STATE_DIR")" == "700" ]] || return 1
}

phase_outer_write_journal() {
  local phase="$1" previous_sha="$2" had_dropin="$3" dropin_mode="$4"
  local temp="$PHASE_DEPLOY_JOURNAL.tmp.$$"
  [[ "$phase" =~ ^(started|nginx_prepared|dropin_installed|services_restarted|smoke_passed|nginx_committed)$ \
     && "$previous_sha" =~ ^[0-9a-f]{40}$ \
     && ( "$had_dropin" == "0" || "$had_dropin" == "1" ) ]] || return 1
  if [[ "$had_dropin" == "1" ]]; then
    [[ "$dropin_mode" =~ ^[0-7]{3,4}$ ]] || return 1
  else
    [[ "$dropin_mode" == "0" ]] || return 1
  fi
  rm -f "$temp"
  printf '%s\n' \
    'version=1' \
    "phase=$phase" \
    "previous_sha=$previous_sha" \
    "dropin_target=$PHASE_PRIVACY_DROPIN_TARGET" \
    "dropin_had=$had_dropin" \
    "dropin_mode=$dropin_mode" \
    "dropin_backup=$PHASE_DEPLOY_DROPIN_BACKUP" \
    "nginx_target=$PHASE_NGINX_TARGET" >"$temp" || return 1
  chmod 600 "$temp" || return 1
  phase_fsync_file_and_parent "$temp" outer_journal_temp || return 1
  mv "$temp" "$PHASE_DEPLOY_JOURNAL" || return 1
  phase_fsync_file_and_parent "$PHASE_DEPLOY_JOURNAL" outer_journal_commit || return 1
  [[ -f "$PHASE_DEPLOY_JOURNAL" && ! -L "$PHASE_DEPLOY_JOURNAL" \
     && "$(phase_file_mode "$PHASE_DEPLOY_JOURNAL")" == "600" ]] || return 1
}

phase_outer_read_journal() {
  [[ -f "$PHASE_DEPLOY_JOURNAL" && ! -L "$PHASE_DEPLOY_JOURNAL" \
     && "$(phase_file_mode "$PHASE_DEPLOY_JOURNAL")" == "600" \
     && "$(wc -l <"$PHASE_DEPLOY_JOURNAL" | tr -d ' ')" == "8" ]] || return 1
  grep -Fqx 'version=1' "$PHASE_DEPLOY_JOURNAL" || return 1
  grep -Fqx "dropin_target=$PHASE_PRIVACY_DROPIN_TARGET" "$PHASE_DEPLOY_JOURNAL" || return 1
  grep -Fqx "dropin_backup=$PHASE_DEPLOY_DROPIN_BACKUP" "$PHASE_DEPLOY_JOURNAL" || return 1
  grep -Fqx "nginx_target=$PHASE_NGINX_TARGET" "$PHASE_DEPLOY_JOURNAL" || return 1
  JOURNAL_PHASE="$(sed -n 's/^phase=//p' "$PHASE_DEPLOY_JOURNAL")"
  JOURNAL_PREVIOUS_SHA="$(sed -n 's/^previous_sha=//p' "$PHASE_DEPLOY_JOURNAL")"
  JOURNAL_DROPIN_HAD="$(sed -n 's/^dropin_had=//p' "$PHASE_DEPLOY_JOURNAL")"
  JOURNAL_DROPIN_MODE="$(sed -n 's/^dropin_mode=//p' "$PHASE_DEPLOY_JOURNAL")"
  [[ "$JOURNAL_PHASE" =~ ^(started|nginx_prepared|dropin_installed|services_restarted|smoke_passed|nginx_committed)$ \
     && "$JOURNAL_PREVIOUS_SHA" =~ ^[0-9a-f]{40}$ \
     && ( "$JOURNAL_DROPIN_HAD" == "0" || "$JOURNAL_DROPIN_HAD" == "1" ) ]] || return 1
  if [[ "$JOURNAL_DROPIN_HAD" == "1" ]]; then
    [[ "$JOURNAL_DROPIN_MODE" =~ ^[0-7]{3,4}$ \
       && -f "$PHASE_DEPLOY_DROPIN_BACKUP" \
       && ! -L "$PHASE_DEPLOY_DROPIN_BACKUP" \
       && "$(phase_file_mode "$PHASE_DEPLOY_DROPIN_BACKUP")" == "600" ]] || return 1
  else
    [[ "$JOURNAL_DROPIN_MODE" == "0" ]] || return 1
  fi
}

phase_outer_mark() {
  local phase="$1"
  phase_outer_read_journal || return 1
  phase_outer_write_journal \
    "$phase" "$JOURNAL_PREVIOUS_SHA" "$JOURNAL_DROPIN_HAD" "$JOURNAL_DROPIN_MODE"
}

phase_outer_clear() {
  rm -f "$PHASE_DEPLOY_JOURNAL" || return 1
  phase_fsync_parent "$PHASE_DEPLOY_JOURNAL" outer_journal_remove || return 1
  rm -f "$PHASE_DEPLOY_DROPIN_BACKUP" || return 1
  phase_fsync_parent "$PHASE_DEPLOY_DROPIN_BACKUP" outer_backup_remove || return 1
  PHASE_OUTER_TRANSACTION_ACTIVE=0
}

phase_nginx_transaction_journal() {
  if [[ -n "${STRUCTURAL_NGINX_TEST_ROOT:-}" ]]; then
    printf '%s\n' \
      "$STRUCTURAL_NGINX_TEST_ROOT/var/lib/structural-isomorphism/nginx-privacy/structural_phase_privacy.journal"
  else
    printf '%s\n' \
      "/var/lib/structural-isomorphism/nginx-privacy/structural_phase_privacy.journal"
  fi
}

phase_privacy_targets_match_sources() {
  [[ -f "$PHASE_NGINX_SOURCE" && -f "$PHASE_NGINX_TARGET" \
     && ! -L "$PHASE_NGINX_TARGET" \
     && -f "$PHASE_PRIVACY_DROPIN_SOURCE" \
     && -f "$PHASE_PRIVACY_DROPIN_TARGET" \
     && ! -L "$PHASE_PRIVACY_DROPIN_TARGET" ]] || return 1
  cmp -s "$PHASE_NGINX_SOURCE" "$PHASE_NGINX_TARGET" \
    && cmp -s "$PHASE_PRIVACY_DROPIN_SOURCE" "$PHASE_PRIVACY_DROPIN_TARGET"
}

begin_phase_outer_transaction() {
  phase_outer_state_init || return 1
  [[ ! -e "$PHASE_DEPLOY_JOURNAL" && ! -L "$PHASE_DEPLOY_JOURNAL" ]] || return 1
  rm -f "$PHASE_DEPLOY_DROPIN_BACKUP" || return 1
  phase_fsync_parent "$PHASE_DEPLOY_DROPIN_BACKUP" outer_stale_backup_remove || return 1
  PHASE_PRIVACY_DROPIN_PREEXISTED=0
  JOURNAL_DROPIN_MODE=0
  if [[ -e "$PHASE_PRIVACY_DROPIN_TARGET" || -L "$PHASE_PRIVACY_DROPIN_TARGET" ]]; then
    [[ -f "$PHASE_PRIVACY_DROPIN_TARGET" && ! -L "$PHASE_PRIVACY_DROPIN_TARGET" ]] \
      || return 1
    PHASE_PRIVACY_DROPIN_PREEXISTED=1
    JOURNAL_DROPIN_MODE="$(phase_file_mode "$PHASE_PRIVACY_DROPIN_TARGET")"
    cp "$PHASE_PRIVACY_DROPIN_TARGET" "$PHASE_DEPLOY_DROPIN_BACKUP" || return 1
    chmod 600 "$PHASE_DEPLOY_DROPIN_BACKUP" || return 1
    phase_fsync_file_and_parent "$PHASE_DEPLOY_DROPIN_BACKUP" outer_backup || return 1
  fi
  PHASE_PRIVACY_DROPIN_BACKUP="$PHASE_DEPLOY_DROPIN_BACKUP"
  phase_outer_write_journal \
    started "$PREVIOUS_SHA" "$PHASE_PRIVACY_DROPIN_PREEXISTED" "$JOURNAL_DROPIN_MODE" \
    || return 1
  PHASE_OUTER_TRANSACTION_ACTIVE=1
}

restore_previous_phase_release() {
  local sha="$1"
  phase_destructive_repo_safe || {
    echo "$LOG_PREFIX CRITICAL: refusing destructive Phase recovery outside an isolated test repository" >&2
    return 1
  }
  git -C "$REPO" cat-file -e "$sha^{commit}" || return 1
  git -C "$REPO" reset --hard "$sha" || return 1
  "$API_PIP" install --disable-pip-version-check -r "$API_REQUIREMENTS" || return 1
  (cd "$WEB_DIR" && pnpm install --frozen-lockfile && pnpm build) || return 1
  systemctl restart phase-detector-api phase-detector-web || return 1
  systemctl is-active --quiet phase-detector-api \
    && systemctl is-active --quiet phase-detector-web
}

recover_phase_outer_transaction() {
  local nginx_journal failed=0
  phase_outer_state_init || return 1
  if [[ ! -e "$PHASE_DEPLOY_JOURNAL" && ! -L "$PHASE_DEPLOY_JOURNAL" ]]; then
    rm -f "$PHASE_DEPLOY_DROPIN_BACKUP" || return 1
    phase_fsync_parent "$PHASE_DEPLOY_DROPIN_BACKUP" outer_orphan_backup_remove || return 1
    return 0
  fi
  phase_outer_read_journal || return 1
  nginx_journal="$(phase_nginx_transaction_journal)"

  if [[ "$JOURNAL_PHASE" == "started" ]]; then
    # `prepare` durably changes and reloads Nginx before the outer phase can
    # be advanced.  A SIGKILL in that narrow interval leaves the inner
    # installer journal as the only proof that Nginx must be rolled back.
    if [[ -e "$nginx_journal" || -L "$nginx_journal" ]]; then
      STRUCTURAL_NGINX_TRANSACTION_ACTION=rollback \
        bash "$NGINX_PRIVACY_INSTALLER" \
          "$PHASE_NGINX_SOURCE" "$PHASE_NGINX_TARGET" \
          phase.bytedance.city structural_phase_privacy || return 1
    fi
    # HEAD alone cannot prove reset --hard completed: Git updates the index,
    # worktree, and ref separately. Always rebuild the recorded previous
    # release so a host crash cannot leave mixed checkout or dependency bytes.
    restore_previous_phase_release "$JOURNAL_PREVIOUS_SHA" || return 1
    phase_outer_clear || return 1
    echo "$LOG_PREFIX recovered interrupted pre-activation Phase deployment"
    return 0
  fi

  # A crash after the Nginx commit but before outer cleanup is safely
  # completed forward only when both durable targets still match sources.
  if [[ "$JOURNAL_PHASE" == "nginx_committed" \
     || ( "$JOURNAL_PHASE" == "smoke_passed" \
          && ! -e "$nginx_journal" \
          && phase_privacy_targets_match_sources ) ]]; then
    phase_privacy_targets_match_sources || return 1
    nginx -t >/dev/null 2>&1 || return 1
    systemctl daemon-reload || return 1
    systemctl restart phase-detector-api phase-detector-web || return 1
    systemctl is-active --quiet phase-detector-api || return 1
    systemctl is-active --quiet phase-detector-web || return 1
    phase_outer_clear || return 1
    echo "$LOG_PREFIX recovered committed Phase privacy transaction"
    return 0
  fi

  STRUCTURAL_NGINX_TRANSACTION_ACTION=rollback \
    bash "$NGINX_PRIVACY_INSTALLER" \
      "$PHASE_NGINX_SOURCE" "$PHASE_NGINX_TARGET" \
      phase.bytedance.city structural_phase_privacy || failed=1
  if [[ "$JOURNAL_DROPIN_HAD" == "1" ]]; then
    install -m "$JOURNAL_DROPIN_MODE" \
      "$PHASE_DEPLOY_DROPIN_BACKUP" "$PHASE_PRIVACY_DROPIN_TARGET" || failed=1
    phase_fsync_file_and_parent \
      "$PHASE_PRIVACY_DROPIN_TARGET" outer_recovery_dropin_restore || failed=1
  else
    rm -f "$PHASE_PRIVACY_DROPIN_TARGET" || failed=1
    phase_fsync_parent \
      "$PHASE_PRIVACY_DROPIN_TARGET" outer_recovery_dropin_remove || failed=1
  fi
  systemctl daemon-reload || failed=1
  [[ "$failed" == "0" ]] || return 1
  restore_previous_phase_release "$JOURNAL_PREVIOUS_SHA" || return 1
  phase_outer_clear || return 1
  echo "$LOG_PREFIX recovered interrupted Phase deployment"
}

restore_phase_privacy_dropin() {
  [[ "$PHASE_PRIVACY_DROPIN_INSTALLED" == "1" ]] || return 0
  local failed=0
  if [[ "$PHASE_PRIVACY_DROPIN_PREEXISTED" == "1" ]]; then
    if [[ -f "$PHASE_PRIVACY_DROPIN_BACKUP" && ! -L "$PHASE_PRIVACY_DROPIN_BACKUP" ]]; then
      cp -a "$PHASE_PRIVACY_DROPIN_BACKUP" "$PHASE_PRIVACY_DROPIN_TARGET" || failed=1
      phase_fsync_file_and_parent \
        "$PHASE_PRIVACY_DROPIN_TARGET" outer_dropin_rollback_restore || failed=1
    else
      failed=1
    fi
  else
    rm -f "$PHASE_PRIVACY_DROPIN_TARGET" || failed=1
    phase_fsync_parent \
      "$PHASE_PRIVACY_DROPIN_TARGET" outer_dropin_rollback_remove || failed=1
  fi
  systemctl daemon-reload || failed=1
  if [[ "$failed" == "0" ]]; then
    PHASE_PRIVACY_DROPIN_INSTALLED=0
    if [[ "$PHASE_OUTER_TRANSACTION_ACTIVE" != "1" ]]; then
      rm -f "$PHASE_PRIVACY_DROPIN_BACKUP"
      PHASE_PRIVACY_DROPIN_BACKUP=""
    fi
  fi
  return "$failed"
}

rollback_phase_nginx() {
  [[ "$PHASE_NGINX_PREPARED" == "1" ]] || return 0
  if STRUCTURAL_NGINX_TRANSACTION_ACTION=rollback \
      bash "$NGINX_PRIVACY_INSTALLER" \
        "$PHASE_NGINX_SOURCE" \
        "$PHASE_NGINX_TARGET" \
        phase.bytedance.city \
        structural_phase_privacy; then
    PHASE_NGINX_PREPARED=0
    return 0
  fi
  return 1
}

commit_phase_privacy() {
  [[ "$PHASE_NGINX_PREPARED" == "1" ]] || return 1
  STRUCTURAL_NGINX_TRANSACTION_ACTION=commit \
    bash "$NGINX_PRIVACY_INSTALLER" \
      "$PHASE_NGINX_SOURCE" \
      "$PHASE_NGINX_TARGET" \
      phase.bytedance.city \
      structural_phase_privacy
  PHASE_NGINX_PREPARED=0
  PHASE_PRIVACY_DROPIN_INSTALLED=0
}

install_phase_privacy_dropin() {
  local expected effective dropins
  expected="ExecStart=/root/Projects/structural-isomorphism-v4/.venv/bin/uvicorn v4.product.d1_phase_detector.api.main:app --host 127.0.0.1 --port 8200 --no-access-log"
  [[ -f "$PHASE_PRIVACY_DROPIN_SOURCE" ]] \
    && grep -Fqx 'ExecStart=' "$PHASE_PRIVACY_DROPIN_SOURCE" \
    && grep -Fqx "$expected" "$PHASE_PRIVACY_DROPIN_SOURCE" || {
      echo "$LOG_PREFIX ERROR: canonical Phase privacy drop-in is invalid" >&2
      return 1
    }
  mkdir -p "$(dirname "$PHASE_PRIVACY_DROPIN_TARGET")" || return 1
  [[ "$PHASE_OUTER_TRANSACTION_ACTIVE" == "1" \
     && "$PHASE_PRIVACY_DROPIN_BACKUP" == "$PHASE_DEPLOY_DROPIN_BACKUP" ]] \
    || return 1
  PHASE_PRIVACY_DROPIN_INSTALLED=1
  install -m 0644 "$PHASE_PRIVACY_DROPIN_SOURCE" "$PHASE_PRIVACY_DROPIN_TARGET" \
    || { restore_phase_privacy_dropin; return 1; }
  phase_fsync_file_and_parent "$PHASE_PRIVACY_DROPIN_TARGET" outer_dropin_install \
    || { restore_phase_privacy_dropin; return 1; }
  systemctl daemon-reload || { restore_phase_privacy_dropin; return 1; }
  effective="$(systemctl show phase-detector-api --property=ExecStart --value)" \
    || { restore_phase_privacy_dropin; return 1; }
  dropins="$(systemctl show phase-detector-api --property=DropInPaths --value)" \
    || { restore_phase_privacy_dropin; return 1; }
  [[ "$effective" == *'/root/Projects/structural-isomorphism-v4/.venv/bin/uvicorn'* \
    && "$effective" == *'--no-access-log'* \
    && "$dropins" == *"$PHASE_PRIVACY_DROPIN_TARGET"* ]] \
    || { restore_phase_privacy_dropin; return 1; }
  systemctl cat phase-detector-api | grep -Fq "EnvironmentFile=$AUTH_ENV_FILE" \
    || { restore_phase_privacy_dropin; return 1; }
}

rollback_phase() {
  local code="${1:-$?}"
  local reason="${2:-command failed}"
  if [[ "$DEPLOY_COMPLETE" == "1" ]]; then return; fi
  trap - ERR INT TERM HUP EXIT
  set +e
  echo "$LOG_PREFIX ERROR: $reason; rolling back to $PREVIOUS_SHA" >&2
  if [[ -f "$PHASE_DEPLOY_JOURNAL" && ! -L "$PHASE_DEPLOY_JOURNAL" ]]; then
    if recover_phase_outer_transaction; then
      exit "$code"
    fi
    echo "$LOG_PREFIX CRITICAL: durable Phase recovery failed; evidence retained" >&2
    exit "$code"
  fi
  rollback_phase_nginx || \
    echo "$LOG_PREFIX CRITICAL: Phase Nginx rollback failed; installer evidence retained" >&2
  restore_phase_privacy_dropin || \
    echo "$LOG_PREFIX CRITICAL: Phase privacy drop-in rollback failed; backup retained" >&2
  phase_destructive_repo_safe || {
    echo "$LOG_PREFIX CRITICAL: refusing destructive Phase rollback outside an isolated test repository" >&2
    exit "$code"
  }
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

phase_sync_exact_commit() {
  local deploy_sha="$1" fetched_main_sha
  [[ "$deploy_sha" =~ ^[0-9a-f]{40}$ ]] || return 1
  phase_destructive_repo_safe || {
    echo "$LOG_PREFIX CRITICAL: refusing destructive Phase activation outside an isolated test repository" >&2
    return 1
  }
  git -C "$REPO" fetch --prune origin \
    '+refs/heads/main:refs/remotes/origin/main' || return 1
  git -C "$REPO" cat-file -e "${deploy_sha}^{commit}" || return 1
  fetched_main_sha="$(git -C "$REPO" rev-parse --verify refs/remotes/origin/main)" \
    || return 1
  [[ "$fetched_main_sha" =~ ^[0-9a-f]{40}$ ]] || return 1
  git -C "$REPO" merge-base --is-ancestor "$deploy_sha" "$fetched_main_sha" \
    || return 1
  git -C "$REPO" reset --hard "$deploy_sha" || return 1
  [[ "$(git -C "$REPO" rev-parse HEAD)" == "$deploy_sha" ]]
}

if [[ "$PHASE_DEPLOY_LIBRARY_CONTEXT" == "1" ]]; then
  return 0 2>/dev/null || exit 0
fi

if [[ "${STRUCTURAL_PHASE_RECOVERY_ONLY:-0}" == "1" ]]; then
  if [[ "${STRUCTURAL_DEPLOY_LOCK_HELD:-0}" != "1" ]]; then
    exec 9>/var/lock/structural-isomorphism-deploy.lock
    flock -w 2700 9
  fi
  phase_privacy_installer_safe || {
    echo "$LOG_PREFIX CRITICAL: installed Nginx privacy installer is missing or unsafe" >&2
    exit 1
  }
  recover_phase_outer_transaction || {
    echo "$LOG_PREFIX CRITICAL: interrupted Phase transaction could not be recovered" >&2
    exit 1
  }
  exit 0
fi

validate_phase_privacy_hmac_preflight || exit 1

if [[ "${STRUCTURAL_DEPLOY_LOCK_HELD:-0}" != "1" ]]; then
  exec 9>/var/lock/structural-isomorphism-deploy.lock
  flock -w 2700 9
fi

# The auth file can change while this process waits for the shared host lock.
# Re-read the same fail-closed boundary before recovery can mutate durable state.
validate_phase_privacy_hmac_preflight || exit 1

phase_privacy_installer_safe || {
  echo "$LOG_PREFIX CRITICAL: installed Nginx privacy installer is missing or unsafe" >&2
  exit 1
}
recover_phase_outer_transaction || {
  echo "$LOG_PREFIX CRITICAL: interrupted Phase transaction could not be recovered" >&2
  exit 1
}
PREVIOUS_SHA="$(git -C "$REPO" rev-parse --verify HEAD)"
[[ "$PREVIOUS_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "$LOG_PREFIX CRITICAL: recovered checkout identity is invalid" >&2
  exit 1
}
DEPLOY_SHA="${PHASE_DEPLOY_COMMIT:-}"
[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "$LOG_PREFIX ERROR: PHASE_DEPLOY_COMMIT must be a full lowercase Git SHA" >&2
  exit 1
}
begin_phase_outer_transaction || {
  echo "$LOG_PREFIX CRITICAL: Phase deploy journal could not be created" >&2
  exit 1
}
trap 'rollback_phase "$?" "command failed"' ERR
trap 'rollback_phase 130 "interrupted by INT"' INT
trap 'rollback_phase 143 "interrupted by TERM"' TERM
trap 'rollback_phase 129 "interrupted by HUP"' HUP
trap 'rollback_phase "$?" "process exited before commit"' EXIT

echo "$LOG_PREFIX start"
phase_sync_exact_commit "$DEPLOY_SHA" || {
  echo "$LOG_PREFIX ERROR: exact requested commit could not be activated" >&2
  exit 1
}
# Revalidate after checkout and before build/restart. A failure here is inside
# the durable outer transaction, so the EXIT trap restores the prior release.
validate_phase_privacy_hmac_preflight || exit 1
echo "$LOG_PREFIX repo synced to $DEPLOY_SHA"
cd "$REPO"

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
systemctl cat phase-detector-api | grep -Fq "EnvironmentFile=$AUTH_ENV_FILE" || {
  echo "$LOG_PREFIX ERROR: phase-detector-api must load the private Phase environment" >&2
  exit 1
}
env_key_once "$WEB_DIR/.env.production" NEXT_PUBLIC_AUTH_ENABLED || {
  echo "$LOG_PREFIX ERROR: NEXT_PUBLIC_AUTH_ENABLED must occur exactly once" >&2
  exit 1
}
if env_exact_once "$WEB_DIR/.env.production" NEXT_PUBLIC_AUTH_ENABLED true; then
  AUTH_ENABLED_FOR_DEPLOY=true
  env_exact_once "$WEB_DIR/.env.production" NEXT_PUBLIC_STRUCTURAL_BETA_ORIGIN https://beta.structural.bytedance.city || {
    echo "$LOG_PREFIX ERROR: public beta callback origin must be canonical" >&2; exit 1;
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
  # The Phase Git worktree points at the single canonical beta private env
  # through an ignored symlink. Follow it so we validate the secret-bearing
  # target (0600), not the symlink inode (0777).
  beta_env_mode="$(stat -Lc '%a' "$BETA_ENV_FILE")"
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
  env_exact_once "$AUTH_ENV_FILE" AUTH_SITE_ROLE phase || {
    echo "$LOG_PREFIX ERROR: AUTH_SITE_ROLE must be phase" >&2
    exit 1
  }
  env_exact_once "$AUTH_ENV_FILE" AUTH_LINK_BASE_URL https://phase.bytedance.city || {
    echo "$LOG_PREFIX ERROR: AUTH_LINK_BASE_URL must use the canonical HTTPS origin" >&2
    exit 1
  }
  env_key_once "$AUTH_ENV_FILE" AUTH_TRUSTED_PROXY_IPS || {
    echo "$LOG_PREFIX ERROR: AUTH_TRUSTED_PROXY_IPS must be explicit" >&2
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
[[ -f "$PHASE_PRIVACY_DROPIN_SOURCE" && -f "$PHASE_NGINX_SOURCE" ]] \
  && phase_privacy_installer_safe || {
  echo "$LOG_PREFIX ERROR: tracked Phase privacy deployment files are missing" >&2
  exit 1
}

export CI=true
trap 'rollback_phase "$?" "command failed"' ERR
trap 'rollback_phase 130 "interrupted by INT"' INT
trap 'rollback_phase 143 "interrupted by TERM"' TERM
trap 'rollback_phase 129 "interrupted by HUP"' HUP

echo "$LOG_PREFIX installing Phase API dependencies"
"$API_PIP" install --disable-pip-version-check -r "$API_REQUIREMENTS"
PYTHONPATH="$REPO" "$API_PYTHON" -c \
  "from v4.product.d1_phase_detector.api.main import app; assert app.title"

cd "$WEB_DIR"
pnpm install --frozen-lockfile
pnpm build
echo "$LOG_PREFIX frontend build OK"

# Apply both privacy boundaries before restarting either service. The Nginx
# installer keeps a durable outer-transaction journal until every Phase smoke
# succeeds, so any later failure restores both the vhost and systemd drop-in.
STRUCTURAL_NGINX_TRANSACTION_ACTION=prepare \
  bash "$NGINX_PRIVACY_INSTALLER" \
    "$PHASE_NGINX_SOURCE" \
    "$PHASE_NGINX_TARGET" \
    phase.bytedance.city \
    structural_phase_privacy
PHASE_NGINX_PREPARED=1
phase_outer_mark nginx_prepared
install_phase_privacy_dropin
phase_outer_mark dropin_installed
systemctl restart phase-detector-api phase-detector-web
phase_outer_mark services_restarted
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
    api_state="$(systemctl is-active phase-detector-api 2>/dev/null || true)"
    web_state="$(systemctl is-active phase-detector-web 2>/dev/null || true)"
    echo "$LOG_PREFIX ERROR: service state api=${api_state:-unknown} web=${web_state:-unknown}" >&2
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
curl -fsS --max-time 10 \
  --resolve phase.bytedance.city:443:127.0.0.1 \
  -D - -o /dev/null https://phase.bytedance.city/ \
  | tr -d '\r' \
  | grep -Fqi 'Referrer-Policy: no-referrer'
systemctl show phase-detector-api --property=ExecStart --value \
  | grep -Fq -- '--no-access-log'
phase_outer_mark smoke_passed
commit_phase_privacy
phase_outer_mark nginx_committed
phase_outer_clear
DEPLOY_COMPLETE=1
trap - ERR INT TERM HUP EXIT
echo "$LOG_PREFIX deploy complete"
