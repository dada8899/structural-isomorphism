"""GET /api/phenomenon/{id} — 现象详情与候选结构邻域。"""
import math
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query

from schemas import PhenomenonResponse
from services.evidence_envelope import build_evidence_envelope
from services.translation import translate_kb_item, translate_kb_items
from services.v2_pairs import get_pairs_for

router = APIRouter(tags=["phenomenon"])


def _with_candidate_evidence(
    item: dict,
    *,
    candidate_kind: str,
    source_label: str,
    gap_summary: str,
    screen_summary: str | None = None,
    independence_summary: str | None = None,
) -> dict:
    """Return a new row with evidence local to this exact candidate.

    The four phenomenon collections have different generation paths.  Keeping
    the envelope construction per row prevents a V2 screen, embedding score,
    or type label from accidentally lending provenance to a neighboring row.
    """
    shaped = dict(item)
    evidence_args = {
        "candidate_kind": candidate_kind,
        "candidate_label": shaped.get("name") or shaped.get("other_name"),
        # Retrieval rank lives in a single explicitly labelled top-level field.
        # Repeating it in the evidence envelope makes a ranking signal look
        # like an independent evidence score.
        "candidate_score": None,
        "source_kind": "internal_kb",
        "source_label": source_label,
        "counterexample_status": "gap_recorded",
        "counterexample_summary": gap_summary,
    }
    if screen_summary:
        evidence_args.update(
            result_provenance="INTERNAL_AI_SCREEN",
            result_verdict="INCONCLUSIVE",
            result_summary=screen_summary,
            independence_kind="internal",
            independence_summary=independence_summary,
        )
    shaped["evidence"] = build_evidence_envelope(**evidence_args)
    return shaped


def _public_record(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "domain": item.get("domain"),
        "type_id": item.get("type_id"),
        "description": item.get("description"),
    }


def _public_v2_candidate(item: dict) -> dict:
    return {
        "other_id": item.get("other_id"),
        "other_name": item.get("other_name"),
        "other_domain": item.get("other_domain"),
        "candidate_reason": item.get("reason"),
        "retrieval_similarity": _retrieval_similarity(item.get("similarity")),
    }


def _retrieval_similarity(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("retrieval similarity must be numeric")
    score = float(value)
    if not math.isfinite(score) or score < -0.000001 or score > 1.000001:
        raise ValueError("retrieval similarity is outside public bounds")
    return max(0.0, min(1.0, score))


def _evidence_copy(lang: str) -> dict[str, str]:
    if lang == "en":
        return {
            "record_source": "Structural internal KB phenomenon record",
            "similar_source": "Structural embedding-neighborhood index",
            "same_source": "Structural candidate-structure label index",
            "v2_source": "Structural V2 pair index",
            "record_gap": "External source, license, and source review are not recorded for this KB record.",
            "similar_gap": "Variable mapping, causal direction, boundary conditions, and counterexamples have not been tested.",
            "same_gap": "A shared label does not test variable mapping, causal direction, boundaries, or counterexamples.",
            "v2_gap": "This pair has not been source-checked, falsification-tested, or independently replicated.",
            "similar_screen": "Embedding-neighborhood candidate; similarity does not establish a shared mechanism.",
            "same_screen": "Shared internal candidate label; it does not establish a shared mechanism.",
            "v2_screen": "Internal V2 AI score; not independent validation.",
            "internal_only": "Generated within the same project pipeline; no external reviewer or independent team is recorded.",
        }
    return {
        "record_source": "Structural 内部 KB 现象记录",
        "similar_source": "Structural 嵌入邻域索引",
        "same_source": "Structural 候选结构标签索引",
        "v2_source": "Structural V2 配对索引",
        "record_gap": "该 KB 记录尚未记录外部来源、许可和来源复核。",
        "similar_gap": "尚未检验变量映射、因果方向、边界条件和反例。",
        "same_gap": "共享标签不等于已检验变量映射、因果方向、边界与反例。",
        "v2_gap": "该配对尚未完成来源核对、证伪检验或独立复现。",
        "similar_screen": "嵌入邻域候选；相似度不足以确认共享机制。",
        "same_screen": "共享内部候选结构标签；不等于共享机制已确认。",
        "v2_screen": "V2 内部 AI 评分；不是独立验证。",
        "internal_only": "由同一项目管道生成；未记录外部评审者或独立团队。",
    }


@router.get("/phenomenon/{phenomenon_id}", response_model=PhenomenonResponse)
async def get_phenomenon(
    phenomenon_id: str = Path(
        ..., min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    ),
    lang: Literal["zh", "en"] = Query(
        "zh", description="Output language: 'zh' (default) or 'en'"
    ),
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

    try:
        item = _public_record(item)
        similar = [
            {
                **_public_record(row),
                "retrieval_similarity": _retrieval_similarity(row.get("score")),
            }
            for row in similar
        ]
        same_structure = [_public_record(row) for row in same_structure]
        v2_pairs = [_public_v2_candidate(row) for row in v2_pairs]
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, "Phenomenon candidate data is invalid") from exc

    copy = _evidence_copy(lang_norm)
    item = _with_candidate_evidence(
        item,
        candidate_kind="phenomenon_kb_record_candidate",
        source_label=copy["record_source"],
        gap_summary=copy["record_gap"],
    )
    similar = [
        _with_candidate_evidence(
            row,
            candidate_kind="embedding_neighbor_candidate",
            source_label=copy["similar_source"],
            gap_summary=copy["similar_gap"],
            screen_summary=copy["similar_screen"],
            independence_summary=copy["internal_only"],
        )
        for row in similar
    ]
    same_structure = [
        _with_candidate_evidence(
            row,
            candidate_kind="shared_type_label_candidate",
            source_label=copy["same_source"],
            gap_summary=copy["same_gap"],
            screen_summary=copy["same_screen"],
            independence_summary=copy["internal_only"],
        )
        for row in same_structure
    ]
    v2_pairs = [
        _with_candidate_evidence(
            row,
            candidate_kind="v2_model_pair_candidate",
            source_label=copy["v2_source"],
            gap_summary=copy["v2_gap"],
            screen_summary=copy["v2_screen"],
            independence_summary=copy["internal_only"],
        )
        for row in v2_pairs
    ]

    response = {
        "phenomenon": item,
        "similar": similar,
        "same_structure": same_structure,
        "v2_pairs": v2_pairs,
    }
    try:
        return PhenomenonResponse.model_validate(response).model_dump(mode="json")
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, "Phenomenon response is invalid") from exc
