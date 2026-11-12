# Active good-first-issues — snapshot 2026-05-24

> **Status**: PUBLIC. All 15 drafts in `docs/community/good-first-issues/` have been filed as live GitHub issues. This page is the single tracking surface — links here, drafts there, issues on GitHub.
>
> **Source for P1 checklist item**: `docs/PUBLIC_READINESS_CHECKLIST.md` → P1 → "15 good-first-issue drafts converted to labeled GitHub issues" (✅ done).
>
> **Maintainer**: @dada8899 — open an issue or DM on Discord (link in README) for mentorship requests.
>
> **Last verified**: 2026-05-24 (all 15 issues confirmed OPEN with correct labels via `gh issue view`).

## Why this file exists

The drafts in `good-first-issues/` are the source-of-truth task specs (what / why / where / how to start / definition of done). The live GitHub issues are the contributor-facing entry points. This page bridges the two:

- One row per issue, with the live URL, difficulty, area, and effort estimate
- Status column (open / claimed / in-progress / merged)
- Refreshed on each monthly community update (next: 2026-06-15)

## Issue index

| # | Title | Area | Difficulty | Est. effort | Status | GH issue |
|---|---|---|---|---|---|---|
| 001 | Add solar-wind speed-burst dataset with pre-registered SOC band | data | ★★ | 4–8 h | open | [#141](https://github.com/dada8899/structural-isomorphism/issues/141) |
| 002 | Add Twitter / X retweet-cascade inter-arrival dataset | data | ★★ | 4–8 h | open | [#142](https://github.com/dada8899/structural-isomorphism/issues/142) |
| 003 | Add GitHub issue resolution-time dataset (heavy-tail / SOC test) | data | ★ → ★★ | 3–6 h | open | [#144](https://github.com/dada8899/structural-isomorphism/issues/144) |
| 004 | Add `fractional_brownian_crossings` universality class YAML | data | ★★ | 4–6 h | open | [#145](https://github.com/dada8899/structural-isomorphism/issues/145) |
| 005 | Add `anderson_localization_transition` universality class YAML | data | ★★★ | 10–15 h | open | [#146](https://github.com/dada8899/structural-isomorphism/issues/146) |
| 006 | Lift coverage of `web/backend/api/ask.py` above 80 % | tests | ★★ | 4–8 h | open | [#147](https://github.com/dada8899/structural-isomorphism/issues/147) |
| 007 | Add coverage for `v4/lib/multitest_correction.py` | tests | ★★ | 4–6 h | open | [#148](https://github.com/dada8899/structural-isomorphism/issues/148) |
| 008 | Improve test coverage of `soc_pipeline.pandas_accessor` | tests | ★ | 2–4 h | open | [#149](https://github.com/dada8899/structural-isomorphism/issues/149) |
| 009 | Fix deprecated `v4.lib.soc_pipeline` references in tutorials and docs | docs | ★ | 2–3 h | open | [#150](https://github.com/dada8899/structural-isomorphism/issues/150) |
| 010 | Audit and fix broken internal links in MkDocs site | docs | ★ | 2–3 h | open | [#151](https://github.com/dada8899/structural-isomorphism/issues/151) |
| 011 | New tutorial — designing synthetic null controls | tutorial | ★★ | 6–10 h | open | [#152](https://github.com/dada8899/structural-isomorphism/issues/152) |
| 012 | New tutorial — writing a pre-registration | tutorial | ★ | 3–5 h | open | [#153](https://github.com/dada8899/structural-isomorphism/issues/153) |
| 013 | Speed up Clauset `xmin` scan in `fit_clauset_powerlaw` | performance | ★★★ | 10–20 h | open | [#154](https://github.com/dada8899/structural-isomorphism/issues/154) |
| 014 | Add Mandarin Chinese translation of the README | i18n | ★ | 2–4 h | open | [#155](https://github.com/dada8899/structural-isomorphism/issues/155) |
| 015 | Add dark-mode toggle with `localStorage` persistence on beta search page | web | ★★ | 4–8 h | open | [#156](https://github.com/dada8899/structural-isomorphism/issues/156) |

## Difficulty legend

- **★** — under 4 h, no specialist domain knowledge needed
- **★★** — 4–10 h, intermediate skills (pandas / numpy / pytest-asyncio / vanilla DOM)
- **★★★** — 10 h+, requires domain familiarity (statistics, disordered-systems physics, profiling craft)

## Difficulty distribution

- ★ : 5 issues (008, 009, 010, 012, 014)
- ★★ : 7 issues (001, 002, 004, 006, 007, 011, 015)
- ★ → ★★ : 1 issue (003 — depends on whether contributor stops at minimal or extends)
- ★★★ : 2 issues (005, 013)

## Area distribution

- data: 5 (001, 002, 003, 004, 005)
- tests: 3 (006, 007, 008)
- docs: 2 (009, 010)
- tutorial: 2 (011, 012)
- performance: 1 (013)
- i18n: 1 (014)
- web: 1 (015)

## Labels in use (per issue)

Every issue carries: `good first issue` + `help wanted` + at least one area label. Verification (2026-05-24, via `gh issue view`):

| # | Labels |
|---|---|
| #141 | `help wanted`, `good first issue`, `replication`, `data` |
| #142 | `help wanted`, `good first issue`, `replication`, `data` |
| #144 | `help wanted`, `good first issue`, `replication`, `data` |
| #145 | `documentation`, `help wanted`, `good first issue`, `data` |
| #146 | `documentation`, `help wanted`, `good first issue`, `data` |
| #147 | `help wanted`, `good first issue`, `tests`, `web` |
| #148 | `help wanted`, `good first issue`, `tests` |
| #149 | `help wanted`, `good first issue`, `tests`, `pipeline` |
| #150 | `documentation`, `help wanted`, `good first issue`, `docs` |
| #151 | `documentation`, `help wanted`, `good first issue`, `docs` |
| #152 | `documentation`, `help wanted`, `good first issue`, `tutorial` |
| #153 | `documentation`, `help wanted`, `good first issue`, `tutorial` |
| #154 | `help wanted`, `good first issue`, `pipeline`, `performance` |
| #155 | `documentation`, `help wanted`, `good first issue`, `i18n` |
| #156 | `help wanted`, `good first issue`, `web` |

## How to claim

1. Comment on the live GH issue: "I'd like to take this".
2. Wait for a maintainer to assign (target: < 48 h; see CONTRIBUTING.md § Review SLA).
3. Open a draft PR within 1 week of being assigned, or the issue is freed up for someone else.
4. For coding issues, include a `pytest` run in the PR description.
5. For data issues, the **pre-registration commit must precede the verdict commit** (this is non-negotiable — see `docs/pre-registrations.md` for why).

## Mentorship

- Each ★ issue: maintainer-paired by default (DM `@dada8899` on the GH issue and one async exchange per week is offered).
- Each ★★★ issue: requires an initial design comment from the contributor before code; maintainer responds with shape feedback before work begins.
- Office hours: every other week, calendar in Discord (`#events`).

## Maintenance

- This file is updated on the **15th of each month** along with the monthly community update.
- If an issue is closed (merged or wontfix), the row is moved to a `## Closed` section at the bottom of this file, with the closing PR/commit linked.
- If an issue stays unassigned for 30+ days, it's re-broadcast in the next newsletter + Discord `#announcements`.

## Contact

- Mentorship pings: `@dada8899` on the live GH issue
- General questions: GitHub Discussions, or `#newcomers` on Discord
- Code of Conduct concerns: see `CODE_OF_CONDUCT.md`
