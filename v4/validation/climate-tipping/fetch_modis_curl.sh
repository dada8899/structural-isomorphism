#!/bin/bash
# fetch_modis_curl.sh - Conservative shell fetcher for MODIS NDVI Amazon panel.
# Uses curl with per-request sleep to dodge ORNL DAAC rate limit.
# Output: one JSON file per (site x year) under raw/modis_subset/.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/raw/modis_subset"
mkdir -p "$OUT"

# (site_id, lat, lon)
SITES=(
  "central_amazonas:-3.0:-60.0"
  "rondonia_arc:-10.0:-62.5"
  "xingu_park:-12.0:-53.0"
  "western_acre:-9.5:-68.0"
  "para_central:-5.5:-55.5"
)

# 24 years × 9-date chunks ≈ many requests; pace at 4s/request.
SLEEP=4

# For each site, hit dates listing once, then chunked subsets in 9-date blocks.
for spec in "${SITES[@]}"; do
  IFS=':' read -r SITE LAT LON <<< "$spec"
  echo "[curl] === $SITE lat=$LAT lon=$LON ==="
  DATES_FILE="$OUT/${SITE}_dates.json"
  if [ ! -s "$DATES_FILE" ]; then
    for attempt in 1 2 3 4 5; do
      code=$(curl -s -o "$DATES_FILE" -w "%{http_code}" --max-time 30 \
        "https://modis.ornl.gov/rst/api/v1/MOD13Q1/dates?latitude=${LAT}&longitude=${LON}")
      if [ "$code" = "200" ]; then break; fi
      wait=$((10 * attempt))
      echo "[curl]   dates HTTP $code (attempt $attempt), sleep ${wait}s"
      sleep "$wait"
    done
  fi
  # Parse year-grouped chunks: take all MODIS date codes A2000-A2024.
  python3 -c "
import json, sys
d = json.load(open('${DATES_FILE}'))
codes = [r['modis_date'] for r in d.get('dates', []) if 2000 <= int(r['calendar_date'][:4]) <= 2024]
# 9-chunk windows
for i in range(0, len(codes), 9):
    chunk = codes[i:i+9]
    print(chunk[0], chunk[-1])
" > "$OUT/${SITE}_chunks.txt"

  while read -r START END; do
    [ -z "$START" ] && continue
    CHUNK_FILE="$OUT/${SITE}_${START}_${END}.json"
    [ -s "$CHUNK_FILE" ] && continue   # idempotent
    for attempt in 1 2 3 4 5; do
      code=$(curl -s -o "$CHUNK_FILE" -w "%{http_code}" --max-time 45 \
        "https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset?latitude=${LAT}&longitude=${LON}&startDate=${START}&endDate=${END}&kmAboveBelow=0&kmLeftRight=0&band=250m_16_days_NDVI")
      if [ "$code" = "200" ]; then break; fi
      wait=$((15 * attempt))
      echo "[curl]   ${START}-${END} HTTP $code (attempt $attempt), sleep ${wait}s"
      sleep "$wait"
    done
    sleep "$SLEEP"
  done < "$OUT/${SITE}_chunks.txt"

  echo "[curl] $SITE done: $(ls $OUT/${SITE}_*.json | wc -l) chunk files"
done

echo "[curl] all sites complete"
