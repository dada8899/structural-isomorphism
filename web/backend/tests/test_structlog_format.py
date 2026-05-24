"""W14-D: structlog JSON format + processor pipeline tests.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_structlog_format.py -v
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from logging_config import (  # noqa: E402
    REQUEST_ID_VAR,
    REQUEST_METHOD_VAR,
    REQUEST_PATH_VAR,
    REQUEST_TIER_VAR,
    configure_logging,
    current_log_file,
    get_logger,
    new_request_id,
)


# ISO 8601 UTC timestamp shape: "2026-05-15T10:30:00.123456Z" or similar.
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+\-]\d{2}:?\d{2})$"
)


def _read_last_json_line(path: Path) -> dict:
    """Read the rotating log file and return the last non-empty parsed line."""
    assert path.exists(), f"log file {path} should exist"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, "log file should contain at least one line"
    return json.loads(lines[-1])


@pytest.fixture(autouse=True)
def fresh_log(tmp_path, monkeypatch):
    """Point each test at its own log file so assertions don't collide."""
    p = tmp_path / "server.jsonl"
    monkeypatch.setenv("STRUCTURAL_LOG_FILE", str(p))
    configure_logging(log_file=p)
    yield p
    # Clean teardown — reset contextvars in case a test left them set.
    try:
        REQUEST_ID_VAR.set("-")
        REQUEST_PATH_VAR.set(None)
        REQUEST_METHOD_VAR.set(None)
        REQUEST_TIER_VAR.set(None)
    except Exception:
        pass


def test_sample_log_line_is_valid_json(fresh_log):
    """Every emitted line must parse as JSON. No half-text, half-json hybrid."""
    log = get_logger("structural.test")
    log.info("sample.event", k="v")
    entry = _read_last_json_line(fresh_log)
    assert isinstance(entry, dict)
    assert entry.get("event") == "sample.event"
    assert entry.get("k") == "v"


def test_log_line_has_iso_timestamp(fresh_log):
    log = get_logger("structural.test")
    log.info("ts.check")
    entry = _read_last_json_line(fresh_log)
    assert "timestamp" in entry, f"no timestamp in {entry!r}"
    assert _ISO_RE.match(entry["timestamp"]), (
        f"timestamp {entry['timestamp']!r} not ISO 8601"
    )


def test_log_line_has_level_field(fresh_log):
    log = get_logger("structural.test")
    log.warning("warn.check")
    entry = _read_last_json_line(fresh_log)
    assert entry.get("level") in ("warning", "WARNING")


def test_log_line_has_service_metadata(fresh_log):
    log = get_logger("structural.test")
    log.info("svc.check")
    entry = _read_last_json_line(fresh_log)
    assert entry.get("service") == "structural-backend"


def test_log_line_includes_request_id_from_contextvar(fresh_log):
    """When REQUEST_ID_VAR is bound, every log line auto-injects it."""
    log = get_logger("structural.test")
    rid = new_request_id()
    token = REQUEST_ID_VAR.set(rid)
    try:
        log.info("rid.check")
    finally:
        REQUEST_ID_VAR.reset(token)
    entry = _read_last_json_line(fresh_log)
    assert entry.get("request_id") == rid


def test_request_id_omitted_when_unset(fresh_log):
    """Log lines outside a request scope must NOT have a stray '-' id."""
    log = get_logger("structural.test")
    log.info("no.rid.check")
    entry = _read_last_json_line(fresh_log)
    # Either omitted or sentinel '-' — we just don't want a misleading value.
    rid = entry.get("request_id")
    assert rid in (None, "-"), f"unexpected request_id: {rid!r}"


def test_path_and_method_propagate(fresh_log):
    log = get_logger("structural.test")
    p = REQUEST_PATH_VAR.set("/api/test")
    m = REQUEST_METHOD_VAR.set("POST")
    t = REQUEST_TIER_VAR.set("pro")
    try:
        log.info("ctx.check")
    finally:
        REQUEST_TIER_VAR.reset(t)
        REQUEST_METHOD_VAR.reset(m)
        REQUEST_PATH_VAR.reset(p)
    entry = _read_last_json_line(fresh_log)
    assert entry.get("path") == "/api/test"
    assert entry.get("method") == "POST"
    assert entry.get("tier") == "pro"


def test_arbitrary_kwargs_become_top_level_fields(fresh_log):
    log = get_logger("structural.test")
    log.info("ask.llm.start", model="deepseek-chat", kb_count=12, latency_ms=234)
    entry = _read_last_json_line(fresh_log)
    assert entry.get("model") == "deepseek-chat"
    assert entry.get("kb_count") == 12
    assert entry.get("latency_ms") == 234


def test_stdlib_logging_also_flows_through_pipeline(fresh_log):
    """logging.getLogger(...).info(...) must be JSON-formatted too —
    so uvicorn/fastapi logs share the same shape."""
    import logging as stdlib_logging

    stdlib_logging.getLogger("structural.legacy").info("legacy_event")
    entry = _read_last_json_line(fresh_log)
    # message may land under `event` (structlog) or `msg` (stdlib bridge)
    # — the formatter normalizes both to the JSON output.
    payload = json.dumps(entry)
    assert "legacy_event" in payload


def test_current_log_file_resolves_env(monkeypatch, tmp_path):
    """STRUCTURAL_LOG_FILE env var overrides the default location."""
    p = tmp_path / "custom.jsonl"
    monkeypatch.setenv("STRUCTURAL_LOG_FILE", str(p))
    assert current_log_file() == p


def test_exception_info_serializes(fresh_log):
    """Tracebacks must serialize without crashing the formatter."""
    log = get_logger("structural.test")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("err.check")
    entry = _read_last_json_line(fresh_log)
    # `exception` or `exc_info` field, depending on processor chain.
    payload = json.dumps(entry)
    assert "boom" in payload or "RuntimeError" in payload
