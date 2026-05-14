# Senior researcher outreach drafts — 2026-05-15

Five cold-email drafts for senior researchers per W7-A Track E. Staggered send schedule T+3, T+5, T+7, T+10, T+14 from launch (see INDEX.md). Each ~3 paragraphs, specific and respectful, no gushing.

Subject line convention: `[arXiv preprint] Cross-domain SOC pipeline with adversarial pre-registration — would value your perspective on <specific concern>`

---

## 1. Dietmar Plenz (NIMH, Bethesda)

**To:** Dietmar Plenz, Section on Critical Brain Dynamics, NIMH
**Subject:** [arXiv preprint] Cross-domain SOC pipeline applied to neural avalanches — would value your perspective on sub-sampling and inter-electrode distance effects

Dear Prof. Plenz,

My name is Qinghui Wan; I work independently on cross-domain validation of self-organized criticality. Over the last several months I have built a frozen 339-LOC Clauset MLE pipeline that I apply, without per-system tuning, to 13 heterogeneous empirical systems — among them neural avalanches reconstructed from public mouse-cortex datasets. The preprint is on arXiv (link below) and the dataset is on Zenodo with a DOI. The point of the project is methodological rather than novel-discovery: pre-register exponent bands, run the same pipeline everywhere, and publish the negatives alongside the positives.

The Beggs–Plenz 2003 *J. Neurosci.* result on neuronal avalanches in cortical slice cultures is the empirical anchor for our neural sub-paper, and our analysis recovers the canonical alpha ~ 1.5 size exponent within the pre-registered band. What I would value your perspective on is a specific concern that Priesemann and colleagues have raised about sub-critical reverberation vs. genuine criticality in in-vivo recordings, and the role of sub-sampling and inter-electrode distance in biasing the apparent exponent. Our pipeline currently does not adjust for these and we are aware that the band-test alone is not diagnostic in their presence.

If you have 30 minutes in the coming weeks for a video call, I would be grateful for a conversation about (a) whether our protocol could be strengthened by an in-vivo replication that explicitly handles sub-sampling, and (b) whether co-authorship on a focused neural-avalanche replication paper (separate from the unified preprint) would be of interest. I understand that your time is heavily booked and there is no obligation; even a written one-paragraph critique would help us before we proceed.

Sincerely,
Qinghui Wan

- arXiv preprint: pending (arXiv link to follow on submission; local copy at `paper/anti-phacking-unified-2026-05-15.md`)
- Dataset DOI: https://doi.org/10.5281/zenodo.19615170
- Repo: https://github.com/dada8899/structural-isomorphism

---

## 2. Viola Priesemann (MPI Dynamics and Self-Organization, Göttingen)

**To:** Viola Priesemann, MPI for Dynamics and Self-Organization
**Subject:** [arXiv preprint] Cross-domain SOC pipeline — would value your perspective on sub-critical reverberation vs. critical regime in our neural verdict

Dear Prof. Priesemann,

I am Qinghui Wan, working independently on a cross-domain validation pipeline for self-organized criticality. The project applies a single frozen Clauset MLE pipeline, without per-domain tuning, across 13 heterogeneous empirical systems and pre-registers the exponent bands before the data are fetched. The companion methodology paper (arXiv pending) walks through four published negative and partial verdicts to illustrate the adversarial pre-registration protocol; the preprint and the SIBD-63 dataset are linked below.

The reason I am writing specifically to you is that the neural sub-paper of the project is the part where I am least confident. Wilting and Priesemann 2018 *Nat. Commun.* makes a careful case that what appears to be critical scaling in in-vivo recordings is often better described as a sub-critical reverberating regime — and that the branching-ratio estimator is more diagnostic than a power-law exponent fit alone when sub-sampling is present. Our current pipeline reports a passing band on a mouse-cortex spike-count dataset, but the band-test does not distinguish a true critical regime from a sub-critical regime that has been sub-sampled into apparent power-law shape. We are aware of this and have flagged it as a known limitation in the paper.

What I would value is a 30-minute call (or even a written critique) on whether our protocol should be strengthened by adding the branching-ratio estimator as a secondary diagnostic before the band-test is reported as PASS. If this strengthens the framework substantially, I would be glad to discuss co-authorship on the neural sub-paper — your participation would meaningfully improve its credibility.

Sincerely,
Qinghui Wan

- arXiv preprint: pending (link to follow; local copy `paper/anti-phacking-unified-2026-05-15.md`)
- Dataset DOI: https://doi.org/10.5281/zenodo.19615170
- Repo: https://github.com/dada8899/structural-isomorphism

---

## 3. Marten Scheffer (Wageningen University)

**To:** Marten Scheffer, Aquatic Ecology and Water Quality Management, WUR
**Subject:** [arXiv preprint] Block-bootstrap correction for autocorrelated early-warning signals — building on your Scheffer et al. 2009 framework

Dear Prof. Scheffer,

I am Qinghui Wan, working independently on a cross-domain validation framework for self-organized criticality and tipping-point detection. One component of the framework is a methodological paper on block-bootstrap confidence intervals for autocorrelated early-warning signal time series — a direct extension of the EWS recipe in Scheffer et al. 2009 *Nature*. The current draft is at `paper/d1-block-bootstrap-ews-2026-05-15.md` in our repo (link below); we plan to submit a focused version to *Methods in Ecology and Evolution*.

The specific contribution of the D1 paper is a finite-sample correction for autocorrelation-induced false positives in EWS variance-and-AC1 indicators. The Scheffer et al. 2009 framework explicitly notes that autocorrelation inflates the false-positive rate for tipping detection in noisy ecological time series; our block-bootstrap procedure gives a finite-sample-corrected confidence interval that closes that gap and reproduces well on the published Lake Tahoe and shallow-lake datasets we re-analyzed. The companion adversarial pre-registration preprint (arXiv pending) puts this in the broader frame of negative-result-aware methodology.

