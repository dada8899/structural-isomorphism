"""Fixed evidence readers and data assembly. Financial writes stay in F9."""
import base64
from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
import os
import sqlite3
import sys
import threading

from . import evidence_method_plan_schemas as types,evidence_method_plan_codec as codec
from .authorization import AccountIdentity,AuthorizationGate,OwnerGateLease
from .errors import ResearchError,not_found
from .provider_schemas import canonical,digest

_FACTORY=object()
_READERS={}


def envelope(data):return dict(schema_version='structure-research-v1',contract_revision=types.CONTRACT,data=data)
def is_evidence(value):
    raw=value['consent_json'] if value else None
    if raw is None:return False
    data=json.loads(raw)
    if type(data) is not dict:raise ValueError('protected native consent object required')
    return data.get('protocol')=='evidence-method-consent-v1'


def _native(conn,store,lease=None):
    from .store import ResearchStore
    from .paid_control import _SCOPES
    if __package__=='web.backend.research':from ..services.sqlite_utils import PrivateAuthConnection
    else:from services.sqlite_utils import PrivateAuthConnection
    base=_SCOPES.get(id(conn))
    if (type(store) is not ResearchStore or type(conn) is not PrivateAuthConnection or not conn.in_transaction
            or base is None or base.conn is not conn or not base.active or base.pid!=os.getpid()
            or conn.private_storage_identity!=store.storage_identity
            or [r[2] for r in conn.execute('PRAGMA database_list') if r[1]=='main']!=[str(store.path)]):
        raise PermissionError('actual evidence transaction required')
    if lease is not None:
        if type(lease) is not OwnerGateLease:raise PermissionError('actual evidence Owner required')
        lease.identity
    return base


def _caller(functions,conn,lease,store):
    expected={f.__code__:f for f in functions};frame=sys._getframe(1)
    try:
        while frame is not None and frame.f_code not in expected:frame=frame.f_back
        if (frame is None or frame.f_globals is not expected[frame.f_code].__globals__
                or frame.f_locals.get('conn') is not conn or frame.f_locals.get('lease') is not lease):
            raise PermissionError('fixed actual evidence producer frame required')
        actual_store=frame.f_locals.get('store')
        if actual_store is None:
            service=frame.f_locals.get('service');actual_store=getattr(service,'store',None)
        if actual_store is not store:raise PermissionError('same evidence producer store required')
        return frame.f_locals.get('request'),frame.f_locals.get('self')
    finally:del frame


def parse_consent(value,*,preview=False):
    raw=value['consent_json']
    if type(raw) is not str:raise PermissionError('evidence consent erased')
    cls=types.PreviewConsent if preview else types.ConfirmedConsent
    consent=codec.parse_model(cls,raw.encode(),32768)
    if codec.bounded(consent,32768).decode()!=raw:raise ValueError('canonical evidence consent required')
    if preview:
        quote=codec.parse_model(types.EvidenceMethodQuote,value['quote_json'].encode(),16384)
        if digest(canonical({'consent':consent.model_dump(mode='json'),'quote':quote.model_dump(mode='json')}))!=value['consent_digest']:raise ValueError('evidence preview digest differs')
    elif digest(canonical(consent.model_dump(mode='json')))!=value['consent_digest']:raise ValueError('evidence consent digest differs')
    encoded=codec.request_bytes(consent.exact_input)
    codec.decode_request(encoded.raw,consent.domain,consent.exact_input,consent.selection_manifest)
    if preview:
        if (consent.domain.request_digest,consent.research_id,consent.principal_id,consent.input_revision,consent.preview_research_version,consent.quote_digest)!=(value['request_digest'],value['research_id'],value['principal_id'],value['input_revision'],value['research_version'],digest(codec.bounded(quote,16384))):raise ValueError('evidence preview row differs')
    if not preview:
        if consent.quote_digest!=digest(codec.bounded(consent.quote,16384)) or consent.quote.codec_digest!=consent.domain.template_code_digest:raise ValueError('original quote domain differs')
        if codec.task_scope_digest(consent)!=consent.task_outbound_scope_digest or consent.dispatch_id!=value['id'] or consent.task_id!=value['task_id'] or consent.result_ref!=value['result_ref'] or consent.account_id!=value['account_id'] or consent.nonce!=value['nonce']:
            raise ValueError('actual evidence task domain differs')
    return consent


