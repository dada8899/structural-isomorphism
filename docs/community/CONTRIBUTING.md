# Contributing to structural-isomorphism

Thanks for your interest. This project welcomes contributions from researchers, engineers, students, and anyone curious about cross-domain validation of self-organized criticality. Whether you want to file a one-line typo fix, add a new dataset, or co-author a paper — there's a path for you here.

## Code of Conduct

This project adheres to the [Contributor Covenant v2.1](CODE_OF_CONDUCT.md). By participating you agree to uphold its terms. Reports go to the contact listed in `CODE_OF_CONDUCT.md`.

## TL;DR — your first PR in 10 minutes

```bash
# 1. Fork and clone
git clone git@github.com:<your-username>/structural-isomorphism.git
cd structural-isomorphism

# 2. Set up dev environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,tutorials]"
pre-commit install              # installs lint + format + DCO hooks

# 3. Make a topic branch
git checkout -b feat/your-short-desc

# 4. Hack. Run the fast sanity suite continuously
pytest v4/tests/sanity -m sanity -v

# 5. Before pushing: run full lint + tests
pre-commit run --all-files
pytest v4/tests/sanity -v
pytest v4/tests/integration -v

# 6. Commit with sign-off (DCO required)
git commit -sm "feat(scope): one-line summary"

# 7. Push and open PR against main
git push -u origin feat/your-short-desc
gh pr create --fill
```

That's it. A maintainer will review within the SLA below.

## Ways to contribute

- **Bug reports** — [GitHub Issues](https://github.com/dada8899/structural-isomorphism/issues) with the `bug` template
- **Feature suggestions** — Issues with the `enhancement` template
- **New validation phases** — Propose adding a new domain (e.g. social-network cascades, climate-tipping events) via an issue first; discuss methodology before coding
- **Documentation, tutorials, translations** — these are first-class contributions, not second-class
- **Pull requests** — bug fixes, features, refactors
- **Replication studies** — re-run existing phases on new datasets; we will give you co-authorship credit
- **Adversarial test cases** — propose pre-registered exponent bands designed to falsify our claims
- **Code review** — yes, you can review PRs as a non-maintainer; we welcome it

## Setup details

### System requirements

- Python 3.11+
- ~ 2 GB free disk space for full dataset checkout
- (Optional) `git-lfs` if you want to pull large binary fixtures locally

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,tutorials]"
```

The `dev` extra includes: `pytest`, `ruff`, `black`, `mypy`, `pre-commit`, `mkdocs`, `mkdocs-material`.
The `tutorials` extra adds: `jupyter`, `ipywidgets`, `matplotlib`, `seaborn`.

### Pre-commit hooks

```bash
pre-commit install
```

This installs hooks that run on every `git commit`:

- `ruff` for linting
- `black` for formatting
- `mypy` for type checking (strict on new code; loose on legacy)
- DCO sign-off check
- End-of-file fixer, trailing-whitespace trim
- YAML / JSON / TOML syntax check

You can run hooks manually any time: `pre-commit run --all-files`.

### Test commands

| Command | What it runs | Time |
|---|---|---|
| `pytest v4/tests/sanity -m sanity -v` | Fast unit tests | < 30 s |
| `pytest v4/tests/integration -v` | Integration tests (DB, HTTP, file IO) | ~ 2 min |
| `pytest v4/tests/e2e -v` | End-to-end tests (Playwright; needs `npx playwright install`) | ~ 5 min |
| `make test-all` | Full suite (213 tests at last count) | ~ 8 min |
| `make lint` | ruff + black --check + mypy | < 30 s |
| `make docs` | mkdocs build (verifies docs render) | ~ 30 s |

## Pull request workflow

1. **Open an issue first** for any non-trivial change (anything beyond typo / one-line bugfix). This lets us discuss approach before you spend hours on it.
2. **Fork** the repository.
3. **Branch** off `main`: `git checkout -b <type>/<short-desc>` (e.g. `feat/add-co2-flux-validation`).
4. **Write your change** with appropriate tests (see § Test requirements).
5. **Update docs** if applicable (see § Documentation requirement).
6. **Run `pre-commit run --all-files`** locally — green before pushing.
7. **Run the relevant test suite** locally — green before pushing.
8. **Commit** with [Conventional Commits](https://www.conventionalcommits.org/) style + DCO sign-off:
   - `git commit -sm "feat(soc-pipeline): add CO2-flux SOC validator"`
9. **Push** and **open a PR** against `main`. Fill out the PR template completely.
10. **Address review feedback** promptly — usually within the same week. If you go silent for > 30 days, we may close the PR (you can always reopen).
11. **Squash-merge** is our default (one logical change per PR → one commit in main).

## Code style

### Python

- **PEP 8** enforced by `ruff` + `black` (configured in `pyproject.toml`).
- **Type hints** strongly encouraged on all new code; required on public APIs.
- **Docstrings** in NumPy or Google style; required on every public function, class, and module.
- **One semantic change per commit**; one feature per PR.

### Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), e.g.:

- `feat(soc-pipeline): ...`
- `fix(d1): ...`
- `docs: ...`
- `test: ...`
- `chore(ci): ...`
- `refactor(v4-validation): ...`

Common scopes: `soc-pipeline`, `v4-validation`, `d1`, `web`, `docs`, `ci`, `infra`, `tests`.

### Markdown

- `YYYY-MM-DD` date format
- Headings ATX-style (`#`, not underline)
- Code fences with language tag (` ```python `, not bare ` ``` `)

