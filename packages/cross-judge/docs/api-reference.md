# API Reference

Public v0.1 surface of `cross-judge`. Everything documented here is
exported from the top-level `cross_judge` package.

## Critic

### `Critic(name, model, vendor, *, prompt_template=None, system_prompt=None, api_key=None, base_url=None, temperature=0.0, max_tokens=1024, http_client=None)`

One LLM configuration that produces a single `Verdict` per query.

| field | type | meaning |
|---|---|---|
| `name` | str | Unique critic identifier (used in disagreement diagnostics) |
| `model` | str | Vendor model id (e.g. `deepseek-v4-pro`, `gpt-4o`) |
| `vendor` | str | `"deepseek"` \| `"openai"` \| `"openrouter"` \| `"custom"` |
| `prompt_template` | str \| None | `str.format`-style template with `{query}` + optional context keys |
| `system_prompt` | str \| None | Optional system message |
| `api_key` | str \| None | Explicit override; defaults from env per `VENDOR_DEFAULTS` |
| `base_url` | str \| None | Explicit override; defaults from `VENDOR_DEFAULTS` |
| `temperature` | float | Sampling temperature (default `0.0`) |
| `max_tokens` | int | Output token cap |
| `http_client` | httpx.Client \| None | Inject for tests / mocking |

```python
critic.judge(query: str, context: dict | None = None) -> Verdict
```

### `VENDOR_DEFAULTS: dict[str, tuple[str, str]]`

Maps `vendor → (base_url, env_var_name)`. Registry inspected by `Critic` at
construction time so callers don't have to memorise endpoints.

## Ensemble

### `Ensemble(critics: list[Critic], voting: str | VotingStrategy = "majority")`

Multi-critic panel.

```python
ensemble.judge(query: str, context: dict | None = None, query_id: str | None = None) -> EnsembleVerdict
```

The judge fan-outs to all critics, collects per-critic `Verdict`s, applies
the voting strategy, and rolls up disagreement metrics.

## Verdict types

### `VerdictKind`

```python
VerdictKind = Literal["KEEP", "REJECT", "SPLIT", "MERGE", "UNCLEAR", "ERROR", "PARSE_FAIL"]
```

Default vocabulary for the B3 / B4 universality-class review pattern.

### `Verdict` (pydantic.BaseModel)

| field | type | meaning |
|---|---|---|
| `kind` | str | Verdict label (`VerdictKind` recommended) |
| `confidence` | float | 0.0–1.0 self-reported |
| `reasoning` | str | 1–4 sentence rationale |
| `critic_id` | str | Producing critic's name |
| `raw_response` | str \| None | Raw LLM text (audit) |
| `error` | str \| None | Error message; `kind` will be `ERROR` |
| `elapsed_s` | float | Wall-clock seconds of LLM call |

Legacy kwarg aliases accepted: `verdict` → `kind`, `rationale` →
`reasoning`, `reviewer_id` → `critic_id`. Properties of the same names are
also exposed for read paths.

### `EnsembleVerdict` (pydantic.BaseModel)

| field | type | meaning |
|---|---|---|
| `query_id` | str | Caller-supplied id |
| `verdicts` | list[Verdict] | Per-critic, input order |
| `consensus` | str | Rolled-up label |
| `avg_confidence` | float | Mean across non-errored |
| `disagreement` | bool | True iff not all `kind` matched |
| `agreement_pct` | float | Fraction matching consensus |
| `krippendorff_alpha` | float \| None | Inter-rater reliability (None if < 2 valid) |
| `voting` | str | Strategy name |
| `meta` | dict | Caller pass-through |

## Voting strategies

```python
from cross_judge import (
    VOTING_STRATEGIES,         # dict[str, VotingStrategy]
    VotingStrategy,            # Protocol: (verdicts) -> (consensus, agreement_pct)
    get_voting_strategy,       # by name
    majority_vote,             # plurality of non-errored kinds
    unanimous,                 # all-or-UNCLEAR
)
```

## Disagreement metrics

```python
from cross_judge import krippendorff_alpha, agreement_pct

alpha = krippendorff_alpha(labels: list[str])   # [-1, 1], None when < 2 valid
pct   = agreement_pct(labels: list[str])        # [0, 1]
```

## Vendor adapters

```python
from cross_judge import VENDORS, VendorConfig, get_vendor, make_client
```

`VENDORS` is the canonical config registry; `make_client(vendor)` returns
the configured `httpx.Client`. Install `cross-judge[openai]` if you prefer
the official openai-python client; inject it via `Critic(http_client=...)`.

## Legacy API (preserved for v4 callers)

```python
from cross_judge import Reviewer, JudgePanel, EnsembleResult
```

- `Reviewer` — single-model reviewer (predecessor to `Critic`).
- `JudgePanel` — panel of reviewers (predecessor to `Ensemble`).
- `EnsembleResult` — aggregated panel result (predecessor to
  `EnsembleVerdict`).

Aggregation helpers also kept: `AggregationStrategy`, `majority`,
`weighted`, `first_disagreement`, `get_strategy`, `avg_confidence`.

## Version

```python
from cross_judge import __version__   # "0.1.1"
```
