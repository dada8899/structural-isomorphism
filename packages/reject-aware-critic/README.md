# reject-aware-critic

**Multi-vendor LLM critic ensemble that rejects 33% of LLM-curated universality classes that single-model critics let through.**

`reject-aware-critic` packages the **B3 within-vendor multi-decoding** and **B4 cross-vendor** critic ensembles from the C4 paper [*A reject-aware pipeline for cross-domain universality discovery*](https://github.com/dada8899/structural-isomorphism/blob/main/paper/c4-reject-aware-pipeline-2026-05-13.md). It is the upstream-applicability layer for LLM-curated taxonomies: where [`cross-judge`](https://github.com/dada8899/structural-isomorphism/tree/main/packages/cross-judge) focuses on P0 reviewer agreement metrics, `reject-aware-critic` focuses on **KEEP / REJECT / SPLIT / MERGE** verdicts on individual candidates — and is specifically tuned to surface the two error patterns single-model critics systematically miss:

- **mechanism-vs-limit-theorem confusion** (e.g. mistaking a Hopf normal form for a universality class)
- **mathematical framework masquerading as universality class** (e.g. a generic copula / decomposition applied to incompatible mechanisms)

On the original 21-class panel, B1 (single Opus) rejected 14.3% of candidates; B3 (3 DeepSeek decodings) rejected 33.3%. The 4 added rejections all matched the prototype trap patterns this package targets.

---

## Install

```bash
pip install reject-aware-critic
```

Python ≥3.10. Depends on `pydantic`, `httpx`, `tenacity` only — no vendor SDKs.

## 30-second demo (offline mock vendor)

```python
from reject_aware_critic import (
    CandidateClass, CriticEnsemble, register_mock_responder,
)
import json

# Offline mock — replace with vendor="deepseek" + DEEPSEEK_API_KEY for real runs.
register_mock_responder(
    "demo",
    lambda model, msgs, t, mt: (
        json.dumps({
            "decision": "REJECT", "confidence": 0.85,
            "rationale": "Generic Hopf normal form — mechanism vs limit theorem.",
            "trap_flags": ["mechanism_vs_limit_theorem"],
        }),
        {"prompt_tokens": 500, "completion_tokens": 80},
    ),
)

candidate = CandidateClass(
    class_id="delay_differential_debt",
    name="Delay Differential Debt",
    shared_equations=["dx/dt = f(x(t-tau))"],
    domains=["macro", "neuro", "ecology"],
    members=["sovereign debt cycle", "neural oscillation", "predator-prey lag"],
)

ensemble = CriticEnsemble.b3(vendor="mock", model="mock-model", mock_responder="demo")
result = ensemble.judge(candidate)

print(result.consensus)            # REJECT
print(result.trap_flags_union)     # ['mechanism_vs_limit_theorem']
print(result.disagreement_signal)  # 0.0 (unanimous)
```

For real LLMs, set the vendor env var and drop `mock_responder=`:

```python
import os
os.environ["DEEPSEEK_API_KEY"] = "sk-..."

ensemble = CriticEnsemble.b3(vendor="deepseek")          # B3: 3 DS decodings
ensemble = CriticEnsemble.b4(["anthropic", "deepseek",   # B4: cross-vendor
                              "kimi", "glm"])
```

## Public API

```python
from reject_aware_critic import (
    Critic,              # single vendor, single decoding
    CriticEnsemble,      # .b3() / .b4() / explicit critics=[...]
    CandidateClass,      # input schema (Pydantic)
    Verdict,             # single-critic output
    EnsembleResult,      # aggregated output
    CostBudgetError,     # raised on max_cost_usd overage
)
```

Critic instantiation:

```python
critic = Critic(
    vendor="deepseek",            # deepseek / anthropic / kimi / glm / openrouter / openai / mock
    model="deepseek-chat",
    persona="rigorous",           # rigorous | lighter | creative_dissenter
    temperature=0.0,
    max_tokens=2000,
    max_cost_usd=0.05,            # raises CostBudgetError on overage
    log_path="critic.jsonl",      # optional JSONL audit log
)
verdict = critic.judge(candidate)
```

## The 4 trap categories

The reject-aware filter (C4 paper §4.3) checks every verdict for four prototype patterns. Critics declare `trap_flags` in the JSON response; the deterministic filter in `filters.py` auto-augments from the rationale text so the LLM forgetting to set a flag still surfaces the trap.

| Flag | Pattern | Example |
|------|---------|---------|
| `mechanism_vs_limit_theorem` | Class is a generic limit theorem (CLT / GEV / Hopf normal form), not a critical-mechanism universality class. | `delay_differential_debt` — a Hopf normal form mistaken for a universality class. |
| `mathematical_framework_masquerading` | Class is built on a generic mathematical framework (copula, decomposition, normal form) applicable to many incompatible mechanisms. | `tail_copula_contagion` — tail copula is a statistical coupling structure, not a dynamical universality class. |
| `surface_similarity_from_heavy_tails` | Members share only a phenomenological signature (heavy tail, scale-free degree distribution) without shared dynamics. | `scale_free_percolation_class` — heavy-tail networks across domains without shared percolation mechanism. |
| `mechanism_dispersion_monolith` | Class lumps together systems whose underlying bistability / criticality mechanisms are mathematically incompatible. | `hysteresis_preisach` (monolithic) — magnetic, traffic, ecological hysteresis under one banner. |

The full reject-aware methodology, the 21-class panel results, and the four prototype demotions are documented in the [C4 paper](https://github.com/dada8899/structural-isomorphism/blob/main/paper/c4-reject-aware-pipeline-2026-05-13.md).

## When to use which ensemble

- **B3** (within-vendor multi-decoding) — cheapest signal, catches within-model confidence drift. Use when you only have one vendor API key.
- **B4** (cross-vendor) — strongest signal, catches architectural disagreement. Use when you have keys for 2+ unrelated vendors and the verdict needs higher confidence.
- **Single `Critic`** — fast and cheap; use as a first-pass filter before invoking the ensemble.

## Cost guardrail

Every `judge()` call estimates USD cost from the server-reported token usage and raises `CostBudgetError` if it exceeds `max_cost_usd` (default $0.05). On a 21-class panel with B3 (3 decodings each), expected cost ≪ $1 per panel using DeepSeek pricing.

## Structured logging

Pass `log_path="critic.jsonl"` to a `Critic` and it appends one JSON line per call — class_id, decision, confidence, trap_flags, elapsed_s, cost_usd, usage, rationale excerpt. Use this for replay / audit / cost monitoring.

## Related

- **[C4 paper](https://github.com/dada8899/structural-isomorphism/blob/main/paper/c4-reject-aware-pipeline-2026-05-13.md)** — methodology and 21-class panel results.
- **[`cross-judge`](https://github.com/dada8899/structural-isomorphism/tree/main/packages/cross-judge)** — sibling package focused on P0 reviewer agreement / Krippendorff alpha rather than KEEP/REJECT/SPLIT/MERGE verdicts.
- **[`soc-pipeline`](https://github.com/dada8899/structural-isomorphism/tree/main/packages/soc-pipeline)** — self-organized-criticality fitting utilities used in the downstream empirical-validation layer.

## License

MIT. See `LICENSE`.
