# delay_differential_debt

**Name (zh)**: 延迟反馈与债务累积类
**Name (en)**: Delay Differential Equations and Accumulated Debt
**Pre-registered exponent band**: Extinction-debt time constant τ ∈ [15, 50] years; committed-debt fraction C/S* ∈ [0.10, 0.30]; Hopf-bifurcation-style damped oscillations detectable in autocorrelation. Rationale: Tilman 1994 Nature 371:65 (original extinction-debt formulation), Diamond 1972, Hanski–Ovaskainen 2002 metapopulation theory.
**Verified status**: false (target: v0.4). B3 consensus = REJECT, note "delay-diff is a math framework not a mechanism." **Expected REJECT verdict is itself paper-worthy** — see C4 paper §4.3 on normal-form vs mechanism confusion.

## Why this class needs an empirical anchor

This is the most interesting "negative result" candidate in the unverified set. B3 already flagged delay-differential equations as a mathematical *framework*, not a mechanism — exactly the trap C4 paper warns about. Verification has two possible high-value outcomes:

1. **PASS** with universal τ band across extinction debt + ENSO + permafrost methane → genuine mechanism, B3 was wrong, paper-worthy *positive* result.
2. **REJECT** with τ scattered widely → confirms C4 paper's "normal-form ≠ universality class" thesis with empirical teeth.

Either result earns a section.

KB linkage: 3 members — extinction debt (conservation biology), ENSO delayed oscillator (oceanography), permafrost methane delayed release (environmental science).

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | PREDICTS database (Hudson et al. 2017 Ecol Evol 7:145) — habitat-change + biodiversity time series | https://www.predicts.org.uk/ | CC-BY 4.0 | ~3.2M biodiversity records × 26k sites | Direct extinction-debt test on global habitat-loss sites | Time series often short (< 10 y); τ ≥ 30 y harder to identify |
| 2 [fallback] | NOAA ENSO indices (Niño 3.4 SST anomaly + warm-water-volume index) 1980–2025 | https://www.cpc.ncep.noaa.gov/data/indices/ | Public | ~17k daily obs | Test ENSO delayed-oscillator τ ≈ 18 months (Suarez–Schopf 1988) | Single time series — no cross-system replication on its own |
| 3 [stretch] | NSF Arctic Data Center permafrost methane flux monitoring (Permafrost Carbon Network 2010–2024) | https://arcticdata.io/ | CC-0 | ~120 stations × 5–15 years | Newest member of the class; thaw-emission lag observable | Heterogeneous methods; ground-truth lag hard to define |

## Validation procedure (concrete)

```bash
mkdir -p data/delay_differential_debt

# 1. PREDICTS subset for European birds in Natura 2000 fragments
# (filter to sites with > 20-year repeat sampling)
python -c "
import requests
# PREDICTS provides API; alternatively bulk-download from data.nhm.ac.uk
"

# 2. Fit delay-differential model x'(t) = f(x(t-tau)) - mu*x(t)
python -m v4.cli validate delay_differential_debt \
  --data data/delay_differential_debt/predicts_natura2000.csv \
  --method dde-fit --lag-search 5,60 \
  --alpha-band 15,50 --null-controls exponential-decay,immediate-equilibration

# 3. Expected verdicts
#   PASS:   tau ∈ [15, 50] consistent across 3 data sources (PREDICTS, ENSO, permafrost),
#           damped-oscillation autocorrelation signature present
#   FAIL:   tau scatters > factor of 3 across sources → confirms B3 REJECT
#   INCONCLUSIVE: only PREDICTS yields a fit; ENSO/permafrost too short/noisy
```

## Estimated workload

- Data acquisition: 6 h (PREDICTS filtering is non-trivial; ENSO straightforward; permafrost requires NSF login)
- Pipeline run: 6 h (DDE fitting is slow; lag-search over 5–60 yr grid)
- Verdict + writeup (including negative-result narrative if REJECT confirmed): 4 h
- **Total: ~16 h / 2 days**

## Risks specific to this class

1. **B3-predicted REJECT may be the result** — this is *desirable* (negative result is informative) but must be pre-registered, not reverse-engineered after seeing the data.
2. **Identifiability**: DDE inference is well-known to suffer from local minima in τ; use multi-start + profile likelihood.
3. **Cross-system τ comparison** requires careful unit handling (PREDICTS in years, ENSO in months, permafrost in days). Convert to dimensionless τ/T_system where T_system is each domain's natural timescale.

## Priority

⭐⭐⭐⭐⭐ (rationale: most likely to yield a *negative-result-as-positive-contribution* section in the v0.4 paper, directly validating the C4 thesis)

## Dependencies

- `scipy.integrate` (ddeint package or jitcdde for DDE solving)
- `lmfit` for non-linear DDE parameter fitting
- No paid API; NSF Arctic Data Center optional registration
- Storage: ~2 GB (PREDICTS subset)
