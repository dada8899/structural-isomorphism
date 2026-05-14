#!/usr/bin/env python3
"""
Layer 5 Phase 5 — NULL VALIDATION.

Purpose: prove the SOC pipeline correctly REJECTS power-law / SOC
signatures on three datasets that are known to NOT be SOC. This
addresses the standard reviewer concern "your pipeline fits everything
to a power law" — by showing it doesn't.

Three null datasets (each generated synthetically with a known non-SOC
distribution):

  1. Gaussian random walk |increments|
     |dX_t| where dX ~ N(0, 1). Expected: P(|dX|) is folded-normal,
     not power-law. Should fail Clauset comparison vs lognormal AND vs
     the Gaussian/exponential baseline.

  2. Pure exponential event sizes
     s_i ~ Exp(lambda). Expected: P(s) ∝ exp(-lambda*s), no heavy tail,
     no power law. Pipeline should report alpha but reject power-law
     in distribution_compare vs exponential.

  3. Homogeneous Poisson event timestamps
     Inter-arrival times t_{i+1}-t_i ~ Exp(rate). Bin into windows,
     count avalanches as in our real-data pipelines. Expected: NO
     temporal clustering, so any 'aftershock decay' fit will give p
     near 0 with low R² (no Omori structure).

For each, we report:
  - alpha (if power-law fit attempted)
  - vs-lognormal R, p
  - vs-exponential R, p
  - whether the test would mistakenly call this 'SOC-like'

Output: null_results.json + a short verdict note.
"""

import json
import math
from pathlib import Path

import numpy as np

OUT_DIR = Path(__file__).resolve().parent
OUT = OUT_DIR / "null_results.json"

RNG = np.random.default_rng(42)


def gaussian_random_walk_increments(n: int = 20_000):
    """|dX| where dX ~ N(0,1). NOT power-law: folded normal."""
    dx = RNG.normal(0.0, 1.0, size=n)
    return np.abs(dx)


def exponential_sizes(n: int = 20_000, rate: float = 1.0):
    """s ~ Exp(rate). NOT power-law: exponential tail."""
    return RNG.exponential(scale=1.0 / rate, size=n)


def poisson_arrivals(n_events: int = 20_000, rate: float = 1.0):
    """Homogeneous Poisson timestamps; no clustering structure."""
    iat = RNG.exponential(scale=1.0 / rate, size=n_events)
    times = np.cumsum(iat)
    return times


def fit_powerlaw(vals, name):
    """Try Clauset power-law fit + comparisons."""
    try:
        import powerlaw
    except Exception as e:
        return {"name": name, "error": f"powerlaw missing: {e}"}
    vals = vals[vals > 0]
    if len(vals) < 100:
        return {"name": name, "error": f"too few: {len(vals)}"}
    fit = powerlaw.Fit(vals, discrete=False, xmin_distance="D", verbose=False)
    alpha = float(fit.power_law.alpha)
    sigma = float(fit.power_law.sigma)
    xmin = float(fit.power_law.xmin)
    n_tail = int(np.sum(vals >= xmin))
    R_ln, p_ln = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
    R_exp, p_exp = fit.distribution_compare("power_law", "exponential", normalized_ratio=True)
    # Verdict: if power-law DOES NOT decisively beat both alternatives
    # (no significant negative R or significantly positive R against the
    # right competitor), we say "SOC-like signature absent".
    rejects_power_law = (R_exp < 0 or R_ln < 0)  # power-law is the loser
    return {
        "name": name,
        "alpha": alpha,
        "sigma_alpha": sigma,
        "xmin": xmin,
        "n_total": int(len(vals)),
        "n_tail": n_tail,
        "vs_lognormal_R": float(R_ln),
        "vs_lognormal_p": float(p_ln),
        "vs_exponential_R": float(R_exp),
        "vs_exponential_p": float(p_exp),
        "rejects_power_law": bool(rejects_power_law),
    }


def bin_and_omori(times, bin_seconds: float = 1.0, sigma_k: float = 3.0,
                  window_bins: int = 30):
    """Same Omori detector as Phase 1-4. On Poisson data should give
    p near 0 with bad R^2 (no decay structure)."""
    if len(times) == 0:
        return {"error": "no events"}
    t0 = times.min()
    n_bins = int((times.max() - t0) / bin_seconds) + 1
    counts = np.zeros(n_bins, dtype=np.int64)
    idx = ((times - t0) / bin_seconds).astype(np.int64)
    idx = np.clip(idx, 0, n_bins - 1)
    np.add.at(counts, idx, 1)

    mu = counts.mean()
    sig = counts.std()
    threshold = mu + sigma_k * sig
    main_idx = np.where(counts > threshold)[0]
    valid = main_idx[(main_idx + window_bins) < n_bins]
    if len(valid) < 10:
        return {"n_main": int(len(valid)), "mu": float(mu),
                "threshold": float(threshold),
                "note": "too few main shocks (Poisson rarely has >3sigma spikes — expected)"}

    rates = np.zeros(window_bins)
    for tau in range(1, window_bins + 1):
        rates[tau - 1] = counts[valid + tau].mean() - mu
    tau_b = np.arange(1, window_bins + 1, dtype=float)
    keep = rates > 0
    if keep.sum() < 6:
        return {"n_main": int(len(valid)), "n_pos_excess_bins": int(keep.sum()),
                "note": "no excess post-shock activity (no Omori decay)"}
    t_fit = tau_b[keep]
    r_fit = rates[keep]
    # Try a fit
    x = np.log10(t_fit + 1.0)
    y = np.log10(r_fit)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "n_main": int(len(valid)),
        "mu": float(mu),
        "threshold": float(threshold),
        "p": float(-slope),
        "R2": float(r2) if r2 is not None else None,
        "n_pos_excess_bins": int(keep.sum()),
    }


