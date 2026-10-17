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
import time
from uuid import uuid4

from .authorization import AccountIdentity,AuthorizationGate,OwnerGateLease
from .errors import ResearchError
from .provider_schemas import CallContext,ProviderObservation,canonical,digest

UPPER_ENTRYPOINTS=("schema_requirements","reserve","authorize","consume","observe","cancel")
_FACTORY=object()
_SCOPES={}
_LOCK=threading.Lock()
_REQUEST_FACTORY=object()
_REQUEST_SOURCES={}


@dataclass(frozen=True)
class SsoAccountDeletionIdentity:
    """Verified SSO deletion subject; deliberately has no direct-session JTI."""
    email: str
    generation: str
    expires_at: int
    subject: str
    issued_ns: int


def _sso_deletion_ledger():
    if __package__=='web.backend.research':from ..api import sso
    else:from api import sso
    return sso,sso.get_replay_store()


class AuthenticatedActionSource:
    """Scoped result of actual route/cookie verification, never an identity DTO."""
    __slots__=('identity','action','research_id','task_id','key_digest','body_digest','pid','reference','active')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _REQUEST_FACTORY:raise TypeError('verified HTTP action source required')
        for key,value in values.items():object.__setattr__(self,key,value)
        object.__setattr__(self,'pid',os.getpid());object.__setattr__(self,'reference',str(uuid4()));object.__setattr__(self,'active',True)
        _REQUEST_SOURCES[self.reference]=self
    def __setattr__(self,*args):raise TypeError('request source immutable')
    def __reduce__(self):raise TypeError('HTTP action source cannot be serialized')
    def close(self):object.__setattr__(self,'active',False);_REQUEST_SOURCES.pop(self.reference,None)


