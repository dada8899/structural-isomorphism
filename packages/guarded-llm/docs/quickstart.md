# Quickstart

Three lines to install. One screen to verify it works.

## Install

```bash
pip install guarded-llm
```

Optional vendor extras (only if you want the official SDK alongside the
built-in `httpx` adapters):

```bash
pip install 'guarded-llm[all]'          # anthropic + openai + zhipuai
pip install 'guarded-llm[anthropic]'    # one provider at a time
pip install 'guarded-llm[dev]'          # pytest + respx + ruff + mypy + build
```

Set the API key for whichever provider(s) you want to use:

```bash
export DEEPSEEK_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export KIMI_API_KEY=...                 # or MOONSHOT_API_KEY
export ZHIPUAI_API_KEY=...              # for the glm extra
```

## Minimal example

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
    budget_cap_usd=0.05,          # raises BudgetExceededError if exceeded
)

assert result.ok
print(result.parsed)              # {"answer": "4", "confidence": 0.99}
print(result.cost_usd)            # estimated USD cost
print(result.attempts)            # how many LLM calls were needed
```

## What the guard does (4 layers)

1. **Layer 0** — strip ` ```json ` fences; locate the outermost JSON envelope
   when the model adds chatty preamble.
2. **Layer 1** — best-effort state-machine fix: trailing commas, single quotes,
   `NaN` / `Infinity`, C-style comments, unescaped interior quotes, BOM.
3. **Layer 2** — `json.loads`.
4. **Layer 3** — validate against your `LLMSchema` (or any class exposing
   `.validate(d) -> (ok, err, instance)` — including Pydantic models).

If any layer fails, the call retries up to `max_retries` times with the
previous error injected back into the prompt for self-correction.

## Where to next

- [API reference](./api-reference.md) — full public surface.
- [Examples](../examples/) — runnable scripts, including multi-provider fallback.
- [CHANGELOG](../CHANGELOG.md) — per-release notes.
