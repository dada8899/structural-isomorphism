# [tests] Add coverage for `v4/lib/multitest_correction.py`

## What

`v4/lib/multitest_correction.py` implements Benjamini-Hochberg FDR + Bonferroni adjustments used by every phase-verification pipeline. It currently has < 60 % branch coverage. Bring it to ≥ 85 %.

## Why

Multi-test correction is statistically critical — a bug here silently inflates or deflates every reported p-value across all 21 validated systems. We need bulletproof tests on this file before the preprint goes to arXiv.

## Where

- Target file: `v4/lib/multitest_correction.py` (192 lines)
- Place new tests at: `v4/tests/sanity/test_multitest_correction.py`
- Reference: [Benjamini & Hochberg 1995 JRSS-B](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x)

## How to start

1. Baseline:
   ```bash
   pytest --cov=v4.lib.multitest_correction --cov-report=term-missing v4/tests/
   ```
2. Hand-compute BH-adjusted p-values for a small example (e.g. p-values `[0.01, 0.04, 0.03, 0.005]`, m=4) and assert the implementation matches the textbook answer.
3. Test corner cases: empty input, single value, all p=1, all p=0, NaN handling, tied p-values.
4. Compare against `statsmodels.stats.multitest.multipletests` as an oracle for property-based testing (use `hypothesis`).

## Definition of done

- [ ] Coverage ≥ 85 % for `multitest_correction.py`
- [ ] At least 1 property-based test using `hypothesis` matching statsmodels' BH/Bonferroni
- [ ] All edge cases above covered with explicit asserts
- [ ] CI green

## Difficulty

★★ (statistical reasoning + property-based testing)
