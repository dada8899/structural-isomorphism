"""
Observability foundation: structured JSON logging + optional Sentry SDK.

Wire-up:
    from services.observability import setup_logging, log_event
    setup_logging()                      # call once at app startup
    log_event("user_query", device_id=d, kind="ask", latency_ms=120)

The JSON formatter emits one event per line on stdout, suitable for systemd /
docker / Loki ingestion. Sentry is opt-in via `SENTRY_DSN` env var; if the SDK
is not installed or DSN is unset, Sentry init silently no-ops.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

_LOG_NAME = "structural.events"
_logger = logging.getLogger(_LOG_NAME)
_sentry_enabled = False


class JsonFormatter(logging.Formatter):
    """Minimal JSON line formatter. Promotes `extra={"fields": {...}}` into the
    top-level object so structured fields remain queryable."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for k, v in fields.items():
                if k in payload:
                    continue  # don't clobber reserved keys
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            # Last-resort fallback so logging never raises into the app.
            return json.dumps({"ts": payload["ts"], "level": payload["level"], "msg": payload["msg"]})


def setup_logging(level: str | int | None = None) -> None:
    """Idempotent: install JSON handler on the events logger + (optionally) Sentry.

    Does NOT touch the root logger config — leaves whatever main.py already set
    (basicConfig with timestamped text) intact for non-event logs.
    """
    global _sentry_enabled

    lvl_env = level if level is not None else os.getenv("OBS_LOG_LEVEL", "INFO")
    lvl = getattr(logging, str(lvl_env).upper(), logging.INFO) if isinstance(lvl_env, str) else lvl_env

    # Idempotent handler install
    has_json = any(getattr(h, "_obs_json", False) for h in _logger.handlers)
    if not has_json:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        setattr(handler, "_obs_json", True)
        _logger.addHandler(handler)
    _logger.setLevel(lvl)
    _logger.propagate = False  # avoid double-logging via root

    # Optional Sentry init — guarded import, env-gated.
    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        try:  # pragma: no cover — depends on optional dep
            import sentry_sdk  # type: ignore

            sentry_sdk.init(
                dsn=dsn,
                environment=os.getenv("SENTRY_ENV", "production"),
                traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
                send_default_pii=False,
            )
            _sentry_enabled = True
            _logger.info("sentry_initialized", extra={"fields": {"env": os.getenv("SENTRY_ENV", "production")}})
        except ImportError:
            _logger.info("sentry_sdk not installed; SENTRY_DSN ignored")
        except Exception as e:  # pragma: no cover
            _logger.warning("sentry_init_failed: %s", e)


def log_event(event: str, **fields: Any) -> None:
    """Emit one structured event line. Extra kwargs land as JSON fields."""
    payload = {"event": event, **fields}
    _logger.info(event, extra={"fields": payload})


def sentry_is_enabled() -> bool:
    return _sentry_enabled
