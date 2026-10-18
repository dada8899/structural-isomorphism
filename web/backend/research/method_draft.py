"""Immutable, current-authorized manual method drafts in the Research DB."""
from contextlib import contextmanager
import json
import os
import sqlite3
import sys
from uuid import uuid4

from .authorization import OwnerGateLease
from .errors import ResearchError,not_found
from .provider_schemas import canonical,digest
from .method_draft_schemas import CONTRACT,MethodDraftRequest,MethodDraftResponse,MethodDraftHistoryResponse

TABLE='research_method_drafts'
_WRITES={}
_COLUMNS=('draft_ref','research_id','principal_id','input_revision','problem_digest','research_version_before','research_version_after','created_at','content_digest','body_json')
_JSON=lambda prefix:'json_array('+','.join(prefix+'.'+name for name in _COLUMNS)+')'
DDL=(
    """CREATE TABLE research_method_drafts (
        draft_ref TEXT NOT NULL PRIMARY KEY,
        research_id TEXT NOT NULL REFERENCES research_controls(id),
        principal_id TEXT NOT NULL REFERENCES research_principals(id),
        input_revision INTEGER NOT NULL CHECK(input_revision BETWEEN 1 AND 2147483647),
        problem_digest TEXT NOT NULL CHECK(length(problem_digest)=64 AND problem_digest NOT GLOB '*[^a-f0-9]*'),
        research_version_before INTEGER NOT NULL CHECK(research_version_before BETWEEN 1 AND 2147483646),
        research_version_after INTEGER NOT NULL CHECK(research_version_after=research_version_before+1),
        created_at TEXT NOT NULL,
        content_digest TEXT NOT NULL CHECK(length(content_digest)=64 AND content_digest NOT GLOB '*[^a-f0-9]*'),
        body_json TEXT NOT NULL CHECK(json_valid(body_json) AND length(CAST(body_json AS BLOB))<=131072),
        FOREIGN KEY(research_id,input_revision) REFERENCES research_revisions(research_id,revision))""",
    'CREATE INDEX research_method_draft_history ON research_method_drafts(research_id,created_at,draft_ref)',
    "CREATE TRIGGER research_method_draft_insert BEFORE INSERT ON research_method_drafts BEGIN SELECT CASE WHEN research_method_draft_allowed('INSERT',"+_JSON('NEW')+")!=1 THEN RAISE(ABORT,'actual method draft producer required') END; END",
    "CREATE TRIGGER research_method_draft_delete BEFORE DELETE ON research_method_drafts BEGIN SELECT CASE WHEN research_method_draft_allowed('DELETE',"+_JSON('OLD')+")!=1 THEN RAISE(ABORT,'actual method draft deletion required') END; END",
    "CREATE TRIGGER research_method_draft_immutable BEFORE UPDATE ON research_method_drafts BEGIN SELECT RAISE(ABORT,'immutable method draft'); END",
    "CREATE TRIGGER research_method_draft_no_replace BEFORE INSERT ON research_method_drafts WHEN EXISTS(SELECT 1 FROM research_method_drafts AS OLD WHERE OLD.rowid=NEW.rowid OR OLD.draft_ref=NEW.draft_ref) BEGIN SELECT RAISE(ABORT,'method draft replacement forbidden'); END",
)


def install_hook(conn):
    pid=os.getpid()
    def allowed(operation,encoded):
        entry=_WRITES.get(id(conn))
        if (not entry or entry['conn'] is not conn or pid!=os.getpid() or not conn.in_transaction
                or not entry['scope'].active or entry['op']!=operation):return 0
        try:
            _validate_write(conn,entry)
            return int(json.loads(encoded)==entry['values'])
        except (PermissionError,ResearchError,ValueError,TypeError,OSError,sqlite3.Error):return 0
    conn.create_function('research_method_draft_allowed',2,allowed)
    conn.create_function('research_method_draft_guard_version',0,lambda:14 if pid==os.getpid() else 0)


def require_hook(conn):
    try:value=conn.execute("SELECT research_method_draft_guard_version(),research_method_draft_allowed('','[]')").fetchone()
    except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'方法草稿连接守卫不可用。') from None
    if tuple(value)!=(14,0):raise ResearchError('SCHEMA_UNSUPPORTED',503,'方法草稿连接守卫不匹配。')


def statement_allowed(conn,action,table,column):
    if action not in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE) or table!=TABLE:return True
    value=_WRITES.get(id(conn))
    return bool(value and value['conn'] is conn and value['scope'].active and value['pid']==os.getpid() and conn.in_transaction)


