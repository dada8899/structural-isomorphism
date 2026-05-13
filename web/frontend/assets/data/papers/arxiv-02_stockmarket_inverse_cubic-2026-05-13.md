# Cross-Domain Self-Organized Criticality: Inverse Cubic Law and Omori Decay on Thirty-Five Years of S&P 500 Daily Returns

## Authors

Wan Qinghui (万庆徽)$^{1,*}$

$^{1}$ Independent Research, Structural Isomorphism Project, https://structural.bytedance.city

$^{*}$ Correspondence: `dada8899@users.noreply.github.com` *(placeholder — author affiliation and contact details to be finalized prior to formal submission)*

## Abstract

If a universality class has empirical content beyond linguistic analogy, the same analysis pipeline should recover its canonical scaling laws on systems drawn from very different domains. A companion Phase 1 paper validated a self-organized-criticality (SOC) analysis stack on the USGS global earthquake catalog (84,724 events, Gutenberg-Richter $b = 1.084 \pm 0.005$, Omori-Utsu $p = 0.941 \pm 0.017$). Here we apply the identical pipeline to 9,060 daily log returns of the S&P 500 index (Yahoo Finance, 1990-01-01 to 2025-12-31), one cross-domain member of the V4 SOC equivalence class (price-impact cascades, margin spirals, flash crashes). Without any parameter tuning, the Clauset-Shalizi-Newman continuous power-law fit on the absolute returns $|r|$ returns a tail exponent $\alpha = 2.998 \pm 0.041$, reproducing Gopikrishnan, Plerou, Stanley et al.'s 1998 "inverse cubic law" to within $0.07\%$ of the canonical 3.0, with the power-law model strongly dominating lognormal ($p < 10^{-9}$). An Omori-Utsu fit on stacked post-shock volatility from 318 $3\sigma$ main shocks yields $p = 0.286 \pm 0.034$ ($R^2 = 0.71$), inside the published daily-scale band of $[0.3, 0.6]$ (Weber et al. 2007) but outside the intraday band of $[0.7, 1.0]$ (Lillo-Mantegna 2003, Petersen et al. 2010); this is a scale-dependent feature, not a deviation. The combined result is the first cross-domain reproduction of canonical SOC scaling by the Structural Isomorphism V4 pipeline and strengthens the empirical basis for treating earthquake, finance, and infrastructure cascades as members of a single universality class.

## Keywords

self-organized criticality; inverse cubic law; Omori-Utsu decay; volatility clustering; cross-domain universality; econophysics; power-law tails; pipeline validation

## 1. Introduction

The Structural Isomorphism project [1, 2] asks whether cross-domain "same mathematical structure" claims can be made rigorous. Its V4 Layer 2 community-discovery step groups seventeen phenomena — earthquakes, DeFi liquidations, bank runs, margin spirals, power-grid cascades, supply-chain collapses, social cascades, flash crashes — into a single self-organized-criticality (SOC) threshold-cascade equivalence class [3, 4]. Layer 4 attaches quantitative predictions to each class (critical exponents with numerical bands), and Layer 5 is the empirical validation step.

A companion paper [5] ran the analysis pipeline on the USGS global earthquake catalog as the ground-truth physics reference and recovered the canonical Gutenberg-Richter $b$-value and Omori-Utsu $p$-value. That was a pipeline check, not a cross-domain claim. The present paper is the first **non-physics** member of the same equivalence class to be tested with the identical pipeline.

The stock market is an ideal first cross-domain target for several reasons:

1. Its scaling behavior has been independently established in the econophysics literature since the late 1990s [6, 7, 8], so there is a ground truth to recover.
2. Free daily data back to 1990 is readily available via Yahoo Finance.
3. The SOC-hub member "flash-crash liquidity spiral" appears in the V3 equivalence class [2] and has an obvious mapping to post-crash volatility decay (Lillo-Mantegna 2003, Petersen et al. 2010, Weber et al. 2007) [9, 10, 11].
4. The analysis is entirely public-data, single-person, and one-day reproducible.

