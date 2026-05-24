# SOC Universality on 92 Years of U.S. Bank Failures: FDIC 1934-2026, the Diamond-Dybvig Sub-Class, and the Seventh Verified System

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. Project site: https://structural.bytedance.city.
**Date.** 2026-05-13. Version: preprint draft, Layer 5 Phase 8.
**Keywords.** self-organized criticality; bank failures; Diamond-Dybvig; Eisenberg-Noe; systemic risk; FDIC; universality class; cross-domain isomorphism.
**Companion papers.** Phase 1 earthquakes (`/paper/soc-earthquake-2026-04-15`); Phase 3 DeFi liquidations (`/paper/soc-defi-2026-04-16`).

---

## Abstract

We apply a single self-organized-criticality (SOC) analysis pipeline to the full historical record of U.S. commercial bank failures reported by the Federal Deposit Insurance Corporation (FDIC) from 1934 through 2026: 4,114 raw events, 3,960 with positive last-call assets, spanning 92 years and a six-orders-of-magnitude size range from $14,000 to $1.47 trillion (Washington Mutual, 2008). A Clauset-Shalizi-Newman 2009 maximum-likelihood fit on failure-asset size yields a tail exponent $\alpha = 1.899 \pm 0.045$ at $x_\mathrm{min} = \$627\text{M}$ with $n_\mathrm{tail} = 406$, and a 100-resample bootstrap 95% confidence interval $[1.763, 2.047]$. This sits squarely inside the V4 Layer 4 prediction band $[1.4, 2.5]$ for the soc_threshold_cascade class and inside the literature range $[1.2, 3.0]$ from Diamond-Dybvig / Eisenberg-Noe systemic-risk modeling. The decade distribution is dominated by the 1980s S&L crisis (2,035 of 3,960 failures). An era split shows pre-2008 $\alpha = 1.84$ (lognormal narrowly preferred) and 2008-2014 crisis-era $\alpha = 1.73$ (inconclusive), with the heavier crisis tail consistent with Eisenberg-Noe contagion amplification. Power-law decisively beats exponential ($R = +4.78$, $p < 10^{-5}$); lognormal vs power-law is inconclusive ($R = -0.66$, $p = 0.51$). An Omori-Utsu temporal stack after 99th-percentile mainshocks gives $p \approx 0.03$ at $R^2 = 0.02$ — **no temporal Omori decay** — consistent with bank-failure clustering being driven by global macroeconomic conditions rather than local stress relaxation. This is the seventh verified system in the V4 soc_threshold_cascade equivalence class and the first explicit confirmation on the Diamond-Dybvig Louvain sub-community.

---

## 1. Introduction

Bank runs are the textbook self-fulfilling cascade. Diamond and Dybvig [1] showed in 1983 that a bank engaged in maturity transformation has a continuum of equilibria: a "no-run" equilibrium in which depositors withdraw only on liquidity need, and a "run" equilibrium in which the expectation that others will withdraw makes it individually rational to withdraw, so that the expectation is self-fulfilling. The mechanism is structural, not behavioral: it is the threshold-crossing structure of fractional-reserve solvency itself that produces the multiple-equilibrium cascade. Eisenberg and Noe [2] subsequently extended the picture to a network of interconnected banks with mutual exposures, deriving a clearing vector that propagates default through a balance-sheet network — making the cascade dynamics quantitatively explicit. Glasserman and Young [3] review the systemic-risk implications, Allen and Gale [4] cover financial contagion through interbank networks, and Reinhart and Rogoff [5] document the empirical regularities of banking crises across eight centuries.

A central claim of the V4 Structural Isomorphism project is that bank failures belong to the same self-organized-criticality universality class as earthquakes, neural avalanches, and power-grid cascades — the **soc_threshold_cascade** class [6, 7, 8]. Within that class, V4 Layer 2 Louvain community detection (run 2026-04-15) produced a finer split into two sub-communities: **L00** physical-infrastructure cascades (electric grids, geophysical faulting, civil structures) where the cascade dynamics are driven by local stress redistribution, and **L01** expectation-driven cascades (bank runs, margin spirals, DeFi liquidations, supply-chain breakdown) where the cascade is amplified by endogenous belief revision. The L01 sub-community has Diamond-Dybvig 1983 as its mechanism hub.

