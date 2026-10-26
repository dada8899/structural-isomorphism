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
import hmac
import asyncio
from contextlib import contextmanager
import ipaddress
import json
import os
import re
import secrets
import smtplib
import ssl
import sqlite3
import threading
import time
import uuid
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlencode, urlsplit

import jwt
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id
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
try:
    from services.privacy_identifiers import (
        opaque_identifier,
        validate_privacy_hmac_config,
    )
except ModuleNotFoundError:
    from web.backend.services.privacy_identifiers import (
        opaque_identifier,
        validate_privacy_hmac_config,
    )

logger = get_logger("structural.auth")

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

# Account deletion and research writes share one persistent, single-host gate.
_AUTH_STORES_GUARD = threading.Lock()
_AUTH_STORES: dict[Path, AuthStore] = {}


@contextmanager
def account_owner_transaction(owner: str):
    normalized = owner.strip().lower()
    if not normalized:
        raise ValueError("account transaction requires an owner")
    if __package__=='web.backend.api':from ..research.authorization import AuthorizationGate
    else:from research.authorization import AuthorizationGate
    store = _store()
    gate_id = store.owner_gate_id(normalized)
    with AuthorizationGate(store).owner_gate_id(gate_id) as lease:
        yield lease



def valid_account_generation(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def verified_account_generation(email, generation):
    """Validate a signed generation; a current row never fills a missing claim."""
    if not valid_account_generation(generation):
        return False
    user = _store().user(email)
    return bool(user and user['lifecycle'] == 'active'
                and not _store().deletion_pending(email)
                and user.get('session_generation') == generation)


class _FavoritesAuthorityError(PermissionError):
    """The actual authenticated request/job capability is no longer valid."""


class _FavoritesAuthority:
    """Per-operation live gate and server-side request/job, never a DTO grant."""
    def __init__(self, email, generation, lease, *, request=None, service=None, job_id=None):
        if not valid_account_generation(generation):
            raise _FavoritesAuthorityError('verified Favorites generation required')
        self.email, self.generation, self.lease = email.strip().lower(), generation, lease
        self.request, self.service, self.job_id = request, service, job_id
        self.store = _store()
        self.path = self.store.path
        self.owner_key = self.store.owner_key(self.email)
        self.active = True
        self.check()

    def check(self):
        import stat
        if __package__ == 'web.backend.api':
            from ..research.authorization import OwnerGateLease
            from ..services.runtime_paths import require_private_auth_lock_dir
        else:
            from research.authorization import OwnerGateLease
            from services.runtime_paths import require_private_auth_lock_dir
        if (not self.active or not _is_prod() or _store().path != self.path
                or not isinstance(self.lease, OwnerGateLease)):
            raise _FavoritesAuthorityError('Favorites authority is no longer active')
        if self.request is not None:
            user, status = resolve_account_user(self.request)
            if (status != 'valid' or not user or user['email'].lower() != self.email
                    or user.get('_verified_generation') != self.generation):
                raise _FavoritesAuthorityError('Favorites request identity changed')
            with self.store._connection() as conn:
                gate = conn.execute('SELECT gate_id FROM auth_owner_gates WHERE owner_key=?',
                    (self.owner_key,)).fetchone()
            if gate is None:
                raise _FavoritesAuthorityError('Favorites gate is missing; no automatic repair')
            gate_id = gate['gate_id']
        elif self.service is not None and self.job_id is not None:
            job = self.service.deletion_job(self.job_id)
            if (job['state'] != 'pending' or job['owner_email'] != self.email
                    or job['session_generation'] != self.generation
                    or job['owner_key'] != self.owner_key or self.service.store.path != self.path):
                raise _FavoritesAuthorityError('Favorites deletion job identity changed')
            gate_id = job['gate_id']
            if __package__ == 'web.backend.api':from ..research.paid_control import verify_deletion_origin
            else:from research.paid_control import verify_deletion_origin
            with self.service.store.transaction() as conn:
                verify_deletion_origin(conn, store=self.service.store, lease=self.lease, job_id=self.job_id)
            user = self.store.user(self.email)
            if user and (user['lifecycle'] != 'deleting' or user['session_generation'] != self.generation):
                raise _FavoritesAuthorityError('Favorites deletion cannot target a new incarnation')
        else:
            raise _FavoritesAuthorityError('actual Favorites request or deletion job required')
        # Also bind legacy-origin jobs to the actual held gate; their Core
        # origin compatibility check alone does not authenticate a lease.
        if type(gate_id) is not str or str(uuid.UUID(gate_id, version=4)) != gate_id:
            raise _FavoritesAuthorityError('Favorites gate identifier is invalid')
        root = require_private_auth_lock_dir(self.path)
        info = (root / (gate_id + '.lock')).lstat()
        identity = (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode), info.st_nlink)
        if (not stat.S_ISREG(info.st_mode) or identity != self.lease.identity
                or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077):
            raise _FavoritesAuthorityError('Favorites lease belongs to another gate')
        return self


