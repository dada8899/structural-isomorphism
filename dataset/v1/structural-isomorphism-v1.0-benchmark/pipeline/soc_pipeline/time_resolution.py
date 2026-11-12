"""Time-resolution bin sweep — Phase 13 stability check.

If a fitted alpha is genuinely SOC, it should be insensitive to the binning
time resolution over a wide range. Sweep bin sizes and check alpha stability.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from .fit import fit_clauset_powerlaw

__all__ = ["time_resolution_sweep"]


def time_resolution_sweep(
    event_times: np.ndarray,
    bin_sizes_sec: Sequence[float] = (60.0, 300.0, 900.0, 3600.0, 21600.0, 86400.0),
    stability_threshold: float = 0.15,
) -> dict[str, Any]:
    """Bin events at multiple time resolutions and fit alpha to each.

    Args:
        event_times: 1-D array of event timestamps in seconds.
        bin_sizes_sec: Sequence of bin sizes (seconds) to sweep.
        stability_threshold: Max alpha spread (max-min) for "stable" verdict.

    Returns:
        dict with:
          - 'sweep': list of {bin_seconds, alpha, n_tail, xmin, error?}
          - 'alpha_min', 'alpha_max', 'alpha_spread'
          - 'is_stable': True if spread < threshold

    Notes:
        Genuinely SOC processes should be roughly bin-invariant. Sharp
        alpha dependence on bin size suggests artifacts (e.g., Poisson
        smoothing from undersampling).
    """
    times = np.asarray(event_times, dtype=float)
    times = times[np.isfinite(times)]
    if len(times) < 100:
        return {"error": f"too few events: {len(times)}"}

    t0 = times.min()
    span = times.max() - t0
    sweep: list[dict[str, Any]] = []
    alphas: list[float] = []
    for bs in bin_sizes_sec:
        n_bins = int(span / bs) + 1
        if n_bins < 50:
            sweep.append({"bin_seconds": float(bs), "error": f"too few bins: {n_bins}"})
            continue
        counts = np.zeros(n_bins, dtype=np.int64)
        idx = ((times - t0) / bs).astype(np.int64)
        idx = np.clip(idx, 0, n_bins - 1)
        np.add.at(counts, idx, 1)
        nonzero = counts[counts > 0].astype(float)
        if len(nonzero) < 100:
            sweep.append({"bin_seconds": float(bs), "error": f"too few nonzero bins: {len(nonzero)}"})
            continue
        fit = fit_clauset_powerlaw(nonzero, name=f"bin_{bs}", discrete=True)
        entry: dict[str, Any] = {"bin_seconds": float(bs)}
        if fit.error:
            entry["error"] = fit.error
        else:
            entry["alpha"] = fit.alpha
            entry["xmin"] = fit.xmin
            entry["n_tail"] = fit.n_tail
            if fit.alpha is not None:
                alphas.append(fit.alpha)
        sweep.append(entry)

    if not alphas:
        return {"sweep": sweep, "error": "no successful fits"}

    arr = np.asarray(alphas)
    spread = float(arr.max() - arr.min())
    return {
        "sweep": sweep,
        "alpha_min": float(arr.min()),
        "alpha_max": float(arr.max()),
        "alpha_spread": spread,
        "alpha_median": float(np.median(arr)),
        "is_stable": spread < stability_threshold,
    }
