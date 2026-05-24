# VERDICT - X3 Climate Tipping Points (Amazon NDVI + AMOC)
## Taxonomy class 3 (scheffer_fold_bifurcation)

**Date.** 2026-05-24
**Validator.** structural-isomorphism v4, X3 climate-tipping track

---

## Headline

| System | Real / Synth | n_months | AR(1) tau | var tau | classical CSD | Verdict | Iso-dist to Scheffer-lake |
|---|---|---|---|---|---|---|---|
| amoc_rapid_26n | REAL | 240 | -0.231 | -0.320 | no | INCONCLUSIVE | 0.756 |
| amazon_ndvi_central_amazonas | REAL | 299 | -0.280 | -0.619 | no | INCONCLUSIVE | 1.023 |
| amazon_ndvi_para_central | SYNTHETIC | 291 | -0.060 | +0.161 | no | SYNTHETIC | 0.352 |
| amazon_ndvi_rondonia_arc | SYNTHETIC | 291 | -0.129 | +0.352 | no | SYNTHETIC | 0.429 |
| amazon_ndvi_western_acre | SYNTHETIC | 291 | +0.091 | -0.118 | no | SYNTHETIC | 0.401 |
| amazon_ndvi_xingu_park | SYNTHETIC | 291 | +0.183 | +0.064 | no | SYNTHETIC | 0.198 |

## Data sources

- **AMOC**: RAPID 26 N array, https://rapid.ac.uk/sites/default/files/rapid_data/moc_transports.nc -- variable `moc_mar_hc10` (overturning transport, Sv), 2004-04-01 onwards, 12-hourly.
- **Amazon NDVI**: NASA ORNL DAAC MODIS MOD13Q1 250 m 16-day NDVI, REST API `https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset`, 2000-02-18 onwards. Sites: central_amazonas (-3.0, -60.0), rondonia_arc (-10.0, -62.5), xingu_park (-12.0, -53.0), western_acre (-9.5, -68.0), para_central (-5.5, -55.5).
- **Reference for isomorphism distance**: v4/validation/scheffer-lake VERDICT-2026-05-13 (Fox River Green Bay DO, USGS 040851385) AR(1) tau=+0.284, var tau=+0.234.

## Method

1. Monthly aggregation; deseasonalise via 12-month climatology removal.
2. Rolling EWS (window = 48 months): AR(1), variance, skewness.
3. Kendall tau monotonic-trend test over the full deseasonalised anomaly series. Classical CSD = positive significant AR(1) AND positive significant variance.
4. Power-law side-test (Clauset 2009 MLE) on |anomaly|, xmin chosen by KS sweep. Not the primary verdict for fold-bifurcation class but a complementary tail diagnostic.
5. Structural isomorphism distance = L2((tau_AR1 - 0.284), (tau_var - 0.234)) against scheffer-lake reference.

## Per-system findings

### amoc_rapid_26n

- Source: `raw/amoc_timeseries.jsonl` (n_raw=14579, n_months=240, 2004-04 -> 2024-03)
- Synthetic: **False**
- AR(1) trend: tau = -0.2315, p = 1.87e-06, n = 192
- Variance trend: tau = -0.3196, p = 4.63e-11
- Skewness trend: tau = +0.3114, p = 1.42e-10
- Classical CSD signature: **False**
- Power-law tail of |anomaly|: alpha = 3.138, xmin = 2.5794, KS = 0.0794, n_tail = 74/240
- Iso-distance to scheffer-lake: **0.756** (lower = closer match)
- Verdict: **INCONCLUSIVE**

### amazon_ndvi_central_amazonas

- Source: `raw/amazon_ndvi_central_amazonas.jsonl` (n_raw=572, n_months=299, 2000-02 -> 2024-12)
- Synthetic: **False**
- AR(1) trend: tau = -0.2797, p = 4.06e-11, n = 251
- Variance trend: tau = -0.6193, p = 2.28e-48
- Skewness trend: tau = +0.3177, p = 6.53e-14
- Classical CSD signature: **False**
- Power-law tail of |anomaly|: alpha = 4.861, xmin = 0.1110, KS = 0.0860, n_tail = 39/299
- Iso-distance to scheffer-lake: **1.023** (lower = closer match)
- Verdict: **INCONCLUSIVE**

