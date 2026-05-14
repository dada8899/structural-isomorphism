# Community launch drafts — INDEX

Drafts prepared by Wave 9 sub-agent D (2026-05-15). All artifacts below are **drafts not yet sent**. They are checked into the repo as version-controlled launch material; the send-out is gated on a final human review pass plus the arXiv submission landing (placeholders in each draft point at "arXiv pending" which must be replaced with the real arXiv ID before transmission).

## Scheduling rationale

The schedule below sequences channels so that signal compounds rather than competes. HN goes first because it tends to drive the largest single-day spike in inbound traffic and you want the most polished, methodology-forward framing to lead. Twitter posts in parallel with HN morning because the two audiences overlap heavily and X amplification often piggybacks on HN front-page momentum. Mastodon (fediscience.org) goes the same afternoon in the European-scientist evening window — Mastodon has slower decay than HN/X, so timing is less critical and a few hours stagger reduces "spam-everywhere" perception. Reddit waits T+1 (Wednesday) so the HN discussion can settle and any follow-up corrections land in the Reddit thread rather than getting buried under HN comment churn. Wednesday mid-morning US is the peak engagement window for both `/r/Physics` and `/r/datascience`. Senior researcher outreach staggers across two weeks at T+3 / T+5 / T+7 / T+10 / T+14 — sending five cold emails to senior researchers in the same week would (a) look like a blast and (b) make it harder to fold any feedback from earlier replies into later emails. Plenz and Priesemann go first because the neural sub-paper is the part most in need of a senior eye; Scheffer and Clauset middle because the D1 EWS and reject-aware framings benefit from arXiv discussion settling; Sornette last because his feedback is most likely to be on a sub-paper rather than the unified preprint.

## Send schedule

| Channel | Time (relative to launch) | Best window | Why this slot |
|---|---|---|---|
| HackerNews "Show HN" | T+0 (launch day) | Tuesday 06:00–09:00 PT (09:00–12:00 ET) | HN front-page lift is highest when posts land just before US East Coast morning peak |
| Twitter / X thread | T+0 (launch day) | 09:00 PT same morning | Coincides with HN spike; X engagement peak is 09:00 PT on weekdays |
| Mastodon (fediscience.org) | T+0 (launch day) | 14:00–17:00 CET (European-scientist evening) | fediscience.org audience is European-skewed scientists; afternoon CET is their evening read time |
| Reddit `/r/Physics` cross-post | T+1 (day after) | Wednesday 10:00 ET | Peak engagement window for `/r/Physics`; gives HN discussion 24h to settle |
| Reddit `/r/datascience` cross-post | T+1 (day after) | Wednesday 10:00 ET | Peak engagement window for `/r/datascience`; co-posted with `/r/Physics` |
| Senior outreach — Plenz | T+3 | Friday morning ET | Neural sub-paper feedback is highest-priority; Plenz first |
| Senior outreach — Priesemann | T+5 | Tuesday morning CET (Göttingen) | Priesemann second; sub-critical reverberation concern is methodologically adjacent to Plenz |
| Senior outreach — Scheffer | T+7 | Wednesday morning CET (Wageningen) | Scheffer mid-week; D1 EWS framing has had time to absorb any early Plenz/Priesemann feedback |
| Senior outreach — Clauset | T+10 | Friday morning MT (Boulder) | Clauset late-first-week; reject-aware framing benefits from arXiv discussion settling |
| Senior outreach — Sornette | T+14 | Monday morning CST (Shenzhen) / Friday morning evening CET | Sornette last; finance and dragon-king feedback is on a sub-paper and is least time-critical |

## Drafts

| # | Channel | File | Status | Word count target |
|---|---|---|---|---|
| 1 | HackerNews | [`hn-launch-2026-05-15.md`](hn-launch-2026-05-15.md) | Draft v1 | ~800 |
| 2 | Twitter / X (7-tweet thread) | [`twitter-thread-2026-05-15.md`](twitter-thread-2026-05-15.md) | Draft v1, each tweet ≤ 280 chars validated | ~270 |
| 3 | Mastodon (fediscience.org) | [`mastodon-2026-05-15.md`](mastodon-2026-05-15.md) | Draft v1 | ~600 |
| 4 | Reddit (`/r/Physics` + `/r/datascience`) | [`reddit-2026-05-15.md`](reddit-2026-05-15.md) | Draft v1, two cross-posts | ~1100 (both combined) |
| 5 | Senior outreach (5 emails) | [`senior-outreach-2026-05-15.md`](senior-outreach-2026-05-15.md) | Draft v1, 5 recipients | ~1500 (all five combined) |

## Pre-send checklist

Before any of the above goes out, the human reviewer needs to confirm:

- [ ] arXiv submission has landed; replace every "arXiv pending" placeholder with the real arXiv ID
- [ ] Zenodo DOI link is live (https://doi.org/10.5281/zenodo.19615170) — confirmed accessible from a non-author IP
- [ ] beta.structural.bytedance.city and phase.bytedance.city are live and not 5xx-ing at launch time
- [ ] PyPI packages (`structural-soc-pipeline`, `structural-critics`, `structural-taxonomy`) are installable from a clean venv
- [ ] CITATION.cff renders correctly via GitHub's "Cite this repository" button
- [ ] Repo README badges all load (not 404)
- [ ] HN account has sufficient karma for the post not to be auto-flagged
- [ ] Twitter / Mastodon accounts are warmed up (not zero-history brand-new accounts)
- [ ] Senior outreach emails: double-check current institutional affiliations (Sornette in particular has moved institutions)
- [ ] Each senior outreach email: confirm the cited paper is real and the cited result is accurately characterized — these are well-known papers but the exact claim attribution should be re-read once before transmission

## Recipient list summary — senior outreach (T+3 to T+14)

| Order | Name | Affiliation | Cited paper(s) | Key ask |
|---|---|---|---|---|
| 1 | Dietmar Plenz | NIMH (NIH, Bethesda) | Beggs & Plenz 2003 *J. Neurosci.* (neuronal avalanches in cortical slice cultures) | 30-min call + possible co-authorship on neural sub-paper |
| 2 | Viola Priesemann | MPI Dynamics and Self-Organization, Göttingen | Wilting & Priesemann 2018 *Nat. Commun.* (sub-critical reverberation vs critical regime + branching-ratio diagnostic) | 30-min call + possible co-authorship on neural sub-paper |
| 3 | Marten Scheffer | Wageningen University | Scheffer et al. 2009 *Nature* (early-warning signals for critical transitions) | 30-min call + possible co-authorship on D1 block-bootstrap EWS paper |
| 4 | Aaron Clauset | CU Boulder, Dept of CS | Clauset–Shalizi–Newman 2009 *SIAM Review* (power-law distributions in empirical data) + Broido & Clauset 2019 *Nat. Commun.* (scale-free networks are rare) | 30-min call + possible co-authorship on future dataset-curation paper |
| 5 | Didier Sornette | SUSTech (formerly ETH Zürich) | Sornette & Ouillon 2012 *EPJ Special Topics* (dragon-kings outlier diagnostic) | 30-min call + possible co-authorship on finance + power-grid sub-paper |

All five emails use the same structure: (1) ~80-word self-introduction + project framing, (2) cite the specific paper of theirs we built on and the specific concern we want their guidance on, (3) specific ask (30 min call + possible co-authorship + zero-cost written critique fallback), (4) sign-off with arXiv + Zenodo DOI + repo links.
