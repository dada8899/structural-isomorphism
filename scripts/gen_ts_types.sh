#!/usr/bin/env bash
# Regenerate `web/phase-detector/lib/api-types.ts` from the consolidated
# Pydantic schemas at `web/backend/schemas.py`.
#
# W15-A (session #10, 2026-05-15): single source of truth for the
# request/response shapes flowing between FastAPI backend and the
# Next.js phase-detector frontend.
#
# Usage:
#     bash scripts/gen_ts_types.sh
#
# Prereqs (already present in CI; install locally as needed):
#     .venv/bin/pip install pydantic-to-typescript
#     pnpm/npm install -g json-schema-to-typescript   (or use npx)
#
# Exits non-zero if generation fails. The `types-sync` GitHub Action
# re-runs this script on every PR and `git diff --exit-code` on the
# output to block merges that ship a stale TS file.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="${PY:-${REPO_ROOT}/.venv/bin/python}"
PYDANTIC2TS="${PYDANTIC2TS:-${REPO_ROOT}/.venv/bin/pydantic2ts}"
OUT="web/phase-detector/lib/api-types.ts"
SCHEMAS_FILE="web/backend/schemas.py"

if [[ ! -x "$PY" ]]; then
  echo "[gen_ts_types] no python at $PY — set PY env var or run 'python -m venv .venv'" >&2
  exit 2
fi
if [[ ! -x "$PYDANTIC2TS" ]]; then
  echo "[gen_ts_types] pydantic2ts not installed in venv — run:" >&2
  echo "    $PY -m pip install pydantic-to-typescript" >&2
  exit 2
fi

# Locate json2ts. We prefer a globally-installed binary, but the cheap
# fallback is `npx --yes json-schema-to-typescript`. Either way the path
# is passed explicitly to pydantic2ts via --json2ts-cmd.
if command -v json2ts >/dev/null 2>&1; then
  JSON2TS="$(command -v json2ts)"
else
  JSON2TS="npx --yes -p json-schema-to-typescript@15 json2ts"
fi

echo "[gen_ts_types] schemas: $SCHEMAS_FILE"
echo "[gen_ts_types] output:  $OUT"
echo "[gen_ts_types] json2ts: $JSON2TS"

# pydantic2ts can ingest a module file directly, sidestepping FastAPI
# import side effects (env loading, slowapi, DB pools, etc).
"$PYDANTIC2TS" \
  --module "$SCHEMAS_FILE" \
  --output "$OUT" \
  --json2ts-cmd "$JSON2TS"

# Sanity-check: must contain at least 15 TS interface/type declarations.
COUNT=$(grep -E "^(export )?(interface|type) " "$OUT" | wc -l | tr -d ' ')
echo "[gen_ts_types] generated $COUNT TS declarations"
if [[ "$COUNT" -lt 15 ]]; then
  echo "[gen_ts_types] WARNING: expected >= 15, got $COUNT" >&2
  exit 1
fi

echo "[gen_ts_types] OK — $OUT updated"
