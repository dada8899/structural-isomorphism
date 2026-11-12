# API reference

## `guardrailed_llm_call(...)`

Two call styles. **Provider-style** is the recommended public API.

### Provider-style (keyword)

```python
result = guardrailed_llm_call(
    provider: str,                   # e.g. "deepseek", "anthropic", "openai", "kimi"
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

Returns a `GuardrailResult` (see below).

### Legacy (positional)

```python
parsed, errors = guardrailed_llm_call(
    prompt_fn: Callable[[str | None], str],
    llm_caller: Callable[[str], str],
    schema_cls: type,
    max_retries: int = 3,
) -> tuple[Any | None, list[str]]
```

Kept for backwards compatibility with the v4 pipeline.

## `GuardrailResult`

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

## `LLMSchema(schema: dict)`

Wraps a JSON Schema (Draft 2020-12) for validation.

```python
schema = LLMSchema({"type": "object", "properties": {...}, "required": [...]})
ok, err, inst = schema.validate(parsed_dict)
```

Raises `ValueError` if the schema itself is invalid.

## `validate_response(d, schema)`

Generic dispatcher — works with both `LLMSchema` instances and dataclass schemas
exposing `.validate(d) -> (ok, err, instance)`.

## `state_machine_fix(raw: str) -> str`

Best-effort cleanup of common LLM JSON drift. Never raises.

## `validate_json(raw_or_dict, schema)`

Convenience: `state_machine_fix` + `json.loads` + `validate_response` in one
call. Returns `(ok, err, instance)`.

## Provider registry

- `get_provider(name) -> BaseProvider` — fetch a provider instance.
- `list_providers() -> list[str]` — sorted list of registered providers.
- `register_provider(name, cls)` — register a `BaseProvider` subclass.
- `BaseProvider` — abstract base; implement `.call(messages, model, max_tokens, schema=None, **kwargs) -> {"text": str, "cost_usd": float}`.

## Built-in providers

| Name | Class | API key env |
|---|---|---|
| `deepseek` | `DeepSeekProvider` | `DEEPSEEK_API_KEY` |
| `anthropic` | `AnthropicProvider` | `ANTHROPIC_API_KEY` |
| `openai` | `OpenAIProvider` | `OPENAI_API_KEY` |
| `kimi` | `KimiProvider` | `KIMI_API_KEY` or `MOONSHOT_API_KEY` |

All built-in providers also accept `api_key=` and `base_url=` kwargs.

## Exceptions

```
GuardrailError                  # base
├── SchemaValidationError       # all retries exhausted with bad output
├── LLMCallError                # provider HTTP / auth / format error
└── BudgetExceededError         # cumulative cost > budget_cap_usd
```

## Legacy dataclass schemas

Imported from `guarded_llm` for backwards compat with the structural-
isomorphism V4 pipeline:

- `Layer3CriticVerdict` — KEEP/SPLIT/REJECT/MERGE_WITH(...) verdicts.
- `Layer4Prediction` — predicted observation in a target system.
- `B3EnsembleReview` — single-model verdict in an N-model ensemble.
