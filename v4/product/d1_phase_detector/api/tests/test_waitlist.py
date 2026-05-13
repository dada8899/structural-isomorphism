"""Tests for the W8-D waitlist endpoints.

We seed the same DB-isolation pattern as test_screener.py:
- Each test gets a fresh SQLite DB.
- The app's @on_event("startup") hook creates the `waitlist` table inside the
  TestClient lifespan (TestClient triggers startup on first request).
"""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "wd1.sqlite"
    # waitlist tests don't require seeded company rows; we just need the file
    # to be a valid sqlite db that the app can open.
    sqlite3.connect(str(db_path)).close()

    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")
    monkeypatch.delenv("BUTTONDOWN_API_KEY", raising=False)

    import v4.product.d1_phase_detector.api.db as db_mod
    import v4.product.d1_phase_detector.api.main as main_mod

    importlib.reload(db_mod)
    importlib.reload(main_mod)

    # TestClient as context manager → triggers startup → ensures table exists.
    with TestClient(main_mod.app) as c:
        yield c


# ---------- POST /api/waitlist ----------


def test_signup_success(client):
    r = client.post(
        "/api/waitlist", data={"email": "hello@example.com", "source": "phase_detector"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["created"] is True


def test_signup_default_source(client):
    r = client.post("/api/waitlist", data={"email": "user@example.com"})
    assert r.status_code == 200
    assert r.json()["created"] is True


def test_signup_idempotent_returns_created_false(client):
    client.post("/api/waitlist", data={"email": "dup@example.com"})
    r = client.post("/api/waitlist", data={"email": "dup@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is False
    assert "already" in body["msg"].lower()


def test_signup_email_normalization(client):
    """Mixed case / leading-trailing whitespace normalize to one row."""
    r1 = client.post("/api/waitlist", data={"email": "Mixed@Example.COM"})
    r2 = client.post("/api/waitlist", data={"email": "  mixed@example.com  "})
    assert r1.json()["created"] is True
    assert r2.json()["created"] is False
    cr = client.get("/api/waitlist/count")
    assert cr.json()["count"] == 1


def test_signup_invalid_email_no_at(client):
    r = client.post("/api/waitlist", data={"email": "not-an-email"})
    assert r.status_code == 422


def test_signup_invalid_email_no_tld(client):
    r = client.post("/api/waitlist", data={"email": "foo@bar"})
    assert r.status_code == 422


def test_signup_invalid_email_empty(client):
    r = client.post("/api/waitlist", data={"email": "   "})
    assert r.status_code == 422


def test_signup_unknown_source_gets_normalized(client):
    r = client.post(
        "/api/waitlist", data={"email": "src@example.com", "source": "totally_bogus"}
    )
    assert r.status_code == 200
    assert r.json()["created"] is True
    # Verify the stored source was normalized to the default.
    import v4.product.d1_phase_detector.api.db as db_mod

    with db_mod.get_cursor() as (cur, driver):
        cur.execute("SELECT source FROM waitlist WHERE email = ?", ("src@example.com",))
        row = cur.fetchone()
        assert row[0] == "phase_detector"


def test_signup_with_placement_and_referrer(client):
    r = client.post(
        "/api/waitlist",
        data={
            "email": "place@example.com",
            "source": "main_site",
            "placement": "hero",
            "referrer": "https://structural.bytedance.city/",
        },
    )
    assert r.status_code == 200
    assert r.json()["created"] is True

    import v4.product.d1_phase_detector.api.db as db_mod

    with db_mod.get_cursor() as (cur, driver):
        cur.execute(
            "SELECT source, placement, referrer FROM waitlist WHERE email = ?",
            ("place@example.com",),
        )
        row = cur.fetchone()
        assert row[0] == "main_site"
        assert row[1] == "hero"
        assert row[2] == "https://structural.bytedance.city/"


# ---------- GET /api/waitlist/count ----------


def test_count_empty(client):
    r = client.get("/api/waitlist/count")
    assert r.status_code == 200
    assert r.json() == {"count": 0}


def test_count_increments(client):
    client.post("/api/waitlist", data={"email": "a@example.com"})
    client.post("/api/waitlist", data={"email": "b@example.com"})
    client.post("/api/waitlist", data={"email": "a@example.com"})  # duplicate
    r = client.get("/api/waitlist/count")
    assert r.json()["count"] == 2


# ---------- CORS preflight ----------


def test_waitlist_cors_allows_post(client):
    r = client.options(
        "/api/waitlist",
        headers={
            "Origin": "https://structural.bytedance.city",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    # FastAPI's CORSMiddleware returns 200 on the preflight when accepted.
    assert r.status_code in (200, 204)
    assert "POST" in r.headers.get("access-control-allow-methods", "")
