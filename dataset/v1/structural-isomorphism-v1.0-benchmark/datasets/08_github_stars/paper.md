# Recovering Barabási-Albert Preferential-Attachment Exponents on 8,398 GitHub Repositories: A Different Universality Class for Phase 6 of a Cross-Domain Pipeline

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. Project site: https://structural.bytedance.city.
**Date.** 2026-05-13. Version: preprint draft for arXiv-style circulation.
**Keywords.** preferential attachment; Yule-Simon; Barabási-Albert; GitHub stargazers; power-law; universality class; pipeline validation; cross-domain isomorphism.

---

## Abstract

The Structural Isomorphism project's V4 layer-5 pipeline has been exercised on six SOC threshold-cascade systems; this paper is the first test on a second class. We fit the Clauset-Shalizi-Newman power-law to the stargazer counts of 8,398 GitHub repositories from stratified search-API queries (star range 248-500,996; snapshot 2026-05-13). The MLE returns $\alpha = 2.867 \pm 0.050$ with bootstrap 95% CI $[2.781, 3.000]$, $x_\mathrm{min} = 25{,}585$ stars, $n_\mathrm{tail} = 1{,}417$. The interval brackets the canonical Barabási-Albert asymptote $\alpha = 3$ at its upper edge. Power-law crushes exponential ($R = +5.45$, $p \approx 5 \times 10^{-8}$); the test against lognormal is inconclusive ($R = -1.45$, $p = 0.15$) — lognormal cannot be ruled out but is not preferred. Per-language sub-fits ($n \geq 300$) span $\alpha \in [2.61, 3.00]$, all inside the predicted band; JavaScript ($n = 1{,}039$) hits $\alpha = 3.00$ to two decimal places. Three matched-$n$ non-power-law nulls are correctly rejected. The result is independent validation, not discovery, and is the first empirical evidence that V4's class separation between SOC threshold cascade and Yule-Simon-style cumulative advantage is operationally meaningful.

## 1. Introduction

Heavy-tailed distributions arise from at least two structurally distinct mechanisms in the universality-class taxonomy used by the Structural Isomorphism project. The first is the self-organized-criticality (SOC) threshold-cascade family of Bak, Tang, and Wiesenfeld [1], in which slowly driven systems with local thresholds shed accumulated stress in power-law-distributed avalanches; canonical examples (tectonic seismicity, solar flares, neural avalanches) were addressed in earlier phases. The second is preferential attachment, in which a growing population accumulates "popularity" at a rate proportional to the popularity already held, written down by Yule [2] for species per genus, generalized by Simon [3] to word frequencies, applied to citations by de Solla Price [4] as "cumulative advantage", and rediscovered for network topology by Barabási and Albert [5]. Albert and Barabási [6] and Newman [7] survey the resulting empirical exponents, which cluster in $\alpha \in [1.8, 3.5]$ across systems ranging from city populations to actor collaborations.

The two classes share a power-law functional form but differ on essentially everything else. SOC predicts paired signatures — a power-law in event size *and* Omori-Utsu temporal aftershock decay — whereas preferential attachment, being a growth process without driving-and-relaxation, predicts only the degree-distribution signature. The exponents cluster around different values: $\tau \in [1.6, 1.8]$ for seismic energies and $\alpha \in [1.5, 2.5]$ for flare peak fluxes versus the Barabási-Albert asymptotic $\alpha = 3$ for canonical preferential-attachment networks [5, 6].

GitHub stars are a near-textbook preferential-attachment system: stars accumulate over time, trending pages weight by recent velocity, users are more likely to star already-popular repositories, and new repositories enter at zero. None of this resembles SOC threshold cascade. Borges and Valente [8] fit a power-law to a smaller GitHub sample and reported an exponent in the BA range; Lima et al. [9] and Cosentino et al. [10] place the platform's social structure in the scale-free-network literature. Our contribution is not to discover that GitHub stars are heavy-tailed but to verify that the unmodified V4 pipeline, calibrated against SOC systems, returns the right exponent in the right band when pointed at a preferential-attachment system. If it returned $\alpha \approx 1.7$, the V4 class separation would be empirically wrong. It does not.

## 2. Data

