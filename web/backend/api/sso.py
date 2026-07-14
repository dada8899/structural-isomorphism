"""Short-lived, one-time Phase-to-beta account exchange.

The URL carries only a two-minute exchange code. Long-lived sessions remain
HttpOnly cookies scoped to their own host; share tokens never enter this flow.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from urllib.parse import urlsplit

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

if __package__ == "web.backend.api":
    from .auth import (
        account_is_active, account_owner_transaction, require_same_origin,
        resolve_session_user,
    )
    from ..services.sso_store import SsoReplayStore
else:
    from api.auth import (
        account_is_active, account_owner_transaction, require_same_origin,
        resolve_session_user,
    )
    from services.sso_store import SsoReplayStore

router = APIRouter(tags=["sso"])
_ALG = "HS256"
_STATE_COOKIE = "structural_sso_state"
_BETA_SESSION_COOKIE = "structural_beta_session"
_ANON_PROOF_COOKIE = "structural_anon_proof"
_CODE_TTL = 120
_STATE_TTL = 300
_SESSION_TTL = 30 * 24 * 3600


def _secret() -> str:
    value = os.getenv("STRUCTURAL_SSO_SECRET", "")
    normalized = value.strip().lower()
    unsafe = any(marker in normalized for marker in ("replace", "change-me", "example", "test-secret", "dev-"))
    if value and (os.getenv("STRUCTURAL_ENV", "dev").lower() != "prod" or (
        len(value) >= 32 and len(set(value)) >= 12 and not unsafe
    )):
        return value
    if os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod":
        raise RuntimeError("STRUCTURAL_SSO_SECRET must be high-entropy in production")
    return "dev-structural-sso-secret-at-least-32-characters"


def _phase_origin() -> str:
    return _validate_origin(
        os.getenv("STRUCTURAL_SSO_PHASE_ORIGIN", "https://phase.bytedance.city"),
        "https://phase.bytedance.city",
    )


def _beta_origin() -> str:
    return _validate_origin(
        os.getenv("STRUCTURAL_SSO_BETA_ORIGIN", "https://beta.structural.bytedance.city"),
        "https://beta.structural.bytedance.city",
    )


def _data_dir() -> Path:
    configured = os.getenv("STRUCTURAL_SSO_DATA_DIR", "").strip()
    if configured:
        return Path(configured)
    if os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod":
        raise RuntimeError("STRUCTURAL_SSO_DATA_DIR is required in production")
    return Path(os.getenv("AUTH_DATA_DIR", Path(__file__).parent.parent / "data"))


def _validate_origin(value: str, canonical: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in ({"https"} if os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod" else {"http", "https"}):
        raise RuntimeError("SSO origin must use an allowed scheme")
    if not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
        raise RuntimeError("SSO origin must be a bare origin")
    if os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod" and value.rstrip("/") != canonical:
        raise RuntimeError("SSO production origin is not canonical")
    return value.rstrip("/")


def _subject_id(email: str) -> str:
    return hmac.new(_secret().encode(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


def _cookie_args(request: Request, max_age: int) -> dict:
    return {
        "httponly": True,
        "secure": os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod" or request.url.scheme == "https",
        "samesite": "lax",
        "path": "/",
        "max_age": max_age,
    }


def _same_origin(request: Request, expected: str) -> bool:
    origin = request.headers.get("origin")
    return not origin or origin.rstrip("/") == expected


def require_beta_origin(request: Request) -> JSONResponse | None:
    if _same_origin(request, _beta_origin()):
        return None
    return JSONResponse({"ok": False, "error": "invalid origin"}, status_code=403)


class IssueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audience: str = Field(pattern=r"^structural-beta$")
    state: str = Field(min_length=32, max_length=128)
    nonce: str = Field(min_length=32, max_length=128)


class ExchangeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=32, max_length=4096)
    state: str = Field(min_length=32, max_length=128)


@router.get("/sso/start")
async def start_exchange(request: Request):
    """Bind state/nonce to the beta browser and continue on canonical Phase."""
    origin_error = require_beta_origin(request)
    if origin_error:
        return origin_error
    now = int(time.time())
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    binding = jwt.encode(
        {"iss": _beta_origin(), "aud": "structural-beta-start", "state": state, "nonce": nonce,
         "iat": now, "exp": now + _STATE_TTL},
        _secret(), algorithm=_ALG,
    )
    query = urlencode({"audience": "structural-beta", "state": state, "nonce": nonce})
    response = RedirectResponse(f"{_phase_origin()}/auth/connect?{query}", status_code=303)
    response.set_cookie(_STATE_COOKIE, binding, **_cookie_args(request, _STATE_TTL))
    return response


@router.post("/sso/issue")
async def issue_exchange_code(body: IssueBody, request: Request):
    """Issue a two-minute code from a valid Phase session."""
    origin_error = require_same_origin(request)
    if origin_error:
        return origin_error
    user, status = resolve_session_user(request)
    if status != "valid" or not user:
        return JSONResponse({"ok": False, "error": "valid session required"}, status_code=401)
    with account_owner_transaction(user["email"]):
        locked_user, locked_status = resolve_session_user(request)
        if locked_status != "valid" or not locked_user:
            return JSONResponse(
                {"ok": False, "error": "valid session required"}, status_code=401,
            )
        if locked_user["email"].lower() != user["email"].lower():
            return JSONResponse(
                {"ok": False, "error": "credential_conflict"}, status_code=409,
            )
        now = int(time.time())
        jti = uuid.uuid4().hex
        expires_at = now + _CODE_TTL
        SsoReplayStore(_data_dir() / "sso_replay.sqlite3").issue(
            jti, _subject_id(locked_user["email"]), locked_user["tier"], expires_at,
            email=locked_user["email"],
        )
        claims = {
            "iss": _phase_origin(), "aud": body.audience, "state": body.state,
            "nonce": body.nonce, "jti": jti, "iat": now, "exp": expires_at,
        }
    return {"ok": True, "code": jwt.encode(claims, _secret(), algorithm=_ALG)}


@router.post("/sso/exchange")
async def exchange_code(body: ExchangeBody, request: Request):
    """Consume a code once and establish a beta-only account session."""
    origin_error = require_beta_origin(request)
    if origin_error:
        return origin_error
    binding_token = request.cookies.get(_STATE_COOKIE, "")
    try:
        binding = jwt.decode(
            binding_token, _secret(), algorithms=[_ALG],
            audience="structural-beta-start", issuer=_beta_origin(),
        )
        code = jwt.decode(
            body.code, _secret(), algorithms=[_ALG], audience="structural-beta",
            issuer=_phase_origin(),
        )
    except jwt.PyJWTError:
        return JSONResponse({"ok": False, "error": "invalid or expired exchange"}, status_code=400)
    if body.state != binding.get("state") or code.get("state") != binding.get("state"):
        return JSONResponse({"ok": False, "error": "state mismatch"}, status_code=400)
    if not hmac.compare_digest(str(code.get("nonce", "")), str(binding.get("nonce", ""))):
        return JSONResponse({"ok": False, "error": "nonce mismatch"}, status_code=400)
    ledger = SsoReplayStore(_data_dir() / "sso_replay.sqlite3")
    code_jti = str(code.get("jti", ""))
    pending = ledger.lookup_issued(code_jti)
    if not pending:
        return JSONResponse({"ok": False, "error": "exchange already used"}, status_code=409)
    issued_email = str(pending.get("email") or "").strip().lower()
    if (
        not issued_email
        or not hmac.compare_digest(_subject_id(issued_email), pending["subject_id"])
    ):
        return JSONResponse({"ok": False, "error": "exchange identity unavailable"}, status_code=409)
    with account_owner_transaction(issued_email):
        issued = ledger.consume_issued(code_jti)
        if not issued:
            return JSONResponse({"ok": False, "error": "exchange already used"}, status_code=409)
        if (
            issued["subject_id"] != pending["subject_id"]
            or str(issued.get("email") or "").strip().lower() != issued_email
        ):
            return JSONResponse({"ok": False, "error": "exchange identity changed"}, status_code=409)
        revoked_at = ledger.subject_revoked_at(issued["subject_id"])
        issued_ns = issued.get("issued_ns")
        if (
            not account_is_active(issued_email)
            or ledger.email_for_subject(issued["subject_id"]) != issued_email
            or (
                revoked_at is not None
                and (issued_ns is None or int(issued_ns) <= revoked_at)
            )
        ):
            return JSONResponse({"ok": False, "error": "account no longer active"}, status_code=409)
        now = int(time.time())
        session = jwt.encode(
            {"iss": _beta_origin(), "aud": "structural-beta-session", "sub": issued["subject_id"],
             "tier": issued.get("tier", "free"), "jti": uuid.uuid4().hex,
             "iat": now, "issued_ns": time.time_ns(), "exp": now + _SESSION_TTL},
            _secret(), algorithm=_ALG,
        )
    response = JSONResponse({"ok": True, "user": {"id": issued["subject_id"]}})
    response.set_cookie(_BETA_SESSION_COOKIE, session, **_cookie_args(request, _SESSION_TTL))
    response.delete_cookie(_STATE_COOKIE, path="/")
    # Phase and beta may share a parent browsing journey. Never leave a direct
    # credential beside the freshly exchanged SSO credential; the resolver
    # still checks dual-cookie conflicts for races, replays and old clients.
    response.delete_cookie("phase_session", path="/")
    return response


def _resolve_direct_beta_user(request: Request) -> tuple[dict | None, str]:
    direct_user, direct_status = resolve_session_user(request)
    if direct_status != "valid" or not direct_user:
        return None, direct_status
    subject = _subject_id(direct_user["email"])
    revoked_at = SsoReplayStore(_data_dir() / "sso_replay.sqlite3").subject_revoked_at(subject)
    if revoked_at is not None and int(direct_user.get("_issued_ns", 0)) <= revoked_at:
        return None, "revoked"
    return {
        "id": subject,
        "email": direct_user["email"],
        "tier": direct_user.get("tier", "free"),
        "auth_method": "direct",
    }, "valid"


def _resolve_sso_beta_user(request: Request) -> tuple[dict | None, str]:
    token = request.cookies.get(_BETA_SESSION_COOKIE, "")
    if not token:
        return None, "absent"
    try:
        claims = jwt.decode(
            token, _secret(), algorithms=[_ALG],
            audience="structural-beta-session", issuer=_beta_origin(),
        )
    except jwt.PyJWTError:
        return None, "invalid"
    subject = str(claims.get("sub", ""))
    ledger = SsoReplayStore(_data_dir() / "sso_replay.sqlite3")
    revoked_at = ledger.subject_revoked_at(subject)
    if revoked_at is not None and int(claims.get("issued_ns", 0)) <= revoked_at:
        return None, "revoked"
    # A Phase exchange is trusted to establish the subject↔email binding.
    # Pre-migration subject-only sessions must confirm their email with a
    # fresh Phase exchange (or direct beta magic link) before email-owned
    # assets are exposed. Never guess or accept an email from the browser.
    email = ledger.email_for_subject(subject)
    if not email or not hmac.compare_digest(_subject_id(email), subject):
        return None, "unlinked"
    return {
        "id": subject,
        "email": email,
        "tier": claims.get("tier", "free"),
        "auth_method": "phase_sso",
    }, "valid"


def resolve_beta_user(request: Request) -> tuple[dict | None, str]:
    """Resolve both credentials independently, then enforce one identity.

    No credential gets priority over another. A malformed/revoked credential
    poisons the request even when the other one is valid, and two valid but
    different subjects are rejected before any account endpoint can mutate.
    """
    direct, direct_status = _resolve_direct_beta_user(request)
    sso_user, sso_status = _resolve_sso_beta_user(request)
    for status in (direct_status, sso_status):
        if status not in {"absent", "valid"}:
            return None, status
    if direct_status == "valid" and sso_status == "valid":
        if not direct or not sso_user or not hmac.compare_digest(direct["id"], sso_user["id"]):
            return None, "credential_conflict"
        return {
            **direct,
            "tier": direct.get("tier", sso_user.get("tier", "free")),
            "auth_method": "direct+phase_sso",
        }, "valid"
    if direct_status == "valid":
        return direct, "valid"
    if sso_status == "valid":
        return sso_user, "valid"
    return None, "absent"


def set_anon_proof(response: JSONResponse, request: Request, anon_id: str) -> None:
    now = int(time.time())
    proof = jwt.encode(
        {"iss": _beta_origin(), "aud": "structural-anon-proof", "sub": anon_id,
         "jti": uuid.uuid4().hex, "iat": now,
         "exp": now + _SESSION_TTL}, _secret(), algorithm=_ALG,
    )
    response.set_cookie(_ANON_PROOF_COOKIE, proof, **_cookie_args(request, _SESSION_TTL))


def resolve_anon_proof(request: Request) -> str | None:
    try:
        claims = jwt.decode(
            request.cookies.get(_ANON_PROOF_COOKIE, ""), _secret(),
            algorithms=[_ALG], audience="structural-anon-proof", issuer=_beta_origin(),
        )
    except jwt.PyJWTError:
        return None
    return str(claims.get("sub", "")) or None
