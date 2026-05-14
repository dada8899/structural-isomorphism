"""W11-A: prompts.py + reviewer.py coverage gaps."""
from __future__ import annotations

import pytest

from cross_judge.prompts import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TEMPLATE,
    render_user_prompt,
)
from cross_judge.reviewer import Reviewer, _extract_json
from cross_judge.schema import Verdict as ReviewerVerdict


# --- prompts.py ---


def test_default_system_prompt_nonempty():
    assert isinstance(DEFAULT_SYSTEM_PROMPT, str)
    assert len(DEFAULT_SYSTEM_PROMPT) > 0
    assert "JSON" in DEFAULT_SYSTEM_PROMPT


def test_default_user_prompt_template_has_placeholders():
    assert "{item}" in DEFAULT_USER_PROMPT_TEMPLATE
    assert "{labels}" in DEFAULT_USER_PROMPT_TEMPLATE


def test_render_user_prompt_basic():
    out = render_user_prompt("event 1", labels=["KEEP", "REJECT"])
    assert "event 1" in out
    assert "KEEP" in out
    assert "REJECT" in out
    assert " | " in out


def test_render_user_prompt_single_label():
    out = render_user_prompt("x", labels=["CONFIRMED"])
    assert "CONFIRMED" in out


def test_render_user_prompt_many_labels():
    out = render_user_prompt("x", labels=["A", "B", "C", "D"])
    assert "A | B | C | D" in out


# --- reviewer._extract_json ---


def test_reviewer_extract_json_valid():
    out = _extract_json('{"verdict": "KEEP"}')
    assert out == {"verdict": "KEEP"}


def test_reviewer_extract_json_with_fence():
    out = _extract_json('```json\n{"v": 1}\n```')
    assert out == {"v": 1}


def test_reviewer_extract_json_invalid():
    assert _extract_json("not json") is None


def test_reviewer_extract_json_empty():
    assert _extract_json("") is None


def test_reviewer_extract_json_trailing_comma():
    out = _extract_json('{"v": 1,\n}')
    assert out == {"v": 1}


# --- Reviewer empty/error paths ---


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    def __init__(self, resp=None, raises=None):
        self.chat = self
        self.completions = self
        self._resp = resp
        self._raises = raises

    def create(self, **kw):
        if self._raises:
            raise self._raises
        return self._resp


def test_reviewer_ask_empty_content_returns_error():
    r = Reviewer(reviewer_id="x", model="m", client=_FakeClient(_FakeResp("")))
    v = r.ask("hello")
    assert v.verdict == "ERROR"
    assert v.error == "empty_response"


def test_reviewer_ask_exception_returns_error():
    r = Reviewer(
        reviewer_id="x", model="m",
        client=_FakeClient(raises=RuntimeError("api down")),
    )
    v = r.ask("hello")
    assert v.verdict == "ERROR"
    assert "RuntimeError" in v.error


def test_reviewer_ask_parse_fail():
    r = Reviewer(
        reviewer_id="x", model="m",
        client=_FakeClient(_FakeResp("totally garbage no json")),
    )
    v = r.ask("hello")
    assert v.verdict == "PARSE_FAIL"


def test_reviewer_ask_success():
    r = Reviewer(
        reviewer_id="x", model="m",
        client=_FakeClient(_FakeResp(
            '{"verdict": "KEEP", "confidence": 0.85, "rationale": "fine"}'
        )),
    )
    v = r.ask("hello")
    assert v.verdict == "KEEP"
    assert v.confidence == 0.85


def test_reviewer_ask_non_numeric_confidence_falls_back():
    r = Reviewer(
        reviewer_id="x", model="m",
        client=_FakeClient(_FakeResp(
            '{"verdict": "KEEP", "confidence": "high"}'
        )),
    )
    v = r.ask("hi")
    assert v.confidence == 0.0


def test_reviewer_ask_confidence_clamped():
    r = Reviewer(
        reviewer_id="x", model="m",
        client=_FakeClient(_FakeResp(
            '{"verdict": "KEEP", "confidence": 5.0}'
        )),
    )
    v = r.ask("hi")
    assert v.confidence == 1.0


def test_reviewer_get_client_default_creates(monkeypatch):
    """Default client created via make_client when none injected."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    r = Reviewer(reviewer_id="x", model="m")
    try:
        c = r._get_client()
    except ImportError:
        pytest.skip("openai package not installed")
    assert c is not None
    # Second call returns same instance
    assert r._get_client() is c
