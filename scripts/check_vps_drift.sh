#!/usr/bin/env bash
# Detect drift between local repo and VPS on critical deployed files.
#
# Tells you when someone (or you) edited VPS backend or static files
# without also committing the change locally — which is how /phase
# ended up serving a 30-line stub for months. Runs on Mac via launchd.
#
# Outputs a single DRIFT/CLEAN line per file. Non-zero exit if any drift.
#
# Usage:  scripts/check_vps_drift.sh

set -u

REPO_ROOT="${REPO_ROOT:-$HOME/Projects/structural-isomorphism}"
VPS_ROOT="/root/Projects/structural-isomorphism"

# (local_path, vps_path) pairs. Add rows when deploying new critical files.
FILES=(
  "web/backend/main.py|web/backend/main.py"
  "web/frontend/index.html|web/frontend/index.html"
  "web/frontend/classes.html|web/frontend/classes.html"
  "web/frontend/discoveries.html|web/frontend/discoveries.html"
  "web/frontend/about.html|web/frontend/about.html"
  "web/frontend/assets/data/universality-classes.json|web/frontend/assets/data/universality-classes.json"
  "phase/index.html|web/frontend/phase/landing.html"
)

DRIFT=0
STAMP="$(date '+%Y-%m-%d %H:%M:%S')"

for pair in "${FILES[@]}"; do
  local_rel="${pair%%|*}"
  vps_rel="${pair##*|}"
  local_path="$REPO_ROOT/$local_rel"
  if [ ! -f "$local_path" ]; then
    printf "MISSING-LOCAL  %s\n" "$local_rel"
    DRIFT=$((DRIFT + 1))
    continue
  fi

  local_md=$(md5 -q "$local_path" 2>/dev/null || md5sum "$local_path" 2>/dev/null | awk '{print $1}')
  vps_md=$(ssh vps "md5sum $VPS_ROOT/$vps_rel 2>/dev/null | awk '{print \$1}'" 2>/dev/null)

  if [ -z "$vps_md" ]; then
    printf "MISSING-VPS    %s -> %s\n" "$local_rel" "$vps_rel"
    DRIFT=$((DRIFT + 1))
  elif [ "$local_md" = "$vps_md" ]; then
    printf "clean          %s\n" "$local_rel"
  else
    printf "DRIFT          %s  (local:%.8s  vps:%.8s)\n" "$local_rel" "$local_md" "$vps_md"
    DRIFT=$((DRIFT + 1))
  fi
done

echo
if [ "$DRIFT" -gt 0 ]; then
  echo "[$STAMP] $DRIFT files drifted. Run rsync or git to reconcile." >&2
  exit 1
fi
echo "[$STAMP] all clean"
