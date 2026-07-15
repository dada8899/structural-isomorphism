# Error handling, offline mode, and incident reporting (W12-E)

**Date**: 2026-05-15
**Scope**: `web/phase-detector` (Next.js app) + `web/backend/api/error_log.py`

This doc explains the resilience layer added in W12-E: how the app degrades when a render crashes, how it survives a flaky network via a service worker, and how reports flow from the browser back into a server-side jsonl that engineers can grep.

## 1. Error-boundary hierarchy

Next.js gives us two boundary slots; we use both, with different scopes and different fidelity:

| Boundary | File | Catches | Fallback fidelity |
|---|---|---|---|
| Page-level | `app/error.tsx` | Errors thrown by any segment _below_ `app/layout.tsx`. The layout (nav, footer, banner) keeps rendering around the failing route. | Full styling — uses `@/lib/error-reporter` for content-free auto-reporting plus a user-initiated GitHub issue URL. |
| Root-level | `app/global-error.tsx` | Errors thrown by `app/layout.tsx` itself (font loader broke, top-level provider died). | Minimal — own `<html>`/`<body>`, no `@/` aliases. Auto-reports the same content-free envelope via raw `fetch`. |

Both boundaries:

- Log only a constant failure category to the console; the `Error` object is not printed.
- Auto-POST an allowlisted error class, timestamp, and fatal flag to `/api/errors` (fire-and-forget, never throws).
- Show the `error.digest` to the user so they can copy it into a bug report.

The page-level boundary additionally renders a "Report this ↗" link. It pre-fills only a fixed generic title and instructions; it does not read or insert the error object, digest, time, page URL, or browser fingerprint. The user decides what to add before submitting the public issue.

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

`/api/errors` accepts a strict schema (`pydantic` with `extra="forbid"`). It accepts only the following content-free envelope. Pre-hardening tabs that still send raw message, stack, digest, URL, User-Agent, or session fields receive `422`; those values never enter the accepted application model.

| Field | Bound | Stripping |
|---|---|---|
| `message` | fixed allowlist | Compatibility field containing only a coarse class such as `TypeError`; never `Error.message` |
| `timestamp` | integer | Used only while queued; persistence uses server time |
| `fatal` | boolean | Distinguishes a root-boundary crash |

`lib/error-reporter.ts` sanitizes again immediately before network transmission and before every local-storage write. When a new release encounters an older offline queue, it keeps only an allowlisted error class, timestamp, and fatal flag and removes every raw field before retrying. The durable server row contains only event name, coarse error type, fatal flag, server time, and a random incident ID.

## 4. Rate limiting + rotation

- **Limit**: 10 reports / 60 s. Requests are bucketed by an ephemeral HMAC of the client IP observed by the trusted server path. The address is neither written to disk nor placed in application logs. Client-supplied session IDs are rejected.
- **Limited response**: HTTP 200 with `{accepted: false, reason: "rate_limited"}`. We do not 429 so the client doesn't need branchy error handling for a non-actionable status.
- **Rotation**: when `error_log.jsonl` crosses 10 MB, it's renamed to `error_log.jsonl.1` (single-slot rotation). Disk usage stays bounded ≤ 20 MB.

## 5. Debugging a reported error

A typical bug report comes in as one or both of:

1. A GitHub issue opened and completed by the user (title prefix `[user-report]`), optionally containing the opaque Next.js digest shown on screen.
2. A content-free `/api/errors` jsonl incident near the same server time.

To find the record:

```bash
ssh root@43.156.233.71 \
  "jq -c 'select(.incident_id == \"<incident-id>\")' \
     /root/Projects/structural-isomorphism/web/backend/data/error_log.jsonl \
     /root/Projects/structural-isomorphism/web/backend/data/error_log.jsonl.1 2>/dev/null"
```

The record exposes no page, device, user, session, message, or stack content. Correlate only by incident ID, coarse error type, fatal flag, and a bounded time window. Ask the reporting user for reproduction steps rather than reconstructing their activity from telemetry.

## 6. Deferred work

- **Real Sentry integration** — current endpoint is a local receiver. Any future processor must receive only the same content-free event type, status, and opaque incident/correlation IDs; request data, messages, breadcrumbs, stack variables, and raw transactions stay disabled.
- **Cache warming** — the SW only precaches `/offline`. We could opportunistically warm the homepage `/` and the most-viewed company pages on `install`. Deferred until we measure how often users actually hit offline mode.
- **next-pwa migration** — if/when we need workbox features (background sync, push), revisit; for now hand-rolled stays.
