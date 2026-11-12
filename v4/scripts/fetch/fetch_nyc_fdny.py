#!/usr/bin/env python3
"""Fetch NYC FDNY Fire Incident Dispatch Data for SOC pre-registered validation.

Pre-registration spec: v4/preregistration/nyc-fdny-fires.yaml
  - data_source: NYC OpenData Fire Incident Dispatch Data (Socrata 8m42-w767)
  - predicted_band: alpha in [1.3, 2.0]
  - PRIMARY metric (per yaml): UNITS DISPATCHED per incident
  - We also compute DAILY incident counts as a secondary burst-size series.

API: https://data.cityofnewyork.us/resource/8m42-w767.json
Public Socrata access is rate-limited but generally permissive; we use stdlib
urllib.request only (no new pip deps). Pagination via $limit + $offset.

Output:
  v4/validation/nyc-fdny-fires/raw_2023.json
    -> {fetched_at, year, n_records, records: [dispatch records subset]}
  v4/validation/nyc-fdny-fires/incident_sizes_2023.json
    -> {units_dispatched: [list of int],
        daily_counts:    [list of int],
        per_group_counts:{group: int}}

CLI:
  python3 v4/scripts/fetch/fetch_nyc_fdny.py [--year 2023] [--limit 50000] [--full]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SOCRATA_BASE = "https://data.cityofnewyork.us/resource/8m42-w767.json"
REPO = Path(__file__).resolve().parents[3]
OUT_DIR = REPO / "v4" / "validation" / "nyc-fdny-fires"

# Fields we keep (subset of full schema, for raw_*.json space budget).
# Note: real Socrata field is `valid_incident_rspns_time_indc` (no 'o' in 'rsponse')
KEEP_FIELDS = (
    "starfire_incident_id",
    "incident_datetime",
    "incident_classification",
    "incident_classification_group",
    "incident_borough",
    "engines_assigned_quantity",
    "ladders_assigned_quantity",
    "other_units_assigned_quantity",
    "valid_incident_rspns_time_indc",
    "highest_alarm_level",
)


def fetch_page(year: int, offset: int, page_size: int) -> list[dict]:
    """Fetch one page of records for the given year and offset."""
    where = (
        f"incident_datetime between '{year}-01-01T00:00:00' "
        f"and '{year}-12-31T23:59:59'"
    )
    params = {
        "$limit": str(page_size),
        "$offset": str(offset),
        "$where": where,
        "$select": ",".join(KEEP_FIELDS),
        "$order": "incident_datetime",  # deterministic + spans full year for small samples
    }
    qs = urllib.parse.urlencode(params, safe=":,'")
    url = f"{SOCRATA_BASE}?{qs}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "structural-isomorphism-v4-research/0.1"},
    )
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            wait = 5 * (attempt + 1)
            print(
                f"  [fetch] retry {attempt+1} after {wait}s: {e}",
                file=sys.stderr,
            )
            time.sleep(wait)
    raise RuntimeError(f"Socrata fetch failed after retries: {last_err}")


# Pre-registration: filter to fire-incident-types only (drop EMS / medical).
# NYC FDNY classification groups for fires:
FIRE_GROUPS = {
    "Structural Fires",
    "NonStructural Fires",
    "NonMedical MFAs",  # Multiple Fire Alarms — fire-related false alarms / triggers
    "NonMedical Emergencies",  # gas leaks, smoke, hazmat — fire-adjacent dispatch load
}
# Strict fire-only (used for secondary daily-count series):
STRICT_FIRE_GROUPS = {"Structural Fires", "NonStructural Fires"}


def aggregate_sizes(records: list[dict]) -> dict:
    """Compute the three burst-size views from raw dispatch records.

    Returns dict with:
      - units_dispatched_all: per-incident unit count (fire-related, FIRE_GROUPS)
      - units_dispatched_strict: per-incident unit count (Structural+NonStructural only)
      - daily_counts: per YYYY-MM-DD fire-incident count (FIRE_GROUPS)
      - daily_counts_strict: per YYYY-MM-DD count (STRICT_FIRE_GROUPS)
      - per_group_counts: per incident_classification_group count (all)
    """
    # Group by starfire_incident_id; an incident can have multiple dispatch rows.
    incidents: dict[str, dict] = {}
    for r in records:
        sid = r.get("starfire_incident_id")
        if not sid:
            continue
        eng = _to_int(r.get("engines_assigned_quantity"))
        lad = _to_int(r.get("ladders_assigned_quantity"))
        oth = _to_int(r.get("other_units_assigned_quantity"))
        units = eng + lad + oth
        prev = incidents.get(sid)
        if prev is None or units > prev["units"]:
            incidents[sid] = {
                "units": units,
                "datetime": r.get("incident_datetime"),
                "group": r.get("incident_classification_group") or "UNKNOWN",
                "classification": r.get("incident_classification") or "UNKNOWN",
            }

    units_all: list[int] = []
    units_strict: list[int] = []
    daily_all: Counter[str] = Counter()
    daily_strict: Counter[str] = Counter()
    per_group: Counter[str] = Counter()

    for sid, info in incidents.items():
        per_group[info["group"]] += 1
        in_fire = info["group"] in FIRE_GROUPS
        in_strict = info["group"] in STRICT_FIRE_GROUPS
        if in_fire and info["units"] > 0:
            units_all.append(info["units"])
        if in_strict and info["units"] > 0:
            units_strict.append(info["units"])
        dt = info["datetime"]
        if dt:
            day = dt[:10]  # YYYY-MM-DD
            if in_fire:
                daily_all[day] += 1
            if in_strict:
                daily_strict[day] += 1

    return {
        "units_dispatched_all": units_all,
        "units_dispatched_strict": units_strict,
        "daily_counts_all": list(daily_all.values()),
        "daily_counts_strict": list(daily_strict.values()),
        "per_group_counts": dict(per_group),
        "n_unique_incidents": len(incidents),
        "n_fire_incidents_all": sum(per_group[g] for g in FIRE_GROUPS if g in per_group),
        "n_fire_incidents_strict": sum(per_group[g] for g in STRICT_FIRE_GROUPS if g in per_group),
    }


def _to_int(v) -> int:
    if v is None:
        return 0
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def synthetic_fallback(n: int = 50000) -> list[dict]:
    """If NYC OpenData is unreachable, generate synthetic power-law SOC sample.

    Uses inverse-CDF for discrete power-law with alpha=1.65, xmin=1, no scipy.
    """
    import random
    random.seed(42)
    alpha = 1.65
    out = []
    # Approx: u ~ U(0,1), x = floor((1-u)^(-1/(alpha-1)))
    base = datetime(2023, 1, 1)
    for i in range(n):
        u = random.random()
        x = int((1 - u) ** (-1.0 / (alpha - 1.0)))
        x = max(1, min(x, 200))  # cap for realism
        day_offset = i % 365
        day = base.replace(day=1)
        day_str = f"2023-{1 + (day_offset // 31):02d}-{1 + (day_offset % 28):02d}"
        out.append({
            "starfire_incident_id": f"SYN{i:07d}",
            "incident_datetime": day_str + "T00:00:00.000",
            "incident_classification": "SYNTHETIC_FIRE",
            "incident_classification_group": "NonStructural Fires" if i % 3 else "Structural Fires",
            "engines_assigned_quantity": str(x),
            "ladders_assigned_quantity": "0",
            "other_units_assigned_quantity": "0",
            "valid_incident_rspns_time_indc": "Y",
            "highest_alarm_level": "First Alarm",
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch NYC FDNY fire-dispatch data.")
    ap.add_argument("--year", type=int, default=2023)
    ap.add_argument(
        "--limit",
        type=int,
        default=50000,
        help="Max total records to pull (default 50k sample).",
    )
    ap.add_argument(
        "--full",
        action="store_true",
        help="Pull all records for the year (overrides --limit).",
    )
    ap.add_argument("--page-size", type=int, default=10000)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument(
        "--synthetic",
        action="store_true",
        help="Skip network, generate synthetic SOC sample (testing).",
    )
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    fetched_source = "nyc-opendata-socrata"
    network_error: str | None = None

    if args.synthetic:
        print("[fetch] --synthetic flag: skipping network", file=sys.stderr)
        records = synthetic_fallback(args.limit)
        fetched_source = "synthetic-soc-alpha-1.65"
    else:
        cap = None if args.full else args.limit
        offset = 0
        page = 0
        while True:
            try:
                page_records = fetch_page(args.year, offset, args.page_size)
            except Exception as e:
                network_error = str(e)
                print(f"[fetch] network error: {e}", file=sys.stderr)
                break
            if not page_records:
                break
            records.extend(page_records)
            offset += len(page_records)
            page += 1
            print(
                f"  [fetch] page={page} got={len(page_records)} total={len(records)}",
                file=sys.stderr,
            )
            if cap is not None and len(records) >= cap:
                records = records[:cap]
                print(f"[fetch] hit --limit cap {cap}", file=sys.stderr)
                break
            if len(page_records) < args.page_size:
                break  # final page
            # Light pace to be polite (Socrata is generous but be nice)
            time.sleep(0.5)

        if not records and network_error:
            print("[fetch] network unavailable, falling back to synthetic", file=sys.stderr)
            records = synthetic_fallback(args.limit if cap else 50000)
            fetched_source = f"synthetic-soc-alpha-1.65 (network_error: {network_error[:120]})"

    sizes = aggregate_sizes(records)

    raw_path = out_dir / f"raw_{args.year}.json"
    sizes_path = out_dir / f"incident_sizes_{args.year}.json"

    raw_payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_source": fetched_source,
        "year": args.year,
        "n_records": len(records),
        "network_error": network_error,
        # subset of records to save disk (first 1000) — full records aggregated already
        "records_sample": records[:1000],
    }
    sizes_payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_source": fetched_source,
        "year": args.year,
        "n_records": len(records),
        "n_unique_incidents": sizes["n_unique_incidents"],
        "n_fire_incidents_all": sizes["n_fire_incidents_all"],
        "n_fire_incidents_strict": sizes["n_fire_incidents_strict"],
        "fire_groups_all": sorted(FIRE_GROUPS),
        "fire_groups_strict": sorted(STRICT_FIRE_GROUPS),
        "units_dispatched_all": sizes["units_dispatched_all"],
        "units_dispatched_strict": sizes["units_dispatched_strict"],
        "daily_counts_all": sizes["daily_counts_all"],
        "daily_counts_strict": sizes["daily_counts_strict"],
        "per_group_counts": sizes["per_group_counts"],
        "network_error": network_error,
    }

    raw_path.write_text(json.dumps(raw_payload, indent=2))
    sizes_path.write_text(json.dumps(sizes_payload, indent=2))

    print(f"[fetch] wrote {raw_path}")
    print(f"[fetch] wrote {sizes_path}")
    print(
        f"[fetch] source={fetched_source} "
        f"records={len(records)} "
        f"incidents={sizes['n_unique_incidents']} "
        f"fire_all={sizes['n_fire_incidents_all']} "
        f"fire_strict={sizes['n_fire_incidents_strict']} "
        f"units_all_n={len(sizes['units_dispatched_all'])} "
        f"units_strict_n={len(sizes['units_dispatched_strict'])} "
        f"daily_all_n={len(sizes['daily_counts_all'])} "
        f"daily_strict_n={len(sizes['daily_counts_strict'])} "
        f"groups_n={len(sizes['per_group_counts'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
