# D1 batch run 2026-05-13 — stats

## Counts

- rows processed: **100**
- ok: **97**
- failed: **3**

## Dynamics family distribution (ok rows)

| family | count | pct |
|---|---:|---:|
| linear_quasi_equilibrium | 29 | 29.9% |
| preferential_attachment | 19 | 19.6% |
| reflexive_fixed_point | 16 | 16.5% |
| soc_threshold_cascade | 10 | 10.3% |
| scheffer_fold | 8 | 8.2% |
| motter_lai_cascade | 7 | 7.2% |
| hysteresis_preisach | 4 | 4.1% |
| extreme_value_tail | 3 | 3.1% |
| mixed_or_unclear | 1 | 1.0% |

## Critical-point state distribution (ok rows)

| state | count | pct |
|---|---:|---:|
| far_from_critical | 46 | 47.4% |
| approaching_critical | 27 | 27.8% |
| post_critical_transition | 14 | 14.4% |
| at_critical | 9 | 9.3% |
| unknown | 1 | 1.0% |

## Agreement with a-priori expectation

- match: **63** (65.6% of 96 priored rows)
- differ: 33
- no_prior: 1

### LLM family vs a-priori (where prior exists)

| a-priori expected | LLM assigned | count |
|---|---|---:|
| extreme_value_tail | extreme_value_tail ✓ | 1 |
| hysteresis_preisach | linear_quasi_equilibrium | 3 |
| hysteresis_preisach | reflexive_fixed_point | 1 |
| hysteresis_preisach | scheffer_fold | 1 |
| hysteresis_preisach | hysteresis_preisach ✓ | 1 |
| linear_quasi_equilibrium | linear_quasi_equilibrium ✓ | 20 |
| linear_quasi_equilibrium | preferential_attachment | 1 |
| linear_quasi_equilibrium | hysteresis_preisach | 1 |
| linear_quasi_equilibrium | scheffer_fold | 1 |
| linear_quasi_equilibrium | mixed_or_unclear | 1 |
| linear_quasi_equilibrium | motter_lai_cascade | 1 |
| motter_lai_cascade | motter_lai_cascade ✓ | 5 |
| motter_lai_cascade | hysteresis_preisach | 1 |
| motter_lai_cascade | soc_threshold_cascade | 1 |
| preferential_attachment | preferential_attachment ✓ | 16 |
| preferential_attachment | linear_quasi_equilibrium | 3 |
| preferential_attachment | reflexive_fixed_point | 3 |
| reflexive_fixed_point | reflexive_fixed_point ✓ | 6 |
| reflexive_fixed_point | preferential_attachment | 1 |
| scheffer_fold | reflexive_fixed_point | 6 |
| scheffer_fold | scheffer_fold ✓ | 5 |
| scheffer_fold | linear_quasi_equilibrium | 2 |
| scheffer_fold | extreme_value_tail | 1 |
| scheffer_fold | preferential_attachment | 1 |
| scheffer_fold | motter_lai_cascade | 1 |
| soc_threshold_cascade | soc_threshold_cascade ✓ | 9 |
| soc_threshold_cascade | linear_quasi_equilibrium | 1 |
| soc_threshold_cascade | scheffer_fold | 1 |
| soc_threshold_cascade | hysteresis_preisach | 1 |

## LLM cost (DeepSeek v4-pro direct API, estimated)

- prompt tokens total: 72,702
- prompt cache hit: 9,600 (13.2%)
- completion tokens: 169,167
- estimated cost: **$0.4059** USD
  - prompt miss @ $0.55/M: $0.0347
  - prompt hit  @ $0.07/M: $0.0007
  - completion  @ $2.19/M: $0.3705
- total LLM attempts: 108 (avg 1.11/row)
- total elapsed (sum across parallel batches): 6151.8s

## Output

- merged jsonl: `structtuples_2026-05-13.jsonl` (100 rows)
