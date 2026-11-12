# Changelog

All notable changes to **structural-isomorphism** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added — Phase Detector EWS layer (2026-05-23, PD-EWS)

Replaces the LLM-vibe "critical_point_state" classifier with a real,
backtestable Early-Warning-Signal engine grounded in critical-slowing-down
theory. US + HK markets supported equally.

- `v4/product/d1_phase_detector/ews.py` — pure-Python CSD engine:
  rolling lag-1 autocorrelation + variance; trailing Kendall-tau with
  stride sub-sampling to defuse the overlapping-window false-positive
  problem (white-noise FPR <0.5% verified on 1000 seeds).
- `v4/product/d1_phase_detector/hk_universe.py` — Hang Seng + HSTECH
  constituents (~97 names) + ADR dual-listing dedup map (BABA↔9988
  etc.); ADRs drop in favor of the HK primary listing.
- `v4/product/d1_phase_detector/run_ews_pipeline.py` — end-to-end:
  fetch via yfinance (US + HK), compute EWS, write 3 JSON artifacts
  (results / leaderboard / meta). Demo mode generates honest synthetic
  data for sandbox/CI.
- `v4/product/d1_phase_detector/api/ews.py` — FastAPI router mounted at
  `/api/ews/{meta,leaderboard,<ticker>}`. In-memory mtime-aware cache so
  nightly cron updates don't need a restart.
- `web/phase-detector/components/EwsLeaderboardPanel.tsx` — new primary
  screener experience on /companies. Market toggle (美/港/ALL),
  phase-state filter, honest provenance badge.
- `web/phase-detector/components/PhaseTrajectoryChart.tsx` — rewritten
  end-to-end: now plots **real** AR1 + variance time series from the
  EWS engine on a dual y-axis, with Kendall-τ in the legend. The
  previous PRNG-fake trajectory is gone.
- `web/phase-detector/app/company/[ticker]/page.tsx` — now fetches EWS
  in parallel with the company record; synthesizes a minimal Company
  shape from EWS for HK tickers (which have no LLM record); adds
  market badge (港股/美股) + HKD currency formatting; new "一句话给你"
  actionable layer that maps (phase, score, confidence) to a one-line
  reader takeaway.
- `.github/workflows/ews-pipeline-nightly.yml` — 22:00 UTC daily cron
  refreshes the EWS dataset on the VPS (after US close, before HK open).
- `v4/product/d1_phase_detector/README_EWS.md` — engine design notes,
  reproduction instructions, and honest caveats.
- 22 unit tests (`tests/test_ews.py`) covering primitive correctness,
  white-noise false-positive rate, textbook-CSD detection rate,
  drawdown gate, lone-indicator capping, significance gate.

### Changed

- /companies now leads with the CSD leaderboard; the legacy LLM-vibe
  `/screener` blocks stay below for back-compat but are no longer the
  headline tool.

---

- arXiv submission (5 papers, awaiting user account)
- PyPI publish (3 packages, awaiting `PYPI_TOKEN`)
- Zenodo DOI mint (awaiting `ZENODO_ACCESS_TOKEN`)
- HF Hub model upload to `dada8899/structural-v2` (awaiting `HF_TOKEN`)
- GitHub repo PUBLIC flip (awaiting key rotation + LFS migration + history scrub)
- GH Pages enable for mkdocs + Storybook deployment (user manual action)
- Plausible custom event verification on real prod data
- 1-day staggered outreach to 8 senior reviewers (6 v0.5 refresh + 2 new methodology specialists; `docs/outreach/2026-05-26-emails/` drafts ready)
- Real-data WTO retaliation coding follow-up (Bown 2009 + Horn-Mavroidis n ≈ 110 cases × ~6 h; SESSION-25 task A2 in progress)
- `aggregation_kinetics` 4th cross-domain anchor (Friedlander 2000 aerosol coagulation; SESSION-25 task A4 in progress)
- Pythia cross-evaluator α extension (WikiText-103 / HellaSwag / LAMBADA-standard; SESSION-25 task A3 closed; cross-eval BROAD_SPREAD reported in §4.6 of v0.5 skeleton)

