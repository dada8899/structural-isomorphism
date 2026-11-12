# aggregation_kinetics

**Name (zh)**: 聚集动力学类（Smoluchowski + 群体异质性两层模型）
**Name (en)**: Aggregation Kinetics (Smoluchowski + Population Heterogeneity Two-Layer Model)
**Pre-registered exponent bands**:
  - **Layer 1 (per-plaque size distribution)**: Clauset α ∈ [1.7, 3.5] (Smoluchowski universal for both diffusion-limited and reaction-limited cluster-cluster aggregation; spans Cruz 1997 α=1.70 plaque areas / Hartig 2018 α=2.10 5xFAD plaque volumes / canonical Smoluchowski α=3/2 to 5/2 across kinetic regimes)
  - **Layer 2 (cross-population total-burden)**: Lognormal preferred over PL (Vuong R < 0, p < 0.05) — *expected* signature of multiplicative-stochastic growth at the patient/population scale (Hyman 2008 *Neuropath Appl Neurobiol* 34:131)
**Verified status**: false (proposed; target: v0.5). Promoted from beta-amyloid X3 Wave 2 candidate.

## Why this class needs a 2-layer framing

The single-layer beta-amyloid validation (commit ad29ad7, X3 Wave 2) was INCONCLUSIVE across all 5 series — Allen Brain TBI cross-section showed lognormal decisively beating PL on 4/5 series. This was framed as a *negative* result. But the *deeper* finding is the literature already predicted this:

- **At the per-plaque scale** (Cruz 1997 *Acta Neuropathol*; Hartig 2018 *J Neurosci Res*): individual plaque size distributions follow PL with α ∈ [1.7, 2.1], consistent with Smoluchowski coagulation cluster-cluster aggregation.
- **At the cross-population scale** (Hyman 2008): inter-patient progression is multiplicatively stochastic — each patient's total burden compounds at a multiplicative rate that varies across the population. The cross-section therefore should be **lognormal**, NOT PL.

The single-layer test (cross-section → expect PL) was the wrong test. The right test is *both* layers. A new universality class — `aggregation_kinetics` — encapsulates the 2-layer prediction:
1. **PL at plaque scale** (intra-individual; Smoluchowski universal)
2. **Lognormal at population scale** (inter-individual; multiplicative stochastic growth universal)

The class is *cross-domain* in the sense that the same 2-layer structure appears in:
- Beta-amyloid plaque burden (Alzheimer's; Hyman 2008)
- Cancer tumor size distributions (Iwata 2000 *J Theor Biol*; Cohen-Saxena 2015)
- Aerosol / colloid coagulation populations (Friedlander 2000 *Smoke Dust Haze*)
- Protein aggregation in cells (Knowles-Vendruscolo 2014 *Annu Rev Phys Chem*)

KB linkage: 5 members — beta-amyloid plaque burden, tumor coagulation, aerosol size distributions, colloidal aggregation, cell-protein aggregates.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Layer | Why fits |
|---|---|---|---|---|---|---|
| 1 [primary, Layer 2] | Allen Brain TBI Study (already fetched 2026-05-24) | Miller 2017 *eLife* 6:e26571 | CC-BY 4.0 | 377 donor × structure | Layer 2 (cross-population burden) | REST API live; already in repo |
| 2 [primary, Layer 1] | Cruz 1997 *Acta Neuropathol* 93:534 plaque area α=1.70 + Hartig 2018 5xFAD α=2.10 | Published tables | Free | Literature constants | Layer 1 (per-plaque size distribution) | Anchor; no fresh data fetch needed |
| 3 [stretch, Layer 1] | ADNI plaque-segmentation imaging metrics | http://adni.loni.usc.edu | Free, registration | ~1,800 patients | Layer 1 fresh data | Registration friction; complex segmentation |

## Validation procedure (concrete)

```bash
mkdir -p v4/validation/aggregation-kinetics

# 1. Layer 1 (literature-anchored): pre-register Cruz 1997 + Hartig 2018 α
#    constants in run_validation.py. No fresh fetch.
# 2. Layer 2 (Allen Brain TBI): re-use existing per-series Clauset α + Vuong
#    lognormal-vs-PL from v4/validation/beta-amyloid/results.json. Lognormal
#    winning is now PASS-of-Layer-2, not INCONCLUSIVE.
# 3. Cross-domain isomorphism check: extend to cancer / aerosol / colloid
#    literature anchors at Layer 1.
# 4. Run:
.venv/bin/python v4/validation/aggregation-kinetics/run_validation.py
```

Pre-registered verdict ladder:
- N_Layer1 < 2 distinct literature anchors → INCONCLUSIVE
- N_Layer2 < 50 cross-population samples → INCONCLUSIVE
- Layer 1 α ∈ [1.7, 3.5] AND Layer 2 lognormal-preferred (R < 0, p < 0.05) → **PASS-CONFIRMED-MULTILAYER**
- Layer 1 α outside band OR Layer 2 PL beats lognormal → REJECT (single-layer model wrong)
- Layer 1 PASS AND Layer 2 PL beats lognormal → SPLIT (per-plaque PL OK, population layer not multiplicative)

## Estimated workload

- Pre-class plan (this file): 30 min (done)
- Validation script (Layer 1 lit anchors + Layer 2 from existing): 45 min
- Verdict + report: 30 min
- KB entries: 15 min
- Total: ~2 h

## Risks specific to this class

1. **Layer 1 currently has only 2 literature anchors** (Cruz, Hartig) — minimum for "≥ 2 distinct" gate. Adding ADNI plaque-segmentation data would strengthen but adds workload.
2. **Class boundary is conceptual.** "Aggregation kinetics" is a broad family. Calling it a single universality class requires showing the same 2-layer structure across *mechanistically distinct* aggregation processes (Aβ vs tumor vs aerosol vs colloid). Multi-domain anchor is essential.
3. **Cross-section lognormal could also be confounded** (selection bias by clinical-stage truncation). Hyman 2008 acknowledges this. Layer 2 PASS is robust to the confound only if multiplicative-stochastic growth genuinely dominates.

## Priority

⭐⭐ (rationale: takes existing beta-amyloid INCONCLUSIVE and reframes as multilayer PASS — high marginal value at low marginal cost since the data is already fetched and the literature anchor is well-established. The multilayer methodology is the v0.5 paper contribution.)

## Dependencies

- `soc_pipeline.fit_clauset_powerlaw` + `vuong_lr_test` (existing)
- `scipy.stats.lognorm` (for Layer 2 lognormal MLE)
- No paid API, no new data fetch
- Storage: < 5 MB (existing Allen Brain raw JSON 1.6 MB)
