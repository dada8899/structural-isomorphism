"""
Structured logging (structlog) + correlation-ID-aware processor pipeline (W14-D).

Goals:
  1. Single JSON-line format on stdout (systemd / docker / Loki-friendly).
  2. Every log line in a request scope automatically carries `request_id`.
  3. Stdlib logging (fastapi, uvicorn, slowapi, our own `logging.getLogger(...)`)
     is routed through the same structlog pipeline, so we get *one* unified
     stream — not "half structlog, half text".
  4. Optional disk sink (rotating file) so an admin tail endpoint can read
     the last N lines deterministically without scraping stdout.

Why structlog (vs raw stdlib logging.handlers + JSONFormatter):
  - First-class contextvars binding (the whole point of correlation IDs).
  - Cheap to add fields at a call site:  `log.info("ask.llm.start", model="x")`
    — no `extra={"fields": {...}}` boilerplate, no clobber rules to remember.
  - Same processors apply uniformly to *every* log entry, regardless of which
    code path emitted it.

The legacy `services.observability.setup_logging()` event-logger continues to
work — its handler is left in place so its existing JSONL contract is
preserved. The two systems share stdout but the events logger uses a
different logger name (`structural.events`) so callers can opt in / out by
choosing their logger.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

import structlog

# ---- request-scoped context vars ----------------------------------------

# The single source of truth for the active request's correlation ID. Set by
# CorrelationIdMiddleware on every incoming request, read by structlog's
# `merge_contextvars` processor on every log call.
REQUEST_ID_VAR: ContextVar[str] = ContextVar("request_id", default="-")

# Optional path / method / tier — populated by the middleware where available
# so all log lines in a request scope carry these without needing each call
# site to pass them. None default keeps non-request log lines clean.
REQUEST_PATH_VAR: ContextVar[Optional[str]] = ContextVar("request_path", default=None)
REQUEST_METHOD_VAR: ContextVar[Optional[str]] = ContextVar("request_method", default=None)
REQUEST_TIER_VAR: ContextVar[Optional[str]] = ContextVar("request_tier", default=None)


def new_request_id() -> str:
    """Generate a fresh correlation ID. UUID4 hex (32 chars, no dashes — easier
    to grep in logs and copy/paste in dashboards)."""
    return uuid.uuid4().hex


# ---- log-file sink (for admin tail endpoint) ----------------------------

_DEFAULT_LOG_DIR = Path(__file__).resolve().parent / "logs"
_DEFAULT_LOG_FILE = "server.jsonl"
_DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MB
_DEFAULT_BACKUP_COUNT = 7


def _resolve_log_path() -> Path:
    """Honour env override; default to web/backend/logs/server.jsonl."""
    custom = os.getenv("STRUCTURAL_LOG_FILE")
    if custom:
        return Path(custom)
    return _DEFAULT_LOG_DIR / _DEFAULT_LOG_FILE


def _ensure_log_dir(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Best-effort — if we can't create the dir (read-only fs in some
        # test envs), the file handler will simply fail and the stream
        # handler still works.
        pass


# ---- structlog processors -----------------------------------------------


def _inject_correlation_ctx(_, __, event_dict: dict) -> dict:
    """Pull request-scoped contextvars onto every log line.

    `merge_contextvars` already handles bound_logger context — this processor
    additionally pulls the *module-level* ContextVars we set in middleware
    (which are not part of structlog's context dict).
    """
    rid = REQUEST_ID_VAR.get()
    if rid and rid != "-":
        event_dict.setdefault("request_id", rid)
    path = REQUEST_PATH_VAR.get()
    if path is not None:
        event_dict.setdefault("path", path)
    method = REQUEST_METHOD_VAR.get()
    if method is not None:
        event_dict.setdefault("method", method)
    tier = REQUEST_TIER_VAR.get()
    if tier is not None:
        event_dict.setdefault("tier", tier)
    return event_dict


def _add_service_metadata(_, __, event_dict: dict) -> dict:
    """Stamp every line with the service name + build env so a shared
    log aggregator (Loki / OpenSearch) can split on `service` cleanly."""
    event_dict.setdefault("service", "structural-backend")
    env = os.getenv("STRUCTURAL_ENV")
    if env:
        event_dict.setdefault("env", env)
    return event_dict


# ---- public API ---------------------------------------------------------


_configured = False


def configure_logging(
    *,
    log_file: Optional[Path] = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
    level: str | int = "INFO",
) -> Path:
    """Configure structlog + stdlib logging into a single JSON pipeline.

    Returns the resolved log-file path (callers — e.g. the admin tail
    endpoint — read from it directly).

    Idempotent: safe to call multiple times. Subsequent calls re-resolve
    the level / file but do not stack handlers.
    """
    global _configured

    path = log_file or _resolve_log_path()
    _ensure_log_dir(path)

    lvl = level
    if isinstance(level, str):
        lvl = getattr(logging, level.upper(), logging.INFO)

    # ---- stdlib root logger: one stream handler + one rotating file ----
    root = logging.getLogger()
    # Tear down anything we previously installed so re-configure is clean.
    for h in list(root.handlers):
        if getattr(h, "_structlog_owned", False):
            root.removeHandler(h)
    root.setLevel(lvl)

    stream_h = logging.StreamHandler(sys.stdout)
    setattr(stream_h, "_structlog_owned", True)
    root.addHandler(stream_h)

    try:
        file_h = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        setattr(file_h, "_structlog_owned", True)
        root.addHandler(file_h)
    except Exception as e:  # pragma: no cover — depends on fs
        # File handler is best-effort; stdout always works.
        sys.stderr.write(f"[logging_config] file handler init failed: {e}\n")

    # Format stdlib log records via structlog's ProcessorFormatter so they
    # get the same JSON shape + correlation injection.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _inject_correlation_ctx,
        _add_service_metadata,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(serializer=_safe_json_dumps),
        ],
    )
    for h in root.handlers:
        h.setFormatter(formatter)

    # ---- structlog config ----
    structlog.configure(
        processors=shared_processors
        + [
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(lvl),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Tame uvicorn / fastapi noise: route their records through root.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "slowapi"):
        lg = logging.getLogger(noisy)
        # Don't add handlers; just let them propagate to root (where we
        # already installed our formatter). Reset their level so DEBUG
        # spam from optional libs doesn't sneak in.
        lg.handlers = []
        lg.propagate = True

    _configured = True
    return path


def _safe_json_dumps(obj: Any, **kwargs: Any) -> str:
    """JSON-dump fallback. Force a `default` serializer that handles datetime /
    Path / arbitrary objects without crashing. Never raises.

    structlog's JSONRenderer pre-injects its own `default=_json_fallback_handler`
    via dumps_kw; we override it here so our `str()` fallback wins (and to
    avoid the `multiple values for keyword argument 'default'` TypeError if we
    also tried to pass default= ourselves)."""
    kwargs["default"] = str
    kwargs.setdefault("ensure_ascii", False)
    try:
        return json.dumps(obj, **kwargs)
    except Exception:
        return json.dumps({"level": "error", "event": "log_serialize_failed",
                           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """Convenience accessor. Auto-configures on first call so import-order
    bugs don't leave logs unformatted."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name or "structural")


def current_log_file() -> Path:
    """Resolve the live log path the admin tail endpoint should read."""
    return _resolve_log_path()
