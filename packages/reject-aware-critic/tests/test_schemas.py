"""Tests for Pydantic schemas (CandidateClass / Verdict / EnsembleResult)."""
from __future__ import annotations

import pytest

from reject_aware_critic import CandidateClass, EnsembleResult, Verdict


class TestCandidateClass:
    def test_minimal_construction(self):
        c = CandidateClass(class_id="abc")
        assert c.class_id == "abc"
        assert c.name == ""
        assert c.shared_equations == []
        assert c.members == []

    def test_empty_id_rejected(self):
        with pytest.raises(ValueError):
            CandidateClass(class_id="")
        with pytest.raises(ValueError):
            CandidateClass(class_id="   ")

    def test_full_construction(self):
        c = CandidateClass(
            class_id="delay_differential_debt",
            name="Delay Differential Debt Dynamics",
            hub="Hopf bifurcation in delayed feedback",
            shared_equations=["dx/dt = f(x(t-tau))"],
            key_invariants=["delay tau", "Hopf frequency"],
            domains=["macroeconomics", "neuroscience"],
            members=["sovereign debt cycle", "neural oscillation"],
            negative_examples=["instantaneous feedback systems"],
            notes="Generic DDE normal form",
            prior_verdict="KEEP",
            prior_confidence=0.7,
            prior_rationale="B1 voted KEEP",
        )
        assert c.class_id == "delay_differential_debt"
        assert c.prior_confidence == 0.7
        assert len(c.members) == 2

    def test_dict_validate(self):
        c = CandidateClass.model_validate({"class_id": "x", "members": ["a"]})
        assert c.class_id == "x"
        assert c.members == ["a"]


class TestVerdict:
    def test_minimal(self):
        v = Verdict(class_id="x", critic_id="c1")
        assert v.decision == "UNCLEAR"
        assert v.confidence == 0.0
        assert v.trap_flags == []

    def test_decision_normalization(self):
        v = Verdict(class_id="x", critic_id="c1", decision="keep")
        assert v.decision == "KEEP"
        v = Verdict(class_id="x", critic_id="c1", decision="SPLIT_INTO_TWO")
        assert v.decision == "SPLIT"
        v = Verdict(class_id="x", critic_id="c1", decision="merge with foo")
        assert v.decision == "MERGE"
        v = Verdict(class_id="x", critic_id="c1", decision="not-a-real-label")
        assert v.decision == "UNCLEAR"
        v = Verdict(class_id="x", critic_id="c1", decision=None)
        assert v.decision == "UNCLEAR"

    def test_confidence_clamp(self):
        v = Verdict(class_id="x", critic_id="c1", confidence=1.5)
        assert v.confidence == 1.0
        v = Verdict(class_id="x", critic_id="c1", confidence=-0.3)
        assert v.confidence == 0.0
        v = Verdict(class_id="x", critic_id="c1", confidence="0.42")
        assert v.confidence == 0.42
        v = Verdict(class_id="x", critic_id="c1", confidence="not-a-number")
        assert v.confidence == 0.0
        v = Verdict(class_id="x", critic_id="c1", confidence=None)
        assert v.confidence == 0.0

    def test_trap_flags(self):
        v = Verdict(
            class_id="x",
            critic_id="c1",
            trap_flags=["mechanism_vs_limit_theorem", "other"],
        )
        assert "mechanism_vs_limit_theorem" in v.trap_flags
        assert "other" in v.trap_flags


class TestEnsembleResult:
    def test_minimal(self):
        verdicts = [Verdict(class_id="x", critic_id="c1", decision="KEEP", confidence=0.8)]
        r = EnsembleResult(
            class_id="x",
            verdicts=verdicts,
            consensus="KEEP",
            consensus_confidence=0.8,
            disagreement_signal=0.0,
        )
        assert r.consensus == "KEEP"
        assert r.total_cost_usd == 0.0
        assert r.n_errors == 0
