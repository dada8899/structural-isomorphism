# W7-B Engineering Value Roadmap — 18-Month Plan for Real Adoption

> Author: W7-B subagent (senior engineering strategist hat — production systems / ML infra / OSS community)
> Date: 2026-05-13
> Repo HEAD at start: `6138d2e` (post W6-E 213-test merge)
> Sibling artefacts: W7-A (research-future), W7-C (PM-future) — this doc focuses **only** on engineering value (libraries, infra, OSS, dev-experience).

---

## 0. Executive summary

**Premise.** structural-isomorphism today is a research project with one shipped product surface (D1 Phase Detector, 100 companies, sqlite, no auth). The repo is PRIVATE. There is no PyPI package, no docs site, no CI, no LICENSE in `setup.py` install path, no contributor pipeline. The 213-test suite (W6-E) and 339-line v4 pipeline are real engineering, but **none of it is reusable outside this repo today.**

**Bet.** The three pieces of code that have the highest leverage to become real OSS infrastructure (in priority order) are:

1. **`v4/lib/llm_guardrail.py`** (441 lines) — strict-JSON LLM caller with schema validation + retry + cost budget. This is a problem every LLM-powered project hits. Decoupling and publishing as `guarded-llm` could plausibly hit 10k+ PyPI downloads/month within 12 months.
2. **`v4/scripts/b3_ensemble.py` + B3 critic prompts** — generic LLM-ensemble-judge framework. Cross-vendor multi-reviewer consensus with versioned prompts. Publish as `cross-judge`.
3. **`v4/lib/soc_pipeline.py`** (339 lines) — Clauset MLE + KS + bootstrap + null model. Wraps `powerlaw` package with reproducibility-grade defaults. Publish as `soc-pipeline`.

The phase-detector product itself (D1) is a *consumer* of these libraries, not the library. Treating D1 as the only deliverable wastes the underlying infra.

**Headline plan.**
- Month 1: repo PUBLIC, LICENSE, CI green, docs scaffold.
- Month 2-3: `soc-pipeline 0.1.0` on PyPI, docs site live at `structural-isomorphism.github.io`.
- Month 4-6: `cross-judge 0.1.0` + `guarded-llm 0.1.0` on PyPI.
- Month 6-9: D1 scaled to 1000+ companies + auth + Stripe pilot.
- Month 9-12: first $1k MRR or pivot to OSS-only.
- Month 12-18: integration ecosystem (Jupyter widget, Pandas extension, VS Code preview) + 5 external contributors.

**Single highest-leverage move (next 30 days):** extract `v4/lib/llm_guardrail.py` into a standalone repo + PyPI package `guarded-llm`. Effort: ~3 engineering days. Impact: unlocks the largest addressable user base of any artefact in this codebase.

---

## 1. What does "engineering value" mean for this project?

Four flavours of engineering value, in increasing strategic depth:

| Flavour | Example in the wild | Test for "are we there?" |
|---|---|---|
| **Reusable library** | `scikit-learn`, `polars`, `dask` | non-author imports it in `requirements.txt` |
| **Production reference** | `huggingface/transformers` examples | non-author forks and adapts to their use case |
| **Community OSS** | `pytest`, `fastapi`, `langchain` | non-author opens PR that gets merged |
| **ML infra primitive** | `outlines`, `instructor`, `guidance` | other libraries depend on us in their requirements |

**Where structural-isomorphism is today:** 0/4. Repo is private. Even the author can't `pip install` it cleanly from a fresh venv.

**Where the codebase *could* land in 12 months, by piece:**

| Code asset | LoC | Reuse potential | Path |
|---|---|---|---|
| `v4/lib/llm_guardrail.py` | 441 | **High** — generic problem (strict-JSON LLM) | Extract → `guarded-llm` PyPI |
| `v4/scripts/b3_ensemble.py` + prompts | ~300 | **High** — cross-vendor LLM judging | Extract → `cross-judge` PyPI |
| `v4/lib/soc_pipeline.py` | 339 | **Medium** — niche but cited domain | Extract → `soc-pipeline` PyPI |
| `v4/lib/embedding_bridge.py` | 499 | **Low-Medium** — domain-specific TF-IDF/embed bridge | Hold in monorepo, doc as reference |
| `v4/lib/embedding_finetune.py` | 449 | **Low** — too coupled to KB data | Hold, doc as reference |
| `v4/cli.py` | 413 | **Low** — repo-internal dispatch | Hold |
| `v4/product/d1_phase_detector/*` | ~900 | **Product, not library** | Scale as SaaS pilot |
| `v4/tests/sanity/*` | 213 tests | **Reference value** as test patterns | Doc in mkdocs as "reproducibility tests" example |

The principle: **the most generic code in this repo is the most under-leveraged.** A strict-JSON LLM caller and an LLM-ensemble judge are problems every LLM team has, not problems unique to cross-domain structural isomorphism.

