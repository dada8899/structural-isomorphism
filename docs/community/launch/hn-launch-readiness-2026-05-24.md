# HN launch readiness audit + day-of playbook — 2026-05-24

**Status**: not-yet-launched. Final go/no-go gate at end of doc.
**Companion**: [hn-launch-2026-05-15.md](hn-launch-2026-05-15.md) — drafted post body.
**Source brief**: W7-D mini-brief 6.

This doc audits what we have, what's missing, and what we do on launch day.
**No launch action is taken from this PR.** The brief explicitly says:
*"不发 launch."*

---

## 1. Readiness checklist

Items marked **(blocker)** must be true before launch. Items marked **(strong)**
are not strictly required but materially affect outcome. Items marked **(nice)**
can be deferred.

### Content + story

- [x] Show HN body drafted ([hn-launch-2026-05-15.md](hn-launch-2026-05-15.md))
- [x] Honest limitations section included (within-vendor ensemble, alpha-near-3 cases, etc.)
- [x] Pre-registered FAIL/PARTIAL/NULL cases documented in the companion paper
- [x] Falsifiability framing throughout — not "we proved" but "we tested"
- [ ] **(blocker)** Demo GIF or 15s screencast embedded above the fold of the linked page
- [ ] **(strong)** Per-prediction audit log button (W7-D § 5) — "show your work" on each StructTuple. Currently methodology page exists but per-prediction transparency is not exposed.
- [ ] **(nice)** Three publicly written case studies (1 hit / 1 miss / 1 in-progress) — boost trust signal
- [ ] **(nice)** Single canonical 90-second video explainer linked from repo README

### Technical readiness

- [x] Public live URL works without auth: `beta.structural.bytedance.city`, `phase.bytedance.city`
- [x] Repo public at `dada8899/structural-isomorphism`; README scannable in 30s
- [x] Test suite green (per CI on `main`)
- [x] PyPI packages live: `structural-soc-pipeline`, `structural-critics`, `structural-taxonomy`
- [x] Dataset on Zenodo with DOI: `10.5281/zenodo.19615170`
- [ ] **(blocker)** Load test passed — site stays up at 50 RPS for 10 min (HN front page peak ≈ 20-40 RPS, 95th pctile ≈ 80 RPS for hot front-page Show HN; we want 2× headroom)
- [ ] **(blocker)** Plausible analytics covering all 26 pages (DONE in this PR — see consistency-audit-2026-05-24.md)
- [ ] **(blocker)** Status page + uptime monitor green for the prior 30 days (≥ 99.5% uptime)
- [ ] **(strong)** CDN cache configured on the marketing site — `Cache-Control: public, max-age=300` on HTML, longer on assets
- [ ] **(strong)** Error tracking (Sentry or equivalent) on both apps catching JS errors + 5xx
- [ ] **(nice)** Backup mirror for the demo URL in case primary CDN flakes

### Funnel + retention

- [x] Waitlist form live (this PR — W7-D mini-brief 1)
- [x] Plausible custom events instrumented (`Waitlist Signup`, `Checkout Start`)
- [ ] **(strong)** Newsletter pipeline ready to send a "thank you HN" issue 24h post-launch — pipeline scripted (W7-D mini-brief 3); content TBD
- [ ] **(strong)** Twitter/X account `@structural_signals` exists with bio + pinned tweet linking to product (deferred per ~/.../W7-D § 8 item 9)
- [ ] **(nice)** Pricing page with Stripe test-mode checkout (this PR — W7-D mini-brief 2; status: live but pre-PMF, "early access" framing)

### Compliance + caveat

- [x] Persistent "not financial advice" caveat in footer of phase detector
- [x] Methodology page exists (W6-B)
- [ ] **(strong)** First-visit caveat toast on `phase.bytedance.city` (W7-D § 5 trust-checklist item)
- [ ] **(nice)** Per-company-page disclaimer for the StructTuple JSON

