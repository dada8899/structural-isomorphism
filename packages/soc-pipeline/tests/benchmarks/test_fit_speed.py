from __future__ import annotations

import numpy as np
import pytest

from soc_pipeline import fit_clauset_powerlaw


@pytest.mark.benchmark
def test_fit_clauset_powerlaw_100k_pareto_speed(benchmark):
    rng = np.random.default_rng(123)
    data = rng.pareto(2.5, 100_000) + 1.0

    result = benchmark.pedantic(
        fit_clauset_powerlaw,
        args=(data,),
        kwargs={"name": "benchmark_pareto_100k"},
        rounds=1,
        iterations=1,
    )

    assert result.error is None
    assert result.n_total == 100_000
    assert result.n_tail >= 5_000
    assert result.extra["xmin_candidates_scanned"] <= 512
    assert 3.2 < result.alpha < 3.8
