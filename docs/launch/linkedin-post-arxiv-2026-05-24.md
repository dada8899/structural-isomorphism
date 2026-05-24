# LinkedIn post — arXiv launch — 2026-05-24

**Posted**: arXiv-day, ~10:00 PT (after the Twitter thread, before HN evening NA).
**Account**: founder's primary LinkedIn (NOT a brand-new project page — LinkedIn algo punishes cold pages).
**Format**: long-form post, ~500 words, with one inline media + one CTA.
**Audience**: ex-colleagues, recruiters, senior researchers, analysts. **Different
voice than Twitter** — less self-aware, more "here is what I built and what
I learned", LinkedIn professional norms.

---

## Post body

A note on a project I have been working on for the past nine months. The
preprint went live on arXiv today.

The question is older than I am: do systems from radically different
scientific domains — financial contagion, neural avalanches, wildfires,
DeFi liquidations, citation cascades — share the same underlying
mathematical structure? Statistical physics has a 50-year-old idea called
universality classes that says yes, in principle. Whether the principle
holds when you apply one unchanged statistical pipeline to messy
empirical data, no per-domain tuning, is a much harder question.

We built the test honestly. One frozen 339-line Python module —
implementing Clauset–Shalizi–Newman 2009 — runs against every system.
Same function, same hyperparameters, same diagnostics. Before any data
is fetched, we commit a YAML file declaring the expected exponent band
for that system, sourced from the published literature. The git
timestamp on that commit is the audit trail.

The result so far: 17 pre-registered systems, 13 land in-band, 4 do not.
The 4 failures are the most important number on the project page. They
are 2023 CVE high-severity disclosure cascades, NYC FDNY 2023 fire
dispatch unit sizes, r/wallstreetbets post cascades, and a commercial
S&P 500 trading-signal fork run walk-forward 2020–2024. We published
the negative verdicts in the same paper as the positives.

I keep coming back to this principle: a framework that never rejects is
not measuring anything. The strongest signal a methodology can send is
that it can fail when reality fails. 13 positives + 4 published failures
from a single pipeline is more credible than 17 positives from a
re-tunable one would have been.

The full preprint, code (MIT), and dataset (CC-BY-4.0, on Zenodo) are
linked below. I would especially welcome two kinds of reviewers:

(1) Domain experts who can spot a band assignment that looks post-hoc.
Every YAML has a `source_paper` field — propose a different paper's
band and we'll re-run the verdict.

(2) Methodology critics who can argue we should not have called
something a "pre-registration" without an external witness like OSF.
That critique is fair and the next replication round will dual-register.

Two live demos let you poke the methodology. The cross-domain search
sits at beta.structural.bytedance.city. A research-preview phase
classifier for 500 public companies — with source-quote provenance and
LLM prompt hash on every prediction — sits at phase.bytedance.city. It
is a research artifact, not a financial product; the disclaimer is on
every page.

For three years I have wanted to test whether cross-domain universality
is empirically real or post-hoc convenient. Today is the first day the
question is in public-evidence form. Curious to hear what readers find.

— Preprint: arXiv:ARXIV_ID_PENDING
— Repo (MIT): github.com/dada8899/structural-isomorphism
— Dataset (CC-BY-4.0): doi.org/10.5281/zenodo.19615170
— PyPI: `pip install structural-soc-pipeline`

#OpenScience #StatisticalPhysics #ComplexSystems #ReproducibleResearch #SelfOrganizedCriticality

---

## Media

Attach the 6-frame contact sheet (`site/demo-contact-sheet.png`) rather than
the GIF. LinkedIn auto-plays GIFs but the static contact sheet renders
cleaner in feed previews and on mobile.

## Engagement strategy

- First 60 minutes: reply to every substantive comment with a paper section
  reference. LinkedIn algo weighs first-hour engagement heavily for B2B-flavored
  posts.
- DO NOT reply with emojis or "thanks!" — that signals low-effort and tanks
  reach. Substantive reply OR no reply.
- After 24h: post a short follow-up *as a comment on the original post* (not as
  a new post) summarizing top 3 questions + answers. LinkedIn rewards "still
  alive" signals on long-form posts.
- After 72h: pull metrics (LinkedIn analytics → impressions, profile views,
  unique reactors) and write into the launch retro.

## What NOT to do on LinkedIn

- No "humble brag" framing ("I'm proud to announce..."). Direct opening.
- No emojis in body. Single emoji-free post lands cleaner in feed.
- No "fundraising" subtext. We are not raising; LinkedIn will surface this to
  recruiters and the line should be: senior IC publishing open methodology.
- No paywalled links. Everything is free / preprint / CC-BY.
- No multi-image carousel — they get fewer impressions than single-image posts
  for technical content (LinkedIn 2025 algo skew).

## Cross-promote

- Reshare from the @ScheffWUR / @V_Priesemann / @aaronclauset accounts is
  unlikely on LinkedIn (they tend to repost on X/Mastodon). Don't engineer
  resharing.
- The post should be visible to recruiter audiences too — there is a
  career-signaling secondary purpose to this post, and that's fine, as long
  as the primary signal is the methodology.

## Failure mode to avoid

LinkedIn occasionally compresses long-form posts behind a "see more" fold
after the first 3 lines. The first 3 lines of this post are:

> *"A note on a project I have been working on for the past nine months. The
> preprint went live on arXiv today.*
> *The question is older than I am: do systems from radically different
> scientific domains — financial contagion, neural avalanches, wildfires,*"

That's intentionally a complete first thought + hook before the fold. If
LinkedIn tightens the fold to first 2 lines, swap the third line to put the
"13 pass, 4 fail" headline earlier. Check live before pinning.
