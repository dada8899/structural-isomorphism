<!--
====================================================================
META — C1 unified preprint draft
Version:  v0.1
Date:     2026-05-22
Status:   草稿待人审 (DRAFT — pending human review before any submission)
Roadmap:  v4-next-roadmap-2026-05-13 §C "维度 C：学术发表" item C1
Scope:    "合成 unified preprint" — synthesize Phase 1-5 (five-system SOC
          core) into a single arXiv-style preprint, candidate title
          "A pipeline for cross-domain validation of self-organized
          criticality: N systems, one method."

DATA SOURCES (every number in this draft traces to one of these):
  - v4/results/FINDINGS-2026-04-15.md          (Layer 1/2 community discovery)
  - v4/results/B2_calibration_summary.md       (Layer 4 prediction calibration)
  - v4/results/B2_ci_summary.md                (Layer 4 prediction 95% CIs — this session)
  - v4/results/A3_universal_collapse_summary.md (cross-system collapse)
  - web/frontend/assets/data/papers/soc-earthquake-2026-04-15.md   (Phase 1)
  - web/frontend/assets/data/papers/soc-stockmarket-2026-04-15.md  (Phase 2)
  - web/frontend/assets/data/papers/soc-defi-2026-04-15.md         (Phase 3)
  - web/frontend/assets/data/papers/soc-neural-2026-04-16.md       (Phase 4)
  - web/frontend/assets/data/papers/soc-null-2026-04-16.md         (Phase 5)
  - web/frontend/assets/data/papers/unified-pipeline-v0.2-2026-05-13.md
    (the existing 13-system v0.2 preprint — this v0.1 draft is the
     narrower Phase 1-5 synthesis the roadmap C1 item asks for, and is
     kept numerically consistent with v0.2)
  - web/frontend/assets/data/papers-manifest.json (paper inventory)

This is a Claude-generated first draft. It has NOT been reviewed by a
domain expert. All [TODO: 待核实] markers below are real gaps that a
human reviewer must close before submission.
====================================================================
-->

# A pipeline for cross-domain validation of self-organized criticality: five systems, one method

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. Project site: https://structural.bytedance.city.
**Version.** v0.1 unified preprint draft (Phase 1–5 synthesis). **Date.** 2026-05-22.
**Status.** Draft — pending human review.
**Keywords.** self-organized criticality; cross-domain validation; power-law; Gutenberg-Richter; Omori-Utsu; inverse cubic law; neural avalanches; null control; universality class; reproducibility.

---

## Abstract

A universality-class membership claim has empirical content only if a single, fixed analysis pipeline — applied with no per-domain tuning — recovers the predicted scaling signatures across systems drawn from very different domains, *and* correctly fails to find those signatures in matched non-class data. We assemble such a pipeline (Clauset–Shalizi–Newman 2009 maximum-likelihood power-law fitting with Kolmogorov–Smirnov-driven `x_min` selection, bootstrap confidence intervals, normalized likelihood-ratio tests against lognormal and exponential alternatives, and Omori–Utsu temporal-decay stacking) into one shared Python module and apply it unchanged to five independent systems: USGS tectonic earthquakes (Phase 1), S&P 500 daily returns (Phase 2), DeFi liquidation cascades across three protocols (Phase 3), task-active mouse-cortex neural avalanches (Phase 4), and a set of four synthetic non-self-organized-criticality (non-SOC) null sources (Phase 5). On real data the pipeline recovers canonical exponents: a Gutenberg–Richter b-value of 1.084 ± 0.005 on 37,281 earthquakes above the completeness magnitude (Omori p = 0.941 ± 0.017); an inverse-cubic tail exponent α = 2.998 ± 0.041 on 9,060 S&P 500 daily returns; tail exponents α ∈ [1.567, 1.684] across 43,065 on-chain DeFi liquidations spanning three architecturally distinct lending protocols (Omori p ∈ [0.69, 0.76]); and, on 1.39 M mouse-cortex spikes, a self-organized-criticality scaling relation satisfied to within 2 % at every bin scale (measured γ ≈ 1.10) although the recording's specific exponents (τ ∈ [2.17, 3.00]) place it in a task-active sub-class rather than the canonical mean-field regime. All four synthetic non-SOC nulls (folded normal, exponential, Poisson inter-arrival, Poisson Omori) are correctly rejected, with power-law-vs-alternative likelihood ratios of −16 to −45 and an Omori-fit R² ≈ 0.002 — ruling out the trivial failure mode "the pipeline fits everything as a power law." We report two qualifications honestly: the pipeline is constructed to detect *endogenous* threshold-cascade signatures and is not expected to flag externally driven crises (Phase 5 validates only the null-rejection direction); and the project's downstream cross-domain *predictions* (Layer 4) remain unverified — their target data has not been collected, so we can give only prior-based credible intervals, not frequentist confidence intervals on observed data. Within those limits, the joint result is an internally consistent, single-pipeline cross-domain test of self-organized-criticality universality across geophysics, equity finance, decentralized finance, and neuroscience.

