from __future__ import annotations

import hashlib

import pytest
from starlette.requests import Request

from services.privacy_identifiers import (
    opaque_identifier,
    validate_privacy_hmac_config,
)


STRONG_KEY = ("01234567" + "89abcdef") * 4


def test_production_privacy_key_is_mandatory(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.delenv("STRUCTURAL_PRIVACY_HMAC_KEY", raising=False)
    with pytest.raises(RuntimeError, match="STRUCTURAL_PRIVACY_HMAC_KEY"):
        validate_privacy_hmac_config()


@pytest.mark.parametrize(
    "value",
    [
        "short",
        "a" * 64,
        "replace-with-private-64-hex-chars",
        f'"{STRONG_KEY}"',
        rf"{STRONG_KEY[:60]}\x41",
        STRONG_KEY.upper(),
        f'"{STRONG_KEY[:62]}"',
        f" {STRONG_KEY}",
        f"{STRONG_KEY} ",
    ],
)
def test_noncanonical_privacy_key_fails_closed(monkeypatch, value: str) -> None:
    monkeypatch.setenv("STRUCTURAL_PRIVACY_HMAC_KEY", value)
    with pytest.raises(RuntimeError, match="unquoted lowercase 64-hex"):
        validate_privacy_hmac_config()


def test_v2_identifiers_are_normalized_keyed_and_domain_separated(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURAL_PRIVACY_HMAC_KEY", STRONG_KEY)
    raw = "Alice@Example.COM"
    email = opaque_identifier("auth-rate.email", raw, kind="email")
    normalized = opaque_identifier(
        "auth-rate.email", " alice@example.com ", kind="email"
    )
    deletion = opaque_identifier("account-deletion.email", raw, kind="email")

    assert email == normalized
    assert email.startswith("auth-rate.email:v2:")
    assert deletion.startswith("account-deletion.email:v2:")
    assert email != deletion
    assert raw.lower() not in email
    assert hashlib.sha256(raw.lower().encode()).hexdigest() not in email


def test_ip_addresses_use_canonical_form(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURAL_PRIVACY_HMAC_KEY", STRONG_KEY)
    expanded = "2001:0db8:0000:0000:0000:0000:0000:0001"
    compressed = "2001:db8::1"
    assert opaque_identifier("waitlist-rate.ip", expanded, kind="ip") == (
        opaque_identifier("waitlist-rate.ip", compressed, kind="ip")
    )


def test_all_slowapi_key_functions_hide_raw_ip(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURAL_PRIVACY_HMAC_KEY", STRONG_KEY)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/health",
            "headers": [],
            "client": ("198.51.100.77", 4321),
            "scheme": "https",
            "server": ("testserver", 443),
            "query_string": b"",
        }
    )
    from middleware.rate_limit import CURRENT_TIER, _composite_key
    from services.rate_limit import _privacy_remote_address

    token = CURRENT_TIER.set("free")
    try:
        tier_key = _composite_key(request)
    finally:
        CURRENT_TIER.reset(token)
    route_key = _privacy_remote_address(request)
    assert tier_key.startswith("free:tier-rate.ip:v2:")
    assert route_key.startswith("route-rate.ip:v2:")
    assert "198.51.100.77" not in tier_key + route_key


def test_auth_store_rejects_new_raw_rate_bucket_writes(tmp_path) -> None:
    from services.auth_store import AuthStore

    store = AuthStore(tmp_path / "auth.sqlite3")
    with pytest.raises(ValueError, match="v2 HMAC"):
        store.record_rate_request("alice@example.com", 3)
    with pytest.raises(ValueError, match="v2 HMAC"):
        store.record_rate_requests([("198.51.100.7", 3)])
    with pytest.raises(ValueError, match="v2 HMAC"):
        store.record_rate_request("global:alice.example.com", 3)
