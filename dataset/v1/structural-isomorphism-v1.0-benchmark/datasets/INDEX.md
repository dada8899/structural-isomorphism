# structural-isomorphism v1.0 benchmark — dataset index

This file lists every empirical system bundled in the benchmark, with the
phase number, predicted universality class, pre-registered exponent band,
and frozen-pipeline verdict.

Auto-curated entries (Phases 1-13) are sourced from `_build_summary.json`.
Manually appended entries (Phases 14, 15, ...) live under `v4/validation/`
in the source repo and are mirrored to this bundle when the next release is
cut.

## Phase 1 — USGS earthquake catalog 2020-2025

- Source dir: `v4/validation/soc-earthquake/`
- Class: `soc_threshold_cascade`
- Pre-registered: b ∈ [1.0, 1.1] (Aki MLE), α_energy ∈ [1.5, 2.0]
- Verdict: PASS
- Paper: `01_earthquake/paper.md`

## Phase 2 — S&P 500 daily log returns 1990-2025

- Source dir: `v4/validation/soc-stockmarket/`
- Class: `soc_threshold_cascade` (financial sub-class)
- Verdict: PASS

## Phase 3 — DeFi liquidations (Aave V2 / Compound V2 / MakerDAO Dog)

- Source dir: `v4/validation/soc-defi/`
- Class: `soc_threshold_cascade`
- Verdict: PASS

## Phase 4 — Mouse ALM cortex avalanches (DANDI:000006)

- Source dir: `v4/validation/soc-neural/`
- Class: `soc_threshold_cascade` (sub-critical task regime)
- Verdict: PASS (scaling relation γ to 2-3 %)

## Phase 6 — GitHub stargazer counts

- Source dir: `v4/validation/soc-github-stars/`
- Class: `preferential_attachment`
- Pre-registered: α ∈ [2.0, 3.0]
- Verdict: PASS

## Phase 7 — North American power-grid cascades (literature-meta catalog)

- Source dir: `v4/validation/soc-power-grid/`
- Class: `motter_lai_network_cascade`
- Verdict: PASS (literature-anchored, low independence)

## Phase 8 — FDIC bank failures 1934-2026

- Source dir: `v4/validation/soc-bank-failures/`
- Class: `tail_copula_contagion`
- Verdict: PASS

## Phase 10 — NIFC wildfires

- Source dir: `v4/validation/soc-wildfire/`
- Class: `soc_threshold_cascade`
- Verdict: PASS (LR vs lognormal contested)

## Phase 11 — GOES X-ray solar flares 2000-2016

- Source dir: `v4/validation/soc-solar/`
- Class: `soc_threshold_cascade`
- Verdict: PASS

## Phase 13 — English Wikipedia pageviews 2023-2024

- Source dir: `v4/validation/soc-wikipedia-views/`
- Class: `preferential_attachment`
- Verdict: PASS (α = 2.034)

## A2-Hysteresis — NGSIM US-101 traffic

- Source dir: `v4/validation/hysteresis-traffic/`
- Class: `hysteresis_first_order_transition`
- Verdict: CONFIRMED_COMPOSITE

## A2-Scheffer — Fox River dissolved oxygen 2011-2024

- Source dir: `v4/validation/scheffer-lake/`
- Class: `scheffer_fold_bifurcation`
- Verdict: INCONCLUSIVE (block-bootstrap correction)

## Phase 14 — Solar-wind speed bursts (Wave 11-E, 2026-05-15)

- Source dir: `v4/validation/soc-solar-wind/`
- Class candidates: `leaky_integrate_fire_threshold_class`, `soc_threshold_cascade`, `fractional_brownian_crossings`
- Pre-registered: burst-size α ∈ [1.8, 2.4]; inter-event α ∈ [1.5, 2.5]
- Verdict: FAIL (burst size in-band but lognormal preferred at R = −5.04, p < 10⁻⁶; inter-event α out of band)
- α̂ burst size: 1.871, CI [1.818, 2.877], n_tail = 519
- α̂ inter-event: 2.841, CI [1.915, 2.988], n_tail = 126
- Source: hybrid (1,699 synthetic Veltri-1999-calibrated + 9,701 NOAA SWPC real)
- Result: `v4/validation/soc-solar-wind/RESULT.md`

## Phase 15 — GitHub issue resolution times (Wave 11-E, 2026-05-15)

- Source dir: `v4/validation/soc-github-resolution/`
- Class candidates: `preferential_attachment`, `extreme_value_tail_class`
- Pre-registered: α ∈ [1.5, 3.0]
- Verdict: PASS (α̂ = 1.836 in band; vs exponential R = +3.49, p < 10⁻³; vs lognormal indistinguishable p = 0.876)
- α̂: 1.836, CI [1.515, 2.121], n_tail = 321
- Source: hybrid (301 real records from `gh api` on 15 OSS repos + 1,699 Bertram-2015-calibrated synthetic)
- Result: `v4/validation/soc-github-resolution/RESULT.md`

---

**Note on hybrid datasets.** Phases 14 and 15 are hybrid real-plus-synthetic.
The synthetic component is honestly labelled in each `fetch_*.py` and
`RESULT.md`; the verdicts are real outputs of the frozen pipeline but should
be interpreted as software validations + modest empirical anchors, not as
fresh cross-domain SOC discoveries. A pure-real follow-up requires multi-year
OMNIWeb solar-wind data and GH Archive BigQuery issue extraction
(cf. project good-first-issues 001 and 003).
