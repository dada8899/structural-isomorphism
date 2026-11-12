"""
Stripe billing API — W7-D mini-brief 2 (2026-05-24).

Why this exists alongside `api/checkout_mock.py`:
    `checkout_mock.py` is a self-contained simulator (random success/decline,
    no Stripe SDK). It served the M10-B "would-have-paid waitlist" use case.

    `billing.py` is the real Stripe integration behind an explicit
    `BILLING_ENABLED` gate. Checkout fails closed unless billing is enabled
    and the matching Stripe credentials are configured. Public mock checkout
    is kept separate and is never presented as a successful payment.

    Migration path: once we want to flip to live Stripe, simply set
    `STRIPE_SECRET_KEY` (no _TEST_) and bump `STRIPE_MODE=live`. The webhook
    path is already split out so we can sign-verify before going live.

Endpoints:
    POST /api/billing/checkout-session
        Body: { tier: "pro"|"team", interval: "month"|"year", email: str }
        → 200 { url: "<checkout url>", session_id: "...", mode: "stripe" }

    POST /api/billing/webhook
        Stripe webhook events verified with Stripe's timestamped HMAC header.
        Stores into the `billing_events` table; subsequent reconciliation
        runs read from it.

    GET /api/billing/events/recent (debug)
        Returns the last 20 webhook events; used by ops dashboards and tests.

Storage: SQLite — `data/billing.db`, table `billing_events`:
    id INTEGER PK
    event_id   TEXT UNIQUE     -- stripe evt_xxx OR mock id
    event_type TEXT            -- checkout.session.completed, etc
    payload    TEXT (JSON)
    received_at TEXT
    verified   INTEGER (0/1)   -- 1 if HMAC matched; 0 for mock
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

router = APIRouter(tags=["billing"])
logger = get_logger("structural.billing")

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Tier pricing — authoritative source. Frontend pricing.html duplicates the
# numbers for display, but the receipt amount comes from here.
_TIER_PRICING = {
    "pro":  {"month": 1900, "year": 19000},   # cents
    "team": {"month": 9900, "year": 99000},
}

# Display strings (kept here so frontend can fetch via a future GET endpoint
# rather than hardcode). USD only for v0.1.
_TIER_DISPLAY = {
    "pro":  {"name": "Pro",  "month_usd": 19,  "year_usd": 190},
    "team": {"name": "Team", "month_usd": 99,  "year_usd": 990},
}


def _data_file() -> Path:
    return Path(__file__).parent.parent / "data" / "billing.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS billing_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT UNIQUE NOT NULL,
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    received_at TEXT NOT NULL,
    verified    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_billing_received
    ON billing_events(received_at DESC);
"""


def _connect() -> sqlite3.Connection:
    f = _data_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(f), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:  # pragma: no cover
        pass
    conn.executescript(_SCHEMA)
    return conn


# --------------------- Stripe SDK lazy import ---------------------

def _stripe_module():
    """Lazy import — if `stripe` SDK isn't installed (e.g. minimal dev env),
    we fall through to mock mode. Tests can monkeypatch this to inject a
    fake module.
    """
    try:
        import stripe  # type: ignore
        return stripe
    except Exception:  # pragma: no cover — import guard
        return None


def _stripe_test_key() -> Optional[str]:
    """Read the env each call so tests can monkeypatch os.environ."""
    return os.environ.get("STRIPE_TEST_SECRET_KEY")


def _webhook_secret() -> Optional[str]:
    return os.environ.get("STRIPE_WEBHOOK_SECRET")


def _billing_enabled() -> bool:
    """Paid billing is opt-in; credentials alone must never activate it."""
    return os.environ.get("BILLING_ENABLED", "").strip().lower() == "true"


def _mode() -> str:
    """Resolve current mode: 'stripe' iff key is set AND SDK importable,
    else 'mock'."""
    if _stripe_test_key() and _stripe_module() is not None:
        return "stripe"
    return "mock"


# --------------------- Checkout session ---------------------

class CheckoutBody(BaseModel):
    tier: str
    interval: str = "month"
    email: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@router.post("/billing/checkout-session")
async def checkout_session(body: CheckoutBody, request: Request):
    tier = (body.tier or "").strip().lower()
    interval = (body.interval or "month").strip().lower()
    email = (body.email or "").strip().lower()

    # --- Validation (mirrors checkout_mock semantics) ---
    if tier not in _TIER_PRICING:
        return JSONResponse(
            {"error": "invalid tier", "allowed": list(_TIER_PRICING.keys())},
            status_code=400,
        )
    if interval not in ("month", "year"):
        return JSONResponse(
            {"error": "invalid interval", "allowed": ["month", "year"]},
            status_code=400,
        )
    if not email or len(email) > 200 or not _EMAIL_RE.match(email):
        return JSONResponse({"error": "invalid email"}, status_code=400)

    if not _billing_enabled():
        return JSONResponse({
            "mode": "unavailable",
            "error": "billing_not_available",
            "message": "Paid plans are not open yet. Join the research preview instead.",
        }, status_code=503)

    amount_cents = _TIER_PRICING[tier][interval]
    success_url = (body.success_url or "/pricing.html?status=success").strip()
    cancel_url = (body.cancel_url or "/pricing.html?status=cancel").strip()

    mode = _mode()

    if mode == "stripe":
        stripe = _stripe_module()
        stripe.api_key = _stripe_test_key()
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                payment_method_types=["card"],
                customer_email=email,
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"Structural {_TIER_DISPLAY[tier]['name']} ({interval}ly)",
                        },
                        "unit_amount": amount_cents,
                        "recurring": {"interval": interval},
                    },
                    "quantity": 1,
                }],
                success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
                metadata={"tier": tier, "interval": interval},
            )
            logger.info("billing.checkout_session_created", tier=tier)
            return JSONResponse({
                "mode": "stripe",
                "session_id": session.get("id"),
                "url": session.get("url"),
                "amount_cents": amount_cents,
            })
        except Exception as exc:
            incident_id = new_incident_id()
            logger.error(
                "billing.checkout_session_failed",
                error_type=type(exc).__name__,
                incident_id=incident_id,
            )
            return JSONResponse(
                {
                    "error": "stripe_error",
                    "detail": "Payment provider unavailable.",
                    "incident_id": incident_id,
                },
                status_code=502,
            )

    # Fail closed: a simulated checkout must never look like a successful
    # subscription on a public product. Keep mock billing in the dedicated
    # checkout_mock test surface; this endpoint represents real billing only.
    logger.warning("billing.unavailable")
    return JSONResponse({
        "mode": "unavailable",
        "error": "billing_not_available",
        "message": "Paid plans are not open yet. Join the research preview instead.",
    }, status_code=503)


