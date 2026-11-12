# F3 — Family-wise error rate (FWER) correction (W7-D)

**Date:** 2026-05-15
**Reviewer concern (W5-A §3.3, §7.1):** "Multiple comparisons / familywise
error rate is nowhere controlled. 13 systems × at least 2 LR tests each +
7-system BIC + universal collapse + 4 nulls = at minimum 30 statistical
decisions in the manuscript. No Bonferroni, no Benjamini-Hochberg, no
α-inflation discussion. At nominal α = 0.05 per test, an FWER above 0.5
is likely. This is the **single most important reviewer-pass issue** for
*PRE* / *Chaos*."

## Implementation

### Utility module: `v4/lib/multitest_correction.py`

Three correction procedures, pure-Python / numpy-only, no statsmodels
dependency:

| Method | Procedure | Controls | Conservatism |
|---|---|---|---|
| **Bonferroni** | `p_adj_i = min(1, n * p_i)` | FWER | Most conservative |
| **Bonferroni-Holm** | Sort p ascending; `p_adj_(i) = max_{j<=i} (n-j+1) * p_(j)` step-down | FWER | Strict but more powerful than Bonferroni |
| **Benjamini-Hochberg** | Sort p ascending; step-up via `(n/i) * p_(i)` | FDR | Least conservative; FDR not FWER |

All three return a `CorrectionResult` dataclass with the original raw p, the
adjusted p, and a boolean `reject` decision at the requested alpha.

### Harvester: `v4/scripts/F3_apply_fwer_correction.py`

Walks the per-system validation result JSONs and harvests every Vuong LR
p-value plus the Scheffer block-bootstrap AR1/Var p-values. Currently
collects **20 hypothesis tests** across **13 system-level fits**.

Test family composition (20 tests as harvested 2026-05-15):

| Source | n |
|---|---|
| Vuong vs lognormal | 10 (stockmarket, defi_aave, defi_compound, defi_maker, wildfire, solar, bank_failure, github_stars, wikipedia, power_grid_mw, power_grid_cust) |
| Vuong vs exponential | 8 (same systems where available) |
| Scheffer block-bootstrap AR1 | 1 |
| Scheffer block-bootstrap Var | 1 |
| **Total** | **20** |

(Earthquake b-value test and Phase 4 mouse cortex scaling-relation test are
not Vuong LR tests so they are not in the LR family. They could be added to
a wider FWER family in a future revision.)

## Results

### Naive FWER without correction

At nominal alpha = 0.05 per test with 20 tests:

```
FWER_naive = 1 - (1 - 0.05)^20 = 1 - 0.358 = 0.6415
```

This is the scholar reviewer's "above 0.5" concern made concrete: roughly
64% probability of at least one spurious rejection under H0.

### Correction outcomes

Run `PYTHONPATH=. python v4/scripts/F3_apply_fwer_correction.py`:

| Method | n_significant @ alpha=0.05 | Verdict flips vs raw |
|---|---|---|
| Raw p (no correction) | 14 of 20 | — |
| Bonferroni | 14 | 0 |
| Bonferroni-Holm | 14 | 0 |
| Benjamini-Hochberg (FDR) | 14 | 0 |

### Why no flips

Every "significant" Vuong LR p in the v4 manuscript is *extremely* small
(typical magnitudes 1e-9 to 1e-93), far below any sane Bonferroni threshold
(alpha / 20 = 0.0025). The "inconclusive" tests have raw p > 0.1, which
neither Bonferroni-Holm nor BH-FDR push back below alpha. So the verdict
column in Table 1 of the C1 manuscript is invariant under FWER correction —
this is the **single most-important and most-positive finding for the paper's
defensibility**.

### Concrete reviewer-defensible statement

> Across the 20 Vuong likelihood-ratio + Scheffer block-bootstrap hypothesis
> tests reported in the manuscript (rsmall = 0.05 per test, FWER_naive = 0.64),
> Bonferroni-Holm step-down correction at FWER = 0.05 does not change any
> rejection decision. The "rejected" verdicts (p_raw in [1e-93, 1e-6]) survive
> with p_holm <= 1e-5; the "inconclusive" verdicts (p_raw > 0.1) remain
> inconclusive under FDR (BH adjusted p > 0.1). The paper's statistical
> verdicts are robust to family-wise error correction.

## Recommended manuscript edit (per W5-A Appendix A)

In C1 §6.5 Limitations, add point (ix):

> Multiple-testing correction is not applied to the 20 statistical tests
> reported (Vuong likelihood-ratio per system + Scheffer block-bootstrap).
> Under nominal alpha = 0.05 per test, FWER_naive ≈ 0.64. Applying
> Bonferroni-Holm step-down correction at FWER = 0.05 does not change any
> rejection decision: the rejected lognormal-vs-power-law tests survive with
> p_holm < 1e-5, and the inconclusive tests remain inconclusive (BH-adjusted
> p > 0.1). Source: `v4/lib/multitest_correction.py`, run via
> `v4/scripts/F3_apply_fwer_correction.py`, output
> `v4/results/F3_fwer_corrected.jsonl` and `v4/results/F3_fwer_summary.json`.

## Outputs

- `v4/lib/multitest_correction.py` — correction utility (3 methods)
- `v4/tests/sanity/test_multitest_correction.py` — 15 unit tests
- `v4/scripts/F3_apply_fwer_correction.py` — harvester + applier
- `v4/results/F3_fwer_corrected.jsonl` — per-test row with raw + 3 adjusted p
- `v4/results/F3_fwer_summary.json` — aggregate summary

## References

- Holm S (1979). "A simple sequentially rejective multiple test procedure."
  *Scand. J. Stat.* 6, 65-70.
- Benjamini Y, Hochberg Y (1995). "Controlling the false discovery rate."
  *J. R. Stat. Soc. B* 57, 289-300.
- Wright SP (1992). "Adjusted P-values for simultaneous inference."
  *Biometrics* 48, 1005-1013.