@contextmanager
def _favorites_authority(email, generation, lease, **source):
    if __package__ == 'web.backend.api':from ..services.runtime_paths import FAVORITES_AUTHORITY
    else:from services.runtime_paths import FAVORITES_AUTHORITY
    authority = _FavoritesAuthority(email, generation, lease, **source)
    token = FAVORITES_AUTHORITY.set(authority)
    try:
        yield authority
    finally:
        authority.active = False
        FAVORITES_AUTHORITY.reset(token)


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
    if _is_prod():
        validate_privacy_hmac_config()
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
    site_role = os.getenv("AUTH_SITE_ROLE", "").strip().lower()
    canonical_origins = {
        "beta": "https://beta.structural.bytedance.city",
        "phase": "https://phase.bytedance.city",
    }
    expected_origin = canonical_origins.get(site_role)
    if expected_origin is None:
        raise RuntimeError("production auth runtime must use an explicit supported AUTH_SITE_ROLE")
    if link_origin.rstrip("/") != expected_origin:
        raise RuntimeError(
            f"{site_role} AUTH_LINK_BASE_URL must use its canonical HTTPS origin"
        )
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
    if os.getenv("STRUCTURAL_ENV","dev").strip().lower()=="prod":
        if __package__=='web.backend.api':from ..services.runtime_paths import private_auth_path
        else:from services.runtime_paths import private_auth_path
        return private_auth_path().parent
    configured = os.getenv("AUTH_DATA_DIR", "").strip()
    return Path(configured) if configured else Path(__file__).resolve().parent.parent / "data"


def _store() -> AuthStore:
    formal=os.getenv("STRUCTURAL_ENV","dev").strip().lower()=="prod"
    path=(_data_dir()/"auth.sqlite3")
    if not formal:path=path.expanduser().resolve()
    with _AUTH_STORES_GUARD:
        identity=AuthStore.preflight_private(path) if formal else None
        key=(True,path,identity) if formal else path
        store=_AUTH_STORES.get(key)
        if store is None:
            store=AuthStore(path)
            _AUTH_STORES[key]=store
        elif formal and (not store._private_auth or store.storage_identity!=identity):
            raise RuntimeError('private Auth cache has an inconsistent profile or identity')
        return store


def account_deletion_epoch(email: str) -> Optional[str]:
    """Expose the opaque deletion generation for owner transaction guards."""
    return _store().account_deletion_epoch(email)


def account_is_active(email: str) -> bool:
    """Return whether an email-owned account still exists after revalidation."""
    store = _store()
    user = store.user(email)
    return bool(user and user["lifecycle"] == "active" and not store.deletion_pending(email))