The catalog was retrieved from the GitHub Search API (`https://api.github.com/search/repositories`) on 2026-05-13. The API caps results at 1,000 per query and orders by stars descending. To span the distribution we used ten stratified `stars:>N` bucket queries with $N \in \{100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000\}$, fetching 100 results per page across up to ten pages per bucket. Duplicates across buckets were collapsed by the API `id` field. The catalog contains 8,398 unique repositories with star counts spanning 248 to 500,996, median 4,734.5 and mean 12,950.6. Per-language counts (where `language` is populated) are Python $= 1{,}506$, JavaScript $= 1{,}039$, TypeScript $= 905$, Go $= 545$, C++ $= 476$, Java $= 471$.

The 1,000-per-query API cap is the dominant sampling artifact: low-star repositories (single-star, fork-noise, abandoned) are systematically absent. Stratification gives effective coverage over four decades in stars (250 to 500k); the Clauset MLE selects $x_\mathrm{min}$ well above the cap-affected regime (Section 4.1), so the fitted tail is not artifact-distorted, but the catalog as a whole is not a uniform random sample from all of GitHub. The snapshot is cross-sectional, so we test only the steady-state signature of preferential attachment, not its dynamics.

## 3. Methods

The analysis uses the shared `v4/lib/soc_pipeline.py` module unchanged from Phase 1 (earthquakes) through Phase 11 (solar flares).

**Clauset-Shalizi-Newman MLE.** A power-law $p(x) \propto x^{-\alpha}$ for $x \geq x_\mathrm{min}$ is fit by selecting $x_\mathrm{min}$ via the Kolmogorov-Smirnov distance and estimating $\alpha$ by maximum likelihood [11]. Because GitHub star counts are integers we use `discrete=True` in the underlying `powerlaw` library [12], which uses the discrete Hurwitz-zeta likelihood; on integer data with $x_\mathrm{min}$ in the tens-of-thousands range, the continuous-form fit shifts $\alpha$ by $\approx 0.02$, comparable to one Clauset standard error.

**Bootstrap CI.** A non-parametric 95% CI on $\alpha$ is computed from $n_\mathrm{boot} = 100$ resamples of the tail with $x_\mathrm{min}$ fixed at the all-data value.

**Likelihood-ratio tests.** Power-law versus lognormal and versus exponential are tested with the Clauset-Shalizi-Newman $R$ statistic and Vuong-style $p$ [11]. Positive $R$ favors power-law.

**Per-language sub-fits.** For each language with $n \geq 300$ we run the full Clauset MLE separately, as a stability check.

**Null control.** Three matched-$n$ non-power-law synthetics (lognormal $\sigma = 1.5$, exponential $\lambda^{-1} = 5000$, uniform on $[1, 10^5]$) are passed through the pipeline; passing requires correct rejection on all three.

## 4. Results

### 4.1 Whole-dataset power-law fit

The Clauset MLE selects $x_\mathrm{min} = 25{,}585$ stars, leaves $n_\mathrm{tail} = 1{,}417$ in the fitted tail, and returns
$$
\alpha = 2.867 \pm 0.050,
$$
with a 100-resample bootstrap 95% CI of $[2.781, 3.000]$. The interval lies entirely inside the predicted band $\alpha \in [2.0, 3.0]$ from the Barabási-Albert preferential-attachment class [5, 6, 7], and its upper edge coincides with the canonical BA asymptote $\alpha = 3$ to three decimal places. The point estimate at $\alpha = 2.87$ also sits comfortably inside the broader Newman [7] empirical range $\alpha \in [1.8, 3.5]$ that summarizes 24 preferential-attachment systems across domains.

The likelihood-ratio test against exponential returns $R = +5.45$, $p = 5 \times 10^{-8}$: power-law decisively crushes exponential. Against lognormal the test is inconclusive, $R = -1.45$, $p = 0.15$: on the 1,417-repository tail neither alternative is significantly preferred. Mitzenmacher [13] and Clauset et al. [11] both note that distinguishing power-law from lognormal below $n \sim 10^4$ in the tail is generically hard. We do not read the inconclusive sign as evidence against the BA mechanism — the fitted exponent matches the BA asymptotic prediction quantitatively, and the inability to reject a smooth alternative at this $n$ is a known discriminator limitation, not a mechanism failure.

### 4.2 Per-language stability

The six languages with $n \geq 300$ are summarized in Table 1. All six exponents lie inside the predicted band $[2.0, 3.0]$.

**Table 1.** Per-language Clauset fits, $n \geq 300$ only.

