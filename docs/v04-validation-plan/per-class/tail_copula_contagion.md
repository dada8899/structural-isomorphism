# tail_copula_contagion

**Name (zh)**: 尾部相关 / Copula 传染类
**Name (en)**: Tail Copula Contagion
**Pre-registered exponent band**: Tail-dependence coefficient λ_tail jump: calm-period 0.10–0.20 → stress-period 0.45–0.65; Δλ ≥ 0.30 to declare PASS. Clayton/Gumbel copula parameter jump Δθ ≥ 1.5. Rationale: Patton 2013 review of dynamic copula models + Longin–Solnik 2001 stock-market extreme correlations.
**Verified status**: false (target: v0.4). B3 consensus = REJECT with note "copula is a parametric family, not a mechanism."

## Why this class needs an empirical anchor

The pre-registered S&P 500 × VIX prediction in the KB is precisely the kind of test the v0.4 paper needs: it parametrizes industry folklore ("correlations go to 1 in a crisis") into a falsifiable band. Like `extreme_value_tail_class`, the B3 REJECT is grounded in the "descriptor vs mechanism" distinction — copulas are statistical glue, not causal physics. A successful PASS here would still not promote it to a mechanism class, but would let us *document* the universal tail-jump band as a stylized fact across finance + climate + insurance.

KB linkage: 5 members across climate (glacial termination triggers), insurance (catastrophe tail dependence), macro (Minsky moments), derivatives (diversification illusion + correlation collapse).

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Yahoo Finance / Stooq daily returns for S&P 500 + CBOE VIX 2000–2025 | https://stooq.com/ + yfinance | Free, terms-of-service | ~6500 days × ~500 stocks | Original pre-registered target; ergodic conditional copula fitting works at this size | Survivorship bias if index composition not back-adjusted |
| 2 [fallback] | DefiLlama liquidation events + ETH/BTC return joint distribution 2020–2025 | https://defillama.com/liquidations + CoinGecko API | CC-BY-NC | ~1.2M liquidations across 20 protocols | Tests whether stress-tail copula jump generalises beyond traditional finance | Short history; protocol-specific noise |
| 3 [stretch] | NOAA paleoclimate proxy joint records: Greenland δ¹⁸O + Antarctica deuterium (NGRIP + EPICA, 0–800 ka BP) | https://www.ncei.noaa.gov/products/paleoclimatology | Public domain | ~10k points at decadal resolution | Climate-side test of cross-hemisphere tail dependence during glacial transitions | Dating uncertainty; serial correlation; very different timescale |

## Validation procedure (concrete)

```bash
mkdir -p data/tail_copula_contagion

# 1. Fetch S&P + VIX
python -c "
import yfinance as yf, pandas as pd
sp = yf.download('^GSPC ^VIX', start='2000-01-01', end='2025-12-31')['Adj Close']
sp.to_csv('data/tail_copula_contagion/sp_vix.csv')
# Constituents: use Wikipedia historical list snapshot
"

# 2. Conditional copula fit (VIX quantile-conditioned)
python -m v4.cli validate tail_copula_contagion \
  --data data/tail_copula_contagion/sp_vix.csv \
  --method dynamic-copula --conditioning-var VIX \
  --quantile-bins 0.50,0.75,0.95 \
  --alpha-band 0.30,0.70 --null-controls gaussian-copula,student-t

# 3. Expected verdicts
#   PASS:  λ_tail jumps from <0.20 (calm) to >0.45 (VIX > q95) with bootstrap 95% CI not crossing 0.30,
#          AND Clayton/Gumbel preferred over Gaussian by AIC/BIC
#   FAIL:  jump absent OR Gaussian copula not rejected
#   INCONCLUSIVE: jump direction correct but magnitude below pre-reg band
```

## Estimated workload

- Data acquisition: 3 h (yfinance survives basic use; component history harder)
- Pipeline run: 4 h (DCC-GARCH-copula is non-trivial; bootstrap CIs slow)
- Verdict + writeup: 3 h
- **Total: ~10 h / 1.5 days for one sub-agent**

## Risks specific to this class

1. **Mechanism-vs-descriptor**: same caveat as EVT. Even PASS does not flip B3 REJECT — it documents the stylised fact.
2. Survivorship bias on S&P constituents over 25 y will inflate calm-period λ_tail (drop the worst performers). Use point-in-time membership from Wikipedia snapshot or Compustat if available.
3. DCC-GARCH–copula has identifiability issues at sample sizes < 2000 obs/pair; restrict to 50 top-cap stocks × 25 y to keep computation tractable.

## Priority

⭐⭐⭐⭐ (rationale: pre-registered prediction is already in KB; data is free; result PASS or FAIL both informative)

## Dependencies

- `yfinance`, `pandas`, `numpy`, `scipy`, `arch` (DCC-GARCH), `copulas` (Sklar copula fitting)
- No paid API
- Storage: < 200 MB
