# guarded-llm

> Strict-JSON LLM call with budget + retry + 5-vendor support in 5 lines.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://pypi.org/project/guarded-llm/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`guarded-llm` is a small, dependency-light Python package that wraps any LLM
chat-completion call into a hardened pipeline:

1. **Strip markdown fences** and locate the JSON envelope in chatty output.
2. **State-machine fix** common drift bugs: trailing commas, single quotes,
   `NaN` / `Infinity`, embedded comments, unescaped interior quotes, BOM.
3. **Parse** with `json.loads`.
4. **Validate** against a Pydantic model, JSON Schema, or any class exposing
   `.validate(d) -> (ok, err, instance)`.

If any layer fails, the prompt is retried with the previous error injected
back as a hint. Cumulative spend is tracked against an optional `Budget`, and
a `BudgetExceeded` exception fires before runaway loops eat your monthly cap.

## Install

```bash
pip install guarded-llm

# Optional vendor extras (only if you want the official SDK alongside the
# built-in HTTP adapter — the built-ins work fine on their own)
pip install guarded-llm[anthropic]
pip install guarded-llm[deepseek]
pip install guarded-llm[kimi]
pip install guarded-llm[glm]
pip install guarded-llm[openai]
pip install guarded-llm[all]            # all five
pip install guarded-llm[dev]            # pytest, respx, ruff, mypy, build
```

## 5-line quickstart

```python
from pydantic import BaseModel
from guarded_llm import GuardedLLM

class Verdict(BaseModel):
    verdict: str
    confidence: float

llm = GuardedLLM(provider="deepseek", model="deepseek-v4-flash", schema=Verdict)
out = llm.call("Is gravity a self-organized criticality system? Reply as JSON.")
print(out.verdict, out.confidence)
```

Set `DEEPSEEK_API_KEY` in your env (or pass `api_key=` into the constructor).

## Why this exists

LLMs in production pipelines have three failure modes that single-shot
`requests.post` doesn't handle:

1. **Schema drift.** Even with `response_format=json_object`, models return
   things like `{...,}` (trailing comma), `{'k': 'v'}` (single quotes),
   ` ```json\n...\n``` ` (markdown fences), or unescaped quotes inside string
   values. These break `json.loads` even though the intent is clear.
2. **Cost overruns.** A buggy prompt loop can burn $50 in an hour before
   anybody notices. You want a hard cap that raises instead of debits.
3. **Vendor lock-in.** Switching from OpenAI → DeepSeek → Kimi → GLM for cost
   or regional reasons should be a one-line config change, not a refactor.

`guarded-llm` fixes all three in ~500 LOC. No SDK lock-in, no heavyweight
runtime, no opinions about your application architecture.

## Quickstart per vendor

All four use the same `GuardedLLM` class — only `provider=` and `model=` change.

### Anthropic Claude

```python
import os
from pydantic import BaseModel
from guarded_llm import GuardedLLM

class Out(BaseModel):
    answer: str

llm = GuardedLLM(
    provider="anthropic",
    model="claude-sonnet-4.5",
    schema=Out,
    api_key=os.environ["ANTHROPIC_API_KEY"],
)
print(llm.call("What is 2+2? Reply as JSON: {answer: '...'}").answer)
```

### DeepSeek (direct or via OpenRouter)

```python
llm = GuardedLLM(provider="deepseek", model="deepseek-v4-flash", schema=Out)
# Override base_url for OpenRouter:
llm = GuardedLLM(
    provider="deepseek",
    model="deepseek/deepseek-chat",
    schema=Out,
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
```

### Kimi (Moonshot)

```python
llm = GuardedLLM(provider="kimi", model="kimi-k2.5", schema=Out)
```

### GLM (Zhipu BigModel)

```python
llm = GuardedLLM(provider="glm", model="glm-4.6", schema=Out)
```

## Budget enforcement

```python
from guarded_llm import GuardedLLM, Budget, BudgetExceeded

budget = Budget(usd_total=0.50, usd_per_call=0.05)
llm = GuardedLLM(provider="deepseek", model="deepseek-v4-flash",
                 schema=Out, budget=budget)

for q in many_questions:
    try:
        out = llm.call(q)
    except BudgetExceeded as e:
        print(f"hit cap at ${budget.spent_usd:.4f}")
        break
```