def current_task_binding_in(conn,store,value):
    consent=parse_consent(value)
    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(value['task_id'],)).fetchone()
    if not task:raise not_found()
    control=AuthorizationGate(store).check_task(conn,task)
    step=conn.execute('SELECT * FROM research_steps WHERE id=? AND task_id=?',(consent.step_id,task['id'])).fetchone()
    grant=conn.execute('SELECT * FROM research_grants WHERE id=?',(consent.grant_id,)).fetchone()
    saved=conn.execute('SELECT * FROM research_revisions WHERE research_id=? AND revision=?',(consent.research_id,consent.input_revision)).fetchone()
    if (not saved or digest(canonical(json.loads(saved['problem_json'])))!=saved['digest'] or saved['digest']!=consent.input_digest
            or json.loads(saved['problem_json'])['original_input']!=consent.exact_input.problem_context.summary
            or not step or step['kind']!='phenomenon_plan' or not grant or grant['version']!=consent.grant_version
            or json.loads(grant['scopes'])!=['execute','provider_outbound']
            or (task['policy_revision'],task['principal_id'],task['grant_id'],task['auth_generation'],task['input_revision'],task['input_digest'],task['owner_epoch'],task['acl_epoch'])
            !=('native-plan-v1',consent.principal_id,consent.grant_id,consent.generation,consent.input_revision,consent.input_digest,consent.owner_epoch,consent.acl_epoch)
            or task['execution_mode']!=consent.mode or task['start_version']!=consent.execution_research_version
            or control['version']!=consent.execution_research_version or control['current_revision']!=consent.input_revision):
        raise PermissionError('actual current evidence task binding differs')
    expected=('QUEUED',1,'PENDING',1) if value['state'] in ('approved','reserved') else ('RUNNING',2,'SENDING',2) if value['state']=='consumed' else None
    if expected is None or (task['execution'],task['version'],step['state'],step['version'])!=expected:raise PermissionError('actual evidence task phase differs')
    from . import plan_native_runtime as runtime
    if consent.domain.producer_digest!=runtime.code_digest() or consent.domain.template_code_digest!=codec.code_digest():raise PermissionError('confirmed evidence code changed')
    if consent.quote_digest!=digest(codec.bounded(consent.quote,16384)):raise ValueError('evidence quote digest differs')
    return consent,task,step,control


class _ReadScope(AbstractContextManager):
    __slots__=('conn','store','lease','base','pid','thread','reference','active','kind','identity','source','rid','revision','version','approved_version','consent')
    def __init__(self,conn,store,lease,kind,*,identity=None,source=None,rid=None,revision=None,version=None,approved_version=None,consent=None,_factory=None):
        frame=sys._getframe(1)
        try:
            if _factory is not _FACTORY or frame.f_globals is not globals() or frame.f_code not in {f.__code__ for f in _SCOPE_BUILDERS}:
                raise TypeError('fixed evidence issuer required')
        finally:del frame
        self.conn,self.store,self.lease,self.base=conn,store,lease,_native(conn,store,lease)
        self.pid,self.thread,self.reference,self.active=os.getpid(),threading.get_ident(),object(),True
        self.kind,self.identity,self.source=kind,identity,source
        self.rid,self.revision,self.version,self.approved_version,self.consent=rid,revision,version,approved_version,consent
        _READERS[self.reference]=self
    def __reduce__(self):raise TypeError('evidence read scope cannot be serialized')
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('evidence read scope immutable')
        object.__setattr__(self,name,value)
    def __enter__(self):
        try:self.require();return self
        except BaseException:self.close();raise
    def __exit__(self,*args):self.close()
    def close(self):object.__setattr__(self,'active',False);_READERS.pop(self.reference,None)
    def require(self):
        if not self.active or self.pid!=os.getpid() or self.thread!=threading.get_ident() or _READERS.get(self.reference) is not self or _native(self.conn,self.store,self.lease) is not self.base:
            raise PermissionError('evidence read scope retired')
        if self.kind in ('preview','confirm','history'):
            from .paid_control import require_authenticated_action
            require_authenticated_action(self.source,identity=self.identity,action='evidence-method-read' if self.kind=='history' else 'evidence-method-'+self.kind,research_id=self.rid,task_id=self.consent.result_ref if self.kind=='history' else None)
            control=AuthorizationGate(self.store).check(self.conn,self.identity,self.store_principal(),self.rid,scope='read' if self.kind=='history' else 'write')
            AuthorizationGate(self.store).check(self.conn,self.identity,self.store_principal(),self.rid)
            if self.kind!='history' and (control['version']!=self.version or control['current_revision']!=self.revision):raise ResearchError('REVISION_CONFLICT',409,'问题或研究版本已变化，请重新预览。')
        else:
            value=self.conn.execute('SELECT * FROM research_plan_native_runs WHERE id=?',(self.consent.dispatch_id,)).fetchone()
            actual,_,_,_=current_task_binding_in(self.conn,self.store,value)
            if actual!=self.consent:raise PermissionError('evidence read task changed')
            from . import plan_native
            plan_native.require_purpose(self.store,types.PURPOSE,current=True)
    def store_principal(self):
        row=self.conn.execute('SELECT id FROM research_principals WHERE normalized_email=? AND session_generation=?',(self.identity.email,self.identity.generation)).fetchone()
        if not row:raise not_found()
        return row[0]


