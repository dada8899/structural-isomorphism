# [performance] Speed up Clauset `xmin` scan in `fit_clauset_powerlaw`

## What

Profile `soc_pipeline.fit_clauset_powerlaw` (in `packages/soc-pipeline/src/soc_pipeline/fit.py`) on a 100k-element input, identify the slowest step (almost certainly the `xmin` candidate scan that computes a KS distance per candidate), and implement caching or vectorization that gives a ≥ 3× speedup. Demonstrate the speedup with a `pytest-benchmark` test.

## Why

Validating our largest catalogs (Wikipedia views, GitHub stars, neural avalanches with >100k events) takes minutes per dataset. A 3× speedup would let us run the whole 21-system battery in under 2 minutes — making CI green within a reasonable wall-time budget.

## Where

- Target file: `packages/soc-pipeline/src/soc_pipeline/fit.py`
- Hot function: the inner loop that scans candidate `xmin` values and computes KS distance for each
- Benchmark home: `packages/soc-pipeline/tests/benchmarks/test_fit_speed.py` (new)

## How to start

1. Profile a baseline:
   ```python
   import cProfile, pstats, numpy as np
   from soc_pipeline import fit_clauset_powerlaw
   data = np.random.pareto(2.5, 100_000) + 1
   cProfile.run("fit_clauset_powerlaw(data)", "fit.prof")
   pstats.Stats("fit.prof").sort_stats("cumulative").print_stats(20)
   ```
2. Confirm the bottleneck is the `xmin` scan. Likely fixes:
   - Pre-sort the array once and reuse
   - Vectorize the KS-distance computation across candidate `xmin` values with numpy broadcasting
   - Cache `log(x)` for the MLE inner sum
   - Skip every-k-th candidate xmin when n > 10k (with a flag, default off)
3. Pin the regression: add `pytest-benchmark` test asserting `fit_time < baseline / 3` on a 100k Pareto.

## Definition of done

- [ ] ≥ 3× speedup on a 100k Pareto input, measured via pytest-benchmark
- [ ] Existing tests in `packages/soc-pipeline/tests/` still pass (correctness preserved)
- [ ] PR description includes before/after profile screenshots or text dumps
- [ ] No new dependencies (or if numba/cython is needed, gate it behind an optional extras_require)

## Difficulty

★★★ (profiling + careful vectorization; tricky to keep numerical correctness)
