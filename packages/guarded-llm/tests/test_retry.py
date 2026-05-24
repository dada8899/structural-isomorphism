"""Tests for the RetryPolicy primitive."""

from __future__ import annotations

import random

import pytest

from guarded_llm import RetryPolicy, RetryExhausted, GuardrailError


def test_defaults():
    p = RetryPolicy()
    assert p.max_attempts == 3
    assert p.backoff_seconds == 1.0
    assert p.jitter is True


def test_sleep_first_attempt_is_zero():
    p = RetryPolicy(max_attempts=3, backoff_seconds=2.0, jitter=False)
    assert p.sleep_seconds(0) == 0.0


def test_sleep_linear_without_jitter():
    p = RetryPolicy(max_attempts=5, backoff_seconds=1.5, jitter=False)
    assert p.sleep_seconds(1) == pytest.approx(1.5)
    assert p.sleep_seconds(2) == pytest.approx(3.0)
    assert p.sleep_seconds(3) == pytest.approx(4.5)


def test_sleep_with_jitter_in_range():
    p = RetryPolicy(max_attempts=3, backoff_seconds=2.0, jitter=True)
    rng = random.Random(42)
    sleeps = [p.sleep_seconds(2, rng=rng) for _ in range(20)]
    # base = 2 * 2 = 4; jitter in [0.5x, 1.5x] -> [2.0, 6.0]
    for s in sleeps:
        assert 2.0 <= s <= 6.0


def test_init_rejects_invalid_max_attempts():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(TypeError):
        RetryPolicy(max_attempts="three")  # type: ignore[arg-type]


def test_init_rejects_negative_backoff():
    with pytest.raises(ValueError):
        RetryPolicy(backoff_seconds=-1.0)


def test_retry_exhausted_is_guardrail_error():
    """RetryExhausted should be catchable via the broad GuardrailError base."""
    exc = RetryExhausted("all failed", attempts=["e1", "e2"], last_raw="garbage")
    assert isinstance(exc, GuardrailError)
    assert exc.attempts == ["e1", "e2"]
    assert exc.last_raw == "garbage"
