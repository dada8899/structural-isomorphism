"""Fetch daily OHLCV for the 1000-ticker backtest universe.

Source: yfinance batched download (preferred, free, no key).
Cache: per-ticker parquet/CSV files at backtest/data/prices/<ticker>.csv.
Reruns reuse cache; pass --force to override.

Time window: 2020-01-01 to 2025-12-31 (5+ years; spans COVID + zero-rate +
tightening + AI rally).

Usage:
  python3 fetch_prices.py                            # full universe (cached)
  python3 fetch_prices.py --limit 50                 # smoke test on 50
  python3 fetch_prices.py --tickers AAPL,TSLA,NVDA   # subset
  python3 fetch_prices.py --force                    # ignore cache
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import os
import sys
import time

LOG = logging.getLogger("fetch_prices_1000")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_UNIVERSE = os.path.join(SCRIPT_DIR, "..", "data", "1000_universe.csv")
DEFAULT_PRICES_DIR = os.path.join(SCRIPT_DIR, "..", "data", "prices")
DEFAULT_META = os.path.join(SCRIPT_DIR, "..", "data", "prices.meta.json")
DEFAULT_START = "2020-01-01"
DEFAULT_END = "2025-12-31"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s %(message)s")


def load_universe(path: str, limit: int | None = None) -> list[str]:
    out: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row.get("ticker", "").strip().upper()
            if t:
                out.append(t)
            if limit and len(out) >= limit:
                break
    return out


def _cache_path(prices_dir: str, ticker: str) -> str:
    # Sanitize ticker for filesystem (dots become underscores)
    safe = ticker.replace(".", "_").replace("/", "_")
    return os.path.join(prices_dir, f"{safe}.csv")


def _is_cached(prices_dir: str, ticker: str, min_rows: int = 100) -> bool:
    p = _cache_path(prices_dir, ticker)
    if not os.path.exists(p):
        return False
    try:
        with open(p, "r", encoding="utf-8") as f:
            n = sum(1 for _ in f)
        return n >= min_rows
    except OSError:
        return False


def _write_ticker_csv(prices_dir: str, ticker: str, rows: list[tuple[dt.date, float, float, float, float, int]]) -> None:
    os.makedirs(prices_dir, exist_ok=True)
    p = _cache_path(prices_dir, ticker)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        for d, o, h, l, c, v in rows:
            w.writerow([d.isoformat(), f"{o:.6f}", f"{h:.6f}", f"{l:.6f}", f"{c:.6f}", v])


def fetch_yfinance_batch(
    tickers: list[str],
    start: str,
    end: str,
    batch_size: int = 50,
    sleep_s: float = 1.5,
    max_retries: int = 3,
) -> tuple[dict[str, list[tuple[dt.date, float, float, float, float, int]]], list[str]]:
    """Fetch daily OHLCV. Returns (results, failed_tickers)."""
    try:
        import yfinance as yf  # type: ignore
        import pandas as pd  # type: ignore
    except ImportError:
        LOG.error("yfinance not installed; pip install yfinance pandas")
        return {}, list(tickers)

    out: dict = {}
    failed: list[str] = []
    n_batches = (len(tickers) + batch_size - 1) // batch_size

    for bi in range(n_batches):
        batch = tickers[bi * batch_size : (bi + 1) * batch_size]
        LOG.info("yfinance batch %d/%d (%d tickers)", bi + 1, n_batches, len(batch))
        df = None
        for attempt in range(1, max_retries + 1):
            try:
                df = yf.download(
                    tickers=" ".join(batch),
                    start=start,
                    end=end,
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )
                break
            except Exception as exc:
                wait = 2.0 * attempt
                LOG.warning("batch %d attempt %d failed: %s (sleep %.1fs)", bi + 1, attempt, exc, wait)
                time.sleep(wait)
        if df is None or df.empty:
            LOG.warning("batch %d: empty after retries; %d tickers failed", bi + 1, len(batch))
            failed.extend(batch)
            time.sleep(sleep_s)
            continue

        # parse single vs multi ticker DataFrame
        if len(batch) == 1:
            t = batch[0]
            rows = _extract_ohlcv(df)
            if rows:
                out[t] = rows
            else:
                failed.append(t)
        else:
            try:
                level0 = set(df.columns.levels[0])  # ticker level
            except AttributeError:
                level0 = set()
            for t in batch:
                if t not in level0:
                    failed.append(t)
                    continue
                sub = df[t]
                rows = _extract_ohlcv(sub)
                if rows:
                    out[t] = rows
                else:
                    failed.append(t)

        time.sleep(sleep_s)

    return out, failed


def _extract_ohlcv(df) -> list[tuple[dt.date, float, float, float, float, int]]:
    """Extract OHLCV rows from a yfinance DataFrame."""
    try:
        need_cols = ["Open", "High", "Low", "Close", "Volume"]
        for c in need_cols:
            if c not in df.columns:
                return []
        sub = df[need_cols].dropna(how="all")
        rows: list = []
        for ts, row in sub.iterrows():
            try:
                d = ts.date() if hasattr(ts, "date") else dt.date.fromisoformat(str(ts)[:10])
                o, h, l, cl, v = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), int(row["Volume"]) if row["Volume"] == row["Volume"] else 0
                if cl != cl:  # NaN check
                    continue
                rows.append((d, o, h, l, cl, v))
            except (ValueError, TypeError):
                continue
        return rows
    except Exception:
        return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default=DEFAULT_UNIVERSE)
    ap.add_argument("--prices-dir", default=DEFAULT_PRICES_DIR)
    ap.add_argument("--meta", default=DEFAULT_META)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--limit", type=int, default=None, help="Stop after N tickers")
    ap.add_argument("--tickers", default=None, help="Comma-separated ticker subset")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--force", action="store_true", help="Ignore cache, refetch")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    _setup_logging(args.verbose)
    os.makedirs(args.prices_dir, exist_ok=True)

    if args.tickers:
        universe = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        universe = load_universe(args.universe, args.limit)
    LOG.info("Universe: %d tickers", len(universe))

    # Skip cached tickers unless --force
    if args.force:
        to_fetch = universe
    else:
        to_fetch = [t for t in universe if not _is_cached(args.prices_dir, t)]
        cached_n = len(universe) - len(to_fetch)
        LOG.info("Cache hit: %d/%d (refetching %d)", cached_n, len(universe), len(to_fetch))

    fetched: dict = {}
    failed: list[str] = []
    if to_fetch:
        fetched, failed = fetch_yfinance_batch(
            to_fetch, args.start, args.end, batch_size=args.batch_size
        )
        for t, rows in fetched.items():
            _write_ticker_csv(args.prices_dir, t, rows)
        LOG.info("Wrote %d ticker CSVs to %s", len(fetched), args.prices_dir)

    # Count final coverage (cache + new fetches)
    covered = [t for t in universe if _is_cached(args.prices_dir, t)]
    meta = {
        "version": "0.1",
        "start": args.start,
        "end": args.end,
        "interval": "1d",
        "source": "yfinance",
        "n_universe": len(universe),
        "n_covered": len(covered),
        "n_failed_this_run": len(failed),
        "n_fetched_this_run": len(fetched),
        "failed_examples": failed[:30],
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(args.meta), exist_ok=True)
    with open(args.meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    LOG.info("Wrote meta -> %s", args.meta)
    LOG.info("Coverage: %d/%d tickers (%.1f%%)", len(covered), len(universe), 100 * len(covered) / max(len(universe), 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