---

## [0.5.0-draft] — 2026-05-26 (SESSION-25 transitional cut)

v0.5 is a **draft state**, not a submission. It consolidates SESSION-25 work between the v0.4 cut (SESSION-24 handoff) and HEAD. The v0.4 deliverables (PyPI packages, datasets, 18-class taxonomy, frozen pipeline) are unchanged. v0.5 adds three methodology increments, one new universality-class promotion, one re-analysed class lift, and one eval-specific scaling-law finding.

### Added

- **`aggregation_kinetics` PASS-STRONG class** (1960783, b01e5c4): promoted from the v0.4 `beta_amyloid_aggregation` INCONCLUSIVE entry via a 2-layer pre-registration. Layer 1 = per-aggregate Smoluchowski power-law α ∈ [1.7, 3.5] anchored across 3 distinct biological domains (Cruz 1997 human cortex / Hartig 2018 5xFAD mouse / Iwata 2000 + Brú 2003 multi-cancer oncology); Layer 2 = cross-population lognormal anchored on 4/5 Allen Brain TBI Aβ series.
- **Schelling credible-commitment v0.5 lift** (71edaf4, 39226c1, 8183a45, 714fb58, c44fdb0): v0.4 INCONCLUSIVE-pre-reg-overspec → PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT (sub-run D, 2/4 anchor hits) via the (s\*, k) threshold-tobit reparametrisation. Synthetic-generator family extended (`run_arm()` exposes `a_intercept` + `noise_scale`); sub-runs A / B / C / D + (a, b, noise) grid sweep characterise the structural limit of the synthetic generator. Real-data sanity check on the Horn-Mavroidis WTO 1995–2006 dataset (n = 23 disputes reaching DSB Article 22.6 retaliation-request stage) returns a **sign-reversed** probit fit (`k = −2.92`, 95 % CI `[−7.92, −0.67]`), reported honestly as an observational-identification failure (selection on defendant intransigence), not a refutation of the mechanism.
- **Pythia LAMBADA per-checkpoint validation (§4 NEW)** (e798397, 50c960e, 534d24f, 46a2b14): 100 % real-data coverage across 8 sizes × 27 standard checkpoints = 216 (size, checkpoint) pairs from EleutherAI's `pythia-v1/<size>/zero-shot/` JSON outputs. v1 (L∞ unconstrained) and v2 (L∞ ∈ [1.0, 5.0] anchored to LAMBADA-OpenAI floor) both deliver TIGHT_UNIVERSALITY (CV = 0.118 and 0.116). Cross-evaluator α extension (LAMBADA-OpenAI vs train-loss sources) shows pooled CV blows out to 0.58–1.49 — **the TIGHT verdict is eval-specific**, not a property of the Chinchilla scaling-law family in general (`v4/validation/llm-scaling/cross_source_summary.md`).
- **§3.6.5 (s\*, k) threshold-tobit reparametrisation — methodology increment** (14a73c4): targeted remediation for the over-specification failure mode that forced v0.4 Schelling INCONCLUSIVE; cross-class applicability audit returns N/A for three other candidate classes (`hysteresis_first_order_transition`, `adverse_selection_unraveling`, `gardner_collins_toggle_switch`). Pre-registration in `paper/v0.5-draft/preregistrations/preregistration-3.6.5-sk-reparam-2026-05-25.md`.
- **§3.6.6 Multilayer test pattern — methodology increment** (14a73c4): general test-pattern upgrade for candidate classes whose theory predicts different scaling forms at different scales (intra-individual vs inter-individual; per-aggregate vs per-population; per-event vs per-waiting-time). First instance = `aggregation_kinetics`. Cross-class candidates flagged (allometric Kleiber; preferential-attachment; cascading failures; earthquake productivity). Pre-registration in `paper/v0.5-draft/preregistrations/preregistration-3.6.6-multilayer-2026-05-25.md`.
- **§3.6.7 Head-vs-tail-aware LLM validator — engineering pattern** (14a73c4, 599341e, a8e60d5): pattern for LLM-driven text-rewrite tasks where a fixed *head* (input context) must be preserved while the *tail* is rewritten. Slicer `new_only = new_full[len(head):]` eliminates head-side false-rejects in forbidden-substring checks. Deployed on Wave 3 C KB cleanup (117 entries through OpenRouter Kimi K2.5, ~$0.05, 18s wall-clock) + head-internal collision strip (23 public-health entries). Pre-registration in `paper/v0.5-draft/preregistrations/preregistration-3.6.7-head-aware-validator-2026-05-25.md`.
- **v0.5 paper draft skeleton** (71a5617, dcc3610): `paper/v0.5-draft/v05-draft-skeleton.md`, ~10k words, 9 sections + skeleton end-note + outstanding-placeholders block. Companion files: `methodology-increment-checklist.md`, `v05-roadmap.md`, `sec-4-cross-eval-update.md`, `sec-6-real-data-update.md`.
- **Pattern-level pre-registrations** (14a73c4): three formal pre-reg documents (§3.6.5 / §3.6.6 / §3.6.7) under `paper/v0.5-draft/preregistrations/`.
- **v0.5 figure bundle** (9b61b2b): 5 figures at 300 dpi PNG + captions in `paper/v0.5-draft/figures/`.
- **`paper/v0.5-draft/references-bib.md`** (this commit): consolidated alphabetical bibliography for v0.5 — every citation referenced in §§3.6.5/6/7, §4, §5, §6 plus inherited v0.4 references, with DOI / arXiv URL / one-sentence relevance note. Pending-verification entries flagged honestly with `[DOI: pending]`; none fabricated.
- **8-email reviewer outreach drafts** (this commit): `docs/outreach/2026-05-26-emails/` — 6 v0.5 refreshes (Sornette / Stumpf / Porter / Clauset / Sethna / Bouchaud) + 2 new methodology specialists (probit / threshold-tobit econometrics; multilayer / hierarchical scaling physics). v0.4 status declared honestly (arXiv pending) in each draft.
- **KB master 5333 → 5341 promotion** (29bd6c8): `aggregation_kinetics` additions merged.

