"""
RFC 7807 problem-details error responses (W11-C, session #10).

This module replaces ad-hoc `{"error": "..."}` JSON bodies with a structured
`Content-Type: application/problem+json` envelope per RFC 7807:

    {
      "type":     "https://structural.bytedance.city/errors/budget_exceeded",
      "title":    "Budget exceeded",
      "status":   429,
      "detail":   "Daily budget of $5 USD exhausted for tier=free.",
      "instance": "/api/ask/stream"
    }

Plus optional structured extension fields (RFC 7807 §3.2 — "Problem Type
Definitions" can add arbitrary members).

Usage in routers:

    from errors import BudgetExceeded, InvalidInput, NotFound

    if user_budget_used:
        raise BudgetExceeded(detail="Daily $5 exhausted", tier="free", remaining_usd=0)

    if not item:
        raise NotFound(detail=f"Phenomenon '{pid}' not found")

The exception handler installed by `install_problem_handlers(app)` translates
any `ProblemDetail` subclass into the RFC 7807 JSON envelope. Generic
exceptions get wrapped into `InternalError` (stack traces logged server-side
only, never sent to clients unless DEBUG mode).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded as SlowAPIRateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

if __package__ == "web.backend":
    from .logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

logger = get_logger("structural.errors")

# Type URI prefix — points to error type catalog. Real URL doesn't need to
# resolve (RFC 7807 §4.2 allows "about:blank") but a stable string lets
# clients map error types to localized messages without parsing `title`.
_ERROR_TYPE_PREFIX = "https://structural.bytedance.city/errors/"

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_INCIDENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_ROUTE_TEMPLATE_RE = re.compile(r"^/[A-Za-z0-9_.~/{\}-]{0,159}$")
_REQUEST_ID_SCOPE_KEY = "structural.request_id"
_INCIDENT_ID_SCOPE_KEY = "structural.incident_id"


class ProblemDetail(Exception):
    """Base class for RFC 7807 problem-details errors.

    Subclasses set `default_status`, `default_title`, and `type_slug` (used to
    build the type URI). Per-instance constructor lets callers override the
    detail string and pass arbitrary structured extension fields.
    """

    default_status: int = 500
    default_title: str = "Internal error"
    type_slug: str = "internal_error"

    def __init__(
        self,
        detail: Optional[str] = None,
        *,
        status: Optional[int] = None,
        title: Optional[str] = None,
        type_slug: Optional[str] = None,
        **extensions: Any,
    ):
        self.status = status if status is not None else self.default_status
        self.title = title if title is not None else self.default_title
        self.detail = detail or self.default_title
        self.type_slug = type_slug or self.type_slug
        # Arbitrary extension fields per RFC 7807 §3.2.
        self.extensions = {k: v for k, v in extensions.items() if v is not None}
        super().__init__(self.detail)

    def to_dict(self, instance: Optional[str] = None) -> dict:
        body = {
            "type": f"{_ERROR_TYPE_PREFIX}{self.type_slug}",
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }
        if instance:
            body["instance"] = instance
        # Merge extensions last so they never override the canonical fields.
        for k, v in self.extensions.items():
            if k not in body:
                body[k] = v
        return body


# ------------- concrete subclasses -------------


class InvalidInput(ProblemDetail):
    default_status = 422
    default_title = "Invalid input"
    type_slug = "invalid_input"


class Unauthenticated(ProblemDetail):
    default_status = 401
    default_title = "Authentication required"
    type_slug = "unauthenticated"


class Forbidden(ProblemDetail):
    default_status = 403
    default_title = "Forbidden"
    type_slug = "forbidden"


class NotFound(ProblemDetail):
    default_status = 404
    default_title = "Not found"
    type_slug = "not_found"


class RateLimitExceeded(ProblemDetail):
    default_status = 429
    default_title = "Rate limit exceeded"
    type_slug = "rate_limit_exceeded"


class BudgetExceeded(ProblemDetail):
    default_status = 429
    default_title = "Budget exceeded"
    type_slug = "budget_exceeded"


class UpstreamUnavailable(ProblemDetail):
    default_status = 503
    default_title = "Upstream unavailable"
    type_slug = "upstream_unavailable"


class InternalError(ProblemDetail):
    default_status = 500
    default_title = "Internal error"
    type_slug = "internal_error"


# ------------- handlers -------------


def _problem_response(exc: ProblemDetail, request: Request) -> JSONResponse:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    instance = template if isinstance(template, str) and _ROUTE_TEMPLATE_RE.fullmatch(template) else None
    body = exc.to_dict(instance=instance)
    headers = {}
    request_id = request.scope.get(_REQUEST_ID_SCOPE_KEY)
    if isinstance(request_id, str) and _REQUEST_ID_RE.fullmatch(request_id):
        headers["X-Request-ID"] = request_id
    # Surface retry-after on rate-limit so HTTP clients honour it.
    if isinstance(exc, RateLimitExceeded):
        retry = exc.extensions.get("retry_after_s")
        if retry is not None:
            headers["Retry-After"] = str(int(retry))
    return JSONResponse(
        status_code=exc.status,
        content=body,
        media_type="application/problem+json",
        headers=headers,
    )


async def _problem_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert any exception to an RFC 7807 envelope.

    - ProblemDetail subclasses → direct conversion.
    - StarletteHTTPException → mapped by status code.
    - RequestValidationError (pydantic) → InvalidInput with field errors.
    - slowapi RateLimitExceeded → RateLimitExceeded with retry hint.
    - Anything else → InternalError; stack trace logged, not returned.
    """
    if isinstance(exc, ProblemDetail):
        return _problem_response(exc, request)

    if isinstance(exc, SlowAPIRateLimitExceeded):
        # slowapi packs the limit string into exc.detail (e.g. "60/minute").
        limit_spec = getattr(exc, "detail", "unknown")
        retry_after = _parse_retry_after(limit_spec)
        wrapped = RateLimitExceeded(
            detail=f"Rate limit {limit_spec} exceeded",
            limit=str(limit_spec),
            retry_after_s=retry_after,
        )
        return _problem_response(wrapped, request)

    if isinstance(exc, RequestValidationError):
        # Surface pydantic errors as `errors` extension list.
        errs = []
        for err in exc.errors():
            errs.append({
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg"),
                "type": err.get("type"),
            })
        wrapped = InvalidInput(
            detail="Request body failed validation",
            errors=errs,
        )
        return _problem_response(wrapped, request)

    if isinstance(exc, StarletteHTTPException):
        # Map common HTTP status codes back into our class hierarchy so the
        # response envelope is consistent across the API surface.
        status = exc.status_code
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        klass = {
            400: InvalidInput,
            401: Unauthenticated,
            403: Forbidden,
            404: NotFound,
            422: InvalidInput,
            429: RateLimitExceeded,
            503: UpstreamUnavailable,
        }.get(status, InternalError)
        wrapped = klass(detail=detail or klass.default_title, status=status)
        return _problem_response(wrapped, request)

    # Unknown exceptions are represented only by a type and random incident
    # handle. Exception strings, tracebacks and raw paths may contain request
    # bodies or credentials and never enter operational logs or responses.
    scoped_incident_id = request.scope.get(_INCIDENT_ID_SCOPE_KEY)
    incident_id = (
        scoped_incident_id
        if isinstance(scoped_incident_id, str) and _INCIDENT_ID_RE.fullmatch(scoped_incident_id)
        else new_incident_id()
    )
    request_id = request.scope.get(_REQUEST_ID_SCOPE_KEY)
    safe_request_id = (
        request_id
        if isinstance(request_id, str) and _REQUEST_ID_RE.fullmatch(request_id)
        else None
    )
    logger.error(
        "privacy.internal_error",
        error_type=type(exc).__name__,
        incident_id=incident_id,
        request_id=safe_request_id,
    )
    wrapped = InternalError(
        detail="An internal error occurred. Please try again.",
        incident_id=incident_id,
    )
    return _problem_response(wrapped, request)


