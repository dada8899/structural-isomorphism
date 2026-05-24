#!/usr/bin/env python3
"""C1 v0.2 -> v0.3 P0 re-runs.

Four re-runs:
  P0-S1: Gardner-Knopoff declustering -> b-value robustness
  P0-S2: M_c cumulative-frequency audit at M=4.45 and M=4.35
  P0-S3: Magnitude-type composition; Mw-only b-value
  P0-E3: Phase 2 Omori slope-zero null rejection significance
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path("/Users/dadamini/Projects/structural-isomorphism")
EQ = ROOT / "v4/validation/soc-earthquake"
SM = ROOT / "v4/validation/soc-stockmarket"

OUT = Path("/tmp/c1_v03_reruns_results.json")
results: dict = {}


# -----------------------------------------------------------------------------
# Earthquake catalog: load
# -----------------------------------------------------------------------------
def load_eq_catalog() -> list[dict]:
    rows = []
    with (EQ / "catalog.jsonl").open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    # Keep tectonic earthquakes with valid mag (match gutenberg_richter.py)
    rows = [r for r in rows if r.get("type") == "earthquake" and r.get("mag") is not None]
    return rows


# -----------------------------------------------------------------------------
# Helpers shared with gutenberg_richter.py
# -----------------------------------------------------------------------------
def aki_b_value(mags_above_mc: np.ndarray, mc: float, bin_width: float = 0.1):
    n = len(mags_above_mc)
    if n < 50:
        raise ValueError(f"too few events: n={n}")
    mean_mag = float(np.mean(mags_above_mc))
    b = math.log10(math.e) / (mean_mag - (mc - bin_width / 2))
    var = float(np.sum((mags_above_mc - mean_mag) ** 2) / (n * (n - 1)))
    sigma_b = 2.3 * (b ** 2) * math.sqrt(var)
    return b, sigma_b, n


def fmd_cumulative(mags: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Cumulative frequency (N >= M) on the bin edges."""
    counts, _ = np.histogram(mags, bins=edges)
    # cumulative from right: N(>=M_i) = sum of counts in bins j>=i
    return np.cumsum(counts[::-1])[::-1]


def b_with_bootstrap(mags: np.ndarray, mc: float, n_boot: int = 500, seed: int = 42):
    mags_above = mags[mags >= mc]
    b, sigma_b, n = aki_b_value(mags_above, mc)
    rng = np.random.default_rng(seed)
    bs = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(mags_above, size=len(mags_above), replace=True)
        mean_mag = float(np.mean(sample))
        bs[i] = math.log10(math.e) / (mean_mag - (mc - 0.05))
    ci = (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))
    return {
        "b": b, "sigma_b": sigma_b, "n_above_Mc": n, "Mc": mc,
        "boot_95CI": ci,
    }


# -----------------------------------------------------------------------------
# P0-S2: FMD cumulative frequency at M=4.45, M=4.35, and bin-level audit
# -----------------------------------------------------------------------------
def run_p0_s2(catalog: list[dict]) -> dict:
    mags = np.array([r["mag"] for r in catalog], dtype=float)
    # match estimate_mc_maxc bin grid
    bin_width = 0.1
    mn = math.floor(mags.min() * 10) / 10
    mx = math.ceil(mags.max() * 10) / 10
    edges = np.arange(mn, mx + bin_width, bin_width)
    counts, _ = np.histogram(mags, bins=edges)
    # max-curvature M_c (non-cumulative argmax)
    idx_argmax = int(np.argmax(counts))
    mc_argmax = float((edges[idx_argmax] + edges[idx_argmax + 1]) / 2)
    # Cumulative N(>=M) for plotting
    cum = np.cumsum(counts[::-1])[::-1]
    # values around M_c
    def at(mag):
        # find the bin whose left edge is approximately `mag`
        i = int(round((mag - edges[0]) / bin_width))
        if 0 <= i < len(edges) - 1:
            bin_center = float((edges[i] + edges[i + 1]) / 2)
            return {"bin_center": bin_center, "n_in_bin": int(counts[i]), "N_cumulative_geq": int(cum[i])}
        return None
    return {
        "Mc_max_curvature": mc_argmax,
        "bin_width": bin_width,
        "n_total_earthquakes": int(mags.size),
        "FMD_at_M_4.35": at(4.35),
        "FMD_at_M_4.45": at(4.45),
        "FMD_at_M_4.55": at(4.55),
        # adjacent bins around max-curvature peak
        "peak_argmax_count": int(counts[idx_argmax]),
        "peak_argmax_bin_center": mc_argmax,
        "neighborhood": {
            "M-0.2": {"bin_center": float((edges[idx_argmax-2] + edges[idx_argmax-1])/2),
                      "n_in_bin": int(counts[idx_argmax-2])} if idx_argmax >= 2 else None,
            "M-0.1": {"bin_center": float((edges[idx_argmax-1] + edges[idx_argmax])/2),
                      "n_in_bin": int(counts[idx_argmax-1])} if idx_argmax >= 1 else None,
            "M":     {"bin_center": mc_argmax, "n_in_bin": int(counts[idx_argmax])},
            "M+0.1": {"bin_center": float((edges[idx_argmax+1] + edges[idx_argmax+2])/2),
                      "n_in_bin": int(counts[idx_argmax+1])} if idx_argmax + 2 < len(edges) else None,
            "M+0.2": {"bin_center": float((edges[idx_argmax+2] + edges[idx_argmax+3])/2),
                      "n_in_bin": int(counts[idx_argmax+2])} if idx_argmax + 3 < len(edges) else None,
        },
    }


