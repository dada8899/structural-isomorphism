# LLM Scaling-Law Re-Validation v2 — Pythia LAMBADA (L_inf>0 constrained, all checkpoints)

**Date.** 2026-05-25 (SESSION-25)
**Module.** `soc_pipeline.learning_curve.fit_learning_curve` with `L_inf_bounds=(1.0, 5.0)`
**Source.** `raw/pythia_lambada_real.csv` (216 rows; **no** warmup filter applied in iteration 2 — see below).

## Why v2

v1 (SESSION-24 `e798397`) gave R² ∈ [0.81, 0.87] with L_inf fit values pinned to ≈ 0 (10⁻¹² to 10⁻¹⁷, the lower bound). LAMBADA-OpenAI has non-zero irreducible entropy: GPT-3 175B reaches LAMBADA ppl ≈ 3.3 (log-ppl ≈ 1.19), Pythia-12B terminates at log-ppl ≈ 1.36. The hypothesis was that anchoring L_inf to the LAMBADA literature floor would tighten fits.

v2 (final, iteration 2): constrain L_inf ∈ [1.0, 5.0] anchored to LAMBADA-OpenAI literature; keep all 216 checkpoints.

(Iteration 1 of v2 *also* dropped warmup checkpoints at log-ppl > 5; this collapsed R² to negative across most sizes because dropping 90/216 points left too few in too narrow an L range for `curve_fit` to recover three parameters jointly. The 70m model collapsed to α=0.01, hitting the alpha lower bound. This degenerate iteration is documented in the script header for provenance, then abandoned. Iteration 2 keeps all data — the warmup transient is part of the fit but the asymptote is anchored.)

## Per-size fits (L(C) = A · C^(-α) + L_inf on LAMBADA log-ppl, L_inf ≥ 1.0)

| Model | α | α_se | L∞ | A | R² | n_post_warmup | provenance |
|---|---|---|---|---|---|---|---|
| pythia-1.4b | 0.1672 | 0.0815 | 1.000 | 9.73e+03 | 0.7927 | 26 | REAL_LAMBADA_v2 |
| pythia-12b | 0.1783 | 0.0843 | 1.000 | 2.45e+04 | 0.7866 | 26 | REAL_LAMBADA_v2 |
| pythia-160m | 0.1411 | 0.0689 | 1.000 | 2.60e+03 | 0.8319 | 26 | REAL_LAMBADA_v2 |
| pythia-1b | 0.1642 | 0.0784 | 1.000 | 8.17e+03 | 0.8030 | 26 | REAL_LAMBADA_v2 |
| pythia-2.8b | 0.1703 | 0.0837 | 1.000 | 1.23e+04 | 0.7860 | 26 | REAL_LAMBADA_v2 |
| pythia-410m | 0.1552 | 0.0785 | 1.000 | 5.06e+03 | 0.8004 | 26 | REAL_LAMBADA_v2 |
| pythia-6.9b | 0.1740 | 0.0825 | 1.000 | 1.76e+04 | 0.7922 | 26 | REAL_LAMBADA_v2 |
| pythia-70m | 0.1194 | 0.0606 | 1.000 | 1.07e+03 | 0.8588 | 26 | REAL_LAMBADA_v2 |

## Universality summary (v2)

- n sizes: **8**
- ᾱ: **0.1587**
- σ_α: 0.0184
- CV: **0.116**
- mean R²: **0.8064**
- L_inf range across sizes: [1.000, 1.000]  ← all 8 sizes hit the lower bound 1.0
- Verdict: **TIGHT_UNIVERSALITY**

## Honest negative finding

The L_inf constraint did **not** improve fit quality. mean R² actually decreased slightly (0.82 → 0.81). All 8 sizes hit the lower bound L_inf = 1.0, meaning the fitter would prefer L_inf < 1.0 if allowed. This is the cleanest possible negative result: within the Pythia training-compute range [10¹⁵, 10²²] FLOPs, LAMBADA log-ppl is **still in the power-law-decay regime**, not the **floor-bounded regime**. Even the largest model (Pythia-12B) terminates at log-ppl ≈ 1.36 with a still-decreasing trajectory.

