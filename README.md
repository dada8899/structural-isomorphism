# Structural Isomorphism

**English** | [简体中文](README-zh.md)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Dataset DOI](https://img.shields.io/badge/Dataset_DOI-10.5281%2Fzenodo.19615170-blue.svg)](https://doi.org/10.5281/zenodo.19615170)
[![Preprint](https://img.shields.io/badge/Preprint-arXiv_pending-orange.svg)](paper/v0-unified-pipeline-2026-05-13.md)
[![Cite](https://img.shields.io/badge/Cite-CITATION.cff-blue.svg)](CITATION.cff)
[![Methodology](https://img.shields.io/badge/Methodology-Anti--p--hacking-blueviolet.svg)](paper/anti-phacking-unified-2026-05-15.md)
[![Tests](https://img.shields.io/badge/tests-48_backend_+_11_e2e-brightgreen.svg)](#tests)
[![Live: Structural Search](https://img.shields.io/badge/Live-beta.structural.bytedance.city-2f9e44)](https://beta.structural.bytedance.city)
[![Live: Phase Detector](https://img.shields.io/badge/Live-phase.bytedance.city-2f9e44)](https://phase.bytedance.city)

> **Do systems from radically different scientific domains share the same underlying mathematical structure?**

Universality classes are one of the most consequential ideas in modern statistical physics: a small number of equations describe phase transitions in materials, magnets, fluids, and lattices that look nothing alike. This project tests whether the same idea extends — without per-domain tuning — to noisy, sparse, high-stakes empirical domains: financial contagion, neural avalanches, DeFi liquidations, wildfires, biological gene switches, citation cascades.

The answer is *not* "yes" by assumption. We treat it as a falsifiable question: pre-register exponent bands, fit the same Clauset MLE pipeline across every domain, and report PASS / FAIL / INCONCLUSIVE with full provenance.

## What's in this repo

<table>
<tr>
<td width="33%" valign="top">

### 1. SOC pipeline
A single shared Clauset MLE module (`v4/lib/soc_pipeline.py`, 339 LOC). Runs unchanged across 13 empirical systems and 4 null controls. Reports power-law vs lognormal vs exponential, with pre-registered exponent bands.

[**→ Pipeline docs**](docs/pipeline.md)

</td>
<td width="33%" valign="top">

### 2. SIBD-63 dataset
63 A-level cross-domain candidate pairs, each with shared equations, variable mappings, and provenance. Curated by a multi-model LLM critic ensemble (Claude · DeepSeek · Kimi · GLM-5).

[**→ Zenodo DOI**](https://doi.org/10.5281/zenodo.19615170)

</td>
<td width="33%" valign="top">

### 3. Phase Detector
A research-preview consumer product. Tags 100 public companies with their current dynamical phase (stable / accumulating / near-critical / reversed / recovering) against nine universality patterns.

**Backtest v0.1 (1000-ticker walk-forward, 2020-2025)**: Sharpe lift of `near_critical` cohort vs equal-weight benchmark = **−0.07** (p = 0.57, NOT significant). Published openly per W7-D Track A → positioning pivot to structured-research-narrative. See [`/backtest`](https://phase.bytedance.city/backtest) for the full transparency report.

[**→ phase.bytedance.city**](https://phase.bytedance.city)

</td>
</tr>
</table>

## Quickstart

```bash
git clone https://github.com/dada8899/structural-isomorphism.git
cd structural-isomorphism
python -m venv .venv && source .venv/bin/activate
pip install -e .
v4 status                           # show pass/fail across 13 systems + 4 nulls
```

Or run the pipeline programmatically:

```python
from v4.lib.soc_pipeline import fit_clauset_powerlaw

result = fit_clauset_powerlaw(observations=my_event_sizes)
print(f"alpha = {result.alpha:.3f}, xmin = {result.xmin}")
print(f"vs lognormal LR = {result.lr_lognormal:.3f}")
```

## Live demos

| Product | URL | What it does |
|---|---|---|
| Structural Search | [beta.structural.bytedance.city](https://beta.structural.bytedance.city) | Perplexity-style natural-language search over the cross-domain knowledge base. Streamed answer, citation cards, similar phenomena across domains. |
| Phase Detector | [phase.bytedance.city](https://phase.bytedance.city) | 100 tagged companies + 1000-ticker (SP500 + R1000 supplement) walk-forward backtest v0.1 (null result, Sharpe lift −0.07, p = 0.57). Research preview — not investment advice. |

## Tests

```bash
pytest v4/tests/sanity -m sanity -q     # 38 sanity tests, ~3.6s
pytest -m "not e2e"                     # full backend, no live network
pytest -m e2e                           # live deployments (slow, may flake)
```

CI runs the sanity + integration suites on every PR. The e2e suite runs nightly against prod.

## Methodology

The pipeline is the *same* function applied across every system — no per-domain hyperparameters. Three commitments make the framework falsifiable rather than confirmatory:

- **Pre-registered exponent bands.** Every claimed universality class declares its expected power-law exponent *before* we touch new data. A fit outside the band is recorded as FAIL, not retroactively re-classified.
- **Null controls.** Four synthetic nulls (uniform, exponential, lognormal, shuffled) are run through the same pipeline. Any framework that does not reject them is broken.
- **Cross-judge ensemble.** A heterogeneous LLM critic ensemble (Claude Sonnet, DeepSeek v4, Kimi K2.5, GLM-5) votes on candidate cross-domain pairs and produces explicit `KEEP / REJECT / SPLIT / MERGE` verdicts. No single model can wave a pair through.

Reference: A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Review* 51(4), 661–703 (2009). See also [`paper/anti-phacking-unified-2026-05-15.md`](paper/anti-phacking-unified-2026-05-15.md) for the anti-p-hacking discipline applied to LLM-in-the-loop science.

## Datasets

| Name | Records | Location | License |
|---|---|---|---|
| **SIBD-63 seed bank** | 63 A-level cross-domain pairs | [10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170) | CC-BY-4.0 |
| **SOC validation systems** | 13 empirical + 4 null distributions | [`dataset/v1/`](dataset/v1/) | CC-BY-4.0 |
| **Universality taxonomy** | 23 classes, pre-registered bands | [`web/frontend/assets/data/universality-classes.json`](web/frontend/assets/data/universality-classes.json) | CC-BY-4.0 |

Full dataset card: [`dataset_card.md`](dataset_card.md). Model card: [`model_card.md`](model_card.md).

## Citation

```bibtex
@dataset{sibd63-2026,
  author    = {Wan, Qinghui},
  title     = {{SIBD-63: A Dataset of A-Level Cross-Domain Structural
                Isomorphism Discoveries with Shared Equations and
                Variable Mappings}},
  year      = {2026},
  publisher = {Zenodo},
  version   = {1.0},
  doi       = {10.5281/zenodo.19615170},
  url       = {https://doi.org/10.5281/zenodo.19615170}
}

@misc{structural-isomorphism-soc-2026,
  title        = {{Structural Isomorphism: A Cross-Domain
                   Self-Organized Criticality Validation Pipeline}},
  author       = {Wan, Qinghui},
  year         = {2026},
  howpublished = {arXiv:XXXX.XXXXX (preprint forthcoming)},
  url          = {https://github.com/dada8899/structural-isomorphism}
}
```

A machine-readable [`CITATION.cff`](CITATION.cff) is provided at the repo root and is honored by GitHub's "Cite this repository" button.

## Repository layout

```
structural-isomorphism/
├── v4/                     research pipeline (Layers 1-5)
│   ├── lib/soc_pipeline.py     the shared 339-LOC Clauset pipeline
│   ├── critics/                multi-model LLM ensemble (B1 / B3 / B4)
│   ├── taxonomy/               per-class YAML predictions
│   ├── tests/                  213 unit + integration + e2e tests
│   ├── results/                frozen verdicts per system
│   └── cli.py                  `v4` console entry point
├── web/                    production websites
│   ├── frontend/               beta.structural.bytedance.city
│   ├── backend/                FastAPI + SSE /api/ask/stream
│   └── phase-detector/         phase.bytedance.city (Next.js 14)
├── paper/                  arXiv-format preprints
├── dataset/v1/             frozen dataset bundle (Zenodo)
├── tutorials/              Jupyter reproduction notebooks
└── docs/                   engineering + methodology docs
```

For contributor details — build conventions, deployment SOP, session retrospectives — see [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/sessions/HANDOFF.md`](docs/sessions/HANDOFF.md). The original dev-focused README is preserved at [`docs/legacy-readme.md`](docs/legacy-readme.md).

## Status

| Component | Status |
|---|---|
| SOC pipeline | Stable. Frozen module + 38 sanity tests + 213 total. |
| Universality taxonomy | v0.3, B3 consensus complete, B4 ensemble run partial. |
| Phase Detector | Live: 100 companies + 1000-ticker walk-forward backtest v0.1 (null result published openly). |
| Structural Search | Live: SSE streaming, full EN i18n (244/244 keys). |
| Unified preprint (C1) | v0.3.1 ready; arXiv submission pending. |
| Solo arXiv drafts | 4 complete (earthquakes, S&P 500, DeFi, neural). |

## Contributing

We welcome:

- **New domain validations** — fork, drop your dataset into `v4/validation/`, run `v4 validate <your-system>`, open a PR with the verdict and a short writeup.
- **Pre-registered exponent bands** for candidate universality classes not yet in the taxonomy.
- **Cross-judge critique** — found a SIBD-63 pair you think is mislabeled? PRs against `v4/critics/` are welcome.
- **Reproduction reports** — if a result fails to reproduce, file an issue with environment and steps.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, code style, and the PR review process. By contributing you agree to the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

Code: MIT — see [`LICENSE`](LICENSE).
Datasets: CC-BY-4.0 — see individual dataset cards.

## Acknowledgments

- Statistical methodology: A. Clauset, C. R. Shalizi, and M. E. J. Newman (2009).
- Universality class concepts: M. Scheffer (fold bifurcations), Motter & Lai (network cascades), Gardner & Collins (toggle switches), Diamond & Dybvig (self-fulfilling bank runs).
- Base embedding model: [shibing624/text2vec-base-chinese](https://huggingface.co/shibing624/text2vec-base-chinese).
- Framework: [sentence-transformers](https://github.com/UKPLab/sentence-transformers).

---

<sub><em>If structural isomorphism is real, it should hold without retraining. We are testing that empirically.</em></sub>
