"""
analyze_regime_shift.py — early-warning-indicator analysis for fold-bifurcation
regime shifts (Scheffer 2001, 2009 Nature; Dakos et al. 2008 PNAS).

Pipeline:
  1. Load lake_do_timeseries.jsonl, align onto continuous daily index, interpolate
     small gaps (<=7 days), seasonally detrend (annual cycle removed via 365-day
     rolling mean), then high-pass via 60-day rolling-mean residual.
  2. Changepoint detection (CUSUM on standardized series). Cluster within 90 days.
  3. Rolling-window early-warning indicators (window = 365 days):
       - lag-1 autocorrelation  AR(1) — expected to RISE before tipping
       - variance               — expected to RISE before tipping
       - skewness               — flips sign as system approaches tip
  4. For each detected changepoint, regress indicator vs time over the
     [shift - 730d, shift] pre-window. Kendall's tau gives a robust
     monotonic-trend test. Positive significant tau on AR1 + variance
     = classical critical-slowing-down signature.
  5. Emit lake_results.json + lake_panel.png + lake_timeseries.png.

NOT a SOC pipeline — Scheffer-class indicators are completely distinct
from power-law / cascade analysis used in soc-* validations.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import kendalltau, skew

ROOT = Path(__file__).resolve().parent
JSONL_PATH = ROOT / "lake_do_timeseries.jsonl"
RESULTS_PATH = ROOT / "lake_results.json"
PANEL_PNG = ROOT / "lake_panel.png"
TS_PNG = ROOT / "lake_timeseries.png"

WINDOW_DAYS = 365          # rolling window for indicators
# CUSUM tuned conservatively: k=0.5 std slack, h=15 std threshold; this
# suppresses seasonal-residual flicker (k=0.5 / h=5 yielded ~39 events, too
# many for the Scheffer regime-shift framing). h=15 keeps only persistent
# mean-level departures that survive >~1 month of consistent z-score >0.5.
CUSUM_K = 0.5
CUSUM_H = 15.0
CLUSTER_GAP = 180          # days; merge changepoints closer than this (was 90)
PRE_WINDOW = 730           # days before shift to test for indicator rise


# ---------------------------------------------------------------------------
# Loading & preprocessing
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """Return dates (datetime[]), do_values, meta."""
    dates: list[datetime] = []
    vals: list[float] = []
    site_name = None
    site_code = None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        dates.append(datetime.fromisoformat(r["date"]))
        vals.append(float(r["do_mg_l"]))
        site_name = site_name or r.get("site_name")
        site_code = site_code or r.get("site_code")
    return (np.array(dates), np.array(vals, dtype=float),
            {"site_name": site_name, "site_code": site_code,
             "n_raw": len(vals)})


def align_daily(dates: np.ndarray, vals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Reindex onto continuous daily grid; small gaps (<=7d) linearly interpolated,
    larger gaps remain NaN."""
    d0, d1 = dates.min(), dates.max()
    n_days = (d1 - d0).days + 1
    grid = np.array([d0 + timedelta(days=i) for i in range(n_days)])
    out = np.full(n_days, np.nan)
    # map raw points
    for d, v in zip(dates, vals):
        idx = (d - d0).days
        out[idx] = v
    # interpolate gaps <=7 days
    isnan = np.isnan(out)
    if isnan.any():
        idx_valid = np.where(~isnan)[0]
        if len(idx_valid) >= 2:
            # find gaps
            i = 0
            while i < len(out):
                if np.isnan(out[i]):
                    # gap start
                    j = i
                    while j < len(out) and np.isnan(out[j]):
                        j += 1
                    gap_len = j - i
                    if gap_len <= 7 and i > 0 and j < len(out):
                        # linear interp
                        v0, v1 = out[i-1], out[j]
                        for k in range(i, j):
                            out[k] = v0 + (v1 - v0) * (k - i + 1) / (gap_len + 1)
                    i = j
                else:
                    i += 1
    return grid, out


def seasonal_detrend(x: np.ndarray, period: int = 365) -> np.ndarray:
    """Remove climatology (mean DO by day-of-year over full series).

    DO has strong seasonal cycle (winter ice-on vs summer stratification);
    EWS theory requires regime-shift signal independent of cycle.
    """
    n = len(x)
    doy = np.arange(n) % period
    climo = np.full(period, np.nan)
    for d in range(period):
        sel = (doy == d) & ~np.isnan(x)
        if sel.sum() >= 3:
            climo[d] = np.nanmean(x[sel])
    # fill missing climo days via simple interpolation
    valid = ~np.isnan(climo)
    if valid.sum() < period:
        idx_v = np.where(valid)[0]
        climo = np.interp(np.arange(period), idx_v, climo[idx_v])
    return x - climo[doy]


