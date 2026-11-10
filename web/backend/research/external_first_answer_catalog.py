"""Exact v17 candidate maintenance and read-only bridge. No Main admission."""
from contextlib import closing, contextmanager
import sqlite3

from .authorization import AccountIdentity, AuthorizationGate
from .errors import ResearchError, not_found
from .external_first_answer_contract import ContractError, SavedRevisionScope, OUTPUT_SCHEMA, parse_unverified_candidate, prepare_closed_public_preview
from .external_first_answer_file_writer import (
    CANDIDATE_DDL, TRIGGER, _TempLedgerProof, _TOKEN, _identity, money_trigger,
)
from .external_first_answer_state import TABLE
from .financial_guard import install_default_hook
from .formula_runtime import FormulaMaintenance, _OfflineFormulaTarget, _check_profile, _offline_maintenance
from .provider_schemas import canonical, digest
from .service import ResearchService
from .store import ResearchStore

_STATE={
    "confirmed":"pending", "reserved":"accepted", "consumed":"unknown",
    "unknown":"unknown", "returned":"completed", "closed_unsent":"not_sent",
}
PUBLIC_CONTRACT="external-first-answer-v1"


def _apply_catalog(target, cap, versions):
    cap.require(target)
    conn = cap.conn
    conn.execute("BEGIN EXCLUSIVE")
    try:
        version = _check_profile(conn, target, versions)
        if version == 16:
            original = conn.execute("SELECT sql FROM sqlite_schema WHERE type='trigger' AND name=?", (TRIGGER,)).fetchone()
            if original is None or money_trigger(original[0]) != CANDIDATE_DDL[-1]:
                raise ContractError("native_catalog_not_exact")
            for statement in CANDIDATE_DDL[:-1]:
                conn.execute(statement)
            conn.execute("DROP TRIGGER " + TRIGGER)
            conn.execute(CANDIDATE_DDL[-1])
            if conn.execute("UPDATE research_schema SET version=17 WHERE id=1 AND version=16").rowcount != 1:
                raise ContractError("external_catalog_CAS_failed")
        ResearchStore._check_v17(conn)
        cap.require(target)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def apply_closed_v17_maintenance(target, capability):
    """Consume an already-held canonical offline v16 capability; never open a path."""
    if (type(target) is not _OfflineFormulaTarget or type(capability) is not FormulaMaintenance
            or capability.source_version != 16):
        raise ContractError("external_offline_maintenance_required")
    _apply_catalog(target, capability, (16,))
    return {"schema": 17, "external_first_answer": "status_only", "may_send": False}


def provision_isolated_v17(proof):
    """Fixture-only entry; the marked private temp proof remains mandatory."""
    if type(proof) is not _TempLedgerProof or proof.token is not _TOKEN or _identity(proof.path) != proof.identity:
        raise ContractError("external_file_proof_required")
    with _offline_maintenance(proof.path, (16, 17)) as (target, cap):
        _apply_catalog(target, cap, (16, 17))
    if _identity(proof.path) != proof.identity:
        raise ContractError("external_file_identity_changed")
    return {"schema": 17, "external_first_answer": "status_only", "database_same_inode": True, "may_send": False}


def _snapshot(proof,conn):
    if type(proof) is not _TempLedgerProof or proof.token is not _TOKEN or _identity(proof.path)!=proof.identity:
        raise ContractError("external_file_proof_required")
    ResearchStore._check_v17(conn)