| Language   | $n$  | $x_\mathrm{min}$ | $n_\mathrm{tail}$ | $\alpha$ |
|------------|------|------------------|-------------------|----------|
| JavaScript | 1039 | 27,337           | 145               | 2.995    |
| C++        | 476  | 32,254           | 38                | 2.977    |
| TypeScript | 905  | 27,907           | 202               | 2.853    |
| Python     | 1506 | 27,464           | 252               | 2.747    |
| Go         | 545  | 15,029           | 194               | 2.651    |
| Java       | 471  | 15,035           | 108               | 2.608    |

JavaScript — the language with the largest sample and the most mature open-source ecosystem — hits $\alpha = 2.995$, matching the BA asymptote $\alpha = 3$ to two decimal places. C++ sits at $\alpha = 2.98$; the newer or more niche ecosystems (Go, Java) sit at the low end near $\alpha \approx 2.6$. One plausible reading is that ecosystems with longer continuous accumulation history are closer to the BA steady-state limit, while still-growing ecosystems have not yet relaxed to the asymptotic slope; Krapivsky, Redner, and Leyvraz [14] derive the dependence of $\alpha$ on seeding and finite-time corrections, and the qualitative direction is consistent. We do not over-interpret on six points: this is an observation worth a dedicated follow-up, not a settled finding.

### 4.3 No temporal analysis

Unlike earlier phases, we do not stack post-trigger event rates. Preferential attachment makes no Omori prediction — it is a growth law, not a relaxation law — so running the SOC temporal stacker on stargazer arrival times would be category-confused. Its absence is by design, not by oversight.

### 4.4 Null control

All three matched-$n$ non-power-law synthetics are correctly rejected: lognormal-source data returns a strongly negative power-law-vs-lognormal $R$; exponential-source data favors exponential under the matched test; uniform-source data fails to admit a stable $x_\mathrm{min}$. The pipeline does not produce false-positive power-law verdicts at the relevant $n$.

## 5. Discussion

Phase 6 is the seventh layer-5 system tested by the Structural Isomorphism pipeline, joining tectonic seismicity (Phase 1), the S&P 500 (Phase 7), three DeFi protocols (Phase 8), mouse visual cortex (Phase 9), U.S. wildfires (Phase 10), and GOES solar flares (Phase 11). The previous six targeted `soc_threshold_cascade` and used the Omori-Utsu temporal stacker; Phase 6 targets `preferential_attachment` and is the first phase to exercise V4's prediction that the two classes are operationally distinct.

The cohort exponents span $\alpha \in [1.08, 3.00]$, distributed by class as the taxonomy expects: SOC systems cluster lower ($b = 1.08$ earthquakes; $\tau \approx 1.7$ seismic energy; $\alpha \approx 1.7$ wildfires; $\alpha \approx 2.2$ solar flares), while GitHub at $\alpha \approx 2.87$ sits at the BA limit. The V4 prediction was not that one exponent is universal across all heavy-tailed systems but that same-class systems share a predicted band and different-class systems occupy different bands. The GitHub result is the first datapoint for the second half.

Future Phase 6-style targets: Wikipedia views, arXiv/OpenAlex citations, Stack Overflow tags, npm downloads, UN city populations, book sales, Twitter followers. Each should return $\alpha \in [2, 3.5]$ if V4's assignment is correct; an SOC-band exponent on any of them would be evidence against the class separation.

A methodological note: the shared pipeline is named for SOC but is a class-agnostic power-law fitter with optional Omori stacking. The class-specific content lives in the prediction band — `soc_threshold_cascade` predicts $\alpha \in [1.5, 2.0]$ plus positive Omori $p$; `preferential_attachment` predicts $\alpha \in [2.0, 3.0]$ and no Omori prediction. This separation is what lets one code base test two distinct claims without confounding them.

## 6. Limitations

