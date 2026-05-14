# Public release readiness — 2026-05-13

This checklist tracks what needs to be done before flipping the repo from PRIVATE to PUBLIC.

## P0 (must complete before flip)

- [x] LICENSE present (MIT)
- [x] CONTRIBUTING.md
- [x] CODE_OF_CONDUCT.md (Contributor Covenant v2.1)
- [x] GOVERNANCE.md (BDFL → council transition plan)
- [x] .github/ISSUE_TEMPLATE/ (bug + feature)
- [x] .github/PULL_REQUEST_TEMPLATE.md
- [x] .github/workflows/ci.yml (GitHub Actions for pytest)
- [x] Plaintext credentials removed from current state (all migrated to env vars in W6-A)
- [ ] **Credentials scrubbed from git history** — historical commits still contain old DeepSeek key references. Requires user authorization to run `git filter-repo` or BFG and force-push cleaned history. Old key should be rotated first regardless.
- [x] README rewritten for external audience (W6-E session #10 — leads with question, 3-card layout, tightened to ~1100 words)
- [ ] All TODO placeholders in `setup.py`, `pyproject.toml`, papers replaced with real values (W6-A handled most; verify before flip)

## P1 (recommended, not blocking)

- [ ] mkdocs / Astro docs site live
- [ ] PyPI packages published (`soc-pipeline`, `guarded-llm`)
- [ ] arXiv preprint v0.3 posted (C1 unified pipeline)
- [ ] Zenodo DOI minted for dataset/v1/ bundle
- [ ] 15 good-first-issue drafts converted to labeled GitHub issues
- [ ] LFS migration completed (current large data files moved to LFS)
- [x] Phase Detector browser-side runtime issue fixed (commit bfdf2b0; regression e2e in `tests/e2e/test_phase_detector_no_react_errors.py`)
- [x] universality-classes.json duplicate class_id resolved (commit bfdf2b0 + W6-E session #10 — `_v2` suffix policy, regression test in `tests/test_universality_classes_unique.py`, decision record in `docs/data/universality-classes-dedupe-2026-05-15.md`)

## Decision gates (founder authorization required)

These actions are irreversible or externally visible and need explicit go-ahead:

- [ ] Rotate DeepSeek API key
- [ ] Force push scrubbed git history
- [ ] Flip repo visibility to PUBLIC
- [ ] Submit C1 v0.3 to arXiv
- [ ] Mint Zenodo DOI (permanent)
- [ ] Publish `soc-pipeline` 0.1.0 to PyPI
- [ ] Publish `guarded-llm` 0.1.0 to PyPI

## Coordination

- arXiv submission and repo PUBLIC flip should happen within days of each other (arXiv preprint references the GitHub repo)
- Zenodo DOI should be minted before arXiv submission so paper can cite the DOI
- Newsletter / HN launch posts should land after repo PUBLIC and arXiv URL are both live

## Status

Last updated: 2026-05-15 (W6-E session #10 — README rewrite + dedupe regression + React error e2e regression tests landed)
Maintainer: @dada8899