---

## 2. Honest engineering-quality audit (as of 2026-05-13)

### 2.1 Strengths

- **Test coverage is real.** W6-E shipped 213 tests across unit / integration / e2e with proper pytest markers and ~5s runtime.
- **CLI is clean.** `v4/cli.py` is a 413-line dispatch layer with `status`, `list`, `validate`, `collapse`, `calibrate`, `critic` — sensible UX for a research project.
- **Reproducibility primitives exist.** `v4/lib/soc_pipeline.py` wraps `powerlaw` with seed control + bootstrap. `v4/scripts/b3_ensemble.py` versions prompts + rationales.
- **Schema-first LLM design.** `v4/lib/llm_schemas.py` (314 lines) + `llm_guardrail.py` is the kind of architecture most LangChain projects don't bother with.
- **Setup.py is correct.** W6-A fixed `install_requires` + url. Wheel builds.

### 2.2 Weaknesses (each must be fixed for "real engineering value")

| # | Weakness | Severity | Fix effort |
|---|---|---|---|
| W1 | **Repo is PRIVATE.** Zero discovery, zero external contribution path. | P0 | 1h |
| W2 | **No PyPI release.** `pip install structural-isomorphism` fails. | P0 | 2-3 days |
| W3 | **No GitHub Actions CI.** Tests pass locally; on PR they're unverified. | P0 | 4-6h |
| W4 | **No docs site.** README is the only doc. Tutorials live in `tutorials/` not rendered. | P0 | 2 days |
| W5 | **No SemVer / changelog.** Version `0.1.0` hardcoded. No release tags. | P1 | 1h scaffold + ongoing discipline |
| W6 | **Secret leaked.** W5-B reviewer flagged plaintext DeepSeek key in `v4/scripts/b3_ensemble.py:48`. | **P0** (security) | 1-2h rotation + git-history scrub decision |
| W7 | **No pre-commit hooks.** Ruff/black/mypy not enforced. Reviewer sees `.gitignored` files in commits (`data/clean-expanded.jsonl` etc as broken LFS pointers). | P1 | 2-3h |
| W8 | **`v4/lib/llm_guardrail.py` is repo-internal.** Not importable as a standalone library. | P1 (unlocks P0 leverage) | 3 days |
| W9 | **B3 ensemble is one-shot script.** Prompts hardcoded for structural-isomorphism task. Not parameterizable. | P1 | 1 week extraction |
| W10 | **F1/F2 embedding bridge has no stable interface.** No type-stubs, signatures shift, no `__all__`. | P2 | 2-3 days |
| W11 | **Sqlite in production.** D1 ships sqlite; can't scale past ~5k companies w/o concurrent-write contention. | P1 (D1 only) | 1 week postgres migration |
| W12 | **No issue/PR templates, no CONTRIBUTING.md, no code-of-conduct.** External contribution friction infinite. | P1 | 1 day |
| W13 | **No Docker image.** Onboarding requires Python 3.8+ env, torch install, etc — 30-60 min friction. | P2 | 2 days |
| W14 | **Broken LFS pointers in `data/` and `results/`.** `git worktree add` warns "28 files that should have been pointers, but weren't". Indicates LFS misconfiguration. | P1 | 2-4h |

**P0 must-fix before any external user touches this repo:** W1, W2, W3, W4, W6 (security).

### 2.3 What's surprisingly already good

- W6-E's 213 tests already give us coverage badge potential ≥70% on `v4/lib/` paths.
- The B1/B3 verdict matrix is **fully reproducible** at ~$0.10/panel per W5-B's note. That's a citable property — most ML projects can't claim that.
- The `v4/cli.py` dispatch pattern is a clean template for any reproducibility-focused research repo. Could itself be a `cookiecutter` template down the line.

---

## 3. 18-month engineering roadmap

### A. Python package family

Three PyPI packages, each independently versioned, each living in its own GitHub repo (extracted from monorepo) but the monorepo retains them as `git subtree` for in-repo development:

#### A.1 `guarded-llm` (extracted from `v4/lib/llm_guardrail.py` + `llm_schemas.py`)
- **Pitch:** Strict-JSON LLM caller with schema validation, retry-with-exponential-backoff, cost budget tracking. Vendor-agnostic (Anthropic / OpenAI / DeepSeek / Kimi / vLLM / Ollama).
- **Differentiator vs. existing:**
  - `instructor` — Pydantic-first, OpenAI-centric, no cost budget
  - `outlines` — token-level constraints, harder to use for high-level "give me valid JSON matching this schema or raise"
  - `guidance` — Microsoft, declarative templates, heavier
  - `guarded-llm` — middle ground: schema-first + multi-vendor + budget-aware + clear retry semantics
