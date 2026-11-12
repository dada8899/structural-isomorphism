# Data acquisition attempts — Gardner-Collins toggle
Date: 2026-05-25

## gardner2000_nature
- got_data: False
- log: GET https://www.nature.com/articles/35002131 -> 200 (292687 bytes); supplementary data not machine-extractable (figure-only)

## tabula_muris_senis
- got_data: False
- log: GET https://tabula-muris-senis.ds.czbiohub.org/ -> 200; portal is SPA, no CSV mirror; .h5ad ~5GB skipped

## Conclusion

Neither the Gardner 2000 supplementary (figure-only, not machine-extractable) nor the Tabula Muris Senis portal (SPA frontend; bulk .h5ad ~5 GB; out of scope for this validation script) yielded a usable expression matrix. Per task brief allowance, we fall through to SYNTHETIC Gardner-Collins ODE simulation as the empirical-baseline verification of the pipeline; verdict is explicitly marked INCONCLUSIVE (synthetic-only) in `verdict.txt`.
