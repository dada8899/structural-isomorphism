"""
GET /api/admin/logs/tail — return the last N JSON log lines (W14-D).

Reads the rotating log file written by `logging_config.configure_logging()`.
Admin tier required (re-uses the existing `X-API-Key` resolution via
`middleware.rate_limit.CURRENT_TIER` contextvar populated by
`TierResolutionMiddleware`).

Query params:
    n         int  default=200, range 1..2000
    filter    str  optional substring match against the raw line (cheap
                   server-side grep — useful for `?filter=ask` or
                   `?filter=request_id:abc...`)
    level     str  optional one of debug/info/warning/error/critical

Response:
    {
      "log_file":  "/path/to/server.jsonl",
      "returned":  198,
      "lines":     [ { ...parsed JSON... }, ... ]   # newest LAST
    }

If a line cannot be parsed as JSON it's returned as `{"raw": "...",
"parse_error": true}` so the operator can still see partial / truncated
content without us silently dropping lines.

Why tail by line and not by byte:
  - The rotating file handler may rotate between calls; reading the last
    N bytes risks straddling a rotation boundary and returning gibberish.
  - 2000 lines × ~500 bytes = ~1 MB ceiling, fine for an admin probe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Query, Request

from errors import Forbidden, Unauthenticated
from logging_config import current_log_file

router = APIRouter(tags=["admin"])


_MAX_N = 2000
_DEFAULT_N = 200


def _is_admin(request: Request) -> bool:
    """Resolve current request's tier via the rate-limit contextvar."""
    try:
        from middleware.rate_limit import CURRENT_TIER as _T

        return _T.get() == "admin"
    except Exception:
        return False


def _require_admin(request: Request) -> None:
    """Raise the same Unauthenticated / Forbidden pattern used by
    /api/admin/keys so the OpenAPI 401/403 contract stays consistent."""
    try:
        from middleware.rate_limit import CURRENT_TIER as _T

        tier = _T.get()
    except Exception:
        tier = "free"

    if tier == "free":
        has_key = bool(
            request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        )
        if not has_key:
            raise Unauthenticated(
                detail="X-API-Key header required for /api/admin/*"
            )
        raise Forbidden(detail="Admin tier required")
    if tier != "admin":
        raise Forbidden(detail="Admin tier required")


def _tail_lines(path: Path, n: int) -> List[str]:
    """Read the last `n` non-empty lines.

    Uses a streaming approach (read the file in 16 KB chunks from the end)
    so we don't load multi-MB files into memory. Falls back to a full read
    if the file is small.
    """
    if not path.exists():
        return []

    try:
        size = path.stat().st_size
    except OSError:
        return []

    # For small files just read everything; simpler + handles edge cases.
    if size <= 256 * 1024:
        with open(path, "rb") as f:
            data = f.read()
        lines = data.splitlines()
        return [ln.decode("utf-8", errors="replace") for ln in lines[-n:]]

    # Streaming tail.
    chunk = 16 * 1024
    pos = size
    collected: list[bytes] = []
    remainder = b""
    with open(path, "rb") as f:
        while pos > 0 and len(collected) <= n:
            read_size = min(chunk, pos)
            pos -= read_size
            f.seek(pos)
            buf = f.read(read_size) + remainder
            parts = buf.split(b"\n")
            # First part may be a fragment continuing from earlier in the
            # file — hold onto it until we read more.
            if pos == 0:
                remainder = b""
                # All parts are complete now.
                pieces = parts
            else:
                remainder = parts[0]
                pieces = parts[1:]
            # Prepend (reverse-order accumulation).
            collected = pieces + collected
            if pos == 0:
                break
    lines = [ln.decode("utf-8", errors="replace") for ln in collected if ln.strip()]
    return lines[-n:]


def _parse_line(raw: str) -> dict:
    """JSON-decode a log line; preserve malformed lines for visibility."""
    raw = raw.strip()
    if not raw:
        return {"raw": raw, "parse_error": True}
    try:
        # stdlib json is fine here — these are small lines and orjson is
        # not required for correctness.
        import json as _json

        return _json.loads(raw)
    except Exception:
        return {"raw": raw, "parse_error": True}


@router.get(
    "/admin/logs/tail",
    summary="Tail recent server log lines (admin only)",
    description=(
        "Returns the last N JSON-formatted log lines from the active server "
        "log file. Use `filter` for a cheap substring match and `level` to "
        "narrow by severity. Admin tier (X-API-Key) required."
    ),
    responses={
        200: {"description": "Tail of recent log lines (newest last)"},
        401: {"description": "Missing or invalid X-API-Key"},
        403: {"description": "API key is valid but not admin tier"},
    },
)
async def tail_logs(
    request: Request,
    n: int = Query(_DEFAULT_N, ge=1, le=_MAX_N),
    filter: Optional[str] = Query(None, max_length=200),
    level: Optional[str] = Query(None, max_length=20),
) -> dict:
    _require_admin(request)

    path = current_log_file()
    raw_lines = _tail_lines(path, n=n)

    # Optional substring + level filters. We over-read a bit to compensate
    # for filtered-out lines but cap at _MAX_N to bound work.
    parsed: List[dict] = []
    f_lower = filter.lower() if filter else None
    lvl_norm = level.upper() if level else None
    for raw in raw_lines:
        if f_lower is not None and f_lower not in raw.lower():
            continue
        obj = _parse_line(raw)
        if lvl_norm is not None:
            entry_level = str(obj.get("level", "")).upper()
            if entry_level != lvl_norm:
                continue
        parsed.append(obj)

    return {
        "log_file": str(path),
        "returned": len(parsed),
        "lines": parsed,
    }
