# Good-first-issue index

> Maintainer-curated entry points for new contributors. Each issue below has a paired markdown draft in this directory and a live GitHub issue. Pair with the public CONTRIBUTING.md.
>
> Last updated: 2026-05-15
> Source: Wave 9 sub-agent A, per W7-C §7.

## Categories

- **data** — new empirical dataset or universality-class YAML
- **tests** — unit / integration / coverage uplift
- **docs** — typo / link fix / deprecated reference cleanup
- **tutorial** — new notebook / pedagogy doc
- **performance** — profile + speed up
- **i18n** — translation
- **web** — frontend / backend UI work

## Difficulty legend

- ★ — under 4 h, no specialist domain knowledge needed
- ★★ — 4–10 h, intermediate skills (pandas / numpy / pytest-asyncio / vanilla DOM)
- ★★★ — 10 h+, requires domain familiarity (statistics, disordered-systems physics, profiling craft)

## Table

| # | Title | Area | Difficulty | Status | GH Issue |
|---|---|---|---|---|---|
| 001 | [Add solar-wind speed-burst dataset with pre-registered SOC band](001-dataset-solar-wind-bursts.md) | data | ★★ | open | [#141](https://github.com/dada8899/structural-isomorphism/issues/141) |
| 002 | [Add Twitter / X retweet-cascade inter-arrival dataset](002-dataset-twitter-cascade-arrivals.md) | data | ★★ | open | [#142](https://github.com/dada8899/structural-isomorphism/issues/142) |
| 003 | [Add GitHub issue resolution-time dataset (heavy-tail / SOC test)](003-dataset-github-issue-resolution-times.md) | data | ★ to ★★ | open | [#144](https://github.com/dada8899/structural-isomorphism/issues/144) |
| 004 | [Add `fractional_brownian_crossings` universality class YAML](004-class-yaml-fractional-brownian-crossings.md) | data | ★★ | open | [#145](https://github.com/dada8899/structural-isomorphism/issues/145) |
| 005 | [Add `anderson_localization_transition` universality class YAML](005-class-yaml-anderson-localization.md) | data | ★★★ | open | [#146](https://github.com/dada8899/structural-isomorphism/issues/146) |
| 006 | [Lift coverage of `web/backend/api/ask.py` above 80 %](006-test-coverage-ask-api.md) | tests | ★★ | open | [#147](https://github.com/dada8899/structural-isomorphism/issues/147) |
| 007 | [Add coverage for `v4/lib/multitest_correction.py`](007-test-coverage-multitest-correction.md) | tests | ★★ | open | [#148](https://github.com/dada8899/structural-isomorphism/issues/148) |
| 008 | [Improve test coverage of `soc_pipeline.pandas_accessor`](008-test-coverage-pandas-accessor.md) | tests | ★ | open | [#149](https://github.com/dada8899/structural-isomorphism/issues/149) |
| 009 | [Fix deprecated `v4.lib.soc_pipeline` references in tutorials and docs](009-docs-fix-deprecated-cli-references.md) | docs | ★ | open | [#150](https://github.com/dada8899/structural-isomorphism/issues/150) |
| 010 | [Audit and fix broken internal links in MkDocs site](010-docs-fix-broken-mkdocs-links.md) | docs | ★ | open | [#151](https://github.com/dada8899/structural-isomorphism/issues/151) |
| 011 | [New tutorial — designing synthetic null controls](011-tutorial-synthetic-null-design.md) | tutorial | ★★ | open | [#152](https://github.com/dada8899/structural-isomorphism/issues/152) |
| 012 | [New tutorial — writing a pre-registration](012-tutorial-pre-registration-workflow.md) | tutorial | ★ | open | [#153](https://github.com/dada8899/structural-isomorphism/issues/153) |
| 013 | [Speed up Clauset `xmin` scan in `fit_clauset_powerlaw`](013-perf-clauset-xmin-scan.md) | performance | ★★★ | open | [#154](https://github.com/dada8899/structural-isomorphism/issues/154) |
| 014 | [Add Mandarin Chinese translation of the README](014-i18n-mandarin-readme.md) | i18n | ★ | open | [#155](https://github.com/dada8899/structural-isomorphism/issues/155) |
| 015 | [Add dark-mode toggle with `localStorage` persistence on beta search page](015-web-dark-mode-persistence.md) | web | ★★ | open | [#156](https://github.com/dada8899/structural-isomorphism/issues/156) |

## Difficulty distribution

- ★ : 6 issues (003, 008, 009, 010, 012, 014)
- ★★ : 7 issues (001, 002, 004, 006, 007, 011, 015)
- ★★★ : 3 issues (005, 013, plus the dual-★ portion of 003)

## How to claim an issue

1. Comment on the live GH issue: "I'd like to take this".
2. Wait for a maintainer to assign (usually < 48 h).
3. Open a draft PR within 1 week of being assigned, or the issue is freed up.
4. For coding issues, include a `pytest` run in the PR description.
5. For data issues, the pre-registration commit must precede the verdict commit.

## Maintainer notes

- Every issue has labels: `good first issue`, `help wanted`, plus area-specific (`data`, `tests`, `docs`, etc.).
- 1:1 mentorship offered: ping `@dada8899` on the issue and we'll arrange one async exchange per week.
- If an issue stays unassigned for 30 days, re-broadcast on the next monthly community update.