def _validate_write(conn,entry):
    from .paid_control import _owner_binding,require_authenticated_action,verify_deletion_origin
    service,identity,pid,rid,lease=map(entry.__getitem__,('service','identity','pid_owner','rid','lease'))
    from .authorization import AuthorizationGate
    _owner_binding(conn,service.store,pid,lease)
    if entry['op']=='DELETE':
        job=verify_deletion_origin(conn,store=service.store,lease=lease,job_id=entry['job_id'])
        # The actual protected deletion job, not a client-supplied principal.
        principal=conn.execute('SELECT normalized_email,session_generation,status FROM research_principals WHERE id=?',(pid,)).fetchone()
        if not principal or principal['status']!='deleting' or principal['normalized_email']!=job['owner_email'] or principal['session_generation']!=job['session_generation']:
            raise PermissionError('deletion principal differs')
    else:
        require_authenticated_action(entry['source'],identity=identity,action='draft-save',research_id=rid,key=entry['key'],body_digest=entry['request_digest'])
        control=AuthorizationGate(service.store).check(conn,identity,pid,rid,scope='write')
        if control['current_revision']!=entry['values'][3] or control['version']!=entry['values'][5]:raise PermissionError('current draft revision changed')


@contextmanager
def _write(conn,service,lease,operation,values,*,identity=None,source=None,key=None,request_digest=None,job_id=None):
    from .paid_control import _current_scope
    from .store import ResearchStore
    from .service import ResearchService
    frame=sys._getframe(1)
    try:
        codes={producer.__code__ for producer in _WRITE_PRODUCERS}
        while frame and frame.f_code not in codes:frame=frame.f_back
        if (not frame or frame.f_globals is not globals() or frame.f_locals.get('conn') is not conn
                or frame.f_locals.get('lease') is not lease or frame.f_locals.get('service') is not service
                or type(service) is not ResearchService or type(service.store) is not ResearchStore
                or not isinstance(conn,sqlite3.Connection) or type(lease) is not OwnerGateLease):
            raise PermissionError('fixed active method draft producer required')
    finally:del frame
    if service.store.storage_identity is not None and getattr(conn,'private_storage_identity',None)!=service.store.storage_identity:
        raise PermissionError('actual native draft database identity required')
    scope=_current_scope(conn)
    if id(conn) in _WRITES:raise PermissionError('nested draft writer forbidden')
    entry={'conn':conn,'scope':scope,'pid':os.getpid(),'service':service,'identity':identity,'pid_owner':values[2],
        'rid':values[1],'lease':lease,'op':operation,'values':values,'source':source,'key':key,'request_digest':request_digest,'job_id':job_id}
    _validate_write(conn,entry)
    _WRITES[id(conn)]=entry;scope.refresh_authorizer()
    try:yield
    finally:_WRITES.pop(id(conn),None);scope.refresh_authorizer()


def _sources(conn,service,identity,rid,refs):
    from .evidence_repository import EvidenceRepository
    from .source_integration import context_for,authorizer
    repository=EvidenceRepository(conn,authorizer(service.store,identity=identity));result=[]
    try:
        for ref in refs:
            row=conn.execute("SELECT task_id FROM research_evidence_objects WHERE id=? AND kind='excerpts' AND research_id=?",(ref['excerpt_id'],rid)).fetchone()
            if not row:raise PermissionError('original Source unavailable')
            value=repository.excerpt_details(context_for(conn,row[0]),ref['excerpt_id'])
            if any(value[key]!=ref[key] for key in ('source_revision','content_digest','start','end')):raise PermissionError('original Source reference changed')
            result.append(value)
    except (LookupError,ValueError,PermissionError):raise ResearchError('DEPENDENCY_UNAVAILABLE',409,'所选来源已不可读取或与原摘录不符，请重新选择。') from None
    return result


def _origin(conn,service,identity,rid,origin):
    if origin['kind']=='user_proposed':return {**origin,'mode':'user_proposed','verification':'unverified'}
    if origin['kind']=='kb_record':raise ResearchError('CATALOG_UNAVAILABLE',503,'当前没有可核对的固定知识库记录，请使用人工提议或已保存的计划线索。')
    if origin['plan_contract']=='funded-plan-v2':
        from .plan_native_runtime import read_in
    else:
        from .plan_result import read_in
    data=read_in(conn,service,identity,rid,origin['result_ref'])['data'];content=data['content']
    if content is None:raise ResearchError('DEPENDENCY_UNAVAILABLE',409,'计划原文当前不可读取。')
    try:
        plan=content['proposal'];candidate=plan['candidates'][origin['candidate_index']];lead=candidate['method_leads'][origin['lead_index']]
    except (KeyError,IndexError,TypeError):raise ResearchError('INPUT_INVALID',422,'所选方法线索不存在。') from None
    return {**origin,'label':candidate['label'],'lead':lead,'mode':content['execution_mode'],
        'producer':content.get('producer','owned-plan-fixture-v1'),'result_digest':digest(canonical(content)),'input_revision':content['input_revision'],
        'verification':'unverified'}