# -----------------------------------------------------------------------------
# P0-S3: Magnitude-type composition; Mw-only b-value
# -----------------------------------------------------------------------------
def run_p0_s3(catalog: list[dict]) -> dict:
    mag_types = Counter()
    for r in catalog:
        t = r.get("magType") or "unknown"
        mag_types[t] += 1
    total = sum(mag_types.values())
    composition = {k: {"n": v, "pct": 100 * v / total} for k, v in mag_types.most_common()}
    # Mw-only subset
    mw_keys = {"mw", "mww", "mwb", "mwc", "mwr"}
    mw_mags = np.array([r["mag"] for r in catalog
                        if (r.get("magType") or "").lower() in mw_keys], dtype=float)
    out = {"composition": composition, "total": total,
           "n_Mw_family": int(mw_mags.size)}
    # b-value for Mw-only subset; estimate Mc by max-curvature on the subset
    if mw_mags.size > 1000:
        bin_width = 0.1
        mn = math.floor(mw_mags.min() * 10) / 10
        mx = math.ceil(mw_mags.max() * 10) / 10
        edges = np.arange(mn, mx + bin_width, bin_width)
        counts, _ = np.histogram(mw_mags, bins=edges)
        idx = int(np.argmax(counts))
        mc_mw = float((edges[idx] + edges[idx + 1]) / 2)
        out["Mw_only"] = b_with_bootstrap(mw_mags, mc_mw, n_boot=500)
        # Also report b at fixed Mc=4.45 for direct comparison with v0.2
        try:
            out["Mw_only_at_Mc_4.45"] = b_with_bootstrap(mw_mags, 4.45, n_boot=500)
        except Exception as e:
            out["Mw_only_at_Mc_4.45"] = {"error": str(e)}
    return out


# -----------------------------------------------------------------------------
# P0-S1: Gardner-Knopoff window declustering -> b-value
# Reference: Gardner & Knopoff 1974, BSSA 64, 1363
# Window (M -> dt, dr) for tectonic earthquakes (T parameter not used since we
# only care about declustering proper):
#   distance:  log10 dr_km = 0.1238*M + 0.983
#   time:      log10 dt_d  = 0.5409*M - 0.547        (M < 6.5)
#              log10 dt_d  = 0.032 *M + 2.7389       (M >= 6.5)
# -----------------------------------------------------------------------------
def gk_window(mag: float) -> tuple[float, float]:
    log_dr = 0.1238 * mag + 0.983
    if mag < 6.5:
        log_dt = 0.5409 * mag - 0.547
    else:
        log_dt = 0.032 * mag + 2.7389
    return 10 ** log_dr, 10 ** log_dt


def haversine_km(lat1, lon1, lat2, lon2):
    # vectorized
    R = 6371.0
    lat1r = np.radians(lat1)
    lat2r = np.radians(lat2)
    dlat = lat2r - lat1r
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def run_p0_s1(catalog: list[dict]) -> dict:
    """Gardner-Knopoff space-time window declustering, then b-value on background."""
    # Sort by time
    cat = sorted(catalog, key=lambda r: r["time_ms"])
    n = len(cat)
    mags = np.array([r["mag"] for r in cat], dtype=float)
    times_d = np.array([r["time_ms"] for r in cat], dtype=float) / (1000 * 86400)  # days
    lats = np.array([r["lat"] for r in cat], dtype=float)
    lons = np.array([r["lon"] for r in cat], dtype=float)
    # Mark aftershocks. Standard GK: for each event in decreasing magnitude
    # order, mark all subsequent events within (dt,dr) as aftershocks of it.
    # Common implementation: iterate by magnitude, take un-marked, mark its
    # cluster. We use a simple linear pass since n is ~85k.
    is_aftershock = np.zeros(n, dtype=bool)
    # Iterate events in *time order*; for each event not already an aftershock,
    # check if any earlier larger event's window covers it. Performance: O(n*W)
    # where W = window count. Use a rolling buffer.
    # Simpler & standard: for each event i, look back over events j<i within
    # max_dt (e.g. 1000 d) and if mags[j] > mags[i] and dt < dt_window(mags[j])
    # and dr < dr_window(mags[j]) -> i is aftershock of j.
    # Use only "potential parents" with mag > mags[i].
    max_lookback_days = 1500.0  # plenty for largest GK window
    # Pre-compute per-event window for efficiency
    # for each i, walk j from i-1 down while times_d[i] - times_d[j] < max_lookback_days
    for i in range(n):
        ti = times_d[i]
        mi = mags[i]
        lat_i = lats[i]
        lon_i = lons[i]
        # earliest j to consider
        j = i - 1
        while j >= 0 and ti - times_d[j] <= max_lookback_days:
            mj = mags[j]
            if mj >= mi:  # only larger or equal events can parent
                dr_w, dt_w = gk_window(mj)
                dt = ti - times_d[j]
                if dt <= dt_w:
                    dr = haversine_km(lat_i, lon_i, lats[j], lons[j])
                    if dr <= dr_w:
                        is_aftershock[i] = True
                        break
            j -= 1
    n_background = int(np.sum(~is_aftershock))
    n_aftershocks = int(np.sum(is_aftershock))
    bg_mags = mags[~is_aftershock]
    # Re-estimate Mc on the background catalog by max-curvature
    bin_width = 0.1
    mn = math.floor(bg_mags.min() * 10) / 10
    mx = math.ceil(bg_mags.max() * 10) / 10
    edges = np.arange(mn, mx + bin_width, bin_width)
    counts, _ = np.histogram(bg_mags, bins=edges)
    idx = int(np.argmax(counts))
    mc_bg = float((edges[idx] + edges[idx + 1]) / 2)
    # b-value at the declustered Mc
    b_at_bg = b_with_bootstrap(bg_mags, mc_bg, n_boot=500)
    # Also at original Mc=4.45 for direct apples-to-apples comparison
    b_at_4p45 = b_with_bootstrap(bg_mags, 4.45, n_boot=500)
    return {
        "n_total": n,
        "n_aftershocks_marked": n_aftershocks,
        "n_background": n_background,
        "aftershock_fraction": n_aftershocks / n,
        "Mc_background_max_curvature": mc_bg,
        "b_value_background_at_Mc_bg": b_at_bg,
        "b_value_background_at_Mc_4.45": b_at_4p45,
        "method_ref": "Gardner-Knopoff 1974 BSSA window declustering",
    }


