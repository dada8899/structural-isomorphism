# Cross-Domain Tail Copula Test: Are Financial Extremes and Natural-Disaster Extremes Co-Occurring?

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. Project site: https://structural.bytedance.city.
**Date.** 2026-05-13. Version: A2 Phase 6 (universality class #6) preprint draft.
**Keywords.** copula; upper tail dependence; cross-domain co-extremes; Gumbel; survival Clayton; financial markets; natural disasters; cross-domain universality.
**Companion papers.** SOC pipeline validation (`/paper/soc-earthquake-2026-04-15`), S&P inverse cubic (`/paper/soc-stockmarket-2026-04-15`).

---

## Abstract

Layer 4 of the Structural Isomorphism project (V4) places, alongside the better-known SOC threshold-cascade class, a second proposed equivalence class **#6: tail copula** — the claim that heavy-tailed marginals from genuinely different domains can share *joint* extreme behaviour, captured by a non-zero upper tail dependence coefficient $\lambda_U$. The literature gives strong $\lambda_U \in [0.1, 0.4]$ for pairs *within* finance (equity indices, FX, credit) and for many *within*-climate pairs (precipitation, temperature). The strongest possible cross-domain version of class #6 is that two domains whose only contact is the macro-economy — equity prices and natural-disaster damages — still exhibit $\lambda_U > 0$. We test this on 7,300 trading days (1996-2024) joining the S&P 500 daily absolute log returns to total NOAA Storm Events damage on the same calendar day. Pseudo-uniform marginals are obtained by empirical CDF rank transform; $\lambda_U$ is estimated three ways (empirical at quantiles $0.90, 0.95, 0.975, 0.99$; Gumbel-copula MLE; survival-Clayton MLE), with block-bootstrap 95% CIs and a 1000-replicate permutation null. The empirical $\lambda_U(0.95) = 0.052$ is indistinguishable from the independence null mean of $0.050$ ($p_{99}$ of null $= 0.077$); the Gumbel MLE drives $\theta \to 1$ (independence boundary, $\lambda_U \to 0$); survival Clayton drives $\theta \to 0$ ($\lambda_U \to 0$); and the conditional baseline lift $P(\text{extreme storm}|\text{extreme return})/P(\text{extreme storm}) = 1.04$ is essentially unity. **A within-domain positive control** — $|r_t|$ versus $|r_{t-1}|$ — recovers $\lambda_U(0.95) = 0.21$ and Gumbel $\lambda_U = 0.138$, well inside the published volatility-clustering range, so the methodology is not at fault. The verdict for the cross-domain version of universality class #6 is **REJECTS** on this domain pair. We interpret this as a sharp narrowing of the class: tail copula universality holds *within* mechanism-coupled domains (within finance, within climate, within network cascades) but does not extend to two domains separated by a macroeconomic lag of weeks-to-quarters. This is itself a falsifiable, transferable prediction.

---

## 1. Introduction

Empirical content of the Structural Isomorphism programme rests on members of a putative universality class behaving the same way under the same analysis. Phase 1 (SOC inverse-cubic / Omori) recovered the canonical SOC exponents on earthquakes and on the S&P 500 with no parameter retuning, supporting class #1. Universality class #6, "tail copula", is a different claim: not about the marginal exponent of a single series but about the **joint** behaviour of two series at the upper extreme.

The upper tail dependence coefficient is

$$
\lambda_U \;=\; \lim_{u \to 1^{-}} \; \Pr\!\bigl[ \,V > F_V^{-1}(u) \;\bigm|\; U > F_U^{-1}(u)\,\bigr],
$$

where $U = F_X(X), V = F_Y(Y)$ are the pseudo-uniform marginals. $\lambda_U \in [0, 1]$; $\lambda_U = 0$ means asymptotically independent in the upper tail; $\lambda_U > 0$ means a non-negligible fraction of one variable's extremes co-occur with the other's. Within finance, paired tail dependence is well established: equity-index pairs after the 2008 crisis give $\lambda_U$ between $0.10$ and $0.40$ (Embrechts, McNeil, Straumann 2002; Patton 2006); within climate, paired precipitation and wind-speed extremes likewise give non-zero $\lambda_U$ (Salvadori et al. 2007). The natural Layer 4 question is whether $\lambda_U > 0$ extends to *cross-domain* pairs that share no obvious physical coupling — i.e., is class #6 a property of "any heavy-tailed bivariate" or only of mechanism-coupled domains?

The strongest published cross-domain candidate is **financial markets versus natural-disaster damages** in the same country (US): the macro-economy receives shocks from large natural disasters (Hsiang & Jina 2014; Bansal et al. 2019) and conversely financial stress can amplify climate-policy outcomes (Battiston et al. 2017). If class #6 is a universal property of joint heavy tails, $\lambda_U > 0$ should appear here. If $\lambda_U \approx 0$, the class is narrower than initially stated, and that narrowing is itself useful.

The contributions are:

1. A reproducible cross-domain joint tail dependence pipeline on two publicly available, distinct-mechanism datasets (S&P 500, NOAA Storm Events).
2. Three independent $\lambda_U$ estimators (empirical, Gumbel-MLE, survival-Clayton-MLE) with block-bootstrap CIs and a permutation null.
3. A within-domain positive control (volatility clustering) demonstrating the pipeline detects known tail dependence when it is present.
4. A clean negative finding for cross-domain class #6 with explicit boundary conditions.

## 2. Data

### 2.1 S&P 500 daily returns

Daily adjusted close prices of `^GSPC` from Yahoo Finance, 1990-01-02 through 2025-12-30 (9,066 trading days, dataset reused from companion paper). We compute $r_t = \log(P_t/P_{t-1})$ and restrict to 1996-01-02 onward to match NOAA Storm Events coverage. Within the restricted window: 7,300 trading days, $\sigma(r) = 0.0119$, range $r \in [-0.128, +0.110]$.

### 2.2 NOAA Storm Events 1996-2024

The NOAA NCEI Storm Events Database is the canonical public catalogue of US severe-weather events (tornadoes, hurricanes, hail, flooding, wildfires, winter storms, etc.). We pulled the full yearly `details` CSVs for 1996-2024 from `https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/` (29 files, ~290 MB compressed, fetched 2026-05-13). Coverage begins 1996 because pre-1996 records have systematic damage-field gaps. The raw catalogue contains **1,708,370 events** with a `DAMAGE_PROPERTY` and `DAMAGE_CROPS` string per event (formats: `1.50K`, `2.30M`, `5.00B`).

We parse damage strings to USD and aggregate by event begin-date, producing a single daily series `total_damage_usd` over **10,580 distinct dates**. The five largest damage-days are (i) 2005-08-29 ($5.0 \times 10^{10}$, Katrina), (ii) 2017-08-26 ($3.3 \times 10^{10}$, Harvey), (iii) 2005-08-28 ($2.5 \times 10^{10}$, Katrina precursor), (iv) 2017-09-20 ($1.8 \times 10^{10}$, Maria mainland tracks), and (v) 2018-11-08 ($1.7 \times 10^{10}$, Camp Fire). All five are widely recognised major-disaster days, providing immediate face validity.

### 2.3 Joint sample

We left-join the storm series onto the S&P trading-day calendar (NYSE-business-days), filling missing storm days with $0$. This yields the 7,300-day joint sample. Series A (financial) is $|r_t|$; series B (climate) is `total_damage_usd`. Both are heavily right-tailed: the largest absolute-return day is 2008-10-13 ($|r| = 0.108$); the largest storm day is 2005-08-29 ($\$5.0 \times 10^{10}$). The two series have **no** common timestamp among their respective top-5 days.

## 3. Methods

### 3.1 Marginal transform

To remove all margin-shape effects we apply the empirical CDF rank transform with continuity correction:

$$ U_t \;=\; \mathrm{rank}(X_t) \,/\, (n+1), \qquad V_t \;=\; \mathrm{rank}(Y_t) \,/\, (n+1). $$

The transformed sample $\{(U_t, V_t)\}_{t=1}^{n}$ has uniform marginals by construction; any remaining structure is purely copula structure.

### 3.2 Three $\lambda_U$ estimators

**Empirical.** For $q$ close to $1$, $\hat\lambda_U(q) = \Pr[V > q \mid U > q]$ computed directly from indicator counts. We report a panel of four quantiles, $q \in \{0.90, 0.95, 0.975, 0.99\}$, and the average. The $q=0.95$ value is the headline.

**Gumbel copula MLE.** The Gumbel family has $C(u,v;\theta) = \exp[-((-\log u)^\theta + (-\log v)^\theta)^{1/\theta}]$ with $\theta \geq 1$; tail asymmetry is upper, $\lambda_U = 2 - 2^{1/\theta}$, $\lambda_L = 0$. Density is Joe's (1997) closed form. We minimise the negative log-likelihood by bounded scalar search on $\theta \in [1.001, 20]$.

**Survival Clayton MLE.** The Clayton family $C(u,v;\theta) = (u^{-\theta} + v^{-\theta} - 1)^{-1/\theta}, \theta > 0$ has lower tail dependence $\lambda_L = 2^{-1/\theta}, \lambda_U = 0$. The $180^\circ$-rotated (survival) variant applies Clayton to $(1-u, 1-v)$, so the *upper* tail dependence of the original is $\lambda_U = 2^{-1/\theta}$. MLE by bounded search on $\theta \in [10^{-3}, 20]$.

Gumbel and Clayton are intentionally chosen as the two most common one-parameter Archimedean families with opposite tail-structure assumptions; agreement across them is evidence the result is not a parametric artefact.

### 3.3 Inference: block bootstrap + permutation null

**Block bootstrap** ($B = 500$, block length $= 20$ trading days) preserves short-range temporal autocorrelation. For each replicate we recompute all three estimators; we report the 2.5 / 97.5 percentile CIs.

**Permutation null** ($P = 1000$, shuffle $V$ only) constructs the empirical distribution of $\lambda_U(0.95)$ under independence. The observed $\hat\lambda_U(0.95)$ is significant iff it exceeds the 99th-percentile of the null distribution.

### 3.4 Positive control

To rule out an estimator failure, we run the identical pipeline on $(|r_t|, |r_{t-1}|)$ within the financial series. Volatility clustering is one of the oldest and most robust stylised facts in finance; under the empirical class #6 claim, $\lambda_U$ for $(|r_t|, |r_{t-1}|)$ should be solidly positive.

### 3.5 Baseline lift

Independent of copula structure, we compute the simplest possible signal: ratio of conditional to unconditional probability of an extreme storm day, conditioning on an extreme absolute-return day, using matched quantile thresholds $q = 0.95$.

## 4. Results

### 4.1 Headline numbers

| Estimator | $\lambda_U$ | 95% CI | Interpretation |
|---|---|---|---|
| Empirical $\hat\lambda_U(q=0.90)$ | $0.089$ | — | $1\sigma$ above null mean |
| Empirical $\hat\lambda_U(q=0.95)$ | $0.052$ | $[0.030, 0.077]$ | indistinguishable from null mean $0.050$ |
| Empirical $\hat\lambda_U(q=0.975)$ | $0.022$ | — | below null |
| Empirical $\hat\lambda_U(q=0.99)$ | $0.000$ | — | zero co-extreme top-1% pairs |
| Gumbel MLE | $0.0014$ | $[0.0014, 0.0129]$ | $\theta = 1.001$, independence boundary |
| Survival-Clayton MLE | $\approx 0$ | $[0, 5 \times 10^{-16}]$ | $\theta = 0.001$, independence boundary |

Both parametric MLEs collapse to the boundary of their parameter space, the strongest possible numerical statement that the data prefer the independence model.

### 4.2 Permutation null

The 1000-replicate null gives mean $\bar\lambda_U^{\,\text{null}}(0.95) = 0.0501$, $p_{95}^{\,\text{null}} = 0.0685$, $p_{99}^{\,\text{null}} = 0.0767$. Observed $\hat\lambda_U(0.95) = 0.052$ sits **inside the bulk** of the null (rank $\sim 0.55$); we cannot reject independence.

### 4.3 Baseline lift

| Threshold | Value |
|---|---|
| $P(\text{extreme storm}, q=0.95)$ | $0.0500$ |
| $P(\text{extreme storm} \mid \text{extreme }|r|)$ | $0.0521$ |
| Lift ratio | $1.041$ |

A $4 \%$ lift is economically and statistically negligible at $n_{\text{extreme}|r|}=365$ extreme-return days.

### 4.4 Positive control

| Pair | $\hat\lambda_U(0.95)$ | $\hat\lambda_U(0.99)$ | Gumbel $\lambda_U$ |
|---|---|---|---|
| $(|r_t|, |r_{t-1}|)$ within S&P | $0.214$ | $0.278$ | $0.138$ |
| $(|r_t|, \text{storm}_t)$ cross-domain | $0.052$ | $0.000$ | $0.001$ |

The within-domain positive control returns Gumbel $\lambda_U = 0.138$, well inside the Embrechts-McNeil-Straumann (2002) and Patton (2006) financial-tail-dependence range of $[0.10, 0.40]$. The estimator works; the cross-domain null is real.

## 5. Discussion

### 5.1 What the null does and does not say

It says: at *daily* frequency, in the *same calendar day*, with simple total-damage and absolute-return summaries, extreme financial-market days do **not** co-occur with extreme natural-disaster days more often than chance. The Gumbel and survival-Clayton MLEs both hitting their independence boundary make this an unusually clean result, not a marginal p-value.

It does **not** say:

- That there is no lagged effect — disaster-driven economic disruption typically plays out over weeks to quarters (Hsiang & Jina 2014), and lagged or low-frequency aggregation may yield different copula structure (planned: $\lambda_U$ at monthly, quarterly aggregation; this paper focuses on daily as the strongest test of "joint extreme on the same day").
- That there is no signal at narrower sub-aggregates — e.g., a hurricane day might co-occur with extreme insurance-sector returns (not S&P 500) or with extreme volatility ($\sigma_t$ not $|r_t|$). The headline is for the aggregate market.
- That natural-disaster impacts do not show up in *prices* at all — clearly Katrina and Harvey moved insurance and energy equities — only that they do not show up as same-day market-wide extreme moves.

### 5.2 What this implies for class #6

Universality class #6 ("tail copula") as initially stated in Layer 4 conflated two distinct claims:

| Sub-class | Statement | Status |
|---|---|---|
| #6a (mechanism-coupled) | Pairs sharing common drivers (within-finance / within-climate / within-network) have $\lambda_U \gg 0$. | Literature-supported; positive control here ($\lambda_U = 0.14$) consistent. |
| #6b (cross-mechanism) | Pairs whose only contact is the macro-economy still have $\lambda_U > 0$. | **Rejected** on this domain pair at daily frequency. |

The clean separation is itself an empirical advance: it tells the project's Layer 2 community-detection step that **upper tail dependence is not a universal property of heavy-tailed bivariates** — it requires a shared mechanism. This narrows the predictive content of class #6, which is the right direction for an empirical research programme.

### 5.3 Relationship to the broader Structural Isomorphism programme

Class #1 (SOC) recovers identical exponents on physics and finance because both members are individually generated by the same cascade mechanism. Class #6's claim is structurally stronger — it would require a shared coupling between two independently-generated series. The data here say no such coupling exists between US weather and US equity prices at the daily scale. Class #6 should therefore be re-stated as a **conditional** universality class (mechanism-coupled domains only), not a universal property of all heavy-tailed pairs.

### 5.4 Limitations

- Daily-frequency aggregation may hide intra-day or low-frequency couplings.
- Total-damage and absolute-return summaries are deliberately coarse; sector-level or vol-of-vol returns may yield different results.
- The 7,300-day sample, while large in absolute terms, has only $0.05 \times 0.05 \times 7300 \approx 18$ expected co-extreme pairs under independence at $q=0.95$, limiting power for very small $\lambda_U > 0$. Resolving $\lambda_U = 0.02$ vs $0.00$ would need an order-of-magnitude longer record.
- NOAA Storm Events covers only the US; cross-country pairs (e.g. global equity index versus global disaster damages) may differ.

## 6. Reproducibility

All inputs are publicly available. Pipeline source:

```
v4/validation/tail-copula/fetch_data.py     # NOAA download + daily aggregation
v4/scripts/a2_copula_tail_dependence.py     # all estimators, bootstrap, null, control
```

The pipeline runs in approximately 5 minutes wall-clock on a laptop after the one-time 290 MB NOAA download (cached under `v4/validation/tail-copula/data/`, gitignored). Output:

```
v4/validation/tail-copula/storm_daily_damage.csv   # daily-aggregated storm damage
v4/validation/tail-copula/results.json             # all numerical outputs
v4/validation/tail-copula/paper.md                 # this paper
```

## 7. References

- Embrechts, McNeil, Straumann (2002), "Correlation and Dependence in Risk Management: Properties and Pitfalls", Cambridge University Press.
- Patton, A. (2006), "Modelling Asymmetric Exchange Rate Dependence", International Economic Review 47(2): 527-556.
- Joe, H. (1997), "Multivariate Models and Dependence Concepts", Chapman & Hall.
- Salvadori, G., De Michele, C., Kottegoda, N. T., Rosso, R. (2007), "Extremes in Nature: An Approach Using Copulas", Springer.
- Hsiang, S., Jina, A. (2014), "The Causal Effect of Environmental Catastrophe on Long-Run Economic Growth", NBER Working Paper 20352.
- Bansal, R., Kiku, D., Ochoa, M. (2019), "Climate Change Risk", Working Paper.
- Battiston, S., Mandel, A., Monasterolo, I., Schütze, F., Visentin, G. (2017), "A Climate Stress-Test of the Financial System", Nature Climate Change 7: 283-288.
- Gopikrishnan et al. (1998), "Inverse cubic law for the distribution of stock price variations", European Physical Journal B 3, 139-140.
- NOAA NCEI Storm Events Database, https://www.ncei.noaa.gov/stormevents/.

## 8. Verdict

Universality class #6 **cross-mechanism variant (#6b)** is **REJECTED** on the financial-versus-natural-disaster pair at daily frequency: empirical $\hat\lambda_U(0.95) = 0.052$ lies inside the independence null, Gumbel and survival-Clayton MLE collapse to the independence boundary, and the conditional baseline lift is $1.04$. The within-mechanism variant (#6a, e.g. volatility clustering) is confirmed by positive control ($\lambda_U = 0.21$ at $q=0.95$, Gumbel $\lambda_U = 0.138$). The recommended Layer 4 update is to split class #6 into mechanism-coupled (supported) and cross-mechanism (rejected) sub-classes.
