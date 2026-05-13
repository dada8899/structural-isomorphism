"""Tests for soc_pipeline.bootstrap."""
from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import BootstrapResult, bootstrap_ci


@pytest.mark.sanity
def test_bootstrap_ci_covers_true_alpha():
    """Bootstrap CI must contain the true alpha for synthetic data."""
    rng = np.random.default_rng(42)
    u = rng.uniform(0.0, 1.0, 5000)
    alpha_true = 2.5
    samples = (1.0 - u) ** (-1.0 / (alpha_true - 1.0))
    result = bootstrap_ci(samples, n_boot=80, seed=42)
    assert isinstance(result, BootstrapResult)
    assert result.error is None
    assert result.ci_low is not None
    assert result.ci_high is not None
    assert result.ci_low < alpha_true < result.ci_high, (
        f"true alpha={alpha_true} not in CI [{result.ci_low}, {result.ci_high}]"
    )


@pytest.mark.sanity
def test_bootstrap_returns_error_on_small_sample():
    samples = np.random.pareto(2.0, size=50) + 1.0
    result = bootstrap_ci(samples, n_boot=50)
    assert result.error is not None
    assert "too few" in result.error.lower()


@pytest.mark.sanity
def test_bootstrap_n_boot_succeeded_positive():
    rng = np.random.default_rng(0)
    samples = rng.pareto(2.0, size=2000) + 1.0
    result = bootstrap_ci(samples, n_boot=40, seed=1)
    assert result.error is None
    assert result.n_boot_succeeded > 20


@pytest.mark.sanity
def test_bootstrap_reproducible_with_seed():
    rng = np.random.default_rng(7)
    samples = rng.pareto(2.0, size=2000) + 1.0
    a = bootstrap_ci(samples, n_boot=40, seed=42)
    b = bootstrap_ci(samples, n_boot=40, seed=42)
    assert a.alpha_median == b.alpha_median
    assert a.ci_low == b.ci_low
