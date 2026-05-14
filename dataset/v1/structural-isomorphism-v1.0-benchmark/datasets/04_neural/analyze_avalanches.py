#!/usr/bin/env python3
"""
Layer 5 Phase 4 — Step 2: Fit Beggs-Plenz SOC exponents on avalanche data.

Neural-avalanche SOC (Beggs-Plenz 2003) predicts:
  P(s) ∝ s^(-tau),   tau = 1.5   (size distribution)
  P(T) ∝ T^(-alpha), alpha = 2.0 (duration distribution)
  <s|T> ∝ T^(1/sigma*nu*z) with exponent 1/(alpha-1) ~= 1

We fit each distribution with Clauset-Shalizi-Newman 2009 (same machinery
as Phase 1/2/3) and compare against lognormal / exponential alternatives.

Input:  a JSONL file with {size: int, duration: int} per line.
Output: avalanche_results.json  with both fits.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import powerlaw


def load_jsonl(path: Path):
    sizes, durations = [], []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                sizes.append(int(d["size"]))
                durations.append(int(d["duration"]))
            except Exception:
                continue
    return np.array(sizes, dtype=float), np.array(durations, dtype=float)


def clauset(vals: np.ndarray, name: str):
    vals = vals[vals > 0]
    if len(vals) < 100:
        return {"error": f"too few ({len(vals)})", "name": name}
    try:
        fit = powerlaw.Fit(vals, discrete=True, xmin_distance="D", verbose=False)
        alpha = float(fit.power_law.alpha)
        sigma = float(fit.power_law.sigma)
        xmin = float(fit.power_law.xmin)
        R_ln, p_ln = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
        R_exp, p_exp = fit.distribution_compare("power_law", "exponential", normalized_ratio=True)
        return {
            "name": name,
            "alpha": alpha,
            "sigma_alpha": sigma,
            "xmin": xmin,
            "n_total": int(len(vals)),
            "n_tail": int(np.sum(vals >= xmin)),
            "vs_lognormal_R": float(R_ln),
            "vs_lognormal_p": float(p_ln),
            "vs_exponential_R": float(R_exp),
            "vs_exponential_p": float(p_exp),
        }
    except Exception as e:
        return {"error": str(e), "name": name}


def mean_size_given_duration(sizes, durations):
    """Test the scaling relation <s|T> ~ T^gamma with gamma = 1/(alpha-1).
    Returns (T_bins, mean_s_per_T, fit_gamma, fit_gamma_sigma, R^2)."""
    T_unique = np.unique(durations.astype(int))
    T_bins = []
    mean_s = []
    for T in T_unique:
        mask = (durations == T)
        if mask.sum() < 30:    # need decent stats per bin
            continue
        T_bins.append(T)
        mean_s.append(sizes[mask].mean())
    if len(T_bins) < 4:
        return {"error": f"too few T bins with enough stats"}
    T_bins = np.array(T_bins, dtype=float)
    mean_s = np.array(mean_s, dtype=float)
    # log-log linear fit mean_s = A * T^gamma
    mask = (T_bins > 0) & (mean_s > 0)
    x = np.log10(T_bins[mask])
    y = np.log10(mean_s[mask])
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    # sigma of slope
    n = len(x)
    mse = ss_res / max(n - 2, 1)
    var_slope = mse / np.sum((x - x.mean()) ** 2)
    return {
        "gamma": float(slope),
        "gamma_sigma": float(np.sqrt(abs(var_slope))),
        "intercept": float(intercept),
        "R2": float(r2) if r2 is not None else None,
        "n_T_bins": int(mask.sum()),
        "T_range": [float(T_bins[mask].min()), float(T_bins[mask].max())],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="synthetic_avalanches.jsonl")
    ap.add_argument("--output", default="synthetic_results.json")
    ap.add_argument("--label", default="synthetic")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    inp = here / args.input
    out = here / args.output

    print(f"Loading {inp.name} ...")
    sizes, durations = load_jsonl(inp)
    print(f"  n avalanches: {len(sizes)}")

    print("\nFitting P(s) — size distribution ...")
    fit_s = clauset(sizes, "size")
    print(f"  tau (size)     = {fit_s.get('alpha'):.4f} +/- {fit_s.get('sigma_alpha'):.4f}")
    print(f"  xmin = {fit_s.get('xmin')}, n_tail = {fit_s.get('n_tail')}")
    print(f"  vs lognormal:   R={fit_s.get('vs_lognormal_R'):.2f}, p={fit_s.get('vs_lognormal_p'):.3g}")
    print(f"  vs exponential: R={fit_s.get('vs_exponential_R'):.2f}, p={fit_s.get('vs_exponential_p'):.3g}")

    print("\nFitting P(T) — duration distribution ...")
    fit_d = clauset(durations, "duration")
    print(f"  alpha (duration) = {fit_d.get('alpha'):.4f} +/- {fit_d.get('sigma_alpha'):.4f}")
    print(f"  xmin = {fit_d.get('xmin')}, n_tail = {fit_d.get('n_tail')}")
    print(f"  vs lognormal:   R={fit_d.get('vs_lognormal_R'):.2f}, p={fit_d.get('vs_lognormal_p'):.3g}")
    print(f"  vs exponential: R={fit_d.get('vs_exponential_R'):.2f}, p={fit_d.get('vs_exponential_p'):.3g}")

    print("\nFitting <s|T> scaling relation ...")
    rel = mean_size_given_duration(sizes, durations)
    if "gamma" in rel:
        print(f"  gamma = {rel['gamma']:.4f} +/- {rel['gamma_sigma']:.4f}, R^2 = {rel['R2']:.4f}")
    else:
        print(f"  {rel.get('error')}")

    # Predicted values (mean-field SOC / Beggs-Plenz)
    # Scaling relation: <s|T> ∝ T^gamma where gamma = (alpha_dur - 1)/(tau - 1)
    # For MF: gamma = (2-1)/(1.5-1) = 1/0.5 = 2.0
    predicted = {
        "tau_size": 1.5,
        "alpha_duration": 2.0,
        "gamma_scaling": 2.0,
        "scaling_relation_formula": "gamma = (alpha_dur - 1) / (tau - 1)",
    }
    ok_size = 1.3 <= fit_s.get("alpha", 0) <= 1.7
    ok_dur  = 1.7 <= fit_d.get("alpha", 0) <= 2.3
    ok_gamma = "gamma" in rel and 1.7 <= rel["gamma"] <= 2.3
    verdict = "CONFIRMED" if (ok_size and ok_dur and ok_gamma) else "PARTIAL"

    result = {
        "label": args.label,
        "predicted_class": "soc_threshold_cascade (neural avalanche, Beggs-Plenz 2003)",
        "n_avalanches": int(len(sizes)),
        "predicted_exponents": predicted,
        "size_fit": fit_s,
        "duration_fit": fit_d,
        "scaling_relation": rel,
        "checks": {
            "tau_in_[1.3,1.7]": ok_size,
            "alpha_in_[1.7,2.3]": ok_dur,
            "gamma_in_[1.7,2.3]": ok_gamma,
        },
        "verdict": verdict,
        "references": [
            "Beggs & Plenz 2003 J. Neurosci — 'Neuronal avalanches in neocortical circuits'",
            "Sethna-Dahmen-Myers 2001 Nature — mean-field branching process scaling",
            "Clauset-Shalizi-Newman 2009 SIAM Rev — power-law fitting",
        ],
    }
    out.write_text(json.dumps(result, indent=2))
    print(f"\nVERDICT: {verdict}")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
