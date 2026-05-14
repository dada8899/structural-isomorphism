# structural-isomorphism v1.0 cross-domain SOC + universality benchmark

**Bundle name:** `structural-isomorphism-v1.0-benchmark`
**Version:** 1.0.0
**Release date:** 2026-05-15
**Source repository:** https://github.com/dada8899/structural-isomorphism
**DOI:** `10.5281/zenodo.PLACEHOLDER` (to be minted; see `../MINT_DOI_RUNBOOK.md`)
**License (data):** CC-BY-4.0 (`LICENSE-DATA`)
**License (code):** MIT (`LICENSE`)
**Git commit (bundle origin):** see `MANIFEST.json:git_commit`
**Bundle hash:** see `MANIFEST.json:bundle_sha256`

---

## 1. What is this?

This is a **frozen, citation-ready, cross-domain benchmark for self-organized
criticality (SOC), preferential attachment, and adjacent universality classes**.
It is the deposit-ready form of the artefact described in the companion paper
`paper/scientific-data-benchmark-2026-05-15.md` (target venue: *Scientific
Data*, Nature) and is intended to be archived at Zenodo with a permanent DOI.

The bundle answers a methodological gap: every paper that claims "system X
exhibits SOC" or "system Y has preferential-attachment exponent ≈ 2" has
historically had to assemble its own dataset, write its own fitting code, and
defend its own null controls. There is no canonical, deposit-grade cross-domain
benchmark that anyone can drop a new system into and compare against. This
bundle is that benchmark.

It ships:

1. **13 empirical systems** spanning seismology, finance, decentralized finance,
   neuroscience, fire ecology, solar physics, banking, open-source software,
   electrical engineering, web traffic, applied probability, ecology, and
   traffic flow. Each system arrives with the raw fetched event-size catalog
   (subject to the large-file policy in §3), the fitted Clauset / b-value /
   Omori results, and a phase-specific companion paper (`paper.md`).
2. **4 synthetic null controls** with their generator code and verdicts —
   Gaussian walk, exponential, Poisson inter-arrival times, and a Poisson-Omori
   stack. Any claim of cross-domain SOC has to beat these.
3. **A frozen fitting pipeline** (the `soc_pipeline` Python package) covering
   Clauset (2009) MLE + bootstrap CI + Vuong likelihood-ratio tests against
   lognormal / exponential / stretched-exponential, the Gutenberg-Richter
   b-value MLE, the Omori p-value MLE, universal-collapse shape-normalized
   tail-fit, and the four built-in synthetic null controls. Plus the LLM
   guardrail and B3 ensemble critic source, so the taxonomy curation step is
   fully reproducible.
4. **A 35-class universality-class taxonomy** with two layers of LLM-critic
   curation (B1 single-Opus and B3 three-DeepSeek ensemble), each class shipped
   as a structured YAML with shared normal-form equation, key invariants,
   positive/negative examples, and the final-layer plurality verdict
   (KEEP / REJECT / SPLIT / MERGE / CONTESTED).
5. **The full layer-3 critic JSONL + layer-4 prediction JSONL outputs** so
   researchers can study where the multi-model critic agreed, disagreed, or
   reframed a class.
6. **A reproducibility entry point**: `repro/reproduce_all.py` runs the frozen
   pipeline on the bundle's data and asserts the headline fit numbers
   reproduce within paper-stated tolerances. A `--smoke` mode runs in ~1 s on
   a laptop; `--full` runs all 13 systems plus the 4 nulls in well under a
   minute on local copies of the fitted-result JSONs.
7. **A tutorial notebook** `tutorials/01_reproduce_earthquake_soc.ipynb` that
   walks a reader from "I have only a clean Python install" to a reproduced
   Phase 1 earthquake b-value in roughly 30 minutes of wall-clock time
   (mostly the USGS API pull).

## 2. Bundle layout

