from __future__ import annotations

import asyncio
import copy
import math

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from web.backend.schemas import DailyResponse, DiscoveriesResponse
from web.backend.services.discovery_contract import (
    build_family_index,
    finite_number,
    shape_discovery_candidate,
    validate_catalog_rows,
)


def sample(**overrides):
    row = {
        "rank": 1,
        "a_id": "a-1", "b_id": "b-1",
        "a_name": "系统 A", "a_name_en": "System A",
        "b_name": "系统 B", "b_name_en": "System B",
        "a_domain": "领域 A", "a_domain_en": "Domain A",
        "b_domain": "领域 B", "b_domain_en": "Domain B",
        "pipeline": "V2",
        "equations": ["dx/dt = f(x)"],
        "risk": "共同冲击可能产生相同表象。",
        "risk_en": "A common shock may produce the same appearance.",
        "target_venue": "Prestigious Journal",
        "full_analysis": "This internal prose must never enter the public contract.",
        "isomorphism_confidence": 99.9,
    }
    row.update(overrides)
    return row


def shape(row=None, *, family_id="pair-0123456789ab", count=1):
    return shape_discovery_candidate(
        row or sample(), tier="priority_review", family_id=family_id, family_variant_count=count
    )


def test_public_candidate_omits_publication_hype_and_uncalibrated_scores() -> None:
    card = shape()
    text = repr(card)
    for forbidden in ("Prestigious Journal", "internal prose", "99.9", "target_venue", "full_analysis"):
        assert forbidden not in text
    assert card["readiness"]["status"] == "blocked"
    assert card["validation_plan"]["preregistered"] is False


def test_plan_is_actionable_but_explicitly_incomplete() -> None:
    plan = shape()["validation_plan"]
    assert plan["status"] == "draft_requires_user_completion"
    assert plan["primary_metric"]["zh"] == "待定义"
    assert "比较方法" in plan["failure_condition"]["zh"]
    assert {gap["gap_id"] for gap in plan["validation_gaps"]} == {
        "source_support_not_reviewed",
        "candidate_equation_not_expert_reviewed",
        "variable_mapping_not_recorded",
        "competing_explanations_not_tested",
        "dataset_and_sampling_not_recorded",
        "baseline_and_stop_rule_not_preregistered",
    }


def test_internal_risk_and_blocking_prose_never_crosses_public_boundary() -> None:
    card = shape(sample(
        risk="本候选已证明，必须立即投稿顶刊。",
        risk_en="This mechanism is proven and must be published immediately.",
        blocking_mechanisms=["统一形式已经成立", "Journal submission is the next step"],
        blocking_mechanisms_en=["The isomorphism is proven"],
    ))
    public_text = repr(card)
    for forbidden in (
        "已证明", "立即投稿", "顶刊", "统一形式已经成立",
        "mechanism is proven", "published immediately", "Journal submission",
        "isomorphism is proven",
    ):
        assert forbidden not in public_text


def test_unexposed_english_fields_cannot_claim_bilingual_evidence() -> None:
    card = shape(sample(
        equations=["dx/dt = f(x)"],
        shared_equation_en="dx/dt = f(x)",
        variable_mapping_en={"state": "state"},
    ))
    assert card["evidence_language"] == "zh_only"

    empty = shape(sample(equations=[], shared_equation=None, variable_mapping=None,
                         shared_equation_en="English-only", variable_mapping_en={"x": "y"}))
    assert empty["evidence_language"] == "not_recorded"
    assert empty["readiness"]["blockers"][:2] == ["candidate_equation", "variable_mapping"]
    gap_ids = {gap["gap_id"] for gap in empty["validation_plan"]["validation_gaps"]}
    assert "candidate_equation_not_recorded" in gap_ids
    assert "variable_mapping_not_recorded" in gap_ids
    assert "candidate_equation_not_expert_reviewed" not in gap_ids
    assert "variable_mapping_not_expert_reviewed" not in gap_ids


