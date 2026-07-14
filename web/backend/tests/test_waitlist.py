"""Unit tests for api.waitlist — W7-D mini-brief 1 (2026-05-24).

Covers:
  - happy path (creates row, returns created=true)
  - duplicate email returns created=false (not an error)
  - invalid email rejected with 400
  - rate limit (5 per IP per window) returns 429
  - UTM params captured and persisted

Run:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_waitlist.py -v
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import waitlist as wl  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect SQLite file to tmp so tests don't pollute repo data/
    tmp_db = tmp_path / "data" / "waitlist.db"
    monkeypatch.setattr(wl, "_data_file", lambda: tmp_db)
    # Reset per-IP rate buckets so tests don't interfere
    wl._reset_rate_limits()

    app = FastAPI()
    app.include_router(wl.router, prefix="/api")
    return TestClient(app)


# ---------- Happy path ----------

def test_happy_path_creates_row(client):
    r = client.post(
        "/api/waitlist",
        json={"email": "alice@example.com", "source": "homepage-hero"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data == {"ok": True, "created": True, "email": "alice@example.com"}

    # Row landed in SQLite with correct shape
    with sqlite3.connect(str(wl._data_file())) as conn:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM waitlist_signups"))
        assert len(rows) == 1
        r0 = rows[0]
        assert r0["email"] == "alice@example.com"
        assert r0["source"] == "homepage-hero"
        assert r0["created_at"]  # non-empty ISO timestamp
        assert r0["ip"] is None
        assert r0["ua"] is None

    # Count endpoint reflects it
    r2 = client.get("/api/waitlist/count")
    assert r2.status_code == 200
    assert r2.json()["count"] == 1


# ---------- Duplicate email ----------

def test_duplicate_email_returns_created_false(client):
    body = {"email": "dup@example.com", "source": "homepage-hero"}
    r1 = client.post("/api/waitlist", json=body)
    assert r1.json()["created"] is True

    r2 = client.post("/api/waitlist", json=body)
    assert r2.status_code == 200
    assert r2.json() == {
        "ok": True, "created": False, "email": "dup@example.com"
    }

    # Only one row in DB
    with sqlite3.connect(str(wl._data_file())) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM waitlist_signups"
        ).fetchone()[0]
        assert n == 1


# ---------- Validation failures ----------

def test_invalid_email_rejected(client):
    r = client.post(
        "/api/waitlist",
        json={"email": "not-an-email", "source": "homepage-hero"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid email"


def test_invalid_source_rejected(client):
    r = client.post(
        "/api/waitlist",
        json={"email": "ok@example.com", "source": "evil-source"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid source"


# ---------- Rate limit ----------

def test_rate_limit_after_5_signups(client):
    """6th signup from the same IP within the window should be 429."""
    for i in range(5):
        r = client.post(
            "/api/waitlist",
            json={"email": f"u{i}@example.com", "source": "test"},
        )
        assert r.status_code == 200, f"signup {i} unexpected status"

    r6 = client.post(
        "/api/waitlist",
        json={"email": "u5@example.com", "source": "test"},
    )
    assert r6.status_code == 429
    assert r6.json()["error"] == "rate_limited"
    assert "testclient" not in wl._rate_buckets


def test_signup_does_not_persist_client_metadata(client):
    response = client.post(
        "/api/waitlist",
        json={"email": "metadata@example.com", "source": "test"},
        headers={"User-Agent": "ua-canary-887738"},
    )
    assert response.status_code == 200
    with sqlite3.connect(str(wl._data_file())) as conn:
        row = conn.execute(
            "SELECT ip, ua FROM waitlist_signups WHERE email = ?",
            ("metadata@example.com",),
        ).fetchone()
    assert row == (None, None)


# ---------- UTM capture ----------

def test_utm_params_persisted(client):
    r = client.post(
        "/api/waitlist",
        json={
            "email": "utm@example.com",
            "source": "homepage-hero",
            "utm_source": "twitter",
            "utm_medium": "tweet",
            "utm_campaign": "phase-launch",
            "utm_content": "thread-1",
        },
    )
    assert r.status_code == 200
    assert r.json()["created"] is True

    with sqlite3.connect(str(wl._data_file())) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM waitlist_signups WHERE email = ?",
            ("utm@example.com",),
        ).fetchone()
        assert row is not None
        assert row["utm_source"] == "twitter"
        assert row["utm_medium"] == "tweet"
        assert row["utm_campaign"] == "phase-launch"
        assert row["utm_content"] == "thread-1"
        assert row["utm_term"] is None  # not provided → NULL
