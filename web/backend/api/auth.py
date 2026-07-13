"""Production passwordless email registration and login.

Passwordless login flow:
    POST /api/auth/request-link  { email }       → sends one-time magic link
    POST /api/auth/verify        { token }       → exchanges token for JWT session cookie
    POST /api/auth/logout                        → clears cookie + revokes session
    GET  /api/auth/me                            → returns session user (or 401)

What's intentionally NOT done here (deferred):
  - Social login (Google / GitHub OAuth). Magic-link is enough for Alpha.
  - Refresh tokens — the JWT is good for 30 days, opaque revocation via
    server-side session table is supported (logout writes to revoked_sessions).
  - 2FA / WebAuthn — out of scope for v1.

Storage: transactional SQLite under persistent AUTH_DATA_DIR. Raw magic-link
tokens are never stored; only SHA-256 hashes. The dev-only email outbox remains
JSONL so local E2E can inspect delivery without an SMTP provider.

JWT format: HS256, claims = {sub: email, tier, iat, exp, jti}. Secret from
JWT_SECRET env var. Dev fallback is a fixed string so tests are
reproducible — production deploys MUST set JWT_SECRET to a random 32+ byte
value (see web/backend/.env.example).
"""
from __future__ import annotations

import hashlib
import asyncio
import ipaddress
import json
import logging
import os
import re
import secrets
import smtplib
import time
import uuid
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlsplit

import jwt
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
try:  # Supports both `api.auth` and `web.backend.api.auth` import modes.
    from services.auth_store import AuthStore, DeletedCredentialError
except ModuleNotFoundError:  # Phase API imports from the repository root.
    from web.backend.services.auth_store import AuthStore, DeletedCredentialError
try:
    from services.account_data_registry import (
        AccountAsset, AccountDataRegistry, deletion_tombstone,
    )
except ModuleNotFoundError:
    from web.backend.services.account_data_registry import (
        AccountAsset, AccountDataRegistry, deletion_tombstone,
    )

logger = logging.getLogger("structural.auth")

router = APIRouter(tags=["auth"])

# --- Config ---
_TOKEN_TTL_MIN = 15            # magic-link freshness window
_SESSION_TTL_DAYS = 30         # JWT lifetime
_RATE_LIMIT_PER_HOUR = 3       # link requests per email per hour
_DEFAULT_IP_RATE_LIMIT_PER_HOUR = 10
_DEFAULT_GLOBAL_RATE_LIMIT_PER_HOUR = 200
_DEFAULT_TIER = "free"
_COOKIE_NAME = "phase_session"
_JWT_ALG = "HS256"
_DEV_FALLBACK_SECRET = "dev-jwt-secret-do-not-use-in-prod-32-chars-min-please"
_UNSAFE_SECRET_MARKERS = ("replace", "change-me", "changeme", "example", "test-secret", "dev-jwt")

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
    secret = os.getenv("JWT_SECRET", "")
    is_prod = os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod"
    normalized = secret.strip().lower()
    looks_predictable = any(marker in normalized for marker in _UNSAFE_SECRET_MARKERS)
    has_low_diversity = len(set(secret)) < 12
    if is_prod and (len(secret) < 32 or looks_predictable or has_low_diversity):
        raise RuntimeError(
            "JWT_SECRET must be a unique, non-placeholder 32+ character value in production"
        )
    return secret or _DEV_FALLBACK_SECRET


def _auth_enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "false").lower() in {"1", "true", "yes"}


def _is_prod() -> bool:
    return os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod"


