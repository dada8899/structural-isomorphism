# Universe selection — backtest v0.1 (1000-ticker)

## Composition

| Source | Count | File row label |
|---|---|---|
| S&P 500 (Wave 1 StructTuple-classified) | 500 | `sp500` |
| Russell 1000 mid-cap supplement (curated) | 501 | `russell_supplement` |
| **Total** | **1001** | |

Output: `backtest/data/1000_universe.csv` (columns: `ticker`, `source`).

## Methodology

### S&P 500 component
Sourced directly from `v4/product/d1_phase_detector/companies_500.jsonl`, the
Wave 1 input list. Each of these 500 tickers has a `critical_point_state`
label assigned by `deepseek-v4-flash` at snapshot 2026-05-13. These labels
power the headline LLM-based hypothesis test (`near_critical` cohort vs
benchmark).

### Russell 1000 supplement
A curated 501-ticker static list, hand-sampled from public Russell 1000
weight tables (iShares IWB ETF holdings, nasdaq.com Russell weights, April
2026 snapshot). Names selected to:

1. Be members of Russell 1000 but NOT in the S&P 500 (deduped against SP500)
2. Span multiple sectors (Technology, Healthcare, Industrials, Financials,
   Consumer, Energy, Utilities, Materials, REITs, Media)
3. Have ≥5y price history available on yfinance (drops occur during fetch)
4. Be sufficiently liquid (large/mid-cap, $1B+ market cap typically)

The Russell 1000 official membership is licensed by FTSE Russell and not
freely redistributable in CSV form. This curated 501-name sample is a
representative ~50% slice of Russell 1000 non-S&P-500 names. We treat it as
"supplementary universe" — not a strict R1000 reconstitution.

## Why these counts (not exactly 1000)

Target was 1000 tickers (per W7-D Track A). Actual = 1001 after dedupe
(S&P 500 list itself has some name overlap with our seed Russell list which
were dropped). The off-by-one is cosmetic; for backtest purposes "1000" is
the order-of-magnitude scale that matters.

## Coverage at fetch time

Expect ~3-5% fetch failures (delisted tickers, dotted-ticker yfinance bugs
like `BRK.B`/`BF.B`, ETF symbols accidentally included). Final n_universe
after price-fetch coverage is logged in `prices.meta.json`.

## Two-tier label structure

The walk-forward backtest produces results in two layered cohorts:

1. **LLM-labelled cohort** (n=500, SP500 only):
   `near_critical = approaching_critical ∪ at_critical` ⇒ 65 tickers
   `other = far_from_critical ∪ post_critical_transition` ⇒ 434 tickers
   1 ticker has `unknown` state and is dropped.

2. **Heuristic-labelled cohort** (n=full 1001, optional):
   A price-volatility-regime heuristic classifier assigns each ticker a
   pseudo-state at each snapshot T based on:
   - Realised volatility past 90 days (high vol = phase-stressed candidate)
   - Maximum drawdown past 180 days
   - AR(1) coefficient of monthly returns
   Top-decile composite score ⇒ `near_critical_heuristic`; bottom-decile ⇒
   `stable_heuristic`. This is a label-free comparator to gauge whether the
   LLM labels add information beyond what naive price stats already provide.

The heuristic cohort is NOT a claim about the LLM — it is a placebo /
baseline. If `near_critical_heuristic` produces a similar (or larger) Sharpe
lift than `near_critical_llm`, the LLM is not adding economic value on this
horizon.

## Future work — true Russell 1000

The Russell 1000 reconstitutes annually in late June. A production version of
this universe should:

1. Pull official annual reconstitution membership from FTSE Russell (paid)
   or proxy from IWB holdings as of the rebalance date.
2. Apply point-in-time membership (so historical T uses then-current R1000).
3. Avoid survivorship bias by including delisted constituents over the
   window — currently we silently drop these.

These improvements are queued for v0.2 of the backtest (post month-3
positioning decision).
