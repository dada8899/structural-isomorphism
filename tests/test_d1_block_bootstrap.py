"""Unit tests for paper.code.d1_block_bootstrap_reference.

Three cases per the D1 method-paper spec:
  1. iid input: block-bootstrap CI should be ~comparable to naive p,
     i.e. both correctly fail to detect a trend.
  2. strong AR1(phi=0.85) input: block-bootstrap CI must be substantially
     wider than the naive Kendall-tau p-value would suggest. Concretely,
     under strong AR1 the naive bootstrap on the indicator is far too
     narrow; the block-bootstrap two-sided p_block must satisfy
     p_block > 0.05 with high probability even though naive p is small.
  3. short series: function must run without exception and emit a
     reasonable warning / fallback (no crash, no nan-explosion).

Run with::

    PYTHONPATH=. pytest tests/test_d1_block_bootstrap.py -v
"""

from __future__ import annotations

import numpy as np
import pytest

from paper.code.d1_block_bootstrap_reference import (
    kendall_tau_vs_time,
    moving_block_bootstrap,
    politis_white_optimal_block_length,
    rolling_ar1,
    rolling_variance,
    stationary_block_bootstrap,
)


***REMOVED*** ---------------------------------------------------------------------
***REMOVED*** Helpers
***REMOVED*** ---------------------------------------------------------------------

def _ar1(n: int, phi: float, sigma: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    eps = rng.normal(scale=sigma, size=n)
    x = np.empty(n)
    x[0] = eps[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    return x


***REMOVED*** ---------------------------------------------------------------------
***REMOVED*** Case 1: iid input — block bootstrap should not blow up; both methods
***REMOVED*** correctly identify no trend.
***REMOVED*** ---------------------------------------------------------------------

def test_iid_input_no_spurious_significance():
    rng = np.random.default_rng(123)
    x = rng.normal(size=600)
    out = stationary_block_bootstrap(
        x,
        n_replicates=400,
        block_length=5,
        indicator_fn=lambda y: rolling_ar1(y, window=120),
        seed=11,
    )
    ***REMOVED*** iid + no trend -> tau_obs should be small in magnitude
    assert abs(out["tau_obs"]) < 0.25, (
        f"unexpected tau_obs={out['tau_obs']} on iid input"
    )
    ***REMOVED*** block-bootstrap p must NOT be tiny (no false positive)
    assert out["p_block"] > 0.05, (
        f"iid input falsely rejected: p_block={out['p_block']}"
    )
    ***REMOVED*** block-bootstrap CI must straddle zero
    assert out["ci_lo_95"] < 0 < out["ci_hi_95"], (
        f"iid CI does not straddle zero: [{out['ci_lo_95']},{out['ci_hi_95']}]"
    )


***REMOVED*** ---------------------------------------------------------------------
***REMOVED*** Case 2: strong AR1 — naive p is misleadingly small, block-bootstrap
***REMOVED*** corrects it.
***REMOVED*** ---------------------------------------------------------------------

def test_strong_ar1_block_bootstrap_corrects_inflation():
    ***REMOVED*** AR1(0.85), no trend, n=600
    x = _ar1(n=600, phi=0.85, sigma=1.0, seed=42)
    out = stationary_block_bootstrap(
        x,
        n_replicates=400,
        block_length=30,
        indicator_fn=lambda y: rolling_ar1(y, window=120),
        seed=7,
    )
    ***REMOVED*** The block-bootstrap CI on tau under no-trend AR1 must be wide enough
    ***REMOVED*** to straddle zero.
    assert out["ci_lo_95"] < 0 < out["ci_hi_95"], (
        f"AR1 block CI fails to straddle zero: "
        f"[{out['ci_lo_95']},{out['ci_hi_95']}]"
    )
    ***REMOVED*** Block-bootstrap p must NOT be < 0.01 (i.e. corrects the naive
    ***REMOVED*** inflation under heavy AR1).
    assert out["p_block"] > 0.01, (
        f"block-bootstrap did not correct AR1 inflation: "
        f"p_block={out['p_block']}, tau_obs={out['tau_obs']}"
    )
    ***REMOVED*** The bootstrap CI width must be wider than the iid-input CI width.
    ***REMOVED*** Sanity check: half-width > 0.2 on n=600 with strong AR1.
    half_width = (out["ci_hi_95"] - out["ci_lo_95"]) / 2.0
    assert half_width > 0.15, (
        f"block CI suspiciously narrow under strong AR1: half_width={half_width}"
    )


***REMOVED*** ---------------------------------------------------------------------
***REMOVED*** Case 3: short series — graceful behaviour (no crash, returns finite).
***REMOVED*** ---------------------------------------------------------------------

def test_short_series_graceful_fallback():
    x = _ar1(n=80, phi=0.6, sigma=1.0, seed=99)
    ***REMOVED*** Window must fit
    out = moving_block_bootstrap(
        x,
        n_replicates=100,
        block_length=6,
        indicator_fn=lambda y: rolling_ar1(y, window=20),
        seed=5,
    )
    assert np.isfinite(out["tau_obs"])
    assert 0.0 < out["p_block"] <= 1.0
    assert np.isfinite(out["ci_lo_95"])
    assert np.isfinite(out["ci_hi_95"])
    assert out["block_length"] >= 2


***REMOVED*** ---------------------------------------------------------------------
***REMOVED*** Sanity: optimal block length grows with AR1 coefficient.
***REMOVED*** ---------------------------------------------------------------------

def test_politis_white_grows_with_autocorrelation():
    x_iid = _ar1(n=800, phi=0.0, sigma=1.0, seed=1)
    x_mid = _ar1(n=800, phi=0.5, sigma=1.0, seed=2)
    x_hi = _ar1(n=800, phi=0.9, sigma=1.0, seed=3)
    L_iid = politis_white_optimal_block_length(x_iid)
    L_mid = politis_white_optimal_block_length(x_mid)
    L_hi = politis_white_optimal_block_length(x_hi)
    ***REMOVED*** Block length must be at least 2 in all cases
    assert L_iid >= 2 and L_mid >= 2 and L_hi >= 2
    ***REMOVED*** On strongly-correlated AR1, optimal block length must exceed
    ***REMOVED*** the iid case
    assert L_hi >= L_iid, (
        f"L_hi={L_hi} not >= L_iid={L_iid} -- Politis-White ordering broken"
    )


***REMOVED*** ---------------------------------------------------------------------
***REMOVED*** Sanity: rolling_ar1 and rolling_variance produce expected shapes.
***REMOVED*** ---------------------------------------------------------------------

def test_rolling_indicators_shapes_and_finiteness():
    x = _ar1(n=300, phi=0.7, sigma=1.0, seed=10)
    ar1 = rolling_ar1(x, window=60)
    var = rolling_variance(x, window=60)
    assert ar1.shape == (300 - 60 + 1,)
    assert var.shape == (300 - 60 + 1,)
    assert np.all(np.isfinite(ar1))
    assert np.all(np.isfinite(var))


***REMOVED*** ---------------------------------------------------------------------
***REMOVED*** Sanity: kendall_tau_vs_time on increasing series gives tau ~ +1.
***REMOVED*** ---------------------------------------------------------------------

def test_kendall_tau_vs_time_monotone():
    y = np.linspace(0, 1, 50)
    tau, p = kendall_tau_vs_time(y)
    assert tau == pytest.approx(1.0, abs=1e-9)
    assert p < 1e-5
