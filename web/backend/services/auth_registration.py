"""Controlled private registration. Receipts describe resources, never sessions.

HTTP constructors remain existing-only. This module owns the single narrow
resource birth path and the atomic token/account finalization transaction.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
from types import MappingProxyType
from uuid import uuid4

from .privacy_identifiers import opaque_identifier

_FACTORY = object()
_REQUEST = vars(sqlite3).setdefault('_structural_registration_request_v1',ContextVar('private_registration_request', default=None))
_DELETE = vars(sqlite3).setdefault('_structural_registration_delete_v1',ContextVar('private_registration_delete', default=None))
_SCOPES = vars(sqlite3).setdefault('_structural_registration_writes_v1',{})
_SESSIONS = vars(sqlite3).setdefault('_structural_registration_sessions_v1',{})
_GEN = re.compile(r'^[a-f0-9]{32}$')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _generation_digest(value):
    return opaque_identifier('account-registration.generation', value, kind='opaque').rsplit(':', 1)[1]


def _private(store):
    from .auth_store import _formal_auth_mode
    current = _formal_auth_mode()
    if current and not store._private_auth:
        raise PermissionError('development Auth cannot become private')
    return current or store._private_auth


def _research_control(store):
    """Select only one of the two real supported ResearchStore classes."""
    import importlib
    module=type(store).__module__
    if module not in ('research.store','web.backend.research.store'):
        raise PermissionError('actual ResearchStore required')
    owner=importlib.import_module(module)
    if type(store) is not owner.ResearchStore:
        raise PermissionError('actual ResearchStore required')
    return importlib.import_module(module.rsplit('.',1)[0]+'.paid_control')


def _route_call(request,name):
    """Bind admission to the live code-owned route, not a Request-shaped DTO."""
    from starlette.requests import Request
    if __package__=='web.backend.services':from ..api import auth
    else:from api import auth
    if (not isinstance(request,Request) or request.method!='POST'
        or request.url.path!='/api/auth/'+('verify' if name=='verify' else 'request-link')
        or auth.require_same_origin(request) is not None):
        raise PermissionError('actual same-origin Auth route required')
    import sys
    endpoints={getattr(module,name).__code__:module for module_name in ('api.auth','web.backend.api.auth')
        if (module:=sys.modules.get(module_name)) is not None and hasattr(module,name)}
    frame=sys._getframe(1)
    try:
        while frame is not None:
            if frame.f_code in endpoints and frame.f_locals.get('request') is request:
                if endpoints[frame.f_code].require_same_origin(request) is not None:raise PermissionError('Auth origin changed')
                return
            frame=frame.f_back
        raise PermissionError('Auth admission requires its live route caller')
    finally:del frame


class RegistrationError(ValueError):
    pass


AUTH_REGISTRATION_TABLES = (
    """CREATE TABLE auth_registration_operations (
        id TEXT PRIMARY KEY, record_version TEXT NOT NULL CHECK(record_version='auth-provision-operation-v1'),
        kind TEXT NOT NULL CHECK(kind IN ('new_account','sign_in','offline_gate_admission')),
        token_hash TEXT UNIQUE, owner_key TEXT NOT NULL, gate_id TEXT NOT NULL,
        expected_generation TEXT, target_generation TEXT, expected_deletion_epoch TEXT,
        token_created_at TEXT, token_expires_at TEXT,
        state TEXT NOT NULL CHECK(state IN ('claimed','gate_ready','finalized','closed')),
        version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647),
        resource_receipt_id TEXT REFERENCES auth_registration_receipts(id), request_digest TEXT,
        database_binding TEXT NOT NULL CHECK(length(database_binding)=64),
        origin_digest TEXT CHECK(origin_digest IS NULL OR length(origin_digest)=64),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        closed_reason TEXT CHECK(closed_reason IN ('expired','cancelled','deleted','conflict','resource_unknown','admitted')),
        last_failure_code TEXT CHECK(last_failure_code IN ('expired','cancelled','deleted','conflict','resource_unknown')),
        CHECK((kind='offline_gate_admission' AND token_hash IS NULL AND expected_generation IS NULL AND target_generation IS NULL)
            OR state='closed' OR (token_hash IS NOT NULL AND token_created_at IS NOT NULL AND token_expires_at IS NOT NULL
                AND length(target_generation)=32 AND target_generation NOT GLOB '*[^a-f0-9]*')),
        CHECK(expected_generation IS NULL OR (length(expected_generation)=32 AND expected_generation NOT GLOB '*[^a-f0-9]*')),
        CHECK(state!='finalized' OR kind!='offline_gate_admission'),
        CHECK((state='closed')=(closed_reason IS NOT NULL)),
        CHECK(state NOT IN ('gate_ready','finalized') OR resource_receipt_id IS NOT NULL)
    )""",
    """CREATE TABLE auth_registration_receipts (
        id TEXT PRIMARY KEY, record_version TEXT NOT NULL CHECK(record_version='auth-provision-receipt-v1'),
        kind TEXT NOT NULL CHECK(kind IN ('gate_resource','account_finalize')),
        operation_id TEXT NOT NULL REFERENCES auth_registration_operations(id),
        owner_key TEXT NOT NULL, gate_id TEXT NOT NULL,
        database_binding TEXT NOT NULL CHECK(length(database_binding)=64),
        lock_dev INTEGER CHECK(lock_dev IS NULL OR (typeof(lock_dev)='integer' AND lock_dev>=0)),
        lock_ino INTEGER CHECK(lock_ino IS NULL OR (typeof(lock_ino)='integer' AND lock_ino>0)),
        generation_digest TEXT CHECK(generation_digest IS NULL OR length(generation_digest)=64),
        operation_version INTEGER NOT NULL CHECK(typeof(operation_version)='integer' AND operation_version>0),
        recorded_at TEXT NOT NULL, payload_digest TEXT NOT NULL CHECK(length(payload_digest)=64),
        CHECK((kind='gate_resource' AND lock_dev IS NOT NULL AND lock_ino IS NOT NULL AND generation_digest IS NULL)
            OR (kind='account_finalize' AND lock_dev IS NULL AND lock_ino IS NULL AND generation_digest IS NOT NULL))
    )""",
    "CREATE UNIQUE INDEX auth_registration_active_owner ON auth_registration_operations(owner_key) WHERE state IN ('claimed','gate_ready') AND kind IN ('new_account','sign_in')",
    "CREATE UNIQUE INDEX auth_registration_gate_resource ON auth_registration_receipts(gate_id) WHERE kind='gate_resource'",
    "CREATE UNIQUE INDEX auth_registration_account_finalize ON auth_registration_receipts(operation_id) WHERE kind='account_finalize'",
)


def _guard(table, action, key, condition='1'):
    return (f'CREATE TRIGGER registration_{table}_{action.lower()} BEFORE {action} ON {table} WHEN {condition} '
        f"BEGIN SELECT CASE WHEN auth_registration_write_allowed('{table}:{action}',{key})!=1 "
        "THEN RAISE(ABORT,'controlled Auth registration required') END; END")


AUTH_REGISTRATION_GUARDS = (
    *(_guard('auth_registration_operations', action, prefix+'.id') for action, prefix in [('INSERT','NEW'),('UPDATE','OLD')]),
    _guard('auth_registration_receipts', 'INSERT', 'NEW.operation_id'),
    _guard('auth_owner_gates', 'INSERT', 'NEW.owner_key'),
    _guard('auth_users', 'INSERT', 'NEW.email'),
    _guard('auth_users', 'DELETE', 'OLD.email'),
    _guard('auth_users','UPDATE','OLD.email'),
    _guard('magic_tokens', 'INSERT', 'NEW.token_hash'),
    _guard('magic_tokens', 'UPDATE', 'OLD.token_hash'),
    _guard('magic_tokens', 'DELETE', 'OLD.token_hash'),
    _guard('auth_notification_outbox', 'INSERT', 'NEW.email'),
    _guard('auth_notification_outbox', 'DELETE', 'OLD.email'),
    """CREATE TRIGGER registration_operations_identity BEFORE UPDATE ON auth_registration_operations
       WHEN NEW.rowid IS NOT OLD.rowid OR NEW.id IS NOT OLD.id OR NEW.record_version IS NOT OLD.record_version
       OR NEW.kind IS NOT OLD.kind OR NEW.owner_key IS NOT OLD.owner_key OR NEW.gate_id IS NOT OLD.gate_id
       OR NEW.database_binding IS NOT OLD.database_binding OR NEW.created_at IS NOT OLD.created_at
       OR NEW.version!=OLD.version+1 OR OLD.state='closed'
       OR NOT ((OLD.state='claimed' AND NEW.state IN ('gate_ready','closed')) OR (OLD.state='gate_ready' AND NEW.state IN ('finalized','closed')) OR (OLD.state='finalized' AND NEW.state='closed'))
       BEGIN SELECT RAISE(ABORT,'invalid registration transition'); END""",
    """CREATE TRIGGER registration_operations_resource BEFORE UPDATE ON auth_registration_operations
       WHEN NEW.resource_receipt_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM auth_registration_receipts r WHERE r.id=NEW.resource_receipt_id
          AND r.kind='gate_resource' AND r.owner_key=NEW.owner_key AND r.gate_id=NEW.gate_id AND r.database_binding=NEW.database_binding)
       BEGIN SELECT RAISE(ABORT,'registration resource mismatch'); END""",
    """CREATE TRIGGER registration_operations_private_identity BEFORE UPDATE ON auth_registration_operations
       WHEN NOT (NEW.state='closed' AND NEW.token_hash IS NULL AND NEW.expected_generation IS NULL AND NEW.target_generation IS NULL
          AND NEW.token_created_at IS NULL AND NEW.token_expires_at IS NULL AND NEW.request_digest IS NULL AND NEW.origin_digest IS NULL)
       AND (NEW.token_hash IS NOT OLD.token_hash OR NEW.expected_generation IS NOT OLD.expected_generation
          OR NEW.target_generation IS NOT OLD.target_generation OR NEW.expected_deletion_epoch IS NOT OLD.expected_deletion_epoch
          OR NEW.token_created_at IS NOT OLD.token_created_at OR NEW.token_expires_at IS NOT OLD.token_expires_at
          OR NEW.request_digest IS NOT OLD.request_digest OR NEW.origin_digest IS NOT OLD.origin_digest)
       BEGIN SELECT RAISE(ABORT,'registration private binding immutable'); END""",
    """CREATE TRIGGER registration_operations_no_replace BEFORE INSERT ON auth_registration_operations
       WHEN EXISTS(SELECT 1 FROM auth_registration_operations o WHERE o.rowid=NEW.rowid OR o.id=NEW.id
          OR (NEW.token_hash IS NOT NULL AND o.token_hash=NEW.token_hash)
          OR (NEW.state IN ('claimed','gate_ready') AND o.state IN ('claimed','gate_ready') AND NEW.kind IN ('new_account','sign_in') AND o.kind IN ('new_account','sign_in') AND o.owner_key=NEW.owner_key))
       BEGIN SELECT RAISE(ABORT,'registration replacement forbidden'); END""",
    """CREATE TRIGGER registration_receipts_no_replace BEFORE INSERT ON auth_registration_receipts
       WHEN EXISTS(SELECT 1 FROM auth_registration_receipts r WHERE r.rowid=NEW.rowid OR r.id=NEW.id
          OR (NEW.kind='gate_resource' AND r.kind=NEW.kind AND r.gate_id=NEW.gate_id)
          OR (NEW.kind='account_finalize' AND r.kind=NEW.kind AND r.operation_id=NEW.operation_id))
       BEGIN SELECT RAISE(ABORT,'receipt replacement forbidden'); END""",
    """CREATE TRIGGER registration_receipts_binding BEFORE INSERT ON auth_registration_receipts
       WHEN NOT EXISTS(SELECT 1 FROM auth_registration_operations o WHERE o.id=NEW.operation_id AND o.owner_key=NEW.owner_key
          AND o.gate_id=NEW.gate_id AND o.database_binding=NEW.database_binding AND o.version=NEW.operation_version
          AND ((NEW.kind='gate_resource' AND o.state='claimed') OR (NEW.kind='account_finalize' AND o.state='gate_ready' AND o.kind!='offline_gate_admission')))
       BEGIN SELECT RAISE(ABORT,'receipt operation mismatch'); END""",
    *(f"CREATE TRIGGER registration_{table}_{action.lower()}_immutable BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'registration evidence retained'); END"
      for table, actions in [('auth_registration_receipts',('UPDATE','DELETE')),('auth_registration_operations',('DELETE',)),('auth_owner_gates',('UPDATE','DELETE'))] for action in actions),
    """CREATE TRIGGER registration_users_no_replace BEFORE INSERT ON auth_users
       WHEN EXISTS(SELECT 1 FROM auth_users WHERE email=NEW.email OR rowid=NEW.rowid)
       BEGIN SELECT RAISE(ABORT,'account replacement forbidden'); END""",
    """CREATE TRIGGER registration_users_lifecycle BEFORE UPDATE OF lifecycle ON auth_users
       WHEN OLD.lifecycle!='active' OR NEW.lifecycle!='deleting'
       BEGIN SELECT RAISE(ABORT,'account lifecycle cannot be restored'); END""",
    """CREATE TRIGGER registration_gates_no_replace BEFORE INSERT ON auth_owner_gates
       WHEN EXISTS(SELECT 1 FROM auth_owner_gates WHERE owner_key=NEW.owner_key OR gate_id=NEW.gate_id OR rowid=NEW.rowid)
       BEGIN SELECT RAISE(ABORT,'gate replacement forbidden'); END""",
)
AUTH_REGISTRATION_DDL = AUTH_REGISTRATION_TABLES + AUTH_REGISTRATION_GUARDS


class _VerifyRequest:
    __slots__ = ('request', 'store', 'pid', 'active', 'nonce', 'caps')
    def __init__(self, request, store, *, _factory=None):
        if _factory is not _FACTORY:
            raise TypeError('real verify request required')
        from starlette.requests import Request
        if not isinstance(request, Request) or request.method!='POST' or not request.url.path.endswith('/auth/verify'):
            raise PermissionError('actual POST verify required')
        _route_call(request,'verify')
        self.request, self.store, self.pid, self.active = request, store, os.getpid(), True
        self.nonce, self.caps = uuid4().hex, []
    def require(self, store):
        if _REQUEST.get() is not self or not self.active or self.pid!=os.getpid() or self.store is not store or not _private(store):
            raise PermissionError('verify request ended or changed')
        _route_call(self.request,'verify')


@contextmanager
def verify_request(request, store):
    """Called only after the formal route's origin and input checks."""
    source = _VerifyRequest(request, store, _factory=_FACTORY)
    token = _REQUEST.set(source)
    try:
        yield source
    finally:
        # An ended request never leaves a live claim blocking a fresh link.
        # A resource without its receipt stays unavailable for explicit offline
        # reconciliation; closing work does not adopt or remove that inode.
        try:
            _close_request_claims(store,source)
        finally:
            source.active = False
            for cap in source.caps:
                object.__setattr__(cap,'active',False)
                _SESSIONS.pop(id(cap),None)
            _REQUEST.reset(token)


