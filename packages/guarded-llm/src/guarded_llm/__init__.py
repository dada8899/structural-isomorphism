"""guarded-llm — strict JSON output with multi-provider support.

Two interchangeable entry points:

**High-level (recommended)** — class-based, reusable::

    from pydantic import BaseModel
    from guarded_llm import GuardedLLM, Budget, RetryPolicy

    class Verdict(BaseModel):
        verdict: str
        confidence: float

    llm = GuardedLLM(
        provider="deepseek",
        model="deepseek-v4-flash",
        schema=Verdict,
        budget=Budget(usd_total=0.50, usd_per_call=0.05),
        retry=RetryPolicy(max_attempts=3, backoff_seconds=1.0),
    )
    out = llm.call("Is gravity a self-organized criticality system?")
    print(out.verdict, out.confidence)

**Low-level (functional)** — original V4 API, kept for backwards compat::

    from guarded_llm import guardrailed_llm_call, LLMSchema

    schema = LLMSchema({
        "type": "object",
        "properties": {"verdict": {"type": "string"}},
        "required": ["verdict"],
    })
    result = guardrailed_llm_call(
        provider="deepseek",
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "..."}],
        schema=schema,
        budget_cap_usd=0.05,
    )
"""

from __future__ import annotations

__version__ = "0.1.0"

***REMOVED*** High-level API
from .core import GuardedLLM, GuardedCallStats
from .budget import Budget, BudgetExceeded
from .retry import RetryPolicy, RetryExhausted
from .validator import SchemaValidator

***REMOVED*** Functional / legacy API
from .guardrail import (
    guardrailed_llm_call,
    GuardrailResult,
    state_machine_fix,
    validate_json,
)
from .schemas import (
    LLMSchema,
    validate_response,
    ***REMOVED*** Legacy dataclass schemas (kept for v4 backwards compat)
    Layer3CriticVerdict,
    Layer4Prediction,
    B3EnsembleReview,
)
from .providers import (
    BaseProvider,
    get_provider,
    list_providers,
    register_provider,
)
from .exceptions import (
    GuardrailError,
    SchemaValidationError,
    LLMCallError,
    BudgetExceededError,
)

__all__ = [
    "__version__",
    ***REMOVED*** High-level class API
    "GuardedLLM",
    "GuardedCallStats",
    "Budget",
    "BudgetExceeded",
    "RetryPolicy",
    "RetryExhausted",
    "SchemaValidator",
    ***REMOVED*** Functional / legacy
    "guardrailed_llm_call",
    "GuardrailResult",
    "state_machine_fix",
    "validate_json",
    ***REMOVED*** Schemas
    "LLMSchema",
    "validate_response",
    "Layer3CriticVerdict",
    "Layer4Prediction",
    "B3EnsembleReview",
    ***REMOVED*** Providers
    "BaseProvider",
    "get_provider",
    "list_providers",
    "register_provider",
    ***REMOVED*** Exceptions
    "GuardrailError",
    "SchemaValidationError",
    "LLMCallError",
    "BudgetExceededError",
]
