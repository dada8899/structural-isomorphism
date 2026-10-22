"""V11 Source-only native writers and retained task-resource bindings.

A stored identity is a binding, never a lease or permission to send.
"""
from contextlib import contextmanager
from functools import lru_cache
import json
import os
import sqlite3
from .evidence_schemas import canonical,sha256
from .errors import ResearchError

VERSION=11
_FACTORY=object()
_WRITES={}
TABLES=('research_source_approvals','research_source_chains','research_source_runs','research_source_requests','research_source_resources')
RESOURCE_DDL="""CREATE TABLE research_source_resources (
 task_id TEXT PRIMARY KEY, owner_gate_id TEXT NOT NULL,
 admission_version TEXT NOT NULL CHECK(admission_version='source-admission-v1'),
 admission_json TEXT CHECK(admission_json IS NULL OR (json_valid(admission_json) AND length(CAST(admission_json AS BLOB))<=32768)),
 admission_digest TEXT NOT NULL CHECK(length(admission_digest)=64 AND admission_digest NOT GLOB '*[^a-f0-9]*'),
 task_gate_identity TEXT CHECK(task_gate_identity IS NULL OR json_valid(task_gate_identity)),
 write_epoch INTEGER NOT NULL DEFAULT 1 CHECK(typeof(write_epoch)='integer' AND write_epoch>0),
 state TEXT NOT NULL CHECK(state IN ('admitted','running','closed')),
 CHECK(state='closed' OR admission_json IS NOT NULL))"""

CONSENT_ORIGIN='authenticated-source-approve-v1'
CONSENT_COLUMNS=(('consent_origin',"TEXT CHECK(consent_origin IS NULL OR consent_origin='authenticated-source-approve-v1')"),
    ('consent_digest',"TEXT CHECK((consent_origin IS NULL AND consent_digest IS NULL) OR (consent_origin IS NOT NULL AND typeof(consent_digest)='text' AND length(consent_digest)=64 AND consent_digest NOT GLOB '*[^a-f0-9]*'))"))


def approval_table():
    from .source_integration import SOURCE_DDL
    return SOURCE_DDL[0].rstrip()[:-1]+', '+', '.join(name+' '+ddl for name,ddl in CONSENT_COLUMNS)+')'


