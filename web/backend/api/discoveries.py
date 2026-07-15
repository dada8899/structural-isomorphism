"""GET /api/discoveries — bounded candidate queue with provenance gaps."""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
    from ..schemas import DiscoveriesResponse
    from ..services.discovery_contract import (
        build_family_index,
        shape_discovery_candidate,
        validate_catalog_rows,
    )
    from ..services.evidence_envelope import build_evidence_envelope
else:
    from logging_config import get_logger, new_incident_id
    from schemas import DiscoveriesResponse
    from services.discovery_contract import (
        build_family_index,
        shape_discovery_candidate,
        validate_catalog_rows,
    )
    from services.evidence_envelope import build_evidence_envelope

router = APIRouter(tags=["discoveries"])
logger = get_logger("structural.discoveries")

_a_cache: Optional[list] = None
_t2_cache: Optional[list] = None


def _load_a_grade():
    global _a_cache
    if _a_cache is not None:
        return _a_cache
    # The merged V2+V3 feed is the only current authority. Falling back to the
    # legacy 19-row file would silently publish an incomplete queue.
    path = Path(__file__).parent.parent.parent / "data" / "a_discoveries_merged.json"
    if not path.exists():
        logger.error("structural.discoveries.priority_catalog_missing")
        raise HTTPException(status_code=503, detail="discovery catalog unavailable")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(
            "structural.discoveries.priority_catalog_load_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raise HTTPException(status_code=503, detail="discovery catalog unavailable") from exc
    if not isinstance(data, dict):
        logger.error("structural.discoveries.priority_catalog_invalid")
        raise HTTPException(status_code=503, detail="discovery catalog invalid")
    try:
        _a_cache = validate_catalog_rows(data.get("discoveries"), catalog="priority_review")
    except ValueError as exc:
        logger.error(
            "structural.discoveries.priority_catalog_invalid",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raise HTTPException(status_code=503, detail="discovery catalog invalid") from exc
    return _a_cache


def _load_tier2():
    global _t2_cache
    if _t2_cache is not None:
        return _t2_cache
    path = Path(__file__).parent.parent.parent / "data" / "a_discoveries_tier2.json"
    if not path.exists():
        logger.error("structural.discoveries.candidate_catalog_missing")
        raise HTTPException(status_code=503, detail="discovery catalog unavailable")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(
            "structural.discoveries.candidate_catalog_load_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raise HTTPException(status_code=503, detail="discovery catalog unavailable") from exc
    if not isinstance(data, dict):
        logger.error("structural.discoveries.candidate_catalog_invalid")
        raise HTTPException(status_code=503, detail="discovery catalog invalid")
    try:
        _t2_cache = validate_catalog_rows(data.get("discoveries"), catalog="candidate_pool")
    except ValueError as exc:
        logger.error(
            "structural.discoveries.candidate_catalog_invalid",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raise HTTPException(status_code=503, detail="discovery catalog invalid") from exc
    return _t2_cache


def build_public_discoveries() -> dict:
    """Build and validate the single public discovery-candidate projection.

    Secondary surfaces such as ``/api/daily`` must consume this function
    instead of reopening legacy result files or reconstructing confidence
    scores.  Validating here also protects direct Python callers, which do not
    pass through FastAPI's response-model validation.
    """
    raw_items = _load_a_grade()
    raw_tier2 = _load_tier2()
    try:
        # Revalidate here because tests and alternate loaders can inject rows;
        # no caller may bypass the public endpoint's fail-closed boundary.
        raw_items = validate_catalog_rows(raw_items, catalog="priority_review")
        raw_tier2 = validate_catalog_rows(raw_tier2, catalog="candidate_pool")
        all_pairs = [tuple(sorted((row["a_id"], row["b_id"]))) for row in raw_items + raw_tier2]
        if len(set(all_pairs)) != len(all_pairs):
            raise ValueError("discovery pairs must be unique across review queues")
        # Candidate identity is global.  Queue placement controls review order,
        # not scientific family membership; grouping each queue independently
        # splits repeated KB anchors and overstates the number of programs.
        family_index = build_family_index([*raw_items, *raw_tier2])
        items = []
        for raw in raw_items:
            family_id, family_count = family_index[(raw["a_id"], raw["b_id"])]
            item = shape_discovery_candidate(
                raw, tier="priority_review", family_id=family_id, family_variant_count=family_count
            )
            item["evidence"] = build_evidence_envelope(
                candidate_kind="discovery_candidate",
                candidate_label=item["candidate_summary"]["zh"],
                requested_level="candidate",
                counterexample_status=(
                    "gap_recorded" if item["validation_plan"]["validation_gaps"] else "not_recorded"
                ),
                counterexample_summary="；".join(
                    gap["label"]["zh"] for gap in item["validation_plan"]["validation_gaps"]
                ),
            )
            items.append(item)
        tier2 = []
        for raw in raw_tier2:
            family_id, family_count = family_index[(raw["a_id"], raw["b_id"])]
            item = shape_discovery_candidate(
                raw, tier="candidate_pool", family_id=family_id, family_variant_count=family_count
            )
            item["evidence"] = build_evidence_envelope(
                candidate_kind="tier2_discovery_candidate",
                candidate_label=item["candidate_summary"]["zh"],
                requested_level="candidate",
                counterexample_status="not_recorded",
            )
            tier2.append(item)
    except (KeyError, TypeError, ValueError) as exc:
        logger.error(
            "structural.discoveries.catalog_record_invalid",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raise HTTPException(status_code=503, detail="discovery catalog invalid") from exc

    family_count = len({item["candidate_family_id"] for item in items + tier2})
    payload = {
        "count": len(items),
        "discoveries": items,
        "tier2_count": len(tier2),
        "tier2": tier2,
        "stats": {
            "total_candidates": len(items) + len(tier2),
            "priority_review": len(items),
            "candidate_pool": len(tier2),
            "candidate_families": family_count,
            "source_backed": 0,
            "ready_for_preregistration": 0,
        },
    }
    try:
        return DiscoveriesResponse.model_validate(payload).model_dump(mode="json")
    except (TypeError, ValueError) as exc:
        logger.error(
            "structural.discoveries.projection_invalid",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raise HTTPException(status_code=503, detail="discovery catalog invalid") from exc


@router.get("/discoveries", response_model=DiscoveriesResponse)
async def list_discoveries():
    return build_public_discoveries()
