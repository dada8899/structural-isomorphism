# [data] Add GitHub issue resolution-time dataset (heavy-tail / SOC test)

## What

Build a dataset of GitHub issue resolution times (time from open → closed) across 50–100 popular OSS repos, then test whether the distribution is heavy-tailed (Pareto/power-law) vs lognormal vs exponential using `soc_pipeline.fit_clauset_powerlaw`.

## Why

Software-engineering productivity studies repeatedly hand-wave that "issue resolution is heavy-tailed" without a rigorous fit. This is a chance for a small but cleanly-pre-registered study, and the data is free via the GitHub Archive on BigQuery (one-time CSV export, no per-request quota).

## Where

- New directory: `v4/validation/soc-github-issues/` (different from existing `soc-github-stars/`)
- Pattern: mirror `soc-github-stars/` exactly (it already has `repos.jsonl` + `analyze.py`)

## How to start

1. Use the [GH Archive](https://www.gharchive.org/) BigQuery dump to extract `(repo, issue_id, open_ts, close_ts)` for 50–100 repos with ≥ 500 closed issues. Save as JSONL.
2. Per repo, compute resolution durations in seconds. Pool or per-repo — your call (document the choice).
3. Pre-register at `paper/pre-registrations/github-issues.md`. Suggested band: α ∈ [1.5, 2.5] if heavy-tail, but also legitimate to pre-register "we expect lognormal to win".
4. Run the fit + Vuong LR test vs lognormal/exponential.

## Definition of done

- [ ] `repos.jsonl` (or `issues.jsonl`) committed
- [ ] `analyze.py` + `verdict.json`
- [ ] Pre-registration committed prior to verdict
- [ ] Test in `v4/tests/integration/test_github_issues.py`
- [ ] At least one paragraph in `verdict.json["notes"]` discussing which distribution won

## Difficulty

★ to ★★ (data extraction is the bottleneck; statistics are 5 lines)
