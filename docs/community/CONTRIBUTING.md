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

| Reviewer | First-response SLA |
|---|---|
| BDFL | 7 calendar days |
| Council member (once council exists per GOVERNANCE.md) | 14 calendar days |
| Volunteer reviewer | best-effort, no formal SLA |

"First response" = an actual review with comments, not just an acknowledgement. If we miss the SLA on your PR, ping `@dada8899` on the PR — sometimes notifications get lost.

For **urgent security fixes**: per `.github/SECURITY.md`, do not open a public PR. Email instead. We aim for 14-day acknowledgement and 90-day fix.

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