def _formula(conn,service,identity,rid,ref):
    if ref is None:return None
    from .formula_result import read_result_in
    data=read_result_in(conn,service,identity,rid,ref)['data']
    if data['state']!='available':raise ResearchError('DEPENDENCY_UNAVAILABLE',409,'所选公式结果当前不可读取。')
    return {'result_ref':ref,'metadata':data['metadata'],'result_digest':digest(canonical(data['result'])),
        'input_revision':conn.execute('SELECT t.input_revision FROM research_formula_runs r JOIN research_tasks t ON t.id=r.task_id WHERE r.result_ref=?',(ref,)).fetchone()[0],'comparison_scope':data['result']['comparison_scope'],
        'outcomes':[{key:item[key] for key in ('check_kind','status','relation')} for item in data['result']['outcomes']],
        'execution_attested':data['provenance']['execution_attested']}


def _metadata(row,control,body):
    return {key:row[key] for key in ('draft_ref','input_revision','problem_digest','research_version_before','research_version_after','created_at','content_digest')}|{
        'is_historical':row['input_revision']!=control['current_revision'],'origin_kind':body['origin']['kind'],
        'validation_status':'unverified','execution_status':'not_executed'}


def _read_in(conn,service,identity,rid,ref):
    pid=service._principal_in(conn,identity);control=service.authorization.check(conn,identity,pid,rid)
    row=conn.execute('SELECT * FROM '+TABLE+' WHERE draft_ref=? AND research_id=? AND principal_id=?',(ref,rid,pid)).fetchone()
    if not row:raise not_found()
    body=json.loads(row['body_json']);request=MethodDraftRequest.model_validate(body['request']).model_dump(mode='json')
    from datetime import datetime
    try:
        if datetime.strptime(row['created_at'],'%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%dT%H:%M:%S.%fZ')!=row['created_at']:raise ValueError()
    except (ValueError,TypeError):raise not_found() from None
    revision=conn.execute('SELECT digest,problem_json FROM research_revisions WHERE research_id=? AND revision=?',(rid,row['input_revision'])).fetchone()
    if (digest(canonical(body))!=row['content_digest'] or not revision or revision[0]!=row['problem_digest']
            or digest(canonical(json.loads(revision['problem_json'])))!=row['problem_digest']
            or control['current_revision']<row['input_revision'] or control['version']<row['research_version_after']
            or row['research_version_after']!=row['research_version_before']+1
            or request['input_revision']!=row['input_revision'] or request['expected_research_version']!=row['research_version_before']
            or body['schema_version']!='structure-research-v1' or body['contract_revision']!=CONTRACT):raise not_found()
    if (_sources(conn,service,identity,rid,request['excerpt_refs'])!=body['sources']
            or _origin(conn,service,identity,rid,request['origin'])!=body['origin']
            or _formula(conn,service,identity,rid,request['formula_result_ref'])!=body['formula']):
        raise ResearchError('DEPENDENCY_UNAVAILABLE',409,'草稿依赖当前无法完整核对，原记录不会重写。')
    return {'schema_version':'structure-research-v1','contract_revision':CONTRACT,
        'data':{'metadata':_metadata(row,control,body),'content':body}}