class _TaskReadAuthorizer:
    def __init__(self,scope,*,_factory=None):
        if _factory is not _FACTORY or type(scope) is not _ReadScope:raise TypeError('fixed evidence task reader required')
        self.scope=scope
    def __call__(self,conn,context,operation):
        if conn is not self.scope.conn or operation!='read':raise PermissionError('evidence task scope is read only')
        self.scope.require()
        task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(context.task_id,)).fetchone()
        step=conn.execute('SELECT * FROM research_steps WHERE id=? AND task_id=?',(context.step_id,context.task_id)).fetchone()
        if (not task or not step or task['policy_revision']!='d1-source-only-v1'
                or task['research_id']!=self.scope.rid or task['input_revision']!=self.scope.revision
                or task['principal_id']!=self.scope.consent.principal_id):raise PermissionError('same-root source task required')
        fields=('research_id','input_revision','input_digest','principal_id','principal_epoch','owner_epoch','acl_epoch')
        if any(task[k]!=getattr(context,k) for k in fields) or task['attempt']!=context.attempt or task['version']!=context.task_version or step['version']!=context.step_version:
            raise PermissionError('source read context changed')
        # A persistent outbound grant never replaces the current read grant.
        current=conn.execute('SELECT epoch FROM research_principals WHERE id=? AND status=\'active\'',(self.scope.consent.principal_id,)).fetchone()
        grant=conn.execute("SELECT 1 FROM research_grants WHERE principal_id=? AND principal_epoch=? AND research_id=? AND acl_epoch=? AND status='active' AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='read')",(self.scope.consent.principal_id,current[0] if current else -1,self.scope.rid,self.scope.consent.acl_epoch)).fetchone()
        if not grant:raise PermissionError('current source read scope ended')
        return True


def _checked_acquisition_admission(original):
    """Classify missing/erased proof before checking an extant original domain.

    This only validates data; it never authorizes a reader or an execution.
    """
    if original is None:raise LookupError('original Source resource unavailable')
    raw=original['admission_json']
    if raw is None:
        if original['state']!='closed':raise ValueError('invalid Source erasure state')
        raise PermissionError('original Source acquisition proof erased')
    if type(raw) is not str:raise ValueError('original Source admission object required')
    recorded=codec.strict_json(raw.encode('utf-8'),32768)
    encoded=canonical(recorded)
    if type(recorded) is not dict or encoded.decode('utf-8')!=raw or digest(encoded)!=original['admission_digest']:
        raise ValueError('original Source admission integrity differs')


def _selection(conn,store,scope,excerpt_ids,summary,*,identity=None):
    from .evidence_repository import EvidenceRepository
    from .source_integration import authorizer,context_for
    from .source_guard import check_origin
    scope.require()
    pid=scope.store_principal() if identity is not None else scope.consent.principal_id
    control=conn.execute('SELECT * FROM research_controls WHERE id=?',(scope.rid,)).fetchone()
    if identity is not None:
        authorize=authorizer(store,identity=identity)
        generation=identity.generation
    else:
        authorize=_TaskReadAuthorizer(scope,_factory=_FACTORY);generation=scope.consent.generation
    repository=EvidenceRepository(conn,authorize);entries=[];handles=[]
    for index,ref in enumerate(excerpt_ids,1):
        stored=conn.execute("SELECT task_id FROM research_evidence_objects WHERE id=? AND kind='excerpts' AND research_id=? AND input_revision=?",(ref,scope.rid,scope.revision)).fetchone()
        if stored is None:raise LookupError('selected source unavailable')
        original=conn.execute('SELECT * FROM research_source_resources WHERE task_id=?',(stored[0],)).fetchone()
        _checked_acquisition_admission(original)
        # check_origin is the fixed original-domain proof, not the current
        # ACL/licence check below. With a present canonical hashed admission,
        # its rejection denotes corruption, never a permission withdrawal.
        try:check_origin(store,conn,stored[0])
        except PermissionError:raise ValueError('original Source acquisition domain differs') from None
        context=context_for(conn,stored[0])
        details=repository.excerpt_details(context,ref)
        candidate,handle=repository.preview_provider_handle(context,ref,'e'+str(index))
        if len(candidate.title)>300 or len(handle.attribution)>400 or len(candidate.quote)>1000:raise codec.EvidenceMethodLimit('complete selected source field exceeds evidence scope')
        entries.append(types.ManifestEntry(handle=handle.handle,source_id=candidate.source_id,source_revision=candidate.source_revision,excerpt_id=ref,
            source_task_id=context.task_id,attempt=context.attempt,raw_digest=candidate.raw_digest,extracted_digest=candidate.extracted_digest,
            discovery_digest=candidate.discovery_digest,excerpt_payload_digest=details['excerpt_digest'],snapshot_payload_digest=details['snapshot_digest'],
            permission_basis_digest=candidate.permission_basis_digest,start=candidate.start,end=candidate.end,quote_sha256=digest(candidate.quote.encode()),
            title=candidate.title,canonical_url=candidate.canonical_url,attribution=handle.attribution,read_scope=candidate.read_scope,origin=candidate.origin,
            acquired_at=candidate.acquired_at,information_cutoff=candidate.information_cutoff))
        handles.append(types.SelectedHandle(handle=handle.handle,title=candidate.title,attribution=handle.attribution,quote=candidate.quote,read_scope=candidate.read_scope,origin=candidate.origin))
    saved=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(scope.rid,scope.revision)).fetchone()
    manifest=types.SelectionManifest(root=types.ManifestRoot(research_id=scope.rid,input_revision=scope.revision,input_digest=saved[0],approved_research_version=scope.approved_version),
        owner=scope.consent.selection_manifest.owner if scope.kind=='history' else types.ManifestOwner(principal_id=pid,generation_digest=digest(generation.encode()),owner_epoch=control['owner_epoch'],acl_epoch=control['acl_epoch']),entries=tuple(entries))
    exact=types.SelectedEvidenceMethodInput(input_template=types.INPUT_TEMPLATE,purpose=types.PURPOSE,
        problem_context=types.ProblemContext(kind='owner_problem_summary',declaration='self_declared',summary=summary),handles=tuple(handles))
    codec.bounded(manifest,16384);codec.request_bytes(exact)
    return manifest,exact


