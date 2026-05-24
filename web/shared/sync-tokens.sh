#!/usr/bin/env bash
# Sync the canonical web/shared/tokens.css to the two site-local mirrors.
# Run this after editing tokens.css.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/shared/tokens.css"
TARGETS=(
  "$ROOT/frontend/assets/css/shared-tokens.css"
  "$ROOT/phase-detector/app/shared-tokens.css"
)

if [[ ! -f "$SRC" ]]; then
  echo "error: $SRC not found" >&2
  exit 1
fi

for t in "${TARGETS[@]}"; do
  cp "$SRC" "$t"
  echo "synced → $t"
done

# Verify the mirrors are byte-identical
for t in "${TARGETS[@]}"; do
  if ! cmp -s "$SRC" "$t"; then
    echo "error: $t diverges from $SRC after copy" >&2
    exit 1
  fi
done

echo "ok: 2 mirrors in sync with $SRC"
