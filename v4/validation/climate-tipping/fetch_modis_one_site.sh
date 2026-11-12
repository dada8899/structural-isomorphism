#!/bin/bash
# Single-site MODIS fetcher (central_amazonas) - skip-existing idempotent.
# Faster + lower rate-limit risk than the 5-site version.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/raw/modis_subset"
mkdir -p "$OUT"

SITE="central_amazonas"
LAT="-3.0"
LON="-60.0"
SLEEP=3

DATES_FILE="$OUT/${SITE}_dates.json"
if [ ! -s "$DATES_FILE" ]; then
  for attempt in 1 2 3 4 5; do
    code=$(curl -s -o "$DATES_FILE" -w "%{http_code}" --max-time 30 \
      "https://modis.ornl.gov/rst/api/v1/MOD13Q1/dates?latitude=${LAT}&longitude=${LON}")
    if [ "$code" = "200" ]; then break; fi
    sleep $((10 * attempt))
  done
fi

python3 -c "
import json
d = json.load(open('${DATES_FILE}'))
codes = [r['modis_date'] for r in d.get('dates', []) if 2000 <= int(r['calendar_date'][:4]) <= 2024]
for i in range(0, len(codes), 9):
    chunk = codes[i:i+9]
    print(chunk[0], chunk[-1])
" > "$OUT/${SITE}_chunks.txt"

TOTAL=$(wc -l < "$OUT/${SITE}_chunks.txt")
echo "[curl] $SITE: $TOTAL chunks total"

DONE=0
SKIP=0
FAIL=0
while read -r START END; do
  [ -z "$START" ] && continue
  CHUNK_FILE="$OUT/${SITE}_${START}_${END}.json"
  if [ -s "$CHUNK_FILE" ] && grep -q '"subset"' "$CHUNK_FILE" 2>/dev/null; then
    SKIP=$((SKIP+1))
    continue
  fi
  ok=0
  for attempt in 1 2 3 4 5; do
    code=$(curl -s -o "$CHUNK_FILE" -w "%{http_code}" --max-time 45 \
      "https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset?latitude=${LAT}&longitude=${LON}&startDate=${START}&endDate=${END}&kmAboveBelow=0&kmLeftRight=0&band=250m_16_days_NDVI")
    if [ "$code" = "200" ]; then ok=1; break; fi
    rm -f "$CHUNK_FILE"
    wait=$((15 * attempt))
    echo "[curl]   ${START}-${END} HTTP $code (attempt $attempt) sleep ${wait}s"
    sleep "$wait"
  done
  if [ "$ok" = "1" ]; then
    DONE=$((DONE+1))
    echo "[curl] +${START}-${END} ok (done=$DONE skip=$SKIP fail=$FAIL)"
  else
    FAIL=$((FAIL+1))
    echo "[curl] !${START}-${END} FAILED after 5 attempts (done=$DONE skip=$SKIP fail=$FAIL)"
  fi
  sleep "$SLEEP"
done < "$OUT/${SITE}_chunks.txt"

echo "[curl] $SITE final: done=$DONE skip=$SKIP fail=$FAIL"
