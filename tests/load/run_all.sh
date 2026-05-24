#!/usr/bin/env bash
# run_all.sh — orchestrator for k6 load test suite (W14-B, session #10)
#
# Runs each scenario in sequence (NOT parallel — parallel runs would
# contaminate each other's baselines). Writes JSON summaries to
# tests/load/results/ and produces a markdown digest at the end.
#
# Usage:
#   BASE_URL=http://localhost:8000 ./tests/load/run_all.sh           # full suite
#   BASE_URL=http://localhost:8000 SKIP_STRESS=1 ./tests/load/run_all.sh  # skip stress
#   BASE_URL=https://beta.structural.bytedance.city SAFE=1 ./tests/load/run_all.sh
#     (SAFE=1 runs only the smoke tests, capped at 1-2 VU — for prod sanity)

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
SAFE="${SAFE:-0}"
SKIP_STRESS="${SKIP_STRESS:-0}"

cd "$(dirname "$0")/../.."  # repo root

if ! command -v k6 >/dev/null 2>&1; then
  echo "ERROR: k6 is not installed."
  echo "Install: brew install k6  (macOS)"
  echo "         https://k6.io/docs/get-started/installation/ (other)"
  exit 1
fi

mkdir -p tests/load/results
cd tests/load

echo "================================================================"
echo " k6 load suite — BASE_URL=$BASE_URL"
echo " Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Safe mode: $SAFE  Skip stress: $SKIP_STRESS"
echo "================================================================"

run_one() {
  local name="$1"
  local script="$2"
  shift 2
  echo ""
  echo "---- [$name] $script ----"
  BASE_URL="$BASE_URL" k6 run "$@" "$script" || echo "WARN: $name returned non-zero (threshold breached or k6 error)"
}

if [ "$SAFE" = "1" ]; then
  echo "SAFE mode — running smokes at 1-2 VU only (no stress, no mixed)."
  run_one "phases_smoke (1 VU)" phases_smoke.js --vus 1 --duration 20s
  run_one "universality_smoke (1 VU)" universality_smoke.js --vus 1 --duration 20s
  echo ""
  echo "Skipped: ask_smoke (would cost LLM budget), mixed_realistic, stress_ramp."
else
  run_one "phases_smoke" phases_smoke.js
  run_one "ask_smoke" ask_smoke.js
  run_one "universality_smoke" universality_smoke.js
  run_one "mixed_realistic" mixed_realistic.js

  if [ "$SKIP_STRESS" != "1" ]; then
    run_one "stress_ramp" stress_ramp.js
  else
    echo "Skipping stress_ramp (SKIP_STRESS=1)."
  fi
fi

echo ""
echo "================================================================"
echo " Digest (tests/load/results/*.json)"
echo "================================================================"
for f in results/*.json; do
  echo ""
  echo "--- $f ---"
  cat "$f"
done

echo ""
echo "Run complete. See tests/load/results/ for machine-readable summaries."