@lru_cache(maxsize=1)
def declarations():
    from .store import ResearchStore
    from .source_integration import SOURCE_DDL
    objects={sql.split()[2]:sql for sql in (*SOURCE_DDL,RESOURCE_DDL)}
    objects['research_source_approvals']=approval_table()
    result=[approval_table(),RESOURCE_DDL]
    unique={
      'research_source_approvals':['NEW.id IS OLD.id'],
      'research_source_chains':['NEW.id IS OLD.id','NEW.principal_id IS OLD.principal_id AND NEW.research_id IS OLD.research_id AND NEW.fingerprint IS OLD.fingerprint'],
      'research_source_runs':['NEW.task_id IS OLD.task_id'],
      'research_source_requests':['NEW.id IS OLD.id','NEW.dispatch_id IS OLD.dispatch_id','NEW.chain_id IS OLD.chain_id AND NEW.ordinal IS OLD.ordinal','NEW.task_id IS OLD.task_id AND NEW.semantic IS OLD.semantic AND NEW.target_digest IS OLD.target_digest'],
      'research_source_resources':['NEW.task_id IS OLD.task_id']}
    for table,ddl in objects.items():
        columns=tuple(name for name,_ in ResearchStore._declared_columns(ddl))
        def image(prefix):return "json_object('rowid',"+prefix+".rowid,"+','.join("'"+name+"',"+prefix+'.'+name for name in columns)+')'
        for operation in ('INSERT','UPDATE','DELETE'):
            before="'null'" if operation=='INSERT' else image('OLD')
            after="'null'" if operation=='DELETE' else image('NEW')
            result.append(f"CREATE TRIGGER {table}_v11_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT CASE WHEN research_source_write_allowed('{table}','{operation}',{before},{after})!=1 THEN RAISE(ABORT,'native Source writer required') END; END")
        result.append(f"CREATE TRIGGER {table}_v11_no_replace BEFORE INSERT ON {table} WHEN EXISTS(SELECT 1 FROM {table} OLD WHERE NEW.rowid=OLD.rowid OR "+' OR '.join('('+term+')' for term in unique[table])+") BEGIN SELECT RAISE(ABORT,'Source replacement forbidden'); END")
        key='task_id' if table in ('research_source_runs','research_source_resources') else 'id'
        result.append(f"CREATE TRIGGER {table}_v11_identity BEFORE UPDATE ON {table} WHEN NEW.rowid IS NOT OLD.rowid OR NEW.{key} IS NOT OLD.{key} BEGIN SELECT RAISE(ABORT,'Source row identity immutable'); END")
    mutable={'research_source_approvals':{'status','consumed_task_id'},
      'research_source_chains':{'used','research_id','fingerprint'},
      'research_source_runs':{'started','write_epoch','task_gate_identity','approval_id','fingerprint'},
      'research_source_requests':{'outcome','execution_closed','closure_ref','closure_proof','ended_at','http_status','safe_code'}}
    for table,fields in mutable.items():
        columns=tuple(name for name,_ in ResearchStore._declared_columns(objects[table]))
        changed=' OR '.join('NEW.'+name+' IS NOT OLD.'+name for name in columns if name not in fields)
        result.append(f"CREATE TRIGGER {table}_v11_domain BEFORE UPDATE ON {table} WHEN {changed} BEGIN SELECT RAISE(ABORT,'immutable Source domain'); END")
    result.extend((
      "CREATE TRIGGER research_source_approval_transition BEFORE UPDATE ON research_source_approvals WHEN (NEW.status IS NOT OLD.status AND NOT ((OLD.status='active' AND NEW.status IN ('consumed','revoked')) OR (OLD.status='consumed' AND NEW.status='revoked'))) OR (OLD.consumed_task_id IS NOT NULL AND NEW.consumed_task_id IS NOT OLD.consumed_task_id) BEGIN SELECT RAISE(ABORT,'Source approval cannot be reapproved'); END",
      "CREATE TRIGGER research_source_chain_domain BEFORE UPDATE ON research_source_chains WHEN (NEW.research_id IS NOT OLD.research_id AND NEW.research_id IS NOT NULL) OR (NEW.fingerprint IS NOT OLD.fingerprint AND NEW.fingerprint IS NOT NULL) BEGIN SELECT RAISE(ABORT,'Source chain cannot be rebound'); END",
      "CREATE TRIGGER research_source_run_domain BEFORE UPDATE ON research_source_runs WHEN (NEW.approval_id IS NOT OLD.approval_id AND NEW.approval_id IS NOT NULL) OR (NEW.fingerprint IS NOT OLD.fingerprint AND NEW.fingerprint IS NOT NULL) BEGIN SELECT RAISE(ABORT,'Source run cannot be rebound'); END",
      "CREATE TRIGGER research_source_request_transition BEFORE UPDATE ON research_source_requests WHEN (OLD.outcome!='SENDING' AND NEW.outcome IS NOT OLD.outcome) OR (OLD.execution_closed=1 AND (NEW.outcome IS NOT OLD.outcome OR NEW.http_status IS NOT OLD.http_status OR NEW.ended_at IS NOT OLD.ended_at OR NEW.safe_code IS NOT OLD.safe_code)) BEGIN SELECT RAISE(ABORT,'Source observation is final'); END",
      "CREATE TRIGGER research_source_resource_binding BEFORE UPDATE ON research_source_resources WHEN NEW.owner_gate_id IS NOT OLD.owner_gate_id OR NEW.admission_version IS NOT OLD.admission_version OR NEW.admission_digest IS NOT OLD.admission_digest OR (NEW.admission_json IS NOT OLD.admission_json AND NOT (NEW.state='closed' AND NEW.admission_json IS NULL)) OR (OLD.task_gate_identity IS NOT NULL AND NEW.task_gate_identity IS NOT OLD.task_gate_identity) OR NEW.write_epoch<OLD.write_epoch OR NEW.write_epoch>OLD.write_epoch+1 OR (OLD.state='closed' AND NEW.state!='closed') OR (OLD.state='running' AND NEW.state='admitted') BEGIN SELECT RAISE(ABORT,'Source resource binding immutable'); END",
      "CREATE TRIGGER research_source_run_binding BEFORE UPDATE ON research_source_runs WHEN (OLD.task_gate_identity IS NOT NULL AND NEW.task_gate_identity IS NOT OLD.task_gate_identity) OR NEW.started<OLD.started OR NEW.started NOT IN (0,1) OR NEW.write_epoch<OLD.write_epoch OR NEW.write_epoch>OLD.write_epoch+1 BEGIN SELECT RAISE(ABORT,'Source run cannot restart'); END",
      "CREATE TRIGGER research_source_request_closed BEFORE UPDATE ON research_source_requests WHEN NEW.execution_closed<OLD.execution_closed OR (OLD.closure_ref IS NOT NULL AND (NEW.closure_ref IS NOT OLD.closure_ref OR NEW.closure_proof IS NOT OLD.closure_proof)) BEGIN SELECT RAISE(ABORT,'Source closure immutable'); END",
      "CREATE TRIGGER research_source_chain_counter BEFORE UPDATE ON research_source_chains WHEN NEW.used<OLD.used OR NEW.used>OLD.used+1 BEGIN SELECT RAISE(ABORT,'Source quota cannot reset'); END"))
    return tuple(result)


