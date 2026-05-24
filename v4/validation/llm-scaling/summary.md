# LLM Scaling-Law Learning-Curve Validation — Summary

**Date.** 2026-05-24
**Module.** `soc_pipeline.learning_curve.fit_learning_curve`
**Pythia sizes fitted.** 6

## Per-series fits  (L(C) = A · C^(-α) + L∞)

| Model | α | α_se | L∞ | A | R² | n |
|---|---|---|---|---|---|---|
| pythia-160m | 0.0949 | 0.0278 | 1.9998 | 20.3 | 0.9919 | 14 |
| pythia-1b | 0.1164 | 0.0121 | 1.7157 | 57.5 | 0.9985 | 14 |
| pythia-2.8b | 0.1459 | 0.0128 | 1.6079 | 226 | 0.9983 | 14 |
| pythia-410m | 0.1000 | 0.0220 | 1.7640 | 30.8 | 0.9949 | 14 |
| pythia-6.9b | 0.1348 | 0.0120 | 1.4568 | 191 | 0.9985 | 14 |
| pythia-70m | 0.1029 | 0.0213 | 2.3058 | 22 | 0.9953 | 14 |
| kaplan2020-gpt | 0.0495 | 0.0067 | 0.0000 | 24.9 | 0.9980 | 12 |
| hoffmann2022-chinchilla | 0.1613 | 0.0055 | 1.7114 | 1.47e+03 | 0.9988 | 14 |

## Universality summary (Pythia 6 sizes)

- α̅ (mean across 6 sizes): **0.1158**
- σ_α: 0.0206
- CV (σ_α/α̅): 0.178
- Verdict: **MODERATE_UNIVERSALITY**

## Benchmarks

- Chinchilla compute exponent α_C ≈ 0.155
- Chinchilla model-size exponent α_N ≈ 0.34
- Chinchilla token-axis exponent α_D ≈ 0.28
- Kaplan 2020 compute exponent α_C ≈ 0.05
- Stevens psychophysics α ≈ 0.5
