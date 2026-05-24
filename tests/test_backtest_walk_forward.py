"""Tests for the walk-forward backtest pipeline — W7-D mini-brief 4 (2026-05-24).

Two scenarios:
  1. pipeline end-to-end with mock data writes both JSON + MD outputs and
     reports plausible summary stats
  2. edge case: month_starts inclusive bounds + empty-cohort handling

Run:
    cd /Users/dadamini/Projects/structural-isomorphism
    .venv/bin/python3 -m pytest tests/test_backtest_walk_forward.py -v
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def bt_mod():
    spec = importlib.util.spec_from_file_location(
        "backtest_walk_forward",
        str(REPO_ROOT / "scripts" / "backtest_walk_forward.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["backtest_walk_forward"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_pipeline_end_to_end_with_mock(tmp_path, bt_mod):
    """Pipeline writes JSON + MD with sensible shape."""
    rc = bt_mod.main([
        "--mock",
        "--start", "2020-01-01",
        "--end", "2022-12-31",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0

    json_path = tmp_path / "walk-forward-v0.1.json"
    md_path = tmp_path / "walk-forward-v0.1.md"
    assert json_path.exists()
    assert md_path.exists()

    result = json.loads(json_path.read_text(encoding="utf-8"))
    assert "rebalances" in result
    assert "summary" in result
    assert "meta" in result

    ***REMOVED*** 3 years × 12 months − 1 (we need d2 = next month) = 35 rebalances
    assert result["summary"]["n_rebalances"] == 35

    ***REMOVED*** Sharpe values are finite numbers
    s = result["summary"]
    for key in ("cohort_sharpe", "spy_sharpe", "sharpe_lift",
                "cohort_cum_return", "spy_cum_return",
                "cohort_max_drawdown", "spy_max_drawdown"):
        v = s[key]
        assert isinstance(v, (int, float))
        assert v == v  ***REMOVED*** NaN check (NaN != NaN)

    ***REMOVED*** Avg turnover is in [0, 1]
    assert 0.0 <= s["avg_turnover"] <= 1.0

    ***REMOVED*** Meta carries data_source label
    assert result["meta"]["data_source"] == "mock"
    assert result["meta"]["version"] == "v0.1"

    ***REMOVED*** Markdown reports the mock honesty banner
    md = md_path.read_text(encoding="utf-8")
    assert "MOCK data" in md
    assert "v0.1" in md


def test_edge_cases(bt_mod):
    """month_starts: inclusive; cohort_for_month: missing month is empty;
    monthly_return: zero-divide guarded."""
    ***REMOVED*** month_starts inclusive on both ends
    months = bt_mod.month_starts(dt.date(2020, 1, 1), dt.date(2020, 4, 1))
    assert months == [
        dt.date(2020, 1, 1), dt.date(2020, 2, 1),
        dt.date(2020, 3, 1), dt.date(2020, 4, 1),
    ]

    ***REMOVED*** Single-month range
    months1 = bt_mod.month_starts(dt.date(2021, 6, 1), dt.date(2021, 6, 1))
    assert months1 == [dt.date(2021, 6, 1)]

    ***REMOVED*** cohort_for_month with missing key returns empty
    cos = [{"ticker": "X", "phases": {"2020-01": "stable"}}]
    assert bt_mod.cohort_for_month(cos, "2020-02") == []
    assert bt_mod.cohort_for_month(cos, "2020-01") == []  ***REMOVED*** not near_critical

    ***REMOVED*** near_critical hit
    cos2 = [{"ticker": "Y", "phases": {"2020-01": "near_critical"}}]
    assert bt_mod.cohort_for_month(cos2, "2020-01") == ["Y"]

    ***REMOVED*** monthly_return: zero-divide returns None
    prices = {"2020-01-01": 0.0, "2020-02-01": 100.0}
    assert bt_mod.monthly_return(prices, dt.date(2020, 1, 1), dt.date(2020, 2, 1)) is None
    ***REMOVED*** Missing date → None
    assert bt_mod.monthly_return(prices, dt.date(2020, 3, 1), dt.date(2020, 4, 1)) is None
    ***REMOVED*** Happy path
    prices2 = {"2020-01-01": 100.0, "2020-02-01": 110.0}
    r = bt_mod.monthly_return(prices2, dt.date(2020, 1, 1), dt.date(2020, 2, 1))
    assert r is not None and abs(r - 0.10) < 1e-9