def read_evidence_http_in(conn,service,owner_lease,identity,request_source,rid,revision,version,excerpt_ids,phase):
    from . import plan_native_runtime as runtime
    from .paid_control import require_authenticated_action
    if phase not in ('preview','confirm') or type(identity) is not AccountIdentity:raise PermissionError('fixed evidence HTTP phase required')
    request,_=_caller((runtime._WRITE_PRODUCERS[0 if phase=='preview' else 1],),conn,owner_lease,service.store)
    expected=types.EvidenceMethodPreviewRequest if phase=='preview' else types.EvidenceMethodConfirmRequest
    if type(request) is not expected:raise PermissionError('actual fixed HTTP evidence request required')
    require_authenticated_action(request_source,identity=identity,action='evidence-method-'+phase,research_id=rid,body_digest=digest(canonical(request.model_dump(mode='json'))))
    saved=conn.execute('SELECT * FROM research_revisions WHERE research_id=? AND revision=?',(rid,revision)).fetchone()
    if not saved:raise not_found()
    problem=json.loads(saved['problem_json'])
    if digest(canonical(problem))!=saved['digest']:raise ValueError('original problem integrity differs')
    if len(problem['original_input'])>1000:raise codec.EvidenceMethodLimit('complete owner problem exceeds selected-input limit')
    if problem['entry']!='phenomenon' or problem['confirmed'] is not True:raise ResearchError('INPUT_INVALID',422,'请先确认当前现象问题。')
    with _ReadScope(conn,service.store,owner_lease,phase,identity=identity,source=request_source,rid=rid,revision=revision,version=version,approved_version=version,_factory=_FACTORY) as scope:
        try:return _selection(conn,service.store,scope,excerpt_ids,problem['original_input'],identity=identity)
        except (PermissionError,LookupError):raise ResearchError('SOURCE_PERMISSION_UNAVAILABLE',409,'选定来源当前不可用于本次外发，请重新选择。') from None


def issue_evidence_task_scope_in(conn,store,owner_lease,dispatch_id,phase):
    from . import plan_native_runtime as runtime
    if phase not in ('balance','reserve','preconsume'):raise PermissionError('fixed evidence task phase required')
    _,actual=_caller(runtime._EVIDENCE_TASK_READ_PRODUCERS,conn,owner_lease,store)
    if actual is not None:
        if phase!='balance' or type(actual) is not runtime.NativeBalanceLease or runtime._CAPS.get(actual.reference) is not actual or not actual.active or actual.used or actual.claim[0]!=dispatch_id:raise PermissionError('actual native balance claim required')
    value=conn.execute('SELECT * FROM research_plan_native_runs WHERE id=?',(dispatch_id,)).fetchone()
    consent,_,_,_=current_task_binding_in(conn,store,value)
    if (phase in ('balance','reserve') and value['state']!='approved') or (phase=='preconsume' and value['state']!='reserved'):raise PermissionError('evidence phase objects differ')
    if phase=='preconsume':validate_admission(value,consent)
    return _ReadScope(conn,store,owner_lease,phase,rid=consent.research_id,revision=consent.input_revision,version=consent.execution_research_version,
        approved_version=consent.preview_research_version,consent=consent,_factory=_FACTORY)


def read_evidence_task_in(conn,scope):
    if type(scope) is not _ReadScope or scope.conn is not conn or scope.kind not in ('balance','reserve','preconsume','send','return'):raise PermissionError('actual evidence task scope required')
    scope.require();consent=scope.consent
    manifest,exact=_selection(conn,scope.store,scope,tuple(e.excerpt_id for e in consent.selection_manifest.entries),consent.exact_input.problem_context.summary)
    if manifest!=consent.selection_manifest or exact!=consent.exact_input:raise PermissionError('confirmed evidence changed')
    encoded=codec.request_bytes(exact);codec.decode_request(encoded.raw,consent.domain,exact,manifest)
    return manifest,exact,encoded


def validate_admission(value,consent):
    if type(value['admission_json']) is not str:raise PermissionError('actual reserved evidence admission required')
    admission=codec.parse_model(types.EvidenceMethodAdmission,value['admission_json'].encode(),65536)
    if (codec.bounded(admission,65536).decode()!=value['admission_json'] or digest(codec.bounded(admission,65536))!=value['admission_digest']
            or admission.domain!=consent.domain or admission.task_outbound_scope_digest!=consent.task_outbound_scope_digest
            or admission.consent_digest!=value['consent_digest'] or admission.quote!=consent.quote
            or admission.mode!=consent.mode or admission.producer!=consent.producer
            or admission.observed_balance.mode!=consent.mode or admission.observed_balance.credential_incarnation!=consent.credential_incarnation
            or admission.ledger_before.id!=consent.account_id or admission.ledger_before.binding_id!=consent.economic_binding
            or (admission.funding_before.balance_claim,admission.funding_before.balance_nonce)!=(consent.dispatch_id,consent.nonce)
            or (admission.funding_before.principal_id,admission.funding_before.generation,admission.funding_before.account_id,admission.funding_before.economic_binding,admission.funding_before.authority_digest,admission.funding_before.grant_epoch,admission.funding_before.credential_incarnation)!=(consent.principal_id,consent.generation,consent.account_id,consent.economic_binding,consent.authority_digest,consent.grant_epoch,consent.credential_incarnation)):raise ValueError('actual evidence admission differs')
    return admission


