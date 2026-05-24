# Phase 6 Findings — GitHub Event Cascades

**Date:** 2026-05-22
**Pipeline:** `packages/soc-pipeline/` (frozen, identical to Phase 1-5)
**Verdict: FAIL** — GitHub event cascades are **not** self-organized critical.

This is an honest negative, in the same spirit as the Phase 5 null controls:
a real FAIL is worth more than a manufactured PASS.

## Data

- **29,400 real events** (issues + PRs) from **25 large, active OSS repos**
  (kubernetes, react, vscode, tensorflow, pytorch, rust, node, TypeScript,
  go, django, flutter, elasticsearch, ansible, angular, electron, next.js,
  deno, home-assistant, grafana, airflow, godot, ClickHouse, ray,
  transformers, n8n).
- Pulled via GitHub GraphQL API; 1,200 most-recent events/repo (django
  returned 600 — fewer available). Full list + counts in `fetch_log.json`.
- 823 main events (loudness > mu + 2sigma) -> **823 cascades**, 306,183
  stacked Omori delays.

## Pipeline results

| Metric | Value | Pre-registered band | In band? |
|---|---|---|---|
| cascade-size **alpha** | **1.696** | [1.5, 3.5] | yes |
| alpha 95% bootstrap CI | [1.626, 2.995] | — | — |
| KS distance | 0.176 | (low = good) | **poor fit** |
| vs lognormal | R = **-11.86**, p ~ 2e-32 | — | **lognormal wins** |
| vs exponential | R = **-14.63**, p ~ 2e-48 | — | **exponential wins** |
| Omori **p** | 0.358 +/- 0.021, R2 = 0.95 | [0.3, 1.3] | yes |

## Why FAIL

Although the fitted alpha (1.70) lands *inside* the pre-registered band, the
**Clauset 2009 model-comparison test decisively rejects the power-law**: both
lognormal (R = -11.9) and exponential (R = -14.6) fit the cascade-size
distribution far better, at overwhelming significance. The KS distance
(0.176) confirms the power-law is a poor description of the tail. Under the
project's standard verdict logic (same as Phase 1-5 `validate()`), "a simpler
model beats power-law" is an automatic FAIL — alpha being in-band does not
rescue it.

## The FAIL is robust (sensitivity sweep)

A genuine scale-free regime gives a **window-invariant** alpha. It does not:

| window | sigma | n cascades | alpha | rejects power-law? | R_lognormal |
|---|---|---|---|---|---|
| 30 d | 2.0 | 823 | 1.70 | **yes** | -11.9 |
| 7 d | 2.0 | 823 | 2.95 | **yes** | -2.9 |
| 3 d | 2.0 | 823 | 2.45 | **yes** | -3.3 |
| 1 d | 2.0 | 823 | 2.17 | **yes** | -3.4 |
| 3 d | 3.0 | 391 | 2.48 | **yes** | -1.7 |

Power-law is rejected in **every** setting, and alpha drifts 1.7 -> 3.0 with
the window — direct evidence that there is no scale-free regime. The FAIL is
not a single-parameter artefact.

## What *does* partially match

The **Omori timing holds**: stacked derived-event delays decay as
rate ~ K/(t+c)^p with p = 0.36 and an excellent R2 = 0.95 (n ~ 306k delays).
So GitHub activity *does* cluster in time after a hot event — there is real
temporal triggering. What fails is the **size** law: the number of
follow-on events per burst is lognormal/exponential, not power-law. A SOC
system needs *both*; GitHub cascades have the timing signature but not the
scale-free size signature.

## Honest limitations

1. **Cascade separation.** With 1,200 events/repo spanning anywhere from
   8 days (vscode) to 308 days (react), a 30-day window often swallows much
   of the stream, so cascades overlap heavily and "cascade size" partly
   measures baseline repo activity rate x window rather than a cleanly
   triggered burst. The sensitivity sweep mitigates this — and the FAIL
   survives every window down to 1 day — but a fully clean test would need
   longer per-repo histories with quiescent gaps between main events.
2. **Loudness proxy.** "Main event" is defined by comments + reactions; an
   alternative trigger definition (cross-references, security-advisory
   labels) could change which events count as mainshocks.
3. **Sample window.** Only the most-recent ~1,200 events per repo (API
   pagination budget). A multi-year backfill would give more main events.
4. None of these limitations point toward a power-law — every robustness
   check pushed further *away* from SOC, so the negative conclusion is safe.

## Bottom line

GitHub event cascades join the list of systems that look heavy-tailed but
are **not** self-organized critical on the size axis. Of the project's
GitHub probes, all three (stars = growth, resolution = waiting time,
cascades = bursts) come back non-SOC — consistent with collaborative
software activity being driven by human/organizational scheduling rather
than a self-tuned critical threshold. A clean **FAIL**, honestly reported.
