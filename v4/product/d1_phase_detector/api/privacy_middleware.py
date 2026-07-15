"""Content-free request correlation for the Phase API."""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Awaitable, Callable

from starlette.responses import JSONResponse


_REQUEST_ID_RE = re.compile(
    r"^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})$"
)
logger = logging.getLogger("phase.privacy")


class PrivacyRequestContextMiddleware:
    """Echo one safe request ID and log only route templates on failures."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        candidates: list[str] = []
        for key, value in scope.get("headers", []):
            if key.lower() != b"x-request-id":
                continue
            try:
                candidates.append(value.decode("ascii"))
            except UnicodeDecodeError:
                candidates.append("")
        supplied = candidates[0] if len(candidates) == 1 else ""
        request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else str(uuid.uuid4())
        scope["structural.request_id"] = request_id

        async def send_with_request_id(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            route = scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            logger.error(
                "phase.request_failed",
                extra={
                    "request_id": request_id,
                    "request_method": str(scope.get("method", "UNKNOWN"))[:16],
                    "route_template": str(route_template)[:160],
                    "error_type": type(exc).__name__,
                },
            )
            response = JSONResponse(
                {"error": "internal server error"},
                status_code=500,
            )
            await response(scope, receive, send_with_request_id)