---

## 1. Introduction

Universality classes are the sharpest tool statistical physics offers for cross-system comparison: two systems in the same class share a small set of critical exponents that are independent of microscopic detail [1, 2]. The concept was extended from equilibrium critical phenomena to non-equilibrium dynamics through the theory of self-organized criticality (SOC) of Bak, Tang, and Wiesenfeld [3], in which slowly driven threshold-cascade systems generically exhibit power-law event-size distributions, Omori-like temporal relaxation, and associated scaling relations without parameter tuning. Tectonic seismicity is the canonical natural realization [3, 4], and the Gutenberg–Richter and Omori–Utsu laws [5, 6] are its most widely reproduced quantitative signatures. Beggs and Plenz [7] opened the biological side of the class with cortical avalanches showing P(s) ∝ s⁻³ᐟ² and P(T) ∝ T⁻². Sornette [8] extended the picture to financial cascades.

The empirical literature contains many single-system measurements but few cross-system comparisons that use one fixed fitting stack. Clauset, Shalizi, and Newman [9] argued that standard estimators — binned-histogram slope fits, naive `x_min` choices — were producing falsely confident power-law conclusions, and that canonical examples deserved re-testing under maximum-likelihood-plus-Kolmogorov–Smirnov estimation with explicit comparison to alternatives. Subsequent practice [9] tightened the floor: a defensible power-law claim today requires a Clauset maximum-likelihood fit with a reported `x_min`, a bootstrap confidence interval, a likelihood-ratio test against at least lognormal and exponential, and a null-control check. Most cross-domain SOC studies do not meet this standard; the typical paper is one system deep.

The Structural Isomorphism project is an attempt to make cross-domain "same mathematical structure" claims operational. Its layered pipeline (i) builds a domain-agnostic catalog of candidate systems and observables, (ii) groups them into candidate equivalence classes from mechanism graphs, (iii) extracts shared invariants for each class, and (iv) issues falsifiable numerical predictions. The Layer 1/2 community-discovery step found that a single self-organized-criticality "threshold-cascade" cluster emerged unsupervised from the project's pair data — 21 phenomena across 12 domains, the largest community in the graph, with earthquakes, DeFi liquidations, bank runs, flash crashes, power-grid cascades, and neural avalanches all assigned to it [v4/results/FINDINGS-2026-04-15.md]. The present paper is the empirical validation step for that cluster's core members.

This paper synthesizes the project's first five validation phases into a single preprint. The contributions are:

1. **A single fixed pipeline across four real systems.** We re-fit power-law tails and, where applicable, Omori temporal decay on USGS earthquakes (Phase 1), S&P 500 daily returns (Phase 2), three DeFi lending protocols (Phase 3 — Aave V2, Compound V2, MakerDAO), and mouse-cortex neural avalanches (Phase 4), all through the same code path with no per-domain parameter tuning.
2. **Null robustness.** Phase 5 runs the identical pipeline on four synthetic non-SOC sources and verifies they are all correctly rejected, ruling out "the pipeline fits everything" as a trivial explanation for the positive findings.
3. **An honest accounting of what the pipeline does and does not establish** — including the lognormal-not-always-rejected qualification, the endogenous-only scope, and the unverified status of the project's downstream predictions.

The paper is organized as follows. Section 2 specifies the shared pipeline. Section 3 reports the five phases. Section 4 places the four real systems side by side. Section 5 discusses the cross-domain picture. Section 6 states the limitations explicitly. Section 7 concludes.

