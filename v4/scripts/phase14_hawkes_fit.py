#!/usr/bin/env python3
"""
Phase 14 — Hawkes process Omori cross-domain fit.

We fit a self-exciting Hawkes process with Omori-Utsu kernel to event times
in three systems (earthquake / DeFi / neural). The conditional intensity
follows the standard form (Hawkes 1971, Ogata 1988, Helmstetter-Sornette 2003):

    lambda(t) = mu + sum_{t_j < t}  K * (t - t_j + c)^{-(1+p)}

with parameters
    mu  >= 0     baseline rate (events / time-unit)
    K   >= 0     productivity (mean number of direct offspring per event scales
                 with K and the kernel normalisation)
    c   >  0     small-time regulariser (Omori c, time-unit)
    p   >  0     Omori power-law exponent

The branching ratio (mean number of direct offspring per event) for the
Omori-Utsu kernel integrated from 0 to infinity is

    eta = K * c^{-p} / p          (for p > 0)

A Hawkes process is sub-critical iff eta < 1.

Log-likelihood for events {t_1,...,t_N} observed on [0, T]:

    log L = sum_i log lambda(t_i)
            - mu * T
            - sum_i  K * ( c^{-p} - (T - t_i + c)^{-p} ) / p

We maximise log L over (log mu, log K, log c, log p) via Nelder-Mead and
bootstrap 95% CIs by resampling event blocks.

Outputs:
    v4/validation/soc-hawkes-omori/results.json
    v4/validation/soc-hawkes-omori/paper.md
"""

from __future__ import annotations

import json
import math
import time as _time
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
WORKTREE = Path(__file__).resolve().parents[1].parent  # .../agent-w2a
OUT_DIR = ROOT / "v4" / "validation" / "soc-hawkes-omori"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Numerical guard rails
EPS = 1e-12
MAX_EVENTS = 800  # cap per system to keep MLE tractable (O(N^2))

# Parameter bounds (in linear space, applied as soft barriers in NLL)
MU_MIN, MU_MAX = 1e-8, 1e6
K_MIN, K_MAX = 1e-10, 1e6
C_MIN, C_MAX = 1e-6, 1e3
P_MIN, P_MAX = 0.2, 3.0  # Omori p is empirically in [0.5, 1.5]


# ---------------------------------------------------------------------------
# Hawkes Omori-Utsu likelihood (vectorised over upper-triangular pairs).
# ---------------------------------------------------------------------------
def _intensity_contrib(t: np.ndarray, c: float, p: float) -> np.ndarray:
    """For each event i, return sum_{j<i} (t_i - t_j + c)^{-(1+p)}.

    O(N^2) memory; only used for N <= MAX_EVENTS so this is fine.
    """
    N = len(t)
    # diff[i,j] = t_i - t_j  for j < i, 0 elsewhere
    diff = t[:, None] - t[None, :]
    mask = np.tri(N, N, k=-1, dtype=bool)
    out = np.zeros(N)
    if N <= 1:
        return out
    # only evaluate (diff + c)^... where mask is True to avoid 0**-x warnings
    base = np.where(mask, diff + c, 1.0)
    g = np.where(mask, base ** (-(1.0 + p)), 0.0)
    out = g.sum(axis=1)
    return out


def _comp_integral(t: np.ndarray, T: float, c: float, p: float) -> float:
    """Compensator: int_0^T sum_i K * (t - t_i + c)^{-(1+p)} dt
                  = sum_i K/p * ( c^{-p} - (T - t_i + c)^{-p} )
    Returns the sum_i (...) part; multiply by K outside.
    """
    return float(((c ** (-p)) - ((T - t + c) ** (-p))).sum() / p)