def _close_request_claims(store,source):
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        rows=conn.execute("SELECT id FROM auth_registration_operations WHERE request_digest=? AND state IN ('claimed','gate_ready')",(_digest(source.nonce),)).fetchall()
        def validate():_native(conn,store);source.require(store)
        with _write(conn,store,{('auth_registration_operations:UPDATE',row['id']) for row in rows},validate,_factory=_FACTORY):
            for row in rows:
                conn.execute("UPDATE auth_registration_operations SET state='closed',version=version+1,closed_reason='cancelled',last_failure_code='cancelled',updated_at=? WHERE id=? AND state IN ('claimed','gate_ready')",(_now(),row['id']))
        conn.commit()


def _native(conn, store):
    from .sqlite_utils import PrivateAuthConnection
    from .runtime_paths import private_auth_path
    import sys
    types={PrivateAuthConnection}|{module.PrivateAuthConnection for name in ('services.sqlite_utils','web.backend.services.sqlite_utils')
        if (module:=sys.modules.get(name)) is not None}
    if type(conn) not in types or not conn.in_transaction or conn.private_storage_identity!=store.storage_identity or store.path!=private_auth_path():
        raise PermissionError('actual private Auth transaction required')
    conn._history_file.check()


@contextmanager
def _write(conn, store, permissions, validate, *, _factory=None):
    if _factory is not _FACTORY or id(conn) in _SCOPES:
        raise PermissionError('controlled Auth scope required')
    _native(conn, store)
    validate()
    scope = (conn, os.getpid(), permissions, validate)
    _SCOPES[id(conn)] = scope
    try:
        yield
    finally:
        _SCOPES.pop(id(conn), None)


