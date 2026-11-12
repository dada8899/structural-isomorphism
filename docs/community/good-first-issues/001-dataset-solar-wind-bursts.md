# [data] Add solar-wind speed-burst dataset with pre-registered SOC band

## What

Add a new empirical SOC validation dataset for solar-wind speed bursts (proton bulk-velocity excursions in the heliospheric current sheet). Pre-register a power-law exponent band before running `soc-pipeline.validate()`, then file the actual fit verdict.

## Why

Solar-wind bursts are a textbook intermittent / avalanche-like signal but are absent from our 21-system catalog in `v4/validation/`. A maintainer-vetted pre-registration here grows the cross-domain breadth that the unified preprint hinges on (Phase A → 25+ systems). Heliospheric data is also publicly available via NASA OMNIWeb, so newcomers can ship without API keys.

## Where

- `v4/validation/soc-solar/` (existing — flares; add `soc-solar-wind/` sibling)
- Pattern to mirror: `v4/validation/soc-earthquake/` (catalog + analyze script + `verdict.json`)
- Class YAML to reference (post-fit): `dataset/v1/structural-isomorphism-v1.0-benchmark/taxonomy/classes/leaky_integrate_fire_threshold_class.yaml` (LIF + threshold is the closest existing universality class)

## How to start

1. Fetch hourly proton-velocity data 2010-2020 from [OMNIWeb low-resolution](https://omniweb.gsfc.nasa.gov/) (`Vp` channel). One JSONL line per burst event.
2. Define a "burst" as a contiguous run where `Vp > μ + 2σ` (rolling window 30 days). Burst size = integrated excess area.
3. Write a pre-registration markdown at `paper/pre-registrations/solar-wind-bursts.md` with your guess band (suggested α ∈ [1.8, 2.4] per [Freeman & Watkins 2002](https://doi.org/10.1126/science.1075962)) **before** running the fit.
4. Run `from soc_pipeline import fit_clauset_powerlaw; fit_clauset_powerlaw(sizes)`.
5. Commit pre-registration, raw catalog, analyze script, and `verdict.json` together.

## Definition of done

- [ ] `v4/validation/soc-solar-wind/catalog.jsonl` committed (with Git LFS if > 5 MB)
- [ ] `v4/validation/soc-solar-wind/analyze.py` runs end-to-end on the catalog
- [ ] `v4/validation/soc-solar-wind/verdict.json` written by `analyze.py`
- [ ] Pre-registration at `paper/pre-registrations/solar-wind-bursts.md`, dated, committed **before** the verdict
- [ ] Test added at `v4/tests/integration/test_solar_wind.py` that asserts `verdict.alpha is not None` and exits in < 60 s on a 1000-event subset

## Difficulty

★★ (data wrangling + light scipy; no LLM, no GPU)
