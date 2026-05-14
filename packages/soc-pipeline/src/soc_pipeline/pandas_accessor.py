"""Pandas Series `.soc` accessor — ergonomic SOC validation for working scientists.

Usage:
    >>> import pandas as pd, numpy as np, soc_pipeline  # noqa: F401 (registers accessor)
    >>> s = pd.Series((np.random.default_rng(0).pareto(1.5, 5000) + 1.0), name="magnitudes")
    >>> s.soc.fit_alpha()         # -> float
    >>> s.soc.validate(expected_band=(2.4, 2.6))  # -> Verdict
    >>> s.soc.is_pass(expected_band=(2.4, 2.6))   # -> bool

Design notes:
    - Registered as a pandas Series extension accessor (`@pd.api.extensions.register_series_accessor`)
    - Side-effect registration occurs on `import soc_pipeline` (this module imported in __init__.py)
    - Numeric dtype enforced at construction (TypeError otherwise)
    - The accessor composes the existing `fit_clauset_powerlaw`, `bootstrap_ci`,
      and `verdict_from_alpha_band` primitives — no new statistical machinery
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .fit import FitResult, fit_clauset_powerlaw
from .bootstrap import BootstrapResult, bootstrap_ci
from .utils import verdict_from_alpha_band

__all__ = ["SocAccessor", "Verdict", "validate"]


@dataclass
class Verdict:
    """Composite SOC verdict for a single series.

    Attributes:
        label: Caller-provided label (or series name, or 'series').
        verdict: One of {'PASS', 'FAIL', 'INCONCLUSIVE'} for quick-look gating.
        underlying_verdict: Standard 3-tier label from `verdict_from_alpha_band`
            (e.g. 'CONFIRMED' / 'DEVIATING' / 'INCONCLUSIVE').
        alpha: Point estimate of the power-law exponent.
        alpha_ci_low: Lower 95% bootstrap CI on alpha (None if bootstrap skipped).
        alpha_ci_high: Upper 95% bootstrap CI on alpha (None if bootstrap skipped).
        xmin: Selected lower bound for the power-law tail.
        ks_statistic: KS distance vs the fitted power-law tail.
        vs_lognormal_R: Vuong LR vs lognormal (positive -> power-law preferred).
        vs_lognormal_p: Two-sided p-value for the LR test vs lognormal.
        vs_exponential_R: Vuong LR vs exponential.
        vs_exponential_p: Two-sided p-value for the LR test vs exponential.
        in_band: Whether `alpha` lies inside the supplied `expected_band`.
        n_total: Total sample size before tail cut.
        n_tail: Number of samples in the fitted tail.
        fit: Underlying FitResult (full detail).
        bootstrap: Underlying BootstrapResult (None if bootstrap skipped/failed).
        error: Set when validation could not be completed.
    """

    label: str = "series"
    verdict: str = "INCONCLUSIVE"
    underlying_verdict: str = "INCONCLUSIVE"
    alpha: float | None = None
    alpha_ci_low: float | None = None
    alpha_ci_high: float | None = None
    xmin: float | None = None
    ks_statistic: float | None = None
    vs_lognormal_R: float | None = None
    vs_lognormal_p: float | None = None
    vs_exponential_R: float | None = None
    vs_exponential_p: float | None = None
    in_band: bool = False
    n_total: int = 0
    n_tail: int = 0
    fit: FitResult | None = None
    bootstrap: BootstrapResult | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict view (drops FitResult/BootstrapResult objects)."""
        d = {
            "label": self.label,
            "verdict": self.verdict,
            "underlying_verdict": self.underlying_verdict,
            "alpha": self.alpha,
            "alpha_ci_low": self.alpha_ci_low,
            "alpha_ci_high": self.alpha_ci_high,
            "xmin": self.xmin,
            "ks_statistic": self.ks_statistic,
            "vs_lognormal_R": self.vs_lognormal_R,
            "vs_lognormal_p": self.vs_lognormal_p,
            "vs_exponential_R": self.vs_exponential_R,
            "vs_exponential_p": self.vs_exponential_p,
            "in_band": self.in_band,
            "n_total": self.n_total,
            "n_tail": self.n_tail,
        }
        if self.error:
            d["error"] = self.error
        return d

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        if self.error:
            return f"Verdict(label={self.label!r}, verdict=ERROR, error={self.error!r})"
        ci = ""
        if self.alpha_ci_low is not None and self.alpha_ci_high is not None:
            ci = f" CI=[{self.alpha_ci_low:.2f}, {self.alpha_ci_high:.2f}]"
        alpha_str = f"{self.alpha:.3f}" if self.alpha is not None else "NA"
        return (
            f"Verdict(label={self.label!r}, verdict={self.verdict}, "
            f"alpha={alpha_str}{ci}, "
            f"n_tail={self.n_tail}/{self.n_total})"
        )


