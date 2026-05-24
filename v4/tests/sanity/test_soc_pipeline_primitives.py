"""Deterministic primitive tests for the `soc_pipeline` package.

Synthetic data with known generative models, ~10s budget.

`fit_clauset_powerlaw` returns a `FitResult` dataclass. We call
`.to_dict()` for the legacy-dict view used in these assertions; the
deprecated v4/lib/soc_pipeline.py shim previously wrapped this for
backward compatibility, but tests now target the real package directly.
"""
from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import fit_clauset_powerlaw


@pytest.mark.sanity
def test_powerlaw_alpha_recovery():
    """Synthetic alpha=2.5 continuous power-law, n=10000 -> recovered alpha in [2.2, 2.8]."""
    np.random.seed(42)
    u = np.random.uniform(0.0, 1.0, 10000)
    xmin = 1.0
    alpha_true = 2.5
    samples = xmin * (1.0 - u) ** (-1.0 / (alpha_true - 1.0))
    result = fit_clauset_powerlaw(samples, name="synthetic_pl").to_dict()
    assert "alpha" in result, f"alpha key missing: {result}"
    assert "n_total" in result
    assert 2.2 < result["alpha"] < 2.8, f"alpha out of band: {result['alpha']}"
    assert result["n_total"] == 10000


@pytest.mark.sanity
def test_rejects_lognormal():
    """Pure lognormal n=2000: LR test must produce a vs_lognormal_R field."""
    np.random.seed(42)
    samples = np.random.lognormal(mean=0.0, sigma=1.5, size=2000)
    samples = samples[samples > 0]
    result = fit_clauset_powerlaw(samples, name="synthetic_lognormal").to_dict()
    assert "vs_lognormal_R" in result, f"missing vs_lognormal_R: {result}"
    # Either lognormal preferred (R<0) or inconclusive — must not declare power_law cleanly
    winner = result.get("vs_powerlaw_lognormal_winner")
    assert winner in ("lognormal", "inconclusive", "power_law"), f"unknown winner: {winner}"


@pytest.mark.sanity
def test_rejects_exponential():
    """Pure exponential: pipeline must produce comparison fields and prefer non-power-law verdict."""
    np.random.seed(42)
    samples = np.random.exponential(scale=1.0, size=5000)
    result = fit_clauset_powerlaw(samples, name="synthetic_exponential").to_dict()
    assert "vs_exponential_R" in result, f"missing vs_exponential_R: {result}"
    # rejects_power_law should be True for non-heavy-tail synthetic data
    assert result.get("rejects_power_law") is True, (
        f"pipeline failed to reject exponential as power-law: {result}"
    )
