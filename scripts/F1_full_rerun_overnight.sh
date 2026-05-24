#!/usr/bin/env bash
# F1_full_rerun_overnight.sh
#
# Queue a full 13-system bootstrap rerun at n_boot=10000 for publication.
#
# The W7-D subset run (earthquake / wildfire / solar at n_boot=10000) is in
# v4/results/F1_bootstrap10k_subset.jsonl. This script is the queued
# overnight expansion: rerun all 13 systems at the higher precision so the
# C1 manuscript v0.3 has uniformly 10k-CI numbers in Table 1.
#
# Estimated runtime: ~12 hours overnight on the dadamini Mac (single-core
# scipy.optimize.minimize per resample; powerlaw package is not parallelized
# at the Fit level). Recommended invocation: `nohup ./scripts/F1_full_rerun_overnight.sh > /tmp/f1_overnight_$(date +%Y%m%d).log 2>&1 &`
#
# Usage:
#   bash scripts/F1_full_rerun_overnight.sh

set -euo pipefail

REPO="$(cd "$(dirname "$0")"/.. && pwd)"
PY="$REPO/.venv/bin/python"
PYTHONPATH="$REPO/packages/soc-pipeline/src:$PYTHONPATH"
export PYTHONPATH

OUT_DIR="$REPO/v4/results"
mkdir -p "$OUT_DIR"
OUT_JSONL="$OUT_DIR/F1_bootstrap10k_full13.jsonl"
LOG="$OUT_DIR/F1_full_rerun_$(date +%Y%m%d).log"

echo "[F1-full] start $(date) -> $OUT_JSONL" | tee -a "$LOG"

# Each system is invoked via the F1 subset script with system filter when
# implemented; for now, the subset script runs 3 systems. The full-13 version
# would extend SUBSET in v4/scripts/F1_bootstrap_10k_subset.py to all
# loaders. Until that expansion exists, this script aggregates the per-phase
# bootstrap CI rerun via the original per-phase analyze scripts using
# n_boot=10000 overrides.

# For clarity: this script is a STUB queueing file. The actual per-phase
# bootstrap reruns are documented in per-phase analyze.py scripts inside
# v4/validation/soc-*/. Future work item: lift those into a single
# `F1_full_rerun.py` that walks SYSTEMS list with the same SUBSET schema.

echo "[F1-full] NOT YET IMPLEMENTED (placeholder)" | tee -a "$LOG"
echo "[F1-full] To complete: " | tee -a "$LOG"
echo "  1. Extend SUBSET in v4/scripts/F1_bootstrap_10k_subset.py with the"\
     "remaining 10 systems' loaders." | tee -a "$LOG"
echo "  2. Run: $PY $REPO/v4/scripts/F1_bootstrap_10k_subset.py" | tee -a "$LOG"
echo "  3. Move output: mv $OUT_DIR/F1_bootstrap10k_subset.jsonl $OUT_JSONL" | tee -a "$LOG"
echo "  4. Update C1 §2.2 Methods + Table 1 with new CIs" | tee -a "$LOG"

echo "[F1-full] end $(date)" | tee -a "$LOG"