def install_hook(conn):
    pid=os.getpid()
    def allowed(table,operation,before,after):
        if table not in TABLES or operation not in ('INSERT','UPDATE','DELETE'):return 0
        scope=_WRITES.get(id(conn))
        if not scope or scope.conn is not conn or scope.pid!=pid or pid!=os.getpid() or not scope.active or not conn.in_transaction:return 0
        try:return int(scope.allow(table,operation,json.loads(before),json.loads(after)))
        except (ValueError,TypeError,KeyError,PermissionError,ResearchError,OSError,sqlite3.Error):return 0
    conn.create_function('research_source_write_allowed',4,allowed)
    conn.create_function('research_source_guard_version',0,lambda:11 if pid==os.getpid() else 0)


def require_hook(conn):
    try:row=conn.execute("SELECT research_source_guard_version(),research_source_write_allowed('probe','INSERT','null','null')").fetchone()
    except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'来源连接守卫不可用。') from None
    if tuple(row)!=(11,0):raise ResearchError('SCHEMA_UNSUPPORTED',503,'来源连接守卫不匹配。')


def statement_allowed(conn,action,table,column):
    if action not in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE) or table not in TABLES:return True
    scope=_WRITES.get(id(conn))
    return bool(scope and scope.conn is conn and scope.pid==os.getpid() and scope.active and scope.base.active)


def _admission_fields(task,run,approval,principal,grant,revision_digest):
    """Pure immutable-domain assembly shared by execution and history checks."""
    # Mutable execution/status fields are excluded; these immutable domain facts
    # are fixed by the authenticated admission and independently rechecked.
    fields={'task':{key:task[key] for key in ('id','research_id','principal_id','principal_epoch','owner_epoch','acl_epoch','grant_id','auth_generation','input_revision','input_digest','start_version','policy_revision','execution_mode')},
      'principal':{key:principal[key] for key in ('id','gate_id','session_generation','epoch')},
      'grant':{key:grant[key] for key in ('id','principal_id','principal_epoch','research_id','acl_epoch','scopes')},
      'run':{key:run[key] for key in ('task_id','approval_id','chain_id','plan_id','fingerprint','origin')},
      'approval':{key:approval[key] for key in ('id','principal_id','principal_epoch','auth_generation','research_id','input_revision','problem_digest','query','plan_json','plan_digest','fingerprint','execution_mode','version','consent_origin','consent_digest')},'revision_digest':revision_digest,
      'version':'source-admission-v1'}
    return fields


def snapshot(conn,task_id):
    from .source_integration import check_approval
    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(task_id,)).fetchone()
    if not task:raise PermissionError('actual Source task required')
    run,approval=check_approval(conn,task)
    if approval['consent_origin']!=CONSENT_ORIGIN or not approval['consent_digest']:raise PermissionError('Source approval has no authenticated consent producer')
    principal=conn.execute('SELECT * FROM research_principals WHERE id=?',(task['principal_id'],)).fetchone()
    grant=conn.execute('SELECT * FROM research_grants WHERE id=?',(task['grant_id'],)).fetchone()
    revision=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(task['research_id'],task['input_revision'])).fetchone()
    if not principal or not grant or not revision:raise PermissionError('Source admission domain unavailable')
    return _admission_fields(task,run,approval,principal,grant,revision[0])


def resource(conn,task_id):
    row=conn.execute('SELECT * FROM research_source_resources WHERE task_id=?',(task_id,)).fetchone()
    if not row:raise PermissionError('protected Source admission missing; historical run is not executable')
    return row


