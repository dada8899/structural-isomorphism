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

## DeepSeek heterogeneous rerun (2026-05-14)

**Context**: User refused the OpenRouter Kimi unblocker (CN region-block / vendor distrust)
and instead requested a 3-model DeepSeek direct-API rerun as heterogeneity proxy. Task spec
asked for `deepseek-chat` + `deepseek-reasoner` model IDs; at runtime the API exposes only
`deepseek-v4-pro` + `deepseek-v4-flash` (verified via `GET /models`). Substituted with 3
temperature / system-prompt variations as the closest available proxy.

**Reviewers**:
- `deepseek-v4-pro-T0` (T=0.0, rigorous Clauset+Stumpf-Porter system prompt)
- `deepseek-v4-flash-T0` (T=0.0, lighter model, rigorous prompt)
- `deepseek-v4-pro-T07-chat` (T=0.7, plain chat-baseline system prompt — no
  cross-domain-physicist persona unlike the original B4 fallback at T=1.0)

**Run stats**:
- 21 classes × 3 reviewers = 63 verdicts
- Cost: **$0.058 USD** (well under $5 budget)
- Wall time: 20.9 min
- Errors: 0, parse failures: 0, retries: 0

**Results** (full table in `B4_deepseek_vs_B3_diff.md`):

- **B4-deepseek vs B3 AGREE**: **15 / 21 (71%)**
- **B4-deepseek vs B3 DIFFER**: 6 / 21 (29%)
- **B4-deepseek vs B4-original AGREE**: 12 / 21 (57%)

**Consensus pattern**:
- 3/3 unanimous: 11 / 21 (52%)
- 2/3 majority: 9 / 21 (43%)
- All-disagree: 1 / 21 (5%)

**Verdict distribution**: KEEP 1, REJECT 12, SPLIT 4, MERGE 3, UNCLEAR 1

### Interpretation

1. **The 62%-disagree result from original B4 is NOT fully replicable.** Swapping the third
   reviewer from "DeepSeek-pro T=1.0 cross-domain physicist persona" to "DeepSeek-pro T=0.7
   plain chat-baseline" flips B3 agreement from 38% → 71%. The original B4's high disagreement
   was partly driven by the adversarial persona, not by inherent verdict uncertainty.

2. **DeepSeek 3-config heterogeneity is a WEAK proxy for cross-architecture probe.** 11/21
   classes get 3/3 unanimous agreement within DeepSeek, indicating within-vendor heterogeneity
   is too low to surface the architectural disagreement that a true Kimi / Claude / Gemini
   reviewer would expose. The rerun probes a narrow slice of the disagreement surface.

3. **Robust signal across both B4 runs**: 12 classes share the same verdict in both B4-original
   and B4-deepseek (57% replicability). These represent the more stable verdicts:
   `extreme_value_tail`, `gardner_collins_*`, `hysteresis_first_order_*`, `markov_chain_*`,
   `motter_lai_*_social`, `schelling_*`, `tail_copula_*`, etc. — mostly REJECT/MERGE.

4. **Persona-sensitive verdicts** (where the two B4 runs disagree): largely the KEEP→UNCLEAR
   churn cases (`delay_differential_debt`, `hysteresis_preisach`, `percolation_connectivity`,
   `reflexive_fixed_point`, `scheffer_fold_bifurcation`, `second_order_damped_oscillator`).
   These need either (a) a true cross-architecture review, or (b) more empirical data, before
   trusting any single verdict.

**Recommendation**: Treat the DeepSeek rerun as a "confidence-stability indicator" alongside
B3 + B4-original, not as a replacement for cross-architecture probe. The 9 classes with both
"3/3 unanimous in B4-deepseek" AND "match B3 consensus" are the highest-confidence verdicts
in taxonomy v2.