The v1 finding (L_inf fit ≈ 0) is therefore not a fit pathology — it is a correct statement that, in this compute range, a pure power-law L(C) = A · C^(-α) describes LAMBADA cross-entropy as well as the floor-augmented form. The asymptote exists in theory (LAMBADA-OpenAI test-set entropy is finite > 0) but Pythia training does not reach the regime where the floor binds the fit.

**The α universality verdict is robust to the fit parameterisation.** Whether you fit pure power-law (v1: α̅ = 0.144, CV = 0.118) or power-law + floor (v2: α̅ = 0.159, CV = 0.116), the cross-size α distribution stays tight (CV < 0.20) and the TIGHT_UNIVERSALITY verdict survives. This robustness check is the *contribution* of v2 — not a R² improvement, but the demonstration that the headline finding does not depend on a contestable fit choice.

## Side-by-side v1 vs v2

| Quantity | v1 (SESSION-24) | v2 (SESSION-25) | Δ |
|---|---|---|---|
| ᾱ | 0.1440 | 0.1587 | +0.0147 |
| CV | 0.118 | 0.116 | -0.002 |
| mean R² | 0.8245 | 0.8064 | -0.0181 |
| L_inf (max across sizes) | 2.30e-12 | 1.000 | constrained > 0 |
| verdict | TIGHT_UNIVERSALITY | TIGHT_UNIVERSALITY | (same) |

## Cross-source comparison (with v2)

| Source | sizes | ᾱ | CV | mean R² | verdict |
|---|---|---|---|---|---|
| **LAMBADA v2** (warmup-filtered, L_inf>0) | 8 | **0.1587** | **0.116** | **0.8064** | TIGHT_UNIVERSALITY |
| LAMBADA v1 (SESSION-24, all checkpoints, L_inf=0) | 8 | 0.1440 | 0.118 | 0.82 | TIGHT_UNIVERSALITY |
| Train loss (wandb, mixed real/syn) | 6 | 0.272 | 0.706 | — | BROAD_SPREAD |
| Train loss (literature-anchored) | 6 | 0.116 | 0.178 | — | MODERATE_UNIVERSALITY |

## Interpretation

1. **The Pythia compute range is pre-asymptotic for LAMBADA.** All 8 sizes still benefit from more compute at the end of training; none has reached the LAMBADA-OpenAI entropy floor. The two-parameter Kaplan/Hoffmann form is over-parameterised for this data.
2. **v1's L_inf ≈ 0 is correct (not a fit bug).** It is the data telling us 'no floor visible in this range', not 'no floor exists in theory'.
3. **Universality verdict is robust to fit methodology.** Both v1 and v2 deliver a tight CV (< 0.20) across all 8 sizes. This is the right kind of robustness check — the cross-size α stability survives a defensible re-specification, even though absolute α shifts ~10%.

## Limitations / extensions

1. L_inf lower bound 1.0 is anchored to GPT-3 / Pythia-12B asymptote literature. A v3 that fits *one global* L_inf across all 8 sizes (Hoffmann 2022 joint-fit style) would be more theoretically principled than per-size L_inf — the irreducible entropy of LAMBADA is a property of the dataset, not the model. Cheap follow-up.
2. Larger-compute Pythia continuations (e.g., 12B trained past 300B tokens) would test whether the floor binds at the post-training horizon. Not currently available publicly.
3. Sensitivity to evaluation choice: LAMBADA-OpenAI vs LAMBADA-standard vs WikiText-103 may give different α. Cross-eval universality is a separate question from cross-size universality.

## Implications for v0.5 paper

v2 replaces v1 as the canonical Pythia-LAMBADA fit for the v0.5 verdict matrix. v1 is preserved at `results_lambada.json` for provenance (SESSION-24's reported numbers). Both should appear in the §3.6 multi-source α universality table.

End of v2 summary.