## Test requirements

Any change with **logic** needs all three layers, per project policy:

### 1. Unit tests (`v4/tests/sanity`)

- 3 - 5 cases per core function: normal + edge + error
- Heuristic functions (classifiers, exponent estimators): **20+ cases including adversarial inputs**
- Must run in < 30 s total
- Required for any change that touches:
  - Pipeline algorithms (`v4/soc_pipeline/`)
  - Statistical estimators (`v4/estimators/`)
  - Schema / config validators
  - Pure utility functions

### 2. Integration tests (`v4/tests/integration`)

- For each API endpoint: success + 404 + bad-input + permission-denied
- Schema changes require migration test + version assertion
- Config layer (CORS, middleware, env-var bridges) explicitly tested via in-process clients
- Required for any change to:
  - HTTP API
  - Database schema or queries
  - Multi-module interactions

### 3. End-to-end / real-environment (`v4/tests/e2e`)

- Browser-driven (Playwright) for web changes
- Real DB (run `python -m db.migrate` against test DB first)
- At least one happy path + one error path
- Required for changes to:
  - Any user-visible feature
  - Web app (`web/`)
  - Multi-service orchestration

If your change is **pure visual polish** (color, spacing, font), unit + integration aren't useful — but e2e screenshot diffs still apply.

**Failing any required layer = PR not ready for merge.**

## Documentation requirement

- **New public API** (function, class, CLI subcommand, HTTP endpoint) needs:
  - Docstring or schema with usage example
  - mkdocs page under `docs/` (or update to existing page)
  - Entry in `docs/api.md` index
- **New dataset or validation phase** needs:
  - Provenance + license note in `docs/data/`
  - SHA-pinned manifest entry
  - At least 1 example notebook in `docs/tutorials/`
- **Behavior changes** in existing API: changelog entry + migration note if breaking
- **Breaking changes**: deprecation period of ≥ 1 minor release before removal

PRs that add code without docs will be asked to add docs before merge. PRs that add docs without code are very welcome and have an expedited review SLA.

## Review SLA

We commit to:

| Reviewer | First-response SLA | Final-decision SLA |
|---|---|---|
| BDFL | 7 calendar days | 21 calendar days |
| Council member (once council exists per GOVERNANCE.md) | 14 calendar days | 30 calendar days |
| Volunteer reviewer | best-effort, no formal SLA | best-effort |

Definitions:

- **First response** = an actual review with comments, not just an acknowledgement. A "looks good, will read this week" comment does *not* count.
- **Final decision** = merge, request-changes-with-specific-list, or close-with-reason. A PR may legitimately go back and forth before final decision; the clock pauses when the ball is in the contributor's court.

