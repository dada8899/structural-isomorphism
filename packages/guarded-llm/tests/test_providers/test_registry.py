"""Tests for the provider registry interface."""

from __future__ import annotations

import pytest

from guarded_llm import (
    BaseProvider,
    get_provider,
    list_providers,
    register_provider,
)


def test_builtin_providers_registered():
    names = list_providers()
    assert "deepseek" in names
    assert "anthropic" in names
    assert "openai" in names
    assert "kimi" in names


def test_get_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("nonexistent-vendor")


def test_get_provider_returns_baseprovider_subclass():
    p = get_provider("deepseek")
    assert isinstance(p, BaseProvider)


def test_register_custom_provider():
    class MyProv(BaseProvider):
        name = "myprov"

        def call(self, messages, model, max_tokens, schema=None, **kwargs):
            return {"text": '{"hello": "world"}', "cost_usd": 0.0001}

    register_provider("myprov", MyProv)
    assert "myprov" in list_providers()
    p = get_provider("myprov")
    out = p.call(messages=[], model="m", max_tokens=10)
    assert out["text"] == '{"hello": "world"}'


def test_register_provider_rejects_non_subclass():
    class NotAProvider:
        pass

    with pytest.raises(TypeError):
        register_provider("bad", NotAProvider)  # type: ignore[arg-type]
