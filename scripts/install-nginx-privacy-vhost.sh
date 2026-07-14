#!/usr/bin/env bash
# Install one canonical privacy vhost as a recoverable transaction.
set -Eeuo pipefail

umask 077
export LC_ALL=C

SOURCE="${1:-}"
TARGET="${2:-}"
DOMAIN="${3:-}"
FORMAT="${4:-}"
TEST_ROOT="${STRUCTURAL_NGINX_TEST_ROOT:-}"
ACTION="${STRUCTURAL_NGINX_TRANSACTION_ACTION:-install}"
LOCK_TIMEOUT_SECONDS="${STRUCTURAL_NGINX_LOCK_TIMEOUT_SECONDS:-30}"
SOURCE_INPUT="$SOURCE"
SOURCE_SNAPSHOT=""
BACKUP_TEMP=""
LOCK_FALLBACK_DIR=""
LOCK_FALLBACK_OWNED=0

die() {
  echo "[nginx-privacy] ERROR: $1" >&2
  exit 1
}

has_unsafe_path_segment() {
  case "$1" in
    *$'\n'*|*$'\r'*|*/../*|*/..|../*|..|*/./*|*/.|./*|.) return 0 ;;
    *) return 1 ;;
  esac
}

file_mode() {
  if stat -c '%a' "$1" >/dev/null 2>&1; then
    stat -c '%a' "$1"
  else
    stat -f '%Lp' "$1"
  fi
}

[[ -n "$SOURCE" && -n "$TARGET" && -n "$DOMAIN" && -n "$FORMAT" ]] \
  || die "source, target, domain, and format are required"
[[ "$SOURCE" == /* && "$TARGET" == /* ]] \
  || die "source and target must be absolute paths"
has_unsafe_path_segment "$SOURCE" && die "source path is not canonical"
has_unsafe_path_segment "$TARGET" && die "target path is not canonical"
[[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$ ]] \
  || die "domain is outside the allowlist"
[[ "$FORMAT" =~ ^[a-z][a-z0-9_]{0,63}$ ]] \
  || die "log format name is outside the allowlist"
[[ "$ACTION" == "install" || "$ACTION" == "prepare" \
   || "$ACTION" == "commit" || "$ACTION" == "rollback" ]] \
  || die "transaction action is outside the allowlist"
[[ "$LOCK_TIMEOUT_SECONDS" =~ ^[0-9]{1,4}$ ]] \
  || die "lock timeout is outside the allowlist"

if [[ -n "$TEST_ROOT" ]]; then
  [[ "$TEST_ROOT" == /* ]] || die "test root must be absolute"
  has_unsafe_path_segment "$TEST_ROOT" && die "test root is not canonical"
  [[ -d "$TEST_ROOT" && ! -L "$TEST_ROOT" ]] || die "test root must be a direct directory"
  TEST_ROOT_REAL="$(cd -P "$TEST_ROOT" && pwd)"
  EXPECTED_CONF_DIR="$TEST_ROOT_REAL/etc/nginx/conf.d"
  STATE_DIR="$TEST_ROOT_REAL/var/lib/structural-isomorphism/nginx-privacy"
else
  [[ "$EUID" -eq 0 ]] || die "installation must run as root"
  EXPECTED_CONF_DIR="/etc/nginx/conf.d"
  STATE_DIR="/var/lib/structural-isomorphism/nginx-privacy"
fi

[[ -d "$EXPECTED_CONF_DIR" && ! -L "$EXPECTED_CONF_DIR" ]] \
  || die "conf.d must be a direct directory"
EXPECTED_CONF_REAL="$(cd -P "$EXPECTED_CONF_DIR" && pwd)"
TARGET_DIR="$(dirname "$TARGET")"
TARGET_BASE="$(basename "$TARGET")"
[[ "$TARGET_BASE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*\.conf$ ]] \
  || die "target filename is outside the allowlist"
[[ -d "$TARGET_DIR" && ! -L "$TARGET_DIR" ]] || die "target parent is unsafe"
TARGET_DIR_REAL="$(cd -P "$TARGET_DIR" && pwd)"
[[ "$TARGET_DIR_REAL" == "$EXPECTED_CONF_REAL" \
   && "$TARGET" == "$EXPECTED_CONF_REAL/$TARGET_BASE" ]] \
  || die "target must be a direct conf.d regular file"
if [[ -e "$TARGET" || -L "$TARGET" ]]; then
  [[ -f "$TARGET" && ! -L "$TARGET" ]] || die "target must not be a symlink or special file"
fi

SOURCE_DIR="$(dirname "$SOURCE")"
SOURCE_BASE="$(basename "$SOURCE")"
[[ -d "$SOURCE_DIR" && ! -L "$SOURCE_DIR" ]] || die "source parent is unsafe"
SOURCE_DIR_REAL="$(cd -P "$SOURCE_DIR" && pwd)"
[[ "$SOURCE" == "$SOURCE_DIR_REAL/$SOURCE_BASE" \
   && -f "$SOURCE" && ! -L "$SOURCE" ]] \
  || die "source must be a direct regular file"
[[ "$SOURCE" != "$TARGET" ]] || die "source and target must differ"

mkdir -p "$STATE_DIR"
[[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die "transaction state directory is unsafe"
STATE_PARENT="$(dirname "$STATE_DIR")"
STATE_REAL="$(cd -P "$STATE_DIR" && pwd)"
[[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] \
  || die "transaction state parent is unsafe"
STATE_PARENT_REAL="$(cd -P "$STATE_PARENT" && pwd)"
[[ "$STATE_REAL" == "$STATE_PARENT_REAL/$(basename "$STATE_DIR")" ]] \
  || die "transaction state directory escaped its parent"
chmod 700 "$STATE_DIR"

file_identity() {
  if stat -Lc '%i:%f:%s:%Y' "$1" >/dev/null 2>&1; then
    stat -Lc '%i:%f:%s:%Y' "$1"
  else
    stat -L -f '%i:%p:%z:%m' "$1"
  fi
}

directory_identity() {
  if stat -Lc '%i:%f' "$1" >/dev/null 2>&1; then
    stat -Lc '%i:%f' "$1"
  else
    stat -L -f '%i:%p' "$1"
  fi
}

file_digest() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

EXPECTED_CONF_IDENTITY="$(directory_identity "$EXPECTED_CONF_DIR")"
TARGET_DIR_IDENTITY="$(directory_identity "$TARGET_DIR")"
STATE_PARENT_IDENTITY="$(directory_identity "$STATE_PARENT")"
STATE_DIR_IDENTITY="$(directory_identity "$STATE_DIR")"

assert_path_anchors() {
  [[ -d "$EXPECTED_CONF_DIR" && ! -L "$EXPECTED_CONF_DIR" \
     && "$(cd -P "$EXPECTED_CONF_DIR" && pwd)" == "$EXPECTED_CONF_REAL" \
     && "$(directory_identity "$EXPECTED_CONF_DIR")" == "$EXPECTED_CONF_IDENTITY" ]] \
    || return 1
  [[ -d "$TARGET_DIR" && ! -L "$TARGET_DIR" \
     && "$(cd -P "$TARGET_DIR" && pwd)" == "$TARGET_DIR_REAL" \
     && "$(directory_identity "$TARGET_DIR")" == "$TARGET_DIR_IDENTITY" \
     && "$TARGET" == "$TARGET_DIR_REAL/$TARGET_BASE" ]] || return 1
  [[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" \
     && "$(cd -P "$STATE_PARENT" && pwd)" == "$STATE_PARENT_REAL" \
     && "$(directory_identity "$STATE_PARENT")" == "$STATE_PARENT_IDENTITY" ]] \
    || return 1
  [[ -d "$STATE_DIR" && ! -L "$STATE_DIR" \
     && "$(cd -P "$STATE_DIR" && pwd)" == "$STATE_REAL" \
     && "$(directory_identity "$STATE_DIR")" == "$STATE_DIR_IDENTITY" ]] || return 1
}

release_transaction_lock() {
  if [[ "$LOCK_FALLBACK_OWNED" == "1" ]]; then
    if assert_path_anchors \
       && [[ -f "$LOCK_FALLBACK_DIR/pid" && ! -L "$LOCK_FALLBACK_DIR/pid" \
       && "$(tr -d ' ' <"$LOCK_FALLBACK_DIR/pid")" == "$$" ]]; then
      rm -f "$LOCK_FALLBACK_DIR/pid"
      rmdir "$LOCK_FALLBACK_DIR" 2>/dev/null || true
    fi
    LOCK_FALLBACK_OWNED=0
  fi
  exec 7>&- 2>/dev/null || true
}

acquire_transaction_lock() {
  local lock_root="$STATE_DIR/locks" lock_file start now holder
  assert_path_anchors || return 1
  mkdir -p "$lock_root"
  [[ -d "$lock_root" && ! -L "$lock_root" ]] || return 1
  chmod 700 "$lock_root"
  lock_file="$lock_root/$FORMAT.lock"
  if command -v flock >/dev/null 2>&1; then
    if [[ -e "$lock_file" || -L "$lock_file" ]]; then
      [[ -f "$lock_file" && ! -L "$lock_file" ]] || return 1
    fi
    exec 7>"$lock_file"
    [[ -f "$lock_file" && ! -L "$lock_file" ]] || return 1
    flock -w "$LOCK_TIMEOUT_SECONDS" 7 || return 1
    return 0
  fi

  LOCK_FALLBACK_DIR="$lock_file.d"
  start="$(date +%s)"
  while ! mkdir "$LOCK_FALLBACK_DIR" 2>/dev/null; do
    [[ -d "$LOCK_FALLBACK_DIR" && ! -L "$LOCK_FALLBACK_DIR" ]] || return 1
    holder=""
    if [[ -f "$LOCK_FALLBACK_DIR/pid" && ! -L "$LOCK_FALLBACK_DIR/pid" ]]; then
      holder="$(tr -d ' ' <"$LOCK_FALLBACK_DIR/pid")"
    fi
    if [[ "$holder" =~ ^[1-9][0-9]*$ ]] && ! kill -0 "$holder" 2>/dev/null; then
      rm -f "$LOCK_FALLBACK_DIR/pid"
      rmdir "$LOCK_FALLBACK_DIR" 2>/dev/null || return 1
      continue
    fi
    now="$(date +%s)"
    (( now - start < LOCK_TIMEOUT_SECONDS )) || return 1
    sleep 0.1
  done
  printf '%s\n' "$$" >"$LOCK_FALLBACK_DIR/pid"
  chmod 600 "$LOCK_FALLBACK_DIR/pid"
  LOCK_FALLBACK_OWNED=1
}

run_test_hook() {
  local hook=""
  [[ -n "$TEST_ROOT" ]] || return 0
  case "$1" in
    after_snapshot) hook="${STRUCTURAL_NGINX_TEST_AFTER_SNAPSHOT_HOOK:-}" ;;
    before_target_install) hook="${STRUCTURAL_NGINX_TEST_BEFORE_TARGET_INSTALL_HOOK:-}" ;;
    *) return 1 ;;
  esac
  [[ -n "$hook" ]] || return 0
  [[ "$hook" == /* && -f "$hook" && ! -L "$hook" && -x "$hook" ]] || return 1
  [[ "$(cd -P "$(dirname "$hook")" && pwd)" == "$TEST_ROOT_REAL"* ]] || return 1
  "$hook"
}

cleanup_ephemeral() {
  if [[ -n "${EFFECTIVE_FILE:-}" ]]; then
    assert_path_anchors && rm -f "$EFFECTIVE_FILE" || true
    EFFECTIVE_FILE=""
  fi
  if [[ -n "${SOURCE_SNAPSHOT:-}" ]]; then
    assert_path_anchors && rm -f "$SOURCE_SNAPSHOT" || true
    SOURCE_SNAPSHOT=""
  fi
  if [[ -n "${BACKUP_TEMP:-}" ]]; then
    assert_path_anchors && rm -f "$BACKUP_TEMP" || true
    BACKUP_TEMP=""
  fi
}

acquire_transaction_lock || die "another privacy vhost transaction is active"
trap 'cleanup_ephemeral; release_transaction_lock' EXIT

JOURNAL="$STATE_DIR/$FORMAT.journal"
BACKUP="$STATE_DIR/$FORMAT.backup"
EFFECTIVE_FILE=""
ACTIVE=0

server_metrics() {
  awk -v domain="$DOMAIN" -v format="$FORMAT" '
    function trim(value) {
      sub(/^[ \t]+/, "", value)
      sub(/[ \t]+$/, "", value)
      return value
    }
    function brace_delta(value, opened, closed, copy) {
      copy = value
      opened = gsub(/\{/, "{", copy)
      copy = value
      closed = gsub(/\}/, "}", copy)
      return opened - closed
    }
    function inspect(    rows, n, i, line, owns, access, header, hidden,
                        errors, proxies, request_ids) {
      total += 1
      n = split(block, rows, "\n")
      owns = access = header = hidden = errors = proxies = request_ids = 0
      for (i = 1; i <= n; i += 1) {
        line = trim(rows[i])
        if (line == "server_name " domain ";") owns = 1
      }
      if (!owns) return
      owned += 1
      for (i = 1; i <= n; i += 1) {
        line = trim(rows[i])
        if (line == "access_log /var/log/nginx/access.log " format ";") access += 1
        if (line == "add_header Referrer-Policy \"no-referrer\" always;") header += 1
        if (line == "proxy_hide_header Referrer-Policy;") hidden += 1
        if (line == "error_log /dev/null crit;") errors += 1
        if (line ~ /^proxy_pass[ \t]/) proxies += 1
        if (line == "proxy_set_header X-Request-ID $request_id;") request_ids += 1
      }
      if (access != 1 || header != 1 || hidden != 1 || errors != 1 \
          || proxies != request_ids) bad += 1
    }
    /^[ \t]*server[ \t]*\{/ && !inside {
      inside = 1
      depth = brace_delta($0)
      block = $0 "\n"
      if (depth == 0) { inspect(); inside = 0; block = "" }
      next
    }
    inside {
      block = block $0 "\n"
      depth += brace_delta($0)
      if (depth == 0) { inspect(); inside = 0; block = "" }
    }
    END {
      if (inside) bad += 1
      printf "%d|%d|%d\n", total, owned, bad
    }
  ' "$1"
}

validate_config() {
  local path="$1" scope="$2" expected_owned="${3:-}"
  local format_count format_body variables expected metrics total owned bad
  format_count="$(grep -Ec "^[[:space:]]*log_format[[:space:]]+$FORMAT([[:space:]]|$)" "$path" || true)"
  [[ "$format_count" == "1" ]] || return 1
  format_body="$(
    awk -v name="$FORMAT" '
      $1 == "log_format" && $2 == name { capture = 1 }
      capture { print }
      capture && /;/ { exit }
    ' "$path"
  )"
  [[ -n "$format_body" && "$format_body" == *';'* ]] || return 1
  variables="$(
    printf '%s\n' "$format_body" \
      | grep -oE '\$[A-Za-z_][A-Za-z0-9_]*' \
      | sort -u || true
  )"
  expected='$body_bytes_sent
$request_id
$request_method
$request_time
$status
$upstream_response_time'
  [[ "$variables" == "$expected" ]] || return 1

  metrics="$(server_metrics "$path")" || return 1
  total="${metrics%%|*}"
  metrics="${metrics#*|}"
  owned="${metrics%%|*}"
  bad="${metrics##*|}"
  [[ "$owned" -gt 0 && "$bad" -eq 0 ]] || return 1
  if [[ "$scope" == "source" ]]; then
    [[ "$total" -eq "$owned" ]] || return 1
  fi
  if [[ -n "$expected_owned" ]]; then
    [[ "$owned" -eq "$expected_owned" ]] || return 1
  fi
  printf '%s' "$owned"
}

snapshot_source() {
  local source_identity fd_identity snapshot_temp
  assert_path_anchors || return 1
  [[ -f "$SOURCE_INPUT" && ! -L "$SOURCE_INPUT" ]] || return 1
  source_identity="$(file_identity "$SOURCE_INPUT")" || return 1
  exec 8<"$SOURCE_INPUT" || return 1
  [[ -f /dev/fd/8 ]] || return 1
  fd_identity="$(file_identity /dev/fd/8)" || return 1
  [[ "$fd_identity" == "$source_identity" ]] || return 1
  [[ -f "$SOURCE_INPUT" && ! -L "$SOURCE_INPUT" \
     && "$(file_identity "$SOURCE_INPUT")" == "$source_identity" ]] || return 1

  SOURCE_SNAPSHOT="$STATE_DIR/$FORMAT.source"
  if [[ -e "$SOURCE_SNAPSHOT" || -L "$SOURCE_SNAPSHOT" ]]; then
    [[ -f "$SOURCE_SNAPSHOT" && ! -L "$SOURCE_SNAPSHOT" ]] || return 1
    rm -f "$SOURCE_SNAPSHOT" || return 1
  fi
  snapshot_temp="$SOURCE_SNAPSHOT.tmp.$$"
  rm -f "$snapshot_temp"
  cp /dev/fd/8 "$snapshot_temp" || return 1
  exec 8<&-
  chmod 600 "$snapshot_temp" || return 1
  assert_path_anchors || return 1
  mv "$snapshot_temp" "$SOURCE_SNAPSHOT" || return 1
  [[ -f "$SOURCE_SNAPSHOT" && ! -L "$SOURCE_SNAPSHOT" \
     && "$(file_mode "$SOURCE_SNAPSHOT")" == "600" ]] || return 1
}

snapshot_source || die "canonical source snapshot could not be secured"
run_test_hook after_snapshot || die "source snapshot fault hook failed"
SOURCE_SERVER_COUNT="$(validate_config "$SOURCE_SNAPSHOT" source)" \
  || die "canonical source failed the privacy contract"
SOURCE_SHA256="$(file_digest "$SOURCE_SNAPSHOT")"
[[ "$SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]] \
  || die "canonical source digest is invalid"

write_journal() {
  local had_target="$1" target_mode="$2" source_sha256="$3" temp="$JOURNAL.tmp.$$"
  assert_path_anchors || return 1
  [[ "$source_sha256" =~ ^[0-9a-f]{64}$ ]] || return 1
  rm -f "$temp"
  printf '%s\n' \
    'version=2' \
    "target=$TARGET" \
    "had_target=$had_target" \
    "target_mode=$target_mode" \
    "source_sha256=$source_sha256" \
    "backup=$BACKUP" >"$temp"
  chmod 600 "$temp"
  assert_path_anchors || return 1
  mv "$temp" "$JOURNAL"
  [[ -f "$JOURNAL" && ! -L "$JOURNAL" ]] || return 1
}

read_journal() {
  [[ -f "$JOURNAL" && ! -L "$JOURNAL" ]] || return 1
  [[ "$(file_mode "$JOURNAL")" == "600" ]] || return 1
  [[ "$(wc -l <"$JOURNAL" | tr -d ' ')" == "6" ]] || return 1
  grep -Fqx 'version=2' "$JOURNAL" || return 1
  grep -Fqx "target=$TARGET" "$JOURNAL" || return 1
  grep -Fqx "backup=$BACKUP" "$JOURNAL" || return 1
  JOURNAL_HAD="$(sed -n 's/^had_target=//p' "$JOURNAL")"
  JOURNAL_MODE="$(sed -n 's/^target_mode=//p' "$JOURNAL")"
  JOURNAL_SOURCE_SHA256="$(sed -n 's/^source_sha256=//p' "$JOURNAL")"
  [[ "$JOURNAL_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]] || return 1
  [[ "$JOURNAL_HAD" == "0" || "$JOURNAL_HAD" == "1" ]] || return 1
  if [[ "$JOURNAL_HAD" == "1" ]]; then
    [[ "$JOURNAL_MODE" =~ ^[0-7]{3,4}$ ]] || return 1
  else
    [[ "$JOURNAL_MODE" == "0" ]] || return 1
  fi
}

clear_transaction_state() {
  # Journal removal is the commit marker. A backup without a journal is an
  # inert orphan and is deleted on the next invocation.
  assert_path_anchors || return 1
  rm -f "$JOURNAL" || return 1
  assert_path_anchors || return 1
  rm -f "$BACKUP" || return 1
}

recover_transaction() {
  assert_path_anchors || return 1
  if [[ ! -e "$JOURNAL" && ! -L "$JOURNAL" ]]; then
    if [[ -e "$BACKUP" || -L "$BACKUP" ]]; then
      [[ -f "$BACKUP" && ! -L "$BACKUP" ]] || return 1
      rm -f "$BACKUP" || return 1
    fi
    return 0
  fi
  read_journal || return 1
  if [[ "$JOURNAL_HAD" == "1" ]]; then
    [[ -f "$BACKUP" && ! -L "$BACKUP" \
       && "$(file_mode "$BACKUP")" == "600" ]] || return 1
    assert_path_anchors || return 1
    install -m "$JOURNAL_MODE" "$BACKUP" "$TARGET" || return 1
    assert_path_anchors || return 1
    [[ -f "$TARGET" && ! -L "$TARGET" ]] || return 1
  else
    assert_path_anchors || return 1
    rm -f "$TARGET" || return 1
  fi
  nginx -t >/dev/null 2>&1 || return 1
  systemctl reload nginx >/dev/null 2>&1 || return 1
  clear_transaction_state || return 1
}

rollback_active() {
  local code="$1" reason="$2"
  trap - ERR INT TERM HUP EXIT
  set +e
  cleanup_ephemeral
  if [[ "$ACTIVE" == "1" ]]; then
    if recover_transaction; then
      ACTIVE=0
    else
      echo "[nginx-privacy] CRITICAL: rollback failed; journal and backup retained" >&2
    fi
  fi
  echo "[nginx-privacy] ERROR: $reason" >&2
  release_transaction_lock
  exit "$code"
}

if [[ "$ACTION" == "commit" ]]; then
  assert_path_anchors || die "prepared transaction paths changed"
  read_journal || die "prepared transaction evidence is invalid"
  [[ -f "$TARGET" && ! -L "$TARGET" ]] \
    || die "prepared target is unavailable"
  [[ "$(file_digest "$TARGET")" == "$JOURNAL_SOURCE_SHA256" ]] \
    || die "prepared target no longer matches validated source"
  validate_config "$TARGET" source >/dev/null \
    || die "prepared target no longer satisfies the privacy contract"
  nginx -t >/dev/null 2>&1 || die "prepared target no longer passes nginx validation"
  clear_transaction_state || die "prepared transaction could not be committed"
  cleanup_ephemeral
  echo "[nginx-privacy] committed $DOMAIN"
  exit 0
fi

if [[ "$ACTION" == "rollback" ]]; then
  recover_transaction \
    || die "prepared transaction could not be rolled back; evidence retained"
  cleanup_ephemeral
  echo "[nginx-privacy] rolled back $DOMAIN"
  exit 0
fi

if [[ -e "$JOURNAL" || -L "$JOURNAL" ]]; then
  if [[ "$ACTION" == "prepare" ]]; then
    die "a prepared transaction already exists"
  fi
  recover_transaction \
    || die "an earlier transaction could not be recovered; evidence retained"
else
  recover_transaction \
    || die "orphan transaction state could not be cleared"
fi

HAD_TARGET=0
TARGET_MODE=0
assert_path_anchors || die "transaction paths changed before backup"
if [[ -f "$TARGET" ]]; then
  HAD_TARGET=1
  TARGET_MODE="$(file_mode "$TARGET")"
  [[ "$TARGET_MODE" =~ ^[0-7]{3,4}$ ]] || die "target mode is invalid"
  TARGET_IDENTITY="$(file_identity "$TARGET")"
  BACKUP_TEMP="$BACKUP.tmp.$$"
  rm -f "$BACKUP_TEMP"
  cp "$TARGET" "$BACKUP_TEMP"
  [[ -f "$TARGET" && ! -L "$TARGET" \
     && "$(file_identity "$TARGET")" == "$TARGET_IDENTITY" \
     && "$(cd -P "$TARGET_DIR" && pwd)" == "$TARGET_DIR_REAL" ]] \
    || die "target changed while the rollback snapshot was created"
  cmp -s "$TARGET" "$BACKUP_TEMP" \
    || die "rollback snapshot does not match the target"
  chmod 600 "$BACKUP_TEMP"
  assert_path_anchors || die "transaction paths changed before backup commit"
  mv "$BACKUP_TEMP" "$BACKUP"
  BACKUP_TEMP=""
fi
write_journal "$HAD_TARGET" "$TARGET_MODE" "$SOURCE_SHA256"
ACTIVE=1

trap 'rollback_active "$?" "transaction failed"' ERR
trap 'rollback_active 130 "transaction interrupted by INT"' INT
trap 'rollback_active 143 "transaction interrupted by TERM"' TERM
trap 'rollback_active 129 "transaction interrupted by HUP"' HUP
trap 'cleanup_ephemeral; release_transaction_lock' EXIT

run_test_hook before_target_install
assert_path_anchors
install -m 0644 "$SOURCE_SNAPSHOT" "$TARGET"
assert_path_anchors
[[ -f "$TARGET" && ! -L "$TARGET" ]]
cmp -s "$SOURCE_SNAPSHOT" "$TARGET"
nginx -t >/dev/null 2>&1
systemctl reload nginx >/dev/null 2>&1

EFFECTIVE_FILE="$(mktemp "$STATE_DIR/$FORMAT.effective.XXXXXX")"
chmod 600 "$EFFECTIVE_FILE"
[[ "$(file_mode "$EFFECTIVE_FILE")" == "600" ]]
# Run exactly once and never print its potentially sensitive output.
NGINX_PRIVACY_EFFECTIVE_FILE="$EFFECTIVE_FILE" \
  nginx -T >"$EFFECTIVE_FILE" 2>/dev/null
validate_config "$EFFECTIVE_FILE" effective "$SOURCE_SERVER_COUNT" >/dev/null

if [[ "$ACTION" == "prepare" ]]; then
  ACTIVE=0
  cleanup_ephemeral
  trap - ERR INT TERM HUP EXIT
  release_transaction_lock
  echo "[nginx-privacy] prepared and verified $DOMAIN"
  exit 0
fi

# Commit by removing the journal first. A crash after this point may leave an
# inert backup, which the next invocation safely removes without rollback.
assert_path_anchors
rm -f "$JOURNAL"
ACTIVE=0
assert_path_anchors
rm -f "$BACKUP"
cleanup_ephemeral
trap - ERR INT TERM HUP EXIT
release_transaction_lock
echo "[nginx-privacy] installed and verified $DOMAIN"
