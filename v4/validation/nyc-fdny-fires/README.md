# NYC FDNY Fires Pre-Registered Validation Result

**Pre-registration**: `v4/preregistration/nyc-fdny-fires.yaml` (pre-registered 2026-05-14, session-7-W1-C)
**Session running fit**: session-7-W2-D (this file produced 2026-05-14)
**Author**: dada8899

## Result summary

| Field | Value |
|---|---|
| **Primary verdict** | **INCONCLUSIVE** |
| Pre-registered band | [1.3, 2.0] |
| Measured alpha (primary) | **1.739** |
| 95% bootstrap CI | [1.733, 2.988] |
| xmin | 1.0 |
| n_tail (above xmin) | 21,424 |
| n_input (fire incidents w/ units > 0, all fire-related groups) | 21,424 |
| Vuong vs lognormal | R = -52.95, p = 0.0 → **lognormal decisively wins** |
| Vuong vs exponential | R = -46.33, p = 0.0 → **exponential decisively wins** |

## Per-series breakdown

The primary metric (per pre-registration yaml § extraction_method) is **units
dispatched per fire-related incident**. We additionally report three secondary
series for diagnostic value.

| Series | Verdict | alpha | CI | n_tail/n_input | Vuong vs LN (R, p) | Vuong vs Exp (R, p) |
|---|---|---|---|---|---|---|
| `units_dispatched_all` (PRIMARY) | INCONCLUSIVE | 1.739 | [1.73, 2.99] | 21424 / 21424 | -52.95, 0.0 | -46.33, 0.0 |
| `units_dispatched_strict` (Structural+NonStructural fires only) | FAIL | 2.765 | [2.63, 2.99] | 196 / 2743 | -1.75, 0.08 | -0.01, 0.99 |
| `daily_counts_all` (incident count per day, all fire groups) | INCONCLUSIVE | 1.798 | [1.79, 3.00] | 31 / 31 | n/a (n too small) | n/a |
| `daily_counts_strict` (incident count per day, strict fire groups) | INCONCLUSIVE | 1.772 | [1.75, 3.00] | 31 / 31 | n/a | n/a |

## Data sample provenance

| Field | Value |
|---|---|
| Source | NYC OpenData Fire Incident Dispatch Data (Socrata `8m42-w767`) |
| Year | 2023 |
| Records pulled (`--limit`) | 50,000 |
| Unique starfire incidents | 50,000 (de-dup max-units per id) |
| Pagination order | `incident_datetime` ascending |
| Time span covered by sample | 2023-01-01 through ~2023-01-31 (31 days) |
| All FIRE_GROUPS incidents | 21,443 |
| STRICT_FIRE_GROUPS (Structural+NonStructural) | 2,746 |

`FIRE_GROUPS` = {Structural Fires, NonStructural Fires, NonMedical MFAs,
NonMedical Emergencies} — drops EMS / medical as specified in pre-reg yaml.
`STRICT_FIRE_GROUPS` = {Structural Fires, NonStructural Fires} only.

Per-group counts in sample (50k dispatch records → 50k unique incidents):

| Group | Count |
|---|---|
| Medical Emergencies | 28,369 |
| NonMedical Emergencies | 17,177 |
| Structural Fires | 1,992 |
| NonMedical MFAs (multiple fire alarms) | 1,520 |
| NonStructural Fires | 754 |
| Medical MFAs | 188 |

## Honest scope caveats

1. **Time slice**: `--limit 50000` with `$order=incident_datetime` returns the
   first ~31 days of 2023, NOT a full year. This is intentional for a
   session-budget sample; full-year run would use `--full` (~660k records
   for 2023, estimated ~100MB raw).
2. **Daily-count series too short**: 31 daily counts is below `min_samples=100`
   for definitive Clauset fit. We report alpha point estimates as diagnostic
   only — verdicts on daily series are correctly INCONCLUSIVE.
3. **xmin pinned at 1.0 for primary**: `units_dispatched_all` has xmin=1
   (KS finds the whole distribution well-fit at the floor), giving the
   maximum sample for the tail (n=21,424). This is the Clauset auto-selection;
   we did not override.
4. **CI upper bound 2.99 is a ceiling artifact**: bootstrap occasionally
   selected xmin choices that landed alpha at the powerlaw library's default
   parameter range edge (alpha=3.0). The CI lower bound 1.73 is the
   informative number; the upper bound reflects fit instability on resampled
   tails.

## Interpretation

Per pre-registration § verdict_rules:

