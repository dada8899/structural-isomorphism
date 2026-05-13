***REMOVED*** API reference

***REMOVED******REMOVED*** `guardrailed_llm_call(...)`

Two call styles. **Provider-style** is the recommended public API.

***REMOVED******REMOVED******REMOVED*** Provider-style (keyword)

```python
result = guardrailed_llm_call(
    provider: str,                   ***REMOVED*** e.g. "deepseek", "anthropic", "openai", "kimi"
    model: str,                      ***REMOVED*** vendor model id
    messages: list[dict],            ***REMOVED*** OpenAI-style chat messages
    schema: LLMSchema | type,        ***REMOVED*** validation target
    max_retries: int = 3,
    max_tokens: int = 2048,
    budget_cap_usd: float | None = None,
    retry_backoff_s: float = 0.0,
    **kwargs,                        ***REMOVED*** forwarded to the provider's .call()
) -> GuardrailResult
```

Returns a `GuardrailResult` (see below).

***REMOVED******REMOVED******REMOVED*** Legacy (positional)

```python
parsed, errors = guardrailed_llm_call(
    prompt_fn: Callable[[str | None], str],
    llm_caller: Callable[[str], str],
    schema_cls: type,
    max_retries: int = 3,
) -> tuple[Any | None, list[str]]
```

Kept for backwards compatibility with the v4 pipeline.

***REMOVED******REMOVED*** `GuardrailResult`

```python
@dataclass
class GuardrailResult:
    parsed: Any              ***REMOVED*** validated instance, or None on full failure
    errors: list[str]        ***REMOVED*** per-attempt error strings
    attempts: int            ***REMOVED*** actual LLM calls made
    cost_usd: float          ***REMOVED*** estimated cumulative USD cost
    raw_outputs: list[str]   ***REMOVED*** raw LLM text from each attempt (for debug)

    @property
    def ok(self) -> bool: ...
```

***REMOVED******REMOVED*** `LLMSchema(schema: dict)`

Wraps a JSON Schema (Draft 2020-12) for validation.

```python
schema = LLMSchema({"type": "object", "properties": {...}, "required": [...]})
ok, err, inst = schema.validate(parsed_dict)
```

Raises `ValueError` if the schema itself is invalid.

***REMOVED******REMOVED*** `validate_response(d, schema)`

Generic dispatcher — works with both `LLMSchema` instances and dataclass schemas
exposing `.validate(d) -> (ok, err, instance)`.

***REMOVED******REMOVED*** `state_machine_fix(raw: str) -> str`

Best-effort cleanup of common LLM JSON drift. Never raises.

***REMOVED******REMOVED*** `validate_json(raw_or_dict, schema)`

Convenience: `state_machine_fix` + `json.loads` + `validate_response` in one
call. Returns `(ok, err, instance)`.

***REMOVED******REMOVED*** Provider registry

- `get_provider(name) -> BaseProvider` — fetch a provider instance.
- `list_providers() -> list[str]` — sorted list of registered providers.
- `register_provider(name, cls)` — register a `BaseProvider` subclass.
- `BaseProvider` — abstract base; implement `.call(messages, model, max_tokens, schema=None, **kwargs) -> {"text": str, "cost_usd": float}`.

***REMOVED******REMOVED*** Built-in providers

| Name | Class | API key env |
|---|---|---|
| `deepseek` | `DeepSeekProvider` | `DEEPSEEK_API_KEY` |
| `anthropic` | `AnthropicProvider` | `ANTHROPIC_API_KEY` |
| `openai` | `OpenAIProvider` | `OPENAI_API_KEY` |
| `kimi` | `KimiProvider` | `KIMI_API_KEY` or `MOONSHOT_API_KEY` |

All built-in providers also accept `api_key=` and `base_url=` kwargs.

***REMOVED******REMOVED*** Exceptions

```
GuardrailError                  ***REMOVED*** base
├── SchemaValidationError       ***REMOVED*** all retries exhausted with bad output
├── LLMCallError                ***REMOVED*** provider HTTP / auth / format error
└── BudgetExceededError         ***REMOVED*** cumulative cost > budget_cap_usd
```

***REMOVED******REMOVED*** Legacy dataclass schemas

Imported from `guarded_llm` for backwards compat with the structural-
isomorphism V4 pipeline:

- `Layer3CriticVerdict` — KEEP/SPLIT/REJECT/MERGE_WITH(...) verdicts.
- `Layer4Prediction` — predicted observation in a target system.
- `B3EnsembleReview` — single-model verdict in an N-model ensemble.
