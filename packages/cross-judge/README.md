# cross-judge

**Multi-vendor LLM ensemble-judge framework with KEEP / REJECT / SPLIT / MERGE
verdicts and Krippendorff α disagreement metrics.**

`cross-judge` wires up a panel of LLM critics — across vendors, models,
temperatures, and prompts — and aggregates their verdicts into a single
consensus label, plus tells you *how much they disagreed*. It's a thin,
focused library for the **LLM-as-judge** methodology with a deliberately
small public surface (`Critic`, `Ensemble`, `Verdict`).

## 5-second pitch

```python
from cross_judge import Critic, Ensemble

critics = [
    Critic(name="claude-strict",  model="anthropic/claude-sonnet-4.5", vendor="openrouter"),
    Critic(name="ds-pro-creative", model="deepseek-v4-pro",            vendor="deepseek",   temperature=0.7),
    Critic(name="kimi-rigor",     model="moonshot/kimi-k2",            vendor="openrouter"),
]
result = Ensemble(critics, voting="majority").judge(
    "Is this candidate a valid universality class?"
)
print(result.consensus)          # "KEEP"
print(result.agreement_pct)      # 0.67
print(result.krippendorff_alpha) # 0.0  (2 vs 1 = chance-level)
```

## Why

LLM-as-judge results from a single model inherit that model's biases —
anchoring, alignment, vendor-specific quirks. Running the same judgment
task across multiple vendors / temperatures / prompts and aggregating
verdicts is a cheap way to:

1. **Mitigate vendor-specific bias** — one model's blind spot ≠ all models'.
2. **Surface contested items** — high-disagreement items deserve human review.
3. **Quantify confidence** — Krippendorff α gives you a defensible number
   to put in a methods section.

This package was extracted from the [structural-isomorphism](https://github.com/dada8899/structural-isomorphism)
project's B3 / B4 ensemble review pipeline (multi-vendor LLM review of
candidate cross-domain universality classes).

## Install

```bash
pip install cross-judge
# or, with the openai-python client as a convenience:
pip install 'cross-judge[openai]'
```

Dependencies: `pydantic>=2`, `httpx>=0.27`, `pyyaml>=6`. No openai-python
required at v0.1 — we ship a minimal httpx-based POST to
`/v1/chat/completions` to avoid version-coupling. Documented choice:
**standalone**, not depending on `guarded-llm` at v0.1, so users can adopt
cross-judge independently. (`guarded-llm` is a sibling package for
single-call safety / cost guards.)

## Quickstart: 3-model judge

```python
from cross_judge import Critic, Ensemble

# Each critic: own model, own temperature, own prompt template.
# Templates use str.format with {query} and optional context keys.

claude = Critic(
    name="claude-strict",
    model="anthropic/claude-sonnet-4.5",
    vendor="openrouter",
    temperature=0.0,
    system_prompt="You are a strict reviewer. Output JSON only.",
    prompt_template=(
        "Judge: {query}\n\n"
        "Output JSON: {{"
        '"kind": "<KEEP|REJECT|SPLIT|MERGE|UNCLEAR>", '
        '"confidence": <0-1>, '
        '"reasoning": "<short>"'
        "}}"
    ),
)

deepseek = Critic(
    name="ds-pro-creative",
    model="deepseek-v4-pro",
    vendor="deepseek",
    temperature=0.7,
    system_prompt="You are a creative dissenter. Output JSON only.",
    prompt_template=claude.prompt_template,
)

kimi = Critic(
    name="kimi-rigor",
    model="moonshot/kimi-k2",
    vendor="openrouter",
    temperature=0.0,
    system_prompt="You are a rigorous reviewer. Output JSON only.",
    prompt_template=claude.prompt_template,
)

ensemble = Ensemble(
    critics=[claude, deepseek, kimi],
    voting="majority",
)

result = ensemble.judge(
    query="Bank failures and earthquake aftershocks both show power-law size distributions — same universality class?",
    query_id="candidate-q-001",
)

print(f"Consensus: {result.consensus}")
print(f"Agreement: {result.agreement_pct:.0%}")
print(f"Krippendorff α: {result.krippendorff_alpha:.3f}")
for v in result.verdicts:
    print(f"  {v.critic_id:20s} kind={v.kind:8s} conf={v.confidence:.2f}  {v.reasoning[:60]}")
```

Set API keys:
```bash
export OPENROUTER_API_KEY='sk-or-...'
export DEEPSEEK_API_KEY='sk-...'
```

## Versioned prompts (recommended pattern)

Prompts have semantics, so they deserve semver. Ship YAML prompts under
git-tracked files and pin to specific versions in production:

```yaml
# prompts/b3_universality_critic.yaml
version: "0.1"
system_prompt: "You are a rigorous universality-class critic ..."
user_prompt_template: |
  Judge the following candidate ...
  {query}
  Output JSON: { "kind": ..., "confidence": ..., "reasoning": ... }
```

