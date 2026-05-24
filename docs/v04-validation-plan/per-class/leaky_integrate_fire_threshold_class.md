# leaky_integrate_fire_threshold_class

**Name (zh)**: 泄漏积分-阈值释放类
**Name (en)**: Leaky Integrate-and-Fire Threshold Release
**Pre-registered exponent band**: Leakage time constant τ = 1/k_a in subjective domain ∈ [30, 150] days (hedonic treadmill); in neuronal domain ∈ [10, 30] ms; in token-bucket domain depends on rate-limit policy. **Cross-domain dimensionless ratio τ_relax / T_event ∈ [3, 30] expected to be universal**. Rationale: Lapicque 1907 (neuronal τ), Frederick–Loewenstein 1999 (hedonic τ ≈ 60–120 d), Turner 1986 (token bucket).
**Verified status**: false (target: v0.4). B3 consensus = SPLIT — splits suggested between neural/economic/CS variants.

## Why this class needs an empirical anchor

The SPLIT consensus says the three members (Piezo1 mechanotransduction, hedonic treadmill, token bucket) may be analogically similar but mechanistically separate. Validation tests whether the *dimensionless* universality survives when you strip out domain-specific units. If τ_relax / T_event clusters in a narrow band across all 3, the SPLIT is overruled. If it scatters, the SPLIT stands.

KB linkage: 3 members — Piezo1 mechanotransduction gating, hedonic-treadmill reference-point adaptation, token-bucket rate limiting.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | SOEP German Socio-Economic Panel (life-satisfaction monthly subsample, 1984–2024) | https://www.diw.de/en/diw_02.c.222829.en/access_and_ordering.html | Free academic, registration | ~15k subjects × 30+ years | Original pre-registered target for hedonic treadmill; long enough for τ estimation | Registration delay (1–2 weeks); subjective scale issues |
| 2 [fallback] | Allen Institute Mouse Connectivity neural-spike recordings (Visual Coding Neuropixels) | https://portal.brain-map.org/explore/circuits/visual-coding-neuropixels | CC-BY 4.0 | ~100 mice × 30k neurons | Cleanest LIF-class data; well-characterised τ | Pure neural domain — doesn't help cross-domain SPLIT test alone |
| 3 [stretch] | CAIDA Anonymised Internet Traces (token-bucket-conformant flows in real backbone traffic) | https://www.caida.org/catalog/datasets/passive_dataset/ | Free academic, registration | ~PB of packet traces | Tests CS-side LIF dynamics in production rate-limiters | Need to back-infer policy; not directly observed |

## Validation procedure (concrete)

```bash
mkdir -p data/leaky_integrate_fire_threshold_class

# 1. SOEP life-satisfaction panel
# (after registration approval; bulk download via Stata format)
python -c "
import pandas as pd
df = pd.read_stata('data/leaky_integrate_fire_threshold_class/soep_satisfaction.dta')
# Identify income-shock events; track satisfaction response trajectory
"

# 2. Fit leaky integrator dS/dt = F(t) - k_a*S to satisfaction trajectory post-shock
python -m v4.cli validate leaky_integrate_fire_threshold_class \
  --data data/leaky_integrate_fire_threshold_class/soep_satisfaction.csv \
  --method leaky-integrator-fit --event-locked \
  --tau-band 30,150 --null-controls instant-return,no-return,linear-trend

# 3. Cross-domain check: also fit on Allen Institute spike trains, compute dimensionless ratio
python scripts/cross_domain_lif_ratio.py

# 4. Expected verdicts
#   PASS:  tau in SOEP ∈ [30, 150]d AND dimensionless ratio τ/T_event matches Allen Institute neural values
#   FAIL:  no leaky-integrator signature in SOEP OR cross-domain ratios differ by > 1 order of magnitude
#   INCONCLUSIVE: SOEP fit OK but Allen comparison ambiguous
```

## Estimated workload

- Data acquisition: 5 h (SOEP registration is the slowest step — apply early; Allen is API-driven and fast)
- Pipeline run: 5 h (event-locked regression + non-linear fit; Allen subset filtering)
- Verdict + writeup: 3 h
- **Total: ~13 h / 2 days** (plus calendar time for SOEP registration)

## Risks specific to this class

1. **SOEP registration is the gating step** — apply ≥ 2 weeks before scheduling sub-agent run.
2. **Subjective scale**: life-satisfaction is bounded [0,10]; reflexive ceiling effects bias τ estimates downward. Use Tobit regression.
3. **Cross-domain dimensionless comparison** depends on choosing T_event correctly (income shock = months? years?). Pre-register the choice.

## Priority

⭐⭐⭐ (rationale: clean math, interesting cross-domain test, but SOEP friction lowers priority for fast sub-agent dispatch)

## Dependencies

- `pandas`, `scipy.optimize`, `statsmodels` (Tobit), `allensdk` (Allen Brain pipeline)
- SOEP registration required
- Storage: ~10 GB if pulling full Allen visual-coding subset
