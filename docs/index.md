---
hide:
  - navigation
---

# Structural Isomorphism

> **Do systems from radically different scientific domains share the same
> underlying mathematical structure?**

A pre-registered, cross-domain validation pipeline for universality classes
in complex systems. One shared Python module
([`v4/lib/soc_pipeline.py`](https://github.com/dada8899/structural-isomorphism/blob/main/v4/lib/soc_pipeline.py),
frozen at commit `7ee228c`) is applied unchanged to thirteen independent
datasets spanning geology, finance, neuroscience, ecology, banking history,
software communities, power grids, and highway traffic — and a growing set
of adversarial pre-registrations that have produced PASS, INCONCLUSIVE, and
FAIL verdicts without per-system tuning.

## Live demos

| Product | URL | What it does |
|---|---|---|
| Structural Search | [beta.structural.bytedance.city](https://beta.structural.bytedance.city){ target=_blank } | Perplexity-style natural-language search over the cross-domain knowledge base. Streamed answer, citation cards, similar phenomena across domains. |
| Phase Detector | [phase.bytedance.city](https://phase.bytedance.city){ target=_blank } | 100 tagged companies + 500-ticker S&P 500 walk-forward backtest. Research preview — *not investment advice*. |

## Get started in 30 seconds

```bash
git clone https://github.com/dada8899/structural-isomorphism.git
cd structural-isomorphism
python -m venv .venv && source .venv/bin/activate
pip install -e .
v4 status                  # show pass/fail across 13 systems + 4 nulls
```

Or run the pipeline programmatically:

```python
from v4.lib.soc_pipeline import fit_clauset_powerlaw

result = fit_clauset_powerlaw(observations=my_event_sizes)
print(f"alpha = {result.alpha:.3f}, xmin = {result.xmin}")
print(f"vs lognormal LR = {result.lr_lognormal:.3f}")
```

See [Getting Started](getting-started.md) for the full walkthrough.

## Three artifacts

<div class="grid cards" markdown>

-   :material-cog-outline: **SOC pipeline**

    ---

    A single shared Clauset MLE module (`v4/lib/soc_pipeline.py`, 339 LOC).
    Runs unchanged across 13 empirical systems and 4 null controls. Reports
    power-law vs lognormal vs exponential, with pre-registered exponent
    bands.

    [:octicons-arrow-right-24: Pipeline docs](pipeline.md)

-   :material-database-outline: **SIBD-63 dataset**

    ---

    63 A-level cross-domain candidate pairs, each with shared equations,
    variable mappings, and provenance. Curated by a multi-model LLM critic
    ensemble (Claude · DeepSeek · Kimi · GLM-5).

    [:octicons-arrow-right-24: Zenodo DOI](https://doi.org/10.5281/zenodo.19615170)

-   :material-rocket-launch-outline: **Phase Detector**

    ---

    A research-preview consumer product. Tags 100 public companies with
    their current dynamical phase (stable / accumulating / near-critical /
    reversed / recovering) against nine universality patterns.

    [:octicons-arrow-right-24: phase.bytedance.city](https://phase.bytedance.city)

</div>

## What this project is

- **A reproducible pipeline.** Clauset–Shalizi–Newman 2009 MLE power-law
  fits with KS-optimal $x_{\mathrm{min}}$, bootstrap confidence intervals,
  Vuong likelihood ratios against lognormal and exponential, Omori–Utsu
  temporal stacking, matched-$n$ synthetic null controls, log-binned
  density estimation, and Bayesian Information Criterion model comparison
  — all in one frozen module.
- **A pre-registration discipline.** Predicted exponent bands are committed
  to git **before** data acquisition. Once pushed, bands cannot be silently
  widened post hoc.
- **A cross-judge ensemble.** Multi-model taxonomy review (B3) and
  cross-judge calibration (B4) catch over-claiming on individual systems.
- **A live phase detector.** D1 ships the pipeline as a queryable service
  with a 7-event SSE orchestrator for streaming verdicts.

## Quick links

- [Getting started](getting-started.md) — install and first run.
- [Pipeline](pipeline.md) — the shared analysis stack.
- [Phase Detector](phase-detector.md) — D1 product overview.
- [API reference](api.md) — `/api/ask` and `/api/ask/stream` schemas.
- [Methodology / cross-judge](methodology/cross-judge.md) — B3 and B4
  ensemble methodology.
- [Methodology / pre-registration](methodology/pre-registration.md) — how
  predictions are locked.
- [Papers](papers.md) — preprints including the unified pipeline preprint
  and the CVE falsification.

## Citation

If you reference this work, please cite the unified pipeline preprint:

```bibtex
@unpublished{structural_isomorphism_2026,
  author = {dada8899},
  title  = {Unified pre-registered validation of self-organized criticality
            across thirteen complex systems},
  year   = {2026},
  note   = {Preprint at \url{https://github.com/dada8899/structural-isomorphism}}
}
```

## Status

This is a research repository under active development. The pipeline
library is frozen at commit `7ee228c`; phase papers and pre-registrations
continue to accrete. See [Papers](papers.md) for the current preprint set.
