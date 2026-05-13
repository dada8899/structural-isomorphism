# W7-D — Product Value Roadmap: From Demo to Must-Have

**Date**: 2026-05-13
**Author**: W7-D subagent (senior B2B SaaS / data-product strategist hat)
**Mission**: Turn structural-isomorphism from "interesting demo" into a product real users pay for monthly, return to weekly, and recommend organically — with 90+ craft.
**Scope**: D1 Phase Detector + structural.bytedance.city main site, 12-month user-facing roadmap.
**Companion docs**: W5-C (PM ARR predict) · W5-E (UX gap to 90) · W5-F (narrative score 6.2) · W6-B (methodology page) · W6-D (copy fixes) · W6-E (test suite).

---

## TL;DR

1. **The product is not a "phase classifier." The product is a *weekly research ritual* that gives one paying ICP — independent financial analysts + small hedge fund research seats — an unfair edge in seeing which public companies are structurally near a regime transition before consensus does.** Everything else is scaffolding for that ritual.
2. **The single highest-leverage move in the next 30 days is: ship a credible waitlist + email-collection loop + first weekly newsletter ("This Week's Structural Signals — 6 companies near critical"). Without retention, more companies / more polish / more backtest is wasted.** Distribution beats craft for a 0-user product.
3. **The honest gate at month 3 is the backtest result.** If 2020–2024 backtest shows ≥0.5 Sharpe lift on `near_critical` cohort vs sector benchmark, double down on alpha-screener positioning (Pro $19 + Team $99 SaaS, $1k MRR by month 6, $20k by month 12). If alpha is null, pivot cleanly to "structured research narrative" positioning (Substack-style + B2B Index API), still credible, still monetizable, just slower MRR ramp.
4. **P0 ICP = independent analyst / financial KOL with ≥1k newsletter subscribers**. Reason: highest willingness-to-pay × reachable × product-fit alignment. NOT retail investors (cost too high, expectations wrong). NOT VCs (wrong asset class). NOT academics (no money).
5. **Wave 8 dispatch candidates: 6 ready-to-ship mini-briefs** (waitlist+Plausible, Stripe-mock Pro tier, weekly newsletter pipeline, backtest engine v0.1, UX-consistency-sprint, HN-launch-readiness). All 6 fit within 8 working days of subagent capacity.

---

## 1. What "real product value" means for structural-isomorphism

Four concurrent tests. A product passes only if all four are true.

| # | Test | Pass criterion (12-month target) |
|---|---|---|
| **V1** | **Weekly active habit** — user voluntarily visits ≥1×/week with actionable take-away | WAU/MAU ≥ 35% (Bear/Notion zone) |
| **V2** | **Cash willingness** — user pays for value beyond free tier | Pro conversion ≥ 4% of free signups; ≥ 60% month-2 retention on Pro |
| **V3** | **Organic recommendation** — user mentions product unprompted to peer | NPS ≥ 40; ≥ 10% of new signups via "heard from friend / Twitter / newsletter" within 6 months |
| **V4** | **90+ craft** — design / copy / performance / trust at Linear · Apple · Bear · Notion tier | Lighthouse perf ≥ 95, Tailwind design system 100% applied, accessibility AAA, 0 dead-end states |

**The deeper question — what is the actual job-to-be-done?**

structural-isomorphism is not "a screener" (Bloomberg already wins). It is not "a chart" (TradingView wins). It is not "research" (Sentieo + analyst reports win).

The unique JTBD is: **"Tell me which of the 500+ public companies I follow are *structurally about to change regime*, regardless of whether the surface-level financials look fine, before the market reprices."** That phrasing only makes sense if there is real signal — which is exactly what the month-3 backtest decides. Until then, the honest product positioning is:

> "Daily structural signals from 1000+ public companies. Each one a hypothesis. Each one with the receipts. You judge the alpha."

That positioning is defensible at score 90 even with zero proven alpha — because the value is **structured ingestion + reproducible methodology + weekly digest**, not "we predict the future." It also leaves the door open to upgrade to alpha-screener language once backtest validates.

---

## 2. ICP lockdown

Six candidates evaluated on three axes (1–10):

