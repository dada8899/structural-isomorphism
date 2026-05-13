# Cross-domain SOC validation dataset (v1)

**Release date:** 2026-05-13
**Version:** 1.0.0
**Git commit (bundle origin):** `607906c`
**Source repository:** https://github.com/dada8899/structural-isomorphism
**DOI:** `10.5281/zenodo.PLACEHOLDER` (to be minted — see `MINT_DOI_RUNBOOK.md`)
**License:** CC-BY-4.0 (data) / MIT (code). See `LICENSE`.

---

## 1. Overview

This dataset is a frozen, multi-domain benchmark for **self-organized
criticality (SOC) and related universality-class validation**. It bundles:

- **16 independently-fetched empirical systems** spanning seismology, finance,
  decentralized finance, neuroscience, fire ecology, solar physics, banking,
  open-source software, electrical engineering, web traffic, ecology, traffic
  flow, epidemiology, applied probability, and a composite *universal-collapse*
  panel of 7 SOC systems plotted on a single rescaled axis.
- **4 synthetic null controls** (Gaussian walk, exponential, Poisson
  inter-arrival, Poisson-Omori stack) that the same fitting pipeline correctly
  rejects — these are the "controls" that any cross-domain power-law claim
  needs in order to defend against false positives.
- **A 35-class universality-class taxonomy** with two layers of LLM-critic
  curation: B1 single-Opus and B3 three-DeepSeek ensemble. Each class lists
  display name, shared normal-form equation, key invariants, positive/negative
  examples, and the ensemble verdict (KEEP / REJECT / SPLIT / MERGE / UNCLEAR).
- **The frozen fitting pipeline** — `soc_pipeline.py` (Clauset MLE + bootstrap
  CI + tail-fit diagnostics), `llm_guardrail.py` (structured-output schema +
  abstention guardrails for the LLM curator), and `b3_ensemble.py` (the
  3-model DeepSeek ensemble critic).
- **A 17-test sanity suite** that regression-tests each system's headline α /
  τ / b-value / Omori-p against its frozen target, plus the null controls and
  the universal-collapse panel.

It is suitable for:

1. **Cross-domain SOC validation** — drop in a new system, run
   `soc_pipeline.py`, compare to the 16 baselines.
2. **Pipeline reproducibility benchmarking** — regenerate every reported α,
   τ, b-value, Omori-p from the raw data in this bundle in < 1 hour on a
   laptop.
3. **LLM ensemble-critic methodology research** — full B1 single-Opus
   verdicts + B3 three-model ensemble verdicts + 21 final-curated class
   YAMLs are included with all three reviewer rationales preserved.
4. **Negative-control / false-positive analysis** — the 4 synthetic nulls
   make it cheap to test whether a new candidate is statistically
   distinguishable from chance.

---

## 2. Bundle layout

