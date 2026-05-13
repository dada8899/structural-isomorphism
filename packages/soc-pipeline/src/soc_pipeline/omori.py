"""Omori-Utsu p-value fitting for aftershock-rate decay.

Two entry points:

    fit_omori_p(dts_sec)  — fit on a stack of aftershock delays
    bin_and_omori_from_events(event_times_sec)  — auto-detect main shocks
        and stack, for streams without main/aftershock labels.

The Omori-Utsu law: rate(t) = K / (t + c)^p
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = ["OmoriResult", "fit_omori_p", "bin_and_omori_from_events"]


@dataclass
class OmoriResult:
    """Result of an Omori-Utsu p-value fit.

    Attributes:
        p: Omori-Utsu decay exponent.
        p_sigma: Standard error on p.
        c_days: Time-shift constant (days) chosen from grid by best R^2.
        logK: log10 of productivity K.
        R2: Goodness-of-fit on log-spaced bins.
        n_aftershocks_in_fit: How many aftershocks fed the regression.
        n_bins_used: How many time bins survived the count>=3 filter.
        t_range_days: (t_min, t_max) of valid bins in days.
        n_main: For bin_and_omori only: how many main shocks were detected.
        mu: For bin_and_omori only: mean bin count.
        sigma: For bin_and_omori only: std bin count.
        threshold: For bin_and_omori only: mu + sigma_k * sigma.
        error: Error string when fit failed.
        extra: Misc fields preserved for backward-compat.
    """

    p: float | None = None
    p_sigma: float | None = None
    c_days: float | None = None
    logK: float | None = None
    R2: float | None = None
    n_aftershocks_in_fit: int = 0
    n_bins_used: int = 0
    t_range_days: tuple[float, float] | None = None
    n_main: int | None = None
    mu: float | None = None
    sigma: float | None = None
    threshold: float | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def fit_omori_p(
    dts_sec: np.ndarray,
    min_sec: float = 300.0,
    max_sec: float = 30 * 86400,
    n_bins: int = 24,
    c_grid_days: tuple[float, ...] = (0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5),
) -> OmoriResult:
    """Omori-Utsu fit on a stack of aftershock times after a main shock.

    Args:
        dts_sec: Delay (seconds) of each aftershock after its main shock.
        min_sec: Lower edge of fit window (default 5 min).
        max_sec: Upper edge of fit window (default 30 days).
        n_bins: Number of log-spaced time bins.
        c_grid_days: Grid for the c (time-shift) parameter; best by R^2 wins.

    Returns:
        OmoriResult dataclass.
    """
    dts = np.asarray(dts_sec, dtype=float)
    if len(dts) < 100:
        return OmoriResult(error=f"too few aftershocks ({len(dts)})")

    dts = dts[(dts >= min_sec) & (dts <= max_sec)]
    if len(dts) == 0:
        return OmoriResult(error="no aftershocks in [min_sec, max_sec]")

    bins = np.logspace(math.log10(min_sec), math.log10(max_sec), n_bins + 1)
    centers = np.sqrt(bins[:-1] * bins[1:])
    widths = bins[1:] - bins[:-1]
    counts, _ = np.histogram(dts, bins=bins)
    rate_per_sec = counts / widths
    valid = counts >= 3
    if valid.sum() < 6:
        return OmoriResult(error=f"too few valid bins ({int(valid.sum())})")

    t_sec = centers[valid]
    r = rate_per_sec[valid]
    w = np.sqrt(counts[valid].astype(float))

    best: dict[str, Any] | None = None
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
        p_val = -slope
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
                "p": float(p_val),
                "p_sigma": sigma_p,
                "logK": float(logK),
                "R2": float(r2) if r2 is not None else None,
            }

    if best is None:
        return OmoriResult(error="no valid Omori fit")

    return OmoriResult(
        p=best["p"],
        p_sigma=best["p_sigma"],
        c_days=best["c_days"],
        logK=best["logK"],
        R2=best["R2"],
        n_aftershocks_in_fit=int(np.sum(counts[valid])),
        n_bins_used=int(valid.sum()),
        t_range_days=(float(t_sec.min() / 86400), float(t_sec.max() / 86400)),
    )


def bin_and_omori_from_events(
    event_times_sec: np.ndarray,
    bin_seconds: float = 60.0,
    sigma_k: float = 3.0,
    window_bins: int = 60,
) -> OmoriResult:
    """Discrete-time Omori detector for event streams without main/aftershock labels.

    Pipeline:

    1. Bin events into windows of bin_seconds.
    2. Detect main shocks where count > mu + sigma_k * sigma.
    3. Stack post-shock counts in window_bins succeeding bins.
    4. Fit log(rate - mu) = logK - p * log(tau + 1) on positive-excess bins.

    Args:
        event_times_sec: 1-D array of event timestamps in seconds.
        bin_seconds: Bin width in seconds.
        sigma_k: Number of std above mean for main-shock threshold.
        window_bins: How many bins after a main shock to track.

    Returns:
        OmoriResult dataclass.
    """
    times = np.asarray(event_times_sec, dtype=float)
    if len(times) == 0:
        return OmoriResult(error="no events")

    t0 = times.min()
    span = times.max() - t0
    if span <= 0:
        return OmoriResult(error="zero time span")
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
        return OmoriResult(
            n_main=int(len(valid)),
            mu=mu,
            sigma=sig,
            threshold=threshold,
            error=f"too few main shocks ({len(valid)})",
            extra={"n_total_bins": int(n_bins)},
        )

    rates = np.zeros(window_bins)
    for tau in range(1, window_bins + 1):
        rates[tau - 1] = float(counts[valid + tau].mean() - mu)
    tau_b = np.arange(1, window_bins + 1, dtype=float)
    keep = rates > 0
    if keep.sum() < 6:
        return OmoriResult(
            n_main=int(len(valid)),
            mu=mu,
            sigma=sig,
            threshold=threshold,
            error="no excess post-shock rate (Omori absent)",
            extra={"n_pos_excess_bins": int(keep.sum())},
        )

    t_fit = tau_b[keep]
    r_fit = rates[keep]
    x = np.log10(t_fit + 1.0)
    y = np.log10(r_fit)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return OmoriResult(
        p=float(-slope),
        logK=float(intercept),
        R2=float(r2) if r2 is not None else None,
        n_main=int(len(valid)),
        mu=mu,
        sigma=sig,
        threshold=threshold,
        n_bins_used=int(keep.sum()),
        extra={
            "n_pos_excess_bins": int(keep.sum()),
            "n_total_bins": int(n_bins),
            "bin_seconds": float(bin_seconds),
        },
    )
