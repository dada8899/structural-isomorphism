"""Phase Detector backtest engine v0.2.

Two modes:
  1. Single-snapshot (default, v0.1 compat): pin --snapshot to one date and
     compute forward-period return per company once. Used by unit tests.

  2. Walk-forward (--walk-forward, v0.2): roll snapshot month-by-month across
     the price history, computing forward-period returns at every month, then
     aggregate to per-month means per group + a single Welch t-test across all
     (company × month) observations. Outputs an extra cumulative_return.png
     and backtest_result.json includes Sharpe + walk-forward stats.

Hypothesis under test:
    "Companies classified as `near_critical` (= approaching_critical OR
     at_critical) at snapshot T have a meaningfully different forward
     return over the next 6 (or 12) months versus the rest."

Inputs:
  --companies     companies_500.jsonl (Wave 1 StructTuple)
  --prices        prices.csv (legacy) OR --real-prices to read prices_500.csv
  --snapshot      YYYY-MM-DD anchor date (default today)
  --period        6m | 12m
  --walk-forward  enable rolling snapshot mode
  --real-prices   shortcut: load v0.2 prices_500.csv + walk-forward
  --dry-run       run end-to-end on synthetic data with no externals

Outputs:
  data/backtest_result.json     {mean, std, sharpe, t, p, n_per_group, ...}
  data/backtest_cumulative.csv  date, near_critical_cumret, other_cumret
  data/cumulative_return.png    (walk-forward only)
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
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

LOG = logging.getLogger("backtest")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRICES = os.path.join(SCRIPT_DIR, "data", "prices.csv")
DEFAULT_REAL_PRICES = os.path.join(SCRIPT_DIR, "prices_500.csv")
DEFAULT_COMPANIES_PRIMARY = os.path.join(SCRIPT_DIR, "companies_500.jsonl")
DEFAULT_COMPANIES_FALLBACK = os.path.join(SCRIPT_DIR, "companies.jsonl")
DEFAULT_RESULT = os.path.join(SCRIPT_DIR, "backtest_result.json")
DEFAULT_CUMCSV = os.path.join(SCRIPT_DIR, "cumulative.csv")
DEFAULT_CUMPNG = os.path.join(SCRIPT_DIR, "cumulative_return.png")
DEFAULT_SNAPSHOT = "2026-05-14"

NEAR_CRITICAL_STATES = {"approaching_critical", "at_critical"}
OTHER_STATES = {"far_from_critical", "post_critical_transition"}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s %(message)s")


@dataclass
class CompanyRow:
    ticker: str
    critical_point_state: Optional[str]

    @property
    def group(self) -> Optional[str]:
        cps = self.critical_point_state
        if cps in NEAR_CRITICAL_STATES:
            return "near_critical"
        if cps in OTHER_STATES:
            return "other"
        return None


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_companies(path: str) -> List[CompanyRow]:
    """Read JSONL — supports both {struct_tuple: {...}} wrapper and flat form."""
    out: List[CompanyRow] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ticker = rec.get("ticker") or rec.get("symbol")
            if not ticker:
                continue
            st = rec.get("struct_tuple")
            if isinstance(st, dict):
                cps = st.get("critical_point_state")
            else:
                cps = rec.get("critical_point_state")
            # NOTE: rows missing struct_tuple (e.g. input-only file like companies.jsonl)
            # become group=None and get skipped downstream — handled gracefully.
            out.append(CompanyRow(ticker=ticker.upper(), critical_point_state=cps))
    return out


def load_prices(path: str) -> Dict[str, List[Tuple[dt.date, float]]]:
    """Load prices.csv into {ticker: [(date, close), ...]} sorted ascending."""
    table: Dict[str, List[Tuple[dt.date, float]]] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = dt.date.fromisoformat(row["date"])
                t = row["ticker"].upper()
                c = float(row["close"])
            except (KeyError, ValueError):
                continue
            table.setdefault(t, []).append((d, c))
    for t in table:
        table[t].sort(key=lambda x: x[0])
    return table


# ---------------------------------------------------------------------------
# Algorithm helpers
# ---------------------------------------------------------------------------

def _nearest_on_or_after(series: List[Tuple[dt.date, float]], target: dt.date) -> Optional[Tuple[dt.date, float]]:
    for d, c in series:
        if d >= target:
            return (d, c)
    return None


def _nearest_on_or_before(series: List[Tuple[dt.date, float]], target: dt.date) -> Optional[Tuple[dt.date, float]]:
    best: Optional[Tuple[dt.date, float]] = None
    for d, c in series:
        if d <= target:
            best = (d, c)
        else:
            break
    return best


def add_months(d: dt.date, months: int) -> dt.date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    # clamp day to month-end
    if m == 12:
        last_day = 31
    else:
        last_day = (dt.date(y, m + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(y, m, min(d.day, last_day))


def parse_period(s: str) -> int:
    s = s.strip().lower()
    if s.endswith("m"):
        return int(s[:-1])
    return int(s)


def compute_group_returns(
    companies: List[CompanyRow],
    prices: Dict[str, List[Tuple[dt.date, float]]],
    snapshot: dt.date,
    months: int,
) -> Tuple[Dict[str, List[float]], Dict[str, List[str]]]:
    """Compute forward returns per group between snapshot and snapshot+months.

    Returns: ({group: [returns]}, {group: [tickers used]})
    """
    target_end = add_months(snapshot, months)
    grouped: Dict[str, List[float]] = {"near_critical": [], "other": []}
    used: Dict[str, List[str]] = {"near_critical": [], "other": []}
    skipped_no_group = 0
    skipped_no_price = 0
    skipped_anchor = 0

    for c in companies:
        g = c.group
        if g is None:
            skipped_no_group += 1
            continue
        series = prices.get(c.ticker)
        if not series:
            skipped_no_price += 1
            continue
        anchor = _nearest_on_or_before(series, snapshot)
        if not anchor:
            anchor = _nearest_on_or_after(series, snapshot)
        end_pt = _nearest_on_or_after(series, target_end)
        if not anchor or not end_pt or anchor[1] <= 0:
            skipped_anchor += 1
            continue
        ret = (end_pt[1] - anchor[1]) / anchor[1]
        grouped[g].append(ret)
        used[g].append(c.ticker)

    LOG.info(
        "Group returns: near_critical=%d, other=%d (skipped no_group=%d, no_price=%d, anchor=%d)",
        len(grouped["near_critical"]), len(grouped["other"]),
        skipped_no_group, skipped_no_price, skipped_anchor,
    )
    return grouped, used


def summarize(returns: List[float], period_months: int) -> Dict[str, float]:
    n = len(returns)
    if n == 0:
        return {"n": 0, "mean": float("nan"), "std": float("nan"), "sharpe": float("nan")}
    mean = statistics.fmean(returns)
    std = statistics.pstdev(returns) if n > 1 else 0.0
    annual_factor = math.sqrt(12.0 / max(period_months, 1))
    sharpe = (mean / std) * annual_factor if std > 0 else float("nan")
    return {"n": n, "mean": mean, "std": std, "sharpe": sharpe}


def ttest_groups(a: List[float], b: List[float]) -> Tuple[float, float]:
    """Welch's t-test. Returns (t, p). Lazy scipy import."""
    if len(a) < 2 or len(b) < 2:
        return (float("nan"), float("nan"))
    try:
        from scipy import stats  # type: ignore
        res = stats.ttest_ind(a, b, equal_var=False)
        return float(res.statistic), float(res.pvalue)
    except Exception as exc:  # pragma: no cover
        LOG.warning("scipy ttest failed: %s — falling back to manual Welch", exc)
        return _manual_welch(a, b)