- **Surface:**
  ```python
  from guarded_llm import GuardedClient, BudgetExceeded

  client = GuardedClient(vendor="anthropic", model="sonnet-4.5", budget_usd=5.0)
  result = client.call(
      schema=MyPydanticModel,
      prompt="...",
      max_retries=3,
      on_validation_fail="repair",  # or "raise"
  )
  ```
- **Repo:** `dada8899/guarded-llm`
- **Target launch:** Month 4

#### A.2 `cross-judge` (extracted from `v4/scripts/b3_ensemble.py`)
- **Pitch:** Cross-vendor LLM ensemble judging framework. Define task schema → register reviewer LLMs (different vendors / models / prompts) → get versioned verdict matrix with consensus rules (majority / Bayesian / Dawid-Skene).
- **Differentiator:** existing eval frameworks (`promptfoo`, `langsmith`, `helicone`) focus on *building* prompts. `cross-judge` focuses on *judging completed artefacts* with reproducible multi-reviewer protocol — a missing piece in LLM-as-judge research.
- **Surface:**
  ```python
  from cross_judge import EnsembleJudge, MajorityRule

  judge = EnsembleJudge(
      reviewers=[
          {"vendor": "anthropic", "model": "sonnet-4.5", "prompt_path": "rev_a.md"},
          {"vendor": "deepseek", "model": "v4-pro", "prompt_path": "rev_b.md"},
          {"vendor": "openai", "model": "gpt-5", "prompt_path": "rev_c.md"},
      ],
      consensus=MajorityRule(min_votes=2),
  )
  verdict = judge.evaluate(candidate={"text": "..."}, schema=VerdictSchema)
  ```
- **Repo:** `dada8899/cross-judge`
- **Target launch:** Month 6

#### A.3 `soc-pipeline` (extracted from `v4/lib/soc_pipeline.py`)
- **Pitch:** Reproducibility-grade self-organized-criticality fitter. Wraps `powerlaw` + adds Clauset goodness-of-fit + bootstrap CI + null model + seed control + JSON-serializable result objects.
- **Differentiator vs. `powerlaw`:** the underlying `powerlaw` package is mature but has reproducibility footguns (no seed surfaced through API, bootstrap is manual, no JSON serialization). `soc-pipeline` is the "batteries-included reproducible wrapper".
- **Target launch:** Month 3 (smallest scope, ships first)
- **Audience:** complexity science, neuroscience (neuronal avalanche analysis), seismology, finance (drawdown distributions).

### B. Documentation site