def test_equation_and_mapping_readiness_are_reported_independently() -> None:
    equation_only = shape(sample(variable_mapping=None))
    assert "candidate_equation" not in equation_only["readiness"]["blockers"]
    assert "variable_mapping" in equation_only["readiness"]["blockers"]
    assert [gap["gap_id"] for gap in equation_only["validation_plan"]["validation_gaps"]][1:3] == [
        "candidate_equation_not_expert_reviewed",
        "variable_mapping_not_recorded",
    ]

    mapping_only = shape(sample(equations=[], variable_mapping={"库存": "stored energy"}))
    assert "candidate_equation" in mapping_only["readiness"]["blockers"]
    assert "variable_mapping" not in mapping_only["readiness"]["blockers"]
    assert [gap["gap_id"] for gap in mapping_only["validation_plan"]["validation_gaps"]][1:3] == [
        "candidate_equation_not_recorded",
        "variable_mapping_not_expert_reviewed",
    ]


def test_localized_equations_preserve_zh_and_reject_malformed_shapes() -> None:
    card = shape(sample(equations=[
        "plain equation",
        {"zh": "中文方程", "en": "English equation"},
    ]))
    assert card["candidate_equations"] == ["plain equation", "中文方程"]

    for malformed in (
        [{"en": "missing zh"}],
        [{"zh": "ok", "extra": "hidden"}],
        [{"zh": "ok", "en": 7}],
        [7],
    ):
        with pytest.raises(ValueError):
            shape(sample(equations=malformed))


def test_family_index_uses_repeated_immutable_anchor() -> None:
    rows = [sample(rank=1), sample(rank=2, b_id="c-1"), sample(rank=3, a_id="d-1", b_id="e-1")]
    index = build_family_index(rows)
    first = index[("a-1", "b-1")]
    second = index[("a-1", "c-1")]
    assert first == second
    assert first[1] == 2
    assert index[("d-1", "e-1")][1] == 1


def test_family_variant_count_uses_final_assignment_not_anchor_frequency() -> None:
    rows = [
        sample(rank=1, a_id="anchor-a", b_id="only-a"),
        sample(rank=2, a_id="anchor-a", b_id="anchor-b"),
        sample(rank=3, a_id="anchor-b", b_id="only-b"),
    ]
    index = build_family_index(rows)
    assert index[("anchor-a", "only-a")][1] == 2
    assert index[("anchor-a", "anchor-b")][1] == 2
    assert index[("anchor-b", "only-b")][1] == 1


def test_candidate_id_survives_queue_promotion_pipeline_and_rank_changes() -> None:
    row = sample(rank=1, pipeline="V2")
    priority = shape_discovery_candidate(
        row, tier="priority_review", family_id="pair-aaaaaaaaaaaa", family_variant_count=1
    )
    reranked = shape_discovery_candidate(
        {**row, "rank": 55, "pipeline": "V3"},
        tier="priority_review", family_id="pair-aaaaaaaaaaaa", family_variant_count=1,
    )
    promoted = shape_discovery_candidate(
        {**row, "rank": 99, "pipeline": None},
        tier="candidate_pool", family_id="pair-bbbbbbbbbbbb", family_variant_count=4,
    )
    assert priority["discovery_id"] == reranked["discovery_id"] == promoted["discovery_id"]


def test_candidate_analyze_url_preserves_stable_origin_identity() -> None:
    from urllib.parse import parse_qs, urlsplit

    card = shape()
    parsed = urlsplit(card["analyze_url"])
    assert parsed.path == "/analyze"
    assert parse_qs(parsed.query) == {
        "a_id": [card["pair"]["a"]["id"]],
        "id": [card["pair"]["b"]["id"]],
        "origin_discovery_id": [card["discovery_id"]],
        "origin_contract_version": [card["schema_version"]],
    }