def _validate_production_config() -> None:
    """Fail closed before creating credentials when production auth is enabled."""
    if not (_is_prod() and _auth_enabled()):
        return
    _jwt_secret()
    required = (
        "AUTH_LINK_BASE_URL", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM_EMAIL",
        "ADMIN_NOTIFICATION_EMAIL", "AUTH_DATA_DIR", "AUTH_TRUSTED_PROXY_IPS",
    )
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError(f"production auth email configuration missing: {', '.join(missing)}")
    link_origin = os.getenv("AUTH_LINK_BASE_URL", "").strip()
    parsed = urlsplit(link_origin)
    if (
        parsed.scheme != "https" or not parsed.netloc
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or parsed.username or parsed.password
    ):
        raise RuntimeError("AUTH_LINK_BASE_URL must be a bare HTTPS origin in production")
    if os.getenv("AUTH_SITE_ROLE", "").strip().lower() != "beta":
        raise RuntimeError("production auth runtime must use AUTH_SITE_ROLE=beta")
    if link_origin.rstrip("/") != "https://beta.structural.bytedance.city":
        raise RuntimeError("beta AUTH_LINK_BASE_URL must use the canonical beta origin")
    data_dir = Path(os.environ["AUTH_DATA_DIR"]).expanduser()
    if not data_dir.is_absolute():
        raise RuntimeError("AUTH_DATA_DIR must be absolute in production")
    repository = Path(__file__).resolve().parents[3]
    resolved_data = data_dir.resolve()
    if resolved_data == repository or repository in resolved_data.parents:
        raise RuntimeError("AUTH_DATA_DIR must be outside the Git worktree in production")
    _trusted_proxy_networks()
    _positive_limit("AUTH_IP_EMAIL_LIMIT_PER_HOUR", _DEFAULT_IP_RATE_LIMIT_PER_HOUR)
    _positive_limit("AUTH_GLOBAL_EMAIL_LIMIT_PER_HOUR", _DEFAULT_GLOBAL_RATE_LIMIT_PER_HOUR)


# --- Storage paths (lazy, overridable in tests) ---

def _data_dir() -> Path:
    configured = os.getenv("AUTH_DATA_DIR", "").strip()
    return Path(configured) if configured else Path(__file__).resolve().parent.parent / "data"


def _store() -> AuthStore:
    return AuthStore(_data_dir() / "auth.sqlite3")


def _outbox_file() -> Path:
    return _data_dir() / "mock_email_outbox.jsonl"


def _account_registry() -> AccountDataRegistry:
    # Lazy import avoids an auth/favorites import cycle.
    try:
        from api import favorites
    except ModuleNotFoundError:
        from web.backend.api import favorites
    store = _store()
    try:
        from api import report_account
    except ModuleNotFoundError:
        from web.backend.api import report_account
    return AccountDataRegistry([
        AccountAsset(
            name="favorites", owner_key="normalized_email",
            retention="until removed by the user or account deletion",
            export=favorites.export_account_favorites,
            delete=favorites.delete_account_favorites,
            restore=favorites.restore_account_favorites,
        ),
        AccountAsset(
            name="claimed_reports", owner_key="sso_subject_hmac",
            retention="until removed by the user or account deletion",
            export=report_account.export_account_reports,
            delete=report_account.delete_account_reports,
            restore=report_account.restore_account_reports,
        ),
        # Account identity is deliberately last: deletion invalidates every
        # outstanding JWT because resolve_session_user requires this row.
        AccountAsset(
            name="authentication", owner_key="normalized_email",
            retention="account lifetime; removed on account deletion",
            export=store.export_account_data,
            delete=store.delete_account_data,
        ),
    ])


def _append_deletion_audit(record: dict) -> None:
    _append_jsonl(_data_dir() / "account_deletion_audit.jsonl", record)


# --- JSONL helpers ---

def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# --- Schemas ---

class RequestLinkBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=_MAX_EMAIL_LEN)
    return_to: Optional[str] = Field(default=None, max_length=500)


