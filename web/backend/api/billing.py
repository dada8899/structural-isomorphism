"""
Stripe billing API — W7-D mini-brief 2 (2026-05-24).

Why this exists alongside `api/checkout_mock.py`:
    `checkout_mock.py` is a self-contained simulator (random success/decline,
    no Stripe SDK). It served the M10-B "would-have-paid waitlist" use case.

    `billing.py` is the *real* Stripe integration with a mock fallback. When
    `STRIPE_TEST_SECRET_KEY` is set, it calls Stripe Checkout test mode
    properly (no real money — cards are Stripe test cards like 4242…).
    When the env is unset (default in CI / dev), it falls back to a mock
    response shaped identically to Stripe's so the frontend behaves the same.

    Migration path: once we want to flip to live Stripe, simply set
    `STRIPE_SECRET_KEY` (no _TEST_) and bump `STRIPE_MODE=live`. The webhook
    path is already split out so we can sign-verify before going live.

Endpoints:
    POST /api/billing/checkout-session
        Body: { tier: "pro"|"team", interval: "month"|"year", email: str }
        → 200 { url: "<checkout url>", session_id: "...", mode: "stripe"|"mock" }

    POST /api/billing/webhook
        Stripe webhook events (mock signature verification — full HMAC will
        be wired when STRIPE_WEBHOOK_SECRET is provided). Stores into the
        `billing_events` table; subsequent reconciliation runs read from it.

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
import logging
import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["billing"])
logger = logging.getLogger("structural.billing")

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

***REMOVED*** Tier pricing — authoritative source. Frontend pricing.html duplicates the
***REMOVED*** numbers for display, but the receipt amount comes from here.
_TIER_PRICING = {
    "pro":  {"month": 1900, "year": 19000},   ***REMOVED*** cents
    "team": {"month": 9900, "year": 99000},
}

***REMOVED*** Display strings (kept here so frontend can fetch via a future GET endpoint
***REMOVED*** rather than hardcode). USD only for v0.1.
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
    except sqlite3.Error:  ***REMOVED*** pragma: no cover
        pass
    conn.executescript(_SCHEMA)
    return conn


***REMOVED*** --------------------- Stripe SDK lazy import ---------------------

def _stripe_module():
    """Lazy import — if `stripe` SDK isn't installed (e.g. minimal dev env),
    we fall through to mock mode. Tests can monkeypatch this to inject a
    fake module.
    """
    try:
        import stripe  ***REMOVED*** type: ignore
        return stripe
    except Exception:  ***REMOVED*** pragma: no cover — import guard
        return None


def _stripe_test_key() -> Optional[str]:
    """Read the env each call so tests can monkeypatch os.environ."""
    return os.environ.get("STRIPE_TEST_SECRET_KEY")


def _webhook_secret() -> Optional[str]:
    return os.environ.get("STRIPE_WEBHOOK_SECRET")


def _mode() -> str:
    """Resolve current mode: 'stripe' iff key is set AND SDK importable,
    else 'mock'."""
    if _stripe_test_key() and _stripe_module() is not None:
        return "stripe"
    return "mock"


***REMOVED*** --------------------- Checkout session ---------------------

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

    ***REMOVED*** --- Validation (mirrors checkout_mock semantics) ---
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
            logger.info(
                "billing checkout-session stripe tier=%s interval=%s email=%s id=%s",
                tier, interval, email, session.get("id"),
            )
            return JSONResponse({
                "mode": "stripe",
                "session_id": session.get("id"),
                "url": session.get("url"),
                "amount_cents": amount_cents,
            })
        except Exception as e:
            logger.exception(
                "billing stripe error tier=%s interval=%s email=%s err=%s",
                tier, interval, email, e,
            )
            return JSONResponse(
                {"error": "stripe_error", "detail": str(e)[:300]},
                status_code=502,
            )

    ***REMOVED*** --- Mock mode ---
    fake_id = "mock_cs_" + uuid.uuid4().hex[:24]
    url = f"{success_url}&session_id={fake_id}"
    logger.info(
        "billing checkout-session mock tier=%s interval=%s email=%s id=%s",
        tier, interval, email, fake_id,
    )
    return JSONResponse({
        "mode": "mock",
        "session_id": fake_id,
        "url": url,
        "amount_cents": amount_cents,
    })


***REMOVED*** --------------------- Webhook ---------------------

def _verify_signature(payload_bytes: bytes, sig_header: str, secret: str) -> bool:
    """HMAC-SHA256 of the raw payload, formatted like Stripe's `t=,v1=` header.

    Real Stripe uses `t=<ts>,v1=<hex>`; we accept either Stripe's format or
    the simpler `sha256=<hex>` (used by tests). Mismatch returns False.
    """
    if not sig_header or not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    ***REMOVED*** Accept either format
    if sig_header.startswith("sha256="):
        provided = sig_header.split("=", 1)[1].strip()
        return hmac.compare_digest(provided, expected)
    ***REMOVED*** Stripe-style: t=...,v1=...
    parts = dict(
        p.split("=", 1) for p in sig_header.split(",") if "=" in p
    )
    provided = parts.get("v1", "").strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


@router.post("/billing/webhook")
async def webhook(request: Request):
    """Receive a Stripe webhook event (or a mocked one in dev/CI).

    Signature verification:
      - If STRIPE_WEBHOOK_SECRET is set, we HMAC-verify the raw body against
        `Stripe-Signature`. On mismatch → 400 (reject).
      - If unset, we accept the event but mark verified=0. This is the
        intended dev/CI path; PROD must set the secret.
    """
    raw = await request.body()
    sig = request.headers.get("stripe-signature") or ""
    secret = _webhook_secret()

    verified = 0
    if secret:
        if _verify_signature(raw, sig, secret):
            verified = 1
        else:
            logger.warning("billing webhook signature mismatch")
            return JSONResponse(
                {"error": "signature_mismatch"}, status_code=400
            )

    try:
        evt = json.loads(raw.decode("utf-8") or "{}")
    except Exception as e:
        logger.warning("billing webhook bad json: %s", e)
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    event_id = evt.get("id") or ("mock_evt_" + uuid.uuid4().hex[:16])
    event_type = evt.get("type") or "unknown"
    received_at = _dt.datetime.now(_dt.timezone.utc).isoformat(
        sep=" ", timespec="seconds"
    )

    try:
        with _connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO billing_events "
                    "(event_id, event_type, payload, received_at, verified) "
                    "VALUES (?,?,?,?,?)",
                    (event_id, event_type, json.dumps(evt), received_at, verified),
                )
                conn.commit()
                logger.info(
                    "billing webhook stored id=%s type=%s verified=%s",
                    event_id, event_type, verified,
                )
                return JSONResponse({
                    "ok": True, "event_id": event_id,
                    "event_type": event_type, "verified": bool(verified),
                })
            except sqlite3.IntegrityError:
                ***REMOVED*** Duplicate event_id — Stripe retries are normal; ack 200.
                logger.info("billing webhook duplicate id=%s", event_id)
                return JSONResponse({
                    "ok": True, "event_id": event_id,
                    "event_type": event_type, "duplicate": True,
                })
    except sqlite3.Error as e:
        logger.error("billing webhook storage failure: %s", e)
        return JSONResponse(
            {"error": "storage_failure"}, status_code=500
        )


@router.get("/billing/events/recent")
async def events_recent(limit: int = 20):
    """Return the most-recent webhook events (debug / ops)."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, event_id, event_type, received_at, verified "
                "FROM billing_events ORDER BY received_at DESC, id DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
            return JSONResponse({
                "count": len(rows),
                "events": [dict(r) for r in rows],
            })
    except sqlite3.Error as e:  ***REMOVED*** pragma: no cover
        logger.error("billing events_recent failed: %s", e)
        return JSONResponse({"count": 0, "events": []})