def validate(
    x_data: Any,
    label: str | None = None,
    expected_band: tuple[float, float] | None = None,
    n_boot: int | None = 200,
    discrete: bool = False,
    seed: int = 42,
    min_samples: int = 100,
) -> Verdict:
    """Run the full SOC validation pipeline on a 1-D numeric array.

    Args:
        x_data: 1-D array-like of positive observed sizes/durations.
        label: Optional caller-provided label.
        expected_band: (low, high) prediction band on alpha. If None, no
            band-check is performed (verdict stays INCONCLUSIVE unless fit fails).
        n_boot: Number of bootstrap resamples. Pass 0 / None to skip CI.
        discrete: True for integer event counts.
        seed: Bootstrap RNG seed.
        min_samples: Fit minimum-sample gate.

    Returns:
        Verdict dataclass.
    """
    import numpy as np

    arr = np.asarray(x_data, dtype=float)
    name = label if label else "series"

    fit = fit_clauset_powerlaw(
        arr, name=name, discrete=discrete, min_samples=min_samples
    )
    if fit.error is not None:
        return Verdict(label=name, error=fit.error, fit=fit, n_total=fit.n_total)

    boot: BootstrapResult | None = None
    if n_boot:
        boot = bootstrap_ci(
            arr, n_boot=n_boot, seed=seed, discrete=discrete,
            min_samples=max(200, min_samples),
        )

    if expected_band is not None:
        underlying = verdict_from_alpha_band(fit.alpha, predicted=expected_band)
        in_band = (
            fit.alpha is not None
            and expected_band[0] <= fit.alpha <= expected_band[1]
        )
    else:
        underlying = "INCONCLUSIVE"
        in_band = False

    # Quick-look gating verdict
    if expected_band is None:
        coarse = "INCONCLUSIVE"
    elif in_band and not fit.rejects_power_law:
        coarse = "PASS"
    elif fit.rejects_power_law or underlying == "DEVIATING":
        coarse = "FAIL"
    else:
        coarse = "INCONCLUSIVE"

    return Verdict(
        label=name,
        verdict=coarse,
        underlying_verdict=underlying,
        alpha=fit.alpha,
        alpha_ci_low=boot.ci_low if boot and boot.error is None else None,
        alpha_ci_high=boot.ci_high if boot and boot.error is None else None,
        xmin=fit.xmin,
        ks_statistic=fit.ks_statistic,
        vs_lognormal_R=fit.vs_lognormal_R,
        vs_lognormal_p=fit.vs_lognormal_p,
        vs_exponential_R=fit.vs_exponential_R,
        vs_exponential_p=fit.vs_exponential_p,
        in_band=in_band,
        n_total=fit.n_total,
        n_tail=fit.n_tail,
        fit=fit,
        bootstrap=boot,
    )


@pd.api.extensions.register_series_accessor("soc")
class SocAccessor:
    """Pandas Series `.soc` accessor — see module docstring for usage."""

    def __init__(self, pandas_obj: pd.Series) -> None:
        self._validate_dtype(pandas_obj)
        self._obj = pandas_obj

    @staticmethod
    def _validate_dtype(obj: pd.Series) -> None:
        if not pd.api.types.is_numeric_dtype(obj):
            raise TypeError(
                "soc accessor requires a numeric Series "
                f"(got dtype={obj.dtype!r})"
            )

    def validate(
        self,
        label: str | None = None,
        expected_band: tuple[float, float] | None = None,
        n_boot: int | None = 200,
        discrete: bool = False,
        seed: int = 42,
        min_samples: int = 100,
    ) -> Verdict:
        """Full SOC validation on this series. See module-level `validate()`."""
        name = label or (self._obj.name if self._obj.name is not None else "series")
        return validate(
            self._obj.values,
            label=str(name),
            expected_band=expected_band,
            n_boot=n_boot,
            discrete=discrete,
            seed=seed,
            min_samples=min_samples,
        )

    def fit_alpha(self, discrete: bool = False, min_samples: int = 100) -> float | None:
        """Convenience: return just the point-estimate alpha (skip bootstrap)."""
        v = self.validate(n_boot=0, discrete=discrete, min_samples=min_samples)
        return v.alpha

    def is_pass(
        self,
        expected_band: tuple[float, float],
        n_boot: int | None = 0,
        discrete: bool = False,
    ) -> bool:
        """Convenience: True iff verdict is PASS."""
        return (
            self.validate(
                expected_band=expected_band, n_boot=n_boot, discrete=discrete
            ).verdict
            == "PASS"
        )