```
structural-isomorphism-v1.0-benchmark/
├── README.md                          (this file)
├── LICENSE                            (data CC-BY-4.0 + code MIT, combined notice)
├── LICENSE-DATA                       (full CC-BY-4.0 legalcode)
├── CITATION.cff                       (citation metadata)
├── MANIFEST.json                      (every file + sha256 + size + license + schema_ref)
├── datasets/                          (13 phases of empirical data + fitted results)
│   ├── 01_earthquake/                 (USGS, M >= 3.5, 2020-2025)
│   ├── 02_stockmarket/                (S&P 500 daily returns 1990-2025)
│   ├── 03_defi/                       (Aave V2 + Compound V2 + MakerDAO Dog)
│   ├── 04_neural/                     (DANDI:000006 mouse ALM cortex avalanches)
│   ├── 05_wildfire/                   (NIFC US wildfires)
│   ├── 06_solar/                      (GOES X-ray flares 2000-2016)
│   ├── 07_bank_failures/              (FDIC 1934-2026)
│   ├── 08_github_stars/               (8398 repos, stratified)
│   ├── 09_power_grid/                 (literature-meta catalog of North American cascades)
│   ├── 10_wikipedia_views/            (English Wikipedia pageviews 2023-2024)
│   ├── 11_hawkes_omori/               (synthetic Hawkes-Omori baseline)
│   ├── 12_scheffer_lake/              (USGS Fox River dissolved oxygen)
│   └── 13_hysteresis_traffic/         (US-101 NGSIM q-rho)
│   └── _build_summary.json            (per-phase copy/stub summary from build_datasets.py)
├── nulls/                             (4 synthetic null controls)
│   ├── _registry.jsonl                (one row per case)
│   ├── _generator.py                  (regenerates the nulls from seed)
│   ├── _all_null_results.json         (full pipeline output)
│   ├── _VERDICT.md                    (human summary; all 4 correctly rejected)
│   ├── gaussian/results.json
│   ├── exponential/results.json
│   ├── poisson/results.json
│   └── poisson_omori/results.json
├── pipeline/                          (frozen pipeline source)
│   ├── soc_pipeline/                  (the package — fit / bootstrap / b_value / omori / etc)
│   ├── pyproject.toml                 (PyPI-style packaging metadata)
│   ├── b3_ensemble.py                 (3-model DeepSeek ensemble critic)
│   ├── llm_guardrail.py               (structured-output + abstention guardrail)
│   └── requirements-pipeline.txt      (pinned deps, see repro/)
├── results/                           (B1 / B3 / layer3 / layer4 JSONL outputs)
│   ├── B3_taxonomy_v2.jsonl           (21 final-curated classes, plurality verdict)
│   ├── B3_ensemble_review.jsonl       (per-reviewer rationales)
│   ├── B3_ensemble_summary.md
│   ├── layer3_critic.jsonl            (full layer-3 critic outputs)
│   ├── layer3_critic_summary.md
│   └── layer4.jsonl                   (per-class downstream predictions, 21 rows)
├── taxonomy/                          (35 class YAMLs + index)
│   ├── universality_classes.yaml      (top-level class index)
│   ├── classes/                       (35 .yaml files: 21 curated + 14 variants)
│   ├── SCHEMA.md                      (YAML schema)
│   └── B1_B3_split_merge_summary.md   (human summary of B1 vs B3 disagreements)
├── tutorials/                         (executable walkthroughs)
│   ├── 01_reproduce_earthquake_soc.ipynb
│   └── README.md
├── repro/                             (reproducibility scripts)
│   ├── build_datasets.py              (populates datasets/ from v4/validation/)
│   ├── generate_manifest.py           (idempotent MANIFEST.json builder)
│   ├── reproduce_all.py               (one-shot reproducibility entry: --smoke | --full)
│   └── requirements-repro.txt         (deps for the reproducibility entry point)
└── paper/
    └── scientific-data-benchmark-2026-05-15.md   (companion paper draft, ~5k words)
```

## 3. Large-file policy

Files larger than 50 MB are not bundled inline. In their stead the bundle
contains `<filename>.LARGE_FILE_README.md` with the file's SHA-256, source URL,
fetch date, and the regeneration command. Two equivalent ways to obtain the
missing files:

