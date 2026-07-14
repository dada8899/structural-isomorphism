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
import math
import os
import re
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

# This historical name now stores only a framework-owned route template or
# ``unknown``. Raw request paths are never bound to a logging context.
REQUEST_PATH_VAR: ContextVar[Optional[str]] = ContextVar("request_path", default=None)
REQUEST_METHOD_VAR: ContextVar[Optional[str]] = ContextVar("request_method", default=None)
REQUEST_TIER_VAR: ContextVar[Optional[str]] = ContextVar("request_tier", default=None)


def new_request_id() -> str:
    """Generate a fresh correlation ID. UUID4 hex (32 chars, no dashes — easier
    to grep in logs and copy/paste in dashboards)."""
    return uuid.uuid4().hex


def new_incident_id() -> str:
    """Generate an opaque support handle unrelated to user content."""
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

_EVENT_RE = re.compile(
    r"^(?:http|auth|account_data|ask|analyze|billing|checkout|llm|retrieval|history|privacy|"
    r"waitlist|newsletter|sentry|startup|shutdown|log|structural|test)"
    r"\.[a-z0-9_.-]{1,95}$"
)
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/{}+-]{1,160}$")
_ERROR_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,95}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9_.:/+-]{1,120}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_INCIDENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_ROUTE_TEMPLATE_RE = re.compile(r"^(?:unknown|/[A-Za-z0-9_.~/{\}-]{0,159})$")
_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
_LEVELS = {"critical", "debug", "error", "exception", "info", "warning"}
_ENV_VALUES = {"dev", "development", "production", "staging", "test"}
_TIER_VALUES = {"anonymous", "free", "guest", "pro", "research", "unknown"}
_SAFE_NUMBER_FIELDS = {
    "candidate_count",
    "count",
    "elapsed_ms",
    "fused_count",
    "kb_count",
    "latency_ms",
    "remaining",
    "sent",
    "status_code",
    "total_recall",
}
_SAFE_BOOL_FIELDS = {
    "expansion_used",
    "provider_attempted",
    "retryable",
    "safe_path_enabled",
    "translation_used",
}


def _privacy_minimize_log_event(_, __, event_dict: dict) -> dict:
    """Rebuild a log event from a small operational allowlist.

    This deliberately discards formatted stdlib messages, exception objects,
    tracebacks and arbitrary ``extra`` fields. Call sites that need a durable
    signal must emit a constant dotted event name plus typed safe fields.
    """
    safe: dict[str, Any] = {}
    raw_event = event_dict.get("event")
    if isinstance(raw_event, str) and _EVENT_RE.fullmatch(raw_event):
        safe["event"] = raw_event
    else:
        safe["event"] = "log.message_redacted"

    request_id = event_dict.get("request_id")
    if isinstance(request_id, str) and _REQUEST_ID_RE.fullmatch(request_id):
        safe["request_id"] = request_id
    method = event_dict.get("method")
    if isinstance(method, str) and method in _METHODS:
        safe["method"] = method
    route = event_dict.get("route_template")
    if isinstance(route, str) and _ROUTE_TEMPLATE_RE.fullmatch(route):
        safe["route_template"] = route
    incident_id = event_dict.get("incident_id")
    if isinstance(incident_id, str) and _INCIDENT_ID_RE.fullmatch(incident_id):
        safe["incident_id"] = incident_id
    level = event_dict.get("level")
    if isinstance(level, str) and level.casefold() in _LEVELS:
        safe["level"] = level.casefold()
    timestamp = event_dict.get("timestamp")
    if isinstance(timestamp, str) and len(timestamp) <= 40 and _TOKEN_RE.fullmatch(timestamp):
        safe["timestamp"] = timestamp

    safe["service"] = "structural-backend"
    env = event_dict.get("env")
    if isinstance(env, str) and env in _ENV_VALUES:
        safe["env"] = env
    error_type = event_dict.get("error_type")
    if isinstance(error_type, str) and _ERROR_TYPE_RE.fullmatch(error_type):
        safe["error_type"] = error_type
    model = event_dict.get("model")
    if isinstance(model, str) and _MODEL_RE.fullmatch(model):
        safe["model"] = model
    tier = event_dict.get("tier")
    if isinstance(tier, str) and tier in _TIER_VALUES:
        safe["tier"] = tier
    for field in _SAFE_NUMBER_FIELDS:
        value = event_dict.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, int) or math.isfinite(value):
                safe[field] = value
    for field in _SAFE_BOOL_FIELDS:
        value = event_dict.get(field)
        if isinstance(value, bool):
            safe[field] = value

    # ProcessorFormatter requires these private transport keys until its final
    # remove_processors_meta stage. They are never rendered.
    for field in ("_record", "_from_structlog"):
        if field in event_dict:
            safe[field] = event_dict[field]
    return safe


def _inject_correlation_ctx(_, __, event_dict: dict) -> dict:
    """Pull request-scoped contextvars onto every log line.

    `merge_contextvars` already handles bound_logger context — this processor
    additionally pulls the *module-level* ContextVars we set in middleware
    (which are not part of structlog's context dict).
    """
    rid = REQUEST_ID_VAR.get()
    if rid and rid != "-":
        event_dict.setdefault("request_id", rid)
    route_template = REQUEST_PATH_VAR.get()
    if route_template is not None:
        event_dict.setdefault("route_template", route_template)
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
    event_dict["service"] = "structural-backend"
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
        sys.stderr.write(
            "[logging_config] file_handler_init_failed "
            f"error_type={type(e).__name__}\n"
        )

    # Format stdlib log records via structlog's ProcessorFormatter so they
    # get the same JSON shape + correlation injection.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _inject_correlation_ctx,
        _add_service_metadata,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _privacy_minimize_log_event,
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
    kwargs.pop("default", None)
    kwargs.setdefault("ensure_ascii", False)
    try:
        return json.dumps(obj, **kwargs)
    except Exception:
        return json.dumps({"level": "error", "event": "log.serialize_failed",
                           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "service": "structural-backend"})


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """Convenience accessor. Auto-configures on first call so import-order
    bugs don't leave logs unformatted."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name or "structural")


def current_log_file() -> Path:
    """Resolve the live log path the admin tail endpoint should read."""
    return _resolve_log_path()
