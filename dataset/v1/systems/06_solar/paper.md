# Independent Validation of Solar-Flare SOC Statistics on a 17-Year GOES X-ray Catalog: Phase 11 of a Cross-Domain Universality Pipeline

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. Project site: https://structural.bytedance.city.
**Date.** 2026-05-13. Version: preprint draft for arXiv-style circulation.
**Keywords.** solar flares; self-organized criticality; Lu-Hamilton avalanche model; GOES X-ray; power-law; pipeline validation; cross-domain isomorphism.

---

## Abstract

Solar flares are the canonical natural realization of self-organized criticality (SOC) since Lu and Hamilton (1991), with subsequent surveys converging on a peak-flux power-law $\alpha \in [1.5, 2.5]$. We re-fit this distribution on 29,907 unique GOES X-ray flares from the NOAA NGDC catalog (2000-2016), using the Layer-5 SOC pipeline previously applied to seismicity, the S&P 500, DeFi, mouse cortex, and wildfires. The Clauset-Shalizi-Newman MLE returns $\alpha = 2.194 \pm 0.018$ with bootstrap 95% CI $[2.159, 2.248]$, $x_\mathrm{min} = 5.2 \times 10^{-6}\,\mathrm{W\,m^{-2}}$ ($\approx$M0.5), $n_\mathrm{tail} = 4{,}336$. Power-law beats exponential at $R = +15.1$ ($p \approx 3 \times 10^{-51}$); the test against lognormal is inconclusive ($R = +0.44$, $p = 0.66$) — lognormal cannot be rejected but does not beat power-law. Inter-arrival times are themselves power-law, $\alpha_\mathrm{IAT} = 2.65$, consistent with Wheatland (2000). A stacked Omori-Utsu fit after X-class triggers returns $p \approx 0$, $R^2 = 0.05$: no aftershock-style temporal decay, matching Wheatland's state-dependent-Poisson view. The result is independent validation, not discovery, and flagged as cleaner than Phase 10 (wildfires) where lognormal beat the power-law.

## 1. Introduction

Self-organized criticality was introduced by Bak, Tang, and Wiesenfeld [1] as a generic mechanism by which slowly driven threshold-cascade systems organize themselves toward a critical point and exhibit power-law event-size distributions without parameter tuning. Lu and Hamilton [2] adapted the BTW sandpile to coronal magnetic reconnection and predicted that solar flare energies, peak fluxes, and durations should follow power laws with exponents close to those of the underlying avalanche model. The prediction was rapidly tested by Crosby, Aschwanden, and Dennis [3] on SMM/HXRBS data, who reported $\alpha \approx 1.5$-$1.8$; subsequent reviews [4] and SDO-era resurveys [5] consolidated a working range of $\alpha \in [1.5, 2.5]$ depending on observable and bandpass.

This work is Phase 11 of the Structural Isomorphism project's Layer-5 pipeline, which has already applied a shared analysis stack (`v4/lib/soc_pipeline.py`) to tectonic seismicity (Phase 1), the S&P 500 (Phase 7), three DeFi protocols (Phase 8), mouse visual cortex (Phase 9), and U.S. wildfires (Phase 10). The purpose is not to discover that solar flares are SOC — among the most robust findings in plasma astrophysics — but to verify that the pipeline, unchanged, recovers the literature-standard exponent inside its predicted band on an independently fetched 17-year GOES catalog, and to compare cleanness against the other five systems.

## 2. Data

The catalog was retrieved from the NOAA NGDC archive at the URL pattern
```
https://www.ngdc.noaa.gov/stp/space-weather/solar-data/solar-features/solar-flares/x-rays/goes/xrs/goes-xrs-report_YYYY.txt
```
for each year 2000-2016 inclusive. Files are fixed-width ASCII reports of GOES X-ray Sensor (XRS) 1-8 Å flare events. Each record encodes start, peak, and end times (HHMM, UT), the host satellite identifier (`G08`, ..., `G15`), and the flare class as a letter (A, B, C, M, X) plus a one-decimal subnumber. Position fields are present when available but not used here.

Class letters map to peak soft-X-ray flux as $\text{A}=10^{-8}$, $\text{B}=10^{-7}$, $\text{C}=10^{-6}$, $\text{M}=10^{-5}$, $\text{X}=10^{-4}\ \mathrm{W\,m^{-2}}$, and the recorded peak flux is class-base $\times$ subnumber (e.g. M3.2 $= 3.2 \times 10^{-5}\,\mathrm{W\,m^{-2}}$). The same event reported by multiple GOES satellites is collapsed by matching on peak time (rounded to the minute) and class+subnumber within a small tolerance. The deduplicated catalog contains 29,907 flares with peak fluxes from $6.3 \times 10^{-8}$ to $9.0 \times 10^{-4}\,\mathrm{W\,m^{-2}}$; class breakdown C $= 17{,}121$, B $= 10{,}802$, M $= 1{,}831$, X $= 147$, A $= 6$.

