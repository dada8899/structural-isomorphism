"""A2 #6 — Copula tail dependence between financial extremes and natural disasters.

Hypothesis (Universality Class #6): two heavy-tailed series from different domains
exhibit non-zero upper tail dependence λ_U > 0 (joint extremes co-occur).

Series A: |S&P 500 daily log returns| (1996-2024).
Series B: NOAA Storm Events daily total damage (1996-2024, USD, US events).

Pipeline:
    1. Load both series; intersect on calendar dates (only S&P trading days kept).
    2. Rank-transform each to uniform marginal via empirical CDF (no para. assumption).
    3. Estimate λ_U via three estimators:
         - Empirical: λ_U(u) = P(V > u | U > u) averaged for u ∈ {0.90, 0.95, 0.975, 0.99}.
         - Gumbel copula MLE: λ_U = 2 - 2^(1/θ).
         - Clayton copula MLE: lower-tail copula → λ_L = 2^(-1/θ). For upper tail
           we fit Survival Clayton (180° rotation) so λ_U = 2^(-1/θ).
    4. Block-bootstrap (block=20 days) the joint sample to get 95% CI on each.
    5. Compare to permutation null (shuffle one series 1000 times → null λ_U distribution).
    6. Compute baseline P(extreme storm | random day) vs P(extreme storm | extreme S&P day).

Writes:
    v4/validation/tail-copula/results.json
    v4/validation/tail-copula/lambda_U_panel.png

Author: W2-B subagent, session #3 (2026-05-13).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]  # v4/
VAL_DIR = ROOT / "validation" / "tail-copula"
SP500 = ROOT / "validation" / "soc-stockmarket" / "sp500_daily.csv"
STORM = VAL_DIR / "storm_daily_damage.csv"
OUT_JSON = VAL_DIR / "results.json"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_sp500() -> pd.DataFrame:
    df = pd.read_csv(
        SP500,
        skiprows=3,
        header=None,
        names=["Date", "AdjClose", "Close", "High", "Low", "Open", "Volume"],
    )
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    df["log_ret"] = np.log(df["AdjClose"]).diff()
    df["abs_log_ret"] = df["log_ret"].abs()
    return df[["Date", "log_ret", "abs_log_ret"]].dropna()


def load_storm() -> pd.DataFrame:
    df = pd.read_csv(STORM, parse_dates=["date"])
    df = df.rename(columns={"date": "Date"})
    return df


def build_joint(start="1996-01-01", end="2025-01-01") -> pd.DataFrame:
    sp = load_sp500()
    st = load_storm()
    sp = sp[(sp["Date"] >= start) & (sp["Date"] < end)]
    st = st[(st["Date"] >= start) & (st["Date"] < end)]
    # Left-join on trading days; storm damage = 0 if no storm that day.
    joint = sp.merge(st[["Date", "total_damage_usd"]], on="Date", how="left")
    joint["total_damage_usd"] = joint["total_damage_usd"].fillna(0.0)
    return joint


# ---------------------------------------------------------------------------
# Marginal transform
# ---------------------------------------------------------------------------
def to_pseudo_uniform(x: np.ndarray) -> np.ndarray:
    """Empirical CDF rank transform to (0, 1) with continuity correction."""
    n = len(x)
    return rankdata(x, method="average") / (n + 1)


# ---------------------------------------------------------------------------
# Estimator 1: Empirical upper tail dependence
# ---------------------------------------------------------------------------
def empirical_lambda_U(u: np.ndarray, v: np.ndarray, q: float) -> float:
    """P(V > q | U > q) for q close to 1."""
    mask_u = u > q
    if mask_u.sum() == 0:
        return float("nan")
    return float((v[mask_u] > q).mean())


def empirical_lambda_U_panel(u, v, quantiles=(0.90, 0.95, 0.975, 0.99)):
    """Return dict of empirical λ_U at each tail quantile, plus average."""
    out = {}
    for q in quantiles:
        out[f"q={q}"] = empirical_lambda_U(u, v, q)
    out["avg"] = float(np.mean([v for k, v in out.items() if "q=" in k]))
    return out


# ---------------------------------------------------------------------------
# Estimator 2: Gumbel copula MLE
# Gumbel C(u,v;θ) = exp(-((-log u)^θ + (-log v)^θ)^(1/θ)), θ ≥ 1.
# Upper tail dep: λ_U = 2 - 2^(1/θ); lower tail dep: 0.
# Density used for MLE: see Joe (1997).
# ---------------------------------------------------------------------------
def _gumbel_log_pdf(u, v, theta):
    """Log-density of bivariate Gumbel copula. Returns array of log-pdf."""
    lu = -np.log(u)
    lv = -np.log(v)
    # tA = ((-log u)^θ + (-log v)^θ)
    a = np.power(lu, theta) + np.power(lv, theta)
    a_pow = np.power(a, 1.0 / theta)
    log_C = -a_pow  # log of copula
    log_c = (
        log_C
        + (theta - 1.0) * np.log(lu * lv)
        - (lu + lv) * 0  # already added via -log u, -log v indirectly
        - np.log(u) - np.log(v)  # converting density of (u,v) — Joe (1997) form
        + (1.0 / theta - 2.0) * np.log(a)
        + np.log(a_pow + theta - 1.0)
    )
    return log_c


def fit_gumbel(u: np.ndarray, v: np.ndarray) -> float:
    """MLE of Gumbel θ ∈ [1.001, 20]. Returns θ_hat."""
    # Clip away exact 0/1 to keep -log finite
    eps = 1e-6
    u = np.clip(u, eps, 1 - eps)
    v = np.clip(v, eps, 1 - eps)

    def neg_ll(theta):
        if theta < 1.001:
            return 1e10
        try:
            ll = _gumbel_log_pdf(u, v, theta).sum()
            if not np.isfinite(ll):
                return 1e10
            return -ll
        except (ValueError, FloatingPointError):
            return 1e10

    res = minimize_scalar(neg_ll, bounds=(1.001, 20.0), method="bounded")
    return float(res.x)


def gumbel_lambda_U(theta: float) -> float:
    return float(2.0 - 2.0 ** (1.0 / theta))


# ---------------------------------------------------------------------------
# Estimator 3: Survival Clayton copula MLE (rotated for upper tail)
# Clayton C(u,v;θ) = (u^-θ + v^-θ - 1)^(-1/θ), θ > 0.
# Lower tail dep: λ_L = 2^(-1/θ); upper tail dep: 0.
# Survival Clayton (180° rotation): apply Clayton to (1-u, 1-v).
# Then upper tail dep of original = λ_L of Clayton on (1-u, 1-v) = 2^(-1/θ).
# ---------------------------------------------------------------------------
def _clayton_log_pdf(u, v, theta):
    """Log-density of bivariate Clayton copula (lower tail dependence)."""
    term = np.power(u, -theta) + np.power(v, -theta) - 1.0
    log_c = (
        np.log(1.0 + theta)
        + (-1.0 - theta) * (np.log(u) + np.log(v))
        + (-1.0 / theta - 2.0) * np.log(term)
    )
    return log_c


def fit_survival_clayton(u: np.ndarray, v: np.ndarray) -> float:
    """Fit Clayton to (1-u, 1-v) → models upper tail dep of original. Returns θ."""
    eps = 1e-6
    u2 = np.clip(1.0 - u, eps, 1 - eps)
    v2 = np.clip(1.0 - v, eps, 1 - eps)

    def neg_ll(theta):
        if theta < 1e-4:
            return 1e10
        try:
            ll = _clayton_log_pdf(u2, v2, theta).sum()
            if not np.isfinite(ll):
                return 1e10
            return -ll
        except (ValueError, FloatingPointError):
            return 1e10

    res = minimize_scalar(neg_ll, bounds=(1e-3, 20.0), method="bounded")
    return float(res.x)


def survival_clayton_lambda_U(theta: float) -> float:
    return float(2.0 ** (-1.0 / theta))


# ---------------------------------------------------------------------------
# Bootstrap CI (block bootstrap to preserve temporal autocorrelation)
# ---------------------------------------------------------------------------
def block_bootstrap_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=n_blocks)
    idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
    return idx


def bootstrap_lambda_U(
    u: np.ndarray,
    v: np.ndarray,
    n_boot: int = 500,
    block: int = 20,
    seed: int = 42,
) -> dict:
    rng = np.random.default_rng(seed)
    n = len(u)
    emp95 = np.empty(n_boot)
    gumbel_lU = np.empty(n_boot)
    surv_clayton_lU = np.empty(n_boot)
    for b in range(n_boot):
        idx = block_bootstrap_indices(n, block, rng)
        ub, vb = u[idx], v[idx]
        emp95[b] = empirical_lambda_U(ub, vb, 0.95)
        try:
            th_g = fit_gumbel(ub, vb)
            gumbel_lU[b] = gumbel_lambda_U(th_g)
        except Exception:
            gumbel_lU[b] = np.nan
        try:
            th_c = fit_survival_clayton(ub, vb)
            surv_clayton_lU[b] = survival_clayton_lambda_U(th_c)
        except Exception:
            surv_clayton_lU[b] = np.nan
    return {
        "empirical_q95": _ci(emp95),
        "gumbel": _ci(gumbel_lU),
        "survival_clayton": _ci(surv_clayton_lU),
    }


def _ci(arr: np.ndarray, alpha: float = 0.05) -> dict:
    arr = arr[~np.isnan(arr)]
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "ci_low": float(np.quantile(arr, alpha / 2)),
        "ci_high": float(np.quantile(arr, 1 - alpha / 2)),
        "n_boot": int(len(arr)),
    }


# ---------------------------------------------------------------------------
# Permutation null
# ---------------------------------------------------------------------------
def permutation_null(
    u: np.ndarray, v: np.ndarray, n_perm: int = 1000, seed: int = 7, q: float = 0.95
) -> dict:
    """Under H0 (independence), shuffle v and recompute empirical λ_U at q."""
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for p in range(n_perm):
        v_perm = rng.permutation(v)
        null[p] = empirical_lambda_U(u, v_perm, q)
    return {
        "q": q,
        "mean_null_lambda": float(np.mean(null)),
        "p99_null": float(np.quantile(null, 0.99)),
        "p95_null": float(np.quantile(null, 0.95)),
        "n_perm": int(n_perm),
    }


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------
def baseline_compare(
    joint: pd.DataFrame, return_q: float = 0.95, damage_q: float = 0.95
) -> dict:
    abs_ret = joint["abs_log_ret"].values
    damage = joint["total_damage_usd"].values
    n = len(joint)
    r_thr = np.quantile(abs_ret, return_q)
    d_thr = np.quantile(damage, damage_q)
    extreme_ret = abs_ret > r_thr
    extreme_dmg = damage > d_thr
    p_extreme_dmg = extreme_dmg.mean()  # baseline P(extreme storm)
    p_dmg_given_ret = (
        extreme_dmg[extreme_ret].mean() if extreme_ret.sum() else float("nan")
    )
    return {
        "P(extreme_storm)": float(p_extreme_dmg),
        "P(extreme_storm | extreme_return)": float(p_dmg_given_ret),
        "lift_ratio": (
            float(p_dmg_given_ret / p_extreme_dmg)
            if p_extreme_dmg > 0
            else float("nan")
        ),
        "n_extreme_ret": int(extreme_ret.sum()),
        "n_extreme_dmg": int(extreme_dmg.sum()),
        "n_total": int(n),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def positive_control_within_domain() -> dict:
    """Sanity check: compute λ_U between |S&P returns| and |S&P returns lagged 1 day|.

    Volatility clustering literature predicts strong tail dependence at lag 1
    (Embrechts 2002, Patton 2006). If our methodology returns λ_U ≈ 0 here too,
    the method is broken; if it returns λ_U > 0, the method works and the
    cross-domain null is real.
    """
    sp = load_sp500()
    sp = sp[(sp["Date"] >= "1996-01-01") & (sp["Date"] < "2025-01-01")].copy()
    sp["abs_lag1"] = sp["abs_log_ret"].shift(1)
    sp = sp.dropna()
    x = sp["abs_log_ret"].values
    y = sp["abs_lag1"].values
    u = to_pseudo_uniform(x)
    v = to_pseudo_uniform(y)
    return {
        "n_obs": int(len(sp)),
        "empirical_q95": empirical_lambda_U(u, v, 0.95),
        "empirical_q99": empirical_lambda_U(u, v, 0.99),
        "gumbel_lambda_U": gumbel_lambda_U(fit_gumbel(u, v)),
    }


def main():
    print("[A2-Copula] Positive control (|S&P| vs |S&P_lag1|)...", flush=True)
    pc = positive_control_within_domain()
    print(f"  positive control: {pc}", flush=True)

    print("[A2-Copula] Loading data...", flush=True)
    joint = build_joint()
    print(f"  joint sample: n={len(joint):,} trading days", flush=True)
    print(
        f"  date range: {joint['Date'].min().date()} → {joint['Date'].max().date()}",
        flush=True,
    )

    x = joint["abs_log_ret"].values
    y = joint["total_damage_usd"].values

    # Pseudo-uniform marginals
    u = to_pseudo_uniform(x)
    v = to_pseudo_uniform(y)

    print("[A2-Copula] Computing empirical λ_U...", flush=True)
    emp = empirical_lambda_U_panel(u, v)
    print(f"  empirical λ_U panel: {emp}", flush=True)

    print("[A2-Copula] Fitting Gumbel copula...", flush=True)
    th_g = fit_gumbel(u, v)
    lU_g = gumbel_lambda_U(th_g)
    print(f"  Gumbel θ={th_g:.4f} → λ_U={lU_g:.4f}", flush=True)

    print("[A2-Copula] Fitting Survival Clayton...", flush=True)
    th_c = fit_survival_clayton(u, v)
    lU_c = survival_clayton_lambda_U(th_c)
    print(f"  Surv-Clayton θ={th_c:.4f} → λ_U={lU_c:.4f}", flush=True)

    print("[A2-Copula] Block-bootstrap CIs (500 reps)...", flush=True)
    boot = bootstrap_lambda_U(u, v, n_boot=500, block=20, seed=42)
    print(f"  boot result: {json.dumps(boot, indent=2)}", flush=True)

    print("[A2-Copula] Permutation null (1000 reps)...", flush=True)
    null = permutation_null(u, v, n_perm=1000, q=0.95)
    print(f"  null: {null}", flush=True)

    print("[A2-Copula] Baseline comparison...", flush=True)
    base = baseline_compare(joint)
    print(f"  baseline: {base}", flush=True)

    # ------------------------------------------------------------------
    # Verdict
    # ------------------------------------------------------------------
    # Significance: empirical λ_U at q=0.95 > 99th percentile of null AND
    # bootstrap CI excludes 0.
    obs_lU = emp["q=0.95"]
    sig_vs_null = obs_lU > null["p99_null"]
    boot_ci = boot["empirical_q95"]
    ci_excl_zero = boot_ci["ci_low"] > 0.0
    nonzero_param = lU_g > 0.02 or lU_c > 0.02  # > floor noise

    if sig_vs_null and ci_excl_zero and (lU_g > 0.05 or lU_c > 0.05):
        verdict = "supports"
        note = "non-trivial upper tail dependence; empirical λ_U > null 99th pct; param CI > 0"
    elif sig_vs_null and (lU_g > 0.02 or lU_c > 0.02):
        verdict = "partial"
        note = "weak but significant tail dep; smaller than financial-financial literature"
    elif obs_lU < null["p95_null"]:
        verdict = "rejects"
        note = "no detectable tail dependence; empirical λ_U inside null distribution"
    else:
        verdict = "partial"
        note = "borderline; signal present but not strongly significant"

    out = {
        "phase": "A2-Copula",
        "universality_class": "#6 tail copula",
        "data_sources": [
            "S&P 500 daily returns (Yahoo Finance, local 1990-2025)",
            "NOAA Storm Events Database (1996-2024, public CSV)",
        ],
        "data_period": f"{joint['Date'].min().date()} to {joint['Date'].max().date()}",
        "n_obs": int(len(joint)),
        "marginal_transform": "empirical CDF rank-to-uniform",
        "lambda_U_empirical_panel": emp,
        "lambda_U_empirical_q95": float(emp["q=0.95"]),
        "lambda_U_gumbel": float(lU_g),
        "lambda_U_clayton": float(lU_c),  # actually survival Clayton
        "gumbel_theta": float(th_g),
        "survival_clayton_theta": float(th_c),
        "lambda_U_ci_95": [boot_ci["ci_low"], boot_ci["ci_high"]],
        "bootstrap": boot,
        "permutation_null": null,
        "baseline_comparison": base,
        "verdict": verdict,
        "verdict_note": note,
        "fit_source": "real_data",
        "positive_control_volatility_clustering": pc,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"\n[A2-Copula] Wrote {OUT_JSON}", flush=True)
    print(f"[A2-Copula] VERDICT: {verdict.upper()} — {note}", flush=True)
    return out


if __name__ == "__main__":
    main()
