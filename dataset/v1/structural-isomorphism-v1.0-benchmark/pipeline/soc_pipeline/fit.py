"""Clauset-Shalizi-Newman 2009 power-law MLE fitting.

Reference: Clauset, A., Shalizi, C. R., & Newman, M. E. (2009).
"Power-law distributions in empirical data." SIAM Review, 51(4), 661-703.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = ["FitResult", "fit_clauset_powerlaw"]


@dataclass
class FitResult:
    """Result of a Clauset 2009 power-law fit.

    Attributes:
        alpha: Power-law scaling exponent (P(x) ~ x^-alpha).
        xmin: Lower-bound xmin selected by KS minimization.
        sigma: Standard error on alpha.
        n_total: Total sample size before xmin cut.
        n_tail: Number of samples >= xmin (used for the fit).
        ks_statistic: KS distance between empirical tail and fitted power-law.
        vs_lognormal_R: Vuong LR statistic vs lognormal (positive -> power-law).
        vs_lognormal_p: Two-sided p-value for the LR test vs lognormal.
        vs_exponential_R: Vuong LR statistic vs exponential.
        vs_exponential_p: Two-sided p-value for the LR test vs exponential.
        vs_powerlaw_lognormal_winner: 'power_law' / 'lognormal' / 'inconclusive'.
        rejects_power_law: True if comparison vs simpler model rejects PL.
        name: Caller-provided label.
        error: If non-None, fit failed and other fields are unset.
    """

    alpha: float | None = None
    xmin: float | None = None
    sigma: float | None = None
    n_total: int = 0
    n_tail: int = 0
    ks_statistic: float | None = None
    vs_lognormal_R: float | None = None
    vs_lognormal_p: float | None = None
    vs_exponential_R: float | None = None
    vs_exponential_p: float | None = None
    vs_powerlaw_lognormal_winner: str = "inconclusive"
    rejects_power_law: bool = False
    name: str = "values"
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Backward-compatible dict view (matches legacy v4/lib API)."""
        d = {
            "name": self.name,
            "alpha": self.alpha,
            "sigma_alpha": self.sigma,
            "xmin": self.xmin,
            "n_total": self.n_total,
            "n_tail": self.n_tail,
            "vs_lognormal_R": self.vs_lognormal_R,
            "vs_lognormal_p": self.vs_lognormal_p,
            "vs_exponential_R": self.vs_exponential_R,
            "vs_exponential_p": self.vs_exponential_p,
            "vs_powerlaw_lognormal_winner": self.vs_powerlaw_lognormal_winner,
            "rejects_power_law": self.rejects_power_law,
            "ks_statistic": self.ks_statistic,
        }
        if self.error:
            d["error"] = self.error
        return d


def fit_clauset_powerlaw(
    x_data: np.ndarray,
    name: str = "values",
    discrete: bool = False,
    xmin_method: str = "ks",
    min_samples: int = 100,
) -> FitResult:
    """Fit a power-law to the tail of x_data using the Clauset 2009 method.

    Args:
        x_data: 1-D array of positive observed sizes/durations.
        name: Caller-provided label for logging / round-tripping.
        discrete: True for integer event counts, False for continuous sizes.
        xmin_method: Currently only 'ks' (Kolmogorov-Smirnov minimization).
        min_samples: Minimum sample size; below this, the function returns a
            FitResult with an error message and unset fields.

    Returns:
        FitResult dataclass.

    Notes:
        Requires the `powerlaw` package (Alstott et al. 2014). If the package
        is not installed, FitResult.error is set and other fields are None.
    """
    try:
        import powerlaw  # type: ignore
    except Exception as exc:  # pragma: no cover - import-time only
        return FitResult(name=name, error=f"powerlaw missing: {exc}")

    if xmin_method != "ks":
        return FitResult(name=name, error=f"xmin_method {xmin_method} not supported")

    x_data = np.asarray(x_data, dtype=float)
    x_data = x_data[np.isfinite(x_data) & (x_data > 0)]
    n_total = int(len(x_data))
    if n_total < min_samples:
        return FitResult(
            name=name,
            n_total=n_total,
            error=f"too few values: {n_total} < {min_samples}",
        )

    fit = powerlaw.Fit(x_data, discrete=discrete, xmin_distance="D", verbose=False)
    alpha = float(fit.power_law.alpha)
    sigma = float(fit.power_law.sigma)
    xmin = float(fit.power_law.xmin)
    n_tail = int(np.sum(x_data >= xmin))
    try:
        ks = float(fit.power_law.D)
    except Exception:
        ks = None

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

    return FitResult(
        alpha=alpha,
        xmin=xmin,
        sigma=sigma,
        n_total=n_total,
        n_tail=n_tail,
        ks_statistic=ks,
        vs_lognormal_R=None if R_ln is None else float(R_ln),
        vs_lognormal_p=None if p_ln is None else float(p_ln),
        vs_exponential_R=None if R_exp is None else float(R_exp),
        vs_exponential_p=None if p_exp is None else float(p_exp),
        vs_powerlaw_lognormal_winner=winner,
        rejects_power_law=bool(rejects),
        name=name,
    )