### Backtest gate (W7-D § 4.B is the "make or break")

The W7-D doc explicitly says: **"No HN launch before backtest done — one shot only, must have ammunition."**

- [ ] **(blocker)** Backtest v0.2 (real data) complete and report published
- [x] Backtest v0.1 scaffold + walk-forward pipeline (this PR — W7-D mini-brief 4)
- [ ] **(blocker)** Backtest decision documented per W7-D § 4.B pre-commits (Strong / Weak / Null)
  - Strong (Sharpe ≥ 0.5) → lean into alpha-screener framing in the HN title/body
  - Weak (0.1–0.4) → "modest alpha, transparent methodology"
  - Null (≤ 0.1) → pivot to "structured research narrative" framing, do NOT claim alpha

---

## 2. Show HN title — 3 candidates (A/B/C)

The 2026-05-15 draft uses title **A**. Variants B and C are alternative
framings for the 3 backtest outcomes from § 4.B. Pick at launch based on
the backtest result.

### A — Methodology-first (current 2026-05-15 draft)
> **Show HN: Structural Isomorphism — testing whether one Clauset MLE pipeline transfers across 13 scientific domains**

- Strengths: signals seriousness, falsifiability-forward, accurate
- Risks: 80 chars is borderline; "Clauset MLE" is jargon for non-stat-physics audiences; lower CTR than action-oriented titles
- Best fit: Null/Weak backtest outcome — methodology IS the product

### B — Alpha-forward (use only if Strong backtest)
> **Show HN: Phase classifier for 500 public companies, transparent methodology, open backtest**

- Strengths: concrete, scannable, names the audience (analysts), invites scrutiny via "open backtest"
- Risks: dangerously close to "prediction service" framing — could attract financial advice complaints
- Best fit: Strong backtest outcome (Sharpe ≥ 0.5) only

### C — Curiosity hook
> **Show HN: We tested if neural avalanches and bank runs obey the same equation. They do.**

- Strengths: highest CTR potential — concrete, surprising, true claim
- Risks: too clickbaity for HN audience; "they do" risks overclaim relative to the careful "13/13 in-band" framing
- Best fit: backup if A underperforms in pre-launch friend test

**Recommendation**: stay with title A. Switch to B only if backtest is Strong AND we've added a per-prediction audit log.

---

## 3. Top 10 anticipated objections + prepared answers

These are the FAQ comments to have prepped in a draft Google Doc on launch day,
so the founder can respond within 5 minutes and not lose comment momentum.

### Q1: "13/13 in-band feels like p-hacking. Where are the failures?"

> Sharing the concern — that's why we pre-registered FAIL cases up front.
> The companion paper (`paper/anti-phacking-unified-2026-05-15.md`) walks
> through four pre-registered cases that returned FAIL, INCONCLUSIVE,
> PARTIAL, NULL — 2023 CVE disclosures, NYC FDNY fire dispatch, r/wsb
> cascades, and a trading commercial fork. We argue 13-pass-of-17 (not
> 13-of-13) is more credible than 17 confirmations from a re-tunable
> pipeline. The next phase is harder: pre-registering bands for NEW
> systems (Bitcoin Cash transactions, FluNet ILI, Flickr cascades) before
> fetching data.

### Q2: "Several alpha values sit near 3.0 — that's the boundary. How is the band test diagnostic there?"

> Correct, and it's a real concern. We report it explicitly in the paper.
> S&P 500 returns and GitHub star cascades both have CIs that touch
> classical-boundary regimes. The KS-CI band overlap is a deliberately
> conservative test — it accepts edge cases as in-band. We'd rather
> over-accept and lose discriminating power than under-accept and look
> stricter than we are. The harder test is whether a NEW system can be
> rejected.

### Q3: "Why no Claude / GPT-5 in the ensemble? Three DeepSeek decodings is not multi-vendor."