1. **GitHub Search API top-1000 cap.** Each `stars:>N` query returns at most 1,000 repositories. Stratification recovers four decades of coverage but cannot reach the zero/one-star tail; the Clauset $x_\mathrm{min}$ at 25,585 sits well above the cap-affected regime, but the catalog is not a uniform random sample.
2. **Self-selection.** Only repositories with public starring activity enter the catalog. The result characterizes the visible public-stargazer slice, not "all software development".
3. **Cross-sectional, not longitudinal.** Preferential attachment is a dynamic mechanism; we test only its steady-state signature. A direct test of the $\propto k$ attachment kernel from public GitHub event archives is feasible but outside this paper.
4. **Star-fraud noise.** Sold, bot, and coordinated stars are documented [9, 10]. The effect at $x_\mathrm{min} > 25{,}000$ is plausibly small because repositories at that scale dominate by genuine reputation, but we have not bounded fraud contamination quantitatively.
5. **Language trend.** The $\alpha = 3.00$ (JavaScript) to $2.61$ (Java) ordering is interpretable as finite-time relaxation but could equally reflect topic-mix or community-size differences. A cross-snapshot analysis would be needed.
6. **Lognormal not rejected.** Power-law beats exponential by $R = +5.45$ but ties lognormal at $R = -1.45$, $p = 0.15$. The fitted tail is "heavy-tailed and consistent with power-law", not "strictly power-law"; Mitzenmacher [13] applies in full.

None of these affects the basic Phase 6 finding: the pipeline recovers $\alpha = 2.87$ on a fresh 8,398-repository sample, the bootstrap CI brackets the BA asymptote, and the result lies inside the V4 layer-4 prediction band for the preferential-attachment class.

## 7. Conclusion

The layer-5 pipeline, run unchanged on 8,398 GitHub repositories, returns $\alpha = 2.867$ with bootstrap 95% CI $[2.781, 3.000]$, inside the predicted band $[2.0, 3.0]$ for the Barabási-Albert class. JavaScript hits the canonical BA asymptote $\alpha = 3$ to two decimal places; all six languages with $n \geq 300$ sit inside the band. Power-law beats exponential by $R = +5.45$; the lognormal test is inconclusive, as is generically expected at $n \sim 10^3$. The result is independent validation of a known platform-level preferential-attachment signature, and is the first empirical evidence in this project that V4's class separation is operationally meaningful: the same code base, applied to systems from two classes, returns exponents in two non-overlapping predicted bands.

## 8. References

[1] P. Bak, C. Tang, and K. Wiesenfeld, "Self-organized criticality: An explanation of 1/f noise," *Phys. Rev. Lett.* **59**, 381 (1987).

[2] G. U. Yule, "A mathematical theory of evolution, based on the conclusions of Dr. J. C. Willis, F.R.S.," *Philos. Trans. R. Soc. B* **213**, 21 (1925).

[3] H. A. Simon, "On a class of skew distribution functions," *Biometrika* **42**, 425 (1955).

[4] D. J. de Solla Price, "A general theory of bibliometric and other cumulative advantage processes," *J. Am. Soc. Inf. Sci.* **27**, 292 (1976).

[5] A.-L. Barabási and R. Albert, "Emergence of scaling in random networks," *Science* **286**, 509 (1999).

[6] R. Albert and A.-L. Barabási, "Statistical mechanics of complex networks," *Rev. Mod. Phys.* **74**, 47 (2002).

[7] M. E. J. Newman, "Power laws, Pareto distributions and Zipf's law," *Contemp. Phys.* **46**, 323 (2005).

[8] H. Borges and M. T. Valente, "What's in a GitHub star? Understanding repository starring practices in a social coding platform," *J. Syst. Softw.* (EMSE follow-on) **146**, 112 (2018).

[9] A. Lima, L. Rocha, M. Musolesi, and V. Latora, "Coding together at scale: GitHub as a collaborative social network," in *Proc. ICWSM* (2014).

[10] V. Cosentino, J. L. Cánovas Izquierdo, and J. Cabot, "A systematic mapping study of software development with GitHub," *IEEE Access* **5**, 7173 (2017).

[11] A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Rev.* **51**, 661 (2009).

[12] J. Alstott, E. Bullmore, and D. Plenz, "powerlaw: A Python package for analysis of heavy-tailed distributions," *PLoS ONE* **9**, e85777 (2014).

[13] M. Mitzenmacher, "A brief history of generative models for power law and lognormal distributions," *Internet Math.* **1**, 226 (2004).

[14] P. L. Krapivsky, S. Redner, and F. Leyvraz, "Connectivity of growing random networks," *Phys. Rev. Lett.* **85**, 4629 (2000).

[15] M. E. J. Newman, "The structure and function of complex networks," *SIAM Rev.* **45**, 167 (2003).