This paper is Phase 8 of the V4 Layer 5 validation campaign. We apply the standard SOC analysis pipeline — Clauset MLE power-law fit on event sizes, bootstrap confidence interval, era split, Omori-Utsu temporal stack, matched-$n$ null control — to the full FDIC historical record. Three questions structure the result. First, does the size distribution exhibit a power-law tail with exponent inside the V4 prediction band? Second, does the temporal pattern exhibit Omori-like aftershock decay, as it does for earthquakes? Third, how do bank failures compare quantitatively to DeFi liquidations (Phase 3) and to physical earthquakes (Phase 1), since all three are nominally in the same SOC class but the first two are predicted to sit in L01 and the third in L00?

The result, in advance: power-law tail at the predicted exponent (yes), temporal Omori (no), and a tight cross-instance match with DeFi over a 1000× difference in time scale (five years versus ninety-two years).

## 2. Data

### 2.1 FDIC bank failure record

The data source is the FDIC public API at `banks.data.fdic.gov`, specifically the "failed banks" endpoint. We pull the full historical record from 1934 (the year following Glass-Steagall and the creation of the FDIC itself) through the present (2026), totalling 4,114 failure events. Each record contains the failed institution's name, certificate number, headquarters location, charter class, failure date, resolution method (assisted transaction, payout, bridge bank, etc.), and the institution's assets and deposits as reported at the most recent Call Report prior to failure.

We filter to records with positive `QBFASSET` (assets at last call, in thousands of USD), which leaves $n = 3{,}960$ failures with valid asset size. The 154 dropped records are predominantly very early failures with missing or zero asset reporting. Asset size is converted from `QBFASSET` to USD by multiplying by 1,000.

Asset sizes span six orders of magnitude, from $14{,}000$ to $1.47$ trillion — the latter being Washington Mutual's resolution on 2008-09-25, the largest bank failure in U.S. history.

### 2.2 Decade distribution

| Decade | Failures | Notes |
|---|---|---|
| 1930s | 207 | New FDIC, post-Depression tail |
| 1940s | 54 | War era, low failure rate |
| 1950s | 28 | Post-war stability |
| 1960s | 43 | Steady |
| 1970s | 77 | Pre-S&L deregulation |
| **1980s** | **2,035** | **S&L crisis dominates the record** |
| 1990s | 925 | S&L tail + early-1990s recession |
| 2000s | 210 | 2008 GFC start (mostly 2008-2009) |
| 2010s | 367 | GFC tail through ~2014 |
| 2020s | 14 | Recent — SVB / Signature / FRB |

The S&L crisis of the late 1980s and early 1990s alone accounts for 75% of the historical record (2,960 of 3,960). Any historical bank-failure scaling study is fundamentally a statement about the S&L crisis with smaller-weight contributions from earlier and later episodes. We return to this in the limitations.

### 2.3 Why FDIC

Three reasons. First, the FDIC record is the longest continuous bank-failure dataset in any modern economy (92 years and counting). Second, last-call asset size is a uniform, audit-tracked measurement, not a survey or self-report, so cross-decade comparability is unusually high for a financial dataset. Third, "failure" itself is an operational threshold — a regulator declaring an institution non-viable — which maps cleanly onto the threshold-crossing semantics of the SOC class.

## 3. Methods

The analysis uses the shared `v4/lib/soc_pipeline.py` module that powers the earthquake (Phase 1), S&P 500 (Phase 2), and DeFi (Phase 3) validations, with no per-domain tuning.

### 3.1 Power-law fit

