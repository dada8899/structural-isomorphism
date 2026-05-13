"""
fetch_lake_data.py — USGS NWIS dissolved oxygen (DO) time series fetch
for Scheffer fold-bifurcation regime-shift validation (V4 taxonomy class #3).

Targets:
  - Primary: Fox River at Green Bay, WI (USGS 040851385) — eutrophic Green Bay embayment
  - Secondary: Manitowoc River at Manitowoc, WI (USGS 04085427)
  - Tertiary (true lake): tries Lake Jesup FL / Delavan Lake WI; falls back if empty.

NWIS daily-value endpoint:
  https://waterservices.usgs.gov/nwis/dv/?format=json&sites=<id>&parameterCd=00300&startDT=<>&endDT=<>&statCd=00003
  parameterCd 00300 = Dissolved oxygen (mg/L), statCd 00003 = daily mean.

Fallback: synthetic fold-bifurcation simulation if no real site yields >= 2 years continuous.

Output: lake_do_timeseries.jsonl — one record per day with site_code, date, do_mg_l, qualifier.
        fetch_log.json — per-site fetch metadata + decision audit.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
OUT_JSONL = OUT_DIR / "lake_do_timeseries.jsonl"
OUT_LOG = OUT_DIR / "fetch_log.json"

# Candidate sites: (site_code, descriptor, start_year)
CANDIDATE_SITES = [
    ("040851385", "Fox River at Green Bay, WI (eutrophic embayment, primary)", 2008),
    ("04085427", "Manitowoc River at Manitowoc, WI (cross-site check)", 2008),
    ("02234432", "Lake Jesup, FL (true LK siteType)", 2005),
    ("423755088341700", "Delavan Lake Inlet, WI (true LK siteType)", 2000),
]

NWIS_DV = "https://waterservices.usgs.gov/nwis/dv/"
USER_AGENT = "structural-isomorphism-v4/scheffer-lake (research)"


def fetch_one(site_code: str, start_year: int, end_year: int = 2024) -> dict:
    """Fetch USGS daily-value DO. Returns parsed dict + success metadata."""
    url = (
        f"{NWIS_DV}?format=json&sites={site_code}"
        f"&parameterCd=00300&startDT={start_year}-01-01&endDT={end_year}-12-31&statCd=00003"
    )
    meta = {
        "site_code": site_code,
        "url": url,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "ok": False,
        "n_records": 0,
        "site_name": None,
        "first_date": None,
        "last_date": None,
        "error": None,
    }
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
        data = json.loads(raw)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return {"meta": meta, "records": []}

    ts_list = data.get("value", {}).get("timeSeries", [])
    if not ts_list:
        meta["error"] = "empty timeSeries"
        return {"meta": meta, "records": []}

    ts = ts_list[0]
    src = ts.get("sourceInfo", {})
    meta["site_name"] = src.get("siteName")
    values = ts.get("values", [{}])[0].get("value", [])

    records = []
    for v in values:
        try:
            val = float(v["value"])
        except (TypeError, ValueError):
            continue
        if val < -1e5 or val > 1e5:  # USGS sometimes uses -999999 sentinel
            continue
        date_str = v["dateTime"][:10]
        records.append({
            "site_code": site_code,
            "site_name": meta["site_name"],
            "date": date_str,
            "do_mg_l": val,
            "qualifiers": v.get("qualifiers", []),
        })

    if records:
        meta["ok"] = True
        meta["n_records"] = len(records)
        meta["first_date"] = records[0]["date"]
        meta["last_date"] = records[-1]["date"]
    else:
        meta["error"] = "no parseable values"
    return {"meta": meta, "records": records}


def synthetic_fold(n_days: int = 4000, seed: int = 42) -> list[dict]:
    """
    Saddle-node (fold) bifurcation demo:
      dP/dt = a - b*P + r * P^2 / (K^2 + P^2) + sigma * noise
    where P is nutrient (phosphorus proxy, mg/L); we monitor DO ~ inversely
    related to P via DO = DO_max - k*P + measurement noise.

    Slowly increase 'a' (nutrient loading) over time so system crosses fold
    at ~day 2500 → sudden transition from oligotrophic (low P, high DO)
    to eutrophic (high P, low DO) state.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    dt = 1.0
    P = np.zeros(n_days)
    P[0] = 0.3  # oligotrophic start
    # bifurcation parameter a ramped from 0.4 -> 1.2 across the run
    a_path = np.linspace(0.4, 1.2, n_days)
    b = 1.0
    r = 1.0
    K = 1.0
    sigma = 0.05
    for t in range(1, n_days):
        dP = (a_path[t] - b * P[t-1] + r * P[t-1]**2 / (K**2 + P[t-1]**2)) * dt
        P[t] = P[t-1] + dP + sigma * rng.standard_normal()
        if P[t] < 0:
            P[t] = 0.0
    DO_max = 12.0
    k = 4.0
    DO = DO_max - k * P + rng.normal(0.0, 0.2, n_days)
    DO = np.clip(DO, 0.0, 15.0)
    start = datetime(2008, 1, 1)
    records = []
    for i in range(n_days):
        d = start + timedelta(days=i)
        records.append({
            "site_code": "SYNTHETIC_FOLD",
            "site_name": "synthetic fold-bifurcation simulation (Scheffer canonical model)",
            "date": d.strftime("%Y-%m-%d"),
            "do_mg_l": float(DO[i]),
            "qualifiers": ["S"],
            "synthetic_P": float(P[i]),
            "synthetic_a": float(a_path[i]),
        })
    return records


