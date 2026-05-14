"""Unified one-call validation API.

This is the canonical entry point for users who want a quick PASS/FAIL/INCONCLUSIVE
verdict on whether a sample looks like a self-organized criticality (SOC) power-law
relative to a pre-registered band.

The contract:

    >>> from soc_pipeline import validate
    >>> v = validate(data, label="earthquake_M", expected_band=(1.9, 2.1))
    >>> print(v.verdict, v.alpha, v.in_band)

INCONCLUSIVE rules:
    - n_total < min_samples (default 100)
    - powerlaw fit raises / returns NaN
    - bootstrap CI cannot be computed (too few values)
    - LR test prefers lognormal or exponential alternative with high confidence

PASS rules:
    - Fit succeeds
    - alpha lies inside expected_band (if provided); otherwise just "fit OK + no
      alternative preferred" -> PASS
    - No alternative model (lognormal / exponential) significantly beats the
      power-law (R > 0 OR p >= 0.1)

FAIL rules:
    - Fit succeeds but alpha is *outside* the pre-registered band
    - or an alternative model significantly beats power-law (R<0 AND p<0.1)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .bootstrap import bootstrap_ci
from .fit import fit_clauset_powerlaw

__all__ = ["Verdict", "validate"]


@dataclass
class Verdict:
    """Unified verdict returned by :func:`validate`.

    Attributes:
        verdict: One of ``"PASS"`` / ``"FAIL"`` / ``"INCONCLUSIVE"``.
        alpha: Power-law exponent estimate (Clauset 2009 MLE).
        alpha_ci_lo: Lower bound of 95% bootstrap CI on alpha.
        alpha_ci_hi: Upper bound of 95% bootstrap CI on alpha.
        xmin: Lower bound selected by KS minimisation.
        n_tail: Sample size at and above ``xmin``.
        ks_distance: Kolmogorov-Smirnov distance of empirical tail vs fit.
        vs_lognormal_R: Vuong LR statistic (positive favours power-law).
        vs_lognormal_p: Two-sided p-value of LR vs lognormal.
        vs_exponential_R: Vuong LR statistic vs exponential.
        vs_exponential_p: Two-sided p-value of LR vs exponential.
        pre_registered_band: Optional ``(low, high)`` band supplied by caller.
        in_band: True/False if alpha falls inside the pre-registered band, or
            None when no band was supplied / fit failed.
        label: Caller-supplied label.
        reason: Human-readable reason string (most useful for INCONCLUSIVE).
    """

    verdict: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    alpha: float
    alpha_ci_lo: float
    alpha_ci_hi: float
    xmin: float
    n_tail: int
    ks_distance: float
    vs_lognormal_R: float
    vs_lognormal_p: float
    vs_exponential_R: float
    vs_exponential_p: float
    pre_registered_band: tuple[float, float] | None
    in_band: bool | None
    label: str = "data"
    reason: str = ""


_NAN = float("nan")


def _inconclusive(
    label: str,
    reason: str,
    *,
    band: tuple[float, float] | None = None,
    alpha: float = _NAN,
    xmin: float = _NAN,
    n_tail: int = 0,
    ks: float = _NAN,
) -> Verdict:
    """Build an INCONCLUSIVE Verdict with default-NaN numeric fields."""
    return Verdict(
        verdict="INCONCLUSIVE",
        alpha=alpha,
        alpha_ci_lo=_NAN,
        alpha_ci_hi=_NAN,
        xmin=xmin,
        n_tail=int(n_tail),
        ks_distance=ks,
        vs_lognormal_R=_NAN,
        vs_lognormal_p=_NAN,
        vs_exponential_R=_NAN,
        vs_exponential_p=_NAN,
        pre_registered_band=band,
        in_band=None,
        label=label,
        reason=reason,
    )


def validate(
    data: np.ndarray,
    label: str = "data",
    expected_band: tuple[float, float] | None = None,
    *,
    discrete: bool = False,
    n_boot: int = 200,
    seed: int = 42,
    min_samples: int = 100,
) -> Verdict:
    """Run the canonical Clauset-grade SOC validation on a 1-D sample.

    Args:
        data: 1-D positive array of event sizes / durations.
        label: Caller-supplied label for round-tripping (e.g. ``"earthquake_M"``).
        expected_band: Optional ``(low, high)`` pre-registered band on alpha.
            When supplied, the verdict checks whether the fitted alpha falls
            inside this band; otherwise the band check is skipped.
        discrete: Pass-through to :func:`fit_clauset_powerlaw`.
        n_boot: Number of bootstrap resamples for the CI (default 200).
        seed: RNG seed for reproducibility of the bootstrap CI.
        min_samples: Minimum sample size; below this returns INCONCLUSIVE.

    Returns:
        A :class:`Verdict` with the unified PASS/FAIL/INCONCLUSIVE outcome.
    """
    arr = np.asarray(data, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    n_total = int(arr.size)

    if n_total < min_samples:
        return _inconclusive(
            label,
            f"too few values: {n_total} < {min_samples}",
            band=expected_band,
        )

    fit = fit_clauset_powerlaw(arr, name=label, discrete=discrete)
    if fit.error or fit.alpha is None or not np.isfinite(fit.alpha):
        return _inconclusive(
            label,
            f"fit failed: {fit.error or 'non-finite alpha'}",
            band=expected_band,
        )

    if n_boot <= 0:
        # caller explicitly disabled bootstrap (fast path for tests / CI)
        ci_lo, ci_hi = _NAN, _NAN
    else:
        boot = bootstrap_ci(arr, n_boot=n_boot, seed=seed, discrete=discrete)
        if boot.error or boot.ci_low is None or boot.ci_high is None:
            ci_lo, ci_hi = _NAN, _NAN
        else:
            ci_lo = float(boot.ci_low)
            ci_hi = float(boot.ci_high)

    alpha = float(fit.alpha)
    xmin = float(fit.xmin) if fit.xmin is not None else _NAN
    n_tail = int(fit.n_tail)
    ks = float(fit.ks_statistic) if fit.ks_statistic is not None else _NAN

    R_ln = float(fit.vs_lognormal_R) if fit.vs_lognormal_R is not None else _NAN
    p_ln = float(fit.vs_lognormal_p) if fit.vs_lognormal_p is not None else _NAN
    R_exp = float(fit.vs_exponential_R) if fit.vs_exponential_R is not None else _NAN
    p_exp = float(fit.vs_exponential_p) if fit.vs_exponential_p is not None else _NAN

    # band check
    if expected_band is None:
        in_band: bool | None = None
    else:
        lo, hi = expected_band
        in_band = bool(lo <= alpha <= hi)

    # alternative-model rejection (Clauset 2009 §6 rule of thumb)
    rejects = False
    rejection_reason = ""
    if np.isfinite(R_ln) and R_ln < 0 and np.isfinite(p_ln) and p_ln < 0.1:
        rejects = True
        rejection_reason = (
            f"lognormal preferred: R={R_ln:.2f} p={p_ln:.3f}"
        )
    if np.isfinite(R_exp) and R_exp < 0 and np.isfinite(p_exp) and p_exp < 0.1:
        rejects = True
        rejection_reason = (
            f"exponential preferred: R={R_exp:.2f} p={p_exp:.3f}"
        )

    if rejects:
        verdict: Literal["PASS", "FAIL", "INCONCLUSIVE"] = "FAIL"
        reason = rejection_reason
    elif expected_band is not None and not in_band:
        verdict = "FAIL"
        reason = (
            f"alpha={alpha:.3f} outside pre-registered band "
            f"[{expected_band[0]:.3f}, {expected_band[1]:.3f}]"
        )
    else:
        verdict = "PASS"
        if expected_band is not None:
            reason = (
                f"alpha={alpha:.3f} inside band "
                f"[{expected_band[0]:.3f}, {expected_band[1]:.3f}]"
            )
        else:
            reason = f"alpha={alpha:.3f} (no band check)"

    return Verdict(
        verdict=verdict,
        alpha=alpha,
        alpha_ci_lo=ci_lo,
        alpha_ci_hi=ci_hi,
        xmin=xmin,
        n_tail=n_tail,
        ks_distance=ks,
        vs_lognormal_R=R_ln,
        vs_lognormal_p=p_ln,
        vs_exponential_R=R_exp,
        vs_exponential_p=p_exp,
        pre_registered_band=expected_band,
        in_band=in_band,
        label=label,
        reason=reason,
    )