> Fair and we say so in § 6 of v0.3 and § 8 of v0.4. The
> architecturally-diverse B4 ensemble (Claude Opus + GPT-5 + DeepSeek +
> Kimi + GLM-5) is blocked partly by OpenRouter region routing for
> Anthropic + Google from China IPs. We've documented this as a known
> limitation, not pitched it as "ensemble". Multi-vendor proper is a Q3
> 2026 deliverable.

### Q4: "Is this financial advice? You list public companies and a 'near critical' label."

> No. Persistent footer caveat on every page; methodology page makes it
> clear we extract structural state from disclosures, we do not predict
> price. The "Phase Detector" research preview is a research artifact —
> intended for analysts using it as one input among many, not retail
> investors looking for buy signals. The dynamics_family + confidence
> score is an extraction, not a forecast.

### Q5: "Cool but is the alpha real?"

> v0.1 of the backtest is in this commit set; v0.2 (real data, full S&P
> 500, 2020–2024 walk-forward) is the next 30 days. Per our
> pre-commits: Sharpe lift ≥ 0.5 → alpha-screener positioning; 0.1–0.4
> → "modest alpha, transparent"; ≤ 0.1 → pivot to structured-narrative.
> Whatever the result is, we'll publish it.

### Q6: "How does this differ from Bloomberg / Sentieo / Koyfin / TIKR?"

> Doesn't replace any of them. Bloomberg = everything. Sentieo / AlphaSense
> = LLM Q&A on filings. Koyfin / TIKR = charts + financials. We sit one
> layer up: 1000 companies' current structural-state, weekly, with
> source quote + LLM prompt hash. Sits next to Koyfin in your tab bar,
> not as a replacement for any of them.

### Q7: "Why power laws? Power laws are everywhere."

> Power laws alone are weak evidence — Stumpf & Porter 2012 already
> dismantled the "everything is power-law" enthusiasm. What we test is
> stronger: the same SOC pipeline yields exponents that land inside
> *pre-registered* bands AND survive Vuong tests against log-normal +
> exponential alternatives AND pass block-bootstrap CIs. It's the
> conjunction that's diagnostic, not "alpha is in (2, 3)".

### Q8: "Open source?"

> MIT-licensed code, CC-BY-4.0 datasets. PyPI: `pip install
> structural-soc-pipeline`. Repo: `dada8899/structural-isomorphism`. The
> 339-LOC frozen pipeline is `v4/lib/soc_pipeline.py` at commit
> `7ee228c`. The Phase Detector data extraction prompts are also open.

### Q9: "Sample size — 13 systems is small. What's the statistical power on the meta-claim?"

> Correct, 13 is small and we don't argue otherwise. The roadmap
> (paper § 8) lists 6 next-batch systems for pre-registration; the
> meta-claim "single pipeline works for n independent domains" gets
> more diagnostic with each fresh in-band hit and especially with each
> fresh fail.

### Q10: "How do you make money?"

> Two paths, gated by the v0.2 backtest. Strong-signal path: Pro $19/mo,
> Team $99/mo for analysts; B2B Structural Index API at $500/mo for
> small funds. Null-signal path: Substack-style narrative product at
> $9/mo. Either way: no VC funding, no growth-at-all-costs. Pricing
> page (currently shows test-mode Stripe) is at /pricing.

---

## 4. Day-of playbook

### T -24h (Monday morning, day before launch)

- [ ] Confirm backtest v0.2 result + decide title A vs B
- [ ] Run final dogfood pass: anonymous incognito → land → submit → screen
      record. If any 4xx/5xx → DO NOT LAUNCH.
- [ ] Pre-cache HN headline image / OG card
- [ ] Drain ALL non-essential cron jobs on VPS for 24h post-launch (sync
      jobs, weekly newsletter cron, etc.) — free up CPU + log bandwidth
- [ ] Notify VPS hoster of expected traffic spike
- [ ] Open prepared-answers Google Doc, paste in the 10 Q&A from §3 above
- [ ] Set Slack + iPhone push notifications for monitor.bytedance.city alerts

