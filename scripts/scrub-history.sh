#!/usr/bin/env bash
# scrub-history.sh — git filter-repo wrapper to redact leaked API keys
# from ALL refs (branches + tags + reflog).
#
# Idempotent: re-running on already-scrubbed history is a no-op.
# Safe by default: --dry-run is the default mode; force-push is NEVER executed
# by this script. Operator must manually run the printed push command after review.
#
# Usage:
#   scripts/scrub-history.sh                      # dry-run (default)
#   scripts/scrub-history.sh --dry-run            # explicit dry-run
#   scripts/scrub-history.sh --execute            # actually rewrite history (still no push)
#   scripts/scrub-history.sh --execute --no-backup
#   scripts/scrub-history.sh --auto-patterns      # build patterns from gitleaks scan
#   scripts/scrub-history.sh --validate-only      # only validate patterns file, no scrub
#
# Reference: docs/audit/git-history-scrub-2026-05-24.md
#            docs/audit/git-history-scrub-postmortem-2026-05-25.md (1187-file pollution RCA)
set -euo pipefail

# -------- paths --------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PATTERNS_FILE="${PATTERNS_FILE:-$REPO_ROOT/scripts/scrub-patterns.txt}"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/.scrub-pre-backup}"
GITLEAKS_REPORT="${GITLEAKS_REPORT:-$REPO_ROOT/.gitleaks-report.json}"
DRY_RUN_LOG="${DRY_RUN_LOG:-$REPO_ROOT/.scrub-dry-run.log}"

# -------- flags --------
MODE="dry-run"
DO_BACKUP=1
AUTO_PATTERNS=0
VALIDATE_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)        MODE="dry-run" ;;
    --execute)        MODE="execute" ;;
    --no-backup)      DO_BACKUP=0 ;;
    --auto-patterns)  AUTO_PATTERNS=1 ;;
    --validate-only)  VALIDATE_ONLY=1 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown flag: $arg" >&2
      exit 2
      ;;
  esac
done

# -------- validate_patterns_file --------
# Defensive check against the 2026-05-24 pollution incident: filter-repo's
# --replace-text reader does NOT skip comment lines. A bare "#" or any line
# without "==>" becomes "literal → ***REMOVED***", catastrophically replacing
# every occurrence of that literal across all blobs in all of history.
#
# Rules enforced:
#   - empty lines: allowed (silently skipped)
#   - lines starting with "#": allowed (defensive; we recommend NEVER putting
#     them in patterns.txt — they should live in scrub-patterns.README.md)
#   - any other line MUST contain "==>" with a non-empty left side
# Failure mode: print every offending line with its number, then exit 4.
validate_patterns_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "ERROR: patterns file not found: $file" >&2
    exit 4
  fi
  if [[ ! -s "$file" ]]; then
    echo "ERROR: patterns file is empty: $file" >&2
    exit 4
  fi

  local lineno=0
  local bad=0
  local literal_count=0
  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    lineno=$((lineno + 1))
    # Strip trailing CR (in case of CRLF files)
    local line="${raw_line%$'\r'}"

    # Empty line: skip
    if [[ -z "$line" ]]; then
      continue
    fi
    # Comment line: allowed but discouraged
    if [[ "${line:0:1}" == "#" ]]; then
      continue
    fi
    # Non-empty, non-comment: must contain "==>" with non-empty LHS
    if [[ "$line" != *"==>"* ]]; then
      echo "ERROR: line $lineno has no '==>' separator: $line" >&2
      echo "       filter-repo would treat this as 'literal $line → ***REMOVED***'." >&2
      echo "       This is the bug that caused the 2026-05-24 1187-file pollution." >&2
      bad=$((bad + 1))
      continue
    fi
    local lhs="${line%%==>*}"
    if [[ -z "$lhs" ]]; then
      echo "ERROR: line $lineno has empty left-hand side before '==>': $line" >&2
      bad=$((bad + 1))
      continue
    fi
    literal_count=$((literal_count + 1))
  done < "$file"

  if [[ "$bad" -gt 0 ]]; then
    echo "FATAL: $bad invalid line(s) in $file — refusing to run filter-repo." >&2
    echo "       Fix the patterns file (see scripts/scrub-patterns.README.md)" >&2
    echo "       and rerun. Metadata/comments belong in the .README.md, NOT here." >&2
    exit 4
  fi
  if [[ "$literal_count" -eq 0 ]]; then
    echo "ERROR: patterns file has 0 literal==>replacement lines: $file" >&2
    exit 4
  fi
  echo "  validate_patterns_file: OK ($literal_count literal rule(s), 0 violations)"
}

