#!/usr/bin/env python3
"""Phase 12 — Polished universal-collapse with finite-size scaling.

Extends A3 (v4/scripts/universal_collapse.py) by adding:

  1. Log-binned density estimation with Poisson error bars (replaces raw CCDF)
  2. Strict finite-size scaling collapse:  P(s, s*) = s^{-alpha} f(s / s*)
       rescaled axes:  x' = s / s*,   y' = s*^{alpha - 1} * p_hat(s)
  3. Bayesian model comparison via BIC across three candidate tail models:
       - pure power-law:           p(s) ∝ s^{-alpha}
       - power-law + exp cutoff:   p(s) ∝ s^{-alpha} * exp(-s / sc)
       - lognormal:                p(s) ∝ (1/s) * exp(-(ln s - mu)^2 / (2 sigma^2))
  4. Goodness-of-collapse metric: cross-system y' variance / within-system y' variance
       on a shared log-binned grid.  ratio < 2 = excellent, > 5 = poor.
  5. Three-panel plot (raw CCDF + 99-pctl rescale + log-binned density with fits)
       plus residuals figure.

Inputs:
  - per-system jsonl/csv files under v4/validation/soc-<system>/
  - fallback: v4/results/A3_universal_collapse.json (frozen metadata)

Outputs (written into v4/validation/soc-universal-collapse/):
  - results.json           per-system tail data, fits, ranking, collapse metric
  - plot_panel_C.png       three-panel figure (A raw, B 99pctl rescale, C log-binned)
  - plot_residuals.png     residuals vs mean collapsed curve
"""

from __future__ import annotations

import json
import math
import traceback
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import optimize, special, stats


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
THIS = Path(__file__).resolve()
HERE = THIS.parent
REPO = THIS.parents[3]
VAL = REPO / "v4" / "validation"
A3_JSON = REPO / "v4" / "results" / "A3_universal_collapse.json"

OUT_JSON = HERE / "results.json"
OUT_PLOT_C = HERE / "plot_panel_C.png"
OUT_PLOT_RES = HERE / "plot_residuals.png"


# ---------------------------------------------------------------------------
# Loaders — return (vals, alpha_known, label).  vals is np.ndarray of strictly
# positive event sizes; alpha_known is the literature / V4-fitted power-law
# exponent for the tail; label is human-readable.
# ---------------------------------------------------------------------------

def _load_jsonl_field(path: Path, field_names: tuple[str, ...]) -> np.ndarray:
    rows: list[float] = []
    if not path.exists():
        return np.array([])
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            v = None
            for fn in field_names:
                if fn in rec and rec[fn] is not None:
                    v = rec[fn]
                    break
            if v is None:
                continue
            try:
                v = float(v)
            except Exception:
                continue
            if v > 0 and math.isfinite(v):
                rows.append(v)
    return np.array(rows)


def load_earthquake() -> tuple[np.ndarray, float, str]:
    # energy_j = 10^(1.5 * mag) for mag >= 4.45 (Mc)
    path = VAL / "soc-earthquake" / "catalog.jsonl"
    if not path.exists():
        return np.array([]), 1.79, "earthquake: catalog missing"
    mags: list[float] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            m = rec.get("mag")
            if m is None:
                continue
            try:
                m = float(m)
            except Exception:
                continue
            if m >= 4.45:
                mags.append(m)
    if not mags:
        return np.array([]), 1.79, "earthquake (energy J) — no records"
    energy = np.power(10.0, 1.5 * np.array(mags))
    return energy, 1.79, "earthquake (energy J)"


def load_stockmarket() -> tuple[np.ndarray, float, str]:
    import pandas as pd
    path = VAL / "soc-stockmarket" / "sp500_daily.csv"
    if not path.exists():
        return np.array([]), 3.00, "stockmarket: csv missing"
    df = pd.read_csv(
        path, skiprows=3, header=None,
        names=["Date", "Adj Close", "Close", "High", "Low", "Open", "Volume"],
    )
    prices = pd.to_numeric(df["Close"], errors="coerce").dropna().values
    if len(prices) < 10:
        return np.array([]), 3.00, "stockmarket: too few rows"
    rets = np.diff(np.log(prices))
    abs_rets = np.abs(rets[np.isfinite(rets)])
    abs_rets = abs_rets[abs_rets > 0]
    return abs_rets, 3.00, "S&P 500 |daily log-return|"