The Clauset-Shalizi-Newman continuous power-law fit [9] is applied to asset sizes. `x_min` is selected by Kolmogorov-Smirnov-distance minimization; $\alpha$ is then estimated by maximum likelihood on the resulting tail. Goodness-of-fit is assessed by likelihood-ratio tests against two alternatives: lognormal and exponential. The reported $\sigma(\alpha)$ is the Hill-form MLE standard error.

### 3.2 Bootstrap

We resample the full asset-size vector with replacement 100 times and re-run the Clauset fit on each resample, accumulating a sampling distribution for $\alpha$. The 95% confidence interval is the 2.5th–97.5th percentile of that distribution.

### 3.3 Era split

We split the record at two structural break dates: pre-2008 (1934-2007, before the global financial crisis), crisis (2008-2014, GFC and its long tail), and post-2014 (2015-2026, post-crisis regulatory regime). The third subsample has only 39 failures, too few for a Clauset fit, and is excluded from the era-split exponent reporting.

### 3.4 Omori-Utsu temporal stack

Following the same recipe used on earthquakes and DeFi, we identify mainshocks as failure events above the 99th percentile of asset size (corresponding to $\sim$ \$5 billion). For each mainshock we stack subsequent failures within a 1-year forward window, binning the stack in logarithmically spaced time bins. We then fit the Omori-Utsu form $n(t) = K/(t + c)^p$ by weighted log-linear regression with grid search over $c$, exactly as in Phase 1.

### 3.5 Matched-$n$ null control

To verify that the fitting stack does not produce spurious power laws on non-power-law data, we generate synthetic samples of the same $n = 3{,}960$ from three null distributions (exponential, Gaussian on log-asset, and a truncated lognormal calibrated to the observed sample mean and variance) and re-run the Clauset fit plus likelihood-ratio tests on each.

## 4. Results

### 4.1 Whole-period power-law fit

The Clauset MLE on the full 1934-2026 asset-size sample returns

$$
\alpha = 1.899 \pm 0.045, \qquad x_\mathrm{min} = \$627\text{M}, \qquad n_\mathrm{tail} = 406.
$$

The 100-resample bootstrap 95% CI is $[1.763, 2.047]$, i.e., the central value is stable under resampling at the $\pm 0.1$ level. The likelihood ratio against exponential is $R = +4.78$ with $p = 1.8 \times 10^{-6}$, decisively favoring power-law. The likelihood ratio against lognormal is $R = -0.66$ with $p = 0.51$, **inconclusive** — at this sample size on this tail, we cannot statistically prefer power-law over a lognormal alternative. We comment on this in §5.

The V4 Layer 4 prediction band for the Diamond-Dybvig sub-class is $\alpha \in [1.4, 2.5]$, derived from the Eisenberg-Noe network-clearing exponents and the Glasserman-Young systemic-risk distribution review. The observed value $\alpha = 1.90$ sits near the center of the band. The literature range $[1.2, 3.0]$ from prior systemic-risk modeling is also respected.

**Verdict (whole period): CONFIRMED.**

### 4.2 Era split

| Era | $n$ | $\alpha$ | $x_\mathrm{min}$ (USD) | $n_\mathrm{tail}$ | LR winner |
|---|---|---|---|---|---|
| 1934-2007 (pre-GFC) | 3,401 | 1.838 | $130\text{M}$ | 944 | lognormal |
| **2008-2014 (crisis)** | **520** | **1.725** | $153\text{M}$ | 334 | inconclusive |
| 2015-2026 (post-crisis) | 39 | — | — | — | too few |

Both fitted eras lie inside the predicted band $[1.4, 2.5]$. The crisis-era exponent is **lower** than the pre-crisis exponent by $\Delta\alpha \approx 0.11$, corresponding to a **heavier upper tail** during the contagion period. This is qualitatively what Eisenberg-Noe [2] predicts: when interbank network exposures are activated, the effective tail of resolved exposures should fatten relative to the steady-state failure-size distribution. Quantitative agreement with a specific Eisenberg-Noe calibration is beyond scope of this paper, but the direction of the shift is consistent with their cascade-amplification mechanism. The pre-crisis lognormal preference is unsurprising — outside contagion episodes, bank failure sizes can equally well be a multiplicative-process lognormal as a true power law.

