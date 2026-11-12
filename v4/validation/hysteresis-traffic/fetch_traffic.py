"""Fetch traffic flow/density data for A2-Hysteresis validation.

Source priority:
  1. Caltrans PeMS — paywall (requires account); SKIP.
  2. NGSIM US-101 trajectory data via Socrata Open Data API
     (https://data.transportation.gov/resource/8ect-6jqj). Aggregate
     server-side into lane x 30-second x 200-foot cells, then convert
     per-cell vehicle counts and mean speeds into (rho, q) via Edie's
     generalized definitions.
  3. Literature replication: Treiber & Kesting 2013 chap.8 calibrated
     fundamental-diagram numbers (q_c1~2200, q_c2~1500-1700 veh/h/lane)
     and Geroliminis & Daganzo 2008 Yokohama macroscopic numbers.

Outputs:
  - us101_ngsim_agg_raw.csv (already pre-fetched on 2026-05-13)
  - traffic_qrho.jsonl (per-cell rho, q records derived from NGSIM)
  - literature_fallback.json (always written, used when NGSIM-derived
    data has insufficient free- or jam-branch points)
"""

from __future__ import annotations

import csv
import json
import math
import sys
import urllib.request
from pathlib import Path

# ---- constants ----
HERE = Path(__file__).parent
NGSIM_RAW = HERE / "us101_ngsim_agg_raw.csv"
QRHO_OUT = HERE / "traffic_qrho.jsonl"
LIT_OUT = HERE / "literature_fallback.json"

# NGSIM US-101 frame rate (Hz). Each row in raw trajectory dataset is
# one (vehicle, frame) sample at 10 Hz, i.e. 0.1 s of vehicle time.
NGSIM_DT_S = 0.1

# Aggregation cell parameters (must match SoQL query that produced raw CSV).
T_BIN_S = 30.0  # seconds per time bin
S_BIN_FT = 200.0  # feet per space bin
FT_PER_MILE = 5280.0


def fetch_ngsim_aggregated(
    limit: int = 50000, force: bool = False
) -> Path:
    """Re-fetch aggregated NGSIM US-101 cells via SoQL if not present.

    The pre-fetched copy at us101_ngsim_agg_raw.csv was generated
    2026-05-13 with the SoQL query embedded in this function. We keep
    the fetch capability for reproducibility but skip by default if
    the file already exists.
    """
    if NGSIM_RAW.exists() and not force:
        print(f"[fetch_ngsim] cached: {NGSIM_RAW} ({NGSIM_RAW.stat().st_size} B)")
        return NGSIM_RAW

    # SoQL: server-side group by lane x 30-s time bin x 200-ft space bin
    # Time origin = 1118846979700 ms (min global_time on US-101).
    soql = (
        "select lane_id, "
        "floor((global_time - 1118846979700)/30000) as t_bin, "
        "floor(local_y/200) as s_bin, "
        "count(*) as n_obs, "
        "avg(v_vel) as v_mean "
        "where location='us-101' "
        "group by lane_id, t_bin, s_bin "
        f"limit {limit}"
    )
    url = (
        "https://data.transportation.gov/resource/8ect-6jqj.csv?$query="
        + urllib.parse.quote(soql)
    )
    print(f"[fetch_ngsim] GET {url[:90]}...")
    with urllib.request.urlopen(url, timeout=120) as resp:
        body = resp.read()
    NGSIM_RAW.write_bytes(body)
    print(f"[fetch_ngsim] wrote {NGSIM_RAW} ({len(body)} B)")
    return NGSIM_RAW


def edie_qrho_per_cell(n_obs: int, v_mean_fts: float) -> tuple[float, float]:
    """Convert NGSIM cell stats (n_obs samples at 10 Hz, mean speed ft/s)
    into Edie's macroscopic density and flow.

    Edie's definitions for an observation region of size T (seconds) by
    X (feet):
        rho = (sum of vehicle-time inside region) / (T * X)
        q   = (sum of vehicle-distance inside region) / (T * X)

    For 10-Hz frame sampling, each vehicle frame contributes 0.1 s of
    vehicle-time and 0.1*v ft of vehicle-distance.

    Returns (rho_veh_per_mile_per_lane, q_veh_per_hour_per_lane).
    Speeds are per-lane; we report per-lane density and per-lane flow.
    """
    veh_time_s = n_obs * NGSIM_DT_S
    veh_dist_ft = n_obs * NGSIM_DT_S * v_mean_fts
    cell_area_s_ft = T_BIN_S * S_BIN_FT  # vehicle-second-feet
    # rho [veh / ft] = veh-time / (T*X)
    rho_per_ft = veh_time_s / cell_area_s_ft
    rho_per_mile = rho_per_ft * FT_PER_MILE
    # q [veh / s] = veh-dist / (T*X)
    q_per_s = veh_dist_ft / cell_area_s_ft
    q_per_h = q_per_s * 3600.0
    return rho_per_mile, q_per_h


