"""Owned LOOPBACK probe reception, never financial authority or paid dispatch.

Production registration/send are intentionally unavailable until all budget
writers are wired. Probe preconditions are synthetic and explicitly labelled.
"""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from .authorization import AuthorizationGate,AccountIdentity,OwnerGateLease
from .paid_control import _current_scope
from .paid_approval import _checked,packet_authority
from .provider_evidence import read_confirmed_provider_packet
from .provider_adapter import OfflineOwnedTransport,prepare_request,final_request_bytes
from .provider_schemas import CallPermit,UsageUpperQuote,BudgetBasisSnapshot,Money,OfflineTransportReturn,canonical,digest,MODEL,DECLARED_VERSION
from .errors import ResearchError

_FACTORY=object()
_OWNED={}


def _now():return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


@dataclass(frozen=True)
class FinancialReturnBinding:
    session_id:str
    approval_ref:str
    approval_digest:str
    account_id:str
    economic_binding:str
    currency:str
    scale:int
    funding_epoch:int
    reservation_id:str
    reservation_version:int
    permit_id:str
    dispatch_id:str
    authorized_task_version:int
    authorized_step_version:int
    task_id:str
    step_id:str
    request_digest:str
    evidence_digest:str
    context_digest:str
    quote_digest:str
    quote_revision:str
    basis_digest:str
    admitted_at:int
    attempt:int
    context_bound:int
    output_bound:int
    reserved_upper:int
    requested_model:str=MODEL
    declared_model_version:str=DECLARED_VERSION
    accounting_policy:str='bounded_usage_upper_v2'
    execution_mode:str='offline_probe'
    producer_version:str='owned-loopback-return-v1'


def _financial_facts(conn,binding):
    row=conn.execute("""SELECT r.*,p.id AS permit_id,p.dispatch_id,p.state AS permit_state,p.request_digest,p.evidence_digest,
        p.authorization_context_digest,p.price_digest,p.budget_basis_digest,p.authorized_task_version,p.authorized_step_version,
        p.admitted_at,p.paid_approval_ref,p.policy_revision AS permit_policy,
        a.binding_id,a.currency,a.scale,q.quote_digest,q.policy_revision AS quote_policy,ap.payload_digest AS approval_digest
        FROM research_reservations r JOIN research_dispatch_permits p ON p.reservation_id=r.id
        JOIN research_funding_accounts a ON a.id=r.account_id JOIN research_price_revisions q ON q.id=r.price_revision
        JOIN research_paid_approvals ap ON ap.id=p.paid_approval_ref
        WHERE p.id=? AND r.id=?""",(binding.permit_id,binding.reservation_id)).fetchone()
    if (not row or row['permit_state']!='consumed' or row['status'] not in ('SENT','UNKNOWN')
            or row['permit_policy']!=binding.accounting_policy or row['policy_revision']!=binding.accounting_policy
            or row['quote_policy']!=binding.accounting_policy or row['version']<binding.reservation_version):raise PermissionError('consumed financial binding unavailable')
    checks={'account_id':binding.account_id,'funding_epoch':binding.funding_epoch,'permit_id':binding.permit_id,
        'dispatch_id':binding.dispatch_id,'authorized_task_version':binding.authorized_task_version,
        'authorized_step_version':binding.authorized_step_version,'task_id':binding.task_id,'step_id':binding.step_id,
        'request_digest':binding.request_digest,'evidence_digest':binding.evidence_digest,
        'authorization_context_digest':binding.context_digest,'price_digest':binding.quote_digest,
        'quote_digest':binding.quote_digest,'price_revision':binding.quote_revision,'budget_basis_digest':binding.basis_digest,
        'admitted_at':binding.admitted_at,'paid_approval_ref':binding.approval_ref,'binding_id':binding.economic_binding,
        'currency':binding.currency,'scale':binding.scale,'approval_digest':binding.approval_digest,'max_cost':binding.reserved_upper}
    if any(row[key]!=value for key,value in checks.items()):raise PermissionError('financial binding changed')
    return row


