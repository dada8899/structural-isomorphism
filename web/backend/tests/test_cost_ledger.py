"""Tests for the daily LLM cost ledger — launch P0-2.

The ledger is the circuit breaker that finally makes `errors.BudgetExceeded`
fire: before this, the exception class existed but was never raised, so an
anonymous user could burn the LLM budget unbounded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from errors import BudgetExceeded  ***REMOVED*** noqa: E402
from services.cost_ledger import _DailyCallLedger  ***REMOVED*** noqa: E402


@pytest.fixture
def ledger():
    """Fresh isolated ledger per test."""
    return _DailyCallLedger()


def test_under_cap_charges_succeed(ledger, monkeypatch):
    monkeypatch.setenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "5")
    ***REMOVED*** 5 charges allowed (count 0..4 < cap).
    for _ in range(5):
        ledger.charge(endpoint="/api/ask/stream")
    snap = ledger.snapshot()
    assert snap["used"] == 5
    assert snap["remaining"] == 0


def test_charge_over_cap_raises_budget_exceeded(ledger, monkeypatch):
    monkeypatch.setenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "3")
    for _ in range(3):
        ledger.charge()
    ***REMOVED*** 4th charge is over cap.
    with pytest.raises(BudgetExceeded) as ei:
        ledger.charge(endpoint="/api/analyze/stream")
    ***REMOVED*** BudgetExceeded is an RFC 7807 ProblemDetail — status 429, friendly.
    assert ei.value.status == 429
    assert "tomorrow" in ei.value.detail.lower()


def test_budget_exceeded_does_not_increment_count(ledger, monkeypatch):
    """A rejected (over-budget) charge must NOT consume a slot — otherwise
    the counter would drift upward forever on every blocked request."""
    monkeypatch.setenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "2")
    ledger.charge()
    ledger.charge()
    for _ in range(3):
        with pytest.raises(BudgetExceeded):
            ledger.charge()
    assert ledger.snapshot()["used"] == 2


def test_cap_zero_disables_breaker(ledger, monkeypatch):
    """cap <= 0 means unlimited — charges never raise."""
    monkeypatch.setenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "0")
    for _ in range(50):
        ledger.charge()  ***REMOVED*** must not raise
    snap = ledger.snapshot()
    assert snap["used"] == 50
    assert snap["remaining"] is None


def test_default_cap_when_env_missing(ledger, monkeypatch):
    monkeypatch.delenv("STRUCTURAL_LLM_DAILY_CALL_CAP", raising=False)
    snap = ledger.snapshot()
    assert snap["cap"] == 500  ***REMOVED*** _DEFAULT_DAILY_CALL_CAP


def test_bad_env_falls_back_to_default(ledger, monkeypatch):
    monkeypatch.setenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "not-a-number")
    assert ledger.snapshot()["cap"] == 500


def test_new_utc_day_resets_counter(ledger, monkeypatch):
    """When the UTC date rolls over, the counter resets to 0."""
    monkeypatch.setenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "2")
    ledger.charge()
    ledger.charge()
    with pytest.raises(BudgetExceeded):
        ledger.charge()
    ***REMOVED*** Simulate a day boundary by rewinding the ledger's stored date.
    ledger._date = "2000-01-01"
    ***REMOVED*** Next charge sees a new day → counter rolls → succeeds.
    ledger.charge()
    assert ledger.snapshot()["used"] == 1


def test_reset_clears_counter(ledger, monkeypatch):
    monkeypatch.setenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "10")
    ledger.charge()
    ledger.charge()
    ledger.reset()
    assert ledger.snapshot()["used"] == 0
