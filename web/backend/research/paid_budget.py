"""One offline v2 ledger owner. No public runner, loader or real funding."""
from dataclasses import dataclass
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time
from typing import Literal
from uuid import uuid4
from pydantic import create_model

from .authorization import AuthorizationGate
from .errors import ResearchError
from .financial_admission_schemas import FinancialAdmissionSnapshot,validate_snapshot_json
from .financial_guard import (OfflineProjectRegistration,_SOURCES,register_closed_project,_financial_write_scope)
from .paid_control import (_FACTORY,_current_scope,_owner_binding,FinancialWriteAuthority,FinancialWriteBinding,
    mint_current_paid_authority,mint_stop_authority,mint_cost_from_return,TrustedCostAuthority)
from .paid_approval import _checked,packet_authority
from .provider_evidence import read_confirmed_provider_packet
from .provider_adapter import prepare_request,final_request_bytes
from .provider_schemas import (DTO,Id,Digest,Money,UsageObservation,UsageUpperQuote,BudgetBasisSnapshot,
    canonical,digest,strict_json,MODEL)
from .usage_upper import reserve_bound,observed_bound

POLICY='bounded_usage_upper_v2'
PRODUCER='owned-budget-offline-v1'
_PREPARED={}
_PREP_FACTORY=object()
from .provider_schemas import OfflineTransportReturn
_FinancialTransport=create_model('FinancialTransport',__base__=DTO,**{
    name:(field.rebuild_annotation(),... if field.is_required() else field.default)
    for name,field in OfflineTransportReturn.model_fields.items() if name not in ('context','candidate')})


def stamp():return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
def uid():return str(uuid4())
def _row(conn,table,key):return conn.execute('SELECT * FROM '+table+' WHERE id=?',(key,)).fetchone()


def _write(conn,lease,operation,target,table,key,sql,args):
    """Private single-statement scope, never accepts a caller verifier."""
    before=_row(conn,table,key);before=dict(before) if before else None
    binding=FinancialWriteBinding(operation,target,table,str(key),digest(canonical(before)),before.get('version',0) if before else 0)
    def validate():
        current=_row(conn,table,key);current=dict(current) if current else None
        if digest(canonical(current))!=binding.before_digest:raise PermissionError('financial row/version changed')
        return binding
    authority=FinancialWriteAuthority(conn,lease,operation,validate,_factory=_FACTORY)
    with _financial_write_scope(conn,lease,authority):return conn.execute(sql,args)


def _source(conn,store,actor,lease,source):
    from .store import ResearchStore
    from .authorization import AccountIdentity,OwnerGateLease
    _current_scope(conn)
    if type(store) is not ResearchStore or type(actor) is not AccountIdentity or type(lease) is not OwnerGateLease:
        raise PermissionError('canonical offline budget context required')
    if (type(source) is not OfflineProjectRegistration or not source._active or source._pid!=os.getpid()
            or _SOURCES.get(source._ref) is not source or source._store is not store or source._identity!=actor):
        raise PermissionError('explicit offline budget source required')
    _owner_binding(conn,store,source._principal,lease)
    AuthorizationGate(store).check(conn,actor,source._principal)
    facts=source._funding.current(conn,source._principal)
    if canonical(facts)!=source._facts:raise PermissionError('offline funding source changed')
    project=_row(conn,'research_project_budgets',1)
    if project and (project['authorization_ref']!=source._reference or project['authorized_cap']!=source._cap.amount_units
            or project['funding_account_id']!=facts['account_id'] or project['economic_binding']!=facts['binding_id']
            or project['mode']!='offline_probe' or project['database_binding']!=digest(str(store.path).encode())):
        raise PermissionError('project authorization changed')
    return facts,project


