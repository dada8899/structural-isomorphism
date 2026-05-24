# Structural Isomorphism: Cross-domain SOC validation dataset and pipeline (v1.0)

**Version.** 1.0.0 — 2026-05-24
**Author.** Wan Qihui (万庆徽), Structural Isomorphism Project (independent researcher)
**Companion paper.** C1 unified preprint — *A pipeline for cross-domain validation of self-organized criticality: five systems, one method* (arXiv:XXXX.XXXXX — to be filled after submission)
**Repository.** https://github.com/dada8899/structural-isomorphism
**License.** MIT (code) / CC-BY-4.0 (derived data; per-system upstream licences honoured — see `data-license-notes.md` inside each system folder)

---

## What this is

A single fixed analysis pipeline applied **unchanged** to thirteen independent empirical systems and four synthetic non-SOC null controls, to test cross-domain self-organized-criticality (SOC) universality claims. The dataset bundle (`dataset-v1.tar.gz`) contains the raw inputs, fit results, taxonomy outputs, and pipeline source code needed to reproduce every number reported in the companion preprint.

## What is inside `dataset-v1.tar.gz`

```
v4/validation/         <- 13 empirical systems + 4 null controls (raw + fit results)
v4/results/            <- Layer 1–4 outputs (taxonomy, ensemble, calibration,
                          universal-collapse, predictions)
dataset/v1/            <- structured benchmark layout (systems / null_controls /
                          taxonomy / tests + manifest.json)
packages/soc-pipeline/ <- pipeline source code snapshot (src + tests +
                          pyproject.toml + README + LICENSE)
```

Bundle size: 44 MB compressed (~206 MB uncompressed, 521 files).

### Systems covered (13 real + 4 null)

| Folder under `v4/validation/`     | System                                     | Phase |
|-----------------------------------|--------------------------------------------|-------|
| `soc-earthquake/`                 | USGS tectonic earthquakes 2020–2025        | 1     |
| `soc-stockmarket/`                | S&P 500 daily returns 1990–2025            | 2     |
| `soc-defi/`                       | Aave V2 + Compound V2 + MakerDAO liq.      | 3     |
| `soc-neural/`                     | DANDI mouse-cortex avalanches              | 4     |
| `null-controls/`                  | Folded normal / exp / Poisson IAT / Omori  | 5     |
| `soc-solar/`                      | NOAA GOES X-ray solar flares               | —     |
| `soc-wildfire/`                   | NIFC US wildfires                          | —     |
| `soc-power-grid/`                 | NERC TADS power-grid disturbances          | —     |
| `soc-github-cascade/`             | GitHub repository event cascades           | —     |
| `soc-github-stars/`               | GitHub stargazer events                    | —     |
| `soc-github-resolution/`          | GitHub issue resolution times              | —     |
| `soc-wsb-posts/`                  | r/wallstreetbets cascade sizes             | —     |
| `pre-reg-p2-reddit/`              | Reddit cross-subreddit cascades            | —     |
| `cve-vulnerabilities/`            | CVE vulnerability burst sizes              | —     |
| `soc-wikipedia-views/`            | Wikipedia article views                    | —     |
| `soc-bank-failures/`              | FDIC bank failures                         | —     |
| `scheffer-lake/`                  | Lake dissolved-oxygen EWS                  | —     |
| `tail-copula/`                    | Storm damage tail copula                   | —     |
| `hysteresis-traffic/`             | Traffic hysteresis loops                   | —     |
| `sir-contagion/`                  | SIR contagion simulation                   | —     |
| `soc-hawkes-omori/`               | Hawkes self-exciting Omori fits            | —     |
| `soc-universal-collapse/`         | Phase-3 universal-collapse data            | —     |
| `nyc-fdny-fires/`                 | NYC FDNY fire response data                | —     |

### Layer 1–4 outputs (`v4/results/`)