def detrend_residual(x: np.ndarray, window: int = 60) -> np.ndarray:
    """Subtract centered rolling mean to remove slow drift; preserves
    short-timescale variability used by EWS."""
    n = len(x)
    out = np.copy(x)
    half = window // 2
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        seg = x[a:b]
        seg = seg[~np.isnan(seg)]
        if len(seg) >= 5:
            out[i] = x[i] - np.mean(seg)
    return out


# ---------------------------------------------------------------------------
# Rolling indicators
# ---------------------------------------------------------------------------
def rolling_ac1(x: np.ndarray, window: int) -> np.ndarray:
    """Lag-1 autocorrelation in trailing window."""
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(window, n):
        w = x[i - window:i]
        w = w[~np.isnan(w)]
        if len(w) < 30:
            continue
        x1, x2 = w[:-1], w[1:]
        s1, s2 = np.std(x1), np.std(x2)
        if s1 < 1e-9 or s2 < 1e-9:
            continue
        out[i] = float(np.corrcoef(x1, x2)[0, 1])
    return out


def rolling_var(x: np.ndarray, window: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(window, n):
        w = x[i - window:i]
        w = w[~np.isnan(w)]
        if len(w) < 30:
            continue
        out[i] = float(np.var(w))
    return out


def rolling_skew(x: np.ndarray, window: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(window, n):
        w = x[i - window:i]
        w = w[~np.isnan(w)]
        if len(w) < 30:
            continue
        out[i] = float(skew(w))
    return out


# ---------------------------------------------------------------------------
# Changepoint detection
# ---------------------------------------------------------------------------
def detect_changepoints_cusum(x: np.ndarray, k: float = CUSUM_K,
                              h: float = CUSUM_H,
                              cluster: int = CLUSTER_GAP) -> list[int]:
    """Two-sided CUSUM (Page 1954). Detects shifts in mean of standardized x.

    k = slack (small drifts ignored), h = decision threshold; both in std units.
    Returns indices of detected mean-shift events.
    """
    valid = ~np.isnan(x)
    if valid.sum() < 100:
        return []
    mu = np.nanmean(x)
    sigma = np.nanstd(x) + 1e-9
    z = (x - mu) / sigma

    sh = sl = 0.0
    raw_events: list[int] = []
    for i in range(len(z)):
        if np.isnan(z[i]):
            continue
        sh = max(0.0, sh + z[i] - k)
        sl = min(0.0, sl + z[i] + k)
        if sh > h or sl < -h:
            raw_events.append(i)
            sh = sl = 0.0  # reset after detection

    # cluster: keep first of each run separated by >= cluster days
    if not raw_events:
        return []
    clustered = [raw_events[0]]
    for e in raw_events[1:]:
        if e - clustered[-1] >= cluster:
            clustered.append(e)
    return clustered


# ---------------------------------------------------------------------------
# EWS trend test (Kendall tau over pre-shift window)
# ---------------------------------------------------------------------------
def kendall_trend(indicator: np.ndarray, end_idx: int,
                  pre_window: int = PRE_WINDOW) -> dict:
    start = max(0, end_idx - pre_window)
    y = indicator[start:end_idx]
    t = np.arange(len(y))
    mask = ~np.isnan(y)
    if mask.sum() < 30:
        return {"tau": None, "p_value": None, "n": int(mask.sum())}
    tau, p = kendalltau(t[mask], y[mask])
    return {"tau": float(tau), "p_value": float(p), "n": int(mask.sum())}


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_timeseries(grid: np.ndarray, raw: np.ndarray, detrended: np.ndarray,
                    changepoints: list[int], path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    for ax in axes:
        ax.grid(False)
    axes[0].plot(grid, raw, lw=0.6, color="#1f77b4", label="DO (mg/L)")
    axes[0].set_ylabel("DO (mg/L)")
    axes[0].set_title("Daily mean dissolved oxygen — raw")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[1].plot(grid, detrended, lw=0.5, color="#2ca02c", alpha=0.8)
    axes[1].axhline(0.0, color="k", lw=0.4)
    axes[1].set_ylabel("DO anomaly\n(seasonal removed)")
    for cp in changepoints:
        for ax in axes:
            ax.axvline(grid[cp], color="r", lw=0.6, ls="--", alpha=0.6)
    axes[1].set_xlabel("Date")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_panel(grid: np.ndarray, ac1: np.ndarray, var: np.ndarray,
               sk: np.ndarray, changepoints: list[int], path: Path) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    for ax in axes:
        ax.grid(False)
    axes[0].plot(grid, ac1, color="#d62728", lw=0.8)
    axes[0].set_ylabel("AR(1)")
    axes[0].set_title(f"Rolling early-warning indicators (window = {WINDOW_DAYS} d)")
    axes[1].plot(grid, var, color="#9467bd", lw=0.8)
    axes[1].set_ylabel("Variance")
    axes[2].plot(grid, sk, color="#8c564b", lw=0.8)
    axes[2].axhline(0.0, color="k", lw=0.4)
    axes[2].set_ylabel("Skewness")
    axes[2].set_xlabel("Date")
    for cp in changepoints:
        for ax in axes:
            ax.axvline(grid[cp], color="r", lw=0.6, ls="--", alpha=0.6)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"[analyze] loading {JSONL_PATH.name}", file=sys.stderr)
    dates, vals, meta = load_jsonl(JSONL_PATH)
    print(f"[analyze]   raw n={len(vals)}, site={meta['site_name']}",
          file=sys.stderr)

    grid, x_aligned = align_daily(dates, vals)
    n_valid = int(np.sum(~np.isnan(x_aligned)))
    print(f"[analyze]   aligned daily grid: {len(grid)} days, "
          f"{n_valid} non-NaN ({n_valid/len(grid)*100:.1f}%)", file=sys.stderr)

    x_deseason = seasonal_detrend(x_aligned)
    x_resid = detrend_residual(x_deseason, window=60)

    # changepoints on the deseasonal series (preserves regime-mean shifts but
    # not annual cycle)
    cps = detect_changepoints_cusum(x_deseason, k=CUSUM_K, h=CUSUM_H,
                                    cluster=CLUSTER_GAP)
    print(f"[analyze]   CUSUM changepoints (k={CUSUM_K}, h={CUSUM_H}): n={len(cps)}",
          file=sys.stderr)
    for cp in cps:
        print(f"[analyze]     - {grid[cp].date()}  idx={cp}", file=sys.stderr)

    # EWS indicators on the high-pass residual (Dakos et al. 2008 method)
    ac1 = rolling_ac1(x_resid, WINDOW_DAYS)
    var = rolling_var(x_resid, WINDOW_DAYS)
    sk = rolling_skew(x_resid, WINDOW_DAYS)

    # per-changepoint Kendall trend tests
    cp_reports = []
    for cp in cps:
        rep = {
            "date": grid[cp].strftime("%Y-%m-%d"),
            "index": int(cp),
            "ac1_trend": kendall_trend(ac1, cp),
            "var_trend": kendall_trend(var, cp),
            "skew_trend": kendall_trend(sk, cp),
            "mean_before_30d": float(np.nanmean(x_aligned[max(0, cp-30):cp])),
            "mean_after_30d": float(np.nanmean(x_aligned[cp:cp+30])),
        }
        cp_reports.append(rep)

    # global trend (informative — long-term EWS without a labeled shift)
    last = len(grid) - 1
    global_trend = {
        "ac1": kendall_trend(ac1, last, pre_window=len(grid)),
        "var": kendall_trend(var, last, pre_window=len(grid)),
        "skew": kendall_trend(sk, last, pre_window=len(grid)),
    }

    plot_timeseries(grid, x_aligned, x_deseason, cps, TS_PNG)
    plot_panel(grid, ac1, var, sk, cps, PANEL_PNG)
    print(f"[analyze]   plots -> {TS_PNG.name}, {PANEL_PNG.name}", file=sys.stderr)

    # verdict — significant rises in AR1 AND variance before at least one shift
    classical_signature = False
    for rep in cp_reports:
        ac = rep["ac1_trend"]
        vt = rep["var_trend"]
        if (ac["tau"] is not None and vt["tau"] is not None and
                ac["tau"] > 0 and ac["p_value"] is not None and ac["p_value"] < 0.05
                and vt["tau"] > 0 and vt["p_value"] is not None and vt["p_value"] < 0.05):
            classical_signature = True
            break

    summary = {
        "site": meta,
        "fetched_from": "lake_do_timeseries.jsonl",
        "n_days_grid": len(grid),
        "n_valid_obs": n_valid,
        "first_date": grid[0].strftime("%Y-%m-%d"),
        "last_date": grid[-1].strftime("%Y-%m-%d"),
        "params": {
            "window_days": WINDOW_DAYS,
            "cusum_k": CUSUM_K,
            "cusum_h": CUSUM_H,
            "cluster_gap": CLUSTER_GAP,
            "pre_window": PRE_WINDOW,
        },
        "changepoints": cp_reports,
        "global_trend": global_trend,
        "classical_csd_signature_detected": classical_signature,
        "interpretation": (
            "Detected ≥1 changepoint with significant rise in BOTH AR(1) and "
            "variance over the preceding 730 days — classical critical-slowing-"
            "down signature consistent with fold-bifurcation regime shift."
            if classical_signature else
            "No changepoint exhibits the classical AR(1)+variance rise "
            "signature. System either lacks fold dynamics, contains hidden "
            "drivers, or shift dynamics are too rapid for window to resolve."
        ),
    }

    with RESULTS_PATH.open("w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"[analyze]   verdict: classical_csd_signature_detected="
          f"{classical_signature}", file=sys.stderr)
    print(f"[analyze]   wrote {RESULTS_PATH.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