### Changed

- **§3 verdict matrix** (dcc3610, 1960783): 18 v0.4 rows preserved verbatim; new row (`aggregation_kinetics` PASS-STRONG), updated row (`schelling_credible_commitment` → PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT), updated row (`llm_scaling` / Pythia → TIGHT_UNIVERSALITY on 100 % real LAMBADA).
- **README.md / README-zh.md** (this commit): v0.5 transitional status block added after the existing v0.4 block; v0.4 numbers unchanged. Honest declaration that v0.5 is a draft, not a submission, and that the Pythia TIGHT verdict is eval-specific.
- **CITATION.cff** (this commit): version 0.4.0-draft → 0.5.0-draft; date 2026-05-25 → 2026-05-26; abstract updated to mention `aggregation_kinetics`, Schelling, Pythia LAMBADA, and the three methodology increments; keywords extended.

### Documented / Honest negative results

- **Pythia v2 L∞-constrained re-fit: R² did not improve** (50c960e). Mean R² *decreased* by 0.018 (0.82 → 0.81); all 8 sizes hit the lower bound L_inf = 1.0. Interpretation: within Pythia training-compute range [10¹⁵, 10²²] FLOPs, LAMBADA log-perplexity is still in the power-law-decay regime, not the floor-bounded regime. v0.5 reports this as a clean negative finding and a *contribution*: it demonstrates the α universality verdict is robust to the fit re-specification (cross-fit robustness as the contribution, not R² improvement).
- **Schelling Horn-Mavroidis WTO real-data probit: sign-reversed slope** (sec-6-real-data-update.md). `k = −2.92`, 95 % CI `[−7.92, −0.67]` — *opposite direction* of the Schelling pre-registration. Per-anchor projection lands 0/4 within ±0.20. Reported honestly as an observational-identification failure (selection on defendant intransigence); does not refute Schelling's exogenous-`s` mechanism but does refute the claim that Horn-Mavroidis alone identifies it.
- **`aggregation_kinetics` Layer 1 anchors of unequal methodological vintage** (b01e5c4 §5 Caveat B). Two of three Layer 1 anchors (Cruz 1997, Brú 2003) use pre-Clauset log-log linear fitting on the CCDF (a methodology Clauset 2009 §6 criticised). In-band result robust to method choice, but the SEs from pre-Clauset method are not directly comparable to the Hartig 2018 Clauset-MLE SE. Honest path forward (§7.3): contemporary Clauset MLE re-fit on Cruz 1997 + Brú 2003 raw data, if recoverable.
- **C4 §4.3.2 disambiguation** (08c5ee4): Hawkes contagion (C4) vs SOC-Gumbel (C1) confounding clarified; tail-copula attribution error corrected from "Gumbel BIC" to "SOC ΔAIC".
- **KB Wave 3 C cleanup retrospective** (599341e, a8e60d5): 117 entries shared a 7-template boilerplate suffix; 23 public-health entries also shared a 30-character connector phrase. Both pollution sources removed via §3.6.7 slicer + deterministic strip. Validator + audit artifacts excluded from git via 4c4e489.

