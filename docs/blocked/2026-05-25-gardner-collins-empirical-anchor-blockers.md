# BLOCKED — Gardner-Collins Toggle Empirical Anchor

> **Date.** 2026-05-25 (SESSION-24)
> **Trigger.** SESSION-23 handoff §8 outstanding #10 + SESSION-24 task (c).
> **Status.** **BLOCKED-ON-EXTERNAL.** Three candidate data sources all hit independent acquisition barriers; CC cannot resolve without human action or a multi-hour interactive data-digitisation session.

## Context

`gardner_collins_toggle_switch_v1` is currently INCONCLUSIVE (synthetic-only) — Hill `n = 3.26` and dwell time `38 d` are in pre-reg band but those numbers come from the pipeline's own ODE simulator (`run_validation.py`). The KB has 0 real-data anchor entries for this class. SESSION-24 (c) aimed to wire one.

## Three candidate data sources (per per-class brief), each blocked

### Source 1 (primary, blocked) — Gardner-Cantor-Collins 2000 Nature 403:339 Fig 5

- **What it is.** The original paper that defines the synthetic genetic toggle switch in E. coli (IPTG/aTc induction profiles). 24 induction profiles in Fig 5 + 1 supplementary table.
- **What we have.** HTML fetch returns 200 (292 KB), but content is the journal article landing page; raw data tables not present.
- **Blocker.** Fig 5 is a *figure*, not a data table — the published numbers exist only as plotted points. Recovering them requires either:
  - Manual point-by-point digitisation from the figure image (WebPlotDigitizer / similar tool, ~2-3 h human time per figure)
  - OCR + plot reconstruction via vision model (Claude with image attachment + careful prompting, ~1 h interactive)
  - Author email request for raw `.csv` (slow + uncertain)
- **CC blocker.** This session has no image-attachment in conversation; cannot directly invoke vision. The Nature image URL is gated behind their CDN; even with vision, plot reconstruction needs interactive tuning.

### Source 2 (fallback, blocked) — Tabula Muris Senis CD4 atlas (Th1/Th2 polarisation)

- **What it is.** 110,000 CD4 T cells across tissues; Tbx21 / Gata3 markers used to detect bimodality (Th1 vs Th2 polarisation).
- **What we have.** Web portal `tabula-muris-senis.ds.czbiohub.org` returns 200, but it's a SPA frontend with no CSV mirror.
- **Blocker.** Bulk download is `.h5ad` (AnnData), ~5 GB, requires `scanpy` + significant compute + extracting just two markers from the full atlas.
- **CC blocker.** 5 GB download exceeds the script wall-clock budget; the full atlas processing (loading, subsetting, computing bimodality) takes ~30 min on a workstation.

### Source 3 (stretch, blocked) — ImmPort SDY1412 / SDY1419 single-cell CD4

- **What it is.** ImmPort study SDY1412 (allergic rhinitis) + SDY1419 (TB) CD4 panels, ~45 patients × 5-15 k cells each.
- **Blocker.** Free **but registration-required**. ImmPort requires user account + study-specific request approval. Cannot be scripted; requires human registration step.
- **CC blocker.** Cannot create accounts or accept TOSes on behalf of the user.

## What CC can do right now (without breaking blockers)

1. **Document blockers** (this memo).
2. **Make synthetic-only verdict explicit and honest.** Existing `verdict.txt` does this; nothing to add.
3. **Pre-stage data-fetch scaffolding** so that when blockers are resolved, the pipeline runs in one command. Already exists in `run_validation.py` + `TRIED.md` audit trail.

## Recommended path forward (ranked by ROI for the human)

### Path A — Gardner 2000 Fig 5 OCR (highest ROI, ~1 h human)

Best value for time invested. Use **WebPlotDigitizer** (browser tool, free):

1. Save Fig 5 from `https://www.nature.com/articles/35002131` as PNG (right-click figure → Save Image).
2. Open WebPlotDigitizer (https://apps.automeris.io/wpd/), load image, calibrate axes, click each data point.
3. Export CSV → `data/gardner_collins_toggle_switch/gardner2000_fig5.csv`.
4. Re-run validation with `--data data/...gardner2000_fig5.csv` flag.
5. Expected outcome: real Hill `n` should be 2-4 (per Gardner-Cantor 2000 abstract); verdict should flip from INCONCLUSIVE → PASS-CONFIRMED if in band.

Estimated time: 30-45 min digitisation + 10 min CC re-run + 15 min verdict update.

### Path B — Tabula Muris Senis subset script (highest data quality, ~3 h human + compute)

Multi-step:

1. Install `scanpy` + dependencies in a fresh venv (or use existing `.venv` — pip install scanpy ~5 min).
2. Download CD4 subset `.h5ad` via Tabula Muris Senis bulk-download (~1 GB partial).
3. Run a 30-line scanpy script extracting Tbx21 / Gata3 columns to CSV.
4. CC takes over with bimodality + Hill fit pipeline.

Estimated time: 1 h setup + 30 min download + 30 min processing + 15 min verdict = ~2.5 h total.

### Path C — ImmPort registration + SDY1412 download (highest clinical relevance, ~1 week)

1. Register at https://www.immport.org (free, 1-2 day approval).
2. Request SDY1412 / SDY1419 study access (approval can take 3-5 days).
3. Download per-patient FCS files.
4. Run FlowJo-style gating (manual or scripted) + Hill fit.

Estimated time: 1 week elapsed (mostly waiting for approvals) + ~4 h hands-on.

## What this BLOCKED status means for the v0.4 paper

- `gardner_collins_toggle_v1` verdict remains **INCONCLUSIVE (synthetic-only)** in v0.4 §3 verdict matrix. No change.
- The v2 (`gardner_collins_toggle_v2`) verdict (PASS + SPLIT vs v1) is unaffected — v2's empirical anchor came from a different anchor case.
- The v0.5 paper revision (if any) should note this blocker explicitly in §6.x "synthetic-anchored classes" caveat list.

## SESSION-24 (c) closure

(c) closes as **BLOCKED-ON-EXTERNAL with path documented**. CC cannot make further progress without one of:
- A 30-45 min WebPlotDigitizer session (Path A, recommended)
- A scanpy install + bulk download (Path B)
- An ImmPort account registration (Path C, multi-day)

When you complete any of the three paths, ping a new CC session with "gardner_v1 anchor data ready at `<path>`, re-run validation" — the pipeline will run in one command.

## Related artifacts

- TRIED.md acquisition log: `v4/validation/gardner-collins-toggle/TRIED.md`
- Per-class brief: `docs/v04-validation-plan/per-class/gardner_collins_toggle_switch.md`
- Validation script: `v4/validation/gardner-collins-toggle/run_validation.py`
- Current verdict (synthetic-only): `v4/validation/gardner-collins-toggle/verdict.txt`

End of memo. Closes SESSION-24 (c) as documented-blocker.
