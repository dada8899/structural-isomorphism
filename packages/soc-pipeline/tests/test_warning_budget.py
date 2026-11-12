"""Keep third-party numerical warning volume visible and bounded."""
from __future__ import annotations

import warnings

import numpy as np

from soc_pipeline import bootstrap_ci, fit_clauset_powerlaw, vuong_lr_test
from soc_pipeline.fit import _run_powerlaw_fit


def test_representative_fit_warning_budget() -> None:
    rng = np.random.default_rng(20260713)
    sample = (rng.pareto(1.5, size=600) + 1.0) * 10.0

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = fit_clauset_powerlaw(sample, min_samples=100)

    assert result.error is None
    messages = [str(item.message) for item in caught]
    assert not any("standard_err" in message for message in messages)
    # Numerical-fit diagnostics remain visible, but a dependency change may
    # not silently turn one representative fit into another warning storm.
    assert len(caught) <= 4, messages[:10]


def test_bootstrap_and_lr_fast_paths_keep_vendor_deprecation_bounded() -> None:
    rng = np.random.default_rng(17)
    sample = (rng.pareto(1.5, size=250) + 1.0) * 10.0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        boot = bootstrap_ci(sample, n_boot=20, seed=3, min_samples=200)
        lr = vuong_lr_test(sample, vs="exponential")
    assert boot.error is None and boot.n_boot_succeeded == 20
    assert lr.error is None
    assert not any("standard_err" in str(item.message) for item in caught)
    assert len(caught) <= 4, [str(item.message) for item in caught[:10]]


def test_powerlaw_pre_v2_sigma_fallback() -> None:
    class Distribution:
        alpha = 2.5
        sigma = 0.2
        xmin = 1.0
        D = 0.1

    class Fit:
        power_law = Distribution()

        def distribution_compare(self, *args, **kwargs):
            return 1.0, 0.5

    class LegacyPowerlaw:
        @staticmethod
        def Fit(*args, **kwargs):
            return Fit()

    result = _run_powerlaw_fit(
        LegacyPowerlaw, np.arange(1.0, 101.0), discrete=False
    )
    assert result[:4] == (2.5, 0.2, 1.0, 0.1)