```python
critic = Critic.from_yaml_prompt(
    name="b3-rigor",
    model="deepseek-v4-pro",
    yaml_path="prompts/b3_universality_critic.yaml",  # git-tagged
)
```

Bump `version` whenever you change wording or vocabulary. Pin in production
to a git tag like `prompts/b3_universality_critic.yaml@v0.1`. Bundled
default prompts ship under `cross_judge/prompts/`:

- `b3_universality_critic.yaml` — research-grade universality-class critic
- `generic_universality_judge.yaml` — domain-agnostic version

## VerdictKind vocabulary

The default vocabulary is `Literal["KEEP", "REJECT", "SPLIT", "MERGE",
"UNCLEAR", "ERROR", "PARSE_FAIL"]`:

| kind | meaning |
|---|---|
| `KEEP`        | accept candidate as-is |
| `REJECT`      | discard (fails criteria) |
| `SPLIT`       | accept but split into sub-classes (composite candidate) |
| `MERGE`       | accept but merge with existing class (duplicate / overlap) |
| `UNCLEAR`     | reviewer cannot decide |
| `ERROR`       | LLM call failed (network / 5xx) |
| `PARSE_FAIL`  | LLM responded but JSON couldn't be parsed |

Free-form labels (`PASS`, `FAIL`, etc.) are also accepted — pass them as
plain strings.

## Voting strategies

| name | rule | use when |
|---|---|---|
| `majority`   | most common label wins; tie-break via `priority=[...]` | default, most ensembles |
| `unanimous`  | only return label if all critics agree; else `fallback` | high-stakes, low false-positive |
| (custom)     | pass any `Callable[[list[Verdict]], (str, bool)]`       | weighted / domain-specific |

```python
# Conservative: only accept items all 3 critics endorsed
ensemble = Ensemble(critics, voting="unanimous", voting_kwargs={"fallback": "NEEDS_REVIEW"})

# Tie-break toward rejection (recall-leaning)
ensemble = Ensemble(critics, voting="majority", voting_kwargs={"priority": ["REJECT", "KEEP"]})
```

## Disagreement metrics primer

cross-judge reports two metrics per ensemble call:

- **`agreement_pct`** — fraction of critics that match the consensus.
  Simple, intuitive: "2 out of 3 critics said KEEP" → 0.67. Not adjusted
  for chance — 50% on a binary choice is no better than coin-flip.

- **`krippendorff_alpha`** — chance-corrected inter-rater reliability
  (Krippendorff 2011). Values:
  - α = **1.0**  → perfect agreement (all critics identical)
  - α = **0.0**  → agreement equal to chance given the marginal distribution
  - α = **<0.0** → systematic disagreement (worse than random)

  α > 0.667 is a common acceptance threshold for "substantial agreement"
  in content analysis. For LLM-as-judge ensembles, treat α < 0.4 as
  "the panel can't agree — surface to human review", and α > 0.8 as
  "ensemble is converged, ship it".

The metric is computed via the coincidence-matrix formulation for nominal
data (Krippendorff 2011 eq. 4), with the small-sample (N-1) correction.
Errored verdicts are excluded from the denominator.

## Reproducibility

`temperature=0.0` gives near-deterministic LLM behavior per vendor (cache
behavior varies — DeepSeek and OpenAI are usually deterministic at temp=0;
OpenRouter passes through). For paper-grade reproducibility:

```python
critic = Critic(name="..., model="...", temperature=0.0)
# Pin the prompt YAML version:
critic = Critic.from_yaml_prompt(..., yaml_path="prompts/b3_universality_critic@v0.1.yaml")
```

Combine with deterministic aggregation (`voting="unanimous"` or
`voting="majority"` with explicit `priority`) for end-to-end reproducible
runs.

## Error handling

Critic calls catch all exceptions and return
`Verdict(kind="ERROR", error="...")` rather than raising. Aggregation
strategies skip errored verdicts — they don't tank consensus. Inspect
`result.verdicts` for per-critic error strings. JSON parse failures
produce `Verdict(kind="PARSE_FAIL", error="parse_fail")` with the raw
response captured in `raw_response` for audit.

## Legacy API

The original `Reviewer` / `JudgePanel` / aggregation surface is preserved
for backward compatibility with the structural-isomorphism
`v4/scripts/b3_ensemble.py` pipeline. New code should prefer
`Critic` / `Ensemble` / `Verdict`. See `cross_judge/reviewer.py` and
`cross_judge/panel.py` for legacy docstrings.

## License

MIT. See `LICENSE`.

## Citation

If cross-judge contributes to a paper, please cite the structural-isomorphism
project where the multi-vendor ensemble judging pattern + Krippendorff α
reporting were developed:

> dada8899. *Cross-domain structural isomorphism: a universality-class
> taxonomy via multi-vendor LLM ensemble review.* 2026.
> [github.com/dada8899/structural-isomorphism](https://github.com/dada8899/structural-isomorphism)

See also the C1 preprint (linked from the repo README) for the methodology
section's full description of the ensemble + Krippendorff α reporting
protocol.
