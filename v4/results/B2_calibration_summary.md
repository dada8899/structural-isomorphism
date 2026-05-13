# B2 — Layer 4 prediction calibration summary

**Run date**: 2026-05-13  

**Total classes**: 21  

**Total predictions**: 24  


## Verification status

| Status | Count | % |
|---|---|---|
| ✅ Confirmed (observed value in predicted band) | 0 | 0% |
| 🟡 Partial (literature band overlap only) | 0 | 0% |
| 🔴 Deviating | 0 | 0% |
| ⚪ Pending (no verified observation yet) | 24 | 100% |

## Verified-observation bootstrap CI refresh

| Quantity | Value | Bootstrap 95% CI | n_boot succeeded |
|---|---|---|---|
| earthquake_alpha | 1.803 | [1.753, 1.838] | 100 |
| stockmarket_alpha | 2.993 | [2.738, 3.000] | 100 |
| defi_aave_alpha | — | failed: too few sizes: 0 | — |
| defi_compound_alpha | — | failed: too few sizes: 0 | — |
| defi_maker_alpha | — | failed: too few sizes: 0 | — |

## Methodology

1. **Band extraction**: regex pulls numerical ranges `[a, b]` / `a-b` / `a 到 b` from each prediction text.
2. **Quantity inference**: looks at ~30 chars before each range for known physical-quantity keywords (α, τ, β, p_omori, b-value, ratio, time, fraction).
3. **Observation matching**: for each verified phase 1-5 system, the prediction text is scanned for domain keywords (earthquake / S&P / DeFi / neural). If matched, the predicted band is compared to observed central value.
4. **Bootstrap CI refresh**: where raw data is available (earthquake, S&P 500, 3 DeFi protocols), Clauset α is re-fit on 100 bootstrap resamples to give updated 95% CI.
5. **Score**:
   - `confirmed`: observed value lies inside predicted band
   - `partial`: predicted band overlaps the canonical literature band even if not the exact observation
   - `deviating`: predicted band misses both
   - `pending`: no verified phase has tested this class+target yet

## Limitations

- Regex band extraction misses range expressions in other phrasings (e.g. 'approximately X with σ Y'). 24/24 predictions had at least one extractable band; not all are physically meaningful quantities.
- Quantity inference is heuristic; some bands attributed to wrong quantity if context keyword is ambiguous.
- For non-α/τ quantities (timings, ratios), no verified observation table exists yet — those default to `pending` until matching phase is run.
- Only SOC threshold cascade class has verified observations; 22 other classes are all `pending` until Phase 6+/A2 phases run.