def issue_authenticated_action(request,*,action,research_id=None,task_id=None,key='',body_digest=''):
    """Reverify the real route and credential appropriate to this action."""
    from starlette.requests import Request
    routes={'cancel':('POST','cancel_research_task'),'account-delete':('POST','delete_my_account'),
        'method-read':('GET','view_research'),'method-reconcile':('POST','reconcile_research_task'),
        'formula-check':('POST','check_research_formula'),'formula-read':('GET','read_research_formula_result'),
        'formula-revision-read':('GET','read_research_formula_revision'),
        'plan-preview':('POST','preview_research_plan'),'plan-confirm':('POST','confirm_research_plan'),'plan-read':('GET','read_research_plan'),
        'source-approve':('POST','source_approval'),'source-start':('POST','source_task')}
    if type(request) is not Request or action not in routes or request.method!=routes[action][0]:
        raise PermissionError('actual authenticated action request required')
    from .provider_schemas import strict_json
    raw=getattr(request,'_body',None)
    if action=='plan-read':
        if request.query_params:raise PermissionError('plan read query forbidden')
        research_id=request.path_params.get('research_id');task_id=request.path_params.get('result_ref');key='';body_digest=digest(b'')
    elif action in ('plan-preview','plan-confirm'):
        if type(raw) is not bytes or request.query_params:raise PermissionError('actual plan request required')
        from .plan_schemas import PlanPreviewEnvelope,PlanConfirmationEnvelope
        payload=strict_json(raw,65536)
        if payload.get('contract_revision')=='funded-plan-v2':
            from .plan_native_schemas import NativePlanPreviewEnvelope,NativePlanConfirmationEnvelope
            model=NativePlanPreviewEnvelope if action=='plan-preview' else NativePlanConfirmationEnvelope
        else:model=PlanPreviewEnvelope if action=='plan-preview' else PlanConfirmationEnvelope
        data=model.model_validate(payload).data
        research_id=request.path_params.get('research_id');task_id=None
        key=request.headers.get('idempotency-key','');body_digest=digest(canonical(data.model_dump(mode='json')))
    elif action in ('formula-read','formula-revision-read'):
        if request.query_params:raise ResearchError('INPUT_INVALID',422,'公式读取不接受查询参数。')
        research_id=request.path_params.get('research_id')
        task_id=str(request.path_params.get('result_ref' if action=='formula-read' else 'revision'))
        body_digest=digest(request.scope.get('query_string',b''));key=''
    elif action in ('source-approve','source-start'):
        if type(raw) is not bytes or request.query_params:raise PermissionError('actual Source request required')
        from .schemas import SourceApprovalEnvelope,SourceStartEnvelope
        model=SourceApprovalEnvelope if action=='source-approve' else SourceStartEnvelope
        data=model.model_validate(strict_json(raw,65536)).data
        research_id=request.path_params.get('research_id');task_id=None
        key=request.headers.get('idempotency-key','');body_digest=digest(canonical(data.model_dump(mode='json')))
    elif action=='formula-check':
        if type(raw) is not bytes or request.query_params:raise PermissionError('actual formula request required')
        from .schemas import FormulaCheckEnvelope
        data=FormulaCheckEnvelope.model_validate(strict_json(raw,65536)).data
        research_id=request.path_params.get('research_id');task_id=None
        key=request.headers.get('idempotency-key','');body_digest=digest(canonical(data.model_dump(mode='json')))
    elif action=='method-read':
        pairs=list(request.query_params.multi_items())
        if len(pairs)>1 or any(name!='task_id' or not value for name,value in pairs):
            raise ResearchError('INPUT_INVALID',422,'研究结果读取参数无效。')
        actual_research=request.path_params.get('research_id');actual_task=request.query_params.get('task_id')
        if (research_id is not None and research_id!=actual_research) or (task_id is not None and task_id!=actual_task):
            raise PermissionError('caller cannot change method read query')
        research_id,task_id=actual_research,actual_task
        body_digest=digest(request.scope.get('query_string',b''));key=''
    elif action in ('cancel','method-reconcile'):
        if type(raw) is not bytes:raise PermissionError('actual parsed request bytes required')
        if action=='method-reconcile' and request.query_params:raise ResearchError('INPUT_INVALID',422,'研究结果提交不接受查询参数。')
        from .schemas import TaskEnvelope
        data=TaskEnvelope.model_validate(strict_json(raw,65536)).data
        actual_research=request.path_params.get('research_id');actual_task=data.task_id
        actual_key=request.headers.get('idempotency-key','')
        actual_digest=digest(canonical(data.model_dump(mode='json')))
        if ((research_id is not None and research_id!=actual_research) or (task_id is not None and task_id!=actual_task)
                or (key and key!=actual_key) or (body_digest and body_digest!=actual_digest)):
            raise PermissionError('caller cannot change authenticated action target')
        research_id,task_id,key,body_digest=actual_research,actual_task,actual_key,actual_digest
    else:
        if type(raw) is not bytes:raise PermissionError('actual parsed request bytes required')
        data=strict_json(raw,65536)
        if type(data) is not dict or set(data)!={'confirmation'} or data['confirmation']!='DELETE':
            raise PermissionError('actual delete confirmation required')
    endpoint=request.scope.get('endpoint')
    expected=routes[action][1]
    if (not request.scope.get('app') or not endpoint or getattr(endpoint,'__name__',None)!=expected
            or (action!='account-delete' and request.path_params.get('research_id')!=research_id)):
        raise PermissionError('action route binding mismatch')
    if __package__=='web.backend.research':from ..api import auth
    else:from api import auth
    if action!='account-delete':
        if __package__=='web.backend.research':from ..api import research as route_module
        else:from api import research as route_module
        actual_endpoint=getattr(route_module,expected)
    else:actual_endpoint=auth.delete_my_account
    if endpoint is not actual_endpoint or getattr(request.scope.get('route'),'endpoint',None) is not actual_endpoint:
        raise PermissionError('actual action endpoint required')
    unified,status=auth.resolve_account_user(request)
    user,direct=auth.resolve_session_user(request)
    claims=auth._decode_jwt(request.cookies.get(auth._COOKIE_NAME,''))
    if status!='valid' or not unified or (request.method=='POST' and auth.require_same_origin(request) is not None):
        raise ResearchError('AUTH_REQUIRED',401,'操作来源认证失效。')
    if action=='account-delete' and direct=='absent':
        sso,_ledger=_sso_deletion_ledger()
        verified,sso_status=sso._resolve_sso_beta_user(request)
        try:
            signed=sso.jwt.decode(request.cookies.get(sso._BETA_SESSION_COOKIE,''),sso._secret(),algorithms=[sso._ALG],
                audience='structural-beta-session',issuer=sso._beta_origin())
        except sso.jwt.PyJWTError:
            raise ResearchError('AUTH_REQUIRED',401,'操作来源认证失效。') from None
        if (sso_status!='valid' or not verified or verified['email']!=unified['email']
                or type(signed.get('gen')) is not str or not signed['gen'] or signed['gen']!=verified.get('_verified_generation')
                or type(signed.get('sub')) is not str or signed['sub']!=verified['id']
                or type(signed.get('exp')) is not int or type(signed.get('issued_ns')) is not int):
            raise ResearchError('AUTH_REQUIRED',401,'操作来源认证失效。')
        identity=SsoAccountDeletionIdentity(verified['email'],signed['gen'],signed['exp'],signed['sub'],signed['issued_ns'])
    else:
        if (direct!='valid' or not user or unified['email']!=user['email'] or not claims
                or type(claims.get('exp')) is not int or not all(type(claims.get(k)) is str and claims[k] for k in ('sub','gen','jti'))):
            raise ResearchError('AUTH_REQUIRED',401,'操作来源认证失效。')
        identity=AccountIdentity(user['email'],claims['gen'],claims['jti'],claims['exp'])
    return AuthenticatedActionSource(_factory=_REQUEST_FACTORY,identity=identity,action=action,research_id=research_id,task_id=task_id,
        key_digest=digest(key.encode()),body_digest=body_digest)


