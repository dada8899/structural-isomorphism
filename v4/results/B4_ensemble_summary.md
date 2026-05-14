# B4 — Heterogeneous-vendor ensemble review summary

**Date**: 2026-05-14  
**Reviewers**: deepseek-pro-rigorous, deepseek-flash-rigorous, deepseek-pro-high-creativity  
**Classes reviewed**: 8  
**Total verdicts**: 24  
**Errors**: 0, **Parse failures**: 0  
**Total wall time**: 7.8 min  

## Setup notes

- OpenRouter Kimi-K2.5 unavailable (OPENROUTER_API_KEY missing); fallback to DeepSeek-pro T=1.0 (NOT a true cross-architecture probe)

## Per-class verdict table

| class_id | deepseek-pro-rigorous | deepseek-flash-rigorous | deepseek-pro-high-creativity | B4 consensus | avg_conf |
|---|---|---|---|---|---|
| `delay_differential_debt` | REJECT | UNCLEAR | SPLIT | **UNCLEAR** | 0.60 |
| `extreme_value_tail_class` | REJECT | REJECT | REJECT | **REJECT** | 0.95 |
| `gardner_collins_toggle_switch_Th1Th2` | MERGE | MERGE | MERGE | **MERGE** | 0.95 |
| `hysteresis_preisach` | REJECT | REJECT | REJECT | **REJECT** | 0.82 |
| `motter_lai_network_cascade` | KEEP | REJECT | UNCLEAR | **UNCLEAR** | 0.73 |
| `scheffer_fold_bifurcation` | UNCLEAR | UNCLEAR | KEEP | **UNCLEAR** | 0.58 |
| `schelling_credible_commitment` | REJECT | REJECT | REJECT | **REJECT** | 0.93 |
| `tail_copula_contagion` | REJECT | REJECT | REJECT | **REJECT** | 0.80 |

## B4 consensus distribution

- **KEEP**: 0
- **REJECT**: 4
- **SPLIT**: 0
- **MERGE**: 1
- **UNCLEAR**: 3

## B3 vs B4 agreement (see B3_taxonomy_v2.jsonl for B3 consensus)

Compare B4 consensus column above with B3 consensus from B3_taxonomy_v2.jsonl.

## Methodology notes

- B4 adds cross-vendor / cross-architecture probe to address the B3 limitation that 3 DeepSeek reviewers probe within-model confidence drift but not architectural disagreement.
- If Kimi-K2.5 reachable via OpenRouter, third reviewer is cross-architecture; else fallback is DeepSeek-pro T=1.0 which is in-vendor and therefore a WEAKER cross-architecture probe (logged in setup notes).
- Consensus rule: majority (>=2/3) for KEEP/REJECT/SPLIT/MERGE; else UNCLEAR. Identical to B3 for compatibility.
