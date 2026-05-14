"""W11-A coverage for web/backend/services/auth.py + rate_limit.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.auth import (  # noqa: E402
    _DEFAULT_LIMITS,
    _extract_token,
    _parse_token_env,
    get_rate_limit_tier,
    tier_limit,
    verify_api_token,
)


class _FakeRequest:
    def __init__(self, headers=None, cookies=None, client_host=None):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client = (
            type("C", (), {"host": client_host})() if client_host else None
        )


# --- _parse_token_env ---


def test_parse_token_env_empty(monkeypatch):
    monkeypatch.delenv("STRUCTURAL_API_TOKENS", raising=False)
    assert _parse_token_env() == {}


def test_parse_token_env_whitespace(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "   ")
    assert _parse_token_env() == {}


def test_parse_token_env_single_paid_token(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:tok_abc")
    assert _parse_token_env() == {"tok_abc": "paid"}


def test_parse_token_env_legacy_bare_token_treated_as_free(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "tok_old")
    assert _parse_token_env() == {"tok_old": "free"}


def test_parse_token_env_unknown_tier_falls_back_to_free(monkeypatch, caplog):
    """Line 70-71: unknown tier → warning + treat as free."""
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "premium:tok_x")
    out = _parse_token_env()
    assert out == {"tok_x": "free"}


def test_parse_token_env_empty_token_skipped(monkeypatch):
    """Line 76: empty token after ':' is skipped."""
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:")
    assert _parse_token_env() == {}


def test_parse_token_env_empty_chunk_skipped(monkeypatch):
    """Line 64: empty chunk skipped (double commas)."""
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:tok_a,,free:tok_b")
    out = _parse_token_env()
    assert "tok_a" in out
    assert "tok_b" in out


def test_parse_token_env_tier_promotion_keeps_higher(monkeypatch):
    """Same token in free + paid → keep paid (higher tier)."""
    monkeypatch.setenv(
        "STRUCTURAL_API_TOKENS", "free:reused,paid:reused"
    )
    assert _parse_token_env() == {"reused": "paid"}


def test_parse_token_env_tier_promotion_does_not_demote(monkeypatch):
    """Paid first, free second → paid wins."""
    monkeypatch.setenv(
        "STRUCTURAL_API_TOKENS", "paid:reused,free:reused"
    )
    assert _parse_token_env() == {"reused": "paid"}


def test_parse_token_env_multiple_tokens(monkeypatch):
    monkeypatch.setenv(
        "STRUCTURAL_API_TOKENS", "paid:p1,paid:p2,free:f1"
    )
    out = _parse_token_env()
    assert out["p1"] == "paid"
    assert out["p2"] == "paid"
    assert out["f1"] == "free"


# --- _extract_token ---


def test_extract_token_bearer_header():
    req = _FakeRequest(headers={"Authorization": "Bearer tok_xyz"})
    assert _extract_token(req) == "tok_xyz"


def test_extract_token_lowercase_authorization():
    req = _FakeRequest(headers={"authorization": "Bearer tok_xyz"})
    assert _extract_token(req) == "tok_xyz"


def test_extract_token_bearer_empty():
    """Bearer with empty token → None (header is present but token empty)."""
    req = _FakeRequest(headers={"Authorization": "Bearer "})
    # Bearer prefix with empty content; falls through to cookie (also none)
    assert _extract_token(req) is None


def test_extract_token_non_bearer():
    req = _FakeRequest(headers={"Authorization": "Basic xyz"})
    assert _extract_token(req) is None


def test_extract_token_cookie_fallback():
    req = _FakeRequest(cookies={"structural_api_token": "tok_from_cookie"})
    assert _extract_token(req) == "tok_from_cookie"


def test_extract_token_cookie_whitespace_stripped():
    req = _FakeRequest(cookies={"structural_api_token": "  tok_x  "})
    assert _extract_token(req) == "tok_x"


def test_extract_token_none_when_absent():
    req = _FakeRequest()
    assert _extract_token(req) is None


# --- verify_api_token ---


def test_verify_api_token_anonymous_when_no_token(monkeypatch):
    monkeypatch.delenv("STRUCTURAL_API_TOKENS", raising=False)
    req = _FakeRequest()
    assert verify_api_token(req) == "anonymous"


def test_verify_api_token_valid_paid(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:tok_p")
    req = _FakeRequest(headers={"Authorization": "Bearer tok_p"})
    assert verify_api_token(req) == "paid"


def test_verify_api_token_valid_free(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "free:tok_f")
    req = _FakeRequest(headers={"Authorization": "Bearer tok_f"})
    assert verify_api_token(req) == "free"


def test_verify_api_token_invalid_returns_none(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:real_tok")
    req = _FakeRequest(headers={"Authorization": "Bearer fake_tok"})
    assert verify_api_token(req) is None


# --- get_rate_limit_tier ---


def test_get_rate_limit_tier_paid():
    assert get_rate_limit_tier("paid") == "60/minute"


def test_get_rate_limit_tier_free():
    assert get_rate_limit_tier("free") == "10/minute"


def test_get_rate_limit_tier_anonymous():
    assert get_rate_limit_tier("anonymous") == "5/minute"


def test_get_rate_limit_tier_unknown_falls_back_to_strictest():
    assert get_rate_limit_tier("enterprise") == "5/minute"  # anonymous bucket


def test_get_rate_limit_tier_case_insensitive():
    assert get_rate_limit_tier("PAID") == "60/minute"


def test_get_rate_limit_tier_non_string_falls_back():
    assert get_rate_limit_tier(None) == "5/minute"  # type: ignore[arg-type]
    assert get_rate_limit_tier(42) == "5/minute"  # type: ignore[arg-type]


# --- tier_limit ---


def test_tier_limit_anonymous_format(monkeypatch):
    monkeypatch.delenv("STRUCTURAL_API_TOKENS", raising=False)
    req = _FakeRequest(client_host="1.2.3.4")
    out = tier_limit(req)
    assert out == "anonymous:1.2.3.4"


def test_tier_limit_paid_format(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:tok_p")
    req = _FakeRequest(
        headers={"Authorization": "Bearer tok_p"}, client_host="5.6.7.8"
    )
    assert tier_limit(req) == "paid:5.6.7.8"


def test_tier_limit_invalid_token_falls_back_to_anonymous(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:real_tok")
    req = _FakeRequest(
        headers={"Authorization": "Bearer fake_tok"}, client_host="9.9.9.9"
    )
    assert tier_limit(req) == "anonymous:9.9.9.9"


def test_tier_limit_no_client_uses_unknown_ip(monkeypatch):
    monkeypatch.delenv("STRUCTURAL_API_TOKENS", raising=False)
    req = _FakeRequest()  # no client
    assert tier_limit(req) == "anonymous:unknown"


# --- rate_limit module ---


def test_rate_limit_limit_returns_callable():
    """limit() returns a decorator-callable."""
    from services.rate_limit import limit

    decorator = limit("5/minute")
    assert callable(decorator)


def test_rate_limit_tier_limit_decorator_works():
    from services.rate_limit import tier_limit_decorator

    decorator = tier_limit_decorator()

    @decorator
    async def my_endpoint(request):
        return "ok"

    assert callable(my_endpoint)


def test_rate_limit_tier_limit_decorator_custom_anon():
    from services.rate_limit import tier_limit_decorator

    decorator = tier_limit_decorator(default_anon="3/minute")
    assert callable(decorator)
