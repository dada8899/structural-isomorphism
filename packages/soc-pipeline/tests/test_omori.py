"""Tests for soc_pipeline.omori."""
from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import OmoriResult, bin_and_omori_from_events, fit_omori_p


@pytest.mark.sanity
def test_omori_p_recovers_synthetic():
    """Synthetic aftershocks with p=1.2 -> recovered p in [0.9, 1.5].

    Generate via inverse-CDF of f(t) = (p-1) * c^(p-1) * (t+c)^-p on [0, inf).
    CDF: F(t) = 1 - (c/(t+c))^(p-1), inverse: t = c * ((1-u)^(-1/(p-1)) - 1).
    """
    rng = np.random.default_rng(42)
    p_true = 1.2
    c_days = 0.01
    c_sec = c_days * 86400
    u = rng.uniform(0.0, 1.0, 20000)
    dts = c_sec * ((1.0 - u) ** (-1.0 / (p_true - 1.0)) - 1.0)
    # Clip to the fit window so we only keep samples the fitter will use
    dts = dts[(dts >= 300.0) & (dts <= 30 * 86400)]
    assert len(dts) > 1000
    result = fit_omori_p(dts)
    assert isinstance(result, OmoriResult)
    assert result.error is None, result.error
    assert result.p is not None
    # Recovery within ±0.3 of true is acceptable for this synthetic + bin scheme
    assert 0.9 < result.p < 1.5, f"p={result.p} far from true {p_true}"
    assert result.R2 is not None
    assert result.R2 > 0.5


@pytest.mark.sanity
def test_omori_p_too_few_aftershocks():
    dts = np.array([100.0, 200.0])
    result = fit_omori_p(dts)
    assert result.error is not None


@pytest.mark.sanity
def test_bin_and_omori_event_stream():
    """Synthetic main + aftershock stream -> Omori detector finds non-trivial result."""
    rng = np.random.default_rng(0)
    # Background Poisson + 20 main shocks each spawning bursts
    bg = rng.uniform(0, 1e6, 5000)
    bursts: list[np.ndarray] = []
    main_times = rng.uniform(1e5, 9e5, 20)
    for mt in main_times:
        bursts.append(mt + rng.exponential(scale=100.0, size=200))
    times = np.sort(np.concatenate([bg, *bursts]))
    result = bin_and_omori_from_events(times, bin_seconds=60.0)
    assert isinstance(result, OmoriResult)
    # At minimum the detector found main shocks
    assert result.n_main is not None
    assert result.n_main > 0


@pytest.mark.sanity
def test_bin_and_omori_empty():
    result = bin_and_omori_from_events(np.array([]))
    assert result.error is not None
