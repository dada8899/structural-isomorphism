# Error handling, offline mode, and incident reporting (W12-E)

**Date**: 2026-05-15
**Scope**: `web/phase-detector` (Next.js app) + `web/backend/api/error_log.py`

This doc explains the resilience layer added in W12-E: how the app degrades when a render crashes, how it survives a flaky network via a service worker, and how reports flow from the browser back into a server-side jsonl that engineers can grep.

## 1. Error-boundary hierarchy

Next.js gives us two boundary slots; we use both, with different scopes and different fidelity:

| Boundary | File | Catches | Fallback fidelity |
|---|---|---|---|
| Page-level | `app/error.tsx` | Errors thrown by any segment _below_ `app/layout.tsx`. The layout (nav, footer, banner) keeps rendering around the failing route. | Full styling — uses `@/lib/error-reporter` for auto-report + a pre-filled GitHub issue URL. |
| Root-level | `app/global-error.tsx` | Errors thrown by `app/layout.tsx` itself (font loader broke, top-level provider died). | Minimal — own `<html>`/`<body>`, no `@/` aliases. Auto-reports via raw `fetch` so a borked bundler can still surface the incident. |

Both boundaries:

- Log the error to the console (so it's still visible in DevTools).
- Auto-POST a sanitised summary to `/api/errors` (fire-and-forget, never throws).
- Show the `error.digest` to the user so they can copy it into a bug report.

The page-level boundary additionally renders a "Report this ↗" link that pre-fills a GitHub issue with title, digest, URL, and browser. The user is one click away from a useful bug report; no need to copy/paste.

## 2. Service-worker caching strategy

The service worker (`web/phase-detector/public/sw.js`) is hand-rolled rather than pulled from `next-pwa`. The intent is to keep the runtime tiny (~3 KB) and the logic legible:

| Resource | Strategy | Why |
|---|---|---|
| `/_next/static/*`, `/icons/*`, fonts, images | `cacheFirst` | Immutable per build; we never want network RTT for static. |
| `/api/phase*`, `/api/companies*`, `/api/discoveries*` | `staleWhileRevalidate` | Phase signals refresh hourly. Show the cached snapshot instantly, refresh in the background. |
| HTML page navigations | `networkFirst` w/ 3 s timeout → cache → `/offline` | Pages should reflect the latest deploy when online; degrade gracefully when not. |
| `/api/errors`, write paths | bypass | Caching writes is wrong; bypass keeps the path simple. |

Cache names are versioned (`phase-static-v1-2026-05-15` etc.). On `activate`, any cache whose prefix matches `phase-` but whose suffix isn't in the keep-set is deleted — old deploys self-evict without manual cache-busting.

### Offline fallback

`app/offline/page.tsx` (precached on `install`) renders the most-recent `phase.lastSnapshot` from `localStorage` if any callers have populated it. The page is read-only and shows a `Try again` button that calls `location.reload()` — when the user gets back online the SW network-first path serves the live page.

`NetworkBanner.tsx` listens to `window` `online`/`offline` events and shows a compact "Offline mode — showing cached data" pill at the top. It also flushes any error reports queued during the offline window via `flushErrorQueue()`.

## 3. Error reporting privacy

`/api/errors` accepts a strict schema (`pydantic` with `extra="forbid"`). Anything outside the allow-list is rejected with 422 — this is the load-bearing guarantee that no `localStorage` blobs, query strings, or arbitrary fields can leak into the log.

| Field | Bound | Stripping |
|---|---|---|
| `message` | 1..500 chars | none beyond truncation |
| `stack` | ≤ 4000 chars | none |
| `digest` | ≤ 64 chars | none |
| `url` | ≤ 500 chars | **query string stripped server-side** (`urlsplit` → empty `query`/`fragment`) |
| `userAgent` | ≤ 300 chars | none — the browser sends it anyway |
| `sessionId` | ≤ 64 chars | opaque uuid generated client-side, lives in `localStorage`; not tied to any account |

Two layers strip the query string: the client (`lib/error-reporter.ts`) and the server. Defence in depth — a misconfigured client can't accidentally smuggle PII through the URL.

## 4. Rate limiting + rotation

- **Limit**: 10 reports / 60 s per `sessionId` (sliding window). Anonymous reports without `sessionId` are bucketed by client IP instead. Implemented as an in-memory `Dict[str, deque[float]]` — sufficient for client-side instrumentation that fires single-digit reports.
- **Limited response**: HTTP 200 with `{accepted: false, reason: "rate_limited"}`. We do not 429 so the client doesn't need branchy error handling for a non-actionable status.
- **Rotation**: when `error_log.jsonl` crosses 10 MB, it's renamed to `error_log.jsonl.1` (single-slot rotation). Disk usage stays bounded ≤ 20 MB.

## 5. Debugging a reported error

A typical bug report comes in as one or both of:

1. A GitHub issue auto-filled by the user (title prefix `[user-report]`), containing the `Digest` field.
2. A `/api/errors` jsonl record for the same `digest`.

To find the record:

```bash
ssh root@43.156.233.71 \
  "jq -c 'select(.digest == \"<digest>\")' \
     /root/Projects/structural-isomorphism/web/backend/data/error_log.jsonl \
     /root/Projects/structural-isomorphism/web/backend/data/error_log.jsonl.1 2>/dev/null"
```

The record exposes the redacted URL, user-agent, truncated stack, and `sessionId`. For repeated incidents, group by `sessionId` to see whether one user is hitting the same path multiple times — that's usually a stale browser tab against a fresh deploy, fixable by hard reload.

## 6. Deferred work

- **Real Sentry integration** — current endpoint is a mock receiver. Migration plan: swap the `_data_file()` write for a `sentry_sdk.capture_event()` call inside the same router, keeping the rate-limit + schema layer in front. The frontend's `lib/error-reporter.ts` API does not need to change.
- **Cache warming** — the SW only precaches `/offline`. We could opportunistically warm the homepage `/` and the most-viewed company pages on `install`. Deferred until we measure how often users actually hit offline mode.
- **next-pwa migration** — if/when we need workbox features (background sync, push), revisit; for now hand-rolled stays.