class VerifyBody(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class DeleteAccountBody(BaseModel):
    confirmation: str = Field(..., min_length=6, max_length=20)


# --- Helpers: email validation, rate limit, token gen, JWT ---

def _normalize_email(raw: str) -> Optional[str]:
    e = (raw or "").strip().lower()
    if not e or len(e) > _MAX_EMAIL_LEN:
        return None
    if not _EMAIL_RE.match(e):
        return None
    return e


def _positive_limit(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _trusted_proxy_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    raw = os.getenv("AUTH_TRUSTED_PROXY_IPS", "").strip()
    if not raw:
        return []
    try:
        return [ipaddress.ip_network(item.strip(), strict=False) for item in raw.split(",") if item.strip()]
    except ValueError as exc:
        raise RuntimeError("AUTH_TRUSTED_PROXY_IPS contains an invalid address or CIDR") from exc


def _client_ip(request: Request) -> str:
    """Resolve the nearest untrusted client; ignore spoofed proxy headers."""
    peer_raw = request.client.host if request.client else "0.0.0.0"
    try:
        peer = ipaddress.ip_address(peer_raw)
    except ValueError:
        return "0.0.0.0"
    trusted = _trusted_proxy_networks()
    if not any(peer in network for network in trusted):
        return peer.compressed
    forwarded: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for raw in request.headers.get("x-forwarded-for", "").split(","):
        if not raw.strip():
            continue
        try:
            forwarded.append(ipaddress.ip_address(raw.strip()))
        except ValueError:
            logger.warning("auth.forwarded_for_rejected reason=malformed")
            return peer.compressed
    for candidate in reversed([*forwarded, peer]):
        if not any(candidate in network for network in trusted):
            return candidate.compressed
    return peer.compressed


def _check_rate_limit(email: str, request: Request) -> bool:
    """Apply atomic per-email, trusted-client-IP and global mail limits."""
    ip_hash = hashlib.sha256(_client_ip(request).encode("utf-8")).hexdigest()
    return _store().record_rate_requests([
        (email, _RATE_LIMIT_PER_HOUR),
        (f"ip:{ip_hash}", _positive_limit(
            "AUTH_IP_EMAIL_LIMIT_PER_HOUR", _DEFAULT_IP_RATE_LIMIT_PER_HOUR,
        )),
        ("global:magic-link-email", _positive_limit(
            "AUTH_GLOBAL_EMAIL_LIMIT_PER_HOUR", _DEFAULT_GLOBAL_RATE_LIMIT_PER_HOUR,
        )),
    ])


def _generate_token() -> str:
    """32-char URL-safe token. token_urlsafe(24) → ~32 chars after base64."""
    return secrets.token_urlsafe(24)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _safe_return_to(raw: Optional[str]) -> Optional[str]:
    """Allow only a local absolute-path return target in emailed links."""
    value = (raw or "").strip()
    if not value or not value.startswith("/") or value.startswith("//"):
        return None
    if "\\" in value or any(ord(char) < 32 for char in value):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.path.startswith("//"):
        return None
    if parsed.path in {"/auth/login", "/auth/verify"}:
        return None
    return value


def _ensure_user(email: str) -> tuple[dict, bool]:
    """Idempotent user creation. Returns (user, was_created)."""
    return _store().ensure_user_and_notification(
        email, _DEFAULT_TIER, datetime.now(timezone.utc).isoformat()
    )


def _send_email(to: str, subject: str, text: str) -> None:
    """Deliver through configured SMTP; mock delivery is dev-only."""
    if not _is_prod() and os.getenv("AUTH_DEV_MODE", "").lower() in {"1", "true", "yes"}:
        _append_jsonl(_outbox_file(), {
            "ts": int(time.time()), "to": to, "subject": subject, "text": text,
        })
        return
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    if not host or not sender:
        raise RuntimeError("email provider is not configured")
    port = int(os.getenv("SMTP_PORT", "587"))
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(host, port, timeout=timeout) as smtp:
        if not use_ssl and os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"}:
            smtp.starttls()
        username = os.getenv("SMTP_USERNAME", "").strip()
        password = os.getenv("SMTP_PASSWORD", "")
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def _notify_admin_new_user(email: str, created_at: str) -> None:
    retry_registration_notifications()


def retry_registration_notifications(limit: int = 50) -> tuple[int, int]:
    """Retry the durable notification queue; suitable for a cron/systemd timer."""
    admin = os.getenv("ADMIN_NOTIFICATION_EMAIL", "").strip()
    if not admin:
        remaining = _store().pending_notification_count()
        logger.error(
            "auth.registration_notification_failed reason=admin_email_missing retryable=true remaining=%d",
            remaining,
        )
        return 0, remaining
    store = _store()
    pending = store.claim_notifications(limit)
    sent = 0
    for item in pending:
        try:
            _send_email(admin, "Structural Isomorphism: new user registration", (
                f"A new user registered.\n\nEmail: {item['email']}\n"
                f"Created at: {item['created_at']}\n"
            ))
            store.mark_notification(item["id"], delivered_at=datetime.now(timezone.utc).isoformat(), error=None)
            sent += 1
        except Exception as exc:
            store.mark_notification(item["id"], delivered_at=None, error=type(exc).__name__)
            logger.exception("auth.registration_notification_failed retryable=true")
    remaining = store.pending_notification_count()
    logger.info("auth.registration_notification_retry sent=%d remaining=%d", sent, remaining)
    return sent, remaining


def _require_same_origin(request: Request) -> Optional[JSONResponse]:
    """Reject cross-site cookie mutations; absent Origin is allowed for non-browser clients."""
    origin = request.headers.get("origin")
    if not origin:
        return None
    expected = os.getenv("AUTH_LINK_BASE_URL", "").rstrip("/")
    if not expected:
        expected = str(request.base_url).rstrip("/")
    if origin.rstrip("/") != expected:
        return JSONResponse({"ok": False, "error": "invalid origin"}, status_code=403)
    return None


def _auth_unavailable() -> Optional[JSONResponse]:
    if not _auth_enabled():
        return JSONResponse({"ok": False, "error": "auth unavailable"}, status_code=503)
    try:
        _validate_production_config()
    except RuntimeError:
        logger.exception("auth.configuration_invalid")
        return JSONResponse({"ok": False, "error": "auth unavailable"}, status_code=503)
    return None


def _issue_jwt(email: str, tier: str) -> tuple[str, str]:
    """Return (jwt_string, jti)."""
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    user = _store().user(email)
    # Some internal/test-only connection flows mint a signed identity before
    # creating an auth account. Such a token cannot pass resolve_session_user;
    # production verify always supplies the persisted account generation.
    generation = user.get("session_generation") if user else uuid.uuid4().hex
    payload = {
        "sub": email,
        "tier": tier,
        "iat": int(now.timestamp()),
        "issued_ns": time.time_ns(),
        "exp": int((now + timedelta(days=_SESSION_TTL_DAYS)).timestamp()),
        "jti": jti,
        "gen": generation,
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
    return _store().is_revoked(jti)


def resolve_session_user(request: Request) -> tuple[Optional[dict], str]:
    """Resolve the HttpOnly session for other API modules.

    The status is one of ``absent``, ``valid``, ``invalid`` or ``unavailable``.
    Callers must not treat an invalid/revoked cookie as anonymous or silently
    fall back to a weaker credential.
    """
    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        return None, "absent"
    if not _auth_enabled():
        return None, "unavailable"
    claims = _decode_jwt(cookie)
    if not claims:
        return None, "invalid"
    if _is_jti_revoked(claims.get("jti", "")):
        return None, "revoked"
    user = _store().user(claims.get("sub", ""))
    if not user or claims.get("gen") != user.get("session_generation"):
        return None, "invalid"
    return {
        "email": user["email"],
        "tier": user["tier"],
        "created_at": user["created_at"],
        "_issued_ns": int(claims.get("issued_ns", 0)),
    }, "valid"


def resolve_account_user(request: Request) -> tuple[Optional[dict], str]:
    """Resolve the canonical beta account across direct and legacy SSO paths."""
    try:
        from api.sso import resolve_beta_user
    except ModuleNotFoundError:
        from web.backend.api.sso import resolve_beta_user
    beta, beta_status = resolve_beta_user(request)
    if beta_status != "valid" or not beta:
        return None, beta_status
    stored = _store().user(beta["email"])
    return {
        "email": beta["email"],
        "tier": beta.get("tier", "free"),
        "created_at": stored.get("created_at") if stored else None,
        "auth_method": "phase_sso",
    }, "valid"


def _account_auth_error(status: str) -> JSONResponse:
    if status == "credential_conflict":
        return JSONResponse(
            {"ok": False, "error": "credential_conflict"}, status_code=409,
        )
    messages = {
        "absent": "no session", "revoked": "session revoked",
        "unlinked": "email confirmation required",
    }
    return JSONResponse({
        "ok": False, "error": messages.get(status, "invalid session"),
    }, status_code=401)


def _clear_beta_session(response: Response) -> None:
    response.delete_cookie(key="structural_beta_session", path="/")


def require_same_origin(request: Request) -> Optional[JSONResponse]:
    """Public wrapper used by cookie-authenticated mutation endpoints."""
    return _require_same_origin(request)


def _cookie_args(request: Request) -> dict:
    """Cookie security: HttpOnly + SameSite=Lax always; Secure when HTTPS."""
    # request.url.scheme is "https" behind a proper proxy that sets
    # X-Forwarded-Proto, but TestClient uses "http". So we relax Secure
    # in tests; production deploys MUST run behind nginx/HTTPS.
    secure = _is_prod() or request.url.scheme == "https"
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
    unavailable = _auth_unavailable()
    if unavailable:
        return unavailable
    origin_error = _require_same_origin(request)
    if origin_error:
        return origin_error
    email = _normalize_email(body.email)
    if not email:
        return JSONResponse(
            {"ok": False, "error": "invalid email"}, status_code=400
        )

    if not _check_rate_limit(email, request):
        return JSONResponse(
            {"ok": False, "error": "rate limit exceeded; try again in 1 hour"},
            status_code=429,
        )

    token = _generate_token()
    now = datetime.now(timezone.utc)
    _store().add_token(
        _token_hash(token), email, now.isoformat(),
        (now + timedelta(minutes=_TOKEN_TTL_MIN)).isoformat(),
    )

    base_url = os.getenv("AUTH_LINK_BASE_URL", "http://localhost:3000").rstrip("/")
    query = {"token": token}
    return_to = _safe_return_to(body.return_to)
    if return_to:
        query["next"] = return_to
    magic_link = f"{base_url}/auth/verify?{urlencode(query)}"
    try:
        await asyncio.to_thread(
            _send_email, email, "Your Structural Isomorphism sign-in link",
            f"Sign in using this one-time link (valid for {_TOKEN_TTL_MIN} minutes):\n\n{magic_link}\n",
        )
    except Exception:
        logger.exception("auth.magic_link_delivery_failed")
        return JSONResponse({"ok": False, "error": "email delivery unavailable"}, status_code=503)

    logger.info("auth.magic_link_requested email_hash=%s", _token_hash(email)[:12])

    # Dev mode: return the link inline so the frontend can show it.
    # In prod, response always omits the link (regardless of dev flag).
    body_out: dict = {"ok": True}
    if not _is_prod() and os.getenv("AUTH_DEV_MODE", "").lower() in ("1", "true", "yes"):
        body_out["dev_link"] = magic_link
        body_out["dev_token"] = token
    return JSONResponse(body_out)


@router.post("/auth/verify", summary="Exchange magic-link token for session")
async def verify(body: VerifyBody, request: Request, response: Response):
    """Validate the token, create/lookup the user, issue a JWT, set cookie."""
    unavailable = _auth_unavailable()
    if unavailable:
        return unavailable
    origin_error = _require_same_origin(request)
    if origin_error:
        return origin_error
    token = (body.token or "").strip()
    if not token:
        return JSONResponse(
            {"ok": False, "error": "missing token"}, status_code=400
        )

    consumed_marker = datetime.now(timezone.utc).isoformat()
    match, status = _store().consume_token(_token_hash(token), consumed_marker)
    if status == "invalid":
        return JSONResponse({"ok": False, "error": "invalid token"}, status_code=400)
    if status == "used" or match is None:
        return JSONResponse({"ok": False, "error": "token already used"}, status_code=400)
    try:
        expires_at = datetime.fromisoformat(match["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except Exception:
        return JSONResponse({"ok": False, "error": "malformed token record"}, status_code=400)
    if datetime.now(timezone.utc) > expires_at:
        return JSONResponse({"ok": False, "error": "token expired"}, status_code=400)

    # Create user if first sign-in.
    email = match["email"]
    try:
        user, was_created = _store().ensure_user_from_token(
            email, _DEFAULT_TIER, datetime.now(timezone.utc).isoformat(), match["created_at"]
        )
    except DeletedCredentialError:
        logger.warning("auth.verify_rejected reason=credential_predates_deletion")
        return JSONResponse({"ok": False, "error": "invalid token"}, status_code=400)
    if was_created:
        # User creation and durable outbox enqueue are already committed. Never
        # delay or roll back the session while SMTP/retries run in background.
        asyncio.create_task(asyncio.to_thread(
            _notify_admin_new_user, email, user["created_at"]
        ))

    # Issue JWT + set cookie.
    jwt_token, _jti = _issue_jwt(email=email, tier=user["tier"])

    logger.info("auth.verified email_hash=%s tier=%s", _token_hash(email)[:12], user["tier"])

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
    # A stale/expired legacy SSO cookie must never shadow the fresh direct
    # credential on the next request.
    _clear_beta_session(resp)
    return resp


@router.post("/auth/logout", summary="Clear session cookie + revoke jti")
async def logout(request: Request):
    """Revoke the current session's jti and clear the cookie.

    Revocation is best-effort: if no/invalid cookie, we still return 200
    and clear the cookie. JWT remains technically valid until expiry but
    the jti revocation list rejects it on next /me call.
    """
    unavailable = _auth_unavailable()
    if unavailable:
        return unavailable
    origin_error = _require_same_origin(request)
    if origin_error:
        return origin_error
    try:
        from api.sso import SsoReplayStore, _data_dir as sso_data_dir, resolve_beta_user
    except ModuleNotFoundError:
        from web.backend.api.sso import SsoReplayStore, _data_dir as sso_data_dir, resolve_beta_user
    beta_user, beta_status = resolve_beta_user(request)
    resp = JSONResponse(
        {"ok": False, "error": "credential_conflict"} if beta_status == "credential_conflict"
        else {"ok": True},
        status_code=409 if beta_status == "credential_conflict" else 200,
    )
    if beta_status == "valid" and beta_user:
        cookie = request.cookies.get(_COOKIE_NAME)
        if cookie:
            claims = _decode_jwt(cookie)
            if claims and claims.get("jti"):
                _store().revoke(
                    claims["jti"], datetime.now(timezone.utc).isoformat(), claims.get("sub")
                )
                logger.info("auth.logout jti=%s", claims["jti"])
        if request.cookies.get("structural_beta_session"):
            SsoReplayStore(sso_data_dir() / "sso_replay.sqlite3").revoke_subject(beta_user["id"])
    # delete_cookie matches the path the cookie was set on.
    resp.delete_cookie(key=_COOKIE_NAME, path="/")
    _clear_beta_session(resp)
    return resp


@router.get("/auth/me", summary="Return current session user")
async def me(request: Request):
    """Return {email, tier, created_at} or 401 if no/invalid session."""
    unavailable = _auth_unavailable()
    if unavailable:
        return unavailable
    user, status = resolve_account_user(request)
    if status != "valid" or not user:
        return _account_auth_error(status)

    return JSONResponse({
        "ok": True,
        "user": {
            "email": user["email"],
            "tier": user["tier"],
            "created_at": user["created_at"],
        },
    })


@router.get("/me/export", summary="Export authenticated account data")
async def export_my_account(request: Request):
    """Export registry-declared assets for the current session only."""
    unavailable = _auth_unavailable()
    if unavailable:
        return unavailable
    user, status = resolve_account_user(request)
    if status != "valid" or not user:
        return _account_auth_error(status)
    try:
        registry = _account_registry()
        data = registry.export_all(user["email"])
    except Exception:
        logger.exception("account_data.export_failed")
        return JSONResponse({"ok": False, "error": "account export unavailable"}, status_code=500)
    logger.info("account_data.exported email_hash=%s", _token_hash(user["email"])[:12])
    return JSONResponse({
        "ok": True,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "assets": registry.manifest(),
        "data": data,
    })


@router.post("/me/delete", summary="Permanently delete authenticated account")
async def delete_my_account(body: DeleteAccountBody, request: Request):
    """Erase registry assets, invalidate credentials and clear the cookie."""
    unavailable = _auth_unavailable()
    if unavailable:
        return unavailable
    origin_error = _require_same_origin(request)
    if origin_error:
        return origin_error
    user, status = resolve_account_user(request)
    if status != "valid" or not user:
        return _account_auth_error(status)
    if body.confirmation != "DELETE":
        return JSONResponse({"ok": False, "error": "confirmation must equal DELETE"}, status_code=400)
    try:
        registry = _account_registry()
        removed = registry.delete_all(user["email"])
    except Exception:
        logger.exception("account_data.delete_failed")
        return JSONResponse({"ok": False, "error": "account deletion failed"}, status_code=500)
    tombstone = deletion_tombstone(user["email"], removed)
    try:
        _append_deletion_audit(tombstone)
    except Exception:
        # Deletion already succeeded. Do not report a false failure that could
        # encourage repeated requests; alert operators without restoring PII.
        logger.exception("account_data.audit_write_failed")
    response = JSONResponse({
        "ok": True,
        "deleted_at": tombstone["deleted_at"],
        "removed": removed,
    })
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    _clear_beta_session(response)
    logger.info("account_data.deleted owner_hash=%s", tombstone["owner_hash"])
    return response


# --- Test helpers ---

def _override_data_dir_for_tests(tmp_dir: Path) -> None:
    """Repoint all storage to tmp_dir. Used by test fixtures only."""
    global _data_dir
    _data_dir = lambda: tmp_dir  # noqa: E731


__all__ = [
    "router",
    "require_same_origin",
    "resolve_account_user",
    "resolve_session_user",
    "retry_registration_notifications",
]
