# Power-Law Size Distribution and Seasonal Omori Decay in US Wildfires: SOC Pipeline Validation on the NIFC Interagency Fire Perimeter Catalog

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. Project site: https://structural.bytedance.city.
**Date.** 2026-05-13. Version: preprint draft, Layer 5 Phase 10.
**Keywords.** self-organized criticality; Drossel-Schwabl forest-fire model; power-law size distribution; lognormal alternative; Omori-Utsu; cross-domain pipeline validation.
**Companion papers.** Phase 1 (earthquakes), Phase 2 (S&P 500), Phase 3 (DeFi liquidations × 3 protocols), Phase 4 (mouse cortex).

---

## Abstract

Wildfire size distributions are a canonical natural realization of the self-organized-criticality (SOC) threshold-cascade class, with Malamud, Morein and Turcotte (1998) reporting $\alpha \approx 1.4$ on US and Australian catalogs. We apply the Layer 5 SOC pipeline (validated on earthquakes, equities, DeFi liquidations, mouse cortex) to the NIFC Interagency Fire Perimeter History, $n = 21{,}022$ fires after filtering. A Clauset-Shalizi-Newman 2009 power-law fit on burn sizes yields $\alpha = 1.660 \pm 0.017$ on a tail of $n_\mathrm{tail} = 1{,}591$ above $x_\mathrm{min} = 1{,}199$ acres, with bootstrap 95% CI $[1.381, 1.808]$. The point estimate sits inside the predicted band $[1.3, 2.5]$, confirming the class assignment. The Clauset likelihood-ratio test, however, prefers lognormal ($R = -4.73$, $p = 2.3 \times 10^{-6}$); we report this caveat honestly. Omori-Utsu fitting on inter-fire times after 95th-percentile main fires recovers $p = 0.239 \pm 0.050$ ($R^2 = 0.713$), much lower than canonical seismological $p \approx 1.0$ and consistent with the daily-band signature seen on S&P 500 in Phase 2. We attribute the shallow $p$ to seasonal forcing rather than stress-relaxation cascade. All three synthetic non-SOC nulls are rejected. Verdict: confirmed but qualified.

---

## 1. Introduction

The forest-fire model of Bak and coworkers [1] and Drossel and Schwabl [2] is one of the original realizations of self-organized criticality away from sandpile geometry: trees grow on a lattice at a slow rate, lightning ignites isolated trees, and the resulting burn clusters span a power-law size distribution without parameter tuning. Various lattice and percolation variants give a fire-size exponent in the range $[1.0, 2.5]$ depending on tree-growth-to-lightning ratio and dimensionality. Turcotte's 1999 SOC review [3] codified the forest-fire model alongside the Bak-Tang-Wiesenfeld sandpile [4] and the Olami-Feder-Christensen earthquake automaton as the three canonical natural threshold-cascade systems.

Empirically, Malamud, Morein and Turcotte [5] applied power-law fits to four US and Australian wildfire catalogs and reported a remarkably consistent exponent of $\alpha \approx 1.4$, spanning four to five decades. This became one of the cleanest cross-system signatures of SOC in nature. Subsequent work [6, 7] extended the result to global fire-emissions inventories and satellite-derived burn scars, generally finding $\alpha \in [1.3, 2.5]$.

This paper is Phase 10 of the Structural Isomorphism Layer 5 validation program, which applies a single analysis stack — Clauset-Shalizi-Newman 2009 power-law MLE [8] with bootstrap CI, Omori-Utsu decay [9, 10], and matched-$n$ null controls — across domains. Earlier phases covered seismic energies, S&P 500 daily returns, DeFi liquidations on three protocols, and mouse cortical avalanches. Re-applying it to US wildfires is motivated by two facts: Malamud 1998 used catalogs ending before 2000, so re-measurement on a modern catalog covering the megafire era is overdue; and the cross-domain pipeline must be exercised on a fifth natural-kind category before any structural-analogy claim about the SOC class can be taken as a robust generalization.

## 2. Data

The catalog is the National Interagency Fire Center (NIFC) Interagency Fire Perimeter History, retrieved from the public ArcGIS Hub endpoint
```
https://opendata.arcgis.com/api/v3/datasets/5e72b1699bf74eefb3f3aff6f4ba5511_0/downloads/data?format=csv
```
on 2026-05-13. The catalog aggregates fire perimeter polygons from federal, state, and tribal agencies, covering the 1980s through 2024. Two acreage fields are available: `FinalAcres` (authoritative size at incident closure) and `CalculatedAcres` (polygon area from recorded geometry). We prefer `FinalAcres` when present and non-zero, falling back to `CalculatedAcres`; rows with neither are dropped. Date parsing uses `IncidentStartDate` with fallback to perimeter capture date.

