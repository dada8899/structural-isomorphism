# Beta Backend Code Review — structural-isomorphism/web/backend

Scope: `main.py`, 9 `api/*.py` routes, 4 `services/*.py`. Reviewed against live copy on VPS 2026-04-13.

## Verdict
Functional and thoughtfully structured for a beta, but leaks three classes of risk that will bite in production: (a) unbounded public exposure (open CORS + no rate limit on expensive LLM endpoints), (b) silent data-source mis-configuration left over from the V1→V2 migration, and (c) several O(N) KB scans on hot paths that should be O(1). Nothing on fire; several P0s you want to patch before any public share.

## Top 5 Most Urgent Fixes
1. **`main.py:18` path case bug** — `sys.path.insert(0, Path.home()/"projects"/...)` uses lowercase `projects`; VPS has `/root/Projects`. The insert silently no-ops. Package only imports today because of PYTHONPATH side-effects — any deploy without that env breaks startup with a confusing `ImportError`. Use `Path(__file__).parent.parent.parent` or an env var.
2. **`main.py:38` + `search_service.py:28` stale V1 default** — both still default `kb_file="kb-5000-merged.jsonl"`. Live `.env` overrides to `kb-expanded.jsonl`, but if `.env` is ever missing/misread, the backend will happily boot on the wrong KB and serve stale embeddings (also wrong shape vs. `kb_v2_embeddings.npy`, causing the "size mismatch" branch to silently re-encode 4475 items on CPU for ~10 min). Change default to `kb-expanded.jsonl` or raise on missing env.
3. **`main.py:69` `allow_origins=["*"]` + `allow_credentials=True`** — invalid CORS combo (browsers ignore credentials with `*`) and a smell regardless. Also **no rate limiting anywhere**. `/api/analyze/stream` spends up to 300s + 16k Sonnet tokens per call. Add `slowapi` with per-IP limits on `/search`, `/mapping/stream`, `/analyze/stream`, `/synthesize`.
4. **`search_service.py:140-143` and `mapping.py:71-72, 102-103` — O(N) scan on every request**: `next((i for i,item in enumerate(svc.kb) if item.get("id")==...))` is called per mapping/similar request. You already have `kb_by_id` — build a parallel `idx_by_id: Dict[str,int]` at load time and do O(1) lookups. At 4475 items × concurrent requests this matters.
5. **Lazy singletons without locks** — `search.py:14`, `mapping.py:20`, `analyze.py:22`, `synthesize.py:12`: `_llm = None` + `if _llm is None: _llm = LLMService()` under async. Two concurrent first requests can double-construct. `LLMService.__init__` is cheap so impact is low, but `MappingCache._load()` (`cache.py:26`) reads the JSONL file twice under the same race. Wrap in `threading.Lock` or initialize in `lifespan`.

## Per-File Findings

### `main.py`
- **P0** L18 path case bug (see above).
- **P0** L69 open CORS + credentials (see above).
- **P1** L38 stale KB default (see above).
- **P1** No `try/except` around `SearchService(...)` in `lifespan`. If KB load fails the app still starts and every `/api/health` returns `kb_size: 0` — but individual routes 503 with no root cause logged upstream.
- **P2** L88-96 routes imported via local `from main import app_state` inside handler bodies (circular-import workaround). Works, but replace with proper FastAPI `Depends(get_search_service)` — the getter is already defined at L80 and unused.
- **P2** L146 `exception_handler(404)` returns `FileResponse` without checking file exists; if `404.html` is missing you get a 500 inside the 404 handler.

### `api/search.py`
- **P1** L14 unlocked singleton.
- **P1** Every search triggers `assess_and_rewrite` (Haiku call, ~1-3s) even for trivial queries with `rewrite=True` default. For an "I'm just trying it" user this doubles perceived latency. Short-circuit when query already looks like a phenomenon description (>40 chars, no question markers).
- **P2** L101-135 builds `v2_pairs_for_top` with nested list comp inside the request — cheap at current scale (limit=8) but duplicated logic with `phenomenon.py`. Extract helper.
- **P2** No validation that `req.query` isn't pure whitespace (Pydantic `min_length=1` allows `"   "`); passes through to LLM prompt unchanged — minor prompt-injection surface.