def _manual_welch(a: List[float], b: List[float]) -> Tuple[float, float]:
    # Fallback if scipy missing; p-value via normal approx (not perfect for small n).
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se == 0:
        return (float("nan"), float("nan"))
    t = (ma - mb) / se
    # 2-sided normal approx
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2))))
    return (t, p)


def build_cumulative_curve(
    companies: List[CompanyRow],
    prices: Dict[str, List[Tuple[dt.date, float]]],
    snapshot: dt.date,
    months: int,
) -> List[Tuple[dt.date, float, float]]:
    """Build equal-weighted cumulative-return curve per group from snapshot to snapshot+months."""
    end = add_months(snapshot, months)
    # collect all month-end dates between snapshot and end across all tickers
    all_dates: set = set()
    for c in companies:
        if c.group is None:
            continue
        series = prices.get(c.ticker)
        if not series:
            continue
        for d, _ in series:
            if snapshot <= d <= end:
                all_dates.add(d)
    timeline = sorted(all_dates)
    if not timeline:
        return []

    # Per ticker, normalize price to 1.0 at snapshot anchor.
    nc_curves: List[List[float]] = []
    oth_curves: List[List[float]] = []
    for c in companies:
        g = c.group
        if g is None:
            continue
        series = prices.get(c.ticker)
        if not series:
            continue
        anchor = _nearest_on_or_before(series, snapshot) or _nearest_on_or_after(series, snapshot)
        if not anchor or anchor[1] <= 0:
            continue
        base = anchor[1]
        # sample each timeline date at most-recent-on-or-before
        curve: List[float] = []
        idx = 0
        last_price = base
        for d in timeline:
            while idx < len(series) and series[idx][0] <= d:
                last_price = series[idx][1]
                idx += 1
            curve.append(last_price / base - 1.0)
        if g == "near_critical":
            nc_curves.append(curve)
        else:
            oth_curves.append(curve)

    out: List[Tuple[dt.date, float, float]] = []
    for i, d in enumerate(timeline):
        nc = statistics.fmean([row[i] for row in nc_curves]) if nc_curves else float("nan")
        oth = statistics.fmean([row[i] for row in oth_curves]) if oth_curves else float("nan")
        out.append((d, nc, oth))
    return out


