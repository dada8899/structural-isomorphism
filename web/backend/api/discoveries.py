"""GET /api/discoveries — A 级发现列表 + tier2 候选池"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from schemas import DiscoveriesResponse
from services.evidence_envelope import build_evidence_envelope

router = APIRouter(tags=["discoveries"])

_a_cache: Optional[list] = None
_t2_cache: Optional[list] = None


def _confidence_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score / 100 if 1 < score <= 100 else score


def _summary(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "；".join(str(item) for item in value if item)
    return None


def _load_a_grade():
    global _a_cache
    if _a_cache is not None:
        return _a_cache
    # Use the merged V2+V3 feed (39 items, each carrying a `pipeline` field).
    # The legacy a_discoveries.json only held the 19 V2 items and lacked the
    # pipeline tag, which broke the V2/V3 filter on the discoveries page and
    # contradicted the "39 discoveries" copy in the UI/i18n.
    path = Path(__file__).parent.parent.parent / "data" / "a_discoveries_merged.json"
    if not path.exists():
        # Fallback to the legacy file so a missing merged file degrades
        # gracefully instead of returning an empty list.
        path = Path(__file__).parent.parent.parent / "data" / "a_discoveries.json"
    if not path.exists():
        _a_cache = []
        return _a_cache
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _a_cache = data.get("discoveries", [])
    return _a_cache


def _load_tier2():
    global _t2_cache
    if _t2_cache is not None:
        return _t2_cache
    path = Path(__file__).parent.parent.parent / "data" / "a_discoveries_tier2.json"
    if not path.exists():
        _t2_cache = []
        return _t2_cache
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _t2_cache = data.get("discoveries", [])
    return _t2_cache


@router.get("/discoveries", response_model=DiscoveriesResponse)
async def list_discoveries():
    raw_items = _load_a_grade()
    items = []
    for raw in raw_items:
        item = dict(raw)
        literature = item.get("literature_evidence") or []
        reviewed = bool(literature) and all(
            isinstance(value, dict) and value.get("source") and value.get("source_review")
            for value in literature
        )
        # No discovery currently has a claim-ledger binding.  Even reviewed
        # literature therefore remains a public candidate until one is added.
        item["evidence"] = build_evidence_envelope(
            candidate_kind="discovery_candidate",
            candidate_label=item.get("paper_title") or item.get("one_line_verdict"),
            candidate_score=_confidence_score(item.get("isomorphism_confidence")),
            requested_level="source_backed" if reviewed else "candidate",
            source_kind="external_source" if reviewed else "not_recorded",
            source_label=(literature[0].get("source") if reviewed else None),
            source_url=(literature[0].get("source") if reviewed else None),
            source_review=(literature[0].get("source_review") if reviewed else None),
            counterexample_status="gap_recorded" if item.get("risk") else "not_recorded",
            counterexample_summary=_summary(item.get("risk")),
        )
        items.append(item)
    tier2 = []
    for raw in _load_tier2():
        item = dict(raw)
        item["evidence"] = build_evidence_envelope(
            candidate_kind="tier2_discovery_candidate",
            candidate_label=item.get("one_line_verdict") or item.get("paper_title"),
            candidate_score=_confidence_score(item.get("isomorphism_confidence", item.get("similarity"))),
            counterexample_status="not_recorded",
        )
        tier2.append(item)
    # Stats — v2 scores are floats (e.g. 9.65), bucket by integer floor for charting
    by_score: dict = {}
    by_status: dict = {}
    for x in items:
        s = x.get("final_score", 0)
        try:
            bucket = str(int(float(s)))
        except (TypeError, ValueError):
            bucket = "0"
        by_score[bucket] = by_score.get(bucket, 0) + 1
        st = x.get("literature_status", "未知")
        by_status[st] = by_status.get(st, 0) + 1
    return {
        "count": len(items),
        "discoveries": items,
        "tier2_count": len(tier2),
        "tier2": tier2,
        "stats": {
            "by_score": by_score,
            "by_status": by_status,
        },
    }