def _send_versions(conn,binding,task):
    step=conn.execute('SELECT * FROM research_steps WHERE id=?',(binding.step_id,)).fetchone()
    if (task['id']!=binding.task_id or task['version']!=binding.authorized_task_version
            or not step or step['task_id']!=task['id'] or step['kind']!='model_report'
            or step['version']!=binding.authorized_step_version):
        raise PermissionError('consumed probe task versions changed')


def _approved_send_facts(conn,approval,payload,context,permit_id,prepared):
    """Compare consumed rows with the independently checked original approval.

    This validates synthetic preconditions; it does not implement consumption
    or turn a legal timestamp into proof of a real financial event.
    """
    funding=payload['funding']
    quote=UsageUpperQuote.model_validate(funding['quote'])
    basis=BudgetBasisSnapshot.model_validate(funding['basis'])
    upper=Money.model_validate(funding['approved_upper'])
    permit=conn.execute('SELECT * FROM research_dispatch_permits WHERE id=?',(permit_id,)).fetchone()
    reservation=conn.execute('SELECT * FROM research_reservations WHERE id=?',(permit['reservation_id'],)).fetchone() if permit else None
    account=conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(approval['account_id'],)).fetchone()
    if not permit or not reservation or not account:raise PermissionError('approved consumed probe preconditions required')
    scope=digest(canonical({'context':context.model_dump(),'approval_ref':approval['id'],'generation':payload['generation']}))
    outbound=digest(canonical({'method':'POST','target':'https://api.deepseek.com/chat/completions','body_digest':prepared.request_digest}))
    admitted=permit['admitted_at']
    if (funding['account_id']!=approval['account_id'] or basis.account_id!=approval['account_id']
            or reservation['account_id']!=approval['account_id'] or account['id']!=funding['account_id']
            or funding['binding_id']!=basis.provider_binding_id or account['binding_id']!=basis.provider_binding_id
            or funding['funding_epoch']!=basis.funding_epoch or account['funding_epoch']!=basis.funding_epoch
            or reservation['funding_epoch']!=basis.funding_epoch or reservation['max_cost']!=upper.amount_units
            or upper.currency!=quote.currency or upper.scale!=quote.scale or account['currency']!=upper.currency
            or account['scale']!=upper.scale or basis.cap.currency!=upper.currency or basis.cap.scale!=upper.scale
            or reservation['price_revision']!=quote.revision or basis.price_revision!=quote.revision
            or permit['price_digest']!=digest(canonical(funding['quote'])) or permit['budget_basis_digest']!=digest(canonical(funding['basis']))
            or permit['paid_approval_ref']!=approval['id'] or reservation['task_id']!=context.task_id
            or reservation['principal_id']!=context.principal_id or reservation['auth_scope_digest']!=scope
            or reservation['outbound_fingerprint']!=outbound or permit['input_digest']!=context.input_digest
            or permit['authorization_context_digest']!=digest(canonical(context.model_dump()))
            or permit['request_digest']!=prepared.request_digest or permit['evidence_digest']!=prepared.evidence_digest
            or type(admitted) is not int or not 0<admitted<=int(time.time())
            or admitted<approval['confirmed_at'] or admitted>=min(quote.valid_until,basis.valid_until,approval['expires_at'])):
        raise PermissionError('consumed probe differs from approved financial facts')
    return permit,reservation,account,quote,basis,upper


class OwnedReturnReceipt:
    __slots__=('_session','_binding','_value','_received_at','_pid')
    def __init__(self,session,value,*,_factory=None):
        if _factory is not _FACTORY or _OWNED.get(session.id) is not session or type(value) is not OfflineTransportReturn:
            raise TypeError('actual owned receiver required')
        self._session,self._binding,self._value=session,session.binding,value
        self._received_at,self._pid=_now(),os.getpid()
    def __reduce__(self):raise TypeError('owned receipts cannot be serialized')
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('owned receipt immutable')
        object.__setattr__(self,name,value)


