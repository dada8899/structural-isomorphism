# Backend Fix Report — beta.structural.bytedance.city

Date: 2026-04-14
Target file locations: `/root/Projects/structural-isomorphism/web/backend/` on VPS

## Latency — Before / After

Test query: `{"query":"为什么创业公司早期更容易创新","top_k":5}`

| Endpoint                  | Before | After  | Target |
|---------------------------|--------|--------|--------|
| `POST /api/search`        | ~5.3s  | 0.56s  | <3s    |
| `POST /api/search/assess` | n/a    | ~5.0s  | (async) |

The headline query is now under 600ms. The LLM assessment runs in parallel from
the frontend and no longer blocks first paint.

## Strategy — Option B (two-phase)

Split `/api/search` into a fast vector path and an independent LLM pre-flight.
Frontend fires both via `Promise.all`, renders results on search return, and
then either (a) overlays the low-fit coaching gate, or (b) re-runs search with
the LLM-rewritten query and swaps in higher-quality rankings. This preserves
the quality gain from query rewriting without blocking the first paint.

## Fixes Landed

### P0 — latency
1. `api/search.py` — `rewrite` default flipped to `False`; assessment returns
   `{"pending": true}`. New `POST /api/search/assess` endpoint for the LLM gate.
2. `services/search_service.py` — added per-instance `lru_cache(1024)` wrapper
   around `encode_texts` for single queries (`encode_query()`).
3. `web/frontend/assets/js/{api.js,search.js}` — `performSearch` now fires
   search and assess in parallel; rewrites trigger a second search to upgrade
   rankings; cache-busting version bumped to `v=20260414a`.

### P0 — 404 handler
4. `main.py` — 404 handler checks `request.url.path.startswith("/api")` and
   returns `JSONResponse({"detail":"not found"})` for API routes; HTML 404
   template still serves for page routes. Verified with curl:
   `/api/phenomenon/fake-id-xyz` → `{"detail":"not found"}`, `/fake-page` →
   HTML 404.

### P1 — security
5. `main.py` — `allow_origins` pinned to
   `https://beta.structural.bytedance.city` + `https://structural.bytedance.city`
   (extendable via `STRUCTURAL_EXTRA_ORIGINS` env). `allow_credentials=False`
   (the `*` + credentials combo was browser-invalid anyway).
6. `services/rate_limit.py` (new) — shared `slowapi` Limiter instance with a
   no-op fallback. `10/minute` per IP on `POST /api/mapping`,
   `POST /api/synthesize`, `GET /api/analyze/stream`. slowapi installed into
   the project venv.

### P1 — V1 residue
7. `main.py` — `sys.path.insert` now uses `Path(__file__).resolve().parent.parent.parent`
   (overridable via `STRUCTURAL_PROJECT_ROOT`). The old lowercase `~/projects`
   default was silently failing on VPS (caught by `PYTHONPATH` in systemd unit).
8. `main.py` + `services/search_service.py` — `kb_file` defaults updated to
   `kb-expanded.jsonl`. The running env already pointed here, but defaults
   are now correct.

### P1 — performance cheap wins
9. `services/search_service.py` — added `idx_by_id: Dict[str, int]` built at
   load time. `api/mapping.py` and `api/analyze.py` now resolve phenomenon
   indices via O(1) lookup instead of O(N) `next((i for i, item in enumerate(svc.kb)))`.
10. `api/examples.py` — module-level `_CACHED_EXAMPLES` caches the 6-search
    homepage computation on first hit.
11. `services/llm_service.py` — hoisted `httpx.AsyncClient` to a module-level
    shared instance (`_get_http_client()`) with keep-alive pool
    (`max_keepalive_connections=20`, `max_connections=50`). All 4 call sites
    (`assess_and_rewrite`, `generate_mapping`, `stream_mapping`,
    `synthesize_answer`, `stream_deep_analysis`) now reuse the pool instead
    of creating a fresh client per call.

## Verification

```
search TIME 0.56s
search (cached) TIME 0.50s
/api/phenomenon/fake-id-xyz → 404 {"detail":"not found"} (Content-Type: application/json)
/fake-page → 404 HTML
/api/search/assess TIME 4.9s (runs in parallel, non-blocking)
/api/mapping with invalid ids → 404 JSON (rate limiter decorator healthy)
Service logs clean, no traceback, no slowapi errors
```

## Deferred

None — all 10 items in the task landed. The one observation worth flagging:
without query rewriting, raw-query rankings are noticeably worse (physics
terms surface for business questions). The two-phase flow mitigates this by
re-running search with the rewritten query once the LLM returns, but the
first paint shows sub-optimal rankings for ~5s. Acceptable tradeoff — users
see something immediately, quality improves in-place.
