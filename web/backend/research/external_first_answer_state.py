"""Candidate durable state for a distinct external first-answer purpose.

No installer, live/fixture issuer, financial writer or transport is defined
here. The DDL must remain uninstalled until a single transaction can admit
both the purpose-specific state transition and the existing shared ledger.
"""
from typing import Literal

from .external_first_answer_contract import PURPOSE, ContractError
from .provider_schemas import DTO, Digest, Id, Positive

TABLE = "research_external_first_answer_runs"
GUARD = "research_external_first_answer_write_allowed"
_TRANSITIONS = {
    "confirmed": frozenset(("reserved", "closed_unsent")),
    "reserved": frozenset(("consumed", "closed_unsent")),
    "consumed": frozenset(("unknown", "returned")),
    # A late receipt is resolved through a separately reviewed reconciliation
    # writer. An ambiguous run never regains an executable state here.
    "unknown": frozenset(),
    "returned": frozenset(),
    "closed_unsent": frozenset(),
}
_COLUMNS = (
    "id", "research_id", "principal_id", "input_revision", "research_version",
    "scope_digest", "preview_digest", "request_digest", "quote_digest",
    "account_id", "funding_epoch", "upper_units", "state", "version",
    "reservation_ref", "receipt_digest", "candidate_digest", "candidate_json",
)
_FIXED = _COLUMNS[:12]


def _image(alias):
    return "json_array(" + ",".join(alias+"."+name for name in _COLUMNS) + ")"


DDL = (
    """CREATE TABLE research_external_first_answer_runs (
        id TEXT PRIMARY KEY NOT NULL,
        research_id TEXT NOT NULL REFERENCES research_controls(id),
        principal_id TEXT NOT NULL REFERENCES research_principals(id),
        input_revision INTEGER NOT NULL CHECK(typeof(input_revision)='integer' AND input_revision BETWEEN 1 AND 2147483647),
        research_version INTEGER NOT NULL CHECK(typeof(research_version)='integer' AND research_version BETWEEN 1 AND 2147483647),
        scope_digest TEXT NOT NULL CHECK(length(scope_digest)=64 AND scope_digest NOT GLOB '*[^a-f0-9]*'),
        preview_digest TEXT NOT NULL CHECK(length(preview_digest)=64 AND preview_digest NOT GLOB '*[^a-f0-9]*'),
        request_digest TEXT NOT NULL CHECK(length(request_digest)=64 AND request_digest NOT GLOB '*[^a-f0-9]*'),
        quote_digest TEXT NOT NULL CHECK(length(quote_digest)=64 AND quote_digest NOT GLOB '*[^a-f0-9]*'),
        account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        funding_epoch INTEGER NOT NULL CHECK(typeof(funding_epoch)='integer' AND funding_epoch>0),
        upper_units INTEGER NOT NULL CHECK(typeof(upper_units)='integer' AND upper_units BETWEEN 1 AND 300000000),
        state TEXT NOT NULL CHECK(state IN ('confirmed','reserved','consumed','unknown','returned','closed_unsent')),
        version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647),
        reservation_ref TEXT UNIQUE CHECK(reservation_ref IS NULL OR reservation_ref=id),
        receipt_digest TEXT CHECK(length(receipt_digest)=64 AND receipt_digest NOT GLOB '*[^a-f0-9]*'),
        candidate_digest TEXT CHECK(length(candidate_digest)=64 AND candidate_digest NOT GLOB '*[^a-f0-9]*'),
        candidate_json TEXT CHECK(candidate_json IS NULL OR (json_valid(candidate_json) AND length(CAST(candidate_json AS BLOB))<=8192)),
        CHECK((candidate_json IS NULL)=(candidate_digest IS NULL)),
        FOREIGN KEY(research_id,input_revision) REFERENCES research_revisions(research_id,revision),
        UNIQUE(research_id,input_revision),
        CHECK((state='confirmed' AND reservation_ref IS NULL AND version=1)
           OR (state IN ('reserved','consumed','unknown','returned') AND reservation_ref IS NOT NULL)
           OR state='closed_unsent'),
        CHECK((state='returned' AND receipt_digest IS NOT NULL)
           OR (state!='returned' AND receipt_digest IS NULL AND candidate_digest IS NULL)))""",
    "CREATE INDEX research_external_first_answer_account_state ON "+TABLE+"(account_id,state)",
    "CREATE TRIGGER research_external_first_answer_insert BEFORE INSERT ON "+TABLE+
    " WHEN NEW.state!='confirmed' OR EXISTS(SELECT 1 FROM "+TABLE+" p WHERE p.rowid=NEW.rowid OR p.id=NEW.id OR "
    "(p.research_id=NEW.research_id AND p.input_revision=NEW.input_revision)) OR coalesce("+GUARD+"('INSERT',NULL,"+
    _image("NEW")+"),0)!=1 BEGIN SELECT RAISE(ABORT,'external answer insert denied'); END",
    "CREATE TRIGGER research_external_first_answer_update BEFORE UPDATE ON "+TABLE+" WHEN NEW.rowid IS NOT OLD.rowid OR "
    + " OR ".join("OLD."+name+" IS NOT NEW."+name for name in _FIXED)
    + " OR NEW.version!=OLD.version+1 OR (OLD.reservation_ref IS NOT NULL AND OLD.reservation_ref IS NOT NEW.reservation_ref)"
    + " OR NOT (" + " OR ".join(
        "(OLD.state='"+previous+"' AND NEW.state IN ("+",".join("'"+next_+"'" for next_ in sorted(allowed))+"))"
        for previous, allowed in _TRANSITIONS.items() if allowed)
    + ") OR coalesce("+GUARD+"('UPDATE',"+_image("OLD")+","+_image("NEW")+"),0)!=1"
    + " BEGIN SELECT RAISE(ABORT,'external answer transition denied'); END",
    # A future account erasure path must prove its existing dedicated owner
    # deletion authority. Deletion is not a way to release possible cost.
    "CREATE TRIGGER research_external_first_answer_delete BEFORE DELETE ON "+TABLE+
    " WHEN OLD.state IN ('reserved','consumed','unknown') OR coalesce("+GUARD+"('DELETE',"+_image("OLD")+
    ",NULL),0)!=1 BEGIN SELECT RAISE(ABORT,'external answer deletion denied'); END",
)


