from __future__ import annotations

import json
import logging
import sys
from copy import deepcopy
from types import SimpleNamespace

from services import observability


CANARIES = (
    "query-canary-a116cf",
    "Bearer-token-canary-6f922c",
    "privacy-canary@example.test",
    "203.0.113.242",
    "session=cookie-canary-0631e1",
    "https://ref.example/referrer-canary-8c97f3",
)


def test_sentry_event_scrubber_rebuilds_from_allowlist_without_mutating_input(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SENTRY_RELEASE", "2026.07.14")
    event = {
        "event_id": "a" * 32,
        "level": "error",
        "timestamp": "2026-07-14T12:00:00Z",
        "platform": "python",
        "environment": "production",
        "release": "2026.07.14",
        "request": {
            "url": f"https://example.test/search?q={CANARIES[0]}",
            "data": CANARIES[1],
            "cookies": CANARIES[4],
            "headers": {"Referer": CANARIES[5], "X-Forwarded-For": CANARIES[3]},
        },
        "breadcrumbs": {"values": [{"message": CANARIES[0]}]},
        "extra": {"email": CANARIES[2]},
        "user": {"ip_address": CANARIES[3]},
        "message": " ".join(CANARIES),
        "logentry": {"message": CANARIES[1]},
        "transaction": f"/items/{CANARIES[0]}",
        "spans": [{"description": CANARIES[5]}],
        "tags": {
            "request_id": "proxy-request-id-1",
            "incident_id": "b" * 32,
            "error_type": "RuntimeError",
            "status_code": 500,
            "service": "structural-backend",
            "email": CANARIES[2],
        },
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": CANARIES[1],
                    "stacktrace": {"frames": [{"vars": {"secret": CANARIES[0]}}]},
                }
            ]
        },
    }
    original = deepcopy(event)

    clean = observability.scrub_sentry_event(event)

    assert event == original
    assert clean == {
        "event_id": "a" * 32,
        "level": "error",
        "timestamp": "2026-07-14T12:00:00Z",
        "platform": "python",
        "environment": "production",
        "release": "2026.07.14",
        "tags": {
            "request_id": "proxy-request-id-1",
            "incident_id": "b" * 32,
            "error_type": "RuntimeError",
            "status_code": 500,
            "service": "structural-backend",
        },
        "exception": {"values": [{"type": "RuntimeError"}]},
    }
    serialized = json.dumps(clean)
    for secret in CANARIES:
        assert secret not in serialized


def test_sentry_event_scrubber_fails_closed_for_invalid_events() -> None:
    assert observability.scrub_sentry_event("not-an-event") is None
    assert observability.scrub_sentry_event({}) is None
    assert observability.scrub_sentry_event({"event_id": "not-hex"}) is None
    assert observability.scrub_sentry_event({"event_id": "a" * 32}) == {
        "event_id": "a" * 32
    }


def test_transaction_scrubber_drops_transaction_name_spans_and_measurements() -> None:
    event = {
        "event_id": "c" * 32,
        "level": "info",
        "transaction": f"/analyze/{CANARIES[0]}",
        "spans": [{"description": CANARIES[1]}],
        "measurements": {CANARIES[2]: {"value": 1}},
        "contexts": {"trace": {"description": CANARIES[5]}},
    }
    assert observability.scrub_sentry_event(event) == {
        "event_id": "c" * 32,
        "level": "info",
    }


def test_json_formatter_drops_content_and_exception_details() -> None:
    try:
        raise RuntimeError(CANARIES[1])
    except RuntimeError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="structural.events",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="privacy.canary",
        args=(),
        exc_info=exc_info,
    )
    record.fields = {
        "request_id": "request-id-123",
        "incident_id": "d" * 32,
        "error_type": "RuntimeError",
        "status_code": 500,
        "latency_ms": 12.5,
        "email": CANARIES[2],
        "ip": CANARIES[3],
        "referrer": CANARIES[5],
        "service": CANARIES[0],
    }

    payload = json.loads(observability.JsonFormatter().format(record))

    assert payload["event"] == "privacy.canary"
    assert payload["service"] == "structural-backend"
    assert payload["request_id"] == "request-id-123"
    assert payload["incident_id"] == "d" * 32
    assert payload["error_type"] == "RuntimeError"
    assert payload["status_code"] == 500
    assert payload["latency_ms"] == 12.5
    serialized = json.dumps(payload)
    for secret in CANARIES:
        assert secret not in serialized
    assert "traceback" not in serialized.casefold()


def test_setup_logging_registers_fail_closed_sentry_controls(monkeypatch) -> None:
    captured = {}

    def init(**kwargs):
        captured.update(kwargs)

    monkeypatch.setenv("SENTRY_DSN", "https://public@example.test/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", SimpleNamespace(init=init))
    monkeypatch.setattr(observability, "_sentry_enabled", False)

    observability.setup_logging()

    assert captured["send_default_pii"] is False
    assert captured["attach_stacktrace"] is False
    assert captured["max_breadcrumbs"] == 0
    assert captured["max_request_body_size"] == "never"
    assert captured["before_breadcrumb"] is observability._drop_breadcrumb
    assert captured["before_send"] is observability.scrub_sentry_event
    assert captured["before_send_transaction"] is observability.scrub_sentry_event
    assert observability._drop_breadcrumb({"message": CANARIES[0]}) is None
    assert observability.sentry_is_enabled() is True
