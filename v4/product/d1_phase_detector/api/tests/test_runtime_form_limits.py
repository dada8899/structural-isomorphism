"""Actual Phase form routes under the compatible patched runtime."""
from __future__ import annotations

import importlib
import sqlite3
from urllib.parse import urlencode

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "phase-form-limits.sqlite"
    sqlite3.connect(path).close()
    monkeypatch.setenv("DB_URL", f"sqlite:///{path}")
    monkeypatch.delenv("BUTTONDOWN_API_KEY", raising=False)
    import v4.product.d1_phase_detector.api.db as db
    import v4.product.d1_phase_detector.api.main as main
    importlib.reload(db)
    importlib.reload(main)
    with TestClient(main.app) as session:
        yield session, path


def _rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT email, source FROM waitlist ORDER BY email").fetchall()


def test_normal_urlencoded_and_multipart_forms_still_store(client):
    session, path = client
    assert session.post("/api/waitlist", data={"email": "normal@example.com"}).status_code == 200
    response = session.post(
        "/api/waitlist", files={"email": (None, "multipart@example.com"), "source": (None, "phase_detector")},
    )
    assert response.status_code == 200
    assert len(_rows(path)) == 2


def test_urlencoded_field_count_is_rejected_before_storage(client):
    session, path = client
    values = [("email", "count@example.com"), *[(f"extra{i}", "v") for i in range(1001)]]
    response = session.post(
        "/api/waitlist", content=urlencode(values),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400
    assert "Too many fields" in response.text
    assert _rows(path) == []


@pytest.mark.parametrize("multipart", [False, True])
def test_oversized_field_is_rejected_without_echo_or_storage(client, multipart):
    session, path = client
    value = "private-body-canary-" + "a" * (1024 * 1024)
    if multipart:
        response = session.post("/api/waitlist", files={"email": (None, "size@example.com"), "extra": (None, value)})
    else:
        response = session.post("/api/waitlist", data={"email": "size@example.com", "extra": value})
    assert response.status_code == 400
    assert "private-body-canary" not in response.text
    assert _rows(path) == []


def test_semicolon_is_literal_not_a_second_form_field(client):
    session, path = client
    response = session.post(
        "/api/waitlist", content="email=literal%40example.com&source=phase_detector;placement=hero",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    # Old non-standard semicolon-separated clients must migrate to ampersands.
    assert _rows(path) == [("literal@example.com", "phase_detector")]


@pytest.mark.parametrize("headers", [
    [f"X-Extra-{i}: bounded" for i in range(9)],
    ["X-Extra: " + "a" * 5000],
])
def test_multipart_header_resources_are_rejected_before_storage(client, headers):
    session, path = client
    boundary = "runtime-header-probe"
    lines = [
        f"--{boundary}",
        'Content-Disposition: form-data; name="email"',
        *headers, "", "headers@example.com", f"--{boundary}--", "",
    ]
    response = session.post(
        "/api/waitlist", content="\r\n".join(lines),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 400
    assert _rows(path) == []
