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

if [[ -d "$MODEL_DIR" ]] && [[ -n "$(ls -A "$MODEL_DIR" 2>/dev/null)" ]]; then
  echo "[restore-models] $MODEL_DIR already populated, skipping"
  exit 0
fi

mkdir -p "$MODEL_DIR"

for CAND in "${CANDIDATES[@]}"; do
  echo "[restore-models] Trying $CAND..."
  if "$VENV_PYTHON" -c "
import sys
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('$CAND')
m.save('$MODEL_DIR')
print('OK')
" 2>&1 | grep -q OK; then
    echo "[restore-models] Saved $CAND → $MODEL_DIR"
    exit 0
  fi
  echo "[restore-models]   $CAND failed, trying next"
done

echo "[restore-models] FATAL: all candidates failed"
exit 1
