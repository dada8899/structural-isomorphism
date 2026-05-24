# API reference

Public surface of `guarded-llm`. Everything documented here is exported
from the top-level `guarded_llm` package.

## High-level wrapper

### `GuardedLLM(provider, model, schema=None, budget=None, retry=None, **provider_kwargs)`

Object-oriented entry point. One instance per `(provider, model, schema)` tuple.

```python
from pydantic import BaseModel
from guarded_llm import GuardedLLM, Budget

class Verdict(BaseModel):
    verdict: str
    confidence: float

llm = GuardedLLM(
    provider="deepseek",
    model="deepseek-v4-flash",
    schema=Verdict,
    budget=Budget(usd_cap=1.00),
)
out = llm.call("Is this a SOC system? Reply as JSON.")
print(out.verdict, out.confidence)
```

## Functional entry points

### `guardrailed_llm_call(...)`

Two call styles; **provider-style** (keyword) is the recommended public API.

```python
result = guardrailed_llm_call(
    provider: str,                   # "deepseek" | "anthropic" | "openai" | "kimi" | "glm"
    model: str,                      # vendor model id
    messages: list[dict],            # OpenAI-style chat messages
    schema: LLMSchema | type,        # validation target
    max_retries: int = 3,
    max_tokens: int = 2048,
    budget_cap_usd: float | None = None,
    retry_backoff_s: float = 0.0,
    **kwargs,                        # forwarded to the provider's .call()
) -> GuardrailResult
```

#### Legacy positional form

```python
parsed, errors = guardrailed_llm_call(
    prompt_fn: Callable[[str | None], str],
    llm_caller: Callable[[str], str],
    schema_cls: type,
    max_retries: int = 3,
) -> tuple[Any | None, list[str]]
```

Kept for backwards compatibility with the v4 pipeline. Migration: prefer
the keyword call to get cost / attempts / raw-output capture.

## Result type

### `GuardrailResult`

```python
@dataclass
class GuardrailResult:
    parsed: Any              # validated instance, or None on full failure
    errors: list[str]        # per-attempt error strings
    attempts: int            # actual LLM calls made
    cost_usd: float          # estimated cumulative USD cost
    raw_outputs: list[str]   # raw LLM text from each attempt (for debug)

    @property
    def ok(self) -> bool: ...
```

## Schemas

### `LLMSchema(schema: dict)`

Wraps a JSON Schema (Draft 2020-12).

```python
schema = LLMSchema({"type": "object", "properties": {...}, "required": [...]})
ok, err, inst = schema.validate(parsed_dict)
```

Raises `ValueError` if the schema itself is invalid.

### `validate_response(d, schema)`

Generic dispatcher — works with `LLMSchema`, Pydantic `BaseModel`, and any
class exposing `.validate(d) -> (ok, err, instance)`.

### `state_machine_fix(raw: str) -> str`

Best-effort cleanup of common LLM JSON drift. Never raises.

### `validate_json(raw_or_dict, schema)`

Convenience: `state_machine_fix` + `json.loads` + `validate_response` in one
call. Returns `(ok, err, instance)`.

## Provider registry

| Symbol | Purpose |
|---|---|
| `get_provider(name) -> BaseProvider` | Fetch a provider instance |
| `list_providers() -> list[str]` | Sorted list of registered providers |
| `register_provider(name, cls)` | Register a `BaseProvider` subclass |
| `BaseProvider` | Abstract base; implement `.call(messages, model, max_tokens, schema=None, **kwargs) -> {"text": str, "cost_usd": float}` |

### Built-in providers

| Name | Class | API key env |
|---|---|---|
| `deepseek` | `DeepSeekProvider` | `DEEPSEEK_API_KEY` |
| `anthropic` | `AnthropicProvider` | `ANTHROPIC_API_KEY` |
| `openai` | `OpenAIProvider` | `OPENAI_API_KEY` |
| `kimi` | `KimiProvider` | `KIMI_API_KEY` or `MOONSHOT_API_KEY` |
| `glm` | `GLMProvider` | `ZHIPUAI_API_KEY` |

All built-in providers also accept `api_key=` and `base_url=` kwargs.

## Budget + retry

```python
from guarded_llm import Budget, BudgetExceeded, RetryPolicy, RetryExhausted

budget = Budget(usd_cap=0.50)         # hard cap; raises BudgetExceeded
retry  = RetryPolicy(max_attempts=5, backoff_s=1.5)
```

## Exceptions

```
GuardrailError                  # base
├── SchemaValidationError       # all retries exhausted with bad output
├── LLMCallError                # provider HTTP / auth / format error
├── BudgetExceededError         # cumulative cost > budget cap
└── RetryExhausted              # retry policy gave up
```

## Legacy dataclass schemas

Imported from `guarded_llm` for backwards compat with the structural-
isomorphism V4 pipeline:

- `Layer3CriticVerdict` — KEEP / SPLIT / REJECT / MERGE_WITH(...) verdicts.
- `Layer4Prediction` — predicted observation in a target system.
- `B3EnsembleReview` — single-model verdict in an N-model ensemble.
