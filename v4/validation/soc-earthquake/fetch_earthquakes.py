#!/usr/bin/env python3
"""
Layer 5 — Phase 1: Fetch USGS earthquake catalog for SOC validation.

Pulls global M >= 3.5 earthquakes from USGS FDSN API in month-sized batches
(API limits to ~20000 events per query). Saves to parquet + JSONL.

Pipeline purpose: validate Gutenberg-Richter (b-value ~1, equivalent to
power-law tau ~= 2 in size form) and Omori 1/t^p laws on ground-truth SOC
data, then apply SAME pipeline to other domains for the project's V4 claim.

Output:
  - catalog.parquet  (one row per event)
  - catalog.jsonl    (fallback if pyarrow missing)
  - fetch_log.json   (run metadata)
"""

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

OUT_DIR = Path(__file__).resolve().parent
CATALOG_PARQUET = OUT_DIR / "catalog.parquet"
CATALOG_JSONL = OUT_DIR / "catalog.jsonl"
LOG_FILE = OUT_DIR / "fetch_log.json"

API = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Config
START = date(2020, 1, 1)
END = date(2025, 1, 1)
MIN_MAG = 3.5
BATCH_DAYS = 30  # month batches — USGS caps per query at 20000 events


def daterange_batches(start: date, end: date, step_days: int):
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=step_days), end)
        yield cur, nxt
        cur = nxt


def fetch_one(start_iso: str, end_iso: str, retries: int = 3) -> list:
    params = {
        "format": "geojson",
        "starttime": start_iso,
        "endtime": end_iso,
        "minmagnitude": MIN_MAG,
        "orderby": "time-asc",
    }
    for attempt in range(retries):
        try:
            r = requests.get(API, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            features = data.get("features", [])
            return features
        except Exception as e:
            wait = 2 ** attempt
            print(f"  retry {attempt + 1}/{retries} after {wait}s — {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(wait)
    print(f"  FAILED after {retries} retries for {start_iso}..{end_iso}", file=sys.stderr)
    return []


def flatten(feat: dict) -> dict:
    props = feat.get("properties") or {}
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates") or [None, None, None]
    return {
        "id": feat.get("id"),
        "time_ms": props.get("time"),
        "time_iso": (
            datetime.utcfromtimestamp(props["time"] / 1000).isoformat() + "Z"
            if props.get("time") is not None
            else None
        ),
        "mag": props.get("mag"),
        "magType": props.get("magType"),
        "place": props.get("place"),
        "lon": coords[0],
        "lat": coords[1],
        "depth_km": coords[2],
        "type": props.get("type"),
        "sig": props.get("sig"),
        "tsunami": props.get("tsunami"),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    batches_done = 0
    all_rows = []

    print(f"Fetching USGS catalog {START} → {END}, min_mag={MIN_MAG}, batches of {BATCH_DAYS}d")

    for a, b in daterange_batches(START, END, BATCH_DAYS):
        sa = a.isoformat()
        sb = b.isoformat()
        feats = fetch_one(sa, sb)
        rows = [flatten(f) for f in feats]
        all_rows.extend(rows)
        total += len(rows)
        batches_done += 1
        print(f"  [{sa}..{sb})  events={len(rows):5d}  cumulative={total}")
        time.sleep(0.25)  # light courtesy throttle

    # Save JSONL as canonical (always works)
    with CATALOG_JSONL.open("w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Try parquet
    parquet_ok = False
    try:
        import pandas as pd
        df = pd.DataFrame(all_rows)
        try:
            df.to_parquet(CATALOG_PARQUET, index=False)
            parquet_ok = True
        except Exception as e:
            print(f"  parquet save skipped: {type(e).__name__}: {e}", file=sys.stderr)
    except Exception:
        pass

    log = {
        "start": str(START),
        "end": str(END),
        "min_mag": MIN_MAG,
        "batch_days": BATCH_DAYS,
        "batches": batches_done,
        "total_events": total,
        "parquet_saved": parquet_ok,
        "jsonl_path": str(CATALOG_JSONL),
        "run_finished_at": datetime.utcnow().isoformat() + "Z",
    }
    LOG_FILE.write_text(json.dumps(log, indent=2))

    print()
    print(f"DONE: {total} events across {batches_done} batches")
    print(f"  JSONL: {CATALOG_JSONL}")
    if parquet_ok:
        print(f"  Parquet: {CATALOG_PARQUET}")
    print(f"  Log:   {LOG_FILE}")


if __name__ == "__main__":
    main()
