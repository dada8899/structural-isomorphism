#!/usr/bin/env python3
"""
C1 v0.3 P0 reruns — Phase 1 (USGS earthquakes).

Addresses three P0 items from the internal review (C1-v0.2-internal-review-2026-05-24.md):
  P0-S1: Gardner-Knopoff 1974 declustering — does declustering shift b-value?
  P0-S2: Cumulative-frequency value at M=4.45 and M=4.35 (FMD audit for Mc=4.45)
  P0-S3: Magnitude-type homogenisation — Mw-only subset b-value

Inputs:   v4/validation/soc-earthquake/catalog.jsonl  (37,281 events M>=4.45)
Outputs:  declustering_fmd_results.json
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "catalog.jsonl"
OUT = HERE / "declustering_fmd_results.json"

R_EARTH_KM = 6371.0
MW_FAMILY = {"mww", "mwr", "mw", "mwb", "mwc", "mwp"}


# ---------- helpers ----------
def haversine_km(lat1, lon1, lat2, lon2):
    lat1 = np.radians(lat1); lon1 = np.radians(lon1)
    lat2 = np.radians(lat2); lon2 = np.radians(lon2)
    dlat = lat2 - lat1; dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R_EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def gk74_window(M):
    """Gardner-Knopoff 1974 spatial (km) and temporal (days) window vs M.

    Spatial:  L(M) = 10**(0.1238*M + 0.983)   (km)
    Temporal: T(M) = 10**(0.5409*M - 0.547)  if M >= 6.5 (days)
              T(M) = 10**(0.032*M + 2.7389) if M <  6.5 (days)
    (Standard Gardner-Knopoff regression from their Table 1.)
    """
    L = 10.0 ** (0.1238 * M + 0.983)
    T = np.where(M >= 6.5,
                 10.0 ** (0.5409 * M - 0.547),
                 10.0 ** (0.032 * M + 2.7389))
    return L, T


def uhrhammer86_window(M):
    """Uhrhammer 1986 — smaller windows than GK74, often preferred globally.

    Spatial:  L(M) = exp(-1.024 + 0.804*M)   (km)
    Temporal: T(M) = exp(-2.87 + 1.235*M)    (days)
    (Smaller than GK74; less aggressive declustering; closer to ETAS on globals.)
    """
    L = np.exp(-1.024 + 0.804 * M)
    T = np.exp(-2.87 + 1.235 * M)
    return L, T


def aki_b(mags, mc, bin_width=0.1):
    n = len(mags)
    mean_mag = float(np.mean(mags))
    b = math.log10(math.e) / (mean_mag - (mc - bin_width / 2))
    var = float(np.sum((mags - mean_mag) ** 2)) / (n * (n - 1))
    sigma_b = 2.3 * (b ** 2) * math.sqrt(var)
    return b, sigma_b, n


def bootstrap_b(mags, mc, n_boot=500, bin_width=0.1, seed=42):
    rng = np.random.default_rng(seed)
    n = len(mags)
    bs = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(mags, size=n, replace=True)
        mean_mag = float(np.mean(sample))
        bs[i] = math.log10(math.e) / (mean_mag - (mc - bin_width / 2))
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


# ---------- pipeline ----------
def load_catalog():
    rows = []
    with CATALOG.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df = df[df["type"] == "earthquake"].dropna(subset=["mag", "lat", "lon", "time_ms"]).copy()
    df["mag"] = df["mag"].astype(float)
    df["t_days"] = df["time_ms"].astype(np.int64) / (1000.0 * 86400.0)
    df = df.sort_values("t_days").reset_index(drop=True)
    return df


def gk_decluster(df, window_fn=gk74_window):
    """Window-based declustering on a time-sorted catalog.

    Algorithm (standard implementation):
      For each event i (in time order), check all later events j within
      L(M_i) km and T(M_i) days. Any such j is marked an aftershock,
      *unless* M_j > M_i, in which case the cluster's main shock
      "promotes" to j and the window is re-anchored on j.

    For computational efficiency on n=37k we use a moving time-window:
      only check j in i+1..k* where t[k*] - t[i] <= max possible T.

    Returns: boolean mask `is_mainshock` (length n).
    """
    n = len(df)
    mags = df["mag"].to_numpy()
    times = df["t_days"].to_numpy()
    lats = df["lat"].to_numpy()
    lons = df["lon"].to_numpy()

    is_main = np.ones(n, dtype=bool)
    cluster_id = np.full(n, -1, dtype=np.int64)
    Ls, Ts = window_fn(mags)

    # max time-window in catalog for early termination
    max_T = float(Ts.max())

    next_cluster = 0
    for i in range(n):
        if not is_main[i]:
            continue
        # Window from event i
        L_i = Ls[i]; T_i = Ts[i]; M_i = mags[i]
        t_lim = times[i] + T_i
        # binary-search the upper time bound to bound j-loop
        j_hi = int(np.searchsorted(times, t_lim, side="right"))
        # Vectorise distance check
        cand = np.arange(i + 1, j_hi)
        if cand.size == 0:
            continue
        # Filter by mag <= M_i (only smaller events are aftershocks; larger
        # promotes the main shock — handled at end)
        d = haversine_km(lats[i], lons[i], lats[cand], lons[cand])
        in_win = d <= L_i
        if not in_win.any():
            continue
        in_win_idx = cand[in_win]
        # Promote: if any in-window event is larger, the largest becomes
        # the new main shock and the cluster re-anchors on it. Standard
        # GK74 promotion rule.
        larger = mags[in_win_idx] > M_i
        if larger.any():
            # Mark current i as aftershock (demoted), and re-anchor on the
            # largest within the window.
            new_main = in_win_idx[np.argmax(mags[in_win_idx])]
            # All the rest are aftershocks
            is_main[i] = False
            for k in in_win_idx:
                if k != new_main:
                    is_main[k] = False
            # cluster id reassigned to the new main shock
            cid = next_cluster; next_cluster += 1
            cluster_id[i] = cid
            cluster_id[in_win_idx] = cid
            # The new_main will be processed in its own loop iteration
            # (its is_main is still True and its window will catch its
            # own aftershocks downstream).
        else:
            # All in-window events are aftershocks of i
            is_main[in_win_idx] = False
            cid = next_cluster; next_cluster += 1
            cluster_id[i] = cid
            cluster_id[in_win_idx] = cid

    return is_main, cluster_id


def fmd(mags, bin_width=0.1):
    """Cumulative + non-cumulative FMD."""
    mn = math.floor(mags.min() * 10) / 10
    mx = math.ceil(mags.max() * 10) / 10
    bins = np.arange(mn, mx + bin_width, bin_width)
    non_cum, edges = np.histogram(mags, bins=bins)
    cum = np.flip(np.cumsum(np.flip(non_cum)))  # cumulative N(>=M)
    centers = (edges[:-1] + edges[1:]) / 2
    return centers, non_cum, cum


def fit_at_mc(mags, mc):
    above = mags[mags >= mc]
    if len(above) < 50:
        return None
    b, sigma, n = aki_b(above, mc)
    ci_lo, ci_hi = bootstrap_b(above, mc, n_boot=500)
    return {
        "Mc": float(mc),
        "n_above_Mc": int(n),
        "b_value": float(b),
        "b_sigma_shi_bolt": float(sigma),
        "b_95_CI_bootstrap": [float(ci_lo), float(ci_hi)],
        "tau_from_b": float(1.0 + b / 1.5),
    }


def main():
    print("=" * 70)
    print("Phase 1 P0 reruns — declustering / FMD / mag-type homogenisation")
    print("=" * 70)

    df_all = load_catalog()
    print(f"\nLoaded earthquake-type events: {len(df_all)}")
    print(f"  mag range [{df_all['mag'].min():.2f}, {df_all['mag'].max():.2f}]")
    print(f"  time range {df_all['t_days'].min():.1f} to {df_all['t_days'].max():.1f} days")

    # --- baseline: re-fit on full earthquake catalog (sanity vs gr_results.json) ---
    print("\n--- BASELINE (un-declustered, all magnitude types) ---")
    mags_full = df_all["mag"].to_numpy()
    centers, non_cum, cum = fmd(mags_full)
    idx_at_445 = int(np.argmin(np.abs(centers - 4.45)))
    idx_at_435 = int(np.argmin(np.abs(centers - 4.35)))
    print(f"  cumulative N(M>=4.35) = {cum[idx_at_435]}")
    print(f"  cumulative N(M>=4.45) = {cum[idx_at_445]}")
    print(f"  non-cum count at M=4.35-4.45 bin = {non_cum[idx_at_435]}")
    print(f"  non-cum count at M=4.45-4.55 bin = {non_cum[idx_at_445]}")
    # Max-curvature Mc
    mc_maxc = float(centers[int(np.argmax(non_cum))])
    print(f"  Mc (max-curvature) = {mc_maxc:.2f}")
    baseline = fit_at_mc(mags_full, 4.45)
    print(f"  b={baseline['b_value']:.4f}+/-{baseline['b_sigma_shi_bolt']:.4f}  n={baseline['n_above_Mc']}")

    # --- P0-S2: FMD audit at M=4.35 vs M=4.45 ---
    print("\n--- P0-S2: FMD audit (Mc=4.45 max-curvature check) ---")
    s2_audit = {
        "Mc_max_curvature_recomputed": mc_maxc,
        "Mc_paper_value": 4.45,
        "Mc_max_curvature_matches_paper": abs(mc_maxc - 4.45) < 0.05,
        "M_bin_centers_local": centers[max(0, idx_at_435 - 2): idx_at_445 + 3].tolist(),
        "non_cumulative_counts_local": non_cum[max(0, idx_at_435 - 2): idx_at_445 + 3].tolist(),
        "cumulative_N_at_M_4_35": int(cum[idx_at_435]),
        "cumulative_N_at_M_4_45": int(cum[idx_at_445]),
        "non_cum_count_in_bin_4_35_to_4_45": int(non_cum[idx_at_435]),
        "non_cum_count_in_bin_4_45_to_4_55": int(non_cum[idx_at_445]),
        "comment": (
            "Max-curvature method selects the magnitude bin with the highest "
            "non-cumulative count. If the recomputed Mc matches the paper's 4.45 "
            "to within bin-width (0.1), the published Mc is auditable."
        ),
    }
    print(json.dumps(s2_audit, indent=2))

    # --- P0-S3: Magnitude-type homogenisation (Mw-only subset) ---
    print("\n--- P0-S3: Mw-only subset (mag type homogenisation) ---")
    df_mw = df_all[df_all["magType"].str.lower().isin(MW_FAMILY)].copy()
    print(f"  Mw-family events: {len(df_mw)}  ({100*len(df_mw)/len(df_all):.1f}% of total)")
    print(f"  magType breakdown: {dict(df_mw['magType'].value_counts())}")
    # Use same Mc=4.45 for direct comparison
    mw_mags = df_mw["mag"].to_numpy()
    mw_fit = fit_at_mc(mw_mags, 4.45)
    if mw_fit is None:
        s3_result = {"error": "Mw-only subset has too few events above Mc=4.45"}
    else:
        # also test natural Mc on Mw subset
        c_mw, nc_mw, _ = fmd(mw_mags)
        mc_mw_natural = float(c_mw[int(np.argmax(nc_mw))])
        nat_fit = fit_at_mc(mw_mags, mc_mw_natural)
        s3_result = {
            "n_mw_family": int(len(df_mw)),
            "fraction_of_catalog": float(len(df_mw) / len(df_all)),
            "magtype_breakdown": dict(df_mw["magType"].value_counts()),
            "fit_at_Mc_4_45": mw_fit,
            "Mc_natural_on_Mw_subset": mc_mw_natural,
            "fit_at_Mc_natural": nat_fit,
            "b_diff_vs_full_at_Mc_4_45": float(mw_fit["b_value"] - baseline["b_value"]),
            "comment": (
                "Mw-only subset re-fit at fixed Mc=4.45 enables direct comparison "
                "vs the un-homogenised baseline. A b-difference < 0.05 indicates "
                "the magnitude-type mixture is not biasing the headline b. "
                "Mw natural Mc may differ since Mw is harder to compute for small events."
            ),
        }
        print(f"  b (Mw-only, Mc=4.45) = {mw_fit['b_value']:.4f}+/-{mw_fit['b_sigma_shi_bolt']:.4f}")
        print(f"  b diff vs full catalog at Mc=4.45 = {s3_result['b_diff_vs_full_at_Mc_4_45']:+.4f}")
        print(f"  Mc natural on Mw subset = {mc_mw_natural:.2f}")
        if nat_fit:
            print(f"  b (Mw-only, Mc_nat={mc_mw_natural:.2f}) = "
                  f"{nat_fit['b_value']:.4f}+/-{nat_fit['b_sigma_shi_bolt']:.4f}")

    # --- P0-S1: GK74 + Uhrhammer86 declustering ---
    print("\n--- P0-S1: Declustering (GK74 + Uhrhammer86) ---")
    s1_runs = {}
    for label, win_fn in [("gardner_knopoff_1974", gk74_window),
                          ("uhrhammer_1986", uhrhammer86_window)]:
        print(f"\n  Running {label} on n={len(df_all)} ...")
        is_main, _ = gk_decluster(df_all, window_fn=win_fn)
        n_main = int(is_main.sum())
        n_after = int((~is_main).sum())
        print(f"    main shocks: {n_main} ({100*n_main/len(df_all):.1f}%) "
              f"aftershocks: {n_after} ({100*n_after/len(df_all):.1f}%)")

        dec_mags = df_all.loc[is_main, "mag"].to_numpy()
        dec_fit = fit_at_mc(dec_mags, 4.45)
        # natural Mc on declustered
        cd, ncd, _ = fmd(dec_mags)
        mc_dec_natural = float(cd[int(np.argmax(ncd))])
        dec_nat_fit = fit_at_mc(dec_mags, mc_dec_natural)
        if dec_fit:
            print(f"    b (Mc=4.45) = {dec_fit['b_value']:.4f}+/-{dec_fit['b_sigma_shi_bolt']:.4f}  "
                  f"n={dec_fit['n_above_Mc']}")
        if dec_nat_fit and abs(mc_dec_natural - 4.45) > 0.01:
            print(f"    b (Mc_nat={mc_dec_natural:.2f}) = "
                  f"{dec_nat_fit['b_value']:.4f}+/-{dec_nat_fit['b_sigma_shi_bolt']:.4f}  "
                  f"n={dec_nat_fit['n_above_Mc']}")
        s1_runs[label] = {
            "n_main_shocks": n_main,
            "n_aftershocks": n_after,
            "aftershock_fraction": float(n_after / len(df_all)),
            "fit_at_Mc_4_45": dec_fit,
            "Mc_natural": mc_dec_natural,
            "fit_at_Mc_natural": dec_nat_fit,
            "b_diff_at_Mc_4_45": (
                float(dec_fit["b_value"] - baseline["b_value"]) if dec_fit else None
            ),
        }

    s1_result = {
        "methods": [
            "Gardner-Knopoff 1974 (L=10^(0.1238M+0.983) km; T piecewise-M days)",
            "Uhrhammer 1986 (L=exp(-1.024+0.804M) km; T=exp(-2.87+1.235M) days)",
        ],
        "n_total": int(len(df_all)),
        "runs": s1_runs,
        "comment": (
            "Standard seismological position (Reasenberg / Gardner-Knopoff): "
            "background b should be estimated on a declustered catalog; "
            "aftershock sequences analysed un-declustered for Omori. "
            "GK74 windows are calibrated on southern-California regional catalogs "
            "and are known to over-decluster on global catalogs (60-80% aftershock "
            "fraction is typical, vs ~30% under modern ETAS-stochastic methods). "
            "Uhrhammer86 windows are smaller and typically give 30-50% aftershock "
            "fraction, closer to ETAS. Cf. Hainzl 2022; van Stiphout et al. 2012."
        ),
    }

    # --- summary verdict ---
    print("\n--- SUMMARY ---")
    summary = {
        "baseline_b_at_Mc_4_45_full_catalog": baseline,
        "P0_S1_declustering": s1_result,
        "P0_S2_FMD_audit": s2_audit,
        "P0_S3_magtype_homogenisation": s3_result,
    }
    # Verdict flags
    verdict = {}
    for label, run in s1_runs.items():
        if run.get("fit_at_Mc_4_45"):
            d = abs(run["fit_at_Mc_4_45"]["b_value"] - baseline["b_value"])
            verdict[f"P0_S1_{label}_b_value"] = run["fit_at_Mc_4_45"]["b_value"]
            verdict[f"P0_S1_{label}_b_shift_abs"] = float(d)
            verdict[f"P0_S1_{label}_aftershock_fraction"] = run["aftershock_fraction"]
    verdict["P0_S2_Mc_max_curvature_matches_4_45"] = s2_audit["Mc_max_curvature_matches_paper"]
    verdict["P0_S2_Mc_max_curvature_recomputed"] = s2_audit["Mc_max_curvature_recomputed"]
    if mw_fit:
        delta_mw = abs(mw_fit["b_value"] - baseline["b_value"])
        verdict["P0_S3_b_shift_under_0_05_at_Mc_4_45"] = bool(delta_mw < 0.05)
        verdict["P0_S3_b_shift_abs_Mw_only_at_Mc_4_45"] = float(delta_mw)
        verdict["P0_S3_Mw_only_b_value_at_Mc_4_45"] = float(mw_fit["b_value"])
        # Mc-natural fit on Mw subset (this is the "fair" comparison)
        nat_fit = s3_result.get("fit_at_Mc_natural") if isinstance(s3_result, dict) else None
        if nat_fit:
            verdict["P0_S3_Mw_only_b_value_at_Mc_natural"] = float(nat_fit["b_value"])
            verdict["P0_S3_Mw_only_Mc_natural"] = float(s3_result["Mc_natural_on_Mw_subset"])
    summary["verdict_flags"] = verdict
    print(json.dumps(verdict, indent=2))

    def _coerce(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, dict):
            return {str(k): _coerce(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_coerce(x) for x in o]
        return o

    OUT.write_text(json.dumps(_coerce(summary), indent=2))
    print(f"\nWrote: {OUT}")


if __name__ == "__main__":
    main()
