#!/usr/bin/env python3
"""Fetch + normalize NIFC InteragencyFirePerimeterHistory wildfire catalog.

Source:
    https://opendata.arcgis.com/api/v3/datasets/
        5e72b1699bf74eefb3f3aff6f4ba5511_0/downloads/data?format=csv&spatialRefId=4326
    (WFIGS Interagency Fire Perimeters; ~21k US fires 2010s-2024)

Output:
    fires.jsonl — one event per line:
        {"id": "...", "name": "...", "date": "YYYY-MM-DD", "size_acres": float}

Size source preference (first non-null wins):
    1. attr_FinalAcres          (post-incident final figure)
    2. attr_CalculatedAcres     (calculated from geometry)
    3. attr_IncidentSize        (running incident report)
    4. poly_GISAcres            (raw GIS perimeter)
    5. poly_Acres_AutoCalc      (auto-calc fallback)

Date source preference:
    1. attr_FireDiscoveryDateTime
    2. attr_ContainmentDateTime
    3. poly_PolygonDateTime
    4. poly_CreateDate

Filters:
    - drop size <= 0 (perimeter glitches / unburned polygons)
    - drop missing date (cannot place on timeline)
    - dedupe by (name, year, rounded_size) to remove repeated perimeter snapshots
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RAW = Path(__file__).parent / "raw_nifc.csv"
OUT = Path(__file__).parent / "fires.jsonl"

SIZE_FIELDS = (
    "attr_FinalAcres",
    "attr_CalculatedAcres",
    "attr_IncidentSize",
    "poly_GISAcres",
    "poly_Acres_AutoCalc",
)
DATE_FIELDS = (
    "attr_FireDiscoveryDateTime",
    "attr_ContainmentDateTime",
    "poly_PolygonDateTime",
    "poly_CreateDate",
)


def _parse_float(s: str) -> float | None:
    if s is None or s == "":
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if v != v or v <= 0:  # NaN or non-positive
        return None
    return v


def _parse_date(s: str) -> str | None:
    """Accept '2022/11/19 03:32:33+00' or ISO; return YYYY-MM-DD."""
    if not s:
        return None
    s = s.strip()
    # Handle '2022/11/19 03:32:33+00' style
    if "/" in s[:10]:
        date_part = s.split(" ", 1)[0]
        try:
            y, m, d = date_part.split("/")
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except (ValueError, IndexError):
            return None
    # ISO style
    if "-" in s[:10] and "T" in s[:11]:
        return s[:10]
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def main() -> int:
    if not RAW.exists():
        print(f"ERROR: missing {RAW}", file=sys.stderr)
        print("Download with:", file=sys.stderr)
        print(
            '  curl -L -o raw_nifc.csv '
            '"https://opendata.arcgis.com/api/v3/datasets/'
            "5e72b1699bf74eefb3f3aff6f4ba5511_0/downloads/data"
            '?format=csv&spatialRefId=4326"',
            file=sys.stderr,
        )
        return 1

    print(f"[fetch] reading {RAW.name}")
    seen: set[tuple[str, str, int]] = set()
    written = 0
    skipped_size = 0
    skipped_date = 0
    skipped_dup = 0

    with RAW.open(encoding="utf-8-sig") as fh, OUT.open("w") as out:
        reader = csv.DictReader(fh)
        for row in reader:
            size = None
            for f in SIZE_FIELDS:
                size = _parse_float(row.get(f, ""))
                if size is not None:
                    break
            if size is None:
                skipped_size += 1
                continue

            date = None
            for f in DATE_FIELDS:
                date = _parse_date(row.get(f, ""))
                if date is not None:
                    break
            if date is None:
                skipped_date += 1
                continue

            name = (row.get("poly_IncidentName") or row.get("attr_IncidentName") or "UNKNOWN").strip()
            year = date[:4]
            dedup_key = (name.upper(), year, int(round(size)))
            if dedup_key in seen:
                skipped_dup += 1
                continue
            seen.add(dedup_key)

            rec = {
                "id": row.get("attr_IrwinID") or row.get("OBJECTID") or "",
                "name": name,
                "date": date,
                "size_acres": float(size),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

    print(f"[fetch] wrote {written} fires to {OUT.name}")
    print(
        f"[fetch] skipped: size_invalid={skipped_size} "
        f"date_invalid={skipped_date} duplicates={skipped_dup}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
