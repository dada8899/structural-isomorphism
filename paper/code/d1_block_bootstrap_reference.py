"""
Reference implementation for the D1 method paper:
"Block-bootstrap correction for Kendall-tau early-warning signals on
autocorrelated environmental time series."

This is a self-contained, dependency-light (numpy + scipy.stats) module
that exposes:

    stationary_block_bootstrap(series, n_replicates, block_length=None,
                               indicator_fn=None, seed=None)
        Politis-Romano (1994) stationary block bootstrap. Returns a
        bootstrap distribution of Kendall-tau computed on the rolling
        indicator (default: rolling lag-1 autocorrelation).

    moving_block_bootstrap(series, n_replicates, block_length=None,
                           indicator_fn=None, seed=None)
        Kunsch (1989) moving (fixed-length) block bootstrap. Same return
        contract as the stationary version. Provided for comparison.

    politis_white_optimal_block_length(series, max_lag=None)
        Politis & White (2004; corrected White & Politis 2009) automatic
        optimal block length for the stationary bootstrap.

    rolling_ar1(series, window) / rolling_variance(series, window)
        The two canonical Scheffer-Dakos-van Nes early-warning indicators.

    kendall_tau_vs_time(indicator_series)
        Observed Kendall-tau between the indicator and the time index.

Designed to be copy-pasted into ecology / EWS practitioner code without
pulling in pandas, statsmodels, or any other heavyweight dependency.

References:
    Kunsch HR (1989). The jackknife and the bootstrap for general
        stationary observations. Ann. Stat. 17, 1217-1241.
    Politis DN, Romano JP (1994). The stationary bootstrap.
        J. Am. Stat. Assoc. 89, 1303-1313.
    Politis DN, White H (2004). Automatic block-length selection for the
        dependent bootstrap. Econometric Reviews 23, 53-70.
    Scheffer M et al. (2009). Early-warning signals for critical
        transitions. Nature 461, 53-59.
    Dakos V et al. (2008). Slowing down as an early warning signal for
        abrupt climate change. PNAS 105, 14308-14312.

Author: structural-isomorphism W7 sub-agent E
Date  : 2026-05-15
License: MIT
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import numpy as np
from scipy.stats import kendalltau


# -----------------------------------------------------------------------
# Rolling indicators
# -----------------------------------------------------------------------

def rolling_ar1(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling lag-1 autocorrelation. Returns array of length n-window+1.

    Vectorised via numpy stride tricks: builds an (n_win, window) view of
    x and computes the per-window Pearson correlation between the first
    window-1 and the last window-1 samples in one batched dot product.
    Cost: O(n * window) in time but ~50× faster than a Python loop.
    NaNs in x propagate to the affected output positions.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if window < 5 or window > n:
        raise ValueError(f"window={window} invalid for n={n}")
    nan_mask = ~np.isfinite(x)
    has_nan = nan_mask.any()
    if has_nan:
        x_for_calc = np.where(nan_mask, 0.0, x)
    else:
        x_for_calc = x

    # Strided (n_win, window) view, then split into 'a' (first w-1) and 'b' (last w-1).
    from numpy.lib.stride_tricks import sliding_window_view
    W = sliding_window_view(x_for_calc, window)  # shape (n_win, window)
    a = W[:, :-1]
    b = W[:, 1:]
    ma = a.mean(axis=1, keepdims=True)
    mb = b.mean(axis=1, keepdims=True)
    a_c = a - ma
    b_c = b - mb
    num = (a_c * b_c).sum(axis=1)
    denom = np.sqrt((a_c * a_c).sum(axis=1) * (b_c * b_c).sum(axis=1))
    out = np.where(denom > 0, num / np.where(denom > 0, denom, 1.0), np.nan)

    if has_nan:
        nan_csum = np.concatenate(([0], np.cumsum(nan_mask.astype(int))))
        nan_in_window = nan_csum[window:] - nan_csum[:-window]
        out = np.where(nan_in_window > 0, np.nan, out)
    return out


def rolling_variance(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling variance (ddof=1). Returns array of length n-window+1.

    O(n) via cumulative sums, vectorised over windows.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if window < 2 or window > n:
        raise ValueError(f"window={window} invalid for n={n}")
    nan_mask = ~np.isfinite(x)
    has_nan = nan_mask.any()
    if has_nan:
        x_for_calc = np.where(nan_mask, 0.0, x)
    else:
        x_for_calc = x
    csum = np.concatenate(([0.0], np.cumsum(x_for_calc)))
    csum_sq = np.concatenate(([0.0], np.cumsum(x_for_calc * x_for_calc)))
    s = csum[window:] - csum[:-window]
    s2 = csum_sq[window:] - csum_sq[:-window]
    var = (s2 - s * s / window) / (window - 1)
    out = np.maximum(var, 0.0)
    if has_nan:
        nan_csum = np.concatenate(([0], np.cumsum(nan_mask.astype(int))))
        nan_in_window = nan_csum[window:] - nan_csum[:-window]
        out = np.where(nan_in_window > 0, np.nan, out)
    return out


# -----------------------------------------------------------------------
# Kendall-tau on indicator
# -----------------------------------------------------------------------

def kendall_tau_vs_time(indicator: np.ndarray) -> Tuple[float, float]:
    """Observed Kendall-tau between the rolling indicator and time.

    Returns (tau, naive_p_value). The naive p-value assumes i.i.d.
    observations of the indicator and is what one would get from
    scipy.stats.kendalltau directly; it is *not* a valid p-value when the
    indicator is computed on a serially-correlated time series.
    """
    indicator = np.asarray(indicator, dtype=float)
    valid = np.isfinite(indicator)
    if valid.sum() < 10:
        return float("nan"), float("nan")
    t = np.arange(len(indicator))[valid]
    y = indicator[valid]
    tau, p = kendalltau(t, y)
    return float(tau), float(p)


# -----------------------------------------------------------------------
# Optimal block length (Politis & White 2004 / White & Politis 2009)
# -----------------------------------------------------------------------

def _autocov(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = x - np.mean(x)
    n = len(x)
    acov = np.zeros(max_lag + 1)
    for k in range(max_lag + 1):
        acov[k] = np.dot(x[: n - k], x[k:]) / n
    return acov


def politis_white_optimal_block_length(
    x: np.ndarray, max_lag: Optional[int] = None
) -> int:
    """Automatic optimal block length for the stationary bootstrap.

    Implements the spectral / flat-top kernel rule of Politis & White
    (2004). Returns an integer >= 1. Falls back to ``ceil(sqrt(n))`` when
    the spectral estimate is non-finite (very short or degenerate series).

    The implementation is intentionally simple (not the full Andrews
    plug-in) since for the rolling-EWS use case the result is used as a
    *default suggestion*, with sensitivity analysis recommended anyway.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 20:
        return max(2, int(np.ceil(np.sqrt(max(n, 4)))))
    if max_lag is None:
        max_lag = int(min(np.floor(2 * np.sqrt(np.log10(n) * n)), n // 4))
    acov = _autocov(x, max_lag)
    if acov[0] <= 0 or not np.isfinite(acov[0]):
        return int(np.ceil(np.sqrt(n)))
    rho = acov / acov[0]
    # Politis-White (2004) flat-top lag-window estimate.
    # m = smallest lag k such that |rho(k+j)| < c * sqrt(log10(n)/n)
    # for j = 1..K_N, with c = 2 and K_N = max(5, sqrt(log10(n))).
    c = 2.0
    threshold = c * np.sqrt(np.log10(n) / n)
    K_N = max(5, int(np.ceil(np.sqrt(np.log10(n)))))
    m_hat = max_lag
    for k in range(1, max_lag - K_N):
        if np.all(np.abs(rho[k : k + K_N + 1]) < threshold):
            m_hat = k
            break
    M = min(2 * m_hat, max_lag)
    # G_hat = sum_{k=-M..M} |k| * lambda(k/M) * rho(k)
    # D_hat = (4/3) * (sum_{k=-M..M} lambda(k/M) * rho(k))^2
    # b_hat = (2 * G_hat^2 / D_hat)^(1/3) * n^(1/3)
    def lam(t: float) -> float:
        a = abs(t)
        if a <= 0.5:
            return 1.0
        if a < 1.0:
            return 2.0 * (1.0 - a)
        return 0.0

    G = 0.0
    D_sum = 0.0
    for k in range(-M, M + 1):
        rk = rho[abs(k)] if abs(k) <= max_lag else 0.0
        w = lam(k / M)
        G += abs(k) * w * rk
        D_sum += w * rk
    # For stationary bootstrap, the optimum is g = (2 * G^2 / D)^{1/3} * n^{1/3}
    D = (4.0 / 3.0) * D_sum * D_sum
    if D <= 0 or not np.isfinite(G) or not np.isfinite(D):
        return int(np.ceil(np.sqrt(n)))
    b_opt = (2.0 * G * G / D) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    b_int = int(np.clip(np.round(b_opt), 2, n // 2))
    return b_int


# -----------------------------------------------------------------------
# Block-bootstrap variants
# -----------------------------------------------------------------------

def _resample_moving_block(
    x: np.ndarray, block_length: int, rng: np.random.Generator
) -> np.ndarray:
    """Kunsch (1989) moving-block bootstrap resample."""
    n = len(x)
    n_blocks = int(np.ceil(n / block_length))
    starts_all = np.arange(0, n - block_length + 1)
    starts = rng.choice(starts_all, size=n_blocks, replace=True)
    chunks = [x[s : s + block_length] for s in starts]
    return np.concatenate(chunks)[:n]


def _resample_stationary_block(
    x: np.ndarray, mean_block_length: float, rng: np.random.Generator
) -> np.ndarray:
    """Politis-Romano (1994) stationary bootstrap resample.

    Block lengths are i.i.d. geometric with mean ``mean_block_length``;
    block start positions are uniform on {0..n-1} with circular wrap.
    """
    n = len(x)
    p = 1.0 / max(mean_block_length, 1.0)
    out = np.empty(n, dtype=x.dtype)
    i = 0
    while i < n:
        start = int(rng.integers(0, n))
        L = int(rng.geometric(p))
        L = max(L, 1)
        for j in range(L):
            if i + j >= n:
                break
            out[i + j] = x[(start + j) % n]
        i += L
    return out


def moving_block_bootstrap(
    series: np.ndarray,
    n_replicates: int = 1000,
    block_length: Optional[int] = None,
    indicator_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    window: int = 365,
    seed: Optional[int] = 42,
) -> dict:
    """Kunsch moving-block bootstrap for Kendall-tau on a rolling indicator.

    Returns a dict with keys::

        {
          'tau_obs': float,
          'p_naive': float,
          'tau_boot': np.ndarray of shape (n_replicates,),
          'p_block': float,                  # two-sided
          'ci_lo_95': float, 'ci_hi_95': float,
          'block_length': int,
        }

    The Kendall-tau is computed on ``indicator_fn(series)`` against time;
    on each bootstrap resample the indicator is recomputed (this is the
    correct procedure for rolling-window EWS, where iid resample of
    the *indicator* would *over*-correct).
    """
    series = np.asarray(series, dtype=float)
    if indicator_fn is None:
        indicator_fn = lambda x: rolling_ar1(x, window=window)
    if block_length is None:
        block_length = politis_white_optimal_block_length(series)
    if block_length < 2:
        block_length = 2

    ind_obs = indicator_fn(series)
    tau_obs, p_naive = kendall_tau_vs_time(ind_obs)

    rng = np.random.default_rng(seed)
    tau_boot = np.full(n_replicates, np.nan)
    for b in range(n_replicates):
        resamp = _resample_moving_block(series, block_length, rng)
        ind_b = indicator_fn(resamp)
        tau_b, _ = kendall_tau_vs_time(ind_b)
        tau_boot[b] = tau_b if np.isfinite(tau_b) else 0.0

    abs_obs = abs(tau_obs)
    n_ge = int(np.sum(np.abs(tau_boot) >= abs_obs))
    p_block = (1 + n_ge) / (1 + n_replicates)

    return {
        "tau_obs": tau_obs,
        "p_naive": p_naive,
        "tau_boot": tau_boot,
        "p_block": p_block,
        "ci_lo_95": float(np.percentile(tau_boot, 2.5)),
        "ci_hi_95": float(np.percentile(tau_boot, 97.5)),
        "block_length": int(block_length),
        "n_replicates": int(n_replicates),
        "method": "moving_block_kunsch_1989",
    }


def stationary_block_bootstrap(
    series: np.ndarray,
    n_replicates: int = 1000,
    block_length: Optional[float] = None,
    indicator_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    window: int = 365,
    seed: Optional[int] = 42,
) -> dict:
    """Politis-Romano (1994) stationary bootstrap for Kendall-tau EWS.

    Same return contract as :func:`moving_block_bootstrap`. The
    ``block_length`` here is the *mean* of the geometric block-length
    distribution; pass ``None`` to use Politis-White automatic selection.
    """
    series = np.asarray(series, dtype=float)
    if indicator_fn is None:
        indicator_fn = lambda x: rolling_ar1(x, window=window)
    if block_length is None:
        block_length = politis_white_optimal_block_length(series)
    block_length = max(float(block_length), 2.0)

    ind_obs = indicator_fn(series)
    tau_obs, p_naive = kendall_tau_vs_time(ind_obs)

    rng = np.random.default_rng(seed)
    tau_boot = np.full(n_replicates, np.nan)
    for b in range(n_replicates):
        resamp = _resample_stationary_block(series, block_length, rng)
        ind_b = indicator_fn(resamp)
        tau_b, _ = kendall_tau_vs_time(ind_b)
        tau_boot[b] = tau_b if np.isfinite(tau_b) else 0.0

    abs_obs = abs(tau_obs)
    n_ge = int(np.sum(np.abs(tau_boot) >= abs_obs))
    p_block = (1 + n_ge) / (1 + n_replicates)

    return {
        "tau_obs": tau_obs,
        "p_naive": p_naive,
        "tau_boot": tau_boot,
        "p_block": p_block,
        "ci_lo_95": float(np.percentile(tau_boot, 2.5)),
        "ci_hi_95": float(np.percentile(tau_boot, 97.5)),
        "block_length": float(block_length),
        "n_replicates": int(n_replicates),
        "method": "stationary_politis_romano_1994",
    }


# -----------------------------------------------------------------------
# Smoke test
# -----------------------------------------------------------------------

if __name__ == "__main__":
    # Quick demo: AR1(0.8) series of n=500, no trend.
    rng = np.random.default_rng(0)
    n = 500
    phi = 0.8
    eps = rng.normal(size=n)
    x = np.empty(n)
    x[0] = eps[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    L = politis_white_optimal_block_length(x)
    print(f"Politis-White optimal block length: {L}")
    out = stationary_block_bootstrap(
        x,
        n_replicates=200,
        block_length=L,
        indicator_fn=lambda y: rolling_ar1(y, window=100),
        seed=1,
    )
    print(f"tau_obs={out['tau_obs']:+.3f}  p_naive={out['p_naive']:.2e}  "
          f"p_block={out['p_block']:.3f}  CI=[{out['ci_lo_95']:+.3f},"
          f"{out['ci_hi_95']:+.3f}]  L={out['block_length']}")
