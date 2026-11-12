# Backtest Engine v0.1

Backtest harness for the **Phase Detector** hypothesis:

> Companies classified as `near_critical` (= `approaching_critical` OR `at_critical`) at snapshot **T** show a meaningfully different forward return over the next 6 (or 12) months versus the rest (`far_from_critical` + `post_critical_transition`).

This is the commercialisation fork — if `near_critical` segment shows positive expected return + statistically distinct distribution, we have a publishable / monetisable signal. v0.1 is the plumbing layer; real-data validation is the next session.

## What's here

| File | Role |
|------|------|
| `fetch_prices.py` | Pull monthly closes (Stooq) or generate synthetic GBM series. `--dry-run` = synthetic, no network. |
| `backtest.py` | Compute group returns, Welch t-test, cumulative curves. `--dry-run` = in-memory synthetic universe. |
| `serve_backtest.py` | stdlib HTTP server exposing `/backtest-result` + `/backtest-cumulative` for the phase-detector Next.js page (NOT auto-started). |
| `tests/test_backtest.py` | pytest unit tests with synthetic fixture. |
| `data/prices.csv` | Generated price history (synthetic by default). |
| `data/backtest_result.json` | Summary JSON (mean / std / Sharpe / Welch t,p / group sizes). |
| `data/backtest_cumulative.csv` | Time-series of group-mean cumulative returns. |

## Quickstart

```bash
# 1. Generate synthetic prices (writes data/prices.csv)
python3 v4/product/d1_phase_detector/fetch_prices.py --dry-run

# 2. Run backtest end-to-end on synthetic (no inputs needed)
python3 v4/product/d1_phase_detector/backtest.py --dry-run

# 3. OR run against the real StructTuple file with synthetic prices
python3 v4/product/d1_phase_detector/fetch_prices.py --dry-run
python3 v4/product/d1_phase_detector/backtest.py \
    --companies v4/product/d1_phase_detector/companies_500.jsonl \
    --prices v4/product/d1_phase_detector/data/prices.csv \
    --snapshot 2026-05-14 --period 6m
```

## Algorithm

1. **Load StructTuples** — `companies_500.jsonl` (Wave 1, 55 rows) preferred, fallback `companies.jsonl`. Reader accepts both the `{ticker, struct_tuple:{...}}` wrapper form and a flat form.
2. **Group split** — `near_critical = {approaching_critical, at_critical}`, `other = {far_from_critical, post_critical_transition}`. Unknown / null state rows dropped.
3. **Per-ticker forward return** — anchor close ≤ snapshot, end close ≥ snapshot + N months. `(end - anchor) / anchor`.
4. **Group statistics** — mean, population std, annualised Sharpe = `mean/std * sqrt(12/period_months)`.
5. **Significance** — Welch two-sample t-test (scipy). Fallback: stdlib normal-approx.
6. **Cumulative curves** — equal-weighted normalised price path per group, sampled at month-end grid; written to CSV for plotting.

## Current limitations (v0.1)

- **Synthetic prices are the default.** Stooq fetch (`--real`) likely fails from many egress IPs; the script logs `WARNING: USING SYNTHETIC FOR DEV` and proceeds. Numbers from synthetic mode are mechanically meaningful but **not market-truth**.
- **One snapshot only.** No walk-forward yet — every company gets the same `T`. Real backtest needs many overlapping snapshots.
- **Wave 1 StructTuple coverage = 55.** Cell sizes per group are small; t-test power limited.
- **Equal-weighted only.** No market-cap or volatility weighting.
- **No transaction costs / shorting / sector neutralisation.** Pure long-only group means.
- **No look-ahead protection beyond timestamp ordering.** Trust that StructTuple's `critical_point_state` was assigned from data available ≤ snapshot.

## Roadmap (next session)

1. **Real data** — switch to a cached daily-bars provider (e.g. polygon.io free tier or a local CSV mirror); run from 2023-01 onwards.
2. **Walk-forward** — generate one StructTuple snapshot per quarter for last 8 quarters; run backtest at each anchor; aggregate.
3. **Phase-detector UI** — `/backtest` page in `structural-isomorphism-v4/web/phase-detector/` calls `serve_backtest.py` on `:8019`. Inline chart of cumulative curve + summary KPIs.
4. **Multiple testing correction** — Benjamini-Hochberg over sector x state cells.
5. **Sensitivity** — vary period (3m, 6m, 12m, 24m); vary inclusion threshold for `near_critical`.

## Test

```bash
python3 -m pytest v4/product/d1_phase_detector/tests/test_backtest.py -v
```

