"""GET /api/daily — three reviewable discovery candidates for today."""

import hashlib
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException

from api.discoveries import build_public_discoveries
from schemas import DailyResponse

router = APIRouter(tags=["daily"])


@router.get("/daily", response_model=DailyResponse)
async def daily_discoveries(lang: Literal["zh", "en"] = "zh"):
    """Return a deterministic preview of the strict public candidate queue.

    There is intentionally no confidence or similarity field.  The underlying
    catalogs contain model-ranking values, but those values are not calibrated
    evidence and must not reappear through a secondary endpoint.
    """
    today = str(date.today())
    payload = build_public_discoveries()
    candidates = [*payload["discoveries"], *payload["tier2"]]
    if len(candidates) < 3:
        raise HTTPException(status_code=503, detail="daily candidates unavailable")
    ranked = sorted(
        candidates,
        key=lambda item: hashlib.sha256(
            f"{today}\x1f{item['discovery_id']}".encode("utf-8")
        ).hexdigest(),
    )
    response = {
        "date": today,
        "lang": lang,
        "discoveries": ranked[:3],
    }
    try:
        return DailyResponse.model_validate(response).model_dump(mode="json")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="daily candidates invalid") from exc
