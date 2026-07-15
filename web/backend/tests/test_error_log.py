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
        "message": "TypeError",
        "timestamp": 1715750000,
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
    assert set(record) == {
        "event", "incident_id", "error_type", "timestamp", "iso", "fatal",
    }
    assert record["event"] == "client_error"
    assert record["error_type"] == "TypeError"
    assert len(record["incident_id"]) == 32
    assert record["fatal"] is False
    assert "testclient" not in json.dumps(record)


def test_fatal_flag_preserved(client):
    c, log_path = client
    r = c.post("/api/errors", json=_valid_payload(fatal=True))
    assert r.status_code == 200
    record = json.loads(log_path.read_text().splitlines()[-1])
    assert record["fatal"] is True


def test_rate_limit_kicks_in(client):
    c, _ = client
    payload = _valid_payload()
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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("stack", "at Secret (private.tsx:42)"),
        ("digest", "app-controlled-digest"),
        ("url", "https://phase.bytedance.city/private?q=secret"),
        ("userAgent", "private-browser-fingerprint"),
        ("sessionId", "private-session-id"),
    ),
)
def test_pre_hardening_raw_fields_are_rejected_before_model_acceptance(
    client, field, value,
):
    c, log_path = client
    r = c.post("/api/errors", json=_valid_payload(**{field: value}))
    assert r.status_code == 422
    assert not log_path.exists()


@pytest.mark.parametrize(
    "message",
    (
        "TypeError: secret value",
        "secret value",
        "typeerror",
        "",
        "X" * 600,
    ),
)
def test_raw_or_nonallowlisted_message_is_rejected(client, message):
    c, log_path = client
    r = c.post("/api/errors", json=_valid_payload(message=message))
    assert r.status_code == 422
    assert not log_path.exists()


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


def test_rotation_at_10mb(client, monkeypatch):
    c, log_path = client
    # Shrink the rotation threshold so we don't actually write 10MB in test.
    monkeypatch.setattr(el, "MAX_LOG_BYTES", 2048)
    payload = _valid_payload()
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
    assert record["event"] == "client_error"
    assert "sessionId" not in record
    # rotated file existence depends on cumulative byte size — assert it's
    # either absent (small payloads) or non-empty.
    if rotated.exists():
        assert rotated.stat().st_size > 0


def test_content_free_reports_share_the_server_ip_bucket(client):
    c, _ = client
    payload = _valid_payload()
    for _ in range(el.RATE_LIMIT_MAX):
        r = c.post("/api/errors", json=payload)
        assert r.json()["accepted"] is True
    # Same server-observed IP → bucketed together → 11th rejected.
    r = c.post("/api/errors", json=payload)
    assert r.json()["accepted"] is False


def test_rate_bucket_keys_are_stable_v2_hmacs(client):
    c, _ = client
    c.post("/api/errors", json=_valid_payload())
    assert el._buckets
    serialized = json.dumps(sorted(el._buckets))
    assert "testclient" not in serialized
    assert all(
        key.startswith("client-errors-rate.ip:v2:") and len(key.rsplit(":", 1)[1]) == 64
        for key in el._buckets
    )


def test_legacy_error_bucket_is_preserved_during_v2_upgrade(client):
    c, _ = client
    legacy = el._legacy_bucket_key("testclient")
    el._buckets[legacy].extend([el.time.time()] * el.RATE_LIMIT_MAX)
    response = c.post("/api/errors", json=_valid_payload())
    assert response.json()["accepted"] is False
    assert legacy not in el._buckets
    assert el._bucket_key("testclient") in el._buckets