class OwnedProviderSession:
    """No constructor from DTO and no production registration implementation."""
    __slots__=('store','identity','pid','id','_receipt','_closed','binding','packet','transport','connection','_received_value','_received_digest')
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('owned resource binding immutable')
        object.__setattr__(self,name,value)
    def __init__(self,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('owned server factory required')
    def __reduce__(self):raise TypeError('owned session cannot cross process')
    @classmethod
    def register(cls,*args,**kwargs):
        raise ResearchError('FEATURE_UNAVAILABLE',503,'生产消费／发送链尚未接齐。')

    @classmethod
    def offline_probe(cls,store,identity,lease,approval_ref,permit_id,*,connection_factory,seconds=5):
        from .store import ResearchStore
        if cls is not OwnedProviderSession or type(store) is not ResearchStore or type(identity) is not AccountIdentity or type(lease) is not OwnerGateLease:
            raise PermissionError('actual canonical offline owner context required')
        obj=cls(_factory=_FACTORY);obj.store,obj.identity,obj.pid=store,identity,os.getpid()
        obj.id,obj._receipt,obj._closed=str(uuid4()),None,False
        obj._received_value,obj._received_digest=None,None
        with store.transaction(write=True) as conn:
            row,payload,context,task=_checked(conn,store,identity,lease,approval_ref)
            consent=packet_authority(conn,store,identity,lease,approval_ref)
            packet=read_confirmed_provider_packet(conn,store,identity,consent)
            prepared=prepare_request(payload['summary'],packet);final_request_bytes(prepared)
            permit,reservation,account,q,basis,upper=_approved_send_facts(conn,row,payload,context,permit_id,prepared)
            obj.binding=FinancialReturnBinding(obj.id,approval_ref,row['payload_digest'],basis.account_id,basis.provider_binding_id,upper.currency,upper.scale,basis.funding_epoch,
                reservation['id'],reservation['version'],permit_id,permit['dispatch_id'],permit['authorized_task_version'],permit['authorized_step_version'],task['id'],permit['step_id'],
                prepared.request_digest,prepared.evidence_digest,digest(canonical(packet.context.model_dump())),digest(canonical(q.model_dump())),q.revision,digest(canonical(payload['funding']['basis'])),permit['admitted_at'],
                packet.context.attempt,q.context_bound,q.output_bound,upper.amount_units)
            _financial_facts(conn,obj.binding)
            _send_versions(conn,obj.binding,task)
            if prepared.request_digest!=payload['request_digest'] or prepared.evidence_digest!=payload['evidence_digest']:
                raise PermissionError('approved packet changed')
            if permit['gate_identity_json']!=canonical(lease.identity).decode():raise PermissionError('probe lease binding mismatch')
            ticket=CallPermit(id=permit_id,account_id=account['id'],provider_binding_id=account['binding_id'],funding_epoch=reservation['funding_epoch'],dispatch_id=permit['dispatch_id'],
                reservation_id=reservation['id'],context=packet.context,request_digest=prepared.request_digest,evidence_digest=prepared.evidence_digest,price_digest=permit['price_digest'],
                price_revision=q.revision,budget_basis_digest=permit['budget_basis_digest'],gate_identity=lease.identity,expires_at=min(q.valid_until,payload['funding']['basis']['valid_until']))
            conn.execute("INSERT INTO research_provider_sessions(id,approval_id,dispatch_id,permit_id,mode,binding_digest,state) VALUES(?,?,?,?,'offline_probe',?,'created')",(obj.id,approval_ref,permit['dispatch_id'],permit_id,digest(canonical(asdict(obj.binding)))))
        obj.packet,obj.transport=packet,OfflineOwnedTransport(connection_factory)
        obj.connection=None
        try:
            object.__setattr__(obj,'connection',obj.transport.preconnect(prepared,q,seconds=seconds))
            with store.transaction(write=True) as conn:
                row,payload,context,task=_checked(conn,store,identity,lease,approval_ref)
                _approved_send_facts(conn,row,payload,context,permit_id,prepared)
                _financial_facts(conn,obj.binding);_send_versions(conn,obj.binding,task)
                if conn.execute("UPDATE research_provider_sessions SET state='sent',version=version+1 WHERE id=? AND state='created' AND version=1",(obj.id,)).rowcount!=1:raise PermissionError('session already started')
            obj.transport.begin(obj.connection,lease=lease,permit=ticket)
            _OWNED[obj.id]=obj
            return obj
        except Exception:
            if obj.connection is not None:obj.connection.close()
            with store.transaction(write=True) as conn:conn.execute("UPDATE research_provider_sessions SET state='unknown',version=version+1 WHERE id=?",(obj.id,))
            raise

    def _current_content(self,conn):
        try:
            gate=AuthorizationGate(self.store)
            task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(self.binding.task_id,)).fetchone()
            if not task:return False
            gate.check_task(conn,task)
            grant=conn.execute('SELECT * FROM research_grants WHERE id=?',(self.packet.context.grant_id,)).fetchone()
            approval=conn.execute('SELECT * FROM research_paid_approvals WHERE id=?',(self.binding.approval_ref,)).fetchone()
            if (not grant or grant['version']!=self.packet.context.grant_epoch or 'execute_paid' not in json.loads(grant['scopes'])
                    or grant['funding_account_id']!=self.binding.account_id or not approval or approval['state'] not in ('confirmed','consumed')
                    or approval['grant_id']!=grant['id'] or grant['funding_permission_ref']!=approval['funding_source_ref']):return False
            research=gate.check(conn,self.identity,self.packet.context.principal_id,self.packet.context.research_id)
            if research['current_revision']!=self.packet.context.input_revision:return False
            from .evidence_repository import EvidenceRepository
            from .source_integration import authorizer,context_for
            repository=EvidenceRepository(conn,authorizer(self.store,identity=self.identity))
            for handle in self.packet.handles:
                row=conn.execute("SELECT task_id FROM research_evidence_objects WHERE id=? AND kind='excerpts'",(handle.excerpt_id,)).fetchone()
                if not row:return False
                candidate=repository.provider_eligibility(context_for(conn,row[0]),handle.excerpt_id)
                if candidate.extracted_digest!=handle.extracted_digest or candidate.quote!=handle.quote:return False
            return True
        except (ResearchError,PermissionError,ValueError,LookupError,TypeError):return False

    def receive(self):
        if self.pid!=os.getpid() or _OWNED.get(self.id) is not self or self._closed or self._receipt is not None:
            raise PermissionError('active owned receiver required')
        def current(context,evidence):
            with self.store.transaction() as conn:
                if not self._current_content(conn):raise PermissionError('content ended')
            return self.packet
        try:value=OfflineOwnedTransport.finish(self.transport,self.connection,current_authorizer=current)
        except Exception:
            self.close()
            raise
        if value.dispatch_id!=self.binding.dispatch_id or value.request_digest!=self.binding.request_digest or value.evidence_digest!=self.binding.evidence_digest:
            raise PermissionError('owned returned binding changed')
        object.__setattr__(self,'_received_value',value)
        object.__setattr__(self,'_received_digest',digest(canonical(value.model_dump())))
        object.__setattr__(self,'_receipt',OwnedReturnReceipt(self,value,_factory=_FACTORY))
        return self._receipt

    def close(self):
        if not self._closed:
            object.__setattr__(self,'_closed',True);_OWNED.pop(self.id,None)
            if self.connection is not None:self.connection.close()
            with self.store.transaction(write=True) as conn:
                conn.execute("UPDATE research_provider_sessions SET state='unknown',version=version+1 WHERE id=? AND financial_return_json IS NULL AND state IN ('created','sent')",(self.id,))
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def persist_owned_return(conn,receipt):
    """Offline source persistence only: no held/upper/account/task mutation."""
    _current_scope(conn)
    if type(receipt) is not OwnedReturnReceipt or receipt._pid!=os.getpid():raise PermissionError('actual owned receipt required')
    owner=receipt._session
    if owner._receipt is not receipt or _OWNED.get(owner.id) is not owner or owner.pid!=os.getpid():raise PermissionError('receipt source retired')
    database=next((r[2] for r in conn.execute('PRAGMA database_list') if r[1]=='main'),None)
    if not database or Path(database).resolve()!=owner.store.path:raise PermissionError('canonical return database required')
    binding=receipt._binding
    if binding!=owner.binding:raise PermissionError('owned receipt binding changed')
    _financial_facts(conn,binding)
    session=conn.execute('SELECT * FROM research_provider_sessions WHERE id=?',(owner.id,)).fetchone()
    if (not session or session['mode']!='offline_probe' or session['binding_digest']!=digest(canonical(asdict(binding)))
            or session['approval_id']!=binding.approval_ref or session['dispatch_id']!=binding.dispatch_id
            or session['permit_id']!=binding.permit_id):raise PermissionError('persistent session binding mismatch')
    value=receipt._value
    if value is not owner._received_value or digest(canonical(value.model_dump()))!=owner._received_digest:
        raise PermissionError('returned DTO is not the owned reception')
    financial={'binding':asdict(binding),'transport':value.model_dump(exclude={'candidate','context'}),'actual_charge':None,
        'execution_mode':'offline_probe','model_analysis_ran':False,'financial_consumer_enabled':False,'received_at':receipt._received_at}
    raw=canonical(financial).decode();stamp=digest(raw.encode())
    if len(raw.encode())>16384:raise ValueError('bounded offline financial provenance required')
    if session['financial_return_json'] is not None:
        if session['return_digest']!=stamp or session['financial_return_json']!=raw:raise PermissionError('immutable received return conflict')
        if not owner._current_content(conn):
            conn.execute('UPDATE research_provider_sessions SET candidate_json=NULL WHERE id=? AND candidate_json IS NOT NULL',(owner.id,))
        return {'return_ref':owner.id,'digest':stamp,'execution_mode':'offline_probe','financial_consumer_enabled':False}
    candidate=value.candidate if owner._current_content(conn) else None
    state='received' if value.usage is not None else 'unknown'
    if conn.execute("UPDATE research_provider_sessions SET state=?,version=version+1,financial_return_json=?,return_digest=?,received_at=?,candidate_json=? WHERE id=? AND financial_return_json IS NULL AND state='sent' AND version=2",(state,raw,stamp,receipt._received_at,candidate,owner.id)).rowcount!=1:
        raise PermissionError('return CAS changed')
    return {'return_ref':owner.id,'digest':stamp,'execution_mode':'offline_probe','financial_consumer_enabled':False}


