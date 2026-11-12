"""Tests for Critic (single-vendor single-decoding LLM judge).

All tests use the 'mock' vendor — no real network. We register custom
mock responders to exercise different code paths (success / parse_fail /
error / cost overage).
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from reject_aware_critic import (
    CandidateClass,
    CostBudgetError,
    Critic,
    register_mock_responder,
)


@pytest.fixture
def candidate():
    return CandidateClass(
        class_id="delay_differential_debt",
        name="Delay Differential Debt",
        hub="Hopf bifurcation in delayed feedback",
        shared_equations=["dx/dt = f(x(t-tau))"],
        members=["sovereign debt cycle", "neural oscillation", "predator-prey"],
        domains=["macro", "neuro", "ecology"],
    )


def _register_keep_responder(name: str = "keep") -> None:
    def _r(model, messages, temperature, max_tokens):
        return (
            json.dumps(
                {
                    "decision": "KEEP",
                    "confidence": 0.85,
                    "rationale": "Shared dynamics and exponents across 3 domains.",
                    "trap_flags": [],
                }
            ),
            {"prompt_tokens": 500, "completion_tokens": 100},
        )
    register_mock_responder(name, _r)


def _register_reject_with_trap_responder(name: str = "reject_trap") -> None:
    def _r(model, messages, temperature, max_tokens):
        return (
            json.dumps(
                {
                    "decision": "REJECT",
                    "confidence": 0.9,
                    "rationale": "This is a central limit theorem confusion; "
                                 "Hopf normal form is not a universality class.",
                    "trap_flags": ["mechanism_vs_limit_theorem"],
                }
            ),
            {"prompt_tokens": 500, "completion_tokens": 100},
        )
    register_mock_responder(name, _r)


def _register_parse_fail_responder(name: str = "parse_fail") -> None:
    def _r(model, messages, temperature, max_tokens):
        return ("not valid json at all", {"prompt_tokens": 10, "completion_tokens": 10})
    register_mock_responder(name, _r)


def _register_empty_responder(name: str = "empty") -> None:
    def _r(model, messages, temperature, max_tokens):
        return ("", {"prompt_tokens": 10, "completion_tokens": 0})
    register_mock_responder(name, _r)


def _register_huge_responder(name: str = "huge") -> None:
    def _r(model, messages, temperature, max_tokens):
        return (
            json.dumps({"decision": "KEEP", "confidence": 0.5, "rationale": "ok"}),
            {"prompt_tokens": 10_000_000, "completion_tokens": 10_000_000},
        )
    register_mock_responder(name, _r)


class TestCriticBasic:
    def test_construction_defaults(self, candidate):
        _register_keep_responder()
        c = Critic(vendor="mock", model="mock-model", mock_responder="keep")
        assert c.critic_id == "mock:mock-model:rigorous"

    def test_unknown_persona_raises(self):
        with pytest.raises(ValueError):
            Critic(vendor="mock", model="m", persona="not-a-persona")

    def test_unknown_vendor_raises(self):
        with pytest.raises(KeyError):
            Critic(vendor="nope-vendor", model="m")

    def test_judge_keep(self, candidate):
        _register_keep_responder()
        c = Critic(vendor="mock", model="mock-model", mock_responder="keep")
        v = c.judge(candidate)
        assert v.decision == "KEEP"
        assert v.confidence == 0.85
        assert v.class_id == candidate.class_id
        assert v.critic_id == c.critic_id
        assert v.error is None
        assert v.elapsed_s >= 0.0

    def test_judge_reject_with_trap(self, candidate):
        _register_reject_with_trap_responder()
        c = Critic(vendor="mock", model="m", mock_responder="reject_trap")
        v = c.judge(candidate)
        assert v.decision == "REJECT"
        assert "mechanism_vs_limit_theorem" in v.trap_flags

    def test_judge_trap_auto_detected_from_rationale(self, candidate):
        # Responder declares no trap_flags but rationale contains the pattern;
        # filter should auto-augment.
        def _r(model, messages, temperature, max_tokens):
            return (
                json.dumps(
                    {
                        "decision": "REJECT",
                        "confidence": 0.7,
                        "rationale": "Pure surface similarity from heavy-tail. "
                                     "Not a real shared mechanism.",
                        "trap_flags": [],
                    }
                ),
                {"prompt_tokens": 100, "completion_tokens": 50},
            )
        register_mock_responder("auto_detect", _r)
        c = Critic(vendor="mock", model="m", mock_responder="auto_detect")
        v = c.judge(candidate)
        assert "surface_similarity_from_heavy_tails" in v.trap_flags

    def test_judge_parse_fail(self, candidate):
        _register_parse_fail_responder()
        c = Critic(vendor="mock", model="m", mock_responder="parse_fail")
        v = c.judge(candidate)
        assert v.decision == "PARSE_FAIL"
        assert v.error == "parse_fail"

    def test_judge_empty_response(self, candidate):
        _register_empty_responder()
        c = Critic(vendor="mock", model="m", mock_responder="empty")
        v = c.judge(candidate)
        assert v.decision == "ERROR"
        assert "empty" in (v.error or "").lower()

    def test_dict_candidate_accepted(self):
        _register_keep_responder()
        c = Critic(vendor="mock", model="m", mock_responder="keep")
        v = c.judge({"class_id": "x", "members": ["a"]})
        assert v.class_id == "x"


class TestCostBudget:
    def test_cost_budget_enforced(self, candidate):
        _register_huge_responder()
        c = Critic(
            vendor="mock",
            model="m",
            mock_responder="huge",
            max_cost_usd=0.05,
            # mock vendor has zero cost by default → override for the test
            cost_per_1k_in=0.001,
            cost_per_1k_out=0.001,
        )
        with pytest.raises(CostBudgetError):
            c.judge(candidate)

    def test_cost_budget_passes_when_cheap(self, candidate):
        _register_keep_responder()
        c = Critic(vendor="mock", model="m", mock_responder="keep", max_cost_usd=0.05)
        v = c.judge(candidate)
        assert v.decision == "KEEP"
        # mock vendor → cost 0
        assert v.cost_usd == 0.0


class TestLogging:
    def test_log_path_writes_jsonl(self, candidate):
        _register_keep_responder()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
            log_path = tf.name
        try:
            c = Critic(
                vendor="mock", model="m", mock_responder="keep", log_path=log_path
            )
            c.judge(candidate)
            c.judge(candidate)
            with open(log_path) as f:
                lines = [l for l in f.read().splitlines() if l.strip()]
            assert len(lines) == 2
            record = json.loads(lines[0])
            assert record["class_id"] == candidate.class_id
            assert record["decision"] == "KEEP"
            assert record["critic_id"] == c.critic_id
        finally:
            os.unlink(log_path)


class TestApiKeyResolution:
    def test_missing_api_key_returns_error_verdict(self, candidate, monkeypatch):
        # use a real vendor without setting its env var → error verdict, not raise
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        c = Critic(vendor="deepseek", model="deepseek-chat", api_key=None)
        v = c.judge(candidate)
        assert v.decision == "ERROR"
        assert "DEEPSEEK_API_KEY" in (v.error or "")
