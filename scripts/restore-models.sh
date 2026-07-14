#!/usr/bin/env bash
# restore-models.sh — idempotent model restore from HF Hub
# Used by: scripts/deploy-vps.sh + systemd structural-web.service PreStart
# Required: venv/bin/python with sentence-transformers installed
#
# Why this exists:
#   2026-05-14 prod 502 (25min) — rsync --delete from git source to deploy
#   target wiped models/structural-v2/ (excluded from git via .gitignore).
#   Backend startup load_model(explicit_path=...) raised, systemd loop.
#   This script restores the model fixture from HF Hub idempotently.
#
# Env vars (with defaults):
#   REPO_ROOT   — deploy target root (default: /root/Projects/structural-isomorphism)
#   MODEL_DIR   — where to save model (default: $REPO_ROOT/models/structural-v2)
#   VENV_PYTHON — python with sentence-transformers (default: $REPO_ROOT/venv/bin/python)

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/root/Projects/structural-isomorphism}"
MODEL_DIR="${MODEL_DIR:-$REPO_ROOT/models/structural-v2}"
VENV_PYTHON="${VENV_PYTHON:-$REPO_ROOT/venv/bin/python}"

# Candidate HF model IDs in fallback order
CANDIDATES=(
  "structural-isomorphism/structural-v1"   # ideal, may not exist on HF
  "shibing624/text2vec-base-chinese"        # base model fallback (used 2026-05-14 recovery)
)

validate_model_destination() {
  "$VENV_PYTHON" - "$REPO_ROOT" "$MODEL_DIR" <<'PY'
import os
import sys
from pathlib import Path

repo_raw, model_raw = sys.argv[1:]
repo = Path(repo_raw)
model = Path(model_raw)
if not repo.is_absolute() or repo.is_symlink() or not repo.is_dir():
    raise SystemExit("REPO_ROOT must be an absolute, real directory")
repo = repo.resolve(strict=True)
if not model.is_absolute():
    raise SystemExit("MODEL_DIR must be absolute")
try:
    relative = model.relative_to(Path(os.path.abspath(repo_raw)))
except ValueError as exc:
    raise SystemExit("MODEL_DIR must remain inside REPO_ROOT") from exc
if not relative.parts:
    raise SystemExit("MODEL_DIR cannot equal REPO_ROOT")

current = repo
for part in relative.parts:
    if part in {"", ".", ".."}:
        raise SystemExit("MODEL_DIR is not normalized")
    current /= part
    if current.is_symlink():
        raise SystemExit("MODEL_DIR crosses a symlink boundary")
    if current.exists():
        resolved = current.resolve(strict=True)
        if resolved != repo and repo not in resolved.parents:
            raise SystemExit("MODEL_DIR resolves outside REPO_ROOT")
PY
}

validate_model_destination || {
  echo "[restore-models] FATAL: unsafe model destination" >&2
  exit 1
}

if [[ -d "$MODEL_DIR" ]] && [[ -n "$(ls -A "$MODEL_DIR" 2>/dev/null)" ]]; then
  echo "[restore-models] $MODEL_DIR already populated, skipping"
  exit 0
fi

mkdir -p "$MODEL_DIR"
validate_model_destination || {
  echo "[restore-models] FATAL: model destination changed during restore" >&2
  exit 1
}

for CAND in "${CANDIDATES[@]}"; do
  echo "[restore-models] Trying $CAND..."
  if validate_model_destination && \
    "$VENV_PYTHON" - "$CAND" "$MODEL_DIR" <<'PY' 2>&1 | grep -q OK; then
import sys
from sentence_transformers import SentenceTransformer

candidate, model_dir = sys.argv[1:]
m = SentenceTransformer(candidate)
m.save(model_dir)
print('OK')
PY
    echo "[restore-models] Saved $CAND → $MODEL_DIR"
    exit 0
  fi
  echo "[restore-models]   $CAND failed, trying next"
done

echo "[restore-models] FATAL: all candidates failed"
exit 1
