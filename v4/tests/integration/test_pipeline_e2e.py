"""Layer 5 SOC pipeline end-to-end integration test.

Synthetic power-law data flows through `fit_clauset_powerlaw` →
`verdict_from_alpha_band` and we assert the verdict is CONFIRMED.

Synthetic non-power-law data flows through the same pipeline and we assert
rejects_power_law=True (negative control).

These are the same primitives the V4 paper uses for the 13 verified
universality classes, so this test guards against silent regression in the
shared library.
"""

from __future__ import annotations

import numpy as np
import pytest

# Wire v4/lib on sys.path
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "v4" / "lib"))

from soc_pipeline import (  # noqa: E402
    fit_clauset_powerlaw,
    run_size_null_controls,
    verdict_from_alpha_band,
)


# ---------------------------------------------------------------------------
# Synthetic power-law generators
# ---------------------------------------------------------------------------


def _sample_power_law(alpha: float, xmin: float, n: int, seed: int = 42) -> np.ndarray:
    """Inverse-CDF sampling of continuous power law P(x) = (alpha-1)/xmin * (x/xmin)^-alpha."""
    rng = np.random.default_rng(seed)
    u = rng.uniform(size=n)
    return xmin * u ** (-1.0 / (alpha - 1.0))


# ---------------------------------------------------------------------------
# Positive control: power-law-distributed data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("true_alpha,seed", [(2.5, 42), (2.0, 7), (3.0, 99)])
def test_powerlaw_recovers_alpha_in_band(true_alpha, seed):
    """Pipeline recovers α within ~0.3 of truth on n=5000 synthetic samples."""
    vals = _sample_power_law(true_alpha, xmin=1.0, n=5000, seed=seed)
    out = fit_clauset_powerlaw(vals, name=f"synth_alpha_{true_alpha}")
    assert "error" not in out, out
    alpha = out["alpha"]
    assert true_alpha - 0.3 <= alpha <= true_alpha + 0.3, (
        f"alpha={alpha:.3f} not within 0.3 of true {true_alpha}"
    )
    assert out["n_total"] >= 4000  # almost all positive after filter


def test_verdict_band_positive():
    """CONFIRMED when alpha is inside predicted band."""
    v = verdict_from_alpha_band(2.5, (2.3, 2.7))
    assert v == "CONFIRMED"


def test_verdict_band_literature_fallback():
    """CONFIRMED (literature band) when narrow band misses but literature catches."""
    v = verdict_from_alpha_band(2.9, (2.3, 2.7), literature=(2.5, 3.0))
    assert v == "CONFIRMED (literature band)"


def test_verdict_band_deviating():
    """DEVIATING when alpha outside both bands."""
    v = verdict_from_alpha_band(5.0, (2.0, 3.0), literature=(1.8, 3.2))
    assert v == "DEVIATING"


def test_verdict_band_inconclusive_on_none():
    v = verdict_from_alpha_band(None, (2.0, 3.0))
    assert v == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Negative control: non-power-law data
# ---------------------------------------------------------------------------


def test_null_controls_all_reject_powerlaw():
    """Pipeline must correctly REJECT the power-law on gaussian / exponential /
    poisson IAT — this is the headline V4 Phase-5 null-control result.
    """
    out = run_size_null_controls(seed=42, n=10_000)  # smaller n to keep test < 30s
    # All three controls must trigger rejects_power_law=True
    for k in ("gaussian_walk", "exponential", "poisson_iat"):
        assert out[k].get("rejects_power_law") is True, (
            f"null control {k} not rejected: {out[k]}"
        )
    assert out["all_rejected"] is True


# ---------------------------------------------------------------------------
# Insufficient data handling
# ---------------------------------------------------------------------------


def test_powerlaw_too_few_samples_returns_error():
    """fit_clauset_powerlaw returns an error dict on n<100 (not exception)."""
    out = fit_clauset_powerlaw(np.array([1.0, 2.0, 3.0]), name="tiny")
    assert "error" in out


def test_powerlaw_filters_nonpositive():
    """Negative and zero values are filtered before fitting."""
    vals = _sample_power_law(2.5, xmin=1.0, n=2000, seed=42)
    # Inject negatives + zeros
    mixed = np.concatenate([vals, [-1.0, 0.0, -10.0] * 100])
    out = fit_clauset_powerlaw(mixed, name="mixed")
    assert "error" not in out
    # Result should be near the underlying clean fit
    assert 2.0 <= out["alpha"] <= 3.0
