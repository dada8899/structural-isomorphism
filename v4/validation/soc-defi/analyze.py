#!/usr/bin/env python3
"""
Layer 5 Phase 3: SOC analysis on Aave V2 liquidation events.

We have 28,943 LiquidationCall events spanning 2020-12 → 2024-01.
Each event gives: timestamp, collateral_asset (address), debt_asset,
debt_to_cover_raw (uint256 in debtAsset decimals),
liquidated_collateral_raw (uint256 in collateralAsset decimals).

To fit a power law on event sizes we need a comparable numeric scale
across events. Raw uint256 values from different tokens (WETH-18,
USDC-6, WBTC-8) live on different scales, so naive pooling is wrong.

Strategy:
  A. Filter to events where debt_asset is a STABLECOIN (USDC, USDT, DAI)
     and use debt_to_cover / 10^decimals as a USD-denominated size.
     Stablecoin debt is ~1:1 with USD, so this is clean.
  B. Separately count liquidation events per day for Omori aftershock
     analysis on event RATE (counts, not sizes), independent of tokens.

Then we fit:
  1. Clauset 2009 power-law on stablecoin debt sizes.
  2. Omori on post-shock daily count rate, same stack as earthquake
     and S&P 500 (log-linear regression with c grid search).

Output:
  - gr_results.json
  - omori_results.json
  - sizes_histogram.json (for optional plotting)
"""

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import powerlaw

OUT_DIR = Path(__file__).resolve().parent
INPUT = OUT_DIR / "aave_v2_liquidations.jsonl"
GR_OUT = OUT_DIR / "gr_results.json"
OMORI_OUT = OUT_DIR / "omori_results.json"

# Stablecoin token addresses on Ethereum mainnet (all lowercase)
STABLES = {
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", 6),
    "0xdac17f958d2ee523a2206206994597c13d831ec7": ("USDT", 6),
    "0x6b175474e89094c44da98b954eedeac495271d0f": ("DAI", 18),
    "0x4fabb145d64652a948d72533023f6e7a623c7c53": ("BUSD", 18),
    "0x853d955acef822db058eb8505911ed77f175b99e": ("FRAX", 18),
    "0x8e870d67f660d95d5be530380d0ec0bd388289e1": ("USDP", 18),
    "0x0000000000085d4780b73119b644ae5ecd22b376": ("TUSD", 18),
    "0x57ab1ec28d129707052df4df418d58a2d46d5f51": ("SUSD", 18),
}

def load_events():
    rows = []
    with INPUT.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def compute_stable_usd_sizes(events):
    usd_sizes = []
    for e in events:
        da = (e.get("debt_asset") or "").lower()
        if da not in STABLES:
            continue
        sym, dec = STABLES[da]
        raw = e.get("debt_to_cover_raw")
        if not raw:
            continue
        try:
            raw_int = int(raw)
        except Exception:
            continue
        usd = raw_int / (10 ** dec)
        if usd <= 0:
            continue
        usd_sizes.append(usd)
    return np.array(usd_sizes, dtype=float)


def gutenberg_richter_equivalent(sizes):
    """Clauset 2009 continuous power-law fit on USD sizes."""
    vals = sizes[sizes > 0]
    if len(vals) < 50:
        return {"error": f"too few values: {len(vals)}"}
    fit = powerlaw.Fit(vals, discrete=False, xmin_distance="D", verbose=False)
    alpha = float(fit.power_law.alpha)
    xmin = float(fit.power_law.xmin)
    sigma = float(fit.power_law.sigma)
    try:
        R_ln, p_ln = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
    except Exception:
        R_ln, p_ln = (None, None)
    try:
        R_exp, p_exp = fit.distribution_compare("power_law", "exponential", normalized_ratio=True)
    except Exception:
        R_exp, p_exp = (None, None)
    try:
        R_tp, p_tp = fit.distribution_compare("power_law", "truncated_power_law", normalized_ratio=True)
    except Exception:
        R_tp, p_tp = (None, None)
    return {
        "alpha": alpha,
        "sigma_alpha": sigma,
        "xmin_usd": xmin,
        "n_total": int(len(vals)),
        "n_tail": int(np.sum(vals >= xmin)),
        "compare_vs_lognormal_R": None if R_ln is None else float(R_ln),
        "compare_vs_lognormal_p": None if p_ln is None else float(p_ln),
        "compare_vs_exponential_R": None if R_exp is None else float(R_exp),
        "compare_vs_exponential_p": None if p_exp is None else float(p_exp),
        "compare_vs_truncated_R": None if R_tp is None else float(R_tp),
        "compare_vs_truncated_p": None if p_tp is None else float(p_tp),
    }