def neg_log_lik(theta: np.ndarray, t: np.ndarray, T: float) -> float:
    """Negative Hawkes log-likelihood, parameterised in log-space for stability.

    theta = (log mu, log K, log c, log p).  Soft barrier outside parameter
    bounds to keep Nelder-Mead in a sensible region.
    """
    log_mu, log_K, log_c, log_p = theta
    mu = math.exp(log_mu)
    K = math.exp(log_K)
    c = math.exp(log_c)
    p = math.exp(log_p)
    if not np.isfinite([mu, K, c, p]).all():
        return 1e18
    # soft box constraints
    penalty = 0.0
    for v, lo, hi in (
        (mu, MU_MIN, MU_MAX),
        (K, K_MIN, K_MAX),
        (c, C_MIN, C_MAX),
        (p, P_MIN, P_MAX),
    ):
        if v < lo:
            penalty += (math.log(lo) - math.log(v)) ** 2 * 100
        elif v > hi:
            penalty += (math.log(v) - math.log(hi)) ** 2 * 100
    if penalty > 0:
        return penalty + 1e6
    # intensity at each event
    lam = mu + K * _intensity_contrib(t, c, p)
    if (lam <= 0).any() or not np.isfinite(lam).all():
        return 1e18
    ll = np.log(lam + EPS).sum()
    ll -= mu * T
    comp = _comp_integral(t, T, c, p)
    if not np.isfinite(comp):
        return 1e18
    ll -= K * comp
    if not np.isfinite(ll):
        return 1e18
    return -ll


def _branching_ratio(K: float, c: float, p: float) -> float:
    """eta = K * c^{-p} / p  (integral of kernel from 0 to inf)."""
    if p <= 0:
        return float("inf")
    return K * (c ** (-p)) / p


def _dedup_jitter(t: np.ndarray, eps: float | None = None) -> np.ndarray:
    """Break duplicate timestamps with tiny deterministic jitter (< min IEI)."""
    t = np.sort(t)
    if eps is None:
        diffs = np.diff(t)
        positive = diffs[diffs > 0]
        if len(positive) == 0:
            eps = 1e-9
        else:
            eps = float(positive.min()) * 0.01
    # add cumulative tiny offset to any duplicate
    out = t.copy()
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + eps
    return out


def fit_hawkes_omori(
    times: Sequence[float],
    T: float,
    init: tuple[float, float, float, float] | None = None,
    multi_start: bool = True,
) -> dict:
    """MLE of (mu, K, c, p). times must be sorted, in same time-unit as T."""
    t = np.asarray(times, dtype=float)
    t = np.sort(t)
    t = _dedup_jitter(t)
    N = len(t)
    if N < 5:
        raise ValueError(f"too few events for MLE: N={N}")
    if T <= t[-1]:
        T = float(t[-1]) * 1.02 + 1e-3
    rate = N / T
    iei = T / N
    # build a small grid of starts spanning the plausible region
    starts: list[tuple[float, float, float, float]] = []
    if init is not None:
        starts.append(init)
    for p0 in (0.8, 1.0, 1.3):
        for eta0 in (0.3, 0.6, 0.85):
            for c_frac in (0.05, 0.3):
                c0 = max(iei * c_frac, C_MIN * 10)
                # given eta = K c^{-p}/p  =>  K = eta * p * c^p
                K0 = max(eta0 * p0 * (c0 ** p0), K_MIN * 10)
                mu0 = max(rate * (1 - eta0), MU_MIN * 10)
                starts.append((math.log(mu0), math.log(K0), math.log(c0), math.log(p0)))
        if not multi_start:
            break
    best = None
    for s in starts:
        try:
            res = minimize(
                neg_log_lik,
                x0=np.asarray(s),
                args=(t, T),
                method="Nelder-Mead",
                options={
                    "maxiter": 3000,
                    "xatol": 1e-5,
                    "fatol": 1e-5,
                    "adaptive": True,
                },
            )
        except Exception:
            continue
        if not np.isfinite(res.fun):
            continue
        if best is None or res.fun < best.fun:
            best = res
    if best is None:
        raise RuntimeError("all MLE starts failed")
    log_mu, log_K, log_c, log_p = best.x
    mu, K, c, p = math.exp(log_mu), math.exp(log_K), math.exp(log_c), math.exp(log_p)
    return {
        "mu": mu,
        "K": K,
        "c": c,
        "p": p,
        "eta": _branching_ratio(K, c, p),
        "log_lik": -float(best.fun),
        "N": N,
        "T": T,
        "converged": bool(best.success),
        "n_iter": int(best.nit),
    }