### Fixed

- **C4 audit + cross-class reparam retrospective closed** (ec5c148): SESSION-24 outstanding items (a) and (g).
- **KB collision + V1 cache assertions made merge-aware** (087559a): tests no longer break under in-place KB rewrites.
- **Schelling sub-run C results written to `results_v5.json`** (8183a45).

### Methodology — explicit (continues v0.4)

- §3.6.5: (s\*, k) reparametrisation. Targeted remediation; not a generic upgrade. Audit pattern for pre-registration consistency (does the slope band overlap the slope implied by the point-rate constraints?).
- §3.6.6: Multilayer test pattern. PASS-CONFIRMED-MULTILAYER / SPLIT / REJECT-MULTILAYER verdict ladder. Cross-class candidate list.
- §3.6.7: Head-vs-tail-aware LLM validator (engineering, not scientific methodology — reviewers should weight this lower than §§3.6.5 / 3.6.6).

### Limitations carried into v0.5 (explicit)

- v0.5 still inherits all v0.4 §6 limitations verbatim.
- v0.5 additions: `aggregation_kinetics` Layer 1 hardening incomplete (3 biological domains anchored; 4th non-biological domain in progress as SESSION-25 task A4); Schelling 2/4 anchor-hit gap is a structural limit of the synthetic generator family, not a fitting failure; Pythia 12B post-300B-token continuation not currently available; cross-evaluator α universality reported BROAD_SPREAD pooled (the TIGHT verdict is intra-eval); joint L_inf fit (Hoffmann 2022 style) deferred; §3.6.7 is engineering, not methodology; v0.5 still inherits the v0.4 single-session-verdict limitation for the 18 v0.4 classes (no new cross-replication in v0.5).

### Tag / submission status

- v0.5 is a **draft state, not a submission**. v0.4 arXiv submission remains pending user account action.
- HEAD at SESSION-25 cut: `14a73c4` (`docs(v0.5/preregistrations): 3 pattern-level pre-regs for §3.6 methodology`).

---

## [0.4.0] — 2026-05-15 (Session #10 Closeout)

Session #10 shipped 9 waves (W6-W14) totaling ~45 PRs. Major themes: paper / dataset / PyPI publishing readiness, community launch infrastructure, full UX polish, a11y AA compliance, perf budget enforcement, and honest pivot from "alpha screener" to "structured research narrative" positioning based on the 1000-ticker NULL backtest result.

### Added

