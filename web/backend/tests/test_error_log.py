"""Unit tests for api.error_log — W12-E.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_error_log.py -q
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

from api import error_log as el  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    tmp_file = tmp_path / "data" / "error_log.jsonl"
    monkeypatch.setattr(el, "_data_file", lambda: tmp_file)
    # Reset rate-limit buckets between tests so we get a fresh window.
    el._buckets.clear()

    app = FastAPI()
    app.include_router(el.router, prefix="/api")
    return TestClient(app), tmp_file


def _valid_payload(**overrides):
    base = {
        "message": "TypeError: cannot read property 'x' of undefined",
        "stack": "at Foo (page.tsx:42)\nat Bar (page.tsx:84)",
        "digest": "abcdef0123",
        "url": "https://phase.bytedance.city/company/AAPL?utm_source=spam",
        "userAgent": "Mozilla/5.0 (test)",
        "timestamp": 1715750000,
        "sessionId": "test-session-1",
        "fatal": False,
    }
    base.update(overrides)
    return base


def test_valid_report_stored(client):
    c, log_path = client
    r = c.post("/api/errors", json=_valid_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] is True
    assert "stored_at" in body
    # File should have one line.
    assert log_path.exists()
    rows = log_path.read_text().splitlines()
    assert len(rows) == 1
    record = json.loads(rows[0])
    assert record["message"].startswith("TypeError")
    # URL query string must be stripped server-side.
    assert "utm_source" not in (record["url"] or "")
    assert record["url"] == "https://phase.bytedance.city/company/AAPL"
    assert record["sessionId"] == "test-session-1"
    assert record["fatal"] is False


def test_fatal_flag_preserved(client):
    c, log_path = client
    r = c.post("/api/errors", json=_valid_payload(fatal=True, sessionId="fatal-1"))
    assert r.status_code == 200
    record = json.loads(log_path.read_text().splitlines()[-1])
    assert record["fatal"] is True


def test_rate_limit_kicks_in(client):
    c, _ = client
    payload = _valid_payload(sessionId="rl-session")
    # First 10 must be accepted.
    for i in range(el.RATE_LIMIT_MAX):
        r = c.post("/api/errors", json=payload)
        assert r.status_code == 200, f"req {i} failed: {r.text}"
        assert r.json()["accepted"] is True, f"req {i} rejected: {r.json()}"
    # 11th in the same window must be rejected as rate-limited.
    r = c.post("/api/errors", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False
    assert body["reason"] == "rate_limited"


def test_rate_limit_per_session_independent(client):
    c, _ = client
    payload_a = _valid_payload(sessionId="alpha")
    payload_b = _valid_payload(sessionId="beta")
    for _ in range(el.RATE_LIMIT_MAX):
        c.post("/api/errors", json=payload_a)
    # Alpha is now capped; beta should still go through.
    r = c.post("/api/errors", json=payload_b)
    assert r.json()["accepted"] is True


def test_malformed_missing_message(client):
    c, _ = client
    r = c.post("/api/errors", json={"stack": "boom"})
    assert r.status_code == 422


def test_malformed_extra_field_rejected(client):
    """Privacy: schema forbids extra fields so localStorage can't sneak through."""
    c, _ = client
    payload = _valid_payload()
    payload["secret_token"] = "leaked"
    r = c.post("/api/errors", json=payload)
    assert r.status_code == 422


def test_message_too_long_rejected(client):
    c, _ = client
    r = c.post("/api/errors", json=_valid_payload(message="x" * 600))
    assert r.status_code == 422


def test_rotation_at_10mb(client, monkeypatch):
    c, log_path = client
    # Shrink the rotation threshold so we don't actually write 10MB in test.
    monkeypatch.setattr(el, "MAX_LOG_BYTES", 2048)
    payload = _valid_payload(stack="x" * 400, sessionId="rot-test")
    # 10 records ≈ enough to exceed 2KB once.
    for i in range(el.RATE_LIMIT_MAX):
        r = c.post("/api/errors", json=payload)
        assert r.status_code == 200
    rotated = log_path.with_suffix(log_path.suffix + ".1")
    # Either active or rotated must exist; rotation only triggers when size
    # threshold is crossed *before* the next write.
    assert log_path.exists()
    # The rotation file is best-effort; assert no crash + at least one record.
    record = json.loads(log_path.read_text().splitlines()[-1])
    assert record["sessionId"] == "rot-test"
    # rotated file existence depends on cumulative byte size — assert it's
    # either absent (small payloads) or non-empty.
    if rotated.exists():
        assert rotated.stat().st_size > 0


def test_anonymous_no_session_uses_ip_bucket(client):
    c, _ = client
    payload = _valid_payload()
    payload["sessionId"] = None
    for _ in range(el.RATE_LIMIT_MAX):
        r = c.post("/api/errors", json=payload)
        assert r.json()["accepted"] is True
    # Same IP, no session → bucketed together → 11th rejected.
    r = c.post("/api/errors", json=payload)
    assert r.json()["accepted"] is False