def aggregate_counts(events, bin_seconds: int):
    """Aggregate event counts into fixed-width time bins.
    Returns (bins, counts) where bins is a monotonically increasing
    int array of bin indices (ts_unix // bin_seconds)."""
    bc = {}
    for e in events:
        t = e.get("ts_unix") or 0
        if not t:
            continue
        b = int(t // bin_seconds)
        bc[b] = bc.get(b, 0) + 1
    if not bc:
        return np.array([]), np.array([])
    b0 = min(bc)
    b1 = max(bc)
    bins = np.arange(b0, b1 + 1)
    counts = np.array([bc.get(int(b), 0) for b in bins], dtype=float)
    return bins, counts


def fit_omori(counts_series, sigma_k=3.0, window_bins=30, bin_unit_label="day"):
    """Identify main shock bins (count > mu + sigma_k * sigma), stack forward
    windows, fit log-linear Omori."""
    mu = counts_series.mean()
    sigma = counts_series.std()
    threshold = mu + sigma_k * sigma
    main_idx = np.where(counts_series > threshold)[0]
    valid = main_idx[(main_idx + window_bins) < len(counts_series)]
    if len(valid) < 10:
        return {"error": f"too few main shocks: {len(valid)}", "threshold": float(threshold), "mu": float(mu), "sigma": float(sigma)}

    # Stack post-shock counts, subtract baseline
    rates = np.zeros(window_bins)
    for tau in range(1, window_bins + 1):
        v = counts_series[valid + tau]
        rates[tau - 1] = v.mean() - mu  # excess rate
    tau_days = np.arange(1, window_bins + 1, dtype=float)
    keep = rates > 0
    if keep.sum() < 6:
        return {"error": f"too few positive-excess tau bins: {int(keep.sum())}"}

    t_fit = tau_days[keep]
    r_fit = rates[keep]
    w = np.ones_like(t_fit)

    best = None
    for c_day in [0.1, 0.3, 0.5, 1.0, 1.5, 2.0]:
        x = np.log10(t_fit + c_day)
        y = np.log10(r_fit)
        Sw = np.sum(w)
        Sx = np.sum(w * x)
        Sy = np.sum(w * y)
        Sxx = np.sum(w * x * x)
        Sxy = np.sum(w * x * y)
        denom = Sw * Sxx - Sx * Sx
        slope = (Sw * Sxy - Sx * Sy) / denom
        intercept = (Sy - slope * Sx) / Sw
        p_est = -slope
        pred_y = intercept + slope * x
        ss_res = float(np.sum(w * (y - pred_y) ** 2))
        ss_tot = float(np.sum(w * (y - np.average(y, weights=w)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
        dof = max(len(y) - 2, 1)
        mse = float(np.sum(w * (y - pred_y) ** 2) / dof)
        var_slope = mse * Sw / denom
        sigma_p = float(math.sqrt(abs(var_slope)))
        if best is None or (r2 is not None and r2 > best["R2"]):
            best = {
                "c_days": c_day,
                "p": float(p_est),
                "p_sigma": sigma_p,
                "logK": float(intercept),
                "R2": float(r2) if r2 is not None else None,
            }

    return {
        "sigma_k": sigma_k,
        "bin_unit": bin_unit_label,
        "mu_per_bin": float(mu),
        "sigma_per_bin": float(sigma),
        "threshold_per_bin": float(threshold),
        "n_main_shocks": int(len(valid)),
        "window_bins": int(window_bins),
        "c_bins": best["c_days"],
        "p": best["p"],
        "p_sigma": best["p_sigma"],
        "R2": best["R2"],
        "predicted_p_range": [0.3, 1.3],
        "p_within_prediction": bool(0.3 <= best["p"] <= 1.3),
        "p_consistent_with_canonical": bool(abs(best["p"] - 1.0) < 2 * best["p_sigma"]),
    }


def main():
    print("Loading Aave V2 liquidations...")
    events = load_events()
    print(f"  total events: {len(events)}")

    # Asset breakdown
    debt_assets = {}
    for e in events:
        a = (e.get("debt_asset") or "").lower()
        debt_assets[a] = debt_assets.get(a, 0) + 1
    top_debt = sorted(debt_assets.items(), key=lambda kv: -kv[1])[:8]
    print("  top debt assets:")
    for a, n in top_debt:
        sym = STABLES.get(a, (a[:12] + "…", 0))[0]
        print(f"    {sym:8s} {n:6d}")

    # Power-law on stablecoin USD sizes
    sizes = compute_stable_usd_sizes(events)
    print(f"\n  stablecoin-debt events: {len(sizes)}")
    if len(sizes) > 0:
        print(f"  USD size range: [{sizes.min():.2f}, {sizes.max():.2f}]")
        print(f"  mean {sizes.mean():.2f}, median {np.median(sizes):.2f}")

    print("\nAnalysis 1 — Clauset power-law on stablecoin USD sizes...")
    pl = gutenberg_richter_equivalent(sizes)
    print(f"  alpha = {pl.get('alpha', '?')}")
    print(f"  xmin  = {pl.get('xmin_usd', '?')}")
    print(f"  n_tail = {pl.get('n_tail', '?')}")
    if "compare_vs_lognormal_p" in pl and pl["compare_vs_lognormal_p"] is not None:
        print(f"  vs lognormal: R={pl['compare_vs_lognormal_R']:.3f}, p={pl['compare_vs_lognormal_p']:.4g}")
    if "compare_vs_exponential_p" in pl and pl["compare_vs_exponential_p"] is not None:
        print(f"  vs exponential: R={pl['compare_vs_exponential_R']:.3f}, p={pl['compare_vs_exponential_p']:.4g}")
    if "compare_vs_truncated_p" in pl and pl["compare_vs_truncated_p"] is not None:
        print(f"  vs truncated_power_law: R={pl['compare_vs_truncated_R']:.3f}, p={pl['compare_vs_truncated_p']:.4g}")

    alpha_pred = (1.5, 3.0)  # wide band — DeFi liquidation sizes have no established literature value
    alpha_ok = False
    if "alpha" in pl:
        alpha_ok = alpha_pred[0] <= pl["alpha"] <= alpha_pred[1]

    gr_out = {
        "domain": "DeFi (Aave V2 liquidations)",
        "predicted_class": "soc_threshold_cascade",
        "cross_domain_test": True,
        "n_total_events": len(events),
        "n_stable_events": int(len(sizes)),
        "time_window": {"start": "2020-12", "end": "2024-01"},
        "clauset_fit": pl,
        "alpha_predicted_range": list(alpha_pred),
        "alpha_within_prediction": alpha_ok,
        "verdict_gr": "CONFIRMED" if alpha_ok else "DEVIATING",
        "method_refs": [
            "Clauset-Shalizi-Newman 2009",
            "Qin et al 2021 (empirical DeFi liquidations)",
        ],
    }
    GR_OUT.write_text(json.dumps(gr_out, indent=2))
    print(f"  saved: {GR_OUT}")

    print("\nAggregating event counts at multiple time scales for Omori...")
    scales = {
        "daily":   (86400,  30),
        "6hour":   (21600,  4 * 30),
        "1hour":   (3600,   24 * 30),
    }
    om_results = {}
    for label, (bin_sec, window) in scales.items():
        _, counts = aggregate_counts(events, bin_sec)
        print(f"  {label:6s} n_bins={len(counts)}, mu={counts.mean():.2f}, max={int(counts.max())}")
        fit = fit_omori(counts, sigma_k=3.0, window_bins=window, bin_unit_label=label)
        om_results[label] = fit
        if "p" in fit:
            print(f"    p = {fit['p']:.3f} +/- {fit['p_sigma']:.3f}, R2 = {fit['R2']:.3f}, n_main = {fit['n_main_shocks']}")
        else:
            print(f"    {fit.get('error', 'no fit')}")

    # Pick best fit by R2 * (1/p_sigma)
    best_scale = max(
        (k for k in om_results if "p" in om_results[k]),
        key=lambda k: (om_results[k].get("R2") or 0) * (1.0 / max(om_results[k].get("p_sigma") or 1, 0.01)),
        default=None,
    )

    om_out = {
        "domain": "DeFi (Aave V2 liquidations)",
        "predicted_class": "soc_threshold_cascade",
        "cross_domain_test": True,
        "fits_by_scale": om_results,
        "best_scale": best_scale,
        "method_refs": [
            "Omori 1894",
            "Lillo-Mantegna 2003",
            "Petersen 2010",
            "Weber 2007",
        ],
    }
    OMORI_OUT.write_text(json.dumps(om_out, indent=2))
    print(f"  saved: {OMORI_OUT}")
    print(f"  best scale: {best_scale}")

    # Use best scale for final verdict
    best = om_results.get(best_scale, {}) if best_scale else {}
    print()
    print("=== VERDICT ===")
    gr_verdict = "CONFIRMED" if alpha_ok else "DEVIATING"
    if not best or "error" in best:
        om_verdict = "INCONCLUSIVE"
    elif best.get("p_within_prediction") or best.get("p_consistent_with_canonical"):
        om_verdict = f"CONFIRMED ({best_scale} scale)"
    else:
        om_verdict = "DEVIATING"
    print(f"  Power-law (USD sizes):  {gr_verdict}  alpha = {pl.get('alpha', '?')}")
    print(f"  Omori (best scale):     {om_verdict}  p = {best.get('p', '?')}")


if __name__ == "__main__":
    main()
