# LLM Scaling-Law Re-Validation — Pythia LAMBADA (100% REAL)

**Date.** 2026-05-25
**Module.** `soc_pipeline.learning_curve.fit_learning_curve` on `lambada_log_ppl`
**Source.** `raw/pythia_lambada_real.csv` (216 rows, 8 sizes × 27 checkpoints)

## Per-size fits (L(C) = A · C^(-α) + L_inf on LAMBADA log-ppl)

| Model | α | α_se | L∞ | A | R² | n | provenance |
|---|---|---|---|---|---|---|---|
| pythia-1.4b | 0.1513 | 0.0747 | 0.000 | 5.66e+03 | nan | 26 | REAL_LAMBADA |
| pythia-12b | 0.1632 | 0.0772 | 0.000 | 1.41e+04 | nan | 26 | REAL_LAMBADA |
| pythia-160m | 0.1276 | 0.0645 | 0.000 | 1.70e+03 | nan | 26 | REAL_LAMBADA |
| pythia-1b | 0.1485 | 0.0720 | 0.000 | 4.80e+03 | nan | 26 | REAL_LAMBADA |
| pythia-2.8b | 0.1543 | 0.0765 | 0.000 | 7.04e+03 | nan | 26 | REAL_LAMBADA |
| pythia-410m | 0.1406 | 0.0727 | 0.000 | 3.14e+03 | nan | 26 | REAL_LAMBADA |
| pythia-6.9b | 0.1584 | 0.0753 | 0.000 | 1.01e+04 | nan | 26 | REAL_LAMBADA |
| pythia-70m | 0.1082 | 0.0578 | 0.000 | 7.62e+02 | nan | 26 | REAL_LAMBADA |

## Universality summary

- n sizes: **8**
- ᾱ: **0.1440**
- σ_α: 0.0170
- CV: 0.118
- Verdict: **TIGHT_UNIVERSALITY**

## Cross-source comparison

| Source | sizes | ᾱ | CV | verdict |
|---|---|---|---|---|
| LAMBADA (THIS run, 100% real) | 8 | 0.1440 | 0.118 | TIGHT_UNIVERSALITY |
| Train loss (wandb, mixed real/syn) | 6 | 0.272 | 0.706 | BROAD_SPREAD |
| Train loss (literature-anchored) | 6 | 0.116 | 0.178 | MODERATE_UNIVERSALITY |

## Implications for v0.4 paper

Replaces the SYNTHETIC-fallback verdict for `llm_scaling` class. All 8 Pythia v1 sizes now have real-data α anchors with the same evaluation (LAMBADA-OpenAI) — no fallback. This closes SESSION-23 outstanding #2 and SESSION-24 task (b).

End of summary.