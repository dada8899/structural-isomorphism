"""Reviewer.ask tests using a mock OpenAI-compat client."""
from __future__ import annotations

from typing import Any

from cross_judge import Reviewer
from cross_judge.reviewer import _extract_json


def test_extract_json_plain():
    assert _extract_json('{"verdict": "KEEP", "confidence": 0.9}') == {
        "verdict": "KEEP",
        "confidence": 0.9,
    }


def test_extract_json_markdown_fence():
    raw = '```json\n{"verdict": "REJECT", "confidence": 0.4}\n```'
    assert _extract_json(raw) == {"verdict": "REJECT", "confidence": 0.4}


def test_extract_json_with_leading_text():
    raw = 'Here is my verdict:\n{"verdict": "KEEP", "confidence": 0.8, "rationale": "ok"}'
    out = _extract_json(raw)
    assert out is not None
    assert out["verdict"] == "KEEP"


def test_extract_json_invalid_returns_none():
    assert _extract_json("nope no json here") is None
    assert _extract_json("") is None


def test_extract_json_trailing_comma_tolerated():
    raw = '{"verdict": "KEEP",\n"confidence": 0.5,\n}'
    out = _extract_json(raw)
    assert out is not None
    assert out["verdict"] == "KEEP"


def test_reviewer_ask_happy_path(static_json_client):
    r = Reviewer(
        reviewer_id="mock-1",
        model="mock-model",
        client=static_json_client(verdict="KEEP", confidence=0.85, rationale="solid"),
    )
    v = r.ask("Judge this item.")
    assert v.reviewer_id == "mock-1"
    assert v.verdict == "KEEP"
    assert v.confidence == 0.85
    assert v.rationale == "solid"
    assert v.error is None
    assert v.raw_response is not None


def test_reviewer_ask_uppercases_verdict(make_mock_client):
    import json as _json

    def _responder(_k: dict[str, Any]) -> str:
        return _json.dumps({"verdict": "keep", "confidence": 0.7, "rationale": "x"})

    r = Reviewer(reviewer_id="m", model="m", client=make_mock_client(_responder))
    v = r.ask("u")
    assert v.verdict == "KEEP"


def test_reviewer_ask_parse_fail(make_mock_client):
    def _responder(_k: dict[str, Any]) -> str:
        return "not json at all"

    r = Reviewer(reviewer_id="m", model="m", client=make_mock_client(_responder))
    v = r.ask("u")
    assert v.verdict == "PARSE_FAIL"
    assert v.error == "parse_fail"
    assert v.confidence == 0.0


def test_reviewer_ask_empty_response(make_mock_client):
    def _responder(_k: dict[str, Any]) -> str:
        return ""

    r = Reviewer(reviewer_id="m", model="m", client=make_mock_client(_responder))
    v = r.ask("u")
    assert v.verdict == "ERROR"
    assert v.error == "empty_response"


def test_reviewer_ask_network_error(make_mock_client):
    def _responder(_k: dict[str, Any]) -> str:
        raise RuntimeError("simulated 502")

    r = Reviewer(reviewer_id="m", model="m", client=make_mock_client(_responder))
    v = r.ask("u")
    assert v.verdict == "ERROR"
    assert v.error is not None
    assert "502" in v.error


def test_reviewer_confidence_clamped(make_mock_client):
    import json as _json

    def _responder(_k: dict[str, Any]) -> str:
        return _json.dumps({"verdict": "KEEP", "confidence": 1.5, "rationale": ""})

    r = Reviewer(reviewer_id="m", model="m", client=make_mock_client(_responder))
    v = r.ask("u")
    assert v.confidence == 1.0


def test_reviewer_passes_model_and_temperature(static_json_client):
    client = static_json_client()
    r = Reviewer(
        reviewer_id="m",
        model="deepseek-v4-pro",
        temperature=0.6,
        max_tokens=512,
        client=client,
    )
    r.ask("u")
    call = client.calls[0]
    assert call["model"] == "deepseek-v4-pro"
    assert call["temperature"] == 0.6
    assert call["max_tokens"] == 512
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1]["role"] == "user"
    assert call["messages"][1]["content"] == "u"