def read_evidence_send_in(conn,actual_send_lease):
    from . import plan_native_runtime as runtime
    send=actual_send_lease
    if type(send) is not runtime.NativePlanSendLease or runtime._CAPS.get(send.reference) is not send or not send.active or send.used or send.pid!=os.getpid():raise PermissionError('actual evidence send lease required')
    _,actual=_caller(runtime._EVIDENCE_SEND_READ_PRODUCERS,conn,send.lease,send.store)
    if actual is not send:raise PermissionError('same actual send lease required')
    value=conn.execute('SELECT * FROM research_plan_native_runs WHERE id=?',(send.dispatch,)).fetchone()
    consent,_,_,_=current_task_binding_in(conn,send.store,value)
    if value['state']!='consumed':raise PermissionError('independently committed evidence consumption required')
    validate_admission(value,consent)
    with _ReadScope(conn,send.store,send.lease,'send',rid=consent.research_id,revision=consent.input_revision,version=consent.execution_research_version,
        approved_version=consent.preview_research_version,consent=consent,_factory=_FACTORY) as scope:
        return read_evidence_task_in(conn,scope)


def read_evidence_return_in(conn,store,lease,owned,consent):
    from . import plan_native_runtime as runtime,plan_native as ports
    _caller((runtime._WRITE_PRODUCERS[3],),conn,lease,store)
    if type(consent) is not types.ConfirmedConsent:raise PermissionError('fixed original return domain required')
    value=conn.execute('SELECT * FROM research_plan_native_runs WHERE id=?',(consent.dispatch_id,)).fetchone()
    pair=ports.installation(store)
    if not pair:raise PermissionError('original return resource unavailable')
    runtime.require_return(owned,pair[1],consent.dispatch_id,consent.nonce,value['admission_digest'],consent.domain.producer_digest)
    current,_,_,_=current_task_binding_in(conn,store,value)
    if current!=consent:raise PermissionError('current return domain changed')
    with _ReadScope(conn,store,lease,'return',rid=consent.research_id,revision=consent.input_revision,version=consent.execution_research_version,
        approved_version=consent.preview_research_version,consent=consent,_factory=_FACTORY) as scope:
        return read_evidence_task_in(conn,scope)


def return_data(consent,admission,value,owned,usage,candidate,recorded_at,*,body_allowed):
    """Build the bounded financial fallback before attempting any optional body."""
    label=None
    try:
        data=codec.strict_json(owned.body,393216);label=data.get('model') if type(data) is dict else None
    except (ValueError,TypeError,UnicodeError,RecursionError):pass
    if type(label) is not str or len(label)>120 or any(ord(c)<32 or ord(c)>126 for c in label):label=None
    receipt=types.OwnedReturnReceipt(protocol='owned-evidence-method-return-v1',domain=consent.domain,task_outbound_scope_digest=consent.task_outbound_scope_digest,
        dispatch=consent.dispatch_id,nonce=consent.nonce,mode=owned.mode,producer=consent.producer,runtime_digest=admission.funding_before.runtime_digest,
        consent_digest=value['consent_digest'],admission_digest=value['admission_digest'],response_digest=digest(owned.body),status=owned.status,
        provider_model_label=label,weight_identity_verified=False)
    receipt_raw=codec.bounded(receipt,4096)
    def commit_for(result):
        commit=types.EvidenceMethodCommit(protocol='evidence-method-commit-v1',domain=consent.domain,task_outbound_scope_digest=consent.task_outbound_scope_digest,
            task_id=consent.task_id,step_id=consent.step_id,result_ref=consent.result_ref,recorded_at=recorded_at,
            consent_digest=value['consent_digest'],admission_digest=value['admission_digest'],result_digest=None if result is None else digest(codec.bounded(result,32768)),
            receipt_digest=digest(receipt_raw),usage_digest=None if usage is None else digest(canonical(usage)),preview_research_version=consent.preview_research_version,
            execution_research_version=consent.execution_research_version,task_before=2,task_after=3,step_before=2,step_after=3)
        codec.bounded(commit,4096);return commit
    fallback=commit_for(None);result=None;commit=fallback
    if body_allowed and usage is not None and candidate is not None:
        try:
            citations=codec.citations(consent);origins={c.origin for c in citations}
            result=types.OwnedEvidenceMethodPlanResult(protocol='owned-evidence-method-plan-result-v1',domain=consent.domain,
                task_outbound_scope_digest=consent.task_outbound_scope_digest,result_ref=consent.result_ref,task_id=consent.task_id,research_id=consent.research_id,
                input_revision=consent.input_revision,input_digest=consent.input_digest,consent_digest=value['consent_digest'],admission_digest=value['admission_digest'],
                recorded_at=recorded_at,execution_mode=consent.mode,producer=consent.producer,real_model_executed=consent.mode=='native_live',weight_identity_verified=False,
                literature_status='selected_stored_excerpts_only',maturity_status='candidate_unverified',mathematics_status='not_checked',mechanism_status='unverified',
                transfer_status='not_validated',automatically_created_sources=0,source_origin='mixed' if len(origins)>1 else next(iter(origins)),citations=citations,candidate=candidate)
            codec.bounded(result,32768);commit=commit_for(result)
        except (ValueError,TypeError,OverflowError):result=None;commit=fallback
    return (None if result is None else result.model_dump(mode='json'),receipt.model_dump(mode='json'),commit.model_dump(mode='json'))


