# Structural API Reference

Public surface for the Structural cross-domain knowledge engine.

- **Base URL (prod):** `https://structural.bytedance.city`
- **Base URL (beta):** `https://beta.structural.bytedance.city`
- **OpenAPI spec:** [`openapi.json`](./openapi.json) (1688 lines, 39 paths)
- **Live docs:** [`/api/docs`](https://structural.bytedance.city/api/docs) — Swagger UI served by FastAPI

## Auth

All endpoints accept anonymous traffic but apply tier-based rate limits.
Supply an `X-API-Key` header to promote a request beyond the free tier.

| Tier  | Limit (req/min) | Notes |
|-------|----------------:|-------|
| free  |              60 | Default (no key) |
| pro   |           1,000 | `sk_test_pro_*` keys |
| team  |           5,000 | `sk_test_team_*` keys |
| admin |              ∞ | Required for `/api/admin/*` |

LLM-expensive endpoints (`/api/ask`, `/api/analyze`, `/api/synthesize`,
`/api/mapping`) consume **half** the bucket per call.

## Error envelope

All non-2xx responses use **RFC 7807** `application/problem+json`:

```json
{
  "type":     "https://structural.bytedance.city/errors/rate_limit_exceeded",
  "title":    "Rate limit exceeded",
  "status":   429,
  "detail":   "Rate limit 60/minute exceeded for tier 'free'",
  "instance": "/api/ask/stream",
  "tier":     "free",
  "limit":    "60/minute",
  "retry_after_s": 60
}
```

Error type slugs:
- `invalid_input` (422)
- `unauthenticated` (401)
- `forbidden` (403)
- `not_found` (404)
- `rate_limit_exceeded` (429)
- `budget_exceeded` (429)
- `upstream_unavailable` (503)
- `internal_error` (500)

## Embedded ReDoc viewer

To render this spec locally, serve it alongside a ReDoc HTML wrapper:

```html
<!doctype html>
<html>
  <head>
    <title>Structural API</title>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" />
  </head>
  <body>
    <redoc spec-url="./openapi.json"></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
  </body>
</html>
```

Or use FastAPI's bundled Swagger UI at `/api/docs`.

## Tag catalog

| Tag | Description |
|-----|-------------|
| ask | Perplexity-like Q&A over the KB |
| search | Vector search for phenomena |
| phenomenon | Per-phenomenon lookups + similar items |
| mapping | LLM-generated structural mappings |
| analyze | Deep cross-domain transfer reports |
| synthesize | Synthesized answer over search results |
| daily | Today's curated discoveries |
| discoveries | A-grade structural discoveries |
| examples | Handpicked example pairs |
| suggest | Search suggestion phrases |
| history | Per-device anonymous query history |
| newsletter | Email newsletter signup |
| checkout-mock | Stripe checkout mock (pre-PMF) |
| system | Health, version, and operational probes |
| admin | Admin-only endpoints (require admin tier) |

## Changelog

- **0.2.0 (2026-05-15, W11-C)** — Added tier-aware rate limiting,
  RFC 7807 error envelopes, `X-API-Key` auth scaffold, `/api/version`
  and `/api/whoami` system endpoints, and an `/api/admin/keys` reflector.
- **0.1.0** — Initial release.
