# Changelog

All notable changes to **structural-isomorphism** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

- arXiv submission (5 papers, awaiting user account)
- PyPI publish (3 packages, awaiting `PYPI_TOKEN`)
- Zenodo DOI mint (awaiting `ZENODO_ACCESS_TOKEN`)
- HF Hub model upload to `dada8899/structural-v2` (awaiting `HF_TOKEN`)
- GitHub repo PUBLIC flip (awaiting key rotation + LFS migration + history scrub)
- GH Pages enable for mkdocs + Storybook deployment (user manual action)
- Plausible custom event verification on real prod data
- 1-day staggered outreach to 5 senior researchers (W9-D drafts ready)

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
- **1000-ticker walk-forward backtest engine v0.1** (W10-A) — produced NULL result (Sharpe lift −0.07, Welch t = 0.573, p = 0.569, n_months = 59, 927 / 1000 tickers covered), now publicly displayed as trust signal
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