def capacity_for_confirmed(consent):
    value={k:getattr(consent,k) for k in types.PreviewConsent.model_fields if k!='protocol'}
    return codec.admission_capacity(types.PreviewConsent(protocol='evidence-method-preview-consent-v1',**value),consent.quote)


def preview_consent(identity,manifest,selected,quote,producer_digest):
    return types.PreviewConsent(protocol='evidence-method-preview-consent-v1',domain=codec.content_domain(selected,manifest,producer_digest),
        principal_id=manifest.owner.principal_id,generation=identity.generation,research_id=manifest.root.research_id,
        input_revision=manifest.root.input_revision,input_digest=manifest.root.input_digest,owner_epoch=manifest.owner.owner_epoch,acl_epoch=manifest.owner.acl_epoch,
        preview_research_version=manifest.root.approved_research_version,execution_research_version=manifest.root.approved_research_version+1,
        selection_manifest=manifest,exact_input=selected,quote_digest=digest(codec.bounded(quote,16384)))


def confirmation_data(consent):
    data=dict(task_id=consent.task_id,result_ref=consent.result_ref,input_revision=consent.input_revision,
        execution_research_version=consent.execution_research_version,purpose=types.PURPOSE,selection_manifest_digest=consent.domain.selection_digest,
        request_digest=consent.domain.request_digest,state='queued',funding_state='approved_not_sent',cost_state='unreserved',cash_evidence='not_observed',
        financial_version=9,real_model_executed=False,model_analysis_ran=False,recorded_at=None)
    value=types.EvidenceMethodConfirmResponse.model_validate(envelope(data));codec.bounded(value,4096)
    return value.model_dump(mode='json')


def preview_data(value,consent,quote,*,can_confirm,reason):
    references=[]
    for e in consent.selection_manifest.entries:
        data=e.model_dump(mode='json');data['source_input_revision']=consent.input_revision
        references.append(types.PublicSourceRef.model_validate({k:data[k] for k in types.PublicSourceRef.model_fields}))
    domain=consent.domain
    result=types.EvidenceMethodPreviewResponse.model_validate(envelope(dict(preview_ref=value['id'],preview_digest=value['consent_digest'],research_id=consent.research_id,
        input_revision=consent.input_revision,research_version=consent.preview_research_version,purpose=types.PURPOSE,input_template=types.INPUT_TEMPLATE,candidate_schema=types.CANDIDATE_SCHEMA,
        selection_manifest_digest=domain.selection_digest,selected_input_digest=domain.selected_input_digest,request_digest=domain.request_digest,template_digest=domain.template_digest,
        outbound_scope_digest=domain.outbound_scope_digest,exact_input=consent.exact_input,source_references=tuple(references),quote=quote,approved_upper_units=quote.approved_upper_units,
        expires_at=quote.valid_until,cash_evidence='not_observed',state='awaiting_confirmation' if can_confirm else 'funding_closed',can_confirm=can_confirm,funding_reason=reason,model_analysis_ran=False,real_model_executed=False)))
    codec.bounded(result,32768);return result.model_dump(mode='json')



def metadata(value,current_revision):
    from . import plan_native_runtime as runtime
    consent=parse_consent(value);_stored_result(value,consent);base=runtime.metadata(value)
    actual=False if consent.mode=='controlled_fixture' or value['state'] in ('approved','reserved') or value['state']=='closed' and value['cost_state']=='unreserved' else True if value['result_json'] else None
    data=types.EvidenceMethodMeta(task_id=consent.task_id,result_ref=consent.result_ref,research_id=consent.research_id,input_revision=consent.input_revision,
        input_digest=consent.input_digest,selection_manifest_digest=consent.domain.selection_digest,request_digest=consent.domain.request_digest,purpose=types.PURPOSE,
        state='pending_reconciliation' if value['state'] in ('consumed','unknown','closed') and value['cost_state'] in ('held','unknown') else base['state'],cost_state=value['cost_state'],cleanup_state=value['cleanup_state'],safe_code=value['safe_code'],recorded_at=base['recorded_at'],
        execution_mode=consent.mode,real_model_executed=actual,is_historical=consent.input_revision!=current_revision)
    codec.bounded(data,2048);return data


