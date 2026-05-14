# NumFOCUS Comprehensive Fiscal Sponsorship Application — structural-isomorphism

**Status**: Draft v0.1 (2026-05-15)
**Target submission window**: 2026-Q4 / 2027-Q1 (after first arXiv acceptance and ≥ 5 external contributors)
**Project**: structural-isomorphism — open infrastructure for cross-domain universality-class validation
**Project lead**: @dada8899 (BDFL)
**Repository**: https://github.com/dada8899/structural-isomorphism
**License**: MIT (code) + CC-BY-4.0 (datasets) + CC-BY-4.0 (docs)

> This document is a working draft of our application to the NumFOCUS Comprehensive Fiscal Sponsorship Program. It is intended both as a self-assessment (what gaps must we close before submitting?) and as the substantive content we will paste into NumFOCUS' online application form when ready. Sections map to the canonical NumFOCUS FS criteria as of 2024-2025.

---

## 1. Project Mission

structural-isomorphism is open infrastructure for cross-domain universality-class validation. We collect, normalize, and analyze event-stream datasets from physically and socially diverse systems — neural avalanches, solar flares, earthquakes, DeFi liquidation cascades, bank failures, wildfire propagation, lake dissolved-oxygen excursions, freeway traffic jams, and GitHub-star bursts — and run a unified statistical pipeline (avalanche-size scaling, branching parameter, crackling-noise exponent collapse, autocorrelation, finite-size scaling) to test whether they belong to the same universality class as self-organized criticality (SOC).

We provide three things the scientific-computing community currently lacks:

1. **A reproducible cross-domain SOC validation pipeline** — built in Python, MIT-licensed, exposed both as a CLI (`python -m soc_pipeline`) and as a Pandas accessor (`df.soc.fit_avalanche()`), with a Jupyter widget for interactive exploration. The same code path runs against 13 verified systems today.
2. **An open dataset with content-addressed versions and SHA-pinned Zenodo archival** — every paper or notebook can pin to an exact byte-for-byte snapshot. Datasets are CC-BY-4.0 with explicit provenance trails.
3. **A multi-vendor LLM judging framework for adversarial replication** — a peer-review-like adversarial layer where independent LLMs (Claude Opus, GPT-4-class, DeepSeek-R1, Kimi K2) attempt to falsify each claim against a pre-registered exponent band. Disagreements are surfaced, not hidden, and the full A/B audit is published with each release.

The project sits squarely inside NumFOCUS' focus areas: open-source scientific Python tooling, reproducible research, and infrastructure that lowers the cost of replication. Our long-term aim is for structural-isomorphism to play the role for cross-domain criticality research that astropy plays for astronomy or scikit-learn for ML — a community-owned baseline that any working scientist can pip-install and trust.

## 2. Open Source License

- **Source code**: MIT License (`LICENSE` in repo root). MIT was chosen for maximum reusability; we explicitly want our pipeline absorbed into downstream commercial and academic tooling without friction.
- **Datasets**: CC-BY-4.0 (`data/LICENSE.data`). Attribution back to upstream sources (FDIC, USGS, NOAA, etc.) is preserved per-record; structural-isomorphism's contribution is the normalization and cross-domain schema.
- **Documentation**: CC-BY-4.0 (`docs/LICENSE.docs`).

All three licenses are OSI-approved or recognized by the Open Definition. No CLA is required from contributors — we use the Developer Certificate of Origin (DCO) via signed commits. We have explicitly chosen not to dual-license or relicense for monetization.

## 3. Project Leadership

### Current state (2026-05)

- **BDFL**: @dada8899 (founder, sole maintainer). Final authority on all decisions per `GOVERNANCE.md`.

### Planned transition: 3-member Maintainer Council

`GOVERNANCE.md` documents the transition trigger and procedure. In summary:

- **Trigger**: whichever of these comes first — (a) externally-merged contributions reach ≥ 5/quarter, (b) first arXiv acceptance lands, or (c) calendar date 2027-01-01.
- **Composition**: 3 members — BDFL + 2 external — selected via open call, 14-day public comment period, BDFL ratification (veto reserved only for conflict-of-interest).
- **Voting**: simple majority for technical decisions; 2/3 supermajority for governance/license changes; 100% consensus required for CoC enforcement against fellow council members.
- **Terms**: 12 months, staggered, renewable. BDFL term is perpetual until self-stepdown.

The council structure is deliberately small at first (3 members) to keep coordination cost low while we are sub-50 contributors; it can expand to 5-7 via amendment vote.

### Succession

Per `GOVERNANCE.md` § Emergency Procedures: ≥ 30 days of unresponsive BDFL → council can co-opt a third member for quorum; ≥ 90 days → council can elect an interim BDFL via 2/3 vote, with NumFOCUS notified.

