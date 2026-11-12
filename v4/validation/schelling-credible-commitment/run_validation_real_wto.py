#!/usr/bin/env python3
"""Schelling credible commitment — real-data WTO retaliation fit (SESSION-25).

Real-data drop-in for `run_validation_v5.py` machinery. Uses the
Horn-Mavroidis WTO Dispute Settlement Dataset (1995-2006, with events
through 2010) as the empirical sample.

Data
----
`data/bown_wto_disputes.csv` — 23 WTO disputes that reached the
retaliation-request stage. Each dispute coded with:
  - `sunk_cost_s` ∈ [0, 1]: institutional sunk cost based on
    (escalation stage × retaliation value). Five stages:
      0.20 = arb req, no authorisation, bilateral settle
      0.25-0.30 = arb req then settled during arbitration
      0.40-0.50 = authorisation granted, no actual retaliation applied
      0.55-0.85 = authorisation + retaliation actually applied
        (with value-multiplier pushing high-$ cases toward 0.85)
  - `defendant_complied_24mo` ∈ {0, 1}: did the defendant bring its
    measure into compliance within 24 months of the relevant event?

The coding scheme is pre-registered in this file's docstring; the
basis for each dispute's outcome is annotated in the CSV `outcome_basis`
column with references to (a) Horn-Mavroidis event fields and (b) WTO
official one-page case summaries (2010 edition).

Limitations
-----------
- n = 23 is below the cheap n=10 rule of thumb but very small for
  per-anchor microtune. Bootstrap CIs will be wide.
- Sunk-cost coding is necessarily categorical (5 stages) → 5 unique
  s-values + value-multiplier perturbation. Not a continuous treatment.
- DS103 and DS113 are linked complaints (same Canadian Special Class
  milk dispute, US + NZ co-complainants) → effectively one obs of
  similar outcome.
- DS217 and DS234 are co-complainants on Byrd Amendment → same outcome.
- DS136 and DS162 are parallel 1916 Act repeals → same outcome.

n_effective for independence ≈ 23 − 4 (duplicates) ≈ 19. Still tiny.

Method
------
Identical to v0.5 sub-run A:
  1. Probit MLE fit on real (s, y) data
  2. Reparametrise to (s*, k)
  3. Bootstrap 95% CIs
  4. Per-anchor projection (sub-run D microtune): does this WTO real
     data, projected onto the 4 anchor (p_low, p_high) profiles, hit
     within ±0.20?
  5. Compare to the WTO synthetic anchor (p_low=0.30, p_high=0.85)
     from `results_v5.json`.

Determinism
-----------
Bootstrap RNG seed = 20260525 (same as v0.5 main runs).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

THIS_DIR = Path(__file__).resolve().parent
DATA_FILE = THIS_DIR / "data" / "bown_wto_disputes.csv"
RESULTS_FILE = THIS_DIR / "results_real_wto.json"
PREREG_V5 = {
    "s_star_band": [0.20, 0.35],
    "k_band": [4.0, 12.0],
    "p_high_threshold": 0.65,
    "p_low_threshold": 0.40,
    "sham_k_max_abs": 1.5,
    "per_anchor_tolerance_strict": 0.20,
}

# Anchors from results_v5.json
ANCHORS = [
    {"domain": "wto_retaliation",            "n": 110,  "p_low": 0.30, "p_high": 0.85},
    {"domain": "ma_termination_fee",         "n": 3000, "p_low": 0.55, "p_high": 0.85},
    {"domain": "dual_class_share",           "n": 500,  "p_low": 0.40, "p_high": 0.80},
    {"domain": "sovereign_default_austerity","n": 120,  "p_low": 0.35, "p_high": 0.75},
]


def load_data():
    """Return (s, y, n, raw_rows) from the CSV."""
    s, y, rows = [], [], []
    with DATA_FILE.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            s.append(float(r["sunk_cost_s"]))
            y.append(int(r["defendant_complied_24mo"]))
            rows.append(r)
    return np.asarray(s), np.asarray(y), len(s), rows


def probit_nll(params, s, y):
    a, b = params
    z = a + b * s
    p = norm.cdf(z)
    p = np.clip(p, 1e-12, 1.0 - 1e-12)
    return -float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def probit_fit_mle(s, y):
    a0 = norm.ppf(np.clip(np.mean(y), 0.05, 0.95))
    b0 = 1.0
    res = minimize(
        probit_nll, x0=np.array([a0, b0]), args=(s, y),
        method="L-BFGS-B", options={"maxiter": 500, "ftol": 1e-10},
    )
    a, b = res.x
    s_star = float(-a / b) if abs(b) > 1e-9 else float("nan")
    return {
        "alpha_probit": float(a),
        "beta_probit": float(b),
        "s_star": s_star,
        "k": float(b),
        "p_at_s_low": float(norm.cdf(a + b * 0.2)),
        "p_at_s_mid": float(norm.cdf(a + b * 0.3)),
        "p_at_s_high": float(norm.cdf(a + b * 0.4)),
        "converged": bool(res.success),
        "nll": float(res.fun),
    }


def bootstrap_ci(s, y, n_boot=2000, seed=20260525):
    rng = np.random.default_rng(seed)
    n = len(s)
    s_stars, ks, alphas, betas = [], [], [], []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        # Resampling must keep some variation across both 0/1 outcomes
        if len(np.unique(y[idx])) < 2:
            continue
        try:
            fit_b = probit_fit_mle(s[idx], y[idx])
            if fit_b["converged"] and abs(fit_b["k"]) > 1e-9:
                s_stars.append(fit_b["s_star"])
                ks.append(fit_b["k"])
                alphas.append(fit_b["alpha_probit"])
                betas.append(fit_b["beta_probit"])
        except Exception:  # noqa: BLE001
            continue
    s_stars = np.array([x for x in s_stars if np.isfinite(x)])
    ks = np.array([x for x in ks if np.isfinite(x)])
    alphas = np.array([x for x in alphas if np.isfinite(x)])
    betas = np.array([x for x in betas if np.isfinite(x)])
    return {
        "s_star_ci95": [float(np.percentile(s_stars, 2.5)), float(np.percentile(s_stars, 97.5))] if len(s_stars) > 10 else [None, None],
        "k_ci95": [float(np.percentile(ks, 2.5)), float(np.percentile(ks, 97.5))] if len(ks) > 10 else [None, None],
        "alpha_ci95": [float(np.percentile(alphas, 2.5)), float(np.percentile(alphas, 97.5))] if len(alphas) > 10 else [None, None],
        "beta_ci95": [float(np.percentile(betas, 2.5)), float(np.percentile(betas, 97.5))] if len(betas) > 10 else [None, None],
        "n_boot_valid": int(len(ks)),
    }


def per_anchor_projection(s, y, fit, tolerance=0.20):
    alpha, beta = fit["alpha_probit"], fit["beta_probit"]
    # Use empirical s̄_low / s̄_high from THIS data
    s_low_mean = float(s[s < 0.35].mean()) if (s < 0.35).any() else float("nan")
    s_high_mean = float(s[s >= 0.35].mean()) if (s >= 0.35).any() else float("nan")
    p_hat_low = float(norm.cdf(alpha + beta * s_low_mean)) if np.isfinite(s_low_mean) else float("nan")
    p_hat_high = float(norm.cdf(alpha + beta * s_high_mean)) if np.isfinite(s_high_mean) else float("nan")

    per = []
    hits = 0
    for A in ANCHORS:
        res_low = abs(p_hat_low - A["p_low"]) if np.isfinite(p_hat_low) else float("nan")
        res_high = abs(p_hat_high - A["p_high"]) if np.isfinite(p_hat_high) else float("nan")
        hit = bool(
            np.isfinite(res_low) and np.isfinite(res_high)
            and res_low <= tolerance and res_high <= tolerance
        )
        if hit:
            hits += 1
        per.append({
            **A,
            "p_hat_low": p_hat_low,
            "p_hat_high": p_hat_high,
            "residual_low": res_low,
            "residual_high": res_high,
            "hit_at_tol": hit,
        })
    return {
        "tolerance": tolerance,
        "n_anchors": len(ANCHORS),
        "n_hits": hits,
        "per_anchor": per,
        "s_low_mean": s_low_mean,
        "s_high_mean": s_high_mean,
        "p_hat_low": p_hat_low,
        "p_hat_high": p_hat_high,
    }


def main():
    s, y, n, rows = load_data()
    print(f"[real-wto] n={n}", file=sys.stderr)
    print(f"[real-wto] s range = [{s.min():.3f}, {s.max():.3f}], "
          f"y_mean = {y.mean():.3f}, s_mean = {s.mean():.3f}", file=sys.stderr)

    # Empirical p_low / p_high (low-s vs high-s halves at s=0.35 cutoff)
    p_low_obs = float(y[s < 0.35].mean()) if (s < 0.35).any() else float("nan")
    p_high_obs = float(y[s >= 0.35].mean()) if (s >= 0.35).any() else float("nan")
    n_low = int((s < 0.35).sum())
    n_high = int((s >= 0.35).sum())
    print(f"[real-wto] p_low_obs = {p_low_obs:.3f} (n={n_low})", file=sys.stderr)
    print(f"[real-wto] p_high_obs = {p_high_obs:.3f} (n={n_high})", file=sys.stderr)

    # Fit probit
    fit = probit_fit_mle(s, y)
    ci = bootstrap_ci(s, y, n_boot=2000)
    fit.update(ci)

    print(f"[real-wto] fitted s* = {fit['s_star']:.3f}, k = {fit['k']:.3f}", file=sys.stderr)
    print(f"[real-wto] 95% CI s* = {fit['s_star_ci95']}, k = {fit['k_ci95']}", file=sys.stderr)
    print(f"[real-wto] p(0.2) = {fit['p_at_s_low']:.3f}, p(0.4) = {fit['p_at_s_high']:.3f}", file=sys.stderr)

    # Per-anchor projection
    pa = per_anchor_projection(s, y, fit, tolerance=PREREG_V5["per_anchor_tolerance_strict"])
    print(f"[real-wto] per-anchor hits @ ±0.20: {pa['n_hits']}/4", file=sys.stderr)

    # Verdict ladder
    s_star_band = PREREG_V5["s_star_band"]
    k_band = PREREG_V5["k_band"]
    s_star_in_band = (s_star_band[0] <= fit["s_star"] <= s_star_band[1])
    k_in_band = (k_band[0] <= fit["k"] <= k_band[1])
    p_high_ok = fit["p_at_s_high"] > PREREG_V5["p_high_threshold"]
    p_low_ok = fit["p_at_s_low"] < PREREG_V5["p_low_threshold"]
    k_ci_low, k_ci_high = fit["k_ci95"]
    k_ci_excludes_0 = (
        k_ci_low is not None
        and k_ci_high is not None
        and not (k_ci_low <= 0 <= k_ci_high)
    )

    if not k_ci_excludes_0:
        verdict = "REJECT-or-INCONCLUSIVE (mechanism unclear, k CI includes 0)"
    elif k_ci_high < 0:
        verdict = "REJECT-SIGN-REVERSED-REAL (k CI excludes 0 below zero)"
    elif s_star_in_band and k_in_band and p_high_ok and p_low_ok:
        if pa["n_hits"] >= 4:
            verdict = "PASS-STRONG-REAL"
        elif pa["n_hits"] >= 3:
            verdict = "PASS-CONFIRMED-WITH-ANCHOR-REAL"
        elif pa["n_hits"] >= 2:
            verdict = "PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT-REAL"
        else:
            verdict = "PASS-CONFIRMED-REAL"
    else:
        failures = []
        if not s_star_in_band:
            failures.append(f"s*={fit['s_star']:.3f} ∉ {s_star_band}")
        if not k_in_band:
            failures.append(f"k={fit['k']:.3f} ∉ {k_band}")
        if not p_high_ok:
            failures.append(f"p(0.4)={fit['p_at_s_high']:.3f} < {PREREG_V5['p_high_threshold']}")
        if not p_low_ok:
            failures.append(f"p(0.2)={fit['p_at_s_low']:.3f} ≥ {PREREG_V5['p_low_threshold']}")
        verdict = "INCONCLUSIVE-or-REJECT: " + "; ".join(failures)

    print(f"[VERDICT-real-wto] {verdict}", file=sys.stderr)

    # Specifically compare to WTO synthetic anchor (the most relevant one)
    wto_synth_p_low, wto_synth_p_high = 0.30, 0.85
    wto_hit = (
        abs(pa["p_hat_low"] - wto_synth_p_low) <= 0.20
        and abs(pa["p_hat_high"] - wto_synth_p_high) <= 0.20
    )

    # Hypothesis (a) vs (b) interpretation
    # (a) structural: real WTO data fits its own anchor cleanly but
    #     other 3 anchors still miss → 4-anchor gap is structural
    # (b) framing: real WTO data fits NONE of the 4 anchors, including
    #     its own → pre-reg coords were misread from literature
    if wto_hit and pa["n_hits"] <= 2:
        hyp_interpretation = "STRUCTURAL-LIKELY: WTO real data hits WTO anchor but ≤2/4 overall → 4-anchor gap is genuine"
    elif wto_hit and pa["n_hits"] >= 3:
        hyp_interpretation = "STRUCTURAL-LESS-LIKELY: WTO real data hits ≥3/4 anchors → curves are more universal than pre-reg suggested"
    elif not wto_hit:
        hyp_interpretation = "FRAMING-LIKELY: WTO real data MISSES its own anchor → pre-reg (s_low/s_high, p_low/p_high) coords are mis-stated for WTO"
    else:
        hyp_interpretation = "INCONCLUSIVE: n too small"

    print(f"[HYPOTHESIS-INTERPRETATION] {hyp_interpretation}", file=sys.stderr)

    out = {
        "system": "Schelling credible commitment — REAL WTO retaliation data fit (SESSION-25)",
        "data_source": "Horn-Mavroidis WTO Dispute Settlement Dataset (World Bank, 2011 update of 2006 cutoff) + WTO Official Case Summaries 2010 Edition + per-dispute manual outcome coding",
        "n_disputes": n,
        "p_low_obs": p_low_obs,
        "p_high_obs": p_high_obs,
        "n_low_bin": n_low,
        "n_high_bin": n_high,
        "prereg_v5": PREREG_V5,
        "fit": fit,
        "per_anchor_projection": pa,
        "wto_anchor_specific_hit": bool(wto_hit),
        "wto_anchor_specific_residual_low": abs(pa["p_hat_low"] - wto_synth_p_low),
        "wto_anchor_specific_residual_high": abs(pa["p_hat_high"] - wto_synth_p_high),
        "verdict": verdict,
        "hypothesis_interpretation": hyp_interpretation,
        "structural_vs_framing": ("structural" if "STRUCTURAL" in hyp_interpretation
                                   else "framing" if "FRAMING" in hyp_interpretation
                                   else "inconclusive"),
        "data_rows": rows,
    }

    with RESULTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"[wrote] {RESULTS_FILE}", file=sys.stderr)
    print(json.dumps({k: v for k, v in out.items() if k != "data_rows"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
