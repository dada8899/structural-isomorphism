# Beta Structural API Review

Tested 2026-04-13 against `http://127.0.0.1:5004` on VPS (proxied via `https://beta.structural.bytedance.city`). KB size = 4443, LLM = `anthropic/claude-sonnet-4.6`.

## Endpoint Inventory

| Method | Path | Status | Latency (cold) | Notes |
|---|---|---|---|---|
| GET | `/api/health` | OK | 1ms | Returns `{status, kb_size, llm_model}` |
| GET | `/api/suggest` | OK | 1ms | Static list of 7 suggestions |
| GET | `/api/examples` | OK | 1ms | 3 hand-picked pairs, server-precomputed |
| GET | `/api/discoveries` | OK | 8ms | A-grade=39, tier2=75, full payload 124KB |
| GET | `/api/daily` | OK | 1ms | 3 picks, deterministic by date |
| GET | `/api/phenomenon/{id}` | OK | 15ms | Returns phenomenon + similar + same_structure + v2_pairs |
| POST | `/api/search` | OK | **15s** w/ rewrite, 50ms w/o | LLM rewrite is the bottleneck |
| POST | `/api/mapping` | OK | **37s** cold, 1ms cached | LLM call, JSONL cache works |
| GET | `/api/mapping/stream` | OK | **38s** query mode | SSE; cache hit instant |
| GET | `/api/analyze/stream` | OK | 30-90s | SSE 9 sections; has retry logic |
| POST | `/api/synthesize` | OK | **23s** | LLM call, no cache layer |

## Bugs

### P0 — None
No 500s, no crashes, no data corruption observed.

### P1 — Schema/Behavior Issues

1. **`similarity` field is wrong by ~10x.** `meta` events from `mapping/stream` and `analyze/stream` report `similarity: 9.5258` for `soc-076` ↔ `5k-ef-238`. Computed as `np.dot(emb_a, emb_b)` in both `api/mapping.py:74` and `api/analyze.py:97`. If embeddings are L2-normalized this should be ≤ 1.0; values >1 mean the embeddings are NOT normalized but the code treats the dot product as "similarity". Same defect in `/api/daily` where `similarity: 0.0092 / 0.0082 / 0.0085` is shown — those numbers come from `isomorphism_confidence/100` fallback when the v2 results file is absent, but tier2 confidences are stored as 0-1 already, producing absurdly low displayed values.
   - Fix: pick one normalization (cosine in [0,1]) and apply consistently across daily/mapping/analyze. For daily, detect whether `confidence` is 0-1 or 0-100 before dividing.

2. **404 on JSON API path returns the HTML 404 page** (verified on `/api/phenomenon/nonexistent-id-999` and `/api/mapping` with bad id). The route raises `HTTPException(404)`, but the global `@app.exception_handler(404)` in `main.py:130` unconditionally serves `404.html`. API consumers get a 60-line HTML blob instead of `{"detail": "..."}`.
   - Fix: branch on `request.url.path.startswith("/api")` in the handler and return `JSONResponse({"detail": exc.detail}, status_code=404)`.

3. **`/api/search` with `rewrite=true` consistently takes 14-15s.** Single query "为什么所有排行榜都是头部通吃" → 14.79s; English equivalent → 15.15s. The LLM `assess_and_rewrite` runs on every search even when not needed. P95 user wait time will be >15s — well above the 5s threshold.
   - Fix: stream the rewrite result OR move rewrite to client-triggered "improve query" button OR use a faster model (Haiku) for rewrite while keeping Sonnet for synthesize/mapping.

### P2 — Quality / UX

4. **Search relevance is poor without rewrite.** Query "为什么所有排行榜都是头部通吃" with rewrite returned: 钢桥的疲劳细节分类, 生态位分化, 量子加速的边界, 乳化作用, 期权做市商. None of these match "winner-takes-all". The rewritten version is good Chinese but the embedding still mis-retrieves. Suggests the embedding model isn't well-aligned with the rewritten phrasing.

5. **Whitespace-only query (`"   "`) returns `count: 0` with HTTP 200**, no error or hint. Frontend must handle empty results gracefully or backend should `query.strip()` and 400.

6. **Junk-character query `!@#$%^&*()_+`** with rewrite=false returns 5 random results scoring 8.9-9.5 (参照群体剥夺感, 湿壁画的即时性约束, 第三人效果). No score floor — every query produces "matches" even when the input is meaningless.
   - Fix: add a minimum-score threshold (e.g. `score > 6`) or use the `assessment.worth_score` to suppress junk.

7. **`/api/synthesize` always calls LLM (23s), no cache.** Mapping has a JSONL cache; synthesize doesn't. Same `(query, top results)` pair will pay 23s every time.

8. **`/api/examples` runs 6 KB searches per request synchronously** (3 pairs × 2). At ~50ms each it's fine now but it's the homepage hot path — should be precomputed at startup or cached for the process lifetime.

9. **`mapping/stream` query-mode similarity 9.13** for "如何提升团队效率" ↔ 飞机升力与失速 — same normalization bug as P1#1, but additionally the value is meaningless to surface to users (UI shows it as a percentage).

10. **`/api/analyze/stream` retry logic is good, but no client-visible timeout.** First-pass 6.8KB / 15s slice I captured was incomplete JSON. Spec says retry on parse fail, but two full Sonnet calls back-to-back can mean 60-90s wait. Add a timeout cap and a "this is taking longer than usual" event.

## Validation Behavior (good)

- Pydantic input validation works: empty `query` → 422, `query` >500 chars → 422, `top_k` >30 → 422.
- Service-not-ready guards (`503`) exist on all routes.
- Mapping cache hit returns in 1.4ms with `from_cache: true`.
- SSE `meta` event arrives before LLM stream so frontend can render headers immediately.

## Recommended Fix Priority

1. Fix the global 404 handler so `/api/*` returns JSON (10 LOC, P1#2).
2. Normalize all `similarity` fields to cosine-in-[0,1] across daily/mapping/analyze (P1#1, P2#9).
3. Move LLM rewrite off the critical path of `/api/search` or switch to Haiku — 15s p95 is the single biggest UX problem (P1#3).
4. Add a score floor on `/api/search` so junk queries return 0 results instead of fake matches (P2#6).
5. Add a synthesize cache keyed by `(query_hash, top_ids)` (P2#7).
6. Precompute `/api/examples` payload at startup (P2#8).

## Backend File References

- `/root/Projects/structural-isomorphism/web/backend/main.py` — app, lifespan, 404 handler (line 130)
- `/root/Projects/structural-isomorphism/web/backend/api/search.py` — POST /api/search
- `/root/Projects/structural-isomorphism/web/backend/api/mapping.py:74` — similarity calc
- `/root/Projects/structural-isomorphism/web/backend/api/analyze.py:97` — similarity calc
- `/root/Projects/structural-isomorphism/web/backend/api/daily.py:84-89` — confidence/100 fallback