## 4. Code of Conduct

The project adopts the [Contributor Covenant v2.1](CODE_OF_CONDUCT.md), with an explicit enforcement-contact line and escalation path. Reports route to `conduct@structural-isomorphism.org` (alias TBD; for now: @dada8899 via GitHub Discussions Meta category, with the option to email directly for privacy-sensitive reports).

Enforcement actions follow the Contributor Covenant Enforcement Ladder:

1. **Correction** — private written warning, public clarification if needed.
2. **Warning** — formal warning with consequences for continued behavior.
3. **Temporary ban** — 7-90 days, no community interaction.
4. **Permanent ban** — repeated or egregious violation.

The 100%-consensus requirement for CoC actions against fellow council members (per GOVERNANCE.md) is deliberate: governance rot in OSS communities most often starts with the inability to discipline insiders. We want the bar to be high enough that no single faction can capture enforcement, but the floor to be a real floor — council members are not above the CoC.

## 5. Public Roadmap

We publish roadmaps as living markdown documents under `docs/future/`:

- `W7-A-academic-value-roadmap-2026-05-13.md` — scientific milestones (preprints, peer review, datasets, conferences)
- `W7-B-engineering-value-roadmap-2026-05-13.md` — engineering and infrastructure (CI, packaging, performance)
- `W7-C-community-roadmap-2026-05-13.md` — community building (this application sits inside W7-C)
- `W7-D-product-value-roadmap-2026-05-13.md` — researcher-facing tooling (web app, notebooks, tutorials)

Each roadmap has dated milestones, owners, and verification criteria. Quarterly review cadence — published as part of the release notes.

GitHub Projects mirrors the roadmaps for tactical execution; the markdown is the source of truth.

## 6. Funding Need

We anticipate a modest, predictable funding need of **$5,000 - $15,000 / year** in the first two years of NumFOCUS sponsorship, growing to ~$30,000/year by year three if external adoption hits W7-A goals.

### Year 1 budget (estimated $8,000)

| Category | Amount | Notes |
|---|---|---|
| LLM API costs (multi-vendor judging) | $2,400 | ~$200/month for OpenRouter (Claude, GPT-4-class, DeepSeek, Kimi) running adversarial-replication CI on PRs. Caps enforced per `docs/MEMORY/preferences/preferences_auto_mode.md` |
| Benchmark dataset CI compute | $1,500 | GitHub Actions large-runner minutes for full-pipeline regression on releases |
| Dataset re-archival to Zenodo | $0 | Free tier sufficient; we pin DOIs |
| Domain + hosting (docs site, web app) | $400 | structural-isomorphism.bytedance.city + cdn |
| Conference travel — 1 maintainer × 1 conference | $2,500 | NetSci, APS March Meeting, or Conference on Complex Systems |
| Swag for first contributors (stickers, postcards) | $400 | First-PR gifts |
| Contingency / buffer | $800 | |

### Year 2-3 scaling

If external adoption grows (W7-A goal: 3 papers cite us, ≥ 50 GitHub-stars-from-academic-institutions), budget grows to support:

- Travel for 2-3 council members to two conferences each
- Sprint days / docathons ($1,500 - $3,000 per event)
- Honoraria for tutorial authors ($500/tutorial)
- Possible part-time technical writer ($5,000-10,000)

We deliberately under-budget compute: long-running heavy experiments (e.g. full re-derivation of universality-class boundaries on 100+ systems) we expect to run on academic compute allocations the maintainers already have access to. NumFOCUS funds should subsidize community work, not science compute.

### Revenue sources

- Initial: NumFOCUS pass-through donations (individual + corporate)
- Mid-term: research grants (NSF CSSI, Sloan, Templeton-style cross-disciplinary) routed through NumFOCUS' 501(c)(3) status
- Long-term: GitHub Sponsors via the NumFOCUS umbrella; one-time donations from researchers who use the pipeline in published work

We do **not** plan to charge for any service, run a SaaS, or sell a "Pro" version. The pipeline and dataset stay free forever; that commitment is enshrined in `GOVERNANCE.md` § License-Change Threshold (requires 2/3 council supermajority + 60-day public-comment period + BDFL co-sign).

## 7. Community Building

We are at the early phase of community formation (sub-10 external contributors as of 2026-05). Existing infrastructure:

- **Discord server** — scaffolded per W9-E with channels for `#help`, `#research`, `#dev`, `#announcements`, `#good-first-issues`. Auto-invite link in README.
- **Newsletter** — monthly `docs/newsletter/` rollup, published as RSS + sendable digest.
- **Good-first-issues** — labeled per CONTRIBUTING.md, each with brief, acceptance criteria, and effort estimate. Mentored by BDFL or council member.
- **Tutorials** — `docs/tutorials/` covers (1) running the pipeline against a new dataset, (2) interpreting the LLM judge audit, (3) writing a pre-registration. Each is reproducible end-to-end in a fresh venv.
- **Office hours** — fortnightly 60-min open Zoom (calendar in Discord), recorded and posted to docs site.
- **Conferences** — submitting talks/posters to NetSci 2026, APS March 2027, Conference on Complex Systems 2026.

Planned 2026-H2:

- Hackathon co-located with NetSci (sponsored by NumFOCUS if accepted)
- "Universality-class challenge" — open call for community-submitted datasets, with leaderboard + DOI
- Translations (Chinese, Spanish, Portuguese) of getting-started.md — bounty-funded

## 8. Existing Citations / External Adoption

Honest current state (2026-05-15):

- **External citations**: 0. Our preprint (`docs/papers.md`) is under preparation; arXiv submission planned 2026-Q3. No published paper yet cites structural-isomorphism by name.
- **Zenodo dataset DOI**: pending first formal release; we expect to mint the DOI on v1.0 tag (planned 2026-Q4).
- **GitHub stars**: ~early-stage (single digits to low double digits as of session #9). Tracked weekly in `docs/maintenance/star-history.md`.
- **External merged PRs**: 0 from outside @dada8899's controlled accounts. (Counted strictly: only PRs from email domains the BDFL does not own.)
- **Downloads**: pip package not yet published; downloads tracked from time of first PyPI release.
- **Mentions in academic talks**: 0 known.

We are filing this application aware that we are at the very early end of NumFOCUS' adoption criteria. Our position: **submit with honest numbers, plan B (Open Collective) as fallback**, and use the application process itself as forcing function for the W7-A milestones (preprint, dataset DOI, first three external citations) that will make a year-2 resubmission strong.

## 9. References

NumFOCUS Comprehensive Fiscal Sponsorship typically asks for 2-3 senior researchers willing to vouch for the project's scientific merit and the maintainer's character. The following are candidate referees; **explicit consent has not yet been obtained** and obtaining it is part of W9-B follow-up.

1. **[TODO: get explicit consent]** — Dr. Dietmar Plenz, NIH — pioneer of neural avalanche research; we have validated against his published datasets and his methodology informed our neural-SOC implementation.
2. **[TODO: get explicit consent]** — Dr. Viola Priesemann, MPI for Dynamics and Self-Organization — branching-parameter methodology, criticality in neural systems.
3. **[TODO: get explicit consent]** — Dr. Marten Scheffer, Wageningen University — regime shifts in ecological systems; we use his published lake DO datasets in soc-lake validation.
4. **[TODO: get explicit consent]** — Dr. Aaron Clauset, University of Colorado Boulder — power-law statistics methodology; we use the Clauset-Shalizi-Newman estimator implementation directly.

Strategy for obtaining consent: cold-email each in 2026-Q3 with the preprint, a 1-pager explaining the project's relationship to their work, and a request to be listed as referee. We expect 1-2 acceptances out of 4; that meets the NumFOCUS minimum.

A secondary list of referees (younger PIs, postdocs, industry researchers) is in `docs/community/REFEREES_INTERNAL.md` (not public; do not commit).

## 10. Plan B if Rejected

NumFOCUS Comprehensive FS has a real bar, and we may not clear it on first submission. Contingencies, in order of preference:

1. **NumFOCUS Affiliated Project status** — a lighter-weight relationship that grants the brand and some community access without full fiscal sponsorship. Affiliate status is usually easier to obtain and we can mature toward FS over 12-18 months.
2. **Open Collective Foundation** (US 501(c)(3) host) — pass-through donations, similar fiscal-host service, lower bar for entry. We have already reserved the project name on Open Collective as a placeholder.
3. **Software Freedom Conservancy** — alternative US 501(c)(3) fiscal sponsor for FOSS projects. Higher bar than Open Collective but more focused on software/open-source than NumFOCUS.
4. **Plain GitHub Sponsors + no fiscal host** — least preferred (no 501(c)(3) deductibility for donors; no formal financial transparency); we would only fall back to this if all three above reject us.

In all four cases, the governance structure (3-member council per GOVERNANCE.md) and license commitments (MIT + CC-BY-4.0, locked) stay the same. NumFOCUS adoption is a force-multiplier, not a foundation; the project's commitments to the community do not depend on it.

## 11. Financial Transparency Commitments

If accepted by NumFOCUS, we commit to:

- **Quarterly financial reports** published in `docs/community/finance/YYYY-QN.md` — every donation source (anonymized below $1,000), every expenditure with purpose, running balance, plus a plain-English summary of "what we spent money on this quarter".
- **Annual budget public-comment period** — Q4 each year, draft budget published in `docs/community/finance/YYYY-budget-draft.md` with 30-day issue-based comment window before council ratification.
- **Conflict-of-interest disclosures** — any council member whose employer or grant sponsor donates to the project recuses from related budgeting decisions, with the recusal logged.
- **No undisclosed sponsorships** — any organizational sponsor that wants to fund a specific feature, dataset, or maintainer time must be disclosed publicly. We will not accept "ghost-sponsored" work.

## 12. Reproducibility & Scientific Standards

We commit to (and currently practice):

- **Pre-registration of exponent bands** before running adversarial-replication tests (`docs/pre-registrations/`)
- **All-A/B-judge-disagreements published** — `docs/llm-ab-test-2026-05-14.md` is the working template; on every release we publish the full judge audit, including disagreements.
- **Content-addressed dataset versioning** — every JSONL/CSV/Parquet in `data/` and `v4/validation/` is SHA-256 pinned; the manifest is part of every release.
- **Negative results published** — `docs/papers.md` § Anti-p-hacking commits to publishing universality-class membership tests **even when they fail** (e.g. domains that look SOC-like but don't pass the full battery). Negative results are scientifically valuable and the field underpublishes them.
- **Reviewer onboarding** — `docs/methodology/reviewer-checklist.md` describes what a third-party reviewer should check on a paper or PR that uses our pipeline.

## 13. Maintainer Bandwidth & Bus Factor

Honest assessment:

- **Current bus factor**: 1 (BDFL @dada8899)
- **Target after first council**: 3 (BDFL + 2 council members, all with merge rights, deploy keys, and infrastructure access)
- **Documentation of operational secrets**: maintained in `docs/SECRETS_BREAK_GLASS.md` (encrypted with age, key held by BDFL + one council member after formation)

The bus-factor-1 state is the largest risk we are knowingly running with right now. Council formation is the primary mitigation.

## 14. Conflict-of-Interest Statement

- **BDFL @dada8899**: no current paid affiliation with any organization whose interests conflict with structural-isomorphism. Operates the project on personal time + personal infrastructure. Funding sought via NumFOCUS would be received via NumFOCUS pass-through, not personally.
- **No grants or contracts** currently fund the project. If/when grants are secured, they will be disclosed in `docs/community/finance/`.
- **No paid endorsements** of vendors. The multi-vendor LLM judging framework deliberately uses 3-4 providers to avoid single-vendor capture.

## 15. Brand & Trademark

We hold **no trademark** on the name "structural-isomorphism" and have no intention to seek one. The name and logos (when designed) will be CC-BY-4.0 along with documentation. Forks may use the name freely as long as they do not misrepresent NumFOCUS sponsorship status.

If NumFOCUS adoption proceeds, we will adopt the standard NumFOCUS trademark policy by reference.

## 16. Application Checklist (Internal Tracking)

Pre-submission gates we want to clear before pressing "submit" on the actual NumFOCUS form:

- [ ] Preprint on arXiv (W7-A milestone, 2026-Q3 target)
- [ ] Zenodo dataset DOI minted (v1.0 release, 2026-Q4)
- [ ] ≥ 5 external contributors with merged PRs (W7-C goal)
- [ ] At least 1 referee letter (W9-B follow-up; need 2 by submission)
- [ ] Maintainer council in place (per GOVERNANCE.md trigger)
- [ ] Discord ≥ 50 members (W9-E)
- [ ] CI pipeline running adversarial-replication on every release
- [ ] Public financial dry-run (mock quarterly report) — demonstrates the cadence we'd hold ourselves to

Expected submission window: **2027-Q1** if all above clear; **2027-Q3** as fallback.

## 17. Acknowledgments

This application draft draws on the public submission templates and post-mortems of:

- [JOSS](https://joss.theoj.org/) (review criteria for scientific software)
- [astropy NumFOCUS sponsorship](https://www.numfocus.org/sponsored-project-application) (the canonical template)
- [scikit-learn governance](https://scikit-learn.org/stable/governance.html) (council structure)
- [matplotlib governance](https://matplotlib.org/stable/devel/min_dep_policy.html) (deprecation policy template, future work)

We thank the NumFOCUS staff and community in advance for considering us, and explicitly thank the open-source scientific Python ecosystem for being the standard we are trying to live up to.

---

*Draft owners*: @dada8899
*Review status*: pending external review (target W11-A)
*Submission status*: not yet submitted
*Last updated*: 2026-05-15