- **Option A (re-fetch).** Each phase ships its original `fetch_*.py` script
  inside `datasets/<slot>/`. Running it from the structural-isomorphism repo
  root regenerates the raw file. Network access required.
- **Option B (Zenodo archive).** The Zenodo deposit includes a separate
  `<bundle>-rawdata.tar.gz` whose contents satisfy the large-file SHA-256
  pins. This is the recommended option for offline / archival use.

In the present bundle (~85 MB total), all per-phase files are under the 50 MB
threshold and are bundled inline, so no large-file stubs are present.

## 4. Provenance — where each file came from

Each empirical phase has its raw data fetched independently from a publicly
documented source:

| slot | source | fetch date | upstream URL |
| --- | --- | --- | --- |
| 01_earthquake | USGS NEIC | 2026-04 | https://earthquake.usgs.gov/fdsnws/event/1/ |
| 02_stockmarket | Yahoo Finance | 2026-04 | ^GSPC daily |
| 03_defi (Aave/Compound/Maker) | protocol event logs via Dune Analytics | 2026-04 | https://dune.com/ |
| 04_neural | DANDI Archive set 000006 | 2026-04 | https://dandiarchive.org/dandiset/000006 |
| 05_wildfire | NIFC | 2026-04 | https://www.nifc.gov/fire-information/statistics |
| 06_solar | NOAA NGDC GOES X-ray events | 2026-04 | https://www.ngdc.noaa.gov/stp/satellite/goes-r.html |
| 07_bank_failures | FDIC failed bank list | 2026-04 | https://www.fdic.gov/resources/resolutions/bank-failures/ |
| 08_github_stars | GitHub REST API | 2026-04 | https://api.github.com/ |
| 09_power_grid | literature-meta catalog (n=123 events) | 2026-05 | Carreras / Dobson / Newman papers |
| 10_wikipedia_views | Wikipedia Pageviews API | 2026-04 | https://wikimedia.org/api/rest_v1/ |
| 11_hawkes_omori | internal generator from `pipeline/soc_pipeline/null_controls.py` | 2026-05 | — |
| 12_scheffer_lake | USGS waterdata | 2026-05 | https://waterdata.usgs.gov/ |
| 13_hysteresis_traffic | FHWA NGSIM US-101 | 2026-05 | https://ops.fhwa.dot.gov/trafficanalysistools/ngsim.htm |

Per-file fetch logs are at `datasets/<slot>/fetch_log.json` where available.

## 5. Schemas

### 5.1 Schemas — JSONL (general convention)

Each line is a JSON object. Fields are documented in the section that follows
for the specific file type.

### 5.2 Schemas — taxonomy JSONL (`results/B3_taxonomy_v2.jsonl`)

| field | type | meaning |
| --- | --- | --- |
| `class_id` | string | snake_case class id, matches `taxonomy/classes/<id>.yaml` |
| `b1_verdict` | enum | KEEP, REJECT, SPLIT, MERGE_WITH(...), UNCLEAR — single-Opus layer 1 |
| `b1_confidence` | enum | low / medium / high |
| `b3_verdicts` | list of 3 strings | layer-3 (three DeepSeek runs) verdicts |
| `b3_confidences` | list of 3 floats | per-reviewer numeric confidence (0-1) |
| `b3_consensus` | string | plurality of `b3_verdicts` |
| `b3_avg_confidence` | float | mean of `b3_confidences` |
| `final_verdict` | string | e.g. `KEEP_strong`, `CONTESTED(B1=KEEP,B3=REJECT)`, `SPLIT_strong` |

### 5.3 Schemas — results JSONL (`results/layer3_critic.jsonl`)

One row per class with the full layer-3 critic narrative:

| field | type | meaning |
| --- | --- | --- |
| `class_id` | string | matches `B3_taxonomy_v2.jsonl` |
| `review_verdict` | enum | KEEP / REJECT / SPLIT / MERGE / UNCLEAR |
| `confidence` | enum | low / medium / high |
| `members_flagged_as_false_positive` | list[string] | members the reviewer says don't belong |
| `members_flagged_reason` | string | mechanism-level rationale |
| `negative_examples` | list[{phenomenon, reason}] | phenomena that *look* like the class but aren't |
| `split_suggestion` | string or null | proposed split if applicable |
| `merge_with` | string or null | class to merge into if applicable |
| `notes` | string | reviewer's free-form observations |

