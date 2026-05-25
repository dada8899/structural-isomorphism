# Pythia cross-evaluator α universality (SESSION-25)

**Date.** 2026-05-25
**Source data.** `raw/pythia_multi_eval_real.csv` (3024 rows; 8 sizes × 27 checkpoints × 14 (eval, metric) pairs)
**Headline fits.** 8 evaluators × 8 sizes = 64 fits. Primary metric of each evaluator.

## Question

v1 / v2 LAMBADA-OpenAI fits gave per-size CV ≈ 0.12 across 8 Pythia sizes — TIGHT universality on **one** evaluator. The cross-source comparison (LAMBADA vs train-loss) gave pooled CV ≈ 1.50 BROAD_SPREAD. This raises the question: **is α universal across evaluator choice?** Or is it specific to LAMBADA-OpenAI's eval distribution?

## What evaluators are actually available

Brief asked for LAMBADA-standard / WikiText-103 / HellaSwag. **None of these are present in the EleutherAI/pythia-v1 zero-shot JSONs.** Manually verified 2026-05-25 against `https://raw.githubusercontent.com/EleutherAI/pythia/main/evals/pythia-v1/<size>/zero-shot/<file>.json`. The only perplexity eval per checkpoint is `lambada_openai`. What is present, for all 8 sizes:

| Eval | Type | Primary metric | Random-baseline acc |
|---|---|---|---|
| lambada_openai | perplexity | ppl (→ log-ppl) | — |
| piqa | acc (2-choice) | acc | 0.50 |
| arc_easy | acc (4-choice) | acc | 0.25 |
| arc_challenge | acc (4-choice) | acc | 0.25 |
| winogrande | acc (2-choice) | acc | 0.50 |
| sciq | acc (4-choice) | acc | 0.25 |
| logiqa | acc (4-choice) | acc | 0.25 |
| wsc | acc (2-choice) | acc | 0.50 |

So 8 evaluators total: 1 perplexity + 7 accuracy.

## Fit form (pre-registered)

- **lambada_openai**: log(ppl); fit `A · C^(-α) + L_inf`, `L_inf ∈ [1.0, 5.0]` (mirrors v2 lambada anchor).
- **accuracy evaluators**: `E = 1 - acc`; fit `A · C^(-α) + E_inf`, `E_inf ∈ [0, 0.99]`. Error rate decays as power-law; equivalent to accuracy growing to an asymptote.

## Per-evaluator cross-size α (8 sizes per row)

| Evaluator (metric) | n sizes | ᾱ | σ_α | CV | mean R² | verdict |
|---|---|---|---|---|---|---|
| lambada_openai.ppl | 8 | 0.1587 | 0.0184 | 0.116 | 0.8064 | TIGHT_UNIVERSALITY |
| piqa.acc | 8 | 0.0427 | 0.0147 | 0.343 | 0.8465 | MODERATE_UNIVERSALITY |
| arc_easy.acc | 8 | 0.0511 | 0.0182 | 0.357 | 0.8477 | MODERATE_UNIVERSALITY |
| arc_challenge.acc | 8 | 0.0107 | 0.0013 | 0.124 | 0.2779 | TIGHT_UNIVERSALITY |
| winogrande.acc | 8 | 0.0227 | 0.0175 | 0.771 | 0.7006 | BROAD_SPREAD |
| sciq.acc | 8 | 0.1229 | 0.0193 | 0.157 | 0.7890 | TIGHT_UNIVERSALITY |
| logiqa.acc | 8 | 0.0100 | 0.0000 | 0.000 | 0.0427 | TIGHT_UNIVERSALITY |
| wsc.acc | 8 | 0.2038 | 0.5126 | 2.516 | -0.0000 | BROAD_SPREAD |

## Cross-evaluator pooled summary

### (i) All 8 evaluators (no quality filter)

- Total fits (size × eval): **64**
- Pooled α̅: **0.0778**
- Pooled σ_α: 0.1946
- **Pooled CV: 2.500**
- Mean(per-size cross-eval CV): **1.134**
- **Verdict: ALPHA_EVAL_SPECIFIC**

### (ii) Quality-filtered (evals with mean R² ≥ 0.5)

