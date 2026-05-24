"""Ensemble integration tests with mock httpx clients."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from cross_judge import Critic, Ensemble, EnsembleVerdict, Verdict


@dataclass
class _MockResponse:
    _body: dict[str, Any]

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._body


@dataclass
class _MockHTTPXClient:
    content: str
    calls: list[dict[str, Any]] = field(default_factory=list)

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _MockResponse:
        self.calls.append({"url": url, "json": json})
        return _MockResponse(
            _body={"choices": [{"message": {"content": self.content}}]}
        )


def _critic_returning(name: str, kind: str, conf: float = 0.9) -> Critic:
    body = json.dumps({"kind": kind, "confidence": conf, "reasoning": f"{name} → {kind}"})
    return Critic(
        name=name,
        model="m",
        api_key="dummy",
        http_client=_MockHTTPXClient(content=body),
    )


def test_ensemble_majority_2_keep_1_reject():
    """Spec: 3 critics (2 KEEP, 1 REJECT) → KEEP with avg_confidence X."""
    critics = [
        _critic_returning("a", "KEEP", 0.9),
        _critic_returning("b", "KEEP", 0.8),
        _critic_returning("c", "REJECT", 0.7),
    ]
    ensemble = Ensemble(critics=critics, voting="majority")
    result = ensemble.judge("query 42")
    assert isinstance(result, EnsembleVerdict)
    assert result.consensus == "KEEP"
    assert result.disagreement is True
    assert abs(result.avg_confidence - 0.8) < 1e-9
    assert abs(result.agreement_pct - 2 / 3) < 1e-9
    assert result.voting == "majority"
    assert len(result.verdicts) == 3
    # Krippendorff α: 2 KEEP + 1 REJECT → α = 0.0 (see test_voting)
    assert result.krippendorff_alpha is not None
    assert abs(result.krippendorff_alpha) < 1e-9


def test_ensemble_unanimous_all_agree():
    critics = [
        _critic_returning("a", "KEEP", 0.9),
        _critic_returning("b", "KEEP", 0.8),
        _critic_returning("c", "KEEP", 0.7),
    ]
    ensemble = Ensemble(critics=critics, voting="unanimous")
    result = ensemble.judge("q")
    assert result.consensus == "KEEP"
    assert result.disagreement is False
    assert result.agreement_pct == 1.0
    assert result.krippendorff_alpha == 1.0


def test_ensemble_unanimous_disagreement_returns_fallback():
    critics = [_critic_returning("a", "KEEP"), _critic_returning("b", "REJECT")]
    ensemble = Ensemble(
        critics=critics,
        voting="unanimous",
        voting_kwargs={"fallback": "MIXED"},
    )
    result = ensemble.judge("q")
    assert result.consensus == "MIXED"
    assert result.disagreement is True


def test_ensemble_query_id_explicit():
    critics = [_critic_returning("a", "KEEP")]
    ensemble = Ensemble(critics=critics)
    result = ensemble.judge("q", query_id="custom-id-1")
    assert result.query_id == "custom-id-1"


def test_ensemble_query_id_defaults_to_query_prefix():
    critics = [_critic_returning("a", "KEEP")]
    ensemble = Ensemble(critics=critics)
    long_q = "x" * 200
    result = ensemble.judge(long_q)
    assert len(result.query_id) <= 80


def test_ensemble_aggregate_verdicts_external():
    """Caller drives Critic.judge externally (e.g. async), aggregates afterward."""
    ensemble = Ensemble(critics=[], voting="majority")
    verdicts = [
        Verdict(critic_id="x", kind="A", confidence=0.9),
        Verdict(critic_id="y", kind="A", confidence=0.7),
        Verdict(critic_id="z", kind="B", confidence=0.5),
    ]
    result = ensemble.aggregate_verdicts(verdicts, query_id="ext-1")
    assert result.consensus == "A"
    assert result.disagreement is True


def test_ensemble_custom_voting_callable():
    """Ensemble accepts a custom strategy callable."""

    def always_split(verdicts):
        return "SPLIT", True

    critics = [_critic_returning("a", "KEEP")]
    ensemble = Ensemble(critics=critics, voting=always_split)
    result = ensemble.judge("q")
    assert result.consensus == "SPLIT"
    assert result.voting == "always_split"


def test_ensemble_meta_passthrough():
    critics = [_critic_returning("a", "KEEP")]
    ensemble = Ensemble(critics=critics)
    result = ensemble.judge("q", meta={"source": "unit-test"})
    assert result.meta == {"source": "unit-test"}


def test_ensemble_reproducibility_temp_zero():
    """Same critics + same mock + temp=0 → identical EnsembleVerdict consensus."""
    crit1 = _critic_returning("a", "KEEP", 0.9)
    crit2 = _critic_returning("a", "KEEP", 0.9)
    e1 = Ensemble(critics=[crit1])
    e2 = Ensemble(critics=[crit2])
    r1 = e1.judge("q")
    r2 = e2.judge("q")
    assert r1.consensus == r2.consensus
    assert r1.avg_confidence == r2.avg_confidence
    assert r1.krippendorff_alpha == r2.krippendorff_alpha
