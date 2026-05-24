"""
Block-bootstrap rerun of the Phase A2-Scheffer Kendall-tau test, accounting for
strong serial correlation in the daily DO residual time series.

The original analyze_regime_shift.py reports tau_AR1 = +0.284 with p = 1.6e-186.
That p-value is naive (assumes i.i.d. observations) and is numerically meaningless
on a serially-correlated daily series with lag-1 autocorrelation ~0.8-0.9.

We use a *moving block* bootstrap (Kunsch 1989; Politis & Romano 1994) with
block size l = 30 days (rough decorrelation scale). The null hypothesis is
"no monotonic trend in the rolling AR1 / Var indicator under preserved
serial structure": we resample blocks WITH REPLACEMENT from the deseasoned
residual series, recompute the rolling indicator, recompute Kendall tau, and
form a null distribution.

References:
- Kunsch HR (1989). "The jackknife and the bootstrap for general stationary
  observations." Ann. Stat. 17, 1217-1241.
- Politis DN, Romano JP (1994). "The stationary bootstrap." J. Am. Stat.
  Assoc. 89, 1303-1313.

Usage:
    python v4/scripts/scheffer_block_bootstrap.py [--n-boot 1000] [--block 30]

Output:
    Writes p_block_bootstrap fields back to
    v4/validation/scheffer-lake/lake_results.json (results.json sibling).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "v4" / "validation" / "scheffer-lake" / "lake_do_timeseries.jsonl"
RESULTS_PATH = REPO_ROOT / "v4" / "validation" / "scheffer-lake" / "lake_results.json"


def load_series() -> pd.DataFrame:
    """Load daily DO series, resample onto continuous daily grid."""
    rows = []
    with open(DATA_PATH) as f:
        for line in f:
            r = json.loads(line)
            rows.append({"date": r["date"], "do": r["do_mg_l"]})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    # Fill onto continuous daily grid; small gaps already interpolated upstream
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full)
    df["do"] = df["do"].interpolate(limit=7)
    return df


def deseason(series: pd.Series) -> pd.Series:
    """Remove DOY climatology + 60-day rolling drift."""
    s = series.copy()
    doy = s.index.dayofyear
    clim = s.groupby(doy).transform("mean")
    anomaly = s - clim
    rolling = anomaly.rolling(60, center=True, min_periods=15).mean()
    return anomaly - rolling


def rolling_ar1(x: np.ndarray, window: int = 365) -> np.ndarray:
    """Rolling lag-1 autocorrelation. Length = len(x) - window + 1."""
    n = len(x)
    out = np.full(n - window + 1, np.nan)
    for i in range(n - window + 1):
        seg = x[i : i + window]
        if np.isnan(seg).any():
            continue
        a = seg[:-1] - np.nanmean(seg[:-1])
        b = seg[1:] - np.nanmean(seg[1:])
        denom = np.sqrt(np.sum(a * a) * np.sum(b * b))
        if denom == 0:
            continue
        out[i] = np.sum(a * b) / denom
    return out


def rolling_var(x: np.ndarray, window: int = 365) -> np.ndarray:
    """Rolling variance. Length = len(x) - window + 1."""
    n = len(x)
    out = np.full(n - window + 1, np.nan)
    for i in range(n - window + 1):
        seg = x[i : i + window]
        if np.isnan(seg).any():
            continue
        out[i] = np.nanvar(seg)
    return out


def kendall_obs(indicator: np.ndarray):
    """Observed Kendall tau against time index."""
    valid = ~np.isnan(indicator)
    if valid.sum() < 30:
        return np.nan, np.nan
    t = np.arange(len(indicator))[valid]
    y = indicator[valid]
    tau, p = kendalltau(t, y)
    return tau, p


def moving_block_bootstrap(
    x: np.ndarray, block: int, n_boot: int, indicator_fn, seed: int = 42
) -> np.ndarray:
    """Standard moving-block bootstrap. Resample blocks, recompute indicator,
    recompute Kendall tau vs time. Returns array of tau_boot."""
    rng = np.random.default_rng(seed)
    n = len(x)
    n_blocks = int(np.ceil(n / block))
    starts_all = np.arange(0, n - block + 1)

    tau_boot = np.zeros(n_boot)
    for b in range(n_boot):
        # Draw random block starts with replacement, concat, truncate to n
        starts = rng.choice(starts_all, size=n_blocks, replace=True)
        chunks = [x[s : s + block] for s in starts]
        resamp = np.concatenate(chunks)[:n]
        ind = indicator_fn(resamp)
        tau, _ = kendall_obs(ind)
        tau_boot[b] = tau if not np.isnan(tau) else 0.0
    return tau_boot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--block", type=int, default=30)
    ap.add_argument("--window", type=int, default=365)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"[block-bootstrap] loading {DATA_PATH.name}")
    df = load_series()
    print(f"[block-bootstrap] series length {len(df)} days, "
          f"{df['do'].notna().sum()} non-NaN")

    resid = deseason(df["do"]).values
    # Drop leading/trailing NaN from rolling deseason
    valid_mask = ~np.isnan(resid)
    resid_clean = resid[valid_mask]
    print(f"[block-bootstrap] residual after deseason: {len(resid_clean)} points")

    # Observed
    ar1_obs = rolling_ar1(resid_clean, window=args.window)
    var_obs = rolling_var(resid_clean, window=args.window)

    tau_ar1_obs, p_ar1_naive = kendall_obs(ar1_obs)
    tau_var_obs, p_var_naive = kendall_obs(var_obs)
    print(f"[block-bootstrap] tau_AR1 obs = {tau_ar1_obs:.4f} "
          f"(naive p = {p_ar1_naive:.3e})")
    print(f"[block-bootstrap] tau_Var obs = {tau_var_obs:.4f} "
          f"(naive p = {p_var_naive:.3e})")

    # Block bootstrap on AR1
    print(f"[block-bootstrap] running {args.n_boot} block-bootstrap resamples, "
          f"block size {args.block}, window {args.window}...")
    tau_ar1_boot = moving_block_bootstrap(
        resid_clean, args.block, args.n_boot,
        lambda x: rolling_ar1(x, window=args.window), seed=args.seed,
    )
    tau_var_boot = moving_block_bootstrap(
        resid_clean, args.block, args.n_boot,
        lambda x: rolling_var(x, window=args.window), seed=args.seed + 1,
    )

    # Two-sided block p-value: fraction of |tau_boot| >= |tau_obs|
    n_ge_ar1 = int(np.sum(np.abs(tau_ar1_boot) >= np.abs(tau_ar1_obs)))
    n_ge_var = int(np.sum(np.abs(tau_var_boot) >= np.abs(tau_var_obs)))
    p_block_ar1 = (1 + n_ge_ar1) / (1 + args.n_boot)
    p_block_var = (1 + n_ge_var) / (1 + args.n_boot)

    print(f"[block-bootstrap] tau_AR1 block p = {p_block_ar1:.4g} "
          f"({n_ge_ar1}/{args.n_boot} |boot| >= |obs|)")
    print(f"[block-bootstrap] tau_Var block p = {p_block_var:.4g} "
          f"({n_ge_var}/{args.n_boot} |boot| >= |obs|)")
    print(f"[block-bootstrap] boot tau_AR1: mean={np.mean(tau_ar1_boot):+.4f} "
          f"std={np.std(tau_ar1_boot):.4f} "
          f"p5={np.percentile(tau_ar1_boot, 5):+.4f} "
          f"p95={np.percentile(tau_ar1_boot, 95):+.4f}")
    print(f"[block-bootstrap] boot tau_Var: mean={np.mean(tau_var_boot):+.4f} "
          f"std={np.std(tau_var_boot):.4f} "
          f"p5={np.percentile(tau_var_boot, 5):+.4f} "
          f"p95={np.percentile(tau_var_boot, 95):+.4f}")

    # Persist
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH) as f:
            results = json.load(f)
    else:
        results = {}

    results.setdefault("block_bootstrap", {}).update({
        "n_boot": args.n_boot,
        "block_size_days": args.block,
        "window_days": args.window,
        "tau_ar1_obs": float(tau_ar1_obs),
        "tau_var_obs": float(tau_var_obs),
        "p_naive_ar1": float(p_ar1_naive),
        "p_naive_var": float(p_var_naive),
        "p_block_bootstrap_ar1": float(p_block_ar1),
        "p_block_bootstrap_var": float(p_block_var),
        "boot_tau_ar1_mean": float(np.mean(tau_ar1_boot)),
        "boot_tau_ar1_std": float(np.std(tau_ar1_boot)),
        "boot_tau_ar1_p95": float(np.percentile(tau_ar1_boot, 95)),
        "boot_tau_var_mean": float(np.mean(tau_var_boot)),
        "boot_tau_var_std": float(np.std(tau_var_boot)),
        "boot_tau_var_p95": float(np.percentile(tau_var_boot, 95)),
        "rationale": (
            "Naive p-values assume i.i.d.; daily DO has lag-1 autocorrelation ~0.8-0.9. "
            "Block bootstrap preserves serial structure within blocks of "
            f"{args.block} days, resamples blocks with replacement, "
            f"recomputes rolling indicator + Kendall tau on each resample. "
            f"p_block reports the fraction of |tau_boot| >= |tau_obs| under "
            "the resampled null."
        ),
    })

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[block-bootstrap] wrote {RESULTS_PATH}")


if __name__ == "__main__":
    sys.exit(main())