def _stored_result(value,consent):
    has_return=value['receipt_json'] is not None or value['commit_json'] is not None
    if not has_return:
        if value['result_json'] is not None or value['usage_json'] is not None or value['state']=='returned':raise ValueError('missing original return chain')
        return None
    if type(value['receipt_json']) is not str or type(value['commit_json']) is not str:raise ValueError('complete original return chain required')
    admission=validate_admission(value,consent)
    result=None if value['result_json'] is None else codec.parse_model(types.OwnedEvidenceMethodPlanResult,value['result_json'].encode(),32768)
    receipt=codec.parse_model(types.OwnedReturnReceipt,value['receipt_json'].encode(),4096)
    commit=codec.parse_model(types.EvidenceMethodCommit,value['commit_json'].encode(),4096)
    usage=None if value['usage_json'] is None else codec.strict_json(value['usage_json'].encode(),4096)
    if usage is not None:
        fields={'protocol','financial_version','prompt_tokens','completion_tokens','total_tokens','booked_upper_units','actual_charge_units','currency','scale'}
        if type(usage) is not dict or set(usage)!=fields or (usage['protocol'],usage['financial_version'],usage['booked_upper_units'],usage['actual_charge_units'],usage['currency'],usage['scale'])!=('native-plan-cost-v1',9,2129920,None,'CNY',6):raise ValueError('original usage domain differs')
        a,b,total=usage['prompt_tokens'],usage['completion_tokens'],usage['total_tokens']
        if any(type(n) is not int for n in (a,b,total)) or not 0<=a<=1048576 or not 0<=b<=4096 or total!=a+b:raise ValueError('original usage bounds differ')
    objects=[(receipt,value['receipt_json'],4096),(commit,value['commit_json'],4096)]
    if result is not None:objects.append((result,value['result_json'],32768))
    for obj,raw,cap in objects:
        if codec.bounded(obj,cap).decode()!=raw:raise ValueError('canonical original evidence output required')
    if (any(obj.domain!=consent.domain or obj.task_outbound_scope_digest!=consent.task_outbound_scope_digest
                or obj.consent_digest!=value['consent_digest'] or obj.admission_digest!=value['admission_digest'] for obj,_,_ in objects)
            or receipt.dispatch!=consent.dispatch_id or receipt.nonce!=consent.nonce or receipt.mode!=consent.mode or receipt.producer!=consent.producer
            or receipt.runtime_digest!=admission.funding_before.runtime_digest
            or (commit.task_id,commit.step_id,commit.result_ref)!=(consent.task_id,consent.step_id,consent.result_ref)
            or (commit.preview_research_version,commit.execution_research_version)!=(consent.preview_research_version,consent.execution_research_version)
            or commit.result_digest!=(None if result is None else digest(codec.bounded(result,32768)))
            or commit.receipt_digest!=digest(codec.bounded(receipt,4096)) or commit.usage_digest!=(None if usage is None else digest(canonical(usage)))
            or value['cost_state']!=('unknown' if usage is None else 'upper_booked')):raise ValueError('original evidence output chain differs')
    if result is not None:
        if (usage is None or result.citations!=codec.citations(consent) or result.task_id!=consent.task_id or result.result_ref!=consent.result_ref
                or result.research_id!=consent.research_id or result.input_revision!=consent.input_revision or result.input_digest!=consent.input_digest
                or result.execution_mode!=consent.mode or result.producer!=consent.producer or result.recorded_at!=commit.recorded_at):raise ValueError('original evidence body differs')
        codec.parse_candidate(codec.bounded(result.candidate,16384),consent.exact_input)
    return result


def read(service,identity,rid,ref,source):
    from .paid_control import require_authenticated_action
    require_authenticated_action(source,identity=identity,action='evidence-method-read',research_id=rid,task_id=ref)
    with service.store.transaction() as conn:return read_in(conn,service,identity,rid,ref,source)


def read_in(conn,service,identity,rid,ref,source):
    pid=service._principal(identity);control=service.authorization.check(conn,identity,pid,rid)
    value=conn.execute('SELECT r.* FROM research_plan_native_runs r JOIN research_tasks t ON t.id=r.task_id WHERE r.result_ref=? AND t.research_id=?',(ref,rid)).fetchone()
    if not value or not is_evidence(value):raise not_found()
    consent=parse_consent(value);result=_stored_result(value,consent);state='none';reason=None
    if result is not None:
        task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(consent.task_id,)).fetchone()
        step=conn.execute('SELECT * FROM research_steps WHERE id=?',(consent.step_id,)).fetchone()
        saved=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(rid,consent.input_revision)).fetchone()
        if (not task or not step or not saved or saved[0]!=consent.input_digest or value['state']!='returned'
                or (task['research_id'],task['principal_id'],task['input_revision'],task['input_digest'],task['policy_revision'],task['execution'],task['version'])!=(rid,consent.principal_id,consent.input_revision,consent.input_digest,'native-plan-v1','COMPLETED',3)
                or task['execution_mode']!=consent.mode or task['start_version']!=consent.execution_research_version
                or (step['task_id'],step['kind'],step['state'],step['version'])!=(task['id'],'phenomenon_plan','SUCCEEDED',3)):raise ValueError('original evidence task commit differs')
    if result is not None:
        try:
            with _ReadScope(conn,service.store,None,'history',identity=identity,source=source,rid=rid,revision=consent.input_revision,version=control['version'],
                approved_version=consent.preview_research_version,consent=consent,_factory=_FACTORY) as scope:
                manifest,selected=_selection(conn,service.store,scope,tuple(e.excerpt_id for e in consent.selection_manifest.entries),consent.exact_input.problem_context.summary,identity=identity)
            if manifest!=consent.selection_manifest or selected!=consent.exact_input:raise ValueError('original evidence source proof differs')
            state='available'
        except LookupError:state='unavailable';reason='SOURCE_UNAVAILABLE';result=None
        except PermissionError:state='unavailable';reason='SOURCE_PERMISSION_UNAVAILABLE';result=None
        except ResearchError as error:
            if error.code not in ('NOT_FOUND','SOURCE_PERMISSION_UNAVAILABLE'):raise
            state='unavailable';reason='SOURCE_UNAVAILABLE' if error.code=='NOT_FOUND' else 'SOURCE_PERMISSION_UNAVAILABLE';result=None
    response=types.EvidenceMethodReadResponse.model_validate(envelope(dict(metadata=metadata(value,control['current_revision']),content_state=state,unavailable_reason=reason,content=result)))
    codec.bounded(response,49152);return response.model_dump(mode='json')


