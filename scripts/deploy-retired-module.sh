#!/usr/bin/env bash

# Exact, reversible cleanup for a tracked module removed from the release.
# This helper is sourced by deploy-vps.sh so rollback works even when the
# manual deployment path has no PREVIOUS_SHA.

RETIRED_TRACKED_RELATIVE_PATH="web/backend/services/verified_isomorphisms.py"
RETIRED_TRACKED_BACKUP=""
RETIRED_TRACKED_CAPTURED=0
RETIRED_TRACKED_WAS_PRESENT=0
RETIRED_TRACKED_REMOVED=0

retired_module_realpath() {
  local path="$1" strict="$2" python="${RUNTIME_PYTHON:-python3}"
  "$python" - "$path" "$strict" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
strict = sys.argv[2] == "1"
print(path.resolve(strict=strict))
PY
}

retired_module_validate_runtime_root() {
  local resolved
  [[ -n "${RUNTIME_ROOT:-}" && "$RUNTIME_ROOT" = /* \
    && -d "$RUNTIME_ROOT" && ! -L "$RUNTIME_ROOT" ]] || return 1
  resolved="$(retired_module_realpath "$RUNTIME_ROOT" 1)" || return 1
  [[ "$resolved" == "$RUNTIME_ROOT" ]] || return 1
}

retired_module_validate_target() {
  local target="$1" current="$1/$RETIRED_TRACKED_RELATIVE_PATH"
  local resolved_target resolved_current
  [[ "$target" = /* && -d "$target" && ! -L "$target" ]] || return 1
  resolved_target="$(retired_module_realpath "$target" 1)" || return 1
  [[ "$resolved_target" == "$target" ]] || return 1
  resolved_current="$(retired_module_realpath "$current" 0)" || return 1
  case "$resolved_current" in
    "$target"/*) ;;
    *) return 1 ;;
  esac
}

retired_module_validate_backup() {
  local resolved
  [[ -n "$RETIRED_TRACKED_BACKUP" \
    && -f "$RETIRED_TRACKED_BACKUP" \
    && ! -L "$RETIRED_TRACKED_BACKUP" ]] || return 1
  case "$RETIRED_TRACKED_BACKUP" in
    "$RUNTIME_ROOT"/.rollback-retired.*) ;;
    *) return 1 ;;
  esac
  resolved="$(retired_module_realpath "$RETIRED_TRACKED_BACKUP" 1)" || return 1
  case "$resolved" in
    "$RUNTIME_ROOT"/.rollback-retired.*) ;;
    *) return 1 ;;
  esac
}

retired_module_cleanup() {
  if [[ -n "$RETIRED_TRACKED_BACKUP" ]]; then
    retired_module_validate_runtime_root || return 1
    retired_module_validate_backup || return 1
    rm -f -- "$RETIRED_TRACKED_BACKUP"
  fi
  RETIRED_TRACKED_BACKUP=""
  RETIRED_TRACKED_CAPTURED=0
  RETIRED_TRACKED_WAS_PRESENT=0
  RETIRED_TRACKED_REMOVED=0
}

retired_module_capture() {
  local target="$1"
  local current="$target/$RETIRED_TRACKED_RELATIVE_PATH"

  retired_module_cleanup || return 1
  retired_module_validate_runtime_root || return 1
  retired_module_validate_target "$target" || return 1
  if [[ ! -e "$current" && ! -L "$current" ]]; then
    RETIRED_TRACKED_CAPTURED=1
    return 0
  fi
  [[ -f "$current" && ! -L "$current" ]] || return 1

  RETIRED_TRACKED_BACKUP="$(mktemp "$RUNTIME_ROOT/.rollback-retired.XXXXXX")" \
    || return 1
  retired_module_validate_backup || return 1
  if ! cp -a -- "$current" "$RETIRED_TRACKED_BACKUP"; then
    retired_module_cleanup
    return 1
  fi
  cmp -s -- "$current" "$RETIRED_TRACKED_BACKUP" || {
    retired_module_cleanup
    return 1
  }
  RETIRED_TRACKED_WAS_PRESENT=1
  RETIRED_TRACKED_CAPTURED=1
}

retired_module_remove() {
  local target="$1" current="$1/$RETIRED_TRACKED_RELATIVE_PATH"
  [[ "$RETIRED_TRACKED_CAPTURED" == "1" ]] || return 1
  retired_module_validate_target "$target" || return 1
  if [[ "$RETIRED_TRACKED_WAS_PRESENT" == "0" ]]; then
    [[ ! -e "$current" && ! -L "$current" ]] || return 1
    return 0
  fi
  retired_module_validate_backup || return 1
  [[ -f "$current" && ! -L "$current" ]] || return 1
  cmp -s -- "$current" "$RETIRED_TRACKED_BACKUP" || return 1
  RETIRED_TRACKED_REMOVED=1
  rm -f -- "$current"
}

retired_module_backup_and_remove() {
  local target="$1"
  retired_module_capture "$target" || return 1
  retired_module_remove "$target"
}

retired_module_restore() {
  local target="$1"
  local current="$target/$RETIRED_TRACKED_RELATIVE_PATH"

  [[ "$RETIRED_TRACKED_CAPTURED" == "1" ]] || return 0
  retired_module_validate_target "$target" || return 1
  if [[ "$RETIRED_TRACKED_WAS_PRESENT" == "1" ]]; then
    retired_module_validate_backup || return 1
    mkdir -p -- "$(dirname "$current")" || return 1
    rm -f -- "$current" || return 1
    cp -a -- "$RETIRED_TRACKED_BACKUP" "$current" || return 1
    cmp -s -- "$RETIRED_TRACKED_BACKUP" "$current" || return 1
  elif [[ "$RETIRED_TRACKED_REMOVED" == "1" ]]; then
    return 1
  fi
  retired_module_cleanup
}
