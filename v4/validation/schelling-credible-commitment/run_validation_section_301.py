#!/usr/bin/env python3
"""Schelling credible commitment — US §301 natural-instrument extension (SESSION-27).

Background (SESSION-25 finding)
-------------------------------
Probit on Horn-Mavroidis WTO DSU sample (n=23) yielded k = -2.92 (sign-flipped
vs. pre-reg expectation k > 0). The mechanism is endogenous selection on
defendant intransigence: in the WTO DSU sample, retaliation authorisation is
*requested* only after a defendant has shown unwillingness to comply through
multiple panel/AB stages. High `sunk_cost_s` correlates with hard-type
defendants → conditional compliance probability is LOWER, not higher, in the
high-s bin. The sign-flip is identification-induced, not a failure of the
underlying Schelling mechanism.

Identification strategy: §301 as natural instrument
---------------------------------------------------
USTR Section 301 investigations are initiated by U.S. petitioners (60% of
cases) or self-initiated by USTR. The decision to apply retaliation is
made unilaterally by the U.S. executive on essentially political grounds:
preserving GSP/CBI benefits, election cycles, sector-specific lobbying.
Crucially, retaliation_applied is NOT conditional on the defendant having
already revealed itself to be a hard type through a multi-stage adjudication
process — it is a fresh executive decision often taken before the defendant
has had any structured chance to bargain on the underlying issue.

This gives us partial exclusion: §301 retaliation_applied is plausibly
exogenous to defendant type, conditional on the underlying foreign measure
being deemed actionable. Compared to the WTO DSU sample where
retaliation_authorised is a function of stage-by-stage non-compliance
revealing the defendant's type, §301 retaliation_applied is closer to a
randomly-assigned treatment with respect to the latent intransigence index.

Hypothesis under the natural-instrument framing
-----------------------------------------------
H1 (Schelling-consistent): In the §301 sample, conditional on retaliation
being applied (high s), the probability of foreign concession should be
HIGHER than in the no-retaliation subset → k > 0 (sign aligned with
pre-reg).

H0 / null (selection-only mechanism): Even in §301 sample, k ≤ 0 because
hard targets are more likely to draw retaliation → finding generalises.

Outcome: an aggregate-level cross-check using Bayard & Elliott (1994)
"Reciprocity and Retaliation in U.S. Trade Policy" published findings
(91 §301 cases, 1975-1994):
  - 35 / 72 analyzable cases successful (48.6% overall concession rate)
  - 12 cases with retaliation applied → 2 successes (17%)
  - => 60 cases without retaliation applied → 33 successes (55%)

The Bayard-Elliott aggregate already exhibits k < 0 at the population
level (retaliation-applied subset compliance rate 17% < no-retaliation
subset compliance rate 55%). This is consistent with WTO DSU finding,
ruling out the simple "WTO sample is special" explanation.

Data
----
`data/section_301_cases.csv` — n=35 §301 investigations from CRS R46604
Table A-1 (post-WTO 1995-Present subset, where individual-level outcome
coding is feasible from CRS notes + public WTO/USTR records).

Each row coded with:
  - `retaliation_applied` ∈ {0, 1}: did USTR actually impose unilateral
    tariffs / GSP suspension under §301?
  - `outcome_concession` ∈ {0, 1}: did the target government make the
    requested change within ~5 years of the §301 determination?
  - `sunk_cost_s` ∈ [0, 1]: institutional sunk cost ordinal proxy,
    same coding logic as WTO DSU file. Higher s for retaliation-applied
    cases, with magnitude scaled by retaliation breadth.

Pre-1995 (cases 1-95) aggregate cross-check uses Bayard-Elliott published
counts, NOT fabricated individual cases.

Method
------
1. Probit MLE on §301 post-1995 individual sample (n=35)
2. Bootstrap 95% CI (n_boot=2000)
3. Aggregate-level cross-check against Bayard-Elliott 1975-1994 (n=72)
4. Split-sample comparison: §301 vs WTO DSU k estimates
5. Verdict ladder: does §301 (exogenous-treatment) sample restore k > 0?

Determinism
-----------
Bootstrap RNG seed = 20260528.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

THIS_DIR = Path(__file__).resolve().parent
DATA_FILE = THIS_DIR / "data" / "section_301_cases.csv"
RESULTS_FILE = THIS_DIR / "results_section_301.json"
WTO_RESULTS_FILE = THIS_DIR / "results_real_wto.json"

PREREG_V5 = {
    "s_star_band": [0.20, 0.35],
    "k_band": [4.0, 12.0],
    "p_high_threshold": 0.65,
    "p_low_threshold": 0.40,
    "sham_k_max_abs": 1.5,
    "per_anchor_tolerance_strict": 0.20,
}

# Bayard & Elliott (1994) aggregate 1975-1994 published counts
# (Reciprocity and Retaliation in US Trade Policy, PIIE; quoted via Cato
#  PA-930 2022 and EveryCRSReport R46604)
BAYARD_ELLIOTT_AGGREGATE = {
    "n_total_cases_1975_1994": 91,
    "n_analyzable": 72,
    "n_total_concessions": 35,
    "n_retaliation_applied": 12,
    "n_retaliation_applied_success": 2,
    "concession_rate_retaliation_applied": 2 / 12,        # 0.167
    "concession_rate_no_retaliation": (35 - 2) / (72 - 12),  # 33/60 = 0.550
    "concession_rate_overall": 35 / 72,                   # 0.486
}


def load_data():
    """Return (s, y, era, retal, rows) from CSV."""
    s, y, era, retal, rows = [], [], [], [], []
    with DATA_FILE.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            s.append(float(r["sunk_cost_s"]))
            y.append(int(r["outcome_concession"]))
            era.append(r["era"])
            retal.append(int(r["retaliation_applied"]))
            rows.append(r)
    return (
        np.asarray(s, dtype=float),
        np.asarray(y, dtype=int),
        np.asarray(era),
        np.asarray(retal, dtype=int),
        rows,
    )


def probit_nll(params, s, y):
    a, b = params
    z = a + b * s
    p = norm.cdf(z)
    p = np.clip(p, 1e-12, 1.0 - 1e-12)
    return -float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def probit_fit_mle(s, y):
    if len(np.unique(y)) < 2:
        return None
    a0 = norm.ppf(np.clip(float(np.mean(y)), 0.05, 0.95))
    b0 = 1.0
    res = minimize(
        probit_nll,
        x0=np.array([a0, b0]),
        args=(s, y),
        method="L-BFGS-B",
        options={"maxiter": 500, "ftol": 1e-10},
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


def bootstrap_ci(s, y, n_boot=2000, seed=20260528):
    rng = np.random.default_rng(seed)
    n = len(s)
    ks, s_stars, alphas, betas = [], [], [], []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        if len(np.unique(y[idx])) < 2:
            continue
        try:
            fb = probit_fit_mle(s[idx], y[idx])
            if fb is None:
                continue
            if fb["converged"] and abs(fb["k"]) > 1e-9:
                ks.append(fb["k"])
                s_stars.append(fb["s_star"])
                alphas.append(fb["alpha_probit"])
                betas.append(fb["beta_probit"])
        except Exception:  # noqa: BLE001
            continue
    ks_a = np.array([x for x in ks if np.isfinite(x)])
    s_stars_a = np.array([x for x in s_stars if np.isfinite(x)])
    alphas_a = np.array([x for x in alphas if np.isfinite(x)])
    betas_a = np.array([x for x in betas if np.isfinite(x)])

    def pct_ci(arr):
        if len(arr) <= 10:
            return [None, None]
        return [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]

    return {
        "k_ci95": pct_ci(ks_a),
        "s_star_ci95": pct_ci(s_stars_a),
        "alpha_ci95": pct_ci(alphas_a),
        "beta_ci95": pct_ci(betas_a),
        "n_boot_valid": int(len(ks_a)),
    }


def aggregate_probit_from_two_bins(p_low, n_low, p_high, n_high, s_low=0.25, s_high=0.65):
    """Closed-form probit for two-bin grouped data.

    Solves for (alpha, beta) such that
        norm.cdf(alpha + beta*s_low)  = p_low_hat
        norm.cdf(alpha + beta*s_high) = p_high_hat
    where p_*_hat are MLE estimates from the bin counts (just the empirical
    rates, since within a single bin probit is saturated).
    Returns (alpha, beta, k=beta).
    """
    # Avoid 0/1 by Laplace smoothing
    p_low_hat = (p_low * n_low + 0.5) / (n_low + 1.0)
    p_high_hat = (p_high * n_high + 0.5) / (n_high + 1.0)
    z_low = norm.ppf(p_low_hat)
    z_high = norm.ppf(p_high_hat)
    beta = (z_high - z_low) / (s_high - s_low)
    alpha = z_low - beta * s_low
    return alpha, beta


def main():
    s, y, era, retal, rows = load_data()
    n = len(s)
    print(f"[§301] n={n} (post-WTO 1995-Present subset)", file=sys.stderr)
    print(f"[§301] s range = [{s.min():.3f}, {s.max():.3f}], "
          f"y_mean = {y.mean():.3f}, s_mean = {s.mean():.3f}", file=sys.stderr)
    print(f"[§301] retaliation_applied = {int(retal.sum())}/{n}", file=sys.stderr)

    # Empirical p_low / p_high (using s<0.5 vs s>=0.5 cutoff since §301
    # natural break is "retaliation applied vs not")
    p_low_obs = float(y[s < 0.5].mean()) if (s < 0.5).any() else float("nan")
    p_high_obs = float(y[s >= 0.5].mean()) if (s >= 0.5).any() else float("nan")
    n_low_bin = int((s < 0.5).sum())
    n_high_bin = int((s >= 0.5).sum())
    print(f"[§301] p_low_obs = {p_low_obs:.3f} (n={n_low_bin}, s<0.5)", file=sys.stderr)
    print(f"[§301] p_high_obs = {p_high_obs:.3f} (n={n_high_bin}, s>=0.5)", file=sys.stderr)

    # Retaliation-stratified rates (the natural-instrument cut)
    p_y_given_retal_1 = float(y[retal == 1].mean()) if (retal == 1).any() else float("nan")
    p_y_given_retal_0 = float(y[retal == 0].mean()) if (retal == 0).any() else float("nan")
    n_retal_1 = int((retal == 1).sum())
    n_retal_0 = int((retal == 0).sum())
    print(f"[§301] P(concession | retal=1) = {p_y_given_retal_1:.3f} (n={n_retal_1})", file=sys.stderr)
    print(f"[§301] P(concession | retal=0) = {p_y_given_retal_0:.3f} (n={n_retal_0})", file=sys.stderr)

    # Probit fit on §301 post-WTO sample
    fit = probit_fit_mle(s, y)
    if fit is None:
        print("[§301] ERROR: degenerate y, cannot fit probit", file=sys.stderr)
        sys.exit(1)
    ci = bootstrap_ci(s, y, n_boot=2000)
    fit.update(ci)

    print(f"[§301] fitted s* = {fit['s_star']:.3f}, k = {fit['k']:.3f}", file=sys.stderr)
    print(f"[§301] 95% CI s* = {fit['s_star_ci95']}, k = {fit['k_ci95']}", file=sys.stderr)
    print(f"[§301] p(0.2) = {fit['p_at_s_low']:.3f}, p(0.4) = {fit['p_at_s_high']:.3f}", file=sys.stderr)

    # Bayard-Elliott aggregate cross-check (1975-1994, n=72)
    p_low_be = BAYARD_ELLIOTT_AGGREGATE["concession_rate_no_retaliation"]
    p_high_be = BAYARD_ELLIOTT_AGGREGATE["concession_rate_retaliation_applied"]
    n_low_be = 72 - 12
    n_high_be = 12
    alpha_be, beta_be = aggregate_probit_from_two_bins(
        p_low=p_low_be, n_low=n_low_be,
        p_high=p_high_be, n_high=n_high_be,
        s_low=0.25, s_high=0.65,
    )
    k_be = beta_be
    print(f"[BE-1975-1994] p_low (no retal) = {p_low_be:.3f}, "
          f"p_high (retal applied) = {p_high_be:.3f}", file=sys.stderr)
    print(f"[BE-1975-1994] inferred alpha = {alpha_be:.3f}, k = {k_be:.3f}", file=sys.stderr)

    # WTO DSU cross-reference
    k_wto = None
    k_wto_ci = None
    if WTO_RESULTS_FILE.exists():
        try:
            with WTO_RESULTS_FILE.open("r", encoding="utf-8") as f:
                wto = json.load(f)
            k_wto = wto["fit"]["k"]
            k_wto_ci = wto["fit"]["k_ci95"]
        except Exception:  # noqa: BLE001
            pass

    # Sign-consistency analysis across THREE samples
    sign_post_wto = "negative" if fit["k"] < 0 else "positive" if fit["k"] > 0 else "zero"
    sign_be = "negative" if k_be < 0 else "positive" if k_be > 0 else "zero"
    sign_wto_dsu = "negative" if (k_wto is not None and k_wto < 0) else "positive" if (k_wto is not None and k_wto > 0) else "unknown"

    all_three_negative = (sign_post_wto == "negative" and sign_be == "negative" and sign_wto_dsu == "negative")
    sign_flip_in_section_301 = (sign_post_wto == "positive")

    if all_three_negative:
        verdict = ("STRUCTURAL-NEGATIVE-K-CONFIRMED: §301 post-WTO probit, "
                   "Bayard-Elliott 1975-1994 aggregate, and WTO DSU all yield "
                   "k<0. Endogenous-selection mechanism generalises beyond "
                   "WTO DSU subsample. Pre-reg k>0 expectation is rejected "
                   "at the cross-sample level.")
        verdict_short = "STRUCTURAL-NEGATIVE-K-CONFIRMED"
    elif sign_flip_in_section_301 and k_wto is not None and k_wto < 0:
        verdict = ("MIXED: §301 post-WTO yields k>0 (sign-aligned with "
                   "pre-reg) while WTO DSU yields k<0. Consistent with §301 "
                   "as exogenous instrument hypothesis. Caveat: §301 post-WTO "
                   f"n={n} is small; CI on k is wide.")
        verdict_short = "MIXED-INSTRUMENT-PARTIAL-RECOVERY"
    else:
        verdict = ("INCONCLUSIVE: cross-sample signs are heterogeneous "
                   "but no clean instrument-recovery pattern.")
        verdict_short = "INCONCLUSIVE"

    # Identification narrative quality flag
    # Did we actually find that retaliation_applied INCREASES concession
    # probability? (the §301-as-instrument prediction)
    delta_retal = p_y_given_retal_1 - p_y_given_retal_0
    instrument_sign_aligned = (delta_retal > 0)
    print(f"[§301] Δ P(concession) | retal_applied - no_retal = {delta_retal:+.3f}", file=sys.stderr)
    print(f"[§301] instrument-prediction sign aligned: {instrument_sign_aligned}", file=sys.stderr)

    out = {
        "system": "Schelling credible commitment — US §301 natural-instrument extension (SESSION-27)",
        "data_sources": [
            "CRS R46604 Table A-1 (Section 301 Investigations 1995-Present, cases 96-130)",
            "Bayard & Elliott (1994) Reciprocity and Retaliation in US Trade Policy (PIIE) aggregate counts via Cato PA-930 (2022)",
            "Horn-Mavroidis WTO DSU sample (n=23) via results_real_wto.json (SESSION-25)",
        ],
        "post_wto_sample": {
            "n": n,
            "p_low_obs": p_low_obs,
            "p_high_obs": p_high_obs,
            "n_low_bin": n_low_bin,
            "n_high_bin": n_high_bin,
            "p_y_given_retal_1": p_y_given_retal_1,
            "p_y_given_retal_0": p_y_given_retal_0,
            "n_retal_1": n_retal_1,
            "n_retal_0": n_retal_0,
            "delta_retal_minus_no_retal": delta_retal,
            "instrument_sign_aligned_with_schelling": bool(instrument_sign_aligned),
            "fit": fit,
        },
        "bayard_elliott_1975_1994_aggregate": {
            **BAYARD_ELLIOTT_AGGREGATE,
            "inferred_alpha_probit": float(alpha_be),
            "inferred_beta_probit": float(beta_be),
            "inferred_k": float(k_be),
            "s_low_assumed": 0.25,
            "s_high_assumed": 0.65,
            "note": ("Closed-form probit from two-bin grouped data with "
                     "s_low/s_high set to match §301-coding logic. "
                     "k_be is identified from cross-bin contrast only; "
                     "no within-bin variance available."),
        },
        "wto_dsu_cross_reference": {
            "k": k_wto,
            "k_ci95": k_wto_ci,
            "source": "results_real_wto.json (Horn-Mavroidis n=23)",
        },
        "sign_consistency": {
            "post_wto_section_301": sign_post_wto,
            "bayard_elliott_1975_1994": sign_be,
            "wto_dsu_horn_mavroidis": sign_wto_dsu,
            "all_three_negative": bool(all_three_negative),
            "sign_flip_in_section_301": bool(sign_flip_in_section_301),
        },
        "verdict": verdict,
        "verdict_short": verdict_short,
        "prereg_v5": PREREG_V5,
        "data_rows": rows,
    }

    with RESULTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"[wrote] {RESULTS_FILE}", file=sys.stderr)
    # Concise stdout summary
    summary = {k: v for k, v in out.items() if k != "data_rows"}
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