def check_active(store,conn,task_id):
    from .authorization import AuthorizationGate
    row=resource(conn,task_id)
    if row['state']=='closed' or row['admission_json'] is None:raise PermissionError('Source resource is closed')
    run=conn.execute('SELECT write_epoch FROM research_source_runs WHERE task_id=?',(task_id,)).fetchone()
    if not run or run[0]!=row['write_epoch']:raise PermissionError('Source write epoch differs')
    actual=snapshot(conn,task_id);encoded=canonical(actual)
    if encoded!=row['admission_json'] or sha256(encoded.encode())!=row['admission_digest'] or actual['principal']['gate_id']!=row['owner_gate_id']:
        raise PermissionError('Source admission domain changed')
    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(task_id,)).fetchone()
    principal=conn.execute('SELECT normalized_email FROM research_principals WHERE id=?',(task['principal_id'],)).fetchone()
    if not principal or store.auth_store.owner_gate_in(conn,principal[0])!=row['owner_gate_id']:raise PermissionError('Source account owner mapping changed')
    AuthorizationGate(store).check_task(conn,task)
    return row


class _Scope:
    def __init__(self,conn,store,mode,*,lease,source=None,identity=None,rid=None,request=None,key=None,task_id=None,owner_lease=None,job_id=None,birth=None):
        from .paid_control import _current_scope
        if mode not in ('approve','admit','worker','close','birth','stop','erase'):raise PermissionError('unsupported Source write operation')
        self.conn,self.store,self.mode,self.pid,self.active=conn,store,mode,os.getpid(),True
        self.base=_current_scope(conn);self.lease=lease;self.source=source;self.identity=identity;self.rid=rid;self.request=request;self.key=key
        self.task_id=task_id;self.owner_lease=owner_lease;self.job_id=job_id;self.birth=birth
        self.images={}
        self.validate()
    def validate(self):
        from .paid_control import _current_scope,require_authenticated_action,verify_deletion_origin
        if _current_scope(self.conn) is not self.base or not self.base.active or self.pid!=os.getpid():raise PermissionError('actual Source transaction retired')
        from .store import ResearchStore
        if type(self.store) is not ResearchStore:raise PermissionError('canonical Source store required')
        if self.store._formal_mode():
            if __package__=='web.backend.research':from ..services.auth_registration import _native
            else:from services.auth_registration import _native
            _native(self.conn,self.store.auth_store)
        if self.mode in ('approve','admit'):
            from .service import digest
            self.lease.identity
            require_authenticated_action(self.source,identity=self.identity,action='source-approve' if self.mode=='approve' else 'source-start',research_id=self.rid,key=self.key,body_digest=digest(self.request.model_dump(mode='json')))
            from .authorization import AuthorizationGate
            control=AuthorizationGate(self.store).check(self.conn,self.identity,self._principal(),self.rid,scope='write')
            gate=self.conn.execute('SELECT gate_id FROM research_principals WHERE id=?',(control['owner_id'],)).fetchone()[0]
            if self.store.auth_store.owner_gate_in(self.conn,self.identity.email)!=gate:raise PermissionError('Source account gate differs')
            self._owner(gate,self.lease)
        elif self.mode=='stop':
            from .service import digest
            from .authorization import AuthorizationGate
            require_authenticated_action(self.source,identity=self.identity,action='cancel',research_id=self.rid,task_id=self.task_id,key=self.key,body_digest=digest(self.request.model_dump(mode='json')))
            AuthorizationGate(self.store).check(self.conn,self.identity,self._principal(),self.rid,scope='write')
            row=resource(self.conn,self.task_id)
            if self.store.auth_store.owner_gate_in(self.conn,self.identity.email)!=row['owner_gate_id']:raise PermissionError('Source stop owner changed')
            self._owner(row['owner_gate_id'],self.lease)
        elif self.mode=='erase':
            protected=verify_deletion_origin(self.conn,store=self.store,lease=self.lease,job_id=self.job_id)
            job=self.conn.execute('SELECT * FROM auth_deletion_jobs WHERE id=?',(self.job_id,)).fetchone()
            if not job or job['state']!='pending':raise PermissionError('pending Source deletion required')
            if protected is None:
                found=self.conn.execute('SELECT 1 FROM research_source_approvals a JOIN research_principals p ON p.id=a.principal_id WHERE p.gate_id=? AND p.normalized_email=? AND p.session_generation=? LIMIT 1',(job['gate_id'],job['owner_email'],job['session_generation'])).fetchone()
                if found:raise PermissionError('Source deletion requires protected origin')
            else:self._owner(job['gate_id'],self.lease)
        elif self.mode=='birth':
            from .authorization import _TaskBirth
            if type(self.birth) is not _TaskBirth:raise PermissionError('actual native Source birth required')
            row=check_active(self.store,self.conn,self.task_id)
            self._owner(row['owner_gate_id'],self.owner_lease)
            self.birth.require(self.store,self.task_id)
        else:
            from .authorization import TaskGateLease
            if type(self.lease) is not TaskGateLease:raise PermissionError('actual native task lease required')
            self.lease.require(self.store,self.conn,cleanup=self.mode=='close')
            if self.mode!='close':check_active(self.store,self.conn,self.task_id)
            if self.mode=='close' and self.owner_lease is None:raise PermissionError('fresh actual owner lease required for Source closure')
            if self.owner_lease is not None:self._owner(resource(self.conn,self.task_id)['owner_gate_id'],self.owner_lease)
    def _principal(self):
        row=self.conn.execute("SELECT id FROM research_principals WHERE normalized_email=? AND session_generation=? AND status='active'",(self.identity.email,self.identity.generation)).fetchone()
        if not row:raise PermissionError('actual Source principal unavailable')
        return row[0]
    def _owner(self,gate,lease):
        from .authorization import OwnerGateLease
        if type(lease) is not OwnerGateLease:raise PermissionError('actual owner lease required')
        info=(self.store.path.parent/'research-locks'/(gate+'.lock')).lstat()
        if (info.st_dev,info.st_ino)!=(lease.identity[0],lease.identity[1]):raise PermissionError('Source owner lease changed')
        if self.store._formal_mode() and self.store.auth_store.expected_owner_gate_identity(gate)!=lease.identity[:2]:raise PermissionError('Source owner receipt changed')
    def allow(self,table,operation,before,after):
        self.validate()
        if table not in TABLES or (operation=='DELETE' and not (self.mode=='erase' and table=='research_source_approvals')):return False
        row=after or before
        key='task_id' if table in ('research_source_runs','research_source_resources') else 'id'
        row_id=row[key]
        image_key=(table,row_id)
        if image_key not in self.images:
            actual=self.conn.execute('SELECT rowid,* FROM '+table+' WHERE '+key+'=?',(row_id,)).fetchone()
            self.images[image_key]=dict(actual) if actual else None
        expected=self.images[image_key]
        if expected is not None and expected.get('rowid')==-1 and before is not None:
            expected=dict(expected,rowid=before['rowid'])
        if before!=expected:return False
        if self.mode=='approve':
            if table!='research_source_approvals' or operation!='INSERT':return False
            from .source_integration import draft,origin
            revision=self.conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(self.rid,self.request.input_revision)).fetchone()
            fields,pd,fp,inp=draft(revision[0],self.request.query)
            if (row['principal_id']!=self._principal() or row['research_id']!=self.rid or row['auth_generation']!=self.identity.generation
                or row['principal_epoch']!=self.conn.execute('SELECT epoch FROM research_principals WHERE id=?',(self._principal(),)).fetchone()[0]
                or row['input_revision']!=self.request.input_revision or row['problem_digest']!=revision[0] or row['query']!=self.request.query
                or row['plan_json']!=canonical(fields) or row['plan_digest']!=pd or row['fingerprint']!=fp or row['execution_mode']!=origin()
                or row['status']!='active' or row['consumed_task_id'] is not None or row['version']!=1
                or row['consent_origin']!=CONSENT_ORIGIN or row['consent_digest']!=self.source.body_digest):return False
        elif self.mode=='admit':
            if table=='research_source_approvals':
                if row_id!=self.request.approval_ref or before is None or row['status']!='consumed' or before['status']!='active':return False
                if any(row[k]!=before[k] for k in row if k not in ('status','consumed_task_id')):return False
            elif table=='research_source_chains':
                if operation!='INSERT' or row['principal_id']!=self._principal() or row['research_id']!=self.rid or row['used']!=0:return False
                approval=self.conn.execute('SELECT fingerprint FROM research_source_approvals WHERE id=?',(self.request.approval_ref,)).fetchone()
                if not approval or row['fingerprint']!=approval[0]:return False
            elif table in ('research_source_runs','research_source_resources'):
                if operation!='INSERT':return False
                task=self.conn.execute('SELECT * FROM research_tasks WHERE id=?',(row_id,)).fetchone()
                if not task or task['principal_id']!=self._principal() or task['research_id']!=self.rid or task['auth_generation']!=self.identity.generation:return False
                if table=='research_source_runs':
                    if row['approval_id']!=self.request.approval_ref or row['started']!=0 or row['task_gate_identity'] is not None:return False
                else:
                    encoded=canonical(snapshot(self.conn,row_id))
                    if row['admission_json']!=encoded or row['admission_digest']!=sha256(encoded.encode()) or row['owner_gate_id']!=snapshot(self.conn,row_id)['principal']['gate_id'] or row['state']!='admitted' or row['write_epoch']!=1 or row['task_gate_identity'] is not None:return False
            else:return False
        elif self.mode=='stop':
            if table!='research_source_resources' or operation!='UPDATE' or row_id!=self.task_id or before is None:return False
            if row['state']!='closed' or row['admission_json']!=before['admission_json'] or row['write_epoch']!=before['write_epoch']+1:return False
            if any(row[k]!=before[k] for k in row if k not in {'state','admission_json','write_epoch'}):return False
        elif self.mode=='erase':
            job=self.conn.execute('SELECT * FROM auth_deletion_jobs WHERE id=?',(self.job_id,)).fetchone()
            if table=='research_source_resources':
                if before is None or row['owner_gate_id']!=job['gate_id'] or row['state']!='closed' or row['admission_json'] is not None:return False
                if row['write_epoch']!=before['write_epoch']+1 or any(row[k]!=before[k] for k in row if k not in {'state','admission_json','write_epoch'}):return False
            elif table=='research_source_approvals':
                if before is None or operation!='DELETE':return False
                if before['principal_id']!=self.conn.execute('SELECT id FROM research_principals WHERE normalized_email=? AND session_generation=?',(job['owner_email'],job['session_generation'])).fetchone()[0]:return False
            elif table=='research_source_runs':
                if before is None or row['approval_id'] is not None or row['fingerprint'] is not None:return False
                if any(row[k]!=before[k] for k in row if k not in {'approval_id','fingerprint'}):return False
                task=self.conn.execute('SELECT principal_id FROM research_tasks WHERE id=?',(row_id,)).fetchone()
                principal=self.conn.execute('SELECT normalized_email,session_generation FROM research_principals WHERE id=?',(task[0],)).fetchone()
                if tuple(principal)!=(job['owner_email'],job['session_generation']):return False
            elif table=='research_source_chains':
                if before is None or row['fingerprint'] is not None or row['research_id'] is not None:return False
                if any(row[k]!=before[k] for k in row if k not in {'fingerprint','research_id'}):return False
                principal=self.conn.execute('SELECT normalized_email,session_generation FROM research_principals WHERE id=?',(row['principal_id'],)).fetchone()
                if tuple(principal)!=(job['owner_email'],job['session_generation']):return False
            else:return False
        elif self.mode=='birth':
            if table not in ('research_source_resources','research_source_runs') or row_id!=self.task_id or operation!='UPDATE':return False
            if row['task_gate_identity']!=canonical(self.birth.identity) or before['task_gate_identity'] is not None:return False
            if any(row[k]!=before[k] for k in row if k!='task_gate_identity'):return False
        else:
            binding=json.loads(resource(self.conn,self.task_id)['admission_json']) if resource(self.conn,self.task_id)['admission_json'] else None
            if table in ('research_source_runs','research_source_resources'):
                if row_id!=self.task_id or operation!='UPDATE':return False
                if self.mode=='worker':
                    allowed={'started'} if table=='research_source_runs' else {'state'}
                    if any(row[k]!=before[k] for k in row if k not in allowed):return False
                    if table=='research_source_runs' and (before['started']!=0 or row['started']!=1):return False
                    if table=='research_source_resources' and (before['state']!='admitted' or row['state']!='running'):return False
                else:
                    allowed={'write_epoch'} if table=='research_source_runs' else {'write_epoch','state','admission_json'}
                    if any(row[k]!=before[k] for k in row if k not in allowed):return False
                    if row['write_epoch']!=before['write_epoch']+1:return False
            elif table=='research_source_requests':
                if self.owner_lease is None or row['task_id']!=self.task_id:return False
                if operation=='INSERT':
                    if self.owner_lease is None or self.mode=='close' or row['outcome']!='SENDING' or row['write_epoch']!=resource(self.conn,self.task_id)['write_epoch'] or row['task_gate_identity']!=canonical(self.lease.identity) or row['owner_gate_identity']!=canonical(self.owner_lease.identity):return False
                elif any(row[k]!=before[k] for k in row if k not in ('outcome','execution_closed','closure_ref','closure_proof','ended_at','http_status','safe_code')):return False
                if self.mode=='close' and (row['outcome']!='UNKNOWN' or row['execution_closed']!=1):return False
            elif table=='research_source_chains':
                if self.mode=='close' or self.owner_lease is None or not binding or row_id!=binding['run']['chain_id'] or operation!='UPDATE' or row['used']!=before['used']+1:return False
                if any(row[k]!=before[k] for k in row if k!='used'):return False
            else:return False
            if self.mode=='close' and table=='research_source_resources' and (row['state']!='closed' or row['admission_json']!=before['admission_json']):return False
        self.images[image_key]=after
        return True