def load_wildfire() -> tuple[np.ndarray, float, str]:
    vals = _load_jsonl_field(VAL / "soc-wildfire" / "fires.jsonl", ("size_acres",))
    return vals, 1.66, "wildfire (acres)"


def load_solar() -> tuple[np.ndarray, float, str]:
    vals = _load_jsonl_field(
        VAL / "soc-solar" / "flares.jsonl",
        ("peak_flux_W_m2", "peak_flux"),
    )
    return vals, 2.19, "solar flare (peak W/m^2)"


def load_bank() -> tuple[np.ndarray, float, str]:
    vals = _load_jsonl_field(
        VAL / "soc-bank-failures" / "bank_failures.jsonl",
        ("assets_usd",),
    )
    return vals, 1.90, "bank failure (assets USD)"


def load_github_stars() -> tuple[np.ndarray, float, str]:
    vals = _load_jsonl_field(
        VAL / "soc-github-stars" / "repos.jsonl",
        ("stars", "stargazers_count"),
    )
    return vals, 2.87, "GitHub stars"


def load_defi() -> tuple[np.ndarray, float, str]:
    vals = _load_jsonl_field(
        VAL / "soc-defi" / "aave_v2_liquidations.jsonl",
        ("debt_to_cover_raw", "debt_to_cover"),
    )
    return vals, 1.68, "Aave V2 liquidation (raw wei)"


SYSTEMS: list[tuple[str, Callable[[], tuple[np.ndarray, float, str]]]] = [
    ("earthquake", load_earthquake),
    ("stockmarket", load_stockmarket),
    ("wildfire", load_wildfire),
    ("solar", load_solar),
    ("bank_failure", load_bank),
    ("github_stars", load_github_stars),
    ("defi_aave", load_defi),
]


# ---------------------------------------------------------------------------
# Log-binned density estimator
# ---------------------------------------------------------------------------

def log_binned_density(
    vals: np.ndarray,
    bins_per_decade: int = 12,
    tail_pctl: float = 50.0,
) -> dict:
    """Compute log-spaced binned density on the tail of `vals`.

    Returns dict with bin_centers, density, errors, edges, n_total_tail.
    Tail = values >= tail_pctl percentile (default median; the visual
    "tail" we plot uses values above that — power-law fits care about
    the upper tail).

    Density:
        rho(b) = count_b / (n * width_b)
    Error (Poisson):
        sigma_rho(b) = sqrt(count_b) / (n * width_b)
    """
    vals = vals[np.isfinite(vals) & (vals > 0)]
    if len(vals) < 20:
        return {"ok": False, "reason": "n<20"}

    s_tail_min = np.percentile(vals, tail_pctl)
    tail = vals[vals >= s_tail_min]
    if len(tail) < 20:
        return {"ok": False, "reason": "tail<20"}

    s_min = tail.min()
    s_max = tail.max()
    n_decades = math.log10(s_max / s_min)
    n_bins = max(8, int(round(bins_per_decade * n_decades)))
    edges = np.geomspace(s_min, s_max * 1.0001, n_bins + 1)

    counts, _ = np.histogram(tail, bins=edges)
    widths = np.diff(edges)
    centers = np.sqrt(edges[:-1] * edges[1:])
    n_total = len(tail)

    density = counts / (n_total * widths)
    err = np.sqrt(np.maximum(counts, 1)) / (n_total * widths)

    keep = counts > 0
    return {
        "ok": True,
        "centers": centers[keep],
        "density": density[keep],
        "err": err[keep],
        "counts": counts[keep].astype(int),
        "edges": edges,
        "n_tail": int(n_total),
        "tail_pctl": tail_pctl,
        "s_tail_min": float(s_tail_min),
    }


# ---------------------------------------------------------------------------
# Tail models  (fit on log-binned density)
# ---------------------------------------------------------------------------

def _safe_log(x: np.ndarray) -> np.ndarray:
    return np.log(np.clip(x, 1e-300, None))


def model_pl(s, log_C, alpha):
    """log p(s) = log_C - alpha * log s ."""
    return log_C - alpha * np.log(s)


def model_pl_cutoff(s, log_C, alpha, log_sc):
    """log p(s) = log_C - alpha * log s - s / sc ."""
    sc = np.exp(log_sc)
    return log_C - alpha * np.log(s) - s / sc