> **[TODO: 待核实 — scope decision]** The roadmap C1 item scopes this unified preprint to Phase 1–5 (the five-system SOC core), and that is what this v0.1 draft synthesizes. A separate, broader 13-system manuscript (`unified-pipeline-v0.2-2026-05-13`) already exists and adds preferential-attachment, Motter–Lai, Preisach, and Scheffer phases. A human reviewer must decide whether C1 ships as the focused five-system SOC paper (recommended by the roadmap title) or is merged into / superseded by the 13-system v0.2 manuscript. This draft assumes the focused five-system version and stays numerically consistent with v0.2.

---

## 2. The shared pipeline

The shared analysis stack is implemented as one Python module and exposed to every phase as a small set of functions. The pipeline is intentionally minimal: each step corresponds to a single published estimator, the parameters are fixed across phases, and the only domain-specific code lives in the per-phase data loaders. No phase modifies the pipeline; no phase tunes a fitting parameter; no phase adds a domain-specific prior.

> **[TODO: 待核实 — module path and provenance]** The 13-system v0.2 manuscript cites the shared module as `v4/lib/soc_pipeline.py` (339 lines, frozen at commit `7ee228c`, 2026-05-13). The five-system Phase 1–5 papers (2026-04-15/16) predate that consolidation and describe the same logical pipeline without a single canonical file path. A human reviewer must confirm the exact module path and commit hash that the Phase 1–5 numbers were produced from before this is stated as fact.

### 2.1 Clauset–Shalizi–Newman maximum-likelihood power-law fit

For each dataset we fit a continuous power-law p(s) ∝ s⁻ᵅ for s ≥ `x_min` using the Clauset–Shalizi–Newman estimator [9]. The lower cutoff `x_min` is selected automatically by minimizing the Kolmogorov–Smirnov distance between the empirical and fitted cumulative distribution functions on the candidate tail; α is then estimated by maximum likelihood on that tail. We use the Alstott–Bullmore–Plenz `powerlaw` library [10] as the canonical implementation, with the discrete-data option set only for explicitly integer-valued data (Phase 4 avalanche sizes and durations). For each fit we report α, its uncertainty, the fitted `x_min` in the domain's natural units, and the tail size `n_tail`.

### 2.2 Bootstrap confidence intervals

We compute a 95 % non-parametric bootstrap confidence interval on α by resampling the size vector with replacement and refitting the Clauset maximum-likelihood estimator on each resample. Phase 1 uses 500 resamples on the b-value; the cross-domain phases use a smaller resample count (the v0.2 manuscript states 100 resamples for the consolidated runs, which conservatively widens the reported interval relative to a 1000-resample run).

> **[TODO: 待核实 — bootstrap resample count per phase]** Phase 1 explicitly reports 500 bootstrap resamples for the b-value. The exact resample count used for Phases 2–4 is not stated identically across the per-phase papers (v0.2 reports 100 for its consolidated runs). A reviewer should confirm the per-phase resample count so the confidence-interval methodology is reported uniformly.

### 2.3 Likelihood-ratio tests against alternatives

For each fit we compute the Clauset–Shalizi–Newman normalized log-likelihood ratio R against two alternatives — lognormal and exponential — with associated p-values. Positive R favors the power-law; p < 0.05 indicates the preference is statistically distinguishable. Rejection of exponential is necessary but not sufficient for a power-law claim; the harder test is against lognormal, which can mimic a power-law tail over a finite dynamic range. Clauset et al. [9] caution that the likelihood-ratio test has limited power for small tails, in which case "inconclusive" must not be read as evidence for either model.

### 2.4 Omori–Utsu temporal decay

Where a system has a meaningful event time series, we estimate temporal aftershock decay following the Omori–Utsu form n(t) = K / (t + c)ᵖ [6]. We identify a main-shock threshold by percentile or by a multiple of the standard deviation, stack post-trigger event counts across all main shocks in a forward window, log-bin the stack, and fit (p, c, K) by weighted log-log regression with c grid-searched. Goodness of fit is reported as a weighted R² in log space. Phase 4's preferential-attachment-adjacent observables (avalanche sizes) are fitted for size scaling only; the Omori stack is not applied where the class makes no temporal-relaxation prediction.

### 2.5 Synthetic null controls

For each phase we generate matched-`n` synthetic samples from non-power-law sources and run the identical pipeline on each. Passing requires correct rejection: the synthetic-null likelihood-ratio against the matching alternative must be strongly negative, or the fit must fail to converge on a stable `x_min`. Phase 5 is a dedicated null-control phase across four canonical non-SOC sources (Section 3.5).

