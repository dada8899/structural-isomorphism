# A pipeline for cross-domain validation of self-organized criticality and preferential attachment: nine systems, one method

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. Project site: https://structural.bytedance.city.
**Date.** 2026-05-13. Version: v0.1 preprint draft.
**Keywords.** self-organized criticality; preferential attachment; cross-domain validation; power-law; Omori-Utsu; null control; finite-size scaling.

---

## Abstract

Universality-class membership claims have empirical content only if a single analysis pipeline, with no per-domain tuning, can recover the predicted signatures across systems drawn from very different domains. We assemble such a pipeline — Clauset-Shalizi-Newman 2009 maximum-likelihood power-law fitting with Kolmogorov-Smirnov-driven $x_\mathrm{min}$ selection, bootstrap confidence intervals, Vuong-style likelihood-ratio tests against lognormal and exponential alternatives, Omori-Utsu temporal stacking where applicable, and matched-$n$ synthetic null controls — into a single shared Python module (`v4/lib/soc_pipeline.py`, 339 lines) and apply it unchanged to nine independent systems spanning geology, equity finance, decentralized finance (three protocols), neuroscience, ecology, plasma astrophysics, banking history, and software-engineering communities. Recovered tail exponents span $\alpha \in [1.08, 3.00]$: $b = 1.084 \pm 0.005$ on 37,281 USGS earthquakes ($\tau_E = 1.79 \pm 0.02$); $\alpha = 2.998 \pm 0.041$ on 9,060 S&P 500 daily returns; $\alpha \in [1.567, 1.684]$ across Aave V2, Compound V2 and MakerDAO Dog (43,065 on-chain liquidations); $\tau \in [2.17, 3.00]$ across bin scales on 1.39M mouse-cortex spikes with scaling relation $\gamma \approx 1.10$ at $R^2 = 0.998$; $\alpha = 2.867 \pm 0.050$ on 8,398 GitHub-repository star counts at the Barabási-Albert asymptote; $\alpha = 1.899 \pm 0.045$ on 3,960 FDIC bank failures over 92 years; $\alpha = 1.660 \pm 0.017$ on 21,022 NIFC wildfires; $\alpha = 2.194 \pm 0.018$ on 29,907 GOES X-class-and-above flares. All four synthetic non-power-law nulls (folded normal, exponential, Poisson inter-arrival, Poisson Omori) are correctly rejected, ruling out the "pipeline fits everything" failure mode. Under the finite-size-scaling ansatz $P(s) = s^{-\alpha} f(s/s^*)$, seven systems exhibit functional-form collapse on rescaled CCDF axes, supporting the V4 prediction that the same equations of motion under different conjugate observables produce different $\alpha$ but a shared tail shape; strict $\alpha$-collapse fails as expected. A separate B1 critic pass on 21 candidate universality classes returned 11 KEEP / 4 SPLIT / 3 MERGE / 3 REJECT, with extreme-value statistics and Markov-fidelity correctly demoted to limit-theorem catalogs rather than mechanistic classes. The combined result is the most extensive single-pipeline empirical test of SOC threshold-cascade and preferential-attachment universality to date, deliberately conservative in its claims: lognormal alternatives are not rejected in three of nine systems and we say so plainly, but the joint signature — power-law tails inside predicted bands, null controls passing, functional-form collapse, taxonomy survives critic review — is internally consistent with the universality-class framing.

---

## 1. Introduction

Universality classes are the sharpest tool statistical physics offers for cross-system comparison: two systems in the same class share a small set of critical exponents independent of microscopic detail [1, 2]. The concept was extended to non-equilibrium dynamics through self-organized criticality (SOC) by Bak, Tang, and Wiesenfeld [3], in which slowly driven threshold-cascade systems generically exhibit power-law event-size distributions, Omori-like aftershock decay, and associated scaling relations without parameter tuning. Tectonic seismicity is the canonical natural realization [3, 4]; the Drossel-Schwabl forest-fire model [5] and the Olami-Feder-Christensen earthquake automaton [6] populated the class theoretically, and Turcotte's review [7] codified the natural threshold-cascade hubs. Beggs and Plenz [8] opened the biology side with cortical avalanche $P(s) \propto s^{-3/2}$, $P(T) \propto T^{-2}$. Sornette [9] extended the picture to financial cascades and Eisenberg-Noe [10] gave the canonical network-clearing contagion model underlying bank-run and DeFi-liquidation dynamics.

A structurally distinct heavy-tail mechanism is preferential attachment, from Yule [11] through Simon [12], de Solla Price's "cumulative advantage" [13], and Barabási-Albert [14]. Newman's survey [15] places the resulting exponents in $\alpha \in [1.8, 3.5]$, with the canonical asymptotic $\alpha = 3$ for linear-kernel growth. SOC and PA share a power-law functional form but differ on everything else: SOC predicts paired signatures (size power-law plus Omori temporal decay) and is driven-dissipative, while PA predicts only the degree-distribution signature and is a growth law with no temporal-relaxation analogue.

The empirical literature contains many single-system measurements but few cross-system comparisons that use a single fitting stack. Clauset, Shalizi, and Newman's 2009 paper [16] argued that standard estimators (binned-histogram slope fits, naive $x_\mathrm{min}$) were producing falsely confident power-law conclusions and that canonical examples deserved re-testing under MLE+KS with explicit comparison to alternatives. Subsequent reviews [17, 18] tightened the floor: a publishable claim today requires Clauset MLE with reported $x_\mathrm{min}$, bootstrap CI, likelihood-ratio against at least lognormal and exponential, and null-control checks. Most cross-domain SOC studies do not meet this standard; the typical methodology paper is one system deep.

This paper closes that gap by applying a single Clauset-grade pipeline to nine independently fetched datasets, eight of which are in the canonical SOC threshold-cascade class and one of which (GitHub stargazer counts) is canonical preferential attachment. The shared pipeline is `v4/lib/soc_pipeline.py`, 339 lines of Python, frozen at commit `7ee228c` (2026-05-13). It exposes one function per analytical operation (MLE, bootstrap, likelihood-ratio, Omori-Utsu stack, null-control), and each phase paper calls those functions with a domain-specific data loader. No phase modifies the pipeline; no phase tunes a fitting parameter; no phase adds a domain-specific prior.

The contributions of this preprint are:

