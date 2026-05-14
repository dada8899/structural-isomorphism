#!/usr/bin/env python3
"""Pre-reg P1 — fetch Bitcoin Cash daily price series + compute log returns.

Per the pre-registration in `paper/v0-unified-pipeline-2026-05-13.md` §8.2:
  P1 = Bitcoin Cash *daily log returns* (2017-2025)
  Class = SOC threshold-cascade (financial)
  Predicted alpha = 2.8 +/- 0.3  (Gopikrishnan/Stanley inverse-cubic regime)
  Literature acceptance band = [2.0, 3.5]

Data source: api.cryptocompare.com `histoday` endpoint, free public, returns
up to 2000 daily candles. We then compute log returns r_t = log(close_t / close_{t-1})
and feed |r_t| (absolute log returns) into the frozen Clauset pipeline.

This is the exact same construction used in the V4 S&P 500 phase
(v4/validation/soc-stockmarket/fetch_and_analyze.py); only the symbol differs.

Outputs:
  bch_daily.csv      raw daily candles (date, close)
  bch_intervals.json absolute log returns + fetch metadata
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
RAW = OUT_DIR / "bch_daily.csv"
INTERVALS_FILE = OUT_DIR / "bch_intervals.json"
META_FILE = OUT_DIR / "fetch_meta.json"

API_URL = "https://min-api.cryptocompare.com/data/v2/histoday?fsym=BCH&tsym=USD&limit=2000"


def fetch_daily() -> list[dict]:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "structural-isomorphism/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.load(resp)
    data = payload.get("Data", {}).get("Data", [])
    return data


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if RAW.exists():
        print(f"[skip] {RAW} exists; remove to refetch.")
        rows = []
        with open(RAW) as f:
            next(f)  # header
            for line in f:
                t, c = line.strip().split(",")
                rows.append((int(t), float(c)))
    else:
        candles = fetch_daily()
        if not candles:
            print("[err] no data from cryptocompare", file=sys.stderr)
            sys.exit(1)
        rows = [(int(c["time"]), float(c["close"])) for c in candles if c.get("close", 0) > 0]
        rows.sort(key=lambda r: r[0])
        with open(RAW, "w") as f:
            f.write("time_unix,close_usd\n")
            for t, c in rows:
                f.write(f"{t},{c}\n")
        print(f"[ok] wrote {len(rows)} daily candles -> {RAW}")

    # Compute log returns
    returns = []
    for i in range(1, len(rows)):
        t0, c0 = rows[i - 1]
        t1, c1 = rows[i]
        if c0 > 0 and c1 > 0:
            returns.append((t1, math.log(c1 / c0)))
    print(f"[stats] {len(returns)} log returns; "
          f"mean={sum(r for _, r in returns)/len(returns):.5f}; "
          f"abs_max={max(abs(r) for _, r in returns):.4f}")

    abs_returns = [abs(r) for _, r in returns if r != 0]
    print(f"[stats] {len(abs_returns)} non-zero |r_t|; "
          f"min={min(abs_returns):.6f}; max={max(abs_returns):.4f}")

    t_min, t_max = rows[0][0], rows[-1][0]
    out = {
        "source": "min-api.cryptocompare.com histoday (free public API)",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_days": len(rows),
        "n_returns": len(returns),
        "date_start_utc": datetime.fromtimestamp(t_min, tz=timezone.utc).isoformat(),
        "date_end_utc": datetime.fromtimestamp(t_max, tz=timezone.utc).isoformat(),
        "construction": "r_t = log(close_t / close_{t-1}); |r_t| as power-law observable",
        # Field name kept as 'intervals_seconds' for compatibility with analyze script;
        # in this P1 file it stores |log returns|, not seconds. Field unit recorded above.
        "observable": "abs_daily_log_return",
        "intervals_seconds": abs_returns,
    }
    with open(INTERVALS_FILE, "w") as f:
        json.dump(out, f)
    print(f"[ok] wrote {len(abs_returns)} |r_t| -> {INTERVALS_FILE}")

    with open(META_FILE, "w") as f:
        json.dump({k: v for k, v in out.items() if k != "intervals_seconds"}, f, indent=2)


if __name__ == "__main__":
    main()
