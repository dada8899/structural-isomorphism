"""Actual revision-owned formula snapshots, local task lifecycle and readers."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .authorization import AuthorizationGate,AccountIdentity
from .errors import ResearchError,not_found
from .formula_schemas import FormulaCheckInput,FormulaInput,FormulaInputError,FormulaLimit,canonical,digest
from .formula_runtime import _write,_FACTORY,TASK_POLICY
from .schemas import FormulaRevisionDraft,FormulaCheckRequest,SCHEMA_VERSION,CONTRACT_REVISION

_EXECUTIONS={}
_EXEC_FACTORY=object()


def _envelope(data):
    result={'schema_version':SCHEMA_VERSION,'contract_revision':CONTRACT_REVISION,'data':data}
    from .schemas import FormulaCheckResponse,FormulaResultResponse
    if 'task_id' in data:result=FormulaCheckResponse.model_validate(result).model_dump(mode='json')
    elif 'metadata' in data:result=FormulaResultResponse.model_validate(result).model_dump(mode='json')
    if len(canonical(result).encode())>524288:raise ResearchError('PAYLOAD_LIMIT',413,'公式结果超过响应上限。')
    return result


def _sources(conn,store,identity,rid,revision,formula):
    """Use the existing Source reader and its own original task/revision scope."""
    from .evidence_repository import EvidenceRepository
    from .source_integration import context_for,authorizer
    repository=EvidenceRepository(conn,authorizer(store,identity=identity))
    resolved=[]
    for side in ('left','right'):
        form=formula.get(side)
        if form is None:continue
        for ref in form['source_refs']:
            if ref['provenance']!='product_excerpt':raise PermissionError('product source reference required')
            source_row=conn.execute("SELECT task_id,payload_digest FROM research_evidence_objects WHERE id=? AND research_id=? AND kind='excerpts'",(ref['id'],rid)).fetchone()
            if not source_row:raise PermissionError('readable original Source required')
            try:
                context=context_for(conn,source_row['task_id'])
                excerpt=repository.get(context,'excerpts',ref['id'])
                snapshot=repository.get(context,'snapshots',excerpt.snapshot_id)
            except ResearchError as error:
                if error.code!='NOT_FOUND':raise
                raise PermissionError('original Source domain unavailable') from None
            except LookupError:raise PermissionError('original Source unavailable') from None
            # Public read authorization above is mandatory. Reuse the same
            # repository's validated cache read for exact range/hash binding.
            _,raw,extracted=repository._get(context,'snapshots',snapshot.id)
            if (snapshot.source_revision!=ref['revision'] or snapshot.extracted_digest!=ref['content_digest']
                    or excerpt.extracted_digest!=snapshot.extracted_digest
                    or ref['locator']!=f'chars:{excerpt.start}:{excerpt.end}'
                    or type(raw) is not bytes or type(extracted) is not str
                    or extracted[excerpt.start:excerpt.end]!=excerpt.quote):
                raise PermissionError('Source reference or original content mismatch')
            snapshot_row=conn.execute('SELECT payload_digest FROM research_evidence_objects WHERE id=?',(snapshot.id,)).fetchone()
            resolved.append({'excerpt_id':excerpt.id,'snapshot_id':snapshot.id,'source_id':snapshot.source_id,
                'source_revision':snapshot.source_revision,'payload_digest':source_row['payload_digest'],'snapshot_digest':snapshot_row[0],
                'content_digest':snapshot.extracted_digest,'raw_digest':snapshot.raw_digest})
    return resolved


def save_snapshot(conn,*,store,lease,identity,principal,rid,revision,draft):
    if draft is None:return None
    if type(draft) is not FormulaRevisionDraft:raise ResearchError('INPUT_INVALID',422,'公式草稿无效。')
    draft=FormulaRevisionDraft.model_validate(draft.model_dump(mode='json'))
    data=draft.model_dump(mode='json')
    for name in ('left','right'):
        if data[name] is not None:data[name]={'id':str(uuid4()),'revision':revision,**data[name]}
    data['executable']=all(form['expression'] is not None for form in (data['left'],data['right']) if form)
    encoded=canonical(data)
    if len(encoded.encode())>65536:raise ResearchError('PAYLOAD_LIMIT',413,'完整公式快照超过64KiB。')
    gate=AuthorizationGate(store)
    def validate():
        gate.check(conn,identity,principal,rid,scope='write')
        if not conn.execute('SELECT 1 FROM research_revisions WHERE research_id=? AND revision=?',(rid,revision)).fetchone():raise PermissionError('problem revision required')
        _sources(conn,store,identity,rid,revision,data)
    try:
        with _write(conn,store,lease,'research_formula_revisions','INSERT',validate,_factory=_FACTORY):
            conn.execute('INSERT INTO research_formula_revisions VALUES(?,?,?,?)',(rid,revision,encoded,digest(data)))
    except (PermissionError,ValueError):raise ResearchError('INPUT_INVALID',422,'公式来源不可读取或与该修订不匹配。') from None
    return {'revision':revision,'formula_digest':digest(data),'executable':data['executable'],'input_origin':data['input_origin']}


def revision_metadata(conn,rid,revision):
    row=conn.execute('SELECT * FROM research_formula_revisions WHERE research_id=? AND revision=?',(rid,revision)).fetchone()
    if not row:return None
    data=json.loads(row['formula_json']) if row['formula_json'] else None
    return {'revision':revision,'formula_digest':row['formula_digest'],'executable':bool(data and data['executable']),
        'input_origin':'user_provided','state':'draft' if data and not data['executable'] else 'available' if data else 'unavailable',
        'snapshot_ref':f'formula-revisions/{revision}'}


def _snapshot(conn,rid,revision):
    row=conn.execute('SELECT * FROM research_formula_revisions WHERE research_id=? AND revision=?',(rid,revision)).fetchone()
    if not row or row['formula_json'] is None:raise not_found()
    formula=json.loads(row['formula_json'])
    if digest(formula)!=row['formula_digest']:raise PermissionError('formula snapshot digest mismatch')
    return row,formula


def read_revision(service,identity,rid,revision,*,request_source):
    rid=service._id(rid);principal=service._principal(identity)
    from .paid_control import require_authenticated_action
    require_authenticated_action(request_source,identity=identity,action='formula-revision-read',research_id=rid,task_id=str(revision))
    with service.authorization.owner_gate(principal),service.store.transaction() as conn:
        service.authorization.check(conn,identity,principal,rid)
        row,formula=_snapshot(conn,rid,revision)
        try:_sources(conn,service.store,identity,rid,revision,formula)
        except (PermissionError,ValueError):return _envelope({'state':'unavailable','formula_digest':row['formula_digest'],'formula':None})
        return _envelope({'state':'available','formula_digest':row['formula_digest'],'formula':formula,
            'display_assessment':'user_confirmation_required_AST_only','source_facts_verified':False})


def _current(conn,store,identity,principal,rid,task_id,nonce,admission,*,sources=True):
    gate=AuthorizationGate(store)
    control=gate.check(conn,identity,principal,rid,scope='write')
    task=conn.execute('SELECT * FROM research_tasks WHERE id=? AND research_id=?',(task_id,rid)).fetchone()
    run=conn.execute("SELECT * FROM research_formula_runs WHERE task_id=? AND claim_nonce=? AND state='claimed'",(task_id,nonce)).fetchone()
    step=conn.execute('SELECT * FROM research_steps WHERE id=? AND task_id=?',(admission['step_id'],task_id)).fetchone()
    if (not task or not run or not step or task['policy_revision']!=TASK_POLICY or task['execution_mode']!='local_math'
            or task['execution']!='RUNNING' or task['version']!=admission['task_version']
            or control['version']!=admission['research_version'] or control['current_revision']!=admission['input_revision']
            or step['kind']!='formula_check' or step['state']!='SENDING' or step['version']!=admission['step_version']
            or json.loads(run['admission_json'])!=admission or task['input_digest']!=admission['problem_digest']):
        raise PermissionError('current formula claim changed')
    gate.check_task(conn,task)
    revision,formula=_snapshot(conn,rid,admission['input_revision'])
    problem=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(rid,admission['input_revision'])).fetchone()
    if not problem or problem[0]!=admission['problem_digest'] or revision['formula_digest']!=admission['formula_digest']:
        raise PermissionError('formula revision binding changed')
    if sources and _sources(conn,store,identity,rid,admission['input_revision'],formula)!=admission['sources']:raise PermissionError('formula source changed')
    return task,step,control


class CurrentFormulaExecution:
    __slots__=('store','identity','principal','rid','task_id','nonce','admission','input_digest','deadline','pid','code_version','active')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _EXEC_FACTORY:raise TypeError('actual formula admission required')
        for k,v in values.items():object.__setattr__(self,k,v)
    def __setattr__(self,*args):raise TypeError('formula execution immutable')
    def __reduce__(self):raise TypeError('formula execution cannot be serialized')
    def require_identity(self):
        if self.pid!=os.getpid() or not self.active or _EXECUTIONS.get(self.nonce) is not self:raise PermissionError('actual formula execution required')
    def current(self):
        """No owner flock; readonly SQLite wait/progress share the wall deadline."""
        self.require_identity()
        remaining=self.deadline-time.monotonic()
        if remaining<=0:return False
        conn=None
        try:
            if self.store._formal_mode():
                if __package__=='web.backend.research':from ..services.sqlite_utils import connect_private_auth
                else:from services.sqlite_utils import connect_private_auth
                conn=connect_private_auth(self.store.path,readonly=True,timeout=min(.01,remaining),expected_identity=self.store.storage_identity)
            else:conn=sqlite3.connect(self.store.path.as_uri()+'?mode=ro',uri=True,timeout=min(.01,remaining),isolation_level=None)
            conn.row_factory=sqlite3.Row
            bound=min(self.deadline,time.monotonic()+.025)
            conn.set_progress_handler(lambda:int(time.monotonic()>=bound),100)
            conn.execute('PRAGMA busy_timeout=5');conn.execute('PRAGMA foreign_keys=ON')
            if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1:return False
            conn.execute('BEGIN')
            _current(conn,self.store,self.identity,self.principal,self.rid,self.task_id,self.nonce,self.admission)
            return time.monotonic()<self.deadline
        except (ResearchError,PermissionError,sqlite3.Error,ValueError,TypeError,OSError):return False
        finally:
            if conn:conn.close()
    def close(self):object.__setattr__(self,'active',False);_EXECUTIONS.pop(self.nonce,None)


def run_metadata(conn,task_id):
    row=conn.execute('SELECT * FROM research_formula_runs WHERE task_id=?',(task_id,)).fetchone()
    if not row:return None
    admission=json.loads(row['admission_json']) if row['admission_json'] else None
    expired=bool(admission and time.time()>admission['claim_expires_at'])
    commit=json.loads(row['commit_json']) if row['state']=='returned' and row['commit_json'] else None
    return {'result_ref':row['result_ref'],'state':'interrupted' if row['state']=='claimed' and expired else row['state'],
        'result_available':row['state']=='returned','input_origin':'user_provided',
        'formula_digest':admission['formula_digest'] if admission else None,
        'formula_result_recorded_at':commit.get('recorded_at') if commit else None,
        'math_status':None,'termination_state':'not_attested' if row['state']=='closed' else 'reaped' if row['state']=='returned' else 'pending',
        'task_completed_means_math_passed':False,'known_cost_units':0}


def start(service,identity,rid,request,key,*,request_source):
    from .paid_control import require_authenticated_action
    from .formula_check import execution_code_version,owned_check
    from .runner import event_in
    if type(request) is not FormulaCheckRequest:raise ResearchError('INPUT_INVALID',422,'公式检查请求无效。')
    rid=service._id(rid);principal=service._principal(identity)
    payload=request.model_dump(mode='json');request_digest=digest(payload)
    require_authenticated_action(request_source,identity=identity,action='formula-check',research_id=rid,key=key,body_digest=request_digest)
    authority=None;owned=None
    with service.authorization.owner_gate(principal) as lease,service.store.transaction(write=True) as conn:
        service.store._check_v10(conn)
        control=service.authorization.check(conn,identity,principal,rid,scope='write')
        replay=service._replay(conn,principal,'formula-check','r:'+rid,key,request_digest)
        if replay is not None:
            saved=conn.execute('SELECT task_id FROM research_formula_runs WHERE result_ref=?',(replay['data']['result_ref'],)).fetchone()
            if not saved:raise not_found()
            return _envelope({'task_id':saved[0],**run_metadata(conn,saved[0])})
        if control['current_revision']!=request.input_revision or control['version']!=request.expected_research_version:
            raise ResearchError('REVISION_CONFLICT',409,'研究已有新修订或状态，请重新读取公式。')
        if control['version']>=2147483646:raise ResearchError('VERSION_CONFLICT',409,'研究版本已达上限。')
        revision,formula=_snapshot(conn,rid,request.input_revision)
        if revision['formula_digest']!=request.formula_digest:raise ResearchError('REVISION_CONFLICT',409,'公式快照已变化。')
        if not formula['executable']:raise ResearchError('INPUT_INVALID',422,'公式仍缺少结构表达，请补充后保存新修订。')
        if conn.execute("SELECT 1 FROM research_tasks WHERE research_id=? AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING')",(rid,)).fetchone():
            raise ResearchError('TASK_ACTIVE',409,'该研究已有运行任务，请先查看或停止。')
        try:sources=_sources(conn,service.store,identity,rid,request.input_revision,formula)
        except (PermissionError,ValueError):raise ResearchError('INPUT_INVALID',422,'本次公式来源不可读取。') from None
        from .service import now
        task_id,step_id,result_ref,nonce,grant_id=[str(uuid4()) for _ in range(5)];timestamp=now()
        check_input=FormulaCheckInput.parse({'research_id':rid,'input_revision':request.input_revision,'task_id':task_id,'attempt':1,
            **{name:formula[name] for name in ('comparison_scope','requested_checks','sample_points')},
            **{name:None if formula[name] is None else {k:v for k,v in formula[name].items() if k!='time_basis'} for name in ('left','right')}})
        if len(canonical(check_input.data()).encode())>65536:raise ResearchError('PAYLOAD_LIMIT',413,'完整检查输入超过64KiB。')
        problem_digest=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(rid,request.input_revision)).fetchone()[0]
        admission={'research_id':rid,'input_revision':request.input_revision,'principal_id':principal,'principal_epoch':control['owner_epoch'],
            'owner_epoch':control['owner_epoch'],'acl_epoch':control['acl_epoch'],'auth_generation':identity.generation,'grant_id':grant_id,
            'problem_digest':problem_digest,'formula_digest':revision['formula_digest'],'full_input_digest':check_input.input_digest,
            'check_input':check_input.data(),'research_version':control['version']+1,'task_version':1,'step_version':1,
            'step_id':step_id,'sources':sources,'claim_expires_at':int(time.time())+3,'code_version':execution_code_version()}
        if len(canonical(admission).encode())>65536:raise ResearchError('PAYLOAD_LIMIT',413,'完整服务端输入超过64KiB。')
        conn.execute("INSERT INTO research_grants(id,principal_id,principal_epoch,research_id,acl_epoch,scopes,status,created_at) VALUES(?,?,?,?,?,?,'active',?)",(grant_id,principal,control['owner_epoch'],rid,control['acl_epoch'],'["execute"]',timestamp))
        conn.execute("""INSERT INTO research_tasks(id,research_id,principal_id,principal_epoch,owner_epoch,acl_epoch,grant_id,auth_generation,input_revision,input_digest,start_version,execution,phase,version,policy_revision,execution_mode,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,'RUNNING','analysis',1,?,'local_math',?,?)""",(task_id,rid,principal,control['owner_epoch'],control['owner_epoch'],control['acl_epoch'],grant_id,identity.generation,request.input_revision,problem_digest,control['version']+1,TASK_POLICY,timestamp,timestamp))
        conn.execute('INSERT INTO research_attempts VALUES(?,1,?,?,?)',(task_id,'initial',TASK_POLICY,problem_digest))
        conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state,version) VALUES(?,?,0,'formula_check','SENDING',1)",(step_id,task_id))
        changed=conn.execute('UPDATE research_controls SET version=version+1,updated_at=? WHERE id=? AND version=?',(timestamp,rid,control['version'])).rowcount
        if changed!=1:raise ResearchError('VERSION_CONFLICT',409,'研究版本已变化。')
        def validate():
            service.authorization.check(conn,identity,principal,rid,scope='write')
            if _sources(conn,service.store,identity,rid,request.input_revision,formula)!=sources:raise PermissionError('source changed')
        with _write(conn,service.store,lease,'research_formula_runs','INSERT',validate,_factory=_FACTORY):
            conn.execute("INSERT INTO research_formula_runs VALUES(?,?,?,?,'claimed',NULL,NULL,NULL)",(task_id,result_ref,canonical(admission),nonce))
        event_in(conn,task_id,'step_started','formula_claimed')
        result=_envelope({'task_id':task_id,**run_metadata(conn,task_id)})
        service._remember(conn,principal,'formula-check','r:'+rid,key,request_digest,result)
    try:
        authority=CurrentFormulaExecution(_factory=_EXEC_FACTORY,store=service.store,identity=identity,principal=principal,rid=rid,task_id=task_id,
            nonce=nonce,admission=admission,input_digest=check_input.input_digest,deadline=time.monotonic()+2,pid=os.getpid(),code_version=admission['code_version'],active=True)
        _EXECUTIONS[nonce]=authority
        owned=owned_check(check_input.data(),authority=authority)
        return _commit(service,authority,owned)
    except (PermissionError,FormulaInputError,ValueError,TypeError):
        _close(service,identity,principal,rid,task_id,nonce)
        with service.store.transaction() as conn:
            service.authorization.check(conn,identity,principal,rid)
            return _envelope({'task_id':task_id,**run_metadata(conn,task_id)})
    finally:
        if owned:owned.close()
        if authority:authority.close()


def _close(service,identity,principal,rid,task_id,nonce):
    from .runner import state_in
    with service.authorization.owner_gate(principal) as lease,service.store.transaction(write=True) as conn:
        run=conn.execute("SELECT * FROM research_formula_runs WHERE task_id=? AND claim_nonce=? AND state='claimed'",(task_id,nonce)).fetchone()
        if not run:return
        def validate():
            if not conn.execute('SELECT 1 FROM research_principals WHERE id=?',(principal,)).fetchone():raise PermissionError('principal required')
        with _write(conn,service.store,lease,'research_formula_runs','UPDATE',validate,_factory=_FACTORY):
            conn.execute("UPDATE research_formula_runs SET state='closed',admission_json=NULL WHERE task_id=? AND state='claimed'",(task_id,))
        task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(task_id,)).fetchone()
        if task['execution']=='RUNNING':
            conn.execute("UPDATE research_steps SET state='DISCARDED',version=version+1 WHERE task_id=? AND state='SENDING'",(task_id,))
            state_in(conn,task_id,'FAILED',safe_code='formula_execution_not_committed')


def _commit(service,authority,owned):
    from .formula_check import OwnedFormulaReturn
    from .formula_result_adapter import project_formula_result
    from .runner import state_in
    if type(owned) is not OwnedFormulaReturn:raise PermissionError('actual owned return required')
    raw,receipt=owned.require(authority)
    request=FormulaCheckInput.parse(authority.admission['check_input'])
    project_formula_result(raw,expected_input=request,expected_output_digest=raw['output_digest'])
    encoded=canonical(raw)
    if len(encoded.encode())>524288:raise FormulaLimit('result limit')
    with service.authorization.owner_gate(authority.principal) as lease,service.store.transaction(write=True) as conn:
        task,step,control=_current(conn,service.store,authority.identity,authority.principal,authority.rid,authority.task_id,authority.nonce,authority.admission)
        # Validate the actual return again inside the short authorization/CAS txn.
        def validate():
            owned.require(authority)
            _current(conn,service.store,authority.identity,authority.principal,authority.rid,authority.task_id,authority.nonce,authority.admission)
        from .service import now
        commit={'recorded_at':now(),'research_before':control['version'],'research_after':control['version']+1,'task_before':task['version'],
            'task_after':task['version']+1,'step_before':step['version'],'step_after':step['version']+1,
            'problem_digest':authority.admission['problem_digest'],'formula_digest':authority.admission['formula_digest'],
            'full_input_digest':request.input_digest,'output_digest':raw['output_digest'],'receipt_ref':receipt['reference']}
        with _write(conn,service.store,lease,'research_formula_runs','UPDATE',validate,_factory=_FACTORY):
            changed=conn.execute("UPDATE research_formula_runs SET state='returned',receipt_json=?,result_json=?,commit_json=? WHERE task_id=? AND claim_nonce=? AND state='claimed'",(canonical(receipt),encoded,canonical(commit),task['id'],authority.nonce)).rowcount
            if changed!=1:raise PermissionError('formula claim CAS failed')
        changed=conn.execute("UPDATE research_steps SET state='SUCCEEDED',version=version+1 WHERE id=? AND version=? AND state='SENDING'",(step['id'],step['version'])).rowcount
        if changed!=1:raise PermissionError('formula step CAS failed')
        state_in(conn,task['id'],'COMPLETED',phase='completed',safe_code='formula_check_returned')
        changed=conn.execute('UPDATE research_controls SET version=version+1 WHERE id=? AND version=?',(authority.rid,control['version'])).rowcount
        if changed!=1:raise PermissionError('formula research CAS failed')
        return _envelope({'task_id':task['id'],**run_metadata(conn,task['id'])})


def read_result(service,identity,rid,ref,*,request_source):
    from .formula_result_adapter import project_formula_result
    rid=service._id(rid);ref=service._id(ref);principal=service._principal(identity)
    from .paid_control import require_authenticated_action
    require_authenticated_action(request_source,identity=identity,action='formula-read',research_id=rid,task_id=ref)
    with service.authorization.owner_gate(principal),service.store.transaction() as conn:
        service.authorization.check(conn,identity,principal,rid)
        row=conn.execute('SELECT r.*,t.input_revision FROM research_formula_runs r JOIN research_tasks t ON t.id=r.task_id WHERE r.result_ref=? AND t.research_id=?',(ref,rid)).fetchone()
        if not row:raise not_found()
        metadata=run_metadata(conn,row['task_id'])
        if row['state']!='returned':return _envelope({'metadata':metadata,'result':None,'state':'unavailable'})
        admission=json.loads(row['admission_json']);commit=json.loads(row['commit_json']);receipt=json.loads(row['receipt_json']);raw=json.loads(row['result_json'])
        try:
            _,formula=_snapshot(conn,rid,row['input_revision'])
            if _sources(conn,service.store,identity,rid,row['input_revision'],formula)!=admission['sources']:raise PermissionError('source changed')
        except (PermissionError,ValueError):return _envelope({'metadata':metadata,'result':None,'state':'unavailable'})
        task=conn.execute('SELECT * FROM research_tasks WHERE id=? AND research_id=?',(row['task_id'],rid)).fetchone()
        step=conn.execute('SELECT * FROM research_steps WHERE id=? AND task_id=?',(admission['step_id'],row['task_id'])).fetchone()
        control=service.authorization.check(conn,identity,principal,rid)
        revision=conn.execute('SELECT digest,problem_json FROM research_revisions WHERE research_id=? AND revision=?',(rid,row['input_revision'])).fetchone()
        try:
            service.authorization.check_task(conn,task)
            if (type(admission['input_revision']) is not int or admission['research_id']!=rid or admission['principal_id']!=principal
                    or admission['input_revision']!=task['input_revision'] or task['policy_revision']!=TASK_POLICY
                    or task['execution_mode']!='local_math' or task['execution']!='COMPLETED' or task['attempt']!=1
                    or not revision or revision['digest']!=admission['problem_digest']
                    or digest(json.loads(revision['problem_json']))!=admission['problem_digest']
                    or digest(formula)!=admission['formula_digest'] or control['current_revision']<task['input_revision']
                    or not step or step['kind']!='formula_check' or step['position']!=0 or step['state']!='SUCCEEDED'
                    or step['reservation_id'] is not None):raise PermissionError('stored formula domain changed')
            bindings={'principal_id':principal,'principal_epoch':admission['principal_epoch'],'owner_epoch':admission['owner_epoch'],
                'acl_epoch':admission['acl_epoch'],'auth_generation':admission['auth_generation'],'grant_id':admission['grant_id'],
                'input_digest':admission['problem_digest'],'start_version':admission['research_version']}
            if any(task[name]!=value for name,value in bindings.items()):raise PermissionError('original task binding changed')
            request=FormulaCheckInput.parse({'research_id':rid,'input_revision':task['input_revision'],'task_id':task['id'],'attempt':task['attempt'],
                **{name:formula[name] for name in ('comparison_scope','requested_checks','sample_points')},
                **{name:None if formula[name] is None else {k:v for k,v in formula[name].items() if k!='time_basis'} for name in ('left','right')}})
            if request.data()!=admission['check_input'] or request.input_digest!=admission['full_input_digest']:
                raise PermissionError('actual immutable formula input changed')
            for prefix in ('research','task','step'):
                if (type(commit.get(prefix+'_before')) is not int or type(commit.get(prefix+'_after')) is not int
                        or not 1<=commit[prefix+'_before']<2147483647 or commit[prefix+'_after']!=commit[prefix+'_before']+1):
                    raise PermissionError('strict protected commit versions required')
            from datetime import datetime
            if type(commit.get('recorded_at')) is not str or datetime.strptime(commit['recorded_at'],'%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%dT%H:%M:%S.%fZ')!=commit['recorded_at']:
                raise PermissionError('strict original formula record timestamp required')
            expected={'recorded_at':commit['recorded_at'],'research_before':admission['research_version'],'research_after':admission['research_version']+1,
                'task_before':admission['task_version'],'task_after':admission['task_version']+1,
                'step_before':admission['step_version'],'step_after':admission['step_version']+1,
                'problem_digest':revision['digest'],'formula_digest':digest(formula),'full_input_digest':request.input_digest,
                'output_digest':raw['output_digest'],'receipt_ref':receipt['reference']}
            if (commit!=expected or task['version']!=commit['task_after'] or step['version']!=commit['step_after']
                    or control['version']<commit['research_after'] or receipt['claim_nonce']!=row['claim_nonce']
                    or receipt['input_digest']!=request.input_digest or receipt['code_version']!=admission['code_version']
                    or receipt['result_digest']!=digest(raw) or receipt['reaped'] is not True):
                raise PermissionError('stored result is not the actual committed task result')
        except (PermissionError,ValueError,TypeError,KeyError):raise not_found() from None
        content=project_formula_result(raw,expected_input=request,expected_output_digest=commit['output_digest']).data()
        # Public pure-content flags remain false. Trust is a distinct server
        # projection backed by this protected stored return, never client JSON.
        return _envelope({'metadata':metadata,'state':'available','result':content,'provenance':{
            'execution_attested':receipt['return_state']=='ok','execution_state':receipt['return_state'],
            'resource_guard':receipt['resource_guard'],'owned_return_ref':receipt['reference'],'reaped':receipt['reaped'],
            'code_version':receipt['code_version'],'full_input_digest':request.input_digest,'output_digest':commit['output_digest'],
            'formula_digest':admission['formula_digest'],'problem_digest':admission['problem_digest'],
            'display_AST_confirmation':'user_confirmed_snapshot','source_origin':formula['input_origin'],
            'source_facts_verified':False,'mathematics_is_not_real_world_mechanism':True}})


def cancel_in(conn,*,store,lease,identity,principal,rid,task_id):
    run=conn.execute("SELECT * FROM research_formula_runs WHERE task_id=? AND state='claimed'",(task_id,)).fetchone()
    if not run:return
    def validate():AuthorizationGate(store).check(conn,identity,principal,rid,scope='write')
    with _write(conn,store,lease,'research_formula_runs','UPDATE',validate,_factory=_FACTORY):
        conn.execute("UPDATE research_formula_runs SET state='closed',admission_json=NULL WHERE task_id=? AND state='claimed'",(task_id,))
    conn.execute("UPDATE research_steps SET state='DISCARDED',version=version+1 WHERE task_id=? AND kind='formula_check' AND state='SENDING'",(task_id,))
