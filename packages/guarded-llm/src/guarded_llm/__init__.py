"""guarded-llm — strict JSON output with multi-provider support.

Quickstart::

    from guarded_llm import guardrailed_llm_call, LLMSchema

    schema = LLMSchema({
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["KEEP", "REJECT"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["verdict", "confidence"],
    })

    result = guardrailed_llm_call(
        provider="deepseek",
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Is gravity a SOC system?"}],
        schema=schema,
        max_retries=3,
        budget_cap_usd=0.05,
    )
    if result.ok:
        print(result.parsed)
"""

from __future__ import annotations

__version__ = "0.1.0"

from .guardrail import (
    guardrailed_llm_call,
    GuardrailResult,
    state_machine_fix,
    validate_json,
)
from .schemas import (
    LLMSchema,
    validate_response,
    # Legacy dataclass schemas (kept for v4 backwards compat)
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
    # Core
    "guardrailed_llm_call",
    "GuardrailResult",
    "state_machine_fix",
    "validate_json",
    # Schemas
    "LLMSchema",
    "validate_response",
    "Layer3CriticVerdict",
    "Layer4Prediction",
    "B3EnsembleReview",
    # Providers
    "BaseProvider",
    "get_provider",
    "list_providers",
    "register_provider",
    # Exceptions
    "GuardrailError",
    "SchemaValidationError",
    "LLMCallError",
    "BudgetExceededError",
]