### amazon_ndvi_para_central

- Source: `raw/amazon_ndvi_para_central.jsonl` (n_raw=552, n_months=291, 2000-02 -> 2024-04)
- Synthetic: **True**
- AR(1) trend: tau = -0.0603, p = +0.1615, n = 243
- Variance trend: tau = +0.1614, p = 1.79e-04
- Skewness trend: tau = +0.2063, p = 1.68e-06
- Classical CSD signature: **False**
- Power-law tail of |anomaly|: alpha = 3.531, xmin = 0.0510, KS = 0.0574, n_tail = 75/291
- Iso-distance to scheffer-lake: **0.352** (lower = closer match)
- Verdict: **SYNTHETIC**

### amazon_ndvi_rondonia_arc

- Source: `raw/amazon_ndvi_rondonia_arc.jsonl` (n_raw=552, n_months=291, 2000-02 -> 2024-04)
- Synthetic: **True**
- AR(1) trend: tau = -0.1288, p = +0.0028, n = 243
- Variance trend: tau = +0.3523, p = 2.86e-16
- Skewness trend: tau = -0.4319, p = 1.16e-23
- Classical CSD signature: **False**
- Power-law tail of |anomaly|: alpha = 3.056, xmin = 0.0349, KS = 0.0786, n_tail = 113/291
- Iso-distance to scheffer-lake: **0.429** (lower = closer match)
- Verdict: **SYNTHETIC**

### amazon_ndvi_western_acre

- Source: `raw/amazon_ndvi_western_acre.jsonl` (n_raw=552, n_months=291, 2000-02 -> 2024-04)
- Synthetic: **True**
- AR(1) trend: tau = +0.0912, p = +0.0341, n = 243
- Variance trend: tau = -0.1180, p = +0.0061
- Skewness trend: tau = -0.0878, p = +0.0416
- Classical CSD signature: **False**
- Power-law tail of |anomaly|: alpha = 5.422, xmin = 0.0430, KS = 0.0630, n_tail = 45/291
- Iso-distance to scheffer-lake: **0.401** (lower = closer match)
- Verdict: **SYNTHETIC**

### amazon_ndvi_xingu_park

- Source: `raw/amazon_ndvi_xingu_park.jsonl` (n_raw=552, n_months=291, 2000-02 -> 2024-04)
- Synthetic: **True**
- AR(1) trend: tau = +0.1827, p = 2.21e-05, n = 243
- Variance trend: tau = +0.0643, p = +0.1354
- Skewness trend: tau = -0.1292, p = +0.0027
- Classical CSD signature: **False**
- Power-law tail of |anomaly|: alpha = 5.049, xmin = 0.0472, KS = 0.0698, n_tail = 37/291
- Iso-distance to scheffer-lake: **0.198** (lower = closer match)
- Verdict: **SYNTHETIC**

## Limitations / honesty

- AMOC RAPID 26 N is 20 years -- shorter than the multi-decadal forcing timescale (Boers 2021 PNAS used ~150 yr SST reconstructions). Our 4-yr EWS window therefore captures intra-decadal variability more than secular destabilisation. A pre-registered finding of *no* tipping signature in the 20-yr direct observation is consistent with Boers' SST-proxy result that the secular signal only emerges over centuries.
- Amazon NDVI: single-pixel MODIS time series have cloud-contamination noise; we did NOT apply QA-flag filtering in this pass (the REST API returns NDVI even when MOD13Q1_QC flags low-quality). A Wave 3 follow-up should re-fetch with quality masks.
- Synthetic fallbacks are flagged explicitly in the table above and in `raw/fetch_log.json`. No system claims REAL where the fetch did not succeed.
