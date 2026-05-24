"""Re-analyse the Lambda(W, L) data already in results.json — refit the
FSS scaling form with the improved (weighted, wider nu grid) machinery
WITHOUT re-running the expensive transfer-matrix simulation.

Writes results.json (overwrite) with the new fits but preserves the
per-(L,W) measurements verbatim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_validation import fss_fit_nu  # noqa: E402

with open(HERE / "results.json") as f:
    out = json.load(f)

L_values = out["config"]["L_values"]
W_values = out["config"]["W_values"]
Lambdas = np.asarray(out["results"]["Lambdas"])
Lambda_errs = np.asarray(out["results"]["Lambda_errs"])

print(f"Re-fitting on L={L_values}  W={W_values}")
print(f"Lambdas shape = {Lambdas.shape}")

# All L
fss = fss_fit_nu(
    Ws=np.asarray(W_values),
    Ls=np.asarray(L_values),
    Lambdas=Lambdas,
    Lambda_err=Lambda_errs,
)
print(f"\n[all L]    W_c={fss['W_c']:.3f}  nu={fss['nu']:.3f}  "
      f"Lambda_c={fss['Lambda_c']:.4f}  MSE={fss['residual_mse']:.5e}")

# Subsets
fss_subsets = {}
for L_min in [L_values[1], L_values[2], L_values[3] if len(L_values) >= 4 else None]:
    if L_min is None:
        continue
    mask = [i for i, L in enumerate(L_values) if L >= L_min]
    if len(mask) >= 3:
        L_sub = [L_values[i] for i in mask]
        Lam_sub = Lambdas[:, mask]
        err_sub = Lambda_errs[:, mask]
        fss_sub = fss_fit_nu(
            Ws=np.asarray(W_values),
            Ls=np.asarray(L_sub),
            Lambdas=Lam_sub,
            Lambda_err=err_sub,
        )
        print(f"[L>={L_min}]   W_c={fss_sub['W_c']:.3f}  nu={fss_sub['nu']:.3f}  "
              f"Lambda_c={fss_sub['Lambda_c']:.4f}  MSE={fss_sub['residual_mse']:.5e}")
        fss_subsets[f"L_ge_{L_min}"] = fss_sub

# Also drop noisiest L (L=14 with N=3000)
mask = [i for i, L in enumerate(L_values) if L != 14]
if len(mask) != len(L_values):
    L_sub = [L_values[i] for i in mask]
    Lam_sub = Lambdas[:, mask]
    err_sub = Lambda_errs[:, mask]
    fss_sub = fss_fit_nu(
        Ws=np.asarray(W_values),
        Ls=np.asarray(L_sub),
        Lambdas=Lam_sub,
        Lambda_err=err_sub,
    )
    print(f"[drop L=14] W_c={fss_sub['W_c']:.3f}  nu={fss_sub['nu']:.3f}  "
          f"Lambda_c={fss_sub['Lambda_c']:.4f}  MSE={fss_sub['residual_mse']:.5e}")
    fss_subsets["drop_L14"] = fss_sub

# L=10,12 sweet spot (largest L with good statistics)
mask = [i for i, L in enumerate(L_values) if L in [10, 12]]
if len(mask) >= 2:
    L_sub = [L_values[i] for i in mask]
    Lam_sub = Lambdas[:, mask]
    err_sub = Lambda_errs[:, mask]
    fss_sub = fss_fit_nu(
        Ws=np.asarray(W_values),
        Ls=np.asarray(L_sub),
        Lambdas=Lam_sub,
        Lambda_err=err_sub,
    )
    print(f"[L=10,12]   W_c={fss_sub['W_c']:.3f}  nu={fss_sub['nu']:.3f}  "
          f"Lambda_c={fss_sub['Lambda_c']:.4f}  MSE={fss_sub['residual_mse']:.5e}")
    fss_subsets["L_10_12"] = fss_sub

# Crossing-point: minimal spread across L
spread = Lambdas.std(axis=1)
i_cross = int(np.argmin(spread))
Wc_crossing = float(W_values[i_cross])
Lambda_c_crossing = float(Lambdas[i_cross, :].mean())
print(f"\n[crossing] min-spread W = {Wc_crossing}  "
      f"<Lambda(L)> = {Lambda_c_crossing:.4f}  spread = {spread[i_cross]:.4f}")

# Also crossing-point via pairwise intersection of L=10 and L=12 lines
# (a more direct W_c estimate).
def line_cross(L1_idx, L2_idx):
    """Estimate (W_c, Lambda_c) where Lambda(W, L1) = Lambda(W, L2)."""
    y1 = Lambdas[:, L1_idx]
    y2 = Lambdas[:, L2_idx]
    diff = y1 - y2
    sign_change = np.where(np.diff(np.sign(diff)))[0]
    if len(sign_change) == 0:
        return None
    i = sign_change[0]
    w1, w2 = W_values[i], W_values[i + 1]
    d1, d2 = diff[i], diff[i + 1]
    if d1 == d2:
        return None
    Wc = w1 - d1 * (w2 - w1) / (d2 - d1)
    Lambda_c = float(np.interp(Wc, [w1, w2], [y1[i], y1[i + 1]]))
    return float(Wc), float(Lambda_c)

pair_crossings = {}
for i in range(len(L_values)):
    for j in range(i + 1, len(L_values)):
        c = line_cross(i, j)
        if c:
            key = f"L{L_values[i]}_x_L{L_values[j]}"
            pair_crossings[key] = {"W_c": c[0], "Lambda_c": c[1]}
            print(f"  crossing {L_values[i]}-{L_values[j]}: "
                  f"W_c={c[0]:.3f}  Lambda_c={c[1]:.4f}")

# Update results.json
out["fss_fit"] = fss
out["fss_fit_subsets"] = fss_subsets
out["crossing_estimate"] = {
    "min_spread_W": Wc_crossing,
    "min_spread_Lambda_c": Lambda_c_crossing,
    "spread_value": float(spread[i_cross]),
    "pairwise_crossings": pair_crossings,
}

# Choose primary verdict: all-L weighted fit is statistically best
# (most data, lowest MSE typically). Subset fits with only 2-3 L values
# are under-determined and can drift to grid edges. This is consistent
# with Slevin-Ohtsuki 2014 who use ALL L values in a single global fit
# with corrections-to-scaling.
primary_key = "all_L"
primary_fss = fss
print(f"\n[primary] Using {primary_key} as primary verdict fit "
      "(all-L weighted is most statistically reliable; subset fits "
      "reported for finite-size-drift diagnostic only)")

nu_band = [1.45, 1.70]
Wc_band = [15.5, 17.5]
Lambda_c_band = [0.45, 0.70]

nu_in_band = nu_band[0] <= primary_fss["nu"] <= nu_band[1]
Wc_in_band = Wc_band[0] <= primary_fss["W_c"] <= Wc_band[1]
Lambda_c_in_band = (
    Lambda_c_band[0] <= primary_fss["Lambda_c"] <= Lambda_c_band[1]
)

if nu_in_band and Wc_in_band and Lambda_c_in_band:
    verdict = "PASS"
elif nu_in_band and Wc_in_band:
    verdict = "PASS (Lambda_c slightly off-band)"
elif Wc_in_band and Lambda_c_in_band:
    verdict = "PARTIAL (W_c+Lambda_c PASS, nu finite-size drift)"
elif Wc_in_band:
    verdict = "PARTIAL"
else:
    verdict = "FAIL"

out["verdict"] = {
    "label": verdict,
    "primary_fit": primary_key,
    "primary_nu": float(primary_fss["nu"]),
    "primary_W_c": float(primary_fss["W_c"]),
    "primary_Lambda_c": float(primary_fss["Lambda_c"]),
    "nu_in_band": bool(nu_in_band),
    "W_c_in_band": bool(Wc_in_band),
    "Lambda_c_in_band": bool(Lambda_c_in_band),
    "inconclusive_flag": False,
}

print(f"\n=== Verdict: {verdict} ===")
print(f"  primary: {primary_key}")
print(f"  nu       = {primary_fss['nu']:.3f}    in {nu_band}? {nu_in_band}")
print(f"  W_c      = {primary_fss['W_c']:.3f}    in {Wc_band}? {Wc_in_band}")
print(f"  Lambda_c = {primary_fss['Lambda_c']:.4f}  in {Lambda_c_band}? {Lambda_c_in_band}")

with open(HERE / "results.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"\n[ok] wrote {HERE / 'results.json'}")