@contextmanager
def _scope(conn,store,mode,**kwargs):
    if id(conn) in _WRITES:raise PermissionError('Source writer already active')
    scope=_Scope(conn,store,mode,**kwargs);_WRITES[id(conn)]=scope;scope.base.refresh_authorizer()
    try:yield scope
    finally:scope.active=False;_WRITES.pop(id(conn),None);scope.base.refresh_authorizer()


def approval_scope(conn,service,lease,identity,rid,request,key,source):
    return _scope(conn,service.store,'approve',lease=lease,identity=identity,rid=rid,request=request,key=key,source=source)


def admission_scope(conn,service,lease,identity,rid,request,key,source):
    return _scope(conn,service.store,'admit',lease=lease,identity=identity,rid=rid,request=request,key=key,source=source)


def worker_scope(conn,store,task_lease,*,owner_lease=None,close=False):
    return _scope(conn,store,'close' if close else 'worker',lease=task_lease,task_id=task_lease.task_id,owner_lease=owner_lease)


def birth_scope(conn,store,task_id,birth,owner_lease):
    return _scope(conn,store,'birth',lease=None,task_id=task_id,birth=birth,owner_lease=owner_lease)


def erase_scope(conn,store,lease,job_id):
    return _scope(conn,store,'erase',lease=lease,job_id=job_id)


