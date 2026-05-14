"""Fetch historical monthly prices for backtest engine v0.2.

Data source priority:
  1. yfinance batched download (default, ~50 tickers/batch with retry)
  2. Stooq daily CSV per-ticker fallback (aggregated to monthly close)
  3. Synthetic GBM fallback (only if --allow-synthetic + both real sources fail)

Output: prices_500.csv (long format: date, ticker, close)
Sibling metadata: prices.meta.json with provenance counts.
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
import time
import urllib.error
import urllib.request
from typing import Dict, Iterable, List, Optional, Tuple

LOG = logging.getLogger("fetch_prices")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(SCRIPT_DIR, "prices_500.csv")
DEFAULT_INPUT = os.path.join(SCRIPT_DIR, "companies_500.jsonl")
STOOQ_URL_TPL = "https://stooq.com/q/d/l/?s={ticker_lower}.us&i=d&d1={d1}&d2={d2}"
STOOQ_TIMEOUT_S = 10


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s %(message)s")


def load_tickers(path: str, limit: int | None) -> List[str]:
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
    # de-dup preserving order
    seen: set = set()
    uniq: List[str] = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


# ---------------------------------------------------------------------------
# yfinance fetcher (batched)
# ---------------------------------------------------------------------------

def fetch_yfinance(
    tickers: List[str],
    period: str = "2y",
    interval: str = "1mo",
    batch_size: int = 50,
    sleep_between_batches_s: float = 2.0,
    max_retries: int = 3,
) -> Dict[str, List[Tuple[dt.date, float]]]:
    """Batch-download monthly closes from yfinance with exponential backoff.

    Returns {ticker: [(date, close), ...]} for successfully fetched tickers.
    Tickers that fail across all retries are simply absent from the result.
    """
    try:
        import yfinance as yf  # type: ignore
        import pandas as pd  # type: ignore  # noqa: F401
    except ImportError:
        LOG.error("yfinance not installed; pip install yfinance pandas")
        return {}

    result: Dict[str, List[Tuple[dt.date, float]]] = {}
    n_batches = (len(tickers) + batch_size - 1) // batch_size
    for batch_idx in range(n_batches):
        batch = tickers[batch_idx * batch_size : (batch_idx + 1) * batch_size]
        LOG.info("yfinance batch %d/%d (%d tickers)", batch_idx + 1, n_batches, len(batch))
        attempt = 0
        df = None
        while attempt < max_retries:
            attempt += 1
            try:
                df = yf.download(
                    tickers=" ".join(batch),
                    period=period,
                    interval=interval,
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )
                break
            except Exception as exc:  # broad: yfinance throws many flavors
                wait = (2 ** attempt) + random.uniform(0, 1)
                LOG.warning("batch %d attempt %d failed: %s; sleep %.1fs", batch_idx + 1, attempt, exc, wait)
                time.sleep(wait)
                df = None
        if df is None or df.empty:
            LOG.warning("batch %d: empty after %d retries", batch_idx + 1, max_retries)
            time.sleep(sleep_between_batches_s)
            continue

        # parse single vs multi
        if len(batch) == 1:
            t = batch[0]
            series_df = df
            closes = _extract_close_series(series_df)
            if closes:
                result[t] = closes
        else:
            for t in batch:
                try:
                    sub = df[t] if t in df.columns.levels[0] else None
                except (AttributeError, KeyError):
                    sub = None
                if sub is None:
                    continue
                closes = _extract_close_series(sub)
                if closes:
                    result[t] = closes

        time.sleep(sleep_between_batches_s)

    LOG.info("yfinance fetched %d/%d tickers", len(result), len(tickers))
    return result


def _extract_close_series(df) -> List[Tuple[dt.date, float]]:
    """Extract (date, close) pairs from a pandas DataFrame with Close column."""
    try:
        if "Close" not in df.columns:
            return []
        closes = df["Close"].dropna()
        out: List[Tuple[dt.date, float]] = []
        for ts, val in closes.items():
            try:
                d = ts.date() if hasattr(ts, "date") else dt.date.fromisoformat(str(ts)[:10])
                out.append((d, float(val)))
            except (ValueError, TypeError):
                continue
        return out
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Stooq fallback (daily -> monthly aggregate)
# ---------------------------------------------------------------------------

def fetch_stooq_daily(ticker: str, start: dt.date, end: dt.date) -> List[Tuple[dt.date, float]]:
    """Pull daily closes from Stooq. Returns [] on failure."""
    url = STOOQ_URL_TPL.format(
        ticker_lower=ticker.lower(),
        d1=start.strftime("%Y%m%d"),
        d2=end.strftime("%Y%m%d"),
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "si-backtest/0.2"})
        with urllib.request.urlopen(req, timeout=STOOQ_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        LOG.debug("Stooq fetch failed for %s: %s", ticker, exc)
        return []

    if "No data" in raw or len(raw) < 30:
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


def aggregate_daily_to_monthly(daily: List[Tuple[dt.date, float]]) -> List[Tuple[dt.date, float]]:
    """Take last available close per month, key by month-end."""
    by_month: Dict[Tuple[int, int], Tuple[dt.date, float]] = {}
    for d, c in daily:
        k = (d.year, d.month)
        prev = by_month.get(k)
        if prev is None or d > prev[0]:
            by_month[k] = (d, c)
    out = [(d, c) for _, (d, c) in sorted(by_month.items())]
    return out


def fetch_stooq_monthly(ticker: str, start: dt.date, end: dt.date) -> List[Tuple[dt.date, float]]:
    daily = fetch_stooq_daily(ticker, start, end)
    if not daily:
        return []
    return aggregate_daily_to_monthly(daily)


# ---------------------------------------------------------------------------
# Synthetic fallback (only if explicitly enabled)
# ---------------------------------------------------------------------------

def synthetic_series(ticker: str, dates: List[dt.date], seed: int = 0) -> List[float]:
    h = abs(hash(ticker)) % 100
    rng = random.Random(seed * 1000 + h)
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
            local_mu = mu + 0.30
        price = price * math.exp(
            (local_mu - 0.5 * sigma * sigma) * dt_step + sigma * math.sqrt(dt_step) * z
        )
        out.append(round(price, 4))
    return out


def month_ends(start: dt.date, end: dt.date) -> List[dt.date]:
    out: List[dt.date] = []
    y, m = start.year, start.month
    while True:
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


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_prices_csv(out_path: str, records: Iterable[Tuple[str, dt.date, float]]) -> int:
    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "ticker", "close"])
        for ticker, date, close in records:
            w.writerow([date.isoformat(), ticker, f"{close:.4f}"])
            n += 1
    return n


def parse_period_to_days(period: str) -> int:
    """Parse strings like '2y', '12mo', '6m' to approx days."""
    period = period.strip().lower()
    if period.endswith("y"):
        return int(period[:-1]) * 365
    if period.endswith("mo"):
        return int(period[:-2]) * 31
    if period.endswith("m"):
        return int(period[:-1]) * 31
    if period.endswith("d"):
        return int(period[:-1])
    return int(period)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch monthly prices (yfinance + Stooq fallback)"
    )
    parser.add_argument("--tickers", default=DEFAULT_INPUT, help="JSONL input with ticker field")
    parser.add_argument("--input", dest="tickers", help="Alias for --tickers (back-compat)")
    parser.add_argument("--output", default=DEFAULT_OUT, help="Output CSV path")
    parser.add_argument("--out", dest="output", help="Alias for --output (back-compat)")
    parser.add_argument("--period", default="2y", help="yfinance period: 2y / 5y / max")
    parser.add_argument("--interval", default="1mo", help="yfinance interval: 1mo / 1wk / 1d")
    parser.add_argument("--limit", type=int, default=None, help="Cap ticker count")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--allow-synthetic", action="store_true", help="Fall back to synthetic for unfetched tickers")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-yfinance", action="store_true", help="Skip yfinance, Stooq only")
    parser.add_argument("--no-stooq", action="store_true", help="Skip Stooq fallback")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    end = dt.date.today()
    start = end - dt.timedelta(days=parse_period_to_days(args.period))

    tickers = load_tickers(args.tickers, args.limit)
    if not tickers:
        LOG.error("No tickers loaded from %s", args.tickers)
        return 2
    LOG.info("Loaded %d tickers, date range %s -> %s", len(tickers), start, end)

    # PHASE 1: yfinance batch
    yf_result: Dict[str, List[Tuple[dt.date, float]]] = {}
    if not args.no_yfinance:
        yf_result = fetch_yfinance(
            tickers,
            period=args.period,
            interval=args.interval,
            batch_size=args.batch_size,
            sleep_between_batches_s=args.sleep,
            max_retries=args.retries,
        )

    # PHASE 2: Stooq fallback for missing
    missing_after_yf = [t for t in tickers if t not in yf_result]
    stooq_result: Dict[str, List[Tuple[dt.date, float]]] = {}
    if missing_after_yf and not args.no_stooq:
        LOG.info("Stooq fallback for %d tickers missing from yfinance", len(missing_after_yf))
        for i, t in enumerate(missing_after_yf):
            rows = fetch_stooq_monthly(t, start, end)
            if rows:
                stooq_result[t] = rows
            if (i + 1) % 50 == 0:
                LOG.info("Stooq progress: %d/%d", i + 1, len(missing_after_yf))
            time.sleep(0.2)
        LOG.info("Stooq fetched %d/%d tickers", len(stooq_result), len(missing_after_yf))

    # PHASE 3: optional synthetic for residual
    missing_final = [t for t in tickers if t not in yf_result and t not in stooq_result]
    synth_result: Dict[str, List[Tuple[dt.date, float]]] = {}
    if missing_final and args.allow_synthetic:
        LOG.warning("Synthesizing %d residual tickers (--allow-synthetic)", len(missing_final))
        dates = month_ends(start, end)
        for t in missing_final:
            ser = synthetic_series(t, dates, seed=args.seed)
            synth_result[t] = list(zip(dates, ser))

    # Merge in priority order
    merged: Dict[str, List[Tuple[dt.date, float]]] = {}
    merged.update(synth_result)
    merged.update(stooq_result)
    merged.update(yf_result)

    out_records: List[Tuple[str, dt.date, float]] = []
    for t in tickers:
        series = merged.get(t)
        if not series:
            continue
        for d, c in series:
            out_records.append((t, d, c))

    n = write_prices_csv(args.output, out_records)

    LOG.info(
        "Wrote %d rows to %s (yfinance=%d, stooq=%d, synthetic=%d, missing=%d)",
        n, args.output,
        len(yf_result), len(stooq_result), len(synth_result),
        len(tickers) - len(yf_result) - len(stooq_result) - len(synth_result),
    )

    meta_path = os.path.join(
        os.path.dirname(args.output) or ".", "prices.meta.json"
    )
    meta = {
        "version": "0.2",
        "yfinance_tickers": len(yf_result),
        "stooq_tickers": len(stooq_result),
        "synthetic_tickers": len(synth_result),
        "missing_tickers": len(tickers) - len(yf_result) - len(stooq_result) - len(synth_result),
        "synthetic": len(synth_result) > 0,
        "all_synthetic": len(synth_result) > 0 and (len(yf_result) + len(stooq_result)) == 0,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "period": args.period,
        "interval": args.interval,
        "n_total_tickers": len(tickers),
        "n_rows": n,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    LOG.info("Wrote metadata -> %s", meta_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
