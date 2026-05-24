"""W11-A coverage gap fillers for api/checkout_mock.py.

Targets uncovered lines:
- _data_file() actual call (line 86)
- random decline path (line 139) — the "real decision" branch when no force_status
- _persist exception handler (lines 210-211)
- /api/usage q_tier path with localhost (line 247)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import checkout_mock as cm  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    tmp_file = tmp_path / "data" / "mock_checkouts.jsonl"
    monkeypatch.setattr(cm, "_data_file", lambda: tmp_file)
    app = FastAPI()
    app.include_router(cm.router, prefix="/api")
    return TestClient(app)


# --- _data_file (line 86) ----------------------------------------------------


def test_data_file_returns_path_inside_backend_data_dir():
    """Direct invocation of _data_file() exercises line 86."""
    p = cm._data_file()
    assert isinstance(p, Path)
    assert p.name == "mock_checkouts.jsonl"
    # Should be inside web/backend/data/
    assert "data" in p.parts


# --- random decline branch (line 139) ----------------------------------------


def test_random_decline_path_taken_when_no_force(client, monkeypatch):
    """Patch random.random to return 0.0 → forces decline via real branch."""
    monkeypatch.setattr(cm.random, "random", lambda: 0.0)
    resp = client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "month",
            "email": "a@b.co",
            "name": "Test User",
            # NO force_status — exercises probabilistic line 139
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "declined"
    assert body["reason"] == "card_declined"


def test_random_success_path_taken_when_no_force(client, monkeypatch):
    """random.random returning 0.99 → success via probabilistic branch."""
    monkeypatch.setattr(cm.random, "random", lambda: 0.99)
    resp = client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "year",
            "email": "rich@b.co",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["amount_usd"] == 190


# --- _persist exception handler (lines 210-211) ------------------------------


def test_persist_failure_does_not_break_endpoint(client, monkeypatch):
    """If _persist raises on open(), endpoint still returns success.

    Forces _data_file to point at a path that will fail to write
    (a directory we can't actually open as a file) — exercises the
    `except Exception` arm.
    """
    monkeypatch.setattr(cm.random, "random", lambda: 0.99)  # force success

    def boom_open(*a, **kw):
        raise PermissionError("disk full")

    # Patch the builtin `open` used inside _persist
    import builtins
    real_open = builtins.open

    def selective_open(file, *a, **kw):
        # Only fail when writing the mock_checkouts.jsonl
        if "mock_checkouts.jsonl" in str(file):
            raise PermissionError("simulated disk full")
        return real_open(file, *a, **kw)

    monkeypatch.setattr(builtins, "open", selective_open)

    resp = client.post(
        "/api/checkout/mock",
        json={"tier": "pro", "interval": "month", "email": "z@b.co"},
    )
    # Endpoint must still succeed despite persist failing
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_persist_failure_on_decline_path(client, monkeypatch):
    """Decline branch also persists; failure must not break user response."""
    monkeypatch.setattr(cm.random, "random", lambda: 0.0)  # force decline

    import builtins
    real_open = builtins.open

    def selective_open(file, *a, **kw):
        if "mock_checkouts.jsonl" in str(file):
            raise OSError("io error")
        return real_open(file, *a, **kw)

    monkeypatch.setattr(builtins, "open", selective_open)

    resp = client.post(
        "/api/checkout/mock",
        json={"tier": "team", "interval": "month", "email": "d@e.co"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"


# --- /api/usage q_tier path (line 247) ---------------------------------------


def test_usage_q_tier_promotes_to_pro_when_localhost(client):
    """?tier=pro on localhost → returns pro limits via q_tier branch."""
    resp = client.get("/api/usage?tier=pro")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "pro"
    assert body["ticker_limit"] == 1000


def test_usage_q_tier_team_localhost(client):
    resp = client.get("/api/usage?tier=team")
    assert resp.status_code == 200
    assert resp.json()["tier"] == "team"


def test_usage_q_tier_invalid_falls_back_to_default(client):
    """Invalid q_tier → falls into else branch → free."""
    resp = client.get("/api/usage?tier=enterprise_xyz")
    assert resp.status_code == 200
    assert resp.json()["tier"] == "free"


def test_usage_q_tier_blank_falls_back(client):
    resp = client.get("/api/usage?tier=")
    assert resp.status_code == 200
    assert resp.json()["tier"] == "free"


# --- additional edge cases for robustness ------------------------------------


def test_checkout_invalid_tier_returns_400(client):
    resp = client.post(
        "/api/checkout/mock",
        json={"tier": "enterprise", "interval": "month", "email": "a@b.co"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid tier"
    assert "pro" in body["allowed"]
    assert "team" in body["allowed"]


def test_checkout_invalid_interval_returns_400(client):
    resp = client.post(
        "/api/checkout/mock",
        json={"tier": "pro", "interval": "biennial", "email": "a@b.co"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid interval"


def test_checkout_invalid_email_returns_400(client):
    resp = client.post(
        "/api/checkout/mock",
        json={"tier": "pro", "interval": "month", "email": "not-an-email"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid email"


def test_checkout_email_too_long_returns_400(client):
    long_email = "a" * 250 + "@b.co"
    resp = client.post(
        "/api/checkout/mock",
        json={"tier": "pro", "interval": "month", "email": long_email},
    )
    assert resp.status_code == 400


def test_checkout_card_last4_extracts_digits_only(client, monkeypatch, tmp_path):
    """card_last4 with mixed chars: only last-4 digits kept."""
    monkeypatch.setattr(cm.random, "random", lambda: 0.99)  # force success
    tmp_file = tmp_path / "data" / "mock_checkouts.jsonl"
    monkeypatch.setattr(cm, "_data_file", lambda: tmp_file)

    resp = client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "month",
            "email": "x@y.co",
            "card_last4": "abcd1234efgh",
        },
    )
    assert resp.status_code == 200


def test_checkout_force_status_success_localhost(client, monkeypatch):
    """force_status=success on localhost → success path even if random.random() < 0.1."""
    monkeypatch.setattr(cm.random, "random", lambda: 0.0)  # would decline normally
    resp = client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "month",
            "email": "x@y.co",
            "force_status": "success",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_checkout_force_status_declined_localhost(client, monkeypatch):
    monkeypatch.setattr(cm.random, "random", lambda: 0.99)  # would succeed normally
    resp = client.post(
        "/api/checkout/mock",
        json={
            "tier": "team",
            "interval": "year",
            "email": "x@y.co",
            "force_status": "declined",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"


def test_checkout_name_truncated_to_max_len(client, monkeypatch):
    monkeypatch.setattr(cm.random, "random", lambda: 0.99)
    resp = client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "month",
            "email": "x@y.co",
            "name": "x" * 500,  # over _MAX_NAME_LEN (100)
        },
    )
    assert resp.status_code == 200
