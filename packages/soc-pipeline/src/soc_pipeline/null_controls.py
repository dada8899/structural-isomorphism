"""Synthetic null controls for SOC pipeline.

A correct SOC pipeline must REJECT power-law on non-heavy-tail synthetic
distributions (gaussian, exponential, poisson IATs). Use these to verify
your fit pipeline isn't a yes-man.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .fit import FitResult, fit_clauset_powerlaw

__all__ = ["NullCase", "synthetic_null"]

NullKind = Literal["gaussian_walk", "exponential", "poisson_iat"]


@dataclass
class NullCase:
    """Result of running the pipeline on one synthetic null distribution.

    Attributes:
        name: Which null distribution generated the sample.
        fit: FitResult from passing the sample through the SOC pipeline.
        correctly_rejected: True iff the pipeline reported rejects_power_law.
    """

    name: NullKind
    fit: FitResult
    correctly_rejected: bool


def _generate(kind: NullKind, n: int, rng: np.random.Generator) -> np.ndarray:
    if kind == "gaussian_walk":
        return np.abs(rng.normal(0.0, 1.0, size=n))
    if kind == "exponential":
        return rng.exponential(scale=1.0, size=n)
    if kind == "poisson_iat":
        # inter-arrival times of a Poisson process
        return rng.exponential(scale=0.1, size=n)
    raise ValueError(f"unknown null kind: {kind}")


def synthetic_null(
    kind: NullKind | None = None,
    n: int = 20_000,
    seed: int = 42,
) -> dict[str, NullCase] | NullCase:
    """Run the pipeline on one or all synthetic nulls.

    Args:
        kind: If None, run all three null kinds (gaussian_walk, exponential,
            poisson_iat) and return a dict keyed by name. If a specific kind,
            return a single NullCase.
        n: Sample size per null.
        seed: RNG seed.

    Returns:
        Either a dict[str, NullCase] (when kind is None) or a single NullCase.

    Notes:
        Use the dict form for the standard validation suite. The returned
        cases each carry a `correctly_rejected` flag — pipeline is healthy
        iff all three reject power-law.
    """
    rng = np.random.default_rng(seed)
    if kind is not None:
        sample = _generate(kind, n, rng)
        fit = fit_clauset_powerlaw(sample, name=kind)
        return NullCase(name=kind, fit=fit, correctly_rejected=bool(fit.rejects_power_law))

    out: dict[str, NullCase] = {}
    for k in ("gaussian_walk", "exponential", "poisson_iat"):
        sample = _generate(k, n, rng)  # type: ignore[arg-type]
        fit = fit_clauset_powerlaw(sample, name=k)
        out[k] = NullCase(
            name=k,  # type: ignore[arg-type]
            fit=fit,
            correctly_rejected=bool(fit.rejects_power_law),
        )
    return out
