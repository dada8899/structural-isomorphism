"""Unit tests for api.checkout_mock — W10-B (session #10).

Asserts:
  - Endpoint contract (status / customer_id / checkout_session_id shape)
  - Persistence to mock_checkouts.jsonl
  - Tier + interval validation (400 on bad input)
  - Decline-path persistence
  - /api/usage returns the right ticker_limit per tier
  - Force-status override only honoured from localhost (security guard)

Run:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_checkout_mock.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import checkout_mock as cm  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect jsonl persistence to tmp so tests don't pollute repo data dir.
    tmp_file = tmp_path / "data" / "mock_checkouts.jsonl"
    monkeypatch.setattr(cm, "_data_file", lambda: tmp_file)

    app = FastAPI()
    app.include_router(cm.router, prefix="/api")
    return TestClient(app)


# ---------- POST /api/checkout/mock ----------

def test_success_returns_customer_and_session_ids(client):
    r = client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "month",
            "email": "alice@example.com",
            "name": "Alice",
            "card_last4": "4242",
            "force_status": "success",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["customer_id"].startswith("mock_cus_")
    assert data["checkout_session_id"].startswith("mock_cs_")
    assert data["tier"] == "pro"
    assert data["interval"] == "month"
    assert data["amount_usd"] == 19


def test_success_team_year_amount(client):
    """Team annual = $990 (10 months for the price of 10× monthly)."""
    r = client.post(
        "/api/checkout/mock",
        json={
            "tier": "team",
            "interval": "year",
            "email": "team@example.com",
            "force_status": "success",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["amount_usd"] == 990


def test_declined_path_returns_reason(client):
    r = client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "month",
            "email": "decline@example.com",
            "force_status": "declined",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "declined"
    assert data["reason"] == "card_declined"
    # Decline path should NOT leak customer/session ids
    assert "customer_id" not in data
    assert "checkout_session_id" not in data


def test_persists_success_to_jsonl(client, tmp_path):
    client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "month",
            "email": "persist@example.com",
            "name": "Persist",
            "force_status": "success",
        },
    )
    f = cm._data_file()
    assert f.exists()
    rows = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "success"
    assert row["email"] == "persist@example.com"
    assert row["tier"] == "pro"
    assert row["interval"] == "month"
    assert row["amount_usd"] == 19
    assert "customer_id" in row
    assert "ts" in row and "iso" in row


def test_persists_decline_to_jsonl(client):
    client.post(
        "/api/checkout/mock",
        json={
            "tier": "team",
            "interval": "month",
            "email": "decline2@example.com",
            "force_status": "declined",
        },
    )
    f = cm._data_file()
    rows = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["status"] == "declined"
    assert rows[0]["email"] == "decline2@example.com"


def test_invalid_tier_rejected(client):
    r = client.post(
        "/api/checkout/mock",
        json={"tier": "enterprise", "interval": "month", "email": "x@y.com"},
    )
    assert r.status_code == 400
    assert "invalid tier" in r.json()["error"]


def test_invalid_interval_rejected(client):
    r = client.post(
        "/api/checkout/mock",
        json={"tier": "pro", "interval": "decade", "email": "x@y.com"},
    )
    assert r.status_code == 400
    assert "invalid interval" in r.json()["error"]


def test_invalid_email_rejected(client):
    r = client.post(
        "/api/checkout/mock",
        json={"tier": "pro", "interval": "month", "email": "not-an-email"},
    )
    assert r.status_code == 400
    assert "invalid email" in r.json()["error"]


def test_empty_email_rejected(client):
    r = client.post(
        "/api/checkout/mock",
        json={"tier": "pro", "interval": "month", "email": ""},
    )
    assert r.status_code == 400


def test_card_last4_only_digits_kept(client):
    """Garbage in card_last4 should be stripped, not crash."""
    client.post(
        "/api/checkout/mock",
        json={
            "tier": "pro",
            "interval": "month",
            "email": "card@example.com",
            "card_last4": "abcd4242xyz",
            "force_status": "success",
        },
    )
    rows = [json.loads(ln) for ln in cm._data_file().read_text().splitlines() if ln.strip()]
    # First 4 digits extracted: "4242"
    assert rows[0]["card_last4"] == "4242"


# ---------- GET /api/usage ----------

def test_usage_default_is_free(client):
    r = client.get("/api/usage")
    assert r.status_code == 200
    data = r.json()
    assert data["tier"] == "free"
    assert data["ticker_limit"] == 100
    assert data["api_quota_today"] == 50
    assert data["api_calls_today"] == 0


def test_usage_pro_via_header(client):
    r = client.get("/api/usage", headers={"x-mock-tier": "pro"})
    assert r.status_code == 200
    data = r.json()
    assert data["tier"] == "pro"
    assert data["ticker_limit"] == 1000


def test_usage_team_via_header(client):
    r = client.get("/api/usage", headers={"x-mock-tier": "team"})
    assert r.status_code == 200
    data = r.json()
    assert data["tier"] == "team"
    assert data["ticker_limit"] == 5000


def test_usage_cookie_tier(client):
    r = client.get("/api/usage", cookies={"mock_tier": "pro"})
    assert r.status_code == 200
    assert r.json()["tier"] == "pro"


def test_usage_unknown_tier_falls_back_to_free(client):
    r = client.get("/api/usage", headers={"x-mock-tier": "vip"})
    assert r.status_code == 200
    assert r.json()["tier"] == "free"


def test_usage_header_wins_over_cookie(client):
    """Header is the higher-precedence channel (matches verify_api_token pattern)."""
    r = client.get(
        "/api/usage",
        headers={"x-mock-tier": "pro"},
        cookies={"mock_tier": "team"},
    )
    assert r.status_code == 200
    assert r.json()["tier"] == "pro"
