"""Content-free operational events and fail-closed optional Sentry export."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import time
from typing import Any

_LOG_NAME = "structural.events"
_logger = logging.getLogger(_LOG_NAME)
_sentry_enabled = False

_EVENT_RE = re.compile(
    r"^(?:auth|account_data|ask|analyze|billing|checkout|history|http|llm|privacy|retrieval|"
    r"sentry|startup|waitlist|newsletter)\.[a-z0-9_.-]{1,95}$"
)
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/+-]{1,160}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_INCIDENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_EVENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_ERROR_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,95}$")
_SENTRY_LEVELS = {"debug", "info", "warning", "error", "fatal"}
_MODEL_RE = re.compile(r"^[A-Za-z0-9_.:/+-]{1,120}$")
_ENV_VALUES = {"dev", "development", "production", "staging", "test"}
_TIER_VALUES = {"anonymous", "free", "guest", "pro", "research", "unknown"}
_SAFE_EVENT_NUMBER_FIELDS = {
    "count",
    "elapsed_ms",
    "latency_ms",
    "remaining",
    "sent",
    "status_code",
}
_SAFE_EVENT_BOOL_FIELDS = {"retryable"}


def _safe_operational_payload(
    event: object,
    fields: object,
    *,
    level: str,
    created: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(created)),
        "level": level,
        "event": event if isinstance(event, str) and _EVENT_RE.fullmatch(event)
        else "privacy.log_message_redacted",
        "service": "structural-backend",
    }
    if not isinstance(fields, dict):
        return payload
    request_id = fields.get("request_id")
    if isinstance(request_id, str) and _REQUEST_ID_RE.fullmatch(request_id):
        payload["request_id"] = request_id
    incident_id = fields.get("incident_id")
    if isinstance(incident_id, str) and _INCIDENT_ID_RE.fullmatch(incident_id):
        payload["incident_id"] = incident_id
    env = fields.get("env")
    if isinstance(env, str) and env in _ENV_VALUES:
        payload["env"] = env
    error_type = fields.get("error_type")
    if isinstance(error_type, str) and _ERROR_TYPE_RE.fullmatch(error_type):
        payload["error_type"] = error_type
    model = fields.get("model")
    if isinstance(model, str) and _MODEL_RE.fullmatch(model):
        payload["model"] = model
    tier = fields.get("tier")
    if isinstance(tier, str) and tier in _TIER_VALUES:
        payload["tier"] = tier
    for name in _SAFE_EVENT_NUMBER_FIELDS:
        value = fields.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, int) or math.isfinite(value):
                payload[name] = value
    for name in _SAFE_EVENT_BOOL_FIELDS:
        value = fields.get(name)
        if isinstance(value, bool):
            payload[name] = value
    return payload


def _safe_sentry_tag(name: str, value: object) -> str | int | None:
    if name == "request_id" and isinstance(value, str) and _REQUEST_ID_RE.fullmatch(value):
        return value
    if name == "incident_id" and isinstance(value, str) and _INCIDENT_ID_RE.fullmatch(value):
        return value
    if name == "error_type" and isinstance(value, str) and _ERROR_TYPE_RE.fullmatch(value):
        return value
    if name == "status_code" and isinstance(value, int) and not isinstance(value, bool):
        if 100 <= value <= 599:
            return value
    if name == "service" and value == "structural-backend":
        return "structural-backend"
    return None


def scrub_sentry_event(event: object, _hint: object = None) -> dict[str, Any] | None:
    """Rebuild a Sentry event from a minimal, typed allowlist.

    Request data, URLs, headers, cookies, bodies, messages, breadcrumbs,
    extras, user data, logentry, spans, raw transactions and stack frames are
    never copied. An event without a valid Sentry event ID is not exportable.
    """
    if not isinstance(event, dict):
        return None
    try:
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id):
            return None
        clean: dict[str, Any] = {"event_id": event_id}
        level = event.get("level")
        if isinstance(level, str) and level.casefold() in _SENTRY_LEVELS:
            clean["level"] = level.casefold()
        timestamp = event.get("timestamp")
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
            if math.isfinite(float(timestamp)):
                clean["timestamp"] = timestamp
        elif isinstance(timestamp, str) and len(timestamp) <= 40 and _TOKEN_RE.fullmatch(timestamp):
            clean["timestamp"] = timestamp
        platform = event.get("platform")
        if platform == "python":
            clean["platform"] = "python"
        environment = event.get("environment")
        if isinstance(environment, str) and environment in _ENV_VALUES:
            clean["environment"] = environment
        configured_release = os.getenv("SENTRY_RELEASE", "")
        release = event.get("release")
        if configured_release and release == configured_release and _TOKEN_RE.fullmatch(configured_release):
            clean["release"] = configured_release

        tags = event.get("tags")
        if isinstance(tags, dict):
            safe_tags: dict[str, str | int] = {}
            for name in ("request_id", "incident_id", "error_type", "status_code", "service"):
                safe_value = _safe_sentry_tag(name, tags.get(name))
                if safe_value is not None:
                    safe_tags[name] = safe_value
            if safe_tags:
                clean["tags"] = safe_tags

        raw_exception = event.get("exception")
        if isinstance(raw_exception, dict) and isinstance(raw_exception.get("values"), list):
            safe_values: list[dict[str, str]] = []
            for value in raw_exception["values"][:4]:
                if not isinstance(value, dict):
                    continue
                error_type = value.get("type")
                if isinstance(error_type, str) and _ERROR_TYPE_RE.fullmatch(error_type):
                    safe_values.append({"type": error_type})
            if safe_values:
                clean["exception"] = {"values": safe_values}
        return clean
    except Exception:
        return None


class JsonFormatter(logging.Formatter):
    """Render only content-free operational identifiers and typed counters."""

    def format(self, record: logging.LogRecord) -> str:
        payload = _safe_operational_payload(
            record.getMessage(),
            getattr(record, "fields", None),
            level=record.levelname.casefold(),
            created=record.created,
        )
        try:
            return json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError):
            return json.dumps(
                {
                    "level": "error",
                    "event": "privacy.log_serialize_failed",
                    "service": "structural-backend",
                }
            )


def _drop_breadcrumb(_breadcrumb: object, _hint: object = None) -> None:
    return None


def log_event(event: str, **fields: Any) -> None:
    """Emit through the legacy sink after its formatter rebuilds the payload."""
    _logger.info(event, extra={"fields": fields})


def setup_logging(level: str | int | None = None) -> None:
    """Install the content-free event sink and optional fail-closed Sentry."""
    global _sentry_enabled

    lvl_env = level if level is not None else os.getenv("OBS_LOG_LEVEL", "INFO")
    lvl = getattr(logging, str(lvl_env).upper(), logging.INFO) if isinstance(lvl_env, str) else lvl_env
    has_json = any(getattr(handler, "_obs_json", False) for handler in _logger.handlers)
    if not has_json:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        setattr(handler, "_obs_json", True)
        _logger.addHandler(handler)
    _logger.setLevel(lvl)
    _logger.propagate = False

    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        try:  # pragma: no cover - depends on optional dependency
            import sentry_sdk  # type: ignore

            sentry_sdk.init(
                dsn=dsn,
                environment=os.getenv("SENTRY_ENV", "production"),
                traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
                send_default_pii=False,
                attach_stacktrace=False,
                max_breadcrumbs=0,
                max_request_body_size="never",
                before_breadcrumb=_drop_breadcrumb,
                before_send=scrub_sentry_event,
                before_send_transaction=scrub_sentry_event,
            )
            _sentry_enabled = True
            log_event("sentry.initialized", env=os.getenv("SENTRY_ENV", "production"))
        except ImportError:
            log_event("sentry.sdk_unavailable")
        except Exception as exc:  # pragma: no cover - provider/runtime specific
            log_event(
                "sentry.initialization_failed",
                error_type=type(exc).__name__,
            )


def sentry_is_enabled() -> bool:
    return _sentry_enabled