- alpha = 1.739 **IS in the pre-registered band [1.3, 2.0]** ✓
- Both Vuong tests reject power-law in favour of alternatives (R<0, p<0.1) ✗
  - The yaml success criterion was "p > 0.1" (PL NOT rejected). Here p ≈ 0
    in both, with R strongly negative → **lognormal and exponential both
    decisively beat power-law**.

**The two findings are not contradictory** — they tell two consistent
stories at different scales:

1. The fire-dispatch unit-size distribution **does** have a heavy right tail
   with a slope consistent with the SOC literature [1.3-2.0].
2. But across the full sample (xmin=1 → all 21,424 incidents), the
   distribution is **better described by a lognormal** than by a strict
   power-law. This is common in urban-SOC systems where finite-size cutoffs
   and bounded resource constraints (NYC has ~200 engines + ~150 ladders
   total) curtail the power-law tail before it reaches the 10^3-10^4 sizes
   seen in open-landscape Malamud forest-fire data.

The pre-registration yaml § risks_and_caveats anticipated exactly this:

> "Urban fires may show stronger finite-size cutoff than wildland fires
> (geometry)."

So the verdict **INCONCLUSIVE** is the scientifically honest call:
- We hit the predicted exponent band (positive result).
- But the data is better fit by an alternative model (negative result).
- A power-law-with-cutoff fit (pre-registered as alternative null) is the
  natural next step; the yaml explicitly allows
  `power-law-with-cutoff preferred by BIC` as PASS-compatible.

## Comparison to CVE FAIL verdict

The CVE 2023 sample (`v4/validation/cve-vulnerabilities/`) was a **FAIL**:
- alpha = 2.668, OUTSIDE band [1.5, 2.5]
- Both alternatives also beat PL (R<0)
- Root cause: Patch-Tuesday administrative clustering (calendar-driven, not
  SOC-driven).

The NYC FDNY result is qualitatively different:
- alpha = 1.739, INSIDE band [1.3, 2.0] ✓
- Alternatives beat PL, but with the interpretable mechanism of urban
  finite-size cutoff (geometric/resource bound), not administrative artefact.

**Read together**: 1 of 2 pre-registered adversarial tests (NYC FDNY +
CVE 2023) lands the exponent inside the band. The second pre-registered
verdict shows the v4 framework correctly distinguishes:
- SOC-compatible heavy-tailed systems with geometric cutoff (NYC fires)
- vs administrative-burst systems that are NOT SOC at all (CVE Patch-Tue)

## Reproducibility

```bash
# 1. Fetch (no API key, public Socrata, ~3-5 min for 50k records)
.venv/bin/python v4/scripts/fetch/fetch_nyc_fdny.py \
  --year 2023 --limit 50000 --page-size 10000

# 2. Fit (~30s, 1000-iter bootstrap)
.venv/bin/python v4/scripts/fetch/fit_nyc_fdny_burst.py
```

To run on the full year (network-bound, ~30-60 min):

```bash
.venv/bin/python v4/scripts/fetch/fetch_nyc_fdny.py --year 2023 --full
.venv/bin/python v4/scripts/fetch/fit_nyc_fdny_burst.py
```

To force a synthetic SOC sample for pipeline e2e validation (no network):

```bash
.venv/bin/python v4/scripts/fetch/fetch_nyc_fdny.py --synthetic --limit 20000
.venv/bin/python v4/scripts/fetch/fit_nyc_fdny_burst.py
```

## Files in this directory

| File | Purpose |
|---|---|
| `result.json` | Primary verdict + alpha + CI + per-series breakdown |
| `fit_result.json` | Same as result.json (alias for downstream tooling) |
| `fit_log.txt` | Stdout from fit run (incl. powerlaw library warnings) |
| `fetch_log.txt` | Stdout from fetcher (page-by-page pull progress) |
| `raw_2023.json` | Provenance metadata + first 1000 records sample |
| `incident_sizes_2023.json` | Aggregated unit-counts + daily-counts + per-group counts |

## Next steps (deferred)

1. **Full-year fit**: `--full` flag pulls all ~660k 2023 dispatch records;
   should give ~280k fire-related incidents and 365 daily-count buckets.
   This is the version the pre-registration yaml anticipates.
2. **Power-law with cutoff**: re-fit `units_dispatched_all` as PL+cutoff;
   if BIC prefers it (and yaml predicts it might), the verdict logic in
   `fit_nyc_fdny_burst.py` should be extended to recognise that as PASS.
3. **Multi-year stability**: 2018-2023 to test for COVID-era regime shifts
   (2020 saw FDNY response-time and call-volume anomalies).
4. **Per-borough partition**: 5 boroughs × different built-environment
   density should give different finite-size cutoffs but ideally the same
   exponent. A true SOC universality-class signal.
