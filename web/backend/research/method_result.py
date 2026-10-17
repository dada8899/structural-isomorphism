"""V9 controlled, erasable method bodies and authenticated typed consumers.

No worker, network, funding resolver, or reconstructed transport receipt.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path

from .authorization import AccountIdentity,AuthorizationGate,OwnerGateLease
from .errors import ResearchError,not_found
from .provider_schemas import canonical,digest,CallContext,EvidencePacket,EvidenceHandle,UsageObservation

PRODUCER='owned-method-offline-v1'
_FACTORY=object()
_WRITES={}
_FIELDS=('candidate_json','body_origin_state','body_candidate_digest','body_envelope_digest','method_commit_json')
_IDENTITY=('id','approval_id','dispatch_id','permit_id','mode','binding_digest')


def _row(conn,ref):
    row=conn.execute('SELECT rowid AS source_rowid,* FROM research_provider_sessions WHERE id=?',(ref,)).fetchone()
    return dict(row) if row else None


def _scope(conn,store,lease,*,write=False):
    from .paid_control import _SCOPES
    from .store import ResearchStore
    scope=_SCOPES.get(id(conn))
    database=next((r[2] for r in conn.execute('PRAGMA database_list') if r[1]=='main'),None)
    if (not scope or scope.conn is not conn or not scope.active or scope.pid!=os.getpid() or not conn.in_transaction
            or (write and not scope.write) or type(store) is not ResearchStore or type(lease) is not OwnerGateLease
            or not database or Path(database).resolve()!=store.path or conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1
            or conn.execute('SELECT version FROM research_schema').fetchone()[0] not in (9,10)):
        raise PermissionError('current canonical method scope required')
    lease.identity
    if conn.execute('SELECT version FROM research_schema').fetchone()[0]==10:ResearchStore._check_v10(conn)
    else:ResearchStore._check_v9(conn)
    return scope


def install_hook(conn):
    pid=os.getpid()
    def allowed(operation,ref,raw):
        entry=_WRITES.get(id(conn))
        if (pid!=os.getpid() or not entry or entry['conn'] is not conn or not entry['scope'].active
                or not conn.in_transaction or entry['operation']!=operation or entry['ref']!=ref):return 0
        try:
            entry['lease'].identity
            entry['validate']()
            return int(json.loads(raw)==entry['expected'] and digest(canonical(_row(conn,ref)))==entry['before'])
        except (PermissionError,ResearchError,ValueError,TypeError,OSError):return 0
    conn.create_function('research_method_write_allowed',3,allowed)
    conn.create_function('research_method_guard_version',0,lambda:9 if pid==os.getpid() else 0)


def statement_allowed(conn):
    entry=_WRITES.get(id(conn))
    return bool(entry and entry['conn'] is conn and entry['scope'].active and entry['scope'].pid==os.getpid() and conn.in_transaction)


@contextmanager
def _write_scope(conn,store,lease,ref,expected,validate,*,operation='write',_factory=None):
    if _factory is not _FACTORY:raise TypeError('actual method producer required')
    scope=_scope(conn,store,lease,write=True)
    if id(conn) in _WRITES:raise PermissionError('method scope already active')
    validate()
    _WRITES[id(conn)]={'conn':conn,'scope':scope,'lease':lease,'ref':ref,'operation':operation,
        'expected':expected,'before':digest(canonical(_row(conn,ref))),'validate':validate}
    scope.refresh_authorizer()
    try:yield
    finally:_WRITES.pop(id(conn),None);scope.refresh_authorizer()


def _values(row,**changes):return {**{field:row.get(field) for field in (*_IDENTITY,*_FIELDS)},**changes}


def fresh_scope(conn,*,store,lease,authority,ref):
    from .paid_control import CurrentPaidAuthority
    if type(authority) is not CurrentPaidAuthority or authority._lease is not lease:raise PermissionError('actual new B reserve source required')
    def identity():
        from .paid_budget import PRODUCER as budget_producer
        facts=authority.require(conn,'reserve')
        permit=conn.execute('SELECT * FROM research_dispatch_permits WHERE step_id=?',(facts.step_id,)).fetchone()
        if not permit or permit['paid_approval_ref']!=facts.approval_ref or permit['state']!='prepared':raise PermissionError('actual new prepared method session required')
        descriptor=digest(canonical({'producer':budget_producer,'dispatch':permit['dispatch_id'],'request':facts.request_digest,'reservation':permit['reservation_id']}))
        return dict(id=ref,approval_id=facts.approval_ref,dispatch_id=permit['dispatch_id'],permit_id=permit['id'],mode='offline_probe',binding_digest=descriptor)
    expected=_values(identity(),body_origin_state='fresh')
    def validate():
        facts=authority.require(conn,'reserve')
        if facts.policy!='bounded_usage_upper_v2' or facts.execution_mode!='offline_probe' or _row(conn,ref) or _values(identity(),body_origin_state='fresh')!=expected:
            raise PermissionError('new method session required')
    return _write_scope(conn,store,lease,ref,expected,validate,operation='birth',_factory=_FACTORY)


def _binding(conn,snapshot,session,approval,context):
    from .method_body_types import ExpectedMethodBodyBinding
    return ExpectedMethodBodyBinding(result_ref=session['id'],research_id=context.research_id,task_id=context.task_id,
        step_id=snapshot.dispatch.step_id,input_revision=context.input_revision,input_digest=context.input_digest,
        approval_ref=approval['id'],dispatch_id=snapshot.dispatch.dispatch_id,permit_id=snapshot.dispatch.permit_id,
        approval_consumed_version=approval['version'],permit_state='consumed',session_consumed_version=snapshot.dispatch.session_after,
        authorized_task_version=snapshot.dispatch.authorized_task_version,authorized_step_version=snapshot.dispatch.authorized_step_version,
        request_digest=snapshot.dispatch.request_digest,evidence_digest=snapshot.dispatch.evidence_digest,
        financial_return_ref=session['id'],financial_return_digest=session['return_digest'],candidate_schema='ModelReportCandidate-v1',
        body_schema='OwnedMethodBody-v1',producer_revision=PRODUCER,execution_mode='offline_probe',received_at=session['received_at'])


def _require_receipt(conn,store,lease,receipt,raw,return_digest):
    from .paid_provider_session import BudgetOwnedReceipt,_B_SESSIONS
    from .paid_budget import _load_admission,PRODUCER as financial_producer
    if type(receipt) is not BudgetOwnedReceipt or receipt._pid!=os.getpid():raise PermissionError('actual B receipt required')
    owner=receipt._owner
    if (_B_SESSIONS.get(owner.id) is not owner or owner.store is not store or owner._receipt is not receipt
            or owner.pid!=os.getpid() or owner._received is not receipt._value or receipt._digest!=digest(canonical(receipt._value.model_dump()))):
        raise PermissionError('actual owned method reception required')
    admission,snapshot,_,_,_,session=_load_admission(conn,store,lease,owner.id)
    actual=dict(record_version=financial_producer,admission_ref=admission['id'],admission_digest=admission['snapshot_digest'],
        transport=receipt._value.model_dump(exclude={'candidate','context'}),received_at=receipt._time,
        execution_mode='offline_probe',model_analysis_ran=False,actual_charge=None)
    if raw!=canonical(actual).decode() or return_digest!=digest(canonical(actual)):raise PermissionError('actual financial reception binding required')
    return owner,snapshot,session


class _ReceiptDecision:
    __slots__=('_conn','_store','_lease','_receipt','_raw','_digest','_values','_before','_scope')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _FACTORY:raise TypeError('actual receipt body decision required')
        for key,value in values.items():object.__setattr__(self,key,value)
    def __setattr__(self,*args):raise TypeError('receipt body decision immutable')
    def __reduce__(self):raise TypeError('receipt body decision cannot be serialized')
    def require(self,conn):
        if conn is not self._conn or _scope(conn,self._store,self._lease,write=True) is not self._scope:raise PermissionError('receipt body decision retired')
        owner,_,_=_require_receipt(conn,self._store,self._lease,self._receipt,self._raw,self._digest)
        if digest(canonical(_row(conn,owner.id)))!=self._before:raise PermissionError('receipt body target changed')
        if json.loads(self._values)['body_origin_state']=='present' and not owner._current_content(conn):raise PermissionError('method content permission ended')


def receipt_body_scope(conn,*,store,lease,receipt,raw,return_digest):
    """A sealed decision, not caller values/callbacks, conveys first-write scope."""
    owner,snapshot,session=_require_receipt(conn,store,lease,receipt,raw,return_digest)
    if session['body_origin_state']=='legacy_unproved':return None,None
    row=_row(conn,owner.id)
    def decision(values):
        return values,_ReceiptDecision(_factory=_FACTORY,_conn=conn,_store=store,_lease=lease,_receipt=receipt,_raw=raw,
            _digest=return_digest,_values=canonical(values),_before=digest(canonical(row)),_scope=_scope(conn,store,lease,write=True))
    if session['financial_return_json'] is not None:
        if session['body_origin_state']=='present' and not owner._current_content(conn):
            return decision(_values(row,candidate_json=None,body_origin_state='closed',body_candidate_digest=None,body_envelope_digest=None,method_commit_json=None))
        return None,None
    values=_values(row,candidate_json=None,body_origin_state='closed',body_candidate_digest=None,body_envelope_digest=None,method_commit_json=None)
    if session['body_origin_state']=='fresh' and owner._current_content(conn) and receipt._value.candidate is not None:
        from .model_report import parse_candidate
        from .method_body_codec import encode_method_body
        try:
            candidate=parse_candidate(receipt._value.candidate.encode(),owner.packet).model_dump(mode='json')
            approval=conn.execute('SELECT * FROM research_paid_approvals WHERE id=?',(session['approval_id'],)).fetchone()
            actual=dict(session,return_digest=return_digest,received_at=receipt._time)
            binding=_binding(conn,snapshot,actual,approval,owner.packet.context)
            encoded=encode_method_body(candidate,binding,digest(canonical(candidate)))
            values=_values(row,candidate_json=encoded.raw.decode(),body_origin_state='present',
                body_candidate_digest=encoded.candidate_digest,body_envelope_digest=encoded.envelope_digest)
        except (ValueError,TypeError,ResearchError):pass
    return decision(values)


def receipt_scope(conn,*,store,lease,receipt,values,decision):
    if (type(decision) is not _ReceiptDecision or decision._conn is not conn or decision._store is not store
            or decision._lease is not lease or decision._receipt is not receipt or canonical(values)!=decision._values):
        raise PermissionError('actual sealed body decision required')
    return _write_scope(conn,store,lease,receipt._owner.id,json.loads(decision._values),lambda:decision.require(conn),_factory=_FACTORY)


def erase_for_deletion(conn,*,store,lease,pid,job_id):
    from .paid_control import verify_deletion_origin
    def validate():
        job=verify_deletion_origin(conn,store=store,lease=lease,job_id=job_id)
        principal=conn.execute('SELECT * FROM research_principals WHERE id=?',(pid,)).fetchone()
        if (not job or job['state']!='pending' or not principal or principal['status']!='deleting'
                or principal['gate_id']!=job['gate_id'] or principal['normalized_email']!=job['owner_email']
                or principal['session_generation']!=job['session_generation']):raise PermissionError('actual deletion body source required')
    rows=conn.execute('SELECT s.id FROM research_provider_sessions s JOIN research_paid_approvals a ON a.id=s.approval_id WHERE a.principal_id=?',(pid,)).fetchall()
    for item in rows:
        row=_row(conn,item[0])
        if row['body_origin_state']=='legacy_unproved':
            conn.execute('UPDATE research_provider_sessions SET candidate_json=NULL WHERE id=?',(item[0],));continue
        values=_values(row,candidate_json=None,body_origin_state='closed',body_candidate_digest=None,body_envelope_digest=None,method_commit_json=None)
        with _write_scope(conn,store,lease,item[0],values,validate,_factory=_FACTORY):
            conn.execute("UPDATE research_provider_sessions SET candidate_json=NULL,body_origin_state='closed',body_candidate_digest=NULL,body_envelope_digest=NULL,method_commit_json=NULL WHERE id=?",(item[0],))


def _request(source,identity,rid,task_id):
    from .paid_control import AuthenticatedActionSource,require_authenticated_action
    if type(source) is not AuthenticatedActionSource or source.action not in ('method-read','method-reconcile'):
        raise PermissionError('actual method HTTP source required')
    require_authenticated_action(source,identity=identity,action=source.action,research_id=rid,task_id=source.task_id)
    if source.task_id is not None and source.task_id!=task_id:raise PermissionError('method request task mismatch')
    return source.action


def _packet(conn,store,identity,snapshot,session,request_source):
    from .evidence_repository import EvidenceRepository
    from .source_integration import authorizer,context_for
    approval=conn.execute('SELECT * FROM research_paid_approvals WHERE id=?',(session['approval_id'],)).fetchone()
    permit=conn.execute('SELECT authorization_context_json FROM research_dispatch_permits WHERE id=?',(snapshot.dispatch.permit_id,)).fetchone()
    if not approval or approval['state']!='consumed' or not approval['payload_json'] or not permit:raise not_found()
    payload=json.loads(approval['payload_json'])
    if digest(canonical(payload))!=approval['payload_digest']:raise PermissionError('method approval input damaged')
    context=CallContext(principal_id=snapshot.actor.principal_id,principal_epoch=snapshot.actor.principal_epoch,
        grant_id=snapshot.actor.grant_id,grant_epoch=snapshot.actor.grant_epoch,owner_epoch=payload['owner_epoch'],acl_epoch=payload['acl_epoch'],
        research_id=approval['research_id'],input_revision=payload['input_revision'],input_digest=payload['problem_digest'],
        task_id=snapshot.dispatch.task_id,attempt=snapshot.dispatch.attempt,plan_id=payload['plan_id'])
    if permit[0] is not None and CallContext.model_validate_json(permit[0])!=context:raise PermissionError('original method context differs')
    if digest(canonical(context.model_dump()))!=snapshot.dispatch.context_digest:raise PermissionError('method original context damaged')
    gate=AuthorizationGate(store);control=gate.check(conn,identity,context.principal_id,context.research_id)
    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(context.task_id,)).fetchone()
    gate.check_task(conn,task)
    current=conn.execute('SELECT id FROM research_tasks WHERE research_id=? AND input_revision=? ORDER BY start_version DESC,id DESC LIMIT 1',
        (control['id'],control['current_revision'])).fetchone()
    historical=task['input_revision']!=control['current_revision'] or not current or current[0]!=task['id']
    action=_request(request_source,identity,control['id'],task['id'])
    if historical and (action!='method-read' or request_source.task_id!=task['id']):raise not_found()
    grant=conn.execute('SELECT * FROM research_grants WHERE id=?',(context.grant_id,)).fetchone()
    if (task['input_revision']>control['current_revision'] or task['input_digest']!=context.input_digest
            or not grant or grant['version']!=context.grant_epoch or 'execute_paid' not in json.loads(grant['scopes'])
            or task['execution'] in ('FAILED','CANCELLED','ACCESS_REVOKED')):raise not_found()
    bindings={'id':context.task_id,'research_id':context.research_id,'principal_id':context.principal_id,'principal_epoch':context.principal_epoch,
        'owner_epoch':context.owner_epoch,'acl_epoch':context.acl_epoch,'grant_id':context.grant_id,'input_revision':context.input_revision,
        'input_digest':context.input_digest,'auth_generation':identity.generation,'attempt':context.attempt,'policy_revision':'bounded_usage_upper_v2'}
    revision=conn.execute('SELECT digest,problem_json FROM research_revisions WHERE research_id=? AND revision=?',(context.research_id,context.input_revision)).fetchone()
    if (any(task[name]!=value for name,value in bindings.items()) or not revision or revision['digest']!=context.input_digest
            or digest(canonical(json.loads(revision['problem_json'])))!=context.input_digest):raise not_found()
    repository=EvidenceRepository(conn,authorizer(store,identity=identity));handles=[]
    for index,ref in enumerate(payload['source_refs']):
        evidence=conn.execute("SELECT task_id FROM research_evidence_objects WHERE id=? AND kind='excerpts' AND research_id=? AND input_revision=?",(ref,context.research_id,context.input_revision)).fetchone()
        if not evidence:raise not_found()
        try:
            source_context=context_for(conn,evidence[0]);eligible,handle=repository.preview_provider_handle(source_context,ref,'e'+str(index+1))
            excerpt,_,_=repository._get(source_context,'excerpts',ref)
            _,_,extracted=repository._get(source_context,'snapshots',excerpt.snapshot_id)
        except LookupError:raise not_found() from None
        handles.append(EvidenceHandle(**handle.model_dump(),extracted_text=extracted,display_permission=True,may_send_to_provider=True))
    packet=EvidencePacket(context=context,handles=tuple(handles))
    if packet.binding_digest()!=snapshot.dispatch.evidence_digest:raise PermissionError('current method sources differ')
    return packet,task,control,approval,historical


class BodySource:
    __slots__=('_conn','_scope','_store','_lease','_identity','_request','_rid','_task','_session','_decoded','_packet','_snapshot','_before','_historical')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _FACTORY:raise TypeError('current controlled body reader required')
        for key,value in values.items():object.__setattr__(self,key,value)
    def __setattr__(self,*args):raise TypeError('body source immutable')
    def __reduce__(self):raise TypeError('body source cannot be serialized')
    def require(self,conn):
        if conn is not self._conn or _scope(conn,self._store,self._lease) is not self._scope:raise PermissionError('body scope retired')
        _request(self._request,self._identity,self._rid,self._task['id'])
        if digest(canonical(_row(conn,self._session['id'])))!=self._before:raise PermissionError('body source changed')
        *_,historical=_packet(conn,self._store,self._identity,self._snapshot,self._session,self._request)
        if historical!=self._historical:raise PermissionError('method read domain changed')
        return self


def read_source(conn,*,store,lease,identity,rid,task_id,request_source):
    scope=_scope(conn,store,lease)
    _request(request_source,identity,rid,task_id)
    from .paid_budget import _validated_return
    session=conn.execute('SELECT s.id FROM research_provider_sessions s JOIN research_paid_approvals a ON a.id=s.approval_id WHERE a.task_id=? AND a.research_id=?',(task_id,rid)).fetchone()
    if not session:return None
    row=_row(conn,session[0])
    if row['body_origin_state']!='present':return None
    _,snapshot,_,_,_,_=_validated_return(conn,store,lease,row['id'],read=True)
    packet,task,control,approval,historical=_packet(conn,store,identity,snapshot,row,request_source)
    from .method_body_codec import decode_method_body
    from .model_report import parse_candidate
    decoded=decode_method_body(row['candidate_json'],_binding(conn,snapshot,row,approval,packet.context),row['body_candidate_digest'],row['body_envelope_digest'])
    parse_candidate(canonical(decoded.candidate.model_dump(mode='json')),packet)
    return BodySource(_factory=_FACTORY,_conn=conn,_scope=scope,_store=store,_lease=lease,_identity=identity,_request=request_source,
        _rid=rid,_task=dict(task),_session=row,_decoded=decoded,_packet=packet,_snapshot=snapshot,_before=digest(canonical(row)),_historical=historical)


def _cost(conn,source):
    from .usage_upper import observed_bound
    from .paid_budget import _validated_return
    _,snapshot,transport,reservation,_,_=_validated_return(conn,source._store,source._lease,source._session['id'],read=True)
    row=conn.execute("SELECT * FROM research_cost_observations WHERE trusted_return_ref=? AND kind='estimated_upper'",(source._session['id'],)).fetchone()
    if reservation['status']!='UPPER_BOOKED' or not row or transport['usage'] is None:raise PermissionError('trusted complete usage required')
    math=observed_bound(snapshot.quote,snapshot.reserved,UsageObservation.model_validate(transport['usage']),
        dispatch_id=snapshot.dispatch.dispatch_id,request_digest=snapshot.dispatch.request_digest)
    if (row['actual_charge'] is not None or row['booked_upper']!=math.observed_upper.amount_units or row['observation_digest']!=digest(canonical(math.model_dump()))
            or row['response_digest']!=transport['response_digest']):raise PermissionError('typed cost binding damaged')


def commit_result(conn,*,store,lease,identity,rid,task_id,request_source):
    if _request(request_source,identity,rid,task_id)!='method-reconcile':raise PermissionError('actual typed reconcile required')
    try:
        source=read_source(conn,store=store,lease=lease,identity=identity,rid=rid,task_id=task_id,request_source=request_source)
        if source is None:return False
        if source._historical:raise PermissionError('historical source is read only')
        source.require(conn);_cost(conn,source)
    except ResearchError as exc:
        if exc.code=='NOT_FOUND':return False
        raise
    except (PermissionError,ValueError,TypeError,KeyError):return False
    if source._session['method_commit_json'] is not None:return True
    task=source._task;step=conn.execute('SELECT * FROM research_steps WHERE id=?',(source._snapshot.dispatch.step_id,)).fetchone()
    control=conn.execute('SELECT * FROM research_controls WHERE id=?',(rid,)).fetchone()
    if task['execution'] in ('COMPLETED','FAILED','CANCELLED','ACCESS_REVOKED') or step['state'] in ('SUCCEEDED','FAILED','DISCARDED'):raise PermissionError('typed task ended')
    meta=dict(version='method-result-commit-v1',result_ref=source._session['id'],research_id=rid,task_id=task_id,step_id=step['id'],
        input_revision=task['input_revision'],input_digest=task['input_digest'],task_before=task['version'],task_after=task['version']+1,
        step_before=step['version'],step_after=step['version']+1,research_before=control['version'],research_after=control['version']+1)
    values=_values(source._session,method_commit_json=canonical(meta).decode())
    with _write_scope(conn,store,lease,source._session['id'],values,lambda:source.require(conn),_factory=_FACTORY):
        if conn.execute('UPDATE research_provider_sessions SET method_commit_json=? WHERE id=? AND method_commit_json IS NULL',(values['method_commit_json'],source._session['id'])).rowcount!=1:raise PermissionError('typed result CAS changed')
    for sql,args in [
        ("UPDATE research_steps SET state='SUCCEEDED',version=version+1 WHERE id=? AND version=?",(step['id'],step['version'])),
        ("UPDATE research_tasks SET execution='COMPLETED',evidence='INSUFFICIENT',version=version+1 WHERE id=? AND version=?",(task_id,task['version'])),
        ('UPDATE research_controls SET version=version+1 WHERE id=? AND version=?',(rid,control['version']))]:
        if conn.execute(sql,args).rowcount!=1:raise PermissionError('typed object CAS changed')
    from .runner import event_in
    event_in(conn,task_id,'terminal')
    return True


def result_view(conn,*,store,lease,identity,rid,task_id,request_source):
    source=read_source(conn,store=store,lease=lease,identity=identity,rid=rid,task_id=task_id,request_source=request_source)
    if source is None or source._session['method_commit_json'] is None:return None
    source.require(conn);_cost(conn,source)
    meta=json.loads(source._session['method_commit_json'])
    task=source._task;control=conn.execute('SELECT * FROM research_controls WHERE id=?',(rid,)).fetchone()
    step=conn.execute('SELECT * FROM research_steps WHERE id=?',(source._snapshot.dispatch.step_id,)).fetchone()
    if (type(meta) is not dict or type(meta.get('input_revision')) is not int
            or not 1<=meta['input_revision']<=2147483647 or any(
        type(meta.get(prefix+'_before')) is not int or type(meta.get(prefix+'_after')) is not int
        or not 1<=meta[prefix+'_before']<2147483647 or meta[prefix+'_after']!=meta[prefix+'_before']+1
        for prefix in ('research','task','step'))):
        raise PermissionError('invalid protected original commit versions')
    expected=dict(version='method-result-commit-v1',result_ref=source._session['id'],research_id=rid,task_id=task_id,step_id=step['id'],
        input_revision=task['input_revision'],input_digest=task['input_digest'],task_before=task['version']-1,task_after=task['version'],
        step_before=step['version']-1,step_after=step['version'],research_before=meta['research_before'],research_after=meta['research_after'])
    if (meta!=expected or control['version']<meta['research_after'] or task['execution']!='COMPLETED'
            or step['state']!='SUCCEEDED'):raise PermissionError('typed current version changed')
    header=source._decoded.header
    return dict(schema_version='MethodHypothesisResultView-v1',result_ref=header.result_ref,input_revision=header.input_revision,input_digest=header.input_digest,
        candidate_schema=header.candidate_schema,body_schema=header.body_schema,producer_revision=header.producer_revision,received_at=header.received_at,
        candidate_digest=source._session['body_candidate_digest'],envelope_digest=source._session['body_envelope_digest'],is_historical=bool(source._historical),
        execution_mode='offline_probe',model_analysis_ran=False,status='qualified_report',evidence='INSUFFICIENT',assessment='llm_inference',review='unreviewed',
        sections=source._decoded.candidate.model_dump(mode='json'),citations=[handle.model_dump(include={'handle','source_id','source_revision','excerpt_id','title','attribution','start','end','quote','extracted_digest'}) for handle in source._packet.handles])
