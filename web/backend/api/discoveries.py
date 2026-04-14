"""GET /api/discoveries — A 级发现列表 + tier2 候选池"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

router = APIRouter(tags=["discoveries"])

_a_cache: Optional[list] = None
_t2_cache: Optional[list] = None


def _load_a_grade():
    global _a_cache
    if _a_cache is not None:
        return _a_cache
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


@router.get("/discoveries")
async def list_discoveries():
    items = _load_a_grade()
    tier2 = _load_tier2()
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
