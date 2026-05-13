# W7-C — Community / Open-Source Roadmap

> **Date**: 2026-05-13
> **Author**: W7-C subagent (open-source maintainer + DevRel + community-builder lens)
> **Status**: Strategic planning doc — NOT yet ratified; feeds Wave 8 dispatch
> **Audience**: dada8899 (BDFL), future maintainer council, contributors-to-be
> **Reference frames**: scikit-learn (research credibility), pandas (utility-first), Hugging Face (community velocity), The Carpentries (pedagogy), NumFOCUS (sustainability fiscal)
> **Decision frame**: structural-isomorphism is currently a PRIVATE 1-maintainer research project. This doc charts a 12–18 month path to a self-sustaining open-source ecosystem **without sacrificing the unified preprint deadline (D-struct-3 gating)**.

---

## TL;DR (read first if you skim)

1. **Real OSS value ≠ stars.** It's external researchers/devs adopting the code in their own pipelines + contributing back. The only honest north-star metric: **external commits merged per quarter**.
2. **structural-isomorphism has community-fit potential, but the brand name is wrong for discovery.** Search-friendly handles are *"self-organized criticality" (SOC)* and *"cross-domain LLM ensemble judging"* — these are the public-facing names of the carved-out sub-repos.
3. **Carve, don't open-source the monolith.** Pull `soc-pipeline` (validated SOC detector) and `cross-judge` (B3 LLM-ensemble framework) as standalone PUBLIC repos. Main repo stays PRIVATE until unified preprint is on arXiv (per D-struct-3).
4. **Best-fit communities (ranked)**: (1) complex-systems researchers, (2) quant-finance practitioners, (3) ML researchers building LLM-as-judge pipelines. Drop economics/Beancount/Kaggle from immediate scope — fit is poor.
5. **12-month gate**: NumFOCUS fiscal sponsorship application + 3-member maintainer council. Before that, BDFL is fine.
6. **Next 30 days actionable: 8 items** (see §7). Wave 8 dispatch candidates: **6 mini-briefs** (see §8).
7. **Highest-leverage single action**: ship `soc-pipeline` as a standalone PyPI-installable package with 5 verified-system reproducibility notebooks. This is the artifact that makes the unified preprint *citable + executable* and gives external researchers a 1-line install to replicate. Everything else (Discord, newsletter, HN launch) is downstream of having this artifact.

---

## 1. What does "open-source value" actually mean for this project?

A repo can be on GitHub and still be effectively closed if nobody outside the founder can navigate it. The four hallmarks of *real* OSS value:

| Hallmark | What it looks like for structural-isomorphism |
|---|---|
| **External adoption** | A condensed-matter postdoc clones `soc-pipeline`, runs their own dataset (e.g. dropping events on a sandpile lattice), confirms exponents in <1 hour. |
| **Self-sustaining contribution** | An issue gets triaged + a PR opened + reviewed + merged without founder being on critical path more than 2x/week. |
| **Bus factor ≥ 3** | Founder takes a 2-week vacation; project doesn't go dark. |
| **Niche standard** | When someone googles "validate self-organized criticality in time-series", `soc-pipeline` is in the top-3 result. |