# --------------------- Webhook ---------------------

def _verify_signature(
    payload_bytes: bytes,
    sig_header: str,
    secret: str,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> bool:
    """Verify a Stripe v1 webhook signature with replay protection.

    Stripe signs ``<timestamp>.<raw_payload>`` and may include multiple v1
    signatures during secret rotation. Requests outside the tolerance window
    are rejected even when their HMAC is otherwise valid.
    """
    if not sig_header or not secret:
        return False
    timestamp: int | None = None
    signatures: list[str] = []
    for part in sig_header.split(","):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        if name.strip() == "t":
            try:
                timestamp = int(value.strip())
            except ValueError:
                return False
        elif name.strip() == "v1" and value.strip():
            signatures.append(value.strip())
    if timestamp is None or not signatures:
        return False
    current = int(time.time()) if now is None else int(now)
    if abs(current - timestamp) > tolerance_seconds:
        return False
    signed_payload = str(timestamp).encode("ascii") + b"." + payload_bytes
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(signature, expected) for signature in signatures)


@router.post("/billing/webhook")
async def webhook(request: Request):
    """Receive a Stripe webhook event (or a mocked one in dev/CI).

    Signature verification:
      - If STRIPE_WEBHOOK_SECRET is set, we HMAC-verify the raw body against
        `Stripe-Signature`. On mismatch → 400 (reject).
      - If unset, we accept the event but mark verified=0. This is the
        intended dev/CI path; PROD must set the secret.
    """
    if not _billing_enabled():
        return JSONResponse({"error": "billing_not_available"}, status_code=503)
    raw = await request.body()
    sig = request.headers.get("stripe-signature") or ""
    secret = _webhook_secret()

    if not secret:
        logger.error("billing.webhook_configuration_invalid", incident_id=new_incident_id())
        return JSONResponse({"error": "webhook_not_configured"}, status_code=503)
    verified = 0
    if _verify_signature(raw, sig, secret):
        verified = 1
    else:
        logger.warning("billing.webhook_signature_rejected")
        return JSONResponse(
            {"error": "signature_mismatch"}, status_code=400
        )

    try:
        evt = json.loads(raw.decode("utf-8") or "{}")
    except Exception as exc:
        logger.warning(
            "billing.webhook_payload_rejected",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    event_id = evt.get("id") or ("mock_evt_" + uuid.uuid4().hex[:16])
    event_type = evt.get("type") or "unknown"
    received_at = _dt.datetime.now(_dt.timezone.utc).isoformat(
        sep=" ", timespec="seconds"
    )

    try:
        with closing(_connect()) as conn, conn:
            try:
                conn.execute(
                    "INSERT INTO billing_events "
                    "(event_id, event_type, payload, received_at, verified) "
                    "VALUES (?,?,?,?,?)",
                    (event_id, event_type, json.dumps(evt), received_at, verified),
                )
                conn.commit()
                logger.info("billing.webhook_stored")
                return JSONResponse({
                    "ok": True, "event_id": event_id,
                    "event_type": event_type, "verified": bool(verified),
                })
            except sqlite3.IntegrityError:
                # Duplicate event_id — Stripe retries are normal; ack 200.
                logger.info("billing.webhook_duplicate")
                return JSONResponse({
                    "ok": True, "event_id": event_id,
                    "event_type": event_type, "duplicate": True,
                })
    except sqlite3.Error as exc:
        logger.error(
            "billing.webhook_storage_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return JSONResponse(
            {"error": "storage_failure"}, status_code=500
        )


@router.get("/billing/events/recent")
async def events_recent(request: Request, limit: int = 20):
    """Return the most-recent webhook events (debug / ops)."""
    if not _billing_enabled():
        return JSONResponse({"error": "billing_not_available"}, status_code=503)
    admin_token = os.environ.get("STRUCTURAL_ADMIN_TOKEN", "")
    provided = request.headers.get("x-admin-token", "")
    if not admin_token or not hmac.compare_digest(provided, admin_token):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        with closing(_connect()) as conn, conn:
            rows = conn.execute(
                "SELECT id, event_id, event_type, received_at, verified "
                "FROM billing_events ORDER BY received_at DESC, id DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
            return JSONResponse({
                "count": len(rows),
                "events": [dict(r) for r in rows],
            })
    except sqlite3.Error as exc:  # pragma: no cover
        logger.error(
            "billing.events_recent_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return JSONResponse({"count": 0, "events": []})
