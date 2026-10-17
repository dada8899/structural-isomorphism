"""Local mathematics provenance, exact V10 overlay and offline provisioning.

JSON, a PID, and a claimed guard are never execution or write capabilities.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
from uuid import uuid4

from .authorization import AuthorizationGate, OwnerGateLease
from .errors import ResearchError, not_found
from .formula_schemas import canonical, digest

SCHEMA_VERSION=10
POLICY='formula-policy-v1'
TASK_POLICY='local-formula-v1'
_FACTORY=object()
_WRITES={}
_MAINTENANCE={}
PROTECTED=('research_formula_revisions','research_formula_runs')
FORMULA_TABLES=(
    """CREATE TABLE research_formula_revisions (
        research_id TEXT NOT NULL, revision INTEGER NOT NULL,
        formula_json TEXT CHECK(formula_json IS NULL OR (json_valid(formula_json) AND length(CAST(formula_json AS BLOB))<=65536)),
        formula_digest TEXT NOT NULL CHECK(length(formula_digest)=64 AND formula_digest NOT GLOB '*[^a-f0-9]*'),
        PRIMARY KEY(research_id,revision),
        FOREIGN KEY(research_id,revision) REFERENCES research_revisions(research_id,revision))""",
    """CREATE TABLE research_formula_runs (
        task_id TEXT NOT NULL PRIMARY KEY REFERENCES research_tasks(id),
        result_ref TEXT NOT NULL UNIQUE, admission_json TEXT CHECK(admission_json IS NULL OR (json_valid(admission_json) AND length(CAST(admission_json AS BLOB))<=65536)),
        claim_nonce TEXT NOT NULL UNIQUE, state TEXT NOT NULL CHECK(state IN ('claimed','returned','closed')),
        receipt_json TEXT CHECK(receipt_json IS NULL OR (json_valid(receipt_json) AND length(CAST(receipt_json AS BLOB))<=4096)),
        result_json TEXT CHECK(result_json IS NULL OR (json_valid(result_json) AND length(CAST(result_json AS BLOB))<=524288)),
        commit_json TEXT CHECK(commit_json IS NULL OR (json_valid(commit_json) AND length(CAST(commit_json AS BLOB))<=4096)),
        CHECK((state='claimed' AND admission_json IS NOT NULL AND receipt_json IS NULL AND result_json IS NULL AND commit_json IS NULL)
            OR (state='returned' AND admission_json IS NOT NULL AND receipt_json IS NOT NULL AND result_json IS NOT NULL AND commit_json IS NOT NULL)
            OR (state='closed' AND receipt_json IS NULL AND result_json IS NULL AND commit_json IS NULL)))""",
)

def _guards():
    result=[]
    for table in PROTECTED:
        for action in ('INSERT','UPDATE','DELETE'):
            result.append(f"CREATE TRIGGER {table}_{action.lower()}_control BEFORE {action} ON {table} BEGIN SELECT CASE WHEN research_formula_write_allowed('{table}','{action}')!=1 THEN RAISE(ABORT,'controlled formula writer required') END; END")
        keys='NEW.rowid=OLD.rowid OR '+('NEW.research_id=OLD.research_id AND NEW.revision=OLD.revision' if table.endswith('revisions') else 'NEW.task_id=OLD.task_id OR NEW.result_ref=OLD.result_ref OR NEW.claim_nonce=OLD.claim_nonce')
        # BEFORE INSERT catches every OR REPLACE path even with recursive_triggers=0.
        result.append(f"CREATE TRIGGER {table}_no_replace BEFORE INSERT ON {table} WHEN EXISTS(SELECT 1 FROM {table} AS OLD WHERE {keys}) BEGIN SELECT RAISE(ABORT,'formula replacement forbidden'); END")
    result.append("CREATE TRIGGER research_formula_revision_identity BEFORE UPDATE ON research_formula_revisions WHEN NEW.rowid IS NOT OLD.rowid OR NEW.research_id IS NOT OLD.research_id OR NEW.revision IS NOT OLD.revision OR NEW.formula_digest IS NOT OLD.formula_digest OR NEW.formula_json IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable formula revision'); END")
    result.append("CREATE TRIGGER research_formula_run_identity BEFORE UPDATE ON research_formula_runs WHEN NEW.rowid IS NOT OLD.rowid OR NEW.task_id IS NOT OLD.task_id OR NEW.result_ref IS NOT OLD.result_ref OR NEW.claim_nonce IS NOT OLD.claim_nonce OR (NEW.admission_json IS NOT OLD.admission_json AND NOT (NEW.state='closed' AND NEW.admission_json IS NULL)) OR OLD.state='closed' OR (OLD.state='returned' AND NEW.state!='closed') BEGIN SELECT RAISE(ABORT,'immutable formula run binding'); END")
    return tuple(result)
FORMULA_DDL=(*FORMULA_TABLES,*_guards())


def formula_table_overlay(tasks,steps):
    return {'research_tasks':tasks.replace("'c0-fixture-v1','d1-source-only-v1'", "'c0-fixture-v1','d1-source-only-v1','local-formula-v1'").replace("'offline_probe','live'", "'offline_probe','live','local_math'"),
        'research_steps':steps.replace("'fetch_source','compose_report','model_report'", "'fetch_source','compose_report','model_report','formula_check'")}


def statement_allowed(conn,action,table,column):
    if action not in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE) or table not in PROTECTED:return True
    entry=_WRITES.get(id(conn))
    return bool(entry and entry['conn'] is conn and entry['pid']==os.getpid() and conn.in_transaction and entry['scope'].active)


def install_hook(conn):
    pid=os.getpid()
    def allowed(table,operation):
        entry=_WRITES.get(id(conn))
        if not (entry and pid==os.getpid() and entry['pid']==pid and entry['conn'] is conn and conn.in_transaction
                and entry['scope'].active and entry['table']==table and entry['operation']==operation):return 0
        try:entry['lease'].identity;entry['validate']();return 1
        except (PermissionError,ResearchError,ValueError,TypeError,OSError,sqlite3.Error):return 0
    conn.create_function('research_formula_write_allowed',2,allowed)
    conn.create_function('research_formula_guard_version',0,lambda:10 if pid==os.getpid() else 0)


def require_hook(conn):
    try:row=conn.execute("SELECT research_formula_guard_version(),research_formula_write_allowed('','')").fetchone()
    except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'公式连接守卫不可用。') from None
    if tuple(row)!=(10,0):raise ResearchError('SCHEMA_UNSUPPORTED',503,'公式连接守卫不匹配。')


@contextmanager
def _write(conn,store,lease,table,operation,validate,*,_factory=None):
    if _factory is not _FACTORY or table not in PROTECTED:raise PermissionError('actual formula producer required')
    from .paid_control import _SCOPES
    from .store import ResearchStore
    scope=_SCOPES.get(id(conn))
    database=next((r[2] for r in conn.execute('PRAGMA database_list') if r[1]=='main'),None)
    if (not isinstance(conn,sqlite3.Connection) or type(store) is not ResearchStore or type(lease) is not OwnerGateLease
            or not scope or scope.conn is not conn or not scope.write or not scope.active or scope.pid!=os.getpid()
            or not conn.in_transaction or not database or Path(database).resolve()!=store.path.resolve()
            or conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1 or id(conn) in _WRITES):
        raise PermissionError('native active formula transaction required')
    lease.identity;ResearchStore._check_v10(conn);validate()
    _WRITES[id(conn)]={'conn':conn,'pid':os.getpid(),'scope':scope,'lease':lease,'table':table,'operation':operation,'validate':validate}
    scope.refresh_authorizer()
    try:yield
    finally:_WRITES.pop(id(conn),None);scope.refresh_authorizer()


class FormulaMaintenance:
    """Actual exclusive SQLite owner, pinned files and verified in-memory backup."""
    __slots__=('store','conn','backup','identity','lockfd','parentfd','parent_identity','pid','active','journal','reference','source_version')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _FACTORY:raise TypeError('offline maintenance context required')
        for k,v in values.items():object.__setattr__(self,k,v)
    def __setattr__(self,*args):raise TypeError('maintenance capability immutable')
    def __reduce__(self):raise TypeError('maintenance cannot be serialized')
    def require(self,store):
        if not self.active or self.pid!=os.getpid() or self.store is not store or _MAINTENANCE.get(self.reference) is not self:
            raise PermissionError('actual maintenance capability required')
        _check_database_path(store.path,self.parentfd,self.parent_identity,self.identity)
        if type(store) is _OfflineFormulaTarget:store.witness.check()
        database=next((row[2] for row in self.conn.execute('PRAGMA database_list') if row[1]=='main'),None)
        if not database or Path(database)!=store.path:raise PermissionError('native database binding changed')
        info=os.fstat(self.lockfd)
        named=os.stat(str(store.path)+'.formula-maintenance',follow_symlinks=False)
        if (info.st_dev,info.st_ino)!=(named.st_dev,named.st_ino):raise PermissionError('maintenance lock changed')
        _safe_file(info)
        if self.conn.execute('PRAGMA locking_mode').fetchone()[0]!='exclusive':raise PermissionError('exclusive database owner required')
    def restore(self):
        """Rollback drills restore into the same open inode, never swap paths."""
        self.require(self.store)
        self.conn.rollback()
        self.backup.backup(self.conn)
        self.conn.execute('PRAGMA foreign_keys=ON');self.conn.execute('BEGIN EXCLUSIVE')
        _check_profile(self.conn,self.store,(self.source_version,))
        if self.conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('restoration FK failure')
        self.conn.commit();self.require(self.store)


def _safe_file(info):
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
        raise PermissionError('private regular maintenance file required')


@contextmanager
def _maintenance_target(store,*,versions=(9,),final_journal=None):
    """Fails boundedly if a live reader/writer prevents exclusive maintenance.

    No boolean attests that services stopped. DELETE journal + EXCLUSIVE mode
    obtains SQLite's actual exclusive lock and retains it through migration.
    """
    from .store import ResearchStore
    if type(store) not in (ResearchStore,_OfflineFormulaTarget):raise PermissionError('canonical maintenance target required')
    lockfd=parentfd=None;conn=backup=None;cap=None;old_journal=None
    try:
        # Never open/dup/close an ordinary DB FD: POSIX close would release
        # same-process SQLite locks held by unrelated native connections.
        parentfd=os.open(store.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        parent_info=os.fstat(parentfd);parent_identity=(parent_info.st_dev,parent_info.st_ino)
        info=os.stat(store.path.name,dir_fd=parentfd,follow_symlinks=False);_safe_file(info)
        identity=(info.st_dev,info.st_ino)
        _check_database_path(store.path,parentfd,parent_identity,identity)
        # Read-only exact V9 preflight precedes journal/DDL mutations.
        ro=sqlite3.connect(store.path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=.1)
        try:
            ro.row_factory=sqlite3.Row
            from .financial_guard import install_default_hook
            install_default_hook(ro);ro.execute('PRAGMA foreign_keys=ON');ro.execute('BEGIN')
            source_version=_check_profile(ro,store,versions);ro.rollback()
            _check_database_path(store.path,parentfd,parent_identity,identity)
        finally:ro.close()
        lockfd=os.open(str(store.path)+'.formula-maintenance',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        _safe_file(os.fstat(lockfd));fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        conn=sqlite3.connect(store.path.as_uri()+'?mode=rw',uri=True,isolation_level=None,timeout=.1,cached_statements=0);conn.row_factory=sqlite3.Row
        _check_database_path(store.path,parentfd,parent_identity,identity)
        install_default_hook(conn);conn.execute('PRAGMA busy_timeout=100');conn.execute('PRAGMA foreign_keys=ON')
        old_journal=conn.execute('PRAGMA journal_mode').fetchone()[0]
        # journal transition requires absent WAL readers; never pretend a flock
        # is evidence that unrelated SQLite consumers honor maintenance.
        _check_database_path(store.path,parentfd,parent_identity,identity)
        if conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0]!='delete':raise PermissionError('exclusive journal unavailable')
        if conn.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone()[0]!='exclusive':raise PermissionError('exclusive mode unavailable')
        conn.execute('BEGIN EXCLUSIVE');_check_profile(conn,store,(source_version,));conn.commit()
        backup=sqlite3.connect(':memory:',isolation_level=None);conn.backup(backup)
        restored=sqlite3.connect(':memory:',isolation_level=None)
        try:
            backup.backup(restored)
            if backup.serialize()!=restored.serialize() or restored.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or restored.execute('PRAGMA foreign_key_check').fetchall():
                raise PermissionError('backup restore proof failed')
        finally:restored.close()
        ref=str(uuid4());cap=FormulaMaintenance(_factory=_FACTORY,store=store,conn=conn,backup=backup,identity=identity,
            lockfd=lockfd,parentfd=parentfd,parent_identity=parent_identity,pid=os.getpid(),active=True,journal=old_journal,reference=ref,source_version=source_version)
        _MAINTENANCE[ref]=cap;cap.require(store)
        yield cap
    finally:
        import sys
        original=sys.exc_info()[0] is not None
        errors=[]
        if cap:object.__setattr__(cap,'active',False);_MAINTENANCE.pop(cap.reference,None)
        # Every cleanup is independent. A failed rollback/FK readback/journal
        # restoration must never skip native close or release owned resources.
        if conn:
            for cleanup in (conn.rollback,
                    lambda:conn.execute('PRAGMA foreign_keys=ON'),
                    lambda:_require_fk_on(conn),
                    lambda:conn.execute('PRAGMA locking_mode=NORMAL'),
                    lambda:conn.execute('PRAGMA journal_mode='+(final_journal or old_journal)) if (final_journal or old_journal) in ('wal','delete') else None,
                    conn.close):
                try:cleanup()
                except BaseException as error:errors.append(error)
        if backup:
            try:backup.close()
            except BaseException as error:errors.append(error)
        for fd in (lockfd,parentfd):
            if fd is not None:
                try:os.close(fd)
                except BaseException as error:errors.append(error)
        if errors and not original:raise errors[0]


def _require_fk_on(conn):
    if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1:raise PermissionError('FK restoration failed')


def _check_database_path(path,parentfd,parent_identity,identity):
    for info in (os.fstat(parentfd),os.stat(path.parent,follow_symlinks=False)):
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev,info.st_ino)!=parent_identity:raise PermissionError('database parent changed')
    for info in (os.stat(path.name,dir_fd=parentfd,follow_symlinks=False),os.stat(path,follow_symlinks=False)):
        _safe_file(info)
        if (info.st_dev,info.st_ino)!=identity:raise PermissionError('database inode changed')


def migrate_v10(store,*,maintenance):
    if type(maintenance) is not FormulaMaintenance:raise PermissionError('actual offline maintenance required')
    maintenance.require(store);conn=maintenance.conn
    try:
        conn.execute('PRAGMA foreign_keys=OFF')
        if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=0:raise PermissionError('FK disable failed')
        conn.execute('BEGIN EXCLUSIVE');maintenance.require(store)
        _check_profile(conn,store,(9,))
        overlays=store._formula_tables();objects=store._current_structure_declarations(version=9)
        extras=[forms[0] for kind,target,forms in objects.values() if target in overlays and kind!='table']
        for name,ddl in overlays.items():
            columns=[row[1] for row in conn.execute('PRAGMA table_info('+name+')')]
            if len(columns)!=len(set(columns)):raise PermissionError('ambiguous source columns')
            conn.execute(ddl.replace('CREATE TABLE IF NOT EXISTS ','CREATE TABLE ',1).replace('CREATE TABLE '+name,'CREATE TABLE '+name+'_v10',1))
            names=','.join('"'+c+'"' for c in columns)
            conn.execute('INSERT INTO '+name+'_v10 ('+names+') SELECT '+names+' FROM '+name)
        for name in reversed(tuple(overlays)):conn.execute('DROP TABLE '+name)
        for name in overlays:conn.execute('ALTER TABLE '+name+'_v10 RENAME TO '+name)
        for ddl in extras:conn.execute(ddl)
        for ddl in FORMULA_DDL:conn.execute(ddl)
        if conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('migration FK failure')
        conn.execute('UPDATE research_schema SET version=10 WHERE id=1 AND version=9')
        store._check_v10(conn);maintenance.require(store);conn.commit()
    except BaseException:conn.rollback();raise
    finally:
        conn.execute('PRAGMA foreign_keys=ON')
        if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1:raise PermissionError('FK restoration failed')


def erase_for_deletion(conn,*,store,lease,pid,job_id):
    from .paid_control import verify_deletion_origin
    verify_deletion_origin(conn,store=store,lease=lease,job_id=job_id)
    def validate():
        job=conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'",(job_id,)).fetchone()
        principal=conn.execute("SELECT * FROM research_principals WHERE id=? AND status='deleting'",(pid,)).fetchone()
        if (not job or not principal or principal['normalized_email']!=job['owner_email']
                or principal['session_generation']!=job['session_generation'] or principal['gate_id']!=job['gate_id']):
            raise PermissionError('actual deleting principal required')
    with _write(conn,store,lease,'research_formula_runs','UPDATE',validate,_factory=_FACTORY):
        conn.execute("UPDATE research_formula_runs SET state='closed',admission_json=NULL,receipt_json=NULL,result_json=NULL,commit_json=NULL WHERE state!='closed' AND task_id IN (SELECT id FROM research_tasks WHERE principal_id=?)",(pid,))
    with _write(conn,store,lease,'research_formula_revisions','DELETE',validate,_factory=_FACTORY):
        conn.execute('DELETE FROM research_formula_revisions WHERE research_id IN (SELECT id FROM research_controls WHERE owner_id=?)',(pid,))


class _OfflineFormulaTarget:
    """Only an actual canonical file witness; never a runtime store instance."""
    __slots__=('path','witness')
    def __init__(self,witness,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('actual canonical private file required')
        self.path,self.witness=witness.path,witness
    def __getattr__(self,name):
        # Fixed static code declarations/checkers, no runtime constructor or
        # dynamic storage/configuration methods are delegated.
        if name not in {'_check_structure_version','_check_v9','_check_v10','_formula_tables','_current_structure_declarations'}:
            raise AttributeError(name)
        from .store import ResearchStore
        return getattr(ResearchStore,name)


def _check_profile(conn,target,versions):
    from .store import ResearchStore
    if __package__=='web.backend.research':from ..services.auth_store import AuthStore,_auth_metadata,_auth_final_contracts
    else:from services.auth_store import AuthStore,_auth_metadata,_auth_final_contracts
    allowed=_auth_final_contracts()
    if _auth_metadata(conn,allowed=allowed) not in allowed:raise PermissionError('complete static Auth metadata required')
    AuthStore.check_gate_policy(conn)
    marker=[tuple(row) for row in conn.execute('SELECT id,version FROM research_schema')]
    if len(marker)!=1 or marker[0][0]!=1 or type(marker[0][1]) is not int or marker[0][1] not in versions:
        raise PermissionError('exact offline research version required')
    version=marker[0][1]
    ResearchStore._check_structure_version(conn,version)
    if version==9:ResearchStore._check_v9(conn)
    elif version==10:ResearchStore._check_v10(conn)
    else:raise PermissionError('offline profile unsupported')
    return version


@contextmanager
def formula_maintenance(store):
    """Development/previously bound store port; never an automatic migration."""
    from .store import ResearchStore
    if type(store) is not ResearchStore:raise PermissionError('canonical store required')
    with _maintenance_target(store) as capability:yield capability


@contextmanager
def _offline_maintenance(path,versions):
    if __package__=='web.backend.research':from ..services.runtime_paths import PrivateAuthFile,private_auth_path
    else:from services.runtime_paths import PrivateAuthFile,private_auth_path
    # This entry does not consume an environment boolean, HTTP request, owner
    # DTO, or a fabricated current store. Only the code-owned static path wins.
    if type(path) is not type(Path()) or path!=private_auth_path():raise PermissionError('approved canonical Auth path required')
    witness=PrivateAuthFile.acquire(path)
    try:
        target=_OfflineFormulaTarget(witness,_factory=_FACTORY)
        with _maintenance_target(target,versions=versions,final_journal='wal') as capability:
            witness.check();yield target,capability
    finally:witness.close()


def provision_formula_v10(path):
    """Explicit offline provisioning after Ops independently secures a backup.

    The in-memory algorithm backup is not a durable production recovery copy.
    Never used by normal Auth/Research constructors or any HTTP route.
    """
    with _offline_maintenance(path,(9,)) as (target,capability):
        migrate_v10(target,maintenance=capability)
        capability.require(target)
        capability.conn.execute('BEGIN')
        try:_check_profile(capability.conn,target,(10,))
        finally:capability.conn.rollback()
        identity=capability.identity
    return {'schema_version':10,'journal_mode':'wal','database_identity':list(identity),
        'backup_scope':'in_memory_algorithm_recovery_only'}


def recover_formula_journal(path):
    """Reconcile a killed maintenance process; no schema repair or replay."""
    with _offline_maintenance(path,(9,10)) as (target,capability):
        capability.conn.execute('BEGIN')
        try:version=_check_profile(capability.conn,target,(9,10))
        finally:capability.conn.rollback()
        identity=capability.identity
    return {'schema_version':version,'journal_mode':'wal','database_identity':list(identity),
        'current_app_compatible':version==10,'schema_repaired':False}
