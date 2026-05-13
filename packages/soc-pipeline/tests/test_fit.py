"""Tests for soc_pipeline.fit — Clauset 2009 MLE."""
from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import FitResult, fit_clauset_powerlaw


@pytest.mark.sanity
def test_powerlaw_alpha_recovery_2_5():
    """Synthetic alpha=2.5 continuous power-law, n=10000 -> recovered alpha in [2.2, 2.8]."""
    rng = np.random.default_rng(42)
    u = rng.uniform(0.0, 1.0, 10000)
    xmin = 1.0
    alpha_true = 2.5
    samples = xmin * (1.0 - u) ** (-1.0 / (alpha_true - 1.0))
    result = fit_clauset_powerlaw(samples, name="synthetic_pl")
    assert isinstance(result, FitResult)
    assert result.error is None
    assert result.alpha is not None
    assert 2.2 < result.alpha < 2.8, f"alpha out of band: {result.alpha}"
    assert result.n_total == 10000


@pytest.mark.sanity
def test_powerlaw_alpha_recovery_3_0():
    """Synthetic alpha=3.0 -> recovered alpha in [2.7, 3.3]."""
    rng = np.random.default_rng(123)
    u = rng.uniform(0.0, 1.0, 10000)
    alpha_true = 3.0
    samples = (1.0 - u) ** (-1.0 / (alpha_true - 1.0))
    result = fit_clauset_powerlaw(samples)
    assert result.error is None
    assert 2.7 < result.alpha < 3.3


@pytest.mark.sanity
def test_rejects_lognormal_via_lr():
    """Pure lognormal n=2000: LR test must produce a vs_lognormal_R field."""
    rng = np.random.default_rng(42)
    samples = rng.lognormal(mean=0.0, sigma=1.5, size=2000)
    samples = samples[samples > 0]
    result = fit_clauset_powerlaw(samples, name="lognormal_test")
    assert result.vs_lognormal_R is not None
    assert result.vs_powerlaw_lognormal_winner in (
        "lognormal", "inconclusive", "power_law"
    )


@pytest.mark.sanity
def test_rejects_exponential():
    """Pure exponential should be rejected as power-law."""
    rng = np.random.default_rng(42)
    samples = rng.exponential(scale=1.0, size=5000)
    result = fit_clauset_powerlaw(samples, name="exponential_test")
    assert result.vs_exponential_R is not None
    assert result.rejects_power_law is True


@pytest.mark.sanity
def test_too_few_samples_returns_error():
    """n < min_samples returns FitResult with error message."""
    samples = np.array([1.0, 2.0, 3.0])
    result = fit_clauset_powerlaw(samples)
    assert result.error is not None
    assert "too few" in result.error.lower()


@pytest.mark.sanity
def test_filters_nonpositive():
    """NaN / zero / negative entries are stripped."""
    rng = np.random.default_rng(0)
    good = rng.pareto(2.5, size=2000) + 1.0
    polluted = np.concatenate([good, [0.0, -1.0, np.nan, np.inf, -np.inf]])
    result = fit_clauset_powerlaw(polluted)
    assert result.error is None
    assert result.n_total == 2000


@pytest.mark.sanity
def test_to_dict_backcompat():
    """to_dict() exposes legacy v4/lib field names for backward compat."""
    rng = np.random.default_rng(0)
    samples = rng.pareto(2.0, size=2000) + 1.0
    fit = fit_clauset_powerlaw(samples, name="dict_test")
    d = fit.to_dict()
    assert "alpha" in d
    assert "sigma_alpha" in d
    assert "xmin" in d
    assert "n_total" in d
    assert "n_tail" in d
    assert "rejects_power_law" in d
    assert d["name"] == "dict_test"


@pytest.mark.sanity
def test_xmin_method_invalid_returns_error():
    samples = np.random.pareto(2.0, size=2000) + 1.0
    result = fit_clauset_powerlaw(samples, xmin_method="bogus")
    assert result.error is not None
