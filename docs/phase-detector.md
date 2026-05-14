# Phase Detector

The Phase Detector (codename **D1**) ships the shared pipeline as a
queryable service. The intended audience is researchers and engineers who
want to drop a size vector or time series into a hosted endpoint and get
back a verdict (PASS / INCONCLUSIVE / FAIL), a fitted exponent with
confidence interval, and the diagnostic alternative-fit comparisons —
without standing up the Python pipeline locally.

## Architecture

The detector is a thin FastAPI service in `web/backend/` that wraps the
shared library. The request path is:

```
client  ──POST /api/ask──▶  orchestrator  ──▶  soc_pipeline.fit_*
                                │
                                └──▶  vuong_lr  ──▶  verdict  ──▶  JSON
```

For long-running fits, the orchestrator streams seven Server-Sent Events
back to the client (the "7-event SSE orchestrator"):

1. `task_received` — request acknowledged.
2. `data_ingested` — size vector parsed; basic sanity checks pass.
3. `xmin_search_start` — Clauset KS-optimal $x_{\mathrm{min}}$ search starts.
4. `xmin_found` — search converged; $x_{\mathrm{min}}$ reported.
5. `bootstrap_running` — block bootstrap underway with progress fraction.
6. `vuong_complete` — likelihood-ratio tests done.
7. `verdict` — final PASS / INCONCLUSIVE / FAIL with the full result table.

The SSE design is the same one used in the Perplexity-like answer
streamer; see the orchestrator implementation in
`web/backend/services/ask_orchestrator.py` for the canonical event schema.

## Usage

The hosted endpoint is rate-limited per tier. The free tier accepts
size vectors up to $n = 5000$; the paid tier accepts $n = 50000$ and
exposes the bootstrap-iteration count as a request parameter.

### Streaming endpoint

```bash
curl -N -X POST https://api.structural-isomorphism.org/api/ask/stream \
    -H "Content-Type: application/json" \
    -d '{
        "sizes": [3, 5, 8, 13, 21, 34, 55, 89, 144, 233],
        "discrete": true,
        "alternatives": ["lognormal", "exponential"]
    }'
```

The response is an `event-stream` of the seven events listed above.

### Synchronous endpoint

For small inputs and quick checks the synchronous endpoint returns the
full result table in one response:

```bash
curl -X POST https://api.structural-isomorphism.org/api/ask \
    -H "Content-Type: application/json" \
    -d '{
        "sizes": [3, 5, 8, 13, 21, 34, 55, 89, 144, 233],
        "discrete": true
    }'
```

```json
{
    "verdict": "INCONCLUSIVE",
    "alpha": 1.92,
    "ci": [1.55, 2.31],
    "x_min": 8,
    "n_tail": 7,
    "vuong": {
        "lognormal": {"R": -0.41, "p": 0.68},
        "exponential": {"R": 0.34, "p": 0.73}
    },
    "comment": "n_tail < 50; Vuong test has limited power per Clauset 2009 §6.3."
}
```

## What the detector does not do

- **It does not pre-register predictions for you.** If you want a
  pre-registered verdict, write a YAML against the schema in
  `v4/preregistration/` and commit it before fetching data. The detector
  will then consume the YAML; see
  [Pre-registration methodology](methodology/pre-registration.md).
- **It does not adjudicate the universality class.** Membership of a
  system in a universality class requires more than a power-law tail —
  see [Cross-judge ensemble](methodology/cross-judge.md) for the
  taxonomy review that the detector explicitly delegates to.

## Self-host

The detector is open source. To run locally:

```bash
cd web/backend
uvicorn main:app --reload --port 8000
```

The SSE endpoint is then at `http://localhost:8000/api/ask/stream`.
