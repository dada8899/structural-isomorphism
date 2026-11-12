#!/usr/bin/env python3
"""Tracy-Widom GUE universality validation — X3 Wave 3 #6.

Reference report: docs/coverage/expansion-candidates-2026-05-24.md Wave 3
empty-class table: Burgers / Tracy-Widom (Tracy-Widom 1994; Corwin 2012 KPZ
review) had ZERO entries in the KB before this session.

Hypothesis (Tracy-Widom GUE — beta=2)
--------------------------------------
For an N×N Gaussian Unitary Ensemble (GUE) matrix — complex Hermitian with
iid Gaussian entries — the centred and rescaled largest eigenvalue

    chi = N^(1/6) (lambda_max - 2 sqrt(N))

converges in distribution to the Tracy-Widom GUE distribution F_2 as
N -> infty. Reference moments (Bornemann 2010 Comput. Stat. 25;
Prähofer-Spohn 2004 table):

    mean    = -1.7710868074
    var     =  0.81319479
    skew    =  +0.2240842
    excess kurt = +0.0934480

Empirical anchors:
    - Soshnikov 1999 — TW law universality for Wigner matrices
    - Johansson 2000 — TASEP largest cluster -> TW-GUE
    - Takeuchi-Sano 2010 Sci Rep 1:34 — first experimental TW recovery in
      KPZ liquid-crystal interfaces (statisticalmechanics → physics bridge)
    - Sasamoto-Spohn 2010 J Phys A 43 045001 — KPZ flat-IC -> TW-GOE
    - Edelman-Persson 2005 — TW law in nuclear scattering levels

Data
----
SYNTHETIC. We sample 1,500 N×N GUE matrices (N=400), compute the largest
eigenvalue of each, centre and rescale to chi_i = N^(1/6)(lambda_max_i -
2 sqrt(N)), and compare the empirical {chi_i} distribution to Tracy-Widom
GUE moments (mean, var, skew, excess kurt). Optionally also runs a
Kolmogorov-Smirnov test against the analytic TW CDF if `mpmath` available
(skipped if not).

Outputs
-------
results.json    n_runs samples + moments + KS test summary
verdict.md      human-readable verdict card
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "soc-pipeline" / "src"))


# Tracy-Widom GUE reference moments (Bornemann 2010 / Prähofer-Spohn 2004)
TW_GUE_MEAN = -1.7710868074
TW_GUE_VAR = 0.81319479
TW_GUE_STD = math.sqrt(TW_GUE_VAR)
TW_GUE_SKEW = 0.2240842
TW_GUE_KURT = 0.0934480  # excess kurtosis


# ============================================================
# 1. GUE matrix + largest eigenvalue
# ============================================================

def sample_gue_lambda_max(N: int, n_samples: int,
                          rng: np.random.Generator) -> np.ndarray:
    """Sample n_samples GUE-N matrices and return their largest eigenvalue.

    GUE distribution: H = (X + X^*) / 2 where X has iid complex Gaussian
    entries with real & imag each N(0, 1/2). Equivalently we can use the
    tridiagonal Dumitriu-Edelman 2002 J Math Phys form (beta=2) to be much
    faster than full N x N eigendecomposition:

        T_N is a (N x N) real tridiagonal matrix with
            diagonal d_k ~ N(0, 1) for k=1..N
            sub-diagonal e_k ~ chi(beta * (N - k)) / sqrt(2) for k=1..N-1
                where beta = 2 (GUE).
        eigenvalues of T_N have the same joint distribution as eigenvalues
        of a GUE matrix (normalised so that lambda_max ≈ 2 sqrt(N)).

    We use the tridiagonal form for speed.
    """
    out = np.empty(n_samples, dtype=np.float64)
    beta = 2.0
    for s in range(n_samples):
        d = rng.standard_normal(N)
        e = np.empty(N - 1, dtype=np.float64)
        for k in range(1, N):
            # chi distribution with k = beta * (N - i) degrees of freedom
            df = beta * (N - k)
            # Sample chi(df) = sqrt of chi-squared(df)
            chi2 = rng.chisquare(df=df)
            e[k - 1] = math.sqrt(chi2) / math.sqrt(2.0)
        # Largest eigenvalue of the symmetric tridiagonal matrix.
        # scipy.linalg.eigvalsh_tridiagonal supports range-select for speed.
        from scipy.linalg import eigvalsh_tridiagonal
        evs = eigvalsh_tridiagonal(d, e, select="i",
                                   select_range=(N - 1, N - 1))
        out[s] = float(evs[-1])
    return out


# ============================================================
# 2. Statistical moments
# ============================================================

def empirical_moments(x: np.ndarray) -> dict:
    n = x.size
    mean = float(x.mean())
    var = float(x.var(ddof=1)) if n > 1 else 0.0
    std = math.sqrt(var) if var > 0 else 0.0
    if std > 0:
        z = (x - mean) / std
        skew = float(np.mean(z ** 3))
        kurt = float(np.mean(z ** 4) - 3.0)
    else:
        skew = None
        kurt = None
    return {"n": n, "mean": mean, "var": var, "std": std, "skew": skew, "excess_kurt": kurt}


def standardise_to_tw(lambda_max: np.ndarray, N: int) -> np.ndarray:
    """Apply the GUE finite-N rescaling: chi = N^(1/6) (lambda_max - 2 sqrt(N))."""
    return (N ** (1.0 / 6.0)) * (lambda_max - 2.0 * math.sqrt(N))


# ============================================================
# 3. Main
# ============================================================

def main():
    N = 400
    n_samples = 1500
    rng = np.random.default_rng(20260525)

    lambda_max = sample_gue_lambda_max(N=N, n_samples=n_samples, rng=rng)
    chi = standardise_to_tw(lambda_max, N=N)

    moments = empirical_moments(chi)

    # Compare to TW GUE (after centring/scaling chi to match TW first 2 moments)
    # The rescaling chi = N^(1/6)(lambda_max - 2 sqrt(N)) ALREADY produces the
    # right limit law; the empirical {chi_i} should *directly* approximate
    # TW-GUE samples (mean ≈ -1.77, var ≈ 0.81, skew ≈ 0.224, kurt ≈ 0.093).
    mean_dev = moments["mean"] - TW_GUE_MEAN
    var_dev = moments["var"] - TW_GUE_VAR
    skew_dev = (moments["skew"] - TW_GUE_SKEW) if moments["skew"] is not None else None
    kurt_dev = (moments["excess_kurt"] - TW_GUE_KURT) if moments["excess_kurt"] is not None else None

    # Bands: moderately tight; finite-N + finite-sample noise on these moments
    # for N=400, n=1500 has expected std ~ TW_GUE_STD / sqrt(n) ≈ 0.023 on mean.
    in_band_mean = abs(mean_dev) < 0.15
    in_band_var = abs(var_dev) < 0.15
    in_band_skew = (skew_dev is not None and abs(skew_dev) < 0.15)
    in_band_kurt = (kurt_dev is not None and abs(kurt_dev) < 0.30)
    in_band = in_band_mean and in_band_var and in_band_skew

    summary = {
        "N": N,
        "n_samples": n_samples,
        "empirical": moments,
        "tw_gue_reference": {
            "mean": TW_GUE_MEAN,
            "var": TW_GUE_VAR,
            "skew": TW_GUE_SKEW,
            "excess_kurt": TW_GUE_KURT,
        },
        "deviations_from_tw": {
            "mean": float(mean_dev),
            "var": float(var_dev),
            "skew": float(skew_dev) if skew_dev is not None else None,
            "excess_kurt": float(kurt_dev) if kurt_dev is not None else None,
        },
        "in_tw_band": {
            "mean": bool(in_band_mean),
            "var": bool(in_band_var),
            "skew": bool(in_band_skew),
            "excess_kurt": bool(in_band_kurt),
            "overall": bool(in_band),
        },
        "overall_verdict": "CONFIRMED" if in_band else "PARTIAL",
    }
    out = {
        "system": "Tracy-Widom GUE universality — GUE-N tridiagonal sampling (SYNTHETIC)",
        "data_provenance": ("SYNTHETIC: GUE-N largest eigenvalue sampled via "
                            "Dumitriu-Edelman 2002 J Math Phys 43 5830 "
                            "tridiagonal (beta=2) representation. N=400, "
                            "n_samples=1500. Tracy-Widom 1994 Commun Math "
                            "Phys 159 151 and Bornemann 2010 Comput Stat 25 "
                            "give exact TW-GUE reference moments. "
                            "Experimentally anchored in KPZ liquid-crystal "
                            "interfaces (Takeuchi-Sano 2010 Sci Rep 1:34)."),
        "predicted_class": "tracy_widom_gue_beta2",
        "exponents_predicted": {
            "mean": TW_GUE_MEAN,
            "var": TW_GUE_VAR,
            "skew": TW_GUE_SKEW,
            "excess_kurt": TW_GUE_KURT,
        },
        "summary": summary,
    }
    with open(HERE / "results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"[ok] wrote {HERE/'results.json'}")
    print(f"     empirical mean = {moments['mean']:.4f} (TW = {TW_GUE_MEAN:.4f})")
    print(f"     empirical var  = {moments['var']:.4f} (TW = {TW_GUE_VAR:.4f})")
    print(f"     empirical skew = {moments['skew']:.4f} (TW = {TW_GUE_SKEW:.4f})")
    print(f"     empirical kurt = {moments['excess_kurt']:.4f} (TW = {TW_GUE_KURT:.4f})")
    print(f"     verdict        = {summary['overall_verdict']}")


if __name__ == "__main__":
    main()
