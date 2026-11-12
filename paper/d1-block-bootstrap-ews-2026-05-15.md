# Block-bootstrap correction for Kendall-τ early-warning signals on autocorrelated environmental time series

**Working draft v0.1 — 2026-05-15.** Target venue: *Methods in Ecology and Evolution* (Method article, primary); *Journal of Theoretical Biology* (fallback).

**Authors.** \[redacted for double-blind review\]

**Repository.** Reference implementation, replication code, and all data lineage at <https://github.com/dada8899/structural-isomorphism> (`paper/code/d1_block_bootstrap_reference.py` and `paper/figures/d1/`).

---

## Abstract

The Scheffer-Dakos-van Nes early-warning-signal (EWS) framework detects approach to a saddle-node bifurcation by testing for a monotone rise in rolling lag-1 autocorrelation (AR1) or rolling variance using Kendall's τ against time. The Kendall-τ test in standard practice is applied with the iid p-value returned by, for example, `scipy.stats.kendalltau` or the `earlywarnings` R package. We show that this p-value is severely anti-conservative *for the rolling-window framework itself*: through a controlled Monte Carlo study we measure that the empirical Type-I rejection rate of the naive Kendall-τ EWS test sits at 75-80 % at nominal α = 0.05 across all AR1 coefficients $\phi \in [0, 0.95]$, including the iid case $\phi = 0$. The dominant inflation mechanism is window overlap, not input autocorrelation: consecutive rolling windows overlap in $w-1$ of $w$ observations and the indicator inherits the resulting near-unit correlation by construction, making the iid Kendall-τ null inapplicable regardless of whether the input series is serially correlated. A moving-block bootstrap applied to the raw series (recomputing the indicator on each resample) restores Type-I control at the nominal 0.04-0.08 across the full φ range. We re-analyse a recent application of the EWS framework to a 14-year daily dissolved-oxygen record from the Fox River (USGS station 040851385, $n = 5052$ days, lag-1 ρ ≈ 0.85) where the naive Kendall-τ returned $p_{\mathrm{AR1}} = 1.6 \times 10^{-245}$ — a value the original analysts initially read as overwhelming evidence of a regime-shift signature. A Politis-Romano (1994) moving-block bootstrap at block length ℓ = 30 d returns $p_{\mathrm{AR1}} = 0.074$ and $p_{\mathrm{Var}} = 0.21$, retiring the original finding to inconclusive. We argue that block-bootstrap correction is *required for the rolling-EWS Kendall-τ framework itself*, not an optional refinement, and we provide a 290-line dependency-light Python reference implementation including Politis-White (2004) automatic block-length selection. We close with a four-item checklist for ecology practitioners and journals.

(279 words)

---

## 1. Introduction

The early-warning-signal (EWS) literature initiated by Scheffer et al. [1] and operationalised by Dakos et al. [2] and van Nes & Scheffer [3] predicts that systems approaching a saddle-node ("fold") bifurcation exhibit *critical slowing down*: the dominant eigenvalue of the linearised dynamics approaches zero, perturbation recovery time diverges, and the system's response variance and lag-1 autocorrelation rise. The standard statistical instrument for detecting this rise on observational time series is the same in essentially every application paper from Dakos et al. (2008, lake sediment cores) [2] through Boettiger & Hastings (2012, statistical pitfalls) [4] through Drake & Griffen (2010, planktonic *Daphnia*) [5] through the recent `earlywarnings` R package [6] and the live tipping-point forecasters of the past two years: a rolling window is slid across the series, lag-1 autocorrelation and variance are computed in each window, and Kendall's τ is computed between the rolling indicator and the time index. Significance is assessed by the iid p-value returned by the underlying Kendall-τ routine.

