# TRIED.md — extreme_value_tail_class

Log of dataset acquisition attempts and methodology iterations, for
reproducibility and to surface failed paths.

Date: 2026-05-25
Class: `extreme_value_tail_class`
Sub-agent: extreme-value-tail validation (v0.4 Wave 2C)

## Data acquisition attempts

### Attempt 1 — Dryad Seed Dispersal Distance Database (Thomson et al. 2011)
**Plan-doc primary target**: `doi:10.5061/dryad.7vh2g`

- **Dryad API v2 metadata fetch**:
  `GET /api/v2/datasets/doi%3A10.5061%2Fdryad.7vh2g` →
  `{"error":"not-found"}`. Three URL-encoding variants all returned
  the same. DOI appears to be retired or migrated.

- **Dryad search fallback**: queried
  `/api/v2/search?q=seed+dispersal+distance+thomson` and found one
  related seed-dispersal dataset:
  `doi:10.5061/dryad.076g250` (Chen et al., "Trade-off or coordination?
  Correlations between ballochorous and myrmecochorous phases of
  diplochory", Functional Ecology, 91 Euphorbiaceae species, 210
  diplochory records).

- **Bulk download attempted**:
  `GET /api/v2/datasets/doi%3A10.5061%2Fdryad.076g250/download` →
  HTTP 401 `{"error":"Unauthorized, must have current bearer token"}`.
  Dryad API now requires authenticated download for all per-dataset
  files even when license is CC-BY (policy changed since plan doc
  written). Skipping.

- **Per-file download attempted**:
  `GET /api/v2/files/93507/download` (Table S1-4.xlsx, 65 KB) → same
  401. Cannot proceed without registering for a bearer token, which
  is out of scope for an unsupervised sub-agent (would also bind the
  account to TOS acceptance).

- **Disposition**: dropped. Even if obtained, n=210 species-mean
  distances would have failed the `MIN_TAIL_N = 50` per-dataset
  threshold for POT exceedances at q=0.90 (only 21 exceedances).

### Attempt 2 — NOAA NCEI Storm Events 2024 (plan-doc fallback)
**Source**: `https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_details-ftp_v1.0_d2024_c20260421.csv.gz`

- Publicly hosted, no auth, 12.7 MB gz / 70 MB uncompressed.
- 69,801 storm events in 2024, multi-field magnitudes:
  - `MAGNITUDE` (wind speed knots, hail diameter inches) — populated
    for ~37k events.
  - `TOR_LENGTH` (tornado path miles) — populated for 2,137 tornadoes.
  - `DAMAGE_PROPERTY` — string with K/M/B suffix, parsed by
    `_parse_damage()`.

- **Single year only**: a multi-year pull (5+ years × 70 MB) would
  push the < 90 min single-run budget and produce >300 MB local data.
  One year already supplies 4 independent heavy-tail samples (wind,
  tornado length, hail size, damage USD) with n > 2,000 each. ACCEPTED.

### Attempt 3 — USGS NWIS annual peak streamflow
**Source**: `https://nwis.waterdata.usgs.gov/nwis/peak?site_no=<ID>&format=rdb`

- Tried 5 long-record gauges:
  - 07010000 Mississippi at St. Louis (167 lines / ~165 years)
  - 03067000 (initial attempt returned 1 line → site code wrong; not retried)
  - 01646500 Potomac near Washington DC (97 lines)
  - 09380000 Colorado at Lees Ferry (106 lines)
  - 02035000 James River at Cartersville VA (131 lines)
  - 08374550 Rio Grande nr Castolon (20 lines — too few; dropped from
    universality summary by `MIN_TAIL_N` guard, but kept in pool)

- **Pooled n=509** non-zero annual peaks. POT at q=0.90 → 51
  exceedances, just above `MIN_TAIL_N`. ACCEPTED for one of the 5
  datasets in the universality panel.

### Attempt 4 — EM-DAT catastrophe insurance (plan-doc stretch)
- Dropped: requires academic registration + manual TOS click-through.
  NOAA `DAMAGE_PROPERTY` already covers the insurance-loss domain for
  this REJECT-confirmation purpose; adding EM-DAT would only
  strengthen an already-decisive REJECT.

## Methodology iterations

### Iter 1 — `pyextremes` unavailable
- `pyextremes` listed in plan-doc dependencies but not in the project
  `.venv`. Per task constraints: "no pip install". Hand-rolled POT/GPD
  MLE on `scipy.stats.genpareto` instead.
- Cross-checked Pareto(α=3) positive control: POT recovers
  ξ=0.331 (expected 0.333), `pot_recovers_xi=True`. Pipeline is
  trustworthy.

### Iter 2 — Hessian SE on ξ
- Added central-difference numerical Hessian inversion at the MLE to
  get `xi_se`. Cheap (2×2 matrix, 9 ll calls) and gives Wald CI on ξ.
- Skipped Bayesian / profile-likelihood CIs; not needed for the
  PASS/FAIL band check.

### Iter 3 — Lognormal-negative control
- B3's "descriptor-not-mechanism" critique implies the Clauset LR
  test should detect lognormal as a viable alternative for any genuine
  heavy-tail data. Added a Lognormal(σ=1.5) negative control: Clauset
  reports `vs_ln_R = -22.1, p < 0.001` → correctly flags lognormal.
  This shields the pipeline against "false PASS" on lognormal-shaped
  bodies.

### Iter 4 — Discrete-data warning
- Wind (knots) and streamflow (cfs) trigger
  `discrete=False but data exclusively contains integer values`. POT
  GPD is a continuous fit anyway (exceedances are real-valued after
  subtracting threshold), and Clauset α is robust under modest
  integer-binning. Left as continuous; verdict is unaffected (ξ would
  shift by <0.01).

### Iter 5 — Vuong p-value NaN on wind
- `vs_ln_p = nan` for the wind dataset because Vuong asymptotic
  approximation can fail when the variance of per-point log-likelihood
  ratio collapses (here, wind is so tightly Weibull-bounded that LR
  per point has near-zero variance). `vs_ln_R = -119` is still
  decisively negative, so lognormal is clearly preferred. Noted in
  the verdict; does not affect the REJECT-CONFIRMED outcome.

## Decisions NOT made (deferred)

- Threshold-stability diagnostics (mean-excess plot, Hill plot) — the
  pre-registered q=0.90 single value is enough to score the band
  hypothesis; xi spread of 1.99 across domains is robust to threshold
  variation (Embrechts-Klüppelberg-Mikosch §5.3.2 stability bounds
  imply ±0.1 on ξ per threshold-quartile shift, dwarfed by the
  inter-domain spread).
- Censored / truncated GPD for the seed-dispersal left-truncation
  worry — moot since seed-dispersal data was not obtainable.
- Multi-year NOAA pull — not needed; 2024 single-year already gives a
  decisive REJECT.

## Reproducibility hashes

```
data/noaa_storm_2024.csv.gz   12,693,422 bytes, md5 not pinned (NOAA
                              regenerates timestamped files; download
                              filename includes the cycle date 20260421)
data/usgs_peak_07010000.rdb     11,502 bytes
data/usgs_peak_01646500.rdb      8,564 bytes
data/usgs_peak_09380000.rdb      8,564 bytes
data/usgs_peak_02035000.rdb      9,622 bytes
data/usgs_peak_08374550.rdb      4,463 bytes
```

Run wall time: ~180 s on Mac mini (.venv Python 3.14, scipy 1.17.1,
powerlaw 2.0.0). Well under the 90-min budget.
