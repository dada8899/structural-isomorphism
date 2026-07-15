#!/bin/bash -p
# Forced-command SSH dispatcher for beta deployments.
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset BASH_ENV ENV CDPATH GLOBIGNORE

[[ "$#" -eq 0 ]] || {
  echo "[deploy-dispatcher] ERROR: positional arguments are forbidden" >&2
  exit 2
}

SCRIPT_PATH="${BASH_SOURCE[0]}"
[[ "$SCRIPT_PATH" == /* && "$SCRIPT_PATH" == */* ]] || {
  echo "[deploy-dispatcher] ERROR: dispatcher must use an absolute path" >&2
  exit 1
}
SCRIPT_DIR="${SCRIPT_PATH%/*}"
[[ -d "$SCRIPT_DIR" && ! -L "$SCRIPT_DIR" ]] || {
  echo "[deploy-dispatcher] ERROR: dispatcher directory is unsafe" >&2
  exit 1
}

ORIGINAL_COMMAND="${SSH_ORIGINAL_COMMAND:-}"
if [[ "$ORIGINAL_COMMAND" =~ ^beta-backend\ ([0-9a-f]{40})$ ]]; then
  ENTRYPOINT="$SCRIPT_DIR/deploy-beta-backend.sh"
  DEPLOY_SHA="${BASH_REMATCH[1]}"
elif [[ "$ORIGINAL_COMMAND" =~ ^phase-deploy\ ([0-9a-f]{40})$ ]]; then
  ENTRYPOINT="$SCRIPT_DIR/deploy-phase-detector-entrypoint.sh"
  DEPLOY_SHA="${BASH_REMATCH[1]}"
else
  echo "[deploy-dispatcher] ERROR: command is not an allowed deployment route" >&2
  exit 2
fi
[[ -f "$ENTRYPOINT" && ! -L "$ENTRYPOINT" && -x "$ENTRYPOINT" ]] || {
  echo "[deploy-dispatcher] ERROR: selected entrypoint is missing or unsafe" >&2
  exit 1
}

exec /usr/bin/env -i \
  PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  HOME=/root \
  "$ENTRYPOINT" "$DEPLOY_SHA"
