"""Read-only bridge to the existing owner, revision and Native ledger.

No HTTP route, confirmation row, new task or dispatch entry is registered.
The external fallback stays closed even after valid explicit confirmation.
"""
from contextlib import contextmanager

from .authorization import AccountIdentity
from .errors import ResearchError, not_found
from .external_first_answer_contract import (
    CAP_UNITS, MIN_RISK_MARGIN_UNITS, compare_confirmation, prepare_closed_preview,
)
from .plan_native_financial import unresolved
from .service import ResearchService


@contextmanager
def _authorized_saved_revision(service, identity, research_id, revision, research_version):
    if type(service) is not ResearchService or type(identity) is not AccountIdentity:
        raise PermissionError("canonical research identity required")
    if any(type(value) is not int or not 1 <= value <= 2147483647 for value in (revision, research_version)):
        raise ResearchError("INPUT_INVALID", 422, "请使用已保存的问题修订。")
    rid = service._id(research_id)
    pid = service._principal(identity)
    with service.authorization.owner_gate(pid) as lease, service.store.transaction() as conn:
        lease.identity
        owner = service.authorization.check(conn, identity, pid)
        control = service.authorization.check(conn, identity, pid, rid, scope="write")
        service.authorization.check(conn, identity, pid, rid)
        if (control["current_revision"], control["version"]) != (revision, research_version):
            raise ResearchError("REVISION_CONFLICT", 409, "问题已变化，请重新预览。")
        saved = conn.execute("SELECT problem_json,digest FROM research_revisions WHERE research_id=? AND revision=?",
                             (rid, revision)).fetchone()
        if not saved:
            raise not_found()
        from .external_first_answer_contract import SavedRevisionScope
        scope = SavedRevisionScope(principal_id=pid, auth_generation=identity.generation,
            principal_epoch=owner["epoch"], owner_epoch=control["owner_epoch"], acl_epoch=control["acl_epoch"],
            research_id=rid, input_revision=revision, research_version=research_version, problem_digest=saved["digest"])
        yield conn, scope, saved["problem_json"].encode("utf-8")


def preview_saved_question(service, identity, research_id, revision, research_version, quote, *, now):
    with _authorized_saved_revision(service, identity, research_id, revision, research_version) as (_, scope, raw):
        return prepare_closed_preview(scope, raw, quote, now=now)


def _ledger_reason(conn, scope, quote):
    # Read the existing shared Native account. A row cannot authorize a new
    # provider purpose, and no legacy/offline resolver can fill a missing row.
    row = conn.execute("""SELECT f.state, f.principal_id, f.generation, f.account_id, f.economic_binding,
                                 f.approved_cap_units, f.risk_margin_units, a.binding_id, a.funding_epoch,
                                 a.provider, a.currency, a.scale
                          FROM research_plan_native_funding f
                          JOIN research_funding_accounts a ON a.id=f.account_id WHERE f.id=1""").fetchone()
    if not row or row["state"] != "authorized" or (row["principal_id"], row["generation"]) != (
            scope.principal_id, scope.auth_generation):
        return "shared_funding_closed"
    if ((row["account_id"], row["economic_binding"], row["funding_epoch"]) !=
            (quote.account_id, quote.economic_binding, quote.funding_epoch)
            or row["binding_id"] != row["economic_binding"]
            or (row["provider"], row["currency"], row["scale"], row["approved_cap_units"]) !=
            ("deepseek", "CNY", 6, CAP_UNITS) or row["risk_margin_units"] < MIN_RISK_MARGIN_UNITS):
        return "shared_ledger_mismatch"
    if unresolved(conn, row["account_id"]):
        return "unknown_reconcile_only"
    return "external_purpose_not_admitted"


def check_saved_confirmation(service, identity, research_id, revision, research_version,
                             preview, quote, confirmation, *, now):
    """Check the real saved revision and ledger under the same read snapshot."""
    with _authorized_saved_revision(service, identity, research_id, revision, research_version) as (conn, scope, raw):
        compare_confirmation(preview, scope, raw, quote, confirmation, now=now)
        return {"state":"closed", "reason":_ledger_reason(conn, scope, quote),
                "may_reserve":False, "may_send":False, "result_ref":None}