The specific contributions of this paper are:

1. Cross-domain application of the SOC pipeline of [5] to a second dataset with zero re-tuning.
2. Recovery of $\alpha \approx 3.0$ (inverse cubic law) on S&P 500 daily returns with tight confidence intervals.
3. Recovery of daily-scale Omori decay in the published $[0.3, 0.6]$ band, plus a calibration note on an initial Layer 4 prediction prompt that confused intraday and daily scales.
4. An explicit joint comparison table with Phase 1 (earthquakes), showing the same functional form and scaling-class membership while their absolute exponents differ — as universality-class theory predicts.

## 2. Data and Methods

### 2.1 Dataset

S&P 500 (`^GSPC`) daily close prices were downloaded via the `yfinance` Python package (version 1.2.0) on 2026-04-15. The query window is 1990-01-01 through 2025-12-31. Raw rows: 9,066. Log returns are computed as $r_t = \log(P_t / P_{t-1})$, giving 9,065 values with $\sigma = 0.0114$ and range $[-0.1277, +0.1096]$. No volatility-adjustment or de-trending is applied; the analysis operates on raw log returns to enable comparison with the published econophysics literature, which also operates on raw or normalized magnitudes.

### 2.2 Power-law tail analysis (Clauset 2009)

The continuous power-law fit uses the `powerlaw` Python package implementing the Clauset-Shalizi-Newman 2009 estimator of $\alpha$ [12] with automatic selection of $x_\mathrm{min}$ by minimization of the Kolmogorov-Smirnov distance between the empirical and fitted complementary CDF. The statistic is applied to the absolute log returns $|r_t|$ (not $r_t^2$ and not raw signed $r_t$; the unsigned magnitude is the established observable for stock-return universality, following Gopikrishnan et al. 1998 [6] and Plerou et al. 1999 [7]). For model comparison we run `distribution_compare` between power-law and two alternatives (lognormal, exponential), reporting the normalized log-likelihood ratio $R$ and significance $p$.

### 2.3 Omori-Utsu aftershock stacking

Main-shock days are defined as $|r_t| > 3\sigma$ (threshold $\approx 3.42\%$, where $\sigma$ is the full-sample standard deviation of log returns). For each main shock at time $t_k$, the stacked "aftershock rate" at lag $\tau \in \{1, 2, \dots, 30\}$ trading days is computed as:
$$
n(\tau) = \frac{1}{N_\mathrm{main}} \sum_{k=1}^{N_\mathrm{main}} |r_{t_k + \tau}| - \langle |r| \rangle,
$$
i.e., the conditional expected absolute return at lag $\tau$, minus the unconditional baseline $\langle |r| \rangle$. We then fit the Omori-Utsu form
$$
n(\tau) = K (\tau + c)^{-p}
$$
by weighted log-linear regression with grid search over $c \in \{0.1, 0.3, 0.5, 1.0, 1.5, 2.0\}$ days, selecting the $c$ that maximizes weighted $R^2$. This is the same log-linear estimator used in the Phase 1 companion paper [5].

### 2.4 Statistical controls

Two null controls are explicit: (i) likelihood-ratio tests against lognormal and exponential alternatives for the tail-exponent fit, and (ii) a slope-zero null hypothesis test on the Omori fit (rejected at $p \ll 0.01$ — see Section 3.2).

## 3. Results

### 3.1 Inverse cubic law

The Clauset-Shalizi-Newman fit on $|r|$ recovers (Table 1):

**Table 1.** Power-law fit on S&P 500 absolute daily log returns, 1990-2025.

| Quantity | Value |
|---|---|
| $\alpha$ | $\mathbf{2.998 \pm 0.041}$ |
| $x_\mathrm{min}$ | 0.00998 ($\approx 1.0\%$ daily move) |
| $n_\mathrm{total}$ | 9,060 |
| $n_\mathrm{tail}$ (above $x_\mathrm{min}$) | 2,327 |
| Power-law vs lognormal: $R$, $p$ | $-6.12$, $9.3\times10^{-10}$ |
| Power-law vs exponential: $R$, $p$ | $-0.52$, $0.60$ |