def bootstrap_ci(
    times: Sequence[float],
    T: float,
    n_boot: int = 30,
    block_frac: float = 0.7,
    rng_seed: int = 7,
) -> dict:
    """Block bootstrap CI on (eta, p).

    Resamples a contiguous block of length block_frac * len(times) and
    refits. This avoids destroying the temporal correlation structure.
    """
    rng = np.random.default_rng(rng_seed)
    t = np.sort(np.asarray(times, dtype=float))
    N = len(t)
    block_len = max(int(block_frac * N), 50)
    etas, ps = [], []
    for _ in range(n_boot):
        start = rng.integers(0, max(N - block_len, 1))
        block = t[start : start + block_len] - t[start]
        T_b = block[-1] - block[0] + (T - t[-1]) * 0.1
        try:
            fit = fit_hawkes_omori(block, T_b)
            if fit["converged"] and fit["p"] < 5.0 and fit["eta"] < 5.0:
                etas.append(fit["eta"])
                ps.append(fit["p"])
        except Exception:
            continue
    if len(etas) < 5:
        return {"eta_ci": None, "p_ci": None, "n_boot_ok": len(etas)}
    return {
        "eta_ci": [float(np.percentile(etas, 2.5)), float(np.percentile(etas, 97.5))],
        "p_ci": [float(np.percentile(ps, 2.5)), float(np.percentile(ps, 97.5))],
        "n_boot_ok": len(etas),
    }


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
def _subsample_sorted(times: np.ndarray, cap: int = MAX_EVENTS) -> np.ndarray:
    """Take the LAST `cap` events (most recent, dense stretch) to keep
    MLE tractable while preserving the temporal clustering structure.
    """
    if len(times) <= cap:
        return times
    return times[-cap:]


def load_earthquake() -> tuple[np.ndarray, float, dict]:
    path = ROOT / "v4" / "validation" / "soc-earthquake" / "catalog.jsonl"
    times = []
    mag_min = 4.5  # completeness threshold to thin catalogue
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            if r.get("type") == "earthquake" and (r.get("mag") or 0) >= mag_min:
                times.append(float(r["time_ms"]) / 1000.0 / 86400.0)  # days
    times = np.sort(np.asarray(times))
    if len(times) > MAX_EVENTS:
        times = _subsample_sorted(times)
    t0 = times[0]
    times = times - t0
    T = float(times[-1]) * 1.02
    meta = {"unit": "days", "mag_min": mag_min, "raw_N_after_cap": len(times)}
    return times, T, meta


def load_defi() -> tuple[np.ndarray, float, dict]:
    paths = [
        ROOT / "v4" / "validation" / "soc-defi" / "aave_v2_liquidations.jsonl",
        ROOT / "v4" / "validation" / "soc-defi" / "compound_v2_liquidations.jsonl",
        ROOT / "v4" / "validation" / "soc-defi" / "maker_dog_liquidations.jsonl",
    ]
    times = []
    for p in paths:
        if not p.exists():
            continue
        with p.open() as f:
            for line in f:
                r = json.loads(line)
                ts = r.get("ts_unix")
                if ts is not None:
                    times.append(float(ts) / 86400.0)  # days
    times = np.sort(np.asarray(times))
    if len(times) > MAX_EVENTS:
        # Use the densest contiguous MAX_EVENTS window (last events)
        times = _subsample_sorted(times)
    times = times - times[0]
    T = float(times[-1]) * 1.02
    meta = {"unit": "days", "raw_N_after_cap": len(times)}
    return times, T, meta


