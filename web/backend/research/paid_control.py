"""Schema-v5 control boundary. No funding, upper ledger or paid producer.

Only stop has an implemented authoritative producer. Paid admission and cost
observation remain fail-closed until Core wires reviewed approval/evidence and
transport provenance. Frozen provider DTOs alone never confer authority.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import threading

from .authorization import AccountIdentity,AuthorizationGate,OwnerGateLease
from .errors import ResearchError
from .provider_schemas import CallContext,ProviderObservation,canonical,digest

UPPER_ENTRYPOINTS=("schema_requirements","reserve","authorize","consume","observe","cancel")
_FACTORY=object()
_SCOPES={}
_LOCK=threading.Lock()


@dataclass(frozen=True)
class SchemaRequirements:
    version: int
    tables: tuple[str,...]
    indexes: tuple[str,...]
    definition_digest: str


@dataclass(frozen=True)
class StopBinding:
    principal_id: str
    task_id: str
    task_version: int
    scope_digest: str
    deletion_job_id: str | None
    gate_identity: tuple[int,...]


def schema_requirements():
    from .store import PRODUCER_SCHEMA_VERSION,V5_SCHEMA,V6_SCHEMA,V6_AUX,V5_GUARDS,PRODUCER_DDL
    from .financial_guard import FINANCIAL_SCHEMA_VERSION,V7_TABLES,V7_GUARDS
    return SchemaRequirements(FINANCIAL_SCHEMA_VERSION,tuple({**V5_SCHEMA,**V6_SCHEMA})+tuple(s.split()[2] for s in (*PRODUCER_DDL,*V7_TABLES)),
        tuple(s.split()[3] for s in V6_AUX if s.startswith("CREATE UNIQUE INDEX")),
        digest(canonical({"tables":{**V5_SCHEMA,**V6_SCHEMA},"producer":PRODUCER_DDL,"aux":V6_AUX,"guards":V5_GUARDS,'v7_tables':V7_TABLES,'v7_guards':V7_GUARDS})))


class _Scope:
    def __init__(self,conn,write):
        self.conn,self.active,self.pid,self.write=conn,True,os.getpid(),write
        table=conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_project_budgets'").fetchone()
        self.financial_active=bool(table and conn.execute("SELECT 1 FROM research_project_budgets WHERE status='active'").fetchone())
        self.authorizer=None
    def refresh_authorizer(self):
        if self.authorizer is not None:self.conn.set_authorizer(self.authorizer)


@contextmanager
def _transaction_scope(conn,*,write):
    """ResearchStore registers one actual transaction, retires on end/exit."""
    if not isinstance(conn,sqlite3.Connection) or not conn.in_transaction:
        raise PermissionError("active database transaction required")
    scope=_Scope(conn,write)
    def authorizer(action,arg1,arg2,database,source):
        if action==sqlite3.SQLITE_TRANSACTION and arg1 in ("COMMIT","ROLLBACK"):
            scope.active=False
        if scope.financial_active:
            from .financial_guard import _statement_allowed
            if not _statement_allowed(conn,action,arg1,arg2):return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    def executing(statement):
        # Authorizers run at compilation and may be skipped for cached SQL.
        # Trace runs at execution, before each actual statement. After an
        # implicit OR ROLLBACK, a BEGIN or outer SAVEPOINT is observed while
        # autocommit is still true, permanently retiring the original scope.
        if not conn.in_transaction:
            scope.active=False
    with _LOCK:
        if id(conn) in _SCOPES:raise PermissionError("transaction already registered")
        _SCOPES[id(conn)]=scope
    scope.authorizer=authorizer
    conn.set_authorizer(authorizer)
    conn.set_trace_callback(executing)
    try:yield
    finally:
        scope.active=False
        with _LOCK:_SCOPES.pop(id(conn),None)
        conn.set_authorizer(None)
        conn.set_trace_callback(None)


def _current_scope(conn):
    with _LOCK:scope=_SCOPES.get(id(conn))
    if (not scope or scope.conn is not conn or not scope.active or not scope.write or scope.pid!=os.getpid()
            or not conn.in_transaction or conn.execute("PRAGMA foreign_keys").fetchone()[0]!=1
            or conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()[0] not in (5,6,7)):
        raise PermissionError("current canonical v5 transaction required")
    if conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]==7:
        from .store import ResearchStore
        ResearchStore._check_v7(conn)
    return scope


def _owner_binding(conn,store,principal_id,lease):
    from .store import ResearchStore
    if type(store) is not ResearchStore:raise PermissionError("canonical research store required")
    if type(lease) is not OwnerGateLease:raise PermissionError("actual owner lease required")
    database=next((row[2] for row in conn.execute("PRAGMA database_list") if row[1]=="main"),None)
    if not database or Path(database).resolve()!=store.path:
        raise PermissionError("canonical database binding required")
    principal=conn.execute("SELECT * FROM research_principals WHERE id=?",(principal_id,)).fetchone()
    if not principal or not principal["gate_id"]:raise PermissionError("owner binding unavailable")
    info=(store.path.parent/"research-locks"/(principal["gate_id"]+".lock")).lstat()
    identity=(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)
    if identity!=lease.identity or not stat.S_ISREG(info.st_mode):
        raise PermissionError("owner lease binding mismatch")
    return principal


class _Authority:
    __slots__=("_conn","_scope","_lease","_operation","_validate","_facts")
    def __init__(self,conn,lease,operation,validate,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError("server control producer required")
        self._conn,self._scope,self._lease=conn,_current_scope(conn),lease
        self._operation,self._validate=operation,validate
        self._facts=validate()

    def __reduce__(self):raise TypeError("authority cannot cross processes or serialization")

    def require(self,conn,operation):
        if (conn is not self._conn or _current_scope(conn) is not self._scope
                or operation!=self._operation or self._validate()!=self._facts):
            raise PermissionError("server authority stale")
        self._lease.identity
        return self._facts


class CurrentPaidAuthority(_Authority):
    """No producer until full paid approval/evidence authority is implemented."""
    __slots__=()


class TrustedCostAuthority(_Authority):
    """No producer until controlled transport/persisted response is implemented."""
    __slots__=()


@dataclass(frozen=True)
class FinancialWriteBinding:
    operation:str
    target:str
    table:str
    key:str
    before_digest:str
    version:int


class FinancialWriteAuthority(_Authority):
    """Internal single-statement permit; never built from a public DTO."""
    __slots__=()


class StopAuthority(_Authority):
    """Current owner or verified pending account deletion; no send permission."""
    __slots__=()


def mint_stop_authority(conn,*,store,lease,principal_id,task_id,expected_task_version,identity=None,deletion_job_id=None):
    _current_scope(conn)
    if type(expected_task_version) is not int or expected_task_version<1:
        raise PermissionError("exact task version required")
    def validate():
        principal=_owner_binding(conn,store,principal_id,lease)
        task=conn.execute("SELECT * FROM research_tasks WHERE id=? AND principal_id=?",(task_id,principal_id)).fetchone()
        if not task or task["version"]!=expected_task_version:raise PermissionError("stop task changed")
        if deletion_job_id is None:
            if type(identity) is not AccountIdentity:raise PermissionError("canonical account identity required")
            research=AuthorizationGate(store).check(conn,identity,principal_id,task["research_id"],scope="write")
            grant_facts=tuple(tuple(row) for row in conn.execute("SELECT id,version,status,scopes,principal_epoch,acl_epoch FROM research_grants WHERE principal_id=? AND research_id=? ORDER BY id",(principal_id,task["research_id"])))
            facts=(principal_id,principal["epoch"],principal["session_generation"],task_id,task["version"],task["input_revision"],task["input_digest"],task["stop_requested"],research["owner_epoch"],research["acl_epoch"],research["version"],grant_facts,lease.identity)
            return StopBinding(principal_id,task_id,task["version"],digest(canonical(facts)),None,lease.identity)
        job=conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'",(deletion_job_id,)).fetchone()
        if (not job or principal["status"]!="deleting" or job["owner_email"]!=principal["normalized_email"]
                or job["session_generation"]!=principal["session_generation"] or job["gate_id"]!=principal["gate_id"]
                or job["database_binding"]!=hashlib.sha256(str(store.path).encode()).hexdigest()
                or job["owner_key"]!=store.auth_store.owner_key(principal["normalized_email"])):
            raise PermissionError("verified deletion authority required")
        facts=(principal_id,principal["epoch"],task_id,task["version"],task["stop_requested"],deletion_job_id,lease.identity)
        return StopBinding(principal_id,task_id,task["version"],digest(canonical(facts)),deletion_job_id,lease.identity)
    return StopAuthority(conn,lease,"cancel",validate,_factory=_FACTORY)


def mint_current_paid_authority(conn,*,store,lease,identity,context,step_id,expected_task_version,expected_step_version,operation,approval_ref):
    _current_scope(conn)
    if type(context) is CallContext and conn.execute('SELECT version FROM research_schema').fetchone()[0] in (6,7):
        policy=conn.execute('SELECT policy_revision FROM research_tasks WHERE id=?',(context.task_id,)).fetchone()
        if policy and policy[0]=='bounded_usage_upper_v2':
            from .paid_approval import mint_current_authority
            return mint_current_authority(conn,store=store,lease=lease,identity=identity,context=context,step_id=step_id,
                expected_task_version=expected_task_version,expected_step_version=expected_step_version,operation=operation,approval_ref=approval_ref)
    if type(identity) is not AccountIdentity or type(context) is not CallContext or operation not in ("reserve","authorize","consume"):
        raise PermissionError("typed server paid context required")
    principal=_owner_binding(conn,store,context.principal_id,lease)
    gate=AuthorizationGate(store)
    gate.check(conn,identity,context.principal_id,context.research_id,scope="write")
    task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(context.task_id,)).fetchone()
    step=conn.execute("SELECT * FROM research_steps WHERE id=? AND task_id=?",(step_id,context.task_id)).fetchone()
    grant=conn.execute("SELECT * FROM research_grants WHERE id=?",(context.grant_id,)).fetchone()
    if (type(expected_task_version) is not int or type(expected_step_version) is not int or not task or not step or not grant
            or task["version"]!=expected_task_version or step["version"]!=expected_step_version
            or principal["epoch"]!=context.principal_epoch or grant["version"]!=context.grant_epoch
            or task["principal_id"]!=context.principal_id or task["principal_epoch"]!=context.principal_epoch
            or task["research_id"]!=context.research_id or task["grant_id"]!=context.grant_id
            or task["input_revision"]!=context.input_revision or task["input_digest"]!=context.input_digest
            or task["owner_epoch"]!=context.owner_epoch or task["acl_epoch"]!=context.acl_epoch
            or task["attempt"]!=context.attempt or task["policy_revision"]!="deepseek-bounded-upper-v1"
            or step["kind"]!="model_report" or task["execution"] in ("COMPLETED","FAILED","CANCELLED","ACCESS_REVOKED")):
        raise PermissionError("current paid bindings unavailable")
    gate.check_task(conn,task)
    # D1 SourceApproval does not authorize paid/model input. No approval or
    # may_send source has been reviewed/wired in this task; never fake a cap.
    raise ResearchError("FEATURE_UNAVAILABLE",503,"付费批准与证据外发授权来源尚未接通。")


def mint_trusted_cost_authority(conn,*,observation):
    _current_scope(conn)
    if type(observation) is not ProviderObservation:
        raise PermissionError("provider DTO is not transport provenance")
    raise ResearchError("FEATURE_UNAVAILABLE",503,"受控供应端费用观测来源尚未接通。")


def persist_offline_owned_source(conn,receipt):
    """Records loopback provenance only, never creates a cost capability."""
    from .paid_provider_session import persist_owned_return
    return persist_owned_return(conn,receipt)


def mint_cost_from_return(conn,*,store,lease,return_ref):
    from .paid_budget import _validated_return
    def validate():return _validated_return(conn,store,lease,return_ref)[0]
    return TrustedCostAuthority(conn,lease,'observe',validate,_factory=_FACTORY)
