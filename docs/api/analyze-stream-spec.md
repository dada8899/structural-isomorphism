# `/api/analyze/stream` — Specification

**Version**: 1.1 (M1.4)
**Status**: Stable
**Last updated**: 2026-05-21

---

## 0. Overview

`GET /api/analyze/stream` — server-sent events (SSE) endpoint that produces a 9-section structural-isomorphism research report. Operates in two modes (Query / Pair). Session #16 added optional persistence (`persist=1`) so a generated report can be saved with a share token.

Implementation: `web/backend/api/analyze.py`
Companion endpoints: `/api/report/*` (see `report-endpoints-spec.md`)

---

## 1. Modes

### 1.1 Query mode

Semantic: "Borrow an answer from KB to my own free-text question."

- **SOURCE (a)** = KB phenomenon retrieved by `b_id`
- **TARGET (b)** = the user's question text

```
GET /api/analyze/stream
  ?b_id=<KB_phenomenon_id>          (required)
  &text_a=<user's free text>         (required for query mode)
  &lang=zh|en                        (optional, default: zh)
  &persist=0|1                       (optional, default: 0)
```

### 1.2 Pair mode

Semantic: "Show me the deep structural comparison between two KB phenomena."

- **SOURCE (a)** = `a_id`
- **TARGET (b)** = `b_id`

```
GET /api/analyze/stream
  ?b_id=<KB_phenomenon_id>          (required)
  &a_id=<KB_phenomenon_id>          (required for pair mode)
  &lang=zh|en                        (optional, default: zh)
  &persist=0|1                       (optional, default: 0)
```

### 1.3 Validation

- `b_id` is always required.
- Exactly ONE of `text_a` / `a_id` must be provided; supplying both makes `text_a` win (query mode is preferred).
- `b_id` (and `a_id` if given) must resolve to a KB row, else 404.

---

## 2. Headers

| Header | Required | Used for |
|---|---|---|
| `X-Anon-Id` | optional | When `persist=1`, written to `reports.creator_anon_id`; later used to filter `/api/reports/mine`. |
| `X-API-Key` | optional | Tier classification (free / pro / team / admin). Affects rate limit + persistence-policy in future versions. |
| `X-Forwarded-Host` / `X-Forwarded-Proto` | server-side | Used by analyze.py to build the `share_url` returned in the `persisted` event. |

---

## 3. Response — SSE event sequence

All events are SSE-formatted (`event:` + `data:` lines, blank-line separated). All payloads are UTF-8 JSON.

### 3.1 Always emitted (in order)

| # | Event | Payload | Notes |
|---|---|---|---|
| 1 | `meta` | `{a, b, similarity, is_query_mode}` | One-time. `a` / `b` are KB rows or user-question stubs (query mode); `similarity` is cosine in [0, 1]. |
| 2..n | `section` | `{key, data}` | One per completed top-level section. 9 expected (see §4). |
| n+1 | `text` | `{content, total_length}` | (optional, raw LLM stream chunks; clients can ignore) |
| n+2 | `persisted` | `{id, share_token, share_url, created_at, is_partial}` | Only when `persist=1`. Always BEFORE `done`. |
| last | `done` | `{report, from_cache}` | Terminal event. `report` = the full 9-section dict, `from_cache` = whether cache hit. |

### 3.2 Conditional events

| Event | Payload | When |
|---|---|---|
| `retry` | `{reason}` | First-pass report failed quality check; second pass is starting. |
| `error` | `{message, retryable}` | Second pass also failed; `done` follows with a fallback report. |

### 3.3 Event semantics — guarantees

- `meta` is ALWAYS the first event.
- `done` is ALWAYS the last event (even after errors).
- `persisted`, when present, is ALWAYS before `done` and ALWAYS exactly once.
- `section` events are emitted incrementally as the LLM streams completed top-level JSON keys.
- A section key is never emitted twice within the same stream.
- Order of `section` events is the order the LLM produces them (typically — but not guaranteed — the canonical 9-section order in §4).

---

## 4. The 9 sections (canonical order)

| Key | Type | Purpose |
|---|---|---|
| `shared_structure` | object | The structural pattern shared by SOURCE & TARGET. Fields: `name`, `formal_expression`, `intuition`. |
| `your_problem_breakdown` | object | Restate TARGET in structural terms. Fields: `summary`, `key_variables`, `dynamics`, `why_stuck`. |
| `target_domain_intro` | object | Background on SOURCE's home domain. Fields: `domain_name`, `corresponding_phenomenon`, `key_thinkers`, `mature_tools`. |
| `structural_mapping` | object | The actual SOURCE → TARGET mapping. Fields: `rationale`, `parameter_map`. |
| `borrowable_insights` | array | List of transferable insights. |
| `how_to_combine` | object | Actionable application. Fields: `steps`, `assumptions_to_verify`, `boundary_conditions`. |
| `research_directions` | object | Where to go next. Fields: `literature_status`, `if_novel_opportunity`, `suggested_references`. |
| `risks_and_limits` | object | Where the analogy breaks. Fields: `failure_cases`, `boundary_conditions`. |
| `action_plan` | object | Concrete next steps. Fields: `immediate_actions`, `3_month_goals`, `12_month_vision`. |

