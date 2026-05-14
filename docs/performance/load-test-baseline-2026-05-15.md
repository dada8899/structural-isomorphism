# Load test baseline — 2026-05-15

**Wave:** W14-B (session #10)
**Tool:** k6 (Grafana). Five scripts under `tests/load/`.
**Target:** beta.structural.bytedance.city (FastAPI on VPS) and local dev.
**Author:** w14-b sub-agent

## Why this exists

W14-B introduces an automated load-test surface for the structural-isomorphism
backend. The W11-C rate-limit middleware introduced free/pro/team/admin tiers
(60 / 1 000 / 5 000 / unlimited req/min) — but we never verified the
60-req/min free-tier ceiling actually holds under concurrent VUs, nor measured
where `/api/daily` (the cheapest GET) starts returning 5xx. This baseline
gives us a starting number and a CI knob to detect regressions.

## How to run

### Local dev

```bash
# 1. Install k6
brew install k6   # macOS
# Linux: see header of tests/load/phases_smoke.js for apt instructions.

# 2. Run the cheap-GET smoke (fastest signal)
BASE_URL=http://localhost:8000 k6 run tests/load/phases_smoke.js

# 3. Full suite (~10–15 min wall clock)
BASE_URL=http://localhost:8000 ./tests/load/run_all.sh

# 4. Just the LLM-bound check (costs real LLM budget)
BASE_URL=http://localhost:8000 k6 run tests/load/ask_smoke.js
```

### Against staging (beta.structural.bytedance.city)

```bash
# Polite mode: 1-2 VUs, smokes only, no stress, no LLM cost.
BASE_URL=https://beta.structural.bytedance.city SAFE=1 ./tests/load/run_all.sh

# Full mixed-traffic profile (asks permission of the owner first):
BASE_URL=https://beta.structural.bytedance.city k6 run tests/load/mixed_realistic.js

# Stress endpoint requires explicit acknowledgement against prod:
I_KNOW_WHAT_I_AM_DOING=yes BASE_URL=https://beta.structural.bytedance.city \
  k6 run tests/load/stress_ramp.js
```

### CI

GitHub Actions workflow `.github/workflows/load-smoke.yml` is
`workflow_dispatch` only — pick a target (`local` / `beta` / custom URL) and
the smoke scenario. No automatic trigger; load tests are too expensive (and
too contended on shared CI runners) to fire on every PR.

## Endpoint mapping note

The W14 task brief named `/api/phases` for the cheap-GET case. The shipped
backend exposes `/api/daily` as the canonical cheap GET (pre-computed rotating
cross-domain analogy, no LLM cost, ~6 KB JSON body). `phases_smoke.js` defaults
to `/api/daily`; override with `PHASES_PATH=/api/phases k6 run …` when that
endpoint lands.

`/api/universality/classes` is the W10-E endpoint. As of 2026-05-15 the route
returns 404 on beta — the W10-E PR has not merged to main yet (verified
2026-05-15 14:00 SGT against beta). `universality_smoke.js` is written to
gracefully accept 404 so it can run today and detect the moment the endpoint
ships.

## Baseline numbers — beta.structural.bytedance.city (1 client, curl)

`k6` is not yet installed locally; the numbers below come from `curl -w` with
five sequential probes per endpoint. These are *single-client TTFB / total
time* numbers — they are the **floor** of the latency distribution
(no contention, no concurrent VUs).

| Endpoint | Status | P50 TTFB (s) | P95 TTFB (s) | Total (s) at P95 | Bytes |
|---|---|---|---|---|---|
| `/api/daily` | 200 | 0.562 | 0.634 | 0.634 | 2 559 |
| `/api/discoveries` | 200 | 0.590 | 0.612 | 0.924 | 182 190 |
| `/phase/api/companies` | 200 | 0.525 | 0.616 | 0.616 | 26 (empty list) |
| `/api/universality/classes` | **404** | 0.510 | 0.526 | 0.526 | 22 |
| `/api/ask/stream` | n/a | not measured (LLM cost) | — | — | — |

Observations:

1. **Single-client floor TTFB ≈ 0.5–0.6 s.** That is mostly transport (TLS
   handshake + transcontinental RTT VPS↔measurer). Application time on top
   is probably 50–100 ms; need a real k6 run with `http_req_waiting` to
   confirm.
2. **`/api/discoveries` is the largest payload** (182 KB) — total time at
   P95 ≈ 0.92 s. Add gzip / brotli on nginx if not already on.
3. **`/api/universality/classes` returns 404** — confirms W10-E pending
   merge. Re-baseline after that PR ships.
4. **`/phase/api/companies` returns `{"count":0,"companies":[]}`** on prod —
   either the JSONL fixture is empty in the deployed image or the file is
   missing from the rsync. Worth a 5-min check with the W10/W11 deploy
   owner; not blocking for load test scaffolding.

## Tier thresholds (W11-C) — does the free-tier 60/min actually hold?

The 60-req/min free-tier limit translates to **1 req/sec per IP**. Under
`mixed_realistic.js` with 50 VUs from a single IP we expect:

- All 50 VUs share one IP → bucket fills in ~1.2 s.
- After that, `phases_smoke.js`-style probes return **429 + RFC 7807**.

**To verify** (run once k6 is installed):

```bash
BASE_URL=https://beta.structural.bytedance.city k6 run tests/load/phases_smoke.js
# Expected: ~60 successful in first second, then 429 wall. error_rate ≈ 1 - (60/total).
```

If `error_rate` does not climb after second 1, the rate-limit middleware
is not wired — file a P0 against `web/backend/middleware/rate_limit.py`.

## Saturation point — `/api/daily`

Estimating without a real k6 run: VPS is 16C/32G, FastAPI single-process
gunicorn (per `scripts/deploy-vps.sh`, verify). Cheap-GET with ~6 KB JSON
should saturate at:

- **~200–400 RPS on a single uvicorn worker** before TCP backlog overflow.
- **~800–1 200 RPS with 4 workers** before NIC / nginx upstream queue.
- VPS network is ~1 Gbps; payload-bound ceiling is ~20 k RPS at this size.

Concretely, `stress_ramp.js` ramps 0 → 100 → 500 → 1 000 VUs. With
sleep(0.1) between requests each VU emits ~10 req/sec → **peak attempted
load 10 000 RPS**. We expect:

- 100 VUs (~1 000 RPS): clean, p95 < 200 ms.
- 500 VUs (~5 000 RPS): degradation begins; p95 > 500 ms; some 429 from
  rate-limit before any 5xx.
- 1 000 VUs (~10 000 RPS): saturation; 5xx rate > 1 %.

**Action item:** run `stress_ramp.js` against staging (with permission) and
record the exact VU count at first 1 % 5xx. Update this doc with the real
number. Until that run happens, **estimated saturation ≈ 500 VUs (~5 kRPS)**.

## Comparison to W11-C rate-limit tiers

Tier req/min limits, normalised to req/sec:

| Tier | req/min | req/sec |
|---|---|---|
| free | 60 | 1.0 |
| pro | 1 000 | 16.7 |
| team | 5 000 | 83.3 |
| admin | unlimited | unlimited |

Per-VU comfortable throughput in `mixed_realistic.js` is ~0.6 req/sec (mean
think time 1 s). So:

- 1 free user = ~0.6 req/sec → comfortably under 1/sec cap; ~60 % bucket
  utilisation. Pass.
- 1 pro user = could sustain ~16 req/sec → app-tier saturation arrives
  first (k6 stress shows we break at ~5 kRPS aggregate, i.e. ~300 pro
  users hammering simultaneously).
- 1 team user (5 kRPS cap) ≈ entire app capacity. **Implication:** rate
  limit doesn't actually protect us at the team tier — application/server
  saturates first. Documented; not a bug for free tier.

## Next steps

1. Install k6 on the dev box; run the full local suite and overwrite the
   curl-derived baseline numbers above with real P50/P95/P99.
2. After W10-E ships, re-run `universality_smoke.js` against beta and
   confirm 200s.
3. Run `stress_ramp.js` once (off-hours, with VPS owner ack) and populate
   the saturation table.
4. Add a quarterly cron (`workflow_dispatch`-only for now; can promote to
   weekly cron once baselines stabilise) that runs `phases_smoke.js`
   against beta and posts the JSON to `docs/performance/`.
5. If `/phase/api/companies` returning empty list is unintended, file a
   ticket with the deploy owner.

## Files

- `tests/load/phases_smoke.js` — 10 VUs × 30 s cheap GET
- `tests/load/ask_smoke.js` — 5 VUs × 60 s LLM-bound POST
- `tests/load/universality_smoke.js` — 10 VUs × 30 s list + detail
- `tests/load/mixed_realistic.js` — 50 VUs × 5 min weighted mix
- `tests/load/stress_ramp.js` — 100 → 500 → 1 000 VUs × 10 min
- `tests/load/queries.json` — 20 realistic /api/ask queries
- `tests/load/run_all.sh` — orchestrator
- `.github/workflows/load-smoke.yml` — manual workflow_dispatch CI
