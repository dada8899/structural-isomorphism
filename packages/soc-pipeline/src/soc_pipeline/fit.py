"""Clauset-Shalizi-Newman 2009 power-law MLE fitting.

Reference: Clauset, A., Shalizi, C. R., & Newman, M. E. (2009).
"Power-law distributions in empirical data." SIAM Review, 51(4), 661-703.
"""
from __future__ import annotations

import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from math import erfc, log, pi, sqrt
from typing import Any

import numpy as np

__all__ = ["FitResult", "fit_clauset_powerlaw"]


_POWERLAW_SIGMA_DEPRECATION = (
    r"Standard error for the MLE should be accessed using the 'standard_err' property\. "
    r"Accessing via 'sigma' property will be removed in v2\.1\."
)


@contextmanager
def _suppress_powerlaw_sigma_deprecation():
    """Suppress only powerlaw 2.0's per-candidate deprecated-property storm."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=_POWERLAW_SIGMA_DEPRECATION,
            category=DeprecationWarning,
        )
        yield


def _run_powerlaw_fit(powerlaw: Any, data: np.ndarray, *, discrete: bool) -> tuple:
    """Run the vendor fit while isolating one known powerlaw 2.0 warning storm.

    powerlaw 2.0 internally reads its deprecated ``sigma`` property once per
    xmin candidate, producing hundreds of thousands of identical warnings.
    Suppression is deliberately scoped to the exact vendor message and this
    call boundary; fit-quality and numerical warnings remain visible.
    """
    with _suppress_powerlaw_sigma_deprecation():
        fit = powerlaw.Fit(data, discrete=discrete, xmin_distance="D", verbose=False)
        alpha = float(fit.power_law.alpha)
        if hasattr(fit.power_law, "standard_err"):
            standard_err = fit.power_law.standard_err
        else:  # powerlaw < 2.0 compatibility
            standard_err = fit.power_law.sigma
        sigma = float(standard_err)
        xmin = float(fit.power_law.xmin)
        try:
            ks = float(fit.power_law.D)
        except Exception:
            ks = None
        try:
            lognormal = fit.distribution_compare(
                "power_law", "lognormal", normalized_ratio=True
            )
        except Exception:
            lognormal = (None, None)
        try:
            exponential = fit.distribution_compare(
                "power_law", "exponential", normalized_ratio=True
            )
        except Exception:
            exponential = (None, None)
    return alpha, sigma, xmin, ks, lognormal, exponential


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
    vs_lognormal_R: float | None = None  # noqa: N815 - public API compatibility
    vs_lognormal_p: float | None = None
    vs_exponential_R: float | None = None  # noqa: N815 - public API compatibility
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
    max_xmin_candidates: int | None = 512,
) -> FitResult:
    """Fit a power-law to the tail of x_data using the Clauset 2009 method.

    Args:
        x_data: 1-D array of positive observed sizes/durations.
        name: Caller-provided label for logging / round-tripping.
        discrete: True for integer event counts, False for continuous sizes.
        xmin_method: Currently only 'ks' (Kolmogorov-Smirnov minimization).
        min_samples: Minimum sample size; below this, the function returns a
            FitResult with an error message and unset fields.
        max_xmin_candidates: Maximum xmin candidates to evaluate for large
            continuous samples. Set to None to scan every possible candidate.

    Returns:
        FitResult dataclass.

    Notes:
        Continuous fits use a vectorized local Clauset estimator. Discrete fits
        still require the `powerlaw` package (Alstott et al. 2014).
    """
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

    if not discrete:
        return _fit_continuous_powerlaw(
            x_data,
            name=name,
            min_samples=min_samples,
            max_xmin_candidates=max_xmin_candidates,
        )

    try:
        import powerlaw  # type: ignore
    except Exception as exc:  # pragma: no cover - import-time only
        return FitResult(name=name, error=f"powerlaw missing: {exc}")

    alpha, sigma, xmin, ks, lognormal, exponential = _run_powerlaw_fit(
        powerlaw, x_data, discrete=True
    )
    n_tail = int(np.sum(x_data >= xmin))
    r_ln, p_ln = lognormal
    r_exp, p_exp = exponential

    rejects = False
    if r_exp is not None and r_exp < 0:
        rejects = True
    if r_ln is not None and r_ln < 0:
        rejects = True

    if r_ln is None:
        winner = "inconclusive"
    elif r_ln > 0 and (p_ln is None or p_ln < 0.1):
        winner = "power_law"
    elif r_ln < 0 and (p_ln is None or p_ln < 0.1):
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
        vs_lognormal_R=None if r_ln is None else float(r_ln),
        vs_lognormal_p=None if p_ln is None else float(p_ln),
        vs_exponential_R=None if r_exp is None else float(r_exp),
        vs_exponential_p=None if p_exp is None else float(p_exp),
        vs_powerlaw_lognormal_winner=winner,
        rejects_power_law=bool(rejects),
        name=name,
    )


def _fit_continuous_powerlaw(
    x_data: np.ndarray,
    *,
    name: str,
    min_samples: int,
    max_xmin_candidates: int | None,
) -> FitResult:
    """Continuous Clauset fit with a vectorized xmin scan."""
    sorted_x = np.sort(x_data)
    min_tail_samples = max(min_samples, int(np.ceil(0.05 * len(sorted_x))))
    fit = _select_continuous_xmin(
        sorted_x,
        min_samples=min_tail_samples,
        max_xmin_candidates=max_xmin_candidates,
    )
    if fit is None:
        return FitResult(
            name=name,
            n_total=int(len(sorted_x)),
            error=f"too few tail values: {len(sorted_x)} < {min_samples}",
        )

    alpha, xmin, sigma, n_tail, ks, candidates_scanned, exact_scan = fit
    tail = sorted_x[sorted_x >= xmin]
    r_ln, p_ln = _vuong_powerlaw_vs_lognormal(tail, xmin, alpha)
    r_exp, p_exp = _vuong_powerlaw_vs_exponential(tail, xmin, alpha)

    rejects = False
    if r_exp is not None and r_exp < 0:
        rejects = True
    if r_ln is not None and r_ln < 0:
        rejects = True

    if r_ln is None:
        winner = "inconclusive"
    elif r_ln > 0 and (p_ln is None or p_ln < 0.1):
        winner = "power_law"
    elif r_ln < 0 and (p_ln is None or p_ln < 0.1):
        winner = "lognormal"
    else:
        winner = "inconclusive"

    return FitResult(
        alpha=alpha,
        xmin=xmin,
        sigma=sigma,
        n_total=int(len(sorted_x)),
        n_tail=n_tail,
        ks_statistic=ks,
        vs_lognormal_R=r_ln,
        vs_lognormal_p=p_ln,
        vs_exponential_R=r_exp,
        vs_exponential_p=p_exp,
        vs_powerlaw_lognormal_winner=winner,
        rejects_power_law=bool(rejects),
        name=name,
        extra={
            "xmin_candidates_scanned": candidates_scanned,
            "xmin_exact_scan": exact_scan,
            "min_tail_samples": min_tail_samples,
        },
    )


def _select_continuous_xmin(
    sorted_x: np.ndarray,
    *,
    min_samples: int,
    max_xmin_candidates: int | None,
) -> tuple[float, float, float, int, float, int, bool] | None:
    n_total = int(len(sorted_x))
    max_start = n_total - min_samples
    if max_start < 0:
        return None

    candidate_indices, exact_scan = _xmin_candidate_indices(
        sorted_x,
        max_start=max_start,
        max_xmin_candidates=max_xmin_candidates,
    )
    if len(candidate_indices) == 0:
        return None

    log_x = np.log(sorted_x)
    suffix_log_sum = np.cumsum(log_x[::-1])[::-1]
    tail_counts = n_total - candidate_indices
    xmin_values = sorted_x[candidate_indices]
    log_xmin = log_x[candidate_indices]
    log_sums = suffix_log_sum[candidate_indices] - tail_counts * log_xmin

    valid = np.isfinite(log_sums) & (log_sums > 0.0)
    if not np.any(valid):
        return None

    candidate_indices = candidate_indices[valid]
    tail_counts = tail_counts[valid]
    xmin_values = xmin_values[valid]
    log_xmin = log_xmin[valid]
    log_sums = log_sums[valid]
    alphas = 1.0 + tail_counts / log_sums
    sigmas = (alphas - 1.0) / np.sqrt(tail_counts)

    ks_distances = _continuous_ks_distances(
        log_x=log_x,
        candidate_indices=candidate_indices,
        log_xmin=log_xmin,
        tail_counts=tail_counts,
        alphas=alphas,
    )

    best_pos = int(np.argmin(ks_distances))
    scanned = int(len(candidate_indices))
    return (
        float(alphas[best_pos]),
        float(xmin_values[best_pos]),
        float(sigmas[best_pos]),
        int(tail_counts[best_pos]),
        float(ks_distances[best_pos]),
        scanned,
        exact_scan,
    )


def _xmin_candidate_indices(
    sorted_x: np.ndarray,
    *,
    max_start: int,
    max_xmin_candidates: int | None,
) -> tuple[np.ndarray, bool]:
    unique_starts = np.flatnonzero(
        np.r_[True, sorted_x[1 : max_start + 1] != sorted_x[:max_start]]
    )
    if max_xmin_candidates is None or len(unique_starts) <= max_xmin_candidates:
        return unique_starts.astype(int, copy=False), True

    positions = np.linspace(0, len(unique_starts) - 1, max_xmin_candidates)
    sampled = unique_starts[np.unique(np.rint(positions).astype(int))]
    return sampled.astype(int, copy=False), False


def _continuous_ks_distances(
    *,
    log_x: np.ndarray,
    candidate_indices: np.ndarray,
    log_xmin: np.ndarray,
    tail_counts: np.ndarray,
    alphas: np.ndarray,
    chunk_size: int = 64,
) -> np.ndarray:
    n_total = len(log_x)
    positions = np.arange(n_total, dtype=float)
    distances = np.empty(len(candidate_indices), dtype=float)

    for start in range(0, len(candidate_indices), chunk_size):
        stop = min(start + chunk_size, len(candidate_indices))
        idx = candidate_indices[start:stop]
        counts = tail_counts[start:stop].astype(float)
        log_ratio = np.maximum(log_x[None, :] - log_xmin[start:stop, None], 0.0)
        model_cdf = 1.0 - np.exp(
            (1.0 - alphas[start:stop, None]) * log_ratio
        )
        rank_upper = (positions[None, :] - idx[:, None] + 1.0) / counts[:, None]
        rank_lower = (positions[None, :] - idx[:, None]) / counts[:, None]
        tail_mask = positions[None, :] >= idx[:, None]

        d_plus = np.where(tail_mask, rank_upper - model_cdf, -np.inf)
        d_minus = np.where(tail_mask, model_cdf - rank_lower, -np.inf)
        distances[start:stop] = np.maximum(
            np.max(d_plus, axis=1),
            np.max(d_minus, axis=1),
        )

    return distances


def _powerlaw_logpdf(x_tail: np.ndarray, xmin: float, alpha: float) -> np.ndarray:
    return log(alpha - 1.0) - log(xmin) - alpha * np.log(x_tail / xmin)


def _vuong_statistic(ll_powerlaw: np.ndarray, ll_other: np.ndarray) -> tuple[float, float]:
    diff = ll_powerlaw - ll_other
    n = len(diff)
    if n < 2:
        return 0.0, 1.0

    std = float(np.std(diff, ddof=1))
    if not np.isfinite(std) or std == 0.0:
        return 0.0, 1.0

    r = float(np.sum(diff) / (sqrt(n) * std))
    p = float(erfc(abs(r) / sqrt(2.0)))
    return r, p


def _vuong_powerlaw_vs_exponential(
    x_tail: np.ndarray,
    xmin: float,
    alpha: float,
) -> tuple[float | None, float | None]:
    shifted = x_tail - xmin
    mean_shifted = float(np.mean(shifted))
    if not np.isfinite(mean_shifted) or mean_shifted <= 0.0:
        return None, None

    rate = 1.0 / mean_shifted
    ll_powerlaw = _powerlaw_logpdf(x_tail, xmin, alpha)
    ll_exponential = log(rate) - rate * shifted
    return _vuong_statistic(ll_powerlaw, ll_exponential)


def _vuong_powerlaw_vs_lognormal(
    x_tail: np.ndarray,
    xmin: float,
    alpha: float,
) -> tuple[float | None, float | None]:
    log_tail = np.log(x_tail)
    mu = float(np.mean(log_tail))
    sigma = float(np.std(log_tail, ddof=0))
    if not np.isfinite(sigma) or sigma <= 0.0:
        return None, None

    z_min = (log(xmin) - mu) / sigma
    survival = 0.5 * erfc(z_min / sqrt(2.0))
    if survival <= 0.0 or not np.isfinite(survival):
        return None, None

    ll_powerlaw = _powerlaw_logpdf(x_tail, xmin, alpha)
    ll_lognormal = (
        -np.log(x_tail)
        - log(sigma)
        - 0.5 * log(2.0 * pi)
        - ((log_tail - mu) ** 2) / (2.0 * sigma**2)
        - log(survival)
    )
    return _vuong_statistic(ll_powerlaw, ll_lognormal)
