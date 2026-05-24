#!/usr/bin/env python3
"""
Layer 5 — Phase 3: Omori aftershock decay.

Omori-Utsu law:  n(t) = K / (t + c)^p
Accepted global p ~= 1.0 (range 0.8..1.3).

Pipeline:
  1. Identify main-shock candidates (M >= M_main, default 6.0).
  2. For each main-shock, define a spatial-temporal aftershock window:
     - spatial radius = 10^(0.5*M - 1.2) km (Wells-Coppersmith style)
     - time window = 30 days
  3. Stack all aftershock sequences (time relative to main-shock).
  4. Bin into log-spaced time bins, compute aftershock rate n(t).
  5. Fit n(t) = K / (t + c)^p by least-squares in log space.
  6. Bootstrap p.

Output:
  - omori_results.json
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

OUT_DIR = Path(__file__).resolve().parent
CATALOG = OUT_DIR / "catalog.parquet"
RESULTS = OUT_DIR / "omori_results.json"


MAIN_MAG_MIN = 6.0
AFTERSHOCK_MIN = 4.0    # only count M >= this in aftershock stack (completeness)
TIME_WINDOW_DAYS = 30
# Spatial window scales with main-shock magnitude (rough Utsu scaling)
# radius_km(M) = 10^(0.5*M - 1.2)
def aftershock_radius_km(mag: float) -> float:
    return 10 ** (0.5 * mag - 1.2)


def load_catalog():
    try:
        import pandas as pd
        df = pd.read_parquet(CATALOG)
    except Exception:
        import pandas as pd
        rows = []
        with (OUT_DIR / "catalog.jsonl").open() as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        df = pd.DataFrame(rows)
    if "type" in df.columns:
        df = df[df["type"] == "earthquake"].copy()
    df = df.dropna(subset=["mag", "time_ms", "lon", "lat"]).reset_index(drop=True)
    df["mag"] = df["mag"].astype(float)
    df["time_ms"] = df["time_ms"].astype(float)
    return df


def great_circle_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def stack_aftershocks(df):
    main = df[df["mag"] >= MAIN_MAG_MIN].copy().reset_index(drop=True)
    print(f"  main shocks (M>={MAIN_MAG_MIN}): {len(main)}")

    all_dt_sec = []  # seconds after main shock
    n_main_used = 0

    for i, row in main.iterrows():
        t0 = row["time_ms"] / 1000.0
        lat0, lon0 = row["lat"], row["lon"]
        M = row["mag"]
        r_km = aftershock_radius_km(M)
        t_end = t0 + TIME_WINDOW_DAYS * 86400

        # Select candidates in forward window
        mask = (df["time_ms"] / 1000.0 > t0) & (df["time_ms"] / 1000.0 < t_end) & (df["mag"] >= AFTERSHOCK_MIN) & (df["mag"] < M)
        cand = df[mask]
        if len(cand) == 0:
            continue

        # Filter by great-circle distance
        d = great_circle_km(cand["lat"].values, cand["lon"].values, lat0, lon0)
        within = d < r_km
        after = cand[within]
        if len(after) == 0:
            continue

        dts = after["time_ms"].values / 1000.0 - t0  # seconds
        all_dt_sec.extend(dts.tolist())
        n_main_used += 1

    print(f"  main shocks with aftershocks: {n_main_used}")
    print(f"  total aftershocks stacked: {len(all_dt_sec)}")
    return np.array(all_dt_sec), n_main_used


def fit_omori(dts_sec: np.ndarray, min_sec: float = 300.0, max_sec: float = 10 * 86400):
    """Fit Omori: n(t) = K / (t + c)^p.
    Robust approach:
      1. Bin aftershocks in log-spaced time bins.
      2. Divide by bin width → rate (per unit time) per bin.
      3. Normalize by number of main shocks (stacked rate per shock).
      4. For each candidate c in {0.001, 0.01, 0.05, 0.1} days, fit
         log n = log K - p * log(t + c) by weighted linear regression.
      5. Pick c giving best reduced chi^2 / R^2.
    This avoids the unstable nonlinear optimizer and mirrors common
    seismological practice (Utsu 1961)."""
    if len(dts_sec) < 100:
        return {"error": f"too few aftershocks ({len(dts_sec)}) for Omori fit"}

    dts_sec = dts_sec[(dts_sec >= min_sec) & (dts_sec <= max_sec)]
    if len(dts_sec) == 0:
        return {"error": "no aftershocks in [min_sec, max_sec]"}

    # Log-spaced bins
    n_bins = 24
    bins = np.logspace(math.log10(min_sec), math.log10(max_sec), n_bins + 1)
    centers = np.sqrt(bins[:-1] * bins[1:])  # geometric center
    widths = bins[1:] - bins[:-1]
    counts, _ = np.histogram(dts_sec, bins=bins)
    rate_per_sec = counts / widths
    valid = counts >= 3  # drop bins with too-small counts
    if valid.sum() < 6:
        return {"error": f"too few valid bins ({valid.sum()})"}

    t_sec = centers[valid]
    r = rate_per_sec[valid]
    w = np.sqrt(counts[valid])  # poisson sigma weight

    best = None
    # Grid search over c (days)
    for c_day in [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2]:
        c_sec = c_day * 86400
        x = np.log10(t_sec + c_sec)
        y = np.log10(r)
        # Weighted linear regression: y = a - p*x
        W = w ** 2
        Sw = np.sum(W)
        Sx = np.sum(W * x)
        Sy = np.sum(W * y)
        Sxx = np.sum(W * x * x)
        Sxy = np.sum(W * x * y)
        denom = Sw * Sxx - Sx * Sx
        slope = (Sw * Sxy - Sx * Sy) / denom
        intercept = (Sy - slope * Sx) / Sw
        p = -slope
        logK = intercept
        pred_y = intercept + slope * x
        ss_res = float(np.sum(W * (y - pred_y) ** 2))
        ss_tot = float(np.sum(W * (y - np.average(y, weights=W)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
        # sigma of slope from weighted regression
        residuals = y - pred_y
        dof = max(len(y) - 2, 1)
        mse = float(np.sum(W * residuals ** 2) / dof)
        var_slope = mse * Sw / denom
        sigma_p = float(math.sqrt(abs(var_slope)))
        if best is None or (r2 is not None and r2 > best["R2"]):
            best = {
                "c_days": c_day,
                "p": float(p),
                "p_sigma": sigma_p,
                "logK": float(logK),
                "R2": float(r2) if r2 is not None else None,
            }

    res = {
        "n_aftershocks_in_fit": int(valid.sum()),
        "n_bins_used": int(valid.sum()),
        "t_range_days": [float(t_sec.min() / 86400), float(t_sec.max() / 86400)],
        "c_days": best["c_days"],
        "p": best["p"],
        "p_sigma": best["p_sigma"],
        "logK": best["logK"],
        "R2": best["R2"],
        "predicted_p_range": [0.8, 1.2],
        "p_within_prediction": bool(0.8 <= best["p"] <= 1.2),
    }
    return res


def main():
    print("Loading catalog...")
    df = load_catalog()
    print(f"  total events: {len(df)}")

    print("Stacking aftershocks...")
    dts, n_main = stack_aftershocks(df)

    print("Fitting Omori-Utsu law...")
    res = fit_omori(dts)
    print(f"  fit result: {res}")

    verdict = "CONFIRMED" if res.get("p_within_prediction") else ("INCONCLUSIVE" if "error" in res else "DEVIATING")
    out = {
        "domain": "seismology (global USGS catalog)",
        "predicted_class": "soc_threshold_cascade (Omori law)",
        "time_window": {"start": "2020-01-01", "end": "2025-01-01"},
        "main_mag_min": MAIN_MAG_MIN,
        "aftershock_mag_min": AFTERSHOCK_MIN,
        "spatial_scaling": "r_km = 10^(0.5 M - 1.2) (Utsu rough)",
        "time_window_days": TIME_WINDOW_DAYS,
        "n_main_shocks_total": int((df["mag"] >= MAIN_MAG_MIN).sum()),
        "n_main_shocks_used": int(n_main),
        "n_aftershocks_total": int(len(dts)),
        "fit": res,
        "verdict": verdict,
        "method_refs": [
            "Omori 1894",
            "Utsu 1961 / Utsu-Ogata-Matsu'ura 1995",
            "Wells-Coppersmith 1994 (aftershock spatial scaling)",
        ],
    }
    RESULTS.write_text(json.dumps(out, indent=2))
    print()
    print(f"VERDICT: {verdict}")
    if "p" in res:
        print(f"  p = {res['p']:.3f} +/- {res['p_sigma']:.3f}  (predicted [0.8, 1.2])")
        print(f"  c = {res['c_days']:.4f} days")
        print(f"  R^2 = {res.get('R2')}")
    print(f"Results saved: {RESULTS}")


if __name__ == "__main__":
    main()