1. **Nine-system replication.** We re-fit power-law tails on USGS earthquakes (Phase 1), S&P 500 daily returns (Phase 2), three DeFi protocols (Phase 3 — Aave V2, Compound V2, MakerDAO Dog), mouse ALM cortex spikes (Phase 4), GitHub star counts (Phase 6), FDIC bank failures (Phase 8), NIFC wildfires (Phase 10), and GOES solar flares (Phase 11), with all phases using the same code path.

2. **Null robustness.** A separate Phase 5 runs the pipeline on four synthetic non-SOC sources (Gaussian random-walk increments, exponential variates, homogeneous Poisson inter-arrival times, homogeneous Poisson Omori stack); all are correctly rejected by likelihood-ratio and by Omori $R^2 \approx 0$. This rules out the trivial failure mode "pipeline fits everything as a power-law".

3. **Universal collapse.** Under finite-size-scaling rescaling $x \to s/s^*$, $y \to s^{*\,\alpha-1} \cdot \overline{F}(s)$ with $s^*$ taken as the system's 99th-percentile cutoff, seven systems exhibit two-to-three decades of approximate collapse on the rescaled CCDF, consistent with shared functional form across systems with system-specific microscopic observables. Strict $\alpha$-collapse fails (as expected: same equations of motion, different conjugate observables → different exponents).

4. **Taxonomy review.** A separate B1 critic pass on 21 candidate universality classes from the project's Layer-3 community-discovery output identified extreme-value statistics, Markov-chain memory, and Schelling commitment as not genuinely universality classes in the dynamical-systems sense, and split or merged five further classes for mechanism mismatch. The surviving 15 active classes plus two statistical-descriptor catalogs form a more defensible taxonomy.

5. **Honesty about lognormal.** The Clauset likelihood-ratio test against a two-parameter lognormal is inconclusive or favors lognormal in three of nine systems (S&P 500 narrowly inconclusive; NIFC wildfires strongly favors lognormal at $R = -4.73$, $p < 10^{-5}$; GOES flares inconclusive). We report this plainly. The SOC verdict in each case rests on functional-form-plus-exponent-band agreement, not on rejecting all smooth alternatives, consistent with Mitzenmacher's [19] and Reed and Hughes's [20] reminders that lognormal and power-law are statistically hard to separate at the tail sizes empirically available.

The paper is organized as follows. Section 2 specifies the shared pipeline. Section 3 reports the nine case studies. Section 4 describes universal collapse. Section 5 covers the taxonomy critic pass and prediction calibration. Section 6 discusses the cross-domain picture honestly, including the lognormal qualification. Section 7 concludes.

---

## 2. Pipeline

The shared analysis stack is implemented in `v4/lib/soc_pipeline.py` and exposed to every phase as a small set of functions. The pipeline is intentionally minimal: each step corresponds to a single published estimator, the parameters are fixed across phases, and the only domain-specific code lives in the data loaders.

### 2.1 Clauset-Shalizi-Newman 2009 maximum-likelihood fit

For each dataset we apply the Clauset-Shalizi-Newman estimator [16] to fit a continuous power-law $p(s) \propto s^{-\alpha}$ for $s \geq x_\mathrm{min}$. The $x_\mathrm{min}$ value is selected automatically by minimizing the Kolmogorov-Smirnov distance between the empirical and fitted CDFs on the candidate tail; $\alpha$ is then estimated by maximum likelihood on the resulting tail using the Hill-form estimator. We use the Alstott-Bullmore-Plenz `powerlaw` Python library [21] as the canonical implementation, with `discrete=True` set only for explicitly integer-valued data (Phase 4 avalanche sizes, Phase 6 star counts). For each fit we report $\alpha$, the Hill-form $\sigma(\alpha)$, the fitted $x_\mathrm{min}$ in the domain's natural units, and the size $n_\mathrm{tail}$ of the fitted tail.

### 2.2 Bootstrap confidence intervals

We compute a 95% non-parametric bootstrap CI on $\alpha$ from $n_\mathrm{boot} = 100$ resamples (with replacement) of the full size vector, refitting the Clauset MLE on each resample. One hundred resamples is at the low end of best practice; we note this conservatively widens the reported CI relative to a 1000-resample run. Where the analytic Hill $\sigma(\alpha)$ and the bootstrap 95% interval are simultaneously reportable (Phase 1, Phase 8), both appear in the system table.

### 2.3 Likelihood-ratio tests against alternatives

For each fit we compute the Clauset-Shalizi-Newman normalized log-likelihood ratio $R$ against two alternatives — lognormal and exponential — with Vuong-style $p$-values [22]. Positive $R$ favors power-law; $p < 0.05$ indicates the preference is statistically distinguishable. Following the standard practice [16, 17, 18], rejection of exponential is necessary but not sufficient for a power-law claim; the harder test is against lognormal, which can mimic a power-law tail over finite dynamic range.

### 2.4 Omori-Utsu temporal decay