def _prices_meta_path(prices_csv: str) -> str:
    return os.path.join(os.path.dirname(prices_csv), "prices.meta.json")


def _read_prices_meta(prices_csv: str) -> Optional[dict]:
    p = _prices_meta_path(prices_csv)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _prices_are_synthetic(prices_csv: str) -> bool:
    meta = _read_prices_meta(prices_csv)
    if not meta:
        return False
    return bool(meta.get("synthetic"))


def write_cumulative_csv(path: str, rows: List[Tuple[dt.date, float, float]]) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "near_critical_cumret", "other_cumret"])
        for d, nc, oth in rows:
            w.writerow([d.isoformat(), f"{nc:.6f}", f"{oth:.6f}"])
    return len(rows)


# ---------------------------------------------------------------------------
# Dry-run synthetic helpers (in-memory, no disk I/O)
# ---------------------------------------------------------------------------

def _synth_dry_run(snapshot: dt.date, months: int) -> Tuple[List[CompanyRow], Dict[str, List[Tuple[dt.date, float]]]]:
    """Build a small synthetic universe entirely in-memory for --dry-run."""
    import random as _r
    rng = _r.Random(7)
    companies: List[CompanyRow] = []
    prices: Dict[str, List[Tuple[dt.date, float]]] = {}
    # 12 month grid extending past target_end so anchors exist
    target_end = add_months(snapshot, months)
    start = add_months(snapshot, -1)
    end = add_months(target_end, 1)

    # build month-end timeline
    timeline: List[dt.date] = []
    cur = start
    while cur <= end:
        timeline.append(cur)
        cur = add_months(cur, 1)

    def make(ticker: str, cps: str, drift: float, vol: float = 0.10):
        companies.append(CompanyRow(ticker=ticker, critical_point_state=cps))
        price = 100.0
        ser: List[Tuple[dt.date, float]] = []
        for d in timeline:
            z = rng.gauss(0, 1)
            price *= math.exp(drift - 0.5 * vol * vol + vol * z)
            ser.append((d, round(price, 4)))
        prices[ticker] = ser

    # near_critical group has stronger positive drift
    for i in range(15):
        make(f"NC{i:03d}", "approaching_critical", drift=0.06, vol=0.08)
    for i in range(5):
        make(f"AC{i:03d}", "at_critical", drift=0.08, vol=0.12)
    for i in range(40):
        make(f"FF{i:03d}", "far_from_critical", drift=0.005, vol=0.06)
    for i in range(10):
        make(f"PT{i:03d}", "post_critical_transition", drift=-0.01, vol=0.10)
    return companies, prices


# ---------------------------------------------------------------------------
# Walk-forward (v0.2)
# ---------------------------------------------------------------------------

