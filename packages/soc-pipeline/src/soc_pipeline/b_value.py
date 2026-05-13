"""Gutenberg-Richter b-value via Aki 1965 MLE.

The G-R law: log10 N(M >= M_thresh) = a - b * M

For tectonic earthquakes, b ~= 1.0. The b-value maps to an equivalent
Clauset alpha on released energy s = 10^(1.5 M) via Hanks-Kanamori scaling:

    alpha = 1 + b / 1.5
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = ["BValueResult", "fit_b_value", "b_to_clauset_alpha"]


@dataclass
class BValueResult:
    """Result of an Aki 1965 b-value fit.

    Attributes:
        b: Gutenberg-Richter b-value.
        sigma_b: Shi-Bolt 1982 uncertainty on b.
        mc: Magnitude of completeness used to truncate the sample.
        n_above_mc: Sample size above mc.
        ci_low: Bootstrap 2.5th percentile (if bootstrap requested).
        ci_high: Bootstrap 97.5th percentile (if bootstrap requested).
        alpha_equivalent: Equivalent Clauset alpha on energy (1 + b/1.5).
        error: Error string when fit failed.
    """

    b: float | None = None
    sigma_b: float | None = None
    mc: float | None = None
    n_above_mc: int = 0
    ci_low: float | None = None
    ci_high: float | None = None
    alpha_equivalent: float | None = None
    error: str | None = None


def estimate_mc_maxc(mags: np.ndarray, bin_width: float = 0.1) -> float:
    """Magnitude of completeness by maximum-curvature.

    Returns the magnitude bin center with the highest non-cumulative count.
    """
    mags = np.asarray(mags, dtype=float)
    mn = math.floor(mags.min() * 10) / 10
    mx = math.ceil(mags.max() * 10) / 10
    bins = np.arange(mn, mx + bin_width, bin_width)
    counts, edges = np.histogram(mags, bins=bins)
    idx = int(np.argmax(counts))
    return float((edges[idx] + edges[idx + 1]) / 2)


def fit_b_value(
    magnitudes: np.ndarray,
    mc: float | None = None,
    bin_width: float = 0.1,
    bootstrap: bool = False,
    n_boot: int = 500,
    seed: int = 42,
) -> BValueResult:
    """Fit a Gutenberg-Richter b-value using Aki 1965 MLE.

    Args:
        magnitudes: 1-D array of earthquake magnitudes.
        mc: Magnitude of completeness; if None, estimated by max-curvature.
        bin_width: Magnitude binning step (used for bias correction).
        bootstrap: If True, compute 95% bootstrap CI on b.
        n_boot: Number of bootstrap resamples.
        seed: RNG seed for the bootstrap.

    Returns:
        BValueResult dataclass.
    """
    mags = np.asarray(magnitudes, dtype=float)
    mags = mags[np.isfinite(mags)]
    if len(mags) < 50:
        return BValueResult(error=f"too few magnitudes: {len(mags)}")

    if mc is None:
        mc = estimate_mc_maxc(mags, bin_width=bin_width)
    above = mags[mags >= mc]
    n = int(len(above))
    if n < 50:
        return BValueResult(error=f"too few events above Mc={mc}: n={n}")

    mean_mag = float(np.mean(above))
    b = math.log10(math.e) / (mean_mag - (mc - bin_width / 2))
    var = float(np.sum((above - mean_mag) ** 2) / (n * (n - 1)))
    sigma_b = 2.3 * (b ** 2) * math.sqrt(var)

    ci_low: float | None = None
    ci_high: float | None = None
    if bootstrap:
        rng = np.random.default_rng(seed)
        bs = np.empty(n_boot)
        for i in range(n_boot):
            sample = rng.choice(above, size=n, replace=True)
            ms = float(np.mean(sample))
            bs[i] = math.log10(math.e) / (ms - (mc - bin_width / 2))
        ci_low = float(np.percentile(bs, 2.5))
        ci_high = float(np.percentile(bs, 97.5))

    return BValueResult(
        b=float(b),
        sigma_b=float(sigma_b),
        mc=float(mc),
        n_above_mc=n,
        ci_low=ci_low,
        ci_high=ci_high,
        alpha_equivalent=b_to_clauset_alpha(b),
    )


def b_to_clauset_alpha(b: float) -> float:
    """Map G-R b-value to equivalent Clauset alpha on energy.

    Energy scaling s = 10^(1.5 M) (Hanks-Kanamori). The CDF transformation
    gives alpha = 1 + b/1.5.
    """
    return 1.0 + b / 1.5
