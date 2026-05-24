# Quickstart

Three lines to install. One screen to verify it works.

## Install

```bash
pip install cross-judge                  # core (pydantic + httpx + pyyaml)
pip install 'cross-judge[openai]'        # + openai-python client (optional)
pip install 'cross-judge[dev]'           # + pytest + pytest-mock + build
```

Requires Python >= 3.10. No openai-python required at v0.1 — we ship a
minimal `httpx`-based POST to `/v1/chat/completions` to avoid version
coupling. (`cross-judge` is independent of `guarded-llm`; you can adopt
either or both.)

Set the API key for each vendor you plan to use:

```bash
export DEEPSEEK_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
export OPENROUTER_API_KEY=sk-or-...
```

## Minimal example: 3-critic ensemble

```python
from cross_judge import Critic, Ensemble

critics = [
    Critic(name="claude-strict",   model="anthropic/claude-sonnet-4.5", vendor="openrouter", temperature=0.0),
    Critic(name="ds-pro-creative", model="deepseek-v4-pro",             vendor="deepseek",   temperature=0.7),
    Critic(name="kimi-rigor",      model="moonshot/kimi-k2",            vendor="openrouter", temperature=0.0),
]

result = Ensemble(critics, voting="majority").judge(
    "Is this candidate a valid cross-domain universality class?"
)

print(result.consensus)            # "KEEP" | "REJECT" | "SPLIT" | "MERGE_WITH(...)" | "UNCLEAR"
print(result.agreement_pct)        # 0.67
print(result.krippendorff_alpha)   # disagreement metric in [-1, 1]

for v in result.verdicts:          # per-critic verdicts
    print(v.critic_name, v.kind, v.confidence)
```

## Why ensemble-judge

LLM-as-judge results from a single model inherit that model's biases —
anchoring, alignment, vendor-specific quirks. Running the same judgment
task across multiple vendors / temperatures / prompts and aggregating
verdicts gives you:

1. **Vendor-bias mitigation** — one model's blind spot ≠ all models'.
2. **Contested-item surfacing** — high-disagreement items deserve a human.
3. **Defensible confidence number** — Krippendorff α is publishable.

## Where to next

- [API reference](./api-reference.md) — full public surface.
- [Examples](../examples/) — runnable scripts, including custom voting.
- [CHANGELOG](../CHANGELOG.md) — per-release notes.
