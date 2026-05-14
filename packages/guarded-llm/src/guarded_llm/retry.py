"""Retry policy for guarded-llm.

Bring-your-own backoff knobs without dragging in tenacity at runtime. (We do
list tenacity as an optional/recommended dep in pyproject.toml for users who
prefer tenacity for richer policies, but the built-in RetryPolicy is enough
for the LLM-call use case.)

Public types::

    RetryPolicy(max_attempts=3, backoff_seconds=1.0, jitter=True)
        .sleep_seconds(attempt: int, rng: random.Random | None) -> float

    RetryExhausted               # raised when max_attempts is exhausted

`RetryExhausted` is exposed as a subclass of the existing
`SchemaValidationError` so existing callers that catch `GuardrailError` keep
working, while new callers can `except RetryExhausted` for clarity.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .exceptions import SchemaValidationError


class RetryExhausted(SchemaValidationError):
    """Raised when all retry attempts fail.

    Carries the per-attempt error list and the final raw LLM output so callers
    can inspect what went wrong without re-running the loop.
    """


@dataclass
class RetryPolicy:
    """Backoff configuration for retry loops.

    Args:
        max_attempts: total number of LLM calls to make before giving up (>= 1).
        backoff_seconds: base sleep between attempts (linear * attempt#).
        jitter: if True, multiply sleep by uniform(0.5, 1.5) to avoid
            thundering-herd retry storms when many parallel clients share a
            single backend.

    Example::

        policy = RetryPolicy(max_attempts=5, backoff_seconds=2.0)
        for attempt in range(policy.max_attempts):
            try:
                return _try_call()
            except RetryableError:
                time.sleep(policy.sleep_seconds(attempt))
        raise RetryExhausted("...")
    """

    max_attempts: int = 3
    backoff_seconds: float = 1.0
    jitter: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool):
            raise TypeError("max_attempts must be an int")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if not isinstance(self.backoff_seconds, (int, float)) or isinstance(
            self.backoff_seconds, bool
        ):
            raise TypeError("backoff_seconds must be a number")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be >= 0")

    def sleep_seconds(self, attempt: int, rng: random.Random | None = None) -> float:
        """Compute backoff for the given attempt number (0-indexed).

        Linear: attempt 0 → 0 sec (don't sleep before first call),
                attempt N → N * backoff_seconds (* jitter, if enabled).
        """
        if attempt <= 0:
            return 0.0
        base = attempt * self.backoff_seconds
        if not self.jitter:
            return base
        r = rng if rng is not None else random
        return base * r.uniform(0.5, 1.5)


__all__ = ["RetryPolicy", "RetryExhausted"]