The `Budget` object persists across `.call()` invocations on the same `GuardedLLM`
instance, so a single budget can guard an entire pipeline. Charges are recorded
**before** the schema-validate step, which means a runaway retry loop can't keep
spending after you've hit the cap.

## Retry semantics

```python
from guarded_llm import RetryPolicy

llm = GuardedLLM(
    provider="deepseek",
    model="deepseek-v4-flash",
    schema=Out,
    retry=RetryPolicy(max_attempts=5, backoff_seconds=2.0, jitter=True),
)
```

- **`max_attempts`**: total LLM calls before giving up (raises `RetryExhausted`).
- **`backoff_seconds`**: base sleep between attempts (linear, multiplied by
  attempt number).
- **`jitter`**: if `True`, multiplies sleep by `uniform(0.5, 1.5)` to avoid
  thundering-herd retry storms when multiple workers share a backend.

On each retry, the previous validation error is appended to the last user
message as a hint:

> "Previous output failed validation: `confidence: out of range`. Output valid
> JSON only — no prose, no markdown fences."

This is enough to recover from drift bugs in ~95% of cases in production.

## Multi-vendor failover

```python
from guarded_llm import GuardedLLM, RetryExhausted

for provider, model in [("deepseek", "deepseek-v4-flash"),
                        ("kimi",     "kimi-k2.5"),
                        ("glm",      "glm-4.6")]:
    try:
        llm = GuardedLLM(provider=provider, model=model, schema=Out)
        return llm.call(prompt)
    except RetryExhausted:
        continue
raise RuntimeError("all vendors failed")
```

See `examples/03_multi_vendor_failover.py` for the full pattern (with budget
sharing across vendors).

## Extending with a new vendor

Adding a new vendor is ~30 lines:

```python
from guarded_llm import BaseProvider, register_provider

class TogetherProvider(BaseProvider):
    name = "together"

    def call(self, messages, model, max_tokens, schema=None, **kwargs):
        import requests, os
        resp = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
            headers={"Authorization": f"Bearer {os.environ['TOGETHER_API_KEY']}"},
        )
        data = resp.json()
        return {
            "text": data["choices"][0]["message"]["content"],
            "cost_usd": 0.0,  # fill in your pricing logic
        }

register_provider("together", TogetherProvider)

# Now any call site can use it:
llm = GuardedLLM(provider="together", model="meta-llama/Llama-3-70b", schema=Out)
```

## Environment variables

| Provider | API key env | Base URL env |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` |
| `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL` |
| `openai` | `OPENAI_API_KEY` | `OPENAI_BASE_URL` |
| `kimi` | `KIMI_API_KEY` or `MOONSHOT_API_KEY` | `KIMI_BASE_URL` |
| `glm` | `GLM_API_KEY` or `ZHIPU_API_KEY` | `GLM_BASE_URL` |

All can also be passed inline via `GuardedLLM(..., api_key=..., base_url=...)`.

## How it compares

| Feature | guarded-llm | instructor | outlines | guidance |
|---|---|---|---|---|
| Multi-provider | 5 built-in | many | partial | partial |
| Closed-model APIs | yes | yes | mostly local | partial |
| JSON Schema input | yes | via Pydantic | yes | yes |
| State-machine drift fixer | yes | retry only | grammar | grammar |
| Cost tracking | yes | no | no | no |
| Budget cap | yes | no | no | no |
| Footprint | tiny (5 deps) | medium | large | medium |

`guarded-llm`'s niche: **closed-model APIs where you can't grammar-constrain
the decoder, but you still want strict JSON without writing five layers of
defensive parsing**. If you're using local HF models, prefer `outlines`'
grammar-level approach; if you're already deep in Pydantic, `instructor` is
elegant — but it doesn't track cost.

## License

MIT — see [LICENSE](./LICENSE).

## Source

Lives inside the [structural-isomorphism](https://github.com/dada8899/structural-isomorphism)
monorepo at `packages/guarded-llm/`. PRs welcome.
