#!/usr/bin/env python3
"""Fetch NOAA NGDC GOES X-ray flare catalog 2000-2016.

URL pattern:
    https://www.ngdc.noaa.gov/stp/space-weather/solar-data/solar-features/
        solar-flares/x-rays/goes/xrs/goes-xrs-report_YYYY.txt

Fixed-width format per line:
    Col  1-11  : event ID prefix (e.g. 31777160101 → 2016-01-01)
    Col 13-16  : start time HHMM
    Col 18-21  : end time HHMM
    Col 23-26  : peak time HHMM
    Col 28-34  : heliographic location (e.g. S19W67)
    Col 60     : flare class letter (A/B/C/M/X)
    Col 62-63  : flare class subnumber (e.g. 62 = 6.2)
    Col 65-67  : GOES satellite
    Col 69-75  : integrated 1-8Å flux (J/m²)
    Col 77-81  : NOAA active region

We extract: peak_time, class, peak_flux_W_m2 (derived from class letter+subnumber).

Output: flares.jsonl
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

OUT = Path(__file__).parent / "flares.jsonl"
LOG = Path(__file__).parent / "fetch_log.json"
BASE = (
    "https://www.ngdc.noaa.gov/stp/space-weather/solar-data/solar-features/"
    "solar-flares/x-rays/goes/xrs/goes-xrs-report_{year}.txt"
)
YEARS = list(range(2000, 2017))  # 2000-2016 inclusive

CLASS_BASE_FLUX = {
    "A": 1e-8,
    "B": 1e-7,
    "C": 1e-6,
    "M": 1e-5,
    "X": 1e-4,
}


def parse_line(line: str, default_year: int) -> dict | None:
    """Parse one GOES XRS report line. Returns None if unparseable."""
    if len(line) < 60:
        return None
    # Date prefix: positions 5-10 (0-based 5,6 = YY, 7,8 = MM, 9,10 = DD)
    # Example "31777160101" → 16=YY, 01=MM, 01=DD
    prefix = line[:11].strip()
    # Take last 6 chars of prefix (YYMMDD)
    if len(prefix) < 6:
        return None
    ymd = prefix[-6:]
    try:
        yy = int(ymd[:2])
        mm = int(ymd[2:4])
        dd = int(ymd[4:6])
        # NGDC uses 2-digit year. <50 → 20YY, else 19YY.
        year = 2000 + yy if yy < 50 else 1900 + yy
        # cross-check year
        if year != default_year and year != default_year - 1 and year != default_year + 1:
            return None
    except ValueError:
        return None

    try:
        peak_hhmm = line[23:27].strip()
        if not peak_hhmm or not peak_hhmm.isdigit():
            return None
        hh = int(peak_hhmm[:2])
        mn = int(peak_hhmm[2:4])
        if hh > 23 or mn > 59:
            return None
        peak_ts = datetime(year, mm, dd, hh, mn).timestamp()
    except (ValueError, IndexError):
        return None

    cls_letter = line[59:60].strip().upper()
    if cls_letter not in CLASS_BASE_FLUX:
        return None
    try:
        # Subnumber: positions 61-63 (e.g. " 62" = 6.2)
        sub_str = line[61:64].strip()
        if not sub_str:
            return None
        # "62" → 6.2; "100" → 10.0
        if len(sub_str) >= 3:
            sub = int(sub_str[:2]) + int(sub_str[2]) / 10.0
        else:
            sub = int(sub_str) / 10.0 if len(sub_str) == 2 else float(sub_str)
        if sub < 1.0 or sub > 99.9:
            return None
    except (ValueError, IndexError):
        return None

    peak_flux = CLASS_BASE_FLUX[cls_letter] * sub

    # Integrated flux (J/m²) at position 68-75
    integrated_flux = None
    try:
        if_str = line[68:76].strip()
        if if_str:
            integrated_flux = float(if_str)
    except (ValueError, IndexError):
        integrated_flux = None

    return {
        "peak_time": datetime.fromtimestamp(peak_ts).isoformat(),
        "peak_ts": peak_ts,
        "flare_class": f"{cls_letter}{sub:.1f}",
        "class_letter": cls_letter,
        "class_subnumber": sub,
        "peak_flux_W_m2": peak_flux,
        "integrated_flux_J_m2": integrated_flux,
    }


def fetch_year(year: int, attempts: int = 3) -> tuple[list[dict], dict]:
    url = BASE.format(year=year)
    for k in range(attempts):
        try:
            r = requests.get(url, timeout=30)
        except Exception as e:
            if k == attempts - 1:
                return [], {"year": year, "status": "fail_net", "error": str(e)}
            time.sleep(2)
            continue
        if r.status_code == 200:
            break
        if k == attempts - 1:
            return [], {"year": year, "status": "http_fail", "code": r.status_code}
        time.sleep(2)

    lines = r.text.splitlines()
    parsed = []
    for line in lines:
        rec = parse_line(line, year)
        if rec is not None:
            parsed.append(rec)
    return parsed, {
        "year": year,
        "status": "ok",
        "lines_total": len(lines),
        "events_parsed": len(parsed),
    }


def main() -> int:
    all_events = []
    log = {"per_year": [], "total": 0}
    for year in YEARS:
        print(f"[fetch] {year} ...", end="", flush=True)
        events, info = fetch_year(year)
        log["per_year"].append(info)
        print(f" {info['status']} (events={info.get('events_parsed', 0)})")
        all_events.extend(events)
        time.sleep(0.3)  # be gentle to NOAA

    # Dedup by (peak_ts, class_letter, subnumber) — same event may appear twice if multiple GOES satellites recorded it
    seen = set()
    deduped = []
    for e in all_events:
        key = (round(e["peak_ts"]), e["class_letter"], round(e["class_subnumber"], 1))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    deduped.sort(key=lambda e: e["peak_ts"])
    log["total"] = len(deduped)
    log["after_dedup_dropped"] = len(all_events) - len(deduped)

    with OUT.open("w") as f:
        for e in deduped:
            f.write(json.dumps(e) + "\n")
    LOG.write_text(json.dumps(log, indent=2))
    print(f"\n[fetch] wrote {len(deduped)} unique flares to {OUT}")
    print(f"[fetch] log: {LOG}")
    # Quick class distribution
    from collections import Counter
    dist = Counter(e["class_letter"] for e in deduped)
    print(f"[fetch] class distribution: {dict(dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
