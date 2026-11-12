"""Tests for soc_pipeline.b_value."""
from __future__ import annotations

import math

import numpy as np
import pytest

from soc_pipeline import b_to_clauset_alpha, fit_b_value
from soc_pipeline.b_value import estimate_mc_maxc


@pytest.mark.sanity
def test_b_to_clauset_alpha():
    assert math.isclose(b_to_clauset_alpha(1.0), 1.0 + 1.0 / 1.5, abs_tol=1e-9)
    assert math.isclose(b_to_clauset_alpha(0.75), 1.5, abs_tol=1e-9)


@pytest.mark.sanity
def test_fit_b_value_recovers_true_b():
    """Synthetic G-R: b_true=1.0, recovered b ~1.0 ±0.1."""
    rng = np.random.default_rng(42)
    b_true = 1.0
    mc = 4.0
    # mag = mc + Exponential(1/(b*ln10))
    mags = mc + rng.exponential(scale=1.0 / (b_true * math.log(10)), size=10000)
    result = fit_b_value(mags, mc=mc)
    assert result.error is None
    assert abs(result.b - b_true) < 0.1, f"b={result.b} too far from true {b_true}"
    assert result.n_above_mc > 9000
    assert result.alpha_equivalent is not None


@pytest.mark.sanity
def test_fit_b_value_with_bootstrap():
    rng = np.random.default_rng(0)
    mc = 4.0
    mags = mc + rng.exponential(scale=1.0 / (1.0 * math.log(10)), size=3000)
    result = fit_b_value(mags, mc=mc, bootstrap=True, n_boot=200)
    assert result.ci_low is not None
    assert result.ci_high is not None
    assert result.ci_low < result.b < result.ci_high


@pytest.mark.sanity
def test_estimate_mc_maxc():
    rng = np.random.default_rng(0)
    # Drop-off below mc=4.0
    mags = np.concatenate([
        rng.uniform(2.0, 4.0, 100),  # incomplete
        4.0 + rng.exponential(scale=1.0 / math.log(10), size=5000),  # complete
    ])
    mc = estimate_mc_maxc(mags)
    assert 3.5 < mc < 4.5, f"mc={mc} not near true 4.0"


@pytest.mark.sanity
def test_fit_b_value_too_few_returns_error():
    mags = np.array([4.0, 4.1])
    result = fit_b_value(mags)
    assert result.error is not None
