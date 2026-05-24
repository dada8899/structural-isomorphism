# Python Package API Reference

This section documents the public Python APIs for the three PyPI packages
that ship from this repository. Pages here are **auto-generated** from
docstrings and type signatures via [mkdocstrings](https://mkdocstrings.github.io/).

| Package | Install | Purpose |
|---|---|---|
| [`soc-pipeline`](./soc-pipeline.md) | `pip install soc-pipeline` | Clauset-grade power-law fit + bootstrap CI + Vuong LR test + null controls |
| [`cross-judge`](./cross-judge.md) | `pip install cross-judge` | Multi-vendor LLM ensemble-judge with majority / unanimous / Krippendorff metrics |
| [`guarded-llm`](./guarded-llm.md) | `pip install guarded-llm` | Strict JSON LLM calls with schema validation, budget guard, retry policy |

For the hosted **HTTP API** (`POST /api/ask` etc.), see [API reference](../index.md).

## Quick links

- Top-level entry points: [`validate`](./soc-pipeline.md#soc_pipeline.validate),
  [`Ensemble.judge`](./cross-judge.md#cross_judge.Ensemble),
  [`GuardedLLM.call`](./guarded-llm.md#guarded_llm.GuardedLLM)
- Verdict types: [`Verdict`](./soc-pipeline.md#soc_pipeline.Verdict) (soc),
  [`EnsembleVerdict`](./cross-judge.md#cross_judge.EnsembleVerdict) (cross-judge)
- Budget / retry: [`Budget`](./guarded-llm.md#guarded_llm.Budget),
  [`RetryPolicy`](./guarded-llm.md#guarded_llm.RetryPolicy)

## Conventions

- All public names are listed in each package's `__all__`.
- Type hints follow PEP 604 (`X | None`).
- Docstrings follow [Google style](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods).
- Examples in docstrings are doctest-style and runnable.
