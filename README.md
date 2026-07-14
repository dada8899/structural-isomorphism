# Structural Isomorphism

**English** | [简体中文](README-zh.md)

> **Current status (2026-07-11).** This repository is a research/product
> workbench, not a validated universality map or investment system. The
> production search artifact contains 4,443 KB records; Phase Detector is a
> 597-ticker demo snapshot with a published null backtest. The strongest
> defensible contribution is the preregistered, reject-aware validation
> protocol. See [`NEXT_SESSION.md`](NEXT_SESSION.md) for operational truth.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Dataset DOI](https://img.shields.io/badge/Dataset_DOI-10.5281%2Fzenodo.19615170-blue.svg)](https://doi.org/10.5281/zenodo.19615170)
[![Preprint](https://img.shields.io/badge/Preprint-arXiv_pending-orange.svg)](paper/v0-unified-pipeline-2026-05-13.md)
[![Cite](https://img.shields.io/badge/Cite-CITATION.cff-blue.svg)](CITATION.cff)
[![Methodology](https://img.shields.io/badge/Methodology-Anti--p--hacking-blueviolet.svg)](paper/anti-phacking-unified-2026-05-15.md)
[![Tests](https://img.shields.io/badge/tests-48_backend_+_11_e2e-brightgreen.svg)](#tests)
[![Coverage](https://img.shields.io/badge/coverage-85.6%25-brightgreen.svg)](.github/workflows/coverage.yml)
[![A11y](https://img.shields.io/badge/a11y-WCAG_2.1_AA-brightgreen.svg)](docs/accessibility/a11y-report-2026-05-15.md)
[![Performance](https://img.shields.io/badge/Performance-CWV_Good_(all_pages)-brightgreen.svg)](docs/performance/perf-fixes-2026-05-15.md)
[![Live: Structural Search](https://img.shields.io/badge/Live-beta.structural.bytedance.city-2f9e44)](https://beta.structural.bytedance.city)
[![Live: Phase Detector](https://img.shields.io/badge/Live-phase.bytedance.city-2f9e44)](https://phase.bytedance.city)

> **We test whether cross-domain systems share measurable scaling signatures — and publish PASS, FAIL, NULL and INCONCLUSIVE results. The strongest current contribution is the reject-aware protocol, not a verified map of universality classes.**

Universality classes are one of the most consequential ideas in modern statistical physics: a small number of equations describe phase transitions in materials, magnets, fluids, and lattices that look nothing alike. This project tests whether the same idea extends — without per-domain tuning — to noisy, sparse, high-stakes empirical domains: financial contagion, neural avalanches, DeFi liquidations, wildfires, biological gene switches, citation cascades.

The answer is *not* "yes" by assumption. We treat it as a falsifiable question: pre-register exponent bands, fit the same Clauset MLE pipeline across every domain, and report PASS / FAIL / INCONCLUSIVE with full provenance. When a hypothesis fails — including our own consumer-facing one — we publish the failure.

**Historical research snapshot: 2026-05-25 (not current production evidence)**
- 27 (v0.3) + 18 (v0.4 Wave 2) = **45 SOC validation systems** across textbook + reflexive + reject-confirm classes (KPZ / DP / RFIM / Manna / Oslo / Tracy-Widom + 18 new)
- **4888 main KB + 300 long-tail (Wave 3C) + 145 Wave 2 entries pending merge** cross-domain knowledge base entries
- 3 PyPI packages live (`soc-pipeline` / `cross-judge` / `guarded-llm`); `reject-aware-critic` v0.1.0 ready (50/50 tests passing)
- C1 unified preprint v0.4 draft (459 lines, §3.5 "Completing the taxonomy"); v0.3 closed 9/9 P0 reviewer concerns, v0.4 batch closed 18/18
- Taxonomy v0.4: **26 internally reviewed candidate classes + 5 SPLIT decisions + 1 MERGE recommendation**; these are not 26 independently verified mechanisms
- One published null result: walk-forward backtest Sharpe lift = **−0.23**

**Status as of 2026-05-26 (v0.5-draft, transitional — see [paper/v0.5-draft/](paper/v0.5-draft/))**

The v0.5 draft consolidates SESSION-25 work since the v0.4 cut. v0.4 outputs above are unchanged; v0.5 adds three methodology increments, one new class promotion, and one eval-specific universality finding:

- **19 candidate classes in the v0.5 research ledger** (+1): these are not 19 independently confirmed empirical mechanisms. Several rely on synthetic or literature-calibrated anchors; `aggregation_kinetics` remains a candidate scaling/mechanism class pending direct held-out replication.
- **Legacy internal PASS count (submission-blocked)**: the v0.5 draft counted 11 PASS-CONFIRMED-or-stronger, but `schelling_credible_commitment` conflicts with the B1 taxonomy and the real WTO sign reversal. It must be excluded from universality PASS counts pending external review.
- **3 methodology increments** (§3.6.5 (s\*, k) reparametrisation / §3.6.6 multilayer test pattern / §3.6.7 head-vs-tail-aware LLM validator) with one full applicability retrospective and three pre-registrations under [paper/v0.5-draft/preregistrations/](paper/v0.5-draft/preregistrations/).
- **Pythia LAMBADA cross-fit (§4)**: 100 % real per-checkpoint evaluation across 8 sizes × 27 checkpoints. v1 (L∞ free) and v2 (L∞ ∈ [1.0, 5.0]) both deliver TIGHT_UNIVERSALITY (CV ≈ 0.12). **The TIGHT verdict is eval-specific**: pooled across LAMBADA + train-loss sources, CV blows out to 0.58–1.49. The v0.4 BROAD_SPREAD verdict was an artefact of mixed 3-real + 3-synthetic train-loss provenance; the universality claim is a property of *the LAMBADA-OpenAI loss curve*, not of the scaling-law family in general.
- **arXiv status**: v0.4 preprint submission pending user action; v0.5 draft is *not* a submission, only an extension. See `release/arxiv-submission-receipt.txt` (to be populated).
- **No new PyPI packages**; no new datasets; v0.5 inherits v0.4's `dataset/v1/` and the three published PyPI packages unchanged.

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

### 3. Phase Detector (research preview)
A null-result research preview. The live site exposes a frozen 597-ticker
demo snapshot. Its walk-forward v0.2 analysis found no predictive alpha;
Sharpe lift of the `near_critical` cohort vs equal-weight benchmark was
**−0.23** and alpha was not significant.

Published openly as a transparency case study in how cross-domain frameworks should *not* be marketed as alpha tools. See [`/backtest`](https://phase.bytedance.city/backtest) for the full report.

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
| Phase Detector | [phase.bytedance.city](https://phase.bytedance.city) | Frozen 597-ticker demo research snapshot + transparent v0.2 null backtest. Not live data or investment advice. |

### On negative results

Cross-domain universality claims have a long history of being over-generated and under-checked: a striking diagram travels faster than the null control behind it. We publish the failures — including our own consumer-facing backtest — because a framework that cannot report rejections cannot be trusted to report acceptances. Reject-aware is what makes the rest of the repo worth reading.

## API reference

- **HTTP API**: production API discovery is intentionally disabled; use the versioned repository reference at [`docs/api/index.md`](docs/api/index.md).
- **Python packages** (`soc-pipeline`, `cross-judge`, `guarded-llm`): auto-generated from docstrings at [docs/api/packages/](docs/api/packages/index.md). Hosted: <https://dada8899.github.io/structural-isomorphism/api/packages/>.

## Tests

```bash
make test-fast          # root offline baseline
make verify-release     # API artifacts + backend/packages/retrieval + browser + Phase build
make test-e2e           # live deployments (non-blocking signal in CI)
```

CI runs the sanity + integration suites on every PR. The e2e suite runs nightly against prod.

## Methodology

The pipeline is the *same* function applied across every system — no per-domain hyperparameters. Three commitments make the framework falsifiable rather than confirmatory:

- **Timestamped pre-registrations where available.** CVE, FDNY and WSB predictions were committed before their recorded runs. The broader historical taxonomy sweep was not uniformly preregistered and must not be described as such.
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

```

No paper DOI or arXiv identifier has been assigned. Cite the versioned dataset
above or the repository commit; do not invent a preprint identifier.

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
| Phase Detector | Live 597-ticker demo snapshot; v0.2 null result published openly. |
| Structural Search | Live with a checksum-verified 4,443-record artifact; individual mappings have mixed provenance and English retrieval remains below the quality gate. |
| Unified preprint (C1) | Reviewer-readable draft; do not submit before claim/evidence and external review gates pass. |
| Research drafts | Four internal domain drafts; none should be represented as an accepted or externally reviewed arXiv paper. |

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