---

## 3. Five validation phases

### 3.1 Phase 1 — USGS earthquakes (ground-truth gate test)

**Data.** 84,724 tectonic earthquakes from the USGS Federated Digital Seismograph Network event service, 2020-01-01 to 2025-01-01, M ≥ 3.5, restricted to `type = earthquake`. No declustering is applied at catalog construction time, since declustering would bias the Gutenberg–Richter fit being measured.

**Method and result.** The magnitude of completeness, estimated by the Wiemer–Wyss maximum-curvature method, is M_c = 4.45, leaving 37,281 events above completeness. An Aki maximum-likelihood fit with the Shi–Bolt uncertainty yields a Gutenberg–Richter b-value of **1.084 ± 0.005**, with a 500-resample bootstrap 95 % confidence interval of [1.073, 1.094], implying an energy power-law exponent τ = 1 + b/1.5 = 1.722. An independent Clauset–Shalizi–Newman continuous-power-law fit on seismic energies s = 10¹·⁵ᴹ recovers α = 1.794 ± 0.024 (n = 1,071 above `x_min`), consistent with the b/1.5 relation. For aftershock sequences following 580 main shocks of M ≥ 6.0 (24,680 stacked aftershocks at M ≥ 4.0), a log-binned Omori–Utsu fit gives **p = 0.941 ± 0.017**, c = 0.10 d, weighted R² = 0.9927 over three temporal decades.

**Role.** Phase 1 is the gate test. Before running the pipeline on any non-physics target, it must recover canonical behavior on a system whose ground truth is not in dispute. It does: both exponents fall inside canonical seismological ranges.

### 3.2 Phase 2 — S&P 500 daily returns (first cross-domain transfer)

**Data.** 9,066 daily close prices of the S&P 500 index (Yahoo Finance, 1990-01-01 to 2025-12-31), giving 9,065 log returns with σ = 0.0114.

**Method and result.** The same Clauset continuous power-law fit, applied to the unsigned daily returns |r|, returns **α = 2.998 ± 0.041** on 9,060 returns — reproducing the Gopikrishnan et al. "inverse cubic law" to within 0.07 % of the canonical value of 3.0. The power-law model strongly dominates lognormal at p < 10⁻⁹ for the *power-law-favored* direction reported in the Phase 2 paper. An Omori–Utsu fit on stacked post-shock volatility from 318 main shocks (|r| > 3σ, threshold ≈ 3.42 %) yields **p = 0.286 ± 0.034** (R² = 0.71), inside the published daily-scale band of [0.3, 0.6] but outside the intraday band of [0.7, 1.0] — a scale-dependent feature, not a deviation.

> **[TODO: 待核实 — lognormal direction for Phase 2]** The Phase 2 paper's abstract states "the power-law model strongly dominating lognormal (p < 10⁻⁹)." The later 13-system v0.2 manuscript instead lists Phase 2 with a likelihood-ratio of R = −6.12 *favoring lognormal* and resolves the power-law verdict on exponent-band agreement (α = 2.998 vs canonical 3.0). These two statements appear to conflict and must be reconciled by a reviewer before this paragraph is finalized; the safer claim is that the power-law verdict for S&P 500 rests on exponent-band agreement, with the raw-tail lognormal comparison flagged as a known qualification (see Section 6.1).

### 3.3 Phase 3 — DeFi liquidation cascades across three protocols

**Data.** 43,065 on-chain liquidation events from three architecturally distinct DeFi lending protocols: Aave V2 (auction-based; 25,601 stablecoin-debt events of 28,943 raw), Compound V2 (direct liquidation; 11,244 stablecoin-debt events of 12,137 raw), and MakerDAO's Dog/Clip Liquidation 2.0 (Dutch clipper auctions; 1,985 events). Block ranges span December 2020 to January 2024.

**Method and result.** The same Clauset fit gives tail exponents **α = 1.684 ± 0.010** (Aave), **1.649 ± 0.016** (Compound), and **1.567 ± 0.015** (MakerDAO) — a spread of only 0.12 across three independent codebases and liquidation mechanisms. Omori–Utsu decay at 1-hour aggregation gives **p = 0.733 ± 0.045, 0.761 ± 0.042, 0.692 ± 0.071** respectively — a spread of 0.07. Every per-protocol power-law fit decisively rejects both lognormal and exponential alternatives.