def admit_resource(conn,task_id):
    value=snapshot(conn,task_id);encoded=canonical(value)
    conn.execute("INSERT INTO research_source_resources(task_id,owner_gate_id,admission_version,admission_json,admission_digest,state) VALUES(?,?,'source-admission-v1',?,?,'admitted')",(task_id,value['principal']['gate_id'],encoded,sha256(encoded.encode())))


def provision_source_v11(path):
    """Explicit offline complete10 -> complete11; no hot/runtime migration."""
    from .formula_runtime import _offline_maintenance,_check_profile
    from .store import ResearchStore
    if __package__=='web.backend.research':from ..services.auth_store import AuthStore
    else:from services.auth_store import AuthStore
    with _offline_maintenance(path,(10,11)) as (target,capability):
        conn=capability.conn;capability.require(target);conn.execute('BEGIN EXCLUSIVE')
        try:
            version=_check_profile(conn,target,(10,11))
            if AuthStore.check_offline_auth_metadata(conn)!='auth-provision-v1':raise PermissionError('Source11 requires current Auth')
            if version==10:
                for name,ddl in CONSENT_COLUMNS:conn.execute('ALTER TABLE research_source_approvals ADD COLUMN '+name+' '+ddl)
                for ddl in declarations():
                    if ddl.startswith('CREATE TABLE research_source_approvals '):continue
                    conn.execute(ddl)
                conn.execute('UPDATE research_schema SET version=11 WHERE id=1 AND version=10')
            ResearchStore._check_v11(conn)
            if conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('Source11 FK failure')
            capability.require(target);conn.commit()
        except BaseException:conn.rollback();raise
        identity=capability.identity
    return {'schema_version':11,'journal_mode':'wal','database_identity':list(identity),'backup_scope':'in_memory_algorithm_recovery_only'}