def activate_offline_in(conn,*,store,actor,lease,source):
    """Explicit server simulation only. Normal app has no configured source."""
    facts,project=_source(conn,store,actor,lease,source)
    if project is None:register_closed_project(conn,store=store,identity=actor,lease=lease,source=source);project=_row(conn,'research_project_budgets',1)
    if project['status']=='closed':
        if project['version']!=1:raise PermissionError('paused project requires separate explicit authorization')
        if _write(conn,lease,'project-update','','research_project_budgets',1,
                "UPDATE research_project_budgets SET status='active',version=version+1 WHERE id=1 AND version=? AND status='closed'",(project['version'],)).rowcount!=1:
            raise PermissionError('offline activation CAS failed')
    elif project['status']!='active':raise PermissionError('project budget blocked')
    scope=_current_scope(conn);scope.financial_active=True;scope.refresh_authorizer()


def _limits(conn,project,account,new):
    if project['status']!='active' or account['status']!='active':raise PermissionError('budget unavailable')
    if conn.execute("SELECT 1 FROM research_reservations WHERE account_id=? AND status='UNKNOWN' LIMIT 1",(account['id'],)).fetchone():
        raise ResearchError('RECONCILIATION_REQUIRED',409,'此资金账户仍有未核对调用，暂停新执行。')
    exposure=account['settled']+account['upper_booked']+account['held']+new
    snapshot=conn.execute('SELECT * FROM research_balance_snapshots WHERE id=? AND account_id=?',(account['snapshot_id'],account['id'])).fetchone()
    if not snapshot or snapshot['expires_at']<=stamp():raise ResearchError('BUDGET_UNVERIFIED',503,'资金依据已过期。')
    available=snapshot['balance']-account['held']-max(0,account['settled']-snapshot['settled_at_observation'])-max(0,account['upper_booked']-snapshot['upper_booked_at_observation'])
    if exposure>min(project['authorized_cap'],account['cap']) or available<new:
        raise ResearchError('BUDGET_EXHAUSTED',429,'共享预算不足。')


def _bump_project(conn,lease):
    project=_row(conn,'research_project_budgets',1)
    if _write(conn,lease,'project-update','','research_project_budgets',1,
            'UPDATE research_project_budgets SET version=version+1 WHERE id=1 AND version=?',(project['version'],)).rowcount!=1:
        raise PermissionError('project budget CAS failed')


