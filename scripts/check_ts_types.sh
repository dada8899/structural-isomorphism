#!/usr/bin/env bash
# Regenerate API TypeScript into a temporary file and compare it exactly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMITTED="${REPO_ROOT}/web/phase-detector/lib/api-types.ts"
TMP_OUTPUT="$(mktemp -t structural-api-types.XXXXXX)"
trap 'rm -f "$TMP_OUTPUT"' EXIT

cd "$REPO_ROOT"
OUT="$TMP_OUTPUT" bash scripts/gen_ts_types.sh

if ! cmp -s "$COMMITTED" "$TMP_OUTPUT"; then
  echo "[check_ts_types] api-types.ts is stale; regenerate and commit it" >&2
  diff -u "$COMMITTED" "$TMP_OUTPUT" || true
  exit 1
fi

echo "[check_ts_types] committed api-types.ts is reproducible"
