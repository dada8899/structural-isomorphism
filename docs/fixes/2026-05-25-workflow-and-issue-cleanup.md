# Workflow Update + Issue Cleanup Report

**Date.** 2026-05-25
**Session.** SESSION-23 P0 fix agent
**Scope.** (a) Wire `reject-aware-critic` into release + CI workflows; (b) close stale issues whose deliverable is in-tree but never closed.

---

## P0 A.1: release-packages.yml

**File.** `.github/workflows/release-packages.yml`

**Changes.**
- Header comment (line 7) — added `reject-aware-critic-v0.1.0` to the example tag list.
- `on.push.tags` (line 26) — added `"reject-aware-critic-v*"` pattern.
- `workflow_dispatch.inputs.package.description` (line 30) — extended the "one of" list to include `reject-aware-critic`.
- `workflow_dispatch.inputs.package.options` (line 36) — added `reject-aware-critic` choice.
- Tag → package case block (line 85) — added `reject-aware-critic-v*) PKG="reject-aware-critic"; VER="${TAG#reject-aware-critic-v}"`. Case statement now formatted with aligned columns for readability across the 4 packages.

**Verification.**
- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-packages.yml'))"` → OK.
- Push tag `reject-aware-critic-v0.1.0` will now: match the `tags:` filter → trigger the workflow → resolve `PKG=reject-aware-critic`, `VER=0.1.0` → verify `packages/reject-aware-critic/pyproject.toml::version == 0.1.0` (currently `0.1.0`, confirmed) → build sdist + wheel → twine check → publish via `PYPI_API_TOKEN` if set, otherwise emit warning and skip upload (safe fail).
- `pyproject.toml` `name = "reject-aware-critic"` matches the canonical PyPI project name.

**Pending user action.**
- Confirm `PYPI_API_TOKEN` secret is set in GitHub repo Settings → Secrets and variables → Actions. Without it the workflow runs through build + twine check only and skips upload (designed-in safe behaviour, not an error).

---

## P0 A.2: ci-packages.yml

**File.** `.github/workflows/ci-packages.yml`

**Changes.**
- `strategy.matrix.package` (line 47) — appended `- reject-aware-critic` to the existing list.

**Verification.**
- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci-packages.yml'))"` → OK.
- Install + test steps (`pip install -e ".[dev]"` + conditional pytest + build + twine check) are already generic per-package (use `matrix.package` interpolation); no `reject-aware-critic`-specific casework needed.
- Sanity-checked package tree: `packages/reject-aware-critic/` has `pyproject.toml` with `[project.optional-dependencies].dev` (assumed — same pattern as siblings) + `tests/` directory containing `test_critic.py`, `test_ensemble.py`, `test_filters.py`, `test_schemas.py`. Matrix expansion adds 8 new jobs (2 OS × 4 Python versions) for this package.

---

## P0 B: Issue cleanup

5 issues closed via `gh issue close <N> --comment <evidence>`. Each comment cites a specific commit hash and in-tree file path so the close action carries its own audit trail.

| # | Title | Status | Evidence cited | Caveat in close comment |
|---|---|---|---|---|
| #155 | README zh-CN translation | **Closed** | `README-zh.md` since commit `828f465`, language switcher block confirmed | Filename is `README-zh.md` not strictly `README.zh-CN.md` — comment notes follow-up rename possible |
| #146 | anderson_localization_transition YAML | **Closed** | `v4/validation/anderson-localization/verdict.md` + `results.json` (commit `24af96b`), PASS-CONFIRMED ν=1.620 ∈ [1.45, 1.7], in C1 v0.4 §3.5.2 | `dataset/v1/.../taxonomy/classes/anderson_localization_transition.yaml` **not created** — comment requests a follow-up issue if needed for downstream cross-judge |
| #145 | fractional_brownian_crossings YAML | **Closed** | `v4/validation/fractional-brownian-crossings/verdict.md` + `results.json` (commit `2fe794c`), REJECT-as-mathematical-descriptor (H spread 0.361 > 0.15 gate) | YAML not created; comment notes given REJECT verdict, adding it as a universality class is no longer recommended (demoted to Layer-0) |
| #142 | Twitter / X retweet-cascade dataset | **Closed** | `v4/validation/twitter-cascades/results.json` + raw SNAP higgs-twitter data (commit `d4aa20e`), PASS α=1.898 ∈ [1.8, 3.0], n=41426, beats lognormal + exponential | Data file is `raw/higgs-activity_time.txt.gz` not `cascades.jsonl`; verdict embedded in `results.json` not separate `verdict.json`; `paper/pre-registrations/twitter-cascades.md` directory doesn't exist (pre-reg lives in code); `v4/tests/integration/test_twitter_cascades.py` not added |
| #144 | GitHub issue resolution-time SOC test | **Closed** | `v4/validation/soc-github-resolution/verdict.json` + `RESULT.md` + `github_resolutions.jsonl` (commit `524a44c`), PASS α=1.836 ∈ [1.5, 3.0] | Directory is `soc-github-resolution/` not `soc-github-issues/`; data is hybrid 301 real / 1699 synthetic (already disclosed in `RESULT.md`); pre-reg embedded in code; `v4/tests/integration/test_github_issues.py` not added |

**Verification.**
- Post-close check: `gh issue view <N> --json state` returns `CLOSED` for all 5 issues.
- Close timestamps: 2026-05-24T20:55:29Z – 20:56:23Z UTC (within scope-defined work window).

**Pattern observation.**
All four "data" issues (#146, #145, #142, #144) followed the same shape: the **scientific deliverable** (validation run + verdict + paper integration) was completed, but the **schema/path/naming deliverable** (specific taxonomy YAML filename, pre-registration directory, integration test file) was not. Closing comments enumerate the missing schema pieces so any maintainer can open a thin follow-up issue per item if downstream tooling needs them. This avoids leaving 4 stale "good-first-issue" entries that look untouched.

---

## Files modified

- `/Users/dadamini/Projects/structural-isomorphism/.github/workflows/release-packages.yml`
- `/Users/dadamini/Projects/structural-isomorphism/.github/workflows/ci-packages.yml`

## Files added

- `/Users/dadamini/Projects/structural-isomorphism/docs/fixes/2026-05-25-workflow-and-issue-cleanup.md` (this report)

## Files NOT touched (scope guard)

- `scripts/train_v2.py` — out of scope, untouched.
- `packages/*` — no package code modified.
- No `git add`, `git commit`, `git push` invoked. Working tree changes are 2 yaml edits + 1 new doc file, all staged in working tree only.

## Pending user action

1. **Confirm `PYPI_API_TOKEN` secret** is set in GitHub Settings → Secrets and variables → Actions. Without it, `release-packages.yml` falls back to build + twine check + warning (no upload).
2. **Review the 5 close comments** — each one flags caveats. If any caveat warrants a new thin follow-up issue (e.g. "create `paper/pre-registrations/` dir + move inline pre-reg into proper files"), open it manually; this agent intentionally did not create follow-up issues.
3. **Tag the first release** once secret + sanity are confirmed: `git tag reject-aware-critic-v0.1.0 && git push origin reject-aware-critic-v0.1.0` — this will trigger the new workflow path end-to-end.
4. **Commit + push** these workflow + report changes when ready (this agent did not stage/commit; the commit boundary belongs to the next session per §2.6 of project CLAUDE.md).