def inspect_closed_bridge(proof):
    """Check current physical catalog with the exact old and new guards closed."""
    if type(proof) is not _TempLedgerProof or proof.token is not _TOKEN:
        raise ContractError("external_file_proof_required")
    with closing(sqlite3.connect(proof.path.as_uri()+"?mode=ro",uri=True,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row
        install_default_hook(conn)
        conn.execute("BEGIN")
        _snapshot(proof,conn)
        conn.rollback()
    return {"schema":17,"external_first_answer":"status_only","may_send":False}


def project_status(row,scope,operation_key):
    """Project only the authorized original durable row; never infer absence."""
    if not row or type(scope) is not SavedRevisionScope:
        raise not_found()
    if (row["id"],row["research_id"],row["principal_id"],row["input_revision"],row["research_version"],row["scope_digest"]) != (
            operation_key,scope.research_id,scope.principal_id,scope.input_revision,scope.research_version,
            digest(canonical(scope.model_dump(mode="json")))):
        raise not_found()
    status=_STATE.get(row["state"])
    if status is None:
        raise not_found()
    return {"contract_revision":PUBLIC_CONTRACT,
            "metadata":{k:getattr(scope,k) for k in ("research_id","input_revision","research_version","problem_digest")},
            "operation_key":operation_key,"status":status}


@contextmanager
def _read_bridge_row(proof,identity,research_id,revision,operation_key):
    if type(identity) is not AccountIdentity:
        raise PermissionError("canonical owner identity required")
    if type(proof) is not _TempLedgerProof or proof.token is not _TOKEN:
        raise ContractError("external_file_proof_required")
    if type(revision) is not int or not 1<=revision<=2147483647:
        raise ResearchError("INPUT_INVALID",422,"无效的问题修订。")
    rid,key=ResearchService._id(research_id),ResearchService._id(operation_key)
    if __package__=='web.backend.research':
        from ..services.sqlite_utils import connect_private_auth
    else:
        from services.sqlite_utils import connect_private_auth
    # Existing Auth/ResearchStore constructors deliberately still refuse v17.
    # Bind the isolated read connection and use only the existing gate reads.
    gate=AuthorizationGate(None)
    with closing(connect_private_auth(proof.path,readonly=True,timeout=2,expected_identity=proof.identity)) as conn:
        conn.row_factory=sqlite3.Row
        install_default_hook(conn)
        conn.execute("BEGIN")
        _snapshot(proof,conn)
        yield _authorized_row(conn,gate,identity,rid,revision,key)


def _authorized_row(conn,gate,identity,rid,revision,key):
    gate.check_account(conn,identity)
    principal=conn.execute("SELECT id FROM research_principals WHERE normalized_email=? AND session_generation=?",
                           (identity.email,identity.generation)).fetchone()
    if principal is None:
        raise not_found()
    owner=gate.check(conn,identity,principal[0])
    control=gate.check(conn,identity,principal[0],rid)
    row=conn.execute("SELECT id,research_id,principal_id,input_revision,research_version,scope_digest,state,candidate_digest,candidate_json FROM "+TABLE+
                     " WHERE id=? AND research_id=? AND principal_id=? AND input_revision=?",
                     (key,rid,principal[0],revision)).fetchone()
    saved=conn.execute("SELECT digest FROM research_revisions WHERE research_id=? AND revision=?",(rid,revision)).fetchone()
    if row is None or saved is None:
        raise not_found()
    scope=SavedRevisionScope(principal_id=principal[0],auth_generation=identity.generation,
         principal_epoch=owner["epoch"],owner_epoch=control["owner_epoch"],acl_epoch=control["acl_epoch"],
         research_id=rid,input_revision=revision,research_version=row["research_version"],problem_digest=saved["digest"])
    return row,scope,key


def read_bridge_status(proof,identity,research_id,revision,operation_key):
    """Read-only seam for a future GET; no HTTP registration or resend."""
    with _read_bridge_row(proof,identity,research_id,revision,operation_key) as (row,scope,key):
        return project_status(row,scope,key)


def project_result(row,scope,operation_key):
    status=project_status(row,scope,operation_key)
    if status["status"]!="completed" or not isinstance(row["candidate_json"],str):
        raise not_found()
    try:
        import json
        raw=row["candidate_json"].encode("utf-8")
        stored=json.loads(raw)
        if digest(raw)!=row["candidate_digest"] or canonical(stored)!=raw:
            raise ValueError()
        parsed=parse_unverified_candidate(canonical(stored["candidate"]))
        if parsed!=stored:
            raise ValueError()
    except (KeyError,TypeError,ValueError,UnicodeError):
        raise not_found() from None
    return {k:v for k,v in status.items() if k!="status"}|{"result_digest":row["candidate_digest"],
            "schema":OUTPUT_SCHEMA,"review_required":True,"candidate":parsed["candidate"]}


def read_bridge_result(proof,identity,research_id,revision,operation_key):
    with _read_bridge_row(proof,identity,research_id,revision,operation_key) as (row,scope,key):
        return project_result(row,scope,key)


def read_main_recovery(service, identity, research_id, revision, operation_key, *, result=False):
    """Use the real admitted store; no fixture proof, issuer or write access."""
    if type(service) is not ResearchService or type(identity) is not AccountIdentity:
        raise PermissionError("canonical research service and identity required")
    rid,key=service._id(research_id),service._id(operation_key)
    with service.store.transaction() as conn:
        if conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()[0]!=17:
            return None
        row,scope,key=_authorized_row(conn,service.authorization,identity,rid,revision,key)
        return (project_result if result else project_status)(row,scope,key)


def project_owner_recovery(conn, gate, identity, control):
    """Locate an existing current-revision run under the caller's owner gate.

    This read grants no send authority and preserves the run's original version.
    The ordinary authorized-row checks still validate every saved scope field.
    """
    rows=conn.execute("SELECT id FROM "+TABLE+" WHERE research_id=? AND input_revision=? LIMIT 2",
                      (control['id'],control['current_revision'])).fetchall()
    if len(rows)!=1:
        return None
    try:
        row,scope,key=_authorized_row(conn,gate,identity,control['id'],control['current_revision'],rows[0]['id'])
        return project_status(row,scope,key)
    except ResearchError as exc:
        if exc.code!='NOT_FOUND':raise
        return None


def project_closed_preview(scope, saved_problem, quote, *, now):
    return prepare_closed_public_preview(scope, saved_problem, quote, now=now)


def require_dispatch_admission():
    raise ResearchError("FEATURE_UNAVAILABLE",503,"外部后备分析尚未开启；已保存问题不受影响。")