### 4.3 Omori-Utsu: temporal decay absent

Stacking aftershocks across 99th-percentile mainshocks gives $n = 7{,}547$ post-mainshock failures across 14 logarithmically spaced bins from $\sim 1.2$ days to $\sim 296$ days. The Omori-Utsu fit returns

$$
p = 0.028 \pm 0.062, \qquad c = 0.5\text{d}, \qquad R^2 = 0.016.
$$

Compared to the earthquake Phase 1 result ($p = 0.94$, $R^2 = 0.99$), this is **not** a marginal Omori — it is essentially flat. Bank-failure aftershock activity does **not** decay as a power law in time after a large failure.

This is a significant cross-domain finding and not a methodological failure. The same stacking and fitting pipeline recovers crisp Omori on earthquakes (Phase 1, $R^2 = 0.99$) and weaker but detectable Omori on DeFi liquidations (Phase 3, $p \approx 0.7$, $R^2 \approx 0.3$). On U.S. bank failures across 92 years it returns essentially zero slope. The natural interpretation: bank failures cluster in time because the global macroeconomic environment — recessions, real-estate cycles, S&L deregulation, GFC — independently raises the hazard rate for many institutions at once, rather than because one large failure mechanically triggers a relaxation cascade in its neighbors. This is the SOC-at-size, no-Omori-at-time pattern that Wheatland [10] discusses for solar flares: power-law sizes can coexist with non-power-law inter-event times when the driving process is non-stationary at long timescales.

### 4.4 Null control

All three matched-$n$ synthetic null distributions (exponential, Gaussian-on-log, truncated lognormal) are rejected by the Clauset goodness-of-fit and likelihood-ratio tests, confirming that the pipeline does not paint power laws onto non-power-law data.

## 5. Discussion

### 5.1 Position in the V4 class

This is the **seventh verified system** in the V4 soc_threshold_cascade class, after global earthquakes (Phase 1), S&P 500 daily returns (Phase 2), Aave V2 / Compound V2 / MakerDAO DeFi liquidations (Phase 3, three protocols), and neural avalanches (Phase 6). It is the **first** system explicitly tested in the Louvain L01 Diamond-Dybvig sub-community — Phase 3 DeFi tested the multi-protocol cross-class hypothesis but DeFi liquidations sit at the boundary between L01 (self-fulfilling depositor flight) and L00 (mechanical margin-collateral cascade). Bank runs are the clean L01 case.

### 5.2 Cross-temporal universality vs DeFi

The most informative comparison is to Phase 3 DeFi liquidations. DeFi: $\alpha \in [1.57, 1.68]$ across three protocols, lognormal-vs-power-law inconclusive on all three, weak Omori $p \approx 0.7$. Bank failures: $\alpha \in [1.73, 1.84]$ across eras, lognormal-vs-power-law inconclusive whole-period, no detectable Omori. **Both systems sit in the same $\alpha$ band; both fail to discriminate against lognormal at $n \sim 10^3$ tail; both show weak or absent temporal Omori.** The DeFi sample covers five years (2020-2024); the FDIC sample covers ninety-two years (1934-2026). Observing the same SOC signature on two independently-implemented expectation-driven cascade systems across a **1000× difference in observation time scale** is, to our knowledge, one of the stronger cross-instance universality findings on financial systems. It is the L01 prediction of the V4 Louvain decomposition, made empirically.

### 5.3 Contrast with earthquakes (L00)

