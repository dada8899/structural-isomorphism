#!/usr/bin/env bash
# Smoke test: curl every public URL on the academic + commercial site and report
# any non-200 response or any response whose body is the 404 fallback page.
#
# Usage:  scripts/smoke_test_urls.sh [base_url]
# Default: https://beta.structural.bytedance.city
#
# Run after every deploy. Exits non-zero if any URL fails.

set -u

BASE="${1:-https://beta.structural.bytedance.city}"

# Paths grouped by area. Add new routes here when adding new pages.
ACADEMIC=(
  /
  /search
  /discoveries
  /classes
  /about
  /analyze
  /paper/soc-earthquake-2026-04-15
  /paper/soc-stockmarket-2026-04-15
  /paper/soc-defi-2026-04-15
  /paper/soc-neural-2026-04-16
  /paper/soc-null-2026-04-16
)

COMMERCIAL=(
  /phase
  /phase/company
  /phase/screener
  /phase/analogy
  /phase/analogy/detail
  /phase/timeline
  /phase/redteam
  /phase/about
  /phase/memo
)

FAIL=0
check() {
  local path="$1"
  local url="$BASE$path"
  local tmp
  tmp=$(mktemp)
  local code
  code=$(curl -o "$tmp" -s -w "%{http_code}" "$url")
  local size
  size=$(wc -c < "$tmp" | tr -d ' ')
  local title
  title=$(grep -oE "<title>[^<]*</title>" "$tmp" 2>/dev/null | head -1 | sed 's/<[^>]*>//g')
  rm -f "$tmp"

  if [ "$code" != "200" ]; then
    printf "FAIL  %s  %s  %s\n" "$code" "$path" "$title"
    FAIL=$((FAIL + 1))
    return
  fi
  # 404 fallback detection: backend returns FileResponse(404.html, status_code=404) on missing,
  # but some routes may serve 404.html body with 200. Cheap heuristic: body title contains "没找到".
  if echo "$title" | grep -q "没找到"; then
    printf "FAIL  404-body  %s  %s\n" "$path" "$title"
    FAIL=$((FAIL + 1))
    return
  fi
  printf "ok    %s  %5sB  %s\n" "$code" "$size" "$path"
}

echo "=== Academic ($BASE) ==="
for p in "${ACADEMIC[@]}"; do check "$p"; done

echo
echo "=== Commercial (Phase Detector) ==="
for p in "${COMMERCIAL[@]}"; do check "$p"; done

echo
if [ "$FAIL" -gt 0 ]; then
  echo "RESULT: $FAIL failed" >&2
  exit 1
fi
echo "RESULT: all ok"