### What to do if we miss the SLA

1. **Day SLA + 0**: ping `@dada8899` on the PR with one polite line ("checking in on review SLA").
2. **Day SLA + 3**: if no response, post in Discord `#contributors-only` (or `#general` if you're not yet `@contributor`).
3. **Day SLA + 7**: open a meta-issue with label `governance` titled "SLA miss: PR #N". This is *not* punitive — it's a public signal that the maintainer is overloaded, and it lets the council reallocate review work.

We track SLA hits/misses in a quarterly governance report (first one due 2026-Q4 once the council is seated per GOVERNANCE.md § 3).

### Urgent security fixes

Per `.github/SECURITY.md`, **do not open a public PR**. Email instead. We aim for 14-day acknowledgement and 90-day fix.

## Maintainer council recruitment

The current project is BDFL-only (see GOVERNANCE.md § 1). The 3-member Maintainer Council forms when triggered per GOVERNANCE.md § 3 (5 external PRs in a quarter, first arXiv acceptance, or 2027-01-01 — whichever first).

If you're considering self-nominating or being nominated, the council selection criteria from GOVERNANCE.md § 5.3 are:

1. **Demonstrable contribution**: ≥ 3 merged PRs OR a documented dataset contribution OR co-authorship on a paper that uses the pipeline.
2. **Diversity**: no two council members from the same lab/employer.
3. **Time commitment**: stated commitment to a 12-month term + ~ 4 hours/week of project work.

Additional **soft signals** we look for (not gating, but they tip a close call):

- **Methodological rigor**: at least one PR that surfaces or fixes a *methodological* bug (false-positive in EWS, mis-applied power-law fit, pre-registration violation), not just a typo or perf win.
- **Mentorship behavior**: shown up in `#newcomers` or on good-first-issues to help newcomers, with patience and without condescension.
- **Adversarial honesty**: at least one public comment where you said "I was wrong about X" or "my earlier review was off". The project lives or dies by negative-result transparency; council members must model this.
- **Code of Conduct posture**: no open or recent COC complaints; visible alignment with Contributor Covenant v2.1 spirit.
- **Cross-domain breadth or depth**: either breadth (you can speak credibly to at least 3 of: SOC theory, statistics, neuroscience, climate, finance, networks, NLP) or deep expertise in one of the core areas.

**Anti-signals** that disqualify a nomination:

- History of unattributed paper / code reuse
- Active legal dispute with the project's IP
- Pattern of dismissive or hostile review comments (even if technically correct)
- Inability to commit ~4 h/week — we'd rather decline than over-extend you

### Becoming a council member is not the only path to influence

The project explicitly recognizes three trajectories with real authority:

1. **Council member** — formal voting authority per GOVERNANCE.md § 6
2. **Domain steward** (informal): you "own" a specific area (e.g. neural-avalanche validation, EWS methodology, frontend). The council defers to you on PRs in your area absent strong reason. This is granted by reputation, not by vote.
3. **Verified researcher** (`@verified-researcher` Discord role): post-ORCID verification, you get write access to `#pre-registrations` and `#company-deep-dives` and can co-sign other researchers' pre-registrations.

## New-contributor first-week onboarding path

You just landed in the project and want to ship something useful within seven days. Here's the recommended path. None of it is mandatory — but each step compresses time-to-impact.

### Day 1 (1 hour) — orientation

- [ ] Read `README.md` end to end.
- [ ] Read this file (CONTRIBUTING.md), even just skim.
- [ ] Read `CODE_OF_CONDUCT.md` (it's short).
- [ ] Skim `GOVERNANCE.md` § 1–3 — you don't need to know the rest yet.
- [ ] Join the Discord (invite in README). Post one line in `#introductions`.

### Day 2 (2 hours) — environment

- [ ] Fork the repo and clone your fork.
- [ ] Set up the dev environment per `## Setup details` above. Confirm `pytest v4/tests/sanity -m sanity -v` is green.
- [ ] Skim the `docs/getting-started.md` walk-through end to end. Run the example notebook in `docs/tutorials/` to make sure your environment is real.
- [ ] If anything broke during setup, file an issue using the `bug` template — this is itself a useful contribution.

### Day 3–4 (~ 3 hours) — pick a good-first-issue

- [ ] Open `docs/community/good-first-issues-active-2026-05-24.md` and scan the table.
- [ ] Pick a ★ (under 4 h, no specialist knowledge) issue that touches an area you're curious about.
- [ ] Comment on the live GH issue: "I'd like to take this; estimated to start within 24 h."
- [ ] If you're new to OSS entirely, add: "First-time contributor — would value a mentor walk-through." A maintainer will pair with you.

### Day 5 (~ 4 hours) — implement

- [ ] Branch: `git checkout -b <type>/<short-desc>`.
- [ ] Implement the change. Run the relevant test layer (see § Test requirements).
- [ ] Run `pre-commit run --all-files`.
- [ ] If you're stuck for more than 30 minutes, ask in `#newcomers` on Discord — that's literally what the channel is for. No shame.

### Day 6 (~ 1 hour) — open PR

- [ ] `git commit -sm "<conventional commit>"` (with DCO `-s` sign-off).
- [ ] `git push -u origin <branch>`.
- [ ] `gh pr create --fill`. Make sure the PR description references the issue (`Closes #N`).
- [ ] Self-review your own diff once before requesting review. Catch the silly stuff.

### Day 7 (~ 30 min) — respond + reflect

- [ ] Address review feedback (if it landed within the SLA window).
- [ ] Reply with a "thanks for the review" line on the merged PR.
- [ ] Add yourself to `CONTRIBUTORS.md` (if it exists by then; otherwise the next contributor will create it).
- [ ] In `#introductions` on Discord, post a one-line summary of what you shipped. This is how the community learns who you are.

### Common stumbling blocks

| Stumble | Fix |
|---|---|
| "I broke a test I don't understand" | Comment on the issue with the failing output; a maintainer pairs |
| "I don't know if my approach is right" | Open a *draft* PR early and ask for direction comments |
| "Pre-commit is yelling at me" | Run `pre-commit run --all-files` until green; ask in `#newcomers` if stuck |
| "I can't get the dataset to download" | LFS-vs-not-LFS confusion is common; see `docs/data/` README |
| "My PR has been sitting for > SLA days" | Ping `@dada8899` once on the PR; if still nothing, escalate per § Review SLA |

### Beyond week one

- After 1 merged PR: drop into `#contributors-only` (auto-granted via the Discord GitHub bot).
- After 3 merged PRs: you meet the council nomination floor per GOVERNANCE.md § 5.3.
- After 5 merged PRs OR a major feature: you're eligible for `@verified-researcher` role on Discord, separate from authorship considerations.

## Translation & multilingual docs

The README is the project's most-translated surface. Long-form docs (mkdocs site, tutorials, papers) are English-first but actively welcome translations.

### Current scope

- **README.md** — English (canonical) + Mandarin Chinese (in progress, issue #155)
- **docs/index.md** — English only for now
- **Newsletters** — English only
- **Tutorials** — English (canonical); translations welcomed

### Translation workflow

1. **Open a tracking issue** with label `i18n` titled `[i18n] <language> translation of <file>`. Existing example: #155.
2. **Branch off the English canonical version** at a known commit SHA. Note the SHA in your PR description (this is what your translation is *based on*).
3. **Place translated files under a language-suffixed path**:
   - `README.md` → `README.zh-CN.md` (or `.zh-TW`, `.ja`, `.de`, etc., using BCP-47 codes)
   - `docs/index.md` → `docs/index.zh-CN.md`
   - For tutorials in subdirs: `docs/tutorials/foo.md` → `docs/tutorials/foo.zh-CN.md`
4. **Do NOT translate** without leaving a header at the top:
   ```markdown
   <!--
   Translation of README.md @ SHA <abc123>
   Translator: <your-handle>
   Last sync with English original: <YYYY-MM-DD>
   -->
   ```
5. **Add a language link footer** in the canonical English file:
   ```markdown
   ## Translations
   - [简体中文](README.zh-CN.md) (synced 2026-05-24)
   ```

### Sync discipline (avoiding stale translations)

This is where translations break in most projects. We enforce a light, automated check.

- **English is the source of truth**. When the canonical file changes substantively (not a typo), the change author is *not* expected to also update translations — but the CI **must flag the staleness**.
- **Staleness check**: a CI job compares the `<!-- Last sync with English original: ... -->` SHA against `git log` on the English file. If the English file has changed since that SHA, the translated file is labeled `stale-translation` automatically.
- **Stale doesn't mean broken**: the translated file stays published with a banner "⚠️ This translation is X commits behind the English version. See changes here."
- **Re-sync PRs are first-class contributions**. A PR titled `i18n(zh-CN): resync README to SHA <new>` is welcomed and reviewed within the normal SLA.

### Translator commitment expectations

We do **not** require translators to maintain their translation forever. But:

- If you open a `[i18n]` PR, please commit to **at least one re-sync within 60 days** of merge.
- After that, the translation is the community's; anyone can submit re-sync PRs.
- If a translation is > 6 months stale and no one re-syncs it, the maintainers will add a `staleness warning > 6mo` notice at the top of the file but will not unpublish it (stale translation > no translation, by a wide margin, for non-critical docs).

### Critical docs require synchronized translation

For three files specifically, a substantive change to the English version **blocks merge** until at least Mandarin (the only currently-supported translation) is also updated, or the translation is explicitly marked deprecated:

1. `CODE_OF_CONDUCT.md` — legal/normative
2. `SECURITY.md` — security-critical
3. `.github/ISSUE_TEMPLATE/coc-report.md` — used in COC reporting

For all other files, async re-sync per the workflow above.

### Future languages

We will accept any translation contribution. Priority order based on current contributor / user signal:

1. Mandarin Chinese (`zh-CN`) — issue #155 in flight
2. Spanish (`es`) — opportunistic
3. Japanese (`ja`) — opportunistic
4. German (`de`) — opportunistic

Open an issue with the `i18n` label to start any of these.

## Good first issues + mentorship

- Browse [good-first-issue](https://github.com/dada8899/structural-isomorphism/labels/good-first-issue) labeled issues. Each has:
  - Clear brief
  - Acceptance criteria
  - Effort estimate (S / M / L)
  - Suggested mentor (maintainer who's offered to help)
- Join the project Discord (invite in README → `#good-first-issues` channel) for synchronous help.
- We hold office hours every fortnight (calendar in Discord); bring questions in any state of half-bakedness.

If you've never contributed to OSS before and you want a guided first PR, comment on a good-first-issue saying so — a mentor will walk you through fork → PR step by step.

## Reporting research / methodological issues

We treat methodological concerns as **top priority**, above performance or feature work.

1. Open an issue with the `research` label
2. Cite specific files/lines and the relevant literature (DOIs preferred)
3. Describe what you think is wrong + what the correct approach is
4. We aim to respond within 7 days (often same day if @dada8899 is online)

If you are submitting an adversarial replication or counter-claim, see `docs/pre-registrations.md` for the pre-registration template.

## Releases & versioning

- SemVer for `packages/*`
- Releases tagged `vX.Y.Z` on `main`
- Release branches: `release/X.Y`
- Release notes in `CHANGELOG.md` and on GitHub Releases
- Datasets versioned independently with content-addressed SHA + Zenodo DOI per major release

## Sponsorship & funding disclosures

If your contribution is funded (grant, employer time, etc.), please disclose in the PR description. We do not require this for individual unpaid contributors. See `GOVERNANCE.md` § 10 for the full COI framework.

## Questions

- General questions: [GitHub Discussions](https://github.com/dada8899/structural-isomorphism/discussions)
- Real-time chat: Discord (invite in README)
- Maintainer contact: see GOVERNANCE.md § 14
- Security: `.github/SECURITY.md`

Thanks for helping us build something useful.
