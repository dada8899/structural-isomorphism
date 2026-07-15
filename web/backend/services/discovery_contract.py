"""Fail-closed public contract for model-ranked discovery candidates.

The source catalog contains useful internal research prose, but it also carries
publication targets, uncalibrated scores, and mechanism claims that have not
been source-reviewed.  This module exposes only a bounded candidate record and
builds a deterministic validation-plan draft.  It never upgrades evidence.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Any, Iterable

if __package__ == "web.backend.services":
    from .candidate_origin import (
        SCHEMA_VERSION,
        analyze_url_for_candidate,
        discovery_id_for_pair,
        normalize_candidate_family_id,
        normalize_candidate_identifier,
    )
else:
    from services.candidate_origin import (
        SCHEMA_VERSION,
        analyze_url_for_candidate,
        discovery_id_for_pair,
        normalize_candidate_family_id,
        normalize_candidate_identifier,
    )

from structural_isomorphism.discovery_evidence import (
    normalize_candidate_equations,
    valid_reviewed_literature_source,
)


def _text(value: Any, *, limit: int, required: bool = False) -> str:
    if not isinstance(value, str):
        if required:
            raise ValueError("required discovery text is missing")
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    cleaned = "".join(char for char in normalized if not unicodedata.category(char).startswith("C")).strip()
    if required and not cleaned:
        raise ValueError("required discovery text is blank")
    return cleaned[:limit]


def _identifier(value: Any, field: str) -> str:
    normalized = normalize_candidate_identifier(value)
    if normalized is None:
        raise ValueError(f"invalid discovery {field}")
    return normalized


def _localized(raw: dict[str, Any], key: str, *, required: bool = False) -> dict[str, str]:
    zh = _text(raw.get(key), limit=500, required=required)
    en = _text(raw.get(f"{key}_en"), limit=500)
    return {"zh": zh, "en": en}


def _variable_mapping(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        pairs = value.items()
    elif isinstance(value, str):
        parsed: list[tuple[str, str]] = []
        for segment in re.split(r"[;；]", value):
            parts = re.split(r"↔|→|=>", segment, maxsplit=1)
            if len(parts) == 2:
                parsed.append((parts[0], parts[1]))
        pairs = parsed
    else:
        return {}
    result: dict[str, str] = {}
    for left, right in pairs:
        left_text = _text(left, limit=120)
        right_text = _text(right, limit=240)
        if left_text and right_text and left_text not in result:
            result[left_text] = right_text
    return result


def _pair_ids(raw: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("discovery catalog row must be an object")
    a_id = _identifier(raw.get("a_id"), "a_id")
    b_id = _identifier(raw.get("b_id"), "b_id")
    if a_id == b_id:
        raise ValueError("discovery pair must contain two distinct KB ids")
    return a_id, b_id


def validate_catalog_rows(rows: Any, *, catalog: str) -> list[dict[str, Any]]:
    """Validate catalog-wide invariants before grouping or rendering."""
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{catalog} discovery catalog must be a non-empty list")
    ranks: set[int] = set()
    pairs: set[tuple[str, str]] = set()
    clean: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{catalog} discovery catalog row must be an object")
        pipeline = row.get("pipeline")
        if catalog == "priority_review" and pipeline not in {"V2", "V3"}:
            raise ValueError("priority-review discovery pipeline must be V2 or V3")
        if catalog == "candidate_pool" and pipeline is not None:
            raise ValueError("candidate-pool discovery pipeline must be unassigned")
        rank = row.get("rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1 or rank in ranks:
            raise ValueError(f"{catalog} discovery ranks must be unique positive integers")
        pair = _pair_ids(row)
        canonical_pair = tuple(sorted(pair))
        if canonical_pair in pairs:
            raise ValueError(f"{catalog} discovery pairs must be unique")
        ranks.add(rank)
        pairs.add(canonical_pair)
        clean.append(row)
    return clean


def _digest(*parts: str, size: int = 16) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:size]


def build_family_index(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], tuple[str, int]]:
    """Group variants by a repeated immutable KB anchor, never by model prose."""
    parsed: list[tuple[str, str]] = [_pair_ids(row) for row in rows]
    frequency = Counter(node for pair in parsed for node in pair)
    assigned: dict[tuple[str, str], str] = {}
    for pair in parsed:
        repeated = sorted((node for node in pair if frequency[node] > 1), key=lambda node: (-frequency[node], node))
        if repeated:
            anchor = repeated[0]
            assigned[pair] = f"anchor-{_digest(anchor, size=12)}"
        else:
            ordered = tuple(sorted(pair))
            assigned[pair] = f"pair-{_digest(*ordered, size=12)}"

    # An edge with two repeated nodes is assigned to exactly one deterministic
    # anchor.  Count the resulting family membership, not the anchor's global
    # incident-edge frequency; otherwise the card can claim four variants while
    # only two rows actually carry that candidate_family_id.
    family_sizes = Counter(assigned.values())
    return {pair: (family_id, family_sizes[family_id]) for pair, family_id in assigned.items()}


def _source_progress(raw: dict[str, Any]) -> dict[str, Any]:
    entries = raw.get("literature_evidence")
    entries = entries if isinstance(entries, list) else []
    recorded = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if valid_reviewed_literature_source(entry):
            recorded += 1
    return {
        "status": "not_started" if recorded == 0 else "incomplete_review",
        "recorded_source_count": recorded,
        "independent_review_complete": False,
        "systematic_search_recorded": False,
    }


def _validation_gaps(*, has_candidate_equation: bool, has_variable_mapping: bool) -> list[dict[str, Any]]:
    """Return policy-owned gaps without echoing unreviewed model prose.

    The internal catalog's ``risk`` and ``blocking_mechanisms`` fields may
    contain publication recommendations or mechanism claims.  Their *content*
    must therefore never cross the public boundary.  This checklist is fixed
    by product policy; the only catalog-derived signals are whether a candidate
    equation and a variable-to-variable mapping were actually recorded.
    """
    gaps: list[dict[str, Any]] = [
        {
            "gap_id": "source_support_not_reviewed",
            "label": {
                "zh": "来源支持尚未经过独立复核。",
                "en": "Source support has not been independently reviewed.",
            },
        },
    ]
    if has_candidate_equation:
        gaps.append(
            {
                "gap_id": "candidate_equation_not_expert_reviewed",
                "label": {
                    "zh": "候选方程尚未经过领域专家复核。",
                    "en": "The candidate equations have not been expert-reviewed.",
                },
            }
        )
    else:
        gaps.append(
            {
                "gap_id": "candidate_equation_not_recorded",
                "label": {
                    "zh": "待检验的候选方程尚未记录。",
                    "en": "The candidate equation has not been recorded.",
                },
            }
        )
    if has_variable_mapping:
        gaps.append(
            {
                "gap_id": "variable_mapping_not_expert_reviewed",
                "label": {
                    "zh": "两边变量的对应关系尚未经过领域专家复核。",
                    "en": "The proposed variable mapping has not been expert-reviewed.",
                },
            }
        )
    else:
        gaps.append(
            {
                "gap_id": "variable_mapping_not_recorded",
                "label": {
                    "zh": "两边哪些变量一一对应尚未记录。",
                    "en": "The variable-to-variable mapping has not been recorded.",
                },
            }
        )
    gaps.extend(
        [
            {
                "gap_id": "competing_explanations_not_tested",
                "label": {
                    "zh": "其他可能解释，以及按理不应出现这种效果的比较组（负对照），尚未检验。",
                    "en": "Alternative explanations and comparison groups that should not show the effect (negative controls) have not been tested.",
                },
            },
            {
                "gap_id": "dataset_and_sampling_not_recorded",
                "label": {
                    "zh": "数据集、抽样窗口与处理步骤尚未记录。",
                    "en": "The dataset, sampling window, and processing steps have not been recorded.",
                },
            },
            {
                "gap_id": "baseline_and_stop_rule_not_preregistered",
                "label": {
                    "zh": "基线、主指标与停止规则尚未在实验前公开锁定（预注册）。",
                    "en": "The baseline, primary metric, and stopping rule have not been publicly locked before the study (preregistered).",
                },
            },
        ]
    )
    return gaps


def _validation_plan(
    a: dict[str, str], b: dict[str, str], gaps: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "status": "draft_requires_user_completion",
        "hypothesis": {
            "zh": f"检验「{a['zh']}」与「{b['zh']}」的结构对应，能否给出只有一种解释成立时才会出现的预测。",
            "en": f"Test whether the proposed structural mapping between {a['en'] or a['zh']} and {b['en'] or b['zh']} predicts an outcome that only one explanation should produce.",
        },
        "data_needed": {
            "zh": "分别记录两侧数据来源、样本窗口、单位、许可与处理步骤；当前目录尚未提供这些记录。",
            "en": "Record source, sample window, units, license, and processing steps for both sides; the current catalog does not yet provide them.",
        },
        "baseline": {
            "zh": "与同领域解释、未采用跨域迁移的方法，以及按理不应出现这种效果的比较组（负对照）比较。",
            "en": "Compare with a within-domain explanation, a method that uses no cross-domain transfer, and a group that should not show the effect (negative control).",
        },
        "primary_metric": {"zh": "待定义", "en": "To be defined"},
        "failure_condition": {
            "zh": "若映射不能给出只有一种解释成立时才会出现的预测，或比较方法达到同等结果，则拒绝本次迁移主张。",
            "en": "Reject the transfer claim if the mapping predicts nothing unique to one explanation or the comparison method performs equally well.",
        },
        "validation_gaps": gaps,
        "preregistered": False,
    }


def shape_discovery_candidate(
    raw: dict[str, Any], *, tier: str, family_id: str, family_variant_count: int
) -> dict[str, Any]:
    if tier not in {"priority_review", "candidate_pool"}:
        raise ValueError("invalid discovery tier")
    normalized_family_id = normalize_candidate_family_id(family_id)
    if normalized_family_id is None:
        raise ValueError("invalid discovery family id")
    if (
        isinstance(family_variant_count, bool)
        or not isinstance(family_variant_count, int)
        or family_variant_count < 1
    ):
        raise ValueError("invalid discovery family variant count")
    a_id, b_id = _pair_ids(raw)
    a_name = _localized(raw, "a_name", required=True)
    b_name = _localized(raw, "b_name", required=True)
    a_domain = _localized(raw, "a_domain", required=True)
    b_domain = _localized(raw, "b_domain", required=True)
    rank = raw.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        raise ValueError("discovery rank must be a positive integer")
    equations = normalize_candidate_equations(raw)
    mapping = _variable_mapping(raw.get("variable_mapping"))
    has_candidate_equation = bool(equations)
    has_variable_mapping = bool(mapping)
    gaps = _validation_gaps(
        has_candidate_equation=has_candidate_equation,
        has_variable_mapping=has_variable_mapping,
    )
    pipeline = raw.get("pipeline")
    if tier == "priority_review" and pipeline not in {"V2", "V3"}:
        raise ValueError("priority-review discovery pipeline must be V2 or V3")
    if tier == "candidate_pool" and pipeline is not None:
        raise ValueError("candidate-pool discovery pipeline must be unassigned")
    # Public identity belongs to the immutable pair, not its mutable queue,
    # rank, or generating pipeline. Promotion/reordering must not break links.
    identifier = discovery_id_for_pair(a_id, b_id)
    # Only the Chinese equation/mapping fields cross this public contract.
    # English-looking fields in the internal catalog cannot justify a
    # bilingual label until they are exposed and independently validated.
    evidence_language = "zh_only" if equations or mapping else "not_recorded"
    return {
        "schema_version": SCHEMA_VERSION,
        "discovery_id": identifier,
        "candidate_family_id": normalized_family_id,
        "family_variant_count": family_variant_count,
        "rank": rank,
        "tier": tier,
        "pipeline": pipeline,
        "pair": {
            "a": {"id": a_id, "name": a_name, "domain": a_domain},
            "b": {"id": b_id, "name": b_name, "domain": b_domain},
        },
        "candidate_summary": {
            "zh": f"比较「{a_name['zh']}」与「{b_name['zh']}」的变量、适用边界，以及只有一种解释成立时才会出现的预测；当前仅为 AI 排序候选。",
            "en": f"Compare {a_name['en'] or a_name['zh']} with {b_name['en'] or b_name['zh']} through variables, limits, and predictions unique to one explanation; this remains an AI-ranked candidate.",
        },
        "candidate_equations": equations,
        "candidate_variable_mapping": mapping,
        "evidence_language": evidence_language,
        "provenance": _source_progress(raw),
        "readiness": {
            "status": "blocked",
            "ready_for_preregistration": False,
            "blockers": (
                ([] if has_candidate_equation else ["candidate_equation"])
                + ([] if has_variable_mapping else ["variable_mapping"])
                + ["source_review", "dataset_record", "primary_metric", "preregistered_stop_rule"]
            ),
        },
        "validation_plan": _validation_plan(a_name, b_name, gaps),
        "analyze_url": analyze_url_for_candidate(
            a_id=a_id,
            b_id=b_id,
            discovery_id=identifier,
            contract_version=SCHEMA_VERSION,
        ),
    }


def finite_number(value: Any) -> float | None:
    """Boundary helper retained for catalog validation and adversarial tests."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