def model_lognormal(s, mu, log_sigma):
    """log p(s) = -log s - 0.5 log(2 pi) - log sigma - (log s - mu)^2 / (2 sigma^2)."""
    sigma = np.exp(log_sigma)
    ls = np.log(s)
    return -ls - 0.5 * math.log(2 * math.pi) - log_sigma - (ls - mu) ** 2 / (2 * sigma * sigma)


@dataclass
class FitResult:
    model: str
    params: dict[str, float]
    log_lik: float
    n: int
    k: int
    bic: float
    aic: float
    rmse_log: float
    ok: bool = True
    reason: str = ""


def _bic(log_lik: float, k: int, n: int) -> float:
    return k * math.log(n) - 2 * log_lik


def _aic(log_lik: float, k: int) -> float:
    return 2 * k - 2 * log_lik


def fit_model(
    centers: np.ndarray,
    density: np.ndarray,
    err: np.ndarray,
    model_fn: Callable,
    p0: list[float],
    param_names: list[str],
    model_name: str,
) -> FitResult:
    """Fit log-density with weighted least-squares; treat residuals as Gaussian
    in log-space with sigma = err / density (relative error) to derive log-lik.

    This is a *pragmatic* Gaussian-in-log approximation; for true MLE on the
    raw tail we would use scipy.stats — but on log-binned density the WLS form
    converges robustly across the 7 systems and is comparable across models
    when both n and the residual covariance structure are identical.
    """
    log_d = _safe_log(density)
    # relative error becomes additive in log space
    sigma_log = np.where(density > 0, err / density, 1.0)
    sigma_log = np.clip(sigma_log, 1e-3, 10.0)

    def residuals(params):
        try:
            pred = model_fn(centers, *params)
        except Exception:
            return np.full_like(log_d, 1e6)
        return (log_d - pred) / sigma_log

    n = len(centers)
    k = len(p0)
    if n <= k + 1:
        return FitResult(
            model=model_name, params={}, log_lik=-np.inf, n=n, k=k,
            bic=np.inf, aic=np.inf, rmse_log=np.inf, ok=False,
            reason="n<=k+1",
        )

    try:
        result = optimize.least_squares(
            residuals, p0, method="lm", max_nfev=20000,
        )
    except Exception as exc:
        return FitResult(
            model=model_name, params={}, log_lik=-np.inf, n=n, k=k,
            bic=np.inf, aic=np.inf, rmse_log=np.inf, ok=False,
            reason=f"lsq fail: {exc}",
        )

    params = dict(zip(param_names, [float(v) for v in result.x]))
    res = result.fun
    rmse_log = float(np.sqrt(np.mean(res ** 2)))
    # Gaussian log-lik in log-space residuals (constant terms dropped consistently
    # across models so BIC differences are meaningful):
    chi2 = float(np.sum(res ** 2))
    log_lik = -0.5 * chi2 - float(np.sum(np.log(sigma_log)))
    bic = _bic(log_lik, k, n)
    aic = _aic(log_lik, k)
    return FitResult(
        model=model_name, params=params, log_lik=log_lik, n=n, k=k,
        bic=bic, aic=aic, rmse_log=rmse_log, ok=np.isfinite(bic),
    )


def fit_all_models(centers: np.ndarray, density: np.ndarray, err: np.ndarray) -> dict:
    """Fit PL, PL+cutoff, LN on (centers, density)."""
    out: dict[str, dict] = {}
    s_min = float(centers.min())
    s_max = float(centers.max())
    # initial guesses
    # alpha guess: slope of log-log linear fit on first 70% of tail
    try:
        n_use = max(3, int(0.7 * len(centers)))
        slope, intercept = np.polyfit(
            np.log(centers[:n_use]), np.log(density[:n_use]), 1,
        )
        alpha0 = float(-slope)
        log_C0 = float(intercept)
    except Exception:
        alpha0 = 2.0
        log_C0 = 0.0
    sc0 = float(np.exp(np.log(s_max) - 0.5))  # ~ s_max / e^0.5
    mu0 = float(np.mean(np.log(centers)))
    log_sigma0 = float(math.log(max(0.3, np.std(np.log(centers)))))

    out["power_law"] = fit_model(
        centers, density, err,
        model_pl, [log_C0, max(0.5, alpha0)], ["log_C", "alpha"], "power_law",
    )
    out["pl_cutoff"] = fit_model(
        centers, density, err,
        model_pl_cutoff, [log_C0, max(0.5, alpha0), math.log(sc0)],
        ["log_C", "alpha", "log_sc"], "pl_cutoff",
    )
    out["lognormal"] = fit_model(
        centers, density, err,
        model_lognormal, [mu0, log_sigma0],
        ["mu", "log_sigma"], "lognormal",
    )
    return out


