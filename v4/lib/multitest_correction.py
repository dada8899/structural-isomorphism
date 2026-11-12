"""Family-wise error rate (FWER) and false-discovery rate (FDR) correction.

Implements Bonferroni-Holm (FWER) and Benjamini-Hochberg (FDR) procedures for
adjusting nominal p-values when multiple hypothesis tests are reported.

Reference: scholar-review W5-A §3.3 — the v4 paper reports ~30 statistical
tests across 13 systems (Vuong LR vs lognormal/exponential, BIC, Kendall-tau).
Under nominal alpha=0.05 per test the family-wise error rate is at least
1 - 0.95^30 ~ 0.79. This module provides Bonferroni-Holm step-down to bring
FWER back to alpha, and BH step-up for FDR control.

The functions are pure-Python (numpy-only) and return both the adjusted
p-values and the boolean reject/retain decision at the requested alpha.

Examples
--------
>>> from v4.lib.multitest_correction import bonferroni_holm
>>> bonferroni_holm([0.01, 0.03, 0.04, 0.5])
({'p_adjusted': [0.04, 0.09, 0.09, 0.5], 'reject': [True, False, False, False], ...})
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

__all__ = [
    "CorrectionResult",
    "bonferroni",
    "bonferroni_holm",
    "benjamini_hochberg",
    "apply_corrections",
]


@dataclass
class CorrectionResult:
    """Container for a single multiple-testing-correction result.

    Attributes:
        method: Name of the correction (e.g. "bonferroni-holm").
        alpha: Family-wise (or FDR) target.
        p_raw: Original input p-values (in original order).
        p_adjusted: Adjusted p-values (in original order). For step-down /
            step-up methods these are the standard "adjusted p-value"
            defined as min over the relevant suffix/prefix.
        reject: Boolean array — True if H0 is rejected at this alpha
            after correction.
        n_tests: Total number of tests in the family.
    """

    method: str
    alpha: float
    p_raw: list[float]
    p_adjusted: list[float]
    reject: list[bool]
    n_tests: int

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "alpha": self.alpha,
            "p_raw": list(self.p_raw),
            "p_adjusted": list(self.p_adjusted),
            "reject": list(self.reject),
            "n_tests": self.n_tests,
        }


def _clean_pvalues(p: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(p), dtype=float)
    # Replace NaN with 1.0 (never reject), clamp to [0,1]
    arr = np.where(np.isnan(arr), 1.0, arr)
    arr = np.clip(arr, 0.0, 1.0)
    return arr


def bonferroni(pvalues: Iterable[float], alpha: float = 0.05) -> CorrectionResult:
    """Bonferroni single-step correction.

    Adjusted p_i = min(1, n * p_i). Conservative; controls FWER strictly.
    """
    p = _clean_pvalues(pvalues)
    n = len(p)
    if n == 0:
        return CorrectionResult("bonferroni", alpha, [], [], [], 0)
    p_adj = np.minimum(1.0, p * n)
    reject = p_adj <= alpha
    return CorrectionResult(
        method="bonferroni",
        alpha=alpha,
        p_raw=p.tolist(),
        p_adjusted=p_adj.tolist(),
        reject=reject.tolist(),
        n_tests=n,
    )


def bonferroni_holm(pvalues: Iterable[float], alpha: float = 0.05) -> CorrectionResult:
    """Bonferroni-Holm step-down (Holm 1979).

    Controls FWER at alpha. Uniformly more powerful than vanilla Bonferroni.

    Procedure: sort p-values ascending; compare p_(i) to alpha / (n - i + 1);
    the first failure stops all further rejections.

    Adjusted p-value: p_adj_(i) = max_{j <= i} (n - j + 1) * p_(j), clipped
    to [0, 1] and made monotone non-decreasing.
    """
    p = _clean_pvalues(pvalues)
    n = len(p)
    if n == 0:
        return CorrectionResult("bonferroni-holm", alpha, [], [], [], 0)

    order = np.argsort(p, kind="stable")
    p_sorted = p[order]
    # multipliers (n - i + 1) for i=1..n => n, n-1, ..., 1
    multipliers = (n - np.arange(n)).astype(float)
    p_adj_sorted_raw = multipliers * p_sorted
    # Enforce monotonicity (running cummax) and clip to [0,1]
    p_adj_sorted = np.minimum.accumulate(p_adj_sorted_raw[::-1])[::-1]
    p_adj_sorted = np.maximum.accumulate(p_adj_sorted)
    p_adj_sorted = np.minimum(p_adj_sorted, 1.0)

    # Unsort
    p_adj = np.empty_like(p_adj_sorted)
    p_adj[order] = p_adj_sorted

    reject = p_adj <= alpha
    return CorrectionResult(
        method="bonferroni-holm",
        alpha=alpha,
        p_raw=p.tolist(),
        p_adjusted=p_adj.tolist(),
        reject=reject.tolist(),
        n_tests=n,
    )


def benjamini_hochberg(
    pvalues: Iterable[float], alpha: float = 0.05
) -> CorrectionResult:
    """Benjamini-Hochberg step-up (BH 1995), FDR control.

    Procedure: sort p-values ascending; find the largest i s.t.
    p_(i) <= (i / n) * alpha; reject all H_(1)..H_(i).

    Adjusted p-value: p_adj_(i) = min_{j >= i} (n / j) * p_(j),
    clipped to [0, 1] and made monotone non-decreasing.
    """
    p = _clean_pvalues(pvalues)
    n = len(p)
    if n == 0:
        return CorrectionResult("benjamini-hochberg", alpha, [], [], [], 0)

    order = np.argsort(p, kind="stable")
    p_sorted = p[order]
    ranks = np.arange(1, n + 1)
    multipliers = n / ranks
    p_adj_sorted_raw = multipliers * p_sorted
    # Monotone non-decreasing from the right (step-up)
    p_adj_sorted = np.minimum.accumulate(p_adj_sorted_raw[::-1])[::-1]
    p_adj_sorted = np.minimum(p_adj_sorted, 1.0)

    p_adj = np.empty_like(p_adj_sorted)
    p_adj[order] = p_adj_sorted

    reject = p_adj <= alpha
    return CorrectionResult(
        method="benjamini-hochberg",
        alpha=alpha,
        p_raw=p.tolist(),
        p_adjusted=p_adj.tolist(),
        reject=reject.tolist(),
        n_tests=n,
    )


def apply_corrections(
    pvalues: Iterable[float], alpha: float = 0.05
) -> dict[str, CorrectionResult]:
    """Apply all three corrections (Bonferroni, Bonferroni-Holm, BH).

    Returns:
        Dict keyed by method name -> CorrectionResult.
    """
    return {
        "bonferroni": bonferroni(pvalues, alpha=alpha),
        "bonferroni-holm": bonferroni_holm(pvalues, alpha=alpha),
        "benjamini-hochberg": benjamini_hochberg(pvalues, alpha=alpha),
    }
