"""JudgePanel integration tests with mock clients."""
from __future__ import annotations

import json
from typing import Any

from cross_judge import JudgePanel, Reviewer


def _make_reviewer_with_verdict(rid: str, verdict: str, conf: float, make_mock_client) -> Reviewer:
    def _responder(_k: dict[str, Any]) -> str:
        return json.dumps({"verdict": verdict, "confidence": conf, "rationale": f"{rid} said {verdict}"})

    return Reviewer(
        reviewer_id=rid,
        model="mock-m",
        client=make_mock_client(_responder),
    )


def test_panel_majority_consensus(make_mock_client):
    reviewers = [
        _make_reviewer_with_verdict("a", "KEEP", 0.9, make_mock_client),
        _make_reviewer_with_verdict("b", "KEEP", 0.8, make_mock_client),
        _make_reviewer_with_verdict("c", "REJECT", 0.7, make_mock_client),
    ]
    panel = JudgePanel(reviewers=reviewers, strategy="majority")
    result = panel.ask(item_id="item-1", user_prompt="Is this thing X?")
    assert result.item_id == "item-1"
    assert len(result.verdicts) == 3
    assert result.consensus == "KEEP"
    assert result.disagreement is True
    assert abs(result.avg_confidence - 0.8) < 1e-9
    assert result.strategy == "majority"


def test_panel_unanimous_all_agree(make_mock_client):
    reviewers = [
        _make_reviewer_with_verdict("a", "PASS", 0.9, make_mock_client),
        _make_reviewer_with_verdict("b", "PASS", 0.8, make_mock_client),
    ]
    panel = JudgePanel(reviewers=reviewers, strategy="unanimous")
    result = panel.ask("item-2", "u")
    assert result.consensus == "PASS"
    assert result.disagreement is False


def test_panel_unanimous_falls_back_on_disagreement(make_mock_client):
    reviewers = [
        _make_reviewer_with_verdict("a", "PASS", 0.9, make_mock_client),
        _make_reviewer_with_verdict("b", "FAIL", 0.9, make_mock_client),
    ]
    panel = JudgePanel(
        reviewers=reviewers,
        strategy="unanimous",
        strategy_kwargs={"fallback": "MIXED"},
    )
    result = panel.ask("item-3", "u")
    assert result.consensus == "MIXED"
    assert result.disagreement is True


def test_panel_weighted(make_mock_client):
    reviewers = [
        _make_reviewer_with_verdict("low", "KEEP", 0.3, make_mock_client),
        _make_reviewer_with_verdict("high", "REJECT", 0.95, make_mock_client),
    ]
    panel = JudgePanel(reviewers=reviewers, strategy="weighted")
    result = panel.ask("item-w", "u")
    # weighted by confidence: REJECT (0.95) > KEEP (0.3)
    assert result.consensus == "REJECT"


def test_panel_handles_errored_reviewer(make_mock_client):
    def _bad_responder(_k: dict[str, Any]) -> str:
        raise RuntimeError("simulated 500")

    bad_reviewer = Reviewer(reviewer_id="bad", model="m", client=make_mock_client(_bad_responder))
    good = _make_reviewer_with_verdict("g1", "KEEP", 0.9, make_mock_client)
    good2 = _make_reviewer_with_verdict("g2", "KEEP", 0.8, make_mock_client)
    panel = JudgePanel(reviewers=[bad_reviewer, good, good2], strategy="majority")
    result = panel.ask("item-e", "u")
    # the bad reviewer doesn't tank consensus
    assert result.consensus == "KEEP"
    assert any(v.error is not None for v in result.verdicts)
    assert any(v.verdict == "ERROR" for v in result.verdicts)


def test_panel_aggregate_verdicts_external_drive(make_mock_client):
    """When callers drive Reviewer.ask externally (e.g. async), they can still
    use Panel.aggregate_verdicts to apply the consensus strategy."""
    from cross_judge.schema import Verdict

    panel = JudgePanel(reviewers=[], strategy="majority")
    verdicts = [
        Verdict(reviewer_id="x", verdict="A", confidence=0.9),
        Verdict(reviewer_id="y", verdict="A", confidence=0.7),
        Verdict(reviewer_id="z", verdict="B", confidence=0.5),
    ]
    result = panel.aggregate_verdicts("item", verdicts)
    assert result.consensus == "A"
    assert result.disagreement is True


def test_panel_custom_strategy_callable(make_mock_client):
    """Caller passes a strategy callable directly."""

    def always_unclear(verdicts):
        return "UNCLEAR", True

    reviewers = [_make_reviewer_with_verdict("a", "KEEP", 0.9, make_mock_client)]
    panel = JudgePanel(reviewers=reviewers, strategy=always_unclear)
    result = panel.ask("i", "u")
    assert result.consensus == "UNCLEAR"
    assert result.strategy == "always_unclear"