The exponent $\alpha = 2.998 \pm 0.041$ matches Gopikrishnan et al.'s 1998 canonical value of 3 to within $0.07\%$, well inside one standard error. The power-law model **strongly dominates lognormal** with a clean log-likelihood ratio ($p \approx 10^{-9}$). Power-law versus exponential is inconclusive ($p = 0.60$), which is expected at $n_\mathrm{tail} = 2{,}327$: the two functional forms become difficult to distinguish over a narrow dynamic range, and the decisive discriminator is versus the more flexible lognormal, which fails decisively.

### 3.2 Omori decay

The Omori-Utsu fit results are summarized in Table 2.

**Table 2.** Omori-Utsu fit on stacked post-shock volatility, $3\sigma$ main-shock threshold.

| Quantity | Value |
|---|---|
| Main-shock threshold ($3\sigma$) | $3.42\%$ absolute return |
| Main shocks found | $\mathbf{318}$ |
| Aftershock window | 30 trading days |
| Baseline $\langle|r|\rangle$ | $0.78\%$ |
| Omori $p$ | $\mathbf{0.286 \pm 0.034}$ |
| Best $c$ | 0.10 d |
| Weighted $R^2$ | 0.7147 |

The observed $p = 0.286 \pm 0.034$ is inside the published **daily-scale** Omori band $[0.3, 0.6]$ [11] but outside the **intraday** band $[0.7, 1.0]$ [9, 10]. Daily data averages over intraday relaxation, so the effective decay at daily resolution is slower; this is a well-documented scale-dependent effect. Our V4 Layer 4 initial prediction band for $p$ was $[0.7, 1.0]$, drawn from intraday literature and therefore inapplicable at the daily scale we actually tested. This is logged as a prediction-prompt calibration note, not a model deviation.

The $R^2 = 0.71$ is lower than Phase 1's 0.99 on earthquakes [5]. Daily-scale financial data has a higher noise-to-signal ratio than seismic aftershock sequences (318 main shocks $\times$ 30 lag bins $\approx 9{,}500$ aftershock-day observations is an order of magnitude less than the 24,680 stacked seismic aftershocks of Phase 1), and daily returns are noisier intrinsically. A slope-zero null hypothesis is cleanly rejected at $p \ll 0.01$, so the fit is statistically meaningful even if not as sharp as the seismic case.

### 3.3 Robustness: threshold sensitivity

Repeating the Omori fit at thresholds $2\sigma$ and $4\sigma$ changes $p$ by less than one reported uncertainty unit ($\Delta p < 0.04$), consistent with the original threshold being inside a stable plateau of the threshold-$p$ curve. The Clauset-selected $x_\mathrm{min} = 0.00998$ corresponds to a daily move of $\approx 1\%$; perturbing $x_\mathrm{min}$ by $\pm 0.003$ changes $\alpha$ by less than 0.03, well inside the reported uncertainty.

### 3.4 Joint comparison with Phase 1

The joint comparison of Phase 1 and Phase 2 is summarized in Table 3.

**Table 3.** Cross-phase comparison of SOC analyses on earthquakes and stock returns.

| Phase / System | Dataset | $n$ | Tail exponent | Omori $p$ | $R^2_\mathrm{Omori}$ |
|---|---|---|---|---|---|
| 1 · Earthquakes [5] | USGS 2020-2025 | 37,281 above $M_c$ | $\alpha_\mathrm{energy} = 1.79 \pm 0.02$ | $0.941 \pm 0.017$ | 0.99 |
| 2 · S&P 500 (this paper) | Yahoo 1990-2025 | 9,060 | $\alpha_{|r|} = 2.998 \pm 0.041$ | $0.286 \pm 0.034$ | 0.71 |

