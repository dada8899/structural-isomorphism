# Show HN title candidates — 2026-05-24

**Purpose**: unblock HN readiness § 2 ("3 title candidates A/B/C" already exist;
this doc expands to 5 + adds A/B test criteria).

**HN title rules (binding constraints)**:

- ≤ 80 characters including "Show HN: " prefix
- HN auto-strips "Show HN:" from front-page display, so the 70 chars after it
  is what readers see
- No emoji, no ALL CAPS, no "1 weird trick" framing — flagged as spam
- "Show HN" template requires either (a) a working demo URL, (b) source code,
  or (c) both. We have both — strongest signal.
- Specific numbers + concrete result + curiosity hook outperform abstract
  framings (HN historical data: posts with numbers in title +18% upvote rate)

**Backtest-conditional**: pick at T-1h based on the v0.2 backtest outcome
(Strong / Weak / Null). The 3 outcome buckets each have a best-fit title.

---

## Candidate 1 — Methodology-first (Title A from existing draft)

> **Show HN: Structural Isomorphism — testing whether one Clauset MLE pipeline transfers across 13 scientific domains**

- 116 characters → **OVER LIMIT**. Trim required.
- Trimmed: *"Show HN: Testing if one statistical pipeline transfers across 13 scientific domains"* (80 chars)
- Strengths: signals seriousness, falsifiability-forward, accurate
- Risks: lower CTR than action-oriented titles, "13 scientific domains" is the only concrete hook
- Best fit: Null / Weak backtest outcome — methodology IS the product

## Candidate 2 — Alpha-forward (Title B from existing draft)

> **Show HN: Phase classifier for 500 public companies with open backtest and methodology**

- 88 chars → **OVER LIMIT**. Trimmed: *"Show HN: Phase classifier for 500 stocks, open backtest, open methodology"* (74 chars)
- Strengths: concrete (500 stocks), scannable, invites scrutiny ("open backtest")
- Risks: close to "prediction service" framing — could attract financial advice complaints, may trigger HN moderator to add `[finance]` tag (negative signal)
- Best fit: Strong backtest (Sharpe ≥ 0.5) ONLY

## Candidate 3 — Curiosity hook (Title C from existing draft)

> **Show HN: We tested if neural avalanches and bank runs obey the same equation**

- 79 chars → **OK** (just under 80)
- Strengths: concrete, surprising, true claim — highest CTR potential
- Risks: leans poetic; HN audience sometimes punishes "too good to be true" framing
- Best fit: any backtest outcome; works as backup if Candidate 1 underperforms in friend-test

## Candidate 4 — Numbers + funnel (NEW)

> **Show HN: 17 domains pre-registered, 13 in-band, 4 published failures. Code + data**

- 86 chars → **OVER LIMIT**. Trimmed: *"Show HN: 17 domains pre-registered, 13 in-band, 4 published failures"* (68 chars)
- Strengths: HIGHEST specificity. Three numbers + one verb. Plays the "we report our failures" hand — extremely strong HN positive signal
- Risks: requires reader to understand "in-band" without context
- Best fit: any backtest outcome; particularly strong for Weak / Null where the
  4-failures detail is the headline asset

## Candidate 5 — Methodology meta (NEW)

> **Show HN: Pre-registering exponent bands before fetching data — does it stop p-hacking?**

- 95 chars → **OVER LIMIT**. Trimmed: *"Show HN: Pre-registering before fetching data to stop p-hacking"* (62 chars)
- Strengths: meta angle, frames as open question (HN loves open questions), keyword "p-hacking" rings the methodology-rigor bell
- Risks: doesn't tell reader what the *product* is — they have to click to find out
- Best fit: Weak / Null backtest — when the methodology IS the product

---

## Decision matrix

| Backtest outcome | Primary title | Backup title |
|---|---|---|
| Strong (Sharpe ≥ 0.5) | Candidate 2 (Phase classifier) | Candidate 4 (numbers + funnel) |
| Weak (Sharpe 0.1–0.4) | Candidate 4 (numbers + funnel) | Candidate 1 (methodology-first) |
| Null (Sharpe ≤ 0.1) | Candidate 5 (pre-registering...) | Candidate 1 (methodology-first) |
| Tie-breaker | Candidate 4 — strongest "we report failures" signal | — |

**Recommendation if no fresh backtest in hand at launch time**:
Use Candidate 4. The 17 / 13 / 4 numbers are true regardless of the
v0.2 backtest result and they perform the strongest "epistemically honest"
signaling.

---

## Pre-launch friend-test

24 hours before launch, share the 5 candidates with 3-5 trusted reviewers
(senior researchers + HN-experienced friends) and ask:

1. *Which one would you click on the HN front page?*
2. *Which one most accurately describes the project?*
3. *Which one most poorly describes the project?*

If the answer to (1) is uniformly different from (2), bias toward (2) — HN
upvotes a true title that hooks less but rewards more on quality of discussion.

---

## A/B not viable on HN

HN does not allow you to test multiple titles. You get **one shot**. If a
title gets < 5 upvotes in the first 15 minutes, the post is dead. You can
delete and re-post once, but a same-day repost is heavily flag-prone.

So this is a single decision at T-1h, not a real A/B.

---

## What the body says (constant across all titles)

The body (first comment, since Show HN URL-post bodies live in the comment
chain) stays identical to the 2026-05-15 draft. The title is what we
swap. See `hn-launch-2026-05-15.md` for the body text.

One exception: if Candidate 2 (Phase classifier) is chosen, the body should
lead with the phase detector + backtest, not with the cross-domain framing.
The 2026-05-15 body leads with the cross-domain framing. So Candidate 2 →
requires re-ordering the body. Not a blocker, but plan for it at T-2h.
