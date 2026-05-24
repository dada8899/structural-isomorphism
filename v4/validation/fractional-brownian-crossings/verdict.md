# Verdict — Fractional Brownian Motion / Level-Crossings (Cross-Domain)

> **Date.** 2026-05-25
> **System.** fBm level-crossings cross-domain universality test.
> **Class.** `fractional_brownian_crossings` (textbook-class entry, NO pre-existing KB predictions).
> **Verdict.** **REJECT-as-mathematical-descriptor**
> **Reason.** H spread 0.361 > 0.15; estimator disagreement in ['finance_hf_log_price']

## Pre-registered PASS gate

- Per-domain trajectory length N ≥ 500
- Cross-domain real-data H median spread ≤ 0.15
- R/S vs DFA per-series disagreement median ≤ 0.20

## Synthetic pipeline calibration (Davies-Harte ground-truth recovery)

| H_true | H_est_median | bias |
|---:|---:|---:|
| 0.30 | 0.344 | +0.044 |
| 0.50 | 0.494 | -0.006 |
| 0.70 | 0.687 | -0.013 |
| 0.90 | 0.876 | -0.024 |

Davies-Harte simulation is the standard exact fBm method; we use it
as a ground-truth pipeline calibration. Bias in the table reflects
R/S + DFA bias on finite-N (N=4096); textbook bias of these estimators
for H near 0.9 is well known (Bardet-Lang 2003 J Time Ser Anal).

## Per-domain Hurst summary

| Domain | n_series | H median | H p25 | H p75 | H range | est. disagree median |
|---|---:|---:|---:|---:|---:|---:|
| climate_temp_anomaly | 9 | 0.838 | 0.796 | 0.861 | [0.741, 1.012] | 0.072 |
| finance_hf_log_price | 5 | 1.252 | 1.246 | 1.255 | [1.239, 1.281] | 0.460 |
| finance_hf_log_return | 5 | 0.478 | 0.477 | 0.491 | [0.466, 0.500] | 0.030 |
| hydrology_nile_annual | 6 | 0.780 | 0.707 | 0.804 | [0.558, 0.847] | 0.044 |
| synthetic_fbm_H03 | 8 | 0.344 | 0.339 | 0.358 | [0.336, 0.378] | 0.074 |
| synthetic_fbm_H05 | 8 | 0.494 | 0.489 | 0.520 | [0.473, 0.527] | 0.038 |
| synthetic_fbm_H07 | 8 | 0.687 | 0.671 | 0.726 | [0.635, 0.749] | 0.019 |
| synthetic_fbm_H09 | 8 | 0.876 | 0.854 | 0.908 | [0.726, 0.937] | 0.044 |

## Cross-domain Hurst spread (real-data domains only)

- Real-domain H medians: {'climate_temp_anomaly': 0.8381012939115842, 'finance_hf_log_return': 0.47754222683576975, 'hydrology_nile_annual': 0.7804606717660373}
- max(H) − min(H) = **0.3605590670758144**
- Pre-reg threshold for cluster: ≤ 0.15
- Insufficient-N domains: none
- Estimator-disagreement violations: ['finance_hf_log_price']

## Interpretation

Cross-domain Hurst medians scatter beyond the pre-registered cluster threshold. Each domain has its own characteristic H (finance ~0.5 ordinary random walk for returns / ~1.0 integrated price; hydrology ~0.7 long-memory; climate ~0.85 strongly persistent). **fBm is a *mathematical descriptor* not a mechanism universality class** — analogous to `second_order_damped_oscillator`. The Hurst parameter is a common parameterisation across domains but does *not* impose a cross-domain scaling collapse.

## Paper positioning recommendation

- **Demote** `fractional_brownian_crossings` to a *Layer-0 mathematical descriptor* in v0.4 taxonomy (sibling of `second_order_damped_oscillator`, `markov_chain_memory_fidelity`, `tail_copula_contagion`, `extreme_value_tail_class`).
- Keep the Hurst-exponent / α=2−H relation as a *parameter family* for long-memory processes; do NOT claim it as a mechanism class.
- KB members from finance / hydrology / climate / Internet stay linked by the *shared modelling framework*, but flagged 'descriptor' not 'mechanism'.

## Reproduction

```bash
cd ~/Projects/structural-isomorphism
.venv/bin/python v4/validation/fractional-brownian-crossings/run_validation.py
```

Wall-clock ~1-3 min (yfinance 1-min fetch dominates).

End of verdict card.
