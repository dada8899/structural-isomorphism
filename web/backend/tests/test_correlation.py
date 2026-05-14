"""W14-D: Correlation-ID middleware tests.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_correlation.py -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from logging_config import REQUEST_ID_VAR, configure_logging, get_logger  # noqa: E402
from middleware.correlation import (  # noqa: E402
    REQUEST_ID_HEADER,
    CorrelationIdMiddleware,
    _coerce_request_id,
    install_correlation_middleware,
)


# UUID4 hex (no dashes) = 32 hex chars; we generate via uuid.uuid4().hex.
_UUID_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture
def app(tmp_path):
    """Build a tiny FastAPI app with only the correlation middleware so
    tests don't depend on the full main.py wiring (search service, etc.)."""
    # Point logs at a tmp file so we don't litter the repo.
    log_file = tmp_path / "server.jsonl"
    configure_logging(log_file=log_file)

    a = FastAPI()
    install_correlation_middleware(a)

    captured: dict = {"rid": None}

    @a.get("/echo")
    async def echo():
        # Capture the contextvar inside a handler so the test can prove
        # the middleware set it before our code ran.
        captured["rid"] = REQUEST_ID_VAR.get()
        return {"ok": True}

    a.state.captured = captured
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def test_request_without_header_gets_generated_uuid(client, app):
    """No X-Request-ID in → 32-char hex UUID4 generated + echoed back."""
    r = client.get("/echo")
    assert r.status_code == 200
    rid = r.headers.get(REQUEST_ID_HEADER)
    assert rid is not None, "X-Request-ID must be echoed on response"
    assert _UUID_HEX_RE.match(rid), f"expected uuid4 hex, got {rid!r}"
    # The same id must have been visible to the handler.
    assert app.state.captured["rid"] == rid


def test_request_with_header_propagates(client, app):
    """Caller-supplied ID survives round-trip and is bound to the handler."""
    supplied = "my-custom-id-1234"
    r = client.get("/echo", headers={REQUEST_ID_HEADER: supplied})
    assert r.status_code == 200
    assert r.headers.get(REQUEST_ID_HEADER) == supplied
    assert app.state.captured["rid"] == supplied


def test_response_echoes_back_header(client):
    """Echo header is present even on non-handler code paths (eg 404)."""
    r = client.get("/no-such-route")
    assert r.status_code == 404
    assert r.headers.get(REQUEST_ID_HEADER), "404 should still carry X-Request-ID"


def test_lowercase_header_accepted(client, app):
    """Header lookup must be case-insensitive (RFC 7230 §3.2)."""
    r = client.get("/echo", headers={"x-request-id": "abc-lower"})
    assert r.headers.get(REQUEST_ID_HEADER) == "abc-lower"
    assert app.state.captured["rid"] == "abc-lower"


def test_malformed_id_replaced_with_uuid(client):
    """Garbage IDs (eg with spaces / control chars) get a fresh UUID."""
    r = client.get(
        "/echo",
        headers={REQUEST_ID_HEADER: "bad id with spaces and !@# chars"},
    )
    rid = r.headers.get(REQUEST_ID_HEADER)
    assert _UUID_HEX_RE.match(rid), f"malformed input should be replaced, got {rid!r}"


def test_coerce_request_id_unit():
    """Pure-fn unit test on the coercion helper."""
    # Empty → generated
    assert _UUID_HEX_RE.match(_coerce_request_id(None))
    assert _UUID_HEX_RE.match(_coerce_request_id(""))
    assert _UUID_HEX_RE.match(_coerce_request_id("   "))
    # Bad char → generated
    assert _UUID_HEX_RE.match(_coerce_request_id("has space"))
    assert _UUID_HEX_RE.match(_coerce_request_id("has\nnewline"))
    # Good → passthrough (trimmed)
    assert _coerce_request_id("good-id_123") == "good-id_123"
    assert _coerce_request_id("  trimmed  ") == "trimmed"
    # 64-char cap respected
    long_id = "a" * 64
    assert _coerce_request_id(long_id) == long_id
    too_long = "a" * 65
    assert _coerce_request_id(too_long) != too_long


def test_log_line_includes_request_id(client, tmp_path):
    """Log lines emitted inside a request scope must carry the request_id."""
    # Reconfigure to ensure logs land in a known tmp file.
    log_file = tmp_path / "server.jsonl"
    configure_logging(log_file=log_file)

    a = FastAPI()
    install_correlation_middleware(a)

    @a.get("/ping")
    async def ping():
        get_logger("structural.test").info("ping.handler", custom_field="hello")
        return {"pong": True}

    c = TestClient(a)
    supplied = "abc12345"
    r = c.get("/ping", headers={REQUEST_ID_HEADER: supplied})
    assert r.status_code == 200

    # Read the rotating file and look for at least one line tagged with
    # the supplied request_id + our custom event name.
    text = log_file.read_text(encoding="utf-8")
    assert supplied in text, "expected request_id in log file"
    assert "ping.handler" in text, "expected event name in log file"
    # And the per-request http.request line that middleware emits.
    assert "http.request" in text or "http.response" in text


def test_request_id_isolated_between_requests(client, app):
    """Two requests must not share a request_id (no contextvar bleed)."""
    r1 = client.get("/echo")
    r2 = client.get("/echo")
    assert r1.headers[REQUEST_ID_HEADER] != r2.headers[REQUEST_ID_HEADER]
