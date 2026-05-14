#!/usr/bin/env bash
# recover-model-v2.sh — restore structural-v2 weights from multiple sources
#
# Background:
#   2026-05-14 W1 prod disaster: rsync --delete wiped VPS models/structural-v2/.
#   W2-F recovery used HF base fallback (shibing624/text2vec-base-chinese) — got
#   service back online, but the saved files are BASE weights, NOT real finetuned
#   v2. W4-D dogfood confirmed retrieval degraded (e.g. 形状记忆 → 团队氛围 false
#   match) because base lacks structural isomorphism signal.
#
#   This script defines the canonical recovery path. Strategy 1+2 are real
#   recovery (true finetuned weights); strategy 3 is the W2-F survival fallback
#   (clearly labeled WARN to avoid silent degradation).
#
# Env vars (with defaults):
#   REPO_ROOT     — repo root (default: $(pwd))
#   MODEL_DIR     — where to save model (default: $REPO_ROOT/models/structural-v2)
#   VENV_PYTHON   — python with sentence-transformers (default: $REPO_ROOT/.venv/bin/python)
#   HF_TARGET_ID  — HF id to try first (default: dada8899/structural-v2)
#   ALLOW_RETRAIN — set to 1 to allow strategy 2 (local re-finetune, 30min-2h)
#   ALLOW_BASE    — set to 1 to allow strategy 3 (base fallback, degraded)
#
# Exit codes:
#   0 — real v2 weights restored (HF or re-finetune)
#   1 — only base fallback applied (WARN: degraded retrieval)
#   2 — all strategies failed

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
MODEL_DIR="${MODEL_DIR:-$REPO_ROOT/models/structural-v2}"
VENV_PYTHON="${VENV_PYTHON:-$REPO_ROOT/.venv/bin/python}"
HF_TARGET_ID="${HF_TARGET_ID:-dada8899/structural-v2}"
ALLOW_RETRAIN="${ALLOW_RETRAIN:-0}"
ALLOW_BASE="${ALLOW_BASE:-0}"

mkdir -p "$MODEL_DIR"

log() { echo "[recover-model-v2] $*"; }

# Idempotency: if MODEL_DIR already has a finetuned-looking model, exit early.
# We detect "finetuned" heuristically: presence of saved training args or non-trivial size.
if [[ -d "$MODEL_DIR" ]] && [[ -f "$MODEL_DIR/model.safetensors" ]]; then
  # Check if this looks like a real v2 (vs base fallback) by inspecting README
  if [[ -f "$MODEL_DIR/README.md" ]] && grep -q "structural-v2\|finetune\|MultipleNegativesRanking" "$MODEL_DIR/README.md" 2>/dev/null; then
    log "$MODEL_DIR appears to be real v2 (README signals finetune), skipping"
    exit 0
  fi
  log "WARN: $MODEL_DIR exists but appears to be base fallback (README lacks v2 signal)"
fi

# ============================================================
# Strategy 1: HuggingFace Hub snapshot_download
# ============================================================
log "Strategy 1: trying HF Hub $HF_TARGET_ID..."
if "$VENV_PYTHON" -c "
import sys
try:
    from huggingface_hub import snapshot_download
    snapshot_download('$HF_TARGET_ID', local_dir='$MODEL_DIR')
    sys.exit(0)
except ImportError:
    print('huggingface_hub not installed', file=sys.stderr); sys.exit(2)
except Exception as e:
    print(f'HF download failed: {e}', file=sys.stderr); sys.exit(1)
" 2>&1; then
  log "OK: restored from HF Hub $HF_TARGET_ID"
  exit 0
fi
log "Strategy 1 failed (model not on HF Hub or hub_hub not installed)"

# ============================================================
# Strategy 2: Local re-finetune from training data
# ============================================================
if [[ "$ALLOW_RETRAIN" == "1" ]]; then
  TRAIN_SCRIPT="$REPO_ROOT/scripts/train_v2.py"
  TRAIN_DATA="$REPO_ROOT/data/clean-expanded.jsonl"
  if [[ -f "$TRAIN_SCRIPT" && -f "$TRAIN_DATA" ]]; then
    log "Strategy 2: re-finetuning v2 locally (this takes 30min-2h on Apple Silicon MPS)"
    log "  script: $TRAIN_SCRIPT"
    log "  data:   $TRAIN_DATA ($(wc -l < "$TRAIN_DATA") entries)"
    log "  output: $MODEL_DIR"
    if "$VENV_PYTHON" "$TRAIN_SCRIPT"; then
      log "OK: re-finetuned v2 saved to $MODEL_DIR"
      log "TODO: consider pushing to HF Hub as canonical source:"
      log "  huggingface-cli upload $HF_TARGET_ID $MODEL_DIR ."
      exit 0
    fi
    log "Strategy 2 failed (training script errored)"
  else
    log "Strategy 2 skipped: missing $TRAIN_SCRIPT or $TRAIN_DATA"
  fi
else
  log "Strategy 2 skipped: ALLOW_RETRAIN!=1 (set to 1 to enable, takes 30min-2h)"
fi

# ============================================================
# Strategy 3: Base model fallback (W2-F survival mode)
# ============================================================
if [[ "$ALLOW_BASE" == "1" ]]; then
  log "Strategy 3: WARN base fallback shibing624/text2vec-base-chinese"
  log "  (this is the W2-F prod recovery state — degraded retrieval, not real v2)"
  if "$VENV_PYTHON" -c "
import sys
try:
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer('shibing624/text2vec-base-chinese')
    m.save('$MODEL_DIR')
    sys.exit(0)
except Exception as e:
    print(f'base fallback failed: {e}', file=sys.stderr); sys.exit(1)
"; then
    log "WARN: saved BASE weights to $MODEL_DIR (NOT real finetuned v2)"
    log "WARN: retrieval will be degraded; schedule re-finetune session ASAP"
    exit 1
  fi
  log "Strategy 3 failed (base download errored)"
else
  log "Strategy 3 skipped: ALLOW_BASE!=1 (set to 1 to use degraded base fallback)"
fi

log "FATAL: all strategies failed or skipped"
log "To proceed, set ALLOW_RETRAIN=1 (real recovery, 30min-2h) or ALLOW_BASE=1 (degraded fallback)"
exit 2
