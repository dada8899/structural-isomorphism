# reflexive_fixed_point_class

**Name (zh)**: 反身性不动点与测量反馈类
**Name (en)**: Reflexive Fixed Point & Measurement Feedback
**Pre-registered exponent band**: Reflexivity strength c ∈ [0.6, 1.6] in `|f'(E)| = 1 + c·w`; KPI-introduction drop in quality/quantity ratio Δ ∈ [0.10, 0.30]. Rationale: Muth 1961 rational-expectations theorem, Goodhart 1975 (originally an internal Bank of England note, later in Goodhart 1981), Soros 1987 *Alchemy of Finance*.
**Verified status**: false (target: v0.4). B3 consensus = KEEP (one of only 5 KEEPs in the cross-judge — high prior).

## Why this class needs an empirical anchor

KEEP from B3 means the cross-judge already considers this a real mechanism. The verification job is to demonstrate the *reflexive bifurcation* signature empirically — that measurement of a metric causes a discontinuous jump in the metric's dynamics. KPI introduction in academic settings is the cleanest natural experiment because the policy switch date is well documented.

KB linkage: 3 members — self-fulfilling stereotypes (psychology), Goodhart's law in performance metrics (public admin), inflation expectation de-anchoring (macro).

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Leiden Ranking + Web of Science faculty publication panel (US R1 universities 2005–2024) | https://www.leidenranking.com/ + WoS API | CC-BY 4.0 (Leiden) / institutional WoS | ~180 universities × 20 y | KPI-introduction dates documented; quality/quantity ratio directly computable | WoS access requires institutional licence |
| 2 [fallback] | Federal Reserve survey of inflation expectations + realised inflation 1980–2025 (Cleveland Fed + Michigan Survey) | https://www.clevelandfed.org/indicators-and-data/inflation-expectations | Public | ~540 monthly obs | Direct test of expectation de-anchoring under Volcker / post-2008 / post-2021 regimes | Regime shifts confound smooth reflexivity inference |
| 3 [stretch] | UK REF (Research Excellence Framework) institutional submissions 2008/2014/2021 | https://results2021.ref.ac.uk/ | Open data | 3 census waves × 154 institutions | Sharp policy switch — cleanest natural experiment, but only 3 time points | Coarse temporal resolution |

## Validation procedure (concrete)

```bash
mkdir -p data/reflexive_fixed_point_class

# 1. Leiden Ranking bulk download
curl -L "https://www.leidenranking.com/downloads/ranking2024-bulk.csv" \
  -o data/reflexive_fixed_point_class/leiden_ranking.csv

# 2. Difference-in-differences around KPI introduction
python -m v4.cli validate reflexive_fixed_point_class \
  --data data/reflexive_fixed_point_class/leiden_ranking.csv \
  --method did --treatment kpi_introduced --outcome quality_quantity_ratio \
  --slope-band 0.6,1.6 --null-controls parallel-trends,no-effect

# 3. Expected verdicts
#   PASS:  DiD coefficient on KPI-introduction × time > 0 with reflexivity c in band,
#          parallel-trends pre-period assumption not rejected
#   FAIL:  no significant ratio drop after KPI introduction OR pre-trends violated
#   INCONCLUSIVE: directional effect present but c outside [0.6, 1.6]
```

## Estimated workload

- Data acquisition: 4 h (Leiden is free; WoS access depends on institution)
- Pipeline run: 3 h (DiD + bootstrap)
- Verdict + writeup: 3 h
- **Total: ~10 h / 1.5 days**

## Risks specific to this class

1. **WoS access**: if no institutional licence, fall back to OpenAlex (free, broader coverage but messier). Pre-decide.
2. **KPI-introduction date coding** requires care — many universities phased KPIs over years rather than at one switch. Use intent-to-treat coding.
3. **Reflexivity in macro inflation** is contaminated by regime shifts (Volcker, 2008, 2021); restrict to a "stable expectations" window if used as fallback.

## Priority

⭐⭐⭐⭐ (rationale: B3 KEEP gives high prior; clean natural experiment; cross-domain — academic KPI + macro expectations — strengthens taxonomy)

## Dependencies

- `pandas`, `linearmodels` (DiD), `statsmodels`
- WoS or OpenAlex API
- Storage: ~3 GB (Leiden bulk + WoS slice)
