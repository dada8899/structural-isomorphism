# [tutorial] New tutorial — designing synthetic null controls

## What

Add `tutorials/04_synthetic_null_design.ipynb` walking through how to design a *synthetic null control* for a candidate SOC dataset. The notebook should explain why naive shuffling is insufficient, demonstrate the project's `synthetic_null` helper, and walk through one worked example end-to-end.

## Why

In our dogfooding sessions we keep seeing contributors confused about "why your fit looks SOC-like on shuffled data — is your detector broken?" — the answer is "you need a synthetic null, not a shuffle null." This is a known pedagogy gap. Filling it pre-empts the next 20 GitHub issues.

## Where

- New file: `tutorials/04_synthetic_null_design.ipynb`
- Helper to demo: `packages/soc-pipeline/src/soc_pipeline/null_controls.py::synthetic_null`
- Reference style: `tutorials/01_reproduce_earthquake_soc.ipynb` (good rhythm of motivation → code → result → interpretation)

## How to start

1. Open `01_reproduce_earthquake_soc.ipynb` to study the tutorial pattern (markdown cell → code cell → result discussion).
2. Section structure suggestion:
   - **Why shuffle nulls fail** (1 figure showing power-law false-positive on shuffled lognormal)
   - **The synthetic-null recipe** (generate 4 surrogate processes: pure lognormal, pure exponential, exponentially-truncated power-law, lognormal+heavy-tail mixture)
   - **Calling `synthetic_null()`** in soc_pipeline
   - **Reading the verdict matrix** (when does the detector correctly reject?)
   - **Mini-exercise**: ask the reader to design a null for their own dataset
3. Render the notebook with `jupyter nbconvert --execute` and commit cell outputs.
4. Add an entry to `tutorials/README.md`.

## Definition of done

- [ ] Notebook runs cell-by-cell in < 60 s on a laptop
- [ ] At least 3 figures (motivation, recipe, verdict matrix)
- [ ] Listed in `tutorials/README.md`
- [ ] Linked from `docs/index.md` learning path
- [ ] No outbound API calls (synthetic data only)

## Difficulty

★★ (pedagogy + light statistics)
