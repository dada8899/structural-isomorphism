"""Critic tests with mock httpx client."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from cross_judge import Critic, Verdict
from cross_judge.core import _extract_json


@dataclass
class _MockResponse:
    """Stand-in for httpx.Response."""

    _body: dict[str, Any]
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._body


@dataclass
class _MockHTTPXClient:
    """Stand-in for httpx.Client."""

    content: str = '{"kind": "KEEP", "confidence": 0.9, "reasoning": "ok"}'
    fail: bool = False
    fail_status: int = 500
    raises: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _MockResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.raises is not None:
            raise self.raises
        body = {
            "choices": [
                {"message": {"content": self.content}}
            ]
        }
        return _MockResponse(_body=body, status_code=self.fail_status if self.fail else 200)


# --- parser tests -------------------------------------------------------------


def test_extract_json_plain():
    assert _extract_json('{"kind": "KEEP"}') == {"kind": "KEEP"}


def test_extract_json_markdown_fence():
    raw = '```json\n{"kind": "REJECT"}\n```'
    assert _extract_json(raw) == {"kind": "REJECT"}


def test_extract_json_leading_text():
    raw = 'Here is my verdict:\n{"kind": "SPLIT", "confidence": 0.7}'
    out = _extract_json(raw)
    assert out is not None
    assert out["kind"] == "SPLIT"


def test_extract_json_invalid_returns_none():
    assert _extract_json("no json here") is None
    assert _extract_json("") is None


# --- Critic.judge -------------------------------------------------------------


def test_critic_judge_happy_path():
    mock = _MockHTTPXClient(
        content=json.dumps({"kind": "KEEP", "confidence": 0.85, "reasoning": "looks good"})
    )
    c = Critic(name="mock", model="m", api_key="dummy", http_client=mock)
    v = c.judge("test query")
    assert v.kind == "KEEP"
    assert v.confidence == 0.85
    assert v.reasoning == "looks good"
    assert v.critic_id == "mock"
    assert v.error is None


def test_critic_judge_legacy_verdict_field():
    """Accept legacy {verdict, rationale} JSON in response."""
    mock = _MockHTTPXClient(
        content=json.dumps({"verdict": "REJECT", "confidence": 0.6, "rationale": "no"})
    )
    c = Critic(name="m", model="m", api_key="dummy", http_client=mock)
    v = c.judge("q")
    assert v.kind == "REJECT"
    assert v.reasoning == "no"


def test_critic_judge_uppercases_kind():
    mock = _MockHTTPXClient(
        content=json.dumps({"kind": "keep", "confidence": 0.5, "reasoning": "x"})
    )
    c = Critic(name="m", model="m", api_key="dummy", http_client=mock)
    v = c.judge("q")
    assert v.kind == "KEEP"


def test_critic_judge_clamps_confidence():
    mock = _MockHTTPXClient(
        content=json.dumps({"kind": "KEEP", "confidence": 1.5, "reasoning": ""})
    )
    c = Critic(name="m", model="m", api_key="dummy", http_client=mock)
    v = c.judge("q")
    assert v.confidence == 1.0


def test_critic_judge_parse_fail():
    mock = _MockHTTPXClient(content="this is not json at all")
    c = Critic(name="m", model="m", api_key="dummy", http_client=mock)
    v = c.judge("q")
    assert v.kind == "PARSE_FAIL"
    assert v.error == "parse_fail"


def test_critic_judge_network_error():
    mock = _MockHTTPXClient(raises=RuntimeError("simulated 502"))
    c = Critic(name="m", model="m", api_key="dummy", http_client=mock)
    v = c.judge("q")
    assert v.kind == "ERROR"
    assert v.error is not None
    assert "502" in v.error


def test_critic_judge_passes_model_and_temperature():
    mock = _MockHTTPXClient()
    c = Critic(
        name="m",
        model="deepseek-v4-pro",
        temperature=0.6,
        max_tokens=512,
        api_key="dummy",
        http_client=mock,
    )
    c.judge("q")
    call = mock.calls[0]
    assert call["json"]["model"] == "deepseek-v4-pro"
    assert call["json"]["temperature"] == 0.6
    assert call["json"]["max_tokens"] == 512
    assert call["headers"]["Authorization"] == "Bearer dummy"


def test_critic_prompt_template_renders_query():
    mock = _MockHTTPXClient()
    c = Critic(
        name="m",
        model="m",
        prompt_template="Judge: {query}",
        api_key="dummy",
        http_client=mock,
    )
    c.judge("isomorphism test")
    rendered = mock.calls[0]["json"]["messages"][-1]["content"]
    assert "isomorphism test" in rendered


def test_critic_prompt_template_uses_context():
    mock = _MockHTTPXClient()
    c = Critic(
        name="m",
        model="m",
        prompt_template="Domain: {domain}\nQ: {query}",
        api_key="dummy",
        http_client=mock,
    )
    c.judge("the query", context={"domain": "neuro"})
    rendered = mock.calls[0]["json"]["messages"][-1]["content"]
    assert "Domain: neuro" in rendered
    assert "Q: the query" in rendered


def test_critic_from_yaml_prompt(tmp_path):
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        'version: "0.1"\n'
        'system_prompt: "You are X."\n'
        'user_prompt_template: "Judge {query}"\n',
        encoding="utf-8",
    )
    c = Critic.from_yaml_prompt(
        name="from-yaml",
        model="m",
        yaml_path=str(yaml_path),
        api_key="dummy",
    )
    assert c.system_prompt == "You are X."
    assert c.prompt_template == "Judge {query}"


def test_critic_vendor_defaults_resolution():
    """Default base_url derives from vendor."""
    mock = _MockHTTPXClient()
    c = Critic(name="m", model="m", vendor="openrouter", api_key="dummy", http_client=mock)
    c.judge("q")
    assert "openrouter.ai" in mock.calls[0]["url"]


def test_critic_reproducibility_seeded_temp_zero():
    """temperature=0 + identical mock → identical Verdicts."""
    mock1 = _MockHTTPXClient(
        content=json.dumps({"kind": "KEEP", "confidence": 0.9, "reasoning": "seeded"})
    )
    mock2 = _MockHTTPXClient(
        content=json.dumps({"kind": "KEEP", "confidence": 0.9, "reasoning": "seeded"})
    )
    c1 = Critic(name="x", model="m", temperature=0.0, api_key="dummy", http_client=mock1)
    c2 = Critic(name="x", model="m", temperature=0.0, api_key="dummy", http_client=mock2)
    v1 = c1.judge("q")
    v2 = c2.judge("q")
    assert v1.kind == v2.kind
    assert v1.confidence == v2.confidence
    assert v1.reasoning == v2.reasoning
