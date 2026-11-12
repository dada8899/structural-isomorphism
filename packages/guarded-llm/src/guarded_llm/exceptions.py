"""Exception hierarchy for guarded-llm.

All errors raised by this package inherit from `GuardrailError`, so callers
can catch the broad case (`except GuardrailError`) or branch on specific
subclasses.
"""

from __future__ import annotations


class GuardrailError(Exception):
    """Base class for all guarded-llm errors."""


class SchemaValidationError(GuardrailError):
    """Raised when LLM output fails schema validation after all retries.

    Attributes:
        attempts: list of per-attempt error strings (length == max_retries)
        last_raw: the raw LLM text from the final attempt (may aid debugging)
    """

    def __init__(self, message: str, attempts: list[str] | None = None, last_raw: str | None = None):
        super().__init__(message)
        self.attempts = attempts or []
        self.last_raw = last_raw


class LLMCallError(GuardrailError):
    """Raised when the underlying LLM HTTP/SDK call fails (network, auth, etc.)."""


class BudgetExceededError(GuardrailError):
    """Raised when cumulative cost in a single call exceeds the user-supplied cap."""

    def __init__(self, message: str, spent_usd: float, cap_usd: float):
        super().__init__(message)
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd


__all__ = [
    "GuardrailError",
    "SchemaValidationError",
    "LLMCallError",
    "BudgetExceededError",
]