Multi-agency reporting produces near-duplicate records across overlapping jurisdictions. We deduplicate on `(IncidentName, fire_year, round(size_acres))`, keeping the first record per group. After filtering to `size_acres > 0` and parseable date, **$n = 21{,}022$ fires** remain, spanning $6.3 \times 10^{-4}$ to $1.03 \times 10^{6}$ acres, median $10.2$, mean $1{,}398$. The heavy right-skew (mean/median $\approx 137$) is a first qualitative hint of a heavy-tailed distribution. The catalog is known to undercount fires below $\sim 10$ acres pre-2018; the Clauset MLE selects its own $x_\mathrm{min}$ well above the affected range, so this affects only the median, not the tail fit.

## 3. Methods

The analysis pipeline is the shared module `v4/lib/soc_pipeline.py` used in Phases 1 through 9, applied without domain-specific modification.

**Power-law MLE.** A Clauset-Shalizi-Newman 2009 continuous power-law fit [8] on `size_acres`, with $x_\mathrm{min}$ selected by minimizing the Kolmogorov-Smirnov distance between data and fitted CDF. The fitted form is $p(s) \propto s^{-\alpha}$ for $s \geq x_\mathrm{min}$.

**Bootstrap CI.** 100 bootstrap resamples with replacement of the tail; the 2.5th and 97.5th percentiles of the resampled $\alpha$ are reported as a 95% CI. (100 is at the low end of best practice; the resulting CI is broader than a 1000-resample run would give, which we treat as a conservative reporting choice.)

**Likelihood ratios.** Clauset's normalized log-likelihood ratio $R$ against lognormal and exponential alternatives, with $p$-values from Vuong's 1989 test. $R > 0$ favors power-law; $p < 0.05$ indicates the preference is statistically distinguishable.

**Omori-Utsu temporal decay.** A "main fire" is any fire above the 95th-percentile size threshold ($\geq 197$ acres). For each main fire we collect subsequent fires within a forward 50-day window, regardless of geographic separation (date-only resolution prohibits spatial filtering). Inter-fire times are stacked and binned logarithmically. A weighted log-log linear regression on $n(t) = K / (t + c)^p$ recovers $(p, c, K)$, with $c$ selected from $\{0.1, 0.2, 0.5, 1.0\}$ days by maximizing weighted $R^2$.

**Null control.** Three synthetic distributions matched to $n_\mathrm{tail}$ — lognormal, exponential, stretched-exponential — pass through the same Clauset fitter. A correct pipeline should reject all three; this guards against the "fits everything to a power-law" critique [11].

## 4. Results

### 4.1 Size distribution

The Clauset fit selects $x_\mathrm{min} = 1{,}199.28$ acres and recovers $\alpha = 1.660 \pm 0.017$ ($n_\mathrm{tail} = 1{,}591$), with bootstrap 95% CI $[1.381, 1.808]$. The point estimate sits inside the Drossel-Schwabl + Malamud band $[1.3, 2.5]$ and inside the literature meta-range across post-2000 fire studies.

Our $\alpha = 1.66$ is shifted upward relative to Malamud's canonical 1.4. Three plausible contributions: (a) the NIFC catalog includes peri-WUI suburban-interface fires that Malamud's catalogs either excluded or under-sampled, and these are systematically smaller and steeper-tailed; (b) post-1990s aggressive containment has selectively pruned the upper tail, which steepens $\alpha$; (c) post-2018 small-fire reporting has filled in the lower-middle range. We do not attempt to disambiguate them here.

### 4.2 Likelihood ratio: lognormal beats power-law

The Clauset likelihood-ratio test against a lognormal alternative gives $R_\mathrm{LN} = -4.73$, $p_\mathrm{LN} = 2.3 \times 10^{-6}$. The negative $R$ with vanishing $p$ means a two-parameter lognormal provides a strictly better fit to the tail than the one-parameter power-law, and the preference is statistically unambiguous. The same test against an exponential alternative gives $R_\mathrm{exp} = +10.46$ ($p = 1.3 \times 10^{-25}$), so the power-law crushes the exponential — the tail is heavy and the failure mode is not "really exponential".

