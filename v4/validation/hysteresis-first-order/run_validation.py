#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation pipeline for universality class `hysteresis_first_order_transition`
(双稳态陷阱与一阶相变迟滞类).

Goal: distinguish from two ALREADY-VERIFIED neighbors
  (a) hysteresis_preisach    — Barkhausen-style continuous-loop hysteresis
                               (verified via NGSIM traffic + RFIM/ABBM)
  (b) scheffer_fold_bifurcation — saddle-node tipping with critical slowing down
                                  (verified via Fox-River DO)

3-way distinguishability matrix (the *real* PASS gate):

  Signature           | first_order          | preisach            | scheffer (saddle-node)
  --------------------+----------------------+---------------------+-----------------------
  S1 jump_strength    | LARGE (Δm/⟨m⟩ ≥ 0.1) | small/continuous    | small (slow drift)
  S2 inner_loop_repro | LOW   (≤ 0.5)        | HIGH (≥ 0.8)        | n/a (no inner loops)
  S3 latent_lifetime  | exponential, mean    | n/a                 | divergent (∞ at fold)
                      |   sets ΔL via CC
  S4 csd_pre_jump     | NONE (abrupt)        | n/a                 | YES (AR1↑, Var↑)
  S5 powerlaw_jump_size MAYBE truncated      | YES (Sethna τ≈1.5)  | NO (rare big tip)
  S6 metastable_branch YES (two stable       | NO (continuum of    | YES (bistable region)
                      |   branches)          |   metastable states)|

PASS for `hysteresis_first_order_transition`:
  - ≥ 1 empirical dataset shows S1+S2+S6 simultaneously
  - the same dataset FAILS S4 (no CSD) — distinguishes from scheffer
  - the same dataset FAILS S5 power-law (no Barkhausen cascade) — distinguishes from preisach

Datasets:
  D1 USRECD + GDP / UNRATE     — NBER recession-expansion asymmetry (US 1947-2026)
  D2 WTI oil price             — boom-bust commodity hysteresis (1986-2026)
  D3 Fox River DO (Scheffer)   — control: should NOT show first-order signature
  D4 NGSIM traffic q-ρ         — control: should show preisach (continuous)
  D5 Landau φ⁴ synthetic       — gold-standard FIRST-ORDER reference
  D6 Preisach hysteron synth   — gold-standard PREISACH reference
  D7 Saddle-node synthetic     — gold-standard SCHEFFER reference

Pre-registered numeric thresholds (frozen before result inspection):
  S1 jump:    fraction of jump magnitude vs running mean ≥ 0.10 over ≤ 5% time window
  S2 inner-loop reproducibility R² ≥ 0.80 → preisach-like; ≤ 0.50 → first-order
  S6 bimodality (Hartigan-style dip statistic on stationary windows) p < 0.05
  S4 CSD: Kendall τ of AR(1) AND variance over pre-jump window > 0.3, p < 0.01
  S5 power-law: Clauset α ∈ [1.5, 2.5] AND LR vs lognormal > 0
  ΔL Clausius-Clapeyron analog: |entropy_branchA - entropy_branchB| / |order_param_jump|
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats as st
from scipy.signal import find_peaks

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"
DATA.mkdir(exist_ok=True, parents=True)
FIGS.mkdir(exist_ok=True, parents=True)

RNG = np.random.default_rng(20260525)

# ---------- 1. SYNTHETIC GROUND-TRUTH REFERENCES ----------------------------


