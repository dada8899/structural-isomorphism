"""Fetch historical monthly prices for backtest engine v0.1.

Data source priority:
  1. Stooq monthly CSV (https://stooq.com/q/d/?s=AAPL.US&i=m&...) — free, no auth
  2. Synthetic GBM fallback (default) for dev — no network dependency

By default this script runs in SYNTHETIC mode and prints a WARNING. Pass --real
to attempt Stooq fetch (likely to be flaky from CN egress / behind NAT).

Output: data/prices.csv  with columns: date, ticker, close
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import logging
import math
import os
import random
import sys
import urllib.error
import urllib.request
from typing import Iterable, List, Tuple

LOG = logging.getLogger("fetch_prices")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(SCRIPT_DIR, "data", "prices.csv")
DEFAULT_INPUT = os.path.join(SCRIPT_DIR, "companies_500_input.jsonl")
STOOQ_URL_TPL = "https://stooq.com/q/d/l/?s={ticker_lower}.us&i=m&d1={d1}&d2={d2}"
STOOQ_TIMEOUT_S = 8


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s %(message)s")


def load_tickers(path: str, limit: int | None) -> List[str]:
    """Load ticker symbols from a JSONL file with `ticker` field."""
    tickers: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("ticker") or rec.get("symbol")
            if t:
                tickers.append(t.upper())
            if limit and len(tickers) >= limit:
                break
    return tickers


def month_ends(start: dt.date, end: dt.date) -> List[dt.date]:
    """Generate month-end dates between start and end inclusive."""
    out: List[dt.date] = []
    y, m = start.year, start.month
    while True:
        # last day of (y, m)
        if m == 12:
            last = dt.date(y, 12, 31)
        else:
            last = dt.date(y, m + 1, 1) - dt.timedelta(days=1)
        if last > end:
            break
        if last >= start:
            out.append(last)
        m += 1
        if m > 12:
            y += 1
            m = 1
    return out


def synthetic_series(ticker: str, dates: List[dt.date], seed: int = 0) -> List[float]:
    """Generate a Geometric Brownian Motion price series.

    Drift and volatility are deterministic from ticker hash so reruns are stable.
    For ~10% of tickers we inject an upward jump in the second half of the window
    to mimic an "approaching_critical -> post_transition" rally — backtest
    differential power test relies on at least *some* differential signal.
    """
    h = abs(hash(ticker)) % 100
    rng = random.Random(seed * 1000 + h)
    # annualized drift in [-0.05, 0.15], vol in [0.15, 0.45]
    mu = -0.05 + (h % 21) * 0.01
    sigma = 0.15 + ((h * 7) % 31) * 0.01
    dt_step = 1.0 / 12.0
    price = 50.0 + (h % 50) * 2
    out: List[float] = []
    rally_start_idx = len(dates) // 2 if (h % 10 == 0) else None
    for i, _d in enumerate(dates):
        z = rng.gauss(0.0, 1.0)
        local_mu = mu
        if rally_start_idx is not None and i >= rally_start_idx:
            local_mu = mu + 0.30  # inject upward drift for "near_critical" rally pattern
        price = price * math.exp((local_mu - 0.5 * sigma * sigma) * dt_step + sigma * math.sqrt(dt_step) * z)
        out.append(round(price, 4))
    return out


def fetch_stooq_monthly(ticker: str, start: dt.date, end: dt.date) -> List[Tuple[dt.date, float]]:
    """Pull monthly closes from Stooq. Returns [] on any failure."""
    url = STOOQ_URL_TPL.format(
        ticker_lower=ticker.lower(),
        d1=start.strftime("%Y%m%d"),
        d2=end.strftime("%Y%m%d"),
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "si-backtest/0.1"})
        with urllib.request.urlopen(req, timeout=STOOQ_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        LOG.warning("Stooq fetch failed for %s: %s", ticker, exc)
        return []

    if "No data" in raw or len(raw) < 30:
        LOG.warning("Stooq returned empty/no-data for %s", ticker)
        return []

    rows: List[Tuple[dt.date, float]] = []
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        try:
            d = dt.datetime.strptime(row["Date"], "%Y-%m-%d").date()
            c = float(row["Close"])
            rows.append((d, c))
        except (KeyError, ValueError):
            continue
    return rows


def write_prices_csv(out_path: str, records: Iterable[Tuple[str, dt.date, float]]) -> int:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    n = 0
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "ticker", "close"])
        for ticker, date, close in records:
            w.writerow([date.isoformat(), ticker, f"{close:.4f}"])
            n += 1
    return n


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch monthly prices (Stooq + synthetic fallback)")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="JSONL input with ticker field")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output CSV path")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD (default: 24 months ago)")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--limit", type=int, default=None, help="Cap ticker count for dev")
    parser.add_argument("--real", action="store_true", help="Attempt Stooq real fetch (otherwise synthetic)")
    parser.add_argument("--dry-run", action="store_true", help="Force synthetic + small limit")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for synthetic mode")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    if args.dry_run:
        args.real = False
        if args.limit is None:
            args.limit = 30
        LOG.info("--dry-run -> synthetic mode, limit=%d", args.limit)

    end = dt.date.fromisoformat(args.end) if args.end else dt.date.today()
    start = dt.date.fromisoformat(args.start) if args.start else (end - dt.timedelta(days=24 * 31))
    # For synthetic mode, extend end +12 months so backtest snapshot=today still
    # has price points covering the forward window. Real Stooq calls won't generate
    # future data (server-side cutoff) so this only affects synthetic series.
    if not args.real and args.end is None:
        end_extended = end + dt.timedelta(days=12 * 31)
        LOG.info("Synthetic mode: extending end %s -> %s for forward-return coverage", end, end_extended)
        end = end_extended

    tickers = load_tickers(args.input, args.limit)
    if not tickers:
        LOG.error("No tickers loaded from %s", args.input)
        return 2
    LOG.info("Loaded %d tickers from %s", len(tickers), args.input)
    LOG.info("Date range: %s -> %s", start, end)

    dates = month_ends(start, end)
    LOG.info("Month-end grid: %d points", len(dates))

    out_records: List[Tuple[str, dt.date, float]] = []
    synth_count = 0
    real_count = 0

    if not args.real:
        print("WARNING: USING SYNTHETIC FOR DEV (no real market data fetched)", file=sys.stderr)
        for t in tickers:
            series = synthetic_series(t, dates, seed=args.seed)
            for d, c in zip(dates, series):
                out_records.append((t, d, c))
            synth_count += 1
    else:
        LOG.info("Attempting Stooq real fetch (will fall back to synthetic per-ticker)")
        for t in tickers:
            rows = fetch_stooq_monthly(t, start, end)
            if rows:
                for d, c in rows:
                    out_records.append((t, d, c))
                real_count += 1
            else:
                LOG.warning("Synthesizing for %s due to fetch miss", t)
                series = synthetic_series(t, dates, seed=args.seed)
                for d, c in zip(dates, series):
                    out_records.append((t, d, c))
                synth_count += 1

    n = write_prices_csv(args.out, out_records)
    LOG.info("Wrote %d rows to %s (real=%d synth=%d tickers)", n, args.out, real_count, synth_count)

    # Sibling metadata file so downstream (backtest.py) can report data provenance honestly.
    meta_path = os.path.join(os.path.dirname(args.out), "prices.meta.json")
    meta = {
        "synthetic_tickers": synth_count,
        "real_tickers": real_count,
        "synthetic": synth_count > 0,
        "all_synthetic": real_count == 0,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "n_rows": n,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    LOG.info("Wrote metadata -> %s", meta_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
