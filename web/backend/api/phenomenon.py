"""GET /api/phenomenon/{id} — 获取现象详情 + 相似项 + v2 跨域对"""
from fastapi import APIRouter, HTTPException, Query

from services.translation import translate_kb_item, translate_kb_items
from services.v2_pairs import get_pairs_for

router = APIRouter(tags=["phenomenon"])


@router.get("/phenomenon/{phenomenon_id}")
async def get_phenomenon(
    phenomenon_id: str,
    lang: str = Query("zh", description="Output language: 'zh' (default) or 'en'"),
):
    from main import app_state

    svc = app_state.get("search")
    if not svc:
        raise HTTPException(503, "Search service not ready")

    item = svc.get_by_id(phenomenon_id)
    if not item:
        raise HTTPException(404, f"Phenomenon '{phenomenon_id}' not found")

    similar = svc.get_similar(phenomenon_id, top_k=8)
    same_structure = svc.get_same_structure(
        item.get("type_id", ""), exclude_id=phenomenon_id, limit=5
    )

    # V2 cross-domain pairs enrichment (hub view)
    v2_pairs = get_pairs_for(phenomenon_id, limit=20)

    # When lang=en, translate the Chinese KB fields on-the-fly. The zh path
    # is a no-op passthrough, so legacy behavior is preserved.
    lang_norm = (lang or "zh").lower()
    if lang_norm == "en":
        item = await translate_kb_item(item, lang_norm)
        similar = await translate_kb_items(similar, lang_norm)
        same_structure = await translate_kb_items(same_structure, lang_norm)

    return {
        "phenomenon": item,
        "similar": similar,
        "same_structure": same_structure,
        "v2_pairs": v2_pairs,
    }
