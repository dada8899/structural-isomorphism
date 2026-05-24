"""W11-A coverage for cross_judge.core.

Targets:
- _extract_json: invalid candidate, fence-only, trailing-comma cleanup, single line
- Critic._resolved_base_url: missing vendor → ValueError
- Critic._resolved_api_key: env-var present, env-var missing, custom-vendor no key
- Critic._get_client: default httpx.Client lazily created (line 145)
- Critic._render_prompt: missing template key → KeyError
- Critic.judge: empty raw response → ERROR Verdict (line 212)
- Critic._parse_verdict: non-numeric confidence (line 247-248)
"""
from __future__ import annotations

import json
import os

import pytest

from cross_judge.core import Critic, _extract_json
from cross_judge.verdict import Verdict


# --- _extract_json ----------------------------------------------------------


def test_extract_json_no_braces_returns_none():
    assert _extract_json("just some text") is None


def test_extract_json_empty_string():
    assert _extract_json("") is None


def test_extract_json_strips_markdown_fence():
    raw = '```json\n{"k": "v"}\n```'
    out = _extract_json(raw)
    assert out == {"k": "v"}


def test_extract_json_strips_naked_fence():
    raw = "```\n{\"k\": \"v\"}\n```"
    assert _extract_json(raw) == {"k": "v"}


def test_extract_json_trailing_comma_cleanup():
    """Inside object trailing-comma is cleaned up on second pass."""
    raw = '{"kind": "KEEP", "confidence": 0.9,\n}'
    out = _extract_json(raw)
    assert out is not None
    assert out["kind"] == "KEEP"


def test_extract_json_trailing_comma_in_array():
    raw = '{"x": [1, 2, 3,\n]}'
    out = _extract_json(raw)
    assert out is not None
    assert out["x"] == [1, 2, 3]


def test_extract_json_completely_unrecoverable():
    raw = "{this is not json at all !!}"
    assert _extract_json(raw) is None


def test_extract_json_brace_order_invalid():
    """} before { → returns None."""
    raw = "} text {"
    assert _extract_json(raw) is None


# --- Critic._resolved_base_url ----------------------------------------------


def test_critic_base_url_explicit_wins():
    c = Critic(name="x", model="m", base_url="https://custom.example/v1")
    assert c._resolved_base_url() == "https://custom.example/v1"


def test_critic_base_url_unknown_vendor_raises():
    c = Critic(name="x", model="m", vendor="acme-fake")
    with pytest.raises(ValueError) as exc:
        c._resolved_base_url()
    assert "Unknown vendor" in str(exc.value)


# --- Critic._resolved_api_key -----------------------------------------------