```
dataset/v1/
├── README.md                          (this file)
├── LICENSE                            (CC-BY-4.0 data / MIT code)
├── CITATION.cff                       (citation metadata)
├── MINT_DOI_RUNBOOK.md                (steps to mint Zenodo DOI)
├── manifest.json                      (file list + sha256 + sizes + counts)
├── systems/                           (16 verified universality systems)
│   ├── 01_earthquake/                 (USGS, M ≥ 3.5, 2020-2025, n = 37k)
│   ├── 02_stockmarket/                (S&P 500 daily returns)
│   ├── 03_defi/                       (Aave/Compound/Maker liquidations, 43k)
│   ├── 04_neural/                     (Plenz-style avalanches, 5 bin factors)
│   ├── 05_wildfire/                   (NIFC US fires, 21k)
│   ├── 06_solar/                      (GOES X-ray flares 2000-2016, 30k)
│   ├── 07_bank_failures/              (FDIC 1934-2026, 3960 failures)
│   ├── 08_github_stars/               (8398 repos, stratified)
│   ├── 09_power_grid/                 (NERC disturbances)
│   ├── 10_wikipedia_views/            (2023-2024 pageviews)
│   ├── 11_hawkes_omori/               (synthetic Hawkes baseline)
│   ├── 12_scheffer_lake/              (Scheffer-style regime shift)
│   ├── 13_hysteresis_traffic/         (US-101 NGSIM q-ρ)
│   ├── 14_sir_contagion/              (SIR epidemic synthetic)
│   ├── 15_tail_copula/                (joint tail copula)
│   └── universal_collapse/            (Phase 12 composite 7-system panel)
│       └── (each system: data/ symlink → v4/validation/<src>/,
│           paper.md, results.json, VERDICT-*.md when applicable)
├── null_controls/                     (4 synthetic nulls — must be rejected)
│   ├── gaussian/results.json
│   ├── exponential/results.json
│   ├── poisson/results.json
│   ├── poisson_omori/results.json
│   ├── _registry.jsonl                (registry of all 4 cases)
│   ├── _all_null_results.json         (full pipeline output)
│   ├── _generator.py                  (regenerates the nulls from seed)
│   └── _VERDICT.md
├── taxonomy/                          (B1 ⊗ B3 universality-class verdicts)
│   ├── B3_taxonomy_v2.jsonl           (final 21 classes, plurality verdict)
│   ├── B3_ensemble_review.jsonl       (per-reviewer rationales, 63 rows)
│   ├── B3_ensemble_summary.md         (human summary)
│   ├── classes/                       (35 YAML files: curated + variants)
│   ├── universality_classes.yaml      (top-level class index)
│   └── SCHEMA.md                      (taxonomy YAML schema)
├── pipeline/                          (frozen pipeline scripts)
│   ├── README.md                      (how to reproduce — see § 6 below)
│   ├── soc_pipeline.py                (Clauset MLE + bootstrap CI, 339 LoC)
│   ├── llm_guardrail.py               (structured-output guard, 441 LoC)
│   └── b3_ensemble.py                 (3-model DeepSeek critic, 584 LoC)
├── tests/                             (sanity / regression / integration)
│   ├── sanity/                        (17 test files — see § 7)
│   ├── integration/                   (cross-module integration tests)
│   ├── conftest.py
│   └── sanity_helpers.py
└── scripts/                           (bundle-build utilities)
    ├── build_bundle.py                (populates systems/ from v4/validation/)
    ├── build_nulls.py                 (splits null registry into per-case)
    └── compute_manifest.py            (regenerates manifest.json)
```

### File and size summary

- **Files:** 244
- **Total size:** ~99 MB (uncompressed, following symlinks)
- **Storage layout:** Symlinks point from `dataset/v1/.../data/` into
  `v4/validation/.../`. This means the bundle adds essentially zero new
  bytes to the repo while still presenting the canonical Zenodo layout
  when followed. When you publish to Zenodo, the runbook (`MINT_DOI_RUNBOOK.md`)
  describes producing a flattened tarball/zip that dereferences the symlinks.

### Headline counts

| Bucket                    | Count |
|---------------------------|-------|
| Verified systems          | 16    |
| Synthetic null controls   | 4     |
| Universality-class YAMLs  | 35    |
| Sanity regression tests   | 17    |

Note on "13 systems": the canonical 13 referred to in the C1 manuscript is
the headline subset of `systems/01_*` through `systems/13_*`. Slots 14–15
(SIR contagion, tail copula) and the `universal_collapse/` composite are
included for completeness and as extended controls; they are not part of
the 13 headline universality-class membership claims.

---

## 3. Per-system file convention

Each `systems/<slot>/` directory contains:

| File              | Description |
|-------------------|-------------|
| `data/`           | Symlink into `v4/validation/<src>/` — full raw data, fetch scripts, intermediate jsonl/parquet/png artefacts |
| `paper.md`        | Self-contained arXiv-style companion paper draft (~3-8k words) — provenance, fit method, α/τ/b-value with CI, comparison to literature band, caveats |
| `results.json`    | Aggregated JSON of all fit results (gr_results.json + omori_results.json + per-protocol fits, depending on system) |
| `VERDICT-*.md`    | Reviewer-style verdict (KEEP / NEEDS-WORK / REJECT) for the system. Not all systems have one; absent ⇒ baseline KEEP |

To find the raw event-level data for a system, follow `systems/<slot>/data/`
and look for `*.jsonl` / `*.csv` / `*.parquet`. Every system also includes
the `fetch_*.py` script that pulled the raw data so you can re-fetch.

---

## 4. Per-null-control file convention

Each `null_controls/<case>/` directory contains a single `results.json`
with the pipeline's full output: α estimate, σ_α, x_min, n_tail,
likelihood-ratio tests (vs lognormal, vs exponential), and the
`pipeline_verdict: rejected` flag.

The aggregate `_all_null_results.json` and `_registry.jsonl` give the same
data in two flat formats convenient for batch comparison. `_generator.py`
is the reproducible synth (rng_seed = 42) that produced the four cases.

---

## 5. Usage

### Quick verification

