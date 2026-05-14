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