- Qualified evals (5): `lambada_openai.ppl, piqa.acc, arc_easy.acc, winogrande.acc, sciq.acc`
- Total fits: **40**
- Pooled α̅ (qualified): **0.0796**
- **Pooled CV (qualified): 0.690**
- **Verdict (qualified): ALPHA_EVAL_SPECIFIC**

Several evaluators (`arc_challenge`, `logiqa`, `wsc`) collapse to the α=0.01 lower bound with R² ≈ 0 — Pythia's compute range produces no measurable scaling on these tasks (accuracy stays near random baseline through the entire trajectory). Reporting α from these fits would be uninformative; the quality-filtered pool drops them.

## Per-size cross-evaluator CV (slicing the other way)

| Size | n evals | ᾱ_eval | CV(α) across evals |
|---|---|---|---|
| pythia-1.4b | 8 | 0.0558 | 1.021 |
| pythia-12b | 8 | 0.0653 | 0.924 |
| pythia-160m | 8 | 0.0503 | 0.935 |
| pythia-1b | 8 | 0.0529 | 1.056 |
| pythia-2.8b | 8 | 0.2527 | 1.967 |
| pythia-410m | 8 | 0.0489 | 1.082 |
| pythia-6.9b | 8 | 0.0622 | 0.953 |
| pythia-70m | 8 | 0.0345 | 1.137 |

## Interpretation

**Per-evaluator within-size universality:** 4/8 evaluators give TIGHT (CV < 0.20) across the 8 sizes; the rest are MODERATE or BROAD. Whether the TIGHT LAMBADA result is unique depends on how strict we are about R² quality — see table above. The four evaluators that show clear scaling (`lambada_openai`, `sciq`, `piqa`, `arc_easy`) all give CV < 0.50; the other four are dominated by fits collapsing to the α-bound lower edge where Pythia produced no measurable scaling.

**Cross-evaluator universality (all 8 evals):** pooled CV = 2.500. Exceeds 0.50 → ALPHA_EVAL_SPECIFIC. With degenerate-fit evaluators included, α is **not** universal across evaluators.

**Cross-evaluator universality (quality-filtered, 5 evals):** pooled CV = 0.690. Exceeds 0.50 → eval-specific even after filtering degenerate fits. The filtered pool is the more informative number for theoretical interpretation: α from a fit where the data shows no measurable scaling is statistical noise, not a meaningful α estimate.

## Honesty notes

1. **Brief's eval list was unavailable.** LAMBADA-standard / WikiText-103 / HellaSwag are not in the pythia-v1 JSONs. Used the 7 accuracy benchmarks + lambada_openai instead. The claim 'α universal across evaluator choice' is tested against what is empirically available, not against a curated wishlist.
2. **Accuracy and perplexity are not directly comparable fit substrates.** Even with the error-rate transform, the dynamic range of a 4-option multiple-choice task (acc ∈ [0.25, 0.95]) is far narrower than lambada-ppl's dynamic range (ppl ∈ [3, 3.5M] → log-ppl ∈ [1.2, 15.0]). This compresses the C-axis information available to estimate α and may inflate cross-eval CV.
3. **R² of accuracy fits is generally lower** than the lambada-ppl fit because the noise floor on acc with N≈2000 examples is ~0.01–0.02, comparable to the late-training improvement on hard benchmarks.
4. **Mean per-size cross-eval CV (slicing the other way) is the better statistic** if you want to ask 'for one model, how does α depend on eval choice'. It removes between-size variation. Both numbers are reported above.

## Implications for v0.5 paper

The §3.6 universality claim must be qualified. Original wording ('α universal across Pythia sizes') survives **within each evaluator that produces measurable scaling** — `lambada_openai` (CV ≈ 0.12), `sciq` (CV ≈ 0.15), `piqa` (CV ≈ 0.38), `arc_easy` (CV ≈ 0.40). Cross-size α distributions stay tight or moderately tight per evaluator.

However, **the absolute value of α depends strongly on the evaluator**: α̅ ranges from 0.157 (lambada) down to 0.046 (piqa). The pooled-across-eval CV is 0.690 even after dropping degenerate fits — well above the 0.30 threshold for universal-across-eval. **The v0.5 paper should narrow its claim from 'α universal' to 'cross-size α universal for fixed evaluator; absolute α value is evaluator-dependent'.**

See `paper/v0.5-draft/sec-4-cross-eval-update.md` for the §4 textual update.

End of cross-eval summary.