"""
POST /api/checkout/mock — Stripe Checkout *mock* endpoint (W10-B, session #10).

This is **not** live Stripe. It simulates the surface area we'll eventually
plug into (customer/session ids, decline 10% of the time, persist to jsonl).
The point is to:

  1. Let the pricing page render a realistic Stripe-style flow today, so we
     can wire / measure / test the funnel BEFORE PMF justifies a real Stripe
     integration.
  2. Build a "would-have-paid" waitlist (mock_checkouts.jsonl) we can convert
     when we flip the switch on real Stripe (Q3 2026 target).
  3. Validate that the /api/usage gate (tier → ticker_limit) actually shapes
     user behaviour vs. always-free.

When real Stripe arrives:
  - Replace this endpoint with stripe.checkout.Session.create()
  - Webhook receiver lives at /api/stripe/webhook (separate file)
  - mock_checkouts.jsonl gets migrated to a `customers` SQLite table
  - The frontend /checkout/mock page is replaced by a redirect to checkout.stripe.com

Body (JSON):
    {
      "tier":      "pro" | "team",
      "interval":  "month" | "year",
      "email":     "user@example.com",
      "name":      "Jane Doe",
      "card_last4": "4242"   # informational only — NEVER a real card
    }

Response:
    200  {
          "status":              "success",
          "customer_id":         "mock_cus_xxxxxxxx",
          "checkout_session_id": "mock_cs_xxxxxxxx",
          "tier":                "pro",
          "interval":            "month",
          "amount_usd":          19,
         }
    200  {  # decline (~10% of requests, simulating real-world failure rate)
          "status":  "declined",
          "reason":  "card_declined",
         }
    400  { "error": "invalid tier" | "invalid interval" | "invalid email" | ... }
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["checkout-mock"])
logger = logging.getLogger("structural.checkout_mock")
# W14-D: structlog adapter — `slog` emits queryable key=value fields
# alongside the legacy stdlib `logger` calls (kept for log-message stability).
try:  # pragma: no cover — import guard for early-load test envs
    from logging_config import get_logger as _glog

    slog = _glog("structural.checkout_mock")
except Exception:  # pragma: no cover
    slog = None

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Tier pricing in USD. Annual = 10x monthly (2 months free). Authoritative source —
# duplicated in web/phase-detector/lib/pricing.ts for frontend, but BE wins on
# the actual receipt amount.
_TIER_PRICING = {
    "pro": {"month": 19, "year": 190},
    "team": {"month": 99, "year": 990},
}

# Simulate ~10% decline rate (Stripe's actual production rate hovers 7-12% on
# B2B SaaS; we pick 10% so the e2e suite can hit both branches deterministically
# via the override below).
_DECLINE_RATE = 0.10

_MAX_NAME_LEN = 100
_MAX_EMAIL_LEN = 200


def _data_file() -> Path:
    """Mock-checkout persistence. JSONL append-only — same shape we'd ingest
    from real Stripe webhooks later."""
    return Path(__file__).parent.parent / "data" / "mock_checkouts.jsonl"


class CheckoutBody(BaseModel):
    tier: str
    interval: str = "month"
    email: str
    name: Optional[str] = ""
    card_last4: Optional[str] = ""
    # Test-only override — lets e2e tests force a deterministic branch
    # without 10x retries to hit the decline path. NEVER honoured if
    # request comes from a non-localhost IP.
    force_status: Optional[str] = None


@router.post("/checkout/mock")
async def checkout_mock(body: CheckoutBody, request: Request):
    """Simulate a Stripe Checkout call.

    Returns success ~90% of the time, decline ~10%. Decline is a *valid*
    business response (200, not 4xx) — the frontend distinguishes via the
    `status` field, mirroring how Stripe surfaces card_declined.
    """
    tier = (body.tier or "").strip().lower()
    interval = (body.interval or "month").strip().lower()
    email = (body.email or "").strip().lower()
    name = (body.name or "").strip()[:_MAX_NAME_LEN]
    card_last4 = re.sub(r"\D", "", (body.card_last4 or ""))[:4]

    # --- Validation ---
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
    if not email or len(email) > _MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        return JSONResponse({"error": "invalid email"}, status_code=400)

    amount = _TIER_PRICING[tier][interval]

    # --- Force-status override (localhost only, e2e support) ---
    force = (body.force_status or "").strip().lower()
    client_host = request.client.host if request.client else ""
    is_local = client_host in ("127.0.0.1", "localhost", "::1", "testclient", "")
    if force in ("success", "declined") and is_local:
        status = force
    else:
        # Real decision: probabilistic decline
        status = "declined" if random.random() < _DECLINE_RATE else "success"

    if status == "declined":
        logger.info(
            "checkout_mock declined: email=%s tier=%s interval=%s",
            email, tier, interval,
        )
        if slog is not None:
            slog.info(
                "checkout.declined",
                tier=tier, interval=interval, amount_usd=amount,
            )
        # Persist the decline too — useful funnel signal.
        _persist({
            "status": "declined",
            "tier": tier,
            "interval": interval,
            "email": email,
            "name": name,
            "card_last4": card_last4,
            "amount_usd": amount,
            "reason": "card_declined",
        }, request)
        return JSONResponse({
            "status": "declined",
            "reason": "card_declined",
        })

    # Success path
    customer_id = "mock_cus_" + uuid.uuid4().hex[:16]
    session_id = "mock_cs_" + uuid.uuid4().hex[:16]

    _persist({
        "status": "success",
        "tier": tier,
        "interval": interval,
        "email": email,
        "name": name,
        "card_last4": card_last4,
        "amount_usd": amount,
        "customer_id": customer_id,
        "checkout_session_id": session_id,
    }, request)

    logger.info(
        "checkout_mock success: email=%s tier=%s interval=%s cust=%s",
        email, tier, interval, customer_id,
    )
    if slog is not None:
        slog.info(
            "checkout.success",
            tier=tier, interval=interval, amount_usd=amount,
            customer_id=customer_id,
        )
    return JSONResponse({
        "status": "success",
        "customer_id": customer_id,
        "checkout_session_id": session_id,
        "tier": tier,
        "interval": interval,
        "amount_usd": amount,
    })


def _persist(payload: dict, request: Request) -> None:
    """Append the would-have-paid record to mock_checkouts.jsonl.

    Storage failure logs a warning but is non-fatal — the user-visible flow
    must still complete (otherwise they hit "checkout broken" when it's
    really just disk-full).
    """
    f = _data_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        entry = dict(payload)
        entry["ts"] = int(time.time())
        entry["iso"] = time.strftime("%Y-%m-%d %H:%M:%S")
        entry["ip"] = request.client.host if request.client else "?"
        entry["ua"] = (request.headers.get("user-agent") or "")[:200]
        entry["referrer"] = (request.headers.get("referer") or "")[:300]
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("checkout_mock persist failed: %s", e)


# -------- /api/usage --------
# Lightweight tier-and-quota probe used by the frontend to gate Pro features
# (paywall modal on tickers 101+). NOT auth-protected — the mock returns
# whichever tier the caller asserts via cookie/header, defaulting to free.
# In production this would hit the real user DB + counters.

_TIER_LIMITS = {
    "free": {"ticker_limit": 100, "api_quota_today": 50},
    "pro": {"ticker_limit": 1000, "api_quota_today": 5000},
    "team": {"ticker_limit": 5000, "api_quota_today": 100000},
}


@router.get("/usage")
async def usage(request: Request):
    """Return current tier + ticker_limit + today's API usage.

    Tier resolution (mock, in priority order):
      1. `?tier=` query param (only for local dev / e2e — ignored from real IPs)
      2. `x-mock-tier` request header
      3. `mock_tier` cookie (set by the success flow on /checkout/mock)
      4. Default: free

    Once real Stripe is in: tier comes from `stripe_customers` table via the
    authenticated user's email. The shape of this response stays the same so
    the frontend doesn't need to change.
    """
    tier = "free"
    client_host = request.client.host if request.client else ""
    is_local = client_host in ("127.0.0.1", "localhost", "::1", "testclient", "")

    q_tier = (request.query_params.get("tier") or "").strip().lower()
    if q_tier in _TIER_LIMITS and is_local:
        tier = q_tier
    else:
        h_tier = (request.headers.get("x-mock-tier") or "").strip().lower()
        if h_tier in _TIER_LIMITS:
            tier = h_tier
        else:
            c_tier = (request.cookies.get("mock_tier") or "").strip().lower()
            if c_tier in _TIER_LIMITS:
                tier = c_tier

    limits = _TIER_LIMITS[tier]
    # api_calls_today is mocked as 0 here — real impl pulls from a counter
    # store (redis / sqlite). Frontend uses this to render usage bars later.
    return JSONResponse({
        "tier": tier,
        "ticker_limit": limits["ticker_limit"],
        "api_calls_today": 0,
        "api_quota_today": limits["api_quota_today"],
    })
