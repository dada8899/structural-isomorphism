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

---

## #6 (NEW 2026-05-25): Negative results as launch narrative

The v0.2 walk-forward came back at Sharpe lift -0.23 and the c4 critic
ensemble demoted 33% of auto-curated classes. A reviewer-feedback pass
on the long-form blog (`blog-post-negative-results-2026-05-25.md`)
flagged "publishing the failures" as the most distinctive,
unforgeable signal in the whole launch package. This adds a sixth
title candidate built explicitly around that frame.

### Three concrete title options

**Candidate 6a — Self-killing backtest**

> **Show HN: We built a cross-domain SOC validator and our own backtest killed it**

- 80 chars including "Show HN:" → **AT LIMIT**. Verify exact byte count at T-2h.
- Strengths: concrete verb ("killed"), self-deprecating framing flips the usual
  "we built X and it works" cliché, signals epistemic honesty without using
  the word
- Risks: "SOC" is jargon — needs to resolve fast in the first body paragraph
  or readers bounce; "killed it" can be misread as positive slang
- Best fit: any backtest outcome — the past tense is honest regardless

**Candidate 6b — Numbered honest funnel**

> **Show HN: -0.23 Sharpe, 33% of our classes rejected, 4 published failures**

- 79 chars → **OK** (just under 80)
- Strengths: three numbers, all negative, all true; impossible to read as a
  product pitch; HN historically over-rewards posts that lead with their
  worst result
- Risks: looks like a confession without context — reader has to click to
  find out *what* the project actually is. High-CTR / low-relevance click
  risk on the front page
- Best fit: when arXiv preprint is live and the title can lean on the
  preprint abstract to provide context one scroll down

**Candidate 6c — Pre-registration discipline frame**

> **Show HN: Pre-registered a backtest, it failed at -0.23 Sharpe, publishing anyway**

- 84 chars → **OVER LIMIT**. Trimmed: *"Show HN: Pre-registered a backtest, it failed, publishing anyway"* (64 chars)
- Strengths: tells the methodology story in a single sentence; "publishing
  anyway" is the unforgeable signal; the pre-registration vocabulary
  attracts the metascience / replication-crisis audience explicitly
- Risks: "failed" alone (after the trim) loses the magnitude; pre-registration
  audience is smaller than the cross-domain-physics audience
- Best fit: when senior-outreach feedback has been heavy on the
  pre-registration angle and we want to recruit metascience commenters
  into the HN thread

### When to use #6

Use #6 when **at least two** of the following hold at T-1h:

- The v0.2 backtest result is still null (Sharpe lift below +0.3) and we
  do not have a re-run on a wider universe that flips the verdict.
- Senior-reviewer outreach has come back with feedback praising the
  *honesty* of the writeup, not the alpha. ("This is what cross-domain
  science needs more of" type comments.)
- The CVE pre-registration failure and the c4 33%-rejection are both
  live in the repo and discoverable from the first comment of the HN
  post within one click.
- We have run friend-test on the negative framing and at least 3/5 friends
  said "I would click that".

### When NOT to use #6

Skip #6 in any of these cases:

- Senior outreach lands one or more positive endorsements from
  recognisable names in stat-mech, complex systems, or quant finance
  before T-1h. In that case the #1 (methodology-first) or #3 (curiosity
  hook) titles are stronger — they let the endorsements do the heavy
  lifting in the thread, and the negative-results material can be a
  comment-thread asset rather than the headline.
- A late v0.2 re-run or v0.3 partial result moves the Sharpe lift above
  +0.3. Then the verdict is no longer "null", #6's premise collapses,
  and Candidate 2 (Phase classifier) becomes viable.
- The repo or the arXiv preprint is not fully indexable at T-1h.
  Without a one-click path to the published failures, #6 reads as
  unsubstantiated confession and underperforms.
- We are A/B-coupling with a Twitter thread that leads with the positive
  13/17 PASS frame. Mixed signals across surfaces dilute both.

### Recommended fallback ranking

Default fallback: **Candidate 6b** (numbered honest funnel). The three
negative numbers in the title are *unforgeable signals* — they cannot be
manufactured by a marketing team, they cannot be A/B-optimised against a
positive variant, and the HN audience has consistently rewarded posts that
lead with their worst result over the last decade. If we have a clean
arXiv preprint live and no senior endorsement in hand, 6b is the safest
high-upside pick.

Secondary fallback: **Candidate 6a** (self-killing backtest) if the friend
test shows 6b confuses non-quant readers. The verb "killed" gives the
non-quant reader something to grab.

Tertiary: **Candidate 6c (trimmed)** if the metascience angle has been
heavily weighted in pre-launch outreach.

### Updated decision matrix (supersedes the §"Decision matrix" table above when #6 is in play)

| Backtest outcome | Senior endorsement in hand? | Primary title | Backup title |
|---|---|---|---|
| Strong (lift ≥ +0.5) | yes or no | Candidate 2 | Candidate 4 |
| Weak (+0.1 to +0.4) | yes | Candidate 1 | Candidate 4 |
| Weak (+0.1 to +0.4) | no | Candidate 4 | **Candidate 6b** |
| Null (lift ≤ +0.1) | yes (≥1 named endorser) | Candidate 1 or 3 | **Candidate 6b** |
| Null (lift ≤ +0.1) | no | **Candidate 6b** | Candidate 5 |
| Tie-breaker / no fresh backtest | — | **Candidate 6b** (unforgeable signal) | Candidate 4 |
