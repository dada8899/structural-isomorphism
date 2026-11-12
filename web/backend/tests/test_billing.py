"""Unit tests for api.billing — W7-D mini-brief 2 (2026-05-24).

Covers:
  - checkout fails closed unless billing and Stripe are configured
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
import time
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import billing  # noqa: E402


def _stripe_signature(body: str, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    signed = str(ts).encode() + b"." + body.encode()
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


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
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("STRUCTURAL_ADMIN_TOKEN", raising=False)

    app = FastAPI()
    app.include_router(billing.router, prefix="/api")
    return TestClient(app)


# ---------- Checkout session ----------

def test_checkout_fails_closed_when_no_key(client):
    """No Stripe configuration must never simulate a paid subscription."""
    r = client.post(
        "/api/billing/checkout-session",
        json={"tier": "pro", "interval": "month", "email": "alice@example.com"},
    )
    assert r.status_code == 503
    data = r.json()
    assert data["mode"] == "unavailable"
    assert data["error"] == "billing_not_available"
    assert "session_id" not in data
    assert "url" not in data


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


def test_checkout_team_year_is_unavailable_without_stripe(client):
    r = client.post(
        "/api/billing/checkout-session",
        json={"tier": "team", "interval": "year", "email": "team@example.com"},
    )
    assert r.status_code == 503
    data = r.json()
    assert data["mode"] == "unavailable"
    assert "amount_cents" not in data


# ---------- Webhook ----------

def test_webhook_persists_event(client, monkeypatch):
    """Webhook stores event into billing_events table and returns 200."""
    evt = {
        "id": "evt_test_001",
        "type": "checkout.session.completed",
        "data": {"object": {"customer_email": "alice@example.com"}},
    }
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRUCTURAL_ADMIN_TOKEN", "admin-test")
    body = json.dumps(evt)
    signature = _stripe_signature(body, "whsec_test")
    r = client.post(
        "/api/billing/webhook",
        content=body,
        headers={"content-type": "application/json", "stripe-signature": signature},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["event_id"] == "evt_test_001"
    assert data["event_type"] == "checkout.session.completed"
    assert data["verified"] is True

    # Verify in DB
    with sqlite3.connect(str(billing._data_file())) as conn:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM billing_events"))
        assert len(rows) == 1
        assert rows[0]["event_id"] == "evt_test_001"
        assert rows[0]["verified"] == 1

    # Recent events endpoint
    r2 = client.get("/api/billing/events/recent", headers={"x-admin-token": "admin-test"})
    assert r2.status_code == 200
    assert r2.json()["count"] == 1


def test_webhook_duplicate_event_is_idempotent(client, monkeypatch):
    """Same event_id arriving twice → 200 with `duplicate: true`, no extra row."""
    evt = {"id": "evt_dup_001", "type": "invoice.paid", "data": {}}
    body = json.dumps(evt)
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_dup")
    signature = _stripe_signature(body, "whsec_dup")
    headers = {"content-type": "application/json", "stripe-signature": signature}

    r1 = client.post(
        "/api/billing/webhook",
        content=body,
        headers=headers,
    )
    assert r1.status_code == 200
    assert r1.json().get("duplicate") is not True

    r2 = client.post(
        "/api/billing/webhook",
        content=body,
        headers=headers,
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
    monkeypatch.setenv("BILLING_ENABLED", "true")

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
    expected = _stripe_signature(body, "whsec_test_secret_xyz")
    r3 = client.post(
        "/api/billing/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "stripe-signature": expected,
        },
    )
    assert r3.status_code == 200
    assert r3.json()["verified"] is True


def test_webhook_rejects_stale_valid_signature(client, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_stale")
    monkeypatch.setenv("BILLING_ENABLED", "true")
    body = json.dumps({"id": "evt_stale", "type": "invoice.paid"})
    stale = _stripe_signature(body, "whsec_stale", int(time.time()) - 301)
    response = client.post(
        "/api/billing/webhook",
        content=body,
        headers={"content-type": "application/json", "stripe-signature": stale},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "signature_mismatch"


# ---------- Real Stripe path (mocked SDK) ----------

def test_checkout_uses_stripe_when_key_present(client, monkeypatch):
    """When STRIPE_TEST_SECRET_KEY is set + SDK importable, the endpoint calls
    Stripe. We monkey-patch the lazy import to return a fake module so we
    don't hit the network."""
    monkeypatch.setenv("STRIPE_TEST_SECRET_KEY", "sk_test_xyz")
    monkeypatch.setenv("BILLING_ENABLED", "true")

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
