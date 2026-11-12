"""Tests for v4/validation/climate-tipping pipeline.

Three layers:
  1. Smoke: scripts import & expose expected callables.
  2. Schema: results.json / verdict.md if present have required keys.
  3. Sanity: inline run on a tiny synthetic input -> verdict mechanism wires up.

These tests are intentionally light: they do NOT re-download MODIS / AMOC
(network-bound), they only validate the pipeline plumbing on whatever artifacts
exist on disk plus a small in-process sanity check.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1] / "v4" / "validation" / "climate-tipping"
FETCH_PY = ROOT / "fetch_climate_data.py"
RUN_PY = ROOT / "run_validation.py"


def _import_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader, f"could not load {path}"
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. Smoke
# ---------------------------------------------------------------------------
def test_smoke_fetch_module_imports():
    assert FETCH_PY.exists(), "fetch_climate_data.py must exist"
    mod = _import_from_path("ct_fetch", FETCH_PY)
    # Required public callables.
    for attr in ("fetch_amoc", "fetch_amazon_ndvi", "synthetic_ndvi_fallback",
                 "_modis_subset_retry", "_modis_dates_in_range"):
        assert hasattr(mod, attr), f"fetch module missing {attr}"
    # SITES is the 5-site Amazon panel.
    assert len(mod.SITES) >= 3, "need at least 3 NDVI sites"
    for site in mod.SITES:
        assert len(site) == 4, "each site = (id, lat, lon, descriptor)"
        sid, lat, lon, desc = site
        assert isinstance(sid, str) and sid
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180


def test_smoke_run_module_imports():
    assert RUN_PY.exists(), "run_validation.py must exist"
    mod = _import_from_path("ct_run", RUN_PY)
    for attr in ("clauset_alpha_ks", "fit_powerlaw_xmin_sweep",
                 "deseasonalise", "monthly_mean", "rolling_stat",
                 "kendall_trend", "analyse_system"):
        assert hasattr(mod, attr), f"run module missing {attr}"


# ---------------------------------------------------------------------------
# 2. Schema (gated on whether artifacts exist)
# ---------------------------------------------------------------------------
def test_results_json_schema_if_present():
    rj = ROOT / "results.json"
    if not rj.exists():
        pytest.skip("results.json not yet generated")
    data = json.loads(rj.read_text())
    assert "systems" in data
    assert isinstance(data["systems"], list)
    assert len(data["systems"]) >= 1
    for sys in data["systems"]:
        assert "system" in sys
        assert "ok" in sys
        if sys["ok"]:
            assert "ews" in sys
            assert "ar1_trend" in sys["ews"]
            assert "var_trend" in sys["ews"]
            assert "classical_csd_signature" in sys["ews"]
            assert "verdict" in sys
            assert sys["verdict"] in ("PASS", "FAIL", "INCONCLUSIVE",
                                      "SYNTHETIC", "QUALIFIED")


def test_verdict_md_present_if_results_present():
    if not (ROOT / "results.json").exists():
        pytest.skip("results not yet generated")
    vmd = ROOT / "verdict.md"
    assert vmd.exists(), "verdict.md must accompany results.json"
    text = vmd.read_text()
    assert "scheffer_fold_bifurcation" in text.lower() or "fold" in text.lower()
    assert "amoc" in text.lower()
    assert "ndvi" in text.lower() or "amazon" in text.lower()
    assert "Data sources" in text


def test_fetch_log_present():
    flog = ROOT / "raw" / "fetch_log.json"
    if not flog.exists():
        pytest.skip("fetch_log.json not yet generated")
    log = json.loads(flog.read_text())
    assert "amoc" in log
    assert "ndvi" in log
    # Honesty rule: at least the AMOC source should have real data attempted.
    assert log["amoc"].get("ok") in (True, False)


# ---------------------------------------------------------------------------
# 3. Sanity: in-process inline run on tiny synthetic series
# ---------------------------------------------------------------------------
def test_clauset_alpha_basic():
    """Clauset MLE on a clean Pareto sample returns alpha close to truth."""
    mod = _import_from_path("ct_run", RUN_PY)
    rng = np.random.default_rng(42)
    # Pareto(2.5): inverse-CDF sample. alpha_shape = 2.5 - 1 = 1.5
    alpha_true = 2.5
    u = rng.uniform(0, 1, size=4000)
    x = (1.0 - u) ** (-1.0 / (alpha_true - 1))  # xmin = 1 by construction
    alpha_hat, ks, n = mod.clauset_alpha_ks(x, xmin=1.0)
    assert 2.2 < alpha_hat < 2.8, f"alpha_hat={alpha_hat} (expected near 2.5)"
    assert ks < 0.1, f"KS distance too large: {ks}"


def test_rolling_ar1_and_kendall_trend_on_csd_signal():
    """A synthetic series whose AR(1) coefficient ramps from 0.3 to 0.95
    should give a strongly positive Kendall tau on rolling AR(1)."""
    mod = _import_from_path("ct_run", RUN_PY)
    rng = np.random.default_rng(0)
    n = 600
    x = np.zeros(n)
    rho_path = np.linspace(0.3, 0.95, n)
    for i in range(1, n):
        x[i] = rho_path[i] * x[i - 1] + rng.normal(0, 1)
    ar1 = mod.rolling_stat(x, window=60, stat="ar1")
    trend = mod.kendall_trend(ar1)
    assert trend["tau"] is not None
    assert trend["tau"] > 0.3, f"expected strong +tau, got {trend['tau']}"
    assert trend["p"] < 1e-5


def test_deseasonalise_zero_mean_per_month():
    mod = _import_from_path("ct_run", RUN_PY)
    months = np.array(["2020-01", "2020-02", "2020-03", "2020-04",
                       "2020-05", "2020-06", "2020-07", "2020-08",
                       "2020-09", "2020-10", "2020-11", "2020-12",
                       "2021-01", "2021-02", "2021-03", "2021-04",
                       "2021-05", "2021-06", "2021-07", "2021-08",
                       "2021-09", "2021-10", "2021-11", "2021-12"],
                      dtype="datetime64[M]")
    # Synthetic with a clean monthly cycle.
    cycle = np.array([10.0 + 5.0 * np.sin(2 * np.pi * m / 12) for m in range(12)])
    vals = np.concatenate([cycle, cycle])  # two identical years
    anom = mod.deseasonalise(vals, months)
    # Each month's anomaly should be near zero.
    assert np.max(np.abs(anom)) < 1e-9


def test_analyse_system_on_synthetic_inline(tmp_path):
    """Build a temporary JSONL of monthly-aggregable noise + linear AR(1) ramp,
    feed into analyse_system, expect a valid report dict."""
    mod = _import_from_path("ct_run", RUN_PY)
    rng = np.random.default_rng(7)
    # 30 yr of daily samples
    n_days = 30 * 365
    base = np.datetime64("2000-01-01")
    rho_path = np.linspace(0.4, 0.92, n_days)
    x = np.zeros(n_days)
    for i in range(1, n_days):
        x[i] = rho_path[i] * x[i - 1] + rng.normal(0, 0.5)
    p = tmp_path / "syn.jsonl"
    with p.open("w") as f:
        for i, v in enumerate(x):
            d = base + np.timedelta64(i, "D")
            f.write(json.dumps({"date": str(d), "moc_sv": float(v),
                                "synthetic": True}) + "\n")
    rep = mod.analyse_system("synthetic_inline", p, value_key="moc_sv")
    assert rep["ok"], rep.get("reason", "?")
    assert rep["synthetic"] is True
    assert rep["verdict"] == "SYNTHETIC"
    assert rep["ews"]["ar1_trend"]["tau"] is not None
    # The ramping AR(1) should give positive trend.
    assert rep["ews"]["ar1_trend"]["tau"] > 0