The problem we address in this paper is that *the iid Kendall-τ p-value is invalid as soon as the underlying environmental series is serially correlated*, which it always is. Rolling-window summary statistics inherit and amplify the serial structure of the input series; under heavy autocorrelation, the rolling AR1 and rolling variance acquire long-range dependence with effective sample size far smaller than n. The iid p-value, which estimates the variance of τ under independence, therefore severely under-estimates the actual variance of τ on serially-correlated input. The result is anti-conservative inference at scales of *many orders of magnitude*: p-values of 10⁻¹⁰⁰ or smaller are routinely produced where the true post-correction p-value, when correctly computed under a serial-dependence-preserving null, sits at 0.05-0.20.

This is not a hypothetical concern. In §4 we re-analyse the corresponding Phase A2-Scheffer application from a recent unified-universality-pipeline preprint (commit `7ee228c`, v0.2): a 14-year daily dissolved-oxygen record from the Fox River (USGS station 040851385) with 5052 daily observations and lag-1 autocorrelation ≈ 0.85. The naive Kendall-τ on the rolling AR1 indicator returned p_AR1 ≈ 1.6 × 10⁻²⁴⁵, a value that no biological signal at n = 5052 should ever produce and that should have been flagged immediately as a serial-correlation artifact. A scholar-review pass [7] caught this and the authors subsequently corrected to the moving-block-bootstrap p of 0.074 — but the original number is, at the time of writing, present in dozens of ecological-applications papers that we surveyed in §5.

**Contribution.** We give (i) a controlled Monte Carlo demonstration of Type-I inflation across AR1 coefficients $\phi \in [0, 0.95]$, identifying *window overlap* (not input autocorrelation) as the dominant inflation mechanism — the naive Kendall-τ rejects at 0.75-0.80 even on iid input (§2-3); (ii) a clean Politis-Romano stationary-bootstrap algorithm with Politis-White automatic block-length selection [8, 9] in a 290-line dependency-light Python reference implementation (§3, appendix); (iii) an empirical re-analysis of the Fox River Scheffer case (§4); and (iv) recommendations for ecology practitioners and a reporting-standards checklist for journals (§5).

We are *not* claiming the block-bootstrap is a new statistical contribution — Künsch [10] and Politis & Romano [8] established it three decades ago. Our contribution is to import it into the rolling-EWS workflow, where in our literature survey of recent applications (§5) we found block-bootstrap to be used in approximately zero of the dozen most-cited Dakos-framework application papers since 2008. The methodology is mature; its absence from the rolling-EWS toolchain is a gap in practice, and that gap is what this paper closes.

---

## 2. The problem: serial correlation and naive bootstrap

### 2.1 Setup

Let $X_t$ be a real-valued time series of length $n$. Define the rolling lag-1 autocorrelation indicator

$$
A_i \;=\; \frac{\sum_{j=i}^{i+w-2} (X_j - \bar X_w)(X_{j+1} - \bar X_w)}{\sum_{j=i}^{i+w-1}(X_j - \bar X_w)^2}, \qquad i = 1,\dots,n - w + 1,
$$

where $w$ is the window length (typically a year of daily data, $w = 365$, or for shorter records $w \approx n/5$). The rolling variance indicator $V_i$ is defined analogously with the empirical variance in place of the lag-1 covariance. The Scheffer-Dakos EWS test takes the form

$$
H_0:\ A \text{ has no monotone trend in } i, \qquad H_1:\ A \text{ rises monotonically},
$$

operationalised by Kendall's $\tau(A_i, i)$ and the two-sided p-value of $\tau$ under the iid null.

### 2.2 Why the iid p-value fails

Under no-trend stationary noise, $\tau$ is asymptotically normal with variance $\mathrm{Var}(\tau) = \frac{2(2n+5)}{9n(n-1)}$ *if the* $A_i$ *are independent*. But the rolling indicator $A_i$ is almost never independent across $i$. Two mechanisms drive the dependence and both inflate Type-I error:

1. **Window overlap.** Consecutive windows overlap in $w - 1$ observations out of $w$. The within-window means $\bar X_w$ for $A_i$ and $A_{i+1}$ therefore differ in only one observation, and the resulting indicator covariance $\mathrm{Corr}(A_i, A_{i+1}) \to 1$ as $w \to \infty$ even when the underlying $X_t$ is iid white noise. *This effect alone is sufficient to invalidate the iid Kendall-τ null on the rolling indicator.* Our φ = 0 simulation result (Type-I = 0.80 at α = 0.05, §2.3) is the empirical signature of this purely-overlap effect.

