# Phase 6 — GitHub Event Cascades (SOC validation)

Sixth cross-domain system run through the project's frozen SOC validation
pipeline (`packages/soc-pipeline/`), the same pipeline used for Phase 1-5
(earthquakes / stock market / DeFi / neural avalanches / null controls).

## Why a new GitHub target

The project already has two GitHub pilots, and **neither tests a cascade**:

| Pilot | What it measures | Why it is not a cascade |
|---|---|---|
| `soc-github-stars` | cumulative star counts (8,398 repos) | preferential-attachment **growth**, not a threshold release |
| `soc-github-resolution` | issue-resolution durations | a per-issue **waiting time**, no triggered burst |

Phase 1 (earthquakes) is the structural template: a localized **trigger**
(mainshock) releases a **burst** of correlated follow-on events (aftershocks)
whose *rate* decays as a power law (Omori) and whose *total size* is
power-law distributed (Gutenberg-Richter / branching). Phase 6 builds the
GitHub analogue of exactly that object.

## Cascade definition (precise)

Per repository, over its event stream (every issue + PR `created_at`):

- **Loudness** of an event = `comments + reactions`.
- **Main event** ("mainshock") = an issue/PR with loudness
  `> mu + 2*sigma` (per-repo threshold). A hot bug report, security
  advisory or major proposal — something that visibly shakes the project.
- **Cascade** triggered by a main event at time `t0` = every issue/PR
  opened in the **same repo** within `(t0, t0 + 30 days]`.
  - **cascade size** `s` = count of derived events → power-law sample
  - **Omori delays** = `(t_derived - t0)` seconds → stacked rate-decay fit

This is structurally isomorphic to Phase 1: trigger → correlated burst →
power-law size + Omori-decaying rate.

## Pre-registered bands (frozen before seeing the verdict)

- cascade-size `alpha in [1.5, 3.5]` (wide; threshold-cascade SOC systems
  in this project's Phase 1-4 land 1.8-3.0, band widened because GitHub
  cascades have no established literature value)
- Omori `p in [0.3, 1.3]` (canonical Omori band, same as Phase 1 / 3)

## Files

| File | Content |
|---|---|
| `fetch_github_cascades.py` | pulls issue/PR streams via GitHub GraphQL (`gh api graphql`) |
| `events.jsonl` | 29,400 real events from 25 repos (one JSON record per event) |
| `fetch_log.json` | repo list, per-repo counts, failures, timestamps |
| `analyze.py` | builds cascades, runs the SOC pipeline + a window/sigma sensitivity sweep |
| `cascade_results.json` | full machine-readable result (fit, CI, Omori, sweep, per-repo) |
| `FINDINGS.md` | short verdict report |

## Reproduce

```bash
python3 fetch_github_cascades.py            # ~5 min, needs authenticated gh CLI
python3 analyze.py                          # runs the frozen pipeline
python3 fetch_github_cascades.py --self-test  # parsing smoke test, writes nothing
```

## Honesty notes

- **Real data only.** `events.jsonl` is 100% GitHub API data. The
  `synth_stream()` in the fetch script is reachable **only** via
  `--self-test` and is never written to `events.jsonl`.
- API limit is the sample limit: 1,200 most-recent events per repo
  (`django/django` returned 600 — fewer recent events available; recorded
  in `fetch_log.json`).
- The 30-day window plus high repo activity means cascades overlap heavily
  and are not cleanly separated — see `FINDINGS.md` for why this is a real
  methodological limitation and how the sensitivity sweep addresses it.
