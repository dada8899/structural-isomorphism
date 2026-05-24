# LLM Scaling-Law Learning-Curve Validation — Summary

**Date.** 2026-05-25
**Module.** `soc_pipeline.learning_curve.fit_learning_curve`
**Pythia CSV.** `v4/validation/llm-scaling/raw/pythia_checkpoints_combined.csv`
**Pythia sizes fitted.** 6

## Per-series fits  (L(C) = A · C^(-α) + L∞)

| Model | α | α_se | L∞ | A | R² | n | provenance |
|---|---|---|---|---|---|---|---|
| pythia-160m | 0.0949 | 0.0278 | 1.9998 | 20.3 | 0.9919 | 14 | SYNTHETIC |
| pythia-1b | 0.1164 | 0.0121 | 1.7157 | 57.5 | 0.9985 | 14 | SYNTHETIC |
| pythia-2.8b | 0.3997 | 0.0305 | 1.6191 | 5.82e+07 | 0.0128 | 40 | REAL_TAIL_NARROW |
| pythia-410m | 0.5757 | 0.0005 | 2.0007 | 7.35e+10 | 0.9856 | 40 | REAL_FULL |
| pythia-6.9b | 0.1348 | 0.0120 | 1.4568 | 191 | 0.9985 | 14 | SYNTHETIC |
| pythia-70m | 0.3119 | 0.0283 | 1.7122 | 1.11e+06 | 0.9732 | 35 | REAL_FULL |
| kaplan2020-gpt | 0.0495 | 0.0067 | 0.0000 | 24.9 | 0.9980 | 12 | LITERATURE_ANCHORED (Kaplan 2020 eq. 1.5) |
| hoffmann2022-chinchilla | 0.1613 | 0.0055 | 1.7114 | 1.47e+03 | 0.9988 | 14 | LITERATURE_ANCHORED (Hoffmann 2022 Table 4 Approach 3) |

## Universality summary (Pythia)

### All 6 sizes

- n sizes: 6
- α̅: **0.2722**
- σ_α: 0.1921
- CV: 0.706
- Verdict: **BROAD_SPREAD**

### REAL wide-range sizes only

- n sizes: 2
- α̅: **0.4438**
- σ_α: 0.1865
- CV: 0.420
- Verdict: **BROAD_SPREAD**

## Benchmarks

- Chinchilla compute exponent α_C ≈ 0.155
- Chinchilla model-size exponent α_N ≈ 0.34
- Chinchilla token-axis exponent α_D ≈ 0.28
- Kaplan 2020 compute exponent α_C ≈ 0.05
- Stevens psychophysics α ≈ 0.5

## Provenance per model

- `pythia-160m`: SYNTHETIC
- `pythia-1b`: SYNTHETIC
- `pythia-2.8b`: REAL_TAIL_NARROW
- `pythia-410m`: REAL_FULL
- `pythia-6.9b`: SYNTHETIC
- `pythia-70m`: REAL_FULL
