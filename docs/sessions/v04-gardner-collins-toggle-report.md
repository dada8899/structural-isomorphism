# v0.4 Validation Report — `gardner_collins_toggle_switch`

**Date.** 2026-05-25
**Class.** Bistable toggle switch (synthetic biology / immunology)
**Brief.** `docs/v04-validation-plan/per-class/gardner_collins_toggle_switch.md`
**Pre-registered band.** Hill `n ∈ [2.0, 4.5]`; bimodality dip ratio < 0.25;
polarised-state dwell-time exponential cutoff `τ ∈ [5, 40]` days.
Anchor papers: Gardner-Cantor-Collins 2000 Nature 403:339 (n≈2.5-3.5);
Mariani et al. 2010 (Th1/Th2, n≈2.8).

## Verdict (one line)

**INCONCLUSIVE (synthetic-only)** — empirical data inaccessible; pipeline
internal status is FULL_PASS on all four pre-registered checks.

## Data source actually used

Two empirical sources were attempted (see `TRIED.md`):

1. **Gardner-Cantor-Collins 2000 Nature 403:339 supplementary.** HTTP GET
   returned 200 (~292 KB), but the supplementary is figure-only (IPTG/aTc
   induction profiles as scanned plots); no machine-extractable data table.
2. **Tabula Muris Senis CD4 T-cell portal** (`tabula-muris-senis.ds.czbiohub.org`).
   Returned 200 but is a Vue SPA frontend; no CSV mirror, and the bulk `.h5ad`
   is ~5 GB — out of scope for a validation script.

Per task brief allowance, we fell through to a **SYNTHETIC** Gardner-Collins
stochastic ODE simulation:

```
du/dt = α/(1+v^n) - u + σ dW_u
dv/dt = α/(1+u^n) - v + σ dW_v
```

Two regimes (decoupled because Hill-n estimation and dwell-time estimation
have conflicting σ requirements):

| regime | n_true | α | σ | n_cells | n_steps | dt | purpose |
|---|---|---|---|---|---|---|---|
| steady-state | 3.0 | 5.0 | 0.20 | 2500 | 4000 | 0.1 | bimodality + Hill fit |
| dwell | 3.0 | 5.0 | 0.95 | 800 | 20000 | 0.1 | Kramers transitions |

Integration step `dt=0.1` is mapped to 0.1 day (canonical biology rate
normalisation; not anchored without empirical data).

## Pre-registered band vs observed

| Check | Pre-reg threshold | Observed | In band? |
|---|---|---|---|
| Hill coefficient `n` | [2.0, 4.5] | **3.26 ± 0.13** (R²=1.00, 10 bins) | yes |
| Bimodality dip ratio | < 0.25 | **0.000** (clear u/v separation) | yes |
| GMM-2 vs GMM-1 BIC delta | > 10 | **+1368** (decisive) | yes |
| Dwell-time tail KS (vs exp) | p ≥ 0.01 | **p = 0.458** (40,373 dwells; tail above median) | yes |
| Dwell-time mean τ | [5, 40] days | **38.0 days** (median 20.8) | yes (bonus) |

All four pre-registered checks pass internally. **Verdict remains
INCONCLUSIVE per task-brief rule** ("synthetic data → must explicitly flag
INCONCLUSIVE in `verdict.txt`").

## Null controls (all behave as expected)

| distribution | dip ratio | GMM₁−GMM₂ BIC (positive = bimodal favoured) | interpretation |
|---|---|---|---|
| unimodal Gaussian | 1.00 | **−21.2** | correctly rejected (GMM-1 wins) |
| exponential | 1.00 | +1074 | BIC misled by skew; dip ratio correctly = 1 → rejected |
| lognormal | 1.00 | +2593 | same — dip is the critical guard |
| uniform | 0.72 | +288 | borderline; dip not sufficient → rejected |
| true bimodal Gaussian mixture | 0.00 | +3738 | positive control passes |

Lesson: BIC alone over-fits non-Gaussian unimodal tails; the **dip-ratio +
BIC dual criterion** is necessary to avoid false positives. This pattern is
re-usable for any future bistability validation in this work.

## P-values

- Bimodality (GMM-2 preferred): ΔBIC = 1368 (≫ 10; strong evidence)
- Hill fit (curve_fit): n = 3.26 ± 0.13, R² = 1.00
- Dwell KS vs exponential (full distribution): p = 0.000 (bulk has transient
  deviation — expected for Kramers)
- Dwell KS vs exponential (**tail above median**, 20,187 dwells): **p = 0.458**
  (asymptotic Kramers tail recovered)

## Honest limitations

1. **Synthetic data only.** The recovered exponent and bimodality reproduce
   what we designed into the simulator (`n_true = 3.0` → fit n = 3.26).
   This validates that *the pipeline works*, not that *the empirical world
   is in this class*. The brief's anchor for "this class is real" remains
   Gardner 2000 + Mariani 2010 + clinical Tabula Muris — none of which were
   computationally accessible here.
2. **Dwell-time band is biology-anchored.** The 5-40 day band derives from
   T-cell biology. Synthetic rate constants have no physical timescale
   without an experimental anchor; the τ=38 day match is a *parameter
   tuning artefact* (σ was chosen to land in the band), not an
   independent validation. We separate `magnitude_ok` from `structure_ok`
   (Kramers exponential tail) in the results for honesty.
3. **No v1/v2 comparison.** Brief flags `gardner_collins_toggle_switch_v2`
   as MERGE-pending. v2 has not yet been pushed through the same pipeline;
   the merge decision cannot be made from this report alone.
4. **Small bin count (10) in Hill fit.** I/O curve is a quantile binning;
   tail bins have ~250 cells but the curve_fit standard error (n_se=0.13)
   may under-represent model misspecification.

## Implications for v0.4 paper

- `gardner_collins_toggle_switch` status: **PIPELINE_VALIDATED,
  EMPIRICAL_PENDING**. Do **not** flip `verified=true` in
  `universality-classes.json` based on this run.
- Pipeline is now reusable for any bistability class (`hysteresis_*`,
  `scheffer_fold_*`); the BIC+dip+tail-KS triple is non-trivial because
  any one alone produces false positives in null controls.
- Empirical-upgrade path is clear: (a) ImmPort SDY1412 registration +
  CD4 Tbx21/Gata3 marker extraction; (b) manual extraction from Gardner
  2000 Fig 5; (c) full Tabula Muris `.h5ad` pipeline on a separate run.
- Paper text should cite this report as "pipeline validation on the
  canonical Gardner-Collins ODE" with explicit synthetic flag, *not* as
  empirical confirmation.

## Files

- Pipeline: `v4/validation/gardner-collins-toggle/run_validation.py`
- Results: `v4/validation/gardner-collins-toggle/results.json`
- Verdict: `v4/validation/gardner-collins-toggle/verdict.txt`
- Run log: `v4/validation/gardner-collins-toggle/run.log`
- Data attempts: `v4/validation/gardner-collins-toggle/TRIED.md`
- KB additions (8 entries): `data/kb-additions-2026-05-25-gardner-collins-toggle.jsonl`
