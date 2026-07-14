"""Account ownership and anonymous-report migration endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
    from .auth import account_owner_transaction
    from .sso import (
        SsoReplayStore, _data_dir, _subject_id, require_beta_origin,
        resolve_anon_proof, resolve_beta_user, set_anon_proof,
    )
    from ..services.report_store import ReportStore
else:
    from logging_config import get_logger, new_incident_id
    from api.auth import account_owner_transaction
    from api.sso import (
        SsoReplayStore, _data_dir, _subject_id, require_beta_origin,
        resolve_anon_proof, resolve_beta_user, set_anon_proof,
    )
    from services.report_store import ReportStore

router = APIRouter(tags=["report-account"])
_store: Optional[ReportStore] = None
logger = get_logger("structural.report_account")


class AnonProofResponse(BaseModel):
    ok: Literal[True]


class ReportClaimResponse(BaseModel):
    ok: Literal[True]
    claimed: int = Field(ge=0)
    owned_total: int = Field(ge=0)
    conflicts: Literal[0]


class AccountReportItem(BaseModel):
    id: str
    query: str
    b_id: str
    lang: str
    created_at: str
    view_count: int = Field(ge=0)
    claimed_at: Optional[str] = None
    has_followup: bool
    followup_status: str
    followup_outcome: str
    origin_candidate: Optional[dict[str, object]] = None
    experiment_status: str
    experiment_deadline: Optional[str] = None
    publish_to_insights: bool
    consent_version: Optional[str] = None
    consented_at: Optional[str] = None
    withdrawn_at: Optional[str] = None


class AccountReportsResponse(BaseModel):
    items: list[AccountReportItem]
    has_more: bool


class ConsentWithdrawalResponse(BaseModel):
    ok: Literal[True]
    report_id: str
    publish_to_insights: Literal[False]
    consent_version: Optional[str] = None
    consented_at: Optional[str] = None
    withdrawn_at: Optional[str] = None


class OwnedReportDeleteResponse(BaseModel):
    ok: Literal[True]
    report_id: str
    reports: Literal[1]
    followups: int = Field(ge=0)
    feedback: int = Field(ge=0)
    share_revoked: Literal[True]


def _beta_auth_error(status: str) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    if status == "credential_conflict":
        return JSONResponse(
            {"ok": False, "error": "credential_conflict"}, status_code=409,
            headers=headers,
        )
    return JSONResponse(
        {"ok": False, "error": "valid beta session required"}, status_code=401,
        headers=headers,
    )


def _get_store() -> ReportStore:
    global _store
    if _store is None:
        _store = ReportStore(Path(__file__).parent.parent / "data" / "history.db")
    return _store


def _revalidate_beta_owner(
    request: Request, expected: dict,
) -> tuple[dict | None, str]:
    current, status = resolve_beta_user(request)
    if status != "valid" or not current:
        return None, status
    if (
        current["id"] != expected["id"]
        or current["email"].lower() != expected["email"].lower()
    ):
        return None, "credential_conflict"
    return current, "valid"


def export_account_reports(email: str) -> dict:
    subject = _subject_id(email)
    ledger = SsoReplayStore(_data_dir() / "sso_replay.sqlite3")
    snapshot = _get_store().export_by_owner(subject)
    snapshot["sso_revoked_at"] = ledger.subject_revoked_at(subject)
    snapshot["sso_identity_binding"] = ledger.export_subject_binding(subject)
    snapshot["sso_exchange_events"] = [
        {
            "tier": row["tier"],
            "expires_at": row["expires_at"],
            "consumed_at": row.get("consumed_at"),
        }
        for row in ledger.export_issued_for_subject(subject)
    ]
    return snapshot


def snapshot_account_reports(email: str) -> dict:
    """Private compensation state, including opaque SSO exchange rows."""
    subject = _subject_id(email)
    ledger = SsoReplayStore(_data_dir() / "sso_replay.sqlite3")
    snapshot = _get_store().export_by_owner(subject)
    snapshot["sso_revoked_at"] = ledger.subject_revoked_at(subject)
    snapshot["sso_identity_binding"] = ledger.export_subject_binding(subject)
    snapshot["sso_issued_codes"] = ledger.export_issued_for_subject(subject)
    return snapshot


def delete_account_reports(email: str) -> dict:
    subject = _subject_id(email)
    ledger = SsoReplayStore(_data_dir() / "sso_replay.sqlite3")
    previous = ledger.subject_revoked_at(subject)
    revoked_at = ledger.revoke_subject(subject)
    report_snapshot = _get_store().export_by_owner(subject)
    binding_snapshot = ledger.export_subject_binding(subject)
    issued_snapshot = ledger.export_issued_for_subject(subject)
    try:
        removed = _get_store().delete_by_owner(subject)
        ledger.delete_subject_binding(subject)
        issued_removed = ledger.delete_issued_for_subject(subject)
    except Exception:
        _get_store().restore_owner_snapshot(report_snapshot)
        ledger.restore_subject_revocation(subject, previous, revoked_at)
        ledger.restore_subject_binding(subject, binding_snapshot)
        ledger.restore_issued(issued_snapshot)
        raise
    return {
        **removed, "beta_sessions_revoked_at": revoked_at,
        "sso_identity_bindings": int(binding_snapshot.get("exists", False)),
        "sso_exchange_codes": issued_removed,
    }


def restore_account_reports(email: str, snapshot: dict, removed: object = None) -> None:
    subject = _subject_id(email)
    _get_store().restore_owner_snapshot(snapshot)
    applied = removed.get("beta_sessions_revoked_at") if isinstance(removed, dict) else None
    if applied is not None:
        SsoReplayStore(_data_dir() / "sso_replay.sqlite3").restore_subject_revocation(
            subject, snapshot.get("sso_revoked_at"), applied,
        )
    binding = snapshot.get("sso_identity_binding")
    if isinstance(binding, dict):
        SsoReplayStore(_data_dir() / "sso_replay.sqlite3").restore_subject_binding(
            subject, binding,
        )
    codes = snapshot.get("sso_issued_codes")
    if isinstance(codes, list):
        SsoReplayStore(_data_dir() / "sso_replay.sqlite3").restore_issued(codes)


@router.post(
    "/reports/anon-proof",
    response_model=AnonProofResponse,
    summary="Bind this browser's existing anonymous reports",
)
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


@router.post(
    "/me/reports/claim",
    response_model=ReportClaimResponse,
    summary="Claim reports proved to belong to this browser",
)
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
    with account_owner_transaction(user["email"]):
        locked_user, locked_status = _revalidate_beta_owner(request, user)
        if locked_status != "valid" or not locked_user:
            return _beta_auth_error(locked_status)
        result = _get_store().claim_by_anon(anon_id, locked_user["id"])
    if result["conflicts"]:
        return JSONResponse({"ok": False, "error": "ownership conflict", **result}, status_code=409)
    return {"ok": True, **result}


@router.get(
    "/me/reports",
    response_model=AccountReportsResponse,
    response_model_exclude_none=True,
    summary="List reports owned by the signed-in account",
)
async def list_account_reports(
    request: Request,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user, status = resolve_beta_user(request)
    if status != "valid" or not user:
        return _beta_auth_error(status)
    rows = _get_store().list_by_owner(user["id"], limit=limit + 1, offset=offset)
    # Return through FastAPI's response-model serializer.  A raw JSONResponse
    # bypasses AccountReportsResponse and could expose a future store column
    # (including a capability) without a code review at this boundary.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {"items": rows[:limit], "has_more": len(rows) > limit}


@router.delete(
    "/me/reports/{report_id}/insights-consent",
    response_model=ConsentWithdrawalResponse,
    summary="Withdraw aggregate-insights consent for an owned report",
)
async def withdraw_report_insights_consent(report_id: str, request: Request):
    """Let an account owner revoke consent from any authenticated device."""
    origin_error = require_beta_origin(request)
    if origin_error:
        return origin_error
    user, status = resolve_beta_user(request)
    if status != "valid" or not user:
        return _beta_auth_error(status)
    with account_owner_transaction(user["email"]):
        locked_user, locked_status = _revalidate_beta_owner(request, user)
        if locked_status != "valid" or not locked_user:
            return _beta_auth_error(locked_status)
        try:
            result = _get_store().withdraw_insights_consent_by_owner(
                report_id, locked_user["id"],
            )
        except PermissionError:
            return JSONResponse(
                {"ok": False, "error": "report not found"}, status_code=404,
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
    return JSONResponse(
        {"ok": True, **result},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.delete(
    "/me/reports/{report_id}",
    response_model=OwnedReportDeleteResponse,
    summary="Permanently delete one account-owned report",
)
async def delete_owned_report(report_id: str, request: Request):
    """Permanently delete one owned report and invalidate its share URL."""
    origin_error = require_beta_origin(request)
    if origin_error:
        return origin_error
    user, status = resolve_beta_user(request)
    if status != "valid" or not user:
        return _beta_auth_error(status)
    with account_owner_transaction(user["email"]):
        locked_user, locked_status = _revalidate_beta_owner(request, user)
        if locked_status != "valid" or not locked_user:
            return _beta_auth_error(locked_status)
        try:
            result = _get_store().delete_report_by_owner(
                report_id, locked_user["id"],
            )
        except PermissionError:
            return JSONResponse(
                {"ok": False, "error": "report not found"}, status_code=404,
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        except Exception as exc:
            logger.error(
                "structural.report.account_delete_failed",
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )
            raise
    logger.info(
        "structural.report.account_deleted",
        count=result["followups"] + result["feedback"],
    )
    return JSONResponse(
        {"ok": True, "report_id": report_id, **result},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