def api_key_retired_by_account_deletion(email: str, created_at: str) -> bool:
    """Fail closed for a legacy key issued no later than a deletion commit."""
    if _store().deletion_pending(email):
        return True
    deleted_at = account_deletion_epoch(email)
    if deleted_at is None:
        return False
    try:
        key_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        deletion_time = datetime.fromisoformat(deleted_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return True
    if (
        key_time.tzinfo is None
        or key_time.utcoffset() is None
        or deletion_time.tzinfo is None
        or deletion_time.utcoffset() is None
    ):
        return True
    return key_time <= deletion_time


def _outbox_file() -> Path:
    return _data_dir() / "mock_email_outbox.jsonl"


def _account_registry(*, favorites_authority=None) -> AccountDataRegistry:
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
    favorite_snapshot = None
    def favorite_call(method, owner, *args):
        if favorites_authority is None:
            return method(owner, *args)
        favorites_authority.check()
        if owner.strip().lower() != favorites_authority.email:
            raise PermissionError('Favorites registry target mismatch')
        if __package__ == 'web.backend.api':from ..services.runtime_paths import FAVORITES_AUTHORITY
        else:from services.runtime_paths import FAVORITES_AUTHORITY
        token = FAVORITES_AUTHORITY.set(favorites_authority)
        try:
            return method(owner, *args)
        finally:
            FAVORITES_AUTHORITY.reset(token)
    def favorite_snapshot_call(owner):
        nonlocal favorite_snapshot
        favorite_snapshot = favorite_call(favorites.snapshot_account_favorites, owner)
        return favorite_snapshot
    def favorite_delete_call(owner):
        if favorites_authority is None:
            return favorites.delete_account_favorites(owner)
        # UNKNOWN is reconciled inside this delete call, before the generic
        # registry may mark it completed or run any compensation.
        try:
            return favorite_call(favorites._delete_private_favorites, owner, favorite_snapshot)
        except favorites._private_paths().FavoritesWriteUnknown as unknown:
            return favorite_call(favorites._reconcile_private_favorites, owner, favorite_snapshot, unknown, 'delete')
    def favorite_restore_call(owner, snapshot, result):
        if favorites_authority is not None and snapshot is not favorite_snapshot:
            raise PermissionError('Favorites restore is not from this registry operation')
        try:
            return favorite_call(favorites.restore_account_favorites, owner, snapshot, result)
        except favorites._private_paths().FavoritesWriteUnknown as unknown:
            return favorite_call(favorites._reconcile_private_favorites, owner, snapshot, unknown, 'restore')
    return AccountDataRegistry([
        AccountAsset(
            name="favorites", owner_key="normalized_email",
            retention="until removed by the user or account deletion",
            export=lambda owner: favorite_call(favorites.export_account_favorites, owner),
            delete=favorite_delete_call,
            restore=favorite_restore_call,
            snapshot=favorite_snapshot_call,
        ),
        AccountAsset(
            name="claimed_reports", owner_key="sso_subject_hmac",
            retention="until removed by the user or account deletion",
            export=report_account.export_account_reports,
            delete=report_account.delete_account_reports,
            restore=report_account.restore_account_reports,
            snapshot=report_account.snapshot_account_reports,
        ),
        # Account identity is deliberately last: deletion invalidates every
        # outstanding JWT because resolve_session_user requires this row.
        AccountAsset(
            name="authentication", owner_key="normalized_email",
            retention="account lifetime; removed on account deletion",
            export=store.export_account_data,
            delete=lambda owner: store.delete_account_data(
                owner,
                rate_keys=(
                    _privacy_rate_key("email", owner),
                    _legacy_privacy_rate_key("email", owner),
                ),
            ),
        ),
    ])


def _append_deletion_audit(record: dict) -> None:
    if os.getenv("STRUCTURAL_ENV","dev").strip().lower()=="prod":
        if __package__=='web.backend.api':from ..services.runtime_paths import append_private_auth_audit
        else:from services.runtime_paths import append_private_auth_audit
        append_private_auth_audit(record)
        return
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


class AuthUserResponse(BaseModel):
    email: str
    tier: str
    created_at: str


class RequestLinkResponse(BaseModel):
    """Enumeration-safe acknowledgement; dev credentials never appear in prod."""

    ok: Literal[True]
    dev_link: Optional[str] = None
    dev_token: Optional[str] = None


class VerifyResponse(BaseModel):
    ok: Literal[True]
    user: AuthUserResponse


class LogoutResponse(BaseModel):
    ok: bool
    error: Optional[Literal["credential_conflict"]] = None


class AuthMeResponse(BaseModel):
    ok: Literal[True]
    user: AuthUserResponse


class AccountAssetManifestResponse(BaseModel):
    name: str
    owner_key: str
    retention: str


class AccountExportResponse(BaseModel):
    ok: Literal[True]
    exported_at: str
    assets: list[AccountAssetManifestResponse]
    data: dict[str, object]


class AccountDeleteResponse(BaseModel):
    ok: Literal[True]
    deleted_at: str
    removed: dict[str, object]


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
            logger.warning("auth.forwarded_for_rejected")
            return peer.compressed
    for candidate in reversed([*forwarded, peer]):
        if not any(candidate in network for network in trusted):
            return candidate.compressed
    return peer.compressed


def _privacy_rate_key(namespace: str, value: str) -> str:
    """Stable v2 HMAC bucket key for identifiers in operational state."""
    kind = "email" if namespace == "email" else "ip"
    return opaque_identifier(f"auth-rate.{namespace}", value, kind=kind)


def _legacy_privacy_rate_key(namespace: str, value: str) -> str:
    """Pre-v2 lookup key retained only for bounded in-place migration."""
    root_key = _jwt_secret().encode("utf-8")
    rate_key = hmac.new(
        root_key,
        b"structural.auth.rate-limit.key.v1",
        hashlib.sha256,
    ).digest()
    digest = hmac.new(
        rate_key,
        namespace.encode("ascii") + b"\0" + value.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{namespace}:v1:{digest}"


def _check_rate_limit(email: str, request: Request) -> bool:
    """Apply atomic opaque per-email, trusted-client-IP and global limits."""
    client_ip = _client_ip(request)
    return _store().record_rate_requests_with_legacy([
        (
            _privacy_rate_key("email", email),
            # The bounded raw-email lookup covers the oldest pre-HMAC schema;
            # v1 used the JWT-derived HMAC. Both are rewritten in-place.
            (_legacy_privacy_rate_key("email", email), email),
            _RATE_LIMIT_PER_HOUR,
        ),
        (
            _privacy_rate_key("ip", client_ip),
            (_legacy_privacy_rate_key("ip", client_ip), client_ip),
            _positive_limit(
                "AUTH_IP_EMAIL_LIMIT_PER_HOUR", _DEFAULT_IP_RATE_LIMIT_PER_HOUR,
            ),
        ),
        (
            "global:magic-link-email",
            (),
            _positive_limit(
                "AUTH_GLOBAL_EMAIL_LIMIT_PER_HOUR",
                _DEFAULT_GLOBAL_RATE_LIMIT_PER_HOUR,
            ),
        ),
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
    if os.getenv("STRUCTURAL_ENV","dev").strip().lower()=="prod" and not _is_prod():
        raise RuntimeError('invalid private Auth profile; mock delivery is forbidden')
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
    use_ssl = port == 465 or os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    tls_options = {"context": ssl.create_default_context()} if use_ssl else {}
    with smtp_cls(host, port, timeout=timeout, **tls_options) as smtp:
        if not use_ssl and os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"}:
            smtp.starttls(context=ssl.create_default_context())
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
            "auth.registration_notification_failed",
            retryable=True,
            remaining=remaining,
            incident_id=new_incident_id(),
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
            logger.error(
                "auth.registration_notification_failed",
                error_type=type(exc).__name__,
                retryable=True,
                incident_id=new_incident_id(),
            )
    remaining = store.pending_notification_count()
    logger.info(
        "auth.registration_notification_retry",
        sent=sent,
        remaining=remaining,
    )
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
    except RuntimeError as exc:
        logger.error(
            "auth.configuration_invalid",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return JSONResponse({"ok": False, "error": "auth unavailable"}, status_code=503)
    return None


def _issue_jwt(email: str = None, tier: str = None, *, authority=None) -> tuple[str, str]:
    """Return (jwt_string, jti)."""
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    store = _store()
    if store._private_auth or _is_prod():
        if __package__=='web.backend.api':from ..services.auth_registration import SessionIssueAuthority
        else:from services.auth_registration import SessionIssueAuthority
        if type(authority) is not SessionIssueAuthority:
            raise PermissionError('formal JWT requires this request committed finalization')
        user=authority.consume(store)
        email,tier=user['email'],user['tier']
    else:
        user=store.user(email)
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
    if (not user or user["lifecycle"] != "active" or _store().deletion_pending(user["email"])
            or claims.get("gen") != user.get("session_generation")):
        return None, "invalid"
    if not valid_account_generation(claims.get("gen")):
        return None, "invalid"
    return {
        "email": user["email"],
        "tier": user["tier"],
        "created_at": user["created_at"],
        "_issued_ns": int(claims.get("issued_ns", 0)),
        "_verified_generation": claims["gen"],
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
    if not stored or not account_is_active(beta["email"]):
        return None, "invalid"
    generation = beta.get("_verified_generation")
    if generation is not None and not verified_account_generation(beta["email"], generation):
        return None, "invalid"
    if _is_prod() and generation is None:
        return None, "invalid"
    return {
        "email": beta["email"],
        "tier": beta.get("tier", "free"),
        "created_at": stored.get("created_at") if stored else None,
        "auth_method": "phase_sso",
        **({"_verified_generation": generation} if generation is not None else {}),
    }, "valid"


def _account_auth_error(status: str) -> JSONResponse:
    if status == "credential_conflict":
        return JSONResponse(
            {"ok": False, "error": "credential_conflict"}, status_code=409,
        )
    messages = {
        "absent": "no session", "revoked": "session revoked",
        "unlinked": "email confirmation required",
        "retired": "session retired; sign in again",
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

@router.post(
    "/auth/request-link",
    response_model=RequestLinkResponse,
    summary="Request a magic-link email",
)
async def request_link(body: RequestLinkBody, request: Request):
    """Generate and deliver a one-time magic-link token.

    Production sends through the configured SMTP transport and fails closed
    when delivery is unavailable. Tests may inject an isolated outbox sender.

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
    try:
        _store().add_token(
            _token_hash(token), email, now.isoformat(),
            (now + timedelta(minutes=_TOKEN_TTL_MIN)).isoformat(),
            request=request,
        )
    except DeletedCredentialError:
        # Same production acknowledgement: no account-state enumeration, no
        # new email-bearing row after the fence and no unusable email sent.
        return JSONResponse({"ok": True})

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
    except Exception as exc:
        logger.error(
            "auth.magic_link_delivery_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return JSONResponse({"ok": False, "error": "email delivery unavailable"}, status_code=503)

    logger.info("auth.magic_link_requested")

    # Dev mode: return the link inline so the frontend can show it.
    # In prod, response always omits the link (regardless of dev flag).
    body_out: dict = {"ok": True}
    if not _is_prod() and os.getenv("AUTH_DEV_MODE", "").lower() in ("1", "true", "yes"):
        body_out["dev_link"] = magic_link
        body_out["dev_token"] = token
    return JSONResponse(body_out)


@router.post(
    "/auth/verify",
    response_model=VerifyResponse,
    summary="Exchange magic-link token for session",
)
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

    store=_store()
    if store._private_auth or _is_prod():
        if __package__=='web.backend.api':from ..services.auth_registration import verify_request,register,RegistrationError
        else:from services.auth_registration import verify_request,register,RegistrationError
        try:
            bucket=opaque_identifier('auth-verify.ip',_client_ip(request),kind='ip')
            if not store.record_rate_requests([(bucket,120)]):
                return JSONResponse({'ok':False,'error':'rate limit exceeded; try again later'},status_code=429)
            with verify_request(request,store) as source:
                with register(store,source,_token_hash(token),_DEFAULT_TIER) as (user,was_created,authority):
                    jwt_token,_jti=_issue_jwt(authority=authority)
                    resp=JSONResponse({'ok':True,'user':{key:user[key] for key in ('email','tier','created_at')}})
                    resp.set_cookie(key=_COOKIE_NAME,value=jwt_token,**_cookie_args(request))
                    _clear_beta_session(resp)
            # Durable notification enqueue is inside the finalization commit.
            # Delivery/retry remains a separate explicitly configured worker.
            return resp
        except (RegistrationError,DeletedCredentialError):
            return JSONResponse({'ok':False,'error':'invalid token; request a new sign-in link'},status_code=400)
        except (PermissionError,RuntimeError,OSError,sqlite3.Error):
            return JSONResponse({'ok':False,'error':'registration unavailable; request a new sign-in link'},status_code=503)

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
        logger.warning("auth.verify_rejected")
        return JSONResponse({"ok": False, "error": "invalid token"}, status_code=400)
    if was_created:
        # User creation and durable outbox enqueue are already committed. Never
        # delay or roll back the session while SMTP/retries run in background.
        asyncio.create_task(asyncio.to_thread(
            _notify_admin_new_user, email, user["created_at"]
        ))

    # Issue JWT + set cookie.
    jwt_token, _jti = _issue_jwt(email=email, tier=user["tier"])

    logger.info("auth.verified", tier=user["tier"])

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


@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    summary="Clear session cookie + revoke jti",
)
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
    if __package__=='web.backend.api':
        from .sso import get_replay_store,resolve_beta_user
    else:
        from api.sso import get_replay_store,resolve_beta_user
    beta_user, beta_status = resolve_beta_user(request)
    resp = JSONResponse(
        {"ok": False, "error": "credential_conflict"} if beta_status == "credential_conflict"
        else {"ok": True},
        status_code=409 if beta_status == "credential_conflict" else 200,
    )
    if beta_status == "valid" and beta_user:
        ledger=get_replay_store()  # Validate before any JTI/subject revocation.
        cookie = request.cookies.get(_COOKIE_NAME)
        if cookie:
            claims = _decode_jwt(cookie)
            if claims and claims.get("jti"):
                _store().revoke(
                    claims["jti"], datetime.now(timezone.utc).isoformat(), claims.get("sub")
                )
                logger.info("auth.logout")
        if request.cookies.get("structural_beta_session"):
            ledger.revoke_subject(beta_user["id"])
    # delete_cookie matches the path the cookie was set on.
    resp.delete_cookie(key=_COOKIE_NAME, path="/")
    _clear_beta_session(resp)
    return resp


@router.get(
    "/auth/me",
    response_model=AuthMeResponse,
    summary="Return current session user",
)
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


@router.get(
    "/me/export",
    response_model=AccountExportResponse,
    summary="Export authenticated account data",
)
async def export_my_account(request: Request):
    """Export registry-declared assets for the current session only."""
    unavailable = _auth_unavailable()
    if unavailable:
        return unavailable
    user, status = resolve_account_user(request)
    if status != "valid" or not user:
        return _account_auth_error(status)
    try:
        with account_owner_transaction(user["email"]) as owner_lease:
            locked_user, locked_status = resolve_account_user(request)
            if locked_status != "valid" or not locked_user:
                return _account_auth_error(locked_status)
            if locked_user["email"].lower() != user["email"].lower():
                return _account_auth_error("credential_conflict")
            if _is_prod():
                with _favorites_authority(locked_user['email'], locked_user.get('_verified_generation'),
                        owner_lease, request=request) as authority:
                    registry = _account_registry(favorites_authority=authority)
                    data = registry.export_all(locked_user['email'])
            else:
                registry = _account_registry()
                data = registry.export_all(locked_user['email'])
    except Exception as exc:
        status_code = 503 if getattr(exc, "status", None) == 503 else 500
        if status_code == 503:
            logger.error(
                "account_data.export_unavailable",
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )
        else:
            logger.error(
                "account_data.export_failed",
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )
        return JSONResponse(
            {"ok": False, "error": "account export unavailable"},
            status_code=status_code,
        )
    logger.info("account_data.exported")
    return JSONResponse({
        "ok": True,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "assets": registry.manifest(),
        "data": data,
    })


@router.post(
    "/me/delete",
    response_model=AccountDeleteResponse,
    summary="Permanently delete authenticated account",
)
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
    job_id = None
    try:
        with account_owner_transaction(user["email"]) as owner_lease:
            # The first resolve selects the lock. Re-resolve inside it so a
            # request queued behind another deletion cannot use a stale JWT.
            locked_user, locked_status = resolve_account_user(request)
            if locked_status != "valid" or not locked_user:
                return _account_auth_error(locked_status)
            if locked_user["email"].lower() != user["email"].lower():
                return _account_auth_error("credential_conflict")
            service = _account_deletion_service()
            account = _store().user(locked_user["email"])
            if __package__=='web.backend.api':
                from ..research.paid_control import issue_authenticated_action
                from ..research.errors import ResearchError
            else:
                from research.paid_control import issue_authenticated_action
                from research.errors import ResearchError
            try:request_source=issue_authenticated_action(request,action='account-delete')
            except (ResearchError,PermissionError,ValueError):request_source=None
            try:
                job_id = service.begin_account_deletion_locked(
                    locked_user["email"], account["session_generation"],
                    _store().owner_gate_id(locked_user["email"]),
                    _account_cleanup_binding(locked_user["email"]),owner_lease=owner_lease,request_source=request_source)
                result = _run_account_deletion_locked(service, job_id,owner_lease=owner_lease)
            finally:
                if request_source is not None:request_source.close()
            removed = result["removed"]
    except Exception as exc:
        status_code = 503 if getattr(exc, "status", None) == 503 else 500
        if status_code == 503:
            logger.error(
                "account_data.delete_unavailable",
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )
        else:
            logger.error(
                "account_data.delete_failed",
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )
        payload = {"ok": False, "error": "account deletion failed"}
        if job_id is not None:
            payload.update({
                "deletion_state":"cleanup_pending", "access_ended":True,
                "message":"账户访问已停止，数据清理尚未完成。请由维护方继续既有删除任务，重新登录不会恢复旧权限。",
            })
        return JSONResponse(payload, status_code=status_code)
    tombstone = deletion_tombstone(user["email"], removed, _jwt_secret())
    try:
        _append_deletion_audit(tombstone)
    except Exception as exc:
        # Deletion already succeeded. Do not report a false failure that could
        # encourage repeated requests; alert operators without restoring PII.
        logger.error(
            "account_data.audit_write_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
    response = JSONResponse({
        "ok": True,
        "deleted_at": tombstone["deleted_at"],
        "removed": removed,
    })
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    _clear_beta_session(response)
    logger.info("account_data.deleted")
    return response


def _account_deletion_service():
    if __package__=='web.backend.api':from ..research import ResearchService,ResearchStore
    else:from research import ResearchService,ResearchStore
    return ResearchService(ResearchStore(_store()))


def _run_account_deletion_locked(service, job_id,*,owner_lease=None):
    import stat
    if __package__=='web.backend.api':
        from ..research.paid_control import verify_deletion_origin
        from ..research.authorization import OwnerGateLease
    else:
        from research.paid_control import verify_deletion_origin
        from research.authorization import OwnerGateLease
    if type(owner_lease) is not OwnerGateLease:
        raise PermissionError('actual account deletion owner lease required')
    identity=owner_lease.identity
    job = service.deletion_job(job_id)
    gate=service.store.path.parent/'research-locks'/(service._id(job['gate_id'])+'.lock')
    info=gate.lstat()
    if identity!=(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink):
        raise PermissionError('account deletion owner lease binding mismatch')
    with service.store.transaction() as conn:verify_deletion_origin(conn,store=service.store,lease=owner_lease,job_id=job_id)
    # Legacy origin is not a reason to drop the caller's actual held lock.
    lease_args={'owner_lease':owner_lease}
    if job["state"] == "completed":
        return json.loads(job["result_json"])
    if job["state"] == "scrubbing":
        return service.finish_account_deletion_locked(job_id, None,**lease_args)
    if not hmac.compare_digest(job["cleanup_binding"], _account_cleanup_binding(job["owner_email"])):
        raise RuntimeError("account deletion recovery binding mismatch")
    service.erase_research_locked(job_id,**lease_args)
    # Generic legacy compensation remains unchanged. The committed auth fence
    # and research epoch are not registry assets and cannot be restored by it.
    first,receipt = service.prepare_legacy_deletion_locked(job_id,**lease_args)
    if receipt is None:
        if _is_prod():
            if __package__=='web.backend.api':from ..services.auth_registration import deletion_scope
            else:from services.auth_registration import deletion_scope
            with _favorites_authority(job['owner_email'], job['session_generation'], owner_lease,
                    service=service, job_id=job_id) as authority, deletion_scope(service,owner_lease,job_id):
                removed = _account_registry(favorites_authority=authority).delete_all(job['owner_email'])
        else:
            removed = _account_registry().delete_all(job["owner_email"])
        receipt = service.record_legacy_deletion_locked(job_id, removed, first=first,**lease_args)
    removed = service.legacy_deletion_result(receipt)
    return service.finish_account_deletion_locked(job_id, removed,**lease_args)


def _account_cleanup_binding(email):
    """Bind recovery to the original fixed stores and SSO identity derivation.

    Persist a digest only; neither paths nor private identity material enter
    an API, ordinary log, or a user-supplied recovery argument.
    """
    if __package__=='web.backend.api':from . import favorites,report_account,sso
    else:from api import favorites,report_account,sso
    ledger = sso.get_replay_store()  # Fail before any other asset getter side effect.
    binding = {
        "auth": str(_store().path.resolve()),
        "favorites": str(favorites._data_file().resolve()),
        "favorites_legacy": str(favorites._legacy_data_file().resolve()),
        "reports": str(report_account._get_store().db_path.resolve()),
        "sso": str(ledger.path.resolve()),
        "subject": sso._subject_id(email),
        "registry": _account_registry().manifest(),
    }
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def pending_account_deletions():
    """Local control only: return bounded opaque job IDs, never user bindings."""
    with _store()._connection() as conn:
        return [row["id"] for row in conn.execute(
            "SELECT id FROM auth_deletion_jobs WHERE state!='completed' ORDER BY created_at,id LIMIT 100"
        )]


def resume_account_deletion(job_id: str):
    """Local control only: resume one persisted job in the configured auth DB.

    Not registered as HTTP/CLI user input. No email, DB path, credential,
    callback, or arbitrary action is accepted; completed jobs are idempotent.
    """
    service = _account_deletion_service()
    job = service.deletion_job(job_id)
    with service.authorization.owner_gate_id(job["gate_id"]) as owner_lease:
        return _run_account_deletion_locked(service, job_id,owner_lease=owner_lease)


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
