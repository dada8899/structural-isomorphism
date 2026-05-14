# B4 — Heterogeneous-vendor ensemble review summary

**Date**: 2026-05-14  
**Reviewers**: deepseek-pro-rigorous, deepseek-flash-rigorous, deepseek-pro-high-creativity  
**Classes reviewed**: 21  
**Total verdicts**: 63  
**Errors**: 0, **Parse failures**: 1  
**Total wall time**: 24.5 min  

## Setup notes

- OpenRouter Kimi-K2.5 unavailable (OPENROUTER_API_KEY missing); fallback to DeepSeek-pro T=1.0 (NOT a true cross-architecture probe)

## Per-class verdict table

| class_id | deepseek-pro-rigorous | deepseek-flash-rigorous | deepseek-pro-high-creativity | B4 consensus | avg_conf |
|---|---|---|---|---|---|
| `adverse_selection_unraveling_class` | REJECT | REJECT | REJECT | **REJECT** | 0.92 |
| `delay_differential_debt` | REJECT | UNCLEAR | KEEP | **UNCLEAR** | 0.62 |
| `extreme_value_tail_class` | REJECT | REJECT | REJECT | **REJECT** | 0.95 |
| `gardner_collins_toggle_switch_Th1Th2` | MERGE | MERGE | MERGE | **MERGE** | 0.95 |
| `gardner_collins_toggle_switch_apoptosis` | REJECT | MERGE | MERGE | **MERGE** | 0.90 |
| `hysteresis_first_order_transition_fertility` | REJECT | REJECT | KEEP | **REJECT** | 0.92 |
| `hysteresis_preisach` | UNCLEAR | REJECT | UNCLEAR | **UNCLEAR** | 0.80 |
| `leaky_integrate_fire_threshold_class` | REJECT | REJECT | SPLIT | **REJECT** | 0.57 |
| `markov_chain_memory_fidelity_class` | REJECT | REJECT | REJECT | **REJECT** | 0.95 |
| `motter_lai_network_cascade` | REJECT | REJECT | KEEP | **REJECT** | 0.92 |
| `motter_lai_network_cascade_social` | MERGE | MERGE | MERGE | **MERGE** | 0.95 |
| `percolation_connectivity` | KEEP | UNCLEAR | KEEP | **KEEP** | 0.83 |
| `preferential_attachment` | UNCLEAR | UNCLEAR | KEEP | **UNCLEAR** | 0.73 |
| `reaction_diffusion_steady_state_class` | REJECT | REJECT | KEEP | **REJECT** | 0.82 |
| `reflexive_fixed_point_class` | UNCLEAR | REJECT | KEEP | **UNCLEAR** | 0.53 |
| `scale_free_percolation_class` | REJECT | REJECT | UNCLEAR | **REJECT** | 0.68 |
| `scheffer_fold_bifurcation` | UNCLEAR | REJECT | KEEP | **UNCLEAR** | 0.90 |
| `schelling_credible_commitment` | REJECT | REJECT | REJECT | **REJECT** | 0.93 |
| `second_order_damped_oscillator` | PARSE_FAIL | UNCLEAR | KEEP | **UNCLEAR** | 0.52 |
| `sir_contagion_network_class` | REJECT | REJECT | SPLIT | **REJECT** | 0.77 |
| `tail_copula_contagion` | REJECT | REJECT | REJECT | **REJECT** | 0.88 |

## B4 consensus distribution

- **KEEP**: 1
- **REJECT**: 11
- **SPLIT**: 0
- **MERGE**: 3
- **UNCLEAR**: 6

## B3 vs B4 agreement (see B3_taxonomy_v2.jsonl for B3 consensus)

Compare B4 consensus column above with B3 consensus from B3_taxonomy_v2.jsonl.

## Methodology notes

- B4 adds cross-vendor / cross-architecture probe to address the B3 limitation that 3 DeepSeek reviewers probe within-model confidence drift but not architectural disagreement.
- If Kimi-K2.5 reachable via OpenRouter, third reviewer is cross-architecture; else fallback is DeepSeek-pro T=1.0 which is in-vendor and therefore a WEAKER cross-architecture probe (logged in setup notes).
- Consensus rule: majority (>=2/3) for KEEP/REJECT/SPLIT/MERGE; else UNCLEAR. Identical to B3 for compatibility.