def test_api_groups_candidate_families_across_review_queues(monkeypatch) -> None:
    from api import discoveries

    priority = sample(rank=1, a_id="shared-anchor", b_id="priority-only")
    pool = sample(rank=2, a_id="shared-anchor", b_id="pool-only", pipeline=None)
    monkeypatch.setattr(discoveries, "_load_a_grade", lambda: [priority])
    monkeypatch.setattr(discoveries, "_load_tier2", lambda: [pool])

    payload = asyncio.run(discoveries.list_discoveries())
    first, second = payload["discoveries"][0], payload["tier2"][0]
    assert first["candidate_family_id"] == second["candidate_family_id"]
    assert first["family_variant_count"] == second["family_variant_count"] == 2
    assert payload["stats"]["candidate_families"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        {"a_id": ""}, {"b_id": "a-1"}, {"rank": 0}, {"rank": True},
        {"a_name": "\x00\x01"}, {"a_domain": None},
    ],
)
def test_invalid_identity_and_blank_fields_fail_closed(mutation) -> None:
    with pytest.raises(ValueError):
        shape(sample(**mutation))


@pytest.mark.parametrize("value", ["safe&evil=1", "#fragment", "line\nbreak", " spaced", "fullwidthＡ"])
def test_identifiers_reject_url_delimiters_controls_and_alias_forms(value) -> None:
    with pytest.raises(ValueError):
        shape(sample(a_id=value))


def test_unicode_format_controls_are_removed_from_public_text_and_download_fields() -> None:
    card = shape(sample(a_name="safe\u202egpj.exe", risk="claim\u2066hidden"))
    assert "\u202e" not in repr(card) and "\u2066" not in repr(card)
    assert card["pair"]["a"]["name"]["zh"] == "safegpj.exe"


def test_catalog_validation_rejects_empty_non_object_duplicate_rank_and_pair() -> None:
    for rows in (
        [],
        ["not-an-object"],
        [sample(rank=1), sample(rank=1, a_id="a-2", b_id="b-2")],
        [sample(rank=1), sample(rank=2)],
        [sample(rank=1), sample(rank=2, a_id="b-1", b_id="a-1")],
    ):
        with pytest.raises(ValueError):
            validate_catalog_rows(rows, catalog="test")


@pytest.mark.parametrize(
    "catalog,row",
    [
        ("priority_review", sample(pipeline=None)),
        ("priority_review", sample(pipeline="V9")),
        ("candidate_pool", sample(pipeline="V2")),
    ],
)
def test_catalog_pipeline_assignment_is_fail_closed(catalog, row) -> None:
    with pytest.raises(ValueError):
        validate_catalog_rows([row], catalog=catalog)


@pytest.mark.parametrize("priority,pool", [([], []), (["bad-row"], [sample(rank=2)]), ([sample()], [])])
def test_api_rejects_empty_or_malformed_catalogs(monkeypatch, priority, pool) -> None:
    from api import discoveries

    monkeypatch.setattr(discoveries, "_load_a_grade", lambda: priority)
    monkeypatch.setattr(discoveries, "_load_tier2", lambda: pool)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discoveries.list_discoveries())
    assert exc.value.status_code == 503


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), -float("inf"), "nan", None])
def test_nonfinite_and_boolean_numbers_are_rejected(value) -> None:
    assert finite_number(value) is None
    if isinstance(value, float):
        assert not math.isfinite(value)


def test_response_schema_rejects_unknown_public_fields() -> None:
    card = shape()
    card["target_venue"] = "must fail"
    payload = {
        "count": 1, "discoveries": [card], "tier2_count": 0, "tier2": [],
        "stats": {
            "total_candidates": 1, "priority_review": 1, "candidate_pool": 0,
            "candidate_families": 1, "source_backed": 0, "ready_for_preregistration": 0,
        },
    }
    with pytest.raises(ValidationError):
        DiscoveriesResponse.model_validate(payload)