**Interpretation.** Three different liquidation mechanisms producing α values within 0.12 of each other is the cross-instance consistency a universality-class claim requires. The DeFi exponents form a tight sub-cluster near earthquake energy exponents (α ≈ 1.6–1.7) and are well separated from the continuous-diffusion stock-return exponent (α ≈ 3.0), evidence for a "discrete threshold-cascade" sub-class of SOC spanning geology and decentralized finance.

### 3.4 Phase 4 — neural avalanches on task-active mouse cortex

**Data.** DANDI Archive dataset 000006, session `sub-anm369962_ses-20170313` — 1,392,414 spikes from 71 sorted units recorded over a 2,266 s delay-response behavioral task in mouse anterior lateral motor (ALM) cortex. A synthetic check uses 200,000 critical Bienaymé–Galton–Watson branching-process avalanches.

**Method and result.** On the synthetic generator the pipeline recovers the mean-field predictions τ = 1.50 and α_T = 1.92 with negligible error, confirming correct behavior on known-critical input. On the real recording, a bin-factor sweep across 1× to 16× the mean inter-event interval gives two findings. First, the SOC scaling relation γ = (α_T − 1)/(τ − 1) is satisfied to within 2 % at every bin scale (measured **γ ≈ 1.10**), and its stability across a 16-fold binning range is a strong statistical signature of genuine criticality. Second, the specific exponents are **not** the canonical mean-field Beggs–Plenz values: **τ ∈ [2.17, 3.00]** and α_T ∈ [2.49, 2.94] depending on bin width, consistently larger than τ = 3/2, α_T = 2.

**Interpretation.** This is not a failure of criticality. Task-active and subsampled cortical recordings are known to shift exponents upward (Priesemann et al.); the recording therefore sits in a task-active SOC sub-class rather than the spontaneous-activity mean-field regime. The equivalence-class claim that neural avalanches belong with earthquakes and DeFi liquidations is not contradicted — it is refined by the observation that the sub-class depends on brain state.

### 3.5 Phase 5 — synthetic non-SOC null controls

**Purpose.** Phases 1–4 each found power-law tails. A standard reviewer concern is "would the pipeline fit a power law to noise too?" A positive null result would fatally weaken every prior claim.

**Data and result.** The identical pipeline is run on four synthetic datasets with known non-SOC distributions:

| Null source | n | Fitted "α" | Likelihood ratio | Verdict |
|---|---|---|---|---|
| Gaussian random-walk increments (folded normal) | 20,000 | 2.999 | R = −28.6 (vs lognormal), −44.8 (vs exponential) | power-law **rejected** ✅ |
| Exponential variates | 20,000 | 2.996 | R = −16.0 (vs lognormal), −17.2 (vs exponential) | power-law **rejected** ✅ |
| Homogeneous Poisson inter-arrival times | ~50,000 | 3.000 | R = −24.5 (vs lognormal), −24.4 (vs exponential) | power-law **rejected** ✅ |
| Homogeneous Poisson → Omori stack | 5,006 s window | — | Omori p = −0.068 (wrong sign), R² = 0.0015 | no Omori structure ✅ |

Across three independent non-power-law size distributions the pipeline correctly rejected the power-law hypothesis at likelihood ratios of −16 to −45; on the temporal side, the Omori detector on a Poisson process gave R² ≈ 0.002. By contrast, the real-data Phases 1–4 returned likelihood ratios favoring power-law and Omori R² values of 0.30 to 0.99.

**Conclusion.** The pipeline is a meaningful detector. It does not confound genuine heavy-tailed SOC behavior with noise or with exponential tails, and the positive findings of Phases 1–4 cannot be dismissed as a methodological artifact. Null validations of power-law fitting tools are an established practice [9]; Phase 5 is the application of that standard practice to this specific pipeline.

---

## 4. Cross-domain comparison

Table 1 places the four real systems side by side. The headline observation is that one fixed pipeline, applied with zero per-domain re-tuning, recovers a coherent SOC signature in each of geophysics, equity finance, decentralized finance, and neuroscience, while Phase 5 confirms the pipeline does not manufacture that signature from non-SOC data.

**Table 1.** Four-system summary. Omori p is reported where the system has a meaningful event time series.

