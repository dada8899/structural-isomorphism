"""
POST /api/newsletter/subscribe — beta site newsletter signup.

Session #9 W2-A: beta site previously only had `/api/waitlist` (cross-origin POST
to the phase backend). Beta-native readers of /start-here, /learn, /discoveries
had no way to subscribe. This endpoint captures email + source into a local
JSONL file. Storage is intentionally simple (append-only, dedupe by email);
backfill to Buttondown happens later via a separate cron job.

Body (JSON):
    { "email": "user@example.com", "source": "start-here-essay-end" }

Response:
    200  { "ok": true,  "created": true,  "email": "<normalized>" }
    200  { "ok": true,  "created": false, "email": "<normalized>" }   # duplicate
    400  { "ok": false, "error": "invalid email" }
    400  { "ok": false, "error": "invalid source" }
"""
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from schemas import NewsletterCountResponse

router = APIRouter(tags=["newsletter"])
logger = logging.getLogger("structural.newsletter")

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
    except Exception as e:
        logger.warning("newsletter dedupe scan failed: %s", e)
    return False


class SubscribeBody(BaseModel):
    email: str
    source: Optional[str] = "unknown"


@router.post("/newsletter/subscribe")
async def subscribe(body: SubscribeBody, request: Request):
    email = (body.email or "").strip().lower()
    source = (body.source or "unknown").strip().lower()

    # --- Validation ---
    if not email or len(email) > _MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        return JSONResponse(
            {"ok": False, "error": "invalid email"}, status_code=400
        )
    if len(source) > _MAX_SOURCE_LEN or source not in _ALLOWED_SOURCES:
        return JSONResponse(
            {"ok": False, "error": "invalid source"}, status_code=400
        )

    # --- Dedupe (cheap linear scan) ---
    if _is_duplicate(email):
        logger.info("newsletter duplicate signup: email=%s source=%s", email, source)
        return JSONResponse(
            {"ok": True, "created": False, "email": email}
        )

    # --- Persist ---
    f = _data_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "email": email,
        "source": source,
        "ts": int(time.time()),
        "iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ip": request.client.host if request.client else "?",
        "ua": (request.headers.get("user-agent") or "")[:200],
        "referrer": (request.headers.get("referer") or "")[:300],
    }
    try:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Storage failure is the only error path we don't swallow — surface to
        # client so JS shows "try again". Otherwise data loss is silent.
        logger.error("newsletter write failed: %s", e)
        return JSONResponse(
            {"ok": False, "error": "storage failure"}, status_code=500
        )

    logger.info("newsletter signup: email=%s source=%s", email, source)
    return JSONResponse(
        {"ok": True, "created": True, "email": email}
    )


@router.get("/newsletter/count", response_model=NewsletterCountResponse)
async def count():
    """Public count of subscribers (used by future social-proof widgets).
    Cheap-but-not-cached — at our scale (~MB jsonl), a full scan is < 5ms."""
    f = _data_file()
    if not f.exists():
        return {"count": 0}
    n = 0
    with open(f, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return {"count": n}