def install_hook(conn):
    """Add only this UDF; retain financial authorizer and transaction tracing."""
    pid = os.getpid()
    def allowed(action, target):
        scope = _SCOPES.get(id(conn))
        if not scope or scope[0] is not conn or scope[1]!=os.getpid() or pid!=os.getpid() or not conn.in_transaction:
            return 0
        if (action, target) not in scope[2]:
            return 0
        try:
            scope[3]()
            return 1
        except (PermissionError, ValueError, RuntimeError, OSError, sqlite3.Error):
            return 0
    conn.create_function('auth_registration_write_allowed', 2, allowed)


def add_token(store, token_hash, email, created_at, expires_at, *, request):
    from starlette.requests import Request
    if not isinstance(request,Request) or request.method!='POST' or not request.url.path.endswith('/auth/request-link'):
        raise PermissionError('actual request-link source required')
    _route_call(request,'request_link')
    if not _private(store):
        raise PermissionError('private token producer required')
    pid=os.getpid()
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        def validate():
            _native(conn,store)
            _route_call(request,'request_link')
            if pid!=os.getpid():raise PermissionError('token producer process changed')
            store.require_registration_allowed(conn,email)
        with _write(conn,store,{('magic_tokens:INSERT',token_hash)},validate,_factory=_FACTORY):
            conn.execute('INSERT INTO magic_tokens(token_hash,email,created_at,expires_at) VALUES(?,?,?,?)',(token_hash,email,created_at,expires_at))
        conn.commit()


@contextmanager
def deletion_scope(service, lease, job_id):
    """Source wrapper only; each Auth write independently validates its job."""
    import importlib
    module=type(service).__module__
    if module not in ('research.service','web.backend.research.service') or lease is None:
        raise PermissionError('actual deletion service and lease required')
    if type(service) is not importlib.import_module(module).ResearchService:raise PermissionError('actual deletion service required')
    _research_control(service.store)
    source=(service,lease,job_id,os.getpid())
    token=_DELETE.set(source)
    try:yield
    finally:_DELETE.reset(token)


def _deletion_validate(conn, store, *, service, lease, job_id, email):
    _native(conn,store)
    if _DELETE.get()!=(service,lease,job_id,os.getpid()) or service.store.path!=store.path or service.store.storage_identity!=store.storage_identity:
        raise PermissionError('actual deletion source changed')
    _research_control(service.store).verify_deletion_origin(conn,store=service.store,lease=lease,job_id=job_id)
    job=conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'",(job_id,)).fetchone()
    user=conn.execute('SELECT * FROM auth_users WHERE email=?',(email,)).fetchone()
    if not job or job['origin_version'] is None or job['owner_email']!=email or job['owner_key']!=store.owner_key(email):
        raise PermissionError('protected pending deletion required')
    if user and (user['lifecycle']!='deleting' or user['session_generation']!=job['session_generation']):
        raise PermissionError('deletion cannot erase a new generation')
    receipt=_receipt(conn,job['gate_id'])
    if not receipt or (receipt['lock_dev'],receipt['lock_ino'])!=lease.identity[:2]:
        raise PermissionError('deletion lease resource changed')
    return job


def mark_account_deleting(conn, *, store, lease, request_source, email, generation):
    """Core creation bridge before the protected job exists in this txn.

    This grants only the active->deleting fence. It never grants erasure;
    erasure requires the subsequently inserted protected pending job.
    """
    control=_research_control(store)
    auth=store.auth_store
    import importlib
    lease_type=importlib.import_module(type(store).__module__.rsplit('.',1)[0]+'.authorization').OwnerGateLease
    if type(lease) is not lease_type:
        raise PermissionError('actual canonical owner gate lease required')
    install_hook(conn)
    def validate():
        _native(conn,auth);control._current_scope(conn)
        control.require_authenticated_action(request_source,identity=request_source.identity,action='account-delete')
        if request_source.identity.email!=email or request_source.identity.generation!=generation:raise PermissionError('actual deletion request changed')
        user=conn.execute('SELECT * FROM auth_users WHERE email=?',(email,)).fetchone()
        if not user or user['lifecycle']!='active' or user['session_generation']!=generation:raise PermissionError('actual active generation required')
        gate=conn.execute('SELECT gate_id FROM auth_owner_gates WHERE owner_key=?',(auth.owner_key(email),)).fetchone()
        resource=_receipt(conn,gate['gate_id']) if gate else None
        # The exact native type's property checks its active flag, creator PID
        # and held kernel FD. Public inode facts copied into a DTO cannot do so.
        held=lease.identity
        if (not resource or resource['owner_key']!=auth.owner_key(email)
            or resource['gate_id']!=gate['gate_id'] or resource['database_binding']!=_binding(auth)
            or (resource['lock_dev'],resource['lock_ino'],os.geteuid(),0o600,1)!=held):
            raise PermissionError('deletion owner resource changed')
        from .runtime_paths import require_private_auth_lock_dir,_check_current_parent,_auth_forbidden_roots
        root=require_private_auth_lock_dir(auth.path)
        directory=os.open('research-locks',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=conn._history_file.parent_fd)
        try:
            _check_current_parent(root,directory,forbidden=_auth_forbidden_roots())
            info=os.stat(gate['gate_id']+'.lock',dir_fd=directory,follow_symlinks=False)
            _safe_file(info)
            if (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)!=held:
                raise PermissionError('deletion owner gate pathname changed')
        finally:os.close(directory)
        auth.require_registration_allowed(conn,email)
    with _write(conn,auth,{('auth_users:UPDATE',email)},validate,_factory=_FACTORY):
        if conn.execute("UPDATE auth_users SET lifecycle='deleting' WHERE email=? AND session_generation=? AND lifecycle='active'",(email,generation)).rowcount!=1:raise PermissionError('deletion fence CAS failed')


