"""End-to-end EWS pipeline: fetch prices (US + HK) -> compute CSD -> write JSON.

Runs on the VPS where outbound network reaches yfinance / stooq. The
output `ews_results.json` is what the FastAPI backend serves to the
phase-detector frontend at /api/ews/*.

Pipeline
========
1. Build the universe:
   - US: companies_500.jsonl (S&P 500 + curated)
   - HK: HK_UNIVERSE from hk_universe.py (~97 names, HSI + HSTECH)
   - Dedup ADRs whose HK dual listing is also present (keep HK primary).
2. Fetch daily OHLCV via yfinance (works for both US and `.HK` suffixes).
3. For each ticker, compute the EWS result (rolling AR1 / variance,
   Kendall tau over trailing year, composite criticality score).
4. Write three artifacts:
   - `ews_results.json`     full per-ticker EWS dict (keyed by ticker)
   - `ews_leaderboard.json` ranked list, scrubbed to card-ready fields
   - `ews_meta.json`        run provenance: as_of, n_tickers, source mix

Usage
-----
    python3 run_ews_pipeline.py                       # full universe
    python3 run_ews_pipeline.py --markets US          # US only
    python3 run_ews_pipeline.py --markets HK          # HK only
    python3 run_ews_pipeline.py --limit 50            # smoke test
    python3 run_ews_pipeline.py --period 2y --interval 1d
    python3 run_ews_pipeline.py --demo                # no network; synth data

Cron suggestion (VPS): nightly at 21:30 HKT (after US close + before HK open):
    30 21 * * 1-5 cd /opt/structural-isomorphism && \
        .venv/bin/python3 v4/product/d1_phase_detector/run_ews_pipeline.py \
        --output v4/product/d1_phase_detector/data/ews_results.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import random
import sys
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))

from v4.product.d1_phase_detector.ews import compute_ews, EwsResult  # noqa: E402
from v4.product.d1_phase_detector.hk_universe import (  # noqa: E402
    HK_UNIVERSE,
    ADR_TO_HK,
    dedup_adr_us_first,
    market_of,
    currency_of,
)

LOG = logging.getLogger("ews_pipeline")
DEFAULT_OUT_DIR = os.path.join(HERE, "data")
US_INPUT = os.path.join(HERE, "companies_500.jsonl")


# ---------------------------------------------------------------------------
# Universe assembly
# ---------------------------------------------------------------------------

def load_us_universe(path: str, limit: Optional[int] = None) -> List[dict]:
    """Pull ticker + minimal metadata from the existing LLM-extracted JSONL."""
    out: List[dict] = []
    if not os.path.exists(path):
        LOG.warning("US universe %s not found; skipping", path)
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
            st = rec.get("struct_tuple") or {}
            t = (rec.get("ticker") or st.get("ticker") or "").upper()
            if not t:
                continue
            out.append({
                "ticker": t,
                "name": st.get("company_name") or t,
                "sector": st.get("sector") or "unknown",
                "market": "US",
                "currency": "USD",
                # carry over LLM context as supplementary, NOT primary
                "llm_dynamics_family": st.get("dynamics_family"),
                "llm_critical_state": st.get("critical_point_state"),
                "llm_tldr": st.get("structural_summary"),
                "llm_confidence": st.get("confidence"),
            })
            if limit and len(out) >= limit:
                break
    # dedup
    seen, uniq = set(), []
    for r in out:
        if r["ticker"] not in seen:
            seen.add(r["ticker"])
            uniq.append(r)
    return uniq


def load_hk_universe(limit: Optional[int] = None) -> List[dict]:
    out = [{
        "ticker": t.ticker,
        "name": t.name,
        "name_zh": t.name_zh,
        "sector": t.sector,
        "market": "HK",
        "currency": "HKD",
        "indices": t.indices,
        "adr_ticker": t.adr_ticker,
    } for t in HK_UNIVERSE]
    if limit:
        out = out[:limit]
    return out


def assemble_universe(markets: List[str], limit_per_market: Optional[int]) -> List[dict]:
    rows: List[dict] = []
    if "US" in markets:
        rows.extend(load_us_universe(US_INPUT, limit=limit_per_market))
    if "HK" in markets:
        rows.extend(load_hk_universe(limit=limit_per_market))
    # Dedup ADR/HK: if both present, drop the US ADR.
    tickers = [r["ticker"] for r in rows]
    kept = set(dedup_adr_us_first(tickers))
    rows = [r for r in rows if r["ticker"] in kept]
    return rows


# ---------------------------------------------------------------------------
# Price fetch — yfinance for both US and HK
# ---------------------------------------------------------------------------

def fetch_prices_yfinance(
    tickers: List[str],
    period: str = "2y",
    interval: str = "1d",
    batch_size: int = 30,
) -> Dict[str, List[Tuple[dt.date, float]]]:
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        LOG.error("yfinance not installed; pip install yfinance pandas")
        return {}
    out: Dict[str, List[Tuple[dt.date, float]]] = {}
    n_batches = (len(tickers) + batch_size - 1) // batch_size
    for bi in range(n_batches):
        batch = tickers[bi * batch_size:(bi + 1) * batch_size]
        LOG.info("yfinance batch %d/%d (%d tickers)", bi + 1, n_batches, len(batch))
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
        except Exception as exc:
            LOG.warning("batch %d failed: %s", bi + 1, exc)
            continue
        if df is None or df.empty:
            continue
        for t in batch:
            try:
                sub = df[t] if len(batch) > 1 else df
            except (KeyError, AttributeError):
                continue
            try:
                closes = sub["Close"].dropna()
            except (KeyError, AttributeError, TypeError):
                continue
            series: List[Tuple[dt.date, float]] = []
            for ts, val in closes.items():
                try:
                    d = ts.date() if hasattr(ts, "date") else dt.date.fromisoformat(str(ts)[:10])
                    series.append((d, float(val)))
                except (ValueError, TypeError):
                    continue
            if series:
                out[t] = series
    LOG.info("yfinance covered %d/%d tickers", len(out), len(tickers))
    return out


# ---------------------------------------------------------------------------
# Demo / sandbox synthesizer — used when --demo, when yfinance is absent,
# OR when individual tickers were uncovered. The synthesizer produces
# realistic-shape price series with a *controlled mix of regimes* so the
# frontend has something honest to render before the VPS pipeline lands
# real prices. Each synthetic series carries `provenance="demo"` so the
# UI can flag it.
# ---------------------------------------------------------------------------

def synthesize_series(
    ticker: str,
    n_days: int = 800,
    regime: Optional[str] = None,
) -> List[Tuple[dt.date, float]]:
    """Deterministic synthetic daily closes. Regime ∈ {calm, csd, drawdown}."""
    import math
    seed = abs(hash(ticker)) % (2**31)
    rng = random.Random(seed)
    if regime is None:
        # Distribute regimes deterministically by ticker hash so the
        # leaderboard reflects a realistic mix (≈70% calm, 20% csd, 10% drawdown).
        r = seed % 100
        regime = "calm" if r < 70 else "csd" if r < 90 else "drawdown"

    rets: List[float] = []
    prev = 0.0
    if regime == "calm":
        for _ in range(n_days):
            new = 0.05 * prev + rng.gauss(0, 0.011)
            rets.append(new); prev = new
    elif regime == "csd":
        # calm baseline then CSD ramp
        baseline = n_days // 2
        ramp = n_days - baseline
        for _ in range(baseline):
            new = 0.05 * prev + rng.gauss(0, 0.008)
            rets.append(new); prev = new
        for i in range(ramp):
            t = i / ramp
            phi = 0.05 + 0.8 * t
            sigma = 0.008 + 0.018 * t
            new = phi * prev + rng.gauss(0, sigma)
            rets.append(new); prev = new
    elif regime == "drawdown":
        for i in range(n_days):
            if i == n_days - 80:
                rets.append(math.log(0.7))
                prev = math.log(0.7)
                continue
            new = 0.05 * prev + rng.gauss(0, 0.013)
            rets.append(new); prev = new

    # convert to closes ending today
    start_price = 20.0 + (seed % 200)
    prices = [start_price]
    for r in rets:
        prices.append(prices[-1] * math.exp(r))
    today = dt.date.today()
    dates = [today - dt.timedelta(days=(len(prices) - 1 - i)) for i in range(len(prices))]
    return list(zip(dates, prices))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EWS pipeline (US + HK)")
    parser.add_argument("--markets", default="US,HK", help="comma list: US,HK")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap each market's ticker count")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--output", default=os.path.join(DEFAULT_OUT_DIR, "ews_results.json"))
    parser.add_argument("--demo", action="store_true",
                        help="skip yfinance, use synthetic series (sandbox testing)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
    )

    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    universe = assemble_universe(markets, args.limit)
    LOG.info("Universe: %d tickers across %s", len(universe), markets)

    tickers = [r["ticker"] for r in universe]
    if args.demo:
        prices = {t: synthesize_series(t) for t in tickers}
        provenance = "demo"
    else:
        prices = fetch_prices_yfinance(tickers, period=args.period, interval=args.interval)
        # backfill missing with synth so frontend never has a hole
        missing = [t for t in tickers if t not in prices]
        LOG.warning("%d tickers missing from yfinance; backfilling synth", len(missing))
        for t in missing:
            prices[t] = synthesize_series(t)
        provenance = "live+synth_fallback" if missing else "live"

    # Compute EWS per ticker
    results = {}
    for row in universe:
        t = row["ticker"]
        closes = prices.get(t, [])
        if not closes:
            continue
        res = compute_ews(closes, ticker=t)
        d = res.to_dict()
        d.update({
            "name": row.get("name"),
            "name_zh": row.get("name_zh"),
            "sector": row.get("sector"),
            "market": row.get("market"),
            "currency": row.get("currency"),
            "indices": row.get("indices"),
            "adr_ticker": row.get("adr_ticker"),
            # supplementary LLM context for US tickers (HK has none)
            "llm_dynamics_family": row.get("llm_dynamics_family"),
            "llm_tldr": row.get("llm_tldr"),
            # provenance per-ticker: live or synth (so UI can flag honestly)
            "price_provenance": "live" if (not args.demo and t in prices and prices[t]
                                          and len(prices[t]) > 100 and provenance != "demo"
                                          and t not in missing if not args.demo else False)
                                       else "demo",
        })
        # Cap the time series shipped to UI: last 180 trading days (~9 months).
        # The full 2y is heavy and the chart only plots the trailing window;
        # 180d keeps the git-committed bootstrap snapshot under ~6 MB.
        for k in ("ar1", "var"):
            ts = d.get(k) or {}
            ts["dates"] = (ts.get("dates") or [])[-180:]
            ts["values"] = (ts.get("values") or [])[-180:]
            d[k] = ts
        results[t] = d

    # Leaderboard: ranked by score desc among approaching/at, then
    # descending confidence. Light payload for the screener cards.
    def _card(t: str, d: dict) -> dict:
        return {
            "ticker": t,
            "name": d.get("name"),
            "name_zh": d.get("name_zh"),
            "sector": d.get("sector"),
            "market": d.get("market"),
            "currency": d.get("currency"),
            "criticality_score": d.get("criticality_score", 0.0),
            "phase_state": d.get("phase_state", "unknown"),
            "confidence": d.get("confidence", 0.0),
            "as_of": d.get("as_of"),
            "tau_ar1": (d.get("ar1") or {}).get("tau"),
            "tau_var": (d.get("var") or {}).get("tau"),
            "price_provenance": d.get("price_provenance"),
        }

    ranked = sorted(
        ({"_t": t, "_d": d} for t, d in results.items()),
        key=lambda r: (
            0 if r["_d"].get("phase_state") in ("approaching_critical", "at_critical") else 1,
            -float(r["_d"].get("criticality_score") or 0),
            -float(r["_d"].get("confidence") or 0),
        ),
    )
    leaderboard = [_card(r["_t"], r["_d"]) for r in ranked]

    # Write outputs
    out_dir = os.path.dirname(args.output) or "."
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, separators=(",", ":"))
    lb_path = os.path.join(out_dir, "ews_leaderboard.json")
    with open(lb_path, "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, ensure_ascii=False, separators=(",", ":"))
    meta_path = os.path.join(out_dir, "ews_meta.json")
    meta = {
        "version": "0.3.0-ews",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_tickers": len(results),
        "n_critical": sum(1 for d in results.values() if d.get("phase_state") == "at_critical"),
        "n_approaching": sum(1 for d in results.values()
                             if d.get("phase_state") == "approaching_critical"),
        "n_post": sum(1 for d in results.values()
                      if d.get("phase_state") == "post_critical_transition"),
        "by_market": {
            m: sum(1 for d in results.values() if d.get("market") == m)
            for m in ("US", "HK")
        },
        "price_provenance": provenance,
        "period": args.period,
        "interval": args.interval,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    LOG.info("Wrote %d EWS records → %s", len(results), args.output)
    LOG.info("Leaderboard → %s, meta → %s", lb_path, meta_path)
    LOG.info("phase mix: critical=%d approaching=%d post=%d",
             meta["n_critical"], meta["n_approaching"], meta["n_post"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
