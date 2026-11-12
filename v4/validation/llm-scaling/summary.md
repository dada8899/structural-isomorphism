# LLM Scaling-Law Learning-Curve Validation — Summary

**Date.** 2026-10-16
**Module.** `soc_pipeline.learning_curve.fit_learning_curve`
**Estimator.** `log-amplitude-analytic-jacobian-v1`
**Original artifact date.** 2026-05-25
**Pythia CSV.** `v4/validation/llm-scaling/raw/pythia_checkpoints_combined.csv`
**Pythia sizes fitted.** 7

## Per-series fits  (L(C) = A · C^(-α) + L∞)

| Model | α | α_se | L∞ | A | R² | n | status | provenance |
|---|---|---|---|---|---|---|---|---|
| pythia-1.4b | 0.5782 | not reported | 1.2150 | 1e+12 | 0.1268 | 40 | descriptive_only | REAL_TAIL_NARROW |
| pythia-160m | 0.0949 | 0.0278 | 1.9998 | 20.3 | 0.9919 | 14 | fit_quality_eligible | SYNTHETIC |
| pythia-1b | 0.1164 | 0.0121 | 1.7157 | 57.5 | 0.9985 | 14 | fit_quality_eligible | SYNTHETIC |
| pythia-2.8b | 0.6034 | not reported | 1.6620 | 1e+12 | 0.0128 | 40 | descriptive_only | REAL_TAIL_NARROW |
| pythia-410m | 0.5757 | 0.0407 | 2.0007 | 7.35e+10 | 0.9856 | 40 | fit_quality_eligible | REAL_FULL |
| pythia-6.9b | 0.1348 | 0.0120 | 1.4568 | 191 | 0.9985 | 14 | fit_quality_eligible | SYNTHETIC |
| pythia-70m | 0.3119 | 0.0283 | 1.7122 | 1.11e+06 | 0.9732 | 35 | fit_quality_eligible | REAL_FULL |
| kaplan2020-gpt | 0.0495 | not reported | 0.0000 | 24.9 | 0.9980 | 12 | fit_quality_eligible | LITERATURE_ANCHORED (Kaplan 2020 eq. 1.5) |
| hoffmann2022-chinchilla | 0.1613 | 0.0055 | 1.7114 | 1.47e+03 | 0.9988 | 14 | fit_quality_eligible | LITERATURE_ANCHORED (Hoffmann 2022 Table 4 Approach 3) |

## Numerical identification and bounds

The 2026-10-16 estimator refits the unchanged historical inputs; this is not a new empirical experiment. A stable constrained solution is not proof of identifiable physical parameters.

- `pythia-1.4b`: bounds=['A']; identification=weak_or_unestablished; uncertainty=not_reported_active_bound. Unconstrained standard errors are not reported at active bounds.
- `pythia-2.8b`: bounds=['A']; identification=weak_or_unestablished; uncertainty=not_reported_active_bound. Unconstrained standard errors are not reported at active bounds.
- `kaplan2020-gpt`: bounds=['L_inf']; identification=weak_or_unestablished; uncertainty=not_reported_active_bound. Unconstrained standard errors are not reported at active bounds.

Both REAL_TAIL_NARROW series remain excluded from exponent inference. The 1.4b fit is now descriptive_only because the improved numerical fit has positive R²; this does not upgrade its narrow-range evidence. Only two real wide-range series are available, still insufficient for universality inference.


## Fit-spread diagnostics (not universality evidence)

**Scientific conclusion.** `INSUFFICIENT_REAL_WIDE_SERIES_FOR_UNIVERSALITY_INFERENCE`

### Fit-quality-eligible sizes (mixed real/synthetic; diagnostic only)

- n sizes: 5
- α̅: **0.2467**
- σ_α: 0.2031
- CV: 0.823
- Verdict: **BROAD_SPREAD**

### REAL wide-range sizes only

- n sizes: 2
- α̅: **0.4438**
- σ_α: 0.1865
- CV: 0.420
- Verdict: **BROAD_SPREAD**

### Excluded from exponent inference

- `pythia-1.4b`: narrow compute range is not eligible for exponent inference
- `pythia-2.8b`: narrow compute range is not eligible for exponent inference

## Benchmarks

- Chinchilla compute exponent α_C ≈ 0.155
- Chinchilla model-size exponent α_N ≈ 0.34
- Chinchilla token-axis exponent α_D ≈ 0.28
- Kaplan 2020 compute exponent α_C ≈ 0.05
- Stevens psychophysics α ≈ 0.5

## Provenance per model

- `pythia-1.4b`: REAL_TAIL_NARROW
- `pythia-160m`: SYNTHETIC
- `pythia-1b`: SYNTHETIC
- `pythia-2.8b`: REAL_TAIL_NARROW
- `pythia-410m`: REAL_FULL
- `pythia-6.9b`: SYNTHETIC
- `pythia-70m`: REAL_FULL