def walk_forward_returns(
    companies: List[CompanyRow],
    prices: Dict[str, List[Tuple[dt.date, float]]],
    months: int,
    min_snapshot: Optional[dt.date] = None,
    max_snapshot: Optional[dt.date] = None,
) -> Tuple[Dict[str, List[float]], List[Tuple[dt.date, float, float, int, int]]]:
    """Roll a `months`-forward window across every available month-end.

    For each snapshot date T (month-end with data) and each company:
      ret = price[T + months] / price[T] - 1

    Returns:
      flat_grouped: {"near_critical": [...all returns...], "other": [...]}
      monthly: list of (snapshot_date, mean_nc, mean_other, n_nc, n_other)
    """
    # Collect set of distinct snapshot dates from all tickers.
    all_dates: set = set()
    for series in prices.values():
        for d, _ in series:
            all_dates.add(d)
    timeline = sorted(all_dates)
    if min_snapshot:
        timeline = [d for d in timeline if d >= min_snapshot]
    if max_snapshot:
        timeline = [d for d in timeline if d <= max_snapshot]

    # We need each snapshot to have a corresponding T+months point available,
    # so cut tail.
    if not timeline:
        return {"near_critical": [], "other": []}, []
    # Filter to snapshots where target_end <= last available date overall.
    last_overall = timeline[-1]
    usable = [d for d in timeline if add_months(d, months) <= last_overall]

    flat_grouped: Dict[str, List[float]] = {"near_critical": [], "other": []}
    monthly: List[Tuple[dt.date, float, float, int, int]] = []

    # Pre-index companies by group for fast iteration
    nc_companies = [c for c in companies if c.group == "near_critical"]
    oth_companies = [c for c in companies if c.group == "other"]

    for snap in usable:
        target_end = add_months(snap, months)
        nc_rets: List[float] = []
        oth_rets: List[float] = []
        for grp, comps, bucket in (
            ("near_critical", nc_companies, nc_rets),
            ("other", oth_companies, oth_rets),
        ):
            for c in comps:
                series = prices.get(c.ticker)
                if not series:
                    continue
                anchor = _nearest_on_or_before(series, snap)
                if not anchor:
                    continue
                end_pt = _nearest_on_or_after(series, target_end)
                if not end_pt or anchor[1] <= 0:
                    continue
                # Sanity: end_pt must not equal anchor (no forward window)
                if end_pt[0] <= anchor[0]:
                    continue
                ret = (end_pt[1] - anchor[1]) / anchor[1]
                bucket.append(ret)
        flat_grouped["near_critical"].extend(nc_rets)
        flat_grouped["other"].extend(oth_rets)
        if nc_rets or oth_rets:
            mean_nc = statistics.fmean(nc_rets) if nc_rets else float("nan")
            mean_oth = statistics.fmean(oth_rets) if oth_rets else float("nan")
            monthly.append((snap, mean_nc, mean_oth, len(nc_rets), len(oth_rets)))

    LOG.info(
        "Walk-forward: %d snapshots, %d nc obs, %d other obs",
        len(monthly), len(flat_grouped["near_critical"]), len(flat_grouped["other"]),
    )
    return flat_grouped, monthly


def write_walk_forward_cumulative_csv(
    path: str,
    monthly: List[Tuple[dt.date, float, float, int, int]],
) -> int:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cum_nc = 0.0
    cum_oth = 0.0
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "snapshot_date", "mean_nc_ret", "mean_other_ret",
            "n_nc", "n_other", "cum_nc_ret", "cum_other_ret",
        ])
        for snap, mnc, moth, nnc, noth in monthly:
            # Compound monthly mean returns (treat each snapshot as a period sample).
            if not math.isnan(mnc):
                cum_nc = (1 + cum_nc) * (1 + mnc) - 1
            if not math.isnan(moth):
                cum_oth = (1 + cum_oth) * (1 + moth) - 1
            w.writerow([
                snap.isoformat(),
                f"{mnc:.6f}" if not math.isnan(mnc) else "",
                f"{moth:.6f}" if not math.isnan(moth) else "",
                nnc, noth,
                f"{cum_nc:.6f}",
                f"{cum_oth:.6f}",
            ])
    return len(monthly)