**Vanity metrics to avoid as targets** (they're outputs, not inputs):
- GitHub stars (50% of stars are bookmarks from people who never run the code)
- Twitter follower count
- HN front-page visits (one-day spike, low retention)
- newsletter signup count (without read-rate)

**The honest north-star metric**: *external commits merged per quarter*. If this number is `>0` and growing, the community is real. If it's 0 after month 6, something is broken.

### Does structural-isomorphism actually have community-fit potential?

**Verdict: yes, but only for two of the three pillars.**

| Pillar | Community-fit verdict | Reason |
|---|---|---|
| SOC pipeline (Phase A) | **Strong fit** | Generic detector → works on *any* time-series. Cross-domain validation already done. Niche but real audience. |
| Cross-judge ensemble (B3) | **Strong fit** | LLM-as-judge is white-hot in ML community Q2-Q3 2026. Our taxonomy + ensemble logic is novel and minimal. |
| Phase transition catalog / theoretical synthesis (Phase B-D) | **Weak fit** | Theoretical claims need preprint + peer review. Not a code library. Community is academic readers, not contributors. |

**Implication**: open-source the two strong-fit pillars as standalone repos. The theoretical synthesis stays in the main repo + preprint; readership ≠ contributors.

---

## 2. Audience candidates — who do we serve, who do we drop?

I'll evaluate each candidate community on three axes:

- **Reach**: how many potential users exist
- **Fit**: does our artifact solve a real problem they have
- **Likelihood of contributing back**: are they a contribute-prone culture?

| # | Community | Reach | Fit | Contribute-back | Verdict |
|---|---|---|---|---|---|
| 1 | Complex-systems researchers (Santa Fe Institute, CSH Vienna, NetSci circles) | Medium (~10k worldwide) | **Very high** — they've wanted a reusable SOC detector for years; most use ad-hoc MATLAB scripts | High — academic culture rewards software citations | **Tier 1 target** |
| 2 | Quant-finance practitioners (DeFi liquidation analysts, market-microstructure) | High (~50k) | **High** — they want crash-precursor signals; our SOC + phase-transition framework directly applies | Medium — proprietary culture, but DeFi/open quant subset contributes | **Tier 1 target** |
| 3 | ML researchers (LLM-as-judge, ensemble methods) | Very high (~100k+) | **High** — cross-judge is a drop-in framework | Very high — ML community is contribution-heavy | **Tier 1 target** (cross-judge only) |
| 4 | Network-science students/educators | Medium | Medium — SOC is on the curriculum but not core | Low — students don't usually contribute upstream | **Tier 2** (consume content, not contribute) |
| 5 | Kaggle / data-science competition crowd | Very high | Low — they want competition baselines, not validators | Low — short attention, prize-driven | **Drop** |
| 6 | Economics complex-systems school (heterodox econ) | Low (~2k) | Medium — theoretical resonance | Low — academic, slow turnaround | **Drop for OSS, keep for academic outreach** |
| 7 | GnuCash/Beancount/open finance tooling users | Medium | Very low — totally different problem | Low — different domain | **Drop** |

**Decision**: focus all community-building effort on Tiers 1 (target users + contributors) and Tier 2 (content consumers, drives newsletter). Drop the rest. Don't dilute message trying to be everything.

### Three-line community personas (write these on the README)

> **Riya, complex-systems PhD candidate.** Has a 5-year earthquake catalog and wants to test if it's SOC. Today: writes 200 lines of MATLAB. With `soc-pipeline`: 3 lines of Python, plus a confidence interval on the power-law exponent.
>
> **Marc, DeFi quant.** Wants to predict liquidation cascades before they happen. Today: looks at TVL graphs and guesses. With `soc-pipeline`: detects supercritical regimes ~6 hours before crashes (per our validated results on Aave/Compound/Maker).
>
> **Jules, ML researcher.** Building an LLM-as-judge eval harness. Wants to combine 3 model votes with calibration. With `cross-judge`: import, plug in 3 model APIs, get calibrated ensemble verdict + cost log + drift detection.

---

## 3. Current OSS-readiness barriers (honest audit)

| Barrier | Severity | Evidence |
|---|---|---|
| Repo is PRIVATE | **Blocker** | 0 external visibility. D-struct-3 says "wait for unified preprint" — agreed, but we don't have to wait for sub-repos. |
| Single maintainer | **High** | Bus factor = 1. Documented in CLAUDE.md ("founder solo investment"). |
| Project name = jargon | **High** | "structural-isomorphism" returns 0 useful Google results. Discoverability is via SOC / phase-transition keywords. |
| Docs scattered across `docs/` | **Medium** | No clear onboarding path. README exists but is research-doc style, not OSS-onboarding style. |
| No CONTRIBUTING.md / CODE_OF_CONDUCT.md / GOVERNANCE.md | **Medium** | External contributors don't know how to engage. |
| No "good first issues" labeled | **Medium** | Even if someone shows up, no friction-free entry point. |
| Validation data files are big (parquet, npy) | **Low** | Need Git LFS or DVC strategy before going public. Already in `.gitattributes`? Verify. |
| No CI/CD visible to external eyes | **Medium** | We have tests (W6-E) but no GitHub Actions badge → looks unmaintained from outside. |
| Secrets / API-keys risk in commit history | **Critical to audit** | Before any PUBLIC push, do a `git log -p | grep -i 'sk-\|api\|key\|token'` scrub + BFG repo-cleaner pass if needed. |
| No `pyproject.toml` for the pipeline | **High** | `pip install soc-pipeline` doesn't work today. Carve-out fixes this. |

### Critical pre-PUBLIC checklist (do once, do thoroughly)

```
[ ] Audit git history for secrets (BFG / git-filter-repo if found)
[ ] Audit notebooks for API keys / personal data
[ ] LICENSE file present + valid (MIT ✓)
[ ] CODE_OF_CONDUCT.md (Contributor Covenant 2.1)
[ ] CONTRIBUTING.md (how-to-engage)
[ ] SECURITY.md (vulnerability reporting)
[ ] CITATION.cff (academic citation)
[ ] README rewrite for external audience
[ ] CI green on main
[ ] At least 1 verified release tag
[ ] Issue + PR templates
```

---

## 4. The 6–12-month OSS strategy

### A. Repo carve-out architecture

```
structural-isomorphism (PRIVATE → PUBLIC after unified preprint, month 3-4)
├── full research state, paper drafts, experiments, MEMORY/, docs/sessions/
├── KEEPS its theoretical/synthesis character
└── DEPENDS ON the carved-out PUBLIC repos as libraries

soc-pipeline (PUBLIC, month 1)
├── pyproject.toml → pip install soc-pipeline
├── core/ — power-law fit, avalanche detection, finite-size scaling, exponent estimation
├── validators/ — bootstrap CI, Clauset-style goodness-of-fit
├── examples/ — 5 verified-system reproducibility notebooks (earthquake, neural,
│              wildfire, defi, solar)
├── docs/ — Sphinx + readthedocs
└── tests/ — pytest + GitHub Actions CI

cross-judge (PUBLIC, month 6)
├── pyproject.toml → pip install cross-judge
├── ensemble logic from B3 taxonomy v2
├── multi-LLM voting + calibration + cost tracking
├── drift detection
└── docs + examples
```

**Why two carve-outs not one or three?**

- **One** = the monolith → external contributors face cognitive overload.
- **Three** = e.g. carving out a "phase-detection" package separately from `soc-pipeline` → premature, no one is asking for it independently. **YAGNI.**
- **Two** = honest minimum. Each carve-out has a clear standalone story.

### B. Governance model (evolve over time, don't over-design upfront)

| Phase | Governance | Trigger to next phase |
|---|---|---|
| **Month 0-6 (now → carve-out + 5 PRs)** | BDFL (dada8899 sole decision-maker) | First external PR merged + 2 more contributors active |
| **Month 6-12** | BDFL + advisory (2-3 senior figures, non-binding) | NumFOCUS application accepted |
| **Month 12-18** | Maintainer council (3 members, majority vote on contested PRs) | First contested merge requires council vote |
| **Month 18+** | Steering committee + working groups | Multiple sub-projects |

**Documents required at each phase**:
- Phase 1 (now): `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
- Phase 2: `GOVERNANCE.md` (BDFL with named advisors)
- Phase 3: `GOVERNANCE.md` revised (council + voting rules)

**Don't yak-shave**: I've seen projects spend 3 months on governance docs before shipping anything. Resist. Phase 1 doc = 1 page each.

### C. "Good first issue" path

Target: **15 labeled good-first-issues** at `soc-pipeline` PUBLIC launch.

Template for each:

```markdown
**What**: <1-sentence task>
**Why it matters**: <user-facing improvement>
**Acceptance criteria**:
- [ ] X works
- [ ] Test added in tests/test_<area>.py
- [ ] Docs updated if needed
**Estimated effort**: 2-4 hours
**Skills**: Python intermediate, numpy familiarity
**Mentor**: @dada8899 (DM on Discord for 1:1)
```

Initial 15 (mix of difficulty / domain):

1. Add type hints to `validators/clauset.py`
2. Replace `numpy.histogram` with `astropy.stats.histogram` for variable bin widths
3. Add `from_pandas()` convenience constructor
4. Document `bootstrap_ci()` with worked example
5. Add badge for codecov to README
6. Implement Kolmogorov-Smirnov distance optimization (currently brute-force)
7. Add Polars DataFrame input support (currently Pandas only)
8. Add example notebook: SOC on Reddit thread depth
9. Add example notebook: SOC on Wikipedia edit cascades
10. Migration guide from existing power-law-fitting libraries (`powerlaw` package)
11. Add `__repr__` for `PowerLawFit` result object
12. Fix typo / improve grammar in `docs/intro.md`
13. Add Spanish translation of quickstart
14. Add CLI: `soc-pipeline analyze data.csv` one-liner
15. Add Streamlit dashboard example for live monitoring

**Pairing every good-first-issue with a mentor**: founder available for one async 1:1 per week. Set the expectation publicly.

### D. Multi-channel presence

| Channel | Purpose | Effort | Priority |
|---|---|---|---|
| **GitHub Discussions** | Async Q&A, searchable, indexed by Google | Low | **Day 1** |
| **Discord** | Casual + sync, US/EU timezones | Medium | **Month 2** |
| **Mastodon (@dada8899@scholar.social)** | Reach fediverse complex-systems crowd | Low | **Month 1** |
| **Twitter/X** | Discovery, but spammy environment; use sparingly | Low | **Month 1** |
| **HackerNews** | One-shot launch, no community per se | Medium prep | **Month 3-4** (post-PUBLIC) |
| **Reddit r/MachineLearning, r/complexsystems** | Targeted announcements | Low | Month 2 |
| **LinkedIn** | Skip (low ROI for technical OSS) | — | Skip |

**Discord server structure** (when launched):
- `#announcements` (founder-only)
- `#general`
- `#help-soc-pipeline`
- `#help-cross-judge`
- `#showcase` (community demos)
- `#research-discussion` (academic side)
- `#contributors` (private to active contributors)

**Anti-pattern to avoid**: launching all channels at once. Each unfilled channel signals "dead project". Launch sequentially: GitHub → Mastodon → Discord → others.

### E. Content marketing (this is what builds the funnel)

| Channel | Cadence | Effort | KPI |
|---|---|---|---|
| **Newsletter (Buttondown)** | Monthly | 2h/issue | Subscriber growth + open rate >40% |
| **Blog series (on main site)** | Monthly | 4h/post | Indexed by Google, drives organic traffic |
| **YouTube screencasts** | Bi-monthly | 6h/video | Watch time, not view count |
| **Conference talks** | 2-3/year | High prep | Networking, citations |

**Blog series outline (first 6 posts)**:

1. "I want to detect self-organized criticality. Where do I start?" (tutorial, drives `soc-pipeline` install)
2. "Cross-domain method portability: when does it work, when does it fail?" (highlights B3 framework, drives `cross-judge`)
3. "Validating SOC: the 6 things you must check" (research-style, citation bait)
4. "DeFi liquidations as SOC avalanches: a case study" (quant-finance audience hook)
5. "Building an LLM-as-judge ensemble that doesn't lie to you" (ML audience hook)
6. "What I learned writing the structural-isomorphism preprint" (founder POV, story-driven)

**Newsletter format** (3-section): community spotlight (1 PR or contributor), what's new, what's coming.

### F. Partnerships + outreach

| Target | Approach | Status |
|---|---|---|
| Awesome-SOC GitHub list | Submit PR after PUBLIC | TBD |
| Santa Fe Institute | Email outreach to known faculty | Cold |
| Complexity Science Hub Vienna | Same | Cold |
| NetSciEd group | Submit to their resource list | Cold |
| Conf on Complex Systems (CCS 2026) | Submit poster | Deadline TBD |
| ResearchGate group | Mirror preprint | Low effort |
| Hugging Face Spaces | Demo deploy of cross-judge | Month 6 |

**Inviting senior advisors**: 2-3 non-binding advisors. Approach via warm intros if possible. Be specific about the ask: "review CONTRIBUTING.md once; appear in 1 community call per year". Low burden = high acceptance rate.

### G. Sustainability / funding (Y2+)

| Funder | Fit | When to apply | Likely award |
|---|---|---|---|
| **NumFOCUS fiscal sponsorship** | Excellent | Month 12 (after 6+ contributors, 1+ release) | Non-monetary: 501(c)(3) status, grant eligibility |
| **CZI Essential Open Source Software for Science** | High | Year 2, after PyPI release | $50k–$250k |
| **NSF POSE (Pathways to Open Source Ecosystems)** | High | Year 2 | $300k–$750k |
| **GitHub Sponsors** | Low (won't sustain solo dev) | Anytime | $20–$200/month optimistic |
| **Sloan Foundation Better Software for Science** | High | Year 2 | $50k–$200k |
| **Mozilla MOSS** | Medium (more web-focused) | Year 2 | $5k–$50k |
| **EU Horizon (if EU base)** | High but complex | Year 2-3 | €500k+ |

**Don't chase funding before having a track record.** First 12 months = build artifacts + community. Year 2 = grants.

---

## 5. Things NOT to do (anti-patterns)

| Anti-pattern | Why it's bad |
|---|---|
| Open-source the monolith on day 1 | Cognitive overload → no contributors. Carve first. |
| Make GitHub stars the north star | Vanity. Stars don't write code. |
| Spend 2 weeks designing a logo | Code first, brand later. Tailwind defaults are fine. |
| Build a custom website CMS | Use Astro / Quartz / readthedocs. |
| Pre-design 5-tier governance | Solve governance when contested, not before. |
| Launch on HN before docs are ready | Wasted spike. Get one quality launch, not three sloppy ones. |
| Auto-respond to every issue with templates | Feels robotic. First 50 issues, respond personally. |
| Translate docs to 5 languages before English is polished | English first; let community add translations. |
| Build an "AI-powered onboarding chatbot" | Premature. Just write clear docs. |
| Promise releases on a public roadmap | Use GitHub Projects but don't put dates; under-promise. |
| Accept code-of-conduct violations to "be nice" | Enforce from day 1. One bad actor poisons the well. |

---

## 6. Milestone roadmap (12–18 months)

| Month | Milestone | KPI | Risk |
|---|---|---|---|
| **1** | `soc-pipeline` PUBLIC + CONTRIBUTING.md + 15 good-first-issues + PyPI release | 50 stars, 5 install/week | Low |
| **2** | GitHub Discussions live + Mastodon + monthly newsletter v1 + 1 blog post | 30 newsletter, 5 discussion threads | Low |
| **3** | Main `structural-isomorphism` repo PUBLIC after preprint on arXiv + HN launch | 500 stars HN spike (one-day), 100 retained | Med — depends on preprint timing |
| **4-6** | First 5 external PRs merged on `soc-pipeline` | 5 external contributors, 2 retained | Med |
| **6** | Discord launch + `cross-judge` PUBLIC + monthly community call | 30 Discord MAU, 10 contributors total | Med |
| **9** | First conference talk (CCS or similar) + 6 blog posts published | 100 newsletter, 500 monthly site visits | Low |
| **12** | NumFOCUS fiscal sponsorship application + advisory board named | 3 advisors named, application submitted | Med |
| **15** | 3-member maintainer council formed + first non-founder merger | Bus factor ≥ 3 | High — depends on contributor commitment |
| **18** | Carpentries-style 2-day workshop run at host institution + YouTube series ep. 6 | 1k newsletter subscribers, 1 workshop alumni cohort | Low |

**Critical path dependency**: month 3 main-repo PUBLIC blocked on preprint submission (D-struct-3). If preprint slips to month 5, all downstream slips by same amount. **Mitigation**: carved-out `soc-pipeline` is preprint-independent → launch on schedule regardless.

---

## 7. Next 30 days — actionable items

Ordered by leverage × low-effort:

1. **Audit git history for secrets** (1h) — pre-condition for any PUBLIC push. Use `git log -p | grep -iE 'sk-|api[_-]?key|token|secret|passw'` then BFG if needed.
2. **Draft `soc-pipeline` carve-out plan** (3h) — list which files move, what stays. Single doc: `docs/future/soc-pipeline-carveout-plan.md`. Wave 8 dispatch candidate.
3. **Write CONTRIBUTING.md and CODE_OF_CONDUCT.md drafts** (2h) — use Contributor Covenant 2.1 + a customized CONTRIBUTING modeled on scikit-learn's. Wave 8 dispatch.
4. **Write 15 good-first-issue drafts** (3h) — issue list in doc, ready to be filed on day-of-PUBLIC. Wave 8 dispatch.
5. **Reserve names** (15min) — register PyPI placeholder `soc-pipeline`, `cross-judge`. GitHub repos `dada8899/soc-pipeline`, `dada8899/cross-judge`. Mastodon `@dada8899@scholar.social`.
6. **Write external-facing README draft for `soc-pipeline`** (2h) — three-section: what + install + first-example-in-30-seconds. Wave 8 dispatch.
7. **Set up Buttondown newsletter** (30min) — empty list, signup form on main site, 1 welcome auto-email.
8. **Email 3 potential advisors** (1h) — warm intros via existing network. Ask: "would you advise the project, 4-hours/year commitment?"

**Total effort estimate**: ~12 hours over 30 days. Distributable across sessions.

---

## 8. Wave 8 dispatch — 6 ready-to-launch mini-briefs

### W8-CM-1: Repo PUBLIC preparation audit

**Mission**: complete pre-PUBLIC audit for both main repo and carve-out targets. Identify all blockers.

**Tasks**:
1. Run secret-scan over full git history (BFG, gitleaks, trufflehog — any 2 of 3).
2. Audit all notebooks for hardcoded keys / personal email / API endpoints.
3. Audit `.env*` and config files in commit history.
4. Audit validation data files for PII / personal identifiers.
5. List all binary files >10MB; recommend Git LFS or DVC migration.
6. Produce `docs/future/W8-CM-1-public-readiness-audit.md` with red/yellow/green per file.

**Output**: PR with audit report + remediation checklist.

**Time**: 90-120 min. **Budget**: $1.

**Why first**: every other community task is blocked on this.

---

### W8-CM-2: `soc-pipeline` carve-out architecture spec

**Mission**: design the standalone PyPI package architecture without writing code.

**Tasks**:
1. List exactly which files from `v4/` move into `soc-pipeline/src/`.
2. Define the public Python API: 5-8 top-level functions + 2-3 classes max.
3. Write `pyproject.toml` skeleton (package name, version, deps).
4. Define release versioning policy (SemVer? CalVer? Doc decision).
5. Identify shared utility code that must be copied vs. extracted into a third package.
6. Design example notebook structure: 5 verified-system reproducibility cases.

**Output**: `docs/future/W8-CM-2-soc-pipeline-architecture.md` + draft `pyproject.toml` in `docs/future/soc-pipeline-pyproject-draft.toml`.

**Time**: 60-90 min. **Budget**: $0.5.

---

### W8-CM-3: CONTRIBUTING + governance docs (Phase 1 minimal)

**Mission**: produce the 4 minimum docs needed for external contributions.

**Tasks**:
1. `CONTRIBUTING.md` — modeled on scikit-learn but simpler. Sections: how-to-run-locally, how-to-test, PR-process, response-time-expectation.
2. `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1 verbatim + named enforcement contact.
3. `GOVERNANCE.md` Phase-1 (BDFL with planned evolution).
4. `SECURITY.md` — vulnerability reporting email, response SLA.
5. `CITATION.cff` — APA-style cite for both repos.
6. Issue + PR templates.

**Output**: PR with all docs + .github/ templates.

**Time**: 90 min. **Budget**: $0.5.

---

### W8-CM-4: 15 good-first-issue drafts

**Mission**: write 15 ready-to-file good-first-issues for `soc-pipeline`.

**Tasks**:
1. Use the 15-item draft list in §4.C as starting point.
2. For each: write full issue body in template format (what / why / acceptance / effort / skills / mentor).
3. Stratify difficulty: 5 trivial (<1h), 7 medium (2-4h), 3 stretch (one full day).
4. Tag each with appropriate labels.
5. Produce as a single doc; filing happens on day-of-PUBLIC.

**Output**: `docs/future/W8-CM-4-good-first-issues.md` with 15 issue drafts.

**Time**: 90 min. **Budget**: $0.5.

---

### W8-CM-5: External-facing READMEs

**Mission**: write public-audience READMEs for both carved-out repos.

**Tasks**:
1. `soc-pipeline/README.md`:
   - 1-paragraph what-is-this
   - 1-line install
   - 30-second first example (must actually run)
   - Link to docs site
   - Link to community channels
   - License + cite + contributing
2. `cross-judge/README.md`: same structure.
3. **Critical**: must not assume reader knows what SOC is. Define on first use.
4. Include badges (CI, coverage, PyPI version, license).
5. One-screenshot or one-plot per README.

**Output**: PR with both README drafts in `docs/future/`.

**Time**: 60-90 min. **Budget**: $0.3.

---

### W8-CM-6: HN launch playbook

**Mission**: produce a complete launch playbook for the day main-repo goes PUBLIC.

**Tasks**:
1. HN title options (5 candidates). Best practices: no "Show HN" prefix unless really demoable; emphasize the validation, not the brand.
2. HN body draft (300 words max): the 1-line ask + 3-paragraph context.
3. First-comment pre-written: "I'll be here answering questions for the next 4 hours."
4. Twitter/X thread (10 tweets) for parallel push.
5. Mastodon long-form post.
6. Reddit r/MachineLearning + r/complexsystems versions (separate posts, not crossposted).
7. Email list to notify advisors / friendly accounts 24h ahead of launch.
8. Timing matrix: best day of week + time of day (Tue/Wed 8-10am Pacific).
9. Post-launch checklist: monitor for first 4 hours, respond to top 10 comments, save analytics screenshots.

**Output**: `docs/future/W8-CM-6-hn-launch-playbook.md`.

**Time**: 60 min. **Budget**: $0.3.

---

## 9. Scoring rubric — how we know community-building is working

Tracked monthly. Reviewed quarterly.

| Metric | Tier | Month-3 target | Month-6 target | Month-12 target |
|---|---|---|---|---|
| GitHub stars (`soc-pipeline`) | Visibility | 100 | 300 | 800 |
| GitHub stars (main repo) | Visibility | 200 | 500 | 1500 |
| External PRs merged | **North star** | 1 | 5 | 15 |
| Active contributors (≥1 commit/quarter) | **North star** | 2 | 5 | 12 |
| Newsletter subscribers | Funnel | 50 | 150 | 400 |
| Newsletter open rate | Quality | 45% | 40% | 35% |
| Discord MAU | Engagement | — | 30 | 80 |
| GitHub Discussions threads/month | Engagement | 5 | 15 | 30 |
| External citations (Google Scholar) | Academic | 0 | 2 | 8 |
| Talks given at conferences | Reach | 0 | 1 | 3 |
| Blog posts (mine + external mentions) | Content | 2 | 6 | 12 |
| PyPI downloads/month | Adoption | 100 | 500 | 2000 |

**Failure thresholds** (re-evaluate strategy if hit):
- Month 6: external PRs merged = 0 → onboarding is broken; investigate.
- Month 12: active contributors < 3 → community is not forming; consider scope-narrowing.
- Month 12: NumFOCUS application rejected → sustainability path needs rethink.

**Success indicators** (lock in strategy):
- Month 6: 3+ external contributors with 2+ PRs each = compounding effect started.
- Month 12: ≥1 contributor onboarded another contributor (without founder involvement) = community self-replication.

---

## 10. Highest-leverage single action

If only ONE thing happens in the next 30 days, make it: **ship `soc-pipeline` as a standalone PyPI-installable package with 5 verified-system reproducibility notebooks**.

Why:
- Turns the unified preprint from a static PDF into an *executable artifact*.
- Gives complex-systems researchers a 1-line install for instant value.
- Establishes credibility (running code > theoretical claims).
- Unblocks every downstream item: Discord, newsletter, blog, HN launch all become easier when there's something concrete to talk about.
- It's the minimum viable open-source contribution that proves we mean it.

Everything else in this doc (governance, partnerships, content) is *amplification* of that core artifact. Without the artifact, amplification has nothing to amplify.

---

## 11. Open questions for user / founder decision

1. **Carve-out timing**: ship `soc-pipeline` PUBLIC before main repo PUBLIC (per this plan), or wait? Recommendation: ship first. User decision.
2. **PyPI naming**: `soc-pipeline` vs `soc-toolkit` vs `pyselforg` vs `socology` — check availability first. Recommendation: `soc-pipeline` (descriptive, search-friendly).
3. **Advisor candidates**: who should we approach in months 6-9? User to nominate 3-5 names with warm-intro paths.
4. **Time budget**: founder confirms 4 hours/week sustained for community work? If less, this whole plan delays.
5. **`cross-judge` priority**: month 6 might be aggressive given B3 framework still maturing. User to confirm or push to month 9.

---

## 12. Cross-reference

- D-struct-3 (main repo PUBLIC after unified preprint) — RESPECTED. Carve-outs are preprint-independent.
- W6-D narrative fixes — feeds into external-facing README tone (less academic, more user-empathy).
- W6-E test suite — provides CI green badge for PUBLIC launch credibility.
- B3 taxonomy v2 — input to `cross-judge` carve-out.
- D1 preprint — gates main repo PUBLIC (month 3-4 target).

---

*End of W7-C roadmap. Next: dispatch to Wave 8 per §8.*