## Why "near_critical → 6mo return" is the commercialisation hinge

The Phase Detector outputs a class label per company. If the label has zero correlation with subsequent risk-adjusted returns, the product is interesting science but not monetisable. v0.1 is the cheapest possible test that the wiring works: can we even *measure* a difference, given the Wave 1 sample size and synthetic noise? Real-data run in session 8 will tell us whether to invest further or pivot the productisation angle.

## Real-data findings (2026-05-14)

**v0.2: walk-forward backtest on real SP500 monthly prices (yfinance, 5y history, 497/500 tickers).**

### Setup

- 500 SP500 StructTuples from `companies_500.jsonl` (Wave 1, classified by `deepseek-v4-flash`)
- Group split: **65 `near_critical`** (approaching_critical + at_critical) vs **434 `other`** (far_from_critical + post_critical_transition); 1 null state dropped
- Price source: `yfinance` monthly closes, 2021-06 → 2026-05 (5 years)
- Coverage: 497/500 tickers fetched (3 missing: `RE` delisted, `BF.B` / `BRK.B` dotted-ticker yfinance bug; Stooq fallback also missed those 3)
- Method: **rolling 6-month forward return** at every month-end snapshot T (54 snapshots × ~497 companies). Welch's t-test (scipy) on the flat pooled observations: 3470 `near_critical` × 23113 `other`.

### Result

| metric | near_critical | other |
|---|---|---|
| n observations | 3,470 | 23,113 |
| mean 6mo return | **+6.16%** | **+6.43%** |
| std | 36.69% | 28.64% |
| annualised Sharpe | 0.24 | 0.32 |

**Welch's t = −0.412, p = 0.681.**

### Interpretation

> **商业化路径暂未打开（p ≫ 0.05）。** On 5-year SP500 walk-forward, the Phase Detector's `near_critical` label produces statistically indistinguishable 6-month forward returns from `other`. Mean returns differ by only 27 bp (likely noise); `near_critical` shows higher dispersion (36.7% vs 28.6% std) → slightly *worse* risk-adjusted return (Sharpe 0.24 vs 0.32).

This null result is informative — but not damning:

1. **Universe matters.** SP500 = already large, mature, dominantly `far_from_critical`. The hypothesis was always more compelling on growth/smid-cap or sector cohorts.
2. **Labels were a-priori, not refreshed.** Each company has *one* `critical_point_state` from a single 2026-05 deepseek-v4-flash run. The walk-forward uses the SAME label for every snapshot from 2021-06 → 2025-11 — which leaks future info backwards if a company *transitioned* during the window, but more importantly fails to capture state transitions over time.
3. **Definition of `near_critical` is wide.** 13% of universe labelled `near_critical` is large enough that any signal gets diluted.
4. **6 months may be the wrong horizon.** Phase transitions can play out over years (preferential_attachment companies) or weeks (panic / contagion). Sensitivity over 3m / 12m / 24m is open.

### Next experiments (priority order)

1. **Per-snapshot label refresh** — re-run StructTuple extraction at quarterly anchors, then backtest. Removes label-leakage.
2. **Universe broadening** — Russell 2000 or sector ETFs (where `near_critical` events are more impactful).
3. **Stratify by `dynamics_family`** — preferential_attachment companies labelled `near_critical` may behave very differently from contagion-family ones.
4. **Threshold tuning** — restrict `near_critical` to high-confidence (`confidence >= 0.8`) labels only.
5. **Horizon sensitivity** — 3m / 12m / 24m grid.

### Reproduce

```bash
# Fetch (~3 min for 500 tickers via yfinance)
python3 v4/product/d1_phase_detector/fetch_prices.py \
    --tickers v4/product/d1_phase_detector/companies_500.jsonl \
    --output v4/product/d1_phase_detector/prices_500.csv \
    --period 5y --interval 1mo

# Walk-forward backtest (~2 sec)
python3 v4/product/d1_phase_detector/backtest.py \
    --companies v4/product/d1_phase_detector/companies_500.jsonl \
    --period 6m --real-prices
```

Artifacts written to `v4/product/d1_phase_detector/`:
- `prices_500.csv` — long-format ticker × date × close (29,566 rows)
- `prices.meta.json` — fetch provenance (yfinance / stooq / synthetic counts)
- `backtest_result.json` — full stats blob (mode, n, means, t, p, Sharpe, …)
- `cumulative.csv` — per-snapshot monthly mean return + compounded cumulative per group
- `cumulative_return.png` — line plot of cumulative return curves