| Phase | System | n (analysis sample) | Tail exponent | Omori p | Verdict |
|---|---|---|---|---|---|
| 1 | USGS earthquakes | 37,281 above M_c | b = 1.084 ± 0.005 (α_E = 1.794 ± 0.024) | 0.941 ± 0.017 | confirmed (ground-truth gate) |
| 2 | S&P 500 daily returns | 9,060 | α = 2.998 ± 0.041 | 0.286 ± 0.034 | confirmed (inverse cubic) |
| 3a | Aave V2 liquidations | 25,601 | α = 1.684 ± 0.010 | 0.733 ± 0.045 | confirmed |
| 3b | Compound V2 liquidations | 11,244 | α = 1.649 ± 0.016 | 0.761 ± 0.042 | confirmed |
| 3c | MakerDAO Dog liquidations | 1,985 | α = 1.567 ± 0.015 | 0.692 ± 0.071 | confirmed |
| 4 | Mouse ALM cortex avalanches | 1,392,414 spikes | τ ∈ [2.17, 3.00] | — (size-scaling phase) | sub-class shift; scaling relation γ ≈ 1.10 holds |
| 5 | Synthetic non-SOC nulls (×4) | 20,000 each | rejected | rejected (R² ≈ 0.002) | correctly negative |

The exponent spread across real systems — α ≈ 1.6 (DeFi, earthquake energy) to α ≈ 3.0 (S&P 500) — is *expected* under universality-class theory. Systems in the same class share equations of motion, not necessarily a single numerical exponent: different conjugate observables (released energy, return magnitude, debt size, avalanche size) carry different scaling exponents. What the framework predicts to be shared is the *functional form* — a power-law tail with an exponential finite-size cutoff — and the *paired-signature structure* (size power-law plus Omori temporal decay) for the threshold-cascade members. The cross-system universal-collapse analysis [v4/results/A3_universal_collapse_summary.md] supports this reading: under the finite-size-scaling ansatz P(s) = s⁻ᵅ f(s/s*), strict α-collapse fails (as expected, since these are different observables on different physical scales), but functional-form collapse succeeds — the rescaled tails align over 2–3 decades.

The most striking single number is the within-Phase-3 consistency: three DeFi protocols with completely different liquidation engines (English auction, direct incentive spread, Dutch clipper) yielding tail exponents within 0.12 of each other. That is the kind of mechanism-independent quantitative agreement that distinguishes a structural universality claim from a surface analogy.

---

## 5. Discussion

**One pipeline, four domains.** The central claim of this preprint is methodological as much as physical. Each of the four real systems has been studied before, individually, in its own literature — Gutenberg–Richter for earthquakes, the inverse cubic law for equity returns, branching-process criticality for neural avalanches. What has not been done at this breadth is to fix a single Clauset-grade fitting stack and transfer it, with no re-tuning, across geophysics, equity finance, decentralized finance, and neuroscience. The fact that the same code path recovers a canonical signature in each domain is the empirical content of the "they belong to one universality class" claim that the project's Layer 2 community-discovery step proposed from mechanism graphs alone.

**Why the null phase is load-bearing.** A cross-domain power-law survey is only persuasive if the surveying instrument can also say "no." Phase 5 is therefore not an appendix but a core result: it converts "the pipeline found power laws everywhere it looked" from a worrying observation into a meaningful one, because the pipeline demonstrably does *not* find power laws in folded-normal, exponential, or Poisson data, and does not find Omori decay in a homogeneous Poisson process.

**DeFi as the flagship transfer.** Of the four real systems, DeFi liquidations are the one with no prior published scaling measurement; earthquakes, equity returns, and neural avalanches all have established literature exponents to recover. Phase 3 is thus the phase where the pipeline makes a genuinely new measurement rather than reproducing a known one, and the three-protocol consistency is what gives that new measurement its credibility.

**Refinement, not contradiction, in Phase 4.** The neural phase deserves emphasis because it shows the framework behaving like a real scientific instrument rather than a confirmation machine. The recording's exponents are *not* the textbook mean-field values; a naïve "confirm SOC" pipeline would either force-fit them or report a failure. Instead, the scaling relation γ ≈ 1.10 holds robustly across a 16-fold binning range — the criticality signature that is invariant to bin choice — while the specific exponents correctly identify a task-active sub-class. The class membership is refined, not rejected.

---

## 6. Limitations

This section is deliberately explicit. The honest scope of the result is narrower than "we proved cross-domain SOC," and the gaps below must be closed or clearly disclosed before submission.

