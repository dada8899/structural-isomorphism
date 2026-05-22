<!--
====================================================================
META — C1 unified preprint draft
Version:  v0.2
Date:     2026-05-22
Status:   草稿待人审 (DRAFT — pending human review before any submission)
Roadmap:  v4-next-roadmap-2026-05-13 §C "维度 C：学术发表" item C1
Scope:    "合成 unified preprint" — synthesize Phase 1-5 (five-system SOC
          core) into a single arXiv-style preprint. C1 ships as the
          FOCUSED five-system SOC paper (see §1, scope decision). The
          broader 13-system manuscript (unified-pipeline-v0.2-2026-05-13)
          is a separate sibling paper, not superseded by or merged into
          this one.

v0.1 -> v0.2 CHANGELOG (this revision closes the seven [TODO 待核实]
markers that v0.1 carried; remaining unresolved items are人工确认项
collected in the Pre-submission checklist at the end):
  1. Scope decision (v0.1 §1 TODO) — RESOLVED. C1 is defined as the
     focused five-system SOC paper; the 13-system manuscript is named
     as a separate sibling work. The TODO is removed; the decision and
     its rationale are now stated in §1.
  2. Pipeline path / version (v0.1 §2 TODO) — RESOLVED against the
     actual repository. v0.1 repeated the 13-system manuscript's claim
     of "v4/lib/soc_pipeline.py, 339 lines, commit 7ee228c". Direct
     inspection shows v4/lib/soc_pipeline.py is now a 75-line
     DEPRECATION SHIM that re-exports the standalone `soc-pipeline`
     package (packages/soc-pipeline/, version 0.1.0, MIT). The
     authoritative implementation is the package; §2 now states this
     accurately and flags the provenance caveat.
  3. Bootstrap resample count (v0.1 §2.2 TODO) — RESOLVED. Only Phase 1
     uses a bootstrap (500 resamples, b-value). Phases 2-4 source
     papers do not bootstrap at all; their alpha uncertainties are the
     Clauset/Hill analytic standard error. §2.2 + Table A2 now state
     this per-phase instead of guessing a uniform count.
  4. Phase 2 lognormal direction (v0.1 §3.2 TODO) — RESOLVED. The
     arxiv-02 paper's own Table 1 reports R = -6.12, p = 9.3e-10 for
     power-law-vs-lognormal. In the Clauset convention a NEGATIVE R
     favors the SECOND model — i.e. lognormal is favored, not the
     power law. The arxiv-02 abstract/prose ("power-law strongly
     dominates lognormal") is an internal sign-interpretation error in
     that paper. §3.2 + §6.1 now state the correct direction.
  5. Endogenous-only limitation (v0.1 §6.2 TODO) — RESOLVED. The Phase
     1-5 source papers contain NO within-project evidence for an
     "endogenous crises only" scope. It is reframed as a known
     structural property of SOC threshold-cascade methods, attributed
     to the external SOC literature, and the wording is softened so it
     is not presented as a finding of this preprint.
  6. Reference list (v0.1 §References TODO) — RESOLVED. The reference
     list is now consolidated and de-duplicated from the five source
     papers' own (individually checked) bibliographies. Entries that
     could not be cross-verified within this repository are marked
     [待核] inline.
  7. Zenodo DOI (v0.1 Appendix A TODO) — NOT resolvable offline.
     Carried forward as an explicit pre-submission人工确认项 (see the
     checklist at the end). The DOI is shown but flagged.

DATA SOURCES (every number in this draft traces to one of these five
arXiv-version source papers plus the 13-system manuscript for
cross-checking; no number is invented):
  - web/.../papers/arxiv-01_earthquake_soc-2026-05-13.md        (Phase 1)
  - web/.../papers/arxiv-02_stockmarket_inverse_cubic-2026-05-13.md (Phase 2)
  - web/.../papers/arxiv-03_defi_cross_protocol-2026-05-13.md   (Phase 3)
  - web/.../papers/arxiv-04_neural_avalanches-2026-05-13.md     (Phase 4)
  - web/.../papers/soc-null-2026-04-16.md                       (Phase 5)
  - web/.../papers/unified-pipeline-v0.2-2026-05-13.md  (13-system sibling, cross-check only)
  - packages/soc-pipeline/  + v4/lib/soc_pipeline.py    (pipeline provenance)

This is a Claude-generated draft. It has NOT been reviewed by a domain
expert. Every remaining人工确认项 is collected in the Pre-submission
checklist at the end of this file.
====================================================================
-->

***REMOVED*** A pipeline for cross-domain validation of self-organized criticality: five systems, one method

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. Project site: https://structural.bytedance.city.
**Version.** v0.2 unified preprint draft (Phase 1–5 synthesis). **Date.** 2026-05-22.
**Status.** Draft — pending human review.
**Keywords.** self-organized criticality; cross-domain validation; power-law; Gutenberg–Richter; Omori–Utsu; inverse cubic law; neural avalanches; null control; universality class; reproducibility.

---

***REMOVED******REMOVED*** Abstract

A universality-class membership claim has empirical content only if a single, fixed analysis pipeline — applied with no per-domain tuning — recovers the predicted scaling signatures across systems drawn from very different domains, *and* correctly fails to find those signatures in matched non-class data. We assemble such a pipeline (Clauset–Shalizi–Newman 2009 maximum-likelihood power-law fitting with Kolmogorov–Smirnov-driven `x_min` selection, a likelihood-ratio test against lognormal and exponential alternatives, and Omori–Utsu temporal-decay stacking) into one shared Python package and apply it unchanged to five independent systems: USGS tectonic earthquakes (Phase 1), S&P 500 daily returns (Phase 2), DeFi liquidation cascades across three protocols (Phase 3), task-active mouse-cortex neural avalanches (Phase 4), and a set of four synthetic non-self-organized-criticality (non-SOC) null sources (Phase 5). On real data the pipeline recovers canonical exponents: a Gutenberg–Richter b-value of 1.084 ± 0.005 on 37,281 earthquakes above the completeness magnitude (Omori p = 0.941 ± 0.017); an inverse-cubic tail exponent α = 2.998 ± 0.041 on 9,060 S&P 500 daily returns; tail exponents α ∈ [1.567, 1.684] across 43,065 on-chain DeFi liquidations spanning three architecturally distinct lending protocols (Omori p ∈ [0.69, 0.76]); and, on 1.39 M mouse-cortex spikes, a self-organized-criticality scaling relation satisfied to within 2 % at every bin scale (measured γ ≈ 1.10) although the recording's specific exponents (τ ∈ [2.17, 3.00]) place it in a task-active sub-class rather than the canonical mean-field regime. All four synthetic non-SOC nulls (folded normal, exponential, Poisson inter-arrival, Poisson Omori) are correctly rejected, with power-law-vs-alternative likelihood ratios of −16 to −45 and an Omori-fit R² ≈ 0.002 — ruling out the trivial failure mode "the pipeline fits everything as a power law." We report three qualifications honestly. (i) The lognormal alternative is not rejected in every raw-tail test: in particular, for S&P 500 the raw-tail likelihood ratio favors lognormal (R = −6.12), and the SOC verdict for that system rests on exponent-band agreement (α = 2.998 vs the canonical 3.0) rather than on rejecting the lognormal. (ii) The pipeline is constructed to detect *endogenous* threshold-cascade signatures and — as is a known property of SOC threshold-cascade methods — is not expected to flag externally driven crises (Phase 5 validates only the null-rejection direction). (iii) The project's downstream cross-domain *predictions* (Layer 4) remain unverified — their target data has not been collected, so we can give only prior-based credible intervals, not frequentist confidence intervals on observed data. Within those limits, the joint result is an internally consistent, single-pipeline cross-domain test of self-organized-criticality universality across geophysics, equity finance, decentralized finance, and neuroscience.

---

***REMOVED******REMOVED*** 1. Introduction

Universality classes are the sharpest tool statistical physics offers for cross-system comparison: two systems in the same class share a small set of critical exponents that are independent of microscopic detail [1, 2]. The concept was extended from equilibrium critical phenomena to non-equilibrium dynamics through the theory of self-organized criticality (SOC) of Bak, Tang, and Wiesenfeld [3], in which slowly driven threshold-cascade systems generically exhibit power-law event-size distributions, Omori-like temporal relaxation, and associated scaling relations without parameter tuning. Tectonic seismicity is the canonical natural realization [3, 4], and the Gutenberg–Richter and Omori–Utsu laws [5, 6] are its most widely reproduced quantitative signatures. Beggs and Plenz [7] opened the biological side of the class with cortical avalanches showing P(s) ∝ s⁻³ᐟ² and P(T) ∝ T⁻². Sornette [8] extended the picture to financial cascades.

The empirical literature contains many single-system measurements but few cross-system comparisons that use one fixed fitting stack. Clauset, Shalizi, and Newman [9] argued that standard estimators — binned-histogram slope fits, naive `x_min` choices — were producing falsely confident power-law conclusions, and that canonical examples deserved re-testing under maximum-likelihood-plus-Kolmogorov–Smirnov estimation with explicit comparison to alternatives. Subsequent practice tightened the floor: a defensible power-law claim today requires a Clauset maximum-likelihood fit with a reported `x_min`, a likelihood-ratio test against at least lognormal and exponential, and a null-control check. Most cross-domain SOC studies do not meet this standard; the typical paper is one system deep.

The Structural Isomorphism project is an attempt to make cross-domain "same mathematical structure" claims operational. Its layered pipeline (i) builds a domain-agnostic catalog of candidate systems and observables, (ii) groups them into candidate equivalence classes from mechanism graphs, (iii) extracts shared invariants for each class, and (iv) issues falsifiable numerical predictions. The Layer 1/2 community-discovery step found that a single self-organized-criticality "threshold-cascade" cluster emerged unsupervised from the project's pair data — the largest community in the graph, with earthquakes, DeFi liquidations, bank runs, flash crashes, power-grid cascades, and neural avalanches all assigned to it. The present paper is the empirical validation step for that cluster's core members.

This paper synthesizes the project's first five validation phases into a single preprint. The contributions are:

1. **A single fixed pipeline across four real systems.** We re-fit power-law tails and, where applicable, Omori temporal decay on USGS earthquakes (Phase 1), S&P 500 daily returns (Phase 2), three DeFi lending protocols (Phase 3 — Aave V2, Compound V2, MakerDAO), and mouse-cortex neural avalanches (Phase 4), all through the same code path with no per-domain parameter tuning.
2. **Null robustness.** Phase 5 runs the identical pipeline on four synthetic non-SOC sources and verifies they are all correctly rejected, ruling out "the pipeline fits everything" as a trivial explanation for the positive findings.
3. **An honest accounting of what the pipeline does and does not establish** — including the lognormal-not-always-rejected qualification, the endogenous-only scope, and the unverified status of the project's downstream predictions.

**Scope decision: this is the focused five-system SOC paper.** The Structural Isomorphism project has produced two manuscript lines at different breadths. The present paper is the *focused* synthesis of the five-system SOC core (Phases 1–5: four real threshold-cascade systems plus the synthetic null phase). A separate, broader manuscript — `unified-pipeline-v0.2-2026-05-13`, here referred to as the *thirteen-system sibling paper* — applies the same methodological framework to thirteen systems across five distinct universality-class parents (adding preferential attachment, Motter–Lai network cascade, Preisach hysteresis, and Scheffer fold-bifurcation phases). The roadmap C1 item is explicitly titled "*N systems, one method*" and scoped to the five-system SOC core, so C1 ships as **this focused paper**. The thirteen-system sibling is *not* superseded by, nor merged into, this paper: the two have different theses (this paper: one SOC universality class verified deeply across four real domains plus a null; the sibling: one *methodological framework* shown to be portable across five class families). They share the Phase 1–4 numbers, and this paper is kept numerically consistent with the sibling. A reviewer may decide at submission time whether to post both, or only the focused one; that is an editorial choice, not an unresolved methodological gap. (For traceability of v0.1→v0.2 changes see the META block at the top of this file.)

The paper is organized as follows. Section 2 specifies the shared pipeline. Section 3 reports the five phases. Section 4 places the four real systems side by side. Section 5 discusses the cross-domain picture. Section 6 states the limitations explicitly. Section 7 concludes.

---

***REMOVED******REMOVED*** 2. The shared pipeline

The shared analysis stack is implemented as one Python package and exposed to every phase as a small set of functions. The pipeline is intentionally minimal: each step corresponds to a single published estimator, the parameters are fixed across phases, and the only domain-specific code lives in the per-phase data loaders. No phase modifies the pipeline; no phase tunes a fitting parameter; no phase adds a domain-specific prior.

**Implementation and provenance.** The authoritative implementation is the standalone Python package `soc-pipeline` (version 0.1.0, MIT licence), located at `packages/soc-pipeline/` in the project repository. It is split into one module per analytical operation: `fit.py` (Clauset maximum-likelihood power-law fit), `bootstrap.py` (bootstrap confidence intervals), `lr_test.py` (likelihood-ratio tests), `omori.py` (Omori–Utsu stacking and fitting), `null_controls.py` (synthetic null generators), `b_value.py` (Aki maximum-likelihood b-value), `universal_collapse.py`, and supporting utilities; it depends only on `numpy`, `scipy`, `pandas`, and `powerlaw`. A legacy path `v4/lib/soc_pipeline.py` is retained for backward compatibility, but it is now a thin (≈75-line) deprecation shim that re-exports the package and emits a `DeprecationWarning`; it is *not* the implementation. We note one provenance caveat the reviewer should be aware of: the thirteen-system sibling manuscript describes the pipeline as "`v4/lib/soc_pipeline.py`, 339 lines, frozen at commit `7ee228c`," a description that predates the extraction of the code into the `soc-pipeline` package and is no longer literally accurate for the current repository layout. The Phase 1–5 source papers (2026-04-15/16) predate the package extraction as well and describe the same *logical* pipeline through per-phase analysis scripts (e.g. `v4/validation/soc-stockmarket/fetch_and_analyze.py`, `v4/validation/null-controls/generate_and_analyze.py`) tagged per phase in the repository (`v4/phase1-earthquake-2026-04-15`, `v4/phase2-stockmarket-2026-04-15`, …). The logical pipeline is identical across all of these; before formal submission a reviewer should record one canonical commit hash or release tag of the `soc-pipeline` package against which the final numbers are confirmed (see the Pre-submission checklist).

***REMOVED******REMOVED******REMOVED*** 2.1 Clauset–Shalizi–Newman maximum-likelihood power-law fit

For each dataset we fit a continuous power-law p(s) ∝ s⁻ᵅ for s ≥ `x_min` using the Clauset–Shalizi–Newman estimator [9]. The lower cutoff `x_min` is selected automatically by minimizing the Kolmogorov–Smirnov distance between the empirical and fitted cumulative distribution functions on the candidate tail; α is then estimated by maximum likelihood (Hill-form estimator) on that tail. We use the Alstott–Bullmore–Plenz `powerlaw` library [10] as the canonical implementation, with the discrete-data option set only for explicitly integer-valued data (Phase 4 avalanche sizes and durations). For each fit we report α, the analytic (Hill-form) standard error σ(α), the fitted `x_min` in the domain's natural units, and the tail size `n_tail`.

***REMOVED******REMOVED******REMOVED*** 2.2 Uncertainty quantification and bootstrap

We report two kinds of uncertainty, and — importantly — *not every phase uses the same one*; the source papers differ here, and we state the per-phase situation explicitly rather than impose a false uniformity.

- **Phase 1 (earthquakes)** reports a bootstrap confidence interval *in addition to* the analytic Shi–Bolt b-value error: a 95 % bootstrap CI on the Gutenberg–Richter b-value from **500 resamples** with replacement of the events above M_c, recomputing the Aki maximum-likelihood estimator on each resample, with a fixed random seed (42) for bit-reproducibility. The reported CI is [1.073, 1.094].
- **Phases 2, 3, 4** (S&P 500, DeFi protocols, neural avalanches): the corresponding source papers do **not** report a bootstrap. The α uncertainties quoted for those phases (e.g. α = 2.998 ± 0.041, the DeFi α ± 0.010–0.016, the Phase 4 per-bin τ errors) are the **Clauset/Hill analytic standard error** returned by the `powerlaw` library, σ(α) ≈ (α − 1)/√n_tail, not bootstrap intervals. This is the standard analytic error for a Clauset maximum-likelihood fit.

For completeness we note that the `soc-pipeline` package does provide a `bootstrap_ci` routine (default 200 resamples, ≥200 recommended), and the thirteen-system sibling manuscript additionally reports 100-resample bootstrap CIs for its consolidated runs. But the Phase 1–5 numbers quoted in *this* paper are exactly as in the five source papers: bootstrap for Phase 1's b-value (500 resamples), analytic Hill error elsewhere. Appendix A, Table A2 lists the per-phase choice. A reviewer who wishes to report a uniform bootstrap CI for all four real phases would need to re-run Phases 2–4 through the package's `bootstrap_ci`; that is a possible methodological upgrade, not a correction of an error.

***REMOVED******REMOVED******REMOVED*** 2.3 Likelihood-ratio tests against alternatives

For each fit we compute the Clauset–Shalizi–Newman normalized log-likelihood ratio R against two alternatives — lognormal and exponential — with associated (Vuong-style) p-values [9]. In the Clauset convention, **a positive R favors the power-law and a negative R favors the alternative**; p < 0.05 indicates the preference is statistically distinguishable. Rejection of exponential is necessary but not sufficient for a power-law claim; the harder test is against lognormal, which can mimic a power-law tail over a finite dynamic range. Clauset et al. [9] caution that the likelihood-ratio test has limited power for small tails (n_tail < ~50), in which case "inconclusive" must not be read as evidence for either model. The sign convention matters: §3.2 and §6.1 below turn on it.

***REMOVED******REMOVED******REMOVED*** 2.4 Omori–Utsu temporal decay

Where a system has a meaningful event time series, we estimate temporal aftershock decay following the Omori–Utsu form n(t) = K / (t + c)ᵖ [6]. We identify a main-shock threshold by percentile or by a multiple of the standard deviation, stack post-trigger event counts across all main shocks in a forward window, log-bin the stack, and fit (p, c, K) by weighted log-log regression with c grid-searched. Goodness of fit is reported as a weighted R² in log space. Phase 4's avalanche-size observables are fitted for size scaling only; the Omori stack is not applied where the class makes no temporal-relaxation prediction.

***REMOVED******REMOVED******REMOVED*** 2.5 Synthetic null controls

For each phase we generate matched-`n` synthetic samples from non-power-law sources and run the identical pipeline on each. Passing requires correct rejection: the synthetic-null likelihood-ratio against the matching alternative must be strongly negative, or the fit must fail to converge on a stable `x_min`. Phase 5 is a dedicated null-control phase across four canonical non-SOC sources (Section 3.5).

---

***REMOVED******REMOVED*** 3. Five validation phases

***REMOVED******REMOVED******REMOVED*** 3.1 Phase 1 — USGS earthquakes (ground-truth gate test)

**Data.** 84,724 tectonic earthquakes from the USGS Federated Digital Seismograph Network (FDSN) event service, 2020-01-01 to 2025-01-01, M ≥ 3.5, restricted to `type = earthquake`. No declustering is applied at catalog construction time, since declustering would bias the Gutenberg–Richter fit being measured.

**Method and result.** The magnitude of completeness, estimated by the Wiemer–Wyss maximum-curvature method, is M_c = 4.45, leaving 37,281 events above completeness. An Aki maximum-likelihood fit with the Shi–Bolt uncertainty yields a Gutenberg–Richter b-value of **1.084 ± 0.005**, with a 500-resample bootstrap 95 % confidence interval of [1.073, 1.094], implying an energy power-law exponent τ = 1 + b/1.5 = 1.722. An independent Clauset–Shalizi–Newman continuous-power-law fit on seismic energies s = 10¹·⁵ᴹ recovers α = 1.794 ± 0.024 (n = 1,071 above `x_min`), consistent with the b/1.5 relation under Hanks–Kanamori scaling. For aftershock sequences following 580 main shocks of M ≥ 6.0 (24,680 stacked aftershocks at M ≥ 4.0), a log-binned Omori–Utsu fit gives **p = 0.941 ± 0.017**, c = 0.10 d, weighted R² = 0.9927 over three temporal decades.

**Role.** Phase 1 is the gate test. Before running the pipeline on any non-physics target, it must recover canonical behavior on a system whose ground truth is not in dispute. It does: both exponents fall inside canonical seismological ranges.

***REMOVED******REMOVED******REMOVED*** 3.2 Phase 2 — S&P 500 daily returns (first cross-domain transfer)

**Data.** 9,066 daily close prices of the S&P 500 index (`^GSPC`, Yahoo Finance via the `yfinance` package, 1990-01-01 to 2025-12-31), giving 9,065 log returns with σ = 0.0114 and range [−0.1277, +0.1096].

**Method and result.** The same Clauset continuous power-law fit, applied to the unsigned daily returns |r|, returns **α = 2.998 ± 0.041** on 9,060 returns (n_tail = 2,327 above `x_min` = 0.00998, a ≈1 % daily move) — reproducing the Gopikrishnan et al. "inverse cubic law" to within 0.07 % of the canonical value of 3.0. An Omori–Utsu fit on stacked post-shock volatility from 318 main shocks (|r| > 3σ, threshold ≈ 3.42 %) yields **p = 0.286 ± 0.034** (R² = 0.71), inside the published daily-scale band of [0.3, 0.6] but outside the intraday band of [0.7, 1.0] — a scale-dependent feature, not a deviation.

**Lognormal comparison — direction stated correctly.** The arxiv-02 source paper's Table 1 reports, for the power-law-vs-lognormal likelihood-ratio test, **R = −6.12, p = 9.3 × 10⁻¹⁰**. In the Clauset sign convention (§2.3) a *negative* R favors the *second* model — i.e. **the raw-tail likelihood-ratio test favors lognormal over the power law for S&P 500**, and the small p-value means that preference is statistically distinguishable, not marginal. We flag explicitly that the arxiv-02 paper's abstract and Section 3.1 prose state the opposite ("the power-law model strongly dominating lognormal, p < 10⁻⁹"); that prose is an *internal sign-interpretation error in the source paper* — it reads the small p-value as a power-law win while the accompanying R = −6.12 in its own Table 1 in fact records a lognormal win. The thirteen-system sibling manuscript reports the same R = −6.12 and reads it correctly as lognormal-favoring. **We therefore state the corrected direction here: for S&P 500 daily returns the raw-tail Vuong test favors lognormal; the SOC verdict for this system does not rest on rejecting the lognormal, but on exponent-band agreement** — the measured α = 2.998 lands essentially on the canonical inverse-cubic value of 3.0, inside one analytic standard error. The power-law-vs-exponential test for the same fit is inconclusive (R = −0.52, p = 0.60), as expected at n_tail ≈ 2,300 over a narrow dynamic range. The general implication of this — that a raw-tail lognormal comparison can favor lognormal without falsifying SOC membership — is discussed in §6.1.

***REMOVED******REMOVED******REMOVED*** 3.3 Phase 3 — DeFi liquidation cascades across three protocols

**Data.** 43,065 on-chain liquidation events from three architecturally distinct DeFi lending protocols: Aave V2 (auction-based; 25,601 stablecoin-debt events), Compound V2 (direct liquidation with incentive spread; 11,244 stablecoin-debt events), and MakerDAO's Dog/Clip Liquidation 2.0 (Dutch clipper auctions; 1,985 events). Block ranges span 2020 to 2024.

**Method and result.** The same Clauset fit gives tail exponents **α = 1.684 ± 0.010** (Aave), **1.649 ± 0.016** (Compound), and **1.567 ± 0.015** (MakerDAO) — a spread of only 0.12 across three independent codebases and liquidation mechanisms. Omori–Utsu decay at 1-hour aggregation gives **p = 0.733 ± 0.045, 0.761 ± 0.042, 0.692 ± 0.071** respectively (weighted R² ∈ [0.24, 0.36], lower than Phase 1 because DeFi event rates are sparse per hourly bin; the slope is nonetheless far from zero — at Compound the flat-rate null is rejected at ≈18σ). Every per-protocol power-law fit decisively rejects both lognormal and exponential alternatives (p < 10⁻⁹).

**Interpretation.** Three different liquidation mechanisms producing α values within 0.12 of each other is the cross-instance consistency a universality-class claim requires. With per-protocol σ(α) ≈ 0.010–0.016 the 0.12 spread is technically 7–12 standard errors — the three α values are *not* statistically identical, and the source paper does not claim they are — but the spread is small on any practical scale and well separated from the stock-return regime (α ≈ 3.0). The DeFi exponents form a tight sub-cluster near earthquake energy exponents (α ≈ 1.6–1.8), evidence for a "discrete threshold-cascade" sub-class of SOC spanning geology and decentralized finance.

***REMOVED******REMOVED******REMOVED*** 3.4 Phase 4 — neural avalanches on task-active mouse cortex

**Data.** DANDI Archive dataset 000006, session `sub-anm369962_ses-20170313` — 1,392,414 spikes from 71 sorted units recorded over a 2,266 s delay-response behavioral task in mouse anterior lateral motor (ALM) cortex. A synthetic check uses 200,000 critical Bienaymé–Galton–Watson branching-process avalanches.

**Method and result.** On the synthetic generator the pipeline recovers the mean-field predictions cleanly: τ = 1.497 (predicted 1.500), α_T = 1.917 (predicted 2.000), with the power-law form dominating lognormal (p = 7 × 10⁻¹⁶) and exponential for both P(s) and P(T). On the real recording, a bin-factor sweep across 1× to 16× the mean inter-event interval gives two findings. First, the SOC scaling relation γ = (α_T − 1)/(τ − 1) is satisfied to within 2 % at every bin scale (measured **γ ≈ 1.10**, with the weighted-regression fit at R² ≈ 0.998–0.999), and its stability across a 16-fold binning range is a strong statistical signature of genuine criticality. Second, the specific exponents are **not** the canonical mean-field Beggs–Plenz values: **τ ∈ [2.17, 3.00]** and α_T ∈ [2.49, 2.94] depending on bin width, consistently larger than τ = 3/2, α_T = 2.

**Interpretation.** This is not a failure of criticality. Task-active and subsampled cortical recordings are known to shift exponents upward (Priesemann et al.); the recording therefore sits in a task-active SOC sub-class rather than the spontaneous-activity mean-field regime. The equivalence-class claim that neural avalanches belong with earthquakes and DeFi liquidations is not contradicted — it is refined by the observation that the sub-class depends on brain state.

***REMOVED******REMOVED******REMOVED*** 3.5 Phase 5 — synthetic non-SOC null controls

**Purpose.** Phases 1–4 each found power-law tails. A standard reviewer concern is "would the pipeline fit a power law to noise too?" A positive null result would fatally weaken every prior claim.

**Data and result.** The identical pipeline is run on four synthetic datasets with known non-SOC distributions. As noted in §2.3, a *negative* R favors the alternative — so for these nulls, a strongly negative R is the *correct* (passing) outcome:

| Null source | n | Fitted "α" | Likelihood ratio | Verdict |
|---|---|---|---|---|
| Gaussian random-walk increments (folded normal) | 20,000 | 2.999 | R = −28.58 (vs lognormal), −44.76 (vs exponential) | power-law **rejected** ✅ |
| Exponential variates | 20,000 | 2.996 | R = −16.03 (vs lognormal), −17.17 (vs exponential) | power-law **rejected** ✅ |
| Homogeneous Poisson inter-arrival times | ~50,000 | 3.000 | R = −24.45 (vs lognormal), −24.39 (vs exponential) | power-law **rejected** ✅ |
| Homogeneous Poisson → Omori stack | 5,006 s window | — | Omori p = −0.068 (wrong sign), R² = 0.0015 | no Omori structure ✅ |

Across three independent non-power-law size distributions the pipeline correctly rejected the power-law hypothesis at likelihood ratios of −16 to −45; on the temporal side, the Omori detector on a homogeneous Poisson process gave R² ≈ 0.002. By contrast, the real-data Phases 1–4 returned likelihood ratios favoring power-law and Omori R² values of 0.24 to 0.99.

**Conclusion.** The pipeline is a meaningful detector. It does not confound genuine heavy-tailed SOC behavior with noise or with exponential tails, and the positive findings of Phases 1–4 cannot be dismissed as a methodological artifact. Null validations of power-law fitting tools are an established practice [9]; Phase 5 is the application of that standard practice to this specific pipeline.

---

***REMOVED******REMOVED*** 4. Cross-domain comparison

Table 1 places the four real systems side by side. The headline observation is that one fixed pipeline, applied with zero per-domain re-tuning, recovers a coherent SOC signature in each of geophysics, equity finance, decentralized finance, and neuroscience, while Phase 5 confirms the pipeline does not manufacture that signature from non-SOC data.

**Table 1.** Four-system summary. Omori p is reported where the system has a meaningful event time series.

| Phase | System | n (analysis sample) | Tail exponent | Omori p | Verdict |
|---|---|---|---|---|---|
| 1 | USGS earthquakes | 37,281 above M_c | b = 1.084 ± 0.005 (α_E = 1.794 ± 0.024) | 0.941 ± 0.017 | confirmed (ground-truth gate) |
| 2 | S&P 500 daily returns | 9,060 | α = 2.998 ± 0.041 | 0.286 ± 0.034 | confirmed on exponent band (raw-tail LR favors lognormal — see §3.2, §6.1) |
| 3a | Aave V2 liquidations | 25,601 | α = 1.684 ± 0.010 | 0.733 ± 0.045 | confirmed |
| 3b | Compound V2 liquidations | 11,244 | α = 1.649 ± 0.016 | 0.761 ± 0.042 | confirmed |
| 3c | MakerDAO Dog liquidations | 1,985 | α = 1.567 ± 0.015 | 0.692 ± 0.071 | confirmed |
| 4 | Mouse ALM cortex avalanches | 1,392,414 spikes | τ ∈ [2.17, 3.00] | — (size-scaling phase) | sub-class shift; scaling relation γ ≈ 1.10 holds |
| 5 | Synthetic non-SOC nulls (×4) | 20,000 each | rejected | rejected (R² ≈ 0.002) | correctly negative |

The exponent spread across real systems — α ≈ 1.6 (DeFi, earthquake energy) to α ≈ 3.0 (S&P 500) — is *expected* under universality-class theory. Systems in the same class share equations of motion, not necessarily a single numerical exponent: different conjugate observables (released energy, return magnitude, debt size, avalanche size) carry different scaling exponents. What the framework predicts to be shared is the *functional form* — a power-law tail with an exponential finite-size cutoff — and the *paired-signature structure* (size power-law plus Omori temporal decay) for the threshold-cascade members.

The most striking single number is the within-Phase-3 consistency: three DeFi protocols with completely different liquidation engines (English auction, direct incentive spread, Dutch clipper) yielding tail exponents within 0.12 of each other. That is the kind of mechanism-independent quantitative agreement that distinguishes a structural universality claim from a surface analogy.

---

***REMOVED******REMOVED*** 5. Discussion

**One pipeline, four domains.** The central claim of this preprint is methodological as much as physical. Each of the four real systems has been studied before, individually, in its own literature — Gutenberg–Richter for earthquakes, the inverse cubic law for equity returns, branching-process criticality for neural avalanches. What has not been done at this breadth is to fix a single Clauset-grade fitting stack and transfer it, with no re-tuning, across geophysics, equity finance, decentralized finance, and neuroscience. The fact that the same code path recovers a canonical signature in each domain is the empirical content of the "they belong to one universality class" claim that the project's Layer 2 community-discovery step proposed from mechanism graphs alone.

**Why the null phase is load-bearing.** A cross-domain power-law survey is only persuasive if the surveying instrument can also say "no." Phase 5 is therefore not an appendix but a core result: it converts "the pipeline found power laws everywhere it looked" from a worrying observation into a meaningful one, because the pipeline demonstrably does *not* find power laws in folded-normal, exponential, or Poisson data, and does not find Omori decay in a homogeneous Poisson process.

**DeFi as the flagship transfer.** Of the four real systems, DeFi liquidations are the one with no prior published scaling measurement; earthquakes, equity returns, and neural avalanches all have established literature exponents to recover. Phase 3 is thus the phase where the pipeline makes a genuinely new measurement rather than reproducing a known one, and the three-protocol consistency is what gives that new measurement its credibility.

**Refinement, not contradiction, in Phase 4.** The neural phase deserves emphasis because it shows the framework behaving like a real scientific instrument rather than a confirmation machine. The recording's exponents are *not* the textbook mean-field values; a naïve "confirm SOC" pipeline would either force-fit them or report a failure. Instead, the scaling relation γ ≈ 1.10 holds robustly across a 16-fold binning range — the criticality signature that is invariant to bin choice — while the specific exponents correctly identify a task-active sub-class. The class membership is refined, not rejected.

---

***REMOVED******REMOVED*** 6. Limitations

This section is deliberately explicit. The honest scope of the result is narrower than "we proved cross-domain SOC."

**6.1 Lognormal is not always rejected — and is favored for S&P 500.** The hardest alternative to a power-law tail is a lognormal, which can mimic power-law behavior over a finite dynamic range. On the raw-tail likelihood-ratio test, the lognormal alternative is not decisively rejected for every system; for S&P 500 daily returns it is in fact *favored* (R = −6.12, p = 9.3 × 10⁻¹⁰; see §3.2). The SOC verdict for that system rests on exponent-band agreement — α = 2.998 essentially on the canonical inverse-cubic 3.0 — not on rejecting the lognormal. We note this is consistent with a known procedural tension: the raw-tail Vuong likelihood ratio (sensitive to a small number of upper-tail individual events, where a lognormal can have a deeper finite-n tail) and log-binned model selection can disagree, and at tail sizes n_tail ∼ 10³–10⁴ the power-law-vs-lognormal distinction is partly procedural. The thirteen-system sibling manuscript discusses this at length and reports that, on a complementary log-binned Bayesian-information-criterion test, power-law-with-cutoff is preferred over lognormal in every system tested. **The defensible framing is that the SOC verdict rests on the joint signature — power-law functional form, exponents inside predicted bands, paired Omori decay, null controls passing — not on any single likelihood-ratio test.** The raw-tail lognormal result for S&P 500 is reported here as a real qualification, not hidden.

**6.2 The pipeline detects endogenous threshold-cascade signatures only.** This pipeline tests for the SOC threshold-cascade signature: self-organized, slowly driven, internally generated cascades. It is not constructed to detect, and should not be expected to flag, externally driven or exogenous crises. We state this as a *known structural property of SOC threshold-cascade analysis methods in general* — the SOC model class describes endogenously organized criticality, and a detector tuned to its power-law-plus-Omori signature has no sensitivity to a shock imposed from outside the system [3, 4; and the SOC monograph literature, e.g. Jensen 1998, Pruessner 2012, Turcotte 1999]. It is **not** a finding of the present preprint, and the Phase 1–5 source papers contain no within-project experiment that demonstrates an endogenous/exogenous discrimination. Phase 5 validates the pipeline only in the null-rejection direction (it correctly says "no" to non-SOC synthetic data); it does not establish that the pipeline would catch every real-world crisis, and externally driven events are explicitly outside the class the pipeline targets. A reviewer extending the discussion of this point should cite the external SOC literature, not this preprint.

**6.3 The project's downstream predictions are unverified.** The Structural Isomorphism project's Layer 4 issues falsifiable numerical predictions for systems that have *not yet been measured*. The current calibration status is honest about this: there are 24 predictions across 21 candidate classes, all with status "待验证" (pending verification). For these predictions the target data has not been collected — the data sources are external databases — so **there is no observed sample to bootstrap a frequentist confidence interval against**. The intervals attached to those predictions are prior-based credible intervals, not confidence intervals on data. **This preprint therefore makes no claim that the project's cross-domain predictions are validated; only that the four real systems above were measured with one pipeline and the null phase passed.**

**6.4 Small-n and uncertainty caveats.** The MakerDAO sub-phase (1,985 events) and the Phase 4 small-bin avalanche fits at 8×/16× binning (n ≈ 19,000–38,000 avalanches, σ(τ) up to ≈0.11) are at the lower end of where the Clauset likelihood-ratio test has good power; "inconclusive" results in those regimes should not be over-read. The uncertainty quantification is not uniform across phases: Phase 1 reports a 500-resample bootstrap on the b-value, whereas Phases 2–4 report the analytic Clauset/Hill standard error (see §2.2 and Appendix Table A2). A uniform bootstrap report across all four real phases would be a reasonable methodological upgrade but was not done in the source papers.

**6.5 Single sessions / single windows.** Phase 4 rests on one mouse-cortex recording session; the task-active-sub-class conclusion would be strengthened by additional sessions. Phase 2 uses one index over one time window. None of the phases is a meta-analysis across many independent datasets within the same domain.

**6.6 This is a Claude-generated draft.** Every number in this draft traces to one of the five Phase 1–5 source papers (cross-checked against the thirteen-system sibling manuscript), but the synthesis, framing, and cross-phase claims have not been checked by a domain expert. The Pre-submission checklist at the end of this file lists every remaining human-confirmation item.

---

***REMOVED******REMOVED*** 7. Conclusion

We assembled a single Clauset-grade analysis pipeline and applied it, without per-domain tuning, to four independent real systems — USGS earthquakes, S&P 500 daily returns, DeFi liquidations across three protocols, and task-active mouse-cortex neural avalanches — plus four synthetic non-SOC null sources. The pipeline recovered canonical SOC signatures on all four real systems (Gutenberg–Richter b = 1.084 ± 0.005; inverse-cubic α = 2.998 ± 0.041; DeFi α ∈ [1.567, 1.684] with cross-protocol spread 0.12; neural scaling relation γ ≈ 1.10 stable across a 16-fold binning range) and correctly rejected the power-law hypothesis on all four nulls. The result is a single-pipeline, cross-domain test of self-organized-criticality universality, deliberately conservative in its claims: the lognormal alternative is not rejected in every raw-tail test — for S&P 500 it is favored, and the SOC verdict there rests on exponent-band agreement — the pipeline targets only endogenous threshold-cascade dynamics, and the project's downstream cross-domain predictions remain unverified for lack of target data. Within those limits, four very different systems gave four coherent results from one method — which is the minimum empirical bar a universality-class claim must clear.

---

***REMOVED******REMOVED*** References

The list below is consolidated and de-duplicated from the individually checked bibliographies of the five Phase 1–5 source papers. Each entry was cross-checked against at least one source paper's reference list. Entries that could not be cross-verified within the project repository are marked **[待核]** (verify bibliographic detail before submission).

**Foundational — universality and SOC**

1. Wilson, K. G. The renormalization group and critical phenomena. *Reviews of Modern Physics* **55**, 583 (1983).
2. Stanley, H. E. Scaling, universality, and renormalization: three pillars of modern critical phenomena. *Reviews of Modern Physics* **71**, S358 (1999).
3. Bak, P., Tang, C. & Wiesenfeld, K. Self-organized criticality: an explanation of 1/f noise. *Physical Review Letters* **59**, 381 (1987).
4. Olami, Z., Feder, H. J. S. & Christensen, K. Self-organized criticality in a continuous, nonconservative cellular automaton modeling earthquakes. *Physical Review Letters* **68**, 1244 (1992).
5. Turcotte, D. L. Self-organized criticality. *Reports on Progress in Physics* **62**, 1377 (1999).
6. Sethna, J. P., Dahmen, K. A. & Myers, C. R. Crackling noise. *Nature* **410**, 242 (2001).
7. Jensen, H. J. *Self-Organized Criticality: Emergent Complex Behavior in Physical and Biological Systems.* Cambridge University Press (1998).
8. Pruessner, G. *Self-Organised Criticality: Theory, Models and Characterisation.* Cambridge University Press (2012).
9. Sornette, D. *Critical Phenomena in Natural Sciences: Chaos, Fractals, Selforganization and Disorder.* 2nd ed., Springer (2006).

**Statistical method — power-law fitting**

10. Clauset, A., Shalizi, C. R. & Newman, M. E. J. Power-law distributions in empirical data. *SIAM Review* **51**, 661 (2009).
11. Alstott, J., Bullmore, E. & Plenz, D. powerlaw: a Python package for analysis of heavy-tailed distributions. *PLoS ONE* **9**, e85777 (2014).
12. Newman, M. E. J. Power laws, Pareto distributions and Zipf's law. *Contemporary Physics* **46**, 323 (2005).
13. Broido, A. D. & Clauset, A. Scale-free networks are rare. *Nature Communications* **10**, 1017 (2019).

**Earthquakes (Phase 1)**

14. Gutenberg, B. & Richter, C. F. Frequency of earthquakes in California. *Bulletin of the Seismological Society of America* **34**, 185 (1944).
15. Omori, F. On the after-shocks of earthquakes. *Journal of the College of Science, Imperial University of Tokyo* **7**, 111 (1894).
16. Utsu, T., Ogata, Y. & Matsu'ura, R. S. The centenary of the Omori formula for a decay law of aftershock activity. *Journal of Physics of the Earth* **43**, 1 (1995).
17. Aki, K. Maximum likelihood estimate of b in the formula log N = a − bM and its confidence limits. *Bulletin of the Earthquake Research Institute, University of Tokyo* **43**, 237 (1965).
18. Shi, Y. & Bolt, B. A. The standard error of the magnitude-frequency b value. *Bulletin of the Seismological Society of America* **72**, 1677 (1982).
19. Wiemer, S. & Wyss, M. Minimum magnitude of completeness in earthquake catalogs: examples from Alaska, the western United States, and Japan. *Bulletin of the Seismological Society of America* **90**, 859 (2000).
20. Hanks, T. C. & Kanamori, H. A moment magnitude scale. *Journal of Geophysical Research* **84**, 2348 (1979).

**Equity finance (Phase 2)**

21. Gopikrishnan, P., Meyer, M., Amaral, L. A. N. & Stanley, H. E. Inverse cubic law for the distribution of stock price variations. *European Physical Journal B* **3**, 139 (1998).
22. Plerou, V., Gopikrishnan, P., Amaral, L. A. N., Meyer, M. & Stanley, H. E. Scaling of the distribution of price variations of individual companies. *Physical Review E* **60**, 6519 (1999).
23. Gabaix, X., Gopikrishnan, P., Plerou, V. & Stanley, H. E. A theory of power-law distributions in financial market fluctuations. *Nature* **423**, 267 (2003).
24. Lillo, F. & Mantegna, R. N. Power-law relaxation in a complex system: Omori law after a financial market crash. *Physical Review E* **68**, 016119 (2003).
25. Petersen, A. M., Wang, F., Havlin, S. & Stanley, H. E. Market dynamics immediately before and after financial shocks: quantifying the Omori, productivity, and Bath laws. *Physical Review E* **82**, 036114 (2010).
26. Weber, P., Wang, F., Vodenska-Chitkushev, I., Havlin, S. & Stanley, H. E. Relation between volatility correlations in financial markets and Omori processes occurring on all scales. *Physical Review E* **76**, 016109 (2007).
27. Mantegna, R. N. & Stanley, H. E. *An Introduction to Econophysics: Correlations and Complexity in Finance.* Cambridge University Press (2000).

**DeFi (Phase 3)**

28. Qin, K., Zhou, L. & Gervais, A. An empirical study of DeFi liquidations: incentives, risks, and instabilities. *Proceedings of the ACM Internet Measurement Conference (IMC '21)* (2021).
29. Perez, D., Werner, S. M., Xu, J. & Livshits, B. Liquidations: DeFi on a knife-edge. *Financial Cryptography and Data Security 2021* (2021).
30. Aave. Aave Protocol V2 Whitepaper (2020). *[待核 — whitepaper, no journal venue]*
31. Compound Labs. Compound V2 Whitepaper (2019). *[待核 — whitepaper, no journal venue]*
32. MakerDAO. Liquidation 2.0 specification: Dog and Clipper detailed documentation (2021). *[待核 — online specification, no journal venue]*
33. Motter, A. E. & Lai, Y.-C. Cascade-based attacks on complex networks. *Physical Review E* **66**, 065102 (2002).

**Neural avalanches (Phase 4)**

34. Beggs, J. M. & Plenz, D. Neuronal avalanches in neocortical circuits. *Journal of Neuroscience* **23**, 11167 (2003).
35. Friedman, N., Ito, S., Brinkman, B. A. W., Shimono, M., DeVille, R. E. L., Dahmen, K. A., Beggs, J. M. & Butler, T. C. Universal critical dynamics in high resolution neuronal avalanche data. *Physical Review Letters* **108**, 208102 (2012).
36. Priesemann, V., Munk, M. H. J. & Wibral, M. Subsampling effects in neuronal avalanche distributions recorded in vivo. *BMC Neuroscience* **15**, 1 (2014).
37. Touboul, J. & Destexhe, A. Power-law statistics and universal scaling in the absence of criticality. *Physical Review E* **95**, 012413 (2017).
38. Harris, T. E. *The Theory of Branching Processes.* Springer (1963); Dover reprint (1989).
39. Li, N., Chen, T.-W., Guo, Z. V., Gerfen, C. R. & Svoboda, K. A motor cortex circuit for motor planning and movement. *Nature* **519**, 51 (2015). [Data: DANDI Archive dataset 000006, mouse anterior lateral motor cortex in delay-response task, https://dandiarchive.org/dandiset/000006.]
40. Beggs, J. M. & Timme, N. Being critical of criticality in the brain. *Frontiers in Physiology* **3**, 163 (2012).

**Project (self-references) — [待核]: internal project documents, not formally published**

41. Wan, Q. Recovering self-organized criticality on a global earthquake catalog: a reproducible pipeline for cross-domain universality-class identification. Structural Isomorphism Project, Phase 1 (2026). *[待核]*
42. Wan, Q. Cross-domain self-organized criticality: inverse cubic law and Omori decay on thirty-five years of S&P 500 daily returns. Structural Isomorphism Project, Phase 2 (2026). *[待核]*
43. Wan, Q. Cross-protocol SOC universality in DeFi liquidation cascades: 43,065 events across Aave V2, Compound V2, and MakerDAO. Structural Isomorphism Project, Phase 3 (2026). *[待核]*
44. Wan, Q. Criticality without mean-field SOC: neural avalanche scaling on task-active mouse cortex. Structural Isomorphism Project, Phase 4 (2026). *[待核]*
45. Structural Isomorphism Project. V1–V4 snapshot: cross-domain universality-class identification. Zenodo (2026), DOI: 10.5281/zenodo.19547879. *[待核 — DOI requires online verification; see Pre-submission checklist item 1]*

---

***REMOVED******REMOVED*** Appendix A — Data and reproducibility

**Table A1.** Data sources and analysis samples.

| Phase | System | Data source | Analysis sample |
|---|---|---|---|
| 1 | USGS earthquakes | USGS FDSN event service, 2020–2025, M ≥ 3.5 | 37,281 above M_c = 4.45 |
| 2 | S&P 500 | Yahoo Finance `^GSPC` daily close (`yfinance`), 1990–2025 | 9,060 returns (n_tail = 2,327) |
| 3 | DeFi liquidations | On-chain event logs: Aave V2, Compound V2, MakerDAO Dog/Clip | 43,065 events (25,601 / 11,244 / 1,985) |
| 4 | Mouse cortex | DANDI Archive 000006, session sub-anm369962_ses-20170313 | 1,392,414 spikes / 71 units |
| 5 | Synthetic nulls | Generated in-repo (`v4/validation/null-controls`) | 20,000 each (×3 size, ×1 Omori) |

**Table A2.** Uncertainty quantification per phase (closes the v0.1 §2.2 [TODO]).

| Phase | Quantity | Uncertainty method | Detail |
|---|---|---|---|
| 1 | b-value | 500-resample bootstrap **+** analytic Shi–Bolt error | seed = 42; 95 % CI [1.073, 1.094] |
| 1 | α (seismic energy) | Clauset/Hill analytic standard error | ± 0.024 |
| 2 | α (S&P 500) | Clauset/Hill analytic standard error | ± 0.041; no bootstrap in source paper |
| 3 | α (each DeFi protocol) | Clauset/Hill analytic standard error | ± 0.010–0.016; no bootstrap in source paper |
| 4 | τ, α_T (per bin factor) | Clauset/Hill analytic standard error | ± 0.01–0.13 depending on bin; no bootstrap in source paper |

**Pipeline.** Authoritative implementation: the `soc-pipeline` Python package (`packages/soc-pipeline/`, version 0.1.0, MIT licence; depends on `numpy`, `scipy`, `pandas`, `powerlaw`). The legacy path `v4/lib/soc_pipeline.py` is a deprecation shim re-exporting the package. Per-phase analysis scripts are tagged in the repository (`v4/phase1-earthquake-2026-04-15`, `v4/phase2-stockmarket-2026-04-15`, …). See §2 for the provenance caveat regarding the "339 lines / commit 7ee228c" description in the thirteen-system sibling manuscript.

**Project Zenodo deposit.** DOI 10.5281/zenodo.19547879 (cited by the Phase 1–4 source papers). **[待确认：发布前需核对 Zenodo deposit 是否覆盖 Phase 1–5 全部代码与数据。]** This DOI could not be verified offline; see Pre-submission checklist item 1.

---

***REMOVED******REMOVED*** Pre-submission checklist (人工确认项 — must be closed by a human before any submission)

The seven v0.1 [TODO 待核实] markers have been closed in this v0.2 draft (see the META block changelog at the top). The items below are the residual human-confirmation tasks that cannot be settled from the repository alone:

1. **Zenodo DOI.** Verify online that DOI `10.5281/zenodo.19547879` resolves, is the current version, and that its deposit covers all Phase 1–5 code and data referenced here. The DOI is shown in the text but flagged [待确认]; do not present it as confirmed until checked.
2. **Pipeline canonical version.** Record one canonical release tag or commit hash of the `soc-pipeline` package against which the final Phase 1–5 numbers are confirmed, and reconcile it with the per-phase repository tags. Note for the reviewer: the thirteen-system sibling manuscript's "`v4/lib/soc_pipeline.py`, 339 lines, commit `7ee228c`" description is stale relative to the current package-based layout.
3. **Reference entries marked [待核].** Confirm full bibliographic detail for the entries flagged [待核] in the reference list — chiefly the DeFi whitepapers/specifications (refs 30–32, which have no journal venue and should perhaps be cited as technical documentation with access dates) and the project self-references (refs 41–45, internal project documents whose final citable form / arXiv identifiers must be decided before submission).
4. **Phase 2 lognormal wording — final editorial sign-off.** §3.2/§6.1 now state that the raw-tail Vuong test favors lognormal for S&P 500 (R = −6.12) and that the arxiv-02 source paper's prose ("power-law strongly dominates lognormal") is an internal sign-interpretation error. A domain reviewer should confirm this reading and decide whether to additionally issue a correction note for the standalone arxiv-02 paper.
5. **Decide whether to post the thirteen-system sibling alongside C1.** This is an editorial choice (post both, or only the focused five-system paper). The scope decision in §1 fixes C1 as the focused paper; whether the sibling is also posted is left to the author at submission time.
6. **Domain-expert review.** This entire draft is Claude-generated and has not been read by a domain expert (§6.6). A seismology/econophysics/neuroscience reviewer should check the cross-phase synthesis and framing before submission.

---

*End of draft v0.2. Status: 草稿待人审. Generated 2026-05-22 from project source materials listed in the meta block at the top of this file. The seven v0.1 [TODO] markers are closed; six residual human-confirmation items are listed above. Not yet reviewed by a domain expert.*
