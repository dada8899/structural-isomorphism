# Cover letter — C1 unified preprint v0.4 (arXiv submission)

**Title.** A pipeline for cross-domain validation of self-organized
criticality: completing the taxonomy.

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project
(independent researcher). Project site: https://structural.bytedance.city

**Primary archive.** `physics.soc-ph` (Physics and Society)
**Cross-list.** `q-fin.ST` (Statistical Finance) ·
`q-bio.NC` (Neurons and Cognition) ·
`cond-mat.stat-mech` (Statistical Mechanics, new in v0.4)

---

## What this paper does

This is v0.4 of a coordinated cross-domain SOC validation effort. v0.3
(prior arXiv release) assembled one fixed Clauset-MLE / likelihood-ratio
/ Omori-Utsu pipeline and applied it unchanged to a five-system SOC
deep core: USGS earthquakes, S&P 500 daily returns, three DeFi lending
protocols, mouse-cortex neural avalanches, and four synthetic non-SOC
nulls. v0.4 adds §3.6 "Completing the taxonomy" — using the same frozen
pipeline to close empirical verdicts on 18 additional candidate
universality classes from the project's cross-judge B3 priors. The new
result: a binary mechanism-vs-descriptor screen (cross-domain scatter
threshold max/min(median θ) > 10× AND ≥ 2 regimes spanned) that
cleanly separates 6 REJECT-CONFIRMED descriptor classes (EVT, copula,
fBm, Markov, damped oscillator, delay-differential) from 10
PASS-CONFIRMED mechanism classes, with 5 SPLIT decisions and 1 MERGE
recommendation netting the project's taxonomy from 26 candidates to
~27–28 empirically supported classes.

## v0.4 vs v0.3 increment

- New §3.6 (18-class verdict matrix + cross-domain scatter threshold).
- New methodological screen (descriptor-vs-mechanism binary).
- Empirical base 27 → 45+ SOC validation systems.
- New references 46–50 (verdict reports + Halford 1992 +
  Stumpf–Porter 2012 + Cohen–Erez–ben-Avraham–Havlin 2000).
- New Appendix A4 (per-class reproducibility map).
- New checklist items 7 + 8 (Wave 3 plan, taxonomy diagram).

## Cross-list rationale

v0.4 adds `cond-mat.stat-mech` to the v0.3 cross-list set because §3.6's
mechanism-vs-descriptor screen draws explicitly on the equilibrium
critical-phenomena literature (Ornstein–Zernike Lorentzian, Anderson
localization, percolation scaling) that sits in stat-mech.

## Reproducibility

- GitHub: https://github.com/dada8899/structural-isomorphism (PUBLIC, MIT)
- PyPI: `soc-pipeline 0.1.0` (live), `iso-graphs`, `null-controls`
- Zenodo: DOI PENDING (new Phase-1–5 + v0.4 §3.6 deposit; v0.4 release
  will retarget after mint)
- 4,888+ KB entries open in repo; v0.4 §3.6 sub-agent reports at
  `docs/sessions/v04-*-report.md` (17 reports) + per-class artefacts at
  `v4/validation/<class>/`.

## Honest disclosures

- 11 of 18 v0.4 classes carry **synthetic** anchors only (real-data
  pending Wave 3).
- One early Layer-4 cross-domain prediction was backtested out-of-sample
  and returned **Sharpe = −0.23** (publicly reported). v0.4 is a
  methodology contribution, not a prediction-validated claim.
- Phase 2 (S&P 500) raw-tail Vuong test favors lognormal at R = −6.12;
  the SOC verdict rests on the joint signature, not on rejecting
  lognormal (see §6.1).
- Internal proxy review identified ~33% reject rate on candidate
  classes; published.

## Conflict of interest

None. Independent-researcher project; no DeFi-protocol, exchange, or
neurolab funding. All raw data sources public.

## Contact

[CONTACT_EMAIL_PENDING] · ORCID [ORCID_PENDING] · Project site as above.

## Companion preprints

v0.4 supersedes v0.3 (arXiv ID PENDING; if v0.3 has not yet been
submitted, post v0.4 only). Four single-phase preprints (Phases 1–4
individually, refs 41–44) and the C4 mechanism-vs-descriptor follow-up
(ref 47) are intended to be submitted in coordinated waves over the
following 6–8 weeks.