# Run validate-only mode early — no preflight, no repo state checks needed.
if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
  echo "[validate-only] $PATTERNS_FILE"
  validate_patterns_file "$PATTERNS_FILE"
  exit 0
fi

# -------- preflight --------
echo "[1/6] preflight"
command -v git-filter-repo >/dev/null 2>&1 || {
  echo "ERROR: git-filter-repo not on PATH. Install via 'brew install git-filter-repo' or 'pip3 install --user git-filter-repo'." >&2
  exit 3
}

if [[ -n "$(git status --porcelain)" ]]; then
  if [[ "$MODE" == "execute" ]]; then
    echo "ERROR: working tree is dirty. Commit / stash before --execute." >&2
    git status --short
    exit 4
  else
    echo "  warn: working tree dirty (ok for dry-run, blocks --execute):"
    git status --short | sed 's/^/    /'
  fi
fi

echo "  repo:          $REPO_ROOT"
echo "  mode:          $MODE"
echo "  patterns file: $PATTERNS_FILE"
echo "  branch:        $(git rev-parse --abbrev-ref HEAD)"
echo "  HEAD:          $(git rev-parse --short HEAD)"
echo "  commits total: $(git log --all --oneline | wc -l | tr -d ' ')"

# -------- optional: auto-build patterns from gitleaks --------
if [[ "$AUTO_PATTERNS" -eq 1 ]]; then
  echo "[2/6] auto-patterns (gitleaks scan → patterns extraction)"
  command -v gitleaks >/dev/null 2>&1 || {
    echo "ERROR: --auto-patterns needs gitleaks. brew install gitleaks." >&2
    exit 5
  }
  command -v jq >/dev/null 2>&1 || {
    echo "ERROR: --auto-patterns needs jq." >&2
    exit 5
  }

  gitleaks detect --no-banner --redact=0 \
    --report-format=json --report-path="$GITLEAKS_REPORT" --log-level=warn || true

  # Extract high-confidence secrets (skip generic-api-key — too noisy).
  EXTRACTED="$(jq -r '
    .[] | select(.RuleID != "generic-api-key")
        | select((.Secret // "") | test("^sk-"))
        | .Secret
  ' "$GITLEAKS_REPORT" | sort -u)"

  if [[ -z "$EXTRACTED" ]]; then
    echo "  no high-confidence sk-* secrets from gitleaks; keeping existing $PATTERNS_FILE"
  else
    echo "  found $(echo "$EXTRACTED" | wc -l | tr -d ' ') unique sk-* secrets via gitleaks"
    {
      echo "# auto-generated by scrub-history.sh --auto-patterns on $(date '+%Y-%m-%d %H:%M:%S')"
      echo "# DO NOT COMMIT — contains raw secret strings."
      while IFS= read -r secret; do
        [[ -z "$secret" ]] && continue
        echo "${secret}==>sk-REDACTED-BY-SCRUB-$(date +%Y%m%d)"
      done <<< "$EXTRACTED"
    } > "$PATTERNS_FILE"
  fi
else
  echo "[2/6] skip auto-patterns (use --auto-patterns to enable)"
fi

# -------- validate patterns file --------
echo "[3/6] validate patterns"
if [[ ! -s "$PATTERNS_FILE" ]]; then
  echo "ERROR: $PATTERNS_FILE missing or empty. Either edit it manually" >&2
  echo "       (format: 'literal==>replacement', one per line — see scrub-patterns.README.md)" >&2
  echo "       or rerun with --auto-patterns." >&2
  exit 6
fi

# Hard validation gate — refuses to run filter-repo if any non-comment,
# non-empty line lacks '==>' (the 2026-05-24 RCA fix).
validate_patterns_file "$PATTERNS_FILE"

NUM_RULES=$(grep -cE '==>' "$PATTERNS_FILE" || true)
echo "  $NUM_RULES replacement rule(s) loaded"
if [[ "$NUM_RULES" -eq 0 ]]; then
  echo "ERROR: no '==>' rules in $PATTERNS_FILE." >&2
  exit 6
fi

# Idempotence check — count current matches per leaked literal
echo "[4/6] idempotence probe (current history matches)"
HITS_BEFORE=0
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ ]] && continue
  [[ -z "$line" ]] && continue
  literal="${line%%==>*}"
  [[ -z "$literal" ]] && continue
  n=$(git log --all --full-history -p 2>/dev/null | grep -c -- "$literal" || true)
  printf "  %s  matches in history: %s\n" "${literal:0:24}…" "$n"
  HITS_BEFORE=$((HITS_BEFORE + n))