def erase_registration_for_job(conn, *, store, lease, job_id):
    """Core bridge: actual same-transaction protected pending deletion only.

    `store` is the real ResearchStore, never a caller supplied evidence DTO.
    """
    control=_research_control(store)
    auth=store.auth_store
    job=conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'",(job_id,)).fetchone()
    if not job:
        raise PermissionError('pending job required')
    source=_DELETE.get()
    if source is not None:
        if source[0].store is not store or source[1] is not lease or source[2]!=job_id:
            raise PermissionError('real Auth deletion context required')
        def validate():return _deletion_validate(conn,auth,service=source[0],lease=lease,job_id=job_id,email=job['owner_email'])
    else:
        def validate():
            _native(conn,auth)
            control._current_scope(conn)
            control.verify_deletion_origin(conn,store=store,lease=lease,job_id=job_id)
            actual=conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'",(job_id,)).fetchone()
            if not actual or actual['origin_version'] is None or actual['owner_email']!=job['owner_email'] or actual['session_generation']!=job['session_generation']:
                raise PermissionError('protected pending deletion changed')
            resource=_receipt(conn,actual['gate_id'])
            if not resource or (resource['lock_dev'],resource['lock_ino'])!=lease.identity[:2]:raise PermissionError('deletion resource changed')
        install_hook(conn)
    validate()
    rows=conn.execute("SELECT * FROM auth_registration_operations WHERE owner_key=? AND state!='closed'",(job['owner_key'],)).fetchall()
    permissions={('auth_registration_operations:UPDATE',row['id']) for row in rows}
    with _write(conn,auth,permissions,validate,_factory=_FACTORY):
        for row in rows:
            if row['kind']!='offline_gate_admission' and row['target_generation']!=job['session_generation']:
                # Unfinished work for this owner cannot survive deletion, even
                # when it has not yet made an account incarnation.
                if row['state']=='finalized':continue
            conn.execute("""UPDATE auth_registration_operations SET state='closed',version=version+1,closed_reason='deleted',last_failure_code='deleted',
                token_hash=NULL,expected_generation=NULL,target_generation=NULL,expected_deletion_epoch=NULL,token_created_at=NULL,token_expires_at=NULL,
                request_digest=NULL,origin_digest=NULL,updated_at=? WHERE id=? AND state!='closed'""",(_now(),row['id']))


def delete_account_data(store,email,*,rate_keys):
    source=_DELETE.get()
    if not source:
        raise PermissionError('actual pending deletion context required')
    service,lease,job_id,pid=source
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        def validate():return _deletion_validate(conn,store,service=service,lease=lease,job_id=job_id,email=email)
        validate()
        # The source's ResearchStore is checked against this very connection;
        # no earlier read-only proof is treated as a write capability.
        erase_registration_for_job(conn,store=service.store,lease=lease,job_id=job_id)
        tokens=[r[0] for r in conn.execute('SELECT token_hash FROM magic_tokens WHERE email=?',(email,))]
        permissions={('magic_tokens:DELETE',key) for key in tokens}|{('auth_users:DELETE',email),('auth_notification_outbox:DELETE',email)}
        with _write(conn,store,permissions,validate,_factory=_FACTORY):
            from .auth_store import _email_hash
            conn.execute('INSERT INTO account_deletion_epochs VALUES(?,?) ON CONFLICT(owner_hash) DO UPDATE SET deleted_at=excluded.deleted_at',(_email_hash(email),_now()))
            counts={'magic_link_events':conn.execute('DELETE FROM magic_tokens WHERE email=?',(email,)).rowcount,
                'registration_notifications':conn.execute('DELETE FROM auth_notification_outbox WHERE email=?',(email,)).rowcount,
                'account':conn.execute('DELETE FROM auth_users WHERE email=?',(email,)).rowcount,
                'revoked_session_events':'retained security markers','security_deletion_epoch':'retained without raw email'}
            counts['rate_limit_events']=conn.execute('DELETE FROM auth_rate_requests WHERE email IN ('+','.join('?' for _ in (email,*rate_keys))+')',(email,*rate_keys)).rowcount
            conn.execute('UPDATE revoked_sessions SET email=NULL WHERE email=?',(email,))
        conn.commit()
        return counts


def _epoch(conn, email):
    from .auth_store import _email_hash, _legacy_email_hash
    rows=conn.execute('SELECT deleted_at FROM account_deletion_epochs WHERE owner_hash IN (?,?)', (_email_hash(email),_legacy_email_hash(email))).fetchall()
    return max((r[0] for r in rows), default=None)


def _token(conn, store, token_hash):
    row=conn.execute('SELECT * FROM magic_tokens WHERE token_hash=?', (token_hash,)).fetchone()
    if not row or row['consumed_at'] is not None:
        raise RegistrationError('invalid or already used token')
    try:
        expires=datetime.fromisoformat(row['expires_at'])
        created=datetime.fromisoformat(row['created_at'])
        if expires.tzinfo is None or created.tzinfo is None or expires<=datetime.now(timezone.utc):
            raise ValueError()
    except (ValueError, TypeError):
        raise RegistrationError('expired or malformed token') from None
    store.require_registration_allowed(conn,row['email'])
    epoch=_epoch(conn,row['email'])
    if epoch is not None and row['created_at']<=epoch:
        raise RegistrationError('credential predates deletion')
    return row, epoch


def _binding(store):
    return _digest(list(store.storage_identity))


def _receipt(conn, gate_id):
    return conn.execute("SELECT * FROM auth_registration_receipts WHERE gate_id=? AND kind='gate_resource'",(gate_id,)).fetchone()


def expected_owner_gate_identity(store, gate_id):
    if not _private(store):
        with store._connection() as conn:
            row=_receipt(conn,gate_id)
            if row is None or row['database_binding']!=_binding(store):
                raise PermissionError('owner gate resource is not admitted')
            return row['lock_dev'],row['lock_ino']
    from .runtime_paths import private_auth_path,RuntimePathError
    from .sqlite_utils import connect_private_auth
    if store.path!=private_auth_path() or store.storage_identity is None:
        raise RuntimePathError('private owner gate has no captured Auth identity')
    conn=connect_private_auth(store.path,readonly=True,expected_identity=store.storage_identity)
    try:
        conn.row_factory=sqlite3.Row
        if __package__=='web.backend.services':from ..research.financial_guard import install_default_hook
        else:from research.financial_guard import install_default_hook
        install_default_hook(conn)
        install_hook(conn)
        conn.execute('PRAGMA busy_timeout=10000')
        conn.execute('PRAGMA secure_delete=ON')
        conn.execute('PRAGMA foreign_keys=ON')
        if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1:
            raise RuntimeError('private Auth foreign keys unavailable')
        conn.execute('BEGIN')
        store.check_gate_policy(conn,initialize=False)
        row=_receipt(conn,gate_id)
        if row is None or row['database_binding']!=_binding(store):
            raise PermissionError('owner gate resource is not admitted')
        return row['lock_dev'],row['lock_ino']
    finally:conn.close()


def _new_receipt(conn, op, kind, *, identity=None, generation=None):
    receipt_id=str(uuid4())
    values=(receipt_id,'auth-provision-receipt-v1',kind,op['id'],op['owner_key'],op['gate_id'],op['database_binding'],
        identity[0] if identity else None,identity[1] if identity else None,
        _generation_digest(generation) if generation else None,op['version'],_now())
    conn.execute('INSERT INTO auth_registration_receipts VALUES('+','.join('?' for _ in range(13))+')', (*values,_digest(values)))
    return receipt_id