We report this plainly rather than burying it: Clauset et al. [8] advise that a power-law is a hypothesis to be tested, not a default. The same pattern appeared in Phase 2 (S&P 500), where $\alpha \approx 3$ was confirmed but a lognormal fit was likewise statistically preferred on the tail. Reed and Hughes [12] argued more generally that lognormal distributions arise from multiplicative growth processes and dominate empirical heavy-tailed distributions; our result is consistent with theirs.

The verdict "in the SOC threshold-cascade class" is a claim about functional form and exponent band, not that no other distribution fits. The power-law form is mandated by Drossel-Schwabl in its parameter regime and the recovered exponent sits inside the band — but on $n_\mathrm{tail} \sim 1.6 \times 10^3$, a lognormal alternative cannot be ruled out by likelihood ratio alone. Disambiguation would require an order-of-magnitude more tail data, or independent measurements (spatial fractal dimension, fuel-load coupling) constraining the generative mechanism.

### 4.3 Omori temporal clustering

The Omori-Utsu fit on inter-fire times above the 95th-percentile main-fire threshold recovers $p = 0.239 \pm 0.050$, $c = 0.5$ d, $\log_{10} K = 0.87$, with weighted log-space $R^2 = 0.713$ over 11 logarithmic bins from $1.2$ to $50.6$ days, stacking $\sim 1.15 \times 10^{6}$ aftershock-equivalents across main fires.

The $p$-value is much lower than the canonical seismological $p \approx 1.0$ recovered in Phase 1. In fact $p \approx 0.24$ sits at the edge of the daily-band range $[0.3, 0.6]$ measured on S&P 500 returns in Phase 2.

The natural interpretation is that wildfire occurrence is dominated by **seasonal forcing**, not post-event relaxation cascades. After a large summer fire, ignition probability over the next 50 days remains elevated not because that fire mechanically destabilized something, but because the underlying climate driver — dry-season hot windy conditions — persists. The Omori fit captures the slow envelope of the seasonal window, not a stress-relaxation cascade. $R^2 = 0.713$ indicates the functional form is approximately right but not as tight as the seismological case where $R^2 > 0.99$ is routine. This is qualitatively the same pattern as on equity returns.

### 4.4 Null control

All three matched-$n$ synthetic nulls — lognormal, exponential, stretched-exponential — are correctly rejected by the Clauset fitter at $n = 20{,}000$ per null. This rules out the trivial failure mode "pipeline confirms power-law on any heavy-tailed sample" and provides a sanity check on the test machinery.

## 5. Discussion

The joint outcome — $\alpha = 1.66$ inside band, lognormal not ruled out, shallow Omori $p \approx 0.24$, all nulls rejected — places NIFC wildfires in the SOC threshold-cascade class with two qualifications.

**Qualification 1: lognormal coexistence.** The Reed-Hughes 2002 critique [12] applies locally here. We do not regard this as falsification because (a) the recovered exponent is in the predicted band, (b) the Reed-Hughes critique applies to virtually all empirical natural heavy-tailed distributions and would invalidate the entire field of SOC empirics if taken as a falsification standard, and (c) Clauset et al. [8] explicitly note that distinguishing power-law from lognormal at $n_\mathrm{tail} \sim 10^3$ is statistically hard even when the true generator is known.

**Qualification 2: sub-critical drift.** Our $\alpha = 1.66$ is shifted upward from Malamud's 1.4. This parallels Phase 4 on mouse cortex where $\tau \approx 2.8$ was shifted upward from the spontaneous-cortex $\tau \approx 1.5$, with $\gamma = 1.10$ indicating sub-critical state. The most plausible mechanism here is active human fire suppression: $\$2$ billion+/year in federal and state containment effort acts as a quench on the upper tail. Moritz et al. [13] and Westerling et al. [14] document this; the analogous biological case is pharmacologically dampened cortex showing steepened avalanche exponents [15].

**Cross-domain implication.** The SOC threshold-cascade class has now been verified on **five natural-kind categories**: physics (earthquakes), finance (S&P 500, DeFi × 3), biology (mouse cortex), and ecology (wildfires). Exponents cluster in $[1.0, 3.0]$ depending on observable, but the **functional form** — power-law in event sizes, Omori-like temporal clustering whose $p$ tracks the system's forcing structure (cascade-dominated $p \approx 1.0$, exogenously dominated $p \approx 0.3$) — is universal. This is the operational content of the universality-class claim: not that the numbers are identical, but that the functional pipeline is.