def test_response_schema_rejects_evidence_hype_and_internal_fields() -> None:
    card = shape()
    from services.evidence_envelope import build_evidence_envelope

    card["evidence"] = build_evidence_envelope(
        candidate_kind="discovery_candidate", candidate_label=card["candidate_summary"]["zh"]
    )
    payload = {
        "count": 1, "discoveries": [card], "tier2_count": 0, "tier2": [],
        "stats": {
            "total_candidates": 1, "priority_review": 1, "candidate_pool": 0,
            "candidate_families": 1, "source_backed": 0, "ready_for_preregistration": 0,
        },
    }
    for mutation in (
        lambda value: value["discoveries"][0]["evidence"].update(target_venue="journal"),
        lambda value: value["discoveries"][0]["evidence"]["result"].update(full_analysis="internal"),
        lambda value: value["discoveries"][0]["evidence"].update(evidence_level="replicated"),
    ):
        attacked = copy.deepcopy(payload)
        mutation(attacked)
        with pytest.raises(ValidationError):
            DiscoveriesResponse.model_validate(attacked)


def test_response_schema_rejects_count_stats_identity_and_tier_drift() -> None:
    from api import discoveries

    discoveries._a_cache = None
    discoveries._t2_cache = None
    payload = asyncio.run(discoveries.list_discoveries())
    for mutation in (
        lambda value: value.update(count=999),
        lambda value: value["stats"].update(candidate_families=999),
        lambda value: value["stats"].update(source_backed=1),
        lambda value: value["discoveries"][1].update(discovery_id=value["discoveries"][0]["discovery_id"]),
        lambda value: value["discoveries"][0].update(tier="candidate_pool"),
    ):
        attacked = copy.deepcopy(payload)
        mutation(attacked)
        with pytest.raises(ValidationError):
            DiscoveriesResponse.model_validate(attacked)


def test_response_schema_rejects_cross_field_evidence_and_readiness_drift() -> None:
    from api import discoveries

    discoveries._a_cache = None
    discoveries._t2_cache = None
    payload = asyncio.run(discoveries.list_discoveries())
    for mutation in (
        lambda value: value["discoveries"][0].update(evidence_language="not_recorded"),
        lambda value: value["tier2"][0]["readiness"]["blockers"].remove("candidate_equation"),
        lambda value: value["tier2"][0]["validation_plan"].update(validation_gaps=[]),
        lambda value: value["discoveries"][0]["provenance"].update(independent_review_complete=True),
        lambda value: value["discoveries"][0]["evidence"]["candidate"].update(score=0.99),
        lambda value: value["discoveries"][0]["evidence"]["result"].update(
            status="recorded", provenance="INTERNAL_REAL_DATA", verdict="PASS"
        ),
        lambda value: value["discoveries"][0]["evidence"]["ledger"].update(
            status="bound", claim_id="fake"
        ),
        lambda value: value["discoveries"][0]["evidence"]["counterexamples"].update(
            status="none_found", summary="No counterexample exists"
        ),
        lambda value: value["discoveries"][0]["readiness"].update(blockers=[]),
        lambda value: value["discoveries"][0].update(pipeline=None),
        lambda value: value["tier2"][0].update(pipeline="V2"),
        lambda value: value["discoveries"][0].update(family_variant_count=999),
    ):
        attacked = copy.deepcopy(payload)
        mutation(attacked)
        with pytest.raises(ValidationError):
            DiscoveriesResponse.model_validate(attacked)