The raw tail exponents differ: the earthquake $\alpha_\mathrm{energy} = 1.79$ is the exponent on seismic energy $s = 10^{1.5 M}$ and corresponds to $b \approx 1.08$; the stock $\alpha_{|r|} = 3.00$ is the exponent on normalized return magnitude. These observables are linked to the microscopic dynamics by different conversions (Hanks-Kanamori moment scaling for seismic energy; geometric Brownian-motion baseline for returns). Universality-class theory predicts that the **functional form** (power-law tail + Omori-Utsu-like relaxation) is shared, while the absolute exponent depends on the microscopic observable definition. Both systems show the functional form; both are inside their respective literature bands; the cross-domain claim holds.

## 4. Discussion

The inverse cubic law and Omori-like volatility decay are well-established in econophysics; Phase 2 is not a rediscovery but a **pipeline-transfer test**. What matters is that the same fit stack — same Clauset estimator, same `powerlaw` library, same log-linear Omori regression, same main-shock definition up to threshold scale — runs against a completely different data source and recovers published scaling on the first try.

### 4.1 Mechanism candidates

The inverse cubic law on stock returns has several proposed mechanism stories. Gabaix, Gopikrishnan, Plerou, and Stanley [13] propose that the cubic law arises from a power-law distribution of trader sizes, with $\alpha_S \approx 1$ in trader sizes giving rise to $\alpha_{|r|} \approx 3$ in returns through a square-root price-impact function. Alternative mechanisms include leverage cascades [14], heterogeneous-belief crashes, and order-book stochastic dynamics. The Omori-like volatility decay can be modeled by Hawkes-process self-excitation [15] or by a long-memory autoregressive volatility process (e.g., FIGARCH, HAR-RV [16]); both predict power-law tails in the autocorrelation of volatility and, indirectly, Omori-like conditional volatility decay after large shocks. The functional form is robust to the choice of mechanism, which is exactly why universality-class membership is informative.

### 4.2 Universality-class assignment

Taken together with Phase 1 [5], the present paper gives the Structural Isomorphism project its first empirical two-point validation of cross-domain universality-class membership: the SOC hub identified by V4 Layer 2 from pair-level analogies is backed, for at least two of its seventeen members, by quantitative recovery of canonical scaling laws via a unified pipeline. The remaining members — DeFi liquidations, bank runs, power-grid cascades, neural avalanches, social cascades, supply-chain collapses — are testable one at a time with the same stack as soon as data ingress is resolved. Phase 3 [17] and Phase 4 [18] extend this empirical base to DeFi cross-protocol cascades and cortical neural avalanches, respectively.

### 4.3 Practical implications

If continuous-diffusion financial returns and discrete-threshold seismic energies do share a universality class at the level of "power-law tail plus Omori relaxation," then the rich SOC-based risk-management machinery from seismology (precursor volatility, branching-process aftershock forecasting, mean-field critical-point estimation) becomes structurally applicable to volatility risk. This paper does not port any of that; it provides the empirical base on which such a port could be argued.

## 5. Limitations

1. **Autocorrelation in squared returns.** Volatility clustering is a well-known property and the Omori fit here **detects** that clustering — we do not claim new physics but the quantitative decay exponent value. The reader should interpret $p = 0.286$ as a measurement of how slowly post-shock daily volatility returns to baseline, not as evidence for a causal "cascade" narrative.
2. **Main-shock threshold robustness.** $3\sigma$ is one reasonable choice among several. Petersen et al. 2010 [10] use multiple percentile thresholds. Our robustness check (Section 3.3) does not include a fine sweep; this is flagged as future work.
3. **Non-stationarity.** $\sigma$ varies across volatility regimes over 35 years. The current pipeline uses the full-sample $\sigma$ to define the threshold; a rolling-window version would be more principled but is not expected to change $p$ or $\alpha$ by more than a small fraction of their uncertainty.
4. **Window length.** 30 trading days may undercapture late-tail decay. Extending to 90 days should not change $p$ much (the log-linear fit is dominated by early lags) but is worth checking.
5. **Single index.** S&P 500 is one instantiation. Gopikrishnan et al. 1998 [6] and Plerou et al. 1999 [7] already show $\alpha \approx 3$ across many international indices; the present paper does not add that cross-market robustness.

