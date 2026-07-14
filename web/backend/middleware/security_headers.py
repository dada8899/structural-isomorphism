"""Security response headers middleware (launch P0-3).

Before this middleware the app shipped zero security headers — no HSTS,
no clickjacking protection, no MIME-sniffing protection, no CSP. That
leaves the site open to being iframed for clickjacking, to MIME-sniff
script execution, and to SSL-strip downgrade on first visit.

This middleware injects a conservative, uniform set of headers on every
response (API + HTML pages alike). It is intentionally added at the app
layer (not nginx) so the protection travels with the code and holds in
local dev / staging too.

Headers injected:
  * Strict-Transport-Security  — force HTTPS for a year (HSTS).
  * X-Frame-Options: DENY      — no embedding in any frame (clickjacking).
  * X-Content-Type-Options: nosniff — disable MIME sniffing.
  * Referrer-Policy            — never emit a request referrer.
  * Content-Security-Policy    — restrict resource origins.

CSP design — DELIBERATELY PERMISSIVE for v1:
  The site loads a handful of third-party / CDN resources:
    - Plausible analytics (self-hosted at plausible.bytedance.city, but
      report.html / reports.html still point at the public plausible.io —
      both are whitelisted so the P1 domain-fix can land separately).
    - KaTeX from cdn.jsdelivr.net on the report share page.
    - Inline <style> / <script> blocks across the static pages.
  `'unsafe-inline'` is kept for script-src/style-src because the existing
  pages embed inline handlers — tightening that needs a frontend refactor
  (nonces / hashes) and is explicitly out of scope here. The rule of this
  task: "宁可保守也别破坏页面". A too-strict CSP that blanks the page is a
  worse launch outcome than a permissive-but-present one.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware


# One-year HSTS. `includeSubDomains` is safe: every *.bytedance.city site
# is already HTTPS-only behind nginx + Let's Encrypt.
_HSTS = "max-age=31536000; includeSubDomains"

# Permissive-but-present CSP. Every external host the frontend actually
# uses is whitelisted; inline scripts/styles are allowed (see module
# docstring for why). connect-src covers same-origin XHR/SSE + analytics.
_CSP = "; ".join([
    "default-src 'self'",
    # Inline handlers + jsdelivr (KaTeX) + both Plausible hosts.
    "script-src 'self' 'unsafe-inline' "
    "https://cdn.jsdelivr.net "
    "https://plausible.bytedance.city https://plausible.io",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    # KaTeX ships fonts; data: covers inline-encoded assets.
    "font-src 'self' data: https://cdn.jsdelivr.net",
    "img-src 'self' data:",
    # SSE / fetch back to our API + analytics beacon.
    "connect-src 'self' https://plausible.bytedance.city https://plausible.io",
    # Hard clickjacking stop (pairs with X-Frame-Options for old browsers).
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])

_STATIC_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": _CSP,
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject a uniform set of security headers on every response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        response = await call_next(request)
        for name, value in _STATIC_HEADERS.items():
            # Assignment replaces any route-provided duplicate. Referrer
            # policy is a global privacy invariant, not a route override.
            response.headers[name] = value
        # HSTS only makes sense over HTTPS. We can't always tell behind a
        # proxy, so honour X-Forwarded-Proto; default to sending it (the
        # site is HTTPS-only in every real deploy, and a browser ignores
        # HSTS received over plain HTTP anyway).
        proto = request.headers.get("x-forwarded-proto", "https").lower()
        if proto == "https":
            response.headers["Strict-Transport-Security"] = _HSTS
        return response


def install_security_headers(app: FastAPI) -> None:
    """Wire the security-headers middleware into a FastAPI app."""
    app.add_middleware(SecurityHeadersMiddleware)


__all__ = ["SecurityHeadersMiddleware", "install_security_headers"]
