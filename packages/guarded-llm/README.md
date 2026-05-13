# guarded-llm

> Strict JSON output from any LLM, with retry + schema validation + multi-provider routing in one call.

> Pre-release: not yet on PyPI; install from source.

## What it does

LLMs hallucinate JSON. `guarded-llm` wraps a single call into a 4-layer
defense:

1. **Strip markdown fences** and locate the JSON envelope in chatty output.
2. **State-machine fix** common drift: trailing commas, single quotes,
   `NaN`/`Infinity`, comments, unescaped interior quotes, BOM.
3. **Parse** with `json.loads`.
4. **Validate** against a schema (JSON Schema via `LLMSchema`, or any class
   exposing a `.validate(d) -> (ok, err, instance)` classmethod).

If any layer fails, the call is retried with the previous error injected back
into the prompt as a hint. After `max_retries`, it returns a structured
`GuardrailResult` with `parsed`, `errors`, `attempts`, and `cost_usd`.

## Install

```bash
# From source (pre-release)
pip install git+https://github.com/dada8899/structural-isomorphism#subdirectory=packages/guarded-llm

# Once published
pip install guarded-llm
```

Optional extras for vendor SDKs (you don't need them — built-in adapters use
plain HTTP via `requests`):

```bash
pip install guarded-llm[anthropic]   # if you want the official anthropic SDK
pip install guarded-llm[openai]      # if you want the official openai SDK
pip install guarded-llm[dev]         # pytest, ruff, mypy
```

## Quickstart

```python
from guarded_llm import guardrailed_llm_call, LLMSchema

schema = LLMSchema({
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["KEEP", "REJECT", "SPLIT", "MERGE"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["verdict", "confidence"],
})

result = guardrailed_llm_call(
    provider="deepseek",
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "Is gravity a self-organized criticality system?"}],
    schema=schema,
    max_retries=3,
    budget_cap_usd=0.05,
)

if result.ok:
    print(result.parsed)         # {"verdict": "REJECT", "confidence": 0.9}
    print(result.cost_usd)       # 0.0012
    print(result.attempts)       # 1
else:
    print("All retries failed:", result.errors)
```

Set `DEEPSEEK_API_KEY` in your env (or pass `api_key=` via `**kwargs`).

## Features

- **Multi-provider out of the box** — DeepSeek, Anthropic Claude, OpenAI,
  Kimi (Moonshot). All built-in adapters use plain HTTP — no vendor SDK
  required.
- **Pluggable** — subclass `BaseProvider` + call `register_provider("name", cls)`
  to add anything else (OpenRouter, Together, Google Gemini, local Ollama, …).
- **Schema validation** — bring your own JSON Schema via `LLMSchema(...)`, or
  use the legacy dataclass schemas (`Layer3CriticVerdict`, `Layer4Prediction`,
  `B3EnsembleReview`) shipped from the structural-isomorphism V4 pipeline.
- **Automatic retry with error feedback** — each retry's prompt includes the
  prior validation error so the model can self-correct.
- **Budget cap** — pass `budget_cap_usd=` and a `BudgetExceededError` fires
  before you torch your wallet on a runaway loop.
- **Structured result** — `GuardrailResult` exposes `parsed`, `errors`,
  `attempts`, `cost_usd`, and `raw_outputs` for debugging.
- **Drop-in compat** — supports the legacy
  `guardrailed_llm_call(prompt_fn, llm_caller, schema_cls, max_retries)`
  signature for existing callers.

## How it compares

| Feature | guarded-llm | [instructor](https://github.com/jxnl/instructor) | [outlines](https://github.com/dottxt-ai/outlines) | [guidance](https://github.com/guidance-ai/guidance) |
|---|---|---|---|---|
| Multi-provider | ✅ 4 built-in | ✅ many | partial (HF-first) | partial |
| Works on closed-model APIs | ✅ | ✅ | mostly local | partial |
| JSON Schema input | ✅ | via Pydantic | ✅ | ✅ |
| State-machine fixer for drift | ✅ | retry only | grammar-constrained | grammar-constrained |
| No SDK lock-in (HTTP only) | ✅ | requires vendor SDK | ✅ | ✅ |
| Cost tracking | ✅ | ❌ | ❌ | ❌ |
| Budget cap | ✅ | ❌ | ❌ | ❌ |
| Footprint | tiny (3 deps) | medium | large (torch optional) | medium |

`guarded-llm`'s niche: **closed-model APIs where you can't grammar-constrain
the decoder, but you still want strict JSON without writing five layers of
defensive parsing**. If you're using local HF models, prefer `outlines`'
grammar-level approach; if you're already deep in Pydantic, `instructor` is
elegant.

## Provider environment variables

| Provider | API key env | Base URL env (optional) |
|---|---|---|
| `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL` |
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` |
| `openai` | `OPENAI_API_KEY` | `OPENAI_BASE_URL` |
| `kimi` | `KIMI_API_KEY` or `MOONSHOT_API_KEY` | `KIMI_BASE_URL` |

You can also pass `api_key=`, `base_url=` directly in the call.

## License

MIT — see [LICENSE](./LICENSE).

## Contributing

This package lives inside the [structural-isomorphism](https://github.com/dada8899/structural-isomorphism)
monorepo at `packages/guarded-llm/`. PRs welcome — see the
[repo issues page](https://github.com/dada8899/structural-isomorphism/issues).