- **Stack:** `mkdocs-material` (Python-native, low maintenance, good search) or Astro Starlight (better for static + interactive). Recommend **mkdocs-material** for v0 — author already knows Python, plugin ecosystem mature.
- **Structure:**
  - `/` — landing (what is structural-isomorphism, who is it for)
  - `/quickstart/` — `pip install` → 5-min worked example
  - `/tutorials/` — 10 tutorials (expand from W3-D's 1):
    1. fit a power law correctly (Clauset method)
    2. cross-domain LLM ensemble judging
    3. strict-JSON LLM calls with retry
    4. embedding bridge for cross-domain search
    5. active learning for cross-domain pairs
    6. phase detector: predict company SOC phase
    7. validation suite: how to test your own domain
    8. reproducibility: seeded pipelines end-to-end
    9. cost budgeting for LLM-heavy research
    10. publishing your own results panel
  - `/api/` — auto-generated from docstrings via `mkdocstrings`
  - `/papers/` — C4 preprint + future C-series papers as web-rendered docs (not just PDFs)
  - `/cookbook/` — short recipes (50-100 LoC each)
- **Hosting:** `structural-isomorphism.github.io` via GitHub Pages, custom domain `docs.structural.bytedance.city` via CNAME.
- **Target launch:** Month 2-3 scaffold + 5 tutorials. Month 4-6 reach 10 tutorials. Month 6+ continuous.

### C. CI / quality gates

#### C.1 GitHub Actions workflows

| Workflow | Trigger | Steps | Budget |
|---|---|---|---|
| `pr-tests.yml` | every PR | install + lint (ruff) + format check (black) + type check (mypy) + unit tests + integration tests | < 5 min |
| `nightly-e2e.yml` | cron `0 2 * * *` | full e2e on D1 Phase Detector + 5 validation phases | ~30 min, $0 (no LLM calls) |
| `release.yml` | tag push | build wheel + sdist + publish to PyPI (after manual approval) | < 2 min |
| `coverage.yml` | weekly | run pytest --cov, push badge to README | < 5 min |
| `link-check.yml` | weekly | check all links in docs/ | < 2 min |

#### C.2 Pre-commit hooks (`.pre-commit-config.yaml`)
- `ruff` (lint + import sort)
- `black` (format)
- `mypy` (gradually-typed: start with `v4/lib/`)
- `pytest -m sanity` (~5s smoke pre-commit)
- `detect-secrets` (P0 — W6 leaked key) + `truffleHog` on push
- `mixed-line-ending`, `trailing-whitespace`, `end-of-file-fixer`

#### C.3 Coverage targets

- Month 1: 50% on `v4/lib/`
- Month 3: 70% on `v4/lib/`, 50% on `v4/product/`
- Month 6: 80% library, 60% product
- README coverage badge from codecov.io.

### D. LLM guardrail framework (`guarded-llm`)

Specifically what to do to make `v4/lib/llm_guardrail.py` into a real PyPI lib.

#### D.1 Refactor checklist
- [ ] Extract to `dada8899/guarded-llm` (new public repo).
- [ ] Vendor-agnostic interface (currently hardcoded for Anthropic + DeepSeek). Add adapter pattern for OpenAI, Kimi, Gemini, Ollama, vLLM.
- [ ] Replace inline schemas with Pydantic v2 models (current uses dataclasses + manual validation).
- [ ] Add `BudgetTracker` as standalone class (currently inline).
- [ ] Add `RetryPolicy` with exponential backoff + jitter.
- [ ] Add `on_validation_fail` modes: `raise` / `repair` (LLM auto-corrects) / `null` (return None) / `partial` (return what parsed).
- [ ] Optional integration: pipe `outlines` constrained generation for vendors that support it.
- [ ] CLI: `guarded-llm test --schema my_schema.json --prompt "..."` for ad-hoc testing.
- [ ] Test suite: 50+ unit tests, mocked-vendor integration tests, **cassette-based real-vendor tests** (record once, replay forever).

#### D.2 Differentiation pitch (1 sentence)
> `instructor` made strict-JSON ergonomic for OpenAI-Pydantic devs. `guarded-llm` makes it ergonomic for **multi-vendor production LLM pipelines with cost budgets and reproducible retry semantics.**

### E. B3 ensemble framework (`cross-judge`)

Specifically what to do to make `v4/scripts/b3_ensemble.py` into a real PyPI lib.

#### E.1 Refactor checklist
- [ ] Extract to `dada8899/cross-judge`.
- [ ] Decouple reviewer prompts from structural-isomorphism task. Reviewer prompts are user-supplied (markdown or .txt files).
- [ ] Task schema is user-supplied (Pydantic / JSON schema).
- [ ] Consensus rules pluggable: `MajorityRule`, `BayesianAggregator`, `DawidSkene` (EM-based), `WeightedMajority` (with reviewer reliability priors).
- [ ] Cross-vendor by design: each reviewer's `{vendor, model}` independently configured.
- [ ] Output: structured verdict matrix as JSONL (one row per candidate × reviewer) + aggregate verdicts.
- [ ] Replay support: re-run only reviewers whose prompts changed (cache by `hash(prompt + model + candidate)`).
- [ ] CLI: `cross-judge run --config judges.yaml --candidates cands.jsonl --out verdicts.jsonl`.
- [ ] Built-in cost estimator: pre-flight `--dry-run` reports estimated $.

#### E.2 Differentiation pitch
> `promptfoo` makes it easy to A/B test prompts. `cross-judge` makes it easy to **judge artefacts with reproducible multi-reviewer multi-vendor protocols** — the missing piece in "LLM-as-judge" research.

### F. D1 Phase Detector — from demo to SaaS pilot

This is the *product* track (W7-C will detail), but the engineering side:

| Step | Effort | Outcome |
|---|---|---|
| Postgres migration (sqlite → pg, alembic schemas) | 1 week | Concurrent writes, 10k+ companies |
| Auth (NextAuth.js + Google OAuth) | 4 days | gated tier |
| Rate limiting (per-IP + per-API-key, redis-backed) | 2 days | abuse-proof public API |
| API key system (Stripe customer portal) | 1 week | self-serve onboarding |
| Stripe billing (free / pro / enterprise tiers) | 1 week | revenue capture |
| Cron refresh (each Sunday, refresh top-1000 companies) | 2 days | freshness |
| Scale extraction to 1000+ companies | 2 weeks LLM time (~$50-100 budget) | W5-C P0 fix |
| API docs (FastAPI OpenAPI → Redoc) | 1 day | self-serve integration |

**Target:** 1000 companies + auth + Stripe pilot by Month 9.

### G. Open-source community

#### G.1 Repo PUBLIC checklist (P0, Month 1)
- [ ] **Secrets audit first** (W6 — flagged DeepSeek key). Use `git-filter-repo` to scrub if needed. Rotate key.
- [ ] LICENSE: MIT (already declared in setup.py — verify LICENSE file exists at root).
- [ ] CONTRIBUTING.md: dev setup, branch naming, PR template, review SLA.
- [ ] CODE_OF_CONDUCT.md (Contributor Covenant 2.1).
- [ ] SECURITY.md (responsible disclosure email).
- [ ] ISSUE_TEMPLATE/ (bug, feature, question, reproducibility-issue).
- [ ] PULL_REQUEST_TEMPLATE.md.
- [ ] README.md polish: hero badges (CI, coverage, PyPI, license), 30-second pitch, install, quickstart, link to docs.
- [ ] Set repo → public + announce in 3 channels (HN, /r/MachineLearning, complexity science Discord).

#### G.2 Community infra (Month 2-3)
- [ ] GitHub Discussions enabled.
- [ ] First "Good first issue" label batch (10 issues, each 2-4h scope).
- [ ] Discord server (low maintenance, low priority — defer to Month 6+ if traction).
- [ ] Monthly office-hours (1h video call, public RSVP).

#### G.3 Contribution funnel KPIs

| Month | Stars | PyPI dl/mo (combined 3 packages) | External PRs merged | Contributors |
|---|---|---|---|---|
| 1 | 50 | 0 | 0 | 1 (author) |
| 3 | 200 | 100 | 0 | 1 |
| 6 | 500 | 1000 | 2 | 3 |
| 12 | 2000 | 5000 | 10 | 5 |
| 18 | 5000 | 15000 | 25 | 8 |

These are *aspirational*; the 5x acceleration between month 6 → 12 requires the package + docs combo to land.

### H. Integration ecosystem (Month 12-18)

Once the core libraries are stable and have non-trivial adoption, expand surface area:

| Integration | Effort | Adoption gate |
|---|---|---|
| **Jupyter widget** — interactive `StructTuple` viewer (`anywidget` framework) | 2-3 weeks | only if `soc-pipeline` has >500 dl/mo |
| **Pandas extension** — `df.struct_tuple()` and `df.fit_powerlaw()` accessor | 1 week | only after `soc-pipeline` |
| **Polars extension** — same as Pandas but for polars (`pl.api.register_dataframe_namespace`) | 1 week | only if Pandas extension picks up |
| **VS Code extension** — pipe selected code → predict phase via D1 API | 3 weeks | only if D1 SaaS has >100 users |
| **Quarto / RMarkdown templates** — reproducible research templates that bundle `soc-pipeline` | 1 week | low priority, niche but valuable |
| **Docker image** — `ghcr.io/dada8899/structural-isomorphism:latest` | 2 days | Month 1 (also needed for CI) |
| **Cloud notebook** — Colab badge + Binder config | 1 day | Month 1 (low cost, high SEO) |

### I. Dev tools / DX

- **CLI ergonomics:** add `rich` for progress bars, `click` for commands (currently `argparse`), `prompt-toolkit` for interactive flows (`v4 init`, `v4 doctor`).
- **`v4 doctor`:** like `gh auth status` — checks Python version, optional deps, API keys, sqlite/postgres, last-run cost. Massive DX win for onboarding.
- **`structural-isomorphism --version` + `--upgrade` self-check.**
- **`.editorconfig`** — line endings, indent.
- **`.devcontainer/`** — VS Code one-click dev env.

---

## 4. NOT to do (next 12 months)

| Avoid | Why |
|---|---|
| Rewrite stack in Rust | Premature; no perf bottleneck on current data scale. Python ecosystem alignment > 2x speed. |
| Cross-language SDK (JS / Go / Rust bindings) | Python-only first. No proven user base for second-language demand. |
| Enterprise on-prem deploy | Need MRR first to know if enterprise even wants this. |
| LangChain / LlamaIndex integration | These wrappers are unstable. Better to be a *primitive* they could optionally use, not a dependent. |
| Web framework opinions (Django / FastAPI starter kit) | D1 already uses FastAPI; don't rebuild as opinionated kit. |
| Building a "platform" before any library has 1000 dl/mo | Hubris. Earn each abstraction tier with proven adoption of the lower one. |
| Custom GitHub Actions runners | YAGNI until CI bill > $50/mo. |
| AI agent framework (à la AutoGen, CrewAI) | Crowded space, lacks our research moat. `cross-judge` is the right niche. |
| Conference talks before docs site exists | Backwards funnel. Docs first, then talks reference docs. |

---

## 5. Milestone roadmap (1-18 months)

| Month | Milestone | KPI for "done" |
|---|---|---|
| **1** | Repo PUBLIC + LICENSE + CONTRIBUTING + security audit clean | 0 secrets in git history, MIT LICENSE rendered on GitHub |
| **1** | CI green on every PR (pytest + ruff + black + mypy) | 7 consecutive days of green main builds |
| **1** | Docker image + Binder + Colab badge | `docker pull ghcr.io/dada8899/structural-isomorphism` works |
| **2** | Pre-commit hooks + coverage badge ≥70% on `v4/lib/` | codecov badge in README |
| **2-3** | mkdocs docs site live with 5 tutorials | 50+ visits/day (sustained) |
| **3** | **PyPI `soc-pipeline 0.1.0`** | 100 downloads in week 1 |
| **4-5** | **PyPI `guarded-llm 0.1.0`** | 500 downloads in month 1 |
| **5-6** | **PyPI `cross-judge 0.1.0`** | 200 downloads in month 1 |
| **6** | D1 sqlite → postgres + auth (no billing yet) | 100 signups on waitlist |
| **6-7** | D1 scaled to 1000 companies (W5-C P0) | response time p95 < 2s |
| **7-8** | API rate limiting + key system | 0 abuse incidents |
| **9** | Stripe billing live (free / pro / enterprise) | first $100 MRR |
| **9-10** | First 2 external PRs merged | 2 unique external contributors |
| **10-12** | Tutorials expanded to 10, total | docs visits 500/day |
| **12** | First $1k MRR or pivot decision point | self-evident |
| **12-15** | Pandas/Polars extensions for `soc-pipeline` | 3rd-party blog post citing one |
| **15-18** | Jupyter widget + VS Code extension | 5 external contributors, 15k PyPI dl/mo |
| **18** | Decision: invest in next-tier infra (cloud, enterprise) or stay OSS-research | data-driven from KPIs |

---

## 6. Next 30 days — 10 actionable tasks

Ordered by **impact / effort** ratio. Each lists agent role + estimated time + measurable outcome.

| # | Task | Effort | Impact | Agent role |
|---|---|---|---|---|
| 1 | **Secret rotation + git-history scrub for DeepSeek key in `v4/scripts/b3_ensemble.py`** (W5-B P0) | 2-3h | **P0 security** — blocks repo-public | infra-security |
| 2 | Repo → PUBLIC after audit + LICENSE file + CONTRIBUTING.md + ISSUE_TEMPLATES + PR template + SECURITY.md | 1 day | unlocks all OSS leverage | oss-maintainer |
| 3 | **`guarded-llm` extraction kickoff** — new repo + skeleton + Pydantic v2 schemas + Anthropic+DeepSeek adapters + 30 unit tests | 3 days | unlocks largest addressable user base | python-package-author |
| 4 | GitHub Actions: `pr-tests.yml` (ruff + black + mypy + pytest unit + pytest integration) | 6h | every future PR is verified | devops |
| 5 | mkdocs-material scaffold + landing page + 1 polished tutorial (Clauset power-law fit, expanded from W3-D) | 2 days | docs site goes live | tech-writer |
| 6 | Pre-commit hooks + `detect-secrets` baseline + fix existing lint debt | 1 day | code quality floor enforced | infra |
| 7 | LFS pointer audit — fix the 28 broken pointers OR `.gitignore` the heavy data | 4h | clean `git worktree add` for new contributors | infra |
| 8 | **`soc-pipeline` extraction (smallest, ships first)** — new repo + 339-line lib + 20 unit tests + README + first PyPI release as `0.1.0a1` | 3 days | first real PyPI presence | python-package-author |
| 9 | Docker image + GHCR push + Colab badge in README | 1 day | onboarding friction halved | devops |
| 10 | README rewrite — hero with badges, 30-sec pitch, install snippet, link to docs | 2-3h | repo first impression matches the engineering quality | tech-writer |

**Sum:** ~16-18 engineering days for one agent, or ~3 weeks across a 5-agent wave.

---

## 7. Wave 8 dispatch candidates

Five concrete mini-briefs (≥5 required) that downstream W8 agents can pick up immediately. Each is independent, parallelizable, and has a measurable deliverable.

### W8-A: Security audit + secret scrub + repo PUBLIC checklist execution

- **Role:** infra-security senior engineer
- **Goal:** repo becomes public-safe by end of session
- **Inputs:** entire repo, especially `v4/scripts/b3_ensemble.py`, `v4/scripts/`, `.env*`, `web/phase-detector/.env*`
- **Deliverables:**
  - Rotated DeepSeek key (user provides new key out-of-band; agent updates `.env.example` only)
  - `git-filter-repo` plan documented in `docs/security/secret-scrub-plan.md` (NOT executed without user approval — destructive)
  - LICENSE file at root (MIT)
  - CONTRIBUTING.md (200 lines: dev setup, branch naming, PR review SLA, code-of-conduct ref)
  - SECURITY.md (responsible disclosure)
  - `.github/ISSUE_TEMPLATE/` 4 templates (bug / feature / question / reproducibility)
  - `.github/PULL_REQUEST_TEMPLATE.md`
- **Verification:** `gh repo view --json visibility` shows public-eligible; `truffleHog` scan returns clean on HEAD (history scrub decision deferred to user); CONTRIBUTING covers all sections in checklist
- **Budget:** 0 LLM calls (pure infra work). 4-6h human-equivalent.

### W8-B: GitHub Actions CI scaffold (PR tests + nightly e2e + release)

- **Role:** devops engineer
- **Goal:** every PR is gated by green CI; nightly e2e runs; release workflow ready
- **Inputs:** `pytest.ini`, `v4/tests/`, `setup.py`, `requirements*.txt`
- **Deliverables:**
  - `.github/workflows/pr-tests.yml` (ruff + black --check + mypy `v4/lib/` + pytest -m "unit or integration") on PR
  - `.github/workflows/nightly-e2e.yml` (cron `0 2 * * *`, runs `v4/cli.py validate --all` + D1 sample run)
  - `.github/workflows/release.yml` (on tag push: build sdist+wheel, upload to PyPI via OIDC trusted publishing)
  - `.github/workflows/coverage.yml` (weekly, push to codecov.io)
  - `pyproject.toml` migration from `setup.py` (modern packaging)
  - `.pre-commit-config.yaml` with ruff / black / mypy / detect-secrets / pytest -m sanity
- **Verification:** all workflows show green on a test PR; pre-commit installs cleanly; mypy passes on `v4/lib/`
- **Budget:** $0. 6-8h.

### W8-C: `soc-pipeline` PyPI extraction (smallest package, ships first as proof)

- **Role:** python-package-author
- **Goal:** ship first PyPI release of the family
- **Inputs:** `v4/lib/soc_pipeline.py` (339 lines), tests that touch it (`v4/tests/sanity/test_soc_*.py`)
- **Deliverables:**
  - New `dada8899/soc-pipeline` repo (private until W8-A clears) with:
    - `src/soc_pipeline/` package (extracted + cleaned, no structural-isomorphism coupling)
    - `pyproject.toml` (PEP 621, hatchling backend)
    - 20+ unit tests (port + expand from monorepo)
    - README with quickstart (fit power-law on synthetic data + on real seismicity)
    - `docs/` mkdocs scaffold (3 pages: quickstart, API, reproducibility)
    - GitHub Actions CI
    - First release `0.1.0a1` to **TestPyPI** (not real PyPI yet)
- **Verification:** `pip install -i https://test.pypi.org/simple/ soc-pipeline==0.1.0a1` succeeds in clean venv + the 5-line README example runs
- **Budget:** $0 LLM. 3 engineering days.

### W8-D: `guarded-llm` extraction kickoff (highest leverage, partial scope)

- **Role:** python-package-author (with LLM-infra background)
- **Goal:** scaffold the package, ship first working Anthropic + DeepSeek adapter, defer multi-vendor expansion to W9
- **Inputs:** `v4/lib/llm_guardrail.py` (441 lines) + `v4/lib/llm_schemas.py` (314 lines)
- **Deliverables:**
  - New `dada8899/guarded-llm` repo with:
    - `src/guarded_llm/` package: `client.py`, `schemas.py`, `budget.py`, `retry.py`, `adapters/{anthropic,deepseek}.py`
    - Pydantic v2 schemas (refactor from current dataclasses)
    - `BudgetTracker` standalone class with `BudgetExceeded` exception
    - `RetryPolicy` with exponential backoff + jitter
    - 30+ unit tests with mocked vendor responses
    - **Cassette-based integration tests** (record once with real API, replay forever in CI for free)
    - README pitching against `instructor` / `outlines` (1-paragraph "why this exists")
  - **NO PyPI release yet** — this is alpha scaffolding for design review.
- **Verification:** clean venv `pip install -e .` works, `pytest` 100% green, example in README runs against real Anthropic API
- **Budget:** ≤$2 LLM (for cassette recording). 3 engineering days.

### W8-E: mkdocs-material docs site scaffold + landing + 1 tutorial

- **Role:** tech-writer (with Python + ML background)
- **Goal:** docs.structural.bytedance.city live within session
- **Inputs:** README.md, W3-D existing tutorial, `v4/cli.py` usage examples, `paper/c4-reject-aware-pipeline-2026-05-13.md`
- **Deliverables:**
  - `docs/` mkdocs-material site (separate from `docs/sessions/`, `docs/reviews/` etc — use `mkdocs/` as content root):
    - `index.md` — 30-sec pitch, who is this for, three callouts (researcher / engineer / curious)
    - `quickstart.md` — `pip install` → 5-min worked example (Clauset power-law fit)
    - `tutorials/01-power-law-correctly.md` — expanded W3-D content (1500 words, Jupyter-style code blocks)
    - `api/` — `mkdocstrings` config for auto-gen API ref
    - `papers/c4-preprint.md` — render the preprint as web doc with anchored sections
  - GitHub Pages deploy via `gh-pages` branch + workflow
  - CNAME `docs.structural.bytedance.city` (DNS via DNSPod — user assists)
  - mkdocs config theme matches `beta.structural.bytedance.city` (Inter + Noto Serif SC, white-first)
- **Verification:** local `mkdocs serve` works, GH Pages preview URL works, all internal links pass linkcheck, Lighthouse mobile score ≥90
- **Budget:** $0. 2 engineering days.

### W8-F (bonus): D1 Phase Detector — sqlite → postgres migration plan + scale-to-1000 plan

- **Role:** backend engineer (FastAPI + postgres)
- **Goal:** unblock D1 to grow past 100 companies (W5-C P0)
- **Inputs:** `v4/product/d1_phase_detector/`, `web/phase-detector/`
- **Deliverables:**
  - `docs/d1-postgres-migration-plan.md`: alembic config, schema, dry-run script, rollback plan
  - `docs/d1-scale-1000-cost-plan.md`: LLM cost estimate ($50-100 budget), batch strategy, dedup, prompt versioning
  - First 100 companies migrated to postgres in dev environment (sqlite kept as fallback)
  - **NO production cut-over** in this session — that's a separate deploy gate
- **Verification:** local dev `docker compose up postgres` + `alembic upgrade head` + sample query returns identical results to current sqlite for 5 spot-checked companies
- **Budget:** $0 LLM, $0 cloud (local dev only). 4-5 engineering days.

---

## 8. Scoring rubric: how we measure "real engineering value"

Six primary KPIs, refreshed quarterly:

| KPI | Source | 6mo target | 12mo target | 18mo target |
|---|---|---|---|---|
| **PyPI download count (combined 3 packages)** | `pypistats.org` | 1000/mo | 5000/mo | 15000/mo |
| **GitHub stars (main repo)** | GitHub API | 500 | 2000 | 5000 |
| **External contributor count** | `git shortlog -sne` minus author | 2 | 5 | 8 |
| **External PRs merged** | GitHub API | 2 | 10 | 25 |
| **Issue close turnaround (median)** | GitHub API | <14d | <7d | <3d |
| **Dependent projects** | libraries.io / GitHub search | 1 | 5 | 15 |

Secondary signals (qualitative, but track):

- citations in technical blogs (Google search alerts on package names)
- citations in HN / lobste.rs / r/MachineLearning posts
- conference talk acceptances (Month 12+: SciPy, PyData, EuroSciPy)
- inclusion in "awesome-*" curated lists
- PyPI Trove classifier appropriate (`Development Status :: 4 - Beta` by Month 9, `:: 5 - Production/Stable` by Month 18)

**Failure modes to detect early:**
- If at Month 6 PyPI downloads are <100/mo combined: docs / discoverability problem, not product problem. Invest in 2 conference talks + blog posts.
- If at Month 9 issues > 50 open with no contributor help: maintainer burnout risk. Tag 10 issues "good first issue" + recruit 1 co-maintainer.
- If at Month 12 zero external PRs merged: contribution friction too high. Audit CONTRIBUTING, simplify dev setup, add `make dev-setup` one-command.

---

## 9. Single highest-leverage move

> **Extract `v4/lib/llm_guardrail.py` (+ `llm_schemas.py`) into a standalone `guarded-llm` PyPI package within 30 days.**

**Why this and not the others:**

1. **Largest addressable user base.** Every LLM-powered Python project hits the strict-JSON problem. There are ~50,000 active Python LLM projects (rough GitHub count). Even 0.1% adoption = 50 dependent projects.
2. **Lowest competition for the specific niche.** `instructor` is OpenAI-Pydantic-first. `outlines` is token-level. `guidance` is heavy. Multi-vendor + budget-aware + production-retry is an open niche.
3. **Clear differentiation pitch.** "Strict-JSON LLM calls that don't blow your budget when retries cascade." One sentence, validates instantly.
4. **Highest pull-through.** Adopters of `guarded-llm` are the *exact* audience for `cross-judge` and `soc-pipeline` later — they're already doing reproducible LLM work.
5. **The code is already production-grade.** 441 lines, used in 213 tests, survived B1/B3 ensemble runs (~$0.10 cost per panel). It's not a toy.
6. **Defensive moat for structural-isomorphism research.** Owning the underlying primitive means future reviewers / collaborators *already use our tools* before they evaluate our papers.

**The risk if we don't do this:** someone else will. The strict-JSON-multi-vendor niche is open today; in 6 months it won't be. Anthropic / OpenAI / a YC startup will ship the "obvious" library and `v4/lib/llm_guardrail.py` becomes shelfware.

---

## 10. Closing note — what success looks like at Month 18

If this roadmap executes:

- `pip install guarded-llm` is in 500+ projects' `requirements.txt`.
- `soc-pipeline` is the recommended power-law tool in 2-3 complexity-science textbooks / lecture notes.
- `cross-judge` is cited in at least 1 NeurIPS / ICML "LLM-as-judge" paper.
- D1 Phase Detector has paying customers (≥$1k MRR) and 1000+ companies indexed.
- 5+ external contributors have merged PRs.
- structural-isomorphism the *project* is known not just for the research claim but for the **reusable infrastructure under it**.

The research claim (cross-domain isomorphism) gets sharper or quieter depending on how W5-B's methodology critiques resolve. Either way, the engineering infrastructure stands.

**That's the bet:** ship the under-libraries, and even if the headline research claim hedges down from 5 universal classes to 2, the codebase still ships value.

— end W7-B —
