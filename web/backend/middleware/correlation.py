"""
Correlation-ID middleware (W14-D, session #10).

Reads the inbound `X-Request-ID` header (any case). If absent or malformed,
generates a fresh UUID4 hex. The ID is:

  1. Bound onto a contextvar (`logging_config.REQUEST_ID_VAR`) so every
     structlog / stdlib log line in the request scope auto-tags with it.
  2. Echoed back as `X-Request-ID` on the response so clients (the SPA,
     curl, support engineers) can quote it when reporting issues.

Path + method + (resolved tier, when available) are also threaded through
contextvars so log lines can be filtered by route without each call site
adding `path=` manually.

Notes on placement:
  - Must run *before* slowapi's rate-limit middleware so rejected-with-429
    responses still carry the X-Request-ID echo.
  - Must run *after* CORS so OPTIONS preflights are answered by Starlette
    without us generating a noisy ID for every preflight.
  - Tier injection is opportunistic — if `middleware.rate_limit.CURRENT_TIER`
    has been populated by TierResolutionMiddleware (which runs ahead of us
    in app order), we mirror it onto REQUEST_TIER_VAR for the logger to see.
"""

from __future__ import annotations

import re
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from logging_config import (
    REQUEST_ID_VAR,
    REQUEST_METHOD_VAR,
    REQUEST_PATH_VAR,
    REQUEST_TIER_VAR,
    get_logger,
    new_request_id,
)

# Accepted shapes: bare UUID4 hex (32 chars), dashed UUID, or any
# alphanumeric-ish string ≤ 64 chars (we don't want to be too strict — many
# clients pass their own request IDs from upstream load balancers).
_VALID_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

REQUEST_ID_HEADER = "X-Request-ID"


def _coerce_request_id(raw: str | None) -> str:
    """Validate caller-provided ID; fall back to a fresh UUID4 hex on miss."""
    if not raw:
        return new_request_id()
    raw = raw.strip()
    if not raw or not _VALID_ID_RE.match(raw):
        return new_request_id()
    return raw


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind X-Request-ID into contextvars and echo on response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER) or request.headers.get(
            REQUEST_ID_HEADER.lower()
        )
        rid = _coerce_request_id(incoming)

        # Bind contextvars for the duration of this request. We deliberately
        # don't use a try/finally to reset — ContextVar is per-task and the
        # asyncio task ends with the request, so leakage is impossible.
        token_rid = REQUEST_ID_VAR.set(rid)
        token_path = REQUEST_PATH_VAR.set(request.url.path)
        token_method = REQUEST_METHOD_VAR.set(request.method)

        # Tier may already be resolved by TierResolutionMiddleware (runs
        # before us in app order). Mirror it if so.
        tier_token = None
        try:
            from middleware.rate_limit import CURRENT_TIER as _RL_TIER

            tier = _RL_TIER.get()
            if tier:
                tier_token = REQUEST_TIER_VAR.set(tier)
        except Exception:
            tier_token = None

        log = get_logger("structural.http")
        log.info(
            "http.request",
            client=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)
        except Exception:
            # Log + re-raise — the FastAPI exception handlers own the
            # actual response shape.
            log.exception("http.request.error")
            raise
        finally:
            # Reset in *reverse* order of set() to play nicely with
            # contextvars' linked-list semantics.
            if tier_token is not None:
                REQUEST_TIER_VAR.reset(tier_token)
            REQUEST_METHOD_VAR.reset(token_method)
            REQUEST_PATH_VAR.reset(token_path)
            REQUEST_ID_VAR.reset(token_rid)

        # Echo the ID back so the client can quote it.
        response.headers[REQUEST_ID_HEADER] = rid
        log.info("http.response", status_code=response.status_code)
        return response


def install_correlation_middleware(app: FastAPI) -> None:
    """Mount the middleware. Call from main.py after CORS / rate-limit setup."""
    app.add_middleware(CorrelationIdMiddleware)