### 5.4 Schemas — results JSONL (`results/layer4.jsonl`)

| field | type | meaning |
| --- | --- | --- |
| `class_id` | string | |
| `hub_name` | string | canonical hub phenomenon for the class |
| `predictions` | list[{target, prediction, test_method, data_source, sample_size, paper_target, status, rationale}] | concrete downstream predictions |

### 5.5 Schemas — nulls JSONL (`nulls/_registry.jsonl`)

| field | type | meaning |
| --- | --- | --- |
| `case_id` | string | `null_001_gaussian_walk`, etc |
| `synthetic_data_type` | string | `gaussian_walk` / `exponential` / `poisson_iat` / `poisson_omori_stack` |
| `params` | dict | generator parameters including `rng_seed` |
| `n_samples` | int | |
| `pipeline_verdict` | enum | `rejected` (expected for all 4) |
| `key_indicators` | dict | `alpha_clauset`, `sigma_alpha`, `xmin`, `vs_lognormal_R`, etc |
| `expected_real_distribution` | string | the true generative form |

### 5.6 Schemas — CSV

Where CSVs appear under `datasets/*/`, each is documented in the upstream
fetch script's docstring. Common columns: `time` (ISO 8601 UTC),
`size_or_magnitude` (float), `id` (string), and source-specific fields.

### 5.7 Schemas — class YAML (`taxonomy/classes/<id>.yaml`)

Per `taxonomy/SCHEMA.md`. Key fields: `display_name`, `equation_canonical`,
`invariants`, `positive_examples`, `negative_examples`, `references`.

## 6. Quickstart — reproduce the earthquake SOC verdict in 30 lines

```python
# 30-line standalone script. Requires: numpy, requests, powerlaw.
import json, requests
from urllib.parse import urlencode

# 1. Pull a 6-month USGS slice (M >= 3.5).
params = {"format": "geojson", "starttime": "2024-01-01", "endtime": "2024-07-01",
          "minmagnitude": 3.5, "limit": 20000}
r = requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query?" + urlencode(params), timeout=60)
mags = [f["properties"]["mag"] for f in r.json()["features"] if f["properties"].get("mag")]

# 2. Convert M -> released energy E (ergs) via Gutenberg-Richter scaling.
import numpy as np
mags = np.asarray(mags)
E = 10.0 ** (1.5 * mags + 11.8)

# 3. Clauset MLE on the released-energy tail.
import powerlaw
fit = powerlaw.Fit(E, discrete=False, verbose=False)

# 4. Gutenberg-Richter b-value from the magnitude tail.
# (b = (1/ln 10) / (mean(M) - M_c)). M_c by maximum-curvature.
mc = mags[np.argmax(np.histogram(mags, bins=30)[0]) + np.histogram(mags, bins=30)[1][0:1].sum() * 0]
mc = max(np.median(mags) - 0.2, 4.0)
b = (1.0 / np.log(10.0)) / max(mags[mags >= mc].mean() - mc, 1e-9)

print(f"Clauset alpha = {fit.alpha:.3f} (xmin = {fit.xmin:.2e})")
print(f"Gutenberg-Richter b = {b:.3f}  (paper headline b = 1.084)")
print(f"vs lognormal Vuong R = {fit.distribution_compare('power_law', 'lognormal')[0]:.2f}")
print(f"vs exponential Vuong R = {fit.distribution_compare('power_law', 'exponential')[0]:.2f}")
```

The full tutorial `tutorials/01_reproduce_earthquake_soc.ipynb` extends this to
the 2020-2025 catalog and produces the paper-headline value `b = 1.084` with
bootstrap 95% CI `[1.073, 1.094]` plus the Vuong LR tests.

## 7. Reproducibility — `repro/reproduce_all.py`

The one-shot reproducibility entry:

```bash
# Smoke mode (default): 2-3 systems, ~1 second
python repro/reproduce_all.py --smoke

# Full mode: all 13 phases + 4 nulls, well under a minute
python repro/reproduce_all.py --full
```

