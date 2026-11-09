"""Candidate file-ledger adapter, executable only on an explicitly marked temp DB.

This is not a migration or a Main issuer. The proposed catalog adds a narrow
alternate trigger arm; the Native Financial9 authorizer and old arm stay intact.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

from .external_first_answer_contract import CAP_UNITS, MIN_RISK_MARGIN_UNITS, ContractError
from .external_first_answer_fixture_writer import FixtureWriter
from .external_first_answer_state import DDL, GUARD, TABLE
from .plan_native_financial import declarations, unresolved


MONEY_GUARD = "research_external_first_answer_money_allowed"
TRIGGER = "research_native_money_control"
_ACCOUNT_COLUMNS = (
    "id","binding_id","fixture_port","mode","currency","scale","funding_epoch","cap","settled","held",
    "status","snapshot_id","version","provider","initial_prepaid_units","other_use_margin_units","upper_booked",
)
_OLD = next(sql for sql in declarations() if sql.startswith("CREATE TRIGGER "+TRIGGER+" "))
_NATIVE_ARM = "research_plan_native_money_allowed(OLD.id)!=1"


def _image(side):
    return "json_array("+",".join(side+"."+name for name in _ACCOUNT_COLUMNS)+")"


def money_trigger(previous):
    """Pure migration specification; never drops an active guard by itself."""
    if previous!=_OLD or previous.count(_NATIVE_ARM)!=1:
        raise ContractError("native_catalog_not_exact")
    return previous.replace(_NATIVE_ARM, _NATIVE_ARM+
        f" AND coalesce({MONEY_GUARD}({_image('OLD')},{_image('NEW')}),0)!=1",1)


CANDIDATE_DDL = (*DDL, money_trigger(_OLD))
_TOKEN=object()
_PRODUCTION_ROOTS=tuple(Path(item) for item in (
    "/var/lib/structural-isomorphism","/var/cache/structural-isomorphism","/srv/structural-isomorphism",
))


def install_closed_hooks(conn):
    """New catalog connections must default deny without breaking the old arm."""
    from .external_first_answer_erasure import allowed_delete
    conn.create_function(GUARD,3,lambda *values:allowed_delete(conn,*values))
    conn.create_function(MONEY_GUARD,2,lambda *_:0)


def require_closed_hooks(conn):
    # A closed reader never receives an admitted grant.
    row=conn.execute(f"SELECT {GUARD}('INSERT',NULL,NULL),{MONEY_GUARD}(NULL,NULL)").fetchone()
    if tuple(row)!=(0,0):
        raise ContractError("external_connection_not_closed")


def unresolved_external(conn,account,*,excluding=None):
    """Candidate reciprocal check for old callers; not wired into Financial9."""
    return conn.execute("SELECT 1 FROM "+TABLE+" WHERE account_id=? AND id IS NOT ? AND state IN ('consumed','unknown') LIMIT 1",
                        (account,excluding)).fetchone() is not None



@dataclass(frozen=True, slots=True, repr=False)
class _TempLedgerProof:
    path: Path
    identity: tuple
    token: object


def _identity(path):
    entry=path.stat(follow_symlinks=False)
    if not stat.S_ISREG(entry.st_mode) or entry.st_uid!=os.geteuid() or stat.S_IMODE(entry.st_mode)!=0o600 or entry.st_nlink!=1:
        raise ContractError("isolated_file_identity")
    return entry.st_dev,entry.st_ino


def approve_isolated_file(path):
    """Explicit test enrollment only; cannot bind a formal production path."""
    if type(path) is not type(Path()) or path.resolve(strict=True)!=path:
        raise ContractError("isolated_file_identity")
    root=Path(tempfile.gettempdir()).resolve(strict=True)
    if not path.is_relative_to(root) or path.parent==root or any(path.is_relative_to(p) for p in _PRODUCTION_ROOTS):
        raise ContractError("isolated_file_required")
    folder=path.parent.stat(follow_symlinks=False)
    if not stat.S_ISDIR(folder.st_mode) or folder.st_uid!=os.geteuid() or stat.S_IMODE(folder.st_mode)!=0o700:
        raise ContractError("isolated_file_required")
    marker=path.with_name("STRUCTURE-EXTERNAL-LEDGER-FIXTURE")
    _identity(marker)
    if marker.read_bytes()!=b"isolated external ledger candidate, no provider\n":
        raise ContractError("isolated_marker_required")
    return _TempLedgerProof(path,_identity(path),_TOKEN)


class CandidateFileWriter(FixtureWriter):
    """Candidate transaction implementation, not available through Main."""

    def __init__(self, conn, proof):
        if type(conn) is not sqlite3.Connection or conn.in_transaction or type(proof) is not _TempLedgerProof or proof.token is not _TOKEN:
            raise ContractError("external_file_proof_required")
        self.conn,self._proof=conn,proof
        self._expect=self._money=None
        self._verify_database()
        conn.execute("PRAGMA foreign_keys=ON")
        conn.create_function(GUARD,3,self._allow_run)
        conn.create_function(MONEY_GUARD,2,self._allow_external_money)

    def _verify_database(self):
        dbs={name:path for _,name,path in self.conn.execute("PRAGMA database_list")}
        if dbs.get("main")!=str(self._proof.path) or set(dbs)-{"main","temp"} or _identity(self._proof.path)!=self._proof.identity:
            raise ContractError("external_file_identity_changed")
        actual=self.conn.execute("SELECT sql FROM sqlite_schema WHERE type='trigger' AND name=?",(TRIGGER,)).fetchone()
        if not actual or actual[0]!=money_trigger(_OLD):
            raise ContractError("external_file_catalog_unbound")

    def _allow_external_money(self,before,after):
        if not self.conn.in_transaction or self._money is None:
            return 0
        import json
        try:
            old,new=json.loads(before),json.loads(after)
            if len(old)!=len(_ACCOUNT_COLUMNS) or len(new)!=len(_ACCOUNT_COLUMNS):
                return 0
            fields=dict(zip(_ACCOUNT_COLUMNS,old))
            current=dict(zip(_ACCOUNT_COLUMNS,new))
            if {k for k in fields if fields[k]!=current[k]}-{"held","upper_booked","version"}:
                return 0
            return int(self._money==(fields["id"],fields["held"],current["held"],
                fields["upper_booked"],current["upper_booked"],current["version"])
                and current["version"]==fields["version"]+1)
        except (TypeError,ValueError):
            return 0

    def _account(self,grant):
        account=super()._account(grant)
        funding=self.conn.execute("""SELECT account_id,economic_binding,approved_cap_units,risk_margin_units,
                   state,principal_id,generation FROM research_plan_native_funding WHERE id=1""").fetchone()
        if funding is None or tuple(funding)!=(grant.account_id,grant.binding,CAP_UNITS,MIN_RISK_MARGIN_UNITS,
                "authorized",grant.scope.principal_id,grant.scope.auth_generation):
            raise ContractError("existing_native_ledger_binding_changed")
        return account

    def reserve(self,run_id,grant,scope,*,now):
        # Existing Native reconciliation is checked inside the same write
        # transaction as the cap, not via an independent observation.
        return self._with_original_funding(super().reserve,run_id,grant,scope,now=now)

    def consume(self,run_id,grant,scope,*,now):
        return self._with_original_funding(super().consume,run_id,grant,scope,now=now)

    def _with_original_funding(self,step,run_id,grant,scope,*,now):
        # Rebind only the pure account read; the underlying writer still owns
        # BEGIN IMMEDIATE/commit. No callbacks are accepted from the caller.
        self._check_legacy_unknown=True
        try:return step(run_id,grant,scope,now=now)
        finally:self._check_legacy_unknown=False

    def _fence(self,grant,scope):
        super()._fence(grant,scope)
        if getattr(self,"_check_legacy_unknown",False) and unresolved(self.conn,grant.account_id):
            raise ContractError("legacy_unknown_reconcile_only")