done < "$PATTERNS_FILE"
echo "  total literal hits in history: $HITS_BEFORE"

if [[ "$HITS_BEFORE" -eq 0 ]]; then
  echo "  history already clean of listed literals — no-op."
  exit 0
fi

# -------- dry-run --------
if [[ "$MODE" == "dry-run" ]]; then
  echo "[5/6] DRY RUN — git filter-repo --dry-run --replace-text"
  # filter-repo --dry-run writes to .git/filter-repo/{first,last}-commits but does NOT
  # mutate refs. We invoke with --force because this is not a fresh clone.
  # Note: by default filter-repo processes ALL refs (branches + tags). We do NOT pass
  # --refs because that would skip side branches where the keys may also live.
  git filter-repo \
    --dry-run \
    --force \
    --replace-text "$PATTERNS_FILE" \
    2>&1 | tee "$DRY_RUN_LOG"

  echo ""
  echo "[6/6] dry-run complete. Log: $DRY_RUN_LOG"
  echo "  Refs were NOT modified."
  echo "  To execute, re-run with: $0 --execute"
  exit 0
fi

# -------- execute --------
echo "[5/6] EXECUTE — rewriting history"
if [[ "$DO_BACKUP" -eq 1 ]]; then
  TS="$(date +%Y%m%d-%H%M%S)"
  TAG="pre-scrub-backup-$TS"
  echo "  creating backup tag: $TAG (on current HEAD)"
  git tag "$TAG"
  # Also bundle a full mirror clone for offline rollback.
  BACKUP_BUNDLE="$BACKUP_DIR/repo-$TS.bundle"
  mkdir -p "$BACKUP_DIR"
  git bundle create "$BACKUP_BUNDLE" --all
  echo "  bundle backup: $BACKUP_BUNDLE  ($(du -h "$BACKUP_BUNDLE" | cut -f1))"
fi

git filter-repo \
  --force \
  --replace-text "$PATTERNS_FILE"

echo ""
echo "[6/6] rewrite complete. New HEAD: $(git rev-parse --short HEAD)"
echo ""
echo "Verification:"
HITS_AFTER=0
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ ]] && continue
  [[ -z "$line" ]] && continue
  literal="${line%%==>*}"
  [[ -z "$literal" ]] && continue
  n=$(git log --all --full-history -p 2>/dev/null | grep -c -- "$literal" || true)
  printf "  %s  remaining: %s\n" "${literal:0:24}…" "$n"
  HITS_AFTER=$((HITS_AFTER + n))
done < "$PATTERNS_FILE"

if [[ "$HITS_AFTER" -gt 0 ]]; then
  echo "WARN: residual literal hits remain. Inspect patterns file and rerun." >&2
fi

cat <<EOM

NEXT STEPS (NOT done by this script):
  1. Re-run gitleaks to confirm zero high-confidence findings:
       gitleaks detect --no-banner --redact --log-level=warn
  2. Inspect a sample diff (e.g. git show <known-leak-commit>:web/scripts/deploy.sh).
  3. Push only after explicit operator GO:
       git remote -v       # confirm 'origin' is the right URL
       git push --force-with-lease --all
       git push --force-with-lease --tags
  4. Coordinate fork cleanup (this rewrite does NOT touch forks).
  5. Notify collaborators — every clone must be re-cloned (not pulled).

Rollback:
  Tag '$TAG' points at pre-scrub HEAD; bundle in $BACKUP_DIR.
  Recovery: git reset --hard refs/tags/$TAG  (before any push).
EOM