def plot_cumulative_png(
    path: str,
    monthly: List[Tuple[dt.date, float, float, int, int]],
    title_suffix: str = "",
) -> bool:
    """Render a 2-line cumulative-return plot. Returns True on success."""
    try:
        import matplotlib  # type: ignore
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        LOG.warning("matplotlib not installed; skipping PNG output")
        return False

    if not monthly:
        LOG.warning("no walk-forward data to plot")
        return False

    dates = [m[0] for m in monthly]
    cum_nc: List[float] = []
    cum_oth: List[float] = []
    cn = 0.0
    co = 0.0
    for _, mnc, moth, _, _ in monthly:
        if not math.isnan(mnc):
            cn = (1 + cn) * (1 + mnc) - 1
        if not math.isnan(moth):
            co = (1 + co) * (1 + moth) - 1
        cum_nc.append(cn)
        cum_oth.append(co)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(dates, [c * 100 for c in cum_nc], label="near_critical", linewidth=2.0, color="#d62728")
    ax.plot(dates, [c * 100 for c in cum_oth], label="other", linewidth=2.0, color="#1f77b4")
    ax.axhline(0, color="#888", linewidth=0.8, linestyle="--")
    ax.set_title(f"Phase Detector walk-forward cumulative return{title_suffix}")
    ax.set_xlabel("Snapshot date")
    ax.set_ylabel("Cumulative return (%)")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    LOG.info("Wrote PNG -> %s", path)
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase Detector backtest v0.2")
    parser.add_argument("--companies", default=None, help="StructTuple JSONL (default companies_500.jsonl)")
    parser.add_argument("--prices", default=DEFAULT_PRICES, help="Prices CSV path")
    parser.add_argument("--real-prices", action="store_true",
                        help="Use prices_500.csv (real fetched data) + walk-forward mode")
    parser.add_argument("--snapshot", default=DEFAULT_SNAPSHOT)
    parser.add_argument("--period", default="6m", help="6m | 12m | <integer months>")
    parser.add_argument("--walk-forward", action="store_true",
                        help="Roll snapshot month-by-month across price history")
    parser.add_argument("--result", default=DEFAULT_RESULT)
    parser.add_argument("--cumulative", default=DEFAULT_CUMCSV)
    parser.add_argument("--png", default=DEFAULT_CUMPNG, help="cumulative return PNG output path")
    parser.add_argument("--dry-run", action="store_true", help="Synthetic in-memory end-to-end")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    snapshot = dt.date.fromisoformat(args.snapshot)
    months = parse_period(args.period)

    # --real-prices implies walk-forward + the new prices_500.csv path
    if args.real_prices:
        if args.prices == DEFAULT_PRICES:
            args.prices = DEFAULT_REAL_PRICES
        args.walk_forward = True

    if args.dry_run:
        LOG.info("DRY RUN: building synthetic universe in-memory")
        companies, prices = _synth_dry_run(snapshot, months)
    else:
        comp_path = args.companies
        if comp_path is None:
            comp_path = DEFAULT_COMPANIES_PRIMARY if os.path.exists(DEFAULT_COMPANIES_PRIMARY) else DEFAULT_COMPANIES_FALLBACK
        if not os.path.exists(comp_path):
            LOG.error("Companies file not found: %s", comp_path)
            return 2
        if not os.path.exists(args.prices):
            LOG.error("Prices file not found: %s (run fetch_prices.py first)", args.prices)
            return 2
        companies = load_companies(comp_path)
        prices = load_prices(args.prices)
        LOG.info("Loaded %d companies from %s", len(companies), comp_path)
        total_rows = sum(len(v) for v in prices.values())
        LOG.info("Loaded %d price rows across %d tickers from %s", total_rows, len(prices), args.prices)

    nc_count = sum(1 for c in companies if c.group == "near_critical")
    oth_count = sum(1 for c in companies if c.group == "other")
    LOG.info("Group split: %d near_critical, %d other (snapshot=%s period=%dm walk_forward=%s)",
             nc_count, oth_count, snapshot, months, args.walk_forward)

    if args.walk_forward:
        return _run_walk_forward(args, companies, prices, snapshot, months)

    # ----- single-snapshot mode (v0.1 compat) -----
    grouped, used = compute_group_returns(companies, prices, snapshot, months)
    nc_summary = summarize(grouped["near_critical"], months)
    oth_summary = summarize(grouped["other"], months)
    t, p = ttest_groups(grouped["near_critical"], grouped["other"])

    LOG.info(
        "mean ret_nc=%.2f%% std=%.2f%% sharpe=%.2f (n=%d) | mean ret_oth=%.2f%% std=%.2f%% sharpe=%.2f (n=%d)",
        100 * nc_summary["mean"], 100 * nc_summary["std"], nc_summary["sharpe"], nc_summary["n"],
        100 * oth_summary["mean"], 100 * oth_summary["std"], oth_summary["sharpe"], oth_summary["n"],
    )
    LOG.info("Welch t=%.3f p=%.4g", t, p)

    cumulative = build_cumulative_curve(companies, prices, snapshot, months)
    n_cum = write_cumulative_csv(args.cumulative, cumulative)
    LOG.info("Wrote cumulative curve %d points -> %s", n_cum, args.cumulative)

    result = {
        "version": "0.1",
        "snapshot": snapshot.isoformat(),
        "period_months": months,
        "groups": {
            "near_critical": {
                **nc_summary,
                "tickers": used["near_critical"],
            },
            "other": {
                **oth_summary,
                "tickers": used["other"],
            },
        },
        "ttest_welch": {"t": t, "p": p},
        "synthetic": bool(args.dry_run) or _prices_are_synthetic(args.prices),
        "prices_meta": _read_prices_meta(args.prices),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    result_dir = os.path.dirname(args.result) or "."
    os.makedirs(result_dir, exist_ok=True)
    with open(args.result, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    LOG.info("Wrote result -> %s", args.result)
    return 0


def _run_walk_forward(
    args,
    companies: List[CompanyRow],
    prices: Dict[str, List[Tuple[dt.date, float]]],
    snapshot: dt.date,
    months: int,
) -> int:
    flat, monthly = walk_forward_returns(companies, prices, months)
    nc_summary = summarize(flat["near_critical"], months)
    oth_summary = summarize(flat["other"], months)
    t, p = ttest_groups(flat["near_critical"], flat["other"])

    LOG.info(
        "[walk-fwd] mean ret_nc=%.2f%% std=%.2f%% sharpe=%.2f (n=%d) | mean ret_oth=%.2f%% std=%.2f%% sharpe=%.2f (n=%d)",
        100 * nc_summary["mean"], 100 * nc_summary["std"], nc_summary["sharpe"], nc_summary["n"],
        100 * oth_summary["mean"], 100 * oth_summary["std"], oth_summary["sharpe"], oth_summary["n"],
    )
    LOG.info("[walk-fwd] Welch t=%.3f p=%.4g", t, p)

    n_cum = write_walk_forward_cumulative_csv(args.cumulative, monthly)
    LOG.info("[walk-fwd] wrote %d monthly rows -> %s", n_cum, args.cumulative)

    plot_cumulative_png(args.png, monthly, title_suffix=f" (period={months}mo, n_snapshots={len(monthly)})")

    result = {
        "version": "0.2",
        "mode": "walk_forward",
        "snapshot_anchor": snapshot.isoformat(),
        "period_months": months,
        "n_snapshots": len(monthly),
        "n_near_critical": nc_summary["n"],
        "n_other": oth_summary["n"],
        "mean_return_nc": nc_summary["mean"],
        "mean_return_other": oth_summary["mean"],
        "std_nc": nc_summary["std"],
        "std_other": oth_summary["std"],
        "sharpe_nc": nc_summary["sharpe"],
        "sharpe_other": oth_summary["sharpe"],
        "t_stat": t,
        "p_value": p,
        "groups": {
            "near_critical": {**nc_summary},
            "other": {**oth_summary},
        },
        "ttest_welch": {"t": t, "p": p},
        "synthetic": bool(args.dry_run) or _prices_are_synthetic(args.prices),
        "prices_meta": _read_prices_meta(args.prices),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    result_dir = os.path.dirname(args.result) or "."
    os.makedirs(result_dir, exist_ok=True)
    with open(args.result, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    LOG.info("[walk-fwd] wrote result -> %s", args.result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
