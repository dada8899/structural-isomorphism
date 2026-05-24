"""Unit tests for api.billing — W7-D mini-brief 2 (2026-05-24).

Covers:
  - checkout-session mock fallback (no STRIPE_TEST_SECRET_KEY)
  - webhook persists event to billing_events table
  - webhook duplicate event_id is OK (idempotent)
  - webhook signature mismatch returns 400 when secret is configured

Run:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_billing.py -v
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import billing  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect SQLite to tmp
    monkeypatch.setattr(
        billing, "_data_file",
        lambda: tmp_path / "data" / "billing.db",
    )
    # Force mock mode by default (no Stripe key). Individual tests can opt in.
    monkeypatch.delenv("STRIPE_TEST_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)

    app = FastAPI()
    app.include_router(billing.router, prefix="/api")
    return TestClient(app)


# ---------- Checkout session ----------

def test_checkout_mock_fallback_when_no_key(client):
    """No STRIPE_TEST_SECRET_KEY → falls back to mock mode."""
    r = client.post(
        "/api/billing/checkout-session",
        json={"tier": "pro", "interval": "month", "email": "alice@example.com"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "mock"
    assert data["session_id"].startswith("mock_cs_")
    assert data["amount_cents"] == 1900  # $19.00
    assert "url" in data
    assert "session_id=mock_cs_" in data["url"]


def test_checkout_validation_errors(client):
    # Bad tier
    r = client.post(
        "/api/billing/checkout-session",
        json={"tier": "enterprise", "interval": "month", "email": "x@y.com"},
    )
    assert r.status_code == 400
    assert "invalid tier" in r.json()["error"]

    # Bad interval
    r = client.post(
        "/api/billing/checkout-session",
        json={"tier": "pro", "interval": "decade", "email": "x@y.com"},
    )
    assert r.status_code == 400
    assert "invalid interval" in r.json()["error"]

    # Bad email
    r = client.post(
        "/api/billing/checkout-session",
        json={"tier": "pro", "interval": "month", "email": "not-an-email"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid email"


def test_checkout_team_year_amount(client):
    r = client.post(
        "/api/billing/checkout-session",
        json={"tier": "team", "interval": "year", "email": "team@example.com"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["amount_cents"] == 99000  # $990.00


# ---------- Webhook ----------

def test_webhook_persists_event(client):
    """Webhook stores event into billing_events table and returns 200."""
    evt = {
        "id": "evt_test_001",
        "type": "checkout.session.completed",
        "data": {"object": {"customer_email": "alice@example.com"}},
    }
    r = client.post(
        "/api/billing/webhook",
        content=json.dumps(evt),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["event_id"] == "evt_test_001"
    assert data["event_type"] == "checkout.session.completed"
    assert data["verified"] is False  # no secret configured → verified=0

    # Verify in DB
    with sqlite3.connect(str(billing._data_file())) as conn:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM billing_events"))
        assert len(rows) == 1
        assert rows[0]["event_id"] == "evt_test_001"
        assert rows[0]["verified"] == 0

    # Recent events endpoint
    r2 = client.get("/api/billing/events/recent")
    assert r2.status_code == 200
    assert r2.json()["count"] == 1


def test_webhook_duplicate_event_is_idempotent(client):
    """Same event_id arriving twice → 200 with `duplicate: true`, no extra row."""
    evt = {"id": "evt_dup_001", "type": "invoice.paid", "data": {}}
    body = json.dumps(evt)

    r1 = client.post(
        "/api/billing/webhook",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r1.status_code == 200
    assert r1.json().get("duplicate") is not True

    r2 = client.post(
        "/api/billing/webhook",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r2.status_code == 200
    assert r2.json()["duplicate"] is True

    with sqlite3.connect(str(billing._data_file())) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM billing_events WHERE event_id=?",
            ("evt_dup_001",),
        ).fetchone()[0]
        assert n == 1


def test_webhook_signature_mismatch_rejected(client, monkeypatch):
    """When STRIPE_WEBHOOK_SECRET is set, mismatched signature → 400."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret_xyz")

    evt = {"id": "evt_sig_001", "type": "x", "data": {}}
    body = json.dumps(evt)

    # No signature header
    r = client.post(
        "/api/billing/webhook",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "signature_mismatch"

    # Bad signature
    r2 = client.post(
        "/api/billing/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "stripe-signature": "sha256=deadbeef",
        },
    )
    assert r2.status_code == 400

    # Correct sha256-prefixed signature → accepted with verified=true
    expected = hmac.new(
        b"whsec_test_secret_xyz", body.encode("utf-8"), hashlib.sha256,
    ).hexdigest()
    r3 = client.post(
        "/api/billing/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "stripe-signature": f"sha256={expected}",
        },
    )
    assert r3.status_code == 200
    assert r3.json()["verified"] is True


# ---------- Real Stripe path (mocked SDK) ----------

def test_checkout_uses_stripe_when_key_present(client, monkeypatch):
    """When STRIPE_TEST_SECRET_KEY is set + SDK importable, the endpoint calls
    Stripe. We monkey-patch the lazy import to return a fake module so we
    don't hit the network."""
    monkeypatch.setenv("STRIPE_TEST_SECRET_KEY", "sk_test_xyz")

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            assert kwargs["customer_email"] == "alice@example.com"
            assert kwargs["mode"] == "subscription"
            return {
                "id": "cs_test_abc123",
                "url": "https://checkout.stripe.com/c/pay/cs_test_abc123",
            }

    class FakeCheckout:
        Session = FakeSession

    class FakeStripe:
        api_key = None
        checkout = FakeCheckout

    monkeypatch.setattr(billing, "_stripe_module", lambda: FakeStripe)

    r = client.post(
        "/api/billing/checkout-session",
        json={"tier": "pro", "interval": "month", "email": "alice@example.com"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "stripe"
    assert data["session_id"] == "cs_test_abc123"
    assert data["url"].startswith("https://checkout.stripe.com/")
