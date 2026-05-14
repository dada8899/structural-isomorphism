<p align="center">
  <h1 align="center">Structural Isomorphism</h1>
  <p align="center">
    <em>Cross-domain SOC validation + LLM-in-the-loop universality class detection</em>
  </p>
  <p align="center">
    <a href="https://www.python.org/downloads/"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-blue.svg"></a>
    <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg"></a>
    <a href="https://doi.org/10.5281/zenodo.19615170"><img alt="Dataset DOI" src="https://img.shields.io/badge/Dataset_DOI-10.5281%2Fzenodo.19615170-blue.svg"></a>
    <a href="https://beta.structural.bytedance.city"><img alt="Live Demo" src="https://img.shields.io/badge/Live-beta.structural.bytedance.city-2f9e44"></a>
    <a href="https://phase.bytedance.city"><img alt="Phase Detector" src="https://img.shields.io/badge/Phase_Detector-phase.bytedance.city-2f9e44"></a>
    <a href="paper/v0-unified-pipeline-2026-05-13.md"><img alt="Preprint" src="https://img.shields.io/badge/Preprint-arXiv_pending-orange.svg"></a>
    <a href="CITATION.cff"><img alt="Citation" src="https://img.shields.io/badge/Cite-CITATION.cff-blue.svg"></a>
    <a href="#run-the-included-regression-suite"><img alt="Tests" src="https://img.shields.io/badge/tests-48_backend_+_11_e2e-brightgreen.svg"></a>
    <a href="paper/anti-phacking-unified-2026-05-15.md"><img alt="Methodology paper" src="https://img.shields.io/badge/Methodology-Anti--p--hacking-blueviolet.svg"></a>
  </p>
</p>

---

## What is this?

**Structural Isomorphism** investigates whether systems across radically different scientific domains — physics, finance, biology, sociology, neuroscience — share the *same underlying mathematical structure* despite zero surface-level vocabulary overlap. We combine a single ~340-LOC self-organized criticality (SOC) statistical pipeline applied unchanged across thirteen empirical systems with a multi-model LLM critic ensemble that proposes, refines, and falsifies candidate universality classes. This repository contains the validated pipeline, the curated dataset, two public web products (a Perplexity-style search engine and a market phase detector), and the preprints that report the results.

## Why it matters

Universality classes are the most consequential idea in modern statistical physics: a small number of equations govern phase transitions across every empirical domain we have measured carefully enough. We extend that lens past condensed-matter physics into noisy, sparse, high-stakes domains (financial contagion, neural avalanches, DeFi liquidations, biological gene switches) using a falsifiable Clauset-grade pipeline plus pre-registered exponent bands. The result is a reusable infrastructure for testing whether any new empirical domain belongs to a known universality class — without retraining, without ad-hoc per-domain tuning.

## What's in this repo

Three primary artifacts, each independently usable:

### 1. SOC validation pipeline (`v4/lib/soc_pipeline.py`)

A single shared 339-LOC Python module that performs Clauset MLE power-law fitting, lognormal/exponential alternative model comparisons, and pre-registered exponent-band hypothesis testing. Applied unchanged to thirteen empirical systems (USGS earthquakes, S&P 500 returns, Aave/Compound/Maker DeFi liquidations, neural avalanche recordings, wildfire size distributions, solar flares, citation networks, and more) plus four synthetic null controls. The companion preprint reports each system's verdict (PASS / FAIL / INCONCLUSIVE) with full provenance.

### 2. Phase Detector product (`web/phase-detector/` + `phase/`)

