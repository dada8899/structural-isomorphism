# §4 update — Pythia cross-evaluator α universality (SESSION-25)

**Status.** Drop-in update for the v0.5 paper's §4 (Pythia scaling-law universality). Sub-agent run 2026-05-25; raw data at `v4/validation/llm-scaling/raw/pythia_multi_eval_real.csv`; results at `v4/validation/llm-scaling/results_cross_eval.json`; per-fit table at `v4/validation/llm-scaling/summary_cross_eval.md`.

---

## What v0.5 previously claimed

§4 (and §3.6 in v0.4 carry-over) reports per-size Pythia α fits on LAMBADA-OpenAI perplexity:

| Run | sizes | ᾱ | CV | mean R² | Verdict |
|---|---|---|---|---|---|
| v1 (free L_inf) | 8 | 0.144 | 0.118 | 0.82 | TIGHT_UNIVERSALITY |
| v2 (L_inf ≥ 1.0) | 8 | 0.159 | 0.116 | 0.81 | TIGHT_UNIVERSALITY |

The headline reading: **α is universal across model size** for Pythia, with CV < 0.20 across 8 sizes spanning ~170× in parameter count. This generalises to a claim about α as a stable scaling exponent for the Pythia training-data manifold.

## What this update tests

Universality across model size (different N, same eval) ≠ universality across evaluator (different eval, same N). The cross-source α run already showed that mixing LAMBADA with train-loss gives BROAD_SPREAD (CV ≈ 1.50). This update isolates the cross-evaluator question on **a single source** (all eval-harness JSONs, same lm-eval-harness implementation).

## Method

1. **Multi-evaluator fetch.** Extended the SESSION-24 fetcher to pull every evaluator's primary metric from the same per-checkpoint JSONs at `evals/pythia-v1/<size>/zero-shot/*_step<N>.json`. All 8 sizes × 27 checkpoints × 8 evaluators = 1728 (size, eval, step) observations.
2. **Brief-requested evaluators not available.** LAMBADA-standard, WikiText-103, and HellaSwag are **absent** from these JSONs. The brief's eval wishlist could not be honoured; what is empirically present is the substrate.
3. **Available evaluators (8 total):**
   - Perplexity: `lambada_openai` (ppl → log-ppl)
   - Accuracy: `piqa`, `arc_easy`, `arc_challenge`, `winogrande`, `sciq`, `logiqa`, `wsc` — primary metric `acc`
4. **Fit form (pre-registered).** Both forms are `L(C) = A · C^(-α) + L_inf`. For lambada-ppl, `L_inf ∈ [1.0, 5.0]` (literature anchor). For accuracy, the dependent variable is error rate `E = 1 − acc` with `E_inf ∈ [0, 0.99]`. This is the error-rate-falls-as-power-law form, equivalent (modulo parameterisation) to acc-grows-to-asymptote.
5. **No warmup filter.** All 27 checkpoints kept per size, mirroring v2.

## Per-evaluator results (8 sizes per row)

| Evaluator (metric) | ᾱ | CV | mean R² | Per-eval verdict |
|---|---|---|---|---|
| lambada_openai.ppl  | 0.1587 | 0.116 | 0.806 | TIGHT_UNIVERSALITY |
| piqa.acc            | 0.0427 | 0.343 | 0.847 | MODERATE_UNIVERSALITY |
| arc_easy.acc        | 0.0511 | 0.357 | 0.848 | MODERATE_UNIVERSALITY |
| arc_challenge.acc   | 0.0107 | 0.124 | 0.278 | TIGHT (degenerate — bound) |
| winogrande.acc      | 0.0227 | 0.771 | 0.701 | BROAD_SPREAD |
| sciq.acc            | 0.1229 | 0.157 | 0.789 | TIGHT_UNIVERSALITY |
| logiqa.acc          | 0.0100 | 0.000 | 0.043 | TIGHT (degenerate — bound) |
| wsc.acc             | 0.2038 | 2.516 | -0.000 | BROAD_SPREAD |

**Degenerate notes.** Three evaluators (`arc_challenge`, `logiqa`, `wsc`) produce fits where most sizes collapse to the α=0.01 lower bound with R² ≈ 0. Interpretation: Pythia's training-compute range does not produce measurable scaling on these tasks — accuracy stays near chance throughout the full trajectory. The α values from these fits are uninformative.

## Cross-evaluator pooled summary

| Pool | n fits | ᾱ | Pooled CV | Verdict (pre-registered ladder) |
|---|---|---|---|---|
| All 8 evals | 64 | 0.078 | **2.500** | ALPHA_EVAL_SPECIFIC |
| Quality-filtered (R² ≥ 0.5, 5 evals: lambada/piqa/arc_easy/winogrande/sciq) | 40 | 0.075 | **0.690** | ALPHA_EVAL_SPECIFIC |

The quality-filtered pool is the more informative number. Even after dropping the three degenerate evaluators, **pooled CV = 0.69 > 0.50** — above the ALPHA_EVAL_SPECIFIC threshold.

## Headline finding

**Cross-size α universality survives within each evaluator that produces measurable scaling. Cross-evaluator α universality does not.**

Concretely:
- `lambada_openai`: ᾱ = 0.159 (CV across 8 sizes = 0.12 — tight)
- `sciq`: ᾱ = 0.123 (CV = 0.16 — tight)
- `piqa`: ᾱ = 0.043 (CV = 0.34 — moderate)
- `arc_easy`: ᾱ = 0.051 (CV = 0.36 — moderate)