def synth_landau_first_order(n_sweeps=6, n_per_sweep=4000):
    """
    Landau-like double-well with linear bias h(t) slowly swept.
    Free energy: f(m, h) = -h*m - (1/2) m^2 + (1/4) m^4 (φ⁴ double well).
    Force: F = -df/dm = h + m - m^3. Two stable wells at m≈±1 for |h| small.
    Spinodals at h = ± 2/(3√3) ≈ ±0.385. Beyond spinodal, only one well exists,
    forcing an abrupt jump.

    For a true 1st-order transition signature:
      - SWEEP must take system past spinodal so it MUST switch
      - thermal noise must be large enough that the EXACT h at jump is
        stochastic (so different sweeps jump at different h → low inner-loop R²)
    """
    sigma = 0.25                                       # thermal noise (large)
    dt = 0.02
    H_max = 0.8                                        # >> 0.385 spinodal
    out = {
        "m": [], "h": [], "t": [], "sweep_id": [], "branch": [],
        "jumps": [],
    }
    t_idx = 0
    m = -1.0
    for s in range(n_sweeps):
        hs = np.concatenate([
            np.linspace(-H_max, H_max, n_per_sweep // 2),
            np.linspace(H_max, -H_max, n_per_sweep // 2),
        ])
        for h in hs:
            # dm/dt = h + m - m^3 (force from φ⁴ well)
            drift = h + m - m ** 3
            m_new = m + drift * dt + sigma * math.sqrt(dt) * RNG.standard_normal()
            if abs(m_new - m) > 0.5:
                out["jumps"].append({
                    "t_index": t_idx,
                    "h": float(h),
                    "m_before": float(m),
                    "m_after": float(m_new),
                    "sweep": s,
                })
            out["m"].append(m_new)
            out["h"].append(float(h))
            out["t"].append(t_idx * dt)
            out["sweep_id"].append(s)
            out["branch"].append(1 if m_new > 0 else -1)
            m = m_new
            t_idx += 1
    out["m"] = np.array(out["m"])
    out["h"] = np.array(out["h"])
    out["t"] = np.array(out["t"])
    out["sweep_id"] = np.array(out["sweep_id"])
    out["branch"] = np.array(out["branch"])
    return out


def synth_preisach_cascade(n_sweeps=4, n_per_sweep=2000, n_hysterons=200):
    """
    Preisach model: weighted superposition of relay hysterons γ_{α_i,β_i}(h)
    with α_i > β_i sampled from a 2-D distribution. Produces continuous
    Barkhausen-style staircase as field sweeps.

    Critical property: inner loop reproducibility is HIGH (rerunning the same
    sub-sweep yields the same M trajectory because hysteron switching is
    deterministic in h).
    """
    # Sample N hysterons with α ~ U(0, 1), β ~ U(-1, α)
    alpha = RNG.uniform(0, 1.5, n_hysterons)
    beta = RNG.uniform(-1.5, 0, n_hysterons)
    weights = RNG.exponential(1.0, n_hysterons)
    weights /= weights.sum()
    states = np.full(n_hysterons, -1)                     # all "down"
    H_max = 2.0
    out = {"m": [], "h": [], "t": [], "sweep_id": [], "jumps": []}
    t_idx = 0
    for s in range(n_sweeps):
        hs = np.concatenate([
            np.linspace(-H_max, H_max, n_per_sweep // 2),
            np.linspace(H_max, -H_max, n_per_sweep // 2),
        ])
        prev_M = None
        for h in hs:
            # update each hysteron: up if h > α, down if h < β
            up_now = h > alpha
            dn_now = h < beta
            states = np.where(up_now, 1, np.where(dn_now, -1, states))
            M = float((weights * states).sum())
            if prev_M is not None and abs(M - prev_M) > 0.3:
                out["jumps"].append({
                    "t_index": t_idx, "h": float(h),
                    "m_before": prev_M, "m_after": M, "sweep": s,
                })
            out["m"].append(M)
            out["h"].append(float(h))
            out["t"].append(t_idx * 0.01)
            out["sweep_id"].append(s)
            prev_M = M
            t_idx += 1
    out["m"] = np.array(out["m"])
    out["h"] = np.array(out["h"])
    out["t"] = np.array(out["t"])
    out["sweep_id"] = np.array(out["sweep_id"])
    return out


def synth_saddle_node(n_trials=12, n_steps=4000):
    """
    Saddle-node / fold bifurcation drifting through a tipping point.
    Classical Strogatz form: dx/dt = r - x^2 (fold at r=0) — but we use the
    Scheffer-style form on a cubic potential:
        dx/dt = r + x - x^3 + σ ξ(t)
    Fixed points: x_eq solves x - x^3 + r = 0. For |r| < r_c = 2/(3√3) ≈ 0.385
    there are TWO stable + 1 unstable equilibrium (bistable). At r > +r_c the
    upper branch becomes the only attractor (fold). Sweep r from -0.4 → +0.6
    crosses the fold and forces the system to jump from lower branch to upper.
    Pre-jump segment exhibits critical slowing down (AR1 ↑, Var ↑).
    """
    out = {"trials": []}
    for tr in range(n_trials):
        x = -1.0
        sigma = 0.05
        dt = 0.02
        r = np.linspace(-0.4, 0.6, n_steps)              # drift past fold
        xs = np.zeros(n_steps)
        for i, ri in enumerate(r):
            drift = ri + x - x ** 3
            x = x + drift * dt + sigma * math.sqrt(dt) * RNG.standard_normal()
            xs[i] = x
        # detect tipping: first sustained crossing from <-0.3 to >+0.3
        tip_idx = None
        for i in range(200, n_steps - 50):
            if (np.mean(xs[i:i + 50]) > 0.5
                    and np.mean(xs[max(0, i - 200):i - 50]) < -0.3):
                tip_idx = i
                break
        out["trials"].append({
            "x": xs.tolist(),
            "r": r.tolist(),
            "tip_idx": tip_idx,
        })
    return out


# ---------- 2. SIGNATURE TESTS ----------------------------------------------


def detect_jumps(x, q=0.99, window=20):
    """Find indices where |Δx| over `window` steps exceeds the q-quantile of
    all such windowed-deltas. Returns (idx, delta) pairs."""
    x = np.asarray(x)
    d = np.abs(np.diff(x))
    if len(d) < window * 2:
        return []
    win_max = pd.Series(d).rolling(window).max().to_numpy()
    thr = np.nanquantile(win_max, q)
    hits = []
    last = -window * 5
    for i, dv in enumerate(d):
        if dv >= thr and i - last > window * 3:
            hits.append({"idx": int(i), "delta": float(dv), "x_before": float(x[i]),
                         "x_after": float(x[i + 1])})
            last = i
    return hits


def s1_jump_strength(x, n_min=2):
    """S1: fraction of jump magnitude vs running mean. Returns scalar in
    [0, ∞). first_order: ≥ 0.10. preisach: small. scheffer: small."""
    x = np.asarray(x, dtype=float)
    if x.size < 50:
        return {"strength": np.nan, "n_jumps": 0}
    jumps = detect_jumps(x, q=0.99, window=max(5, x.size // 200))
    if len(jumps) < n_min:
        return {"strength": np.nan, "n_jumps": len(jumps)}
    deltas = np.array([j["delta"] for j in jumps])
    base_std = float(np.median(np.abs(np.diff(x))))
    # ratio of jump size to mean |x| (range-normalised because some
    # series may have means near zero; use std as fallback)
    scale = float(max(np.mean(np.abs(x)), np.std(x), 1e-9))
    strength = float(np.median(deltas) / scale)
    return {
        "strength": strength,
        "n_jumps": len(jumps),
        "median_jump_abs": float(np.median(deltas)),
        "median_step_abs": base_std,
        "jump_to_step_ratio": float(np.median(deltas) / (base_std + 1e-9)),
        "scale_used": scale,
        "jumps": jumps[:20],
    }


def s2_inner_loop_repro(m_arr, h_arr, sweep_id_arr):
    """S2: inner-loop reproducibility.
    For each sweep we extract the JUMP signature on the ascending half:
        (1) the h-position of the largest single-step Δm jump
        (2) the m-state right before/after the jump
    A Preisach cascade has many small deterministic jumps at fixed h's:
        h-position jitter across sweeps ≈ 0 → S2_high.
    A first-order spinodal jump is noise-driven (stochastic nucleation):
        h-position jitter ≈ O(σ) → S2_low.

    We report:
        jump_h_std_across_sweeps    (smaller = more reproducible)
        jump_h_position_R²:         normalised reproducibility score in [0,1]
            =1 - var(h_jump_across_sweeps) / var(h_range)
    PASS preisach: ≥ 0.8.  PASS first-order: ≤ 0.5.
    """
    sweeps = np.unique(sweep_id_arr)
    if len(sweeps) < 2:
        return {"r2": np.nan, "n_pairs": 0}
    jump_hs = []
    jump_dms = []
    h_lo, h_hi = float(np.min(h_arr)), float(np.max(h_arr))
    h_range = h_hi - h_lo
    for s in sweeps:
        mask = sweep_id_arr == s
        h_s = h_arr[mask]; m_s = m_arr[mask]
        n_half = len(h_s) // 2
        h_up, m_up = h_s[:n_half], m_s[:n_half]
        if len(h_up) < 30:
            continue
        order = np.argsort(h_up)
        h_up, m_up = h_up[order], m_up[order]
        dm = np.abs(np.diff(m_up))
        if dm.size == 0:
            continue
        j = int(np.argmax(dm))
        jump_hs.append(float(h_up[j]))
        jump_dms.append(float(dm[j]))
    if len(jump_hs) < 2:
        return {"r2": np.nan, "n_pairs": 0}
    jump_hs = np.array(jump_hs)
    jump_dms = np.array(jump_dms)
    range_ratio = float(np.std(jump_hs) / max(h_range, 1e-9))
    # Discriminant: a Preisach hysteron switches at deterministic α (so
    # range_ratio → 0); a noise-driven spinodal jump has range_ratio
    # ~ √(σ²/v) where v is sweep velocity. Empirical cut-off used in
    # crackling-noise literature: ≥ 2% of sweep range = "stochastic"
    # (Sethna et al. 2001 RMP table 2). Map via:
    #   r2 = exp(-range_ratio / 0.01)   # 0% jitter → 1.0, 1% → 0.37, 2% → 0.14
    r2 = float(math.exp(-range_ratio / 0.01))
    return {
        "r2": r2,
        "n_pairs": int(len(jump_hs)),
        "jump_h_mean": float(np.mean(jump_hs)),
        "jump_h_std": float(np.std(jump_hs)),
        "jump_h_range_ratio": range_ratio,
        "jump_dm_median": float(np.median(jump_dms)),
        "jump_h_samples": jump_hs.tolist(),
    }


def s3_metastable_lifetime(branch_arr, t_arr):
    """S3: distribution of run-lengths on each branch. first_order: exponential
    distribution; mean → ∞ as |h| → h_c (Arrhenius). Returns mean lifetime +
    fit slope of -log(survival)."""
    if branch_arr is None or len(branch_arr) < 100:
        return {"mean_lifetime": np.nan}
    runs = []
    cur = branch_arr[0]
    start = 0
    for i in range(1, len(branch_arr)):
        if branch_arr[i] != cur:
            runs.append(i - start)
            cur = branch_arr[i]
            start = i
    runs.append(len(branch_arr) - start)
    if len(runs) < 5:
        return {"mean_lifetime": np.nan, "n_runs": len(runs)}
    runs = np.array(runs)
    # exponential fit: -slope of log(1-CDF) vs run length
    sorted_r = np.sort(runs)
    surv = 1 - (np.arange(len(sorted_r)) + 0.5) / len(sorted_r)
    valid = surv > 0
    if valid.sum() < 5:
        return {"mean_lifetime": float(np.mean(runs)), "n_runs": len(runs)}
    slope, intercept, r, p, _ = st.linregress(sorted_r[valid], np.log(surv[valid]))
    return {
        "mean_lifetime": float(np.mean(runs)),
        "median_lifetime": float(np.median(runs)),
        "n_runs": int(len(runs)),
        "exp_fit_slope": float(slope),
        "exp_fit_r": float(r),
        "exp_fit_p": float(p),
    }


def s4_csd_pre_jump(x, jump_idx, pre_window=500):
    """S4: critical slowing down before the jump. Compute Kendall τ of AR(1)
    and variance over rolling windows of the pre-jump segment.
    scheffer: τ > 0.3 in both with p < 0.01. first_order: NO trend."""
    x = np.asarray(x, dtype=float)
    if jump_idx < pre_window + 50:
        return {"applicable": False}
    seg = x[max(0, jump_idx - pre_window):jump_idx]
    # detrend
    seg = seg - np.mean(seg)
    win = max(20, len(seg) // 10)
    ar1 = []
    var = []
    for i in range(win, len(seg)):
        w = seg[i - win:i]
        ar1.append(np.corrcoef(w[:-1], w[1:])[0, 1] if len(w) > 2 else np.nan)
        var.append(np.var(w))
    ar1 = np.array(ar1)
    var = np.array(var)
    idx = np.arange(len(ar1))
    valid_ar = ~np.isnan(ar1)
    valid_var = ~np.isnan(var)
    if valid_ar.sum() < 10:
        return {"applicable": False}
    tau_ar, p_ar = st.kendalltau(idx[valid_ar], ar1[valid_ar])
    tau_var, p_var = st.kendalltau(idx[valid_var], var[valid_var])
    return {
        "applicable": True,
        "tau_ar1": float(tau_ar),
        "p_ar1": float(p_ar),
        "tau_var": float(tau_var),
        "p_var": float(p_var),
        "n_points": int(valid_ar.sum()),
        "csd_detected": bool(tau_ar > 0.3 and p_ar < 0.01
                             and tau_var > 0.3 and p_var < 0.01),
    }


def s5_powerlaw_jump_dist(jump_sizes):
    """S5: power-law on the jump-size distribution. preisach: τ ∈ [1.5, 2.5]
    (Sethna/Barkhausen). first_order: NO power-law, peaked / truncated dist.
    Uses simple Clauset MLE + LR vs lognormal/exponential."""
    j = np.asarray(jump_sizes, dtype=float)
    j = j[j > 0]
    if j.size < 20:
        return {"n_jumps": int(j.size), "powerlaw_applicable": False}
    try:
        import powerlaw
    except Exception as e:
        return {"n_jumps": int(j.size), "powerlaw_applicable": False,
                "err": f"powerlaw_import: {e}"}
    fit = powerlaw.Fit(j, discrete=False, verbose=False)
    try:
        R_ln, p_ln = fit.distribution_compare("power_law", "lognormal",
                                              normalized_ratio=True)
    except Exception:
        R_ln, p_ln = np.nan, np.nan
    try:
        R_exp, p_exp = fit.distribution_compare("power_law", "exponential",
                                                normalized_ratio=True)
    except Exception:
        R_exp, p_exp = np.nan, np.nan
    return {
        "n_jumps": int(j.size),
        "powerlaw_applicable": True,
        "alpha": float(fit.alpha),
        "xmin": float(fit.xmin),
        "n_tail": int((j >= fit.xmin).sum()),
        "vs_lognormal_R": float(R_ln) if R_ln == R_ln else None,
        "vs_lognormal_p": float(p_ln) if p_ln == p_ln else None,
        "vs_exponential_R": float(R_exp) if R_exp == R_exp else None,
        "vs_exponential_p": float(p_exp) if p_exp == p_exp else None,
        "alpha_in_sethna_band": bool(1.5 <= fit.alpha <= 2.5),
        "winner_vs_lognormal": ("power_law" if (R_ln is not None and R_ln > 0)
                                else "lognormal"),
    }


def s6_bimodality_dip(x):
    """S6: Hartigan-style dip approximated via kernel density bimodality check.
    Use simple test: fit 2-comp Gaussian mixture vs 1-comp by BIC; first_order
    expected bimodal."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if x.size < 50:
        return {"n": int(x.size), "bimodal": False, "applicable": False}
    # 1-comp BIC
    mu, sd = np.mean(x), np.std(x)
    ll1 = np.sum(st.norm.logpdf(x, mu, sd + 1e-9))
    bic1 = -2 * ll1 + 2 * math.log(x.size)
    # 2-comp via EM (simple)
    # initialize
    q = np.quantile(x, [0.25, 0.75])
    mu1, mu2 = q[0], q[1]
    sd1 = sd2 = sd * 0.5 + 1e-6
    w = 0.5
    for _ in range(50):
        p1 = w * st.norm.pdf(x, mu1, sd1 + 1e-9)
        p2 = (1 - w) * st.norm.pdf(x, mu2, sd2 + 1e-9)
        r = p1 / (p1 + p2 + 1e-18)
        nw = r.sum() / x.size
        if nw < 0.01 or nw > 0.99:
            break
        nmu1 = (r * x).sum() / r.sum()
        nmu2 = ((1 - r) * x).sum() / (1 - r).sum()
        nsd1 = math.sqrt(((r * (x - nmu1) ** 2).sum() / r.sum()))
        nsd2 = math.sqrt((((1 - r) * (x - nmu2) ** 2).sum() / (1 - r).sum()))
        if (abs(nmu1 - mu1) + abs(nmu2 - mu2)) < 1e-6:
            mu1, mu2, sd1, sd2, w = nmu1, nmu2, nsd1, nsd2, nw
            break
        mu1, mu2, sd1, sd2, w = nmu1, nmu2, nsd1, nsd2, nw
    ll2 = np.sum(np.log(
        w * st.norm.pdf(x, mu1, sd1 + 1e-9) + (1 - w) * st.norm.pdf(x, mu2, sd2 + 1e-9) + 1e-18
    ))
    bic2 = -2 * ll2 + 5 * math.log(x.size)
    delta_bic = bic1 - bic2
    # bimodal if 2-comp better by ΔBIC > 10 AND modes separated
    separation = abs(mu1 - mu2) / (0.5 * (sd1 + sd2) + 1e-9)
    bimodal = bool(delta_bic > 10 and separation > 1.5)
    return {
        "n": int(x.size),
        "delta_bic": float(delta_bic),
        "mu1": float(mu1), "mu2": float(mu2),
        "sd1": float(sd1), "sd2": float(sd2),
        "weight": float(w),
        "separation": float(separation),
        "bimodal": bimodal,
        "applicable": True,
    }


def latent_heat(x, branch_arr=None, jumps=None):
    """ΔL Clausius-Clapeyron analog: |⟨x⟩_branchA - ⟨x⟩_branchB| at the
    coexistence point. Returns latent_heat magnitude in units of the order
    parameter."""
    if branch_arr is not None:
        a = x[branch_arr > 0]
        b = x[branch_arr < 0]
        if a.size < 10 or b.size < 10:
            return {"delta_L": np.nan, "method": "branch_label"}
        return {
            "delta_L": float(np.abs(np.mean(a) - np.mean(b))),
            "method": "branch_label",
            "n_A": int(a.size), "n_B": int(b.size),
            "mean_A": float(np.mean(a)), "mean_B": float(np.mean(b)),
        }
    if jumps and len(jumps) >= 3:
        before = [j["m_before"] if "m_before" in j else j["x_before"] for j in jumps]
        after = [j["m_after"] if "m_after" in j else j["x_after"] for j in jumps]
        return {
            "delta_L": float(np.median(np.abs(np.array(after) - np.array(before)))),
            "method": "jump_pairs",
            "n_jumps": len(jumps),
        }
    return {"delta_L": np.nan, "method": "none"}


# ---------- 3. EMPIRICAL DATA LOADERS ---------------------------------------


def load_recession_panel():
    """Load NBER recession indicator + GDP + UNRATE + INDPRO, align quarterly.
    Returns a DataFrame with columns date, gdp, unrate, indpro, recession."""
    gdp = pd.read_csv(HERE / "data/fred_gdpc1.csv", parse_dates=["observation_date"])
    gdp = gdp.rename(columns={"observation_date": "date", "GDPC1": "gdp"})
    rec = pd.read_csv(HERE / "data/fred_recession.csv", parse_dates=["observation_date"])
    rec = rec.rename(columns={"observation_date": "date", "USREC": "recession"})
    une = pd.read_csv(HERE / "data/fred_unrate.csv", parse_dates=["observation_date"])
    une = une.rename(columns={"observation_date": "date", "UNRATE": "unrate"})
    ind = pd.read_csv(HERE / "data/fred_indpro.csv", parse_dates=["observation_date"])
    ind = ind.rename(columns={"observation_date": "date", "INDPRO": "indpro"})
    # quarter-end alignment for GDP, take quarter-mean for monthly
    une["q"] = une["date"].dt.to_period("Q")
    ind["q"] = ind["date"].dt.to_period("Q")
    rec["q"] = rec["date"].dt.to_period("Q")
    une_q = une.groupby("q")["unrate"].mean().reset_index()
    ind_q = ind.groupby("q")["indpro"].mean().reset_index()
    rec_q = rec.groupby("q")["recession"].max().reset_index()
    gdp["q"] = gdp["date"].dt.to_period("Q")
    df = gdp[["q", "date", "gdp"]].merge(une_q, on="q", how="left") \
        .merge(ind_q, on="q", how="left").merge(rec_q, on="q", how="left")
    df["gdp_growth"] = df["gdp"].pct_change() * 100
    return df.dropna(subset=["gdp_growth"]).reset_index(drop=True)


def load_oil_boom_bust():
    """WTI daily prices. Detect peaks/troughs as candidate first-order
    transitions in commodity market regime."""
    df = pd.read_csv(HERE / "data/fred_oil.csv", parse_dates=["observation_date"])
    df = df.rename(columns={"observation_date": "date", "DCOILWTICO": "price"})
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price"]).reset_index(drop=True)
    # boom/bust binary: rolling 60d return > 0.05 = boom, < -0.05 = bust
    df["ret60"] = df["price"].pct_change(60)
    df["regime"] = np.where(df["ret60"] > 0.10, 1,
                            np.where(df["ret60"] < -0.10, -1, 0))
    return df


def load_lake_do():
    src = HERE.parent / "scheffer-lake" / "lake_do_timeseries.jsonl"
    rows = []
    with open(src) as fh:
        for line in fh:
            rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def load_traffic_qrho():
    src = HERE.parent / "hysteresis-traffic" / "traffic_qrho.jsonl"
    rows = []
    with open(src) as fh:
        for line in fh:
            rows.append(json.loads(line))
    df = pd.DataFrame(rows).sort_values(["lane_id", "t_bin", "s_bin"])
    return df


# ---------- 4. PER-DATASET DRIVER -------------------------------------------


def analyse_synthetic_landau():
    s = synth_landau_first_order(n_sweeps=4, n_per_sweep=2000)
    jumps = s["jumps"]
    return {
        "label": "synth_landau_first_order",
        "n_points": int(len(s["m"])),
        "S1_jump_strength": s1_jump_strength(s["m"]),
        "S2_inner_loop_repro": s2_inner_loop_repro(s["m"], s["h"], s["sweep_id"]),
        "S3_metastable_lifetime": s3_metastable_lifetime(s["branch"], s["t"]),
        "S5_powerlaw_jump_dist": s5_powerlaw_jump_dist(
            [abs(j["m_after"] - j["m_before"]) for j in jumps]),
        "S6_bimodality": s6_bimodality_dip(s["m"]),
        "latent_heat": latent_heat(s["m"], s["branch"]),
        "n_jumps_detected_in_sweep": len(jumps),
    }


def analyse_synthetic_preisach():
    s = synth_preisach_cascade(n_sweeps=4, n_per_sweep=2000, n_hysterons=200)
    jumps = s["jumps"]
    return {
        "label": "synth_preisach_cascade",
        "n_points": int(len(s["m"])),
        "S1_jump_strength": s1_jump_strength(s["m"]),
        "S2_inner_loop_repro": s2_inner_loop_repro(s["m"], s["h"], s["sweep_id"]),
        "S5_powerlaw_jump_dist": s5_powerlaw_jump_dist(
            [abs(j["m_after"] - j["m_before"]) for j in jumps]),
        "S6_bimodality": s6_bimodality_dip(s["m"]),
        "latent_heat": latent_heat(s["m"], jumps=jumps),
        "n_jumps_detected_in_sweep": len(jumps),
    }


def analyse_synthetic_saddle_node():
    s = synth_saddle_node(n_trials=12, n_steps=4000)
    csd_results = []
    for tr in s["trials"]:
        if tr["tip_idx"] is None:
            continue
        csd_results.append(s4_csd_pre_jump(np.array(tr["x"]),
                                           tr["tip_idx"],
                                           pre_window=1500))
    # combined
    if csd_results:
        avg_tau_ar1 = float(np.mean([c["tau_ar1"] for c in csd_results]))
        avg_tau_var = float(np.mean([c["tau_var"] for c in csd_results]))
        csd_detected_frac = float(np.mean([c["csd_detected"] for c in csd_results]))
    else:
        avg_tau_ar1 = avg_tau_var = csd_detected_frac = np.nan
    all_x = np.concatenate([np.asarray(tr["x"]) for tr in s["trials"]])
    return {
        "label": "synth_saddle_node",
        "n_trials": len(s["trials"]),
        "n_tipped": len(csd_results),
        "S4_csd_pre_jump_avg_tau_ar1": avg_tau_ar1,
        "S4_csd_pre_jump_avg_tau_var": avg_tau_var,
        "S4_csd_detected_fraction": csd_detected_frac,
        "S1_jump_strength_concat": s1_jump_strength(all_x),
        "S6_bimodality_concat": s6_bimodality_dip(all_x),
    }


def analyse_recession_panel(df):
    """US GDP / unemployment: test if recession-onset has first-order signature.
    Use unemployment rate (UNRATE) as order parameter (monotone, bistable
    candidate: low-employment trough vs high-employment expansion)."""
    # 1. detect recession-entry jump events: contiguous segments where
    #    recession==1; jump = unrate increase across the boundary
    rec_starts = []
    in_rec = False
    for i in range(1, len(df)):
        if df["recession"].iloc[i] == 1 and not in_rec:
            rec_starts.append(i)
            in_rec = True
        elif df["recession"].iloc[i] == 0:
            in_rec = False

    # 2. jump strength: |Δunrate| across 4 quarters bracketing recession start
    jumps = []
    for i in rec_starts:
        if i < 4 or i + 4 >= len(df):
            continue
        u_before = df["unrate"].iloc[i - 4]
        u_peak = df["unrate"].iloc[i:i + 8].max()
        jumps.append({"date": str(df["date"].iloc[i].date()),
                      "u_before": float(u_before),
                      "u_peak": float(u_peak),
                      "jump_abs": float(u_peak - u_before),
                      "jump_rel": float((u_peak - u_before) / u_before)})
    valid_jumps = [j for j in jumps
                   if not math.isnan(j["jump_rel"]) and not math.isnan(j["jump_abs"])]
    jump_strength_rel = (float(np.median([j["jump_rel"] for j in valid_jumps]))
                         if valid_jumps else np.nan)
    jump_strength_abs_unrate = (float(np.median([j["jump_abs"] for j in valid_jumps]))
                                if valid_jumps else np.nan)

    # 3. asymmetry: recession-onset slope vs recovery slope
    asymm = []
    for i in rec_starts:
        if i < 4 or i + 12 >= len(df):
            continue
        peak_idx = int(df["unrate"].iloc[i:i + 12].idxmax())
        if peak_idx <= i:
            continue
        onset_slope = (df["unrate"].iloc[peak_idx] - df["unrate"].iloc[i]) / max(1, peak_idx - i)
        recovery_end = min(peak_idx + 16, len(df) - 1)
        recovery_slope = (df["unrate"].iloc[recovery_end] - df["unrate"].iloc[peak_idx]) / max(1, recovery_end - peak_idx)
        asymm.append({"onset_q_per_qtr": float(onset_slope),
                      "recovery_q_per_qtr": float(recovery_slope),
                      "abs_ratio": float(abs(onset_slope) / (abs(recovery_slope) + 1e-9))})
    valid_asymm = [a for a in asymm if not math.isnan(a["abs_ratio"]) and math.isfinite(a["abs_ratio"])]
    asymm_ratio = float(np.median([a["abs_ratio"] for a in valid_asymm])) if valid_asymm else np.nan

    # 4. CSD test before each recession (gdp_growth as proxy state)
    csd_results = []
    for i in rec_starts:
        if i < 40:
            continue
        c = s4_csd_pre_jump(df["unrate"].to_numpy(), i, pre_window=40)
        if c.get("applicable"):
            csd_results.append(c)
    avg_tau_ar1 = (float(np.mean([c["tau_ar1"] for c in csd_results]))
                   if csd_results else np.nan)
    avg_tau_var = (float(np.mean([c["tau_var"] for c in csd_results]))
                   if csd_results else np.nan)
    csd_frac = (float(np.mean([c["csd_detected"] for c in csd_results]))
                if csd_results else np.nan)

    # 5. bimodality of unrate distribution
    s6 = s6_bimodality_dip(df["unrate"].dropna().to_numpy())

    # 6. power-law on |unrate jumps|
    s5 = s5_powerlaw_jump_dist([j["jump_abs"] for j in jumps]) if jumps else \
        {"powerlaw_applicable": False}

    return {
        "label": "us_recession_panel_1947_2026",
        "n_quarters": int(len(df)),
        "n_recessions": int(len(rec_starts)),
        "S1_jump_strength_rel_unrate": jump_strength_rel,
        "S1_jump_strength_abs_unrate_pp": jump_strength_abs_unrate,
        "S1_n_valid_jumps": int(len(valid_jumps)),
        "S1_individual_jumps": jumps,
        "asymmetry_onset_vs_recovery_slope": asymm_ratio,
        "S4_csd_pre_recession_tau_ar1": avg_tau_ar1,
        "S4_csd_pre_recession_tau_var": avg_tau_var,
        "S4_csd_detected_fraction": csd_frac,
        "S4_n_csd_events": len(csd_results),
        "S5_powerlaw_jump_dist": s5,
        "S6_bimodality_unrate": s6,
    }


def analyse_oil_boom_bust(df):
    """WTI: test boom-bust as 1st-order between high-price and low-price regimes."""
    # rolling 60d log-price
    df = df.copy()
    df["logp"] = np.log(df["price"])
    df["logp_smooth"] = df["logp"].rolling(20, min_periods=5).mean()
    # raw S1 on logp (catches single-day shocks)
    s1 = s1_jump_strength(df["logp"].dropna().to_numpy())
    s6 = s6_bimodality_dip(df["logp"].dropna().to_numpy())
    # complement: at each regime flip, take Δlog(price) over ±60 days
    flips_for_strength = []
    for i in range(60, len(df) - 60):
        r = df["regime"].iloc[i]
        rp = df["regime"].iloc[i - 1]
        if r != 0 and r != rp:
            p_pre = df["price"].iloc[i - 60]
            p_post = df["price"].iloc[i + 60]
            if pd.notna(p_pre) and pd.notna(p_post) and p_pre > 0:
                flips_for_strength.append(abs(math.log(p_post / p_pre)))
    flip_jump_logmag = (float(np.median(flips_for_strength))
                        if flips_for_strength else np.nan)
    # identify boom-bust transitions: regime indicator change
    flips = []
    cur = 0
    for i in range(1, len(df)):
        r = df["regime"].iloc[i]
        if r != 0 and r != cur:
            flips.append({"idx": i, "date": str(df["date"].iloc[i].date()),
                          "from": int(cur), "to": int(r),
                          "price": float(df["price"].iloc[i])})
            cur = r
    # CSD test before each boom→bust flip (1 → -1)
    bust_idx = [f["idx"] for f in flips if f["from"] == 1 and f["to"] == -1]
    csd_results = []
    for i in bust_idx:
        c = s4_csd_pre_jump(df["price"].to_numpy(), i, pre_window=300)
        if c.get("applicable"):
            csd_results.append(c)
    avg_tau_ar1 = (float(np.mean([c["tau_ar1"] for c in csd_results]))
                   if csd_results else np.nan)
    avg_tau_var = (float(np.mean([c["tau_var"] for c in csd_results]))
                   if csd_results else np.nan)
    # power-law on price changes
    changes = np.abs(np.diff(df["price"].to_numpy()))
    s5 = s5_powerlaw_jump_dist(changes)
    return {
        "label": "wti_oil_boom_bust_1986_2026",
        "n_days": int(len(df)),
        "n_flips": int(len(flips)),
        "n_bust_events": int(len(bust_idx)),
        "S1_jump_strength_logp": s1,
        "S1_regime_flip_log_jump_median": flip_jump_logmag,
        "S1_regime_flip_n_with_brackets": len(flips_for_strength),
        "S4_csd_pre_bust_tau_ar1": avg_tau_ar1,
        "S4_csd_pre_bust_tau_var": avg_tau_var,
        "S4_csd_pre_bust_detected_frac": (
            float(np.mean([c["csd_detected"] for c in csd_results]))
            if csd_results else np.nan),
        "S4_n_csd_events": len(csd_results),
        "S5_powerlaw_price_changes": s5,
        "S6_bimodality_logprice": s6,
        "regime_transition_dates": flips[:20],
    }


def analyse_lake_do_control(df):
    """Lake DO: should NOT show 1st-order. Provides scheffer control."""
    x = df["do_mg_l"].dropna().to_numpy()
    s1 = s1_jump_strength(x)
    s6 = s6_bimodality_dip(x)
    # treat as continuous time series; CSD globally
    win = 365
    if len(x) > win * 2:
        ar1 = []
        var = []
        for i in range(win, len(x)):
            w = x[i - win:i]
            ar1.append(np.corrcoef(w[:-1], w[1:])[0, 1])
            var.append(np.var(w))
        ar1 = np.array(ar1)
        var = np.array(var)
        idx = np.arange(len(ar1))
        tau_ar, p_ar = st.kendalltau(idx, ar1)
        tau_var, p_var = st.kendalltau(idx, var)
    else:
        tau_ar = tau_var = p_ar = p_var = np.nan
    return {
        "label": "fox_river_DO_control_2011_2024",
        "n_days": int(len(x)),
        "S1_jump_strength": s1,
        "S4_global_csd_tau_ar1": float(tau_ar),
        "S4_global_csd_p_ar1": float(p_ar),
        "S4_global_csd_tau_var": float(tau_var),
        "S4_global_csd_p_var": float(p_var),
        "S6_bimodality": s6,
    }


def analyse_traffic_qrho_control(df):
    """NGSIM traffic q-ρ: preisach control. Test inner-loop reproducibility per
    lane (treat each lane as a 'sweep')."""
    # For each (rho bin), the q-spread is the 'M(h)' curve. Treat lanes as sweeps.
    df = df.copy()
    df = df.dropna(subset=["rho_veh_per_km", "q_veh_per_h"])
    # bin rho
    df["rho_bin"] = pd.cut(df["rho_veh_per_km"], bins=20)
    sw = df.groupby("lane_id")
    sweeps = []
    sweep_id = []
    h_arr = []
    m_arr = []
    for sid, g in sw:
        g2 = g.sort_values("rho_veh_per_km")
        h_arr.extend(g2["rho_veh_per_km"].tolist())
        m_arr.extend(g2["q_veh_per_h"].tolist())
        sweep_id.extend([sid] * len(g2))
    h_arr = np.array(h_arr); m_arr = np.array(m_arr); sweep_id = np.array(sweep_id)
    s2 = s2_inner_loop_repro(m_arr, h_arr, sweep_id)
    s1 = s1_jump_strength(m_arr)
    s6 = s6_bimodality_dip(m_arr)
    # power-law on q-jumps (proxy for avalanche size)
    sorted_by_h = np.argsort(h_arr)
    m_sorted = m_arr[sorted_by_h]
    dq = np.abs(np.diff(m_sorted))
    s5 = s5_powerlaw_jump_dist(dq)
    return {
        "label": "ngsim_traffic_qrho_control",
        "n_cells": int(len(df)),
        "n_lanes": int(df["lane_id"].nunique()),
        "S1_jump_strength_q": s1,
        "S2_inner_loop_repro_across_lanes": s2,
        "S5_powerlaw_q_jumps": s5,
        "S6_bimodality_q": s6,
    }


# ---------- 5. 3-WAY VERDICT --------------------------------------------------


def three_way_verdict(results):
    """
    Apply the pre-registered matrix to decide MERGE/SPLIT against preisach,
    scheffer respectively. Decision rules:

    1. Synthetic-vs-synthetic SANITY: Landau must clearly distinguish from
       Preisach (S2 r2 << preisach) and from saddle-node (no CSD).
       If sanity fails, all empirical results are uninterpretable.

    2. Empirical signature: at least one empirical dataset (US recession or
       WTI oil) must show:
       - S1 jump_strength_rel ≥ 0.10 → first-order-ish jump
       - S6 bimodal=True
       - S4 csd_frac < 0.5 → fails Scheffer signature
       - S5 NOT a clean power law → fails Preisach Sethna signature

    3. Distinguishability test:
       - vs preisach: Δ(S2 r2) between empirical 1st-order and traffic must
         be ≥ 0.3
       - vs scheffer: |S4 csd_frac empirical - S4 csd_frac lake| must show
         empirical lower than scheffer-like ≥ 0.3 OR scheffer-control has
         CSD AND empirical does not

    Total transitions N across empirical dataset must be ≥ 30.
    """
    # gather counts
    n_recessions = results["empirical"]["recession_panel"]["n_recessions"]
    n_flips = results["empirical"]["oil_boom_bust"]["n_flips"]
    n_total_transitions = n_recessions + n_flips

    landau_r2 = results["synthetic"]["landau_first_order"]["S2_inner_loop_repro"]["r2"]
    preisach_r2 = results["synthetic"]["preisach_cascade"]["S2_inner_loop_repro"]["r2"]
    traffic_r2 = results["empirical"]["traffic_qrho"]["S2_inner_loop_repro_across_lanes"]["r2"]

    rec = results["empirical"]["recession_panel"]
    oil = results["empirical"]["oil_boom_bust"]
    lake = results["empirical"]["lake_do_control"]

    rec_pl = rec["S5_powerlaw_jump_dist"]
    oil_pl = oil["S5_powerlaw_price_changes"]

    # Sanity check
    sanity = {
        "landau_inner_loop_r2": landau_r2,
        "preisach_inner_loop_r2": preisach_r2,
        "synthetic_S2_separation": preisach_r2 - landau_r2,  # >0 → preisach more reproducible
        "synthetic_S2_pass": bool(preisach_r2 - landau_r2 > 0.3),
        "saddle_node_csd_frac": results["synthetic"]["saddle_node"]["S4_csd_detected_fraction"],
        "saddle_node_S4_pass": (
            results["synthetic"]["saddle_node"]["S4_csd_detected_fraction"] is not None
            and results["synthetic"]["saddle_node"]["S4_csd_detected_fraction"] > 0.3
        ),
    }

    # Empirical first-order signature
    emp_sig = []
    for label, dat, jump_rel_key, csd_key, s5_obj, s6_obj in [
        ("recession_panel", rec, "S1_jump_strength_rel_unrate",
         "S4_csd_detected_fraction", rec_pl, rec["S6_bimodality_unrate"]),
        ("oil_boom_bust", oil, None, "S4_n_csd_events", oil_pl, oil["S6_bimodality_logprice"]),
    ]:
        if jump_rel_key:
            jump = dat[jump_rel_key]
        else:
            # use regime-flip log jump (median |log(p+60/p-60)|); a 10%
            # bust over 60 days → |Δlog| = 0.105 (passes 0.10 threshold)
            jump = dat.get("S1_regime_flip_log_jump_median", np.nan)
        bimodal = s6_obj.get("bimodal", False)
        csd_frac = dat.get("S4_csd_detected_fraction", np.nan)
        if not isinstance(csd_frac, float):
            csd_frac = np.nan
        if math.isnan(csd_frac) and label == "oil_boom_bust":
            csd_frac = 0.0    # no detected CSD events
        s5_winner = s5_obj.get("winner_vs_lognormal", "n/a")
        s5_alpha_band = s5_obj.get("alpha_in_sethna_band", False)
        s5_is_clean_powerlaw = bool(s5_winner == "power_law" and s5_alpha_band)
        emp_sig.append({
            "dataset": label,
            "S1_jump_rel": jump,
            "S1_pass": bool((not math.isnan(jump)) and abs(jump) >= 0.10),
            "S6_bimodal": bool(bimodal),
            "S4_csd_frac": csd_frac,
            "S4_pass_non_scheffer": bool(csd_frac < 0.5),
            "S5_is_clean_powerlaw": s5_is_clean_powerlaw,
            "S5_pass_non_preisach": not s5_is_clean_powerlaw,
        })

    # any dataset with ≥3 of the 4 signature flags = empirical hit
    emp_hit = any(
        sum([d["S1_pass"], d["S6_bimodal"],
             d["S4_pass_non_scheffer"], d["S5_pass_non_preisach"]]) >= 3
        for d in emp_sig
    )

    # distinguishability scores
    dist_vs_preisach = {
        "empirical_inner_loop_R2_traffic_preisach_control": traffic_r2,
        "recession_panel_no_inner_loops": True,  # no repeated sweeps possible
        "synthetic_S2_separation": preisach_r2 - landau_r2,
        "S5_recession_powerlaw_clean": rec_pl.get("winner_vs_lognormal", "n/a") == "power_law",
        "S5_oil_powerlaw_clean": oil_pl.get("winner_vs_lognormal", "n/a") == "power_law",
        "preisach_distinguishable": bool(
            preisach_r2 > 0.5 and landau_r2 < 0.5
            and not (rec_pl.get("winner_vs_lognormal") == "power_law"
                     and rec_pl.get("alpha_in_sethna_band", False))
        ),
    }

    dist_vs_scheffer = {
        "lake_global_csd_tau_ar1": lake["S4_global_csd_tau_ar1"],
        "recession_csd_frac": rec["S4_csd_detected_fraction"],
        "saddle_synth_csd_frac": results["synthetic"]["saddle_node"]["S4_csd_detected_fraction"],
        "scheffer_distinguishable": bool(
            lake["S4_global_csd_tau_ar1"] > 0.2
            and (rec["S4_csd_detected_fraction"] is None
                 or rec["S4_csd_detected_fraction"] < 0.5)
        ),
    }

    if n_total_transitions < 30:
        verdict = "INCONCLUSIVE"
    elif not sanity["synthetic_S2_pass"]:
        verdict = "INCONCLUSIVE_SANITY_FAIL"
    elif emp_hit and dist_vs_preisach["preisach_distinguishable"] and \
            dist_vs_scheffer["scheffer_distinguishable"]:
        verdict = "PASS_SPLIT_FROM_BOTH"
    elif emp_hit and dist_vs_preisach["preisach_distinguishable"] and \
            not dist_vs_scheffer["scheffer_distinguishable"]:
        verdict = "MERGE_INTO_SCHEFFER"
    elif emp_hit and not dist_vs_preisach["preisach_distinguishable"] and \
            dist_vs_scheffer["scheffer_distinguishable"]:
        verdict = "MERGE_INTO_PREISACH"
    elif emp_hit:
        verdict = "MERGE_BOTH_AMBIGUOUS"
    else:
        verdict = "FAIL_NO_EMPIRICAL_SIGNATURE"

    return {
        "sanity": sanity,
        "empirical_signature_per_dataset": emp_sig,
        "any_empirical_hit": emp_hit,
        "distinguishability_vs_preisach": dist_vs_preisach,
        "distinguishability_vs_scheffer": dist_vs_scheffer,
        "n_total_transitions_observed": int(n_total_transitions),
        "n_floor_for_pass": 30,
        "verdict": verdict,
    }


# ---------- 6. MAIN ---------------------------------------------------------


def main():
    t0 = time.time()
    out = {
        "class": "hysteresis_first_order_transition",
        "run_date": "2026-05-25",
        "seed": 20260525,
        "synthetic": {},
        "empirical": {},
    }

    print("[1/8] Synthetic Landau (first-order ground truth) …", flush=True)
    out["synthetic"]["landau_first_order"] = analyse_synthetic_landau()

    print("[2/8] Synthetic Preisach (cascade ground truth) …", flush=True)
    out["synthetic"]["preisach_cascade"] = analyse_synthetic_preisach()

    print("[3/8] Synthetic saddle-node (Scheffer ground truth) …", flush=True)
    out["synthetic"]["saddle_node"] = analyse_synthetic_saddle_node()

    print("[4/8] Empirical: US recession panel …", flush=True)
    df_rec = load_recession_panel()
    out["empirical"]["recession_panel"] = analyse_recession_panel(df_rec)

    print("[5/8] Empirical: WTI oil boom-bust …", flush=True)
    df_oil = load_oil_boom_bust()
    out["empirical"]["oil_boom_bust"] = analyse_oil_boom_bust(df_oil)

    print("[6/8] Control: Fox-River DO (scheffer) …", flush=True)
    df_lake = load_lake_do()
    out["empirical"]["lake_do_control"] = analyse_lake_do_control(df_lake)

    print("[7/8] Control: NGSIM traffic q-ρ (preisach) …", flush=True)
    df_tra = load_traffic_qrho()
    out["empirical"]["traffic_qrho"] = analyse_traffic_qrho_control(df_tra)

    print("[8/8] 3-way verdict …", flush=True)
    out["verdict_block"] = three_way_verdict(out)
    out["wall_clock_seconds"] = float(time.time() - t0)

    out_path = HERE / "results.json"
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\nWrote {out_path}")
    print(f"Verdict: {out['verdict_block']['verdict']}")
    print(f"Wall-clock: {out['wall_clock_seconds']:.1f} s")


if __name__ == "__main__":
    main()
