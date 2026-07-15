from __future__ import annotations

import logging
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from v4.product.d1_phase_detector.api.privacy_middleware import (
    PrivacyRequestContextMiddleware,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(PrivacyRequestContextMiddleware)

    @app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError("bounded failure")

    return app


def test_valid_request_id_is_echoed_exactly_once() -> None:
    request_id = "7dca94aef82f4f548b19857dddbb12f4"
    with TestClient(_app()) as client:
        response = client.get("/ok", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers.get_list("x-request-id") == [request_id]


def test_invalid_request_id_is_replaced() -> None:
    canary = "private/request?id=secret"
    with TestClient(_app()) as client:
        response = client.get("/ok", headers={"X-Request-ID": canary})
    generated = response.headers["x-request-id"]
    assert generated != canary
    assert re.fullmatch(r"[0-9a-f-]{36}", generated)


def test_human_readable_request_id_cannot_inject_log_content() -> None:
    supplied = "alice.example.com-private"
    with TestClient(_app()) as client:
        response = client.get("/ok", headers={"X-Request-ID": supplied})
    assert response.headers["x-request-id"] != supplied
    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["x-request-id"])


def test_exception_log_uses_template_and_omits_request_canaries(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="phase.privacy")
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.get(
            "/explode?secret=query-canary-771",
            headers={
                "Referer": "https://private.example/referrer-canary-882",
                "User-Agent": "ua-canary-993",
            },
        )
    assert response.status_code == 500
    records = [record for record in caplog.records if record.name == "phase.privacy"]
    assert len(records) == 1
    record = records[0]
    assert record.route_template == "/explode"
    assert record.request_method == "GET"
    serialized = repr(record.__dict__)
    for canary in ("query-canary-771", "referrer-canary-882", "ua-canary-993"):
        assert canary not in serialized
    assert response.headers.get_list("x-request-id") == [record.request_id]
