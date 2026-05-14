# API Auth & Tier Limits

The Structural HTTP API is anonymous-first. Any unauthenticated caller can
hit `/api/ask/stream`, `/api/analyze/stream`, and friends — but their
requests are bucketed into the strictest rate-limit tier (`anonymous`,
5/min). Operators can issue tokens to promote select callers to a looser
tier without touching code.

## Tiers

| Tier        | Identifies via                          | Rate limit |
|-------------|------------------------------------------|------------|
| `paid`      | Bearer token (or cookie) on allowlist   | 60/minute  |
| `free`      | Bearer token (or cookie) on allowlist   | 10/minute  |
| `anonymous` | No token (default)                      | 5/minute   |

Limits are enforced by `services/rate_limit.tier_limit_decorator()`. Each
endpoint may override the anonymous floor via the `default_anon` argument
(e.g. `@tier_limit_decorator(default_anon="5/minute")` on `/ask/stream`,
which is more expensive to serve).

## Token configuration

Tokens are configured via the `STRUCTURAL_API_TOKENS` environment variable.
Format:

    STRUCTURAL_API_TOKENS="<tier>:<token>,<tier>:<token>,..."

Bare tokens without a `<tier>:` prefix default to `free` (for backward
compatibility with single-tier rollouts).

Example:

    export STRUCTURAL_API_TOKENS="paid:tok_live_3K9zXq2,free:tok_free_kx7,legacy_token"

`tok_live_3K9zXq2` ⇒ paid · `tok_free_kx7` ⇒ free · `legacy_token` ⇒ free.

If the same string appears under multiple tiers, the higher tier wins
(`paid` > `free` > `anonymous`).

### Security notes

- Tokens are **environment-only**. They MUST NOT be committed to git.
- Tokens are matched by exact string equality. Pick something at least
  24 chars of base62/hex entropy (`openssl rand -hex 16`).
- Tokens are sent in plaintext over the wire — only deploy behind HTTPS.
- Invalid tokens (provided but not on the allowlist) trigger an HTTP 401
  on the protected endpoint. Missing tokens fall through to anonymous.

## Passing a token

### Authorization header (preferred)

    curl -H "Authorization: Bearer tok_live_3K9zXq2" \
         -H "Content-Type: application/json" \
         -X POST https://structural.bytedance.city/api/ask/stream \
         -d '{"query": "why do crowds clap in sync?"}'

### Cookie (browser flows)

The frontend may set `structural_api_token` on the user's behalf:

    document.cookie = 'structural_api_token=tok_live_3K9zXq2; Secure; SameSite=Lax';

The backend looks up the cookie automatically when no `Authorization`
header is present.

## Rate-limit response

When over-limit, slowapi returns HTTP 429 with a `Retry-After` header.
Clients should back off and retry rather than retrying immediately —
hammering 429s does not promote the request to a looser tier.

## Operator quick-reference

| Action                       | Command                                                |
|------------------------------|--------------------------------------------------------|
| Generate a token             | `openssl rand -hex 16`                                 |
| Add a paid token (systemd)   | edit `Environment=STRUCTURAL_API_TOKENS=...` then `systemctl restart structural-api` |
| Verify a token is recognised | `curl -H "Authorization: Bearer <tok>" /api/health`    |
| Revoke a token               | remove from env, restart service                       |

## Implementation pointers

- `web/backend/services/auth.py` — `verify_api_token`, `get_rate_limit_tier`, `tier_limit`.
- `web/backend/services/rate_limit.py` — `tier_limit_decorator`.
- `web/backend/api/ask.py`, `web/backend/api/analyze.py` — protected endpoints.
- `web/backend/tests/test_auth_tier.py` — unit tests covering all tier paths.