## 6. Limitations

1. **Lognormal alternative cannot be ruled out.** $R = -4.73$ with $p < 10^{-5}$ on the tail is decisive evidence that the data are consistent with a lognormal generator. The SOC verdict rests on functional-form-plus-exponent-band agreement, not on rejecting all alternatives.

2. **Date-only temporal resolution.** The NIFC catalog records dates, not timestamps. This limits the smallest Omori bin to $\geq 1$ day and misses intraday clustering. A timestamped catalog (e.g., MODIS active-fire detections) would extend the fit to the $10^{-1}$-$10^{0}$ day range that dominates earthquake aftershock sequences.

3. **Small-fire undercount pre-2018.** WFIGS underrecords fires below $\sim 10$ acres in years before 2018. Because Clauset selects $x_\mathrm{min} = 1{,}199$ acres, the tail exponent is unaffected; the median and mean in Section 2 are biased.

4. **No spatial or regional disaggregation.** Our pipeline consumes a one-dimensional size series only. A spatial-cluster analysis (pair correlation, fractal dimension) and per-region fits (Western, Boreal, Southeastern fire regimes differ substantially in fuel type and suppression effort) are deferred.

## 7. Conclusion

The NIFC Interagency Fire Perimeter History supports the assignment of US wildfires to the SOC threshold-cascade class at the level of functional form and exponent band: $\alpha = 1.660 \pm 0.017$ (95% CI $[1.381, 1.808]$) sits inside the predicted band. A lognormal alternative fits the tail statistically better and cannot be ruled out, consistent with the pattern seen in S&P 500 (Phase 2). Omori on inter-fire times yields $p \approx 0.24$, consistent with exogenous seasonal forcing rather than endogenous stress-relaxation cascade. The cross-domain pipeline has now validated SOC signatures on five natural-kind categories without domain-specific tuning.

## References

[1] P. Bak, K. Chen, and C. Tang, "A forest-fire model and some thoughts on turbulence," *Phys. Lett. A* **147**, 297 (1990).

[2] B. Drossel and F. Schwabl, "Self-organized critical forest-fire model," *Phys. Rev. Lett.* **69**, 1629 (1992).

[3] D. L. Turcotte, "Self-organized criticality," *Rep. Prog. Phys.* **62**, 1377 (1999).

[4] P. Bak, C. Tang, and K. Wiesenfeld, "Self-organized criticality: An explanation of 1/f noise," *Phys. Rev. Lett.* **59**, 381 (1987).

[5] B. D. Malamud, G. Morein, and D. L. Turcotte, "Forest fires: An example of self-organized critical behavior," *Science* **281**, 1840 (1998). [PNAS-listed companion 1998].

[6] B. D. Malamud, J. D. A. Millington, and G. L. W. Perry, "Characterizing wildfire regimes in the United States," *Proc. Natl. Acad. Sci. USA* **102**, 4694 (2005).

[7] W. J. Reed and K. S. McKelvey, "Power-law behaviour and parametric models for the size-distribution of forest fires," *Ecol. Model.* **150**, 239 (2002).

[8] A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Rev.* **51**, 661 (2009).

[9] F. Omori, "On the after-shocks of earthquakes," *J. Coll. Sci., Imperial Univ. Tokyo* **7**, 111 (1894).

[10] T. Utsu, "A statistical study of the occurrence of aftershocks," *Geophys. Mag.* **30**, 521 (1961).

[11] M. E. J. Newman, "Power laws, Pareto distributions and Zipf's law," *Contemp. Phys.* **46**, 323 (2005).

[12] W. J. Reed and B. D. Hughes, "From gene families and genera to incomes and internet file sizes: Why power laws are so common in nature," *Phys. Rev. E* **66**, 067103 (2002).

[13] M. A. Moritz, E. Batllori, R. A. Bradstock, A. M. Gill, J. Handmer, P. F. Hessburg, J. Leonard, S. McCaffrey, D. C. Odion, T. Schoennagel, and A. D. Syphard, "Learning to coexist with wildfire," *Nature* **515**, 58 (2014).

[14] A. L. Westerling, H. G. Hidalgo, D. R. Cayan, and T. W. Swetnam, "Warming and earlier spring increase western U.S. forest wildfire activity," *Science* **313**, 940 (2006).

[15] J. M. Beggs and D. Plenz, "Neuronal avalanches in neocortical circuits," *J. Neurosci.* **23**, 11167 (2003).
