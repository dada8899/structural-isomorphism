"""Bootstrap confidence intervals on the Clauset 2009 alpha estimator."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["BootstrapResult", "bootstrap_ci"]


@dataclass
class BootstrapResult:
    """Bootstrap CI on the power-law alpha.

    Attributes:
        alpha_mean: Mean of bootstrap-resampled alpha.
        alpha_median: Median of bootstrap-resampled alpha.
        alpha_std: Standard deviation across bootstrap samples.
        ci_low: Lower percentile of alpha (default 2.5).
        ci_high: Upper percentile of alpha (default 97.5).
        n_boot_succeeded: Number of resamples where fitting succeeded.
        error: Optional error string when fewer than 20 resamples succeeded.
    """

    alpha_mean: float | None = None
    alpha_median: float | None = None
    alpha_std: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n_boot_succeeded: int = 0
    error: str | None = None


def bootstrap_ci(
    x_data: np.ndarray,
    n_boot: int = 200,
    seed: int = 42,
    discrete: bool = False,
    ci_pct: tuple[float, float] = (2.5, 97.5),
    min_samples: int = 200,
) -> BootstrapResult:
    """Bootstrap a CI on the Clauset 2009 alpha estimator.

    Args:
        x_data: 1-D positive sample.
        n_boot: Number of resamples (default 200; >=200 recommended).
        seed: RNG seed for reproducibility.
        discrete: Pass-through to powerlaw.Fit.
        ci_pct: Lower/upper percentile pair for the CI (default 95% CI).
        min_samples: Minimum sample size to attempt bootstrap.

    Returns:
        BootstrapResult dataclass. If fewer than 20 fits succeed, returns
        a result with error set.
    """
    try:
        import powerlaw  # type: ignore
    except Exception as exc:
        return BootstrapResult(error=f"powerlaw missing: {exc}")

    x_data = np.asarray(x_data, dtype=float)
    x_data = x_data[np.isfinite(x_data) & (x_data > 0)]
    if len(x_data) < min_samples:
        return BootstrapResult(error=f"too few values: {len(x_data)} < {min_samples}")
    rng = np.random.default_rng(seed)
    n = len(x_data)
    alphas: list[float] = []
    for _ in range(n_boot):
        sample = rng.choice(x_data, size=n, replace=True)
        try:
            f = powerlaw.Fit(sample, discrete=discrete, xmin_distance="D", verbose=False)
            alphas.append(float(f.power_law.alpha))
        except Exception:
            continue
    if len(alphas) < 20:
        return BootstrapResult(
            n_boot_succeeded=len(alphas),
            error=f"only {len(alphas)}/{n_boot} fits succeeded",
        )
    arr = np.asarray(alphas)
    return BootstrapResult(
        alpha_mean=float(arr.mean()),
        alpha_median=float(np.median(arr)),
        alpha_std=float(arr.std()),
        ci_low=float(np.percentile(arr, ci_pct[0])),
        ci_high=float(np.percentile(arr, ci_pct[1])),
        n_boot_succeeded=int(len(arr)),
    )