I would be grateful for 30 minutes of your time to discuss two questions: (a) whether the block-bootstrap correction would meaningfully strengthen the EWS toolkit for ecological tipping-point detection as you envision it, and (b) whether co-authorship on the D1 paper would be of interest. Your participation would substantially raise the credibility ceiling of the methodology paper and would, I believe, be a small additional commitment given that the framework is already yours.

Sincerely,
Qinghui Wan

- arXiv preprint: pending (link to follow; local copy `paper/anti-phacking-unified-2026-05-15.md`)
- D1 EWS paper draft: `paper/d1-block-bootstrap-ews-2026-05-15.md`
- Dataset DOI: https://doi.org/10.5281/zenodo.19615170
- Repo: https://github.com/dada8899/structural-isomorphism

---

## 4. Aaron Clauset (CU Boulder)

**To:** Aaron Clauset, Department of Computer Science, CU Boulder
**Subject:** [arXiv preprint] Reject-aware pipeline built on Clauset–Shalizi–Newman 2009 — would value your perspective on within-vendor LLM ensemble limits

Dear Prof. Clauset,

I am Qinghui Wan, working independently on a cross-domain validation pipeline for self-organized criticality. The pipeline implements the Clauset–Shalizi–Newman 2009 *SIAM Review* discrete power-law MLE — KS-optimal `xmin`, Hill-form `alpha`, block-bootstrap CIs, Vuong likelihood-ratio tests against lognormal and exponential — as a single 339-LOC frozen module, applied without per-system tuning across 13 empirical systems and 4 null controls. The companion methodology paper, "Adversarial Pre-Registration as Anti-p-Hacking Methodology," reports four published FAIL / INCONCLUSIVE / PARTIAL / NULL verdicts; the arXiv link is pending and the dataset DOI is below.

The reason I am writing specifically to you is that the philosophical anchor of the project — that the unit of credibility should be the public ledger of verdicts rather than the individual confirming paper — is squarely in the spirit of Broido and Clauset 2019 *Nat. Commun.*, where what looked like a confirmed empirical regularity (scale-free networks) was carefully shown to be the exception rather than the rule under the same pipeline applied uniformly. We have tried to apply that discipline to a different but methodologically adjacent question. One specific concern I would value your perspective on: our LLM critic ensemble is currently within-vendor (three DeepSeek decodings at varied temperature), and we describe this honestly as a limitation pending a cross-architecture B4 build. We worry the within-vendor ensemble materially inflates the apparent rejection rate vs. a true cross-family ensemble.

If you have 30 minutes for a video call, I would value your view on (a) whether our reject-aware framing maps cleanly onto the Broido-Clauset rejection-aware spirit or whether we have misrepresented it, and (b) whether co-authorship on a future dataset-curation paper (the cross-domain SIBD-63 candidate set is a natural sequel) would be of interest. Even a written one-paragraph critique would be enormously helpful.

Sincerely,
Qinghui Wan

- arXiv preprint: pending (local copy `paper/anti-phacking-unified-2026-05-15.md`)
- Dataset DOI: https://doi.org/10.5281/zenodo.19615170
- Repo: https://github.com/dada8899/structural-isomorphism

---

## 5. Didier Sornette (SUSTech, formerly ETH Zürich)

**To:** Didier Sornette, Institute of Risk Analysis, Prediction and Management, SUSTech
**Subject:** [arXiv preprint] S&P 500 inverse-cubic boundary case and dragon-king diagnostics — would value your perspective on power-law vs. dragon-king reading

Dear Prof. Sornette,

I am Qinghui Wan, working independently on a cross-domain SOC validation pipeline. The pipeline applies the Clauset–Shalizi–Newman 2009 discrete MLE without per-system tuning across 13 empirical systems; the companion methodology paper exhibits four pre-registered FAIL / INCONCLUSIVE / PARTIAL / NULL verdicts including one on an S&P 500 walk-forward forward-return signal that returned a near-perfectly-null t-test on 54 monthly snapshots (t = −0.412, p = 0.681). The arXiv preprint is pending; dataset DOI below.

The reason I am writing to you specifically is that two of the systems in the validation set — S&P 500 daily returns and power-grid blackout sizes — are squarely in the territory you have shaped. The S&P 500 result reproduces the inverse-cubic exponent (alpha ~ 3.0, CI overlapping the boundary) consistent with Plerou-Gopikrishnan-Stanley, but our band-test does not by itself distinguish a generic power-law from a dragon-king regime in the tail. Sornette and Ouillon 2012 *Eur. Phys. J. Special Topics* makes the case that a uniform-power-law reading can be diagnostic-positive even when the tail's largest events are governed by a distinct mechanism, and that an outlier-test (the dragon-king test) is the appropriate secondary diagnostic. Our current pipeline does not run that secondary test.

I would value 30 minutes of your time to discuss (a) whether adding a dragon-king secondary diagnostic to the band-test for finance and power-grid systems would meaningfully strengthen the protocol, and (b) whether co-authorship on a finance-and-grid focused replication sub-paper would be of interest. We are not in a hurry; even a written response noting whether the framing is misguided would help us decide whether to invest in the secondary diagnostic now or to defer it.

Sincerely,
Qinghui Wan

- arXiv preprint: pending (local copy `paper/anti-phacking-unified-2026-05-15.md`)
- Dataset DOI: https://doi.org/10.5281/zenodo.19615170
- Repo: https://github.com/dada8899/structural-isomorphism