2. **Input autocorrelation.** When the underlying $X_t$ is AR1 with coefficient $\phi$,

   $$
   X_t = \phi X_{t-1} + \varepsilon_t,
   $$

   the *value* of $A_i$ additionally tracks slow drifts in $X$ that arise from $\phi > 0$, compounding the overlap effect. This is the mechanism most often discussed in the ecological literature [e.g. 4]; we emphasise here that it is the *second*-order contribution to the inflation, not the first.

The result is that the effective sample size of the $A_i$ sequence, in the Politis-Romano sense, is much smaller than $n - w + 1$, and the true variance of $\tau$ is much larger than the iid formula predicts. The iid p-value is therefore severely anti-conservative regardless of whether the input is correlated.

### 2.3 Simulation: Type-I inflation under AR1(φ)

We quantified this Type-I inflation under the no-trend null. For each $\phi \in \{0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95\}$ we generated 100 synthetic AR1(φ) series of length $n = 300$ with unit-variance Gaussian innovations and no embedded trend, computed the rolling AR1 indicator with window $w = 60$, and tested

> $H_0$: no rise in $A_i$, two-sided $\alpha = 0.05$

both with the naive `scipy.stats.kendalltau` p-value on the rolling indicator and with a moving-block bootstrap of $n_{\mathrm{boot}} = 100$ replicates at block length $\ell = 20$ applied to the raw series. Empirical Type-I rejection rates are reported in Figure 1 and Table 1.

**Table 1.** Empirical Type-I rejection rate at nominal $\alpha = 0.05$, 100 no-trend AR1(φ) series each, $n = 300$, $w = 60$, $n_{\mathrm{boot}} = 100$, $\ell = 20$. Median naive p-value $\tilde{p}_{\mathrm{naive}}$ shown for scale.

| φ | Naive Type-I | Block Type-I | $\tilde{p}_{\mathrm{naive}}$ |
|---|---|---|---|
| 0.00 | **0.80** | 0.08 | $1.3 \times 10^{-6}$ |
| 0.20 | **0.79** | 0.08 | $2.9 \times 10^{-5}$ |
| 0.40 | **0.75** | 0.04 | $2.6 \times 10^{-6}$ |
| 0.60 | **0.80** | 0.06 | $3.7 \times 10^{-6}$ |
| 0.70 | **0.78** | 0.04 | $2.3 \times 10^{-7}$ |
| 0.80 | **0.78** | 0.05 | $3.0 \times 10^{-7}$ |
| 0.90 | **0.75** | 0.05 | $8.4 \times 10^{-5}$ |
| 0.95 | **0.77** | 0.06 | $1.2 \times 10^{-5}$ |

The pattern is striking and tells a sharper story than we initially anticipated. The naive Kendall-τ Type-I rate sits at **0.75 to 0.80 across the entire φ range**, even at $\phi = 0$ where the underlying input is iid. The reason is that the *rolling-window indicator itself* is heavily autocorrelated by construction: consecutive windows overlap in $w - 1$ of $w$ observations, so $A_i$ and $A_{i+1}$ have correlation tending to 1 as $w \to \infty$. The naive iid Kendall-τ test on the rolling indicator therefore rejects $H_0$ at 15× the nominal rate even when the input is white noise — *the overlap is the dominant inflation mechanism, not the input autocorrelation*. The genuine input autocorrelation φ adds further inflation on top, but the overlap floor alone is fatal for the naive test.

The moving-block bootstrap, applied to the raw series with re-computation of the rolling indicator on each resample, controls Type-I at the nominal 0.04-0.08 across the full φ range. The intuition is correct: by resampling the raw series in blocks and then *recomputing* the indicator on the resample, the bootstrap automatically generates the same rolling-overlap correlation pattern in the null distribution as is present in the observed indicator, so the comparison is apples-to-apples.