def derive_qrho_from_ngsim(min_n_obs: int = 30) -> tuple[list[dict], dict]:
    """Read aggregated CSV and emit (rho, q) per cell.

    Filters out cells with very few samples (likely lane boundary or
    end-of-segment artifacts).

    Returns (records, summary).
    """
    records: list[dict] = []
    with NGSIM_RAW.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lane = int(row["lane_id"])
                t_bin = int(row["t_bin"])
                s_bin = int(row["s_bin"])
                n_obs = int(row["n_obs"])
                v_mean = float(row["v_mean"])  # ft/s
            except (KeyError, ValueError):
                continue
            if n_obs < min_n_obs:
                continue
            # restrict to mainline lanes 1-5 (US-101 has 5 mainline + 2 aux)
            if lane < 1 or lane > 5:
                continue
            rho, q = edie_qrho_per_cell(n_obs, v_mean)
            # convert per-mile to per-km for consistency with literature
            rho_per_km = rho / 1.609
            records.append(
                {
                    "lane_id": lane,
                    "t_bin": t_bin,
                    "s_bin": s_bin,
                    "n_obs": n_obs,
                    "v_mean_fts": v_mean,
                    "v_mean_kmh": v_mean * 0.3048 * 3.6,
                    "rho_veh_per_km": rho_per_km,
                    "q_veh_per_h": q,
                }
            )
    if records:
        rhos = [r["rho_veh_per_km"] for r in records]
        qs = [r["q_veh_per_h"] for r in records]
        summary = {
            "n_cells": len(records),
            "rho_range": [min(rhos), max(rhos)],
            "q_range": [min(qs), max(qs)],
            "v_range_kmh": [
                min(r["v_mean_kmh"] for r in records),
                max(r["v_mean_kmh"] for r in records),
            ],
        }
    else:
        summary = {"n_cells": 0}
    return records, summary


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def write_literature_fallback() -> dict:
    """Hardcoded calibrated fundamental-diagram numbers from textbooks.

    These are NOT used unless NGSIM-derived data fails the minimum
    free-branch (>=50) and jam-branch (>=50) point thresholds.

    Sources:
      - Treiber & Kesting 2013 "Traffic Flow Dynamics" textbook,
        chap.8 table 8.1: per-lane capacities on German A5 motorway.
      - Geroliminis & Daganzo 2008 Transp.Res.B 42: Yokohama
        macroscopic fundamental diagram (network-aggregated).
    """
    payload = {
        "treiber2013_chap8_a5_motorway": {
            "q_c1_veh_per_h_per_lane": 2200.0,
            "q_c2_veh_per_h_per_lane": 1600.0,  # midpoint of 1500-1700
            "ratio": 2200.0 / 1600.0,
            "rho_crit_veh_per_km_per_lane": 25.0,
            "v_free_kmh": 110.0,
            "source": "Treiber & Kesting 2013 chap.8 table 8.1",
        },
        "geroliminis2008_yokohama_mfd": {
            # Network-level MFD; numbers are per-intersection capacity,
            # not per-lane. Used as a second literature anchor.
            "q_c1_veh_per_h": 18.0,
            "q_c2_veh_per_h": 13.0,
            "ratio": 18.0 / 13.0,
            "source": (
                "Geroliminis & Daganzo 2008 Transp.Res.B 42 Yokohama MFD"
            ),
        },
    }
    LIT_OUT.write_text(json.dumps(payload, indent=2))
    return payload


def main() -> int:
    print("== A2-Hysteresis traffic fetch ==")
    fetch_ngsim_aggregated()
    records, summary = derive_qrho_from_ngsim()
    write_jsonl(QRHO_OUT, records)
    lit = write_literature_fallback()
    print(
        f"[derive] NGSIM cells={summary['n_cells']}, "
        f"rho range={summary.get('rho_range')}, "
        f"q range={summary.get('q_range')}"
    )
    print(f"[literature] anchors: {list(lit.keys())}")
    print(f"[output] {QRHO_OUT}")
    print(f"[output] {LIT_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
