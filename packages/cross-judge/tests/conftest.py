"""Shared pytest fixtures: a mock OpenAI-compatible client.

The fixture is decoupled from the real `openai` package — we just need
something whose `.chat.completions.create(...)` returns an object with
`.choices[0].message.content`. This keeps tests offline + deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest


@dataclass
class _Msg:
    content: str


@dataclass
class _Choice:
    message: _Msg


@dataclass
class _Resp:
    choices: list[_Choice]


class _MockCompletions:
    def __init__(self, responder: Callable[[dict[str, Any]], str]):
        self._responder = responder
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Resp:
        self.calls.append(kwargs)
        content = self._responder(kwargs)
        return _Resp(choices=[_Choice(message=_Msg(content=content))])


class _MockChat:
    def __init__(self, responder: Callable[[dict[str, Any]], str]):
        self.completions = _MockCompletions(responder)


class MockClient:
    """Stand-in for openai.OpenAI client. Carries a `chat.completions.create`
    method that returns whatever the supplied responder produces."""

    def __init__(self, responder: Callable[[dict[str, Any]], str]):
        self.chat = _MockChat(responder)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.chat.completions.calls


@pytest.fixture
def make_mock_client() -> Callable[..., MockClient]:
    """Factory: pass a responder fn (kwargs -> content_str), get a MockClient."""

    def _factory(responder: Callable[[dict[str, Any]], str]) -> MockClient:
        return MockClient(responder)

    return _factory


@pytest.fixture
def static_json_client(make_mock_client: Callable[..., MockClient]) -> Callable[..., MockClient]:
    """Factory: returns a client that always responds with the same JSON content."""

    def _factory(verdict: str = "KEEP", confidence: float = 0.9, rationale: str = "looks good") -> MockClient:
        import json as _json

        body = _json.dumps({"verdict": verdict, "confidence": confidence, "rationale": rationale})

        def _responder(_kwargs: dict[str, Any]) -> str:
            return body

        return make_mock_client(_responder)

    return _factory
