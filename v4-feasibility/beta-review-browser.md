# Beta Browser Functional Review — `beta.structural.bytedance.city`

**Date:** 2026-04-13
**Tester:** Claude (subagent)
**Method note (important):** A real browser session could **not** be driven. Playwright MCP refused with `Browser is already in use for /Users/wanqh/.playwright-profile` (the user's foreground Chrome PID 65239 owns the profile lock), and the claude-in-chrome extension responded `Browser extension is not connected`. As a fallback I drove the site at the HTTP/JS-source level: fetched every documented route, called every backend endpoint that `assets/js/api.js` exposes, executed all required search edge cases against `/api/search`, and read the SPA bootstraps (`search.js`, `analyze.js`, `phenomenon.js`, `responsive.css`) to determine routing/empty-state/responsive behaviour. Everything below is grounded in that probe — visual rendering, console errors, and live click flows still need a manual pass.

---

## Pages reachable (HTTP)

| Route | HTTP | Bytes | Title | Notes |
|---|---|---|---|---|
| `/` | 200 | 13318 | Structural — 万物的形状都在重复 | server-rendered shell + `home.js` hydrates `daily-grid`, `home-suggestions` |
| `/discoveries` | 200 | 4269 | 精选发现 — Structural | hydrated by `discoveries.js` from `/api/discoveries` |
| `/search` | 200 | 3080 | 搜索 — Structural | requires `?q=` query param |
| `/search?q=` (empty) | 200 | 3080 | — | `search.js:649` redirects to `/` when `q` is falsy — OK |
| `/analyze` | 200 | 7460 | 深度分析 — Structural | requires `?id=`; `analyze.js` redirects to `/` if missing |
| `/phenomenon/5k-ef-362` (real) | 200 | 3507 | 现象详情 | hydrated by `phenomenon.js` |
| `/phenomenon/fake-id` | **200** | 3507 | 现象详情 | shell still served — JS hits `/api/phenomenon/fake-id` (real 404) and presumably renders an error state. **Server should ideally 404 the SPA route too, or make sure the JS path renders the friendly empty state — see P1 #2.** |
| `/nonexistent` | 404 | 2280 | 没找到 — Structural | nice 404 page with serif “404 / 这个现象还没有被收录 / 返回首页” |
| `/about` | 200 | 7526 | 关于 — Structural | h1 + 5 sections, all internal/external links resolve |

External links from footer + about: `https://structural.bytedance.city/paper-zh.html` → 200, `https://github.com/dada8899` → 200. No dead links found.

## Backend endpoints (called directly)

| Endpoint | HTTP | Notes |
|---|---|---|
| `GET /api/health` | 200 | `{"status":"ok","kb_size":4443,"llm_model":"anthropic/claude-sonnet-4.6"}` |
| `GET /api/daily` | 200 | 3 pairs returned, **but every `a.id`/`b.id` is `""`** (empty) and `a.type_id`/`description` empty — see P0 #1 |
| `GET /api/examples` | 200 | 3 pairs, all `id`s present and well-formed |
| `GET /api/suggest` | 200 | 7 chip strings |
| `GET /api/discoveries` | 200 | `count: 39` items |
| `GET /api/phenomenon/5k-ef-362` | 200 | full payload incl. `similar[]` |
| `GET /api/phenomenon/fake-id` | 404 | clean error |
| `POST /api/search` (normal CN) | 200 | "为什么创业公司早期更容易创新" — **17.7s**, 3 results, rewritten_query present |
| `POST /api/search` (English) | 200 | 5.5s, 3 results, rewritten into Chinese |
| `POST /api/search` ("a" 1-char) | 200 | 0.7s, 3 weak results (top score 6.9) — no input validation, low-quality output |
| `POST /api/search` (300 CN chars "为什么"×100) | 200 | 6.0s, accepts |
| `POST /api/search` (empty `""`) | **422** | `string_too_short` — server rejects, but the SPA never sends empty (textarea submit blocked client-side); fine |

---

## P0 — broken / blocking

1. **`/api/daily` returns empty `id` fields.** Payload: `"a":{"id":"","name":"限流的令牌桶",...}`, same for `b`. Effect: the homepage "今日发现" cards on `home.html` (`#daily-grid`) cannot link to `/phenomenon/{id}` — clicks land on `/phenomenon/` (or do nothing depending on `home.js`). This is the most prominent CTA below the fold and it dead-ends. Compare to `/api/examples`, which returns proper IDs. Fix: backend should populate `a.id/b.id/type_id/description` in the daily payload (same shape as `/api/examples`).
2. **First search is shockingly slow.** `POST /api/search` for the suggested normal query took **17.7s** end-to-end; English took 5.5s; long Chinese 6.0s; single-char 0.7s. The 17s outlier blows past `analyze-loading__typical "通常需 30–60s"` for *just the search step*. There's no streaming/partial render hint to the user during this window; the search.html shell only shows skeleton cards. P0 because first-time users will assume the site is dead.

## P1 — confusing / missing states

1. **Stat mismatches between marketing copy and API.**
   - Hero says "**87** 学科 / **4,475** 现象"; `/api/health` returns `kb_size: 4443` (32-item drift).
   - "查看全部 **19** 个 A 级精选发现" but `/api/discoveries` returns 39 items. If 19 is the A-grade subset, the link target (`/discoveries`) shows all 39 — copy or filter is wrong.
   - Pick one source of truth and inject at build time (or fetch on render).
2. **`/phenomenon/fake-id` serves a 200 SPA shell** instead of an explicit 404 route. The friendly "没找到" page exists at `/nonexistent` — wire it up for unknown phenomenon IDs as well, either server-side or by having `phenomenon.js` swap to the 404 layout on `404` from `/api/phenomenon/{id}`. (Need browser pass to confirm what the JS actually shows.)
3. **No "compare two phenomena" UI.** The task brief mentions an "analyze two phenomena" feature; `/analyze` is *not* that — it is the post-search streaming-report viewer (requires `?id=b_id&q=...`). If the product wants a manual two-input mode, it does not exist. If not, the brief is stale — but the route itself with no params silently redirects to `/` (line ~`window.location.href = '/'`), no message.
4. **Single-char/garbage queries return low-signal results without coaching.** Searching `"a"` returns 3 phenomena with top score 6.9 and `worth_score: 4`; the API has a `coaching` and `rewrite_suggestion` slot but both come back null. Either suppress results below a quality threshold or surface the coaching string.
5. **Daily payload has `similarity: 0.0082–0.0092`.** Hero evidence shows "94%". The `home.js` either renders these as percentages anyway (so user sees "1%") or there's a separate score field never populated. Verify what users actually see — if it's "1%", that's a P0; flagged here as P1 pending visual confirmation.

## P2 — polish

1. **Long search latency without progressive feedback.** `searchbox__hint` says `⌘+Enter`, but no inline timer/progress like `analyze-loading__timer-row`. Add a visible elapsed-time indicator after 3s.
2. **Mobile (375×?)**: `responsive.css` has only 1024 / 768 / 480 breakpoints — 375px viewports get the smallest tier. Cannot verify layout without a real browser, but the home hero has fixed inline padding via `--space-*` tokens and a 3-column `usecases-grid` that needs to collapse — visually verify on first manual pass.
3. **Header nav `我的收藏`** uses `data-fav-link` + a hidden `<span data-fav-badge hidden>0</span>`; if `home.js` never increments past 0, the badge stays hidden — fine, but verify the empty state isn't broken.
4. **Footer `paper-zh.html`** points to the production domain `structural.bytedance.city`, not beta. Intentional? Inconsistent vs. other beta-internal links.
5. **No persistent global nav on `/about`, `/discoveries`, `/search`, `/analyze`, `/phenomenon/*`** beyond the `site-header` on each page (verified all five pages include `site-header__nav` markup with links to `/discoveries`, `/about`, `/`). So navigation back home is always available — good. The header logo is the home link in every shell.

## Console errors

**Not measurable** without a live browser session. The static JS read clean (`api.js`, `home.js`, `search.js`, `analyze.js` all parse, all use modern `async/await` + `URLSearchParams` with no obvious syntax issues). The only place an unhandled rejection is likely is `apiFetch` → throws on non-2xx; needs visual confirmation that callers `try/catch`.

## UX overall

The site is a polished single-purpose tool: server-rendered shells + thin JS hydration, clear copy, sensible 404, well-structured nav. Backend is fast for trivial queries but the headline normal query (17.7s) is a UX cliff. The biggest gap is the broken `/api/daily` payload — that section is on the homepage and silently dead-ends users.

## Top 5 fixes (do these first)

1. **Fix `/api/daily`** to return real IDs / type_id / description (mirror `/api/examples`). Until then, `#daily-grid` is a dead CTA on the most-trafficked page.
2. **Reconcile homepage stat numbers** with `/api/health` (4443 vs 4475; 19 vs 39 discoveries). Build-time substitution is fine.
3. **Investigate the 17s normal-query latency** for `/api/search`. Either cache, warm the embedding model, or stream partial results — and add elapsed-time UI in the skeleton state after 3s.
4. **Make `/phenomenon/{unknown}` reach the 404 page** (or have `phenomenon.js` render the friendly empty state on API 404). 200-with-empty-shell is the worst of both worlds.
5. **Either build the "analyze two phenomena" input UI on `/analyze`** or remove the route from internal docs / add a noindex; visiting it directly currently silently redirects with no explanation.

---

### What still needs a real-browser pass

- Visual verification of mobile (375px) layout on home / discoveries / phenomenon detail.
- Whether `daily-grid` cards actually render and what link they point to (since `id=""`).
- Console errors during the 17s search wait and during a full `/analyze` SSE stream.
- Whether `home.js` shows daily similarity as "1%" or recomputes it.
- Click-through: search → phenomenon detail → analyze → back-button behaviour.
- Whether the favorite-badge increments and persists across reloads.

Re-run me when the playwright profile is free (kill the stale `playwright-mcp` process trees in `~/.playwright-profile`) or after launching the claude-in-chrome extension.
