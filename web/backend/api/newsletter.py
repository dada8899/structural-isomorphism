"""Closed subscription endpoints for this release.

Existing lists and external unsubscribe arrangements are not changed. The
HTTP routes deliberately declare no body, never inspect submitted data and
never call the legacy storage helpers retained below for separate maintenance.
"""
import json
import re
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

router = APIRouter(tags=["newsletter"])
logger = get_logger("structural.newsletter")

# RFC-5322-ish — pragmatic, not strict. Catches obvious junk + protects the
# jsonl file. We don't bounce-validate here; that happens at send time.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

# Allow only known sources so the jsonl stays clean for downstream aggregation.
# Add new sources here when adding new placements (keep in sync with
# web/frontend/assets/js/newsletter.js mountNewsletter calls).
_ALLOWED_SOURCES = {
    "start-here-essay-end",
    "learn-end",
    "discoveries-top",
    "test",  # for curl/local testing only — filter out in analytics
}

_MAX_EMAIL_LEN = 200
_MAX_SOURCE_LEN = 60


def _data_file() -> Path:
    """Local jsonl store. Created lazily; parent dir ensured on first write."""
    return (
        Path(__file__).parent.parent / "data" / "newsletter-subscribers.jsonl"
    )


def _is_duplicate(email: str) -> bool:
    """Linear scan — fine up to ~tens of thousands of rows. If we hit scale,
    swap for sqlite. For now, beta is pre-Alpha and dedupe is best-effort."""
    f = _data_file()
    if not f.exists():
        return False
    try:
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if (row.get("email") or "").lower() == email:
                    return True
    except Exception as exc:
        logger.warning(
            "newsletter.dedupe_scan_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
    return False


class SubscribeBody(BaseModel):
    email: str
    source: Optional[str] = "unknown"


class SubscriptionUnavailableResponse(BaseModel):
    ok: Literal[False] = False
    created: Literal[False] = False
    error: Literal["newsletter_unavailable", "waitlist_unavailable"]
    detail: str


def unavailable_response(kind: Literal["newsletter", "waitlist"] = "newsletter") -> JSONResponse:
    return JSONResponse({
        "ok": False,
        "created": False,
        "error": kind + "_unavailable",
        "detail": "新增订阅暂不可用。既有订阅请查看原邮件中的退订说明。",
    }, status_code=503, headers={"Cache-Control": "no-store"})


@router.post("/newsletter/subscribe", status_code=503, response_model=SubscriptionUnavailableResponse)
async def subscribe(request: Request):
    """New subscriptions are unavailable; submitted bodies are never consumed."""
    return unavailable_response()


@router.get("/newsletter/count", status_code=503, response_model=SubscriptionUnavailableResponse)
async def count():
    """The closed endpoint does not read or disclose a subscriber count."""
    return unavailable_response()