| ICP | Willingness to pay | Accessibility | Product-fit | Total | Rank |
|---|---|---|---|---|---|
| **Independent analyst / financial KOL** (≥1k subs newsletter) | 8 (already pay $20–100/mo for Sentieo, Koyfin, Substack) | 9 (reachable via Twitter/X, LinkedIn, RIA conferences) | 9 (research副驾驶 = exact JTBD) | **26** | **P0** |
| Small hedge fund / quant analyst (1–10 person fund) | 9 (data budgets $1k–10k/seat) | 5 (cold outbound only; relationship-driven) | 8 (need API + bulk export) | 22 | P1 |
| VC analyst (early-stage) | 6 (firms pay but unclear personal authority) | 7 (Twitter-active community) | 5 (signal is for *public* co, VC needs private) | 18 | P2 |
| Financial media reporter | 4 (rarely pay personally) | 8 (HARO, Twitter pitches) | 7 (story素材 yes, regular use no) | 19 | P2 |
| Academic researcher | 2 (no individual budget) | 6 (reachable via arXiv, SSRN) | 7 (replication tool) | 15 | P3 |
| Retail investor (curious) | 3 (won't pay above $5/mo) | 4 (no targeted channel exists) | 4 (signal too sophisticated for casual use) | 11 | NOT TARGET |

**Locked P0 = Independent analyst / financial KOL.** Concrete persona:
- Name: "Sarah, 32, ex-sell-side equity research, runs a 4k-subscriber Substack ($8/mo, ~$10k MRR personal income), focuses on small-cap industrials"
- Existing stack: Bloomberg Terminal ($24k/yr employer paid OR shared, more likely Koyfin $79/mo personal), Twitter, SeekingAlpha, S&P CapIQ trial
- Pain: "I have 60 companies in my watchlist. I read all earnings calls. I miss inflection points 30% of the time because I'm reading sequentially and the structural shift doesn't show up in DCF until two quarters later."
- What she'll pay $19–49/mo for: "A weekly Tuesday morning email — '6 companies in your watchlist moved into near_critical this week, here's why, here's the source quote, here's a link to the full breakdown.' If 1 of those is right per quarter, the subscription pays for itself."
- Acquisition channel: Twitter/X cold (curated reply to her tweets with single-company signal), guest post on her Substack, FinTwit thread monthly, podcast appearance (Animal Spirits / Compound Money zone, not Bloomberg Surveillance).

P1 / P2 / P3 are **NOT pursued** in months 1–9. They are upsell paths once Sarah-persona retention proves > 60% month-2.

---

## 3. Current product weaknesses (frank diagnosis)

Already surfaced in W5-C / W5-E / W5-F, consolidated here:

### Data weakness
- **D1**: 100 companies — too small to be useful watchlist coverage. Sarah needs 500–1000 minimum.
- **D2**: No ground-truth eval for LLM extraction quality. Some `dynamics_family` labels are likely wrong; we don't know which.
- **D3**: Zero backtest. We cannot answer "does `near_critical` actually outperform?" — meaning we cannot say what the product is *worth*.
- **D4**: No weekly refresh — data is a snapshot, not a feed. Sarah's "this week" expectation isn't met.

### Product surface weakness
- **P1**: ICP not declared anywhere on site — homepage talks to everyone, converts no one.
- **P2**: Main site + D1 Phase Detector visually + verbally inconsistent (different nav, different fonts in spots, different tone).
- **P3**: No account / waitlist / pricing. The funnel ends at "browse and leave."
- **P4**: Zero retention loop — no email, no RSS, no alerts, no Slack/Twitter integration.
- **P5**: No analytics (Plausible not wired). We can't measure what's working.

### Trust weakness
- **T1**: Caveat is buried — users could think this is financial advice.
- **T2**: Methodology page (W6-B) exists but no audit log / "show your work" per prediction.
- **T3**: No historical case study — "here's a company we flagged near_critical in 2022Q3, here's what happened" — which is the single most persuasive content type for this category.

### Craft weakness (UX score 71/100 from W5-E)
- **C1**: Mobile experience adequate but not flawless.
- **C2**: Dark mode missing.
- **C3**: i18n incomplete (CN fragments mixed with EN).
- **C4**: LCP ~1.8s (target <1.2s), CLS occasional.
- **C5**: No onboarding flow — first-visit user is dropped into a 100-row table.

### Growth weakness
- **G1**: Zero owned distribution (no newsletter, no Twitter handle, no RSS).
- **G2**: SEO basically nonexistent (no `/companies/{ticker}/structural-state` indexable pages).
- **G3**: HN launch readiness: not ready (no signup, no story, no founder voice).

---

## 4. 12-month product roadmap

### A. Sample expansion — 100 → 1000+ companies

- **Month 1**: 100 → 250 (S&P 500 small/mid cap pass)
- **Month 3**: 250 → 500 (full S&P 500 + Russell 1000 top 250)
- **Month 6**: 500 → 1000 (R1000 full + top 100 ADRs)
- **Month 9–12**: Add Hong Kong HSCEI top 200, Tokyo TPX Core 30 (international expansion gates here)

**LLM cost model**:
- Doubao seed 1.6 (per renai D-renai-10 baseline): ~$0.003/1k input tokens, ~$0.015/1k output
- Per company: ~30k input tokens (10-K + 4 quarterly calls), ~3k output tokens = $0.135/company
- Weekly refresh on 1000 cos = $135/wk = ~$7k/yr ✓ comfortably under $10k LLM budget gate
- DeepSeek V4 backup (per reference_deepseek_direct_api_2026_05_06) for redundancy

Cron infra cost: VPS already in place. ~$0 incremental.

### B. Backtest engine (the make-or-break experiment)

**Hypothesis**: Companies labeled `near_critical` in quarter Q outperform sector benchmark in Q+1, Q+2 risk-adjusted.

**Build**:
- Reconstruct historical `StructTuple` for top 200 S&P companies, 2020Q1–2024Q4 (20 quarters × 200 = 4000 quarterly snapshots)
- Cost: ~$0.135 × 4000 = $540 in LLM, one-time
- For each `near_critical` flag, compute forward 6-month return vs sector ETF
- Statistical test: t-stat on alpha residual, also examine `dynamics_family` × `near_critical` interaction
- Threshold for "real signal": Sharpe lift ≥ 0.4, t-stat ≥ 2.0

**Three outcomes — pre-committed responses**:

| Outcome | Probability est. | Response |
|---|---|---|
| Strong signal (Sharpe ≥ 0.5) | ~15% | Lean fully into alpha-screener positioning. Pricing Pro $29, Team $149, B2B Index API $1k/mo. Aggressive HN/FinTwit launch with backtest case studies. |
| Weak signal (Sharpe 0.1–0.4) | ~35% | Honest positioning: "structured signal, modest alpha, transparent methodology." Price Pro $19, Team $99. Lead with reproducibility, not returns. |
| Null result (Sharpe ≤ 0.1) | ~50% | Pivot to **structured-research-narrative product**. Position as Substack-for-systematic-thinkers. Pro $9, no backtest claims. B2B Index API still viable to academic + media. Lower MRR ceiling but credible. |

**Critical**: this decision is announced publicly. Transparency about null results is itself a trust signal that no Bloomberg-tier competitor will match.

### C. User account + auth + waitlist (Month 1)

- Simple OAuth: Google + GitHub + email magic link (3 paths)
- Free tier: 5 lookups/week, basic filter, no historical access
- Waitlist before paid tier exists — collect 100+ emails as pre-launch validation
- Tech: Clerk or Supabase auth (managed, $0 free tier, ship in 2 days vs custom 5)

### D. Pricing (Month 2 — Stripe mock first per session #30 D-strip-2)

| Tier | Price | Includes | Target |
|---|---|---|---|
| Free | $0 | 5 lookups/wk · basic filter · weekly newsletter · no historical | acquisition |
| **Pro** | **$19/mo** ($190/yr 20% off) | unlimited lookups · custom filter alerts via email · 4-quarter history · CSV export 50/mo | **Sarah persona** |
| Team | $99/mo ($990/yr) | 5 seats · API access (1k req/mo) · CSV unlimited · Slack integration | small fund |
| Enterprise | "Contact us" — $500–2000/mo | unlimited API · dedicated Slack · custom universe · SLA | hedge fund / boutique |

Stripe mock first (session #30 decision), real Stripe day 14.

### E. Retention loops (Month 1–3)

- **Weekly newsletter "This Week's Structural Signals"** — Tuesday 7am ET. Format: hero quote · 6 companies highlighted · 1 deep-dive narrative · methodology footer. Built on Substack OR Buttondown OR custom (decision TBD; recommend Buttondown $9/mo + Plausible).
- **Custom filter alerts**: user saves "small-cap industrials, dynamics_family = bistable, near_critical = true" → email when new match.
- **RSS feed**: `/feed.xml` of weekly digest + per-company state changes — captures FinTwit power-users.
- **Twitter/X bot** `@structural_signals` (Month 2): weekly top-10 thread, screenshot card per company, link back to site. Manual curation first, automation Month 6.
- **Slack/Discord integration** (Month 4, Team tier only): webhook on filter match.

### F. Trust signals (Month 1–2)

- **Methodology page upgrade** (W6-B foundation): add "What we extract / What we don't / Known false-positive patterns" sections
- **Per-prediction audit log**: each company page shows the raw quote(s), the LLM model + version + date, the extraction prompt hash. "Show your work" button revealing the LLM's reasoning.
- **Caveat hardening**: persistent footer "Not financial advice. For research purposes." + first-visit toast acknowledged.
- **Historical case studies**: 3 publicly written case studies — 1 hit, 1 miss, 1 in-progress. Honest about misses → highest trust signal.

### G. Content + SEO (Month 2–6)

- **Blog: weekly "What happened to {Company} this week"** — long-form, SEO-target = "{ticker} regime shift analysis." 52 posts/yr → ~50k organic traffic/yr realistic.
- **HN launch** (target Month 4, candidate Y8-A in dispatch): "Show HN: Structural Phase Detector for 500 public companies — open methodology, transparent backtest." Single best front-of-funnel event possible.
- **Monthly Twitter thread** — 8-tweet narrative of best case that month.
- **2 paid KOL case-study collaborations** Month 3–6: pay 1 Sarah-persona analyst $1000–2000 each to do a deep-dive review, publish to their newsletter + our blog. Goal: borrowed trust + Sarah-persona signal-boost.
- **Reproducibility kit**: GitHub repo with eval scripts, extraction prompts, backtest code — by Month 6. Drives academic citations + dev trust.

### H. B2B Index API (Month 6+ long-term)

- **"Structural Index"** = monthly time-series of every company's `StructTuple`
- API: `$0.10/query` pay-as-you-go OR `$500/mo` subscription with 50k queries
- Target customers: small hedge funds, boutique research firms, fintech ML teams who want structured features
- Tech: simple REST endpoint + Postman collection + 5 cookbook recipes
- Distribution: post to /r/algotrading once, FinTwit thread, no other channel needed — buyers find their own way to this category

### I. Internationalization (Month 9–12)

- CN: complete translation of all pages + write CN-original blog content (Sarah-persona-CN = "雪球大V分析师")
- JP/KR/TW expansion gated by CN traction
- Translation cost: ~$3k for full site (DeepL + native QA)
- Localized data: Japanese small caps + Hong Kong dual-listed (cross-listed股 first because data overlap with existing universe)

---

## 5. The 90-point craft checklist

What it takes from 71 → 95 (W5-E gap):

### UX consistency
- [ ] Design system documented (Figma library OR Tailwind preset) — same `--color-primary`, `--space-*`, `--radius-*` across both apps
- [ ] Both apps share the same nav header component, same footer, same focus rings
- [ ] Mobile flawless: tap targets ≥ 44px, no horizontal scroll, no overflow text
- [ ] Accessibility AAA: contrast ≥ 7:1, all interactive elements keyboard-reachable, screen-reader announces filter state changes
- [ ] Dark mode complete (Apple system-pref-driven)
- [ ] CN/EN switch in nav, 100% string coverage either language

### Trust
- [ ] Every prediction has primary-source link (8-K, 10-K, earnings call URL with timestamp)
- [ ] "Show audit log" button reveals: model name + version, prompt hash, extraction date, confidence score
- [ ] Caveat in footer persistent + toast on first visit
- [ ] Methodology page passes a stress test: a quant could replicate one StructTuple from the doc alone

### Performance
- [ ] LCP < 1.2s (currently ~1.8s) — image lazy-load, font preload, edge CDN
- [ ] CLS < 0.05 (currently occasional)
- [ ] TTFB < 200ms at p95
- [ ] API p95 < 100ms (lookup endpoint, filter endpoint)
- [ ] No 404, no 500, no JS errors in Sentry per week

### Engagement / onboarding
- [ ] Onboarding flow < 30s: name → use case (3 options) → first sample company served
- [ ] Core action ≤ 3 clicks: home → company → state change → source quote
- [ ] Weekly retention > 30% by Month 6
- [ ] Newsletter open rate > 40%, click rate > 8%

### Polish
- [ ] Zero dead-end states (every empty/error has helpful next-action)
- [ ] Hover/focus/active/disabled states everywhere
- [ ] Empty states have personality (illustrate, don't just say "no results")
- [ ] Microcopy reviewed pass-by-pass against Linear / Bear standard

---

## 6. NOT to do (anti-roadmap)

- ❌ **No mobile native app** — PWA covers 95% of need. Native = 6mo + $50k + App Store gatekeeper friction.
- ❌ **No social features** — no comments, no "follow another analyst," no community. Adds moderation cost + dilutes core JTBD.
- ❌ **No retail investor pursuit** — CAC too high ($30–100 via paid ads vs $0–5 organic for Sarah-persona), expectations wrong (retail wants "buy/sell signal," we don't give that), churn high.
- ❌ **No hiring before PMF** — every dollar to data + content + a freelance designer for the UX sprint. No engineering hire until $5k MRR.
- ❌ **No mobile app, no chat AI in v1, no Bloomberg-style multi-asset coverage, no real-time intraday data, no SEC filing alerts re-builder, no portfolio tracking, no broker integration** — these are tempting feature creep that move us off the Sarah-persona ritual.
- ❌ **No "AI insights" branding** — over-claimed in market, undermines trust. We say "structured extraction" not "AI predicts."
- ❌ **No HN launch before backtest done** — one shot only, must have ammunition.

---

## 7. Milestone roadmap (12 months)

| Month | Milestone | KPI gate | Cost |
|---|---|---|---|
| **1** | Plausible live · waitlist + email collection · 100→250 companies · weekly newsletter v1 · Sarah-persona persona doc | 100 waitlist signups · 20% newsletter open | $50 (Buttondown) |
| **2** | UX consistency sprint 71→85 · Pro tier launch via Stripe (mock first) · auth (Google+GitHub+magic link) · first 3 case studies | 5 paid users · UX score ≥ 85 | $200 (Stripe + Plausible + Buttondown) |
| **3** | Backtest engine v0.1 (200 cos × 20 quarters) · public blog post of result · pivot decision documented · 250→500 companies | Backtest decision logged · 500 newsletter subs | $540 (LLM backtest) + $50 ongoing |
| **4** | HN launch · custom filter alerts live · UX 85→90 · 1 paid KOL case study published | 1000 newsletter subs · 25 paid · HN top-30 | $1500 (KOL fee) |
| **5–6** | Twitter bot live · API beta (Team tier) · 500→700 cos · 2nd KOL case study · backtest v0.2 with more data | $1k MRR · 2000 subs · 5 Team customers | $1500 (KOL fee 2) |
| **7–9** | 700→1000 cos · alerts polished · methodology audit log · Slack integration · case-study library 8+ posts | $5k MRR · 4000 subs · 30 Team customers · NPS ≥ 35 | $0 incremental |
| **10–12** | International (CN site complete) · B2B Index API GA · Series Seed prep OR profitable solo continuation · enterprise tier 2–3 customers | **$20k MRR target** · 10000 subs · 1 enterprise · NPS ≥ 45 · WAU/MAU ≥ 35% | $3k (CN translation) |
| **12+** | Scale: 1000→2000 cos, JP/HK markets, native Slack app, dedicated CS for enterprise tier | $100k MRR aspiration | tied to revenue |

**Total 12-mo opex (data + tools + content)** ≈ $25–35k assuming no hire. Self-funded plausible.

**Revenue gate logic**:
- Month 6 < $1k MRR → re-evaluate ICP (was Sarah wrong?)
- Month 9 < $5k MRR → re-evaluate distribution (KOL strategy not working?)
- Month 12 < $15k MRR → choose: continue solo profitable (lifestyle) OR shelve (project complete, blog as legacy artifact)
- Month 12 ≥ $20k MRR → Seed raise becomes viable ($1–2M @ 8–12% on $12–20M post)

---

## 8. Next 30 days — actionable list

These are the only things that matter in days 1–30. Each ≤ 2-day subagent task.

1. **Wire Plausible analytics to both sites** (D1 + main) with custom events: `view_company`, `apply_filter`, `click_source`, `waitlist_signup`, `newsletter_subscribe`. Half day.
2. **Ship waitlist + email collection** — minimal: email input on homepage + on D1 + post-confirmation thank-you with "we'll send weekly digest." Buttondown integration. 1 day.
3. **Define + publish Sarah-persona** to `docs/personas/p0-independent-analyst.md` + reflect persona-language on homepage hero rewrite. Half day.
4. **First weekly newsletter — manually composed** for week of 2026-05-19. 6 companies + 1 narrative + methodology footer. Half day editorial + half day template build.
5. **UX consistency P0 sprint** — single design token file, nav unified across both apps, footer unified, dark mode foundation, mobile audit. 3 days.
6. **Backtest engine scaffold** — repo layout + historical data fetch script + StructTuple historical reconstruction prompt template + 50-company sample run for sanity. Output: "here's what the pipeline does, here are 50 reconstructed snapshots" — full 4000 snapshot run happens Month 3 not now. 2 days.
7. **Caveat hardening** — site-wide footer + first-visit toast + per-company-page disclaimer. Half day.
8. **Methodology page audit-log foundation** — for 5 sample companies, expose the raw quote + LLM model + prompt hash + extraction date. 1 day.
9. **Twitter/X account live** `@structural_signals` — bio, pinned tweet linking to product, 3 seed tweets. 1 hour + curation rhythm.
10. **Stripe mock + Pro tier UI** — pricing page exists, "Coming soon — join waitlist for early access" CTA, Stripe test-mode checkout for $19/mo Pro tier (no charge, just collect cards). 2 days.

**Total: ≈ 12 working days of subagent capacity → fits 6 parallel subagents in 2-3 days wall-clock.**

---

## 9. Wave 8 dispatch candidates (≥ 5 mini-briefs, ready-to-ship)

Each ready-to-paste-into-dispatch with worktree path, branch, deliverable, acceptance.

### W8-A — Waitlist + Plausible analytics (foundation)
- **Worktree**: `.claude/worktrees/agent-w8a` branch `v4/session4-w8a-waitlist-plausible`
- **Goal**: ship email collection + analytics across both apps
- **Deliverables**:
  - Plausible script integrated in `apps/main` and `apps/d1-phase-detector`
  - Custom events fired: `waitlist_signup`, `view_company`, `apply_filter`, `click_source`
  - Buttondown integration: form posts to Buttondown API, returns success/error UX
  - Homepage hero CTA: "Get this week's signals — Tuesday morning" + email input + button
  - D1 footer CTA replica
  - Privacy policy updated to note Plausible (GDPR-safe, cookieless) + Buttondown
- **Acceptance**: real signup → real Buttondown contact → Plausible dashboard shows event · all 3-tier tests pass · LCP not regressed
- **Estimate**: 1.5 day

### W8-B — UX consistency P0 sprint (71 → 85)
- **Worktree**: `.claude/worktrees/agent-w8b` branch `v4/session4-w8b-ux-consistency`
- **Goal**: close the design-system gap between main site + D1
- **Deliverables**:
  - `packages/ui-tokens` (or main `styles/tokens.css`) with shared color, type, spacing, radius, shadow tokens
  - Unified `<SiteHeader>` and `<SiteFooter>` components consumed by both apps
  - Dark mode foundation (prefers-color-scheme respected, manual toggle in nav)
  - Mobile audit: any tap target < 44px fixed, no horizontal overflow at 320px width
  - 10 microcopy fixes against Linear/Bear standard (specific list provided in brief)
- **Acceptance**: UX score reassessed ≥ 85 by independent reviewer subagent · Lighthouse a11y ≥ 95 · all e2e tests pass on mobile viewport
- **Estimate**: 3 days

### W8-C — Stripe mock + Pro tier UI
- **Worktree**: `.claude/worktrees/agent-w8c` branch `v4/session4-w8c-stripe-pro-tier`
- **Goal**: pricing page + checkout funnel (Stripe test mode, no real money)
- **Deliverables**:
  - `/pricing` page with Free / Pro $19 / Team $99 / Enterprise cards
  - Stripe Checkout test-mode integration for Pro tier (collects card, doesn't charge — message "early access $0 first month")
  - Post-checkout success page + email confirmation
  - Auth flow: email magic link via Resend OR Supabase Auth (decide in brief)
  - Account page `/account` showing tier + lookups remaining
- **Acceptance**: end-to-end signup → checkout → account view works · Stripe webhook fires in test mode · 0 PII written outside Stripe + own DB · tests pass
- **Estimate**: 2 days

### W8-D — Weekly newsletter pipeline v0.1
- **Worktree**: `.claude/worktrees/agent-w8d` branch `v4/session4-w8d-newsletter-pipeline`
- **Goal**: from raw `StructTuple` weekly diff → composed newsletter email
- **Deliverables**:
  - Script `scripts/weekly-digest.py` that:
    1. Reads last week's vs this week's StructTuple state for all companies
    2. Selects 6 companies (3 highest-confidence near_critical entries + 2 dynamics_family transitions + 1 editor's pick slot)
    3. Generates draft email markdown via LLM (DeepSeek V4 primary, Doubao seed backup per renai precedent)
    4. Outputs `digests/2026-WW.md` + uploads to Buttondown as draft
  - Newsletter template: hero + 6 cards + 1 deep-dive (manual) + methodology footer + unsubscribe
  - Cron schedule: Monday 6am UTC for human review, sends Tuesday 11am UTC (7am ET)
  - First newsletter manually QA'd before send
- **Acceptance**: digest pipeline runs end-to-end without manual intervention · Buttondown draft renders correctly · open rate target ≥ 30% on first send (gated, evaluated post-send)
- **Estimate**: 2.5 days

### W8-E — Backtest engine v0.1 scaffold + 50-co sanity run
- **Worktree**: `.claude/worktrees/agent-w8e` branch `v4/session4-w8e-backtest-scaffold`
- **Goal**: build pipeline shell, run small sample, defer full run to Month 3
- **Deliverables**:
  - `backtest/` package with:
    - `fetch_historical.py` (yfinance + sector ETF mapping)
    - `reconstruct_structtuple.py` (10-K + 4 quarterly calls → StructTuple via LLM)
    - `eval_alpha.py` (compute forward 6-month return vs sector benchmark)
    - `report.py` (markdown summary)
  - 50-company sanity run (top 50 by market cap, 2023Q1 snapshots only)
  - Output: `docs/backtest/v0.1-sanity-2026-05-13.md` showing methodology + 50-co results
  - LLM cost log + reproducibility note
- **Acceptance**: pipeline runs end-to-end, 50-co output produced, methodology document peer-reviewable, cost < $50 actual spend, clear path to full run documented
- **Estimate**: 2.5 days

### W8-F — HN launch readiness checklist
- **Worktree**: `.claude/worktrees/agent-w8f` branch `v4/session4-w8f-hn-launch-prep`
- **Goal**: prepare everything needed for an HN launch (target Month 4, after backtest)
- **Deliverables**:
  - HN-readiness checklist `docs/launches/hn-launch-readiness-2026-05-13.md`:
    - Required: backtest result, methodology page, audit log feature, case study × 1, waitlist > 500, uptime > 99.5% past 30 days
    - Day-of prep: founder voice draft post (3 variants), comment templates for predictable HN objections (10 prepared), live monitoring dashboard, status page
  - Draft "Show HN: ..." post (3 variants A/B/C — title + body)
  - 10 anticipated objections + prepared answers (financial-advice concern, LLM hallucination concern, sample size concern, ICP concern, monetization concern, methodology, backtest, accuracy claims, data source, philosophy)
  - "Day-of" runbook: who watches, response time SLA, how to handle traffic spike (CDN cache config check)
- **Acceptance**: checklist comprehensive, runbook actionable, draft posts critique-ready by next session
- **Estimate**: 1.5 days

**Total Wave 8 capacity ask**: 13 days of subagent work, fits 6 parallel subagents in ~2.5 days wall-clock with isolation:worktree.

**Priority order if capacity constrained**: W8-A (foundation) > W8-D (newsletter — main retention loop) > W8-B (UX) > W8-C (pricing) > W8-E (backtest) > W8-F (HN prep).

---

## 10. Scoring rubric — how we measure 90+

Six metrics, each weighted, target shown.

| Metric | Why | Month 1 | Month 3 | Month 6 | Month 12 | Weight |
|---|---|---|---|---|---|---|
| **WAU / MAU** | habit signal — Bear/Notion zone is 35% | n/a | 15% | 25% | 35% | 25% |
| **Pro tier conversion** | willingness-to-pay signal | n/a | 1% | 3% | 5% | 20% |
| **MRR / ARR** | unambiguous business signal | $0 | $200 | $1k | $20k | 25% |
| **NPS** | recommendation likelihood | n/a | 25 | 35 | 45 | 10% |
| **Press / KOL mentions** | distribution working | 0 | 2 | 8 | 25 | 10% |
| **Retention curve M2** | product stickiness | n/a | 40% | 55% | 65% | 10% |

A 90+ score = WAU/MAU ≥ 35% AND Pro conversion ≥ 4% AND MRR ≥ $15k AND NPS ≥ 40 AND retention ≥ 60%. Anything less is a craft / fit / distribution gap to be diagnosed.

---

## Appendix A — risks + mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Backtest shows null result | 50% | high (kills alpha framing) | Pre-committed pivot to narrative-product positioning (see § 4.B). Honesty is itself a trust moat. |
| LLM extraction quality drift | 40% | medium | Monthly eval against 50-co ground-truth set (built once in Month 2). Alert if F1 drops > 5pp. |
| Sarah-persona doesn't convert at 4% | 35% | high (ICP wrong) | Persona interview round at Month 3 with 10 newsletter subs. Adjust pricing / feature mix based on findings. |
| Compliance — financial advice claim | 20% | high (legal) | Persistent caveat + ToS + "not financial advice" toast + DM lawyer review at Month 2 before paid launch. |
| Doubao / DeepSeek pricing change | 25% | medium | Multi-provider abstraction (already in renai precedent). 2-week migration capacity assumed. |
| Single-founder bandwidth | 90% | medium | Auto-mode subagent workflow + biweekly user-feedback cadence + ruthless NOT-to-do list. |
| HN launch flop | 30% | medium | Single-shot; prep heavy (W8-F). If flops, FinTwit + Product Hunt are secondary launches. |
| Regional block (CN IP) on LLM | 50% | low (mitigated) | DeepSeek direct API already in stack per reference_deepseek_direct_api_2026_05_06. |

---

## Appendix B — competitive positioning grid

| Product | Audience | Price | What it does | Where we fit |
|---|---|---|---|---|
| Bloomberg Terminal | sell-side / buy-side pros | $24k/yr/seat | everything | not our market |
| Sentieo / AlphaSense | research analysts | $1k–6k/seat/yr | smart search + LLM Q&A on filings | adjacent; we differ via *structural state*, not text Q&A |
| Koyfin | independent analysts | $79/mo | charts + financials | adjacent; we differ via *regime signal*, not data display |
| TIKR Terminal | retail / indep | $30/mo | screener + DCF | adjacent; we differ via *qualitative structure*, not quant ratios |
| Quartr / Daloopa | analysts | $50–200/mo | structured filings | adjacent; we sit on top of structured filings, add *regime layer* |
| Substack-tier indep newsletters | retail+pro | $5–50/mo | one writer's view | competitor for attention; we differ via systematic + reproducible |

**Our unique slot**: "Systematic structural-regime view of 1000 public companies, transparent methodology, weekly digest. Sits next to Koyfin in your tab bar, not as replacement for Bloomberg."

---

## Closing — the bet

The bet is that **one specific user — Sarah, the 4k-subscriber independent analyst — has been waiting for someone to ship structured regime signals to her inbox every Tuesday morning at 7am ET, with the receipts, at a price she can expense.**

If she pays $19/mo and brings two friends per quarter, this product reaches $20k MRR by month 12 with one founder, $25k opex, no employees.

If she doesn't pay, the diagnostic is sharp: ICP was wrong, OR craft was below 90, OR retention loop broken. Each is fixable, each tells us something. Failure is informative.

The single highest-leverage next move is **W8-A + W8-D shipped this week**: a real waitlist with a real first newsletter on its way. Without that, nothing else matters. With that, we have a feedback loop and a year to learn.

— W7-D subagent, 2026-05-13
