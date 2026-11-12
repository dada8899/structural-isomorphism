"""Tests for the Budget cost-cap primitive."""

from __future__ import annotations

import math

import pytest

from guarded_llm import Budget, BudgetExceeded


def test_basic_consume_under_caps():
    b = Budget(usd_total=1.0, usd_per_call=0.5)
    b.consume(0.1)
    b.consume(0.2)
    assert b.spent_usd == pytest.approx(0.3)
    assert b.remaining_usd == pytest.approx(0.7)


def test_per_call_cap_blocks_single_oversized_charge():
    b = Budget(usd_total=10.0, usd_per_call=0.05)
    with pytest.raises(BudgetExceeded) as exc:
        b.consume(0.10)
    assert "per-call cap" in str(exc.value)
    assert b.spent_usd == 0.0  # state not mutated on rejection


def test_total_cap_blocks_when_cumulative_exceeds():
    b = Budget(usd_total=0.30, usd_per_call=1.0)
    b.consume(0.15)
    b.consume(0.10)
    with pytest.raises(BudgetExceeded) as exc:
        b.consume(0.10)
    assert "total cap" in str(exc.value)
    assert b.spent_usd == pytest.approx(0.25)  # state unchanged


def test_default_per_call_cap_is_infinite():
    b = Budget(usd_total=100.0)
    assert math.isinf(b.usd_per_call)
    b.consume(50.0)  # would have failed if there were a finite per-call cap


def test_reset_clears_spend():
    b = Budget(usd_total=1.0)
    b.consume(0.5)
    b.reset()
    assert b.spent_usd == 0.0
    assert b.remaining_usd == pytest.approx(1.0)


def test_rejects_negative_charge():
    b = Budget(usd_total=1.0)
    with pytest.raises(ValueError):
        b.consume(-0.01)


def test_rejects_non_numeric_charge():
    b = Budget(usd_total=1.0)
    with pytest.raises(TypeError):
        b.consume("free")  # type: ignore[arg-type]


def test_rejects_bool_charge():
    """bool is a subclass of int; we still want to reject it for type clarity."""
    b = Budget(usd_total=1.0)
    with pytest.raises(TypeError):
        b.consume(True)  # type: ignore[arg-type]


def test_init_validation():
    with pytest.raises(ValueError):
        Budget(usd_total=-0.5)
    with pytest.raises(ValueError):
        Budget(usd_total=1.0, usd_per_call=-0.5)
    with pytest.raises(TypeError):
        Budget(usd_total="cheap")  # type: ignore[arg-type]


def test_remaining_never_negative_after_partial_state():
    """If somebody manually pokes spent_usd over usd_total, remaining stays >= 0."""
    b = Budget(usd_total=1.0)
    b.spent_usd = 1.5  # simulate manual override
    assert b.remaining_usd == 0.0