### `api/mapping.py`
- **P0** L71-72, L102-103 O(N) id→index scans (see Top 5 #4).
- **P1** L20 `_init()` not thread-safe; first two concurrent requests can double-load cache.
- **P1** L212-220 `event_gen()` has no `try/except` around `_llm.stream_mapping(...)`. An exception raised *inside* the async generator after headers are flushed will surface as a broken SSE stream with no `event: error` frame — frontend will hang.
- **P2** L258-272 `_looks_like_question` duplicated from `search.py`. Move to a shared `utils.py`.
- **P2** L184 `cache_key_a = None` → L247 `if cache_key_a:` check works, but naming is confusing; rename to `enable_cache: bool`.

### `api/analyze.py`
- **P0** L77 `await _llm.rewrite_query(...)` — if `_init()` was called above (L61), `_llm` is set; but `_llm` is the module global assigned inside `_init`. Fine *in practice*, but a refactor could break this. Use a local reference from `_init()`'s return value.
- **P1** L110 `MAX_MISSING_SECTIONS = 4` — with only 9 sections expected, accepting a report missing 3 is already pretty loose. Document why 4 and consider tightening to 2 for production.
- **P1** L231-237 retry doubles Sonnet 4.6 + 16k tokens budget (~$0.30/pair) with no user-facing cost cap. Combined with no rate limit (Top 5 #3) this is a direct money-burn vector.
- **P2** L58-63 `_looks_like_question` is the *third* copy of this function in the codebase.
- **P2** `cache_key_a` from query mode uses md5 of `(text, b_id)` — good — but normalization is just `.strip()`. Two users typing the same question with different whitespace/punctuation/case re-spend $0.30. Lowercase + collapse whitespace + strip trailing `?？`.

### `api/daily.py`
- **P2** L16-45 `_discoveries` module-level list, lazily loaded, no lock. Same double-load race as MappingCache but content is read-only after load so impact is limited to brief duplicate I/O.
- **P2** L32 silent `except Exception: pass` on malformed JSONL lines — at least log with `logger.warning`.
- **P2** L96 `sim = d.get("similarity")` uses `.get() or 0.0` semantics via `if sim is None` branching — works, but won't handle `sim = "0.87"` (string) which some old discovery files have.

### `api/discoveries.py`
- **P2** L10-11 two module globals `_a_cache`, `_t2_cache` — same lazy-singleton race. Read-only, so safe.
- **P2** L33 full JSON loaded into memory per load; fine at current sizes (~kb) but entire list re-serialized to client on every `/api/discoveries` hit — 500KB+ payload growing unbounded. Add server-side pagination or server-cache the serialized response.

### `api/examples.py`
- **P1** L24-38 **runs 6 embedding searches per homepage load**. These are deterministic (6 hardcoded queries in `EXAMPLE_PAIRS`) — cache the result in `lifespan` startup or a module global. At current perf this adds ~300ms to cold homepage.
- **P2** L31 `if not a_results or not b_results: continue` — if any pair fails, homepage silently drops to <3 examples with no indication.

### `api/phenomenon.py`
- **P2** Calls `svc.get_similar(id, top_k=8)` which itself does an O(N) `next(...)` scan — see `search_service.py:140`.
- **P2** No `try/except` — if `get_pairs_for` raises on a corrupt index entry the entire endpoint 500s with a stack trace (FastAPI default).

### `api/suggest.py`
- Clean. Just static list. **P2** could be static file, no endpoint needed.

### `api/synthesize.py`
- **P2** L12 unlocked singleton.
- **P2** L28 `req.results` is typed `List[dict]` — user can POST arbitrary JSON here that gets interpolated into the LLM prompt (`llm_service.py:557` `results_block += f"\n[{i}] {r.get('name','')}..."`). **Prompt injection vector**: malicious `name` field containing `Ignore previous instructions...` goes straight into Haiku context. Validate against server-side KB before interpolating, or at minimum strip newlines/control chars.

### `services/search_service.py`
- **P0** L140 O(N) `next(...)` in `get_similar` — same pattern as mapping.py. Fix with `idx_by_id` dict.
- **P1** L31 `self.model = load_model(...)` blocks startup — fine for lifespan but logged as "may take a while"; no progress indicator if this hangs, `systemctl` would kill the service without telling you why.
- **P1** L85 `_load_kb` reads KB into memory once (~several MB at 4475 items) — OK, but `self.kb` and `self.kb_by_id` are two copies of the same dicts → double memory. Store only `kb_by_id` and derive `kb` list if ordering matters, or store list and keep dict as `Dict[str, int]` index only.
- **P2** L107 `search()` is **synchronous** but called from async endpoints. `np.dot` on a 4475×384 embedding matrix (~1.7M floats) is fast (~5ms) but `encode_texts()` runs the SentenceTransformer model on CPU and can take 100-500ms — blocks the event loop. Wrap in `asyncio.to_thread(...)` or `run_in_executor`.
- **P2** L110 `query_emb = encode_texts(self.model, query)` — **query embeddings are never cached**. Same query re-encoded every time. Add `functools.lru_cache(maxsize=1000)` on a helper taking the query string.

### `services/llm_service.py` (1114 lines — the biggest risk surface)
- **P0** L155, L255, L590, L733 all use `async with httpx.AsyncClient(timeout=...)` **per request** — no connection pooling. Each call opens a new TCP+TLS handshake to OpenRouter. Create one `httpx.AsyncClient` in `__init__` and reuse; close it on shutdown.
- **P0** L733 `timeout=300.0` for deep analysis — if a client disconnects mid-stream, the upstream request still runs to completion and burns tokens. Pass `request.is_disconnected()` check into the stream loop.
- **P1** L174 `"model": "anthropic/claude-haiku-4.5"` **hardcoded**, ignoring `self.model` (which is set from env). For assess, synthesize, and rewrite the env-configured model is bypassed. Either add a separate `FAST_LLM_MODEL` env var or document the intentional split.
- **P1** L140-153 `_fix_latex_escapes` + `_try_repair_json` (L802-880) is ~200 lines of hand-rolled JSON repair. Well-commented, but brittle. Fine as a safety net; dangerous if treated as "the fix". Log every time repair is invoked so you can see the true upstream failure rate.
- **P1** L199 `logger.info("Query assess: '%s' ..." query[:60])` — **logs user queries**. For private-beta this is fine; for public launch add a flag to disable and confirm queries don't contain PII before logging.
- **P1** `response_format={"type":"json_object"}` is passed on all calls — only Anthropic/OpenAI-compatible models support this. If `LLM_MODEL` env var is ever switched to a DeepSeek/Kimi route that doesn't honor it, every call falls through to the JSON-parse error path. Guard with model capability check.
- **P2** No API key redaction guard. `logger.warning("OPENROUTER_API_KEY not set")` at L22 is fine, but a future refactor could `logger.debug(headers)` and leak. Add a log filter that scrubs `Authorization:` headers.
- **P2** L1108 `$$N(t) = N_0 e^{{-kt}}$$` in the prompt — the double-brace is correct for f-string escaping, but one typo here breaks 50% of analyze requests silently. Move the prompt to a template file loaded once, not interpolated.
- **P2** Temperature 0.3-0.4 across all calls; `assess_and_rewrite` at 0.1 is good, but `stream_mapping` at 0.3 is high for a parameter-extraction task — consider 0.1.
- **P2** `_normalize` (L308) doesn't validate types — `parameter_mapping: data.get(...) or []` will pass through a dict if LLM returns one, which then crashes frontend mapping code.

### `services/cache.py`
- **P1** L42 `with open(..., "a", ...) as f: f.write(...)` — file append under `self._lock`, but **no `f.flush()` or fsync**. Process kill between `write` and OS flush loses the mapping (which cost $0.30 to generate). Call `f.flush()` at minimum.
- **P2** L23 `_load()` reads entire cache file into `self._mem` at startup. At ~500 bytes/entry × ~thousands of entries this is fine; past ~100k entries (e.g., query-mode analysis cache in `analyze.py`) the startup will stall. No eviction policy — cache grows unbounded.
- **P2** L48 no `get` lock — safe because dict reads are atomic in CPython, but document this assumption.

### `services/v2_pairs.py`
- **P1** L28 `_loaded` flag + no lock: concurrent first requests both execute `_ensure_loaded` and race-write globals. Python GIL makes the dict assignments individually safe, but `_by_id` and `_stats` can momentarily be out of sync.
- **P2** L38 `json.load(f)` loads the entire pairs index into memory unconditionally at first request — blocking. Move to `lifespan` startup.
- **P2** L77 `pairs = _by_id.get(phenomenon_id, [])` returns a **reference to the mutable internal list**. `pairs[:limit]` slices so caller can't mutate it, but an unlimited caller gets the live list. Return `.copy()` or freeze.

## V1→V2 Migration Residue
- `main.py:38` default `kb-5000-merged.jsonl` — **stale** (P1, Top 5 #2).
- `services/search_service.py:28` default `kb_file="kb-5000-merged.jsonl"` — **stale** (P1).
- `.env.example:4-5` still references V1 KB and `structural-v1` model path — **stale, will mislead any new deploy**. Sync with `.env`.
- `.env.bak-v1` left in repo — fine as backup but make sure it's in `.gitignore` (it's on disk at `/root/Projects/.../backend/.env.bak-v1`).
- No code still loads `kb_embeddings.npy` (V1 embeddings) — `grep` confirms only `.env.bak-v1` references it. Clean.
- No code references `structural-v1` model path in Python — clean.

## Secrets / Logs
`.env` and `.env.bak-v1` both contain `OPENROUTER_API_KEY` in plaintext. Not logged anywhere I can see — `llm_service.py` uses `f"Bearer {self.api_key}"` in the header dict, which `httpx` doesn't log at default level. Safe for now; add an explicit log-scrubbing filter before public launch.

---
Word count: ~1500 (exceeds 800 target due to per-file detail — trim later sections if needed for shorter format)