def list_query(items):
    if len(items)!=len(dict(items)) or any(k not in ('limit','cursor') for k,v in items):raise ResearchError('INPUT_INVALID',422,'列表参数不符合要求。')
    data=dict(items);raw=data.get('limit','20')
    if raw not in tuple(str(i) for i in range(1,21)):raise ResearchError('INPUT_INVALID',422,'列表数量须为1至20。')
    cursor=data.get('cursor')
    if cursor is not None:
        import re
        if type(cursor) is not str or not 1<=len(cursor)<=2048 or re.fullmatch('[A-Za-z0-9_-]+',cursor) is None:raise ResearchError('INPUT_INVALID',422,'列表位置不符合要求。')
    return int(raw),cursor


def list_results(service,identity,rid,limit,cursor,source):
    from .paid_control import require_authenticated_action
    require_authenticated_action(source,identity=identity,action='evidence-method-list',research_id=rid,body_digest=digest(canonical({'limit':limit,'cursor':cursor})))
    if type(limit) is not int or not 1<=limit<=20:raise ResearchError('INPUT_INVALID',422,'列表数量须为1至20。')
    with service.store.transaction() as conn:
        pid=service._principal_in(conn,identity);control=service.authorization.check(conn,identity,pid,rid)
        binding=dict(principal_id=pid,generation_digest=digest(identity.generation.encode()),research_id=rid,research_version=control['version'])
        where=" FROM research_plan_native_runs r JOIN research_tasks t ON t.id=r.task_id WHERE t.research_id=? AND json_extract(r.consent_json,'$.protocol')='evidence-method-consent-v1'"
        order="coalesce(json_extract(r.commit_json,'$.recorded_at'),t.created_at)"
        anchor=None
        if cursor is not None:
            try:
                if type(cursor) is not str or not 1<=len(cursor)<=2048:raise ValueError('cursor bound')
                raw=base64.urlsafe_b64decode(cursor+'='*((-len(cursor))%4));data=codec.strict_json(raw,1536)
                if type(data) is not dict or set(data)!={*binding,'at','ref'} or any(data[k]!=v for k,v in binding.items()) or type(data['at']) is not str or type(data['ref']) is not str:raise ValueError('cursor binding')
                if base64.urlsafe_b64encode(codec.bounded(data,1536)).decode().rstrip('=')!=cursor:raise ValueError('cursor canonical')
                actual=conn.execute('SELECT '+order+' AS ordered_at'+where+' AND r.result_ref=?',(rid,data['ref'])).fetchone()
                if not actual or actual['ordered_at']!=data['at']:raise ValueError('cursor actual anchor')
                anchor=(data['at'],data['ref'])
            except (ValueError,TypeError,UnicodeError):raise ResearchError('INPUT_INVALID',422,'列表位置已变化，请从首页重新读取。') from None
        query='SELECT r.*,t.created_at AS task_created,'+order+' AS ordered_at'+where;args=[rid]
        if anchor is not None:query+=' AND ('+order+',r.result_ref)<(?,?)';args.extend(anchor)
        query+=' ORDER BY '+order+' DESC,r.result_ref DESC LIMIT ?';args.append(limit+1)
        values=conn.execute(query,args).fetchall();items=[metadata(value,control['current_revision']) for value in values[:limit]]
        next_cursor=None
        if len(values)>limit:
            last=values[limit-1];next_cursor=base64.urlsafe_b64encode(codec.bounded({**binding,'at':last['ordered_at'],'ref':last['result_ref']},1536)).decode().rstrip('=')
        response=types.EvidenceMethodListResponse.model_validate(envelope(dict(items=items,next_cursor=next_cursor)))
        codec.bounded(response,49152);return response.model_dump(mode='json')


_SCOPE_BUILDERS=(read_evidence_http_in,issue_evidence_task_scope_in,read_evidence_send_in,read_evidence_return_in,read_in)
