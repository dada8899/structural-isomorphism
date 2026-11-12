#!/usr/bin/env bash
# Cleanup remote branches that have already been merged into main.
#
# This is the safe slice: every branch listed below is `git branch -r --merged
# origin/main` filtered to exclude main itself — i.e. their entire commit
# history lives on main already. Deleting them loses nothing.
#
# Session #16 captured 36 merged branches. The full repo has ~160 remote
# branches total; the rest are UNMERGED and need a per-branch judgment
# call (see "Unmerged branches" section at the bottom of this script).
#
# Usage:
#   ./scripts/cleanup-stale-branches.sh --dry-run    # preview
#   ./scripts/cleanup-stale-branches.sh              # actually delete
#
# Each delete is a separate `git push origin --delete` so a single failure
# doesn't abort the rest. The branch list is regenerated from `git branch -r`
# at runtime, NOT hardcoded — so it stays correct if more merges happen
# between session #16 and the day you run this.

set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# //;s/^#//'
      exit 0 ;;
  esac
done

echo "[cleanup] Fetching latest remote state..."
git fetch origin --prune

# Regenerate the merged-list at runtime — don't trust a stale committed list.
MERGED_BRANCHES=$(git branch -r --merged origin/main | grep -vE 'HEAD|main$' | sed 's|^  origin/||')

if [ -z "$MERGED_BRANCHES" ]; then
  echo "[cleanup] no merged branches to delete; nothing to do."
  exit 0
fi

COUNT=$(echo "$MERGED_BRANCHES" | wc -l | tr -d ' ')
echo "[cleanup] $COUNT merged remote branches eligible for deletion:"
echo "$MERGED_BRANCHES" | sed 's/^/  - /'
echo

if [ "$DRY_RUN" = "1" ]; then
  echo "[cleanup] --dry-run; not deleting."
  exit 0
fi

read -r -p "[cleanup] Delete all $COUNT branches? [y/N] " ans
case "$ans" in
  y|Y) ;;
  *) echo "[cleanup] aborted."; exit 1 ;;
esac

FAIL_COUNT=0
SUCCESS_COUNT=0
while IFS= read -r br; do
  [ -z "$br" ] && continue
  echo "[cleanup] deleting origin/$br ..."
  if git push origin --delete "$br" 2>&1 | grep -E 'deleted|remote:' ; then
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
  else
    echo "[cleanup]   ✗ failed (continuing)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
done <<< "$MERGED_BRANCHES"

echo
echo "[cleanup] done: $SUCCESS_COUNT deleted, $FAIL_COUNT failed."

# -----------------------------------------------------------------------------
# Unmerged branches (manual review required)
# -----------------------------------------------------------------------------
#
# Run this to inspect:
#   git branch -r --no-merged origin/main | grep -v HEAD | head -30
#
# Heuristics for what's safe to delete from the unmerged set:
#   1. Older than 60 days AND PR was closed-not-merged → safe to delete
#      (work was abandoned, not lost).
#   2. v4/session3-* / session-NN-* prefixes for sessions whose HANDOFF.md
#      explicitly says "all work landed" → safe.
#   3. claude/project-progress-update-* → automation noise, safe.
#   4. fix/p[01]-*-1778xxxxxx-NNNN (timestamp suffix) → robo-generated CI
#      fix branches, almost certainly safe.
#
# When in doubt, DON'T delete. Branch creation is free; archaeology isn't.