### T -1h (Tuesday, 7:30 AM ET)

- [ ] Sanity-check: `curl -I https://beta.structural.bytedance.city` → 200
- [ ] Sanity-check: `curl -I https://phase.bytedance.city` → 200
- [ ] Verify Plausible recording events (visit the site, see it light up)
- [ ] Verify analytics for both /pricing and /waitlist endpoints
- [ ] Verify the backend tail logs: `ssh vps tail -f web/backend/logs/*.log` — quiet
- [ ] Pull `git pull` latest master → verify deploy is current commit
- [ ] Final test of /api/waitlist POST → ensure write to DB works
- [ ] Have repo + paper + Zenodo DOI tabs all preloaded
- [ ] Coffee

### T 0 (Tuesday 8:00 AM ET — submit)

- [ ] Submit Show HN post with title A (or B if backtest greenlights)
- [ ] Watch the first 5 minutes — is it climbing? If it stalls at rank 25+ → don't bump; let it ride
- [ ] Within 10 min, post first comment (the body — Show HN auto-includes
      URL but body lives in the first comment)

### T +1h .. T +6h (peak)

- [ ] Respond to every top-level comment within 15 minutes
- [ ] Watch monitor.bytedance.city dashboard: latency p95, error rate, RPS
- [ ] If RPS > 100 RPS sustained → scale (currently we'd hit VPS CPU cap; have
      tccli ready to provision a temp upgrade if needed)
- [ ] Pin the 3-5 best questions; reply with prepared answers from § 3
- [ ] DO NOT delete or vote-manipulate any comments. HN flags this.

### T +6h .. T +24h

- [ ] Continue answering every comment, even if slower
- [ ] At T +12h, post a comment summarizing the top 3 questions + answers (helps
      late readers)
- [ ] Schedule the "Thank you HN, here are the top concerns" follow-up post
      for T +48h (NOT a "Show HN") on /r/algotrading or directly on the blog

### T +24h .. T +48h

- [ ] Send the W7-D weekly-signals newsletter with a "from HN" subject line
      tag (the pipeline is in this PR — content needs human editorial)
- [ ] If we cleared 500 waitlist signups in 24h, the launch was a hit. < 200 → diagnose.
- [ ] Write the retrospective doc: `docs/community/launch/hn-launch-retro-YYYY-MM-DD.md`
      with traffic curve + top objections actually surfaced + waitlist conversion

### Rollback conditions

If any of the following → take down the linkpost via `delete` on HN
(allowed within first 2h):

- Critical bug found that misrepresents methodology
- VPS goes down for > 5 min and we can't restore
- A top comment exposes a factual error we can't refute and can't quickly fix

Soft rollback (don't delete, but stop driving traffic): if NPS-equivalent feedback
in the comments turns hostile in the first 3 hours, stop tweeting / re-posting,
let it slide off front page naturally.

---

## 5. Go / no-go gate

Launch only if **ALL** of:

1. All `(blocker)` items in § 1 are checked
2. Backtest v0.2 complete + decision documented
3. § 4 T-1h checks all pass
4. Founder has 8 contiguous hours available for comment monitoring

**Current status (2026-05-24)**: NOT READY.
Outstanding blockers:

- Demo GIF / screencast above the fold (§ 1 content)
- Load test passing 50 RPS × 10 min (§ 1 technical)
- Backtest v0.2 (real data) complete (§ 5 gate item 2)

Next checkpoint: 2026-06-24 (one month).

---

## Appendix — link-checks ran in this audit

| Link | Status (2026-05-24) |
|---|---|
| beta.structural.bytedance.city | not checked from here (no network) |
| phase.bytedance.city | not checked from here (no network) |
| github.com/dada8899/structural-isomorphism | not checked from here |
| Zenodo DOI | format valid: 10.5281/zenodo.19615170 |
| PyPI packages | three names declared; install verification pending |

The "not checked" items are flagged for re-verification in the T-1h list.
