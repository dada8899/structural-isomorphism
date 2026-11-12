# Getting started

## Install

```bash
pip install git+https://github.com/dada8899/structural-isomorphism#subdirectory=packages/guarded-llm
```

Set the API key for whichever provider(s) you want to use:

```bash
export DEEPSEEK_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export KIMI_API_KEY=...        # or MOONSHOT_API_KEY
```

## Your first call

```python
from guarded_llm import guardrailed_llm_call, LLMSchema

schema = LLMSchema({
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["answer", "confidence"],
})

result = guardrailed_llm_call(
    provider="deepseek",
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "What is 2+2? Output JSON."}],
    schema=schema,
)

print(result.parsed)         # {"answer": "4", "confidence": 0.99}
print(result.cost_usd)       # estimated USD cost
print(result.attempts)       # how many calls were needed
```

## What happens under the hood

1. **Layer 0** — strip ` ```json ` fences and locate the outermost JSON envelope
   if the model adds chatty preamble.
2. **Layer 1** — best-effort state-machine fix: trailing commas, single quotes,
   `NaN`/`Infinity`, C-style comments, unescaped interior `"`, BOM.
3. **Layer 2** — `json.loads`.
4. **Layer 3** — validate against your `LLMSchema` (or any object with a
   `.validate(d) -> (ok, err, instance)` classmethod).

If any layer fails the call is retried up to `max_retries` times, with the
previous error injected back into the prompt so the model can self-correct.

## Common patterns

### Budget cap

```python
result = guardrailed_llm_call(
    provider="anthropic",
    model="claude-sonnet-4.5",
    messages=[...],
    schema=schema,
    budget_cap_usd=0.10,   # raises BudgetExceededError if cumulative cost > $0.10
)
```

### Custom retry backoff

```python
result = guardrailed_llm_call(
    ...,
    max_retries=5,
    retry_backoff_s=2.0,   # sleep between retries
)
```

### Fallback chain across providers

See [`examples/multi_provider.py`](../examples/multi_provider.py).

### Bringing your own provider

```python
from guarded_llm import BaseProvider, register_provider

class MyProvider(BaseProvider):
    name = "myprov"
    def call(self, messages, model, max_tokens, schema=None, **kwargs):
        # ... call your endpoint ...
        return {"text": raw_text, "cost_usd": 0.0}

register_provider("myprov", MyProvider)
```

Then use `provider="myprov"` in `guardrailed_llm_call(...)`.

## Migrating from the legacy v4/lib API

The legacy positional signature still works:

```python
parsed, errors = guardrailed_llm_call(
    prompt_fn=lambda last_err: build_prompt(last_err),
    llm_caller=lambda p: my_llm(p),
    schema_cls=MyDataclassSchema,
    max_retries=3,
)
```

We recommend migrating to the keyword (provider-style) call when you can —
you get cost tracking, attempt counting, and structured raw output capture.