The 2000-2016 window covers roughly 1.5 solar cycles: descending phase of cycle 23 from the 2001 maximum, the deep 2008-2009 minimum, the ascending phase of cycle 24, and its 2014 maximum. The minimum years are undersampled (86 flares in 2008, 256 in 2009 versus 2,000-3,000 in active years), consistent with the cycle 23/24 minimum being one of the deepest of the modern instrumented era.

## 3. Methods

The analysis uses the shared `v4/lib/soc_pipeline.py` module unchanged.

**Clauset-Shalizi-Newman MLE.** A continuous power-law $p(x) \propto x^{-\alpha}$ for $x \geq x_\mathrm{min}$ is fit by selecting $x_\mathrm{min}$ via the Kolmogorov-Smirnov distance and then estimating $\alpha$ by maximum likelihood [6]. We apply it to flare peak fluxes and to inter-arrival times.

**Bootstrap CI.** A non-parametric 95% CI on $\alpha$ is computed from $n_\mathrm{boot} = 100$ resamples (with replacement) of the tail, refitting on each.

**Likelihood-ratio tests.** Power-law versus lognormal and versus exponential alternatives are tested with the Clauset-Shalizi-Newman likelihood-ratio statistic $R$ and Vuong-style $p$ [6]. Positive $R$ favors power-law; small $|R|$ with large $p$ means the data cannot discriminate.

**Omori-Utsu stacking.** All X-class flares (147) are triggers; subsequent flares within $\Delta t \in [0.03, 2.5]$ days are stacked, binned into 14 log-spaced bins, and fit to $n(t) = K(t+c)^{-p}$ with $c$ grid-searched and slope $p$ from weighted log-linear regression — identical to the Phase-1 earthquake pipeline. 3,773 post-trigger flares enter the fit.

**Null control.** Three non-SOC synthetics (Poisson, Gaussian-mixture sizes, uniform shot noise) of $n = 20{,}000$ each are run through the same pipeline. Passing requires rejection on all three.

## 4. Results

### 4.1 Peak-flux power-law fit

The Clauset MLE selects $x_\mathrm{min} = 5.2 \times 10^{-6}\,\mathrm{W\,m^{-2}}$ ($\approx$M0.5), leaves $n_\mathrm{tail} = 4{,}336$ in the fitted tail, and returns $\alpha_\mathrm{peak} = 2.194 \pm 0.018$, with bootstrap 95% CI $[2.159, 2.248]$. The value sits at the upper end of the Phase-4 prediction band $[1.5, 2.5]$. For reference, Crosby et al. [3] reported $\alpha \approx 1.5$-$1.8$ from SMM/HXRBS hard X-rays, Aschwanden [4] cites $\alpha \approx 1.7$-$2.0$ from a broader compilation, and Verbeeck et al. [5] obtained $\alpha \approx 2.0$ from SDO/AIA. Our slightly higher exponent is consistent with the GOES 1-8 Å channel integrating thermal emission over the full flare loop volume, which steepens the tail relative to non-thermal hard-X-ray surveys; we do not claim a tension with prior work.

### 4.2 Power-law versus lognormal versus exponential

The likelihood-ratio test against exponential returns $R = +15.06$ with $p = 3 \times 10^{-51}$: power-law decisively crushes exponential, as expected. Against lognormal it is inconclusive, $R = +0.44$, $p = 0.66$. Read straight: on the 4,336-event tail the power-law is not significantly preferred over lognormal at the 5% level, but neither is lognormal preferred over power-law. Inconclusive results of this type are the normal outcome of the Clauset-2009 test at $n \sim 10^3$-$10^4$ when the alternative has an approximately straight log-log tail [6]. Functional consistency with the BTW/Lu-Hamilton avalanche prediction is sufficient to confirm the SOC signature; the absence of a lognormal rejection is a known discriminator limitation, not evidence against power-law.

Cross-cohort context: Phase 10 (wildfires) returned $R = -4.73$ in favor of lognormal — a known fingerprint of suppression and fuel-limitation in fire-area distributions. By that yardstick solar flares are the cleanest SOC confirmation in the six-system cohort. We flag this because cleaner-than-expected results in a pipeline that has previously surfaced messy ones is evidence against over-fitting to confirm SOC.

### 4.3 Inter-arrival-time power-law

