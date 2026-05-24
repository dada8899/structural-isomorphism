"""Tests for the pandas `.soc` accessor."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import soc_pipeline  # noqa: F401 — side-effect registers accessor
from soc_pipeline.pandas_accessor import SocAccessor, Verdict


# --------------------------------------------------------------------- helpers


def _pareto_series(
    alpha_true: float = 1.5,
    n: int = 5000,
    seed: int = 0,
    name: str = "magnitudes",
) -> pd.Series:
    """Generate a Pareto series with shape `alpha_true`.

    Note: scipy/numpy pareto shape `a` corresponds to Clauset alpha = a + 1.
    """
    rng = np.random.default_rng(seed)
    return pd.Series(rng.pareto(alpha_true, n) + 1.0, name=name)


# --------------------------------------------------------------- registration


def test_accessor_registered_on_import():
    """Importing soc_pipeline should register `.soc` on pandas Series."""
    s = pd.Series([1.0, 2.0, 3.0])
    assert hasattr(s, "soc")
    assert isinstance(s.soc, SocAccessor)


def test_accessor_returns_same_class_each_time():
    """`.soc` should be the SocAccessor type, not some wrapper."""
    s = pd.Series([1.0, 2.0, 3.0])
    a1 = s.soc
    a2 = s.soc
    assert type(a1) is type(a2) is SocAccessor


# --------------------------------------------------------------- dtype guard


def test_typeerror_on_non_numeric():
    """Non-numeric series should raise TypeError on accessor construction."""
    s = pd.Series(["a", "b", "c"])
    with pytest.raises(TypeError, match="numeric Series"):
        _ = s.soc.fit_alpha()


def test_typeerror_on_object_dtype():
    """Object-dtype mixed series should raise TypeError."""
    s = pd.Series([1, "two", 3.0], dtype=object)
    with pytest.raises(TypeError):
        _ = s.soc.fit_alpha()


def test_int_dtype_accepted():
    """Integer dtype should be accepted (is_numeric_dtype returns True)."""
    s = pd.Series(np.arange(1, 200, dtype=np.int64))
    # Should NOT raise on accessor construction
    _ = s.soc
    # Will likely error on fit because xmin too small etc; we just check no
    # type-error at the dtype check.


# --------------------------------------------------------------- happy path


def test_fit_alpha_returns_float_near_truth():
    """For Pareto(a=1.5), Clauset alpha should be ~2.5."""
    s = _pareto_series(alpha_true=1.5, n=5000, seed=0)
    alpha = s.soc.fit_alpha()
    assert alpha is not None
    assert isinstance(alpha, float)
    # Generous band (small-sample fluctuation + Clauset MLE bias)
    assert 2.2 < alpha < 2.8, f"alpha={alpha} not in (2.2, 2.8)"


def test_validate_with_matching_band_passes():
    """For Pareto with true alpha=2.5, the band (2.3, 2.7) should yield in_band=True."""
    s = _pareto_series(alpha_true=1.5, n=5000, seed=0)
    v = s.soc.validate(expected_band=(2.3, 2.7), n_boot=50)
    assert isinstance(v, Verdict)
    assert v.error is None
    assert v.in_band is True
    assert v.alpha is not None
    assert 2.3 <= v.alpha <= 2.7
    assert v.verdict == "PASS"
    assert v.n_tail > 0
    assert v.n_total == 5000
    assert v.alpha_ci_low is not None
    assert v.alpha_ci_high is not None
    assert v.alpha_ci_low <= v.alpha <= v.alpha_ci_high + 0.05  # CI sanity


def test_validate_with_non_matching_band_marks_out_of_band():
    """If the band is far from truth, in_band should be False."""
    s = _pareto_series(alpha_true=1.5, n=5000, seed=0)
    v = s.soc.validate(expected_band=(5.0, 6.0), n_boot=0)
    assert v.in_band is False
    # underlying verdict should be DEVIATING since alpha falls outside predicted
    assert v.underlying_verdict == "DEVIATING"


def test_is_pass_true_for_matching():
    s = _pareto_series(alpha_true=1.5, n=5000, seed=0)
    assert s.soc.is_pass(expected_band=(2.3, 2.7)) is True


def test_is_pass_false_for_non_matching():
    s = _pareto_series(alpha_true=1.5, n=5000, seed=0)
    assert s.soc.is_pass(expected_band=(5.0, 6.0)) is False


def test_label_falls_back_to_series_name():
    """If no `label` given, use the Series name."""
    s = _pareto_series(name="quake_magnitudes", n=2000, seed=1)
    v = s.soc.validate(n_boot=0)
    assert v.label == "quake_magnitudes"


def test_label_falls_back_to_series_default_when_no_name():
    """Unnamed series should yield label='series'."""
    s = pd.Series(_pareto_series(n=2000, seed=2).values)  # name=None
    v = s.soc.validate(n_boot=0)
    assert v.label == "series"


def test_explicit_label_overrides():
    s = _pareto_series(name="ignored", n=2000, seed=3)
    v = s.soc.validate(label="my_label", n_boot=0)
    assert v.label == "my_label"


# --------------------------------------------------------------- reproducibility


def test_reproducibility_under_seed():
    """Same data + same seed -> same bootstrap CI."""
    s = _pareto_series(alpha_true=1.5, n=3000, seed=42)
    v1 = s.soc.validate(expected_band=(2.3, 2.7), n_boot=50, seed=123)
    v2 = s.soc.validate(expected_band=(2.3, 2.7), n_boot=50, seed=123)
    assert v1.alpha == pytest.approx(v2.alpha)
    if v1.alpha_ci_low is not None and v2.alpha_ci_low is not None:
        assert v1.alpha_ci_low == pytest.approx(v2.alpha_ci_low)
        assert v1.alpha_ci_high == pytest.approx(v2.alpha_ci_high)


def test_different_seeds_give_different_bootstrap_ci():
    """Different bootstrap seeds should perturb CI (sanity that seed actually flows)."""
    s = _pareto_series(alpha_true=1.5, n=3000, seed=42)
    v1 = s.soc.validate(expected_band=(2.3, 2.7), n_boot=50, seed=123)
    v2 = s.soc.validate(expected_band=(2.3, 2.7), n_boot=50, seed=456)
    # Point estimate (alpha) is from the full sample so should be identical
    assert v1.alpha == pytest.approx(v2.alpha)
    # CI should differ because bootstrap RNG differs
    assert v1.alpha_ci_low != v2.alpha_ci_low or v1.alpha_ci_high != v2.alpha_ci_high


# --------------------------------------------------------------- skip-bootstrap


def test_n_boot_zero_skips_bootstrap():
    """`n_boot=0` should leave alpha_ci_low/high as None."""
    s = _pareto_series(alpha_true=1.5, n=2000, seed=10)
    v = s.soc.validate(expected_band=(2.3, 2.7), n_boot=0)
    assert v.alpha is not None
    assert v.alpha_ci_low is None
    assert v.alpha_ci_high is None


def test_fit_alpha_does_not_run_bootstrap():
    """`fit_alpha()` is a fast path — must not bootstrap."""
    s = _pareto_series(alpha_true=1.5, n=2000, seed=11)
    # If this were running 200-boot it would be much slower; we just assert
    # the return type + non-None.
    alpha = s.soc.fit_alpha()
    assert isinstance(alpha, float)


# --------------------------------------------------------------- error handling


def test_too_few_samples_returns_error():
    """A series shorter than min_samples should set Verdict.error and verdict=INCONCLUSIVE."""
    s = pd.Series(np.arange(1, 50, dtype=float))
    v = s.soc.validate(expected_band=(2.0, 3.0), n_boot=0)
    assert v.error is not None
    assert "too few" in v.error.lower()
    assert v.verdict == "INCONCLUSIVE"


def test_no_band_yields_inconclusive_verdict():
    """If no expected_band supplied, coarse verdict stays INCONCLUSIVE."""
    s = _pareto_series(alpha_true=1.5, n=2000, seed=12)
    v = s.soc.validate(n_boot=0)
    assert v.verdict == "INCONCLUSIVE"
    assert v.in_band is False


# --------------------------------------------------------------- to_dict


def test_verdict_to_dict_is_json_friendly():
    """to_dict() should return a flat dict of primitives (no FitResult)."""
    s = _pareto_series(alpha_true=1.5, n=2000, seed=13)
    v = s.soc.validate(expected_band=(2.3, 2.7), n_boot=0)
    d = v.to_dict()
    assert isinstance(d, dict)
    assert d["verdict"] in {"PASS", "FAIL", "INCONCLUSIVE"}
    assert d["alpha"] == pytest.approx(v.alpha)
    # FitResult / BootstrapResult should NOT appear in to_dict
    assert "fit" not in d
    assert "bootstrap" not in d