A research-preview consumer product that tags 100 publicly listed companies with their current dynamical phase (`stable`, `accumulating`, `near_critical`, `reversed`, `recovering`) using LLM-extracted StructTuple features mapped onto nine universality patterns drawn from cross-domain dynamical systems. Live at [phase.bytedance.city](https://phase.bytedance.city). Methodology paper in [`paper/`](paper/). A v0.1 historical backtest engine runs against a larger 500-ticker S&P 500 universe (see [`v4/product/d1_phase_detector/README_BACKTEST.md`](v4/product/d1_phase_detector/README_BACKTEST.md)).

### 3. Cross-judge methodology (`v4/critics/` + `web/`)

A reproducible workflow for asking the question *"do these two phenomena from different domains share a universality class?"*:

- A heterogeneous ensemble of LLM critics (Claude Sonnet, DeepSeek v4, Kimi K2.5, GLM-5) votes on candidate cross-domain pairs and produces explicit `KEEP / REJECT / SPLIT / MERGE` verdicts. (B3 / B4 stages.)
- A 35-class universality taxonomy with per-class YAML predictions enables falsifiable pre-registration: state the expected exponent band *before* pulling the data.
- A Perplexity-style search interface at [beta.structural.bytedance.city](https://beta.structural.bytedance.city) lets users query in natural language and receive streamed answers grounded in the knowledge base, with citation cards and similarity-ranked cross-domain phenomena.

## Live demos

| Product | URL | What it does |
|---|---|---|
| Structural search | https://beta.structural.bytedance.city | Natural-language query, streamed answer, KB citations, similar phenomena from other domains |
| Phase Detector | https://phase.bytedance.city | 100 companies tagged with dynamical phase + nine universality patterns (500-ticker S&P 500 backtest universe in v0.1) |

## Quick start

```bash
git clone https://github.com/dada8899/structural-isomorphism.git
cd structural-isomorphism
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Run the SOC pipeline on a sample dataset

```python
from v4.lib.soc_pipeline import fit_clauset_powerlaw

# fit a power-law tail with Clauset MLE + xmin selection
result = fit_clauset_powerlaw(observations=my_event_sizes)
print(f"alpha = {result.alpha:.3f}, xmin = {result.xmin}")
print(f"vs lognormal: log-likelihood ratio = {result.lr_lognormal:.3f}")
print(f"in pre-registered band [{lo}, {hi}]? {lo <= result.alpha <= hi}")
```

### Verify thirteen systems at once

```bash
v4 status                      # show pass/fail across all 13 systems + 4 nulls
v4 validate soc-earthquakes    # re-run a single system
v4 list                        # enumerate all registered systems
```

### Run the included regression suite

```bash
.venv/bin/python -m pytest v4/tests/sanity -m sanity -q
# 38 sanity tests, ~3.6s — guards exponent bands, hash invariants,
# null-control rejection, schema validation.
```

### Reproduce a validation paper

Three solo arXiv-format preprints live under [`paper/`](paper/) with full reproduction instructions. The unified pipeline preprint is [`paper/v0-unified-pipeline-2026-05-13.md`](paper/v0-unified-pipeline-2026-05-13.md).

## Datasets

| Name | Records | DOI / Location | License |
|---|---|---|---|
| **SIBD-63** seed bank | 63 A-level cross-domain candidate pairs with shared equations + variable mappings | [10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170) | CC-BY-4.0 |
| **SOC validation systems** | 13 empirical event-size distributions + 4 synthetic null controls | [`dataset/v1/`](dataset/v1/) | CC-BY-4.0 |
| **35-class taxonomy YAML** | Per-class universality-class definitions with predicted exponent bands | [`web/frontend/assets/data/universality-classes.json`](web/frontend/assets/data/universality-classes.json) + [`v4/taxonomy/`](v4/taxonomy/) | CC-BY-4.0 |

## Citation

If you use the **SIBD-63 seed bank dataset**:

```bibtex
@dataset{sibd63-2026,
  author       = {Wan, Qinghui},
  title        = {{SIBD-63: A Dataset of A-Level Cross-Domain
                   Structural Isomorphism Discoveries with Shared
                   Equations and Variable Mappings}},
  year         = {2026},
  publisher    = {Zenodo},
  version      = {1.0},
  doi          = {10.5281/zenodo.19615170},
  url          = {https://doi.org/10.5281/zenodo.19615170}
}
```

If you cite the **unified SOC validation pipeline**:

```bibtex
@misc{structural-isomorphism-soc-2026,
  title        = {{Structural Isomorphism: A Cross-Domain
                   Self-Organized Criticality Validation Pipeline}},
  author       = {Wan, Qinghui},
  year         = {2026},
  howpublished = {arXiv:XXXX.XXXXX (preprint forthcoming)},
  url          = {https://github.com/dada8899/structural-isomorphism}
}
```

A machine-readable `CITATION.cff` is provided at the repo root and is honored by GitHub's "Cite this repository" button.

## Repository layout

```
structural-isomorphism/
├── v4/                     # primary research pipeline (Layers 1-5)
│   ├── lib/soc_pipeline.py # the shared 339-LOC Clauset pipeline
│   ├── critics/            # multi-model LLM ensemble (B1 / B3 / B4)
│   ├── taxonomy/           # 35-class per-class YAML taxonomy
│   ├── tests/              # 213 unit + integration + e2e tests
│   ├── results/            # frozen verdicts per system
│   └── cli.py              # `v4` console entry point
├── web/                    # production websites
│   ├── frontend/           # beta.structural.bytedance.city (search engine)
│   ├── backend/            # FastAPI + SSE Perplexity-style /api/ask/stream
│   └── phase-detector/     # phase.bytedance.city (Next.js 14)
├── paper/                  # arXiv-format preprints (v0 unified + 4 solo)
├── dataset/v1/             # frozen dataset bundle (mintable Zenodo DOI)
├── tutorials/              # Jupyter reproduction notebooks
├── plans/                  # research plan documents (Layer 5+, B4+, ...)
└── docs/                   # engineering docs (deployment, security, sessions)
```

For engineering / contributor details (build conventions, deployment SOP, session-by-session retros) see [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/sessions/HANDOFF.md`](docs/sessions/HANDOFF.md). The previous developer-focused README is preserved at [`docs/legacy-readme.md`](docs/legacy-readme.md).

## Status

| Component | Status |
|---|---|
| SOC validation pipeline | Stable. Frozen `soc_pipeline.py` + 38 sanity tests + 213 total tests. Used unchanged across 13 systems. |
| Universality taxonomy (35 classes) | v0.3, B3 consensus complete (5 KEEP / 7 REJECT / 5 SPLIT / 4 MERGE), B4 ensemble run partial. |
| Phase Detector | Live at 100 companies + 500-ticker S&P 500 walk-forward backtest v0.1. Research-preview disclaimer in product. |
| Structural search engine | Live at beta.structural.bytedance.city. Perplexity-style SSE streaming, 244/244 i18n EN keys. |
| Unified preprint (C1) | v0.3.1 ready. arXiv submission pending account setup. |
| Solo arXiv drafts | 4 drafts complete (earthquakes, S&P 500, DeFi cross-protocol, neural avalanches partial). |

## Contributing

We welcome:

- **New empirical domain validations** that fit the SOC / universality framework — fork, drop your dataset into `v4/validation/`, run `v4 validate <your-system>`, open a PR with your verdict and a short writeup.
- **Pre-registered exponent bands** for a candidate universality class not yet in the 35-class taxonomy.
- **Cross-judge critique** — find a pair in SIBD-63 you think is mislabeled? PRs against `v4/critics/` are welcomed.
- **Reproduction reports** — if a result fails to reproduce, file an issue with environment + steps.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, code style, and the PR review process. By contributing you agree to the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

This project is licensed under the MIT License — see [`LICENSE`](LICENSE).

Datasets are released under CC-BY-4.0; see individual dataset cards.

## Acknowledgments

- Base embedding model: [shibing624/text2vec-base-chinese](https://huggingface.co/shibing624/text2vec-base-chinese)
- Training framework: [sentence-transformers](https://github.com/UKPLab/sentence-transformers)
- Statistical methodology: A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," SIAM Review 51(4), 661–703 (2009)
- Universality class concept and naming conventions: M. Scheffer (fold bifurcations), Motter & Lai (network cascades), Gardner & Collins (toggle switches), Diamond & Dybvig (self-fulfilling bank runs)

---

<p align="center">
  <em>If structural isomorphism is real, it should hold without retraining. We are testing that empirically.</em>
</p>