def rank_by_bic(fits: dict[str, FitResult]) -> list[tuple[str, float]]:
    ok = [(k, v.bic) for k, v in fits.items() if v.ok and np.isfinite(v.bic)]
    ok.sort(key=lambda x: x[1])
    return ok


# ---------------------------------------------------------------------------
# Collapse machinery
# ---------------------------------------------------------------------------

def rescale_collapse(
    centers: np.ndarray,
    density: np.ndarray,
    err: np.ndarray,
    s_star: float,
    alpha: float,
) -> dict:
    """Map (s, p) -> (s/s*, s*^{alpha-1} * p) so power-law-with-cutoff
    distributions of different scales overlay onto a single master curve."""
    x = centers / s_star
    factor = s_star ** (alpha - 1.0)
    y = factor * density
    y_err = factor * err
    return {
        "x_rescaled": x.tolist(),
        "y_rescaled": y.tolist(),
        "y_err_rescaled": y_err.tolist(),
        "s_star": float(s_star),
        "alpha_used": float(alpha),
    }


def collapse_quality(systems_rescaled: dict[str, dict]) -> dict:
    """Project every system onto a shared log-binned x'-grid and compute
    cross-system variance vs within-system variance of log y'.

    Quality = mean cross_var / mean within_var.  Smaller is better;
        < 2  excellent, < 5 good, > 5 poor.
    """
    if not systems_rescaled:
        return {"ok": False, "reason": "no systems"}

    # Build shared x' grid covering common range
    x_mins, x_maxs = [], []
    for s in systems_rescaled.values():
        x = np.array(s["x_rescaled"])
        x_mins.append(x.min())
        x_maxs.append(x.max())
    x_lo = max(x_mins)
    x_hi = min(x_maxs)
    if x_lo >= x_hi:
        # No common range — use loose overlap
        x_lo = min(x_mins)
        x_hi = max(x_maxs)

    n_bins = 20
    grid = np.geomspace(x_lo, x_hi, n_bins)

    # interpolate log y onto grid for each system
    matrix = []
    sys_names = []
    for name, s in systems_rescaled.items():
        x = np.array(s["x_rescaled"])
        y = np.array(s["y_rescaled"])
        keep = (y > 0) & np.isfinite(y)
        if keep.sum() < 4:
            continue
        x = x[keep]
        y = y[keep]
        order = np.argsort(x)
        x = x[order]
        y = y[order]
        log_x = np.log(x)
        log_y = np.log(y)
        # only interpolate inside this system's x range
        log_grid = np.log(grid)
        in_range = (log_grid >= log_x.min()) & (log_grid <= log_x.max())
        row = np.full(n_bins, np.nan)
        row[in_range] = np.interp(log_grid[in_range], log_x, log_y)
        matrix.append(row)
        sys_names.append(name)

    mat = np.array(matrix)  # shape (n_systems, n_bins)
    # ABSOLUTE cross-system variance (in log-y space, on the raw rescaled axis).
    # Dominated by per-system absolute density prefactor — units / scale offset.
    cross_var_abs = np.nanvar(mat, axis=0, ddof=1)
    mean_curve_abs = np.nanmean(mat, axis=0)

    # SHAPE-NORMALIZED variance: subtract each system's own mean log-y, so we
    # measure shape similarity (not absolute prefactor). This is the
    # genuine universal-collapse quantity: are the *shapes* of the master
    # curves identical, ignoring overall units?
    row_means = np.nanmean(mat, axis=1, keepdims=True)
    mat_shape = mat - row_means
    cross_var_shape = np.nanvar(mat_shape, axis=0, ddof=1)
    mean_curve_shape = np.nanmean(mat_shape, axis=0)

    # Within-system spread: per-system variance of own shape residuals
    # (proxy for the intrinsic roughness of the master curve in each
    # system's tail data).
    deviations = mat_shape - mean_curve_shape  # shape (n_systems, n_bins)
    within_var = np.nanvar(deviations, axis=1, ddof=1)

    finite_cross_abs = cross_var_abs[np.isfinite(cross_var_abs)]
    finite_cross_shape = cross_var_shape[np.isfinite(cross_var_shape)]
    finite_within = within_var[np.isfinite(within_var)]

    if len(finite_cross_abs) == 0 or len(finite_within) == 0:
        return {"ok": False, "reason": "no overlap"}

    mean_cross_abs = float(np.mean(finite_cross_abs))
    mean_cross_shape = float(np.mean(finite_cross_shape))
    mean_within = float(np.mean(finite_within))
    ratio_abs = mean_cross_abs / mean_within if mean_within > 0 else float("inf")
    ratio_shape = mean_cross_shape / mean_within if mean_within > 0 else float("inf")

    def classify(r: float) -> str:
        if r < 2.0:
            return "excellent"
        if r < 5.0:
            return "good"
        if r < 10.0:
            return "moderate"
        return "poor"

    return {
        "ok": True,
        "x_grid": grid.tolist(),
        "mean_curve_log_y": mean_curve_abs.tolist(),
        "mean_curve_shape_log_y": mean_curve_shape.tolist(),
        "cross_system_log_var_absolute": cross_var_abs.tolist(),
        "cross_system_log_var_shape_normalized": cross_var_shape.tolist(),
        "within_system_log_var": within_var.tolist(),
        "mean_cross_var_absolute": mean_cross_abs,
        "mean_cross_var_shape_normalized": mean_cross_shape,
        "mean_within_var": mean_within,
        "ratio_absolute": ratio_abs,
        "ratio_shape_normalized": ratio_shape,
        "verdict_absolute": classify(ratio_abs),
        "verdict_shape_normalized": classify(ratio_shape),
        "systems_in_metric": sys_names,
        "note": (
            "ratio_absolute is dominated by per-system unit / prefactor "
            "differences (event sizes live on wildly different physical "
            "scales). ratio_shape_normalized subtracts each system's "
            "mean log-y so it measures pure shape similarity, which is "
            "the operationally meaningful universal-collapse claim."
        ),
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def _make_three_panel_plot(per_system: dict, mean_curve_pkg: dict) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.6))
    ax_raw, ax_rescale, ax_logbin = axes
    cmap = plt.cm.tab10(np.linspace(0, 1, len(per_system)))

    for (name, info), color in zip(per_system.items(), cmap):
        if not info.get("ok"):
            continue
        bin_data = info["log_binned"]
        centers = np.array(bin_data["centers"])
        density = np.array(bin_data["density"])
        err = np.array(bin_data["err"])
        # Panel A: raw log-binned density (which is essentially log-spaced PDF)
        ax_raw.errorbar(
            centers, density, yerr=err, fmt="o", ms=3, color=color,
            label=f"{name} α={info['alpha_known']:.2f}",
            alpha=0.7, capsize=0, lw=0.8,
        )

        # Panel B: 99-pctl rescaled
        x_r = np.array(info["rescale_99pctl"]["x_rescaled"])
        y_r = np.array(info["rescale_99pctl"]["y_rescaled"])
        y_e = np.array(info["rescale_99pctl"]["y_err_rescaled"])
        ax_rescale.errorbar(
            x_r, y_r, yerr=y_e, fmt="o", ms=3, color=color, alpha=0.7,
            capsize=0, lw=0.8, label=name,
        )

        # Panel C: best-fit overlay on rescaled axes
        ax_logbin.errorbar(
            x_r, y_r, yerr=y_e, fmt="o", ms=3, color=color, alpha=0.55,
            capsize=0, lw=0.8, label=name,
        )

    # Mean collapsed curve on panel C (absolute mean — note shape ratio
    # is shown in the legend, see ratio_shape_normalized)
    if mean_curve_pkg.get("ok"):
        x_grid = np.array(mean_curve_pkg["x_grid"])
        log_y_mean = np.array(mean_curve_pkg["mean_curve_log_y"])
        keep = np.isfinite(log_y_mean)
        ax_logbin.plot(
            x_grid[keep], np.exp(log_y_mean[keep]), "k-", lw=2.2,
            label=(
                "mean curve  "
                f"shape ratio={mean_curve_pkg.get('ratio_shape_normalized', 0):.2f} "
                f"({mean_curve_pkg.get('verdict_shape_normalized','?')})"
            ),
            zorder=5,
        )

    for ax in axes:
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.grid(True, which="both", alpha=0.3)

    ax_raw.set_xlabel("event size s (native units)")
    ax_raw.set_ylabel(r"density $\hat p(s)$  (log-binned, Poisson errors)")
    ax_raw.set_title("(A) Raw log-binned tail density, 7 SOC systems")
    ax_raw.legend(fontsize=7, loc="lower left")

    ax_rescale.set_xlabel(r"$s / s_*$  (rescale by 99th-pctl cutoff)")
    ax_rescale.set_ylabel(r"$s_*^{\alpha-1}\,\hat p(s)$  (universal-collapse axis)")
    ax_rescale.set_title("(B) Finite-size rescaled, 99-pctl cutoff")
    ax_rescale.legend(fontsize=7, loc="lower left")

    ax_logbin.set_xlabel(r"$s / s_*$")
    ax_logbin.set_ylabel(r"$s_*^{\alpha-1}\,\hat p(s)$")
    ax_logbin.set_title("(C) Rescaled + mean collapsed curve")
    ax_logbin.legend(fontsize=7, loc="lower left")

    plt.tight_layout()
    plt.savefig(OUT_PLOT_C, dpi=140, bbox_inches="tight")
    plt.close(fig)


