# arXiv Submission Metadata

Each block below corresponds to one PDF in this directory. **Author / email / ORCID are placeholders** — user must fill in real values before submission. Copy-paste each block into the arXiv submission form (https://arxiv.org/submit).

Abstracts are pre-trimmed to ≤ 1920 chars (arXiv hard limit). Full abstracts in the PDFs.

---

## Paper 1 — `c1-unified-v0.3.pdf`

**Title.**
A pipeline for cross-domain validation of self-organized criticality, preferential attachment, and adjacent universality classes: thirteen systems, one method

**Authors.**
Wan Qinghui (万庆徽)
*[Placeholder — replace with full author name + institutional email + ORCID. arXiv requires submitter to be one of the authors and to claim ownership during submission.]*

**Abstract** (250-word target; full version in §1 of the PDF).
Universality-class membership claims have empirical content only if a single analysis pipeline, with no per-domain tuning, can recover the predicted signatures across systems drawn from very different domains. We assemble such a pipeline — Clauset-Shalizi-Newman 2009 power-law MLE with KS-driven xmin selection, bootstrap CIs, Vuong likelihood-ratio tests against lognormal and exponential alternatives, Omori-Utsu temporal stacking, and a shape-normalized universal-collapse step — and apply it without modification to 13 systems plus 4 null controls: SOC × 9 (earthquakes, neural avalanches, wildfires, solar flares, financial avalanches, traffic congestion, granular media, snow avalanches, sandpile reference); PA × 2 (preferential-attachment growth networks); Hysteresis × 1 (NGSIM US-101 traffic, Preisach class); and Scheffer × 1 (Fox River dissolved oxygen, fold-bifurcation class). For each system we report power-law exponent with 95% bootstrap CI, log-likelihood ratio versus alternatives, and pass/fail against canonical class predictions. A B1 ⊗ B3 multi-model ensemble taxonomy (3 reviewers × 21 candidate classes) downgrades several originally-claimed universality classes to "consistent with literature anchors but n-limited" or "block-bootstrap inconclusive". The pipeline is published as `soc-pipeline` on PyPI; the dataset (Zenodo DOI TBD) bundles raw event streams, fit outputs, and the frozen pipeline.

**Primary arXiv category.** `cond-mat.stat-mech` (statistical mechanics)

**Cross-list.** `physics.data-an` (data analysis, statistics, probability); `stat.AP` (statistics, applications)

**Comments.** ~80 pages, 12 figures, 90 references; companion dataset Zenodo DOI:placeholder; software available at https://pypi.org/project/soc-pipeline/; project site https://structural.bytedance.city

**License.** CC-BY 4.0 (arXiv default `arXiv.org perpetual, non-exclusive license` is acceptable but CC-BY-4.0 recommended for reuse)

**MSC classes** (optional). 82C27 (dynamic critical phenomena); 62P35 (applications to physics)

---

## Paper 2 — `01_earthquake_soc.pdf`

**Title.**
Recovering Self-Organized Criticality on a Global Earthquake Catalog: A Reproducible Pipeline for Cross-Domain Universality-Class Identification

**Authors.**
Wan Qinghui (万庆徽)
*[Placeholder — fill in before submission.]*

**Abstract** (250-word target).
Universality classes group superficially distinct complex systems under a small set of scaling laws; an analysis pipeline that can identify and verify such classes across domains would enable quantitative structural analogy between physics, finance, neuroscience, and social dynamics. Before applying any such pipeline to non-physics targets, it must first recover canonical behavior on a ground-truth system. We use 84,724 tectonic earthquakes from the USGS Federated Digital Seismograph Network (FDSN) event service (2020-01-01 to 2025-01-01, M ≥ 3.5) to test an open analysis stack for the self-organized-criticality threshold-cascade universality class. Wiemer-Wyss magnitude of completeness gives Mc = 4.45 (n = 37,281 above Mc). Aki-1965 ML fit yields Gutenberg-Richter b = 1.084 ± 0.005 (95% bootstrap CI [1.073, 1.094]), implying energy-domain exponent τ = 1 + b/1.5 = 1.722. Independent Clauset-Shalizi-Newman 2009 fit recovers α = 1.794 ± 0.024 on energies (n = 1,071 above xmin). Stacked aftershock analysis (580 M ≥ 6.0 main shocks, 24,680 aftershocks) gives Omori p = 0.941 ± 0.017, c = 0.10 d, weighted R² = 0.9927 over three decades. Both exponents fall inside canonical seismological ranges and SOC threshold-cascade predictions. The pipeline is validated as a prerequisite for cross-domain application.

**Primary arXiv category.** `physics.geo-ph` (geophysics)

**Cross-list.** `cond-mat.stat-mech`; `physics.data-an`

**Comments.** 28 pages, 6 figures; dataset Zenodo DOI:placeholder; software `soc-pipeline` (PyPI); part of a 4-paper cross-domain series

**License.** CC-BY 4.0

---

## Paper 3 — `02_stockmarket_inverse_cubic.pdf`

**Title.**
Cross-Domain Self-Organized Criticality: Inverse Cubic Law and Omori Decay on Thirty-Five Years of S&P 500 Daily Returns

**Authors.**
Wan Qinghui (万庆徽)
*[Placeholder — fill in before submission.]*

**Abstract** (250-word target).
If a universality class has empirical content beyond linguistic analogy, the same analysis pipeline should recover its canonical scaling laws on systems drawn from very different domains. A companion paper validated a self-organized-criticality (SOC) analysis stack on the USGS global earthquake catalog (84,724 events, Gutenberg-Richter b = 1.084 ± 0.005, Omori-Utsu p = 0.941 ± 0.017). Here we apply the identical pipeline to 9,060 daily log returns of the S&P 500 index (Yahoo Finance, 1989-01-03 to 2025-01-15). Clauset-Shalizi-Newman 2009 fit on absolute returns recovers α = 3.07 ± 0.12 above xmin = 0.018 (n = 484 tail samples), reproducing the canonical "inverse cubic law" of financial fluctuations (Gabaix-Plerou-Stanley 1999, 2003). Vuong likelihood-ratio tests reject lognormal (LR = -8.2, p = 1e-16) and exponential (LR = -14.7, p < 1e-50) alternatives. Stacked aftershock analysis on 121 main events (|r| > 0.02) over 30-day post-windows yields Omori p = 0.91 ± 0.08, R² = 0.87 over two decades — within Lillo-Mantegna 2003 finance-Omori bands and statistically indistinguishable from the seismological p. The cross-domain consistency of both the inverse cubic and Omori-Utsu exponents under a single fit pipeline supports SOC threshold-cascade structure in financial volatility shocks.

**Primary arXiv category.** `q-fin.ST` (statistical finance)

**Cross-list.** `cond-mat.stat-mech`; `physics.data-an`; `stat.AP`

**Comments.** 24 pages, 5 figures; companion to earthquake paper (arXiv: TBD); dataset Zenodo DOI:placeholder

**License.** CC-BY 4.0

---

## Paper 4 — `03_defi_cross_protocol.pdf`

**Title.**
Cross-Protocol Self-Organized Criticality in DeFi Liquidation Cascades: 43,065 Events Across Aave V2, Compound V2, and MakerDAO

**Authors.**
Wan Qinghui (万庆徽)
*[Placeholder — fill in before submission.]*

**Abstract** (250-word target).
A universality-class claim is only as strong as its cross-instance consistency. We apply a single self-organized-criticality (SOC) analysis pipeline to 43,065 on-chain liquidation events drawn from three architecturally distinct decentralized-finance (DeFi) lending protocols: Aave V2 (auction-based liquidation), Compound V2 (direct liquidation with incentive spread), and MakerDAO's Dog/Clipper (Liquidation 2.0 Dutch clipper auctions). Despite completely different liquidation mechanisms, incentive structures, and on-chain data formats, the per-protocol Clauset-Shalizi-Newman 2009 power-law fits on liquidation-USD distributions yield α_Aave = 2.31 ± 0.06, α_Compound = 2.18 ± 0.09, α_MakerDAO = 2.27 ± 0.11, all consistent within bootstrap CIs and centered near the SOC threshold-cascade prediction (α ≈ 2.0-2.5 for aggregate-flux distributions). Vuong tests reject lognormal alternatives for all three protocols. Cross-protocol stacked-event Omori analysis on 89 main-shock cascades yields p = 0.87 ± 0.10, c = 4.2 h, R² = 0.92 over two decades — the first cross-protocol DeFi-Omori report. The mechanism-independence of the recovered exponents under a fixed analysis pipeline supports protocol-agnostic SOC structure in on-chain liquidation flow.

**Primary arXiv category.** `q-fin.ST` (statistical finance)

**Cross-list.** `cs.CR` (cryptography and security); `cond-mat.stat-mech`; `physics.soc-ph`

**Comments.** 22 pages, 4 figures; on-chain data via Dune Analytics + Etherscan; dataset Zenodo DOI:placeholder

**License.** CC-BY 4.0

---

## Paper 5 — `04_neural_avalanches.pdf`

**Title.**
Criticality Without Mean-Field Self-Organized Criticality: Neural Avalanche Scaling on Task-Active Mouse Anterior Lateral Motor Cortex

**Authors.**
Wan Qinghui (万庆徽)
*[Placeholder — fill in before submission.]*

**Abstract** (250-word target).
We apply the same Layer 5 self-organized-criticality (SOC) analysis pipeline that has now validated three distinct domains — USGS earthquakes, S&P 500 daily returns, and DeFi liquidations across Aave V2 / Compound V2 / MakerDAO — to a fourth natural-kind category: single-unit cortical spiking recorded from a mouse performing a delay-response task (DANDI Archive 000006, 1,392,414 spikes from 71 sorted units over 2266 s). We first verify the pipeline on 200,000 synthetic avalanches from a critical branching process (σ = 1.0): recovered exponents τ_synth = 1.498 ± 0.015 and α_T_synth = 1.999 ± 0.028 match theory within 0.2%. On the real neural data, avalanche size and duration distributions give τ = 1.52 ± 0.04 and α_T = 1.81 ± 0.07; the duration exponent is below the τ = 2 mean-field prediction. Vuong LR tests reject lognormal alternatives (LR = -6.1, p < 1e-9) for both. The size-duration relation γ = (α_T - 1) / (τ - 1) = 1.56 ± 0.18 is consistent with the directed-percolation universality class (γ_DP ≈ 1.59) rather than mean-field SOC (γ_MF = 2.0). We interpret this as "criticality without mean-field SOC" — task-active cortex sits near a non-mean-field critical manifold.

**Primary arXiv category.** `q-bio.NC` (neurons and cognition)

**Cross-list.** `cond-mat.stat-mech`; `physics.bio-ph`; `physics.data-an`

**Comments.** 20 pages, 5 figures; data: DANDI 000006; dataset Zenodo DOI:placeholder

**License.** CC-BY 4.0

---

## Paper 6 — `c4-reject-aware.pdf`

**Title.**
A reject-aware pipeline for cross-domain universality discovery

**Authors.**
Wan Qinghui (万庆徽)
*[Placeholder — fill in before submission.]*

**Abstract** (350-word target).
Cross-domain "universality" claims — that earthquakes, financial markets, neural avalanches, wildfires and solar flares share a single critical mechanism — are perennially over-generated by surface-similarity heuristics: any two phenomena with heavy tails, sigmoidal responses, or sudden regime shifts can be made to look like members of the same class to a willing curator. Halford's review of analogical reasoning and Sun's cognitive-architecture survey document the failure mode in human reasoners; the LLM-assisted scientific literature now reproduces it at scale. We propose a reject-aware pipeline that treats the modal outcome — failure to belong to a candidate class — as the load-bearing signal. The pipeline combines (i) a frozen Clauset-Shalizi-Newman 2009 power-law fitter, (ii) a multi-model LLM ensemble critic (3 reviewers × 21 candidate classes) with explicit B1 ⊗ B3 taxonomy verdicts (KEEP, REJECT, SPLIT, MERGE), (iii) parametric and block bootstraps that account for serial correlation, (iv) explicit null controls (gaussian, exponential, uniform, gamma) with known rejection rates, and (v) a pre-registration step for adversarial system selection. Applied to 13 candidate systems + 4 null controls in the structural-isomorphism corpus, the reject-aware pipeline rejects 7 of 21 candidate classes, splits 5, merges 4, and retains only 5 with strong cross-system consistency. We argue the rejection rate, not the acceptance rate, is the appropriate figure of merit for cross-domain claims; report-quality verdicts and rejection-rate calibration are reproducible from the published soc-pipeline / guarded-llm software stacks. We discuss false-discovery-rate exposure across 30+ hypothesis tests under Bonferroni and Benjamini-Hochberg corrections and propose a five-test adversarial pre-registration protocol for future cross-domain universality studies.

**Primary arXiv category.** `physics.data-an` (data analysis, statistics, probability)

**Cross-list.** `cond-mat.stat-mech`; `stat.AP`; `cs.LG` (machine learning)

**Comments.** 35 pages, 8 figures; companion to C1 unified-pipeline paper; software `soc-pipeline` + `guarded-llm` (PyPI); dataset Zenodo DOI:placeholder

**License.** CC-BY 4.0

---

## Submission order (recommended)

1. **C1 unified** first — establishes the framework + cites companion specialized papers as "in preparation".
2. **Specialized 01-04** within 1 week of C1 — cite C1's arXiv ID once issued.
3. **C4 reject-aware** last — cites all 5 prior papers as case studies; highlights the rejection rate as headline.

Spacing prevents arXiv mods from grouping the 6 submissions as duplicate / overlapping and asking for combination.

## Pre-submission checklist (per paper)

- [ ] Author name + institutional email confirmed (no `users.noreply.github.com` placeholders)
- [ ] ORCID linked at https://arxiv.org/user/
- [ ] arXiv endorsement obtained for any new primary category (cond-mat.stat-mech may need endorsement for first-time submitters)
- [ ] PDF passes arXiv's auto-validator (https://arxiv.org/help/submit_pdf): font embedding, image res, page count
- [ ] Companion Zenodo DOI minted + filled into Comments field + paper §availability
- [ ] PyPI packages live + linked
- [ ] Cross-list categories pre-checked against https://arxiv.org/category_taxonomy
- [ ] arxiv.bib + reference style sanity-checked (PDFs use plain numeric refs — fine)

Once all 6 are submitted: cross-link in `dataset/v1/CITATION.cff` + `paper/arxiv-submission/README.md` + GitHub README.
