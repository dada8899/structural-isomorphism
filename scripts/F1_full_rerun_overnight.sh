***REMOVED***!/usr/bin/env bash
***REMOVED*** F1_full_rerun_overnight.sh
***REMOVED***
***REMOVED*** Queue a full 13-system bootstrap rerun at n_boot=10000 for publication.
***REMOVED***
***REMOVED*** The W7-D subset run (earthquake / wildfire / solar at n_boot=10000) is in
***REMOVED*** v4/results/F1_bootstrap10k_subset.jsonl. This script is the queued
***REMOVED*** overnight expansion: rerun all 13 systems at the higher precision so the
***REMOVED*** C1 manuscript v0.3 has uniformly 10k-CI numbers in Table 1.
***REMOVED***
***REMOVED*** Estimated runtime: ~12 hours overnight on the dadamini Mac (single-core
***REMOVED*** scipy.optimize.minimize per resample; powerlaw package is not parallelized
***REMOVED*** at the Fit level). Recommended invocation: `nohup ./scripts/F1_full_rerun_overnight.sh > /tmp/f1_overnight_$(date +%Y%m%d).log 2>&1 &`
***REMOVED***
***REMOVED*** Usage:
***REMOVED***   bash scripts/F1_full_rerun_overnight.sh

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

***REMOVED*** Each system is invoked via the F1 subset script with system filter when
***REMOVED*** implemented; for now, the subset script runs 3 systems. The full-13 version
***REMOVED*** would extend SUBSET in v4/scripts/F1_bootstrap_10k_subset.py to all
***REMOVED*** loaders. Until that expansion exists, this script aggregates the per-phase
***REMOVED*** bootstrap CI rerun via the original per-phase analyze scripts using
***REMOVED*** n_boot=10000 overrides.

***REMOVED*** For clarity: this script is a STUB queueing file. The actual per-phase
***REMOVED*** bootstrap reruns are documented in per-phase analyze.py scripts inside
***REMOVED*** v4/validation/soc-*/. Future work item: lift those into a single
***REMOVED*** `F1_full_rerun.py` that walks SYSTEMS list with the same SUBSET schema.

echo "[F1-full] NOT YET IMPLEMENTED (placeholder)" | tee -a "$LOG"
echo "[F1-full] To complete: " | tee -a "$LOG"
echo "  1. Extend SUBSET in v4/scripts/F1_bootstrap_10k_subset.py with the"\
     "remaining 10 systems' loaders." | tee -a "$LOG"
echo "  2. Run: $PY $REPO/v4/scripts/F1_bootstrap_10k_subset.py" | tee -a "$LOG"
echo "  3. Move output: mv $OUT_DIR/F1_bootstrap10k_subset.jsonl $OUT_JSONL" | tee -a "$LOG"
echo "  4. Update C1 §2.2 Methods + Table 1 with new CIs" | tee -a "$LOG"

echo "[F1-full] end $(date)" | tee -a "$LOG"
