"""Tests for soc_pipeline.null_controls."""
from __future__ import annotations

import pytest

from soc_pipeline import NullCase, synthetic_null


@pytest.mark.sanity
def test_synthetic_null_all_three_rejected():
    """Healthy pipeline rejects power-law on all three synthetic nulls."""
    out = synthetic_null(n=5000, seed=42)
    assert isinstance(out, dict)
    assert set(out.keys()) == {"gaussian_walk", "exponential", "poisson_iat"}
    for name, case in out.items():
        assert isinstance(case, NullCase)
        assert case.correctly_rejected, (
            f"{name}: pipeline failed to reject power-law; "
            f"fit={case.fit.to_dict()}"
        )


@pytest.mark.sanity
def test_synthetic_null_single_kind():
    case = synthetic_null(kind="exponential", n=3000, seed=0)
    assert isinstance(case, NullCase)
    assert case.name == "exponential"
    assert case.correctly_rejected


@pytest.mark.sanity
def test_synthetic_null_invalid_kind():
    with pytest.raises(ValueError):
        synthetic_null(kind="bogus_dist", n=1000)  # type: ignore[arg-type]
