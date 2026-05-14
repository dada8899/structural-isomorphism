"""Mocked smoke tests for the 5 built-in providers.

We mock `requests.post` so no real network or API keys are required. Each
test verifies the provider:

  - sends the right body shape (model, messages, max_tokens)
  - extracts text from the vendor's response envelope
  - reports cost based on usage tokens

This is what would otherwise require a live API key — by mocking at the
`requests` boundary we exercise the full adapter without spending money.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from guarded_llm import get_provider, LLMCallError


def _make_response(status: int, json_body: dict | None, text_body: str = "") -> MagicMock:
    mock = MagicMock()
    mock.status_code = status
    mock.text = text_body or (str(json_body) if json_body else "")
    if json_body is not None:
        mock.json = MagicMock(return_value=json_body)
    else:
        mock.json = MagicMock(side_effect=ValueError("no json"))
    return mock


# ---------- Anthropic --------------------------------------------------------


def test_anthropic_happy_path():
    body = {
        "content": [{"type": "text", "text": '{"verdict": "KEEP"}'}],
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    with patch("requests.post", return_value=_make_response(200, body)) as mock_post:
        p = get_provider("anthropic")
        out = p.call(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4.5",
            max_tokens=100,
            api_key="test-key",
        )
        assert out["text"] == '{"verdict": "KEEP"}'
        # 100 in @ $3/M + 50 out @ $15/M = 0.0003 + 0.00075 = 0.00105
        assert out["cost_usd"] == pytest.approx(0.00105)
        # Verify request body
        call_body = mock_post.call_args.kwargs["json"]
        assert call_body["model"] == "claude-sonnet-4.5"
        assert call_body["max_tokens"] == 100


def test_anthropic_system_extracted_from_messages():
    body = {
        "content": [{"type": "text", "text": "{}"}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    with patch("requests.post", return_value=_make_response(200, body)) as mock_post:
        p = get_provider("anthropic")
        p.call(
            messages=[
                {"role": "system", "content": "be terse"},
                {"role": "user", "content": "hi"},
            ],
            model="claude-sonnet-4.5",
            max_tokens=10,
            api_key="test-key",
        )
        call_body = mock_post.call_args.kwargs["json"]
        assert call_body["system"] == "be terse"
        # system message should NOT appear in messages array
        assert all(m["role"] != "system" for m in call_body["messages"])


def test_anthropic_missing_api_key_raises():
    p = get_provider("anthropic")
    p.api_key = ""
    with pytest.raises(LLMCallError, match="API key not set"):
        p.call(messages=[], model="x", max_tokens=10)


def test_anthropic_http_error_raises():
    with patch("requests.post", return_value=_make_response(500, None, "server boom")):
        p = get_provider("anthropic")
        with pytest.raises(LLMCallError, match="500"):
            p.call(
                messages=[{"role": "user", "content": "hi"}],
                model="claude-sonnet-4.5",
                max_tokens=10,
                api_key="test-key",
            )


# ---------- DeepSeek ---------------------------------------------------------


def test_deepseek_happy_path():
    body = {
        "choices": [{"message": {"content": '{"ok": true}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    with patch("requests.post", return_value=_make_response(200, body)) as mock_post:
        p = get_provider("deepseek")
        out = p.call(
            messages=[{"role": "user", "content": "hi"}],
            model="deepseek-v4-flash",
            max_tokens=100,
            api_key="test-key",
        )
        assert out["text"] == '{"ok": true}'
        # 100 @ $0.07/M + 50 @ $0.27/M = 7e-6 + 1.35e-5
        assert out["cost_usd"] == pytest.approx(7e-6 + 1.35e-5, rel=1e-3)
        # JSON mode should be requested when schema is set
        call_body = mock_post.call_args.kwargs["json"]
        assert call_body["model"] == "deepseek-v4-flash"


def test_deepseek_response_format_set_when_schema_passed():
    body = {
        "choices": [{"message": {"content": "{}"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    with patch("requests.post", return_value=_make_response(200, body)) as mock_post:
        p = get_provider("deepseek")
        p.call(
            messages=[{"role": "user", "content": "hi"}],
            model="deepseek-v4-flash",
            max_tokens=10,
            schema={"type": "object"},
            api_key="test-key",
        )
        call_body = mock_post.call_args.kwargs["json"]
        assert call_body.get("response_format") == {"type": "json_object"}


# ---------- Kimi -------------------------------------------------------------


def test_kimi_happy_path():
    body = {
        "choices": [{"message": {"content": '{"x": 1}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    with patch("requests.post", return_value=_make_response(200, body)) as mock_post:
        p = get_provider("kimi")
        out = p.call(
            messages=[{"role": "user", "content": "hi"}],
            model="kimi-k2.5",
            max_tokens=100,
            api_key="test-key",
        )
        assert out["text"] == '{"x": 1}'
        assert out["cost_usd"] > 0
        call_body = mock_post.call_args.kwargs["json"]
        assert "moonshot.cn" in mock_post.call_args.args[0]
        assert call_body["model"] == "kimi-k2.5"


# ---------- OpenAI -----------------------------------------------------------


def test_openai_happy_path():
    body = {
        "choices": [{"message": {"content": '{"y": 2}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    with patch("requests.post", return_value=_make_response(200, body)) as mock_post:
        p = get_provider("openai")
        out = p.call(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
            max_tokens=100,
            api_key="test-key",
        )
        assert out["text"] == '{"y": 2}'
        # 100 @ $2.50/M + 50 @ $10/M = 0.00025 + 0.0005 = 0.00075
        assert out["cost_usd"] == pytest.approx(0.00075)
        call_body = mock_post.call_args.kwargs["json"]
        assert call_body["model"] == "gpt-4o"


# ---------- GLM --------------------------------------------------------------


def test_glm_happy_path():
    body = {
        "choices": [{"message": {"content": '{"z": 3}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    with patch("requests.post", return_value=_make_response(200, body)) as mock_post:
        p = get_provider("glm")
        out = p.call(
            messages=[{"role": "user", "content": "hi"}],
            model="glm-4.6",
            max_tokens=100,
            api_key="test-key",
        )
        assert out["text"] == '{"z": 3}'
        assert out["cost_usd"] > 0
        call_body = mock_post.call_args.kwargs["json"]
        assert "bigmodel.cn" in mock_post.call_args.args[0]
        assert call_body["model"] == "glm-4.6"


def test_glm_registered_in_list():
    from guarded_llm import list_providers

    assert "glm" in list_providers()


# ---------- Reproducibility / determinism -----------------------------------


def test_state_machine_fix_is_deterministic():
    """Same input -> same output. No hidden randomness in the fixer pipeline."""
    from guarded_llm import state_machine_fix

    raw = "{'a': 1, 'b': NaN,}"
    out1 = state_machine_fix(raw)
    out2 = state_machine_fix(raw)
    out3 = state_machine_fix(raw)
    assert out1 == out2 == out3


def test_retry_policy_jitter_deterministic_with_seeded_rng():
    """With a seeded RNG, sleep_seconds is reproducible."""
    import random

    from guarded_llm import RetryPolicy

    p = RetryPolicy(max_attempts=5, backoff_seconds=1.0, jitter=True)
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    seq1 = [p.sleep_seconds(i, rng=rng1) for i in range(1, 5)]
    seq2 = [p.sleep_seconds(i, rng=rng2) for i in range(1, 5)]
    assert seq1 == seq2
