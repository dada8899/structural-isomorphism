"""Unit tests for services.auth — API token tier classification."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Ensure web/backend is on sys.path so `services.*` resolves regardless of
# the pytest invocation directory.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from services.auth import (  # noqa: E402
    get_rate_limit_tier,
    tier_limit,
    verify_api_token,
)


def _make_request(headers: dict | None = None, cookies: dict | None = None,
                  client_host: str = "203.0.113.7"):
    """Build a minimal duck-typed Request fixture sufficient for auth.* helpers."""
    return SimpleNamespace(
        headers=headers or {},
        cookies=cookies or {},
        client=SimpleNamespace(host=client_host),
    )


# ---------------- verify_api_token ----------------


def test_no_token_returns_anonymous(monkeypatch):
    monkeypatch.delenv("STRUCTURAL_API_TOKENS", raising=False)
    req = _make_request()
    assert verify_api_token(req) == "anonymous"


def test_bearer_valid_paid(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:tok_paid_abc,free:tok_free_xyz")
    req = _make_request(headers={"Authorization": "Bearer tok_paid_abc"})
    assert verify_api_token(req) == "paid"


def test_bearer_valid_free(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:tok_paid_abc,free:tok_free_xyz")
    req = _make_request(headers={"Authorization": "Bearer tok_free_xyz"})
    assert verify_api_token(req) == "free"


def test_bearer_invalid_returns_none(monkeypatch):
    """Provided-but-wrong token → None so endpoints can raise 401."""
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:tok_paid_abc")
    req = _make_request(headers={"Authorization": "Bearer wrong_token"})
    assert verify_api_token(req) is None


def test_cookie_fallback(monkeypatch):
    """When no Authorization header is present, cookie is consulted."""
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "free:tok_free_xyz")
    req = _make_request(cookies={"structural_api_token": "tok_free_xyz"})
    assert verify_api_token(req) == "free"


def test_header_wins_over_cookie(monkeypatch):
    """Authorization header takes precedence over cookie."""
    monkeypatch.setenv(
        "STRUCTURAL_API_TOKENS",
        "paid:tok_paid_abc,free:tok_free_xyz",
    )
    req = _make_request(
        headers={"Authorization": "Bearer tok_paid_abc"},
        cookies={"structural_api_token": "tok_free_xyz"},
    )
    assert verify_api_token(req) == "paid"


def test_bare_token_defaults_to_free(monkeypatch):
    """Legacy env entries without `<tier>:` prefix get treated as free."""
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "legacy_token_no_prefix")
    req = _make_request(headers={"Authorization": "Bearer legacy_token_no_prefix"})
    assert verify_api_token(req) == "free"


def test_higher_tier_wins_when_token_reused(monkeypatch):
    """If the same token string appears under two tiers, paid wins."""
    monkeypatch.setenv(
        "STRUCTURAL_API_TOKENS",
        "free:dup_token,paid:dup_token",
    )
    req = _make_request(headers={"Authorization": "Bearer dup_token"})
    assert verify_api_token(req) == "paid"


def test_empty_env_no_tokens(monkeypatch):
    """Empty env → any provided token is invalid; absent token is anonymous."""
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "")
    assert verify_api_token(_make_request()) == "anonymous"
    req = _make_request(headers={"Authorization": "Bearer anything"})
    assert verify_api_token(req) is None


def test_malformed_bearer_falls_through_to_anonymous(monkeypatch):
    """Authorization header without the Bearer prefix is ignored."""
    monkeypatch.delenv("STRUCTURAL_API_TOKENS", raising=False)
    req = _make_request(headers={"Authorization": "Basic abcd"})
    # No bearer found, no cookie → anonymous (not None).
    assert verify_api_token(req) == "anonymous"


# ---------------- get_rate_limit_tier ----------------


def test_get_rate_limit_tier_known():
    assert get_rate_limit_tier("paid") == "60/minute"
    assert get_rate_limit_tier("free") == "10/minute"
    assert get_rate_limit_tier("anonymous") == "5/minute"


def test_get_rate_limit_tier_case_insensitive():
    assert get_rate_limit_tier("PAID") == "60/minute"
    assert get_rate_limit_tier("Free") == "10/minute"


def test_get_rate_limit_tier_unknown_falls_back_to_anonymous():
    # Conservative default: never accidentally promote unknown tiers.
    assert get_rate_limit_tier("vip") == "5/minute"
    assert get_rate_limit_tier("") == "5/minute"
    assert get_rate_limit_tier(None) == "5/minute"  # type: ignore[arg-type]


# ---------------- tier_limit (key/limit string for slowapi) ----------------


def test_tier_limit_anonymous_has_ip_suffix(monkeypatch):
    monkeypatch.delenv("STRUCTURAL_API_TOKENS", raising=False)
    req = _make_request(client_host="198.51.100.42")
    assert tier_limit(req) == "anonymous:198.51.100.42"


def test_tier_limit_paid_promotes(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:tok_paid_abc")
    req = _make_request(
        headers={"Authorization": "Bearer tok_paid_abc"},
        client_host="198.51.100.42",
    )
    assert tier_limit(req) == "paid:198.51.100.42"


def test_tier_limit_invalid_token_buckets_as_anonymous(monkeypatch):
    """Bad token must NOT accidentally land in a generous bucket."""
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "paid:correct")
    req = _make_request(
        headers={"Authorization": "Bearer wrong"},
        client_host="198.51.100.42",
    )
    assert tier_limit(req) == "anonymous:198.51.100.42"
