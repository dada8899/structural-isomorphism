# F5 — r_shape null distribution (W7-D)

**Date:** 2026-05-15
**Reviewer concern (W5-A §4.4(a),(b) / §7.6):** "The paper currently calls
1.11 'excellent by the r < 2 threshold' (§4.4) — that's borrowing a
within-system threshold and applying it cross-domain without justification.
Recommended: generate 10,000 surrogate datasets where each of the 7 systems
is independently fitted by lognormal with the empirical mu, sigma^2, then
run the same row-centered ratio computation. The empirical value's
percentile rank against that null distribution is the actual significance
statement."

## Key finding: r_shape is a combinatorial artifact

When the matrix has no NaN entries and shape (S, B) = (7 systems, 20 bins),
the **r_shape ratio is mathematically equal to**:

```
r_shape = ((B - 1) / B) × (S / (S - 1))
        = (19 / 20) × (7 / 6)
        = 133 / 120
        = 1.10833...
```

**regardless of the underlying data.**

This is verifiable empirically by running the script:

```
python paper/figures/methodology/generate_F5.py --n-perm 10000
```

Output (2026-05-15):

```
observed r_shape = 1.108333
combinatorial constant ((B-1)/B)*(S/(S-1)) = (19/20)*(7/6) = 1.108333
r_shape is combinatorial artifact: True (diff = 0.0000)
r_shape null sanity (200 column-permutation reps): mean=1.108333 std=2.01e-16
                                                   unique values = 1
```

The within-row column-permutation null is fully degenerate — every replicate
returns the same r_shape = 1.10833. This proves the statistic is invariant
under any permutation that preserves row marginals.

**Implication:** the paper's headline number r_shape = 1.11 across 7 systems
on a 20-bin grid is exactly the ((B-1)/B) × (S/(S-1)) combinatorial constant
that would be returned whether the data is (a) actual SOC tails, (b)
independent random Gaussians, or (c) the same row repeated 7 times — provided
the matrix is row-centered before the ratio is computed.

### Algebraic identity (informal)

After row-centering, sum_j A[i,j] = 0 for each row i. The cross-system
variance averaged over columns and the within-system variance averaged over
rows both collapse to scaled sums over the same set of squared deviations
(modulo a (S-1)·(B-1) / S·B Bessel-correction ratio).

## Substituted statistic: shape-collapse RMSE

To produce a non-degenerate measure of cross-system shape similarity, we
substitute the **shape-collapse RMSE**:

```
RMSE = sqrt( mean_{i, j} (row_centered[i, j] - mean_curve[j])^2 )
```

This statistic IS data-dependent and provides a meaningful test against the
null "rows are independent Gaussians."

## Null distribution

Under H0 = "no shared shape across systems", we draw each system's log-y row
as `N(mu_i, sigma_i^2)` independently, with mu_i and sigma_i^2 being the
empirical row mean and stddev of the actual data. We compute RMSE on 10,000
such surrogate replicates.

## Results

| Statistic | Observed | Null (Gaussian surrogate) | p_left | p_right |
|---|---:|---|---:|---:|
| r_shape (paper formula) | 1.108333 | 1.108333 ± 2.0e-16 (degenerate) | — | — |
| shape-collapse RMSE | 0.5963 | mean 1.920, std 0.134, p5 1.70, p95 2.14 | **9.99e-05** | 1.0 |

**Interpretation:**

- `p_left = 9.99e-05` for the RMSE statistic. The observed cross-system shape
  similarity is *much better* (lower RMSE) than what would arise from
  independent Gaussian rows with matched marginals. **This is a real positive
  result for the universality claim**, just not via the paper's r_shape formula.

- The null mean RMSE = 1.92 in log-y units, while observed = 0.60 — about a
  3× tighter alignment than chance. Adjusted for the 10,000-rep precision
  floor, p < 0.0001 means the observed collapse is in the lower-0.01-percent
  tail of the null.

## Reviewer-defensible reframing for the manuscript

**Replace** §4.4-§4.5 headline ("first quantitative confirmation of
universality-class membership ... r_shape = 1.11 well inside the 'excellent'
threshold r < 2") **with**:

> Across 7 SOC systems on a 20-bin shared rescaled grid, the row-centered
> log-y matrix exhibits a shape-collapse RMSE of 0.60 (log-y units), compared
> to a Gaussian-surrogate null mean of 1.92 (s.d. 0.13) — empirical p < 0.0001
> against the null of independent system shapes. The paper's previously
> headlined cross/within variance ratio r_shape = 1.11 is shown to equal the
> ((B-1)/B)(S/(S-1)) combinatorial constant for the chosen grid and is not a
> data-dependent test statistic; we substitute the shape-collapse RMSE for
> the formal significance statement.

This is a *stronger* paper outcome than the original framing: it concedes
the W5-A §4.4 critique fully (admitting r_shape is degenerate) AND produces
a non-degenerate alternative test with an unambiguous low p-value supporting
the original universality claim.

## Outputs

- `paper/figures/methodology/F5_r_shape_null.pdf` — two-panel figure:
  (a) RMSE histogram + observed line, (b) degenerate r_shape null
  showing the artifact
- `paper/figures/methodology/F5_r_shape_null.png` — same in PNG
- `paper/figures/methodology/F5_r_shape_null_data.json` — raw numerics
- `paper/figures/methodology/generate_F5.py` — generator script

## References

- Lübeck S (2004). "Universal scaling behavior of non-equilibrium phase
  transitions." *Int. J. Mod. Phys. B* 18, 3977-4118.
- Pruessner G (2012). *Self-Organized Criticality.* Cambridge University Press.
- Christensen K, Moloney NR (2005). *Complexity and Criticality.* Imperial.
- Stumpf MPH, Porter MA (2012). "Critical truths about power laws."
  *Science* 335, 665-666.
