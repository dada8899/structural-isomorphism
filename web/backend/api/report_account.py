"""Account ownership and anonymous-report migration endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

if __package__ == "web.backend.api":
    from .sso import (
        SsoReplayStore, _data_dir, _subject_id, require_beta_origin,
        resolve_anon_proof, resolve_beta_user, set_anon_proof,
    )
    from ..services.report_store import ReportStore
else:
    from api.sso import (
        SsoReplayStore, _data_dir, _subject_id, require_beta_origin,
        resolve_anon_proof, resolve_beta_user, set_anon_proof,
    )
    from services.report_store import ReportStore

router = APIRouter(tags=["report-account"])
_store: Optional[ReportStore] = None


def _beta_auth_error(status: str) -> JSONResponse:
    if status == "credential_conflict":
        return JSONResponse(
            {"ok": False, "error": "credential_conflict"}, status_code=409,
        )
    return JSONResponse(
        {"ok": False, "error": "valid beta session required"}, status_code=401,
    )


def _get_store() -> ReportStore:
    global _store
    if _store is None:
        _store = ReportStore(Path(__file__).parent.parent / "data" / "history.db")
    return _store


def export_account_reports(email: str) -> dict:
    subject = _subject_id(email)
    ledger = SsoReplayStore(_data_dir() / "sso_replay.sqlite3")
    snapshot = _get_store().export_by_owner(subject)
    snapshot["sso_revoked_at"] = ledger.subject_revoked_at(subject)
    snapshot["sso_identity_binding"] = ledger.export_subject_binding(subject)
    return snapshot


def delete_account_reports(email: str) -> dict:
    subject = _subject_id(email)
    ledger = SsoReplayStore(_data_dir() / "sso_replay.sqlite3")
    previous = ledger.subject_revoked_at(subject)
    revoked_at = ledger.revoke_subject(subject)
    report_snapshot = _get_store().export_by_owner(subject)
    try:
        removed = _get_store().delete_by_owner(subject)
        binding = ledger.delete_subject_binding(subject)
    except Exception:
        _get_store().restore_owner_snapshot(report_snapshot)
        ledger.restore_subject_revocation(subject, previous, revoked_at)
        raise
    return {
        **removed, "beta_sessions_revoked_at": revoked_at,
        "sso_identity_binding": binding,
    }


def restore_account_reports(email: str, snapshot: dict, removed: object = None) -> None:
    subject = _subject_id(email)
    _get_store().restore_owner_snapshot(snapshot)
    applied = removed.get("beta_sessions_revoked_at") if isinstance(removed, dict) else None
    if applied is not None:
        SsoReplayStore(_data_dir() / "sso_replay.sqlite3").restore_subject_revocation(
            subject, snapshot.get("sso_revoked_at"), applied,
        )
    binding = removed.get("sso_identity_binding") if isinstance(removed, dict) else None
    if isinstance(binding, dict):
        SsoReplayStore(_data_dir() / "sso_replay.sqlite3").restore_subject_binding(
            subject, binding,
        )


@router.post("/reports/anon-proof")
async def bind_current_anon(request: Request, x_anon_id: Optional[str] = Header(None)):
    """Upgrade this browser's existing opaque anon id to HttpOnly proof.

    This endpoint never accepts a report id or share token. The opaque anon id
    must already own at least one report, limiting the migration to the same
    bearer capability the legacy product used.
    """
    origin_error = require_beta_origin(request)
    if origin_error:
        return origin_error
    if not x_anon_id or len(x_anon_id) > 200 or not _get_store().has_reports_for_anon(x_anon_id):
        return JSONResponse({"ok": False, "error": "no reports for this browser"}, status_code=404)
    response = JSONResponse({"ok": True})
    set_anon_proof(response, request, x_anon_id)
    return response


@router.post("/me/reports/claim")
async def claim_current_browser_reports(request: Request):
    origin_error = require_beta_origin(request)
    if origin_error:
        return origin_error
    user, status = resolve_beta_user(request)
    if status != "valid" or not user:
        return _beta_auth_error(status)
    anon_id = resolve_anon_proof(request)
    if not anon_id:
        return JSONResponse({"ok": False, "error": "current browser proof required"}, status_code=403)
    result = _get_store().claim_by_anon(anon_id, user["id"])
    if result["conflicts"]:
        return JSONResponse({"ok": False, "error": "ownership conflict", **result}, status_code=409)
    return {"ok": True, **result}


@router.get("/me/reports")
async def list_account_reports(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user, status = resolve_beta_user(request)
    if status != "valid" or not user:
        return _beta_auth_error(status)
    rows = _get_store().list_by_owner(user["id"], limit=limit + 1, offset=offset)
    return {"items": rows[:limit], "has_more": len(rows) > limit}