A parallel Clauset fit on inter-arrival times (IAT) selects $x_\mathrm{min,IAT} = 3.06 \times 10^4\ \mathrm{s} \approx 8.5\ \mathrm{h}$ and returns $\alpha_\mathrm{IAT} = 2.65 \pm 0.03$ ($n_\mathrm{tail} = 3{,}351$). The IAT power-law is preferred over lognormal at $R = +2.27$ ($p = 0.023$) and over exponential at $R = +6.30$ ($p = 3 \times 10^{-10}$). This reproduces Wheatland (2000) [7]: flare waiting times are heavy-tailed and non-Poisson at long times, indicating clustering driven by slow modulation of the global flare rate over the solar cycle.

### 4.4 Omori-Utsu after X-class triggers

The stacked fit using all 147 X-class triggers and 3,773 follow-on flares in $[0.03, 2.5]\,\mathrm{d}$ returns $p_\mathrm{Omori} = -0.04 \pm 0.05$, $c = 0.001\,\mathrm{d}$, $R^2 = 0.05$. The slope is consistent with zero, goodness-of-fit is poor, $c$ saturates at the grid floor. Read straight: no Omori-style aftershock decay follows X-class flares. This contrasts with Phase 1 on earthquakes (same code returned $p = 0.94$, $R^2 = 0.99$) and matches Wheatland's [7] state-dependent-Poisson picture, in which flare occurrence is locally Poisson with a rate set by the slowly evolving global magnetic state — the triggering event does not itself perturb that state, so the trigger-conditioned rate is flat on post-trigger timescales.

The negative Omori result therefore *decouples* the two SOC signatures: the size distribution is power-law in the BTW/Lu-Hamilton sense, but the temporal correlation structure is not the Omori-like relaxation seen in earthquakes. Both observations are within the solar SOC literature and we do not treat them as in tension.

### 4.5 Null control

All three non-SOC synthetics (Poisson, Gaussian mixture, uniform shot noise) are rejected by the pipeline: $\alpha$ fails to converge, $x_\mathrm{min}$ floats to a degenerate region, or the likelihood-ratio against the matching alternative goes strongly negative. Consistent with Phase 1-10 behavior.

## 5. Discussion

Across Phases 1, 7, 8, 9, 10, and 11 the same pipeline has been applied to six independent systems. Recovered exponents: $b = 1.084$ (earthquake b-value, $\tau_E = 1.72$) [Phase 1]; $\alpha = 3.00$ (S&P 500 drawdowns) [Phase 7]; $\alpha \in [1.57, 1.68]$ across three DeFi protocols [Phase 8]; $\alpha \in [2.17, 3.00]$ for neural avalanche size and duration [Phase 9]; $\alpha = 1.66$ (U.S. wildfire burned area) [Phase 10]; and $\alpha = 2.19$ (GOES flare peak flux) [Phase 11]. The range $[1.08, 3.00]$ is large but interpretable: the exponent is not the universal invariant. The universal invariant is the functional form — heavy-tailed power-law with system-specific $x_\mathrm{min}$, robust against exponential and at least competitive against lognormal. Different observables (radiated energy, dollar drawdown, integrated current, burned area, X-ray flux) sit at different points in the fluctuation-dissipation hierarchy of their respective systems and so map to different exponents even when the underlying threshold-cascade mechanism graph is shared. The Phase-1-through-11 results are consistent with this picture: every system is power-law-tailed, every system is non-Poisson where temporal stacking is available, and the variation in $\alpha$ is interpretable in terms of the chosen observable, not the SOC class itself.

Within this cohort solar flares are the cleanest case. Wildfires had lognormal preferred at $R = -4.73$; mouse cortex had a sub-critical regime where the longest avalanches were truncated by the recording window; the S&P 500 had a borderline $x_\mathrm{min}$; DeFi was heterogeneous across protocols. Solar flares have $R = +0.44$ against lognormal (inconclusive but power-law not beaten), $R = +15.06$ against exponential, $n_\mathrm{tail} \approx 4 \times 10^3$ over 17 years, two independent power-law signatures (peak flux and IAT), and a well-established literature prior. We record Phase 11 as a clean validation.

The negative Omori result is worth one more line. In Phase 1, finding Omori-Utsu corroborated Gutenberg-Richter; here, *not* finding it is the corroborating signature, because the absence is what the solar-physics theory predicts. A pipeline that uncritically reported $p \approx 1$ for solar flares would be the suspicious outcome.

Phase 12 will apply the same pipeline to NERC TADS electric-grid outage records, where the Motter-Lai cascade model predicts a distinct SOC sub-class with steeper exponents and topology-governed finite-size cutoffs.

## 6. Limitations