@contextmanager
def _provision_lock(store):
    from .runtime_paths import PrivateAuthFile, _check_current_parent, _auth_forbidden_roots
    witness=PrivateAuthFile.acquire(store.path)
    fd=None
    try:
        if witness.file_identity!=store.storage_identity:
            raise PermissionError('Auth database changed')
        fd=os.open('registration-provision.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=witness.parent_fd)
        def check():
            witness.check()
            entry=os.stat('registration-provision.lock',dir_fd=witness.parent_fd,follow_symlinks=False)
            held=os.fstat(fd)
            for info in (entry,held):
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
                    raise PermissionError('unsafe provision lock')
            if (entry.st_dev,entry.st_ino)!=(held.st_dev,held.st_ino):
                raise PermissionError('provision lock changed')
        check()
        deadline=time.monotonic()+5
        while True:
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic()>=deadline:
                    raise RegistrationError('registration busy') from None
                time.sleep(.01)
        check()
        yield witness
        check()
    finally:
        if fd is not None:
            os.close(fd)
        witness.close()


def _claim(store, source, token_hash, *, birth=False):
    source.require(store)
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        token,epoch=_token(conn,store,token_hash)
        email=token['email']; owner=store.owner_key(email)
        user=conn.execute('SELECT * FROM auth_users WHERE email=?',(email,)).fetchone()
        if user and not _GEN.fullmatch(user['session_generation'] or ''):
            raise RegistrationError('account generation is unavailable')
        gate=conn.execute('SELECT gate_id FROM auth_owner_gates WHERE owner_key=?',(owner,)).fetchone()
        if (gate is None)!=birth:
            raise RegistrationError('resource reservation changed')
        if user and gate is None:
            raise RegistrationError('existing account has no admitted resource')
        if conn.execute("SELECT 1 FROM auth_registration_operations WHERE owner_key=? AND state IN ('claimed','gate_ready')",(owner,)).fetchone():
            raise RegistrationError('registration already pending')
        if conn.execute('SELECT 1 FROM auth_registration_operations WHERE token_hash=?',(token_hash,)).fetchone():
            raise RegistrationError('token operation already exists; use a fresh link')
        gate_id=str(uuid4()) if birth else gate['gate_id']
        generation=user['session_generation'] if user else uuid4().hex
        op_id=str(uuid4()); now=_now()
        permissions={('auth_registration_operations:INSERT',op_id)}
        if birth:
            permissions.add(('auth_owner_gates:INSERT',owner))
        def validate():
            _native(conn,store); source.require(store)
            actual,_=_token(conn,store,token_hash)
            if actual['email']!=email:
                raise PermissionError('token owner changed')
        with _write(conn,store,permissions,validate,_factory=_FACTORY):
            if birth:
                conn.execute('INSERT INTO auth_owner_gates VALUES(?,?)',(owner,gate_id))
            conn.execute('''INSERT INTO auth_registration_operations
                (id,record_version,kind,token_hash,owner_key,gate_id,expected_generation,target_generation,
                 expected_deletion_epoch,token_created_at,token_expires_at,state,version,request_digest,database_binding,origin_digest,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,'claimed',1,?,?,?,?,?)''',
                (op_id,'auth-provision-operation-v1','sign_in' if user else 'new_account',token_hash,owner,gate_id,
                 user['session_generation'] if user else None,generation,epoch,token['created_at'],token['expires_at'],
                 _digest(source.nonce),_binding(store),_digest(['verify',source.nonce]),now,now))
        conn.commit()
        return op_id,gate_id


def _mark_ready(store, source, op_id, *, born_identity=None):
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        op=conn.execute('SELECT * FROM auth_registration_operations WHERE id=?',(op_id,)).fetchone()
        def validate():
            _native(conn,store); source.require(store)
            actual=conn.execute('SELECT state,version,request_digest FROM auth_registration_operations WHERE id=?',(op_id,)).fetchone()
            if not actual or tuple(actual)!=('claimed',op['version'],_digest(source.nonce)):
                raise PermissionError('claim changed')
            _token(conn,store,op['token_hash'])
        permissions={('auth_registration_operations:UPDATE',op_id),('auth_registration_receipts:INSERT',op_id)}
        with _write(conn,store,permissions,validate,_factory=_FACTORY):
            receipt=_receipt(conn,op['gate_id'])
            if born_identity is not None:
                if receipt:
                    raise PermissionError('resource already published')
                ref=_new_receipt(conn,op,'gate_resource',identity=born_identity)
            else:
                if not receipt or receipt['database_binding']!=_binding(store):
                    raise PermissionError('existing resource has no receipt; offline admission required')
                ref=receipt['id']
            count=conn.execute("UPDATE auth_registration_operations SET state='gate_ready',version=version+1,resource_receipt_id=?,updated_at=? WHERE id=? AND state='claimed' AND version=?",
                (ref,_now(),op_id,op['version'])).rowcount
            if count!=1:
                raise PermissionError('claim CAS failed')
        conn.commit()


def _birth(store, source, token_hash):
    """FS/DB are deliberately separate; an orphan file is never auto-adopted."""
    from .runtime_paths import require_private_auth_lock_dir, _check_current_parent, _auth_forbidden_roots
    with _provision_lock(store) as witness:
        op_id,gate_id=_claim(store,source,token_hash,birth=True)
        root=require_private_auth_lock_dir(store.path)
        directory=os.open('research-locks',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=witness.parent_fd)
        fd=None
        try:
            _check_current_parent(root,directory,forbidden=_auth_forbidden_roots())
            # O_EXCL failure is an unknown resource, never evidence of ownership.
            fd=os.open(gate_id+'.lock',os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
            info=os.fstat(fd)
            if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or not stat.S_ISREG(info.st_mode):
                raise PermissionError('new owner gate is unsafe')
            os.fsync(fd);os.fsync(directory)
            witness.check();_check_current_parent(root,directory,forbidden=_auth_forbidden_roots())
            entry=os.stat(gate_id+'.lock',dir_fd=directory,follow_symlinks=False)
            if (entry.st_dev,entry.st_ino)!=(info.st_dev,info.st_ino):
                raise PermissionError('new owner gate changed')
            _mark_ready(store,source,op_id,born_identity=(info.st_dev,info.st_ino))
        finally:
            if fd is not None:
                os.close(fd)
            os.close(directory)
        return op_id,gate_id


class SessionIssueAuthority:
    __slots__=('source','store','lease','user','pid','active','used')
    def __init__(self,source,store,lease,user,*,_factory=None):
        if _factory is not _FACTORY:
            raise TypeError('committed first finalization required')
        for key,value in dict(source=source,store=store,lease=lease,user=MappingProxyType(dict(user)),pid=os.getpid(),active=True,used=False).items():
            object.__setattr__(self,key,value)
        _SESSIONS[id(self)]=self
        source.caps.append(self)
    def __setattr__(self,name,value):
        raise TypeError('sealed session authority is immutable')
    def __reduce__(self):
        raise TypeError('session issue authority cannot be serialized')
    def consume(self,store):
        self.source.require(store)
        if _SESSIONS.get(id(self)) is not self or self.store is not store or not self.active or self.used or self.pid!=os.getpid():
            raise PermissionError('session authority retired')
        self.lease.identity
        actual=store.user(self.user['email'])
        if not actual or actual['lifecycle']!='active' or actual['session_generation']!=self.user['session_generation'] or store.deletion_pending(actual['email']):
            raise PermissionError('account changed before issue')
        object.__setattr__(self,'used',True);object.__setattr__(self,'active',False)
        _SESSIONS.pop(id(self),None)
        return dict(self.user)


def _finalize(store,source,op_id,lease,tier):
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        op=conn.execute('SELECT * FROM auth_registration_operations WHERE id=?',(op_id,)).fetchone()
        if not op or op['kind'] not in ('new_account','sign_in'):
            raise PermissionError('online registration required')
        token,epoch=_token(conn,store,op['token_hash'])
        email=token['email'];created=op['kind']=='new_account'
        def validate():
            _native(conn,store);source.require(store)
            actual=conn.execute('SELECT * FROM auth_registration_operations WHERE id=?',(op_id,)).fetchone()
            resource=conn.execute('SELECT * FROM auth_registration_receipts WHERE id=?',(op['resource_receipt_id'],)).fetchone()
            held=lease.identity
            if (not actual or actual['state']!='gate_ready' or actual['version']!=op['version'] or actual['request_digest']!=_digest(source.nonce)
                or not resource or resource['kind']!='gate_resource' or resource['database_binding']!=_binding(store)
                or (resource['lock_dev'],resource['lock_ino'])!=held[:2] or actual['owner_key']!=store.owner_key(email)
                or actual['database_binding']!=_binding(store) or _epoch(conn,email)!=op['expected_deletion_epoch']):
                raise PermissionError('registration finalization fence changed')
            # The token may already be consumed by this transaction's preceding
            # CAS. Read the original row and allow only its exact local marker.
            current=conn.execute('SELECT * FROM magic_tokens WHERE token_hash=?',(op['token_hash'],)).fetchone()
            if not current or current['email']!=email or current['created_at']!=op['token_created_at'] or current['expires_at']!=op['token_expires_at']:
                raise PermissionError('original token changed')
            if current['consumed_at'] not in (None,marker) or datetime.fromisoformat(current['expires_at'])<=datetime.now(timezone.utc):
                raise PermissionError('token expired or consumed')
            store.require_registration_allowed(conn,email)
        marker=_now();validate()
        user=conn.execute('SELECT * FROM auth_users WHERE email=?',(email,)).fetchone()
        if (created and user is not None) or (not created and (not user or user['session_generation']!=op['expected_generation'] or op['target_generation']!=op['expected_generation'])):
            raise PermissionError('account generation changed')
        permissions={('magic_tokens:UPDATE',op['token_hash']),('auth_registration_operations:UPDATE',op_id),('auth_registration_receipts:INSERT',op_id)}
        if created:
            permissions|={('auth_users:INSERT',email),('auth_notification_outbox:INSERT',email)}
        with _write(conn,store,permissions,validate,_factory=_FACTORY):
            if conn.execute('UPDATE magic_tokens SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL',(marker,op['token_hash'])).rowcount!=1:
                raise PermissionError('token consumption CAS failed')
            if created:
                conn.execute('INSERT INTO auth_users(email,tier,created_at,session_generation,lifecycle) VALUES(?,?,?,?,\'active\')',(email,tier,marker,op['target_generation']))
                conn.execute("INSERT INTO auth_notification_outbox(kind,email,created_at) VALUES('new_user',?,?)",(email,marker))
            _new_receipt(conn,op,'account_finalize',generation=op['target_generation'])
            if conn.execute("UPDATE auth_registration_operations SET state='finalized',version=version+1,updated_at=? WHERE id=? AND state='gate_ready' AND version=?",(marker,op_id,op['version'])).rowcount!=1:
                raise PermissionError('finalize CAS failed')
        user=dict(conn.execute('SELECT * FROM auth_users WHERE email=?',(email,)).fetchone())
        # If COMMIT raises, no authority is created, even if SQLite committed.
        conn.commit()
        return user,created,SessionIssueAuthority(source,store,lease,user,_factory=_FACTORY)


@contextmanager
def register(store, source, token_hash, tier):
    source.require(store)
    # Close the locator transaction before waiting for either filesystem lock.
    with store._connection() as conn:
        conn.execute('BEGIN')
        token,_=_token(conn,store,token_hash)
        gate=conn.execute('SELECT gate_id FROM auth_owner_gates WHERE owner_key=?',(store.owner_key(token['email']),)).fetchone()
    if gate is None:
        op_id,gate_id=_birth(store,source,token_hash)
    else:
        op_id,gate_id=_claim(store,source,token_hash)
        _mark_ready(store,source,op_id)
    if __package__=='web.backend.services':from ..research.authorization import AuthorizationGate
    else:from research.authorization import AuthorizationGate
    with AuthorizationGate(store).owner_gate_id(gate_id) as lease:
        if expected_owner_gate_identity(store,gate_id)!=lease.identity[:2]:
            raise PermissionError('stable gate inode changed')
        yield _finalize(store,source,op_id,lease,tier)


def _execute_script(conn, script):
    statement=''
    for line in script.splitlines(True):
        statement+=line
        if sqlite3.complete_statement(statement):
            conn.execute(statement);statement=''
    if statement.strip():conn.execute(statement)


def _fresh_auth(conn):
    from .auth_store import _BASE_SCHEMA_STATEMENTS,_AUTH_LIFECYCLE_SQL,AuthStore
    if __package__=='web.backend.services':from ..research.store import ResearchStore
    else:from research.store import ResearchStore
    for ddl in _BASE_SCHEMA_STATEMENTS:
        if 'auth_deletion_jobs' not in ddl:conn.execute(ddl)
    conn.execute(_AUTH_LIFECYCLE_SQL)
    objects=ResearchStore._current_structure_declarations(version=15)
    for kind in ('table','index','trigger'):
        for _name,(actual_kind,_target,forms) in objects.items():
            if kind==actual_kind:conn.execute(forms[0])
    conn.execute('INSERT INTO research_schema VALUES(1,15)')
    AuthStore.check_gate_policy(conn,initialize=True)
    for ddl in AUTH_REGISTRATION_DDL:conn.execute(ddl)


def _fresh_history(conn):
    from . import history_db,report_store,connections_store,connections_p3_store
    for module in (history_db,report_store,connections_store,connections_p3_store):
        _execute_script(conn,module._SCHEMA)


def _fresh_sso(conn):
    from .sso_store import _SSO_TABLE_DDL
    for ddl in _SSO_TABLE_DDL:conn.execute(ddl)


def _graph(conn):
    """Complete immutable declaration graph, including xinfo/index/FK shape."""
    if __package__=='web.backend.services':from ..research.store import ResearchStore
    else:from research.store import ResearchStore
    graph=[]
    for kind,name,target,sql in conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY name'):
        quoted='"'+name.replace('"','""')+'"'
        shape=tuple(tuple(r) for r in conn.execute('PRAGMA table_xinfo('+quoted+')')) if kind=='table' else tuple(tuple(r) for r in conn.execute('PRAGMA index_xinfo('+quoted+')')) if kind=='index' else ()
        foreign=tuple(tuple(r) for r in conn.execute('PRAGMA foreign_key_list('+quoted+')')) if kind=='table' else ()
        graph.append((kind,name,target,ResearchStore._normalize_sql(sql) if sql else None,shape,foreign))
    return tuple(graph)


def _expected_graph(create):
    conn=sqlite3.connect(':memory:',isolation_level=None)
    try:
        conn.row_factory=sqlite3.Row
        conn.execute('BEGIN');create(conn)
        return _graph(conn)
    finally:conn.close()


def _safe_file(info):
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
        raise PermissionError('private runtime file is unsafe')


def _create_file(directory,name):
    fd=os.open(name,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
    try:_safe_file(os.fstat(fd));os.fsync(fd)
    finally:os.close(fd)
    os.fsync(directory)


def _mkdir_approved(path):
    from .runtime_paths import _directory_fd
    if not path.is_absolute() or '..' in path.parts:raise PermissionError('canonical offline directory required')
    parent=_directory_fd(path.parent)
    try:
        try:os.mkdir(path.name,0o700,dir_fd=parent)
        except FileExistsError:pass
        directory=os.open(path.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        info=os.fstat(directory)
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:
            os.close(directory);raise PermissionError('private directory is unsafe')
        os.fsync(parent)
        return directory
    finally:os.close(parent)


def bootstrap_private_runtime():
    """Explicit stopped-service operation on code-approved roots only.

    The complete all-absent or all-existing set is checked before database
    writes. A partial/crashed bootstrap requires operator reconciliation.
    No development constructor or profile switch is used.
    """
    from . import runtime_paths as paths
    if not paths.STATE_ROOT.is_absolute() or not paths.CACHE_ROOT.is_absolute() or paths.LOG_ROOT!=paths.STATE_ROOT/'logs':
        raise PermissionError('canonical approved runtime roots required')
    from pathlib import Path
    repository=Path(__file__).resolve().parents[3]
    forbidden=paths._repository_roots(repository)|{repository/'web/frontend'}
    for root in (paths.STATE_ROOT,paths.CACHE_ROOT,paths.LOG_ROOT):
        if '..' in root.parts or any(root==item or root.is_relative_to(item) for item in forbidden):raise PermissionError('offline root overlaps a repository')
    directories=[];lockfd=None
    try:
        state=_mkdir_approved(paths.STATE_ROOT);directories.append(state)
        cache=_mkdir_approved(paths.CACHE_ROOT);directories.append(cache)
        logs=_mkdir_approved(paths.LOG_ROOT);directories.append(logs)
        paths._auth_forbidden_roots()
        try:_create_file(state,'bootstrap-runtime.lock')
        except FileExistsError:pass
        info=os.stat('bootstrap-runtime.lock',dir_fd=state,follow_symlinks=False);_safe_file(info)
        lockfd=os.open('bootstrap-runtime.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=state)
        _safe_file(os.fstat(lockfd))
        if (info.st_dev,info.st_ino)!=(os.fstat(lockfd).st_dev,os.fstat(lockfd).st_ino):raise PermissionError('bootstrap lock changed')
        fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        names=('auth.sqlite3','history.db','sso_replay.sqlite3','favorites.jsonl','favorites.lock','account_deletion_audit.jsonl','registration-provision.lock','research-locks')
        existing=[]
        for name in names:
            try:entry=os.stat(name,dir_fd=state,follow_symlinks=False)
            except FileNotFoundError:continue
            if name=='research-locks':
                if not stat.S_ISDIR(entry.st_mode) or entry.st_uid!=os.geteuid() or stat.S_IMODE(entry.st_mode)!=0o700:raise PermissionError('unsafe gate directory')
            else:_safe_file(entry)
            existing.append(name)
        if existing and len(existing)!=len(names):raise PermissionError('partial private runtime requires offline reconciliation')
        fresh=not existing
        if fresh:
            for name in names:
                if name=='research-locks':os.mkdir(name,0o700,dir_fd=state);os.fsync(state)
                else:_create_file(state,name)
        identity={name:(os.stat(name,dir_fd=state,follow_symlinks=False).st_dev,os.stat(name,dir_fd=state,follow_symlinks=False).st_ino) for name in names}
        for name,create in [('auth.sqlite3',_fresh_auth),('history.db',_fresh_history),('sso_replay.sqlite3',_fresh_sso)]:
            path=paths.STATE_ROOT/name
            conn=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,isolation_level=None,timeout=.1)
            try:
                conn.row_factory=sqlite3.Row
                if not fresh:
                    conn.execute('BEGIN')
                    if _graph(conn)!=_expected_graph(create):raise PermissionError('existing private runtime schema differs')
                    if name=='auth.sqlite3':
                        from .auth_store import AuthStore
                        AuthStore.check_gate_policy(conn)
                        if list(map(tuple,conn.execute('SELECT * FROM research_schema')))!=[(1,15)]:raise PermissionError('exact Research15 required')
                    conn.rollback()
                    if conn.execute('PRAGMA journal_mode').fetchone()[0]!='wal':raise PermissionError('existing private runtime WAL required')
                    if conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0]!='delete':raise PermissionError('offline exclusive journal required')
                    conn.execute('PRAGMA locking_mode=EXCLUSIVE');conn.execute('BEGIN EXCLUSIVE');conn.commit()
                    conn.execute('PRAGMA locking_mode=NORMAL')
                    if conn.execute('PRAGMA journal_mode=WAL').fetchone()[0]!='wal':raise PermissionError('offline WAL restoration required')
                else:
                    conn.execute('BEGIN EXCLUSIVE');create(conn)
                    if _graph(conn)!=_expected_graph(create):raise PermissionError('bootstrap declaration mismatch')
                    if conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('bootstrap FK failure')
                    conn.commit()
                    if conn.execute('PRAGMA journal_mode=WAL').fetchone()[0]!='wal':raise PermissionError('bootstrap WAL unavailable')
                if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise PermissionError('runtime integrity failure')
            finally:conn.close()
        for name in names:
            info=os.stat(name,dir_fd=state,follow_symlinks=False)
            if (info.st_dev,info.st_ino)!=identity[name]:raise PermissionError('bootstrap identity changed')
            if name!='research-locks':_safe_file(info)
        paths._check_current_parent(paths.STATE_ROOT,state,forbidden=paths._auth_forbidden_roots())
        return {'contract':'auth-provision-v1','research_schema':15,'created':fresh}
    finally:
        if lockfd is not None:os.close(lockfd)
        for directory in reversed(directories):os.close(directory)


class _OfflineAuthTarget:
    """Native maintenance binding; never constructs a runtime Auth account."""
    def __init__(self,witness,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('actual offline file witness required')
        self.witness=witness;self.path=witness.path;self._private_auth=True
    @property
    def storage_identity(self):
        self.witness.check();return self.witness.file_identity


def _offline_research_profile(conn):
    from .auth_store import AuthStore
    if __package__=='web.backend.services':from ..research.store import ResearchStore
    else:from research.store import ResearchStore
    profile=AuthStore.check_offline_auth_metadata(conn)
    version=conn.execute('SELECT version FROM research_schema').fetchone()[0]
    if (profile,version) not in (('legacy_auth',10),('auth-provision-v1',10),('auth-provision-v1',11),('auth-provision-v1',12),('auth-provision-v1',13),('auth-provision-v1',14),('auth-provision-v1',15)):
        raise PermissionError('exact offline Auth research profile required')
    ResearchStore._check_structure_version(conn,version)
    return version


@contextmanager
def _offline_auth():
    """Exact RO preflight, then actual exclusive SQLite maintenance lock."""
    from .runtime_paths import PrivateAuthFile,private_auth_path
    from .sqlite_utils import connect_private_auth
    from .auth_store import AuthStore
    if __package__=='web.backend.services':from ..research.store import ResearchStore
    else:from research.store import ResearchStore
    path=private_auth_path();witness=PrivateAuthFile.acquire(path)
    conn=None;backup=None;target=None
    try:
        ro=connect_private_auth(path,readonly=True)
        try:
            ro.execute('BEGIN');AuthStore.check_offline_auth_metadata(ro)
            _offline_research_profile(ro);AuthStore.check_gate_policy(ro)
        finally:ro.close()
        target=_OfflineAuthTarget(witness,_factory=_FACTORY)
        # This is an explicit offline control-file birth after exact source
        # inspection, not a runtime repair of a missing owner gate.
        try:_create_file(witness.parent_fd,'registration-provision.lock')
        except FileExistsError:pass
        with _provision_lock(target):
            conn=connect_private_auth(path,timeout=.1,expected_identity=witness.file_identity)
            conn.execute('PRAGMA busy_timeout=100')
            if conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0]!='delete':raise PermissionError('offline exclusive journal unavailable')
            if conn.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone()[0]!='exclusive':raise PermissionError('offline exclusive mode unavailable')
            conn.execute('BEGIN EXCLUSIVE')
            AuthStore.check_offline_auth_metadata(conn);_offline_research_profile(conn);AuthStore.check_gate_policy(conn)
            conn.commit()
            backup=sqlite3.connect(':memory:',isolation_level=None)
            conn.backup(backup)
            restored=sqlite3.connect(':memory:',isolation_level=None)
            try:
                backup.backup(restored)
                if backup.serialize()!=restored.serialize() or restored.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise PermissionError('offline backup restoration proof failed')
            finally:restored.close()
            yield target,conn
    finally:
        errors=[]
        if conn is not None:
            for cleanup in (conn.rollback,lambda:conn.execute('PRAGMA foreign_keys=ON'),lambda:conn.execute('PRAGMA locking_mode=NORMAL'),lambda:conn.execute('PRAGMA journal_mode=WAL'),conn.close):
                try:cleanup()
                except BaseException as error:errors.append(error)
        if backup is not None:
            try:backup.close()
            except BaseException as error:errors.append(error)
        witness.close()
        import sys
        if errors and sys.exc_info()[0] is None:raise errors[0]


def migrate_private_auth_registration():
    """Explicit precise legacy Auth graph -> two tables/guards; Research10 stays."""
    from .auth_store import AuthStore
    if __package__=='web.backend.services':from ..research.store import ResearchStore
    else:from research.store import ResearchStore
    with _offline_auth() as (target,conn):
        conn.execute('BEGIN EXCLUSIVE')
        profile=AuthStore.check_offline_auth_metadata(conn)
        if profile=='legacy_auth':
            for ddl in AUTH_REGISTRATION_DDL:conn.execute(ddl)
        if AuthStore.check_offline_auth_metadata(conn)!='auth-provision-v1':raise PermissionError('registration migration incomplete')
        research_version=_offline_research_profile(conn)
        if conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('registration migration FK failure')
        conn.commit()
        return {'contract':'auth-provision-v1','research_schema':research_version,'migrated':profile=='legacy_auth'}


def admit_private_gate(owner_key, *, operation_id=None):
    """Explicit offline resource publication, never account finalization.

    Existing mappings and stable inodes are only admitted under actual exclusive
    maintenance. An orphan birth requires the precise same operation ID; the
    resource receipt is attached to it and that operation is closed, never
    resumed as an online verification request.
    """
    from .auth_store import AuthStore
    from .runtime_paths import require_private_auth_lock_dir,_check_current_parent,_auth_forbidden_roots
    if not isinstance(owner_key,str) or not owner_key.startswith('account-owner.gate:v2:'):raise PermissionError('opaque existing owner key required')
    with _offline_auth() as (target,conn):
        conn.execute('BEGIN EXCLUSIVE')
        if AuthStore.check_offline_auth_metadata(conn)!='auth-provision-v1':raise PermissionError('current registration schema required')
        gate=conn.execute('SELECT gate_id FROM auth_owner_gates WHERE owner_key=?',(owner_key,)).fetchone()
        if not gate:raise PermissionError('existing mapping required')
        gate_id=gate['gate_id']
        from uuid import UUID
        if str(UUID(gate_id,version=4))!=gate_id:raise PermissionError('canonical gate required')
        prior=conn.execute('SELECT * FROM auth_registration_operations WHERE id=?',(operation_id,)).fetchone() if operation_id else None
        if operation_id and (not prior or prior['owner_key']!=owner_key or prior['gate_id']!=gate_id or prior['database_binding']!=_binding(target) or prior['state'] not in ('claimed','gate_ready','closed')):
            raise PermissionError('actual same orphan operation required')
        original_token=None
        if prior:
            original_token=conn.execute('SELECT * FROM magic_tokens WHERE token_hash=?',(prior['token_hash'],)).fetchone()
            if (not original_token or original_token['consumed_at'] is not None
                or AuthStore.owner_key(original_token['email'])!=owner_key
                or original_token['created_at']!=prior['token_created_at'] or original_token['expires_at']!=prior['token_expires_at']
                or prior['origin_digest'] is None or prior['request_digest'] is None):
                raise PermissionError('orphan source token no longer exists or changed')
        if not operation_id and conn.execute("SELECT 1 FROM auth_registration_operations WHERE gate_id=? AND kind!='offline_gate_admission'",(gate_id,)).fetchone():
            raise PermissionError('orphan resource requires exact operation reconciliation')
        root=require_private_auth_lock_dir(target.path)
        directory=os.open('research-locks',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=target.witness.parent_fd)
        fd=None
        try:
            _check_current_parent(root,directory,forbidden=_auth_forbidden_roots())
            entry=os.stat(gate_id+'.lock',dir_fd=directory,follow_symlinks=False);_safe_file(entry)
            fd=os.open(gate_id+'.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
            info=os.fstat(fd);_safe_file(info)
            if (info.st_dev,info.st_ino)!=(entry.st_dev,entry.st_ino):raise PermissionError('resource changed')
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            receipt=_receipt(conn,gate_id)
            if receipt:
                def validate_existing():
                    _native(conn,target)
                    _check_current_parent(root,directory,forbidden=_auth_forbidden_roots())
                    current=os.stat(gate_id+'.lock',dir_fd=directory,follow_symlinks=False)
                    _safe_file(current);held=os.fstat(fd);_safe_file(held)
                    identity=(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)
                    if (tuple((current.st_dev,current.st_ino,current.st_uid,stat.S_IMODE(current.st_mode),current.st_nlink))!=identity
                        or (held.st_dev,held.st_ino,held.st_uid,stat.S_IMODE(held.st_mode),held.st_nlink)!=identity
                        or receipt['owner_key']!=owner_key or receipt['gate_id']!=gate_id
                        or receipt['database_binding']!=_binding(target)
                        or (receipt['lock_dev'],receipt['lock_ino'])!=(info.st_dev,info.st_ino)):
                        raise PermissionError('admitted resource identity differs')
                    if prior:
                        actual=conn.execute('SELECT * FROM auth_registration_operations WHERE id=?',(prior['id'],)).fetchone()
                        token=conn.execute('SELECT * FROM magic_tokens WHERE token_hash=?',(prior['token_hash'],)).fetchone()
                        if (not actual or actual['state']!=prior['state'] or actual['version']!=prior['version']
                            or actual['owner_key']!=owner_key or actual['database_binding']!=_binding(target)
                            or not token or token['consumed_at'] is not None or AuthStore.owner_key(token['email'])!=owner_key
                            or token['created_at']!=prior['token_created_at'] or token['expires_at']!=prior['token_expires_at']
                            or (prior['state']=='gate_ready' and prior['resource_receipt_id']!=receipt['id'])):
                            raise PermissionError('same operation resource reconciliation changed')
                validate_existing()
                if prior and prior['state'] in ('claimed','gate_ready'):
                    install_hook(conn)
                    with _write(conn,target,{('auth_registration_operations:UPDATE',prior['id'])},validate_existing,_factory=_FACTORY):
                        if conn.execute("UPDATE auth_registration_operations SET state='closed',version=version+1,closed_reason='resource_unknown',last_failure_code='resource_unknown',updated_at=? WHERE id=? AND state=? AND version=?",(_now(),prior['id'],prior['state'],prior['version'])).rowcount!=1:
                            raise PermissionError('existing resource operation retirement CAS failed')
                    conn.commit()
                else:conn.rollback()
                return {'admitted':False}
            op_id=str(uuid4());now=_now()
            install_hook(conn)
            def validate():
                _native(conn,target)
                _check_current_parent(root,directory,forbidden=_auth_forbidden_roots())
                current=os.stat(gate_id+'.lock',dir_fd=directory,follow_symlinks=False);_safe_file(current)
                if (current.st_dev,current.st_ino)!=(info.st_dev,info.st_ino):raise PermissionError('offline gate changed')
            permissions={('auth_registration_operations:INSERT',op_id),('auth_registration_operations:UPDATE',op_id),('auth_registration_receipts:INSERT',op_id)}
            if prior and prior['state']=='claimed':permissions.add(('auth_registration_operations:UPDATE',prior['id']))
            with _write(conn,target,permissions,validate,_factory=_FACTORY):
                conn.execute("""INSERT INTO auth_registration_operations(id,record_version,kind,owner_key,gate_id,state,version,database_binding,origin_digest,created_at,updated_at)
                    VALUES(?,'auth-provision-operation-v1','offline_gate_admission',?,?,'claimed',1,?,?,?,?)""",
                    (op_id,owner_key,gate_id,_binding(target),_digest(['offline-gate',operation_id,info.st_dev,info.st_ino]),now,now))
                op=conn.execute('SELECT * FROM auth_registration_operations WHERE id=?',(op_id,)).fetchone()
                ref=_new_receipt(conn,op,'gate_resource',identity=(info.st_dev,info.st_ino))
                conn.execute("UPDATE auth_registration_operations SET state='gate_ready',version=version+1,resource_receipt_id=?,updated_at=? WHERE id=?",(ref,now,op_id))
                conn.execute("UPDATE auth_registration_operations SET state='closed',version=version+1,closed_reason='admitted',updated_at=? WHERE id=?",(now,op_id))
                if prior and prior['state']=='claimed':
                    if conn.execute("UPDATE auth_registration_operations SET state='closed',version=version+1,closed_reason='resource_unknown',last_failure_code='resource_unknown',updated_at=? WHERE id=? AND state='claimed' AND version=?",(now,prior['id'],prior['version'])).rowcount!=1:
                        raise PermissionError('orphan retirement CAS failed')
            conn.commit();return {'admitted':True}
        finally:
            if fd is not None:os.close(fd)
            os.close(directory)
