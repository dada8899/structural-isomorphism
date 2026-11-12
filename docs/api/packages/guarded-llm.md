# guarded-llm

Strict JSON LLM calls — schema validation, budget guard, retry policy, multi-provider support.

```bash
pip install guarded-llm
```

## Quick start (class-based API)

```python
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
```

## High-level class API

::: guarded_llm.GuardedLLM

::: guarded_llm.GuardedCallStats

::: guarded_llm.Budget

::: guarded_llm.BudgetExceeded

::: guarded_llm.RetryPolicy

::: guarded_llm.RetryExhausted

::: guarded_llm.SchemaValidator

## Functional / legacy API

::: guarded_llm.guardrailed_llm_call

::: guarded_llm.GuardrailResult

::: guarded_llm.state_machine_fix

::: guarded_llm.validate_json

## Schemas

::: guarded_llm.LLMSchema

::: guarded_llm.validate_response

::: guarded_llm.Layer3CriticVerdict

::: guarded_llm.Layer4Prediction

::: guarded_llm.B3EnsembleReview

## Providers

::: guarded_llm.BaseProvider

::: guarded_llm.get_provider

::: guarded_llm.list_providers

::: guarded_llm.register_provider

## Exceptions

::: guarded_llm.GuardrailError

::: guarded_llm.SchemaValidationError

::: guarded_llm.LLMCallError

::: guarded_llm.BudgetExceededError