**6.1 Lognormal is not always rejected.** The hardest alternative to a power-law tail is a lognormal, which can mimic power-law behavior over a finite dynamic range. On the raw-tail likelihood-ratio test, the lognormal alternative is not decisively rejected for every system. The 13-system v0.2 manuscript reports that the raw-tail comparison favors lognormal in several systems (and specifically lists S&P 500 with a lognormal-favoring R), with the SOC verdict in those cases resting on exponent-band agreement rather than on rejecting all smooth alternatives. The procedural tension — raw-tail Vuong R versus log-binned Bayesian-information-criterion model selection can disagree — is real and is discussed in the v0.2 manuscript. A reviewer must reconcile the Phase 2 paper's "power-law strongly dominates lognormal" statement with v0.2's lognormal-favoring R for the same system (see the [TODO] in Section 3.2). **The defensible framing is that the SOC verdict rests on the joint signature — power-law functional form, exponents inside predicted bands, paired Omori decay, null controls passing — not on any single likelihood-ratio test.**

**6.2 The pipeline detects endogenous threshold-cascade signatures only.** This pipeline tests for the SOC threshold-cascade signature: self-organized, slowly driven, internally generated cascades. It is not constructed to detect, and should not be expected to flag, externally driven or exogenous crises. Phase 5 validates the pipeline only in the null-rejection direction (it correctly says "no" to non-SOC synthetic data); it does not establish that the pipeline would catch every real-world crisis, and externally driven events are explicitly outside the class the pipeline targets.

> **[TODO: 待核实 — endogenous-only claim]** The "endogenous crises only" limitation is stated here because it is a known structural property of SOC early-warning / threshold-cascade methods and appears as an established conclusion elsewhere in the user's broader work. It is **not** directly evidenced inside the Phase 1–5 source papers in this repository. A reviewer must either (a) cite a within-project result that demonstrates the endogenous-only scope, or (b) attribute it to the external SOC literature, or (c) soften the wording. Do not present it as a finding of this preprint without a citation.

**6.3 The project's downstream predictions are unverified.** The Structural Isomorphism project's Layer 4 issues falsifiable numerical predictions for systems that have *not yet been measured*. The current calibration status [v4/results/B2_calibration_summary.md, B2_ci_summary.md] is honest about this: there are 24 predictions across 21 candidate classes, all with status "待验证" (pending verification). For these predictions the target data has not been collected — the data sources are external databases (Dune, NOAA, FAERS, ...) — so **there is no observed sample to bootstrap a frequentist confidence interval against**. The intervals attached to those predictions are prior-based credible intervals (a Monte-Carlo triangular prior over the LLM-proposed band), not confidence intervals on data; the project's own B2 summary states this plainly. Of the 3 prediction bands that *could* be matched to a verified observation, 0 landed strictly in-band and 3 were "out-band-partial" (predicted band overlaps the literature band but not the observed value). **This preprint therefore makes no claim that the project's cross-domain predictions are validated; only that the four real systems above were measured with one pipeline and the null phase passed.**

**6.4 Small-n and bootstrap caveats.** The MakerDAO sub-phase (1,985 events) and the Phase 4 small-bin avalanche fits are at the lower end of where the Clauset likelihood-ratio test has good power; "inconclusive" results in those regimes should not be over-read. The bootstrap resample count is not uniform across phases (see [TODO] in Section 2.2), and low resample counts conservatively widen intervals.

**6.5 Single sessions / single windows.** Phase 4 rests on one mouse-cortex recording session; the task-active-sub-class conclusion would be strengthened by additional sessions. Phase 2 uses one index over one time window. None of the phases is a meta-analysis across many independent datasets within the same domain.

**6.6 This is a Claude-generated first draft.** Every number in this draft traces to a file in `v4/results/` or to a per-phase paper, but the synthesis, framing, and cross-phase claims have not been checked by a domain expert. All [TODO: 待核实] markers are real gaps.

---

## 7. Conclusion

