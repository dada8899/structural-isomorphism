# Walk-forward backtest v0.2 (real data)

_Window_: 2020-01-01 → 2024-12-31
_Data source — prices_: **REAL** (yfinance, 99/100 top tickers + SPY; failed: ['RE'])
_Data source — classification_: **REAL** (D1 single-snapshot 2026-05-13)
_Rebalances_: 59 months
_Cohort_: 29 tickers (near_critical = approaching_critical ∪ at_critical)

> ⚠️ **Classification is single-snapshot (2026-05-13), not monthly time-varying.** We apply a 2026-built D1 classifier ex-post to 2020-2024 returns. This is an ex-post *discriminative* test (does today's structural label correlate with past risk-adjusted returns?), not a true ex-ante forecast. For a clean walk-forward test we need monthly D1 snapshots at historical timestamps (deferred to v0.3).

## Honest verdict (W7-D § 3 month-3 gate)

**alpha not confirmed** — Sharpe lift = **-0.23**

> Pivot to structured research narrative positioning. Sharpe lift below the +0.3 floor — D1 classification does not show evidence of standalone alpha on this universe/window. Lean into transparent methodology + research-tool framing.

## Headline numbers

| Metric | Cohort (`near_critical`) | SPY benchmark |
|---|---:|---:|
| Cumulative return | +111.72% | +95.82% |
| Annualized Sharpe | +0.60 | +0.84 |
| Max drawdown | -47.83% | -23.97% |
| Sharpe lift | **-0.23** | — |
| Avg turnover / rebalance | **1.9%** | — |
| Max turnover | 100.0% | — |

## CAPM alpha decomposition

Simplified regression `r_cohort = α + β · r_SPY + ε` (no risk-free; monthly returns).

| Quantity | Value |
|---|---:|
| Alpha (monthly) | -0.020% |
| Alpha (annualized, arithmetic) | **-0.24%** |
| Alpha t-statistic | **-0.02** |
| Beta (vs SPY) | +1.40 |
| R² | 0.535 |
| N (months) | 59 |

Interpretation guide:
- |t| ≥ 2.0 → alpha statistically distinguishable from 0 at ~95% confidence
- |t| < 1.0 → alpha indistinguishable from noise
- v0.2 uses naive OLS SE (no Newey-West / no rolling); residuals likely autocorrelated

## Reading guide — W7-D § 3 pre-commits

| Outcome | Sharpe lift bar | Pre-committed response |
|---|---|---|
| Strong | ≥ +0.5 | Lean into alpha-screener positioning |
| Inconclusive | +0.3 .. +0.5 | Extend evidence (200 tickers / 2015-2024 / monthly D1) |
| Null | < +0.3 | Pivot to structured-research narrative |

## Cohort composition (static, single-snapshot)

- Tickers (29): BAC, BIIB, BLDP, COIN, CRWD, CVX, DIS, FSLR, GM, ILMN, INTC, LCID, LLY, MRNA, NFLX, NIO, OXY, PLUG, RBLX, REGN, RIVN, ROKU, SEDG, SLB, SNOW, TSLA, U, UPST, WBD
- Sector mix: biotech (3), tech_auto_ev (3), energy_oil_gas (2), tech_software_gaming (2), energy_solar (2), energy_hydrogen (2), media_entertainment (2), tech_internet_streaming (2), tech_auto (1), financials_bank (1), healthcare_pharma (1), energy_oilfield_svc (1), tech_software_cloud (1), tech_software_security (1), biotech_tools (1), financials_crypto (1), financials_fintech (1), tech_semiconductor (1), consumer_auto (1)
- Dynamics family mix: reflexive_fixed_point (10), preferential_attachment (4), mixed_or_unclear (4), scheffer_fold (4), soc_threshold_cascade (3), hysteresis_preisach (2), motter_lai_cascade (1), extreme_value_tail (1)

## Pipeline notes

- yfinance monthly close prices, auto-adjusted (handles splits/dividends)
- Equal-weight monthly rebalance; cohort identity is constant (single-snapshot label)
- Cash-equivalent fallback when cohort member missing a month (e.g., pre-IPO)
- Turnover ≠ 0 only when cohort members enter/exit due to price-data availability
- v0.2 limitations: no transaction costs, no shorts, no factor decomposition (FF / Carhart), no Newey-West SE

## Charts

- Cumulative wealth: `walk-forward-v0.2-cumret.png`
- Drawdown profile:  `walk-forward-v0.2-drawdown.png`
- Turnover bar:      `walk-forward-v0.2-turnover.png`

## v0.3 roadmap

- Produce monthly D1 snapshots at historical timestamps (2020-01..2024-12) → true ex-ante test
- Carhart 4-factor regression (MKT / SMB / HML / MOM) for alpha attribution
- Bootstrap CI on Sharpe lift + Newey-West SE on alpha
- Sector-neutralized variant (long cohort / short sector-matched SPDR slice)
- Universe expansion: 200 tickers, window 2015-2024
