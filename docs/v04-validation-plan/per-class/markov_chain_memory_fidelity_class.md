# markov_chain_memory_fidelity_class

**Name (zh)**: 马尔可夫链状态记忆保真类
**Name (en)**: Markov Chain State Memory & Fidelity
**Pre-registered exponent band**: First-order Markov property held (LRT p > 0.10 against second-order alternative); forgetting rate ε ∈ [0.02, 0.10] / hour for generator on/off; stationary distribution matches realised mean within 10%. Rationale: Markov 1906; Kolmogorov forward equation; PJM-CAISO operational reports.
**Verified status**: false (target: v0.4). B3 consensus = REJECT, note "statistical descriptor, not mechanism." **Expected REJECT verdict** — see same pattern as `extreme_value_tail_class` and `tail_copula_contagion`.

## Why this class needs an empirical anchor

Like EVT and copulas, "first-order Markov" is a *statistical model class*, not a *causal mechanism*. The B3 REJECT is theoretically grounded. Verification matters as a *consistency check* on the descriptor-vs-mechanism boundary: if first-order Markov fits all three KB members (DNA methylation, X-inactivation mosaicism, generator on/off) with comparable τ, then REJECT is correctly applied (universal *statistics* without universal *mechanism*).

KB linkage: 3 members — hemimethylated DNA methylation inheritance (molecular bio), stochastic X-inactivation mosaicism (dev bio), generator on/off Markov modelling (electrical eng).

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | PJM Interconnection hourly generation fuel-mix 2018–2025 + EIA-860 plant-level on/off status | https://www.pjm.com/markets-and-operations/data-dictionary + https://www.eia.gov/electricity/data/eia860/ | Public | ~60k hours × ~500 units | Original pre-registered target; clean binary state series | Maintenance vs economic shutdowns not distinguished in raw data |
| 2 [fallback] | CAISO OASIS market data 2018–2025 (similar structure, west-coast generators) | http://oasis.caiso.com/ | Public | ~60k hours × ~300 units | Replication on independent ISO | Same caveat |
| 3 [stretch] | Roadmap Epigenomics methylation arrays — repeated time points on same lineage (lineage-tracking data such as Shipony et al. 2014 Nature 513:115) | https://egg2.wustl.edu/roadmap/web_portal/ | Free | ~100 samples | Tests molecular-bio variant of the class | Few repeat-time-point datasets exist; sparse temporal sampling |

## Validation procedure (concrete)

```bash
mkdir -p data/markov_chain_memory_fidelity_class

# 1. PJM hourly generation
curl -L "https://api.pjm.com/api/v1/gen_by_fuel?..." \
  -o data/markov_chain_memory_fidelity_class/pjm_hourly.csv

# 2. Likelihood-ratio test first-order vs higher-order Markov
python -m v4.cli validate markov_chain_memory_fidelity_class \
  --data data/markov_chain_memory_fidelity_class/pjm_hourly.csv \
  --method markov-order-lrt --max-order 3 \
  --tau-band 12,50 --null-controls independent-bernoulli,deterministic-cycle

# 3. Expected verdicts
#   PASS:  LRT p > 0.10 (first-order not rejected), forgetting rate ε in band,
#          stationary distribution prediction matches observed within 10%
#   FAIL:  higher-order Markov preferred OR independent-Bernoulli preferred
#   INCONCLUSIVE: order ambiguous between 1 and 2
```

## Estimated workload

- Data acquisition: 3 h (PJM API needs registration but is fast)
- Pipeline run: 3 h (LRT + stationary distribution + bootstrap is light)
- Verdict + writeup: 2 h
- **Total: ~8 h / 1 day**

## Risks specific to this class

1. **Expected REJECT**: pre-register that even a PASS does not promote this from descriptor to mechanism — it confirms B3's framing.
2. **Maintenance shutdowns** are not Markov (scheduled, deterministic). Filter or model separately.
3. Higher-order Markov tests have low power on short time series — need ≥ 10⁴ obs per unit.

## Priority

⭐⭐ (rationale: low scientific yield — B3 REJECT likely confirmed and the class is statistical not mechanistic; quick to run, so worth doing for taxonomy completeness)

## Dependencies

- `pandas`, `scipy.stats`, `hmmlearn`
- PJM API key (free)
- Storage: < 1 GB