def require_authenticated_action(source,*,identity,action,research_id=None,task_id=None,key=None,body_digest=None):
    if (type(source) is not AuthenticatedActionSource or not source.active or source.pid!=os.getpid()
            or _REQUEST_SOURCES.get(source.reference) is not source or not (type(identity) is AccountIdentity
                or (action=='account-delete' and type(identity) is SsoAccountDeletionIdentity))
            or source.identity!=identity or identity.expires_at<=time.time() or source.action!=action
            or source.research_id!=research_id or source.task_id!=task_id
            or (key is not None and source.key_digest!=digest(key.encode())) or (body_digest is not None and source.body_digest!=body_digest)):
        raise PermissionError('verified action source missing or stale')
    if type(identity) is SsoAccountDeletionIdentity:
        # This is the existing SSO subject-revocation ledger, never the direct
        # revoked_sessions JTI path. Recheck during each short capability use.
        _sso,ledger=_sso_deletion_ledger()
        revoked=ledger.subject_revoked_at(identity.subject)
        if revoked is not None and identity.issued_ns<=revoked:
            raise PermissionError('SSO deletion subject revoked')
    return source.reference


_ORIGIN_FIELDS=('id','owner_key','gate_id','database_binding','cleanup_binding','created_at')


def deletion_origin_digest(job):
    from .financial_guard import JOB_ORIGIN_VERSION
    return digest(canonical({'version':JOB_ORIGIN_VERSION,'job_id':job['id'],**{name:job[name] for name in _ORIGIN_FIELDS if name!='id'}}))


def _deletion_lease_binding(conn,store,lease,job):
    from .store import ResearchStore
    database=next((row[2] for row in conn.execute('PRAGMA database_list') if row[1]=='main'),None)
    if type(store) is not ResearchStore or not database or Path(database).resolve()!=store.path:
        raise PermissionError('canonical deletion database required')
    if type(lease) is not OwnerGateLease:raise PermissionError('actual deletion owner lease required')
    if job['database_binding']!=digest(str(store.path).encode()):raise PermissionError('deletion database binding changed')
    from uuid import UUID
    if str(UUID(job['gate_id'],version=4))!=job['gate_id']:raise PermissionError('deletion gate malformed')
    info=(store.path.parent/'research-locks'/(job['gate_id']+'.lock')).lstat()
    if (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)!=lease.identity:
        raise PermissionError('deletion lease does not belong to this job')


def _job_has_v2(conn,job):
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13):
        if conn.execute("SELECT 1 FROM research_source_approvals a JOIN research_principals p ON p.id=a.principal_id WHERE p.gate_id=? AND (? IS NULL OR (p.normalized_email=? AND p.session_generation=?)) LIMIT 1",(job['gate_id'],job['owner_email'],job['owner_email'],job['session_generation'])).fetchone():return True
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (10,11,12,13):
        formula=conn.execute('SELECT 1 FROM research_formula_revisions f JOIN research_controls c ON c.id=f.research_id JOIN research_principals p ON p.id=c.owner_id WHERE p.gate_id=? '+('AND p.normalized_email=? AND p.session_generation=? ' if job['owner_email'] is not None and job['session_generation'] is not None else '')+'LIMIT 1',
            (job['gate_id'],job['owner_email'],job['session_generation']) if job['owner_email'] is not None and job['session_generation'] is not None else (job['gate_id'],)).fetchone()
        if formula:return True
    if job['owner_email'] is not None and job['session_generation'] is not None:
        return bool(conn.execute("SELECT 1 FROM research_tasks t JOIN research_principals p ON p.id=t.principal_id WHERE p.gate_id=? AND p.normalized_email=? AND p.session_generation=? AND t.policy_revision IN ('bounded_usage_upper_v2','local-formula-v1') LIMIT 1",
            (job['gate_id'],job['owner_email'],job['session_generation'])).fetchone())
    return bool(conn.execute("SELECT 1 FROM research_tasks t JOIN research_principals p ON p.id=t.principal_id WHERE p.gate_id=? AND t.policy_revision IN ('bounded_usage_upper_v2','local-formula-v1') LIMIT 1",(job['gate_id'],)).fetchone())


