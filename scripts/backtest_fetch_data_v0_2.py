#!/usr/bin/env python3
"""Fetch SP500 top-100 + SPY monthly close prices 2020-2024 — W7-D v0.2.

Output:
    backtest/data/sp500-top100-2020-2024.parquet  (LFS via .gitattributes)
    backtest/data/sp500-top100-2020-2024.meta.json

Honesty rules:
    - If yfinance succeeds for SPY + >= 80 of top-100 → status = "REAL"
    - If yfinance partially fails → status = "PARTIAL_REAL" with missing list
    - If yfinance entirely fails → status = "FETCH_FAILED" (don't fabricate)

Universe:
    top-100 by market cap from v4/product/d1_phase_detector/companies.jsonl.

The D1 classification (single-snapshot 2026-05-13) lives in
companies_500.jsonl; this script only fetches prices.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger("backtest.fetch")
REPO_ROOT = Path(__file__).resolve().parent.parent
COMPANIES_PATH = REPO_ROOT / "v4" / "product" / "d1_phase_detector" / "companies.jsonl"
OUT_DIR = REPO_ROOT / "backtest" / "data"
OUT_PARQUET = OUT_DIR / "sp500-top100-2020-2024.parquet"
OUT_META = OUT_DIR / "sp500-top100-2020-2024.meta.json"


def load_top100_tickers() -> list[str]:
    tickers: list[str] = []
    with COMPANIES_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            t = rec.get("ticker")
            if t:
                tickers.append(t)
    return tickers


def fetch_yfinance_batch(
    tickers: list[str],
    start: str,
    end: str,
    interval: str = "1mo",
    batch_size: int = 20,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Fetch yfinance prices in batches.

    Returns (long_df, succeeded_tickers, failed_tickers).
    long_df columns: date, ticker, close.
    """
    all_frames: list[pd.DataFrame] = []
    succeeded: list[str] = []
    failed: list[str] = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        logger.info(
            "fetching batch %d/%d (%d tickers)",
            i // batch_size + 1,
            (len(tickers) + batch_size - 1) // batch_size,
            len(batch),
        )
        try:
            df = yf.download(
                tickers=" ".join(batch),
                start=start,
                end=end,
                interval=interval,
                progress=False,
                auto_adjust=True,
                threads=False,
                group_by="ticker",
            )
        except Exception as e:
            logger.warning("batch %s failed: %s", batch, e)
            failed.extend(batch)
            continue

        if df is None or df.empty:
            failed.extend(batch)
            continue

        # df has MultiIndex columns (ticker, field) when group_by="ticker"
        if isinstance(df.columns, pd.MultiIndex):
            for t in batch:
                if (t, "Close") not in df.columns:
                    failed.append(t)
                    continue
                ser = df[(t, "Close")].dropna()
                if len(ser) < 12:
                    failed.append(t)
                    continue
                sub = ser.reset_index().rename(columns={"Date": "date", t: "close"})
                # When pandas renames, sometimes column stays "Close" — normalise
                if "close" not in sub.columns:
                    sub.columns = ["date", "close"]
                sub["ticker"] = t
                all_frames.append(sub[["date", "ticker", "close"]])
                succeeded.append(t)
        else:
            # Single-ticker case (batch_size == 1)
            t = batch[0]
            if "Close" not in df.columns:
                failed.append(t)
                continue
            ser = df["Close"].dropna()
            if len(ser) < 12:
                failed.append(t)
                continue
            sub = ser.reset_index()
            sub.columns = ["date", "close"]
            sub["ticker"] = t
            all_frames.append(sub[["date", "ticker", "close"]])
            succeeded.append(t)

        time.sleep(0.3)  # polite throttle

    if not all_frames:
        return pd.DataFrame(columns=["date", "ticker", "close"]), succeeded, failed

    long_df = pd.concat(all_frames, ignore_index=True)
    # Flatten MultiIndex columns that yfinance may leak through reset_index
    if isinstance(long_df.columns, pd.MultiIndex):
        long_df.columns = [c[0] if isinstance(c, tuple) else c for c in long_df.columns]
    # Force plain string column names (defensive against str-tuple repr)
    long_df.columns = [str(c).split("'")[1] if str(c).startswith("(") else str(c)
                       for c in long_df.columns]
    long_df = long_df[["date", "ticker", "close"]].copy()
    long_df["date"] = pd.to_datetime(long_df["date"]).dt.tz_localize(None)
    long_df["ticker"] = long_df["ticker"].astype(str)
    long_df["close"] = long_df["close"].astype(float)
    return long_df, succeeded, failed


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(description="Fetch SP500 top100 + SPY monthly prices.")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2025-01-01")  # exclusive end, gives 2024-12 last bar
    parser.add_argument("--out-parquet", default=str(OUT_PARQUET))
    parser.add_argument("--out-meta", default=str(OUT_META))
    parser.add_argument("--force", action="store_true",
                        help="Refetch even if parquet exists")
    args = parser.parse_args(argv)

    out_parquet = Path(args.out_parquet)
    out_meta = Path(args.out_meta)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)

    if out_parquet.exists() and not args.force:
        logger.info("parquet already exists at %s — pass --force to refetch", out_parquet)
        return 0

    tickers = load_top100_tickers()
    if len(tickers) != 100:
        logger.warning("expected 100 top tickers, got %d", len(tickers))

    universe = ["SPY"] + tickers  # SPY benchmark first
    logger.info("fetching %d symbols (SPY + %d tickers) %s → %s",
                len(universe), len(tickers), args.start, args.end)

    long_df, succeeded, failed = fetch_yfinance_batch(
        tickers=universe, start=args.start, end=args.end, interval="1mo",
    )

    # Determine status
    spy_ok = "SPY" in succeeded
    ticker_hits = sum(1 for t in tickers if t in succeeded)
    if spy_ok and ticker_hits >= 80:
        status = "REAL"
    elif spy_ok and ticker_hits >= 40:
        status = "PARTIAL_REAL"
    else:
        status = "FETCH_FAILED"

    if long_df.empty or not spy_ok:
        logger.error("fetch failed — SPY missing or empty frame. status=%s", status)

    # Persist parquet
    if not long_df.empty:
        long_df.to_parquet(out_parquet, index=False)
        logger.info("wrote %s (%d rows, %d tickers)",
                    out_parquet, len(long_df), long_df["ticker"].nunique())

    meta = {
        "version": "v0.2",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "start": args.start,
        "end": args.end,
        "interval": "1mo",
        "source": "yfinance",
        "status": status,
        "n_succeeded": len(succeeded),
        "n_failed": len(failed),
        "n_top100_hits": ticker_hits,
        "spy_ok": spy_ok,
        "succeeded": sorted(succeeded),
        "failed": sorted(failed),
    }
    out_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("wrote %s — status=%s spy_ok=%s top100_hits=%d failed=%d",
                out_meta, status, spy_ok, ticker_hits, len(failed))
    return 0 if status != "FETCH_FAILED" else 2


if __name__ == "__main__":
    sys.exit(main())
