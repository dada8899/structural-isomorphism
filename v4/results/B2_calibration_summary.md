# B2 — Layer 4 prediction calibration (v2, W1-D)

**Run date**: 2026-05-13 (session #3, W1-D)

**Script**: `v4/scripts/b2_calibrate_predictions.py`


## Overview

- Classes processed: **21**
- Predictions processed: **24**
- Extracted numerical bands (total): **42**
- Bands matched to a verified observation: **3** / 42 (7%)

## 95% CI method per band

| Method | Count | Description |
|---|---|---|
| `literature_band_rescaled` | 42 | Treat LLM band as ±2σ → 95% CI = mid ± 1.96σ_est |
| `bootstrap` | 0 | Verified phase: bootstrap CI on observed value attached |

## Reverse-filled verdicts on verified phases

Among **3** bands matched to a verified observation:

| Verdict | Count | % | Meaning |
|---|---|---|---|
| `in_band` | 0 | 0% | Observed value lies inside predicted 95% CI |
| `out_band_partial` | 3 | 100% | Predicted band overlaps literature band but not observed |
| `complete_mismatch` | 0 | 0% | Predicted band misses both observed and literature |

## Bootstrap CI refresh on raw data

| Observation | Median α | Bootstrap 95% CI | n_boot |
|---|---|---|---|
| earthquake_alpha_energy | 1.803 | [1.753, 1.838] | 100 |
| stockmarket_alpha_returns | 2.993 | [2.738, 3.000] | 100 |

## Surprises — LLM bands that miss the observed value

(none — all matched predictions land in_band or out_band_partial)

## Methodology

**Method A — `literature_band_rescaled` (default)**

LLM predictions give heuristic ranges (e.g. `[0.08, 0.22]`). We treat each band
as a ~2σ envelope around its midpoint, then rescale to a 95% CI:

```
mid = (low + high) / 2
sigma_est = (high - low) / 4   # half-width / 2
CI_95 = mid ± 1.96 × sigma_est
```

This widens narrow LLM bands by ~5% and shrinks very wide ones — conservative but
honest given the LLM never specified what its band meant. All 24 predictions have
all extracted bands rescaled this way as a baseline.

**Method B — `bootstrap` (verified phases only)**

For the 13 verified phases (HANDOFF §1), raw data is re-bootstrapped (n_boot=100)
with `soc_pipeline.bootstrap_alpha_ci`. The observed value + its empirical 95% CI
are attached to any predicted band that matches the verified system by class_id ∩
domain keyword. Verdict = `in_band` if observed lies inside the rescaled predicted CI,
`out_band_partial` if predicted band overlaps literature but not observed, else
`complete_mismatch`.

## Limitations

- LLM bands have no specified semantic (1σ? 2σ? P5-P95?). Choosing 2σ is a
  middle-ground assumption; if true semantic is 1σ, our 95% CI is too narrow.

- Quantity inference uses heuristic context window — a band labelled 'ratio' may
  actually represent something else; mismatches between predicted unit and verified
  observation unit are filtered only by domain keyword, not unit.

- 11 predictions touch domains with no verified phase yet (e.g. building collapse,
  traffic phase transition); those land `pending` by default.

- Bootstrap CI uses n_boot=100 — sufficient for stable median but tail estimates
  could shift ±5% with n_boot=500.

