# B4 DeepSeek heterogeneous ensemble vs B3 — diff report

**Date**: 2026-05-14 (session #8 rerun, DeepSeek-only no OpenRouter)

**Setup**: 3 DeepSeek direct-API reviewers — pro T=0.0 (rigorous), flash T=0.0 (rigorous), pro T=0.7 (chat-baseline). DeepSeek-chat / DeepSeek-reasoner unavailable on this account; v4-pro / v4-flash substituted with 3 temperature / system-prompt variations.

## Per-class verdict diff

| class_id | B3 | B4-deepseek | pattern | B4-orig | reviewers (v_A / v_B / v_C) |
|---|---|---|---|---|---|
| `adverse_selection_unraveling_class` | SPLIT | **SPLIT** | 2/3 | REJECT | SPLIT / REJECT / SPLIT |
| `delay_differential_debt` | REJECT | **REJECT** | 3/3 | UNCLEAR | REJECT / REJECT / REJECT |
| `extreme_value_tail_class` | REJECT | **REJECT** | 3/3 | REJECT | REJECT / REJECT / REJECT |
| `gardner_collins_toggle_switch_Th1Th2` | MERGE | **MERGE** | 3/3 | MERGE | MERGE / MERGE / MERGE |
| `gardner_collins_toggle_switch_apoptosis` | MERGE | **MERGE** | 2/3 | MERGE | REJECT / MERGE / MERGE |
| `hysteresis_first_order_transition_fertility` | MERGE | **REJECT** | 2/3 | REJECT | MERGE / REJECT / REJECT |
| `hysteresis_preisach` | REJECT | **REJECT** | 3/3 | UNCLEAR | REJECT / REJECT / REJECT |
| `leaky_integrate_fire_threshold_class` | SPLIT | **REJECT** | 2/3 | REJECT | REJECT / REJECT / SPLIT |
| `markov_chain_memory_fidelity_class` | REJECT | **REJECT** | 3/3 | REJECT | REJECT / REJECT / REJECT |
| `motter_lai_network_cascade` | SPLIT | **SPLIT** | 2/3 | REJECT | SPLIT / REJECT / SPLIT |
| `motter_lai_network_cascade_social` | MERGE | **MERGE** | 3/3 | MERGE | MERGE / MERGE / MERGE |
| `percolation_connectivity` | SPLIT | **SPLIT** | 2/3 | KEEP | SPLIT / SPLIT / REJECT |
| `preferential_attachment` | KEEP | **UNCLEAR** | all-disagree | UNCLEAR | UNCLEAR / REJECT / KEEP |
| `reaction_diffusion_steady_state_class` | KEEP | **REJECT** | 3/3 | REJECT | REJECT / REJECT / REJECT |
| `reflexive_fixed_point_class` | KEEP | **REJECT** | 2/3 | UNCLEAR | UNCLEAR / REJECT / REJECT |
| `scale_free_percolation_class` | REJECT | **REJECT** | 3/3 | REJECT | REJECT / REJECT / REJECT |
| `scheffer_fold_bifurcation` | KEEP | **KEEP** | 2/3 | UNCLEAR | KEEP / REJECT / KEEP |
| `schelling_credible_commitment` | REJECT | **REJECT** | 3/3 | REJECT | REJECT / REJECT / REJECT |
| `second_order_damped_oscillator` | KEEP | **REJECT** | 3/3 | UNCLEAR | REJECT / REJECT / REJECT |
| `sir_contagion_network_class` | SPLIT | **SPLIT** | 2/3 | REJECT | SPLIT / REJECT / SPLIT |
| `tail_copula_contagion` | REJECT | **REJECT** | 3/3 | REJECT | REJECT / REJECT / REJECT |

## Aggregate metrics

- **Classes compared**: 21
- **3/3 unanimous**: 11 (52%)
- **2/3 majority**: 9 (43%)
- **All-disagree (no majority)**: 1 (5%)

- **B4-deepseek vs B3 AGREE**: 15 / 21 (71%)
- **B4-deepseek vs B3 DIFFER**: 6 / 21 (29%)
- **B4-deepseek vs B4-original AGREE**: 12 / 21 (57%)

## B4-deepseek consensus distribution

- **KEEP**: 1
- **REJECT**: 12
- **SPLIT**: 4
- **MERGE**: 3
- **UNCLEAR**: 1

## Interpretation

### Q1: Is the original B4 (62% disagree) replicable with a different third-reviewer config?

NO — B4-deepseek matches B4-original on only 57% of classes. Third-reviewer config (T=0.7 chat baseline vs T=1.0 cross-domain physicist persona) materially changes the verdict.

### Q2: Is 'DeepSeek 3-config' an acceptable heterogeneity proxy?

**MIXED** — 11/21 unanimous, 9/21 2/3 majority, 1/21 all-disagree. Heterogeneity is present but moderate; useful as a confidence indicator, less so as a robust cross-architecture replacement.

## Methodology notes

- DeepSeek-chat / DeepSeek-reasoner unavailable on this account (api.deepseek.com/models returns only deepseek-v4-pro / deepseek-v4-flash). Substituted with 3 temperature / system-prompt variations of v4-pro/v4-flash.
- Cost budget: $5 USD enforced via per-call running-total check; actual spend logged in script stderr.
- Consensus rule: majority (>=2/3) for KEEP/REJECT/SPLIT/MERGE; else UNCLEAR. Identical to B3/B4 for compatibility.
- ERROR / PARSE_FAIL records (if any) are excluded from consensus computation; pattern is 'all-disagree' if all 3 fail.