def main() -> int:
    audit = {"attempts": [], "chosen": None, "fallback_used": False,
             "started_at": datetime.utcnow().isoformat() + "Z"}
    chosen_records: list[dict] = []
    chosen_site = None

    for site, descriptor, start_year in CANDIDATE_SITES:
        print(f"[fetch] trying {site}: {descriptor}", file=sys.stderr)
        result = fetch_one(site, start_year)
        result["meta"]["descriptor"] = descriptor
        audit["attempts"].append(result["meta"])
        # require >= 2 years of records to call it usable
        if result["meta"]["ok"] and result["meta"]["n_records"] >= 700:
            print(f"[fetch]   OK n={result['meta']['n_records']}, "
                  f"{result['meta']['first_date']} -> {result['meta']['last_date']}",
                  file=sys.stderr)
            if chosen_site is None:
                chosen_records = result["records"]
                chosen_site = site
                audit["chosen"] = {
                    "site_code": site,
                    "descriptor": descriptor,
                    "n_records": result["meta"]["n_records"],
                    "first_date": result["meta"]["first_date"],
                    "last_date": result["meta"]["last_date"],
                    "site_name": result["meta"]["site_name"],
                }
        else:
            print(f"[fetch]   skip ({result['meta'].get('error', 'too short')})",
                  file=sys.stderr)
        time.sleep(0.5)  # be polite

    if chosen_site is None:
        print("[fetch] no candidate site yielded >=700 days; using SYNTHETIC fold model",
              file=sys.stderr)
        chosen_records = synthetic_fold(n_days=4000)
        chosen_site = "SYNTHETIC_FOLD"
        audit["fallback_used"] = True
        audit["chosen"] = {
            "site_code": "SYNTHETIC_FOLD",
            "descriptor": "fold-bifurcation simulation (Scheffer canonical model)",
            "n_records": len(chosen_records),
            "first_date": chosen_records[0]["date"],
            "last_date": chosen_records[-1]["date"],
            "site_name": "SYNTHETIC",
        }

    with OUT_JSONL.open("w") as f:
        for r in chosen_records:
            f.write(json.dumps(r) + "\n")

    audit["finished_at"] = datetime.utcnow().isoformat() + "Z"
    audit["n_written"] = len(chosen_records)
    audit["out_path"] = str(OUT_JSONL)
    with OUT_LOG.open("w") as f:
        json.dump(audit, f, indent=2)

    print(f"[fetch] wrote {len(chosen_records)} records -> {OUT_JSONL.name}",
          file=sys.stderr)
    print(f"[fetch] chosen site: {chosen_site} (fallback={audit['fallback_used']})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