Within each evaluator, the 8 Pythia sizes give a coherent α. **Between evaluators, ᾱ ranges from 0.043 (piqa) to 0.159 (lambada) — a factor of ~3.7× difference.** That spread is not a measurement artifact (R² ≥ 0.8 on each of these evaluators); it reflects that the *amount* of compute needed to reduce error/loss by a factor of e is task-dependent, even when both tasks are evaluated on the same model checkpoints from the same training run.

## How v0.5's claims must change

### Original §4 claim (v0.4 carry-over, retained in v0.5 skeleton)

> "Pythia 8 sizes give CV < 0.20 on LAMBADA-OpenAI scaling exponent α, establishing TIGHT cross-size universality of the scaling law for language-model training."

### Replacement claim for v0.5

> "Pythia 8 sizes give CV < 0.20 on LAMBADA-OpenAI log-perplexity α — TIGHT cross-size universality **for that evaluator**. The within-evaluator universality replicates on SciQ (CV = 0.16). On evaluators with weaker signal (PIQA, ARC-easy), within-size universality is moderate (CV ≈ 0.34–0.36). The **absolute value of α depends strongly on evaluator**: ᾱ on LAMBADA (0.159) is ~3.7× larger than ᾱ on PIQA (0.043). Cross-evaluator α universality is **not** supported by this data (pooled CV = 0.69 across qualified evaluators)."

### Theoretical implication

The v0.5 "α as scaling-law universality marker" framing should be qualified:
- α is a **per-(evaluator, model-family) constant**, not a universal scaling exponent of training compute.
- Two practitioners measuring "the Pythia scaling exponent" on different benchmarks will report different α values, even though their data is internally consistent.
- The cross-domain isomorphism claim (§5+, comparing α across LLM / Schelling / aggregation kinetics) must specify *which* α — the one fitted on the natural choice of loss / error metric for that domain. The implicit comparison "Pythia α ≈ Schelling α ≈ kinetics α" is meaningful only if the chosen metric per domain is the canonical one (cross-entropy on the eval distribution / segregation-deviation / aerosol-moment), not any arbitrary benchmark.

### Updated verdict-matrix row (replaces the current §3.6 row)

| Source | sizes | ᾱ | CV | Verdict |
|---|---|---|---|---|
| Pythia LAMBADA-OpenAI v1 (free L_inf) | 8 | 0.144 | 0.118 | TIGHT (within-eval) |
| Pythia LAMBADA-OpenAI v2 (L_inf ≥ 1.0) | 8 | 0.159 | 0.116 | TIGHT (within-eval) |
| Pythia SciQ acc | 8 | 0.123 | 0.157 | TIGHT (within-eval) |
| Pythia PIQA acc | 8 | 0.043 | 0.343 | MODERATE (within-eval) |
| Pythia ARC-easy acc | 8 | 0.051 | 0.357 | MODERATE (within-eval) |
| **Pythia cross-evaluator pool** (qual., 5 evals) | 40 | 0.075 | **0.690** | **EVAL-SPECIFIC** |
| Train loss (mixed real/syn) | 6 | 0.272 | 0.706 | BROAD_SPREAD |
| Train loss (lit-anchored) | 6 | 0.116 | 0.178 | MODERATE_UNIVERSALITY |

## Honesty notes

1. **Brief asked for evals that don't exist in this corpus.** LAMBADA-standard / WikiText-103 / HellaSwag are not in the EleutherAI/pythia-v1 zero-shot JSONs. If the v0.5 paper needs those evaluators, the authors will need to (i) recompute them by running lm-eval-harness against Pythia HF checkpoints (~$0 cost on a single A100 hour per evaluator-size combo, ~1 day total) or (ii) cite them from other sources where Pythia results are reported. This sub-agent did not have access to either path.
2. **Accuracy fits are inherently less informative than perplexity.** Dynamic range of acc on a 4-option MC task is ≤ 0.75; on log-ppl it is > 10 nats. A fixed observation noise (~0.01 on N≈2000-example acc) eats more of the available signal. Mean R² for accuracy fits clustered at 0.8, vs 0.81 for lambada-ppl — comparable, but the parameter uncertainty on α is intrinsically larger.
3. **WSC and LogiQA degeneracy is real.** These tasks have small evaluation sets (104 / 651 examples) and accuracy hovers near chance. The fact that α collapses to the bound is a property of the data, not the fit method.
4. **WinoGrande slipped past the R² ≥ 0.5 filter (mean R² = 0.70) but has CV = 0.77.** Several sizes hit the α=0.01 bound while others land at 0.03–0.07; the lower-bound sizes inflate CV without lowering R². If we used a stricter quality threshold (CV < 1.0 on within-eval *and* no size at bound), WinoGrande would also drop. With or without it, the qualified pool CV > 0.5.

## Files produced by this update

| File | Purpose |
|---|---|
| `v4/validation/llm-scaling/raw/fetch_pythia_multi_eval.py` | Multi-eval fetcher (new) |
| `v4/validation/llm-scaling/raw/pythia_multi_eval_real.csv` | 3024-row long-form data (new) |
| `v4/validation/llm-scaling/run_validation_cross_eval.py` | Per-(size, eval) fitter (new) |
| `v4/validation/llm-scaling/results_cross_eval.json` | Full JSON results (new) |
| `v4/validation/llm-scaling/summary_cross_eval.md` | Full markdown summary (new) |
| `v4/validation/llm-scaling/figures/cross_eval_alpha.png` | Per-(size, eval) α scatter (new) |
| `paper/v0.5-draft/sec-4-cross-eval-update.md` | This file (drop-in §4 update) |

Existing files untouched: `fetch_pythia_lambada.py`, `run_validation_lambada.py`, `run_validation_lambada_v2.py`, all v1/v2 lambada results.

End of §4 update.