def save(service,identity,rid,request,key,source):
    from .paid_control import require_authenticated_action
    from .service import now
    rid=service._id(rid);pid=service._principal(identity);payload=request.model_dump(mode='json');request_digest=digest(canonical(payload))
    require_authenticated_action(source,identity=identity,action='draft-save',research_id=rid,key=key,body_digest=request_digest)
    with service.authorization.owner_gate(pid) as lease,service.store.transaction(write=True) as conn:
        control=service.authorization.check(conn,identity,pid,rid,scope='write')
        replay=service._replay(conn,pid,'method-draft','r:'+rid,key,request_digest)
        if replay is not None:return MethodDraftResponse.model_validate(_read_in(conn,service,identity,rid,replay['draft_ref'])).model_dump(mode='json')
        if control['current_revision']!=request.input_revision or control['version']!=request.expected_research_version or control['version']>=2147483647:
            raise ResearchError('VERSION_CONFLICT',409,'问题已更新，请重读后保存新草稿。')
        if request.supersedes_ref:_read_in(conn,service,identity,rid,request.supersedes_ref)
        revision=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(rid,request.input_revision)).fetchone()
        body={'schema_version':'structure-research-v1','contract_revision':CONTRACT,'request':payload,
            'sources':_sources(conn,service,identity,rid,payload['excerpt_refs']),
            'origin':_origin(conn,service,identity,rid,payload['origin']),
            'formula':_formula(conn,service,identity,rid,request.formula_result_ref)}
        encoded=canonical(body)
        if len(encoded)>131072:raise ResearchError('PAYLOAD_LIMIT',413,'完整方法草稿超过保存上限，请减少引用或文字。')
        ref=str(uuid4());values=[ref,rid,pid,request.input_revision,revision[0],control['version'],control['version']+1,now(),digest(encoded),encoded.decode()]
        with _write(conn,service,lease,'INSERT',values,identity=identity,source=source,key=key,request_digest=request_digest):
            conn.execute('INSERT INTO '+TABLE+' VALUES('+','.join('?' for _ in values)+')',values)
        if conn.execute('UPDATE research_controls SET version=version+1,updated_at=? WHERE id=? AND version=?',(values[7],rid,control['version'])).rowcount!=1:raise PermissionError('method draft research CAS failed')
        service._remember(conn,pid,'method-draft','r:'+rid,key,request_digest,{'draft_ref':ref})
        return MethodDraftResponse.model_validate(_read_in(conn,service,identity,rid,ref)).model_dump(mode='json')


def read(service,identity,rid,ref,source):
    from .paid_control import require_authenticated_action
    rid=service._id(rid);ref=service._id(ref)
    require_authenticated_action(source,identity=identity,action='draft-read',research_id=rid,task_id=ref)
    with service.store.transaction() as conn:return MethodDraftResponse.model_validate(_read_in(conn,service,identity,rid,ref)).model_dump(mode='json')


def history(service,identity,rid,limit,cursor,source):
    from .paid_control import require_authenticated_action
    rid=service._id(rid)
    require_authenticated_action(source,identity=identity,action='draft-history',research_id=rid)
    with service.store.transaction() as conn:
        pid=service._principal_in(conn,identity);service.authorization.check(conn,identity,pid,rid)
        if cursor is not None:
            service._id(cursor)
            if not conn.execute('SELECT 1 FROM '+TABLE+' WHERE research_id=? AND draft_ref=?',(rid,cursor)).fetchone():raise not_found()
        refs=[r[0] for r in conn.execute('SELECT draft_ref FROM '+TABLE+' WHERE research_id=? AND (? IS NULL OR draft_ref>?) ORDER BY draft_ref LIMIT ?',(rid,cursor,cursor,limit+1))]
        items=[_read_in(conn,service,identity,rid,ref)['data']['metadata'] for ref in refs[:limit]]
        return MethodDraftHistoryResponse.model_validate({'schema_version':'structure-research-v1','contract_revision':CONTRACT,'data':{'items':items,'next_cursor':refs[limit-1] if len(refs)>limit else None}}).model_dump(mode='json')


def erase_in(conn,service,lease,pid,job_id):
    for row in conn.execute('SELECT * FROM '+TABLE+' WHERE principal_id=?',(pid,)).fetchall():
        values=[row[key] for key in _COLUMNS]
        with _write(conn,service,lease,'DELETE',values,job_id=job_id):conn.execute('DELETE FROM '+TABLE+' WHERE draft_ref=?',(row['draft_ref'],))


def provision_method_drafts_v14(path):
    from .formula_runtime import _offline_maintenance,_check_profile
    from .store import ResearchStore
    with _offline_maintenance(path,(13,14)) as (target,cap):
        conn=cap.conn;cap.require(target);conn.execute('BEGIN EXCLUSIVE')
        try:
            version=_check_profile(conn,target,(13,14))
            if version==13:
                for sql in DDL:conn.execute(sql)
                if conn.execute('UPDATE research_schema SET version=14 WHERE id=1 AND version=13').rowcount!=1:raise PermissionError('method draft marker CAS failed')
            ResearchStore._check_v14(conn)
            if conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('method draft FK failure')
            cap.require(target);conn.commit()
        except BaseException:conn.rollback();raise
        identity=cap.identity
    return {'schema_version':14,'financial_protocol':9,'journal_mode':'wal','database_identity':list(identity),'backup_scope':'in_memory_algorithm_recovery_only'}


_WRITE_PRODUCERS=(save,erase_in)
