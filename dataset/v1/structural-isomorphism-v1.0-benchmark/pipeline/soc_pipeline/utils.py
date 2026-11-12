"""Shared utilities — CCDF helper + verdict logic."""
from __future__ import annotations

import numpy as np

__all__ = ["empirical_ccdf", "verdict_from_alpha_band"]


def empirical_ccdf(
    vals: np.ndarray, n_points: int = 200
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Compute the complementary CDF P(X > s) on a log-spaced grid.

    Args:
        vals: 1-D array of positive values.
        n_points: Number of log-spaced sample points.

    Returns:
        (grid, ccdf) — both shape (n_points,). Returns (None, None) if input
        is empty after filtering for positive finite values.
    """
    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals) & (vals > 0)]
    if len(vals) == 0:
        return None, None
    vals = np.sort(vals)
    grid = np.geomspace(vals.min() * 1.001, vals.max(), n_points)
    n = len(vals)
    ccdf = np.array([(vals > g).sum() / n for g in grid])
    return grid, ccdf


def verdict_from_alpha_band(
    alpha: float | None,
    predicted: tuple[float, float],
    literature: tuple[float, float] | None = None,
) -> str:
    """Standard 3-tier SOC verdict.

    Args:
        alpha: Fitted alpha value or None.
        predicted: (low, high) first-principles prediction band.
        literature: (low, high) wider literature-acceptance band. Optional.

    Returns:
        'CONFIRMED' | 'CONFIRMED (literature band)' | 'DEVIATING' | 'INCONCLUSIVE'
    """
    if alpha is None:
        return "INCONCLUSIVE"
    if predicted[0] <= alpha <= predicted[1]:
        return "CONFIRMED"
    if literature and literature[0] <= alpha <= literature[1]:
        return "CONFIRMED (literature band)"
    return "DEVIATING"
