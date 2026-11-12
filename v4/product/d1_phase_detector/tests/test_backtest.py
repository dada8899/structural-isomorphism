"""Unit tests for backtest engine v0.1.

Run:
    python3 -m pytest v4/product/d1_phase_detector/tests/test_backtest.py -v
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.path.normpath(os.path.join(HERE, "..", "backtest.py"))


def _load_backtest_module():
    """Load backtest.py without depending on package init."""
    spec = importlib.util.spec_from_file_location("backtest_v01", MODULE_PATH)
    assert spec and spec.loader, f"cannot load module from {MODULE_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["backtest_v01"] = mod
    spec.loader.exec_module(mod)
    return mod


bt = _load_backtest_module()


def _flat_series(start_price: float, months: int, monthly_ret: float, anchor: dt.date):
    """Build a deterministic monthly series with constant monthly return."""
    out = []
    price = start_price
    cur = anchor
    for _ in range(months + 1):
        out.append((cur, round(price, 4)))
        price *= 1.0 + monthly_ret
        cur = bt.add_months(cur, 1)
    return out


def _make_universe():
    """Synthetic universe where near_critical has +2% monthly drift, other 0%."""
    snapshot = dt.date(2024, 1, 31)
    companies = [
        bt.CompanyRow("NC1", "approaching_critical"),
        bt.CompanyRow("NC2", "approaching_critical"),
        bt.CompanyRow("NC3", "at_critical"),
        bt.CompanyRow("OT1", "far_from_critical"),
        bt.CompanyRow("OT2", "far_from_critical"),
        bt.CompanyRow("OT3", "post_critical_transition"),
        bt.CompanyRow("SK", None),  # dropped
    ]
    prices = {
        "NC1": _flat_series(100.0, 12, 0.02, snapshot),
        "NC2": _flat_series(100.0, 12, 0.022, snapshot),
        "NC3": _flat_series(100.0, 12, 0.025, snapshot),
        "OT1": _flat_series(100.0, 12, 0.000, snapshot),
        "OT2": _flat_series(100.0, 12, 0.001, snapshot),
        "OT3": _flat_series(100.0, 12, -0.001, snapshot),
    }
    return companies, prices, snapshot


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_company_row_group_classification():
    assert bt.CompanyRow("X", "approaching_critical").group == "near_critical"
    assert bt.CompanyRow("X", "at_critical").group == "near_critical"
    assert bt.CompanyRow("X", "far_from_critical").group == "other"
    assert bt.CompanyRow("X", "post_critical_transition").group == "other"
    assert bt.CompanyRow("X", None).group is None
    assert bt.CompanyRow("X", "unknown").group is None


def test_add_months_basic():
    assert bt.add_months(dt.date(2024, 1, 31), 6) == dt.date(2024, 7, 31)
    # Feb clamping
    assert bt.add_months(dt.date(2024, 1, 31), 1) == dt.date(2024, 2, 29)
    assert bt.add_months(dt.date(2023, 1, 31), 1) == dt.date(2023, 2, 28)


def test_parse_period():
    assert bt.parse_period("6m") == 6
    assert bt.parse_period("12m") == 12
    assert bt.parse_period("3") == 3


def test_compute_group_returns():
    companies, prices, snapshot = _make_universe()
    grouped, used = bt.compute_group_returns(companies, prices, snapshot, months=6)

    assert len(grouped["near_critical"]) == 3
    assert len(grouped["other"]) == 3
    assert "SK" not in used["near_critical"] and "SK" not in used["other"]

    # near_critical ~ (1.02^6 - 1) ≈ 0.126; other ~ 0
    nc_mean = sum(grouped["near_critical"]) / 3
    oth_mean = sum(grouped["other"]) / 3
    assert nc_mean > 0.10, f"near_critical mean too low: {nc_mean}"
    assert abs(oth_mean) < 0.02, f"other mean too high: {oth_mean}"


def test_ttest_significance():
    companies, prices, snapshot = _make_universe()
    grouped, _ = bt.compute_group_returns(companies, prices, snapshot, months=6)
    t, p = bt.ttest_groups(grouped["near_critical"], grouped["other"])
    assert not math.isnan(t)
    assert not math.isnan(p)
    # With ~12% vs ~0% mean and very low variance, t should be very large and p tiny
    assert t > 5, f"expected huge t-stat for fixture, got {t}"
    assert p < 0.01, f"expected significant p, got {p}"


def test_ttest_small_sample_returns_nan():
    t, p = bt.ttest_groups([0.1], [0.0])
    assert math.isnan(t) and math.isnan(p)


def test_summarize_empty_and_nonempty():
    empty = bt.summarize([], 6)
    assert empty["n"] == 0 and math.isnan(empty["mean"])

    summ = bt.summarize([0.1, 0.2, 0.15, 0.05], 6)
    assert summ["n"] == 4
    assert 0.08 < summ["mean"] < 0.14
    assert summ["std"] > 0
    # sharpe should be real
    assert not math.isnan(summ["sharpe"])


def test_cumulative_curve_length():
    companies, prices, snapshot = _make_universe()
    rows = bt.build_cumulative_curve(companies, prices, snapshot, months=6)
    assert len(rows) >= 6, f"expected >=6 cumulative points, got {len(rows)}"
    # First point should be near zero (anchor day)
    first_nc = rows[0][1]
    first_oth = rows[0][2]
    assert abs(first_nc) < 0.01, f"first nc cumret not ~0: {first_nc}"
    assert abs(first_oth) < 0.01, f"first oth cumret not ~0: {first_oth}"
    # Last point: near_critical should be > other
    last_nc = rows[-1][1]
    last_oth = rows[-1][2]
    assert last_nc > last_oth, f"expected nc cumret > oth cumret, got {last_nc} vs {last_oth}"


def test_dry_run_main_writes_artifacts(tmp_path):
    result_path = tmp_path / "result.json"
    cum_path = tmp_path / "cum.csv"
    rc = bt.main([
        "--dry-run",
        "--snapshot", "2024-01-31",
        "--period", "6m",
        "--result", str(result_path),
        "--cumulative", str(cum_path),
    ])
    assert rc == 0
    assert result_path.exists() and result_path.stat().st_size > 0
    assert cum_path.exists() and cum_path.stat().st_size > 0

    import json
    payload = json.loads(result_path.read_text())
    assert payload["version"] == "0.1"
    assert payload["synthetic"] is True
    assert payload["groups"]["near_critical"]["n"] > 0
    assert payload["groups"]["other"]["n"] > 0