def deletion_scope(conn,service,lease,job_id):
    from contextlib import nullcontext
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] not in (11,12,13,14,15):return nullcontext()
    return erase_scope(conn,service.store,lease,job_id)


def erase_approvals(conn,pid):
    conn.execute('DELETE FROM research_source_approvals WHERE principal_id=?',(pid,))


def erase_resource(conn,task_id):
    conn.execute("UPDATE research_source_resources SET state='closed',admission_json=NULL,write_epoch=write_epoch+1 WHERE task_id=? AND (state!='closed' OR admission_json IS NOT NULL)",(task_id,))


def stop_in(conn,service,lease,identity,rid,request,key,source):
    row=conn.execute('SELECT * FROM research_source_resources WHERE task_id=?',(request.task_id,)).fetchone()
    if not row or row['state']=='closed':return
    with _scope(conn,service.store,'stop',lease=lease,identity=identity,rid=rid,request=request,key=key,source=source,task_id=request.task_id):
        conn.execute("UPDATE research_source_resources SET state='closed',write_epoch=write_epoch+1 WHERE task_id=? AND state!='closed'",(request.task_id,))


def check_origin(store,conn,task_id):
    """Historical acquisition integrity; never grants present execution rights.

    The caller separately verifies the current reader and publisher licence.
    Stop, old JTI expiry, or withdrawal of the old execute scope is not a read
    withdrawal. Account deletion removes this private original admission.
    """
    row=resource(conn,task_id)
    recorded,mode=_recorded_admission(row)
    from .source_integration import _canonical_draft,normalized_query
    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(task_id,)).fetchone()
    run=conn.execute('SELECT * FROM research_source_runs WHERE task_id=?',(task_id,)).fetchone()
    approval=conn.execute('SELECT * FROM research_source_approvals WHERE id=?',(run['approval_id'],)).fetchone() if run else None
    if (not task or not run or not approval or task['execution_mode']!=mode
            or run['origin']!=mode or approval['execution_mode']!=mode
            or approval['consent_origin']!=CONSENT_ORIGIN or not approval['consent_digest']):
        raise PermissionError('Source recorded acquisition mode differs')
    fields,pd,fp,inp=_canonical_draft(approval['problem_digest'],approval['query'],mode)
    legacy=sha256(canonical({'problem_digest':approval['problem_digest'],'query':normalized_query(approval['query']),
        'operation_family':'crossref-plos-method-get'}).encode())
    if (canonical(fields)!=approval['plan_json'] or pd!=approval['plan_digest'] or inp!=task['input_digest']
            or run['fingerprint'] not in (fp,legacy) or run['fingerprint']!=approval['fingerprint']):
        raise PermissionError('Source recorded plan binding differs')
    principal=conn.execute('SELECT * FROM research_principals WHERE id=?',(task['principal_id'],)).fetchone()
    grant=conn.execute('SELECT * FROM research_grants WHERE id=?',(task['grant_id'],)).fetchone()
    revision=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',
                          (task['research_id'],task['input_revision'])).fetchone()
    if not principal or not grant or not revision or revision[0]!=approval['problem_digest']:
        raise PermissionError('Source original domain unavailable')
    actual=_admission_fields(task,run,approval,principal,grant,revision[0])
    _check_recorded_fields(actual,recorded,row['owner_gate_id'])
    return row