def verify_deletion_origin(conn,*,store,lease,job_id):
    job=conn.execute('SELECT * FROM auth_deletion_jobs WHERE id=?',(job_id,)).fetchone()
    if not job:raise PermissionError('actual deletion job required')
    protected='origin_version' in job.keys() and job['origin_version'] is not None
    if not protected:
        if _job_has_v2(conn,job):raise PermissionError('legacy deletion cannot control v2 resources')
        return None
    from .store import ResearchStore
    from .financial_guard import JOB_ORIGIN_VERSION
    _deletion_lease_binding(conn,store,lease,job)
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (10,11,12,13):ResearchStore.check_runtime_version(conn)
    elif conn.execute('SELECT version FROM research_schema').fetchone()[0]==9:ResearchStore._check_v9(conn)
    else:ResearchStore._check_v8(conn)
    if job['origin_version']!=JOB_ORIGIN_VERSION or job['origin_digest']!=deletion_origin_digest(job):
        raise PermissionError('protected deletion origin damaged')
    if job['state']=='pending':
        if not job['owner_email'] or not job['session_generation'] or store.auth_store.owner_key(job['owner_email'])!=job['owner_key']:
            raise PermissionError('pending deletion incarnation binding unavailable')
        user=conn.execute('SELECT lifecycle,session_generation FROM auth_users WHERE email=?',(job['owner_email'],)).fetchone()
        if user and (user['lifecycle']!='deleting' or user['session_generation']!=job['session_generation']):
            raise PermissionError('deletion cannot affect another incarnation')
    elif job['state'] in ('scrubbing','completed'):
        if job['owner_email'] is not None or job['session_generation'] is not None or not job['research_erased'] or job['result_json'] is None:
            raise PermissionError('deletion completion binding unavailable')
    else:raise PermissionError('unknown deletion stage')
    return dict(job)


def create_authenticated_deletion_job(conn,*,store,lease,source,values):
    from .financial_guard import JOB_ORIGIN_VERSION,_financial_write_scope
    _current_scope(conn)
    require_authenticated_action(source,identity=source.identity,action='account-delete')
    _deletion_lease_binding(conn,store,lease,values)
    user=conn.execute('SELECT lifecycle,session_generation FROM auth_users WHERE email=?',(source.identity.email,)).fetchone()
    if (not user or user['lifecycle']!='deleting' or user['session_generation']!=source.identity.generation
            or values['owner_email']!=source.identity.email or values['session_generation']!=source.identity.generation
            or values['owner_key']!=store.auth_store.owner_key(source.identity.email)
            or conn.execute('SELECT gate_id FROM auth_owner_gates WHERE owner_key=?',(values['owner_key'],)).fetchone()[0]!=values['gate_id']):
        raise PermissionError('authenticated deletion fence missing')
    values=dict(values,origin_version=JOB_ORIGIN_VERSION)
    values['origin_digest']=deletion_origin_digest(values)
    binding=FinancialWriteBinding('delete-create',values['id'],'auth_deletion_jobs',values['id'],digest(canonical(values)),0)
    def validate():
        require_authenticated_action(source,identity=source.identity,action='account-delete')
        _deletion_lease_binding(conn,store,lease,values)
        if conn.execute('SELECT 1 FROM auth_deletion_jobs WHERE id=?',(values['id'],)).fetchone():raise PermissionError('job already created')
        return binding
    authority=FinancialWriteAuthority(conn,lease,'delete-create',validate,_factory=_FACTORY)
    with _financial_write_scope(conn,lease,authority):
        conn.execute('INSERT INTO auth_deletion_jobs('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))


