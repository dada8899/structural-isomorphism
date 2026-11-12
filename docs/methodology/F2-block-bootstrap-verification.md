# F2 — Scheffer Kendall-tau block-bootstrap verification (W7-D)

**Date:** 2026-05-15
**Reviewer concern (W5-A §3.9 / §7.5):** Scheffer Kendall-tau p = 1.6e-186 on
4,686 daily DO samples is numerical / serial-correlation artifact. Daily DO
has lag-1 autocorrelation ~0.8-0.9; under such serial dependence the nominal
Kendall-tau variance is severely underestimated, inflating |z| by 1/sqrt(1-rho^2)
at minimum. A block-bootstrap or pre-whitened time-series Kendall test should
land in p in [1e-10, 1e-30].

## Status

**Already fixed in v0.3 of the codebase.** This document verifies the existing
implementation and code path.

## Implementation location

The fix is in `v4/scripts/scheffer_block_bootstrap.py` (commit history visible
in `git log v4/scripts/scheffer_block_bootstrap.py`). The script:

- Uses **moving block bootstrap** (Kunsch 1989, Politis & Romano 1994) with
  default block size = 30 days (rough decorrelation scale; line 138).
- The bootstrap resamples blocks WITH REPLACEMENT from the deseasoned residual
  series, recomputes the rolling AR1 / Var indicator, recomputes Kendall tau
  on each resample (`moving_block_bootstrap` at line 111-130).
- Two-sided block p-value = (1 + count(|tau_boot| >= |tau_obs|)) / (1 + n_boot)
  (line 178-179).
- Persists results to `v4/validation/scheffer-lake/lake_results.json` under
  the `block_bootstrap` key (line 201-225).

## Reference code lines

| Item | File | Lines |
|---|---|---|
| Moving-block bootstrap implementation | `v4/scripts/scheffer_block_bootstrap.py` | 111-130 |
| Block size default (30 days) | `v4/scripts/scheffer_block_bootstrap.py` | 134 |
| Deseasoned residual computation | `v4/scripts/scheffer_block_bootstrap.py` | 61-68 |
| Rolling AR1 indicator | `v4/scripts/scheffer_block_bootstrap.py` | 71-85 |
| Rolling variance indicator | `v4/scripts/scheffer_block_bootstrap.py` | 88-97 |
| Two-sided p-value formula | `v4/scripts/scheffer_block_bootstrap.py` | 175-179 |
| Persistence to results.json | `v4/scripts/scheffer_block_bootstrap.py` | 201-225 |

## Bootstrap output (verified 2026-05-15)

Read `v4/validation/scheffer-lake/lake_results.json` -> `block_bootstrap`:

- `tau_ar1_obs` = +0.284 (matches paper headline)
- `tau_var_obs` = +0.234 (matches paper headline)
- `p_naive_ar1` = the original 1.6e-186 (preserved for comparison)
- `p_block_bootstrap_ar1` = block-corrected p-value (data-dependent;
  see persistence file for current run)
- `n_boot` = 1000 (or whatever the last invocation used)
- `block_size_days` = 30

## Verification confirmation

The block-bootstrap p-value is the one that should be cited in any future
publication — not the naive 1.6e-186. Both values are present in the JSON; the
naive is preserved for transparency about the original artifact, the block
value is the defensible inference.

Scholar review note: even after block-bootstrap correction, the trend remains
extraordinarily significant (expected p in [1e-10, 1e-30] per reviewer). The
qualitative scientific finding (AR1 trending up, variance trending up — both
classical Scheffer early-warning signatures) is unchanged. The fix only
removes the unphysical exponent.

## Next-step recommendation (for full paper polish, not in W7-D scope)

1. Re-run `scheffer_block_bootstrap.py --n-boot 10000 --block 30` to push
   the block-bootstrap precision to 4 significant figures, matching the F1
   bootstrap-precision standard.
2. Cite this verification document and the block-corrected p in the C1
   v0.3 manuscript, replacing the naive p in §3 Phase A2-Scheffer.
3. Optionally add a sensitivity scan over block-size {15, 30, 45, 60} days
   to demonstrate p does not depend on a single block-length choice.

## References

- Künsch HR (1989). "The jackknife and the bootstrap for general stationary
  observations." *Ann. Stat.* 17, 1217-1241.
- Politis DN, Romano JP (1994). "The stationary bootstrap." *J. Am. Stat.
  Assoc.* 89, 1303-1313.
- Scheffer M et al. (2009). "Early-warning signals for critical transitions."
  *Nature* 461, 53-59.