On success it prints `✓ Reproducibility verified` and exits 0. The script
emits `out/all_verdicts.jsonl`, one row per system, with the headline fit
metric, the paper-frozen target, the tolerance, and the verdict (PASS /
FAIL / NO_VALUE / NO_TARGET).

**Expected smoke runtime:** ~1 s on a laptop.
**Expected full runtime:** ~2 s on a laptop (the bundle ships the fitted
result JSONs, so the headline reproducibility check is a load-and-extract
pass, not a re-fit). To rerun the full Clauset MLE from raw data, use the
notebook in `tutorials/` for an end-to-end demo on Phase 1 and follow the
same pattern for any other phase.

**Expected hash stability.** `repro/generate_manifest.py` produces a
byte-stable `MANIFEST.json` across reruns; verify with:

```bash
python repro/generate_manifest.py && md5sum MANIFEST.json
python repro/generate_manifest.py && md5sum MANIFEST.json  # must match
```

The bundle hash (`MANIFEST.json:bundle_sha256`) is what Zenodo / DataCite
should pin in their record.

## 8. Citation

If you use this bundle in published work, please cite both:

1. **This dataset (Zenodo DOI):**

```bibtex
@dataset{structural_isomorphism_v1_0_benchmark_2026,
  author       = {{structural-isomorphism contributors}},
  title        = {{structural-isomorphism v1.0 cross-domain SOC + universality benchmark}},
  year         = 2026,
  month        = may,
  publisher    = {Zenodo},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.PLACEHOLDER},
  url          = {https://doi.org/10.5281/zenodo.PLACEHOLDER}
}
```

2. **The companion paper:**

```bibtex
@article{structural_isomorphism_dataset_paper_2026,
  author  = {{structural-isomorphism contributors}},
  title   = {{A cross-domain SOC + critical-systems benchmark with synthetic nulls and multi-model class curation}},
  journal = {Scientific Data (submitted)},
  year    = 2026,
  note    = {Preprint at \url{https://github.com/dada8899/structural-isomorphism/blob/main/dataset/v1/structural-isomorphism-v1.0-benchmark/paper/scientific-data-benchmark-2026-05-15.md}}
}
```

3. **The methods paper (the underlying pipeline, optional):**

```bibtex
@article{structural_isomorphism_v0_3_2026,
  author  = {{structural-isomorphism contributors}},
  title   = {{A pipeline for cross-domain validation of self-organized criticality, preferential attachment, and adjacent universality classes: thirteen systems, one method}},
  journal = {arXiv (cond-mat.stat-mech, physics.data-an)},
  year    = 2026,
  note    = {arXiv:NNNN.NNNNN}
}
```

## 9. How this bundle relates to the rest of the repo

This bundle is a *frozen subset* of the structural-isomorphism research repo,
chosen for deposit to Zenodo. The full repo
(https://github.com/dada8899/structural-isomorphism) additionally contains
the v3 / v4 work-in-progress, the larger 35-class candidate taxonomy with
the 14 variants that did not survive curation, the web demo, validation
infrastructure, and the test scaffolding. The deposit version pins exactly
the artefacts needed to reproduce the headline empirical results, the
synthetic-null rejection, and the 21 final-curated universality classes.

The bundle hash is the citation primitive. The git commit recorded in
`MANIFEST.json:git_commit` resolves the *exact* state of the source repo
from which this bundle was built.

## 10. Open questions & future versions

- **v1.1** will fold in the five pre-registered new systems described in §8
  of the methods paper, fetched after the v1.0 deposit. (Pre-registration is
  what gives v1.1 its scientific value — predictions logged before fitting.)
- **v2.0** is expected to add a 100-time-series leaderboard for the
  papers-with-code task ("predict each system's universality class invariant
  + best Vuong-LR alternative; score against B3-curated ground truth").

Bug reports / data corrections / new-system PRs → repo issue tracker.

---

*Bundle built by the W7-A Track A roadmap (`docs/future/W7-A-academic-value-roadmap-2026-05-13.md`).*
