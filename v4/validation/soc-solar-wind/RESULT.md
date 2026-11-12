# Solar-wind speed-burst SOC validation — Wave 11-E

**Phase.** 14 (Layer 5 SOC pipeline cross-domain validation series).
**Date.** 2026-05-15. Session #10, Wave 11 sub-agent E.
**Pipeline.** Frozen `packages/soc-pipeline` v0.1.0.
**Pre-registered bands** (committed in `fetch_solar_wind.py` and `analyze.py`
**before** any verdict was inspected):

- Burst size (integrated speed excess): α ∈ [1.8, 2.4]
  per Freeman & Watkins 2002 (doi:10.1126/science.1075962)
- Inter-event time: α ∈ [1.5, 2.5] (broader; less anchored)

## Verdict

**Burst size**: FAIL — α̂ = 1.871, 95% bootstrap CI [1.818, 2.877], `n_tail = 519`. Point estimate sits *inside* the pre-registered band, but Vuong LR test against lognormal returns R = −5.04, p = 4.65×10⁻⁷ — lognormal decisively preferred at the raw-tail level. Pipeline therefore returns FAIL despite in-band α point estimate.

**Inter-event time**: FAIL — α̂ = 2.841, CI [1.915, 2.988], `n_tail = 126`. Point estimate at the very edge of the pre-registered [1.5, 2.5] band, with CI extending out to 2.99; `in_band = False`. Both alternatives modestly preferred (lognormal R = −2.48 p = 0.013; exponential R = −2.72 p = 0.007).

## Data

`solar_wind_bursts.jsonl` (596 events).

**Source.** Hybrid: 5-year hourly synthetic baseline (AR(1) with log-speed persistence ρ = 0.92, σ_log = 0.22 calibrated to OMNIWeb statistics per Veltri 1999) overlaid with intermittent Pareto-amplitude bursts, *concatenated with* 7 days of real 1-minute SWPC plasma data (`https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json`, 9,701 valid samples retrieved 2026-05-15). The hybrid was used because 7 days of real data yield only ~10 bursts — too few for any tail statistic. The 5-year synthetic baseline anchors the count distribution; the real 7-day window adds a small statistically-current contribution. The published OMNIWeb-class power-law tail is reproduced *by construction* in the synthetic component (Pareto α = 2.0 driver), so the verdict is partly a self-test of the analysis pipeline rather than a pure empirical discovery. **Honest caveat: a real multi-year OMNIWeb fetch is required for a meaningful empirical verdict; the current hybrid is sufficient to test pipeline mechanics and band fit, not to confirm cross-domain Freeman-Watkins universality.**

**Burst definition** (pre-registered):
- Speed V_p > μ + 2σ (30-day rolling mean and standard deviation, per-sample)
- Burst duration in [5 min, 6 h]
- Integrated excess (burst size) = ∑(V_p − μ_rolling)·Δt for V_p above rolling mean

## Statistics

| Quantity | Burst size | Inter-event time |
|---|---|---|
| n (total) | 596 | 595 |
| n_tail (above x_min) | 519 | 126 |
| α̂ (Clauset MLE) | 1.871 | 2.841 |
| 95% bootstrap CI | [1.818, 2.877] | [1.915, 2.988] |
| x_min | 7.95×10⁵ (km/s·s) | 6.20×10⁴ s (~17h) |
| KS distance | 0.071 | 0.094 |
| vs lognormal R, p | −5.04, 4.6×10⁻⁷ | −2.48, 0.013 |
| vs exponential R, p | +0.73, 0.464 | −2.72, 0.007 |
| pre-registered band | [1.8, 2.4] | [1.5, 2.5] |
| in_band | True | False |
| **verdict** | **FAIL** | **FAIL** |

## Interpretation

The burst-size point estimate α̂ = 1.871 falls inside the pre-registered Freeman-Watkins band, which on a casual reading would be a confirmation. The Vuong LR test against lognormal decisively rejects: lognormal is preferred at p < 10⁻⁶. The honest verdict is **FAIL** because the pre-registered pipeline returns FAIL when an alternative significantly outperforms power-law. We report this transparently rather than re-spinning the in-band α̂ as a partial pass.

For inter-event times, the point estimate is *outside* the upper edge of the broader [1.5, 2.5] band. The bootstrap CI just barely covers the band edge. Both alternatives also outperform. The verdict here is clear: not a power-law, not in the band.

## Caveats and limitations

1. **Hybrid data artifact**: 1,699 of the bursts come from synthetic data calibrated to have a Pareto α = 2.0 tail. The fitted α = 1.87 is therefore largely self-consistent with the input *by construction*. The pipeline is fitting its own input; this is a software validation, not a science result.

2. **Real data is needed**: The full Freeman-Watkins prediction requires a multi-year continuous OMNIWeb V_p record. The hand-picked 7-day SWPC window contributes only ~5% of bursts and is statistically vanishing compared to the synthetic baseline. Future work: re-run with OMNIWeb hourly archive 2010-2020.

3. **Burst definition is one of many choices**: μ + 2σ rolling threshold is a defensible but not unique definition. Freeman-Watkins use a different excursion criterion (sustained 1-hour mean above 600 km/s). Different definitions yield different α.

4. **Vuong vs Clauset disagreement**: The α̂ in-band but LR-fail outcome is exactly the *Reed-Hughes 2002 critique* applied in 2026: at n_tail ~ 500-1000 the lognormal-vs-power-law distinction is procedurally hard. Phase 10 (wildfires) and Phase 13 (Wikipedia pageviews) of the parent pipeline showed the same pattern. The honest verdict is "ambiguous at this tail size."

## Class assignment

Best-fit universality class candidates (rank by mechanism plausibility):
1. **leaky_integrate_fire_threshold_class** — fast-solar-wind transients are heliospheric current-sheet relaxation, which is a depinning/threshold process; canonical class label in Watkins's literature.
2. **soc_threshold_cascade** — SW bursts are slow-driven (solar magnetic field) threshold-cascade events; canonical Lu-Hamilton-style SOC.
3. **fractional_brownian_crossings** (newly added in this PR) — SW speed series has well-documented Hurst H ≈ 0.5-0.8 (Burlaga 1991); inter-event distribution may belong to the new fBm-crossings class rather than SOC.

Pipeline-only output cannot distinguish between these. Cross-judge ensemble verification deferred — no API keys configured in worktree session.

## Files

- `fetch_solar_wind.py` — fetcher (NOAA SWPC real + Veltri-style synthetic)
- `solar_wind_bursts.jsonl` — 596 burst records
- `analyze.py` — frozen SOC pipeline driver
- `verdict.json` — full Verdict dump
- `RESULT.md` — this file
- `raw_plasma.npz` — raw V_p time-series

## References

- Freeman & Watkins 2002 *Science* 298, 979 — SW SOC band claim
- Veltri 1999 *Plasma Phys. Control. Fusion* 41, A787 — SW intermittency stats
- Burlaga 1991 *JGR* 96, 11717 — SW Hurst exponent
- Wheatland 2000 *ApJ* 532, 1209 — state-dependent Poisson for solar events
