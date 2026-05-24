"""Walk-forward backtest engine v0.1 — 1000-ticker universe.

Pipeline
========

1. Load universe CSV (`backtest/data/1000_universe.csv`)
2. Load per-ticker daily OHLCV from `backtest/data/prices/<ticker>.csv`
3. Resample daily -> monthly closes (last close of each month)
4. Two label sources:
   a. LLM (StructTuple `critical_point_state` from `companies_500.jsonl`)
   b. Heuristic price-regime classifier (vol + drawdown + AR(1) decile)
5. Walk-forward: for each month-end T from min_T to max_T - hold_months:
   - Form long/short cohorts based on each label source
   - Compute monthly forward return for each cohort
   - Compute equal-weight benchmark return
6. Aggregate per-cohort stats: mean, std, Sharpe, Sortino, max drawdown,
   hit rate, vs benchmark Sharpe lift
7. Write results JSON + monthly time series CSV + summary table

Usage
-----
  python3 engine.py                              # full universe, full window
  python3 engine.py --tickers AAPL,TSLA --start 2024-01-01 --end 2024-12-31
  python3 engine.py --hold-months 1 --strategy long_short
  python3 engine.py --skip-cache-check          # don't validate price cache

Outputs
-------
  backtest/results/v0.1-{label}-{timestamp}.json
  backtest/results/v0.1-monthly-{label}-{timestamp}.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import math
import os
import statistics
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

LOG = logging.getLogger("backtest_engine")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_UNIVERSE = os.path.join(SCRIPT_DIR, "data", "1000_universe.csv")
DEFAULT_PRICES_DIR = os.path.join(SCRIPT_DIR, "data", "prices")
DEFAULT_LLM_LABELS = os.path.join(
    SCRIPT_DIR, "..", "companies_500.jsonl"
)
DEFAULT_RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
DEFAULT_START = "2020-06-01"
DEFAULT_END = "2025-12-01"

NEAR_CRITICAL_STATES = {"approaching_critical", "at_critical"}
STABLE_STATES = {"far_from_critical", "post_critical_transition"}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

@dataclass
class TickerSeries:
    ticker: str
    # month_end -> close
    monthly_close: Dict[dt.date, float] = field(default_factory=dict)
    # for heuristic features: rolling daily returns by date
    daily_close: List[Tuple[dt.date, float]] = field(default_factory=list)


def load_universe(path: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = (row.get("ticker") or "").strip().upper()
            src = (row.get("source") or "").strip()
            if t:
                out.append((t, src))
    return out


def load_ticker_csv(prices_dir: str, ticker: str) -> Optional[TickerSeries]:
    safe = ticker.replace(".", "_").replace("/", "_")
    p = os.path.join(prices_dir, f"{safe}.csv")
    if not os.path.exists(p):
        return None
    ts = TickerSeries(ticker=ticker)
    try:
        with open(p, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    d = dt.date.fromisoformat(row["date"])
                    c = float(row["close"])
                except (KeyError, ValueError):
                    continue
                if c <= 0:
                    continue
                ts.daily_close.append((d, c))
    except OSError:
        return None
    ts.daily_close.sort(key=lambda x: x[0])
    # Build monthly closes (last close of each month)
    by_month: Dict[Tuple[int, int], Tuple[dt.date, float]] = {}
    for d, c in ts.daily_close:
        k = (d.year, d.month)
        prev = by_month.get(k)
        if prev is None or d > prev[0]:
            by_month[k] = (d, c)
    for _, (d, c) in by_month.items():
        # Anchor at month-end
        month_end = _month_end(d.year, d.month)
        ts.monthly_close[month_end] = c
    return ts


def load_llm_labels(path: str) -> Dict[str, str]:
    """Returns {ticker -> critical_point_state}."""
    out: Dict[str, str] = {}
    if not os.path.exists(path):
        LOG.warning("LLM labels file not found: %s", path)
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = (rec.get("ticker") or rec.get("symbol") or "").upper()
            if not t:
                continue
            st = rec.get("struct_tuple") or {}
            cps = st.get("critical_point_state") if isinstance(st, dict) else None
            if cps:
                out[t] = cps
    return out


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _month_end(year: int, month: int) -> dt.date:
    if month == 12:
        return dt.date(year, 12, 31)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


def _iter_month_ends(start: dt.date, end: dt.date) -> List[dt.date]:
    out: List[dt.date] = []
    y, m = start.year, start.month
    while True:
        d = _month_end(y, m)
        if d > end:
            break
        if d >= start:
            out.append(d)
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return out


def _add_months(d: dt.date, months: int) -> dt.date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return _month_end(y, m)


# ---------------------------------------------------------------------------
# Heuristic regime classifier
# ---------------------------------------------------------------------------

def realized_vol_90d(daily: List[Tuple[dt.date, float]], anchor: dt.date) -> Optional[float]:
    """Std-dev of last 90 daily log-returns ending <= anchor."""
    cutoff = anchor - dt.timedelta(days=130)  # ~90 trading days
    window = [(d, c) for d, c in daily if cutoff <= d <= anchor]
    if len(window) < 30:
        return None
    rets: List[float] = []
    for i in range(1, len(window)):
        if window[i - 1][1] > 0:
            rets.append(math.log(window[i][1] / window[i - 1][1]))
    if len(rets) < 20:
        return None
    return statistics.pstdev(rets) * math.sqrt(252)


def max_drawdown_180d(daily: List[Tuple[dt.date, float]], anchor: dt.date) -> Optional[float]:
    cutoff = anchor - dt.timedelta(days=180)
    window = [(d, c) for d, c in daily if cutoff <= d <= anchor]
    if len(window) < 30:
        return None
    peak = window[0][1]
    mdd = 0.0
    for _, c in window:
        if c > peak:
            peak = c
        dd = (c - peak) / peak
        if dd < mdd:
            mdd = dd
    return mdd  # negative; closer to 0 = less drawdown


def ar1_monthly(monthly_close: Dict[dt.date, float], anchor: dt.date, n: int = 12) -> Optional[float]:
    """AR(1) coefficient of last n monthly log-returns ending <= anchor."""
    months = sorted([d for d in monthly_close.keys() if d <= anchor])
    if len(months) < n + 2:
        return None
    months = months[-(n + 1):]
    rets: List[float] = []
    for i in range(1, len(months)):
        c0 = monthly_close[months[i - 1]]
        c1 = monthly_close[months[i]]
        if c0 > 0:
            rets.append(math.log(c1 / c0))
    if len(rets) < n - 1:
        return None
    mean = statistics.fmean(rets)
    num = sum((rets[i] - mean) * (rets[i - 1] - mean) for i in range(1, len(rets)))
    den = sum((r - mean) ** 2 for r in rets)
    if den == 0:
        return None
    return num / den


def heuristic_score(
    daily: List[Tuple[dt.date, float]],
    monthly: Dict[dt.date, float],
    anchor: dt.date,
) -> Optional[float]:
    """Composite phase-stress score. Higher = more 'near_critical'-like.

    Components (all anchor-aware, no look-ahead):
      vol_90d (higher = more stressed)
      |mdd_180d| (higher abs = more stressed)
      ar1 (higher absolute persistence = more regime-locked)
    """
    vol = realized_vol_90d(daily, anchor)
    mdd = max_drawdown_180d(daily, anchor)
    ar = ar1_monthly(monthly, anchor)
    if vol is None or mdd is None:
        return None
    score = vol * 0.5 + abs(mdd) * 0.4
    if ar is not None:
        score += abs(ar) * 0.1
    return score


# ---------------------------------------------------------------------------
# Cohort formation per snapshot
# ---------------------------------------------------------------------------

def llm_cohort(
    label_map: Dict[str, str],
    universe_tickers: List[str],
) -> Dict[str, List[str]]:
    """Static (per-ticker) cohort assignment from LLM labels."""
    nc: List[str] = []
    other: List[str] = []
    for t in universe_tickers:
        s = label_map.get(t)
        if s in NEAR_CRITICAL_STATES:
            nc.append(t)
        elif s in STABLE_STATES:
            other.append(t)
    return {"near_critical": nc, "other": other}


def heuristic_cohort_at_snapshot(
    snapshot: dt.date,
    universe: List[TickerSeries],
    decile: float = 0.10,
) -> Dict[str, List[str]]:
    """Top/bottom decile by heuristic score at snapshot."""
    scored: List[Tuple[str, float]] = []
    for ts in universe:
        sc = heuristic_score(ts.daily_close, ts.monthly_close, snapshot)
        if sc is None:
            continue
        scored.append((ts.ticker, sc))
    if len(scored) < 20:
        return {"near_critical_heuristic": [], "stable_heuristic": []}
    scored.sort(key=lambda x: x[1])
    n = len(scored)
    k = max(1, int(n * decile))
    stable = [t for t, _ in scored[:k]]
    near = [t for t, _ in scored[-k:]]
    return {"near_critical_heuristic": near, "stable_heuristic": stable}


# ---------------------------------------------------------------------------
# Return calculations
# ---------------------------------------------------------------------------

def forward_return(ts: TickerSeries, snapshot: dt.date, hold_months: int) -> Optional[float]:
    """Monthly forward return: (close[T + hold] / close[T]) - 1.

    Uses closest available month-end on or before snapshot as anchor, and
    closest on or after target_end as exit.
    """
    months = sorted(ts.monthly_close.keys())
    if not months:
        return None
    anchor = None
    for d in months:
        if d <= snapshot:
            anchor = d
        else:
            break
    if anchor is None:
        return None
    target_end = _add_months(snapshot, hold_months)
    exit_d = None
    for d in months:
        if d >= target_end:
            exit_d = d
            break
    if exit_d is None:
        return None
    a = ts.monthly_close[anchor]
    e = ts.monthly_close[exit_d]
    if a <= 0:
        return None
    return (e / a) - 1.0


def cohort_monthly_return(
    cohort_tickers: List[str],
    series_map: Dict[str, TickerSeries],
    snapshot: dt.date,
    hold_months: int,
) -> Tuple[Optional[float], int]:
    """Equal-weighted mean monthly forward return of cohort."""
    rets: List[float] = []
    for t in cohort_tickers:
        ts = series_map.get(t)
        if ts is None:
            continue
        r = forward_return(ts, snapshot, hold_months)
        if r is not None:
            rets.append(r)
    if not rets:
        return None, 0
    return statistics.fmean(rets), len(rets)


# ---------------------------------------------------------------------------
# Performance stats
# ---------------------------------------------------------------------------

def sharpe_annualized(returns: List[float], freq: int = 12) -> float:
    """Annualised Sharpe from a return series of frequency `freq` per year."""
    if len(returns) < 2:
        return float("nan")
    mu = statistics.fmean(returns)
    sd = statistics.pstdev(returns)
    if sd == 0:
        return float("nan")
    return (mu / sd) * math.sqrt(freq)


def sortino_annualized(returns: List[float], freq: int = 12) -> float:
    if len(returns) < 2:
        return float("nan")
    mu = statistics.fmean(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return float("nan")
    dsd = math.sqrt(statistics.fmean([r * r for r in downside]))
    if dsd == 0:
        return float("nan")
    return (mu / dsd) * math.sqrt(freq)


def max_drawdown_from_returns(returns: List[float]) -> float:
    cum = 1.0
    peak = 1.0
    mdd = 0.0
    for r in returns:
        cum *= (1 + r)
        if cum > peak:
            peak = cum
        dd = (cum - peak) / peak
        if dd < mdd:
            mdd = dd
    return mdd


def hit_rate(returns: List[float]) -> float:
    if not returns:
        return float("nan")
    return sum(1 for r in returns if r > 0) / len(returns)


def t_test_paired(diffs: List[float]) -> Tuple[float, float]:
    """One-sample t-test on diff series (cohort minus benchmark)."""
    if len(diffs) < 2:
        return (float("nan"), float("nan"))
    try:
        from scipy import stats  # type: ignore
        res = stats.ttest_1samp(diffs, 0.0)
        return float(res.statistic), float(res.pvalue)
    except ImportError:
        mu = statistics.fmean(diffs)
        sd = statistics.pstdev(diffs)
        if sd == 0:
            return (float("nan"), float("nan"))
        se = sd / math.sqrt(len(diffs))
        t = mu / se if se > 0 else float("nan")
        p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2)))) if t == t else float("nan")
        return (t, p)


# ---------------------------------------------------------------------------
# Main walk-forward
# ---------------------------------------------------------------------------

def run_walk_forward(
    universe_tickers: List[str],
    universe_source: Dict[str, str],
    series_map: Dict[str, TickerSeries],
    llm_labels: Dict[str, str],
    start: dt.date,
    end: dt.date,
    hold_months: int,
    decile: float,
) -> Dict:
    """Walk-forward returns per cohort per snapshot.

    Returns a dict with monthly_rows and aggregate_stats per cohort.
    """
    month_ends = _iter_month_ends(start, end)
    # Drop trailing months that don't have hold_months of forward data.
    month_ends = month_ends[: max(0, len(month_ends) - hold_months)]
    LOG.info("Walk-forward: %d snapshots from %s to %s, hold=%dmo",
             len(month_ends), month_ends[0] if month_ends else "—",
             month_ends[-1] if month_ends else "—", hold_months)

    universe_obj = [series_map[t] for t in universe_tickers if t in series_map]

    # Static LLM cohort (uses only sp500 subset since R1000 supplement has no labels)
    llm_groups = llm_cohort(llm_labels, universe_tickers)
    LOG.info("Static LLM cohort: near_critical=%d, other=%d",
             len(llm_groups["near_critical"]), len(llm_groups["other"]))

    monthly_rows: List[Dict] = []
    # cohort -> [returns]
    cohort_rets: Dict[str, List[float]] = {
        "near_critical_llm": [],
        "other_llm": [],
        "near_critical_heuristic": [],
        "stable_heuristic": [],
        "benchmark_ew": [],
    }

    for T in month_ends:
        # Dynamic heuristic cohorts at this snapshot.
        h_groups = heuristic_cohort_at_snapshot(T, universe_obj, decile=decile)
        # Benchmark = equal-weight across all tickers with valid forward return.
        bench_tickers = [t for t in universe_tickers if t in series_map]
        bench_ret, n_bench = cohort_monthly_return(bench_tickers, series_map, T, hold_months)

        nc_llm_ret, n_nc_llm = cohort_monthly_return(llm_groups["near_critical"], series_map, T, hold_months)
        oth_llm_ret, n_oth_llm = cohort_monthly_return(llm_groups["other"], series_map, T, hold_months)
        nc_h_ret, n_nc_h = cohort_monthly_return(h_groups["near_critical_heuristic"], series_map, T, hold_months)
        st_h_ret, n_st_h = cohort_monthly_return(h_groups["stable_heuristic"], series_map, T, hold_months)

        if bench_ret is not None:
            cohort_rets["benchmark_ew"].append(bench_ret)
        if nc_llm_ret is not None:
            cohort_rets["near_critical_llm"].append(nc_llm_ret)
        if oth_llm_ret is not None:
            cohort_rets["other_llm"].append(oth_llm_ret)
        if nc_h_ret is not None:
            cohort_rets["near_critical_heuristic"].append(nc_h_ret)
        if st_h_ret is not None:
            cohort_rets["stable_heuristic"].append(st_h_ret)

        monthly_rows.append({
            "snapshot_date": T.isoformat(),
            "n_universe": n_bench,
            "benchmark_ew_ret": bench_ret,
            "near_critical_llm_ret": nc_llm_ret,
            "n_nc_llm": n_nc_llm,
            "other_llm_ret": oth_llm_ret,
            "n_oth_llm": n_oth_llm,
            "near_critical_heuristic_ret": nc_h_ret,
            "n_nc_heuristic": n_nc_h,
            "stable_heuristic_ret": st_h_ret,
            "n_stable_heuristic": n_st_h,
        })

    # Aggregate stats per cohort
    stats_out: Dict[str, Dict] = {}
    bench = cohort_rets["benchmark_ew"]
    bench_sharpe = sharpe_annualized(bench)

    for name, rets in cohort_rets.items():
        if not rets:
            stats_out[name] = {"n": 0}
            continue
        sh = sharpe_annualized(rets)
        sn = sortino_annualized(rets)
        mdd = max_drawdown_from_returns(rets)
        hr = hit_rate(rets)
        mu = statistics.fmean(rets)
        sd = statistics.pstdev(rets)
        cumret = 1.0
        for r in rets:
            cumret *= (1 + r)
        cumret -= 1.0
        # vs benchmark: pair on shared months
        if name != "benchmark_ew":
            n_pair = min(len(rets), len(bench))
            diffs = [rets[i] - bench[i] for i in range(n_pair)] if n_pair > 0 else []
            t_stat, p_val = t_test_paired(diffs)
            sharpe_lift = sh - bench_sharpe if (sh == sh and bench_sharpe == bench_sharpe) else float("nan")
            mean_diff_monthly = statistics.fmean(diffs) if diffs else float("nan")
        else:
            t_stat, p_val, sharpe_lift, mean_diff_monthly = float("nan"), float("nan"), 0.0, 0.0
        stats_out[name] = {
            "n_months": len(rets),
            "mean_monthly": mu,
            "std_monthly": sd,
            "sharpe_annualised": sh,
            "sortino_annualised": sn,
            "max_drawdown": mdd,
            "hit_rate": hr,
            "cumulative_return": cumret,
            "sharpe_lift_vs_bench": sharpe_lift,
            "mean_diff_monthly_vs_bench": mean_diff_monthly,
            "t_stat_vs_bench": t_stat,
            "p_value_vs_bench": p_val,
        }

    return {
        "monthly_rows": monthly_rows,
        "stats": stats_out,
        "cohorts": {
            "near_critical_llm_tickers": llm_groups["near_critical"],
            "other_llm_tickers": llm_groups["other"],
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Walk-forward backtest engine v0.1")
    ap.add_argument("--universe", default=DEFAULT_UNIVERSE)
    ap.add_argument("--prices-dir", default=DEFAULT_PRICES_DIR)
    ap.add_argument("--llm-labels", default=DEFAULT_LLM_LABELS)
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    ap.add_argument("--tickers", default=None, help="Comma-separated subset (overrides universe)")
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--hold-months", type=int, default=1)
    ap.add_argument("--decile", type=float, default=0.10)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--tag", default=None, help="Suffix for result filenames")
    ap.add_argument("--skip-cache-check", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    _setup_logging(args.verbose)

    # Load universe
    if args.tickers:
        universe = [(t.strip().upper(), "cli") for t in args.tickers.split(",") if t.strip()]
    else:
        universe = load_universe(args.universe)
        if args.limit:
            universe = universe[: args.limit]

    universe_tickers = [t for t, _ in universe]
    universe_source = {t: s for t, s in universe}
    LOG.info("Universe: %d tickers", len(universe_tickers))

    # Load price series
    series_map: Dict[str, TickerSeries] = {}
    missing: List[str] = []
    for t in universe_tickers:
        ts = load_ticker_csv(args.prices_dir, t)
        if ts is None or len(ts.daily_close) < 50:
            missing.append(t)
            continue
        series_map[t] = ts
    LOG.info("Loaded %d/%d ticker series (%d missing/insufficient)",
             len(series_map), len(universe_tickers), len(missing))

    if not series_map:
        LOG.error("No ticker series loaded. Run fetch_prices.py first.")
        return 2

    # Load LLM labels
    llm_labels = load_llm_labels(args.llm_labels)
    LOG.info("Loaded %d LLM labels", len(llm_labels))

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    res = run_walk_forward(
        universe_tickers=universe_tickers,
        universe_source=universe_source,
        series_map=series_map,
        llm_labels=llm_labels,
        start=start,
        end=end,
        hold_months=args.hold_months,
        decile=args.decile,
    )

    os.makedirs(args.results_dir, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = args.tag or f"{len(series_map)}t"

    monthly_csv = os.path.join(args.results_dir, f"v0.1-monthly-{tag}-{timestamp}.csv")
    summary_json = os.path.join(args.results_dir, f"v0.1-{tag}-{timestamp}.json")

    # Monthly CSV
    if res["monthly_rows"]:
        keys = list(res["monthly_rows"][0].keys())
        with open(monthly_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for row in res["monthly_rows"]:
                row_out = {k: ("" if row[k] is None else row[k]) for k in keys}
                w.writerow(row_out)
        LOG.info("Wrote monthly CSV -> %s (%d rows)", monthly_csv, len(res["monthly_rows"]))

    # Summary JSON
    summary = {
        "version": "0.1",
        "engine": "walk_forward_1000ticker",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "start": args.start,
            "end": args.end,
            "hold_months": args.hold_months,
            "decile": args.decile,
            "n_universe_input": len(universe_tickers),
            "n_universe_covered": len(series_map),
            "n_universe_missing": len(missing),
        },
        "stats": res["stats"],
        "cohort_counts": {
            "near_critical_llm": len(res["cohorts"]["near_critical_llm_tickers"]),
            "other_llm": len(res["cohorts"]["other_llm_tickers"]),
        },
        "missing_examples": missing[:50],
    }
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    LOG.info("Wrote summary JSON -> %s", summary_json)

    # Print headline
    bench_sh = res["stats"]["benchmark_ew"].get("sharpe_annualised", float("nan"))
    nc_llm_sh = res["stats"]["near_critical_llm"].get("sharpe_annualised", float("nan"))
    nc_llm_lift = res["stats"]["near_critical_llm"].get("sharpe_lift_vs_bench", float("nan"))
    nc_llm_p = res["stats"]["near_critical_llm"].get("p_value_vs_bench", float("nan"))
    nc_h_sh = res["stats"]["near_critical_heuristic"].get("sharpe_annualised", float("nan"))
    nc_h_lift = res["stats"]["near_critical_heuristic"].get("sharpe_lift_vs_bench", float("nan"))
    LOG.info("=" * 70)
    LOG.info("HEADLINE")
    LOG.info("  benchmark EW Sharpe: %.3f", bench_sh)
    LOG.info("  near_critical_llm   Sharpe: %.3f (lift %+.3f, p=%.3g)", nc_llm_sh, nc_llm_lift, nc_llm_p)
    LOG.info("  near_critical_heur. Sharpe: %.3f (lift %+.3f)", nc_h_sh, nc_h_lift)
    LOG.info("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
