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
# Prereqs (the same pinned set is installed in CI):
#     .venv/bin/pip install -r scripts/requirements-types.txt
#     npm ci --prefix scripts/types-generator
#
# Exits non-zero if generation fails. The `types-sync` GitHub Action
# re-runs this script on every PR and `git diff --exit-code` on the
# output to block merges that ship a stale TS file.
set -euo pipefail

# Reject legacy shell-command injection surfaces before inspecting any local
# dependency. The same hostile input must fail identically in every runtime.
if [[ -n "${JSON2TS_CMD:-}" || -n "${JSON2TS_PACKAGE_JSON:-}" ]]; then
  echo "[gen_ts_types] legacy command overrides are forbidden" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DEFAULT_TYPES_VENV="${REPO_ROOT}/.venv"
if [[ -x "${REPO_ROOT}/.venv-openapi/bin/python" ]]; then
  DEFAULT_TYPES_VENV="${REPO_ROOT}/.venv-openapi"
fi
PY="${PY:-${DEFAULT_TYPES_VENV}/bin/python}"
OUT="${OUT:-web/phase-detector/lib/api-types.ts}"
TYPE_REQUIREMENTS="scripts/requirements-types.txt"
TYPE_GENERATOR="scripts/generate_ts_types.py"
TYPE_TOOL_ROOT="scripts/types-generator"

# Accept either an absolute path (local .venv) or a bare command name on
# $PATH (CI sets PY=python). The `[[ -x ... ]]` test below only works on
# real paths, so resolve bare names through `command -v` first.
if [[ "$PY" != /* ]]; then
  PY_RESOLVED="$(command -v "$PY" || true)"
  if [[ -z "$PY_RESOLVED" ]]; then
    echo "[gen_ts_types] no python on PATH as '$PY' — set PY env var or run 'python -m venv .venv'" >&2
    exit 2
  fi
  PY="$PY_RESOLVED"
fi
if [[ ! -x "$PY" ]]; then
  echo "[gen_ts_types] no python at $PY — set PY env var or run 'python -m venv .venv'" >&2
  exit 2
fi

# Pydantic's JSON schema semantics are artifact inputs. Refuse a convenient
# but unpinned local environment instead of silently rewriting committed TS.
"$PY" - "$TYPE_REQUIREMENTS" <<'PY'
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re
import sys

requirements = Path(sys.argv[1]).read_text(encoding="utf-8")
for package in ("pydantic", "pydantic-to-typescript"):
    match = re.search(
        rf"^{re.escape(package)}==([^\s#]+)\s*(?:#.*)?$",
        requirements,
        re.MULTILINE | re.IGNORECASE,
    )
    if match is None:
        raise SystemExit(f"[gen_ts_types] {package} must be exactly pinned in {sys.argv[1]}")
    expected = match.group(1)
    try:
        actual = version(package)
    except PackageNotFoundError:
        actual = "not-installed"
    if actual != expected:
        raise SystemExit(
            f"[gen_ts_types] {package} version mismatch: got {actual}, expected {expected}; "
            f"install -r {sys.argv[1]}"
        )
PY

if [[ ! -f "${TYPE_TOOL_ROOT}/package-lock.json" \
   || ! -x "${TYPE_TOOL_ROOT}/node_modules/.bin/json2ts" ]]; then
  echo "[gen_ts_types] locked json2ts runtime is missing — run:" >&2
  echo "    npm ci --ignore-scripts --no-audit --no-fund --prefix ${TYPE_TOOL_ROOT}" >&2
  exit 2
fi

echo "[gen_ts_types] schemas: web/backend/schemas.py"
echo "[gen_ts_types] output:  $OUT"
echo "[gen_ts_types] json2ts: locked repository runtime"

"$PY" "$TYPE_GENERATOR" --output "$OUT"

# Sanity-check: must contain at least 15 TS interface/type declarations.
COUNT=$(grep -E "^(export )?(interface|type) " "$OUT" | wc -l | tr -d ' ')
echo "[gen_ts_types] generated $COUNT TS declarations"
if [[ "$COUNT" -lt 15 ]]; then
  echo "[gen_ts_types] WARNING: expected >= 15, got $COUNT" >&2
  exit 1
fi

echo "[gen_ts_types] OK — $OUT updated"