```bash
git clone https://github.com/dada8899/structural-isomorphism.git
cd structural-isomorphism
python3 dataset/v1/scripts/compute_manifest.py
# regenerates manifest.json — should show 244 files / 99 MB / 16 / 4 / 35 / 17
```

### Reproduce a single system's headline result

```bash
cd structural-isomorphism
python3 dataset/v1/systems/01_earthquake/data/gutenberg_richter.py
# expected: b ≈ 1.084 (CI [1.073, 1.094]) — matches paper.md
```

See `pipeline/README.md` for the full reproducibility runbook.

### Apply the frozen pipeline to a new system

```python
# from anywhere inside the repo
import sys
sys.path.insert(0, "dataset/v1/pipeline")
from soc_pipeline import fit_powerlaw_clauset

# my_events = np.array([...])   # your event-size array
result = fit_powerlaw_clauset(my_events, bootstrap_n=100)
print(result["alpha"], result["xmin"], result["vs_lognormal_p"])
```

### Run the regression sanity suite

```bash
cd structural-isomorphism
pytest dataset/v1/tests/sanity/ -q
# 17 test files; ~30s on laptop; all should pass at git commit 607906c
```

---

## 6. Citation

If you use this dataset, please cite it via `CITATION.cff`. Once the DOI is
minted, the canonical citation will be:

> dada8899 (2026). *Cross-domain SOC validation dataset (v1)*. Zenodo.
> https://doi.org/10.5281/zenodo.XXXXXXX

Until the DOI is minted, please cite by git commit:

> dada8899 (2026). *Cross-domain SOC validation dataset (v1)*. GitHub.
> https://github.com/dada8899/structural-isomorphism @ commit 607906c.

### Companion papers

The bundle's companion manuscript ("A cross-domain SOC + critical-systems
benchmark with synthetic nulls and multi-model class curation", ~5k words)
is in active preparation for *Scientific Data* (Nature Publishing Group) /
*Earth System Science Data* (Copernicus). When published, please cite
that paper in addition to the dataset DOI.

---

## 7. License + attribution

- **Data:** CC-BY-4.0 (this includes systems/*/data/, taxonomy/, null_controls/,
  every `results.json` and `paper.md`).
- **Code:** MIT (pipeline/, scripts/, tests/).

Every paper.md inside `systems/<slot>/` lists the upstream primary data
provider (USGS, NIFC, GOES, FDIC, Compound Labs subgraph, etc.). If you
redistribute the bundle or build on it, please also credit those primary
sources where applicable.

---

## 8. Contact + provenance

- **Authors:** dada8899 (Independent Research)
- **Issue tracker:** https://github.com/dada8899/structural-isomorphism/issues
- **Bundle assembled:** 2026-05-13 by W8-A subagent
  (`v4/session3-w8a-zenodo-dataset` branch)
- **Source commit:** 607906c (main HEAD)
- **Reviewers consulted at assembly time:** none yet — this bundle is the
  pre-mint snapshot. Reviewer feedback will fold into v1.1.

---

## 9. Acknowledgments

- USGS Earthquake Catalog, NOAA GOES X-ray flare catalog, FDIC failed-bank
  list, NIFC fire database, Compound Labs and Aave subgraphs, Wikimedia
  pageviews API — the upstream primary data providers.
- The structural-isomorphism project's V1/V2/V3 retrieval pipelines and
  V4 universality-class engine, on which the curated 35-class taxonomy
  builds.
- DeepSeek v4 family (pro 0.0, flash 0.0, pro 0.6 adversarial-dissenter) —
  the B3 ensemble critic.
- Anthropic Claude Opus 4.6 — the B1 single-reviewer baseline and the
  multi-agent assembly tooling.

---

## 10. Known limitations

1. The B3 ensemble is *same-family* (3 DeepSeek configs, not 3 vendors).
   This is a real limitation, discussed in the companion paper §5.
   OpenRouter access to Anthropic/Gemini from CN IPs was region-blocked
   at assembly time.
2. Slots 11 (Hawkes-Omori) and 15 (tail copula) are largely synthetic /
   methodological systems, not empirical SOC validations. They are
   included as pipeline regression anchors, not as headline universality
   claims.
3. Symlinks rely on the repo layout. For Zenodo upload, see
   `MINT_DOI_RUNBOOK.md` for the dereferenced-tarball recipe.
4. Some systems (e.g., 04_neural) split results across multiple
   `bf_<binfactor>_fit.json` files (one per bin factor sweep);
   `results.json` aggregates these but the canonical-published numbers
   are derived from `bf_4` (see `paper.md`).
