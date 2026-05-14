# cross-judge

**Lightweight multi-vendor LLM ensemble judge for ML / research workflows.**

cross-judge lets you wire up a panel of LLM reviewers — across vendors,
models, temperatures, or system prompts — and aggregate their verdicts into
a single consensus label. It's a thin, focused library for the
**LLM-as-judge** methodology: one item in, N independent verdicts out,
plus a consensus aggregator on top.

## Why

LLM-as-judge results from a single model are known to inherit that model's
biases (anchoring, alignment, vendor-specific quirks). Running the same
judgment task across multiple vendors / temperatures / prompts and
aggregating verdicts is a cheap way to:

1. Mitigate vendor-specific bias.
2. Surface contested items (disagreement = signal).
3. Probe within-model confidence drift (same vendor, varied temperature / persona).

This package was extracted from the [structural-isomorphism](https://github.com/dada8899/structural-isomorphism)
project's B3 / B4 ensemble review pipeline (multi-vendor LLM review of
candidate cross-domain universality classes).

## Install

```bash
pip install -e packages/cross-judge          # development
# or, eventually:  pip install cross-judge   # not yet on PyPI
```

Dependencies: `openai>=1.0`, `pydantic>=2.0`.

## Quick example

```python
from cross_judge import Reviewer, JudgePanel

# Three DeepSeek reviewers: 2 deterministic + 1 high-temperature dissenter
reviewers = [
    Reviewer(
        reviewer_id="ds-pro-T0",
        model="deepseek-v4-pro",
        vendor="deepseek",
        temperature=0.0,
        system_prompt="You are a rigorous judge. Output JSON only.",
    ),
    Reviewer(
        reviewer_id="ds-flash-T0",
        model="deepseek-v4-flash",
        vendor="deepseek",
        temperature=0.0,
        system_prompt="You are a rigorous judge. Output JSON only.",
    ),
    Reviewer(
        reviewer_id="ds-pro-T07",
        model="deepseek-v4-pro",
        vendor="deepseek",
        temperature=0.7,
        system_prompt="You are a creative dissenter. Output JSON only.",
    ),
]

panel = JudgePanel(reviewers=reviewers, strategy="majority")

user_prompt = """Judge whether this is a valid universality class.

Item: <your item>

Output JSON: {"verdict": "KEEP"|"REJECT"|"UNCLEAR", "confidence": 0.0-1.0, "rationale": "..."}
"""

result = panel.ask(item_id="class_42", user_prompt=user_prompt)
print(result.consensus, result.avg_confidence, result.disagreement)
for v in result.verdicts:
    print(f"  {v.reviewer_id}: {v.verdict} (conf={v.confidence:.2f})")
```

Set the DeepSeek API key first:

```bash
export DEEPSEEK_API_KEY='sk-...'
```

(For OpenRouter, set `OPENROUTER_API_KEY` and pass `vendor="openrouter"`.
For OpenAI, set `OPENAI_API_KEY` and pass `vendor="openai"`.)

## Aggregation strategies

Strategies map `list[Verdict]` → `(consensus_label, disagreement_bool)`.

| name | rule |
|---|---|
| `majority` | most common label; tiebreaker via `priority=[...]` or first-seen |
| `unanimous` | only returns a label when all reviewers agree; else `fallback` |
| `weighted` | weighted vote = reviewer.weight × verdict.confidence |
| `first_disagreement` | returns `DISAGREE` if any two reviewers differ; else the agreed label |

Custom strategies:

```python
def my_strategy(verdicts):
    # ... your logic ...
    return "KEEP", False  # (consensus, disagreement_bool)

panel = JudgePanel(reviewers=reviewers, strategy=my_strategy)
```

## Vendors

Out of the box (all OpenAI-compatible /v1/chat/completions endpoints):

- `deepseek` — `https://api.deepseek.com/v1`, env `DEEPSEEK_API_KEY` (**default**)
- `openai` — `https://api.openai.com/v1`, env `OPENAI_API_KEY`
- `openrouter` — `https://openrouter.ai/api/v1`, env `OPENROUTER_API_KEY`

For arbitrary OpenAI-compatible endpoints, pass `base_url=...` directly to
`Reviewer` (or build the `openai.OpenAI` client yourself and pass `client=...`).

## Error handling

Reviewer calls catch all exceptions and return `Verdict(verdict="ERROR",
error="...")` rather than raising. Aggregation strategies skip errored
verdicts — they don't tank consensus. Inspect `result.verdicts` for the
per-reviewer error string.

JSON parse failures produce `Verdict(verdict="PARSE_FAIL", error="parse_fail")`
with the raw response captured in `raw_response` for audit.

## Example: research-grade prompt

`examples/taxonomy_b4_demo.py` reproduces a small slice of the
structural-isomorphism B4 ensemble (universality-class review) end-to-end
on a synthetic 3-item batch. Run with a real `DEEPSEEK_API_KEY` to
exercise the live path, or with the bundled `--mock` flag for an offline
demonstration.

## License

MIT. See `LICENSE`.

## Citation

If cross-judge contributes to a paper, please cite the structural-isomorphism
project where the multi-vendor ensemble judging pattern was developed:

> dada8899. "Cross-domain structural isomorphism: a universality-class
> taxonomy via multi-vendor LLM ensemble review." 2026.
> https://github.com/dada8899/structural-isomorphism