def _parse_retry_after(limit_spec: str) -> int:
    """Best-effort: parse '60/minute' → 60 seconds. Conservative fallback."""
    try:
        s = str(limit_spec).lower()
        if "/" not in s:
            return 60
        _, _, unit = s.partition("/")
        unit = unit.strip()
        if unit.startswith("second"):
            return 1
        if unit.startswith("minute"):
            return 60
        if unit.startswith("hour"):
            return 3600
        if unit.startswith("day"):
            return 86400
    except Exception:
        pass
    return 60


def install_problem_handlers(app: FastAPI) -> None:
    """Wire RFC 7807 handlers into a FastAPI app.

    Registers:
    - ProblemDetail (and all subclasses)
    - RequestValidationError (pydantic)
    - StarletteHTTPException (HTTPException raises from FastAPI)
    - slowapi.RateLimitExceeded
    - generic Exception (last-resort safety net)
    """
    app.add_exception_handler(ProblemDetail, _problem_handler)
    app.add_exception_handler(RequestValidationError, _problem_handler)
    app.add_exception_handler(StarletteHTTPException, _problem_handler)
    app.add_exception_handler(SlowAPIRateLimitExceeded, _problem_handler)
    # Catch-all — only kicks in if nothing else matched.
    app.add_exception_handler(Exception, _problem_handler)


__all__ = [
    "ProblemDetail",
    "InvalidInput",
    "Unauthenticated",
    "Forbidden",
    "NotFound",
    "RateLimitExceeded",
    "BudgetExceeded",
    "UpstreamUnavailable",
    "InternalError",
    "install_problem_handlers",
]