def main():
    print("=" * 64)
    print("NULL VALIDATION — pipeline must reject power-law on these")
    print("=" * 64)

    results = {}

    print("\n[1] Gaussian random walk |increments|")
    g = gaussian_random_walk_increments()
    print(f"    n={len(g)}, mean={g.mean():.3f}, max={g.max():.2f}")
    results["gaussian_walk"] = fit_powerlaw(g, "gaussian_walk")
    r = results["gaussian_walk"]
    print(f"    alpha={r.get('alpha'):.3f}, vs lognormal R={r.get('vs_lognormal_R'):.2f}, "
          f"vs exp R={r.get('vs_exponential_R'):.2f}")
    print(f"    rejects_power_law: {r.get('rejects_power_law')}")

    print("\n[2] Exponential event sizes (rate=1.0)")
    e = exponential_sizes()
    print(f"    n={len(e)}, mean={e.mean():.3f}, max={e.max():.2f}")
    results["exponential"] = fit_powerlaw(e, "exponential")
    r = results["exponential"]
    print(f"    alpha={r.get('alpha'):.3f}, vs lognormal R={r.get('vs_lognormal_R'):.2f}, "
          f"vs exp R={r.get('vs_exponential_R'):.2f}")
    print(f"    rejects_power_law: {r.get('rejects_power_law')}")

    print("\n[3] Homogeneous Poisson timestamps — Omori on bin counts")
    times = poisson_arrivals(n_events=50_000, rate=10.0)
    print(f"    n_events={len(times)}, span={times.max():.1f}s")
    omori = bin_and_omori(times, bin_seconds=1.0)
    results["poisson_omori"] = omori
    print(f"    {omori}")
    # Also check: Poisson size distribution = the inter-arrival times themselves
    # are exponential (no power law)
    print("    + Power-law fit on inter-arrival times (should reject):")
    iat = np.diff(times)
    pl_iat = fit_powerlaw(iat, "poisson_iat")
    results["poisson_iat"] = pl_iat
    print(f"    alpha={pl_iat.get('alpha'):.3f}, vs lognormal R={pl_iat.get('vs_lognormal_R'):.2f}, "
          f"vs exp R={pl_iat.get('vs_exponential_R'):.2f}")
    print(f"    rejects_power_law: {pl_iat.get('rejects_power_law')}")

    # Joint verdict
    correctly_rejected = (
        results["gaussian_walk"].get("rejects_power_law", False)
        and results["exponential"].get("rejects_power_law", False)
        and results["poisson_iat"].get("rejects_power_law", False)
    )
    poisson_no_omori = (
        omori.get("R2") is None
        or (omori.get("R2") is not None and omori.get("R2") < 0.5)
    )
    pipeline_ok = correctly_rejected and poisson_no_omori

    summary = {
        "task": "NULL VALIDATION",
        "objective": "Pipeline must REJECT power-law on synthetic non-SOC data",
        "datasets_tested": ["gaussian_walk", "exponential", "poisson_iat", "poisson_omori"],
        "all_three_size_dists_rejected_power_law": correctly_rejected,
        "poisson_failed_omori_fit": poisson_no_omori,
        "pipeline_robustness": "PASSED" if pipeline_ok else "FAILED",
        "note": (
            "If pipeline_robustness == PASSED, the positive SOC findings of "
            "Phases 1-4 cannot be explained by 'pipeline fits everything as "
            "power-law'. The pipeline is a meaningful detector, not a "
            "tautological labelling tool."
        ),
        "results": results,
    }
    OUT.write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 64)
    print(f"PIPELINE ROBUSTNESS: {summary['pipeline_robustness']}")
    print("=" * 64)
    print(f"  All three size dists rejected power-law: {correctly_rejected}")
    print(f"  Poisson failed Omori fit (R²<0.5 or no fit): {poisson_no_omori}")
    print(f"  Saved: {OUT}")


if __name__ == "__main__":
    main()