def test_critic_api_key_explicit_wins(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    c = Critic(name="x", model="m", api_key="sk-explicit")
    assert c._resolved_api_key() == "sk-explicit"


def test_critic_api_key_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-here")
    c = Critic(name="x", model="m")
    assert c._resolved_api_key() == "sk-env-here"


def test_critic_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    c = Critic(name="x", model="m")
    with pytest.raises(RuntimeError) as exc:
        c._resolved_api_key()
    assert "Missing API key" in str(exc.value)


def test_critic_api_key_custom_vendor_no_key_raises(monkeypatch):
    c = Critic(name="x", model="m", vendor="acme-fake")
    with pytest.raises(RuntimeError) as exc:
        c._resolved_api_key()
    assert "Missing api_key" in str(exc.value)


# --- Critic._get_client default --------------------------------------------


def test_critic_get_client_default_creates_httpx():
    """Line 145: first call to _get_client creates httpx.Client."""
    c = Critic(name="x", model="m")
    assert c.http_client is None
    client = c._get_client()
    assert client is not None
    # Second call returns same instance
    assert c._get_client() is client


# --- Critic._render_prompt -------------------------------------------------


def test_critic_render_prompt_missing_key_raises():
    c = Critic(
        name="x",
        model="m",
        prompt_template="Need {missing_var}: {query}",
    )
    with pytest.raises(KeyError) as exc:
        c._render_prompt("hi", context={})
    assert "missing required key" in str(exc.value)


def test_critic_render_prompt_basic():
    c = Critic(
        name="x", model="m", prompt_template="Q: {query}"
    )
    out = c._render_prompt("hello", context={})
    assert out == "Q: hello"


def test_critic_render_prompt_with_context():
    c = Critic(
        name="x",
        model="m",
        prompt_template="{query} domain={domain}",
    )
    out = c._render_prompt("Q", context={"domain": "earthquakes"})
    assert "domain=earthquakes" in out


# --- Critic.judge — empty response path ------------------------------------


class _FakeResp:
    def __init__(self, body, status=200):
        self._body = body
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def post(self, *a, **kw):
        return self._resp


def test_critic_judge_empty_content_returns_error_verdict(monkeypatch):
    """Empty `content` in LLM response → ERROR Verdict (line 212)."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    fake = _FakeResp(
        body={"choices": [{"message": {"content": ""}}]},
    )
    c = Critic(name="x", model="m", http_client=_FakeClient(fake))
    v = c.judge("hello")
    assert v.kind == "ERROR"
    assert v.error == "empty_response"


def test_critic_judge_whitespace_only_content_returns_error(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    fake = _FakeResp(body={"choices": [{"message": {"content": "   \n  "}}]})
    c = Critic(name="x", model="m", http_client=_FakeClient(fake))
    v = c.judge("hello")
    assert v.kind == "ERROR"


def test_critic_judge_http_error_caught(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    fake = _FakeResp(body={}, status=500)
    c = Critic(name="x", model="m", http_client=_FakeClient(fake))
    v = c.judge("hi")
    assert v.kind == "ERROR"
    assert v.error and "http" in v.error.lower() or "RuntimeError" in v.error


def test_critic_judge_parse_failure(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    fake = _FakeResp(
        body={"choices": [{"message": {"content": "not json garbage"}}]},
    )
    c = Critic(name="x", model="m", http_client=_FakeClient(fake))
    v = c.judge("hi")
    assert v.kind == "PARSE_FAIL"
    assert v.error == "parse_fail"


def test_critic_judge_success(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    fake = _FakeResp(body={"choices": [{"message": {"content": '{"kind": "KEEP", "confidence": 0.8, "reasoning": "looks right"}'}}]})
    c = Critic(name="x", model="m", http_client=_FakeClient(fake))
    v = c.judge("hi")
    assert v.kind == "KEEP"
    assert v.confidence == 0.8


# --- _parse_verdict edge cases ---------------------------------------------


def test_parse_verdict_non_numeric_confidence_falls_back_to_zero():
    """Line 247-248: non-numeric confidence raises TypeError/ValueError → 0.0."""
    c = Critic(name="x", model="m")
    v = c._parse_verdict('{"kind": "KEEP", "confidence": "high"}', elapsed=0.1)
    assert v.kind == "KEEP"
    assert v.confidence == 0.0  # could not parse "high" → 0.0


def test_parse_verdict_none_confidence_falls_back_to_zero():
    c = Critic(name="x", model="m")
    v = c._parse_verdict('{"kind": "KEEP", "confidence": null}', elapsed=0.1)
    assert v.confidence == 0.0


def test_parse_verdict_clamps_confidence_to_one():
    c = Critic(name="x", model="m")
    v = c._parse_verdict('{"kind": "KEEP", "confidence": 5.0}', elapsed=0.1)
    assert v.confidence == 1.0


def test_parse_verdict_clamps_confidence_to_zero():
    c = Critic(name="x", model="m")
    v = c._parse_verdict('{"kind": "KEEP", "confidence": -2.0}', elapsed=0.1)
    assert v.confidence == 0.0


def test_parse_verdict_supports_legacy_verdict_field():
    """Legacy schema uses `verdict`/`rationale` instead of `kind`/`reasoning`."""
    c = Critic(name="x", model="m")
    v = c._parse_verdict(
        '{"verdict": "REJECT", "confidence": 0.6, "rationale": "old style"}',
        elapsed=0.05,
    )
    assert v.kind == "REJECT"
    assert v.reasoning == "old style"


def test_parse_verdict_uppercases_kind():
    c = Critic(name="x", model="m")
    v = c._parse_verdict('{"kind": "keep"}', elapsed=0.05)
    assert v.kind == "KEEP"


def test_parse_verdict_default_kind_unclear():
    c = Critic(name="x", model="m")
    v = c._parse_verdict('{"confidence": 0.5}', elapsed=0.05)
    assert v.kind == "UNCLEAR"
