"""Tests for the v0.2 walk-forward backtest pipeline — W7-D (2026-05-25).

Three scenarios:
  1. unit/sanity — math helpers (Sharpe, max DD, cum return, CAPM)
  2. schema — required fields exist in JSON output
  3. end-to-end smoke — runs against bundled parquet if present, OR
     synthesises a tiny parquet on tmp_path so the test never depends
     on yfinance network availability

Run:
    cd /Users/dadamini/Projects/structural-isomorphism
    .venv/bin/python3 -m pytest tests/test_backtest_walk_forward_v0_2.py -v
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_parquet_engine_matches_root_backtest_extra() -> None:
    assert importlib.metadata.version("pyarrow") == "24.0.0"


@pytest.fixture(scope="module")
def bt_mod():
    spec = importlib.util.spec_from_file_location(
        "backtest_walk_forward_v0_2",
        str(REPO_ROOT / "scripts" / "backtest_walk_forward_v0_2.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["backtest_walk_forward_v0_2"] = mod
    spec.loader.exec_module(mod)
    return mod


# ----------------- unit / math sanity -----------------

def test_annualized_sharpe_zero_vol(bt_mod):
    """Zero-volatility returns → Sharpe 0 (not NaN, not inf)."""
    rets = np.array([0.01, 0.01, 0.01, 0.01])
    s = bt_mod.annualized_sharpe(rets)
    assert s == 0.0


def test_annualized_sharpe_positive(bt_mod):
    """Constant positive drift + small noise → positive Sharpe in reasonable range."""
    rng = np.random.default_rng(7)
    rets = 0.01 + 0.02 * rng.standard_normal(60)
    s = bt_mod.annualized_sharpe(rets)
    # Per W7-D §3 sanity: any reasonable monthly Sharpe must lie in [-2, 5]
    assert -2.0 <= s <= 5.0
    assert s > 0  # positive drift → positive Sharpe expected


def test_max_drawdown_monotone_up(bt_mod):
    """All-positive returns → drawdown 0."""
    rets = np.array([0.01, 0.02, 0.01, 0.03])
    assert bt_mod.max_drawdown(rets) == 0.0


def test_max_drawdown_crash(bt_mod):
    """50% crash → -0.5 drawdown."""
    rets = np.array([-0.5, 0.0])
    dd = bt_mod.max_drawdown(rets)
    assert abs(dd - (-0.5)) < 1e-9


def test_cum_return_compounding(bt_mod):
    """(1+0.1)(1+0.1) − 1 = 0.21."""
    rets = np.array([0.1, 0.1])
    c = bt_mod.cum_return(rets)
    assert abs(c - 0.21) < 1e-9


def test_capm_alpha_zero_beta_one(bt_mod):
    """If cohort = SPY identically, alpha=0, beta=1, R²=1, t≈0."""
    rng = np.random.default_rng(42)
    spy = 0.01 + 0.03 * rng.standard_normal(60)
    cohort = spy.copy()
    capm = bt_mod.capm_alpha_tstat(cohort, spy)
    assert abs(capm["beta"] - 1.0) < 1e-9
    assert abs(capm["alpha_monthly"]) < 1e-9
    assert capm["r_squared"] > 0.999


def test_capm_alpha_positive_intercept(bt_mod):
    """cohort = spy + 0.01/month → alpha ≈ 0.01, beta ≈ 1, alpha t-stat large."""
    rng = np.random.default_rng(13)
    spy = 0.01 + 0.03 * rng.standard_normal(120)
    cohort = spy + 0.01  # +1% per month constant alpha
    capm = bt_mod.capm_alpha_tstat(cohort, spy)
    assert abs(capm["alpha_monthly"] - 0.01) < 1e-6
    assert abs(capm["beta"] - 1.0) < 1e-6
    # Perfectly clean alpha with zero residual → t-stat is inf, but our SE has
    # numerical floor, so just assert it's a finite or very large number, and
    # certainly > 5 (statistically significant).
    assert capm["alpha_tstat"] > 5.0 or not np.isfinite(capm["alpha_tstat"])


def test_honest_verdict_buckets(bt_mod):
    """Verdict gate matches W7-D §3 thresholds."""
    assert bt_mod.honest_verdict(0.6)["bucket"] == "alpha_confirmed"
    assert bt_mod.honest_verdict(0.5)["bucket"] == "alpha_confirmed"
    assert bt_mod.honest_verdict(0.4)["bucket"] == "inconclusive"
    assert bt_mod.honest_verdict(0.3)["bucket"] == "inconclusive"
    assert bt_mod.honest_verdict(0.29)["bucket"] == "alpha_not_confirmed"
    assert bt_mod.honest_verdict(-0.5)["bucket"] == "alpha_not_confirmed"


def test_cohort_extraction(bt_mod):
    """approaching_critical + at_critical → near_critical; others excluded."""
    recs = [
        {"ticker": "A", "critical_point_state": "approaching_critical"},
        {"ticker": "B", "critical_point_state": "at_critical"},
        {"ticker": "C", "critical_point_state": "far_from_critical"},
        {"ticker": "D", "critical_point_state": "post_critical_transition"},
        {"ticker": "E", "critical_point_state": None},
    ]
    cohort = bt_mod.cohort_from_classification(recs)
    assert cohort == ["A", "B"]


# ----------------- smoke / e2e against synthetic tiny parquet -----------------

def _build_tiny_parquet(tmp_path: Path) -> tuple[Path, Path]:
    """Make a 24-month parquet with SPY + 6 tickers, deterministic."""
    rng = np.random.default_rng(2026)
    dates = pd.date_range("2020-01-01", periods=24, freq="MS")
    universe = ["SPY", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    rows = []
    for t in universe:
        p = 100.0
        mu = 0.006 if t == "SPY" else 0.005
        sigma = 0.03 if t == "SPY" else 0.06
        for d in dates:
            r = mu + sigma * rng.standard_normal()
            p *= (1.0 + r)
            rows.append({"date": d, "ticker": t, "close": round(p, 4)})
    df = pd.DataFrame(rows)
    parquet_path = tmp_path / "tiny.parquet"
    df.to_parquet(parquet_path, index=False)
    meta_path = tmp_path / "tiny.meta.json"
    meta_path.write_text(json.dumps({
        "version": "test",
        "status": "REAL",
        "n_top100_hits": 6,
        "failed": [],
        "spy_ok": True,
    }, indent=2), encoding="utf-8")
    return parquet_path, meta_path


def _build_tiny_classification(tmp_path: Path) -> tuple[Path, Path]:
    """top100-like + classification jsonl with 6 tickers, 2 near_critical."""
    top100 = [
        {"ticker": "AAA", "sector": "tech", "market_cap_bn_usd": 100},
        {"ticker": "BBB", "sector": "tech", "market_cap_bn_usd": 90},
        {"ticker": "CCC", "sector": "energy", "market_cap_bn_usd": 80},
        {"ticker": "DDD", "sector": "energy", "market_cap_bn_usd": 70},
        {"ticker": "EEE", "sector": "biotech", "market_cap_bn_usd": 60},
        {"ticker": "FFF", "sector": "biotech", "market_cap_bn_usd": 50},
    ]
    top100_path = tmp_path / "top100.jsonl"
    with top100_path.open("w") as fh:
        for r in top100:
            fh.write(json.dumps(r) + "\n")

    classified = [
        {"ticker": "AAA", "struct_tuple": {
            "ticker": "AAA", "critical_point_state": "approaching_critical",
            "dynamics_family": "scheffer_fold", "confidence": 0.8,
        }},
        {"ticker": "BBB", "struct_tuple": {
            "ticker": "BBB", "critical_point_state": "far_from_critical",
            "dynamics_family": "linear_quasi_equilibrium", "confidence": 0.9,
        }},
        {"ticker": "CCC", "struct_tuple": {
            "ticker": "CCC", "critical_point_state": "at_critical",
            "dynamics_family": "scheffer_fold", "confidence": 0.6,
        }},
        {"ticker": "DDD", "struct_tuple": {
            "ticker": "DDD", "critical_point_state": "post_critical_transition",
            "dynamics_family": "linear_quasi_equilibrium", "confidence": 0.7,
        }},
        {"ticker": "EEE", "struct_tuple": {
            "ticker": "EEE", "critical_point_state": "far_from_critical",
            "dynamics_family": "preferential_attachment", "confidence": 0.85,
        }},
        {"ticker": "FFF", "struct_tuple": {
            "ticker": "FFF", "critical_point_state": "far_from_critical",
            "dynamics_family": "preferential_attachment", "confidence": 0.85,
        }},
    ]
    classified_path = tmp_path / "classified.jsonl"
    with classified_path.open("w") as fh:
        for r in classified:
            fh.write(json.dumps(r) + "\n")
    return top100_path, classified_path


def test_pipeline_smoke_synthetic(tmp_path, bt_mod):
    """End-to-end on synthetic 24-month parquet — never needs network."""
    parquet_path, _meta_path = _build_tiny_parquet(tmp_path)
    top100_path, classified_path = _build_tiny_classification(tmp_path)
    out_dir = tmp_path / "results"

    rc = bt_mod.main([
        "--prices", str(parquet_path),
        "--top100", str(top100_path),
        "--classified", str(classified_path),
        "--out-dir", str(out_dir),
        "--start", "2020-01-01",
        "--end", "2021-12-31",
        "--prefix", "smoke-v0.2",
    ])
    assert rc == 0

    # Output files
    json_path = out_dir / "smoke-v0.2.json"
    md_path = out_dir / "smoke-v0.2.md"
    cumret_path = out_dir / "smoke-v0.2-cumret.png"
    dd_path = out_dir / "smoke-v0.2-drawdown.png"
    tov_path = out_dir / "smoke-v0.2-turnover.png"
    assert json_path.exists()
    assert md_path.exists()
    assert cumret_path.exists() and cumret_path.stat().st_size > 1000
    assert dd_path.exists() and dd_path.stat().st_size > 1000
    assert tov_path.exists() and tov_path.stat().st_size > 1000


def test_pipeline_schema(tmp_path, bt_mod):
    """JSON output has all required keys and sane shapes."""
    parquet_path, _ = _build_tiny_parquet(tmp_path)
    top100_path, classified_path = _build_tiny_classification(tmp_path)
    out_dir = tmp_path / "results"

    bt_mod.main([
        "--prices", str(parquet_path),
        "--top100", str(top100_path),
        "--classified", str(classified_path),
        "--out-dir", str(out_dir),
        "--start", "2020-01-01",
        "--end", "2021-12-31",
        "--prefix", "schema-v0.2",
    ])
    d = json.loads((out_dir / "schema-v0.2.json").read_text())

    assert set(d.keys()) >= {"meta", "cohort", "rebalances", "summary", "verdict", "chart_paths"}
    assert d["meta"]["version"] == "v0.2"
    assert d["meta"]["data_source_prices"] in {"REAL", "PARTIAL_REAL", "FETCH_FAILED", "UNKNOWN"}
    assert d["meta"]["data_source_classification"] in {"REAL", "PARTIAL_REAL", "FALLBACK_NEUTRAL"}
    assert isinstance(d["meta"]["honest_caveats"], list) and len(d["meta"]["honest_caveats"]) >= 3

    summary_required = {
        "n_rebalances", "cohort_size",
        "cohort_cum_return", "spy_cum_return",
        "cohort_sharpe", "spy_sharpe", "sharpe_lift",
        "cohort_max_drawdown", "spy_max_drawdown",
        "avg_turnover", "max_turnover", "capm",
    }
    assert summary_required.issubset(d["summary"].keys())

    capm_required = {"alpha_monthly", "alpha_annual", "beta", "alpha_tstat",
                     "r_squared", "n_obs"}
    assert capm_required.issubset(d["summary"]["capm"].keys())

    # Cohort = AAA + CCC from the fixture
    assert set(d["cohort"]["tickers"]) == {"AAA", "CCC"}
    assert d["cohort"]["size"] == 2
    assert d["verdict"]["bucket"] in {"alpha_confirmed", "inconclusive", "alpha_not_confirmed"}

    # 24 months, first dropped to compute MoM returns → 23 rebalances
    assert len(d["rebalances"]) == 23


def test_pipeline_sanity_bounds(tmp_path, bt_mod):
    """Sharpe / max DD / cum return must lie in plausible ranges."""
    parquet_path, _ = _build_tiny_parquet(tmp_path)
    top100_path, classified_path = _build_tiny_classification(tmp_path)
    out_dir = tmp_path / "results"

    bt_mod.main([
        "--prices", str(parquet_path),
        "--top100", str(top100_path),
        "--classified", str(classified_path),
        "--out-dir", str(out_dir),
        "--start", "2020-01-01",
        "--end", "2021-12-31",
        "--prefix", "sanity-v0.2",
    ])
    d = json.loads((out_dir / "sanity-v0.2.json").read_text())
    s = d["summary"]

    # W7-D §3 sanity gates
    assert -2.0 <= s["cohort_sharpe"] <= 5.0
    assert -2.0 <= s["spy_sharpe"] <= 5.0
    assert -1.0 <= s["cohort_max_drawdown"] <= 0.0
    assert -1.0 <= s["spy_max_drawdown"] <= 0.0
    assert 0.0 <= s["avg_turnover"] <= 1.0
    assert 0.0 <= s["max_turnover"] <= 1.0
    # Cumulative return over ~2 years for a long-only equity strategy: plausibly [-90%, +500%]
    assert -0.9 <= s["cohort_cum_return"] <= 5.0
    assert -0.9 <= s["spy_cum_return"] <= 5.0


@pytest.mark.requires_internet
def test_pipeline_real_data_if_present(bt_mod):
    """If the real-data parquet exists locally, ensure it loads and runs.

    Marked requires_internet because fetching it requires yfinance, but
    we skip without it rather than failing.
    """
    real_parquet = REPO_ROOT / "backtest" / "data" / "sp500-top100-2020-2024.parquet"
    if not real_parquet.exists():
        pytest.skip("real-data parquet not available; run scripts/backtest_fetch_data_v0_2.py")

    # Just verify it parses + loads (no main() call to avoid clobbering results/)
    prices_long, meta = bt_mod.load_prices(real_parquet)
    assert {"date", "ticker", "close"}.issubset(prices_long.columns)
    assert "SPY" in prices_long["ticker"].unique()
    assert meta.get("status") in {"REAL", "PARTIAL_REAL"}
    # Should have ~60 monthly bars × ~100 tickers = ~6000 rows
    assert len(prices_long) > 3000