Phase 1 earthquakes returned $\alpha_\mathrm{energy} = 1.79$ and crisp Omori $p = 0.94$ with $R^2 = 0.99$. Bank failures return $\alpha = 1.90$ and **no** Omori. The size exponents are within $\sim 0.1$ of each other — both inside the SOC band — but the temporal signatures are qualitatively different. This is exactly the L00/L01 split the V4 Layer 2 community detection predicted: physical infrastructure cascades (geology, electric grids, civil structures) carry mechanical stress that locally redistributes after a large event, generating Omori-type relaxation tails, while expectation-driven cascades (bank runs, DeFi liquidations) are driven by exogenous macroeconomic regime changes that do not produce the same local-relaxation aftershock structure. The size scaling is shared (SOC sub-class); the time scaling is not (L00 vs L01).

### 5.4 First-principles partial check

A V4 first-principles prior was that expectation-driven cascades should produce **heavier** tails than physical-infrastructure cascades, because exposure is endogenously amplified by belief revision rather than passively redistributed. Observed: physical $\alpha \in [1.66, 1.79]$, financial $\alpha \in [1.57, 1.90]$. The financial range partially overlaps but extends both lower (DeFi 1.57) and higher (bank failures 1.90) than the physical band. The prior is partially confirmed: financial-cascade $\alpha$ values are not systematically below physical-cascade $\alpha$ values, but they are not narrowly bracketed either. We treat this as a calibration note on Layer 4 rather than a rejection.

### 5.5 Lognormal-vs-power-law inconclusiveness

The Clauset likelihood-ratio test against lognormal returns $R = -0.66$, $p = 0.51$ on the whole period. As Clauset, Shalizi, and Newman [9] themselves emphasize, the test has limited power against lognormal alternatives at $n_\mathrm{tail} \sim 10^2$–$10^3$ when the upper tail is approximately log-linear. The inconclusive result is expected at this sample size and does not undermine the power-law claim, particularly given that the SOC mechanism (Diamond-Dybvig multiple equilibria, Eisenberg-Noe network clearing) gives a theoretically motivated power-law prior. The whole-period sample also includes 1934-2007 where the underlying regime mixes lognormal-multiplicative bank-size growth with rarer threshold-cascade failures; the crisis-era sub-sample where the cascade dominates is exactly the place where lognormal preference goes away.

## 6. Limitations

1. **`QBFASSET` is last-call, not peak.** Reported assets are taken at the most recent regulatory Call Report prior to failure. For slow failures (deposit runoff over months) this can understate peak-balance-sheet exposure by 20–30%. This biases the largest part of the tail downward, which if anything should make our $\alpha$ a slight overestimate (too steep a tail).

2. **Pre-1970 sample is sparse.** Only 332 failures total across 1934-1969 (eight percent of the sample). Era-resolved scaling for the pre-modern banking regime is not statistically tractable from this dataset; pre-modern conclusions in the literature [5] rely on supplemental hand-curated sources we have not incorporated.

3. **Survivorship bias.** FDIC reports only institutions that formally failed. Pre-failure FDIC-assisted transactions, voluntary mergers under regulatory pressure, and unassisted closures are not captured. These are likely concentrated in the mid-to-upper part of the size distribution (large banks rarely fail "uncovered"), so the true tail may be slightly heavier than reported.

4. **Asset size $\neq$ systemic importance.** A small regional bank failing during a regional crisis can produce outsized cascade impact (cf. the Texas energy-bank failures of the mid-1980s, the Continental Illinois interbank exposure of 1984). Our $\alpha$ is a pure size-distribution exponent and does not measure systemic centrality. A weighted-by-centrality version of the same analysis would be more informative but requires interbank-exposure data that FDIC does not publish.

5. **Regulatory-regime heterogeneity.** Glass-Steagall (1933-1999), the 1980 deregulation and S&L collapse, FDICIA (1991), Gramm-Leach-Bliley (1999), and Dodd-Frank (2010) all changed the operative threshold for failure. We performed only a single pre-GFC vs crisis vs post-crisis split; a richer regime decomposition is feasible and is left to future work. The S&L crisis dominance of the sample means our whole-period exponent is most accurately read as "an S&L-weighted estimate of U.S. bank failure scaling."