class StoredRunFence(DTO):
    """Inert exact saved operation facts; never a lease or consumption permit."""
    run_id: Id
    purpose: Literal["external-first-answer-question-v1"]
    scope_digest: Digest
    request_digest: Digest
    account_id: Id
    funding_epoch: Positive
    state: Literal["confirmed", "reserved", "consumed", "unknown", "returned", "closed_unsent"]
    version: Positive


def consumer_boundary(run, current_scope_digest, current_request_digest):
    """Return the only allowed next observation in the unbound build.

    An already consumed or UNKNOWN operation never re-enters dispatch.
    There is no callback, boolean, DTO or fixture path that opens a sender.
    """
    if type(run) is not StoredRunFence:
        raise ContractError("saved_external_operation_required")
    try:
        run = StoredRunFence.model_validate(run)
    except ValueError:
        raise ContractError("saved_external_operation_invalid") from None
    if run.purpose != PURPOSE:
        raise ContractError("external_purpose_mismatch")
    if run.state in ("consumed", "unknown"):
        action = "reconcile_original_only"
    elif (run.scope_digest, run.request_digest) != (current_scope_digest, current_request_digest):
        action = "binding_changed_no_send"
    elif run.state == "returned":
        action = "read_authorized_original_only"
    elif run.state == "closed_unsent":
        action = "closed_no_send"
    else:
        action = "shared_native_writer_unbound"
    return {"state":"closed", "next_action":action, "may_reserve":False, "may_consume":False, "may_send":False}
