# Verdict — Tracy-Widom GUE (β=2) Universality

> **Date.** 2026-05-25
> **System.** GUE-N largest eigenvalue (N=400, n_samples=1500).
> **Class.** `tracy_widom_gue_beta2`
> **Data provenance.** SYNTHETIC (Dumitriu-Edelman tridiagonal sampling).
> **Reference moments (Bornemann 2010 / Prähofer-Spohn 2004):**
>   - mean = −1.7711
>   - var  = 0.8132
>   - skew = +0.2241
>   - excess kurt = +0.0934

## Recovered moments

| Quantity | TW-GUE reference | Empirical (N=400, n=1500) | Deviation | In band? |
|---|---|---|---|---|
| mean | −1.7711 | **−1.7594** | +0.0117 | yes (band ±0.15) |
| var | 0.8132 | **0.8360** | +0.0228 | yes (band ±0.15) |
| skew | +0.2241 | **+0.2695** | +0.0454 | yes (band ±0.15) |
| excess kurt | +0.0934 | +0.1917 | +0.098 | borderline (band ±0.30) |

**Verdict: CONFIRMED.** All four moments align with Tracy-Widom GUE
within the predicted bands (kurt is the noisiest higher-moment but
still in band).

## Method

For each of 1500 samples we generate the Dumitriu-Edelman 2002
J Math Phys 43 5830 tridiagonal representation of GUE-N (β=2):

```
T_N is N×N symmetric tridiagonal:
  d_k     ~ N(0, 1)            (diagonal, k=1..N)
  e_k     ~ chi(2(N - k)) / √2 (sub-diagonal, k=1..N-1)
```

Its eigenvalues have the same joint law as those of a true GUE matrix,
but the tridiagonal form allows O(N) largest-eigenvalue extraction via
`scipy.linalg.eigvalsh_tridiagonal(select='i')`, ~100× faster than
direct N×N eigendecomp.

The largest eigenvalue λ_max is then rescaled

    χ = N^(1/6) · (λ_max − 2 √N)

which under N → ∞ converges in distribution to Tracy-Widom GUE F_2.

## Why this matters

Tracy-Widom is the **universal** distribution for largest fluctuations
in:
- KPZ growth interface tip height (Sasamoto-Spohn 2010)
- TASEP largest cluster (Johansson 2000)
- Nuclear scattering level spacings (Edelman-Persson 2005)
- Liquid-crystal turbulent KPZ fronts (Takeuchi-Sano 2010 Sci Rep 1:34
  — first experimental TW recovery)
- Financial correlation matrices (Laloux-Cizeau-Bouchaud-Potters 1999)

This Wave-3 entry adds TW universality to the KB, which together with
the KPZ entry forms the KPZ ⇄ TW bridge.