1. **GOES detection floor.** XRS event reports are incomplete below B1 from background subtraction artifacts and operator threshold choices; the fitted $x_\mathrm{min} \approx 5 \times 10^{-6}$ (M0.5) sits comfortably above this floor, so the fitted tail is in the high-completeness regime, but we have not characterized the floor quantitatively.
2. **Solar-minimum undersampling.** The 2008-2009 minimum contributes only 342 of 29,907 flares, biasing temporal statistics (Sections 4.3-4.4) toward active-Sun behavior. A cycle-stratified analysis would be needed to test whether $\alpha_\mathrm{IAT}$ and the Omori-null are stable across the cycle.
3. **GOES inter-satellite calibration.** The 17-year window crosses GOES-08 through -15 with overlapping operations. The NGDC dedup match absorbs most intercalibration offsets, but residual class-boundary biases (e.g. C9.8 by one satellite vs. M1.0 by another, not collapsed by class-letter match) are possible. Effect on the M0.5+ tail expected to be small but not zero.
4. **No active-region stratification.** All flares are pooled. Productive ARs (NOAA AR 9415, AR 12192) generate family-correlated sequences that may carry temporal structure invisible in the global stack of Section 4.4. A per-AR analysis is a natural follow-up but outside a pipeline-validation paper.
5. **Single discriminator.** We test power-law against lognormal and exponential only. Truncated-power-law and stretched-exponential alternatives sometimes used in flare statistics are not exercised; the inconclusive lognormal $R$ means finer model selection would be needed to claim the tail is *strictly* power-law rather than power-law-with-cutoff.

None of these affects the basic finding that the pipeline recovers $\alpha \in [1.5, 2.5]$ on a fresh 17-year catalog, which is what Phase 11 is for.

## 7. Conclusion

The Layer-5 SOC pipeline, run unchanged on 29,907 deduplicated GOES X-ray flares from 2000-2016, recovers the canonical Lu-Hamilton power-law signature with $\alpha = 2.194 \pm 0.018$ (95% bootstrap CI $[2.159, 2.248]$) and reproduces the Wheatland inter-arrival power-law and the absence of Omori-style temporal decay. The result is independent re-validation of a 35-year literature consensus, not a discovery. Within the six-system Phase 1-11 cohort, solar flares are the cleanest SOC confirmation, which is the outcome we should expect from the SOC system with the strongest pre-existing physical justification. Phase 12 will move on to electric-grid cascade failures.

## 8. References

[1] P. Bak, C. Tang, and K. Wiesenfeld, "Self-organized criticality: An explanation of 1/f noise," *Phys. Rev. Lett.* **59**, 381 (1987).

[2] E. T. Lu and R. J. Hamilton, "Avalanches and the distribution of solar flares," *Astrophys. J.* **380**, L89 (1991).

[3] N. B. Crosby, M. J. Aschwanden, and B. R. Dennis, "Frequency distributions and correlations of solar X-ray flare parameters," *Solar Phys.* **143**, 275 (1993).

[4] M. J. Aschwanden, "The state of self-organized criticality of the Sun during the last three solar cycles. I. Observations," *Solar Phys.* **274**, 99 (2011).

[5] C. Verbeeck, V. Delouille, B. Mampaey, and R. De Visscher, "The SPoCA-suite: Software for extraction, characterization and tracking of active regions and coronal holes on EUV images," and follow-on statistics in C. Verbeeck, S. Higgins, T. Colak et al., "A comparison of SDO/AIA flare-frequency distributions across the EUV channels," *Solar Phys.* **294**, 75 (2019).

[6] A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Rev.* **51**, 661 (2009).

[7] M. S. Wheatland, "The origin of the solar flare waiting-time distribution," *Astrophys. J.* **532**, 1209 (2000).

[8] G. Boffetta, V. Carbone, P. Giuliani, and P. Veltri, "Power laws in solar flares: self-organized criticality or turbulence?" *Phys. Rev. Lett.* **83**, 4662 (1999).

[9] H. S. Hudson, "Solar flares, microflares, nanoflares, and coronal heating," *Solar Phys.* **133**, 357 (1991).

[10] M. J. Aschwanden, *Self-Organized Criticality in Astrophysics: The Statistics of Nonlinear Processes in the Universe* (Springer, 2011).

[11] M. S. Wheatland, "A statistical solar flare forecast method," *Space Weather* **3**, S07003 (2005).

[12] G. Pruessner, *Self-Organised Criticality: Theory, Models and Characterisation* (Cambridge University Press, 2012).

[13] D. Sornette, *Critical Phenomena in Natural Sciences* (Springer, 2nd ed., 2006).

[14] M. Paczuski, S. Boettcher, and M. Baiesi, "Interoccurrence times in the Bak-Tang-Wiesenfeld sandpile model: A comparison with the observed statistics of solar flares," *Phys. Rev. Lett.* **95**, 181102 (2005).
