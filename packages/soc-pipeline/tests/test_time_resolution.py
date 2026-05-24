"""Tests for soc_pipeline.time_resolution."""
from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import time_resolution_sweep


@pytest.mark.sanity
def test_time_resolution_sweep_returns_sweep_entries():
    rng = np.random.default_rng(0)
    # 5000 events over 30 days
    times = np.sort(rng.uniform(0, 30 * 86400, 5000))
    out = time_resolution_sweep(times, bin_sizes_sec=(300.0, 3600.0, 86400.0))
    assert "sweep" in out
    assert len(out["sweep"]) == 3


@pytest.mark.sanity
def test_time_resolution_too_few_events():
    out = time_resolution_sweep(np.array([1.0, 2.0]))
    assert "error" in out