class BudgetPreparation:
    __slots__=('store','actor','source','pid','approval','reservation','permit','dispatch','session','prepared','reserved','basis','confirmed_at','reserve_time','_active')
    def __init__(self,*,_factory=None):
        if _factory is not _PREP_FACTORY:raise TypeError('actual budget reserve required')
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('budget preparation immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('preparations cannot cross process')


def reserve_in(conn,*,store,actor,lease,source,approval_ref):
    _,project=_source(conn,store,actor,lease,source)
    if not project:raise PermissionError('project not registered')
    row,payload,context,task=_checked(conn,store,actor,lease,approval_ref)
    step=conn.execute("SELECT * FROM research_steps WHERE task_id=? AND kind='model_report'",(task['id'],)).fetchone()
    if not step or step['state']!='PENDING' or conn.execute('SELECT 1 FROM research_reservations WHERE step_id=?',(step['id'],)).fetchone():
        raise PermissionError('existing reservation cannot be resent')
    packet=read_confirmed_provider_packet(conn,store,actor,packet_authority(conn,store,actor,lease,approval_ref))
    prepared=prepare_request(payload['summary'],packet);final_request_bytes(prepared)
    authority=mint_current_paid_authority(conn,store=store,lease=lease,identity=actor,context=context,step_id=step['id'],
        expected_task_version=task['version'],expected_step_version=step['version'],operation='reserve',approval_ref=approval_ref)
    cap=authority.require(conn,'reserve')
    quote=UsageUpperQuote.model_validate(payload['funding']['quote']);now=int(time.time());dispatch=uid()
    reserved=reserve_bound(quote,dispatch_id=dispatch,request_digest=prepared.request_digest,now=now)
    if reserved.reserved_upper!=cap.approved_upper or project['funding_account_id']!=cap.account_id:raise PermissionError('approved reserve mismatch')
    account=_row(conn,'research_funding_accounts',cap.account_id);_limits(conn,project,account,reserved.reserved_upper.amount_units)
    reservation,permit,session=uid(),uid(),uid();upper=reserved.reserved_upper.amount_units
    _write(conn,lease,'reserve-row',reservation,'research_reservations',reservation,"INSERT INTO research_reservations(id,account_id,task_id,step_id,operation_key,price_revision,funding_epoch,max_cost,status,policy_revision,principal_id,auth_scope_digest,outbound_fingerprint) VALUES(?,?,?,?,?,?,?,?,'HELD',?,?,?,?)",
        (reservation,cap.account_id,task['id'],step['id'],dispatch,quote.revision,account['funding_epoch'],upper,POLICY,context.principal_id,cap.auth_scope_digest,cap.outbound_fingerprint))
    expiry=datetime.fromtimestamp(min(quote.valid_until,payload['funding']['basis']['valid_until']),timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    _write(conn,lease,'reserve-row',permit,'research_dispatch_permits',permit,"INSERT INTO research_dispatch_permits(id,step_id,reservation_id,dispatch_id,input_digest,state,expires_at,policy_revision,request_digest,evidence_digest,price_digest,budget_basis_digest,budget_basis_json,authorization_context_digest,authorized_task_version,authorized_step_version,paid_approval_ref,admitted_at,gate_identity_json) VALUES(?,?,?,?,?,'prepared',?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (permit,step['id'],reservation,dispatch,context.input_digest,expiry,POLICY,prepared.request_digest,prepared.evidence_digest,cap.quote_digest,cap.basis_digest,
         canonical(payload['funding']['basis']).decode(),digest(canonical(context.model_dump())),task['version'],step['version']+1,approval_ref,now,canonical(lease.identity).decode()))
    descriptor=digest(canonical({'producer':PRODUCER,'dispatch':dispatch,'request':prepared.request_digest,'reservation':reservation}))
    if conn.execute('SELECT version FROM research_schema').fetchone()[0]==9:
        from .method_result import fresh_scope
        with fresh_scope(conn,store=store,lease=lease,authority=authority,ref=session):
            _write(conn,lease,'reserve-row',session,'research_provider_sessions',session,"INSERT INTO research_provider_sessions(id,approval_id,dispatch_id,permit_id,mode,binding_digest,state,body_origin_state) VALUES(?,?,?,?,'offline_probe',?,'created','fresh')",(session,approval_ref,dispatch,permit,descriptor))
    else:_write(conn,lease,'reserve-row',session,'research_provider_sessions',session,"INSERT INTO research_provider_sessions(id,approval_id,dispatch_id,permit_id,mode,binding_digest,state) VALUES(?,?,?,?,'offline_probe',?,'created')",(session,approval_ref,dispatch,permit,descriptor))
    conn.execute("UPDATE research_steps SET state='PREPARED',reservation_id=?,version=version+1 WHERE id=? AND version=?",(reservation,step['id'],step['version']))
    if _write(conn,lease,'money',account['id'],'research_funding_accounts',account['id'],
            'UPDATE research_funding_accounts SET held=held+?,version=version+1 WHERE id=? AND version=?',(upper,account['id'],account['version'])).rowcount!=1:raise PermissionError('reserve CAS failed')
    _bump_project(conn,lease)
    proof=BudgetPreparation(_factory=_PREP_FACTORY)
    for key,value in dict(store=store,actor=actor,source=source,pid=os.getpid(),approval=approval_ref,reservation=reservation,permit=permit,
            dispatch=dispatch,session=session,prepared=prepared,reserved=reserved,basis=BudgetBasisSnapshot.model_validate(payload['funding']['basis']),
            confirmed_at=row['confirmed_at'],reserve_time=now,_active=True).items():setattr(proof,key,value)
    _PREPARED[session]=proof
    return proof


def authorize_in(conn,proof,lease):
    if type(proof) is not BudgetPreparation or proof.pid!=os.getpid() or not proof._active or _PREPARED.get(proof.session) is not proof:
        raise PermissionError('actual reserve preparation required')
    _,project=_source(conn,proof.store,proof.actor,lease,proof.source)
    row,payload,context,task=_checked(conn,proof.store,proof.actor,lease,proof.approval)
    reservation=_row(conn,'research_reservations',proof.reservation);permit=_row(conn,'research_dispatch_permits',proof.permit)
    session=_row(conn,'research_provider_sessions',proof.session);step=_row(conn,'research_steps',permit['step_id']) if permit else None
    if (not reservation or not permit or not session or not step or reservation['status']!='HELD'
            or permit['state']!='prepared' or session['state']!='created' or session['financial_return_json'] is not None
            or permit['dispatch_id']!=proof.dispatch or session['dispatch_id']!=proof.dispatch
            or reservation['max_cost']!=proof.reserved.reserved_upper.amount_units
            or final_request_bytes(proof.prepared)!=proof.prepared.raw or context!=proof.prepared.packet.context):
        raise PermissionError('reserved dispatch changed')
    facts=mint_current_paid_authority(conn,store=proof.store,lease=lease,identity=proof.actor,context=context,step_id=step['id'],
        expected_task_version=task['version'],expected_step_version=step['version'],operation='consume',approval_ref=proof.approval).require(conn,'consume')
    account=_row(conn,'research_funding_accounts',facts.account_id);_limits(conn,project,account,0)
    if account['held']<reservation['max_cost']:raise PermissionError('full held reserve missing')
    return row,payload,context,task,step,reservation,permit,session,project


def consume_in(conn,proof,lease):
    row,payload,ctx,task,step,r,p,s,project=authorize_in(conn,proof,lease)
    now=int(time.time());admission_id=uid()
    from . import usage_upper
    snap=FinancialAdmissionSnapshot(record_version='financial-admission-v1',producer_version=PRODUCER,policy=POLICY,mode='offline_probe',purpose='method_hypothesis',
        project=dict(budget_id=1,version=project['version'],authorized_cap=Money(currency='CNY',scale=6,amount_units=project['authorized_cap']).model_dump(),
            authorization_ref=project['authorization_ref'],authorization_digest=project['authorization_digest'],database_binding=project['database_binding'],
            account_id=r['account_id'],economic_binding=project['economic_binding'],funding_epoch=r['funding_epoch']),
        actor=dict(principal_id=ctx.principal_id,principal_epoch=ctx.principal_epoch,grant_id=ctx.grant_id,grant_epoch=ctx.grant_epoch,
            approval_ref=row['id'],approval_digest=row['payload_digest'],funding_permission_ref=payload['funding']['source_ref'],
            funding_permission_digest=digest(canonical({'source':payload['funding']['source_ref'],'account':r['account_id']})),scope_digest=r['auth_scope_digest']),
        dispatch=dict(task_id=task['id'],step_id=step['id'],attempt=ctx.attempt,authorized_task_version=task['version'],authorized_step_version=step['version'],
            task_before=task['version'],task_after=task['version']+1,step_before=step['version'],step_after=step['version']+1,
            reservation_id=r['id'],reservation_before=r['version'],reservation_after=r['version']+1,permit_id=p['id'],permit_before='prepared',permit_after='consumed',
            dispatch_id=proof.dispatch,session_id=s['id'],session_before=s['version'],session_after=s['version']+1,
            request_digest=proof.prepared.request_digest,evidence_digest=proof.prepared.evidence_digest,context_digest=digest(canonical(ctx.model_dump())),outbound_fingerprint=r['outbound_fingerprint']),
        quote=UsageUpperQuote.model_validate(payload['funding']['quote']),reserved=proof.reserved,basis=proof.basis,
        quote_digest=proof.reserved.quote_digest,basis_digest=digest(canonical(proof.basis.model_dump())),approved_upper=proof.reserved.reserved_upper,
        codec_digest=payload['funding']['quote']['final_request_code_digest'],math_version=POLICY,math_code_digest=digest(Path(usage_upper.__file__).read_bytes()),
        confirmed_at=proof.confirmed_at,reserve_checked_at=proof.reserve_time,admitted_at=now,recorded_at=now)
    raw=canonical(snap.model_dump());validate_snapshot_json(raw,expected_digest=digest(raw))
    for sql,args in [
        ("UPDATE research_dispatch_permits SET state='consumed' WHERE id=? AND state='prepared'",(p['id'],)),
        ("UPDATE research_reservations SET status='SENT',version=version+1 WHERE id=? AND version=? AND status='HELD'",(r['id'],r['version'])),
        ("UPDATE research_provider_sessions SET state='consumed',version=version+1 WHERE id=? AND version=? AND state='created'",(s['id'],s['version'])),
        ("UPDATE research_paid_approvals SET state='consumed',dispatch_id=?,version=version+1 WHERE id=? AND version=? AND state='confirmed'",(proof.dispatch,row['id'],row['version'])),
        ("UPDATE research_steps SET state='SENDING',version=version+1 WHERE id=? AND version=?",(step['id'],step['version'])),
        ("UPDATE research_tasks SET execution='WAITING_EXTERNAL',version=version+1 WHERE id=? AND version=?",(task['id'],task['version']))]:
        table=sql.split()[1];key=args[-2] if table in ('research_reservations','research_provider_sessions','research_steps','research_tasks') else p['id'] if table=='research_dispatch_permits' else row['id']
        if _write(conn,lease,'consume-row',str(key),table,key,sql,args).rowcount!=1:raise PermissionError('consume CAS failed')
    conn.execute("INSERT INTO research_task_events VALUES(?,?,?,?,?,?)",(task['id'],conn.execute('SELECT COALESCE(MAX(seq),0)+1 FROM research_task_events WHERE task_id=?',(task['id'],)).fetchone()[0],task['version']+1,'budget_consumed',None,stamp()))
    _write(conn,lease,'admit',proof.dispatch,'research_financial_admissions',admission_id,
        'INSERT INTO research_financial_admissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (admission_id,1,r['id'],p['id'],s['id'],proof.dispatch,'financial-admission-v1',PRODUCER,POLICY,'offline_probe',raw.decode(),digest(raw),stamp()))
    _bump_project(conn,lease)
    return admission_id,snap


@dataclass(frozen=True)
class CostReturnBinding:
    return_ref:str
    admission_digest:str
    return_digest:str
    reservation_id:str
    reservation_version:int
    account_version:int
    project_version:int


def _load_admission(conn,store,lease,return_ref,*,read=False):
    if read:
        from .method_result import _scope
        _scope(conn,store,lease)
    else:_current_scope(conn)
    row=conn.execute('SELECT * FROM research_financial_admissions WHERE session_id=?',(return_ref,)).fetchone()
    if not row or row['producer_version']!=PRODUCER or row['mode']!='offline_probe':raise PermissionError('new controlled admission required')
    snap=validate_snapshot_json(row['snapshot_json'].encode(),expected_digest=row['snapshot_digest'])
    _owner_binding(conn,store,snap.actor.principal_id,lease)
    project=_row(conn,'research_project_budgets',1);r=_row(conn,'research_reservations',row['reservation_id']);p=_row(conn,'research_dispatch_permits',row['permit_id']);s=_row(conn,'research_provider_sessions',return_ref)
    from . import usage_upper
    q=_row(conn,'research_price_revisions',snap.quote.revision)
    approval=_row(conn,'research_paid_approvals',snap.actor.approval_ref)
    if (snap.project.database_binding!=digest(str(store.path).encode()) or not project or not r or not p or not s or not q
            or project['funding_account_id']!=snap.project.account_id or project['economic_binding']!=snap.project.economic_binding
            or project['authorized_cap']!=snap.project.authorized_cap.amount_units or project['authorization_digest']!=snap.project.authorization_digest
            or project['authorization_ref']!=snap.project.authorization_ref or project['database_binding']!=snap.project.database_binding or project['mode']!='offline_probe'
            or r['account_id']!=snap.project.account_id or r['funding_epoch']!=snap.project.funding_epoch or r['max_cost']!=snap.reserved.reserved_upper.amount_units
            or r['id']!=snap.dispatch.reservation_id or r['task_id']!=snap.dispatch.task_id or r['step_id']!=snap.dispatch.step_id
            or r['version']<snap.dispatch.reservation_after or r['auth_scope_digest']!=snap.actor.scope_digest
            or r['outbound_fingerprint']!=snap.dispatch.outbound_fingerprint
            or r['policy_revision']!=POLICY or p['policy_revision']!=POLICY or q['policy_revision']!=POLICY
            or p['id']!=snap.dispatch.permit_id or p['step_id']!=snap.dispatch.step_id or p['reservation_id']!=r['id']
            or p['state']!='consumed' or p['dispatch_id']!=snap.dispatch.dispatch_id or s['dispatch_id']!=p['dispatch_id']
            or s['id']!=snap.dispatch.session_id or s['permit_id']!=p['id'] or s['approval_id']!=snap.actor.approval_ref
            or s['version']<snap.dispatch.session_after or s['mode']!='offline_probe'
            or not approval or approval['payload_digest']!=snap.actor.approval_digest or p['paid_approval_ref']!=approval['id']
            or p['request_digest']!=snap.dispatch.request_digest or p['evidence_digest']!=snap.dispatch.evidence_digest
            or p['authorization_context_digest']!=snap.dispatch.context_digest
            or p['price_digest']!=snap.quote_digest or p['budget_basis_digest']!=snap.basis_digest
            or p['authorized_task_version']!=snap.dispatch.authorized_task_version or p['authorized_step_version']!=snap.dispatch.authorized_step_version
            or q['quote_json']!=canonical(snap.quote.model_dump()).decode() or q['quote_digest']!=snap.quote_digest or q['account_id']!=snap.project.account_id
            or snap.math_code_digest!=digest(Path(usage_upper.__file__).read_bytes())):
        raise PermissionError('original financial admission binding changed')
    return row,snap,project,r,p,s


def _validated_return(conn,store,lease,return_ref,*,read=False):
    admission,snap,project,r,p,s=_load_admission(conn,store,lease,return_ref,read=read)
    if not s['financial_return_json']:raise PermissionError('no durable owned return')
    raw=s['financial_return_json'].encode()
    data=strict_json(raw,16384)
    allowed={'record_version','admission_ref','admission_digest','transport','received_at','execution_mode','model_analysis_ran','actual_charge'}
    if (set(data)!=allowed or data['record_version']!=PRODUCER or data['admission_ref']!=admission['id']
            or data['admission_digest']!=admission['snapshot_digest'] or data['execution_mode']!='offline_probe'
            or data['model_analysis_ran'] is not False or data['actual_charge'] is not None
            or canonical(data)!=raw or digest(raw)!=s['return_digest'] or data['received_at']!=s['received_at']):
        raise PermissionError('durable financial return damaged')
    transport=data['transport']
    try:_FinancialTransport.model_validate(transport)
    except ValueError:raise PermissionError('invalid bounded financial transport') from None
    expected=set(OfflineTransportReturn.model_fields)-{'candidate','context'}
    if (type(transport) is not dict or set(transport)!=expected or transport['execution_mode']!='offline_probe'
            or transport['dispatch_id']!=snap.dispatch.dispatch_id or transport['request_digest']!=snap.dispatch.request_digest
            or transport['evidence_digest']!=snap.dispatch.evidence_digest or transport['response_model'] not in (None,MODEL)):
        raise PermissionError('financial transport binding damaged')
    if r['status'] not in ('SENT','UNKNOWN','UPPER_BOOKED'):raise PermissionError('financial reservation not consumable')
    account=_row(conn,'research_funding_accounts',r['account_id'])
    binding=CostReturnBinding(return_ref,admission['snapshot_digest'],s['return_digest'],r['id'],r['version'],account['version'],project['version'])
    return binding,snap,transport,r,account,project


def observe_in(conn,*,store,lease,return_ref):
    try:
        cap=mint_cost_from_return(conn,store=store,lease=lease,return_ref=return_ref);cap.require(conn,'observe')
    except (PermissionError,ValueError):
        # Missing durable reception is never permission to recreate a receipt.
        original=conn.execute('SELECT reservation_id FROM research_financial_admissions WHERE session_id=?',(return_ref,)).fetchone()
        if not original:raise
        r=_row(conn,'research_reservations',original[0])
        unknown_in(conn,r['id'],store=store,lease=lease)
        return {'kind':'unknown','actual_charge':None,'reserved_upper':r['max_cost']}
    _,snap,transport,r,account,project=_validated_return(conn,store,lease,return_ref)
    previous=conn.execute("SELECT * FROM research_cost_observations WHERE trusted_return_ref=? AND kind='estimated_upper'",(return_ref,)).fetchone()
    if previous:
        if r['status']!='UPPER_BOOKED':raise PermissionError('booked observation state damaged')
        return dict(previous)
    upper=snap.reserved.reserved_upper.amount_units
    try:
        if transport['usage'] is None or transport['response_digest'] is None:raise ValueError('missing final usage')
        usage=UsageObservation.model_validate(transport['usage'])
        math=observed_bound(snap.quote,snap.reserved,usage,dispatch_id=snap.dispatch.dispatch_id,request_digest=snap.dispatch.request_digest)
    except ValueError:
        unknown_in(conn,snap.dispatch.reservation_id,store=store,lease=lease)
        return {'kind':'unknown','actual_charge':None,'reserved_upper':upper}
    if account['held']<upper:raise PermissionError('original held upper missing')
    booked=math.observed_upper.amount_units;oid=uid()
    _write(conn,lease,'cost-insert',oid,'research_cost_observations',oid,"INSERT INTO research_cost_observations(id,account_id,reservation_id,dispatch_id,policy_revision,kind,response_digest,usage_ref,provider_response_ref,usage_json,observation_digest,reserved_upper,booked_upper,actual_charge,price_revision,basis_digest,safe_code,observed_at,released_reserve_difference,trusted_return_ref) VALUES(?,?,?,?,?,'estimated_upper',?,?,?,?,?,?,?,NULL,?,?,?,?,?,?)",
        (oid,account['id'],r['id'],snap.dispatch.dispatch_id,POLICY,transport['response_digest'],math.usage_binding_digest,transport['provider_ref'],canonical(usage.model_dump()).decode(),
         digest(canonical(math.model_dump())),upper,booked,snap.quote.revision,snap.basis_digest,transport['safe_code'],stamp(),upper-booked,return_ref))
    if _write(conn,lease,'observe-row',r['id'],'research_reservations',r['id'],"UPDATE research_reservations SET status='UPPER_BOOKED',version=version+1 WHERE id=? AND version=? AND status IN ('SENT','UNKNOWN')",(r['id'],r['version'])).rowcount!=1:raise PermissionError('observe CAS failed')
    if _write(conn,lease,'money',account['id'],'research_funding_accounts',account['id'],
            'UPDATE research_funding_accounts SET held=held-?,upper_booked=upper_booked+?,version=version+1 WHERE id=? AND version=?',
            (upper,booked,account['id'],account['version'])).rowcount!=1:raise PermissionError('observe ledger CAS failed')
    _bump_project(conn,lease)
    return dict(_row(conn,'research_cost_observations',oid))


def unknown_in(conn,reservation_id,*,store,lease):
    _current_scope(conn)
    r=_row(conn,'research_reservations',reservation_id)
    if not r or r['policy_revision']!=POLICY:raise PermissionError('original v2 reservation required')
    _owner_binding(conn,store,r['principal_id'],lease)
    if r['status']=='SENT':
        _write(conn,lease,'unknown',r['id'],'research_reservations',r['id'],
            "UPDATE research_reservations SET status='UNKNOWN',version=version+1 WHERE id=? AND status='SENT' AND version=?",(r['id'],r['version']))


def cancel_in(conn,*,store,actor,lease,task_id,expected_task_version,deletion_job_id=None,request_source=None,key=None,body_digest=None):
    task=_row(conn,'research_tasks',task_id)
    cap=mint_stop_authority(conn,store=store,lease=lease,principal_id=task['principal_id'],task_id=task_id,
        expected_task_version=expected_task_version,identity=actor,deletion_job_id=deletion_job_id,request_source=request_source,key=key,body_digest=body_digest)
    stop_financial_in(conn,store=store,lease=lease,authority=cap)
    conn.execute("UPDATE research_tasks SET stop_requested=1,execution='CANCELLED',version=version+1 WHERE id=? AND version=?",(task_id,expected_task_version))


def stop_financial_in(conn,*,store,lease,authority):
    from .paid_control import StopAuthority
    if type(authority) is not StopAuthority or authority._lease is not lease:raise PermissionError('actual stop source required')
    facts=authority.require(conn,'cancel');task_id=facts.task_id
    for r in conn.execute("SELECT * FROM research_reservations WHERE task_id=? AND policy_revision=?",(task_id,POLICY)).fetchall():
        p=conn.execute('SELECT * FROM research_dispatch_permits WHERE reservation_id=?',(r['id'],)).fetchone()
        if r['status']=='HELD' and p['state']=='prepared':
            account=_row(conn,'research_funding_accounts',r['account_id'])
            if account['held']<r['max_cost']:raise PermissionError('held cancellation mismatch')
            _write(conn,lease,'cancel-row',p['id'],'research_dispatch_permits',p['id'],"UPDATE research_dispatch_permits SET state='revoked' WHERE id=? AND state='prepared'",(p['id'],))
            _write(conn,lease,'cancel-row',r['id'],'research_reservations',r['id'],"UPDATE research_reservations SET status='RELEASED',version=version+1 WHERE id=? AND version=?",(r['id'],r['version']))
            _write(conn,lease,'money',account['id'],'research_funding_accounts',account['id'],'UPDATE research_funding_accounts SET held=held-?,version=version+1 WHERE id=? AND version=?',(r['max_cost'],account['id'],account['version']))
        elif r['status']=='SENT':unknown_in(conn,r['id'],store=store,lease=lease)
    if _row(conn,'research_project_budgets',1):_bump_project(conn,lease)


def reconcile_task_in(conn,*,store,lease,task_id):
    _current_scope(conn)
    task=_row(conn,'research_tasks',task_id)
    if not task or task['policy_revision']!=POLICY:raise PermissionError('v2 task required')
    _owner_binding(conn,store,task['principal_id'],lease)
    results=[]
    for reservation in conn.execute('SELECT * FROM research_reservations WHERE task_id=? AND policy_revision=?',(task_id,POLICY)).fetchall():
        if reservation['status'] in ('SENT','UNKNOWN','UPPER_BOOKED'):
            admission=conn.execute('SELECT session_id FROM research_financial_admissions WHERE reservation_id=?',(reservation['id'],)).fetchone()
            if admission:results.append(observe_in(conn,store=store,lease=lease,return_ref=admission[0]))
            elif reservation['status']=='SENT':unknown_in(conn,reservation['id'],store=store,lease=lease)
    return results
