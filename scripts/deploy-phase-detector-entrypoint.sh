#!/bin/bash -p
# Exact-SHA forced-command entrypoint for the installed Phase deploy engine.
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset BASH_ENV ENV CDPATH GLOBIGNORE

DEPLOY_SHA="${1:-}"
[[ "$#" -eq 1 && "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "[phase-dispatch] ERROR: expected one full lowercase Git SHA" >&2
  exit 2
}

SCRIPT_PATH="${BASH_SOURCE[0]}"
[[ "$SCRIPT_PATH" == /* && "$SCRIPT_PATH" == */* ]] || {
  echo "[phase-dispatch] ERROR: entrypoint must use an absolute path" >&2
  exit 1
}
SCRIPT_DIR="${SCRIPT_PATH%/*}"
ENGINE="$SCRIPT_DIR/deploy-phase-detector-vps.sh"
[[ -d "$SCRIPT_DIR" && ! -L "$SCRIPT_DIR" \
  && -f "$ENGINE" && ! -L "$ENGINE" && -x "$ENGINE" ]] || {
  echo "[phase-dispatch] ERROR: installed Phase deploy engine is missing or unsafe" >&2
  exit 1
}

# The installed engine owns locking, interrupted-transaction recovery,
# previous-SHA capture, durable intent, and only then the exact Git reset.
exec /usr/bin/env -i \
  PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  HOME=/root \
  PHASE_DEPLOY_COMMIT="$DEPLOY_SHA" \
  /bin/bash "$ENGINE"