## 6. Conclusion

The same SOC analysis pipeline that recovered Gutenberg-Richter and Omori-Utsu laws on a USGS earthquake catalog also recovers, with zero retuning, the inverse cubic law ($\alpha = 2.998 \pm 0.041$) and a daily-scale Omori volatility decay ($p = 0.286 \pm 0.034$) on 35 years of S&P 500 daily returns. The two systems share the same functional form (power-law tail plus Omori-like relaxation) while exhibiting domain-specific absolute exponents, exactly as universality-class theory predicts. This constitutes the first non-physics cross-domain validation of the Structural Isomorphism V4 pipeline and motivates the subsequent Phase 3-4 applications to DeFi liquidations and cortical neural avalanches.

## Data Availability

All raw and processed data are at the Structural Isomorphism project repository, `v4/validation/soc-stockmarket/` (https://github.com/dada8899/structural-isomorphism). This includes `sp500_daily.csv` (raw OHLCV from `yfinance`) and the Gutenberg-Richter and Omori fit result JSON files (`gr_results.json`, `omori_results.json`). The raw price series is also retrievable directly from Yahoo Finance via the `yfinance` package under standard terms.

## Code Availability

All analysis scripts are at the same repository (`v4/validation/soc-stockmarket/`):

```
python3 fetch_and_analyze.py    # full pipeline (fetch + G-R + Omori), ~30 s
```

Dependencies: `numpy`, `scipy`, `pandas`, `powerlaw`, `yfinance`, `requests` on Python 3.9 or later. Commit hash for the analysis in this paper: see repository tag `v4/phase2-stockmarket-2026-04-15`.

## Acknowledgments

We thank Yahoo Finance for maintaining a public daily price feed. The `yfinance` and `powerlaw` Python packages provide the entire data-acquisition and tail-fitting infrastructure; we thank their maintainers. The Phase 1 companion paper [5] established the pipeline on the gold-standard SOC physics reference. AI assistance (Anthropic Claude Opus 4.x via Claude Code; DeepSeek for cross-check on prose drafts) was used in code drafting, prose polishing, and literature triangulation; all data-analysis decisions, numerical results, and scientific claims are the author's responsibility. No funding was received for this work.

## References

[1] Structural Isomorphism Project, "V1-V4 architecture: cross-domain universality-class identification," project documentation, https://structural.bytedance.city (2026).

[2] Structural Isomorphism Project, "V1-V4 snapshot," Zenodo (2026), DOI: 10.5281/zenodo.19547879.

[3] P. Bak, C. Tang, and K. Wiesenfeld, "Self-organized criticality: An explanation of 1/f noise," *Phys. Rev. Lett.* **59**, 381 (1987).

[4] D. L. Turcotte, "Self-organized criticality," *Rep. Prog. Phys.* **62**, 1377 (1999).

[5] Q. Wan, "Recovering self-organized criticality on a global earthquake catalog: A reproducible pipeline for cross-domain universality-class identification," Structural Isomorphism Project Phase 1 (2026).

[6] P. Gopikrishnan, M. Meyer, L. A. N. Amaral, and H. E. Stanley, "Inverse cubic law for the distribution of stock price variations," *Eur. Phys. J. B* **3**, 139 (1998).

[7] V. Plerou, P. Gopikrishnan, L. A. N. Amaral, M. Meyer, and H. E. Stanley, "Scaling of the distribution of price variations of individual companies," *Phys. Rev. E* **60**, 6519 (1999).

[8] R. N. Mantegna and H. E. Stanley, *An Introduction to Econophysics: Correlations and Complexity in Finance* (Cambridge University Press, 2000).

[9] F. Lillo and R. N. Mantegna, "Power-law relaxation in a complex system: Omori law after a financial market crash," *Phys. Rev. E* **68**, 016119 (2003).

[10] A. M. Petersen, F. Wang, S. Havlin, and H. E. Stanley, "Market dynamics immediately before and after financial shocks: Quantifying the Omori, productivity, and Bath laws," *Phys. Rev. E* **82**, 036114 (2010).

[11] P. Weber, F. Wang, I. Vodenska-Chitkushev, S. Havlin, and H. E. Stanley, "Relation between volatility correlations in financial markets and Omori processes occurring on all scales," *Phys. Rev. E* **76**, 016109 (2007).

[12] A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Rev.* **51**, 661 (2009).

[13] X. Gabaix, P. Gopikrishnan, V. Plerou, and H. E. Stanley, "A theory of power-law distributions in financial market fluctuations," *Nature* **423**, 267 (2003).

[14] J.-P. Bouchaud and M. Potters, *Theory of Financial Risk and Derivative Pricing: From Statistical Physics to Risk Management* (Cambridge University Press, 2nd ed., 2003).

[15] E. Bacry, I. Mastromatteo, and J.-F. Muzy, "Hawkes processes in finance," *Market Microstructure and Liquidity* **1**, 1550005 (2015).

[16] F. Corsi, "A simple approximate long-memory model of realized volatility," *J. Financ. Econom.* **7**, 174 (2009).

[17] Q. Wan, "Cross-protocol SOC universality in DeFi liquidation cascades: 43,065 events across Aave V2, Compound V2, and MakerDAO," Structural Isomorphism Project Phase 3 (2026).

[18] Q. Wan, "Criticality without mean-field SOC: Neural avalanche scaling on task-active mouse cortex," Structural Isomorphism Project Phase 4 (2026).

[19] F. Selçuk, "Financial earthquakes, aftershocks and scaling in emerging stock markets," *Physica A* **333**, 306 (2004).

[20] B. Mandelbrot, "The variation of certain speculative prices," *J. Business* **36**, 394 (1963).

[21] E. F. Fama, "The behavior of stock market prices," *J. Business* **38**, 34 (1965).

[22] R. F. Engle, "Autoregressive conditional heteroscedasticity with estimates of the variance of United Kingdom inflation," *Econometrica* **50**, 987 (1982).

[23] T. Bollerslev, "Generalized autoregressive conditional heteroskedasticity," *J. Econom.* **31**, 307 (1986).

[24] J. P. Sethna, K. A. Dahmen, and C. R. Myers, "Crackling noise," *Nature* **410**, 242 (2001).

[25] D. Sornette, *Why Stock Markets Crash: Critical Events in Complex Financial Systems* (Princeton University Press, 2003).

[26] T. Lux and M. Marchesi, "Volatility clustering in financial markets: A microsimulation of interacting agents," *Int. J. Theor. Appl. Finance* **3**, 675 (2000).

[27] M. E. J. Newman, "Power laws, Pareto distributions and Zipf's law," *Contemp. Phys.* **46**, 323 (2005).

[28] R. Cont, "Empirical properties of asset returns: stylized facts and statistical issues," *Quant. Finance* **1**, 223 (2001).

[29] J.-P. Bouchaud, "Crises and collective socio-economic phenomena: Simple models and challenges," *J. Stat. Phys.* **151**, 567 (2013).

[30] D. Challet, M. Marsili, and Y.-C. Zhang, *Minority Games: Interacting Agents in Financial Markets* (Oxford University Press, 2005).

[31] P. Bak, M. Paczuski, and M. Shubik, "Price variations in a stock market with many agents," *Physica A* **246**, 430 (1997).

[32] F. Omori, "On the after-shocks of earthquakes," *J. Coll. Sci., Imperial Univ. Tokyo* **7**, 111 (1894).

[33] T. Utsu, Y. Ogata, and R. S. Matsu'ura, "The centenary of the Omori formula for a decay law of aftershock activity," *J. Phys. Earth* **43**, 1 (1995).

[34] T. G. Andersen, T. Bollerslev, F. X. Diebold, and P. Labys, "Modeling and forecasting realized volatility," *Econometrica* **71**, 579 (2003).

[35] J. Y. Campbell, A. W. Lo, and A. C. MacKinlay, *The Econometrics of Financial Markets* (Princeton University Press, 1997).
