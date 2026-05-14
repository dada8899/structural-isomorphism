"""Unit tests for api.newsletter — session #9 W2-A.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_newsletter.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import newsletter as nl  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect storage to tmp_path so tests don't write to the repo.
    tmp_file = tmp_path / "data" / "newsletter-subscribers.jsonl"
    monkeypatch.setattr(nl, "_data_file", lambda: tmp_file)

    app = FastAPI()
    app.include_router(nl.router, prefix="/api")
    return TestClient(app)


def test_subscribe_valid(client):
    r = client.post(
        "/api/newsletter/subscribe",
        json={"email": "alice@example.com", "source": "start-here-essay-end"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["created"] is True
    assert data["email"] == "alice@example.com"


def test_subscribe_duplicate(client):
    payload = {"email": "bob@example.com", "source": "test"}
    r1 = client.post("/api/newsletter/subscribe", json=payload)
    assert r1.status_code == 200 and r1.json()["created"] is True

    r2 = client.post("/api/newsletter/subscribe", json=payload)
    assert r2.status_code == 200
    assert r2.json()["created"] is False


def test_subscribe_case_insensitive_dedupe(client):
    client.post(
        "/api/newsletter/subscribe",
        json={"email": "lower@example.com", "source": "test"},
    )
    r = client.post(
        "/api/newsletter/subscribe",
        json={"email": "LOWER@example.com", "source": "test"},
    )
    assert r.status_code == 200
    assert r.json()["created"] is False


def test_invalid_email_format(client):
    r = client.post(
        "/api/newsletter/subscribe",
        json={"email": "not-an-email", "source": "test"},
    )
    assert r.status_code == 400
    assert "invalid email" in r.json()["error"]


def test_empty_email(client):
    r = client.post(
        "/api/newsletter/subscribe",
        json={"email": "", "source": "test"},
    )
    assert r.status_code == 400


def test_too_long_email(client):
    r = client.post(
        "/api/newsletter/subscribe",
        json={"email": "a" * 200 + "@x.com", "source": "test"},
    )
    assert r.status_code == 400


def test_invalid_source(client):
    r = client.post(
        "/api/newsletter/subscribe",
        json={"email": "valid@example.com", "source": "drop-table-users"},
    )
    assert r.status_code == 400
    assert "invalid source" in r.json()["error"]


def test_all_allowed_sources(client):
    """Every source registered in _ALLOWED_SOURCES must round-trip."""
    for i, src in enumerate(sorted(nl._ALLOWED_SOURCES)):
        r = client.post(
            "/api/newsletter/subscribe",
            json={"email": f"user{i}@example.com", "source": src},
        )
        assert r.status_code == 200, f"source {src!r} got {r.status_code}: {r.text}"
        assert r.json()["created"] is True


def test_count_endpoint(client):
    assert client.get("/api/newsletter/count").json()["count"] == 0
    client.post(
        "/api/newsletter/subscribe",
        json={"email": "c1@example.com", "source": "test"},
    )
    client.post(
        "/api/newsletter/subscribe",
        json={"email": "c2@example.com", "source": "test"},
    )
    # Duplicate doesn't bump count.
    client.post(
        "/api/newsletter/subscribe",
        json={"email": "c1@example.com", "source": "test"},
    )
    assert client.get("/api/newsletter/count").json()["count"] == 2


def test_email_normalized_to_lowercase_in_storage(client, tmp_path, monkeypatch):
    # Re-mount with a fresh tmp file we can read directly.
    tmp_file = tmp_path / "data" / "subs.jsonl"
    monkeypatch.setattr(nl, "_data_file", lambda: tmp_file)
    app = FastAPI()
    app.include_router(nl.router, prefix="/api")
    c = TestClient(app)
    c.post(
        "/api/newsletter/subscribe",
        json={"email": "MixedCase@Example.COM", "source": "test"},
    )
    content = tmp_file.read_text(encoding="utf-8")
    assert "mixedcase@example.com" in content
    assert "MixedCase" not in content