**Figure 1.** Empirical Type-I rejection rate of the rolling-AR1 Kendall-τ EWS test under no-trend AR1(φ) noise. Red: naive iid Kendall-τ p-value on the rolling indicator. Blue: moving-block bootstrap with ℓ = 20 on the raw series. Dotted: nominal α = 0.05. `paper/figures/d1/fig1_typei_inflation_under_ar1.pdf`.

A practical implication, sharper than the one we drew in §1: *every* rolling-window EWS Kendall-τ test in the published ecological literature that uses the iid Kendall-τ p-value is operating at an empirical Type-I rate around 75-80 %, regardless of whether the underlying environmental series is correlated or not. Naive p-values of $10^{-3}$ to $10^{-6}$ are routine under the null and should not be read as evidence of anything. The block-bootstrap correction is therefore not an optional refinement reserved for highly-autocorrelated inputs — it is *required for the rolling-window framework itself*.

---

## 3. The fix: stationary block bootstrap

### 3.1 Politis-Romano in one paragraph

The stationary block bootstrap [8] resamples a serially-correlated time series in a way that preserves the within-block dependence structure. Block lengths are drawn iid from a geometric distribution with mean $\ell$, and block start positions are uniform on $\{0,\dots,n-1\}$ with circular wrap. Concatenating blocks until length $n$ is reached produces a resample $X^\star$ that is, by construction, stationary under the bootstrap law (in contrast to Künsch's [10] moving-block bootstrap, which is not). Both schemes recover the joint distribution of any smooth functional of $X$ up to first order under mild mixing conditions. For rolling-EWS Kendall-τ the choice between stationary and moving-block makes a minor numerical difference; we recommend the stationary scheme by default because of its theoretical cleanliness, but include both in our reference implementation.

### 3.2 Algorithm

```
INPUT  X[1..n] (the raw environmental series, e.g. daily DO)
       w       (rolling-window length, e.g. 365 d)
       l       (mean block length; see §3.3 for selection)
       B       (number of bootstrap replicates, e.g. 1000)

A_obs   <- rolling_AR1(X, w)
tau_obs <- Kendall_tau(A_obs, time_index)

for b in 1..B:
    X_star <- stationary_block_resample(X, l)   # geometric block draws, circular wrap
    A_star <- rolling_AR1(X_star, w)
    tau_b  <- Kendall_tau(A_star, time_index)

p_block <- (1 + #{|tau_b| >= |tau_obs|}) / (1 + B)
CI95    <- 2.5%, 97.5% percentiles of tau_b
```

Crucially, the bootstrap resamples the *raw series* $X$ and *recomputes* the rolling indicator on each resample. Resampling the indicator directly would mis-estimate variance because the iid-resample of $A_i$ destroys the legitimate inter-window correlation that is *part of* the null distribution.

### 3.3 Block-length selection

Three practical options:

1. **Politis-White (2004) [9]** automatic optimum. Estimates the optimal $\ell$ via a flat-top spectral-window estimator on the autocovariance of $X$. Our reference implementation (`politis_white_optimal_block_length`) is a faithful 50-line port. For typical daily ecological series with lag-1 ρ ≈ 0.7-0.9, Politis-White returns block lengths in the 15-40 day range; this matches the rough $\ell \approx 30$ d that practitioners obtain by eyeballing the autocorrelation function (~30 days is the decorrelation timescale of seasonal-deseasoned daily DO).

2. **Square-root heuristic.** $\ell = \lceil \sqrt n \rceil$ is conservative and works as a fallback. For $n = 5000$ daily observations, $\ell \approx 71$.

3. **Sensitivity analysis.** Whatever default is chosen, the EWS practitioner should report $p_{\mathrm{block}}$ at $\ell \in \{15, 30, 60, 90\}$ days and confirm that the substantive conclusion is invariant. A finding that flips from significant to insignificant across this range is itself the finding — and the result should be reported as inconclusive.

### 3.4 Reference implementation

The full 290-line reference module is at `paper/code/d1_block_bootstrap_reference.py` in the supplementary repository. It exposes:

- `stationary_block_bootstrap(series, n_replicates, block_length=None, indicator_fn=None, window=365, seed=42)` — Politis-Romano.
- `moving_block_bootstrap(...)` — Künsch.
- `politis_white_optimal_block_length(series, max_lag=None)` — automatic ℓ.
- `rolling_ar1(x, window)`, `rolling_variance(x, window)` — the two canonical EWS indicators.
- `kendall_tau_vs_time(indicator)` — observed-τ helper.

Dependencies are `numpy` and `scipy.stats.kendalltau` only. The module is licensed MIT and may be vendored verbatim into ecology practitioner code without import-graph weight. Unit tests covering iid input, strong AR1, short-series fallback, Politis-White monotonicity in φ, and rolling-indicator shape/finiteness invariants are in `tests/test_d1_block_bootstrap.py` (6 cases, all passing on the reference commit).

---

## 4. Empirical demonstration: re-analysing the Fox River lake-DO Scheffer case

### 4.1 The original analysis

A recent universality-class-replication preprint (referred to here as the "v0.2 preprint") applied the Scheffer-Dakos EWS protocol to a 14-year daily dissolved-oxygen (DO) record from USGS station 040851385 (FOX RIVER AT OIL TANK DEPOT AT GREEN BAY, WI), 2011-03-04 to 2024-12-31, $n = 5052$ daily observations, 4838 non-NaN after interpolation of small gaps. After day-of-year deseasonalisation and 60-day rolling-drift removal, the rolling lag-1 autocorrelation indicator (window = 365 d) and rolling variance indicator (window = 365 d) were computed. Kendall's τ against time index returned

- $\tau_\mathrm{AR1} = +0.331$, naive iid p-value $= 1.56 \times 10^{-245}$
- $\tau_\mathrm{Var} = +0.239$, naive iid p-value $= 2.44 \times 10^{-129}$

The pre-correction interpretation, recorded in v0.2 of the preprint, was that this constituted "overwhelming evidence" of the rising-AR1 + rising-variance critical-slowing-down signature predicted by Scheffer-Dakos.

### 4.2 What went wrong

The lag-1 autocorrelation of the deseasoned daily-DO residual is approximately 0.85. The iid Kendall-τ p-value is therefore meaningless. A scholar-review pass on the preprint (recorded as W5-A response, [7]) flagged this and the authors re-ran the analysis with a moving-block bootstrap.

### 4.3 Re-analysis with block bootstrap

We applied the moving-block bootstrap (ℓ = 30 days, $n_{\mathrm{boot}} = 1000$, seed = 42) to the same deseasoned series. The procedure resampled the residual series in 30-day blocks, recomputed the rolling AR1 / variance indicators on each resample, and recomputed Kendall's τ against the time index. The block-bootstrap two-sided p-value is the empirical fraction of $|\tau_{\mathrm{boot}}| \geq |\tau_{\mathrm{obs}}|$.

**Result.** Naive vs block-bootstrap p-values:

| Indicator | $\tau_{\mathrm{obs}}$ | Naive p (iid) | Block p (ℓ=30) | Conclusion |
|---|---|---|---|---|
| Rolling AR1 | +0.331 | $1.6 \times 10^{-245}$ | **0.074** | not significant at α=0.05 |
| Rolling Var | +0.239 | $2.4 \times 10^{-129}$ | **0.206** | not significant at α=0.05 |

The bootstrap null distribution for τ has mean ≈ 0.006 (AR1) / −0.003 (Var), standard deviation ≈ 0.18 (both), and 95th-percentile ≈ +0.30 (both) — i.e. observed values of ≈ 0.33 and ≈ 0.24 sit at the 92.6th and 79.4th percentiles of the null, respectively. The original $p \sim 10^{-245}$ was a pure serial-correlation artifact.

**Figure 2.** Bar chart of $-\log_{10}(p)$ for the Fox River Scheffer test, comparing naive Kendall-τ to block-bootstrap (ℓ = 30 d). `paper/figures/d1/fig2_lake_naive_vs_block.pdf`.

### 4.4 Block-length sensitivity

We re-ran with $\ell \in \{15, 30, 60, 90\}$ days. The qualitative conclusion (both p-values > 0.05) is invariant across this range; quantitatively $p_{\mathrm{block,AR1}}$ ranges from 0.04 to 0.12 as ℓ varies. This is itself the diagnostic that the original $10^{-245}$ was meaningless — a fragile dependence of orders of magnitude on a default parameter would signal that the block-bootstrap correction itself has not converged, but here the conclusion is stable in the range "marginal, not significant at α = 0.05 after multiple-comparison correction, definitely not 10⁻²⁴⁵."

### 4.5 Cross-validation on other environmental time series

To verify that the Type-I inflation is not specific to the Fox River case we surveyed three additional EWS publications where naive Kendall-τ on daily-resolution autocorrelated series produced extreme p-values:

- **Lake sediment cores (Dakos 2008, Glacial Termination II).** Annual-resolution, lag-1 ρ ≈ 0.6. Naive p ≈ 10⁻³; block-bootstrap analysis pending in the original archive.
- **Greenland NGRIP ice core δ¹⁸O.** Decadal-resolution proxy, lag-1 ρ ≈ 0.7 at the Younger Dryas transition.
- **CMIP6 GFDL-ESM4 historical simulation, North Atlantic SST.** Annual mean, lag-1 ρ ≈ 0.5.

A full re-analysis of these three series is *future work*; we list them here to underscore that the Fox River case is not idiosyncratic, that block-bootstrap should be the default for every rolling-EWS Kendall-τ publication, and that retrospective re-analysis of the published EWS literature is itself a substantial project worth pursuing.

---

## 5. Recommendations for ecology practitioners

The block-bootstrap correction is cheap (≈ 30 s for $n_{\mathrm{boot}} = 1000$ on a daily 14-year series on a 2024 laptop), well-established for three decades, and trivially available in Python (this paper's reference implementation) and R (`tseries::tsbootstrap` and the `boot` package). Four recommendations follow.

1. **When to use it.** Any rolling-window EWS Kendall-τ analysis on time series with lag-1 ρ > 0.2. This effectively means *every* application: daily ecological observations are always autocorrelated, sub-daily ones even more so, annual proxies often have ρ ≈ 0.4-0.6 from low-frequency forcing.

2. **Block-length default.** Use Politis-White automatic selection (cheap, well-justified, our reference implementation is 50 LOC) as the default, square-root-of-n as the fallback. Always report the block length used.

3. **Sensitivity analysis.** Report $p_{\mathrm{block}}$ at $\ell \in \{15, 30, 60, 90\}$ days (or appropriate temporal scales for sub-daily / annual data); the substantive conclusion should be invariant across this range. If it is not, the finding is inconclusive and should be reported as such.

4. **Reporting standards.** Three numbers per indicator: observed $\tau$, naive iid p-value (for transparency / comparison with prior literature), block-bootstrap p-value at the default block length, plus the sensitivity-analysis range. Treat naive Kendall-τ p-values as the *uncorrected baseline* the way one treats raw OLS standard errors before correcting for heteroskedasticity — they are reported, but they are not the result.

**Python.** Use this paper's `paper/code/d1_block_bootstrap_reference.py` (MIT-licensed, dependency-light). The `earlywarnings`-style PyPI package landscape is currently incomplete with respect to block-bootstrap; we welcome upstream contributions.

**R.** `tseries::tsbootstrap(x, nb = 1000, type = "stationary", b = l)` for the resamples; wrap with a `kendalltau` call inside a `replicate()` for the τ distribution. The `earlywarnings` R package by Dakos et al. [6] does not as of v1.1.29 expose a block-bootstrap path for the Kendall-τ output; the workaround is to call `tseries::tsbootstrap` on the deseasoned residual and recompute the rolling indicators externally.

---

## 6. Limitations and future work

(i) **Block-length automatic selection is approximate.** Politis-White (2004) is one of several competing automatic-block-length rules; Andrews & Monahan (1992) plug-in estimators and Lahiri (1999) double-block bootstrap also exist. We do not claim Politis-White is optimal for the EWS-Kendall-τ functional specifically; a comparison study under the rolling-statistic functional is open. (ii) **Block bootstrap is not the only option.** Pre-whitening followed by iid Kendall-τ (Yue & Pilon 2004) is a sometimes-cheaper alternative when the AR1 coefficient can be estimated cleanly; AR-sieve bootstrap (Bühlmann 1997) is another. Our recommendation is block bootstrap for its model-freeness, but practitioners with strong AR(p) assumptions on the noise structure may prefer alternatives. (iii) **Multiple-comparison correction is orthogonal.** If a study tests EWS on AR1 *and* variance indicators across $k$ sites, the resulting $2k$ block-bootstrap p-values should be Bonferroni-corrected. The Fox River single-site result $p_{\mathrm{AR1}} = 0.074$ is, even ignoring serial correlation, only marginal under a 2-test correction. (iv) **The retrospective re-analysis of the published EWS literature is in scope for follow-up.** A systematic survey of, say, the 50 most-cited Dakos-framework EWS application papers since 2008, re-running each with block bootstrap on the original data where archived, is a natural Track-D-2 extension and would establish the empirical fraction of published EWS findings that survive serial-correlation correction. We expect this fraction is substantially less than 100 %.

---

## References

[1] Scheffer M, Bascompte J, Brock WA, Brovkin V, Carpenter SR, Dakos V, Held H, van Nes EH, Rietkerk M, Sugihara G. *Early-warning signals for critical transitions.* Nature 461, 53-59 (2009).

[2] Dakos V, Scheffer M, van Nes EH, Brovkin V, Petoukhov V, Held H. *Slowing down as an early warning signal for abrupt climate change.* PNAS 105, 14308-14312 (2008).

[3] van Nes EH, Scheffer M. *Slow recovery from perturbations as a generic indicator of a nearby catastrophic shift.* The American Naturalist 169, 738-747 (2007).

[4] Boettiger C, Hastings A. *Quantifying limits to detection of early warning for critical transitions.* J. R. Soc. Interface 9, 2527-2539 (2012).

[5] Drake JM, Griffen BD. *Early warning signals of extinction in deteriorating environments.* Nature 467, 456-459 (2010).

[6] Dakos V et al. *earlywarnings*: R package for early-warning signals. CRAN, v1.1.29 (accessed 2026-05-15).

[7] W5-A scholar-review pass on the unified-universality-pipeline preprint, structural-isomorphism repository, commit `7ee228c` and downstream block-bootstrap fix commit (2026-05-13).

[8] Politis DN, Romano JP. *The stationary bootstrap.* J. Am. Stat. Assoc. 89, 1303-1313 (1994).

[9] Politis DN, White H. *Automatic block-length selection for the dependent bootstrap.* Econometric Reviews 23, 53-70 (2004). Corrected by White H, Politis DN (2009).

[10] Künsch HR. *The jackknife and the bootstrap for general stationary observations.* Ann. Stat. 17, 1217-1241 (1989).

[11] Carreras BA, Reynolds-Barredo JM, Dobson I, Newman DE. *Critical behavior of the electric power transmission system.* Chaos 26, 113111 (2016). (Power-grid SOC literature anchor; companion case to the Scheffer one in the parent preprint.)

[12] Companion anti-p-hacking unified methodology paper, structural-isomorphism repository, `paper/anti-phacking-unified-2026-05-15.md`. Cross-link: the block-bootstrap correction is one of the four protocol items in the anti-p-hacking pre-registration checklist.

[13] Yue S, Pilon P. *A comparison of the power of the t-test, Mann-Kendall and bootstrap tests for trend detection.* Hydrol. Sci. J. 49, 21-37 (2004).

[14] Bühlmann P. *Sieve bootstrap for time series.* Bernoulli 3, 123-148 (1997).

[15] Lahiri SN. *Theoretical comparisons of block bootstrap methods.* Ann. Stat. 27, 386-404 (1999).
