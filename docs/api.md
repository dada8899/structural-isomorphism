# API

The hosted Phase Detector exposes two endpoints. See
[Phase Detector](phase-detector.md) for the architectural overview.

## `POST /api/ask`

Synchronous fit. Returns the full result table in one response.

### Request

```json
{
    "sizes": [<size_1>, <size_2>, ...],
    "discrete": true,
    "alternatives": ["lognormal", "exponential"]
}
```

- `sizes`: list of positive numbers, the event sizes. Must contain at
  least 50 entries; the free tier rejects requests with more than 5000.
- `discrete`: boolean. If true, the fit uses the discrete Clauset
  estimator. Set to true for integer-valued data (avalanche sizes,
  star counts, page views).
- `alternatives`: list of alternatives to compare against. Currently
  `lognormal` and `exponential` are supported.

### Response

```json
{
    "verdict": "PASS | INCONCLUSIVE | FAIL",
    "alpha": 1.92,
    "ci": [1.55, 2.31],
    "x_min": 8,
    "n_tail": 7,
    "vuong": {
        "lognormal": {"R": -0.41, "p": 0.68},
        "exponential": {"R": 0.34, "p": 0.73}
    },
    "comment": "<diagnostic note, e.g. about n_tail or band proximity>"
}
```

## `POST /api/ask/stream`

Streaming fit. Returns Server-Sent Events with seven event types. See
[Phase Detector](phase-detector.md) for the full event catalog.

### Request

Identical to `/api/ask`.

### Response

`Content-Type: text/event-stream`. Each event has the form:

```
event: <event_type>
data: <JSON payload>
```

Event types in order: `task_received`, `data_ingested`,
`xmin_search_start`, `xmin_found`, `bootstrap_running`,
`vuong_complete`, `verdict`.

## Authentication and rate limits

The current public deployment is open access with per-IP rate limiting:

- Free tier: 60 requests per hour, $n \leq 5000$, default bootstrap
  iterations.
- Authenticated tier: 600 requests per hour, $n \leq 50000$,
  configurable bootstrap iterations up to 5000.

Authentication uses bearer tokens. To request a token, open an issue
on the repository.

## Errors

Errors are returned as JSON with an `error_code` and a human-readable
`message`:

```json
{
    "error_code": "INPUT_TOO_SHORT",
    "message": "sizes must contain at least 50 entries; got 12"
}
```

The error codes are stable and documented in
`web/backend/api/errors.py`.
