***REMOVED***!/usr/bin/env python3
"""Walk-forward backtest v0.1 — W7-D mini-brief 4 (2026-05-24).

Hypothesis (per W7-D § 4.B):
    Companies classified as `near_critical` by D1 Phase Detector in month M
    outperform an equal-weighted benchmark in months M+1 .. M+3.

This v0.1 prioritises **pipeline correctness over real-data findings**.
When real D1 + yfinance data is wired, drop --mock and the same pipeline
runs against production data without code changes.

Pipeline:
    For each rebalance month from 2020-01 to 2024-12 (inclusive):
        1. Look up the cohort: tickers labeled `near_critical` AS OF the
           1st trading day of the month (point-in-time, no look-ahead).
        2. Hold equal-weight one month, until next rebalance.
        3. Compute monthly return for cohort vs SPY benchmark.
    Aggregate:
        - cumulative wealth curve for cohort + SPY
        - annualized Sharpe (per-cohort, per-SPY, difference)
        - max drawdown for each
        - one-way turnover (% of holdings rotated per rebalance)

Inputs (in order of preference):
    --companies <path>   100-row JSON  (see _MOCK_COMPANIES for shape)
                         OR `data/phase-detector/companies.json`
    --prices  <path>     CSV  date,SPY,<ticker>,<ticker>,...
                         OR `data/phase-detector/prices.csv`
    --mock               force-use bundled mock data (default if either
                         input is missing)

Outputs:
    backtest/results/walk-forward-v0.1.json    — machine-readable
    backtest/results/walk-forward-v0.1.md      — short report

Usage:
    python3 scripts/backtest_walk_forward.py            ***REMOVED*** mock if data absent
    python3 scripts/backtest_walk_forward.py --mock     ***REMOVED*** explicit
    python3 scripts/backtest_walk_forward.py --start 2020-01-01 --end 2024-12-31
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("structural.backtest")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "backtest" / "results"
DEFAULT_COMPANIES = REPO_ROOT / "data" / "phase-detector" / "companies.json"
DEFAULT_PRICES = REPO_ROOT / "data" / "phase-detector" / "prices.csv"


***REMOVED*** ----------------- Mock data generation -----------------

_MOCK_TICKERS = [f"M{i:03d}" for i in range(100)]


def _mock_companies() -> list[dict[str, Any]]:
    """100 synthetic tickers. Each has a per-month phase trace (60 months)
    so we can do a true walk-forward without look-ahead.

    Companies have a stable family + a per-month phase label. We seed
    deterministically so two runs produce identical outputs (idempotency
    matters for backtest credibility)."""
    rng = random.Random(42)
    families = ["bistable", "phase_transition", "metastable", "growth_regime", "stationary"]
    out: list[dict[str, Any]] = []
    for t in _MOCK_TICKERS:
        family = rng.choice(families)
        phases: dict[str, str] = {}
        ***REMOVED*** 60 months 2020-01 .. 2024-12
        for y in range(2020, 2025):
            for m in range(1, 13):
                key = f"{y:04d}-{m:02d}"
                ***REMOVED*** Higher chance of near_critical in dec 2021 / mar 2023 for variety
                p = rng.random()
                if (y == 2021 and m == 12) or (y == 2023 and m == 3):
                    label = "near_critical" if p < 0.30 else "stable"
                else:
                    label = "near_critical" if p < 0.10 else "stable"
                phases[key] = label
        out.append({"ticker": t, "dynamics_family": family, "phases": phases})
    return out


def _mock_prices(tickers: list[str], months: list[dt.date]) -> dict[str, dict[str, float]]:
    """Return prices[ticker][YYYY-MM-DD]. SPY is at index 0 of the returned
    dict under key 'SPY'. Use a multiplicative random walk with mild drift
    so the cohort beats SPY ~ half the time (we WANT this v0.1 to look
    honest, not rigged)."""
    rng = random.Random(7)
    prices: dict[str, dict[str, float]] = {}
    keys = ["SPY"] + tickers
    for k in keys:
        p = 100.0
        per_month: dict[str, float] = {}
        for m in months:
            mu = 0.006 if k == "SPY" else 0.005  ***REMOVED*** ~7%/yr drift, slightly higher for SPY
            sigma = 0.03 if k == "SPY" else 0.06
            r = rng.gauss(mu, sigma)
            p *= (1.0 + r)
            per_month[m.isoformat()] = round(p, 4)
        prices[k] = per_month
    return prices


***REMOVED*** ----------------- Data loading -----------------

def load_companies(path: Optional[Path]) -> tuple[list[dict[str, Any]], str]:
    """Load companies file. Return (list, source_label)."""
    if path and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data, "real"
        except Exception as e:
            logger.warning("companies load failed: %s — using mock", e)
    return _mock_companies(), "mock"


def load_prices(
    path: Optional[Path],
    tickers: list[str],
    months: list[dt.date],
) -> tuple[dict[str, dict[str, float]], str]:
    """Load CSV prices. Header row: date,SPY,ticker1,ticker2,...
    Return (prices_dict, source_label)."""
    if path and path.exists():
        try:
            prices: dict[str, dict[str, float]] = {}
            with open(path, "r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                header = next(reader)
                cols = header[1:]
                for col in cols:
                    prices[col] = {}
                for row in reader:
                    if not row:
                        continue
                    date_str = row[0]
                    for i, col in enumerate(cols, start=1):
                        if i < len(row) and row[i]:
                            try:
                                prices[col][date_str] = float(row[i])
                            except ValueError:
                                pass
            if "SPY" in prices and any(t in prices for t in tickers[:5]):
                return prices, "real"
        except Exception as e:
            logger.warning("prices load failed: %s — using mock", e)
    return _mock_prices(tickers, months), "mock"


***REMOVED*** ----------------- Walk-forward loop -----------------

def month_starts(start: dt.date, end: dt.date) -> list[dt.date]:
    """Inclusive list of first-day-of-month dates between start and end."""
    out = []
    y, m = start.year, start.month
    while True:
        d = dt.date(y, m, 1)
        if d > end:
            break
        out.append(d)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def cohort_for_month(companies: list[dict[str, Any]], ym: str) -> list[str]:
    """Tickers labeled `near_critical` AS OF the start of month `ym` (YYYY-MM)."""
    out = []
    for c in companies:
        phases = c.get("phases", {})
        if phases.get(ym) == "near_critical":
            out.append(c["ticker"])
    return out


def monthly_return(prices: dict[str, float], d1: dt.date, d2: dt.date) -> Optional[float]:
    """Total return between two first-of-month dates. None if either missing."""
    p1 = prices.get(d1.isoformat())
    p2 = prices.get(d2.isoformat())
    if p1 is None or p2 is None or p1 == 0:
        return None
    return (p2 / p1) - 1.0


def run_walk_forward(
    companies: list[dict[str, Any]],
    prices: dict[str, dict[str, float]],
    start: dt.date,
    end: dt.date,
) -> dict[str, Any]:
    """Walk-forward loop. Returns a summary dict."""
    months = month_starts(start, end)
    rebalances = []
    prev_holdings: set[str] = set()
    cohort_rets: list[float] = []
    spy_rets: list[float] = []

    for i in range(len(months) - 1):
        d1, d2 = months[i], months[i + 1]
        ym = d1.strftime("%Y-%m")
        cohort = cohort_for_month(companies, ym)
        ***REMOVED*** Equal-weighted; if zero, fall through to SPY (cash equivalent)
        rets: list[float] = []
        for t in cohort:
            r = monthly_return(prices.get(t, {}), d1, d2)
            if r is not None:
                rets.append(r)
        cohort_ret = (sum(rets) / len(rets)) if rets else 0.0
        spy_ret = monthly_return(prices.get("SPY", {}), d1, d2) or 0.0

        holdings = set(cohort)
        if not prev_holdings and not holdings:
            turnover = 0.0
        elif not prev_holdings:
            turnover = 1.0
        else:
            symmetric_diff = prev_holdings.symmetric_difference(holdings)
            turnover = len(symmetric_diff) / (2 * max(len(prev_holdings | holdings), 1))
        prev_holdings = holdings

        rebalances.append({
            "month": ym,
            "n_holdings": len(cohort),
            "cohort_return": cohort_ret,
            "spy_return": spy_ret,
            "active_return": cohort_ret - spy_ret,
            "turnover": round(turnover, 4),
        })
        cohort_rets.append(cohort_ret)
        spy_rets.append(spy_ret)

    return {
        "rebalances": rebalances,
        "summary": _summarize(cohort_rets, spy_rets, rebalances),
    }


def _summarize(
    cohort_rets: list[float],
    spy_rets: list[float],
    rebalances: list[dict[str, Any]],
) -> dict[str, Any]:
    def _ann_sharpe(rets: list[float]) -> float:
        if len(rets) < 2:
            return 0.0
        mean = statistics.mean(rets)
        sd = statistics.pstdev(rets)
        if sd == 0:
            return 0.0
        return (mean / sd) * math.sqrt(12)

    def _max_dd(rets: list[float]) -> float:
        wealth = 1.0
        peak = 1.0
        dd = 0.0
        for r in rets:
            wealth *= (1.0 + r)
            peak = max(peak, wealth)
            dd = min(dd, (wealth / peak) - 1.0)
        return dd

    def _cumret(rets: list[float]) -> float:
        w = 1.0
        for r in rets:
            w *= (1.0 + r)
        return w - 1.0

    avg_turnover = (
        statistics.mean([r["turnover"] for r in rebalances])
        if rebalances else 0.0
    )

    return {
        "n_rebalances": len(rebalances),
        "cohort_cum_return": _cumret(cohort_rets),
        "spy_cum_return": _cumret(spy_rets),
        "cohort_sharpe": _ann_sharpe(cohort_rets),
        "spy_sharpe": _ann_sharpe(spy_rets),
        "sharpe_lift": _ann_sharpe(cohort_rets) - _ann_sharpe(spy_rets),
        "cohort_max_drawdown": _max_dd(cohort_rets),
        "spy_max_drawdown": _max_dd(spy_rets),
        "avg_turnover": round(avg_turnover, 4),
    }


***REMOVED*** ----------------- Report rendering -----------------

def render_report_md(
    result: dict[str, Any],
    data_label: str,
    start: dt.date,
    end: dt.date,
) -> str:
    s = result["summary"]
    honesty = ""
    if data_label == "mock":
        honesty = (
            "\n> ⚠️ **v0.1 uses MOCK data to validate pipeline only.** "
            "Real data ingest (yfinance + D1 100-company snapshots) lands in v0.2. "
            "Numbers below describe the **synthetic** universe — do not interpret as alpha.\n"
        )

    lines = [
        f"***REMOVED*** Walk-forward backtest v0.1",
        "",
        f"_Window_: {start.isoformat()} → {end.isoformat()}",
        f"_Data source_: **{data_label}**",
        f"_Rebalances_: {s['n_rebalances']} months",
        honesty,
        "***REMOVED******REMOVED*** Headline numbers",
        "",
        "| Metric | Cohort (`near_critical`) | SPY benchmark |",
        "|---|---:|---:|",
        f"| Cumulative return | {s['cohort_cum_return']*100:+.2f}% | {s['spy_cum_return']*100:+.2f}% |",
        f"| Annualized Sharpe | {s['cohort_sharpe']:+.2f} | {s['spy_sharpe']:+.2f} |",
        f"| Max drawdown | {s['cohort_max_drawdown']*100:+.2f}% | {s['spy_max_drawdown']*100:+.2f}% |",
        f"| Sharpe lift | **{s['sharpe_lift']:+.2f}** | — |",
        f"| Avg turnover / rebalance | **{s['avg_turnover']*100:.1f}%** | — |",
        "",
        "***REMOVED******REMOVED*** Reading guide",
        "",
        "Per W7-D § 4.B pre-commits:",
        "",
        "| Outcome | Threshold | Response |",
        "|---|---|---|",
        "| Strong signal | Sharpe lift ≥ +0.5 | Lean into alpha-screener positioning |",
        "| Weak signal | +0.1 .. +0.4 | Honest positioning, transparent methodology |",
        "| Null result | ≤ +0.1 | Pivot to structured-research-narrative product |",
        "",
        "***REMOVED******REMOVED*** Pipeline notes",
        "",
        "- Walk-forward, point-in-time cohort lookup (no look-ahead bias)",
        "- Equal-weight monthly rebalance",
        "- Cash-equivalent fallback when cohort is empty for a given month",
        "- Turnover = symmetric-difference / union of holdings month-over-month",
        "- v0.1 limitations: no transaction costs, no shorts, no factor decomposition",
        "",
        "***REMOVED******REMOVED*** Next steps for v0.2",
        "",
        "- Replace mock prices with yfinance close-prices for SPY + 100 mock tickers (real tickers TBD)",
        "- Wire D1 monthly snapshots (one JSON per month, 60 months 2020-01..2024-12)",
        "- Add bootstrap CI on Sharpe lift",
        "- Sector-neutralization via SPDR sector ETFs",
    ]
    return "\n".join(lines) + "\n"


***REMOVED*** ----------------- CLI -----------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward backtest v0.1")
    parser.add_argument("--companies", default=str(DEFAULT_COMPANIES))
    parser.add_argument("--prices", default=str(DEFAULT_PRICES))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--mock", action="store_true",
                        help="Force-use bundled mock data even if real exists")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.mock:
        companies, c_src = _mock_companies(), "mock"
    else:
        companies, c_src = load_companies(Path(args.companies))

    tickers = [c["ticker"] for c in companies]
    months = month_starts(start, end)

    if args.mock:
        prices, p_src = _mock_prices(tickers, months), "mock"
    else:
        prices, p_src = load_prices(Path(args.prices), tickers, months)

    data_label = "mock" if (c_src == "mock" or p_src == "mock") else "real"

    result = run_walk_forward(companies, prices, start, end)
    result["meta"] = {
        "version": "v0.1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(
            sep=" ", timespec="seconds"),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "data_source": data_label,
        "n_companies": len(companies),
    }

    json_path = out_dir / "walk-forward-v0.1.json"
    md_path = out_dir / "walk-forward-v0.1.md"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md_path.write_text(render_report_md(result, data_label, start, end), encoding="utf-8")

    logger.info(
        "wrote %s + %s (data=%s rebalances=%d sharpe_lift=%+.2f)",
        json_path, md_path, data_label,
        result["summary"]["n_rebalances"], result["summary"]["sharpe_lift"],
    )
    print(str(md_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
