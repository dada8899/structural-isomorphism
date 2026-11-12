"""Vuong (1989) likelihood-ratio test for non-nested distribution comparison.

Used to compare power-law vs lognormal / exponential / stretched_exponential
on a sample's tail above xmin.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

__all__ = ["LRResult", "vuong_lr_test"]

Distribution = Literal[
    "lognormal", "exponential", "stretched_exponential", "truncated_power_law"
]


@dataclass
class LRResult:
    """Result of a Vuong LR test power_law vs `vs`.

    Attributes:
        vs: Alternative distribution name.
        R: Normalized LR statistic. R > 0 favors power-law, R < 0 favors alternative.
        p: Two-sided p-value (small => one model significantly better).
        winner: 'power_law' / `vs` / 'inconclusive'.
        error: Error string when fit failed.
    """

    vs: str
    R: float | None = None
    p: float | None = None
    winner: str = "inconclusive"
    error: str | None = None


def vuong_lr_test(
    x_data: np.ndarray,
    vs: Distribution = "lognormal",
    discrete: bool = False,
    alpha_threshold: float = 0.1,
) -> LRResult:
    """Run Vuong 1989 LR test on power-law vs alternative.

    Args:
        x_data: Positive 1-D sample.
        vs: Alternative distribution ('lognormal' / 'exponential' /
            'stretched_exponential' / 'truncated_power_law').
        discrete: Pass-through to powerlaw.Fit.
        alpha_threshold: p-value cutoff for declaring a winner.

    Returns:
        LRResult dataclass.
    """
    try:
        import powerlaw  # type: ignore
    except Exception as exc:
        return LRResult(vs=vs, error=f"powerlaw missing: {exc}")

    x_data = np.asarray(x_data, dtype=float)
    x_data = x_data[np.isfinite(x_data) & (x_data > 0)]
    if len(x_data) < 100:
        return LRResult(vs=vs, error=f"too few values: {len(x_data)}")
    try:
        fit = powerlaw.Fit(x_data, discrete=discrete, xmin_distance="D", verbose=False)
        R, p = fit.distribution_compare("power_law", vs, normalized_ratio=True)
    except Exception as exc:
        return LRResult(vs=vs, error=f"lr test failed: {exc}")

    winner = "inconclusive"
    if R is not None and p is not None and p < alpha_threshold:
        winner = "power_law" if R > 0 else vs

    return LRResult(vs=vs, R=float(R) if R is not None else None,
                    p=float(p) if p is not None else None, winner=winner)
