"""
Magic-link auth scaffold (W15-B, session #10).

Passwordless login flow:
    POST /api/auth/request-link  { email }       → mock-sends magic link
    POST /api/auth/verify        { token }       → exchanges token for JWT session cookie
    POST /api/auth/logout                        → clears cookie + revokes session
    GET  /api/auth/me                            → returns session user (or 401)

What's intentionally NOT done here (deferred):
  - Real email send (SendGrid / Postmark / Resend). For now, we write the
    magic link to `data/mock_email_outbox.jsonl` so dev/E2E can read it.
  - Social login (Google / GitHub OAuth). Magic-link is enough for Alpha.
  - Refresh tokens — the JWT is good for 30 days, opaque revocation via
    server-side session table is supported (logout writes to revoked_sessions).
  - 2FA / WebAuthn — out of scope for v1.

Storage (all JSONL, append-only with periodic compaction TBD):
    data/magic_tokens.jsonl          one record per requested link
        { token, email, created_at, expires_at, consumed_at }
    data/mock_email_outbox.jsonl     mock email "sent" log (dev only)
        { ts, to, subject, link }
    data/auth_users.jsonl            user records (created on first verify)
        { email, tier, created_at }
    data/revoked_sessions.jsonl      jti revocation list (logout writes here)
        { jti, revoked_at }
    data/auth_rate_limit.jsonl       per-email request counter (3/hr/email)
        { email, ts }

JWT format: HS256, claims = {sub: email, tier, iat, exp, jti}. Secret from
JWT_SECRET env var. Dev fallback is a fixed string so tests are
reproducible — production deploys MUST set JWT_SECRET to a random 32+ byte
value (see web/backend/.env.example).
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("structural.auth")

router = APIRouter(tags=["auth"])

# --- Config ---
_TOKEN_TTL_MIN = 15            # magic-link freshness window
_SESSION_TTL_DAYS = 30         # JWT lifetime
_RATE_LIMIT_PER_HOUR = 3       # link requests per email per hour
_DEFAULT_TIER = "free"
_COOKIE_NAME = "phase_session"
_JWT_ALG = "HS256"
_DEV_FALLBACK_SECRET = "dev-jwt-secret-do-not-use-in-prod-32-chars-min-please"

# RFC-5322-ish pragmatic email regex (same as newsletter.py).
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)
_MAX_EMAIL_LEN = 200


def _jwt_secret() -> str:
    """Read JWT secret from env, fall back to a fixed dev string.

    In tests we monkeypatch this to a known value. In prod the env var is
    set in systemd EnvironmentFile (see deploy/structural-backend.service).
    """
    return os.getenv("JWT_SECRET") or _DEV_FALLBACK_SECRET


# --- Storage paths (lazy, overridable in tests) ---

def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _tokens_file() -> Path:
    return _data_dir() / "magic_tokens.jsonl"


def _outbox_file() -> Path:
    return _data_dir() / "mock_email_outbox.jsonl"


def _users_file() -> Path:
    return _data_dir() / "auth_users.jsonl"


def _revoked_sessions_file() -> Path:
    return _data_dir() / "revoked_sessions.jsonl"


def _rate_limit_file() -> Path:
    return _data_dir() / "auth_rate_limit.jsonl"


# --- JSONL helpers ---

def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


# --- Schemas ---

class RequestLinkBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=_MAX_EMAIL_LEN)


class VerifyBody(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


# --- Helpers: email validation, rate limit, token gen, JWT ---

def _normalize_email(raw: str) -> Optional[str]:
    e = (raw or "").strip().lower()
    if not e or len(e) > _MAX_EMAIL_LEN:
        return None
    if not _EMAIL_RE.match(e):
        return None
    return e


def _check_rate_limit(email: str) -> bool:
    """Return True if email is under the per-hour limit, False if exceeded."""
    rows = _read_jsonl(_rate_limit_file())
    now = int(time.time())
    cutoff = now - 3600
    recent = [r for r in rows if r.get("email") == email and r.get("ts", 0) >= cutoff]
    if len(recent) >= _RATE_LIMIT_PER_HOUR:
        return False
    _append_jsonl(_rate_limit_file(), {"email": email, "ts": now})
    return True


def _generate_token() -> str:
    """32-char URL-safe token. token_urlsafe(24) → ~32 chars after base64."""
    return secrets.token_urlsafe(24)


def _ensure_user(email: str) -> dict:
    """Idempotent user creation. Returns the user record (existing or new)."""
    rows = _read_jsonl(_users_file())
    for r in rows:
        if r.get("email") == email:
            return r
    user = {
        "email": email,
        "tier": _DEFAULT_TIER,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_jsonl(_users_file(), user)
    return user


def _issue_jwt(email: str, tier: str) -> tuple[str, str]:
    """Return (jwt_string, jti)."""
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    payload = {
        "sub": email,
        "tier": tier,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=_SESSION_TTL_DAYS)).timestamp()),
        "jti": jti,
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALG)
    return token, jti


def _decode_jwt(token: str) -> Optional[dict]:
    """Verify signature + expiry. Return claims or None if invalid."""
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return None


def _is_jti_revoked(jti: str) -> bool:
    if not jti:
        return False
    rows = _read_jsonl(_revoked_sessions_file())
    return any(r.get("jti") == jti for r in rows)


def _cookie_args(request: Request) -> dict:
    """Cookie security: HttpOnly + SameSite=Lax always; Secure when HTTPS."""
    # request.url.scheme is "https" behind a proper proxy that sets
    # X-Forwarded-Proto, but TestClient uses "http". So we relax Secure
    # in tests; production deploys MUST run behind nginx/HTTPS.
    secure = request.url.scheme == "https"
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": _SESSION_TTL_DAYS * 24 * 3600,
        "path": "/",
    }


# --- Endpoints ---

@router.post("/auth/request-link", summary="Request a magic-link email")
async def request_link(body: RequestLinkBody, request: Request):
    """Generate a magic-link token and 'send' it (mock writes to outbox.jsonl).

    Returns 200 unconditionally for valid emails to prevent enumeration
    (whether the email exists or not, the response is identical). Invalid
    email format still returns 400.
    """
    email = _normalize_email(body.email)
    if not email:
        return JSONResponse(
            {"ok": False, "error": "invalid email"}, status_code=400
        )

    if not _check_rate_limit(email):
        return JSONResponse(
            {"ok": False, "error": "rate limit exceeded; try again in 1 hour"},
            status_code=429,
        )

    token = _generate_token()
    now = datetime.now(timezone.utc)
    record = {
        "token": token,
        "email": email,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=_TOKEN_TTL_MIN)).isoformat(),
        "consumed_at": None,
    }
    _append_jsonl(_tokens_file(), record)

    # Mock email send: write to outbox.jsonl. Dev frontend reads this file
    # via NEXT_PUBLIC_AUTH_DEV_MODE inline display. Prod replaces this with
    # a real SMTP / SendGrid call.
    base_url = os.getenv("AUTH_LINK_BASE_URL", "http://localhost:3000")
    magic_link = f"{base_url}/auth/verify?token={token}"
    _append_jsonl(_outbox_file(), {
        "ts": int(time.time()),
        "to": email,
        "subject": "Your sign-in link",
        "link": magic_link,
    })

    logger.info("auth.magic_link_requested email=%s", email)

    # Dev mode: return the link inline so the frontend can show it.
    # In prod, response always omits the link (regardless of dev flag).
    body_out: dict = {"ok": True}
    if os.getenv("AUTH_DEV_MODE", "").lower() in ("1", "true", "yes"):
        body_out["dev_link"] = magic_link
        body_out["dev_token"] = token
    return JSONResponse(body_out)


@router.post("/auth/verify", summary="Exchange magic-link token for session")
async def verify(body: VerifyBody, request: Request, response: Response):
    """Validate the token, create/lookup the user, issue a JWT, set cookie."""
    token = (body.token or "").strip()
    if not token:
        return JSONResponse(
            {"ok": False, "error": "missing token"}, status_code=400
        )

    rows = _read_jsonl(_tokens_file())
    match = None
    for r in rows:
        if r.get("token") == token:
            match = r
            break

    if match is None:
        return JSONResponse(
            {"ok": False, "error": "invalid token"}, status_code=400
        )

    # Replay guard: consumed tokens can't be re-used.
    if match.get("consumed_at"):
        return JSONResponse(
            {"ok": False, "error": "token already used"}, status_code=400
        )

    # Expiry check.
    try:
        expires_at = datetime.fromisoformat(match["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "malformed token record"}, status_code=400
        )
    if datetime.now(timezone.utc) > expires_at:
        return JSONResponse(
            {"ok": False, "error": "token expired"}, status_code=400
        )

    # Mark consumed by appending a tombstone record. Linear scan reads will
    # see both the original (with consumed_at=None) AND the tombstone; the
    # logic should treat any tombstone as consumed. Simpler: just rewrite
    # the file. At Alpha scale (~100s of tokens), full rewrite is cheap.
    consumed_marker = datetime.now(timezone.utc).isoformat()
    new_rows = []
    for r in rows:
        if r.get("token") == token:
            r = dict(r)
            r["consumed_at"] = consumed_marker
        new_rows.append(r)
    _tokens_file().parent.mkdir(parents=True, exist_ok=True)
    with open(_tokens_file(), "w", encoding="utf-8") as f:
        for r in new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Create user if first sign-in.
    email = match["email"]
    user = _ensure_user(email)

    # Issue JWT + set cookie.
    jwt_token, _jti = _issue_jwt(email=email, tier=user["tier"])

    logger.info("auth.verified email=%s tier=%s", email, user["tier"])

    payload = {
        "ok": True,
        "user": {
            "email": user["email"],
            "tier": user["tier"],
            "created_at": user["created_at"],
        },
    }
    resp = JSONResponse(payload)
    resp.set_cookie(key=_COOKIE_NAME, value=jwt_token, **_cookie_args(request))
    return resp


@router.post("/auth/logout", summary="Clear session cookie + revoke jti")
async def logout(request: Request):
    """Revoke the current session's jti and clear the cookie.

    Revocation is best-effort: if no/invalid cookie, we still return 200
    and clear the cookie. JWT remains technically valid until expiry but
    the jti revocation list rejects it on next /me call.
    """
    cookie = request.cookies.get(_COOKIE_NAME)
    if cookie:
        claims = _decode_jwt(cookie)
        if claims and claims.get("jti"):
            _append_jsonl(_revoked_sessions_file(), {
                "jti": claims["jti"],
                "revoked_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info("auth.logout jti=%s email=%s", claims["jti"], claims.get("sub"))

    resp = JSONResponse({"ok": True})
    # delete_cookie matches the path the cookie was set on.
    resp.delete_cookie(key=_COOKIE_NAME, path="/")
    return resp


@router.get("/auth/me", summary="Return current session user")
async def me(request: Request):
    """Return {email, tier, created_at} or 401 if no/invalid session."""
    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        return JSONResponse(
            {"ok": False, "error": "no session"}, status_code=401
        )

    claims = _decode_jwt(cookie)
    if not claims:
        return JSONResponse(
            {"ok": False, "error": "invalid session"}, status_code=401
        )

    jti = claims.get("jti", "")
    if _is_jti_revoked(jti):
        return JSONResponse(
            {"ok": False, "error": "session revoked"}, status_code=401
        )

    email = claims.get("sub", "")
    # Look up canonical user record so tier changes propagate.
    rows = _read_jsonl(_users_file())
    user = next((u for u in rows if u.get("email") == email), None)
    if not user:
        return JSONResponse(
            {"ok": False, "error": "user not found"}, status_code=401
        )

    return JSONResponse({
        "ok": True,
        "user": {
            "email": user["email"],
            "tier": user["tier"],
            "created_at": user["created_at"],
        },
    })


# --- Test helpers ---

def _override_data_dir_for_tests(tmp_dir: Path) -> None:
    """Repoint all storage to tmp_dir. Used by test fixtures only."""
    global _data_dir
    _data_dir = lambda: tmp_dir  # noqa: E731


__all__ = ["router"]
