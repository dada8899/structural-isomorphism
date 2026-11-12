# Walk-forward backtest v0.1

_Window_: 2020-01-01 → 2024-12-31
_Data source_: **mock**
_Rebalances_: 59 months

> ⚠️ **v0.1 uses MOCK data to validate pipeline only.** Real data ingest (yfinance + D1 100-company snapshots) lands in v0.2. Numbers below describe the **synthetic** universe — do not interpret as alpha.

## Headline numbers

| Metric | Cohort (`near_critical`) | SPY benchmark |
|---|---:|---:|
| Cumulative return | +19.75% | +32.09% |
| Annualized Sharpe | +0.58 | +0.68 |
| Max drawdown | -8.28% | -11.50% |
| Sharpe lift | **-0.10** | — |
| Avg turnover / rebalance | **48.9%** | — |

## Reading guide

Per W7-D § 4.B pre-commits:

| Outcome | Threshold | Response |
|---|---|---|
| Strong signal | Sharpe lift ≥ +0.5 | Lean into alpha-screener positioning |
| Weak signal | +0.1 .. +0.4 | Honest positioning, transparent methodology |
| Null result | ≤ +0.1 | Pivot to structured-research-narrative product |

## Pipeline notes

- Walk-forward, point-in-time cohort lookup (no look-ahead bias)
- Equal-weight monthly rebalance
- Cash-equivalent fallback when cohort is empty for a given month
- Turnover = symmetric-difference / union of holdings month-over-month
- v0.1 limitations: no transaction costs, no shorts, no factor decomposition

## Next steps for v0.2

- Replace mock prices with yfinance close-prices for SPY + 100 mock tickers (real tickers TBD)
- Wire D1 monthly snapshots (one JSON per month, 60 months 2020-01..2024-12)
- Add bootstrap CI on Sharpe lift
- Sector-neutralization via SPDR sector ETFs