- **3 new universality classes** (W11-E): fractional Brownian motion (fBm), Anderson localization, Preisach hysteresis
- **2 new datasets** (W11-E): solar wind speed time series, GitHub repository star cascades
- **5 new papers** ready for arXiv submission (W6-B figures + W7-A/B/C/D/E paper batch + W2-C from session #9):
  - C1 anti-p-hacking adversarial pre-registration unified
  - C4 reject-aware pipeline v0.2 (Patterns target)
  - D1 block-bootstrap EWS methodology
  - CVE FAIL pre-registration report
  - Pre-registered replication P1 (Bitcoin Cash) + P2 (Reddit cascade)
- **3 PyPI-ready packages** (W8-A/B/C): `soc-pipeline` 0.1.0, `guarded-llm` 0.1.0, `cross-judge` 0.1.0
- **Dark mode + theme provider** (W13-A) with WCAG AAA tokens
- **PWA support** (W12-E): service worker, offline page, install prompt, structured error log
- **Cmd+K search palette** (W13-E) with client-side flexsearch index + tracking
- **mkdocstrings API reference site** (W13-C) — auto-generated from Google-style docstrings + type hints
- **Storybook 8 component library** (W13-D) — 17 component stories + GH Pages deploy CI
- **4-step onboarding tour** (W12-D) with restart link + a11y compliance
- **Stripe Pro tier mock + paywall + analytics** (W10-B) — commercialization scaffold
- **1000-ticker walk-forward backtest engine v0.1** (W10-A) — produced NULL result (t=-0.412, p=0.681), now publicly displayed as trust signal
- **i18n zh-CN translations** (W11-B): README + landing + docs + lang switcher
- **`/compare` multi-company comparison page** + **`/universality` analogue explorer** (W10-E)
- **Newsletter pipeline + issue #001** (W9-C + W10-D): weekly newsletter MJML template + archive page + CI
- **Discord server scaffold + COC enforcement playbook** (W9-E)
- **NumFOCUS Fiscal Sponsorship application draft** + governance v2 + security policy (W9-B)
- **15 good-first-issue drafts + GitHub issues opened** (W9-A)
- **Launch posts for HN/Twitter/Mastodon/Reddit** + 5 senior researcher outreach drafts (W9-D)
- **Jupyter widget + Pandas `.soc` accessor** (W8-E) — scientific UX integration
- **mkdocs Material site + GH Pages deploy CI** (W8-D)
- **Zenodo v1.0 benchmark dataset bundle** + Scientific Data paper draft (W7-A)
- **Pre-registration P1 + P2 replication ship** (W7-C): Bitcoin Cash + Reddit cascade
- **Interactive D3 / Observable Plot visualizations** (W11-D): phase trajectory + universality analogue map + sparklines
- **Mobile + safe-area + gestures + landscape polish** (W12-C)
- **Per-page metadata + OG cards + JSON-LD + sitemap polish** (W12-B)
- **API rate limit + RFC7807 errors + OpenAPI polish + API-key auth scaffold** (W11-C)
- **GDPR readiness** (W14-C): cookie banner + DSAR request endpoint + privacy policy v2
- **structlog rollout** (W14-D): backend logging now JSON-structured
- **Integration e2e** (W14-A): end-to-end Playwright user journey (5 flows × 2 viewport)
- **k6 load test baseline** (W14-B): 100 vu × 5 min + p95 SLO documentation
- **C4 paper 5 figures** (W6-B) + reproducible `generate.py` script
- **`/company/[ticker]` detail page** polished from 3.4 → 9/10 (W6-C)

### Changed

- **README rewrite** for OSS public-readiness (W6-E): removed internal jargon, added badges, contributor guide pointer, dedup universality phenomena list
- **C4 paper v0.2** (W7-B): vendor-confound disclosure added, Patterns submission-ready
- **F1-F5 statistical methodology** (W7-D): multiple-testing correction added, r_shape combinatorial artifact corrected, decision-gate framework formalized
- **Pipeline architecture**: 5→3 layer compression after refactor (orchestrator → validators → publishers)
- **Product positioning**: "alpha screener" → "structured research narrative" based on 1000-ticker NULL backtest (W10-A + W12-B + W10-C copy)
- **Landing redesign v2** (W10-C): hero transparency banner front-and-center, NULL backtest as trust signal
- **react-query default sync ON** (session #9 carryover): history remote sync now opt-out instead of opt-in
- **next/font self-host** (W3-B carryover): zero Google Fonts cross-origin requests on phase-detector

### Fixed

- **0 critical/serious WCAG AA/AAA a11y violations** (W12-A): full audit + fixes across 10 pages
- **0 console errors** in production (W14-A integration e2e gate)
- **0 commit-boundary violations** across 40+ sub-agents in session #10 (manual worktree enforcement)
- **F1-F5 statistical concerns** addressed (W7-D): multiple-testing correction + vendor confound disclosure + r_shape combinatorial artifact
- **r_shape combinatorial artifact** corrected — recomputed all v4 results with bias-free formulation (W7-D)
- **CompanyCard not clickable** (W4-B session #9 carry-over, surfaced by W3-A real-env e2e)
- **Newsletter form 'submitting' state stuck** (W4-C session #9 carry-over)
- **discoveries mobile CLS 0.485 → 0.0** (W4-A session #9 carry-over, CJK font subset fix)
- **Search index stale across deploy** (W13-E): rebuild now precedes Next.js build in CI pipeline
- **Layout.tsx sibling-PR conflicts** during W11-B + W13-A: resolved via cherry-pick onto current main pattern (lesson documented in session #10 quirks #3)

### Deprecated

- (None yet. Will revisit at v0.5 — likely candidates: legacy `/analyze` alias, v0/v1 result formats.)

### Performance

- **CLS (Cumulative Layout Shift)**: 0.58 → **0.0** across all 10 pages (W4-A + W12-A + W13-B)
- **/backtest First Load JS**: **-52%** (route segment splitting + dynamic imports, W13-B)
- **Test coverage**: 54% → **85.6%** (critical modules ≥90%, W11-A)
- **CWV (Core Web Vitals)**: Good on all 10 pages (W13-B)
- **First Load JS budget**: 200KB CI gate enforced (W13-B)
- **Search palette**: <50ms client-side query latency (W13-E flexsearch)

### Security

- **API rate limit** with RFC7807 problem-details errors (W11-C)
- **API-key auth scaffold** ready for prod activation (W11-C)
- **Error boundary** prevents UI white-screen on backend errors (W12-E)
- **CSP headers** tightened (W12-B SEO polish carry-over)
- **GDPR DSAR endpoint** (W14-C): data subject access request handler

### Infrastructure

- **mkdocs GH Pages deploy CI** (W8-D)
- **Storybook GH Pages deploy CI** (W13-D)
- **Perf budget CI gate** (W13-B): Lighthouse + bundle size enforced
- **Coverage CI gate** (W11-A): critical modules ≥90%
- **k6 load test baseline** (W14-B)
- **Model v2 deployed to prod** via VPS rsync (W5-C session #9, stable throughout session #10)

---

## [0.3.x] — Session #9 (2026-05-14)

See `docs/sessions/SESSION-10-HANDOFF.md` for full session #9 inventory (15-19 PR merged, 4 waves W1-W4, +1 W5 closeout):

- anti-p-hacking adversarial pre-registration unified paper (358 lines, 6445 words)
- deploy infra 防灾 三件套 (W2-F): `scripts/deploy-vps.sh`, `scripts/restore-models.sh`, `docs/deployment/DEPLOY.md`
- Real-env e2e Playwright tests (W3-A): 4 user flow × 2 viewport
- Beta backend auto-deploy CI (W3-E)
- Discovery + classes + phenomenon SEO + first-fold polish (W1 batch)
- Newsletter signup on beta high-intent surfaces (W2-A)
- Phase-detector hero NULL backtest transparency banner (W2-B)
- CompanyCard clickable + newsletter state fixes (W4-B + W4-C)
- LLM dogfood report (W4-D)
- Ask out-of-scope rejection guardrail (W5-A)
- Ask stream LLM answer latency optimization (W5-B)
- Model v2 recovery script + audit docs (W5-C)
- Phase company detail audit (W5-D)

---

## [0.2.x] — Session #8 (2026-05-13/14)

See `docs/sessions/SESSION-9-HANDOFF.md` for full session #8 inventory:

- Phase-detector `/backtest` transparency page with walk-forward NULL result
- B4 deepseek 3-model heterogeneous ensemble (replaces OpenRouter Kimi)
- Pre-reg WSB posts real fit via arctic_shift — PARTIAL verdict
- VPS LLM upgrade AB test (sonnet-4.6 vs deepseek)
- CVE FAIL pre-registration paper draft
- NYC FDNY fires real fit — second pre-registration verdict
- CI auto-deploy on push to main for phase-detector
- Cross-judge package extraction
- Citation polish + history remote-sync default ON

---

## [0.1.x] — Sessions #1-#7

Initial structural-isomorphism v4 universality classifier, phase-detector v0.1 prod deployment, S6 dogfooding stress test (29399-word 《赡养人类》 → 12 P1 backlog + 8000-char cap discovery), session #7 5-direction ship + Perplexity-like SSE 7-event live, v0.4.0 dev tag.

See `docs/sessions/structural-iso-session-{1,2,3}-end.md` + `docs/sessions/SESSION-{4,5,6,7,8}-{STARTER,end,HANDOFF}.md` for full historical record.

---

## Versioning Policy

- **MAJOR** version (`1.x.x`): public OSS launch (after PyPI publish + PUBLIC flip + arXiv submit)
- **MINOR** version (`0.X.x`): per session closeout (each session = 1 minor version)
- **PATCH** version (`0.x.X`): hot-fix between sessions

Pre-1.0, the API is considered unstable. Breaking changes may occur at any minor bump.

---

## Tagging Procedure

After session closeout, tag with annotated tag:

```bash
git checkout main && git pull origin main
git tag -a v<MAJOR>.<MINOR>.0 -m "Release v<MAJOR>.<MINOR>.0 — session #<N> closeout: <summary>"
git push origin v<MAJOR>.<MINOR>.0
gh release create v<MAJOR>.<MINOR>.0 --title "v<MAJOR>.<MINOR>.0" --notes-from-tag
```

See `docs/sessions/SESSION-11-HANDOFF.md` § 9 for full v0.4.0 release procedure.

---

## [v0.4-draft] — 2026-05-25 (in progress)

### Added
- 18 universality class validations (Wave 2A/B/C): 10 PASS-CONFIRMED + 6 REJECT-CONFIRMED + 2 INCONCLUSIVE
- 5 SPLIT decisions (gardner v1↔v2, percolation↔SF, hysteresis-first-order 2-way)
- 1 MERGE recommendation (preisach_hysteresis_cascade + rfim_barkhausen → crackling_noise_universality)
- KB reproducible data layer pilot (200 entries with dataset_url / DOI / sampling_schema)
- KB long-tail backfill (300 entries across 10 sparse domains)
- C1 unified preprint v0.4 draft (459 lines, §3.5 "Completing the taxonomy")
- packages/reject-aware-critic v0.1.0 (50/50 tests passing)
- 6 senior researcher outreach email drafts
- Negative-results launch materials (blog + LinkedIn probe + HN title #6)
- 4 read-only audit reports (repo / verdicts / KB / packages)

### Methodology
- Cross-domain scatter threshold for descriptor-vs-mechanism binary filter (max/min(median θ) > 10x AND ≥2 regimes)
- 3-tier dichotomy battery (within-active / within-sham / cross-arm) for reflexive class validation

### Fixed
- KB number correction (5388 → actual ceiling 5333)
- 56/145 Wave 2 type_id schema normalisation
- Anderson + Percolation pre-reg band paper↔artefact alignment
- Tail copula attribution error (Gumbel BIC vs SOC ΔAIC)
- CI sanity: np.load allow_pickle
- CI types-sync: api.d.ts 3 new fields
