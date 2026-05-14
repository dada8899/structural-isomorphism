# [tests] Improve test coverage of `soc_pipeline.pandas_accessor`

## What

The `.soc` pandas accessor (`packages/soc-pipeline/src/soc_pipeline/pandas_accessor.py`, shipped in W8-e) currently has only the happy-path test from `tutorials/03_pandas_accessor.ipynb`. Add comprehensive unit tests covering: empty Series, NaN-containing Series, non-numeric dtype, MultiIndex inputs, and the `validate()` shortcut method.

## Why

The accessor is the user-facing surface that newcomers will hit first (literally `df['size'].soc.fit()`). Bugs here will be the first thing external researchers notice. Right now if a user passes a Series with even one NaN the behaviour is undocumented.

## Where

- Target file: `packages/soc-pipeline/src/soc_pipeline/pandas_accessor.py`
- Place new tests at: `packages/soc-pipeline/tests/test_pandas_accessor.py`
- Existing happy-path notebook: `tutorials/03_pandas_accessor.ipynb`

## How to start

1. Baseline coverage:
   ```bash
   cd packages/soc-pipeline
   pip install -e .[dev]
   pytest --cov=soc_pipeline.pandas_accessor --cov-report=term-missing tests/
   ```
2. Write tests for at minimum these cases (one assert each):
   - Empty Series → should raise `ValueError` (or return a sentinel `FitResult.error`?)
   - Series with NaN → document policy (drop? raise?) and test it
   - Series of strings → should raise `TypeError`
   - 10-element Series → should return `FitResult` with `n_total == 10`
   - MultiIndex Series → should still work; values matter, not index
   - `.soc.validate()` chained call returns a verdict object
3. Update `packages/soc-pipeline/README.md` to document the policy decisions you make.

## Definition of done

- [ ] Coverage ≥ 90 % on `pandas_accessor.py`
- [ ] Policy for NaN / empty / wrong-dtype documented in README
- [ ] Tests run in < 5 s
- [ ] CI green

## Difficulty

★ (well-scoped pandas / pytest work)
