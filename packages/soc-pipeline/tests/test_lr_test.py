"""Tests for soc_pipeline.lr_test."""
from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import LRResult, vuong_lr_test


@pytest.mark.sanity
def test_lr_prefers_powerlaw_on_pareto():
    rng = np.random.default_rng(0)
    samples = rng.pareto(2.0, size=4000) + 1.0
    result = vuong_lr_test(samples, vs="exponential")
    assert isinstance(result, LRResult)
    assert result.error is None
    assert result.R is not None
    assert result.R > 0


@pytest.mark.sanity
def test_lr_on_exponential_against_exponential():
    """Pure exponential: power-law should not beat exponential."""
    rng = np.random.default_rng(0)
    samples = rng.exponential(scale=1.0, size=5000)
    result = vuong_lr_test(samples, vs="exponential")
    assert result.R is not None
    # Either winner=exponential or inconclusive; not power-law
    assert result.winner != "power_law"


@pytest.mark.sanity
def test_lr_too_few_samples():
    samples = np.array([1.0, 2.0, 3.0])
    result = vuong_lr_test(samples)
    assert result.error is not None
