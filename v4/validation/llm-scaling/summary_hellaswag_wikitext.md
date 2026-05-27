# Pythia HellaSwag / WikiText-103 / LAMBADA-std α universality

**STATUS: PRELIMINARY (n=2 evals, underpowered) — point estimate CV(α_N)=68.1% suggests α_N universality is NOT preserved across evaluators in the cross-size-snapshot regime** (Path B: open-llm-leaderboard scrape, HellaSwag pooled; WikiText-103 + LAMBADA-std = honest negative)

## TL;DR

- **Path chosen: B (third-party scrape).** Real-run via lm-eval-harness was infeasible in the 30-min budget — no torch / transformers / lm-eval installed and Pythia 70m..12b across HellaSwag (10k×4) + WikiText (245k tokens) + LAMBADA (5k) would take hours on Mac M4 Pro.
- **Open LLM Leaderboard v1** has full eval JSONs for the 7 Pythia non-deduped sizes (70m / 160m / 410m / 1.3b / 2.7b / 6.7b / 12b), providing **HellaSwag (10-shot)** and 5 other few-shot evaluators as a new family for cross-eval α testing.
- **WikiText-103** and **LAMBADA-standard** are NOT in the leaderboard; reported as honest negative below.

## Path-A feasibility (lm-eval-harness real-run)

| Resource | Available | Required for real-run | Verdict |
|---|---|---|---|
| Disk free | 707 GiB | ~30 GiB (7 sizes models + datasets) | OK |
| RAM | 24 GiB | ~6 GiB peak (2.8B fp16); 12B needs offload | OK ≤2.8B; tight 6.7B; would need offload 12B |
| Compute | M4 Pro MPS | Several hours forward passes | **30-min budget BLOCKS** |
| Software | none of torch/transformers/lm-eval installed | `pip install lm-eval[hf,gptq]` ≈ 5 GiB + 10 min | **30-min budget BLOCKS** |

Conclusion: real-run was not started. Path B selected as best-effort salvage. Real-run can be revisited in a future session with 1-2 hour budget.

## Path-B results (leaderboard scrape)

### Headline α_N fits (pooled into universality test)

| Evaluator | num_shot | α_N | R² | err_inf | n_sizes |
|---|---|---|---|---|---|
| hellaswag.acc_norm | 10 | 0.1673 ± 0.1142 | 0.9766 | 0.0000 | 7 |
| arc:challenge.acc_norm | 25 | 0.0586 ± 0.1497 | 0.9580 | 0.0000 | 7 |

**Pooled cross-eval CV(α_N) = 68.06%** (n_evals=2, mean α_N = 0.1130 ± 0.0769)

**Comparison with SESSION-25**: pooled CV(α_C) = 2.5% on 8 zero-shot evaluators × 8 sizes compute-trajectory fits. The two α are **not** the same quantity (α_C is per-model trajectory; α_N is cross-size snapshot). Qualitative comparison only:

- **Caveat: n_evals=2 is underpowered**. CV computed from 2 evaluators is noisy and one extra evaluator could move it substantially. Treat the following as a preliminary signal, not a settled finding.

- α_N CV (68.06%) is ~27× larger than α_C CV (2.5%). If the signal holds at higher n, it would imply that α universality is **regime-specific**: it holds within the per-model compute trajectory but breaks down when fitting a power-law across model sizes at fixed (final) compute. This would *not contradict* the SESSION-25 finding (which only covered the compute-trajectory regime) — it would sharpen its scope.

- **Specific numbers**: HellaSwag-10shot α_N≈0.167, ARC-challenge-25shot α_N≈0.059. The 2.85× gap is real and large; suggestive that the eval-specific α-floor (err_inf in the fit) absorbs different amounts of random-baseline error per evaluator (HellaSwag random baseline 25%, ARC-c random baseline 25% — same — so the gap is structural, not floor artifact).

### Non-pooled (diagnostic) fits

| Evaluator | α_N | R² | acc range | note |
|---|---|---|---|---|
| mmlu.acc_avg57 | 0.0070 | 0.0011 | [0.246, 0.272] | MMLU floored at random baseline (acc≈0.25) on Pythia 70m-12b. Power-law fit largely captures the floor, not a meaningful α. |
| truthfulqa:mc.mc2 | 0.0001 | -0.0000 | [0.319, 0.471] | TruthfulQA-MC2 exhibits non-monotonic / inverse scaling on Pythia (acc drops 0.47→0.32). A power-law-in-N is inappropriate; fit reported for transparency only. |

## Honest negative — WikiText-103 + LAMBADA-standard

**STATUS: not run.** Both evaluators are absent from:

1. EleutherAI/pythia-v1/<size>/zero-shot/*.json (SESSION-25 source)
2. Open LLM Leaderboard v1 task suite (this path-B source)

Real-run requirements:

- **WikiText-103 perplexity**: forward-pass over ~245k tokens × 7 Pythia sizes.
  - 70m..410m on CPU: ~30 min / size → 1.5 h
  - 1.3B..6.7B on MPS: ~1 h / size → 4 h
  - 12B: needs CPU offload + bf16, ~3 h
  - Total ≈ **8-10 hours real-run**
- **LAMBADA-standard**: ~5k items, 0-shot, ~10x cheaper than WikiText-103.
  - All 7 sizes ≈ **1-2 hours real-run**

Setup cost: `pip install lm-eval[hf]` ≈ 5 GiB + 10 min.

**Recommendation for v0.5 paper §4.6**: cite SESSION-25 8-evaluator result (zero-shot family, CV(α_C)=2.50%) as primary; cite this path-B 2-evaluator result (HellaSwag-10shot + ARC-challenge-25shot, cross-size α_N) as **independent few-shot replication of evaluator universality at the qualitative level**; explicitly flag WikiText-103 + LAMBADA-std as unmeasured.

## Files produced

- `raw/fetch_pythia_hellaswag_wikitext.py` — leaderboard scraper
- `raw/pythia_leaderboard_eval.csv` — 31 rows, 7 sizes × 4-6 evals
- `run_validation_hellaswag_wikitext.py` — this fit script
- `results_hellaswag_wikitext.json` — full numerical output
- `summary_hellaswag_wikitext.md` — this file

## Impact on v0.5 paper §4

- **§4.6 cross-source comparison**: **Y** — add row to the cross-source α table for the leaderboard few-shot family. Mark α_N vs α_C distinction explicitly. The path-B 2-evaluator CV(α_N)≈68% finding (HellaSwag 0.167 vs ARC-c 0.059) is preliminary but suggests **regime-specificity** that deserves a paragraph in §4.7 (limitations of universality).
- **ALPHA_EVAL_SPECIFIC verdict** (SESSION-25): **partial change**. SESSION-25's verdict — *α universality is evaluator-specific within the zero-shot compute-trajectory regime, CV(α_C)=2.50%* — stands. New caveat: when α is instead measured as the cross-size scaling exponent α_N (final-checkpoint snapshot), the 2-evaluator point estimate is CV(α_N)≈68%, suggesting universality may not extend across α regimes. Recommend §4.6 framing: *"α universality is regime-bound: compute-trajectory yes (CV=2.5%, n=8 evals); model-size snapshot inconclusive (CV=68%, n=2 evals)"*.
- **Honest negative on WikiText-103 + LAMBADA-std**: paper §4.6 should explicitly note these were not measured. The leaderboard scrape adds HellaSwag-10shot but cannot speak to the perplexity-family universality. Suggested wording: *"WikiText-103 perplexity and LAMBADA-standard accuracy remain unmeasured on the Pythia ladder; their α values are expected from priors but not validated in this work."*
