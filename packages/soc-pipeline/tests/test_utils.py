"""Tests for soc_pipeline.utils."""
from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import empirical_ccdf, verdict_from_alpha_band


@pytest.mark.sanity
def test_empirical_ccdf_shape_and_monotonic():
    rng = np.random.default_rng(0)
    samples = rng.pareto(2.0, size=2000) + 1.0
    grid, ccdf = empirical_ccdf(samples, n_points=100)
    assert grid is not None and ccdf is not None
    assert grid.shape == (100,)
    assert ccdf.shape == (100,)
    # CCDF is non-increasing along the grid
    assert np.all(np.diff(ccdf) <= 0)


@pytest.mark.sanity
def test_empirical_ccdf_empty():
    grid, ccdf = empirical_ccdf(np.array([]))
    assert grid is None and ccdf is None


@pytest.mark.sanity
def test_verdict_confirmed():
    v = verdict_from_alpha_band(2.0, predicted=(1.5, 2.5))
    assert v == "CONFIRMED"


@pytest.mark.sanity
def test_verdict_literature_fallback():
    v = verdict_from_alpha_band(2.6, predicted=(1.5, 2.5), literature=(1.3, 3.0))
    assert v == "CONFIRMED (literature band)"


@pytest.mark.sanity
def test_verdict_deviating():
    v = verdict_from_alpha_band(5.0, predicted=(1.5, 2.5), literature=(1.3, 3.0))
    assert v == "DEVIATING"


@pytest.mark.sanity
def test_verdict_inconclusive_for_none():
    v = verdict_from_alpha_band(None, predicted=(1.5, 2.5))
    assert v == "INCONCLUSIVE"