- `B1_final_taxonomy.jsonl` + `B3_taxonomy_v2.jsonl` — 21-candidate universality-class taxonomy from the multi-model LLM ensemble critic (B1 baseline + B3 calibrated v2).
- `B3_ensemble_summary.md` / `B4_heterogeneous_ensemble.jsonl` — heterogeneous-ensemble cross-check.
- `A3_universal_collapse.json` + `_plot.png` — Phase-3 universal scaling collapse.
- `layer4_predictions_v2_with_ci.jsonl` — Layer-4 cross-domain predictions with credible intervals.
- `F1_bootstrap10k_subset.jsonl` + `F3_fwer_corrected.jsonl` — bootstrap and FWER multiple-comparison correction.

## Pipeline

Authoritative implementation: `packages/soc-pipeline/` (version 0.1.0, MIT, ~1,595 LOC across 12 modules):

- `fit.py` — Clauset–Shalizi–Newman MLE power-law fit + KS-driven `x_min` selection
- `lr_test.py` — Vuong likelihood-ratio test vs. lognormal / exponential
- `b_value.py` — Gutenberg–Richter b-value + Aki / Shi–Bolt error
- `omori.py` — Omori–Utsu temporal-decay stacking
- `bootstrap.py` — block / non-overlapping bootstrap resamplers
- `universal_collapse.py` — data-collapse fitting
- `null_controls.py` — synthetic non-SOC generators
- `time_resolution.py` — time-resolution sensitivity sweep
- `pandas_accessor.py` — pandas `.soc` accessor
- `validate.py` — phase-validate orchestration (W11A test coverage)
- `utils.py`

Legacy entry point `v4/lib/soc_pipeline.py` is a 75-line deprecation shim re-exporting the package (kept for paper provenance — the companion C1 preprint and the 13-system sibling manuscript both still cite the legacy "339-line" description).

## Reproducibility

```bash
# 1. Extract
tar -xzf dataset-v1.tar.gz

# 2. Install pipeline
cd packages/soc-pipeline
pip install -e .            # or: pip install soc-pipeline

# 3. Reproduce per-system fits (example — Phase 1 earthquakes)
python -m soc_pipeline.b_value \
    --catalog v4/validation/soc-earthquake/catalog.jsonl \
    --mc 4.45 --bootstrap 500 --seed 42

# 4. Reproduce null controls (Phase 5)
python -m soc_pipeline.null_controls --out v4/validation/null-controls/

# 5. Verify against published numbers
diff <(python -m soc_pipeline.fit --json v4/validation/soc-defi/aave_v2_liquidations.jsonl) \
     v4/validation/soc-defi/gr_results.json
```

Expected canonical numbers (from companion preprint §3):

- Phase 1 (USGS earthquakes, n=37,281, M_c=4.45): b = 1.084 ± 0.005, Omori p = 0.941 ± 0.017
- Phase 2 (S&P 500, n=9,060): α = 2.998 ± 0.041
- Phase 3 (DeFi, n=43,065): α ∈ [1.567, 1.684] across three protocols, Omori p ∈ [0.69, 0.76]
- Phase 4 (mouse cortex, n=1,392,414 spikes): γ ≈ 1.10, τ ∈ [2.17, 3.00]
- Phase 5 (nulls): LR(power-law vs. alt.) ∈ [−45, −16], all rejected

## Integrity

See `manifest.txt` for SHA-256 of `dataset-v1.tar.gz` and per-file SHA-256 of every file in the bundle (521 files total).

## Citation

If you use this dataset or pipeline, please cite both the Zenodo deposit and the companion arXiv preprint:

```bibtex
@dataset{wan2026soc_dataset_v1,
  author       = {Wan, Qihui},
  title        = {Structural Isomorphism: Cross-domain SOC validation
                  dataset and pipeline (v1.0)},
  year         = 2026,
  publisher    = {Zenodo},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.XXXXXXX},
  url          = {https://doi.org/10.5281/zenodo.XXXXXXX}
}

@unpublished{wan2026soc_unified,
  author       = {Wan, Qihui},
  title        = {A pipeline for cross-domain validation of
                  self-organized criticality: five systems, one method},
  year         = 2026,
  note         = {arXiv:XXXX.XXXXX}
}
```

## Contact

Project site: https://structural.bytedance.city
Issues: https://github.com/dada8899/structural-isomorphism/issues