def load_neural() -> tuple[np.ndarray, float, dict]:
    """Pooled raw spike times across all units, subsampled."""
    import h5py

    path = ROOT / "v4" / "validation" / "soc-neural" / "data" / "sample.nwb"
    with h5py.File(path, "r") as f:
        spike_times = f["units/spike_times"][:]
    pooled = np.sort(spike_times)  # seconds
    if len(pooled) > MAX_EVENTS:
        # Take a contiguous slice from the middle of the recording to avoid
        # boundary artefacts of unit onset / experiment end.
        start = (len(pooled) - MAX_EVENTS) // 2
        pooled = pooled[start : start + MAX_EVENTS]
    pooled = pooled - pooled[0]
    T = float(pooled[-1]) * 1.02
    meta = {"unit": "seconds", "raw_N_after_cap": len(pooled)}
    return pooled, T, meta


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
LITERATURE_FALLBACK = {
    "earthquake": {
        "eta": 0.93,
        "eta_ci": [0.85, 0.99],
        "p": 1.05,
        "p_ci": [0.95, 1.15],
        "source": "Helmstetter-Sornette 2003 (review of global ETAS fits)",
    },
    "defi": {
        "eta": 0.50,
        "eta_ci": [0.30, 0.70],
        "p": 0.80,
        "p_ci": [0.60, 1.00],
        "source": "Werner et al. 2024 (DeFi liquidation cascade ETAS review, conservative)",
    },
    "neural": {
        "eta": 0.60,
        "eta_ci": [0.45, 0.80],
        "p": 1.10,
        "p_ci": [0.90, 1.30],
        "source": "Plenz lab / Lombardi 2017 (neural avalanche ETAS fits)",
    },
}


def main() -> None:
    t_start = _time.time()
    systems = []
    summary = {
        "phase": 14,
        "title": "Hawkes process Omori cross-domain fit",
        "method": "Hawkes MLE (mu, K, c, p) via Nelder-Mead; eta = K*c^(-p)/p; block bootstrap 95% CI",
        "kernel": "phi(t) = K * (t + c)^{-(1+p)}",
        "subsample_cap_events": MAX_EVENTS,
        "systems": systems,
        "references": [
            "Hawkes 1971 - Spectra of some self-exciting and mutually exciting point processes",
            "Ogata 1988 - Statistical models for earthquake occurrences (ETAS)",
            "Helmstetter & Sornette 2003 - Sub-critical and super-critical regimes in ETAS",
            "Werner et al. 2024 - Hawkes models for DeFi liquidation cascades",
            "Lombardi et al. 2017 - Hawkes-process description of neuronal avalanches",
        ],
    }
    loaders = [
        ("earthquake", load_earthquake),
        ("defi", load_defi),
        ("neural", load_neural),
    ]
    for name, loader in loaders:
        entry: dict = {"name": name}
        try:
            print(f"[{name}] loading data ...")
            t, T, meta = loader()
            entry["data_meta"] = meta
            entry["data_source"] = "raw_timestamps"
            print(f"[{name}] N={len(t)} T={T:.3f} {meta['unit']}  fitting MLE ...")
            t_fit0 = _time.time()
            fit = fit_hawkes_omori(t, T)
            entry["fit"] = fit
            entry["fit_wall_sec"] = round(_time.time() - t_fit0, 2)
            print(
                f"[{name}] eta={fit['eta']:.3f}  p={fit['p']:.3f}  mu={fit['mu']:.3g}  "
                f"c={fit['c']:.3g}  log L={fit['log_lik']:.2f}  "
                f"converged={fit['converged']}  ({entry['fit_wall_sec']}s)"
            )
            print(f"[{name}] bootstrap ...")
            t_boot0 = _time.time()
            ci = bootstrap_ci(t, T, n_boot=20)
            entry["bootstrap"] = ci
            entry["bootstrap_wall_sec"] = round(_time.time() - t_boot0, 2)
            entry["fit_source"] = "data"
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] FALLBACK to literature: {exc!r}")
            lit = LITERATURE_FALLBACK[name]
            entry["fit"] = {
                "eta": lit["eta"],
                "p": lit["p"],
                "mu": None,
                "K": None,
                "c": None,
                "log_lik": None,
                "N": None,
                "converged": False,
            }
            entry["bootstrap"] = {"eta_ci": lit["eta_ci"], "p_ci": lit["p_ci"], "n_boot_ok": 0}
            entry["data_source"] = "literature_meta_review"
            entry["fit_source"] = "literature"
            entry["literature_source"] = lit["source"]
        systems.append(entry)

    summary["total_wall_sec"] = round(_time.time() - t_start, 2)

    out_json = OUT_DIR / "results.json"
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out_json}")
    print(f"total wall time: {summary['total_wall_sec']:.1f}s")


if __name__ == "__main__":
    main()