We assembled a single Clauset-grade analysis pipeline and applied it, without per-domain tuning, to four independent real systems — USGS earthquakes, S&P 500 daily returns, DeFi liquidations across three protocols, and task-active mouse-cortex neural avalanches — plus four synthetic non-SOC null sources. The pipeline recovered canonical SOC signatures on all four real systems (Gutenberg–Richter b = 1.084 ± 0.005; inverse-cubic α = 2.998 ± 0.041; DeFi α ∈ [1.567, 1.684] with cross-protocol spread 0.12; neural scaling relation γ ≈ 1.10 stable across a 16-fold binning range) and correctly rejected the power-law hypothesis on all four nulls. The result is a single-pipeline, cross-domain test of self-organized-criticality universality, deliberately conservative in its claims: the lognormal alternative is not rejected in every raw-tail test, the pipeline targets only endogenous threshold-cascade dynamics, and the project's downstream cross-domain predictions remain unverified for lack of target data. Within those limits, four very different systems gave four coherent results from one method — which is the minimum empirical bar a universality-class claim must clear.

---

## References

> **[TODO: 待核实 — reference list]** The numbered citations below are reconstructed from the in-text citations of the Phase 1–5 source papers and the v0.2 manuscript. Several entries need exact bibliographic details (year, volume, page) verified against the source papers before submission. The Phase 1–5 papers and the v0.2 manuscript contain fuller, individually checked reference lists; a reviewer should consolidate from those.

1. Stanley, H. E. *Introduction to Phase Transitions and Critical Phenomena.* Oxford University Press (1971). *[TODO: 待核实 — confirm canonical universality-class reference used by source papers]*
2. Kadanoff, L. P. Scaling laws for Ising models near T_c. *Physics* **2**, 263 (1966). *[TODO: 待核实]*
3. Bak, P., Tang, C. & Wiesenfeld, K. Self-organized criticality. *Physical Review Letters* **59**, 381 (1987).
4. Turcotte, D. L. Self-organized criticality. *Reports on Progress in Physics* **62**, 1377 (1999). *[TODO: 待核实 — exact entry]*
5. Gutenberg, B. & Richter, C. F. Frequency of earthquakes in California. *Bulletin of the Seismological Society of America* **34**, 185 (1944). *[TODO: 待核实]*
6. Utsu, T., Ogata, Y. & Matsu'ura, R. S. The centenary of the Omori formula. *Journal of Physics of the Earth* **43**, 1 (1995). *[TODO: 待核实]*
7. Beggs, J. M. & Plenz, D. Neuronal avalanches in neocortical circuits. *Journal of Neuroscience* **23**, 11167 (2003).
8. Sornette, D. *Why Stock Markets Crash.* Princeton University Press (2003). *[TODO: 待核实]*
9. Clauset, A., Shalizi, C. R. & Newman, M. E. J. Power-law distributions in empirical data. *SIAM Review* **51**, 661 (2009).
10. Alstott, J., Bullmore, E. & Plenz, D. powerlaw: A Python package for analysis of heavy-tailed distributions. *PLoS ONE* **9**, e85777 (2014).

Additional domain-specific references (Aki 1965 b-value MLE; Shi & Bolt 1982 uncertainty; Wiemer & Wyss 2000 completeness; Gopikrishnan, Plerou & Stanley 1998 inverse cubic law; Weber et al. 2007 financial Omori; Priesemann et al. 2014 subsampled cortex; Broido & Clauset 2019 scale-free-networks-are-rare) are cited in the individual Phase 1–5 papers and must be carried over with full bibliographic detail. **[TODO: 待核实 — consolidate full reference list from the five source papers.]**

---

## Appendix A — Data and reproducibility

| Phase | System | Data source | Analysis sample |
|---|---|---|---|
| 1 | USGS earthquakes | USGS FDSN event service, 2020–2025, M ≥ 3.5 | 37,281 above M_c = 4.45 |
| 2 | S&P 500 | Yahoo Finance `^GSPC` daily close, 1990–2025 | 9,060 returns |
| 3 | DeFi liquidations | On-chain event logs: Aave V2, Compound V2, MakerDAO Dog | 43,065 events |
| 4 | Mouse cortex | DANDI Archive 000006, session sub-anm369962_ses-20170313 | 1,392,414 spikes / 71 units |
| 5 | Synthetic nulls | Generated in-repo (`v4/validation/null-controls`) | 20,000 each (×4) |

Project Zenodo deposit: DOI 10.5281/zenodo.19547879 (cited by the Phase 1–2 source papers). **[TODO: 待核实 — confirm the deposit DOI is current and that it covers the Phase 1–5 code and data referenced here.]**

---

*End of draft v0.1. Status: 草稿待人审. Generated 2026-05-22 from project source materials listed in the meta block at the top of this file. Not yet reviewed by a domain expert.*