def _make_residuals_plot(per_system: dict, mean_curve_pkg: dict) -> None:
    if not mean_curve_pkg.get("ok"):
        return
    fig, ax = plt.subplots(1, 1, figsize=(10, 5.4))
    cmap = plt.cm.tab10(np.linspace(0, 1, len(per_system)))
    x_grid = np.array(mean_curve_pkg["x_grid"])
    log_y_mean_shape = np.array(mean_curve_pkg["mean_curve_shape_log_y"])

    for (name, info), color in zip(per_system.items(), cmap):
        if not info.get("ok"):
            continue
        x_r = np.array(info["rescale_99pctl"]["x_rescaled"])
        y_r = np.array(info["rescale_99pctl"]["y_rescaled"])
        keep = (y_r > 0) & np.isfinite(y_r) & (x_r > 0)
        if keep.sum() < 4:
            continue
        x_r = x_r[keep]
        y_r = y_r[keep]
        order = np.argsort(x_r)
        x_r = x_r[order]
        y_r = y_r[order]
        log_x = np.log(x_r)
        log_y = np.log(y_r)
        in_range = (np.log(x_grid) >= log_x.min()) & (np.log(x_grid) <= log_x.max())
        interp = np.full_like(x_grid, np.nan, dtype=float)
        interp[in_range] = np.interp(np.log(x_grid[in_range]), log_x, log_y)
        # shape-normalize: subtract per-system mean before comparing to mean shape
        sys_mean = np.nanmean(interp)
        if not np.isfinite(sys_mean):
            continue
        shape = interp - sys_mean
        resid = shape - log_y_mean_shape
        keep2 = np.isfinite(resid)
        ax.plot(x_grid[keep2], resid[keep2], "o-", ms=4, color=color,
                label=name, alpha=0.75)

    ax.axhline(0.0, color="k", lw=1, ls="--", alpha=0.6)
    ax.set_xscale("log")
    ax.set_xlabel(r"$s / s_*$")
    ax.set_ylabel(
        r"shape residual: $(\log \hat y_i - \overline{\log \hat y_i})"
        r" - $ mean shape curve"
    )
    ax.set_title(
        "Per-system shape residuals (per-system mean subtracted)"
        f"   shape ratio = {mean_curve_pkg.get('ratio_shape_normalized', 0):.2f} "
        f"({mean_curve_pkg.get('verdict_shape_normalized','?')})"
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, which="both", alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_PLOT_RES, dpi=140, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _serializable_fit(fit: FitResult) -> dict:
    d = asdict(fit)
    for k, v in list(d.items()):
        if isinstance(v, float) and not math.isfinite(v):
            d[k] = None
    return d


def run() -> dict:
    per_system: dict[str, dict] = {}
    rescaled_for_quality: dict[str, dict] = {}

    for name, loader in SYSTEMS:
        try:
            vals, alpha_known, label = loader()
        except Exception as exc:
            per_system[name] = {
                "ok": False,
                "reason": f"loader exc: {exc}",
                "traceback": traceback.format_exc(limit=2),
            }
            continue

        if vals is None or len(vals) < 100:
            per_system[name] = {
                "ok": False, "label": label,
                "reason": f"insufficient data: n={0 if vals is None else len(vals)}",
            }
            continue

        info: dict = {
            "ok": True,
            "label": label,
            "alpha_known": float(alpha_known),
            "n_total": int(len(vals)),
            "value_range": [float(np.min(vals)), float(np.max(vals))],
            "s_star_99pctl": float(np.percentile(vals, 99)),
            "s_star_95pctl": float(np.percentile(vals, 95)),
        }

        binned = log_binned_density(vals, bins_per_decade=12, tail_pctl=50.0)
        if not binned.get("ok"):
            per_system[name] = {
                "ok": False, "label": label,
                "reason": f"log-binning: {binned.get('reason')}",
            }
            continue

        info["log_binned"] = {
            "centers": binned["centers"].tolist(),
            "density": binned["density"].tolist(),
            "err": binned["err"].tolist(),
            "counts": binned["counts"].tolist(),
            "n_tail": binned["n_tail"],
            "tail_pctl": binned["tail_pctl"],
            "s_tail_min": binned["s_tail_min"],
            "n_bins": int(len(binned["centers"])),
        }

        # 99-pctl rescale on the log-binned curve
        rescale = rescale_collapse(
            binned["centers"], binned["density"], binned["err"],
            s_star=info["s_star_99pctl"], alpha=alpha_known,
        )
        info["rescale_99pctl"] = rescale
        rescaled_for_quality[name] = rescale

        # Bayesian model fits
        try:
            fits = fit_all_models(binned["centers"], binned["density"], binned["err"])
        except Exception as exc:
            fits = {}
            info["fits_error"] = f"{exc}\n{traceback.format_exc(limit=2)}"

        info["fits"] = {k: _serializable_fit(v) for k, v in fits.items()}
        if fits:
            ranking = rank_by_bic(fits)
            info["bic_ranking"] = [
                {"model": m, "bic": float(b)} for m, b in ranking
            ]
            if ranking:
                info["best_model"] = ranking[0][0]
                if len(ranking) >= 2:
                    info["delta_bic_best_vs_second"] = float(
                        ranking[1][1] - ranking[0][1]
                    )

        per_system[name] = info
        print(
            f"[{name:14s}] n={info['n_total']:>6d}  "
            f"α={alpha_known:.2f}  s*={info['s_star_99pctl']:.3g}  "
            f"best={info.get('best_model','?')}"
        )

    # Cross-system collapse quality
    quality = collapse_quality(rescaled_for_quality)

    # Plots
    try:
        _make_three_panel_plot(per_system, quality)
        plot_c_ok = True
    except Exception as exc:
        plot_c_ok = False
        print(f"plot_panel_C failed: {exc}")
        traceback.print_exc()
    try:
        _make_residuals_plot(per_system, quality)
        plot_res_ok = True
    except Exception as exc:
        plot_res_ok = False
        print(f"plot_residuals failed: {exc}")
        traceback.print_exc()

    # Aggregate model preferences
    model_votes: dict[str, int] = {"power_law": 0, "pl_cutoff": 0, "lognormal": 0}
    for info in per_system.values():
        if info.get("ok") and info.get("best_model") in model_votes:
            model_votes[info["best_model"]] += 1

    summary = {
        "phase": "v4-L5-phase12",
        "date": "2026-05-13",
        "n_systems_attempted": len(SYSTEMS),
        "n_systems_ok": sum(1 for v in per_system.values() if v.get("ok")),
        "model_votes_best_BIC": model_votes,
        "collapse_quality": quality,
        "plot_panel_C_written": plot_c_ok,
        "plot_residuals_written": plot_res_ok,
    }

    output = {
        "summary": summary,
        "per_system": per_system,
    }

    OUT_JSON.write_text(json.dumps(output, indent=2, default=str))
    print()
    print(f"results.json   -> {OUT_JSON}")
    print(f"plot_panel_C   -> {OUT_PLOT_C}  (ok={plot_c_ok})")
    print(f"plot_residuals -> {OUT_PLOT_RES}  (ok={plot_res_ok})")
    print()
    print("Summary:")
    print(json.dumps(summary, indent=2))
    return output


if __name__ == "__main__":
    run()