`MAX_MISSING_SECTIONS = 4` triggers a retry: if ≥ 4 of the 9 are absent, the first pass is considered incomplete.

---

## 5. The `persisted` event (M1.4)

When `persist=1`, exactly one `persisted` event is emitted right before `done`.

```jsonc
{
  "id":          "r_abc123def456abcd",  // 18 chars
  "share_token": "32-hex-char-hmac-token",
  "share_url":   "https://<host>/report/share/<token>",
  "created_at":  "2026-05-21T03:14:15.123456Z",
  "is_partial":  false
}
```

- `id` is opaque and stable.
- `share_token` is `HMAC-SHA256(id, STRUCTURAL_SHARE_TOKEN_SECRET)[:32]`. Anyone with the token can read via `GET /api/report/share/{token}` without auth.
- `share_url` is fully qualified (honours `X-Forwarded-Host` / `X-Forwarded-Proto`).
- `is_partial` is `true` when the report is a fallback / has missing sections — clients should dim the "Share" button.

### Persist on cache hit

When cache hits, the report is still persisted IF `persist=1` — each user gets a fresh `r_` id and share token. Payload contents may match a previous row's exactly; that's acceptable v1 behaviour.

### Failure handling

Persistence failure is logged but NEVER tears down the SSE stream — the report itself is what the user came for. Clients should:
1. Treat missing `persisted` event as "share feature unavailable for this report" (do NOT retry the whole stream).
2. Fall back to the in-memory report payload from `done`.

---

## 6. Caching

The report is cached by `(query_hash | a_id, b_id, lang)`:

- Query-mode key: `q_<md5(query, b_id, lang)[:16]>`
- Pair-mode key: `<a_id>` (zh) or `<a_id>__en` (en, legacy zh stays unsuffixed)

Cache hits skip the LLM call entirely (≪ 1s response). Fallback sentinels (`shared_structure.name == "结构分析暂不可用"` / `"Structural analysis unavailable"`) are NEVER cached so users always re-roll a bad report.

---

## 7. Latency

Real-prod data (2026-05-21):

| Path | p50 | p95 | notes |
|---|---|---|---|
| Cache hit | < 200ms | < 500ms | network-bound |
| Live generation (`:nitro`) | ~80s | > 180s | session-#16 measurement showed 6/9 sections at 180s timeout. Tune `OPENROUTER_DEEP_ANALYSIS_TIMEOUT` if you tighten this. |

Clients SHOULD render incrementally as `section` events arrive — do NOT block on `done` alone.

---

## 8. Errors

| Status | Cause |
|---|---|
| 400 | Neither `text_a` nor `a_id` supplied. |
| 401 | `X-API-Key` header present but invalid. |
| 404 | `b_id` (or `a_id` in pair mode) not in KB. |
| 503 | Search service still loading (cold start). |

SSE-level errors (LLM timeout / parse failure) are reported via the `error` event followed by `done` with a fallback report — the HTTP status stays 200.

---

## 9. Versioning

- Wire format is versioned by `prompt_version` (currently `v1`, written into `reports.prompt_version` on persist).
- New `section` keys may be added (additive, non-breaking).
- Removing a section or renaming one is breaking — requires bumping `prompt_version`.
- `persisted` event added in M1.4 (session #16) is purely additive — clients that don't set `persist=1` see the same SSE stream as before.

---

## 10. Examples

### 10.1 Query mode, persist on

```bash
curl -sN \
  -H "X-Anon-Id: my-anon-uuid" \
  "https://beta.structural.bytedance.city/api/analyze/stream?b_id=soc-160&text_a=如何防止用户流失&lang=zh&persist=1"
```

Expected event order: `meta` → many `text`/`section` → `persisted` → `done`.

### 10.2 Pair mode, no persist (default)

```bash
curl -sN \
  "https://beta.structural.bytedance.city/api/analyze/stream?a_id=sci-001&b_id=soc-160&lang=zh"
```

Expected event order: `meta` → many `text`/`section` → `done`. No `persisted` event.

### 10.3 Reading back a shared report

```bash
curl -s "https://beta.structural.bytedance.city/api/report/share/<token-from-persisted-event>"
```

Returns `{id, query, payload, model, created_at, view_count, is_partial, ...}` — full report JSON, no auth required.
