#!/usr/bin/env python3
"""KPZ universality class validation — X3 Wave 3 (empty-class entry #1).

Reference report: docs/coverage/expansion-candidates-2026-05-24.md Wave 3
empty-class table: KPZ (Kardar-Parisi-Zhang 1986) had ZERO entries in the KB
before this session.

Hypothesis (KPZ 1+1d universality class)
-----------------------------------------
For a self-affine 1+1d growing interface h(x, t),

    W(L, t) := sqrt(<(h - <h>_x)^2>_x)

obeys Family-Vicsek scaling W(L, t) = L^alpha f(t / L^z) with KPZ exponents

    alpha = 1/2       (roughness)
    beta  = 1/3       (growth)
    z     = alpha/beta = 3/2

Empirical anchor: Maunuksela 1997 (paper-burn), Pastor 1992 (electrodep.),
Bonachela 2011 (bacterial colonies), Takeuchi-Sano 2010 Sci Rep (LC turbulent
fronts). Theory: Kardar-Parisi-Zhang 1986 PRL 56 889.

Data
----
SYNTHETIC. Kim-Kosterlitz 1989 (PRL 62 2289) Restricted Solid-on-Solid (RSOS)
single-step model on a 1D periodic lattice — the canonical lattice realisation
of KPZ universality. Rule: pick a site, attempt h -> h+1; accept iff
|h_new - h_NN| <= 1 on both neighbours. Parallel even/odd sub-lattice update.

Why synthetic is acceptable here:
  KPZ exponents are universal across all members of the class; recovering
  alpha=1/2, beta=1/3 on RSOS is the same claim as recovering them on
  paper-burn / LC fronts. Lab data sources are not openly archived.

Outputs
-------
results.json
verdict.md
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


# ============================================================
# 1. RSOS (single-step) growth — vectorised sub-lattice update
# ============================================================

def rsos_grow(L: int, n_mono: int, rng: np.random.Generator, n_snap: int = 80):
    """KK RSOS growth on periodic 1D lattice; logarithmic snapshots.

    Returns (times: (T,) ndarray of monolayer-equivalent timestamps,
             widths: (T,) ndarray of W(t),
             h_final: (L,) ndarray)
    """
    h = np.zeros(L, dtype=np.int64)
    snap_steps = np.unique(np.clip(
        np.round(np.logspace(0, math.log10(max(n_mono, 2)), n_snap)).astype(int),
        1, n_mono,
    ))
    snap_set = set(snap_steps.tolist())
    times = []
    widths = []

    even = np.arange(0, L, 2)
    odd = np.arange(1, L, 2)

    for step in range(1, n_mono + 1):
        for sub in (even, odd):
            tries = rng.random(sub.size) < 0.5
            if not tries.any():
                continue
            sites = sub[tries]
            left = (sites - 1) % L
            right = (sites + 1) % L
            cond = (h[sites] + 1 - h[left] <= 1) & (h[sites] + 1 - h[right] <= 1)
            h[sites[cond]] += 1
        if step in snap_set:
            times.append(float(step))
            widths.append(float(np.sqrt(np.mean((h - h.mean()) ** 2))))
    return np.asarray(times), np.asarray(widths), h


# ============================================================
# 2. Log-log slope fit
# ============================================================

def fit_loglog(x: np.ndarray, y: np.ndarray) -> dict:
    mask = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 4:
        return {"slope": None, "intercept": None, "r2": None, "n": int(mask.sum())}
    xl = np.log10(x[mask])
    yl = np.log10(y[mask])
    slope, intercept = np.polyfit(xl, yl, 1)
    yhat = slope * xl + intercept
    ss_res = float(np.sum((yl - yhat) ** 2))
    ss_tot = float(np.sum((yl - yl.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"slope": float(slope), "intercept": float(intercept),
            "r2": float(r2), "n": int(mask.sum())}


# ============================================================
# 3. Tracy-Widom GUE reference moments
# ============================================================

TW_GUE_MEAN = -1.7710868074
TW_GUE_VAR = 0.81319479
TW_GUE_SKEW = 0.2240842
TW_GUE_KURT = 0.0934480


# ============================================================
# 4. Main: ensemble-averaged Family-Vicsek
# ============================================================

def main():
    # System sizes and seeds — RSOS saturates ~ L^z = L^1.5 monolayers.
    # We run ~12*L^1.5 monolayers and average W^2 across n_seed seeds before
    # taking log-slope. This is the canonical ensemble approach
    # (Family-Vicsek 1985; Barabási-Stanley 1995 §6).
    L_values = [64, 128, 256, 512]
    n_seed = 8
    seed_base = 20260525

    per_L_aggregate = {}
    per_L_final_h = {L: [] for L in L_values}
    for L in L_values:
        n_mono = int(round(12.0 * L ** 1.5))
        # Need a common time-grid; use logarithmic schedule per L.
        time_grid = None
        w_sq_runs = []
        for s in range(n_seed):
            rng = np.random.default_rng(seed_base + 17 * L + s)
            t, w, h_final = rsos_grow(L, n_mono, rng=rng)
            if time_grid is None:
                time_grid = t
            else:
                # Different seeds yield same snap schedule (deterministic logspace)
                assert np.allclose(t, time_grid), "snapshot schedule drift"
            w_sq_runs.append(w ** 2)
            per_L_final_h[L].append(h_final)
        w_sq_mean = np.mean(np.asarray(w_sq_runs), axis=0)
        w_mean = np.sqrt(w_sq_mean)

        # Growth-regime fit: t in [20, ~ 0.05 * L^z] avoids early-time noise floor
        # and pre-saturation crossover.
        t_lo = 20.0
        t_sat = float(L) ** 1.5
        t_hi = 0.05 * t_sat
        mask = (time_grid >= t_lo) & (time_grid <= t_hi)
        if mask.sum() < 5:
            mask = (time_grid >= 10.0) & (time_grid <= 0.1 * t_sat)
        growth_fit = fit_loglog(time_grid[mask], w_mean[mask])

        sat_mask = time_grid >= 0.7 * time_grid.max()
        w_sat = float(np.mean(w_mean[sat_mask])) if sat_mask.sum() else float(w_mean[-1])

        per_L_aggregate[L] = {
            "L": L, "n_mono": n_mono, "n_seed": n_seed,
            "growth_slope": growth_fit,
            "w_sat": w_sat,
            "n_snap": int(time_grid.size),
        }

    # alpha fit across L
    Lvals = np.asarray(list(per_L_aggregate.keys()), dtype=float)
    Wsats = np.asarray([per_L_aggregate[L]["w_sat"] for L in per_L_aggregate], dtype=float)
    alpha_fit = fit_loglog(Lvals, Wsats)

    # beta fit: average of growth slopes for largest 2 sizes (cleanest window)
    L_largest = list(per_L_aggregate.keys())[-2:]
    beta_vals = [per_L_aggregate[L]["growth_slope"]["slope"]
                 for L in L_largest
                 if per_L_aggregate[L]["growth_slope"]["slope"] is not None]
    beta_mean = float(np.mean(beta_vals)) if beta_vals else None
    z_est = (alpha_fit["slope"] / beta_mean
             if alpha_fit["slope"] is not None and beta_mean else None)

    # Tracy-Widom proxy on largest-L final heights
    # Use the centred max height across seeds as the TW-like statistic
    largest = max(L_values)
    h_runs = per_L_final_h[largest]
    centred_max = np.array([h.max() - h.mean() for h in h_runs])
    if centred_max.std() > 0:
        z = (centred_max - centred_max.mean()) / centred_max.std()
        tw_skew = float(np.mean(z ** 3))
        tw_kurt = float(np.mean(z ** 4) - 3.0)
    else:
        tw_skew = None
        tw_kurt = None

    in_band = (
        alpha_fit["slope"] is not None and 0.40 <= alpha_fit["slope"] <= 0.65
        and beta_mean is not None and 0.27 <= beta_mean <= 0.40
    )

    summary = {
        "n_seeds_per_L": n_seed,
        "alpha_fit": alpha_fit,
        "beta_mean_largest2": beta_mean,
        "z_estimate": z_est,
        "alpha_predicted": 0.5,
        "beta_predicted": 1.0 / 3.0,
        "z_predicted": 1.5,
        "alpha_band": [0.40, 0.65],
        "beta_band": [0.27, 0.40],
        "in_kpz_band": bool(in_band),
        "tracy_widom_compare": {
            "n_seeds": int(len(h_runs)),
            "kpz_centred_max_skew": tw_skew,
            "kpz_centred_max_excess_kurt": tw_kurt,
            "tw_gue_skew": TW_GUE_SKEW,
            "tw_gue_excess_kurt": TW_GUE_KURT,
            "note": ("Skewness of centred max-height across n_seeds samples "
                     "is a qualitative TW proxy; rigorous TW-GOE recovery for "
                     "flat-IC KPZ needs >=1000 seeds (Sasamoto-Spohn 2010)."),
        },
        "overall_verdict": "CONFIRMED" if in_band else "PARTIAL",
    }

    out = {
        "system": "KPZ universality class — Kim-Kosterlitz RSOS (SYNTHETIC)",
        "data_provenance": ("SYNTHETIC: 1+1d Kim-Kosterlitz RSOS (KK 1989 "
                            "PRL 62 2289). RSOS in KPZ universality class; "
                            "same alpha=1/2, beta=1/3 as paper-burn fronts "
                            "(Maunuksela 1997 PRL 79 1515), liquid-crystal "
                            "turbulent fronts (Takeuchi-Sano 2010 Sci Rep "
                            "1:34), bacterial colony edges (Bonachela 2011 "
                            "J Theor Biol 269 251). 8 seeds per L, "
                            "ensemble-averaged W^2(L,t)."),
        "predicted_class": "kpz_1plus1d_growth",
        "exponents_predicted": {"alpha": 0.5, "beta": 1.0/3.0, "z": 1.5},
        "per_L": list(per_L_aggregate.values()),
        "summary": summary,
    }

    with open(HERE / "results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"[ok] wrote {HERE/'results.json'}")
    print(f"     alpha = {alpha_fit['slope']:.3f}  (predicted 0.500)")
    print(f"     beta  = {beta_mean:.3f}  (predicted 0.333)" if beta_mean else "     beta = None")
    print(f"     z     = {z_est:.3f}  (predicted 1.500)" if z_est else "     z = None")
    print(f"     verdict = {summary['overall_verdict']}")


if __name__ == "__main__":
    main()