def test_live_catalog_is_strict_candidate_only() -> None:
    from api import discoveries

    discoveries._a_cache = None
    discoveries._t2_cache = None
    payload = asyncio.run(discoveries.list_discoveries())
    validated = DiscoveriesResponse.model_validate(payload)
    assert validated.count == 39
    assert validated.tier2_count == 75
    assert validated.stats.total_candidates == 114
    assert validated.stats.candidate_families == 59
    assert validated.stats.source_backed == 0
    assert all(row.evidence.evidence_level == "candidate" for row in validated.discoveries + validated.tier2)
    assert all(row.readiness.ready_for_preregistration is False for row in validated.discoveries)
    assert sum(bool(row.candidate_equations) for row in validated.discoveries) == 39
    assert sum(bool(row.candidate_variable_mapping) for row in validated.discoveries) == 20
    assert sum("variable_mapping" in row.readiness.blockers for row in validated.discoveries) == 19
    assert all(
        row.readiness.blockers[:2] == ["candidate_equation", "variable_mapping"]
        for row in validated.tier2
    )
    by_rank = {row.rank: row for row in validated.discoveries}
    assert {rank: len(by_rank[rank].candidate_equations) for rank in (4, 6, 9, 10, 18)} == {
        4: 3, 6: 3, 9: 3, 10: 3, 18: 3,
    }


def test_catalog_shape_error_becomes_service_unavailable(monkeypatch) -> None:
    from api import discoveries

    monkeypatch.setattr(discoveries, "_load_a_grade", lambda: [sample(a_id="")])
    monkeypatch.setattr(discoveries, "_load_tier2", lambda: [])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discoveries.list_discoveries())
    assert exc.value.status_code == 503


def test_daily_reuses_strict_candidate_projection_without_scores(monkeypatch) -> None:
    from api import daily, discoveries

    priority = [
        sample(rank=1, a_id="a-1", b_id="b-1"),
        sample(rank=2, a_id="a-2", b_id="b-2"),
        sample(rank=3, a_id="a-3", b_id="b-3"),
    ]
    pool = [sample(rank=4, a_id="a-4", b_id="b-4", pipeline=None)]
    monkeypatch.setattr(discoveries, "_load_a_grade", lambda: priority)
    monkeypatch.setattr(discoveries, "_load_tier2", lambda: pool)

    payload = asyncio.run(daily.daily_discoveries("zh"))
    validated = DailyResponse.model_validate(payload)

    assert validated.lang == "zh"
    assert len(validated.discoveries) == 3
    assert len({row.discovery_id for row in validated.discoveries}) == 3
    assert all(row.schema_version == "discovery-candidate-v2" for row in validated.discoveries)
    assert all(row.evidence.evidence_level == "candidate" for row in validated.discoveries)
    public_text = repr(payload)
    for forbidden in (
        "isomorphism_confidence", "similarity", "target_venue", "full_analysis", "99.9"
    ):
        assert forbidden not in public_text


def test_daily_fails_closed_when_public_queue_cannot_supply_three(monkeypatch) -> None:
    from api import daily, discoveries

    monkeypatch.setattr(
        discoveries,
        "_load_a_grade",
        lambda: [sample(rank=1, a_id="a-1", b_id="b-1")],
    )
    monkeypatch.setattr(
        discoveries,
        "_load_tier2",
        lambda: [sample(rank=2, a_id="a-2", b_id="b-2", pipeline=None)],
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(daily.daily_discoveries("en"))
    assert exc.value.status_code == 503


def test_daily_schema_rejects_extra_fields_and_duplicate_candidates(monkeypatch) -> None:
    from api import daily, discoveries

    monkeypatch.setattr(
        discoveries,
        "_load_a_grade",
        lambda: [
            sample(rank=1, a_id="a-1", b_id="b-1"),
            sample(rank=2, a_id="a-2", b_id="b-2"),
        ],
    )
    monkeypatch.setattr(
        discoveries,
        "_load_tier2",
        lambda: [sample(rank=3, a_id="a-3", b_id="b-3", pipeline=None)],
    )
    payload = asyncio.run(daily.daily_discoveries("en"))

    extra = copy.deepcopy(payload)
    extra["similarity"] = 0.99
    with pytest.raises(ValidationError):
        DailyResponse.model_validate(extra)

    duplicate = copy.deepcopy(payload)
    duplicate["discoveries"][2] = copy.deepcopy(duplicate["discoveries"][0])
    with pytest.raises(ValidationError):
        DailyResponse.model_validate(duplicate)
