# B3 — Multi-model ensemble review summary

**Date**: 2026-05-13  
**Reviewers**: 3 (deepseek-v4-pro rigorous T=0.0, deepseek-v4-flash rigorous T=0.0, deepseek-v4-pro creative T=0.6)  
**Classes reviewed**: 21  
**Total verdicts**: 63  
**Errors**: 0, **Parse failures**: 0  
**Total wall time**: 40.8 min  

## Per-class verdict table

| class_id | B1 | deepseek-pro-rigorous | deepseek-flash-rigorous | deepseek-pro-creative | B3 consensus | avg_conf |
|---|---|---|---|---|---|---|
| `adverse_selection_unraveling_class` | SPLIT | SPLIT | SPLIT | SPLIT | **SPLIT** | 0.92 |
| `delay_differential_debt` | KEEP | REJECT | REJECT | KEEP | **REJECT** | 0.75 |
| `extreme_value_tail_class` | REJECT | REJECT | REJECT | REJECT | **REJECT** | 0.93 |
| `gardner_collins_toggle_switch_Th1Th2` | MERGE_WITH(gardner_collins_toggle_switch_apoptosis) | MERGE | MERGE | MERGE | **MERGE** | 0.95 |
| `gardner_collins_toggle_switch_apoptosis` | MERGE_WITH(gardner_collins_toggle_switch_Th1Th2) | MERGE | MERGE | MERGE | **MERGE** | 0.93 |
| `hysteresis_first_order_transition_fertility` | KEEP | MERGE | REJECT | MERGE | **MERGE** | 0.83 |
| `hysteresis_preisach` | SPLIT | REJECT | REJECT | SPLIT | **REJECT** | 0.82 |
| `leaky_integrate_fire_threshold_class` | SPLIT | SPLIT | SPLIT | SPLIT | **SPLIT** | 0.75 |
| `markov_chain_memory_fidelity_class` | REJECT | REJECT | REJECT | REJECT | **REJECT** | 0.94 |
| `motter_lai_network_cascade` | KEEP | KEEP | SPLIT | SPLIT | **SPLIT** | 0.83 |
| `motter_lai_network_cascade_social` | MERGE_WITH(motter_lai_network_cascade) | MERGE | MERGE | REJECT | **MERGE** | 0.93 |
| `percolation_connectivity` | KEEP | SPLIT | KEEP | SPLIT | **SPLIT** | 0.89 |
| `preferential_attachment` | KEEP | UNCLEAR | KEEP | KEEP | **KEEP** | 0.75 |
| `reaction_diffusion_steady_state_class` | KEEP | KEEP | REJECT | KEEP | **KEEP** | 0.85 |
| `reflexive_fixed_point_class` | KEEP | KEEP | REJECT | KEEP | **KEEP** | 0.73 |
| `scale_free_percolation_class` | KEEP | KEEP | REJECT | REJECT | **REJECT** | 0.77 |
| `scheffer_fold_bifurcation` | KEEP | KEEP | KEEP | KEEP | **KEEP** | 0.88 |
| `schelling_credible_commitment` | REJECT | REJECT | REJECT | REJECT | **REJECT** | 0.91 |
| `second_order_damped_oscillator` | KEEP | KEEP | KEEP | KEEP | **KEEP** | 0.93 |
| `sir_contagion_network_class` | SPLIT | SPLIT | REJECT | SPLIT | **SPLIT** | 0.83 |
| `tail_copula_contagion` | KEEP | REJECT | REJECT | SPLIT | **REJECT** | 0.76 |

## B3 consensus distribution

- **KEEP**: 5
- **REJECT**: 7
- **SPLIT**: 5
- **MERGE**: 4
- **UNCLEAR**: 0

## Raw verdict distribution (across all 63 calls)

- **REJECT**: 22
- **KEEP**: 16
- **SPLIT**: 14
- **MERGE**: 10
- **UNCLEAR**: 1

## B1 critic vs B3 ensemble agreement

- Agree (B1 simplified == B3 consensus): **14** / 21
- Disagree: **7** / 21

## Methodology notes

- 3 DeepSeek-only reviewers (same vendor, different model/temperature configurations).
- v4-pro @ T=0.0 = main rigorous reviewer (full chain-of-thought reasoning).
- v4-flash @ T=0.0 = faster light-weight reviewer (less reasoning depth, similar prompt).
- v4-pro @ T=0.6 = creative dissenter system prompt (probes confidence drift via temperature + adversarial role).
- Cross-family ensemble (Kimi / GLM-5) NOT yet wired due to OpenRouter CN region-block + unverified backup-router base URLs.
- **Limitation**: same-model-family ensemble probes within-model confidence drift, not architectural disagreement. Will be addressed in B4+ with verified cross-vendor router.
- Consensus rule: majority (≥2/3) for KEEP/REJECT/SPLIT/MERGE; else UNCLEAR.
