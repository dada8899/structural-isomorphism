from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.research_fingerprint import (
    ConfirmedResearchFingerprint,
    FINGERPRINT_HINT_MAX_CHARS,
    bounded_fingerprint_rerank,
    build_fingerprint_retrieval_hint,
)


def fingerprint(**overrides):
    payload = {
        "source_query": "为什么需求过冲会导致库存反复积压？",
        "summary": "补货反馈存在时滞，需求冲击可能被连续放大",
        "variables": ["需求冲击", "补货延迟"],
        "constraints": ["不增加长期库存"],
        "unknowns": ["反馈方向"],
        "revision": 1,
    }
    payload.update(overrides)
    return ConfirmedResearchFingerprint.model_validate(payload)


def test_fingerprint_normalizes_nfkc_and_layout_whitespace():
    value = fingerprint(
        source_query="为什么需求过冲会导致库存反复积压？\n",
        summary="补货反馈存在时滞，\n需求冲击可能被连续放大",
        variables=["Ａ库存"],
    )
    assert value.source_query == "为什么需求过冲会导致库存反复积压?"
    assert value.summary == "补货反馈存在时滞, 需求冲击可能被连续放大"
    assert value.variables == ["A库存"]


@pytest.mark.parametrize("bad", ["变量\u200b名", "变量\ufe0f名", "变量\u034f名", "变量\ud800名"])
def test_fingerprint_rejects_invisible_and_surrogate_text(bad):
    with pytest.raises(ValidationError):
        fingerprint(variables=[bad])


def test_fingerprint_is_strict_and_extra_forbidden():
    with pytest.raises(ValidationError):
        fingerprint(revision=True)
    with pytest.raises(ValidationError):
        fingerprint(unexpected="value")
    with pytest.raises(ValidationError):
        fingerprint(variables=["库存", "库存"])


def test_fingerprint_enforces_item_and_collection_bounds():
    with pytest.raises(ValidationError):
        fingerprint(summary="太短")
    with pytest.raises(ValidationError):
        fingerprint(variables=[str(index) for index in range(13)])
    with pytest.raises(ValidationError):
        fingerprint(constraints=["x" * 121])


def test_retrieval_hint_is_bounded_and_omits_raw_source_query():
    value = fingerprint(summary="S" * 1000, variables=["V" * 120] * 1, constraints=["C" * 120])
    hint = build_fingerprint_retrieval_hint(value)
    assert len(hint) <= FINGERPRINT_HINT_MAX_CHARS
    assert value.source_query not in hint
    assert hint.startswith("S" * 20)
    assert "variables:" in hint


def test_bounded_rerank_can_reorder_only_close_raw_candidates():
    original = [
        {"id": "a", "score": 0.51},
        {"id": "b", "score": 0.50},
        {"id": "c", "score": 0.10},
    ]
    fingerprint_results = [{"id": "b", "score": 1.0}, {"id": "outside", "score": 1.0}]
    reranked = bounded_fingerprint_rerank(original, fingerprint_results, top_k=3)
    assert [row["id"] for row in reranked] == ["b", "a", "c"]
    assert reranked[0]["score"] == 0.50
    assert {row["id"] for row in reranked} == {"a", "b", "c"}


def test_bounded_rerank_cannot_overcome_large_raw_gap_or_add_candidates():
    original = [{"id": "a", "score": 0.80}, {"id": "b", "score": 0.50}]
    fingerprint_results = [{"id": "outside", "score": 99}, {"id": "b", "score": 99}]
    reranked = bounded_fingerprint_rerank(original, fingerprint_results, top_k=5)
    assert [row["id"] for row in reranked] == ["a", "b"]
    assert all(row["id"] != "outside" for row in reranked)


def test_bounded_rerank_rejects_duplicate_or_invalid_original_rows():
    original = [
        {"id": "a", "score": float("nan")},
        {"id": "a", "score": 1.0},
        {"id": "", "score": 1.0},
        {"id": "b", "score": True},
        None,
    ]
    reranked = bounded_fingerprint_rerank(original, [{"id": "b"}], top_k=2)
    assert [row["id"] for row in reranked] == ["b", "a"]


def test_bounded_rerank_zero_top_k_is_empty():
    assert bounded_fingerprint_rerank([{"id": "a", "score": 1}], [], top_k=0) == []