# Additive B producer. The reviewed A probe above deliberately remains a
# transport-only source with synthetic preconditions and cannot issue B facts.
_B_FACTORY=object()
_B_SESSIONS={}


@dataclass(frozen=True)
class _BudgetContentBinding:
    task_id:str
    approval_ref:str
    account_id:str


class BudgetOwnedReceipt:
    __slots__=('_owner','_value','_digest','_time','_pid')
    def __init__(self,owner,value,*,_factory=None):
        if _factory is not _B_FACTORY or _B_SESSIONS.get(owner.id) is not owner or owner._received is not value:
            raise TypeError('actual budgeted owned finish required')
        self._owner,self._value,self._digest,self._time,self._pid=owner,value,digest(canonical(value.model_dump())),_now(),os.getpid()
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('owned receipt immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('receipts cannot cross processes')


class BudgetedOwnedSession:
    """Owns reserve/preconnect/consume/commit proof/begin/finish; loopback only."""
    __slots__=('store','identity','pid','id','packet','binding','transport','connection','proof','admission','snapshot',
        '_received','_receipt','_closed','_commit_verified')
    def __init__(self,*,_factory=None):
        if _factory is not _B_FACTORY:raise TypeError('budgeted server factory required')
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('budgeted resource binding immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('budgeted resources cannot be serialized')

    @classmethod
    def offline_start(cls,store,identity,source,approval_ref,*,connection_factory,seconds=5):
        from . import paid_budget as ledger
        from .financial_guard import OfflineProjectRegistration
        from .store import ResearchStore
        if cls is not BudgetedOwnedSession:raise TypeError('fixed budgeted producer required')
        if type(store) is not ResearchStore or type(identity) is not AccountIdentity or type(source) is not OfflineProjectRegistration:
            raise PermissionError('configured offline budget context required')
        obj=cls(_factory=_B_FACTORY);obj.store,obj.identity,obj.pid=store,identity,os.getpid()
        obj._received,obj._receipt,obj._closed,obj._commit_verified=None,None,False,False
        obj.connection=None
        proof=None
        try:
            with AuthorizationGate(store).owner_gate(source._principal) as lease:
                with store.transaction(write=True) as conn:
                    ledger.activate_offline_in(conn,store=store,actor=identity,lease=lease,source=source)
                    proof=ledger.reserve_in(conn,store=store,actor=identity,lease=lease,source=source,approval_ref=approval_ref)
                obj.proof,obj.id,obj.packet=proof,proof.session,proof.prepared.packet
                obj.binding=_BudgetContentBinding(proof.prepared.packet.context.task_id,approval_ref,proof.basis.account_id)
                obj.transport=OfflineOwnedTransport(connection_factory)
                object.__setattr__(obj,'connection',obj.transport.preconnect(proof.prepared,source._funding._quote,seconds=seconds))
                with store.transaction(write=True) as conn:
                    admission,snapshot=ledger.consume_in(conn,proof,lease)
                # A distinct connection sees only committed DB facts. An ack
                # exception above never reaches begin, even after real commit.
                with store.transaction() as conn:
                    saved=conn.execute('SELECT snapshot_digest FROM research_financial_admissions WHERE id=? AND session_id=?',(admission,obj.id)).fetchone()
                    ticket=conn.execute('SELECT state FROM research_dispatch_permits WHERE id=?',(proof.permit,)).fetchone()
                    if not saved or saved[0]!=digest(canonical(snapshot.model_dump())) or not ticket or ticket[0]!='consumed':
                        raise PermissionError('budget consumption commit not visible')
                obj.admission,obj.snapshot=admission,snapshot
                object.__setattr__(obj,'_commit_verified',True)
                permit=CallPermit(id=proof.permit,account_id=snapshot.project.account_id,provider_binding_id=snapshot.project.economic_binding,
                    funding_epoch=snapshot.project.funding_epoch,dispatch_id=proof.dispatch,reservation_id=proof.reservation,
                    context=proof.prepared.packet.context,request_digest=snapshot.dispatch.request_digest,evidence_digest=snapshot.dispatch.evidence_digest,
                    price_digest=snapshot.quote_digest,price_revision=snapshot.quote.revision,budget_basis_digest=snapshot.basis_digest,
                    gate_identity=lease.identity,expires_at=min(snapshot.quote.valid_until,snapshot.basis.valid_until))
                if not obj._commit_verified:raise PermissionError('confirmed budget commit required')
                obj.transport.begin(obj.connection,lease=lease,permit=permit)
            _B_SESSIONS[obj.id]=obj
            return obj
        except Exception:
            if obj.connection is not None:obj.connection.close()
            if proof is not None:
                with AuthorizationGate(store).owner_gate(source._principal) as recovery_lease,store.transaction(write=True) as conn:
                    ledger.unknown_in(conn,proof.reservation,store=store,lease=recovery_lease)
                    ledger._write(conn,recovery_lease,'unknown-row',proof.session,'research_provider_sessions',proof.session,
                        "UPDATE research_provider_sessions SET state='unknown',version=version+1 WHERE id=? AND financial_return_json IS NULL",(proof.session,))
            raise
        finally:
            if proof is not None:
                ledger._PREPARED.pop(proof.session,None)
                object.__setattr__(proof,'_active',False)

    def _current_content(self,conn):return OwnedProviderSession._current_content(self,conn)

    def receive(self):
        if self.pid!=os.getpid() or self._closed or _B_SESSIONS.get(self.id) is not self or self._receipt is not None:
            raise PermissionError('actual budgeted owned receiver required')
        def current(context,evidence):
            with self.store.transaction() as conn:
                if not self._current_content(conn):raise PermissionError('content authorization ended')
            return self.packet
        value=OfflineOwnedTransport.finish(self.transport,self.connection,current_authorizer=current)
        if (value.dispatch_id!=self.snapshot.dispatch.dispatch_id or value.request_digest!=self.snapshot.dispatch.request_digest
                or value.evidence_digest!=self.snapshot.dispatch.evidence_digest):raise PermissionError('owned return binding changed')
        object.__setattr__(self,'_received',value)
        object.__setattr__(self,'_receipt',BudgetOwnedReceipt(self,value,_factory=_B_FACTORY))
        return self._receipt

    def close(self):
        if not self._closed:
            object.__setattr__(self,'_closed',True);_B_SESSIONS.pop(self.id,None)
            if self.connection is not None:self.connection.close()
            from .paid_budget import unknown_in
            with AuthorizationGate(self.store).owner_gate(self.snapshot.actor.principal_id) as lease,self.store.transaction(write=True) as conn:
                if conn.execute('SELECT financial_return_json FROM research_provider_sessions WHERE id=?',(self.id,)).fetchone()[0] is None:
                    unknown_in(conn,self.proof.reservation,store=self.store,lease=lease)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def persist_budget_return(conn,*,store,lease,receipt):
    from . import paid_budget as ledger
    _current_scope(conn)
    if type(receipt) is not BudgetOwnedReceipt or receipt._pid!=os.getpid():raise PermissionError('actual owned budget receipt required')
    owner=receipt._owner
    if (_B_SESSIONS.get(owner.id) is not owner or owner._receipt is not receipt or owner.store is not store
            or owner._received is not receipt._value or receipt._digest!=digest(canonical(receipt._value.model_dump()))):
        raise PermissionError('owned budget provenance retired or changed')
    admission,snapshot,project,r,p,s=ledger._load_admission(conn,store,lease,owner.id)
    data={'record_version':ledger.PRODUCER,'admission_ref':admission['id'],'admission_digest':admission['snapshot_digest'],
        'transport':receipt._value.model_dump(exclude={'candidate','context'}),'received_at':receipt._time,
        'execution_mode':'offline_probe','model_analysis_ran':False,'actual_charge':None}
    raw=canonical(data).decode();stamp=digest(raw.encode())
    if len(raw.encode())>16384:raise ValueError('bounded financial return required')
    allowed=owner._current_content(conn)
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (9,10) and s['body_origin_state']!='legacy_unproved':
        from .method_result import receipt_body_scope,receipt_scope
        values,decision=receipt_body_scope(conn,store=store,lease=lease,receipt=receipt,raw=raw,return_digest=stamp)
        if s['financial_return_json'] is not None:
            if s['financial_return_json']!=raw or s['return_digest']!=stamp:raise PermissionError('immutable budget return conflict')
            if values is not None:
                with receipt_scope(conn,store=store,lease=lease,receipt=receipt,values=values,decision=decision):
                    conn.execute("UPDATE research_provider_sessions SET candidate_json=NULL,body_origin_state='closed',body_candidate_digest=NULL,body_envelope_digest=NULL,method_commit_json=NULL WHERE id=?",(owner.id,))
            return owner.id
        state='received' if receipt._value.usage is not None else 'unknown'
        with receipt_scope(conn,store=store,lease=lease,receipt=receipt,values=values,decision=decision):
            if ledger._write(conn,lease,'return',owner.id,'research_provider_sessions',owner.id,
                    "UPDATE research_provider_sessions SET state=?,version=version+1,financial_return_json=?,return_digest=?,received_at=?,candidate_json=?,body_origin_state=?,body_candidate_digest=?,body_envelope_digest=?,method_commit_json=? WHERE id=? AND version=? AND financial_return_json IS NULL AND state IN ('consumed','unknown')",
                    (state,raw,stamp,receipt._time,values['candidate_json'],values['body_origin_state'],values['body_candidate_digest'],values['body_envelope_digest'],values['method_commit_json'],owner.id,s['version'])).rowcount!=1:
                raise PermissionError('budget body/financial return CAS failed')
        return owner.id
    if s['financial_return_json'] is not None:
        if s['financial_return_json']!=raw or s['return_digest']!=stamp:raise PermissionError('immutable budget return conflict')
        if not allowed:conn.execute('UPDATE research_provider_sessions SET candidate_json=NULL WHERE id=?',(owner.id,))
        return owner.id
    candidate=receipt._value.candidate if allowed else None
    state='received' if receipt._value.usage is not None else 'unknown'
    if ledger._write(conn,lease,'return',owner.id,'research_provider_sessions',owner.id,
            "UPDATE research_provider_sessions SET state=?,version=version+1,financial_return_json=?,return_digest=?,received_at=?,candidate_json=? WHERE id=? AND version=? AND financial_return_json IS NULL AND state IN ('consumed','unknown')",
            (state,raw,stamp,receipt._time,candidate,owner.id,s['version'])).rowcount!=1:raise PermissionError('budget return CAS failed')
    return owner.id
