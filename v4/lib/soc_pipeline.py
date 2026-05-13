#!/usr/bin/env python3
"""Shared SOC pipeline for V4 Layer 5 phases 6+.

Three primitives reused across all phases:

  1. fit_clauset_powerlaw(vals): α + xmin + comparison vs lognormal / exponential
  2. omori_from_aftershock_stack(dts_sec): log-spaced Omori-Utsu fit
  3. bin_and_omori_from_events(event_times_sec): main-shock detection + stack

All match the implementations of soc-earthquake/*.py (frozen reference).

Usage:
  from soc_pipeline import fit_clauset_powerlaw, omori_from_aftershock_stack
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def fit_clauset_powerlaw(
    vals: np.ndarray,
    name: str = "values",
    discrete: bool = False,
) -> dict[str, Any]:
    """Clauset-Shalizi-Newman 2009 power-law fit + comparisons.

    Returns:
        alpha, sigma_alpha, xmin, n_total, n_tail,
        vs_lognormal_R, vs_lognormal_p,
        vs_exponential_R, vs_exponential_p,
        vs_powerlaw_lognormal_winner: 'power_law' / 'lognormal' / 'inconclusive',
        rejects_power_law: True if pipeline should reject SOC label.
    """
    try:
        import powerlaw
    except Exception as exc:
        return {"name": name, "error": f"powerlaw missing: {exc}"}

    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals) & (vals > 0)]
    if len(vals) < 100:
        return {"name": name, "error": f"too few values: {len(vals)}"}

    fit = powerlaw.Fit(vals, discrete=discrete, xmin_distance="D", verbose=False)
    alpha = float(fit.power_law.alpha)
    sigma = float(fit.power_law.sigma)
    xmin = float(fit.power_law.xmin)
    n_tail = int(np.sum(vals >= xmin))

    try:
        R_ln, p_ln = fit.distribution_compare(
            "power_law", "lognormal", normalized_ratio=True
        )
    except Exception:
        R_ln, p_ln = (None, None)
    try:
        R_exp, p_exp = fit.distribution_compare(
            "power_law", "exponential", normalized_ratio=True
        )
    except Exception:
        R_exp, p_exp = (None, None)

    # Verdict logic same as null_validation reference
    rejects = False
    if R_exp is not None and R_exp < 0:
        rejects = True
    if R_ln is not None and R_ln < 0:
        rejects = True

    if R_ln is None:
        winner = "inconclusive"
    elif R_ln > 0 and (p_ln is None or p_ln < 0.1):
        winner = "power_law"
    elif R_ln < 0 and (p_ln is None or p_ln < 0.1):
        winner = "lognormal"
    else:
        winner = "inconclusive"

    return {
        "name": name,
        "alpha": alpha,
        "sigma_alpha": sigma,
        "xmin": xmin,
        "n_total": int(len(vals)),
        "n_tail": n_tail,
        "vs_lognormal_R": None if R_ln is None else float(R_ln),
        "vs_lognormal_p": None if p_ln is None else float(p_ln),
        "vs_exponential_R": None if R_exp is None else float(R_exp),
        "vs_exponential_p": None if p_exp is None else float(p_exp),
        "vs_powerlaw_lognormal_winner": winner,
        "rejects_power_law": bool(rejects),
    }


def omori_from_aftershock_stack(
    dts_sec: np.ndarray,
    min_sec: float = 300.0,
    max_sec: float = 30 * 86400,
    n_bins: int = 24,
    c_grid_days: tuple[float, ...] = (0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5),
) -> dict[str, Any]:
    """Omori-Utsu fit on a stack of aftershock times (seconds after main).

    Matches soc-earthquake/omori_decay.py::fit_omori but parameterized.
    Returns p, p_sigma, c_days, logK, R2, predicted_band match.
    """
    dts_sec = np.asarray(dts_sec, dtype=float)
    if len(dts_sec) < 100:
        return {"error": f"too few aftershocks ({len(dts_sec)})"}

    dts_sec = dts_sec[(dts_sec >= min_sec) & (dts_sec <= max_sec)]
    if len(dts_sec) == 0:
        return {"error": "no aftershocks in [min_sec, max_sec]"}

    bins = np.logspace(math.log10(min_sec), math.log10(max_sec), n_bins + 1)
    centers = np.sqrt(bins[:-1] * bins[1:])
    widths = bins[1:] - bins[:-1]
    counts, _ = np.histogram(dts_sec, bins=bins)
    rate_per_sec = counts / widths
    valid = counts >= 3
    if valid.sum() < 6:
        return {"error": f"too few valid bins ({int(valid.sum())})"}

    t_sec = centers[valid]
    r = rate_per_sec[valid]
    w = np.sqrt(counts[valid].astype(float))

    best = None
    for c_day in c_grid_days:
        c_sec = c_day * 86400
        x = np.log10(t_sec + c_sec)
        y = np.log10(r)
        W = w ** 2
        Sw = np.sum(W)
        Sx = np.sum(W * x)
        Sy = np.sum(W * y)
        Sxx = np.sum(W * x * x)
        Sxy = np.sum(W * x * y)
        denom = Sw * Sxx - Sx * Sx
        if denom == 0:
            continue
        slope = (Sw * Sxy - Sx * Sy) / denom
        intercept = (Sy - slope * Sx) / Sw
        p = -slope
        logK = intercept
        pred_y = intercept + slope * x
        ss_res = float(np.sum(W * (y - pred_y) ** 2))
        ss_tot = float(np.sum(W * (y - np.average(y, weights=W)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
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

    if best is None:
        return {"error": "no valid Omori fit"}

    return {
        "n_aftershocks_in_fit": int(np.sum(counts[valid])),
        "n_bins_used": int(valid.sum()),
        "t_range_days": [
            float(t_sec.min() / 86400),
            float(t_sec.max() / 86400),
        ],
        **best,
    }


def bin_and_omori_from_events(
    event_times_sec: np.ndarray,
    bin_seconds: float = 60.0,
    sigma_k: float = 3.0,
    window_bins: int = 60,
) -> dict[str, Any]:
    """Discrete-time Omori detector for event streams without main/aftershock labels.

    Same as null-controls/generate_and_analyze.py::bin_and_omori.
    Pipeline:
      1. Bin events into windows of bin_seconds.
      2. Detect main shocks as bins where count > μ + sigma_k·σ.
      3. Stack post-shock counts in window_bins succeeding bins.
      4. Fit log(rate-μ) = logK - p·log(τ+1) on positive excess bins.
    """
    times = np.asarray(event_times_sec, dtype=float)
    if len(times) == 0:
        return {"error": "no events"}

    t0 = times.min()
    span = times.max() - t0
    if span <= 0:
        return {"error": "zero time span"}
    n_bins = int(span / bin_seconds) + 1
    counts = np.zeros(n_bins, dtype=np.int64)
    idx = ((times - t0) / bin_seconds).astype(np.int64)
    idx = np.clip(idx, 0, n_bins - 1)
    np.add.at(counts, idx, 1)

    mu = float(counts.mean())
    sig = float(counts.std())
    threshold = mu + sigma_k * sig
    main_idx = np.where(counts > threshold)[0]
    valid = main_idx[(main_idx + window_bins) < n_bins]
    if len(valid) < 10:
        return {
            "n_main": int(len(valid)),
            "mu": mu,
            "sigma": sig,
            "threshold": threshold,
            "n_total_bins": int(n_bins),
            "note": "too few main shocks",
        }

    rates = np.zeros(window_bins)
    for tau in range(1, window_bins + 1):
        rates[tau - 1] = float(counts[valid + tau].mean() - mu)
    tau_b = np.arange(1, window_bins + 1, dtype=float)
    keep = rates > 0
    if keep.sum() < 6:
        return {
            "n_main": int(len(valid)),
            "n_pos_excess_bins": int(keep.sum()),
            "note": "no excess post-shock rate (Omori absent)",
        }

    t_fit = tau_b[keep]
    r_fit = rates[keep]
    x = np.log10(t_fit + 1.0)
    y = np.log10(r_fit)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "n_main": int(len(valid)),
        "mu": mu,
        "sigma": sig,
        "threshold": threshold,
        "p": float(-slope),
        "logK": float(intercept),
        "R2": float(r2) if r2 is not None else None,
        "n_pos_excess_bins": int(keep.sum()),
        "n_total_bins": int(n_bins),
        "bin_seconds": float(bin_seconds),
    }


def run_size_null_controls(seed: int = 42, n: int = 20_000) -> dict[str, Any]:
    """Run the same size-distribution null check used in Phase 5.

    Three synthetic non-SOC distributions; pipeline must reject power-law on all.
    """
    rng = np.random.default_rng(seed)
    out = {}
    g = np.abs(rng.normal(0.0, 1.0, size=n))
    out["gaussian_walk"] = fit_clauset_powerlaw(g, "gaussian_walk")
    e = rng.exponential(scale=1.0, size=n)
    out["exponential"] = fit_clauset_powerlaw(e, "exponential")
    iat = rng.exponential(scale=0.1, size=n)
    out["poisson_iat"] = fit_clauset_powerlaw(iat, "poisson_iat")

    correctly_rejected = all(
        bool(out[k].get("rejects_power_law", False))
        for k in ("gaussian_walk", "exponential", "poisson_iat")
    )
    out["all_rejected"] = correctly_rejected
    return out


def verdict_from_alpha_band(
    alpha: float | None,
    predicted: tuple[float, float],
    literature: tuple[float, float] | None = None,
) -> str:
    """Standard 3-tier verdict.

    CONFIRMED: in predicted band
    CONFIRMED (literature): outside narrow but within literature
    DEVIATING: outside both
    """
    if alpha is None:
        return "INCONCLUSIVE"
    if predicted[0] <= alpha <= predicted[1]:
        return "CONFIRMED"
    if literature and literature[0] <= alpha <= literature[1]:
        return "CONFIRMED (literature band)"
    return "DEVIATING"


def bootstrap_alpha_ci(
    vals: np.ndarray,
    n_boot: int = 200,
    seed: int = 42,
    discrete: bool = False,
    ci_pct: tuple[float, float] = (2.5, 97.5),
) -> dict[str, float] | None:
    """Bootstrap 95% CI on Clauset α. Used by B2 calibration."""
    try:
        import powerlaw
    except Exception:
        return None
    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals) & (vals > 0)]
    if len(vals) < 200:
        return None
    rng = np.random.default_rng(seed)
    n = len(vals)
    alphas = []
    for _ in range(n_boot):
        sample = rng.choice(vals, size=n, replace=True)
        try:
            f = powerlaw.Fit(sample, discrete=discrete, xmin_distance="D", verbose=False)
            alphas.append(float(f.power_law.alpha))
        except Exception:
            continue
    if len(alphas) < 20:
        return None
    arr = np.asarray(alphas)
    return {
        "alpha_mean": float(arr.mean()),
        "alpha_median": float(np.median(arr)),
        "alpha_std": float(arr.std()),
        "ci_low": float(np.percentile(arr, ci_pct[0])),
        "ci_high": float(np.percentile(arr, ci_pct[1])),
        "n_boot_succeeded": int(len(arr)),
    }