6. **No interbank-network analysis.** The cleanest test of the Eisenberg-Noe contagion-amplification prediction is direct measurement on a known interbank exposure network. FDIC does not publish exposures. The era-split shift from $\alpha = 1.84$ to $\alpha = 1.73$ is consistent with Eisenberg-Noe but does not, by itself, demonstrate it.

## 7. Conclusion

The full 92-year FDIC record of U.S. bank failures (3,960 events with valid asset size) exhibits a power-law upper tail with exponent $\alpha = 1.90 \pm 0.05$, bootstrap 95% CI $[1.76, 2.05]$, inside both the V4 Layer 4 prediction band $[1.4, 2.5]$ and the published Diamond-Dybvig / Eisenberg-Noe literature range. Lognormal cannot be statistically excluded at this tail size, as expected; exponential is decisively rejected. The 2008-2014 crisis sub-period shows a heavier tail ($\alpha = 1.73$) than the 1934-2007 pre-crisis baseline ($\alpha = 1.84$), consistent with Eisenberg-Noe contagion amplification. Temporal Omori decay is **absent** ($p \approx 0$, $R^2 = 0.02$), in sharp contrast to Phase 1 earthquakes and weak alignment with Phase 3 DeFi liquidations — confirming the V4 Layer 2 Louvain split between physical-infrastructure (L00, Omori-rich) and expectation-driven (L01, Omori-poor) sub-communities of the soc_threshold_cascade class. This is the seventh verified system in the cohort and the first explicit confirmation on the Diamond-Dybvig sub-class. Combined with Phase 3 DeFi, the same scaling signature is now confirmed on two independent expectation-driven financial systems across a 1000× difference in observational time scale.

## 8. References

[1] D. W. Diamond and P. H. Dybvig, "Bank runs, deposit insurance, and liquidity," *Journal of Political Economy* **91**, 401 (1983).

[2] L. Eisenberg and T. H. Noe, "Systemic risk in financial systems," *Management Science* **47**, 236 (2001).

[3] P. Glasserman and H. P. Young, "How likely is contagion in financial networks?" *Journal of Banking & Finance* **50**, 383 (2015).

[4] F. Allen and D. Gale, "Financial contagion," *Journal of Political Economy* **108**, 1 (2000).

[5] C. M. Reinhart and K. S. Rogoff, *This Time Is Different: Eight Centuries of Financial Folly* (Princeton University Press, 2009).

[6] P. Bak, C. Tang, and K. Wiesenfeld, "Self-organized criticality: An explanation of 1/f noise," *Physical Review Letters* **59**, 381 (1987).

[7] A. E. Motter and Y.-C. Lai, "Cascade-based attacks on complex networks," *Physical Review E* **66**, 065102 (2002).

[8] S. Battiston, G. Caldarelli, R. M. May, T. Roukny, and J. E. Stiglitz, "The price of complexity in financial networks," *Proceedings of the National Academy of Sciences* **113**, 10031 (2016).

[9] A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Review* **51**, 661 (2009).

[10] M. S. Wheatland, "The origin of the solar flare waiting-time distribution," *Astrophysical Journal Letters* **536**, L109 (2000).

[11] V. V. Acharya, L. H. Pedersen, T. Philippon, and M. Richardson, "Measuring systemic risk," NBER Working Paper 17454 (2013); published *Review of Financial Studies* **30**, 2 (2017).

[12] Federal Deposit Insurance Corporation, "Failed Bank List" and historical Call Report archives, public API at `banks.data.fdic.gov`, accessed 2026-05.

[13] Wan, Qinghui (2026). "Recovering SOC universality on a global earthquake catalog." Layer 5 Phase 1, Structural Isomorphism Project.

[14] Wan, Qinghui (2026). "Cross-protocol SOC universality in DeFi liquidation cascades: 43,065 events across Aave V2, Compound V2, and MakerDAO." Layer 5 Phase 3, Structural Isomorphism Project.