# -----------------------------------------------------------------------------
# P0-E3: Phase 2 Omori slope-zero rejection significance
# Test: H0: p = 0 (flat-rate decay) vs H_alt: p != 0
# We have p_est = 0.286 ± 0.034 from existing source data; significance is the
# t-statistic vs zero on that fit. Re-derive the fit ourselves from
# stacked_excess_rates and tau_days to confirm the numbers, then report
# significance.
# -----------------------------------------------------------------------------
def run_p0_e3() -> dict:
    omori = json.loads((SM / "omori_results.json").read_text())
    fit = omori["fit"]
    tau = np.array(fit["tau_days"], dtype=float)
    rates = np.array(fit["stacked_excess_rates"], dtype=float)
    c = float(fit["c_days"])
    p_est_source = float(fit["p"])
    p_sigma_source = float(fit["p_sigma"])
    # Refit log-log: log(rate) = logK - p * log(t + c)
    valid = rates > 0
    x = np.log(tau[valid] + c)
    y = np.log(rates[valid])
    # weights: use the inverse variance proxy = rates (since Poisson-like)
    # Match the source paper convention; if it used unweighted regression let's
    # do unweighted as well.
    n_pts = len(x)
    A = np.vstack([np.ones(n_pts), -x]).T  # logK, p
    coef, resid, _, _ = np.linalg.lstsq(A, y, rcond=None)
    logK_fit, p_fit = float(coef[0]), float(coef[1])
    yhat = A @ coef
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot
    # standard error of slope p
    # OLS with design matrix [1, -x] -> Var(coef) = sigma^2 * (X'X)^-1
    sigma2 = ss_res / (n_pts - 2)
    XtX_inv = np.linalg.inv(A.T @ A)
    se_p = float(np.sqrt(sigma2 * XtX_inv[1, 1]))
    t_stat = p_fit / se_p
    # two-sided p-value via normal approx (high df)
    from math import erf, sqrt
    pval_two = 2 * (1 - 0.5 * (1 + erf(abs(t_stat) / sqrt(2))))
    return {
        "p_refit": p_fit,
        "p_sigma_refit": se_p,
        "logK_refit": logK_fit,
        "R2_refit": r2,
        "p_source_paper": p_est_source,
        "p_sigma_source_paper": p_sigma_source,
        "t_stat_vs_zero_slope": t_stat,
        "two_sided_p_value": pval_two,
        "n_bins_used": n_pts,
        "interpretation": (
            f"Flat-rate null (p=0) is rejected at |t|={abs(t_stat):.1f}σ "
            f"(two-sided p={pval_two:.2e})."
        ),
    }


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    print("Loading earthquake catalog ...")
    catalog = load_eq_catalog()
    print(f"  loaded {len(catalog)} tectonic earthquakes")

    print("P0-S2: FMD cumulative-frequency audit ...")
    results["P0-S2"] = run_p0_s2(catalog)

    print("P0-S3: Magnitude-type composition + Mw-only b ...")
    results["P0-S3"] = run_p0_s3(catalog)

    print("P0-S1: Gardner-Knopoff declustering + b-value ...")
    results["P0-S1"] = run_p0_s1(catalog)

    print("P0-E3: Phase 2 Omori slope-zero significance ...")
    results["P0-E3"] = run_p0_e3()

    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"Wrote {OUT}")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
