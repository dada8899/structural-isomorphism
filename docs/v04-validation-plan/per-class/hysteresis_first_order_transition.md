# hysteresis_first_order_transition

**Name (zh)**: 双稳态陷阱与一阶相变迟滞类
**Name (en)**: Bistable Trap & First-Order Hysteresis
**Pre-registered exponent band**: Hysteresis-loop area / mean state-variable ∈ [0.05, 0.30]; saddle-node-bifurcation slope sign change confirmed; recovery probability after parameter restoration < 0.30. Rationale: Landau 1937 / Scheffer 2001 Nature 413:591 / Lutz 2007 (low-fertility trap).
**Verified status**: false (target: v0.4). B3 consensus = MERGE — likely overlaps with `hysteresis_preisach` (already verified) and `scheffer_fold_bifurcation` (already verified).

## Why this class needs an empirical anchor

This class is in danger of being absorbed: `hysteresis_preisach` covers magnetic-style stacked hysteresis loops and `scheffer_fold_bifurcation` covers the saddle-node tipping. The unique contribution of this class is the *demographic / corporate-finance* member set (low-fertility trap, managerial entrenchment), which neither parent class covers. Validation should test whether OECD fertility data shows the same hysteresis signature as Scheffer-style ecological tipping (in which case MERGE) or whether the demographic dynamics produce a distinctly different loop shape (in which case KEEP).

KB linkage: 3 members — low-fertility-trap hypothesis (demography), internal lake phosphorus loading (env science, overlaps with Scheffer), managerial entrenchment (corporate finance).

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | OECD Family Database + World Bank WDI fertility/GDP panel 1970–2024 (36 OECD countries) | https://www.oecd.org/els/family/database.htm + https://databank.worldbank.org/source/world-development-indicators | OECD: CC-BY 4.0 / WB: CC-BY 4.0 | 36 × 55 = 1980 country-years | Original pre-registered target; family-policy spend + TFR jointly observable | OECD policy-spend reporting inconsistent pre-1990 |
| 2 [fallback] | Lutz–Skirbekk–Testa 2006 low-fertility-trap replication data (Vienna Institute of Demography) | https://www.oeaw.ac.at/vid/data/demographic-data-sheets/ | Free | ~40 European subnational units | Direct replication of the canonical low-fertility-trap study | Smaller N |
| 3 [stretch] | Compustat managerial entrenchment dataset (Bebchuk–Cohen–Ferrell 2009 RFS replication, E-index) | https://wrds-www.wharton.upenn.edu/ | Institutional licence | ~3000 firms × 20 y | Tests corporate-finance variant; cleanest hysteresis observed in CEO-turnover events | WRDS licence required |

## Validation procedure (concrete)

```bash
mkdir -p data/hysteresis_first_order_transition

# 1. OECD + WDI merge
curl -L "https://stats.oecd.org/SDMX-JSON/data/FAMILY/.PFL.../all?contentType=csv" \
  -o data/hysteresis_first_order_transition/oecd_family.csv

# 2. Fit hysteresis loop in (family-spend, TFR) plane per country
python -m v4.cli validate hysteresis_first_order_transition \
  --data data/hysteresis_first_order_transition/oecd_family_tfr.csv \
  --method loop-area --parameter family_spend --state tfr \
  --area-band 0.05,0.30 --null-controls single-valued,linear-tracking

# 3. Cross-check: same pipeline on Scheffer lake-phosphorus data
python scripts/cross_check_scheffer_overlap.py

# 4. Expected verdicts
#   PASS:  loop area in band for fertility AND fertility-loop topologically distinct
#          from Scheffer-lake-loop signature
#   FAIL:  no measurable loop area OR identical signature to Scheffer (MERGE confirmed)
#   INCONCLUSIVE: country-by-country heterogeneity dominates
```

## Estimated workload

- Data acquisition: 3 h (OECD + WDI APIs are clean)
- Pipeline run: 4 h (loop-area estimation + per-country bootstrap)
- Verdict + writeup including MERGE decision narrative: 4 h
- **Total: ~11 h / 1.5 days**

## Risks specific to this class

1. **MERGE collision with already-verified Scheffer class** is the central scientific question. Pre-register the discriminating signature (e.g., loop concavity, time-asymmetry).
2. Family-spend definition varies (cash transfers vs in-kind vs tax credits). Standardise to % of GDP across all transfer types.
3. Causality vs correlation: TFR-spend relationship is bidirectional. Use instrumental variables (e.g., political-control change as instrument for spend) if depth allows.

## Priority

⭐⭐⭐ (rationale: MERGE decision is high-value but the empirical loop in OECD data may be visually obvious without rigorous validation needed)

## Dependencies

- `pandas`, `oecd-data` Python wrapper, `wbdata`
- WRDS optional (stretch)
- Storage: < 100 MB
