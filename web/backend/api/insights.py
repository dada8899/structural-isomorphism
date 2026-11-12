"""GET /api/insights/* — fail-closed paused public aggregation.

Static k-anonymity thresholds and count bands are vulnerable to differencing
in a low-volume product. These endpoints therefore return stable withheld or
empty states that never depend on report data. Re-enablement requires a
separately reviewed delayed-batch, sticky-suppression or formal-DP design.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

logger = get_logger("structural.insights")
router = APIRouter(tags=["insights"])


# ---------------- response shapes ----------------------------------- #


class SummaryResponse(BaseModel):
    status: Literal["public_aggregation_paused"]


# ---------------- endpoints ----------------------------------------- #


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


async def no_store_insights_responses(request: Request, call_next):
    """Cover exact/prefix paths, framework errors and unhandled failures."""
    path = request.url.path
    if path != "/api/insights" and not path.startswith("/api/insights/"):
        return await call_next(request)
    response: Optional[Response] = None
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "structural.insights.request_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        response = JSONResponse(
            {"detail": "Internal Server Error"}, status_code=500,
        )
    finally:
        if response is not None:
            _no_store(response)
    return response


@router.get(
    "/insights/summary",
    response_model=SummaryResponse,
    summary="Public aggregation status",
)
async def insights_summary(response: Response):
    """Stable paused status; never reads report data."""
    _no_store(response)
    return {"status": "public_aggregation_paused"}


@router.get(
    "/insights/stuck-structures",
    response_model=SummaryResponse,
    summary="Paused public stuck-structure aggregation",
)
async def stuck_structures(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
):
    """Stable paused status; ``limit`` cannot affect data visibility."""
    _no_store(response)
    return {"status": "public_aggregation_paused"}


@router.get(
    "/insights/verified",
    response_model=SummaryResponse,
    summary="Paused public result aggregation",
)
async def verified(
    response: Response,
    limit: int = Query(50, ge=1, le=100),
):
    """Stable paused status; ``limit`` cannot affect data visibility."""
    _no_store(response)
    return {"status": "public_aggregation_paused"}