def _check_recorded_fields(actual,recorded,owner_gate_id):
    """Pure original-domain comparison, never a current reader/worker grant."""
    try:
        # Only the old execution epoch/scope may have legitimately retired.
        compared={**actual,'principal':{**actual['principal'],'epoch':actual['task']['principal_epoch']},
                  'grant':{**actual['grant'],'scopes':recorded['grant']['scopes']}}
        if canonical(compared)!=canonical(recorded) or compared['principal']['gate_id']!=owner_gate_id:
            raise PermissionError('Source original domain differs')
    except (KeyError,TypeError,ValueError):
        raise PermissionError('Source original domain unavailable') from None


def _recorded_admission(row):
    """Decode protected acquisition data only; this returns no capability."""
    if row['admission_json'] is None:raise PermissionError('Source original admission was erased')
    try:
        recorded=json.loads(row['admission_json'])
        encoded=canonical(recorded)
        if (row['admission_version']!='source-admission-v1' or type(recorded) is not dict
                or recorded.get('version')!='source-admission-v1' or encoded!=row['admission_json']
                or sha256(encoded.encode())!=row['admission_digest']):
            raise PermissionError('Source original admission digest differs')
        mode=recorded['task']['execution_mode']
        modes=(mode,recorded['run']['origin'],recorded['approval']['execution_mode'],
               json.loads(recorded['approval']['plan_json'])['execution_mode'])
        if any(type(value) is not str or value not in ('offline_probe','live') or value!=mode for value in modes):
            raise PermissionError('Source recorded acquisition mode differs')
    except (KeyError,TypeError,ValueError):
        raise PermissionError('Source original admission unavailable') from None
    return recorded,mode
