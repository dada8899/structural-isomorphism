# Twitter / X thread — arXiv launch — 2026-05-24

**Posted**: arXiv-day, 09:00 PT (Tuesday optimal slot).
**Account**: @dada8899 (or project handle once warm).
**Format**: 10-tweet thread (extended vs the 7-tweet 2026-05-15 thread).
**Companion**: media attached on tweet 1 (`site/demo.mp4`) + tweet 4 (band-overlap plot).
**Char budget**: ≤ 270 chars/tweet (room for trailing emoji-free media).

> Difference vs `twitter-thread-2026-05-15.md` (the pre-arXiv version):
> this thread leads with **arXiv ID + paper title**, includes a media asset
> on tweet 1, and ends with a CTA to follow + reply for replication notes.

---

## Tweet 1 (with demo.mp4 attached)

New paper on arXiv today: we tested whether one frozen statistical pipeline transfers, untuned, across 13 cross-domain systems — neural avalanches, bank runs, wildfires, GitHub stars, more. 13 pass pre-registered bands. 4 fail. We published the failures. Thread ↓

## Tweet 2

arXiv: arxiv.org/abs/ARXIV_ID_PENDING — "Adversarial Pre-Registration as Anti-p-Hacking Methodology: A Single Cross-Domain SOC Pipeline with 17 Pre-Registrations and 4 Negative Verdicts" — cond-mat.stat-mech (primary), physics.data-an (cross-list).

## Tweet 3

The pipeline is one frozen file: v4/lib/soc_pipeline.py, 339 LOC, commit 7ee228c. Discrete Clauset MLE: KS-optimal xmin, Hill alpha, block-bootstrap CIs, Vuong tests vs lognormal + exponential. Same function, every system. No per-domain knobs anywhere downstream.

## Tweet 4 (with band-overlap plot attached)

Pre-registration is the discipline. Every claimed universality class declares its exponent band in a YAML committed BEFORE we touch the data. Out-of-band fits are FAIL — not retroactively re-classified. `pre_registered_at` git timestamps anchor the chain of custody.

## Tweet 5

The 4 published failures: 2023 CVE high-severity disclosures (Vuong → lognormal), NYC FDNY fire dispatch (CI outside band), r/wsb post cascades (tail-only power law), and a commercial S&P 500 trading fork (Sharpe indistinguishable from zero). Paper § 4.

## Tweet 6

Why this matters: 13 PASS + 4 published FAIL is more credible than 17 PASS from a re-tunable pipeline. A framework that never rejects isn't measuring anything. The 4 published negatives are the evidence the pipeline can fail when reality fails.

## Tweet 7

Honest limits — and we hold these in the paper, not in apology mode: (a) the LLM ensemble for stat-pipeline is within-vendor (B3, 3x DeepSeek), not cross-architecture; B4 partly blocked by region routing for some vendors. (b) several alphas sit near 3.0 boundary.

## Tweet 8

Open artifacts. Code MIT: github.com/dada8899/structural-isomorphism. Dataset CC-BY: doi.org/10.5281/zenodo.19615170 (SIBD-63, 63 A-level cross-domain pairs, multi-vendor critic verdicts). PyPI: pip install structural-soc-pipeline. 213 unit + 11 e2e tests.

## Tweet 9

Live demos. Search across the cross-domain KB: beta.structural.bytedance.city. Phase classifier for 500 public companies with source-quote provenance + LLM prompt hash on every prediction: phase.bytedance.city. Research preview — not investment advice.

## Tweet 10

What we want from reviewers: try to break a verdict. If you think any of the 13 PASSes is post-hoc band engineering, the YAML files have a source_paper field — propose a different paper's band and we'll re-run. PRs welcome at v4/preregistration/. Follow + reply for replication notes.

---

## Tweet 11 (BONUS — only post if main thread is going well at 2h mark)

For those asking "how do you make money": v0.2 backtest gates the answer.
Sharpe ≥ 0.5 → analyst-tier Pro + B2B Structural Index API. ≤ 0.1 → pivot
to Substack-style narrative product on top of the open methodology. Either
way: pricing page lives at /pricing.

## Tweet 12 (BONUS — for the senior researcher pings)

Senior outreach to @ScheffWUR / @V_Priesemann / @aaronclauset / Plenz / Sornette is queued for T+3 to T+14 — after public reception lands, not before. We want them seeing the preprint + the comments alongside, so the cold-email has substance to anchor on.

---

## Visual asset specs

- **Tweet 1 media**: `site/demo.mp4` (15s, 800×500, ≤ 2 MB, H.264 faststart). X auto-converts to GIF preview in feed.
- **Tweet 4 media**: `paper/figures/band-overlap-13-systems.png` (single panel, 1200×900, light theme, color-blind-safe palette). If not yet generated, fallback: contact-sheet from `tools/demo-still-*.png`.

## Posting cadence

- All tweets in one thread, posted back-to-back (no time gap). X penalizes time-gapped self-reply threads vs single-shot threads.
- After thread is up, quote-tweet **tweet 1** from a co-author or trusted reviewer's account with a "this is what I look at when people ask me about cross-domain X" framing. Do not engagement-farm via DM-requested quote tweets — X feed sentiment punishes obvious coordination.

## Engagement playbook

- **First 60 min**: respond to every quoted reply within 10 min. X algo weighs early reply velocity heavily.
- **First 24h**: pin tweet 1; check 3x daily; quote-reply with paper screenshots to specific data-objection tweets (not generic "great work" comments).
- **If a quote-reply has > 50 likes**: pin it temporarily and add to FAQ doc.
- **If a critic with > 20K followers replies**: respond once, substantively, with paper link + line/section reference. Do NOT engage in a thread fight; one reply, then move on.

## Cross-promote

- Drop the thread link into the Mastodon post (already drafted in `mastodon-2026-05-15.md`)
- Embed the thread in the blog post (`blog-post-arxiv-2026-05-24.md`) under "Discussion"
- Forward to private group DMs of senior researchers (Plenz / Priesemann etc) with a "fyi the thread is up; cold email coming T+3 to T+14" note — relationship hygiene, not an ask
