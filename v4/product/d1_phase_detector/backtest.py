"""Phase Detector backtest engine v0.1.

Hypothesis under test:
    "Companies classified as `near_critical` (= approaching_critical OR
     at_critical) at snapshot T have a meaningfully different forward
     return over the next 6 (or 12) months versus the rest."

Inputs:
  --companies   companies_500.jsonl (Wave 1 StructTuple) or fallback companies.jsonl
  --prices      data/prices.csv produced by fetch_prices.py
  --snapshot    YYYY-MM-DD anchor date (default 2026-05-14)
  --period      6m | 12m
  --dry-run     run end-to-end on synthetic data with no externals

Outputs:
  data/backtest_result.json     {mean, std, sharpe, t, p, n_per_group, ...}
  data/backtest_cumulative.csv  date, near_critical_cumret, other_cumret
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
DEFAULT_COMPANIES_PRIMARY = os.path.join(SCRIPT_DIR, "companies_500.jsonl")
DEFAULT_COMPANIES_FALLBACK = os.path.join(SCRIPT_DIR, "companies.jsonl")
DEFAULT_RESULT = os.path.join(SCRIPT_DIR, "data", "backtest_result.json")
DEFAULT_CUMCSV = os.path.join(SCRIPT_DIR, "data", "backtest_cumulative.csv")
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
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase Detector backtest v0.1")
    parser.add_argument("--companies", default=None, help="StructTuple JSONL (default companies_500.jsonl)")
    parser.add_argument("--prices", default=DEFAULT_PRICES)
    parser.add_argument("--snapshot", default=DEFAULT_SNAPSHOT)
    parser.add_argument("--period", default="6m", help="6m | 12m | <integer months>")
    parser.add_argument("--result", default=DEFAULT_RESULT)
    parser.add_argument("--cumulative", default=DEFAULT_CUMCSV)
    parser.add_argument("--dry-run", action="store_true", help="Synthetic in-memory end-to-end")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    snapshot = dt.date.fromisoformat(args.snapshot)
    months = parse_period(args.period)

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
    LOG.info("Group split: %d near_critical, %d other (snapshot=%s period=%dm)",
             nc_count, oth_count, snapshot, months)

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
    os.makedirs(os.path.dirname(args.result), exist_ok=True)
    with open(args.result, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    LOG.info("Wrote result -> %s", args.result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