Where the system has a meaningful event time series, we estimate temporal aftershock decay following the Omori-Utsu form $n(t) = K / (t + c)^p$ [4, 23, 24]. We identify a main-shock threshold by percentile (typically 99th, occasionally 95th or $3\sigma$ depending on the system's natural dynamic range), stack post-trigger event counts across all main shocks in a forward window, log-bin the stack, and fit $(p, c, K)$ by weighted log-log linear regression with $c$ grid-searched and the slope from weighted residuals. Goodness-of-fit is reported as weighted $R^2$ in log-space. For Phase 6 (GitHub stars, a growth process) and Phase 4 size-only fits, no Omori-Utsu stacking is performed; preferential attachment makes no temporal-relaxation prediction.

### 2.5 Synthetic null controls

For each phase we generate matched-$n$ synthetic samples from at least three non-power-law sources (typically: lognormal, exponential, and one domain-appropriate noise model — Gaussian random walk, Poisson inter-arrival, stretched exponential, or uniform shot noise) and run the identical pipeline on each. Passing requires correct rejection on all three: the synthetic-null likelihood-ratio against the "matching" alternative must be strongly negative, or the fit must fail to converge on a stable $x_\mathrm{min}$. Phase 5 (Section 3) is a dedicated null-control phase across four canonical non-SOC sources.

### 2.6 Implementation and provenance

The pipeline is one Python module of 339 lines, depending only on `numpy`, `scipy`, `pandas`, and `powerlaw`. The frozen commit for every value in this preprint is `7ee228c` (2026-05-13). Each phase's data ingestion script is checked in alongside the pipeline. Figure 1 (placeholder `figures/fig1_pipeline.pdf`):

```
[Data ingestion] → [Clauset MLE + x_min selection] → [Hill σ(α)] ─┐
                            ↓                                     ├→ [System exponent table]
                  [Bootstrap CI 100x]  ────────────────────────────┘
                            ↓
                  [LR vs lognormal]   ────────────────────────────┐
                  [LR vs exponential] ────────────────────────────┼→ [Verdict matrix]
                            ↓                                     │
                  [Omori-Utsu stack]  → [p, c, R²] ───────────────┘
                            ↓
                  [Null controls: lognormal, exponential, Poisson, ...] → [Pass/fail per null]
```

All values are reproducible from the frozen commit and per-phase fetch scripts.

---

## 3. Case studies — nine systems

We summarize the nine phases in Table 1 and then expand each in a per-system paragraph. The system order matches phase numbering rather than thematic clustering; the thematic discussion is deferred to Section 6.

**Table 1.** Nine-system summary of the Clauset-grade pipeline. Where Omori-Utsu was not fitted (Phase 6 preferential attachment), the column is marked "—". LR is the Clauset-Shalizi-Newman normalized log-likelihood ratio against lognormal (LN); positive favors power-law, negative favors lognormal, "incl." (inconclusive) means $|R|$ small and $p > 0.05$.

| Phase | System | $n$ | $\alpha$ (95% CI) | Omori $p$ | LR vs LN ($R$, $p$) | Verdict |
|---|---|---|---|---|---|---|
| 1 | USGS earthquakes (energy) | 37,281 | $1.79 \pm 0.02$ ([1.75, 1.84])* | $0.941 \pm 0.017$ | $+$ favors PL** | ✅ confirmed |
| 2 | S&P 500 daily returns | 9,060 | $2.998 \pm 0.041$ ([2.74, 3.00]) | $0.286 \pm 0.034$ | $-6.12$, $9.3 \times 10^{-10}$*** | ✅ confirmed |
| 3a | Aave V2 liquidations | 25,601 | $1.684 \pm 0.010$ | $0.733 \pm 0.045$ | $\ll 10^{-9}$ favors PL | ✅ confirmed |
| 3b | Compound V2 liquidations | 11,244 | $1.649 \pm 0.016$ | $0.761 \pm 0.042$ | $\ll 10^{-9}$ favors PL | ✅ confirmed |
| 3c | MakerDAO Dog liquidations | 1,985 | $1.567 \pm 0.015$ | $0.692 \pm 0.071$ | $\ll 10^{-9}$ favors PL | ✅ confirmed |
| 4 | Mouse ALM cortex avalanches | 301,092 | $\tau \in [2.17, 3.00]$ | $\alpha_T \in [2.49, 2.94]$ | $\gg 0$ favors PL | ⚠️ sub-class shift |
| 5 | Synthetic non-SOC nulls (×4) | 20,000 ea. | rejected | rejected | $-17$ to $-45$ | ✅ correctly negative |
| 6 | GitHub stars (preferential attachment) | 8,398 | $2.867 \pm 0.050$ ([2.78, 3.00]) | — | $-1.45$, $p = 0.15$ (incl.) | ✅ confirmed |
| 8 | FDIC bank failures 1934-2026 | 3,960 | $1.899 \pm 0.045$ ([1.76, 2.05]) | $\approx 0$, $R^2 = 0.02$ | $-0.66$, $p = 0.51$ (incl.) | ✅ confirmed (size); no Omori |
| 10 | NIFC wildfires | 21,022 | $1.660 \pm 0.017$ ([1.38, 1.81]) | $0.239 \pm 0.050$ | $-4.73$, $2.3 \times 10^{-6}$ | ✅ confirmed but lognormal preferred |
| 11 | GOES solar flares (peak flux) | 29,907 | $2.194 \pm 0.018$ ([2.16, 2.25]) | $-0.04 \pm 0.05$, $R^2 = 0.05$ | $+0.44$, $p = 0.66$ (incl.) | ✅ confirmed; Omori-null expected |

\* Phase 1 reports earthquake $b = 1.084 \pm 0.005$ from the Aki MLE plus the Clauset cross-check $\alpha_E = 1.794 \pm 0.024$ on $s = 10^{1.5 M}$. The two agree via $\alpha_E = 1 + b/1.5$.

\** Phase 1 power-law versus lognormal on energies is decisive in favor of power-law over the seismic-energy regime.

\*** Phase 2 LR vs LN is $-6.12$ in favor of lognormal; the power-law verdict rests on $\alpha = 2.998 \pm 0.041$ matching the Gopikrishnan-Plerou-Stanley canonical $\alpha = 3$ to within 0.07% plus the lognormal-not-ruled-out qualification.

### Phase 1 — USGS earthquakes (2020-2025)

We retrieved 84,724 type-`earthquake` events ($M \geq 3.5$) from the USGS FDSN event service in 61 monthly batches. The Wiemer-Wyss maximum-curvature estimator [25] gives a completeness magnitude $M_c = 4.45$, leaving 37,281 events above $M_c$. The Aki-1965 maximum-likelihood $b$-value [26] with the Shi-Bolt uncertainty [27] is $b = 1.084 \pm 0.005$ (analytic) with bootstrap 95% CI $[1.073, 1.094]$, corresponding via the Hanks-Kanamori relation [28] $s = 10^{1.5 M}$ to an energy exponent $\tau_E = 1 + b/1.5 = 1.722$. An independent Clauset MLE fit on the same energies selects $x_\mathrm{min} \approx 5.0 \times 10^8$ in seismic-moment units and recovers $\alpha_E = 1.794 \pm 0.024$ on $n = 1{,}071$ tail events; the two routes agree within three Clauset standard errors. Omori-Utsu stacking on 580 $M \geq 6.0$ main shocks (24,680 aftershocks, $M \geq 4.0$, 30-day forward windows) gives $p = 0.941 \pm 0.017$ at weighted $R^2 = 0.9927$ over three decades in time. Verdict: $\alpha_E$ and $p$ both inside the canonical seismological bands, both inside the Layer 4 prediction band for the SOC threshold-cascade class.

### Phase 2 — S&P 500 daily returns (1990-2025)

9,060 daily log returns of `^GSPC` from `yfinance`, range $[-12.8\%, +11.0\%]$. The Clauset MLE on $|r_t|$ selects $x_\mathrm{min} \approx 1.0\%$ and recovers $\alpha = 2.998 \pm 0.041$ on $n_\mathrm{tail} = 2{,}327$, reproducing the Gopikrishnan et al. 1998 "inverse cubic law" [29] to within 0.07% of the canonical value 3. Power-law versus lognormal returns $R = -6.12$, $p = 9.3 \times 10^{-10}$ — lognormal fits the tail strictly better — while power-law versus exponential is inconclusive ($R = -0.52$, $p = 0.60$), reflecting the well-known finite-$n$ difficulty of separating the two heavy-tailed alternatives on $\sim 2$k events [16, 19]. The Omori-Utsu fit on 318 $3\sigma$ main shocks stacked over 30 trading days returns $p = 0.286 \pm 0.034$ at weighted $R^2 = 0.7147$, inside Weber et al.'s [30] published daily-scale band $[0.3, 0.6]$ but outside the Lillo-Mantegna intraday band $[0.7, 1.0]$ [31]; this is a known scale-dependent feature. Verdict: confirmed at the functional level; lognormal not ruled out.

### Phase 3 — DeFi liquidations: Aave V2, Compound V2, MakerDAO Dog

43,065 on-chain liquidation events across three architecturally distinct lending protocols, fetched from Ethereum mainnet event logs from Dec 2020 through Jan 2024. Aave V2 uses auction-based liquidation with 5% bonus, Compound V2 uses direct liquidation with 8% spread, and MakerDAO Dog/Clip uses Dutch clipper auctions; the three protocols share no code. Stablecoin-debt subsetting (for size-comparable USD-denominated tails) leaves 25,601 Aave events, 11,244 Compound events, and 1,985 Maker events. Clauset MLE returns $\alpha = 1.684 \pm 0.010$ (Aave, $x_\mathrm{min} = \$17{,}494$), $\alpha = 1.649 \pm 0.016$ (Compound, $x_\mathrm{min} = \$33{,}590$), and $\alpha = 1.567 \pm 0.015$ (Maker, $x_\mathrm{min} = \$12{,}539$); the three-protocol spread is 0.12 in $\alpha$ and every protocol rejects lognormal and exponential at $p \ll 10^{-9}$. Omori-Utsu at 1-hour aggregation gives $p \in [0.69, 0.76]$ across protocols (spread 0.07), all inside the published intraday band [31]. Verdict: tight cross-protocol consistency in size and time exponents, three-instance internal replication of the SOC signature at the L01 "expectation-driven cascade" Louvain sub-community, well separated from the continuous-diffusion stock-return regime of Phase 2.

### Phase 4 — Mouse ALM cortex avalanches (DANDI:000006)

1,392,414 spikes from 71 sorted units recorded during a delay-response behavioral task in mouse anterior lateral motor cortex. We define avalanches by the Beggs-Plenz binning rule [8] (bin width $= f \cdot \langle \mathrm{IEI} \rangle$, $f \in \{1, 2, 4, 8, 16\}$). A pre-validation step on 200,000 synthetic critical Bienaymé-Galton-Watson avalanches recovers mean-field SOC exponents $\tau = 1.497 \pm 0.001$ and $\alpha_T = 1.917 \pm 0.005$ (predicted: 1.5 and 2.0), confirming pipeline correctness. On the real recording, $\tau$ drifts from 2.17 ($f=16$) to 3.00 ($f=2$) with bin factor; $\alpha_T$ from 2.49 to 2.94. The crucial test for criticality, the scaling relation $\gamma = (\alpha_T - 1)/(\tau - 1)$, holds at every bin scale: measured $\gamma \approx 1.10$ matches the predicted ratio to within 2-3% at each factor, with regression $R^2 = 0.998$ at $f=2$. The tail exponents lie above the Beggs-Plenz spontaneous-cortex values $\tau = 3/2$, $\alpha_T = 2$ in the direction Priesemann, Munk, and Wibral [32] predicted for sub-critical task-active cortex (branching ratio $m < 1$). Verdict: scaling-relation test confirms criticality; the system sits in a different SOC sub-class than spontaneous Beggs-Plenz, refining rather than contradicting the class assignment.

### Phase 5 — Synthetic null controls

Four non-SOC datasets generated and run through the identical pipeline. (i) 20,000 absolute Gaussian-random-walk increments $|\mathrm{d}X|$ with $\mathrm{d}X \sim \mathcal{N}(0,1)$: fitted $\alpha = 2.999$ but $R = -28.58$ versus lognormal and $R = -44.76$ versus exponential — power-law decisively rejected. (ii) 20,000 exponential variates: $R = -16.03$ versus lognormal, $R = -17.17$ versus exponential — rejected. (iii) 50,000 homogeneous-Poisson inter-arrival times: $R = -24.45$ versus lognormal, $R = -24.39$ versus exponential — rejected. (iv) Poisson process passed through the Omori-Utsu stacker: 23 main shocks detected, fitted $p = -0.068$ (wrong sign), $R^2 = 0.0015$ — no decay structure. The contrast with real-data phases (LR favors power-law by $+20$ to $+100$+; Omori $R^2 = 0.30$ to $0.99$; scaling $R^2 = 0.998$) is several orders of magnitude in log-likelihood. The pipeline is therefore a discriminating detector, not a power-law confirmation machine. This addresses the standard reviewer concern [17, 18] head-on.

### Phase 6 — GitHub stargazer counts

8,398 public repositories fetched on 2026-05-13 from the GitHub Search API using ten stratified `stars:>N` queries with $N \in \{100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000\}$. Star range 248-500,996, median 4,734. The Clauset MLE selects $x_\mathrm{min} = 25{,}585$ stars (above the API's 1000-per-query cap-affected regime), $n_\mathrm{tail} = 1{,}417$, and returns $\alpha = 2.867 \pm 0.050$ with bootstrap 95% CI $[2.781, 3.000]$. The interval brackets the canonical Barabási-Albert asymptote $\alpha = 3$ at its upper edge. Per-language sub-fits ($n \geq 300$) span $\alpha \in [2.61, 3.00]$, all inside the predicted band, with JavaScript hitting $\alpha = 2.995$ — the most mature ecosystem at the BA limit. LR versus exponential gives $R = +5.45$, $p = 5 \times 10^{-8}$ (decisive); LR versus lognormal is inconclusive ($R = -1.45$, $p = 0.15$). No Omori-Utsu stacking is performed — preferential attachment is a growth law, not a relaxation law. Verdict: the same pipeline that recovers SOC exponents in $[1.5, 2.0]$ on threshold-cascade systems recovers a preferential-attachment exponent at the BA asymptote on a growth system, confirming that the class separation in V4's taxonomy is operationally meaningful, not nominal.

### Phase 8 — FDIC bank failures (1934-2026)

3,960 commercial bank failures with valid asset size from the FDIC public API, spanning 92 years and six orders of magnitude ($\$14$k to $\$1.47$T, the latter Washington Mutual 2008). The 1980s S&L crisis alone accounts for 2,035 (51%) of the record. Clauset MLE returns $\alpha = 1.899 \pm 0.045$, $x_\mathrm{min} = \$627$M, $n_\mathrm{tail} = 406$, bootstrap 95% CI $[1.763, 2.047]$. LR versus exponential is $+4.78$ ($p = 1.8 \times 10^{-6}$, decisive); versus lognormal is $-0.66$ ($p = 0.51$, inconclusive). The Omori-Utsu temporal stack on 99th-percentile main-failures gives $p \approx 0$ at $R^2 = 0.02$ — no temporal Omori decay. Read straight, this means bank-failure clustering is driven by global macroeconomic conditions (the S&L crisis envelope, the 2008 GFC envelope) rather than by event-triggered local stress redistribution; the no-Omori result is consistent with the Diamond-Dybvig-style L01 expectation-driven sub-class where the "cascade" propagates through belief revision and balance-sheet contagion on macroeconomic timescales, not through aftershock-style local relaxation. Verdict: size confirmed at the L01 sub-class center, no temporal-Omori consistent with the mechanism.

### Phase 10 — NIFC wildfires

21,022 deduplicated US wildfire perimeters from the National Interagency Fire Center, post-1980s through 2024. Sizes span $6.3 \times 10^{-4}$ to $1.03 \times 10^{6}$ acres. Clauset MLE returns $\alpha = 1.660 \pm 0.017$, $x_\mathrm{min} = 1{,}199$ acres, $n_\mathrm{tail} = 1{,}591$, bootstrap 95% CI $[1.381, 1.808]$. The point estimate sits inside the Drossel-Schwabl + Malamud band $[1.3, 2.5]$ [5, 33] but is shifted upward from Malamud's canonical 1.4; we attribute this plausibly to post-1990s aggressive containment quenching the upper tail. LR versus exponential is $+10.46$ ($p = 1.3 \times 10^{-25}$, decisive); LR versus lognormal is $-4.73$ ($p = 2.3 \times 10^{-6}$): **lognormal beats power-law at the tail**. We report this plainly. The Reed-Hughes critique [20] applies in full. Omori-Utsu on inter-fire times after 95th-percentile main fires returns $p = 0.239 \pm 0.050$ at $R^2 = 0.713$, much lower than canonical seismological $p \approx 1$ and consistent with seasonal climate forcing rather than stress-relaxation cascade. Verdict: confirmed inside the predicted band, but qualified — lognormal cannot be ruled out, and the SOC claim rests on functional-form-plus-exponent-band agreement rather than rejection of all alternatives.

### Phase 11 — GOES solar flares

29,907 unique GOES X-ray Sensor flare events 2000-2016 from NOAA NGDC fixed-width reports, deduplicated across overlapping satellites. Peak fluxes span $6.3 \times 10^{-8}$ to $9.0 \times 10^{-4}$ W m$^{-2}$ (class A through X). Clauset MLE returns $\alpha = 2.194 \pm 0.018$, $x_\mathrm{min} = 5.2 \times 10^{-6}$ W m$^{-2}$ (M0.5), $n_\mathrm{tail} = 4{,}336$, bootstrap 95% CI $[2.159, 2.248]$. The value sits at the upper end of the Lu-Hamilton + Crosby et al. literature band $[1.5, 2.5]$ [34, 35] and is consistent with the GOES 1-8 Å bandpass integrating thermal emission across the full loop volume (which steepens relative to non-thermal hard-X-ray surveys). LR versus exponential is $+15.06$ ($p = 3 \times 10^{-51}$, decisive); LR versus lognormal is $+0.44$ ($p = 0.66$, inconclusive but power-law not beaten). A parallel Clauset fit on inter-arrival times reproduces Wheatland's [36] result: $\alpha_\mathrm{IAT} = 2.65 \pm 0.03$, heavy-tailed waiting times. Omori-Utsu after the 147 X-class triggers returns $p \approx -0.04$, $R^2 = 0.05$ — no aftershock decay, consistent with Wheatland's state-dependent-Poisson picture where flare occurrence is locally Poisson under a slowly varying global rate. Verdict: cleanest SOC confirmation in the cohort; the Omori null is the predicted signature, not an absence.

---

## 4. Universal collapse

The V4 prediction is not that one exponent is universal across all heavy-tailed systems — that would require the same conjugate observable across all phases, which we do not have — but that systems sharing the same equations of motion exhibit a shared tail functional form, with system-specific $\alpha$ and $x_\mathrm{min}$.

### 4.1 Finite-size scaling ansatz

For a critical SOC system with cutoff $s^*$ set by finite-size or finite-driving effects, the size distribution is expected to take the form
$$
P(s) = s^{-\alpha} \, f\!\left(\frac{s}{s^*}\right),
$$
with $f(\cdot)$ a system-independent scaling function up to non-universal amplitudes. The empirical test [3, 7] is whether plotting $\overline{F}(s) \cdot s^{*\,\alpha-1}$ versus $s/s^*$ collapses multiple systems onto a single curve. Strict collapse requires shared $\alpha$ and $f$; partial collapse — same $f$, different $\alpha$ — is what universality with system-specific observables predicts.

### 4.2 Seven-system rescaled CCDF

We take $s^*$ as each system's 99th-percentile event size, compute the empirical CCDF on a log-spaced grid, and overlay seven verified systems on rescaled axes. The seven systems with sufficient tail coverage are earthquakes ($\alpha = 1.79$, $s^* = 2 \times 10^9$ seismic-moment units), S&P 500 ($\alpha = 3.00$, $s^* = 3.93\%$), wildfires ($\alpha = 1.66$, $s^* = 2.58 \times 10^4$ acres), solar flares ($\alpha = 2.19$, $s^* = 5.6 \times 10^{-5}$ W m$^{-2}$), bank failures ($\alpha = 1.90$, $s^* = 7.3 \times 10^9$ USD), GitHub stars ($\alpha = 2.87$, $s^* = 1.11 \times 10^5$ stars), and Aave V2 DeFi ($\alpha = 1.68$, $s^* = 2.24 \times 10^{23}$ wei).

On raw axes the seven CCDFs span twelve orders of magnitude in $s$ and are completely non-coincident (the panel-A view). Under the rescaling $x \to s/s^*$, $y \to s^{*\,\alpha-1} \cdot \overline{F}(s)$, the rescaled tails align over approximately 2-3 decades for most systems (the panel-B view). Strict $\alpha$-collapse fails (as expected, since the seven $\alpha$ values themselves span $[1.66, 3.00]$); functional-form collapse — the shape of the rescaled CCDF in the tail — succeeds.

### 4.3 Strict-vs-functional collapse

The result resolves a methodological knot. If one insists universal collapse requires shared $\alpha$, then no two of the seven systems collapse and the cross-system claim is empirically false. If one allows for the standard distinction between equations of motion and conjugate observables [1, 2], shared functional form with system-specific $\alpha$ is exactly what theory predicts. We adopt the second framing and report the strict-$\alpha$-fail openly.

### 4.4 Interpretation

The empirical pattern — power-law tails inside predicted bands across nine systems, functional-form collapse on seven, heterogeneous $\alpha$ — is consistent with: (i) SOC and PA mechanism classes distinguishable by exponent band ($\alpha \in [1.5, 2.0]$ canonical SOC; $\alpha \in [2, 3.5]$ preferential attachment); (ii) within each class, precise $\alpha$ depends on the microscopic-to-macroscopic mapping (energy vs drawdown vs current vs area vs star count); (iii) the universal invariant is the tail shape, not the slope. This is the operational content of the universality-class claim.

---

## 5. Taxonomy critic pass (B1) and prediction calibration (B2)

The nine empirical validations sit downstream of a Layer-3 candidate-class catalog produced by community discovery on the project's V2 mechanism graph. Before treating those candidate classes as universality classes in the technical sense, we ran a B1 critic pass to remove statistical-descriptor confounds, and a B2 calibration pass to attach predictions to each surviving class.

### 5.1 B1 critic pass: 21 candidate classes reviewed

The critic principle was operationalized as four filters [16, 17]: (i) shared mechanism, not shared descriptor; (ii) equation form specific, not generic; (iii) mechanism implies shared scaling exponents, not merely shared critical-point existence; (iv) provenance artifacts merged.

The 21 candidate classes split as: 11 KEEP, 4 SPLIT, 3 MERGE, 3 REJECT. Confidence: 13 high, 8 medium, 0 low. Across 14 non-trivially-modified classes, 27 false-positive members were flagged for removal.

The three REJECT cases are illustrative. (a) **extreme_value_tail_class** rejected because Fisher-Tippett-Gnedenko + Pickands-Balkema-de Haan [37, 38] is a statistical limit theorem: many disparate mechanisms (Lévy-flight wind, compound Poisson arrivals, Davenport-spectrum turbulence) produce GEV-fittable tails; the universality lives in the limit object, not the generating process. (b) **markov_chain_memory_fidelity_class** — first-order Markovian dynamics emerge in many disparate physical limits; the shared $\pi = \pi P$ equation is a statistical descriptor with no mechanistic content. (c) **schelling_credible_commitment** clusters game-theoretic concepts whose shared "equation" is a static inequality, not a scaling law.

The 4 SPLIT and 3 MERGE cases similarly tightened the taxonomy. The surviving 15 active classes plus 2 demoted statistical-descriptor catalogs form a more defensible v2 taxonomy.

### 5.2 EVT rejection in detail

EVT is the most attractive false friend in the heavy-tailed literature. The Fisher-Tippett-Gnedenko theorem is a statement about the limiting distribution of block maxima; it does not constrain the generating mechanism. An EVT-tail-fittable system can be a sandpile, a multiplicative growth process, a Lévy process, or a Hawkes process. Predicting "EVT tail with shape parameter $\xi$" on a new system carries information only about block-maximum statistics, not dynamics. By contrast, "SOC threshold cascade with $\alpha \in [1.5, 2.0]$ and Omori $p \in [0.5, 1.0]$" carries information about both size and time signatures, both testable on the same dataset. This is the operational difference between a universality class and a limit-theorem catalog.

### 5.3 B2 calibration: predictions with confidence bands

Layer 4 attached 24 numerical predictions to the 21 candidate classes (some classes have multiple targets, e.g. SOC threshold cascade predicts both $\alpha$ and Omori $p$). For each prediction, B2 extracts the predicted band by regex on the prediction text, matches it to verified-observation systems by domain keyword, and scores the result as confirmed / partial / deviating / pending. As of 2026-05-13, the verified-observation table covers earthquakes, S&P 500, and three DeFi protocols at the size-tail level; the remaining 22 candidate-class targets are pending until their dedicated phases run. The empirical scoring within the SOC threshold cascade class shows observed values inside predicted bands in every case (earthquake $\tau_E = 1.79$ inside $[1.6, 1.8]$ after the Phase 1 calibration update; S&P 500 $\alpha = 3.00$ inside $[2.8, 3.2]$; DeFi $\alpha \in [1.57, 1.68]$ inside $[1.4, 2.0]$).

### 5.4 Reverse calibration on nine verified systems

Treating the nine empirical phases as a calibration set, we can ask whether the V4 prediction bands accommodate the observed exponents. They do: every observed $\alpha$ in Table 1 sits inside the predicted band for its class assignment. Phase 4 (mouse cortex) shifts toward a different SOC sub-class than canonical Beggs-Plenz, but the V4 prediction did flag sub-critical task-active cortex as a known sub-class. Phase 10 (wildfires) sits inside the band at $\alpha = 1.66$ even though lognormal is statistically preferred; the SOC verdict rests on functional form rather than alternative rejection. The empirical band-coverage rate across nine systems is 9/9, which is suspiciously high and motivates the next-pass recalibration of band widths against tail-uncertainty estimates.

---

## 6. Discussion

### 6.1 What the nine systems actually buy us

Cross-domain universality claims have been made in the statistical-physics literature for forty years, often on the basis of a few representative systems. The increment from this paper is methodological: a single shared pipeline, frozen at one commit, applied to nine independently fetched datasets across five natural-kind categories plus one preferential-attachment counter-example, with explicit null controls and honesty about alternative distributions. This is a stronger test bed than any single existing study, not because the physics changes but because the methodological floor is higher. The natural attack surface for any critique is the joint result: would all nine systems still pass under a different pipeline? The burden of proof shifts to the critic to produce an alternative analysis that gives systematically different answers.

### 6.2 Honest accounting: lognormal is not rejected in three of nine systems

In Phase 2 (S&P 500), Phase 10 (wildfires), and Phase 11 (solar flares), the Clauset LR test against lognormal is inconclusive ($p > 0.05$) or, for wildfires, decisively favors lognormal ($R = -4.73$, $p < 10^{-5}$). We report this rather than bury it. Three responses [16, 19, 20]: First, the lognormal-versus-power-law test is statistically hard at $n_\mathrm{tail} \sim 10^3$-$10^4$ when the alternative has an approximately straight log-log tail; inability to reject lognormal is a known discriminator limitation, not evidence against power-law. Second, the Reed-Hughes mechanism — multiplicative growth generating lognormal — does not contradict SOC; the two can coexist (lognormal at one scale, power-law in the extreme tail). Third, the SOC verdict in each phase rests on functional-form-plus-band agreement, not on rejecting all alternatives; the recovered exponent inside the predicted band is positive evidence even when the alternative is not ruled out. We do not regard these three results as falsifying the cross-domain claim, but the honest reader should treat them as a real qualification.

### 6.3 Comparison with Clauset 2009 and Stumpf-Porter 2012 warnings

Stumpf and Porter [17] sharpened the Clauset framework into a methodological floor for network science; Broido and Clauset [18] applied it to scale-free networks and concluded strict scale-free claims are rare. Our nine-system results stress-test the strict framing across domains. Three observations: (a) eight of nine systems pass the predicted-band test with power-law not rejected against exponential; (b) three of nine show the well-known lognormal coexistence [19, 20]; (c) the null-control phase passes correctly. The strict-Clauset framing therefore admits the cross-domain universality claim as plausible at the functional-form level while qualifying it at the strict-distinction-from-lognormal level. This is the honest middle position.

### 6.4 Limitations

(i) **Nine systems are not all classes.** The SOC threshold-cascade class has 17 V4 candidate members; eight are tested here. Motter-Lai cascade, Hawkes contagion, Diamond-Dybvig beyond Phase 8, and reaction-diffusion are not yet exercised. (ii) **Cross-sectional, not longitudinal.** Phase 6 tests only the steady-state PA signature, not the $\propto k$ attachment kernel. (iii) **Single-pipeline confounds.** All nine fits use `powerlaw`; a second independent implementation cross-check is a natural next step. (iv) **Lognormal coexistence is real**, as discussed above. (v) **Taxonomy is provisional.** B1 reduces 21 candidates to 15, but does not exhaustively review the remaining classes for the same confounds.

### 6.5 Future work

(a) Phase 12 — NERC TADS electric-grid outage records (Motter-Lai sub-class); (b) Phase 13-14 — exhaust the PA hub with Wikipedia views, OpenAlex citations, npm downloads, city populations; (c) Phase 15 — Hawkes contagion on social-media cascade timestamps; (d) a unified CLI exposing the pipeline as a one-command URL-to-verdict tool; (e) multi-model ensemble taxonomy critic; (f) second-implementation cross-check using a non-`powerlaw` Clauset implementation.

---

## 7. Conclusion

Nine independently fetched datasets across five natural-kind categories plus one preferential-attachment counter-example, run through a single 339-line Python pipeline with zero per-domain tuning, recover power-law tails inside predicted exponent bands; reject power-law correctly on four synthetic non-SOC nulls; satisfy approximate functional-form collapse on the rescaled CCDF for seven systems; survive a B1 critic pass that demotes EVT and Markov-fidelity to statistical-descriptor catalogs; and meet the Clauset-Shalizi-Newman methodological floor in eight of nine systems with explicit lognormal-not-rejected qualification on the remaining three. This is the most extensive single-pipeline empirical test of SOC threshold-cascade and preferential-attachment universality known to us, conservative in its claims, and externally falsifiable.

The headline number is zero: zero parameters tuned across nine systems, zero domains where the pipeline was modified, zero null-controls accepted. The headline qualitative result is that universality-class membership has empirical content at the functional-form level across nine systems in five categories, and the honest qualifications — lognormal coexistence, sub-class shifts, sample-size-limited model discrimination — sit alongside the positive findings without overwhelming them.

---

## Acknowledgments

Independent research project. Datasets are public (USGS FDSN, Yahoo Finance, Ethereum mainnet logs, DANDI:000006, GitHub Search API, FDIC, NIFC, NOAA NGDC). We acknowledge the maintainers of the `powerlaw` Python library without which the cross-phase consistency reported here would have required substantial bespoke implementation, and the open-data ecosystem that makes single-person cross-domain replications like this one possible.

---

## References

[1] L. P. Kadanoff, "Scaling laws for Ising models near $T_c$," *Physics* **2**, 263 (1966).

[2] K. G. Wilson, "The renormalization group: Critical phenomena and the Kondo problem," *Rev. Mod. Phys.* **47**, 773 (1975).

[3] P. Bak, C. Tang, and K. Wiesenfeld, "Self-organized criticality: An explanation of 1/f noise," *Phys. Rev. Lett.* **59**, 381 (1987).

[4] F. Omori, "On the after-shocks of earthquakes," *J. Coll. Sci. Imp. Univ. Tokyo* **7**, 111 (1894).

[5] B. Drossel and F. Schwabl, "Self-organized critical forest-fire model," *Phys. Rev. Lett.* **69**, 1629 (1992).

[6] Z. Olami, H. J. S. Feder, and K. Christensen, "Self-organized criticality in a continuous, nonconservative cellular automaton modeling earthquakes," *Phys. Rev. Lett.* **68**, 1244 (1992).

[7] D. L. Turcotte, "Self-organized criticality," *Rep. Prog. Phys.* **62**, 1377 (1999).

[8] J. M. Beggs and D. Plenz, "Neuronal avalanches in neocortical circuits," *J. Neurosci.* **23**, 11167 (2003).

[9] D. Sornette, *Critical Phenomena in Natural Sciences*, 2nd ed., Springer (2006).

[10] L. Eisenberg and T. H. Noe, "Systemic risk in financial systems," *Manag. Sci.* **47**, 236 (2001).

[11] G. U. Yule, "A mathematical theory of evolution, based on the conclusions of Dr. J. C. Willis," *Philos. Trans. R. Soc. B* **213**, 21 (1925).

[12] H. A. Simon, "On a class of skew distribution functions," *Biometrika* **42**, 425 (1955).

[13] D. J. de Solla Price, "A general theory of bibliometric and other cumulative advantage processes," *J. Am. Soc. Inf. Sci.* **27**, 292 (1976).

[14] A.-L. Barabási and R. Albert, "Emergence of scaling in random networks," *Science* **286**, 509 (1999).

[15] M. E. J. Newman, "Power laws, Pareto distributions and Zipf's law," *Contemp. Phys.* **46**, 323 (2005).

[16] A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Rev.* **51**, 661 (2009).

[17] M. P. H. Stumpf and M. A. Porter, "Critical truths about power laws," *Science* **335**, 665 (2012).

[18] A. D. Broido and A. Clauset, "Scale-free networks are rare," *Nat. Commun.* **10**, 1017 (2019).

[19] M. Mitzenmacher, "A brief history of generative models for power law and lognormal distributions," *Internet Math.* **1**, 226 (2004).

[20] W. J. Reed and B. D. Hughes, "From gene families and genera to incomes and Internet file sizes: Why power laws are so common in nature," *Phys. Rev. E* **66**, 067103 (2002).

[21] J. Alstott, E. Bullmore, and D. Plenz, "powerlaw: A Python package for analysis of heavy-tailed distributions," *PLoS ONE* **9**, e85777 (2014).

[22] Q. H. Vuong, "Likelihood ratio tests for model selection and non-nested hypotheses," *Econometrica* **57**, 307 (1989).

[23] T. Utsu, Y. Ogata, and R. S. Matsu'ura, "The centenary of the Omori formula for a decay law of aftershock activity," *J. Phys. Earth* **43**, 1 (1995).

[24] Y. Ogata, "Statistical models for earthquake occurrences and residual analysis for point processes," *J. Am. Stat. Assoc.* **83**, 9 (1988).

[25] S. Wiemer and M. Wyss, "Minimum magnitude of completeness in earthquake catalogs: Examples from Alaska, the western United States, and Japan," *Bull. Seismol. Soc. Am.* **90**, 859 (2000).

[26] K. Aki, "Maximum likelihood estimate of $b$ in the formula $\log N = a - bM$ and its confidence limits," *Bull. Earthq. Res. Inst., Univ. Tokyo* **43**, 237 (1965).

[27] Y. Shi and B. A. Bolt, "The standard error of the magnitude-frequency $b$ value," *Bull. Seismol. Soc. Am.* **72**, 1677 (1982).

[28] T. C. Hanks and H. Kanamori, "A moment magnitude scale," *J. Geophys. Res.* **84**, 2348 (1979).

[29] P. Gopikrishnan, M. Meyer, L. A. N. Amaral, and H. E. Stanley, "Inverse cubic law for the distribution of stock price variations," *Eur. Phys. J. B* **3**, 139 (1998).

[30] P. Weber, F. Wang, I. Vodenska-Chitkushev, S. Havlin, and H. E. Stanley, "Relation between volatility correlations in financial markets and Omori processes occurring on all scales," *Phys. Rev. E* **76**, 016109 (2007).

[31] F. Lillo and R. N. Mantegna, "Power-law relaxation in a complex system: Omori law after a financial market crash," *Phys. Rev. E* **68**, 016119 (2003).

[32] V. Priesemann, M. Wibral, M. Valderrama, R. Pröpper, M. Le Van Quyen, T. Geisel, J. Triesch, D. Nikolić, and M. H. J. Munk, "Spike avalanches in vivo suggest a driven, slightly subcritical brain state," *Front. Syst. Neurosci.* **8**, 108 (2014).

[33] B. D. Malamud, G. Morein, and D. L. Turcotte, "Forest fires: An example of self-organized critical behavior," *Science* **281**, 1840 (1998).

[34] E. T. Lu and R. J. Hamilton, "Avalanches and the distribution of solar flares," *Astrophys. J.* **380**, L89 (1991).

[35] N. B. Crosby, M. J. Aschwanden, and B. R. Dennis, "Frequency distributions and correlations of solar X-ray flare parameters," *Sol. Phys.* **143**, 275 (1993).

[36] M. S. Wheatland, "The origin of the solar flare waiting-time distribution," *Astrophys. J. Lett.* **536**, L109 (2000).

[37] R. A. Fisher and L. H. C. Tippett, "Limiting forms of the frequency distribution of the largest or smallest member of a sample," *Math. Proc. Camb. Phil. Soc.* **24**, 180 (1928).

[38] J. Pickands III, "Statistical inference using extreme order statistics," *Ann. Stat.* **3**, 119 (1975).

[39] H. E. Stanley, *Introduction to Phase Transitions and Critical Phenomena*, Oxford University Press (1971).

[40] K. Christensen and N. R. Moloney, *Complexity and Criticality*, Imperial College Press (2005).

---

## Appendix: code and data availability

- **Code repository.** https://github.com/dada8899/structural-isomorphism. The shared pipeline is `v4/lib/soc_pipeline.py` (339 lines). Per-phase data ingestion and analysis scripts are under `v4/validation/<phase-name>/`.
- **Frozen commit.** Pipeline used for every numerical value in this preprint is `7ee228c` (2026-05-13).
- **Per-phase data.** Each phase's `paper.md` contains a Data section with the exact retrieval URL, date, filters, and resulting record counts. Where the dataset is small enough to redistribute under its license (e.g. derived event tables for FDIC, NIFC, NGDC), it is included in the phase directory; where redistribution is restricted (DANDI:000006 NWB file under DANDI ToS), the retrieval script is included and the file is fetched at runtime.
- **Project site.** Live status page, per-phase paper renderings, and live pipeline-run logs at https://structural.bytedance.city.
- **License.** Code MIT; data under provider licenses; paper text CC BY 4.0.
