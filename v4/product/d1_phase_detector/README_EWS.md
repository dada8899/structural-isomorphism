# Phase Detector — Early-Warning-Signal (EWS) layer

> Added 2026-05-23 to replace the LLM-vibe "critical_point_state" with a real,
> computed, backtestable signal grounded in critical-slowing-down (CSD) theory.

## Why this exists

The v0.2 product shipped a screener whose "critical_point_state" was produced
by an LLM reading a company description and picking one of 5 categories. The
"early-warning indicators" (`ar1_trend`, `variance_trend`, `tail_exponent_drift`)
shown on each company's detail page were similarly LLM-asserted strings — no
time series was ever touched. The headline trajectory chart was a deterministic
PRNG of the ticker. The walk-forward backtest (500 tickers × 5 years) returned
**p = 0.681**: no measurable alpha.

The EWS layer here is the honest version of what the product *claims* to do.

## What it computes

For each ticker, daily log-returns over the trailing ~2 years feed two rolling
statistics over a 60-trading-day window:

1. **Lag-1 autocorrelation (AR1)** — Pearson AC(1) of returns inside the window.
2. **Variance** — sample variance of the same window.

Both rolling series are then evaluated for monotonic trend over the trailing
**~1 year** via Kendall's tau, with a **stride sub-sample** equal to ~¼ of the
rolling-window length. The stride matters: consecutive rolling values share
59/60 of their data, so the nominal tau p-value is anti-conservative. Stride
sampling breaks the worst of the overlap. (We verified empirically that this
drops the at_critical false-positive rate on i.i.d. random walks from ≈20%
to ≈0.3%.)

The composite **criticality_score ∈ [0, 100]** requires *both* taus to be
positive *and* nominally significant (p < 0.01). A lone positive tau is
capped at ≈35 — yellow, never red — because CSD theory predicts both
indicators move together. Negative taus contribute zero.

A separate **post_critical_transition** gate fires when the trailing window
contains a drawdown > 30% from its peak; this catches the "already tipped"
case that resets the CSD signal.

## Layout

```
v4/product/d1_phase_detector/
├── ews.py                 # pure-Python engine, ~300 LOC, no scipy/numpy
├── hk_universe.py         # HSI + HSTECH + selective bench (~97 names) + ADR map
├── run_ews_pipeline.py    # one-shot: fetch (yfinance) → compute → write JSON
├── tests/test_ews.py      # unit tests (22 tests, FPR/TPR aggregate guarantees)
├── api/ews.py             # FastAPI router: /api/ews/{meta,leaderboard,<ticker>}
└── data/
    ├── ews_results.json      # full per-ticker EWS dict (cron-refreshed)
    ├── ews_leaderboard.json  # ranked card payload (light, ~200 KB)
    └── ews_meta.json         # run provenance + counts
```

## US + HK markets

`hk_universe.py` ships the HSI + HSTECH constituents (manually curated, quarterly
refresh cadence) plus a selective bench. ADR dual-listings (BABA/9988,
JD/9618, BIDU/9888, etc.) are deduplicated **HK-first** — the HK primary listing
has been the deeper book post-2022 for these names.

yfinance covers both markets with the same API; HK tickers use the `.HK`
suffix (e.g. `0700.HK` for Tencent). The pipeline treats them identically
on the compute side; differences (HKD currency, Stock Connect southbound flow,
T+2 settlement, HK trading halts producing OHLCV gaps that ≠ delisting) are
surfaced in the UI as market badges + sector tags rather than baked into the
math.

## Running

```bash
# Sandbox / dev (no network): synthetic prices with a realistic regime mix.
python3 v4/product/d1_phase_detector/run_ews_pipeline.py --demo

# Full nightly run on VPS (US + HK):
python3 v4/product/d1_phase_detector/run_ews_pipeline.py

# US-only quick smoke:
python3 v4/product/d1_phase_detector/run_ews_pipeline.py --markets US --limit 50
```

The nightly cron is scheduled in `.github/workflows/ews-pipeline-nightly.yml`
(22:00 UTC — after US close, before HK open).

## Validation

`tests/test_ews.py` is the verification we can do without a stock-data
network. The 22 tests cover:

* primitive correctness (variance, autocorrelation, Kendall-tau);
* white-noise **false-positive rate** < 3 % across 200 seeds;
* textbook-CSD **detection rate** ≥ 50 % across 50 seeds;
* drawdown gate fires on synthesized −40 % drops;
* lone indicator capped at yellow;
* non-significant tau treated as zero;
* JSON serializability + graceful handling of bad price data.

```
22 passed in 3.15s
```

## Honest caveats

* CSD signals are *necessary-but-not-sufficient* warnings. A high score does
  NOT predict direction — it says the system has lost resilience and any
  shock will be amplified. The frontend's "一句话给你" actionable layer states
  this explicitly per case.
* Backtesting CSD on individual equities is research literature with mixed
  results. We will publish the new backtest under `backtest/v0.2-ews/` once
  the VPS has fed the engine a full nightly history; until then the leaderboard
  is positioned as a research tool, not an alpha source.
* Stride sub-sampling trades statistical power for honest significance. A
  short series can fail to detect a real CSD shift; the `confidence` field
  is the reader's guard.
