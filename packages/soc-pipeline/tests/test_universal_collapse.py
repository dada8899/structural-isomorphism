"""Tests for soc_pipeline.universal_collapse."""
from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import CollapseResult, shape_normalized_collapse


@pytest.mark.sanity
def test_shape_normalized_collapse_two_systems():
    rng = np.random.default_rng(0)
    sys_a = (1.0 - rng.uniform(0, 1, 5000)) ** (-1.0 / (2.0 - 1.0))
    sys_b = (1.0 - rng.uniform(0, 1, 5000)) ** (-1.0 / (3.0 - 1.0))
    out = shape_normalized_collapse({
        "system_a": (sys_a, 2.0),
        "system_b": (sys_b, 3.0),
    })
    assert isinstance(out, CollapseResult)
    assert out.n_systems == 2
    assert "system_a" in out.systems
    assert "system_b" in out.systems
    assert out.alpha_range == (2.0, 3.0)
    a = out.systems["system_a"]
    assert a.x_rescaled.shape == a.y_rescaled.shape
    assert a.n == 5000
    assert a.s_star > 0


@pytest.mark.sanity
def test_shape_normalized_collapse_skips_small_samples():
    out = shape_normalized_collapse({
        "small": (np.array([1.0, 2.0, 3.0]), 2.0),
    })
    assert out.n_systems == 0
