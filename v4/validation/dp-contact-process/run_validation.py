#!/usr/bin/env python3
"""Directed Percolation (DP) universality class validation — X3 Wave 3 #2.

Reference report: docs/coverage/expansion-candidates-2026-05-24.md Wave 3
empty-class table: DP (Directed Percolation, Hinrichsen 2000 review) had
ZERO entries in the KB before this session.

Hypothesis (DP universality class, 1+1d)
-----------------------------------------
At an absorbing-state phase transition with a single absorbing state and
short-range interactions (DP-conjecture, Janssen-Grassberger 1981), the
order-parameter density ρ(t) at criticality decays as

    ρ(t) ~ t^(-theta)        (asymptotic, t -> infty)

with the DP scaling exponent

    theta = beta / nu_||     # 1+1d DP: theta = 0.1595

Below criticality ρ(t) decays exponentially fast (extinction regime);
above criticality ρ(t) approaches a finite stationary value ρ_inf > 0.

Reference exponents (1+1d DP — Henkel-Hinrichsen-Lübeck 2008, Table 3.1)
    beta      = 0.276486   (order-parameter exponent)
    nu_||     = 1.733847   (temporal correlation length)
    nu_perp   = 1.096854   (spatial correlation length)
    theta     = beta/nu_|| = 0.159464
    z         = nu_||/nu_perp = 1.580745

Empirical anchor: Pomeau 1986 / Hof et al. 2008 (turbulent puff lifetime in
pipe flow; transition Reynolds # ~ 2040 from Avila et al. 2011 Science);
Take Eda-Hatano 2007 PRL (liquid-crystal turbulence DP transition);
Daviaud 2005 (Rayleigh-Bénard convection).

Data
----
SYNTHETIC. We use the **Domany-Kinzel (DK) cellular automaton** in
1+1d on a tilted lattice — the canonical discrete realisation of DP.
Site (i, t+1) becomes active with probability
    p_1  if exactly one of its two parents (i-1, t) and (i+1, t) is active
    p_2  if both parents are active.
The standard 1d DP transition lives at (p_1, p_2 = p_1*(2-p_1)),
specifically at p_1 = p_c = 0.7054 (DK 1984 J Phys A 17 L311) for the
'two-parent' line which lies in the DP universality class.

We run discrete-time CP at p_c on a periodic lattice and measure ρ(t).

Outputs
-------
results.json    per-seed ρ(t) decay slopes + ensemble theta estimate
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


# ============================================================
# 1. Domany-Kinzel 1+1d cellular automaton
# ============================================================

# DK 'one-parent' line: p_2 = p_1 (Wolfram-Rule-90-like; site polluted iff
# exactly one parent active OR both with prob p_1). Critical p_c = 0.7054.
# We use the simpler symmetric form: a site (i, t+1) is active iff
#   exactly one of (i-1, t), (i+1, t) is active with prob p   OR
#   both are active with prob q.
# For q = 2p - p^2 we recover bond DP and p_c ≈ 0.6447 (Grassberger 1979).

P_C_BOND_DP_1D = 0.6447  # bond DP critical probability, 1+1d

def dk_step(state: np.ndarray, p: float, q: float, rng: np.random.Generator) -> np.ndarray:
    L = state.size
    left = np.roll(state, 1)
    right = np.roll(state, -1)
    n_active_parents = left.astype(np.int8) + right.astype(np.int8)
    out = np.zeros(L, dtype=np.int8)
    one_mask = n_active_parents == 1
    two_mask = n_active_parents == 2
    if one_mask.any():
        r = rng.random(L)
        out[one_mask & (r < p)] = 1
    if two_mask.any():
        r = rng.random(L)
        out[two_mask & (r < q)] = 1
    return out


def simulate_cp(L: int, T: int, p: float, q: float | None,
                rng: np.random.Generator) -> np.ndarray:
    """Returns ρ(t) for t=0..T (uniform random IC, density=0.5)."""
    if q is None:
        q = 2.0 * p - p * p
    state = (rng.random(L) < 0.5).astype(np.int8)
    rho = np.empty(T + 1, dtype=np.float64)
    rho[0] = float(state.mean())
    for t in range(1, T + 1):
        state = dk_step(state, p, q, rng)
        rho[t] = float(state.mean())
        if rho[t] == 0.0:
            # absorbed; pad with zeros
            rho[t + 1:] = 0.0
            break
    return rho


# ============================================================
# 2. Log-log slope extractor
# ============================================================

def fit_loglog_window(t: np.ndarray, y: np.ndarray, t_lo: float, t_hi: float) -> dict:
    mask = (t >= t_lo) & (t <= t_hi) & (y > 0) & np.isfinite(y)
    if mask.sum() < 5:
        return {"slope": None, "intercept": None, "r2": None,
                "n": int(mask.sum()), "window": [t_lo, t_hi]}
    xl = np.log10(t[mask])
    yl = np.log10(y[mask])
    slope, intercept = np.polyfit(xl, yl, 1)
    yhat = slope * xl + intercept
    ss_res = float(np.sum((yl - yhat) ** 2))
    ss_tot = float(np.sum((yl - yl.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"slope": float(slope), "intercept": float(intercept),
            "r2": float(r2), "n": int(mask.sum()),
            "window": [t_lo, t_hi]}


# ============================================================
# 3. Main
# ============================================================

THETA_DP_1D = 0.159464  # exact 1+1d DP value
BETA_DP_1D = 0.276486
NU_PARA_DP_1D = 1.733847


def main():
    L = 4096
    T = 1000
    n_seed = 12
    p_lo = 0.62      # below criticality (exponential decay expected)
    p_c = P_C_BOND_DP_1D
    p_hi = 0.67      # above criticality (saturates to finite ρ_inf)

    times = np.arange(T + 1, dtype=float)

    results_per_p = {}
    for label, p_val in [("below", p_lo), ("critical", p_c), ("above", p_hi)]:
        rho_runs = []
        for s in range(n_seed):
            rng = np.random.default_rng(20260525 + 101 * s + int(p_val * 1e6))
            rho = simulate_cp(L=L, T=T, p=p_val, q=None, rng=rng)
            rho_runs.append(rho)
        rho_mean = np.mean(np.asarray(rho_runs), axis=0)

        # Power-law fit on critical-decay regime t ∈ [50, 800]
        crit_fit = fit_loglog_window(times, rho_mean, 50.0, 800.0)
        # Final ρ (last 100 timesteps) for above-critical saturation check
        rho_late = float(np.mean(rho_mean[-100:]))
        results_per_p[label] = {
            "p": p_val,
            "n_seed": n_seed,
            "L": L,
            "T": T,
            "rho_late": rho_late,
            "rho_t_initial": float(rho_mean[0]),
            "rho_t_50": float(rho_mean[50]) if T >= 50 else None,
            "rho_t_T": float(rho_mean[T]),
            "loglog_fit_50_800": crit_fit,
        }

    crit = results_per_p["critical"]
    theta_meas = -crit["loglog_fit_50_800"]["slope"] if crit["loglog_fit_50_800"]["slope"] is not None else None

    in_band = (theta_meas is not None and 0.12 <= theta_meas <= 0.20)

    summary = {
        "theta_measured": theta_meas,
        "theta_predicted": THETA_DP_1D,
        "theta_band": [0.12, 0.20],
        "beta_predicted": BETA_DP_1D,
        "nu_parallel_predicted": NU_PARA_DP_1D,
        "p_c_used": P_C_BOND_DP_1D,
        "below_rho_late": results_per_p["below"]["rho_late"],
        "critical_rho_late": results_per_p["critical"]["rho_late"],
        "above_rho_late": results_per_p["above"]["rho_late"],
        "monotone_phase_diagram":
            (results_per_p["below"]["rho_late"]
             < results_per_p["critical"]["rho_late"]
             < results_per_p["above"]["rho_late"]),
        "in_dp_band": bool(in_band),
        "overall_verdict": "CONFIRMED" if in_band else "PARTIAL",
        "n_seeds": n_seed,
    }

    out = {
        "system": "Directed Percolation (DP) universality class — Domany-Kinzel CA (SYNTHETIC)",
        "data_provenance": ("SYNTHETIC: 1+1d Domany-Kinzel cellular automaton "
                            "(DK 1984 J Phys A 17 L311); bond-DP line with "
                            "p_c = 0.6447 (Grassberger 1979). DP universality "
                            "anchored experimentally by Hof-Westerweel-Schneider "
                            "2008 Nature (pipe-flow turbulent puffs) and "
                            "Takeuchi-Sano 2007 PRL 99 234503 (liquid-crystal "
                            "turbulence DP transition); pipe transition Reynolds "
                            "# 2040 from Avila-Moxey-Lozar 2011 Science 333 192."),
        "predicted_class": "directed_percolation_1plus1d",
        "exponents_predicted": {
            "theta": THETA_DP_1D,
            "beta": BETA_DP_1D,
            "nu_parallel": NU_PARA_DP_1D,
        },
        "per_p": results_per_p,
        "summary": summary,
    }
    with open(HERE / "results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"[ok] wrote {HERE/'results.json'}")
    print(f"     theta_measured  = {theta_meas}")
    print(f"     theta_predicted = {THETA_DP_1D}")
    print(f"     monotone_phase_diagram = {summary['monotone_phase_diagram']}")
    print(f"     verdict         = {summary['overall_verdict']}")


if __name__ == "__main__":
    main()