def deletion_job_write(conn,*,store,lease,job_id,sql,args):
    from .financial_guard import _financial_write_scope
    _current_scope(conn)
    protected=verify_deletion_origin(conn,store=store,lease=lease,job_id=job_id)
    if protected is None:return conn.execute(sql,args)
    if protected['state']=='completed':raise PermissionError('completed deletion is read only')
    if protected['state']=='scrubbing' and not sql.startswith("UPDATE auth_deletion_jobs SET state='completed'"):
        raise PermissionError('scrubbing only permits final completion')
    before=digest(canonical(protected))
    binding=FinancialWriteBinding('delete-stage',job_id,'auth_deletion_jobs',job_id,before,0)
    def validate():
        current=verify_deletion_origin(conn,store=store,lease=lease,job_id=job_id)
        if current is None or digest(canonical(current))!=before:raise PermissionError('deletion stage changed')
        return binding
    authority=FinancialWriteAuthority(conn,lease,'delete-stage',validate,_factory=_FACTORY)
    with _financial_write_scope(conn,lease,authority):return conn.execute(sql,args)


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
        # Pausing execution never withdraws protection of existing tickets.
        self.financial_active=bool(table and conn.execute("SELECT 1 FROM research_project_budgets WHERE id=1").fetchone())
        marker=conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_source_resources'").fetchone()
        self.source_active=bool(marker)
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
        from .plan_native_financial import statement_allowed as native_statement_allowed
        if not native_statement_allowed(conn,action,arg1,arg2):return sqlite3.SQLITE_DENY
        from .plan_financial import statement_allowed as plan_statement_allowed
        if not plan_statement_allowed(conn,action,arg1,arg2):return sqlite3.SQLITE_DENY
        from .formula_runtime import statement_allowed as formula_statement_allowed
        if not formula_statement_allowed(conn,action,arg1,arg2):return sqlite3.SQLITE_DENY
        if scope.source_active:
            from .source_guard import statement_allowed as source_statement_allowed
            if not source_statement_allowed(conn,action,arg1,arg2):return sqlite3.SQLITE_DENY
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
            or conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()[0] not in (5,6,7,8,9,10,11,12,13)):
        raise PermissionError("current canonical v5 transaction required")
    if conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]==7:
        from .store import ResearchStore
        ResearchStore._check_v7(conn)
    elif conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]==8:
        from .store import ResearchStore
        ResearchStore._check_v8(conn)
    elif conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]==9:
        from .store import ResearchStore
        ResearchStore._check_v9(conn)
    elif conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0] in (10,11,12,13):
        from .store import ResearchStore
        ResearchStore.check_runtime_version(conn)
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


def mint_stop_authority(conn,*,store,lease,principal_id,task_id,expected_task_version,identity=None,deletion_job_id=None,
        request_source=None,key=None,body_digest=None):
    _current_scope(conn)
    if type(expected_task_version) is not int or expected_task_version<1:
        raise PermissionError("exact task version required")
    def validate():
        principal=_owner_binding(conn,store,principal_id,lease)
        task=conn.execute("SELECT * FROM research_tasks WHERE id=? AND principal_id=?",(task_id,principal_id)).fetchone()
        if not task or task["version"]!=expected_task_version:raise PermissionError("stop task changed")
        if deletion_job_id is None:
            if type(identity) is not AccountIdentity:raise PermissionError("canonical account identity required")
            if task['policy_revision']=='bounded_usage_upper_v2':
                require_authenticated_action(request_source,identity=identity,action='cancel',research_id=task['research_id'],task_id=task_id,key=key,body_digest=body_digest)
            research=AuthorizationGate(store).check(conn,identity,principal_id,task["research_id"],scope="write")
            grant_facts=tuple(tuple(row) for row in conn.execute("SELECT id,version,status,scopes,principal_epoch,acl_epoch FROM research_grants WHERE principal_id=? AND research_id=? ORDER BY id",(principal_id,task["research_id"])))
            facts=(principal_id,principal["epoch"],principal["session_generation"],task_id,task["version"],task["input_revision"],task["input_digest"],task["stop_requested"],research["owner_epoch"],research["acl_epoch"],research["version"],grant_facts,lease.identity)
            return StopBinding(principal_id,task_id,task["version"],digest(canonical(facts)),None,lease.identity)
        job=conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'",(deletion_job_id,)).fetchone()
        if task['policy_revision']=='bounded_usage_upper_v2':verify_deletion_origin(conn,store=store,lease=lease,job_id=deletion_job_id)
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
    if type(context) is CallContext and conn.execute('SELECT version FROM research_schema').fetchone()[0] in (6,7,8,9,10,11,12,13):
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
