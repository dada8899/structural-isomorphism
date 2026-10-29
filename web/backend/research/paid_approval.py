"""Internal offline approval producer; there is no live funding resolver/API."""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import json
import time
from uuid import uuid4

from .authorization import AccountIdentity,AuthorizationGate
from .errors import ResearchError,not_found
from .provider_schemas import UsageUpperQuote,BudgetBasisSnapshot,Money,CallContext,canonical,digest
from .provider_adapter import prepare_request,final_request_bytes
from .provider_evidence import read_provider_eligibility
from .paid_control import _Authority,_FACTORY,_current_scope,_owner_binding
from .paid_control import CurrentPaidAuthority

POLICY='bounded_usage_upper_v2'
_SOURCES={}


def request_codec_digest():
    from pathlib import Path
    from . import provider_adapter,provider_schemas,preview_codec
    return digest(canonical({module.__name__.rsplit('.',1)[-1]:digest(Path(module.__file__).read_bytes()) for module in (provider_adapter,provider_schemas,preview_codec)}))


class OfflineFundingResolver:
    """Explicit server simulation dependency, never proof of real prepayment.

    No writes/provision, keys, network, arbitrary verifier or live mode. Rows
    alone do not activate it, and its identity is never accepted from clients.
    """
    __slots__=('_ref','_pid','_quote','_basis','_upper','_active')
    def __init__(self,*,principal_id,quote,basis,approved_upper):
        if type(quote) is not UsageUpperQuote or type(basis) is not BudgetBasisSnapshot or type(approved_upper) is not Money:
            raise TypeError('typed offline source configuration required')
        quote=UsageUpperQuote.model_validate(quote.model_dump())
        basis=BudgetBasisSnapshot.model_validate(basis.model_dump())
        approved_upper=Money.model_validate(approved_upper.model_dump())
        amounts=(basis.initial_prepaid,basis.other_use_margin,basis.cap,basis.settled_actual,basis.upper_booked,basis.held,basis.available_after_observed_consumption,approved_upper)
        if (quote.currency!='CNY' or approved_upper.currency!='CNY' or basis.cap.currency!='CNY'
                or any(value.currency!='CNY' or value.scale!=6 for value in amounts)
                or basis.cap.amount_units!=basis.initial_prepaid.amount_units-basis.other_use_margin.amount_units
                or basis.price_revision!=quote.revision or approved_upper.amount_units<=0
                or quote.final_request_code_digest!=request_codec_digest()):
            raise ValueError('same-currency offline configuration required')
        self._ref,self._pid,self._quote,self._basis,self._upper,self._active=str(uuid4()),principal_id,quote,basis,approved_upper,True
        _SOURCES[self._ref]=self
    def __reduce__(self):raise TypeError('offline source cannot be serialized')
    def close(self):
        self._active=False;_SOURCES.pop(self._ref,None)
    def current(self,conn,pid):
        if not self._active or _SOURCES.get(self._ref) is not self or pid!=self._pid:raise PermissionError('registered offline source unavailable')
        q,b,u=self._quote,self._basis,self._upper
        if min(q.valid_until,b.valid_until)<=int(time.time()):raise ResearchError('BUDGET_UNVERIFIED',503,'离线控制依据已过期。')
        from .usage_upper import preview_bound,UpperMathError
        try:bound=preview_bound(q,now=int(time.time()))
        except UpperMathError:raise ResearchError('BUDGET_UNVERIFIED',503,'当前报价不满足已审短时效或金额上界。') from None
        if bound.upper_bound!=u or bound.quote_revision!=q.revision or bound.quote_digest!=digest(canonical(q.model_dump())):
            raise ResearchError('BUDGET_UNVERIFIED',503,'服务器模拟授权值与原报价上界不一致。')
        a=conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(b.account_id,)).fetchone()
        p=conn.execute('SELECT * FROM research_price_revisions WHERE id=? AND account_id=?',(q.revision,b.account_id)).fetchone()
        snapshot=conn.execute('SELECT * FROM research_balance_snapshots WHERE id=? AND account_id=?',(b.id,b.account_id)).fetchone()
        if (not a or not p or a['status']!='active' or a['mode']!='live' or a['provider']!='deepseek'
                or a['currency']!='CNY' or a['scale']!=6 or a['binding_id']!=b.provider_binding_id
                or a['funding_epoch']!=b.funding_epoch or a['cap']!=b.cap.amount_units
                or a['initial_prepaid_units']!=b.initial_prepaid.amount_units or a['other_use_margin_units']!=b.other_use_margin.amount_units
                or p['policy_revision']!=POLICY or p['quote_digest']!=digest(canonical(q.model_dump()))
                or p['quote_json']!=canonical(q.model_dump()).decode() or not snapshot or a['snapshot_id']!=b.id
                or snapshot['funding_epoch']!=b.funding_epoch or snapshot['basis_evidence_digest']!=digest(canonical(b.model_dump()))
                or snapshot['expires_at']<=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                or not all(snapshot[name]==1 for name in ('hard_prepaid','auto_topup_off','postpaid_off'))):
            raise ResearchError('BUDGET_UNVERIFIED',503,'离线资金配置与当前控制记录不符。')
        return dict(source_ref=self._ref,mode='offline_probe',account_id=b.account_id,binding_id=b.provider_binding_id,
            funding_epoch=b.funding_epoch,quote=q.model_dump(),basis=b.model_dump(),approved_upper=bound.upper_bound.model_dump())


@dataclass(frozen=True)
class PacketBinding:
    approval_ref:str
    principal_id:str
    research_id:str
    input_revision:int
    context:CallContext
    source_refs:tuple[str,...]
    source_manifest_digest:str
    mode:str


class PaidPacketAuthority(_Authority):
    __slots__=()


@dataclass(frozen=True)
class PaidBinding:
    approval_ref:str
    principal_id:str
    task_id:str
    step_id:str
    task_version:int
    step_version:int
    account_id:str
    policy:str
    execution_mode:str
    request_digest:str
    evidence_digest:str
    quote_digest:str
    basis_digest:str
    approved_upper:Money
    auth_scope_digest:str
    outbound_fingerprint:str


def mint_current_authority(conn,*,store,lease,identity,context,step_id,expected_task_version,expected_step_version,operation,approval_ref):
    from .provider_evidence import read_confirmed_provider_packet
    if operation not in ('reserve','authorize','consume') or type(context) is not CallContext:
        raise PermissionError('fixed paid operation required')
    def validate():
        row,payload,current,task=_checked(conn,store,identity,lease,approval_ref)
        step=conn.execute('SELECT * FROM research_steps WHERE id=? AND task_id=?',(step_id,task['id'])).fetchone()
        if (type(expected_task_version) is not int or type(expected_step_version) is not int or current!=context
                or not step or step['kind']!='model_report' or step['version']!=expected_step_version or task['version']!=expected_task_version
                or step['state'] not in ('PENDING','PREPARED')):raise PermissionError('paid step/context changed')
        source=packet_authority(conn,store,identity,lease,approval_ref)
        packet=read_confirmed_provider_packet(conn,store,identity,source)
        prepared=prepare_request(payload['summary'],packet);final_request_bytes(prepared)
        if prepared.request_digest!=payload['request_digest'] or prepared.evidence_digest!=payload['evidence_digest']:
            raise PermissionError('confirmed full packet changed')
        f=payload['funding'];a=conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(row['account_id'],)).fetchone()
        upper=Money.model_validate(f['approved_upper'])
        auth_scope=digest(canonical({'context':current.model_dump(),'approval_ref':approval_ref,'generation':identity.generation}))
        outbound=digest(canonical({'method':'POST','target':'https://api.deepseek.com/chat/completions','body_digest':prepared.request_digest}))
        reservation=conn.execute('SELECT * FROM research_reservations WHERE step_id=?',(step_id,)).fetchone()
        if reservation and (reservation['status']!='HELD' or reservation['policy_revision']!=POLICY
                or reservation['task_id']!=task['id'] or reservation['account_id']!=row['account_id']
                or reservation['funding_epoch']!=f['funding_epoch'] or reservation['price_revision']!=f['quote']['revision']
                or reservation['principal_id']!=row['principal_id'] or reservation['auth_scope_digest']!=auth_scope
                or reservation['outbound_fingerprint']!=outbound):
            raise PermissionError('old possible send cannot be reauthorized')
        this=reservation['max_cost'] if reservation and reservation['status']=='HELD' else 0
        if reservation and this!=upper.amount_units:raise PermissionError('approved reservation upper changed')
        if operation!='reserve' and (not reservation or reservation['policy_revision']!=POLICY or this!=upper.amount_units):
            raise PermissionError('same-policy full reservation required')
        permit=conn.execute('SELECT * FROM research_dispatch_permits WHERE step_id=?',(step_id,)).fetchone()
        if operation!='reserve' and (not permit or permit['state']!='prepared' or permit['paid_approval_ref']!=approval_ref
                or permit['policy_revision']!=POLICY or permit['reservation_id']!=reservation['id']
                or permit['authorized_task_version']!=task['version'] or permit['authorized_step_version']!=step['version']
                or permit['request_digest']!=prepared.request_digest or permit['evidence_digest']!=prepared.evidence_digest
                or permit['price_digest']!=digest(canonical(f['quote'])) or permit['budget_basis_digest']!=digest(canonical(f['basis']))
                or permit['input_digest']!=current.input_digest or permit['authorization_context_digest']!=digest(canonical(current.model_dump()))):
            raise PermissionError('current prepared paid permit required')
        if operation!='reserve' and (permit['expires_at']<=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                or type(permit['admitted_at']) is not int or not 0<permit['admitted_at']<=int(time.time())
                or permit['admitted_at']>=f['quote']['valid_until']):
            raise PermissionError('current prepared paid permit required')
        if row['max_calls']!=1 or row['dispatch_id'] is not None:raise PermissionError('single-call approval already consumed')
        if (a['settled']+a['upper_booked']+a['held']+(0 if this else upper.amount_units)>a['cap']):
            raise ResearchError('BUDGET_EXHAUSTED',429,'当前占用已达到上限。')
        snapshot=conn.execute('SELECT * FROM research_balance_snapshots WHERE id=?',(a['snapshot_id'],)).fetchone()
        available=snapshot['balance']-a['held']-max(0,a['settled']-snapshot['settled_at_observation'])-max(0,a['upper_booked']-snapshot['upper_booked_at_observation'])
        if available<(0 if this else upper.amount_units):raise ResearchError('BUDGET_EXHAUSTED',429,'当前余额约束不足。')
        return PaidBinding(approval_ref,row['principal_id'],task['id'],step_id,task['version'],step['version'],row['account_id'],POLICY,
            'offline_probe',prepared.request_digest,prepared.evidence_digest,digest(canonical(f['quote'])),digest(canonical(f['basis'])),upper,auth_scope,outbound)
    return CurrentPaidAuthority(conn,lease,operation,validate,_factory=_FACTORY)


def _checked(conn,store,identity,lease,approval_ref,*,allow_confirming=False):
    _current_scope(conn)
    if type(identity) is not AccountIdentity:raise PermissionError('canonical identity required')
    row=conn.execute('SELECT * FROM research_paid_approvals WHERE id=?',(approval_ref,)).fetchone()
    if not row or row['payload_json'] is None:raise not_found()
    _owner_binding(conn,store,row['principal_id'],lease)
    control=AuthorizationGate(store).check(conn,identity,row['principal_id'],row['research_id'],scope='write')
    if row['state'] not in (('draft','confirmed') if allow_confirming else ('confirmed',)) or row['confirmed_at'] is None or row['expires_at']<=int(time.time()):raise PermissionError('explicit paid consent unavailable')
    payload=json.loads(row['payload_json'])
    if digest(canonical(payload))!=row['payload_digest']:raise PermissionError('paid input digest mismatch')
    if payload['codec_digest']!=request_codec_digest():raise PermissionError('approved request code changed')
    if (payload['generation']!=identity.generation or payload['input_revision']!=control['current_revision']
            or payload['owner_epoch']!=control['owner_epoch'] or payload['acl_epoch']!=control['acl_epoch']):raise PermissionError('paid input/owner changed')
    revision=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(control['id'],control['current_revision'])).fetchone()
    if not revision or revision[0]!=payload['problem_digest']:raise PermissionError('paid problem changed')
    source=_SOURCES.get(row['funding_source_ref'])
    if type(source) is not OfflineFundingResolver:raise ResearchError('FEATURE_UNAVAILABLE',503,'真实资金来源未核，未授予付费权限。')
    funding=source.current(conn,row['principal_id'])
    if funding!=payload['funding']:raise PermissionError('approved funding/quote changed')
    grant=conn.execute('SELECT * FROM research_grants WHERE id=?',(row['grant_id'],)).fetchone()
    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(row['task_id'],)).fetchone()
    if (not grant or not task or grant['status']!='active' or 'execute_paid' not in json.loads(grant['scopes'])
            or grant['funding_account_id']!=row['account_id'] or grant['funding_permission_ref']!=source._ref
            or task['grant_id']!=grant['id'] or task['principal_id']!=row['principal_id'] or task['policy_revision']!=POLICY):raise PermissionError('independent paid grant required')
    AuthorizationGate(store).check_task(conn,task)
    if task['execution'] in ('FAILED','COMPLETED','CANCELLED','ACCESS_REVOKED'):raise PermissionError('paid task ended')
    context=CallContext(principal_id=row['principal_id'],principal_epoch=task['principal_epoch'],grant_id=grant['id'],grant_epoch=grant['version'],owner_epoch=task['owner_epoch'],acl_epoch=task['acl_epoch'],research_id=task['research_id'],input_revision=task['input_revision'],input_digest=task['input_digest'],task_id=task['id'],attempt=1,plan_id=payload['plan_id'])
    return row,payload,context,task


def packet_authority(conn,store,identity,lease,approval_ref,*,allow_confirming=False):
    def validate():
        row,payload,context,task=_checked(conn,store,identity,lease,approval_ref,allow_confirming=allow_confirming)
        return PacketBinding(approval_ref,row['principal_id'],row['research_id'],payload['input_revision'],context,tuple(payload['source_refs']),payload['source_manifest_digest'],'offline_probe')
    return PaidPacketAuthority(conn,lease,'packet',validate,_factory=_FACTORY)


class PaidApprovalService:
    def __init__(self,store,*,funding_resolver=None):
        self.store,self.resolver=store,funding_resolver
        if funding_resolver is not None and type(funding_resolver) is not OfflineFundingResolver:raise TypeError('controlled offline resolver required')

    def preview(self,identity,research_id,input_revision,research_version,source_refs,*,key=None,client_request_digest=None):
        if self.resolver is None:raise ResearchError('FEATURE_UNAVAILABLE',503,'资金使用依据未核，当前入口关闭。')
        candidate=read_provider_eligibility(self.store,identity,research_id,input_revision,research_version,source_refs)
        gate=AuthorizationGate(self.store)
        with self.store.transaction() as conn:
            principal=conn.execute('SELECT id FROM research_principals WHERE normalized_email=? AND session_generation=?',(identity.email,identity.generation)).fetchone()
            if not principal:raise not_found()
            pid=principal[0]
        with gate.owner_gate(pid),self.store.transaction(write=True) as conn:
            control=gate.check(conn,identity,pid,research_id,scope='read')
            if control['current_revision']!=input_revision or control['version']!=research_version:raise ResearchError('REVISION_CONFLICT',409,'问题已变化。')
            from .service import ResearchService
            if key is not None:
                replay=ResearchService._replay(conn,pid,'paid-preview','r:'+research_id,key,client_request_digest)
                if replay is not None:
                    row=conn.execute('SELECT * FROM research_paid_approvals WHERE id=? AND principal_id=? AND research_id=?',(replay['preview_ref'],pid,research_id)).fetchone()
                    if not row or row['state']!='draft' or row['payload_json'] is None or row['expires_at']<=int(time.time()):raise ResearchError('REVISION_CONFLICT',409,'原预览已消费或过期，请重新预览。')
                    original=json.loads(row['payload_json'])
                    from .provider_evidence import read_preview_manifest
                    fresh=read_preview_manifest(conn,self.store,identity,research_id,input_revision,research_version,source_refs,original['summary'])
                    if (digest(canonical(fresh))!=original['manifest_digest'] or self.resolver.current(conn,pid)!=original['funding']
                            or request_codec_digest()!=original['codec_digest']):raise ResearchError('REVISION_CONFLICT',409,'原预览绑定已变化。')
                    return {'preview_view':replay}
            principal=conn.execute('SELECT * FROM research_principals WHERE id=?',(pid,)).fetchone()
            problem=conn.execute('SELECT * FROM research_revisions WHERE research_id=? AND revision=?',(research_id,input_revision)).fetchone()
            data=json.loads(problem['problem_json'])
            if not data['confirmed']:raise ResearchError('INPUT_INVALID',422,'请先确认问题。')
            funding=self.resolver.current(conn,pid)
            from .provider_evidence import read_preview_manifest
            from .preview_codec import preview_request,PreviewOutboundHandle
            manifest=read_preview_manifest(conn,self.store,identity,research_id,input_revision,research_version,source_refs,data['summary'])
            encoded=preview_request(data['summary'],tuple(PreviewOutboundHandle.model_validate(item) for item in manifest['handles']))
            payload=dict(generation=identity.generation,input_revision=input_revision,research_version=research_version,
                problem_digest=problem['digest'],summary=data['summary'],principal_epoch=principal['epoch'],owner_epoch=control['owner_epoch'],acl_epoch=control['acl_epoch'],
                source_refs=list(source_refs),source_manifest_digest=digest(canonical([asdict(item) for item in candidate.excerpts])),funding=funding,codec_digest=request_codec_digest(),
                preview_manifest=manifest,manifest_digest=digest(canonical(manifest)),outbound_request_digest=encoded.outbound_request_digest)
            aid=str(uuid4());timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            expires=min(funding['quote']['valid_until'],funding['basis']['valid_until'],int(time.time())+120)
            utc=lambda value:datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            view=dict(preview_ref=aid,preview_version=1,status='draft',expires_at=utc(expires),
                bindings=dict(research_id=research_id,input_revision=input_revision,input_digest=problem['digest'],research_version=research_version),
                purpose='method_hypothesis',provider='deepseek',model='deepseek-flash',declared_model_version='DeepSeek-V4.1-Flash',
                execution_mode='offline_probe',policy_revision=POLICY,
                quote=dict(revision=funding['quote']['revision'],digest=digest(canonical(funding['quote'])),valid_until=utc(funding['quote']['valid_until'])),
                maximum_reserve=funding['approved_upper'],actual=None,cost_label='maximum_reserve_not_actual',max_calls=1,
                manifest=manifest,manifest_digest=payload['manifest_digest'],outbound_request_digest=encoded.outbound_request_digest,
                may_send_to_provider=False,model_analysis_ran=False)
            view['preview_digest']=digest(canonical(view));payload['preview_digest']=view['preview_digest']
            conn.execute("INSERT INTO research_paid_approvals(id,principal_id,research_id,payload_json,payload_digest,state,mode,policy_revision,funding_source_ref,account_id,expires_at,created_at) VALUES(?,?,?,?,?,'draft','offline_probe',?,?,?,?,?)",(aid,pid,research_id,canonical(payload).decode(),digest(canonical(payload)),POLICY,self.resolver._ref,funding['account_id'],expires,timestamp))
            if key is not None:ResearchService._remember(conn,pid,'paid-preview','r:'+research_id,key,client_request_digest,view)
            # Legacy aliases remain internal only; the future route must emit
            # exactly preview_view, never directly serialize this container.
            return {**view,'preview_view':view,'mode':'offline_probe','summary':data['summary'],'excerpts':manifest['sources'],
                'maximum_approved_upper':funding['approved_upper'],'may_send':False}

    def confirm(self,identity,preview_ref,preview_digest,key,*,expected_preview_version=1,research_id=None,input_revision=None,expected_research_version=None,client_request_digest=None):
        from .provider_evidence import read_confirmed_provider_packet
        from .service import ResearchService,now
        from .projection import ResearchProjection
        gate=AuthorizationGate(self.store)
        if type(expected_preview_version) is not int or expected_preview_version<1:raise ResearchError('INPUT_INVALID',422,'预览版本无效。')
        if type(key) is not str or not 1<=len(key)<=128 or any(not (c.isascii() and (c.isalnum() or c in '._:-')) for c in key):raise ResearchError('INPUT_INVALID',422,'操作标识无效。')
        operation_digest=client_request_digest or digest(canonical({'preview_ref':preview_ref,'digest':preview_digest,'version':expected_preview_version}))
        with self.store.transaction() as conn:
            row=conn.execute('SELECT principal_id,research_id,payload_json FROM research_paid_approvals WHERE id=?',(preview_ref,)).fetchone()
            if not row:raise not_found()
            pid=row[0]
            gate.check(conn,identity,pid,row['research_id'],scope='write')
            if research_id is not None and row['research_id']!=research_id:raise not_found()
            bound=json.loads(row['payload_json']) if row['payload_json'] else None
            if not bound:raise not_found()
            if ((input_revision is not None and input_revision!=bound['input_revision']) or
                    (expected_research_version is not None and expected_research_version!=bound['research_version'])):
                raise ResearchError('REVISION_CONFLICT',409,'确认的预览输入绑定不一致。')
        with gate.owner_gate(pid) as lease,self.store.transaction(write=True) as conn:
            row=conn.execute('SELECT * FROM research_paid_approvals WHERE id=?',(preview_ref,)).fetchone()
            gate.check(conn,identity,pid,row['research_id'],scope='write')
            def current_receipt(receipt):
                owner=gate.check(conn,identity,pid,row['research_id'])
                # A financial/confirmation replay never reinstates permission
                # to display source material that has since been revoked.
                from .evidence_repository import EvidenceRepository
                from .source_integration import authorizer,context_for
                saved=json.loads(row['payload_json']) if row['payload_json'] else None
                if not saved:raise not_found()
                repository=EvidenceRepository(conn,authorizer(self.store,identity=identity))
                for source_ref in saved['source_refs']:
                    item=conn.execute("SELECT task_id FROM research_evidence_objects WHERE id=? AND kind='excerpts' AND research_id=? AND input_revision=?",(source_ref,row['research_id'],saved['input_revision'])).fetchone()
                    if not item:raise not_found()
                    try:repository.provider_eligibility(context_for(conn,item[0]),source_ref)
                    except (ValueError,LookupError,PermissionError):raise ResearchError('SOURCE_PERMISSION_UNAVAILABLE',409,'资料读取资格已变化。') from None
                view=ResearchProjection.build(conn,owner,task_id=receipt['task_id'])['data']
                return {**receipt,'research_version':view['research_version'],'task_version':view['task_version'],
                    'execution':view['execution'],'status':view['status']}
            replay=ResearchService._replay(conn,pid,'paid-confirm','approval:'+preview_ref,key,operation_digest)
            if replay is not None:return current_receipt(replay)
            payload=json.loads(row['payload_json'])
            if (row['state']!='draft' or row['version']!=expected_preview_version or row['expires_at']<=int(time.time())
                    or digest(canonical(payload))!=row['payload_digest'] or payload.get('preview_digest')!=preview_digest):raise ResearchError('REVISION_CONFLICT',409,'付费预览已失效。')
            control=gate.check(conn,identity,pid,row['research_id'],scope='write')
            if control['version']!=payload['research_version'] or control['current_revision']!=payload['input_revision']:raise ResearchError('REVISION_CONFLICT',409,'问题已变化。')
            from .provider_evidence import read_preview_manifest
            from .preview_codec import preview_request,PreviewOutboundHandle
            manifest=read_preview_manifest(conn,self.store,identity,row['research_id'],payload['input_revision'],control['version'],tuple(payload['source_refs']),payload['summary'])
            encoded=preview_request(payload['summary'],tuple(PreviewOutboundHandle.model_validate(item) for item in manifest['handles']))
            if digest(canonical(manifest))!=payload['manifest_digest'] or encoded.outbound_request_digest!=payload['outbound_request_digest']:
                raise ResearchError('REVISION_CONFLICT',409,'获准外发资料或模板已变化。')
            if conn.execute("SELECT 1 FROM research_tasks WHERE research_id=? AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING')",(row['research_id'],)).fetchone():raise ResearchError('VERSION_CONFLICT',409,'已有活跃任务。')
            if conn.execute("SELECT 1 FROM research_reservations r JOIN research_tasks t ON t.id=r.task_id WHERE t.research_id=? AND r.status IN ('SENT','UNKNOWN')",(row['research_id'],)).fetchone():raise ResearchError('RECONCILIATION_REQUIRED',409,'旧收费结果未知。')
            tid,gid,sid=str(uuid4()),str(uuid4()),str(uuid4());timestamp=now()
            payload['plan_id']=str(uuid4())
            conn.execute("INSERT INTO research_grants(id,principal_id,principal_epoch,research_id,acl_epoch,scopes,status,created_at,funding_account_id,funding_permission_ref) VALUES(?,?,?,?,?,'[\"execute\",\"execute_paid\"]','active',?,?,?)",(gid,pid,payload['principal_epoch'],row['research_id'],payload['acl_epoch'],timestamp,row['account_id'],row['funding_source_ref']))
            conn.execute("""INSERT INTO research_tasks(id,research_id,principal_id,principal_epoch,owner_epoch,acl_epoch,grant_id,auth_generation,input_revision,input_digest,start_version,execution,phase,version,policy_revision,execution_mode,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,'QUEUED','analysis',1,?,'offline_probe',?,?)""",(tid,row['research_id'],pid,payload['principal_epoch'],payload['owner_epoch'],payload['acl_epoch'],gid,identity.generation,payload['input_revision'],payload['problem_digest'],control['version']+1,POLICY,timestamp,timestamp))
            conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state) VALUES(?,?,0,'model_report','PENDING')",(sid,tid))
            conn.execute("INSERT INTO research_attempts VALUES(?,1,'initial',?,?)",(tid,POLICY,payload['problem_digest']))
            conn.execute('UPDATE research_paid_approvals SET task_id=?,grant_id=?,confirmed_at=?,payload_json=?,payload_digest=? WHERE id=? AND state=\'draft\'',(tid,gid,int(time.time()),canonical(payload).decode(),digest(canonical(payload)),preview_ref))
            consent=packet_authority(conn,self.store,identity,lease,preview_ref,allow_confirming=True)
            packet=read_confirmed_provider_packet(conn,self.store,identity,consent)
            prepared=prepare_request(payload['summary'],packet);final_request_bytes(prepared)
            if prepared.request_digest!=payload['outbound_request_digest'] or [handle.outbound() for handle in packet.handles]!=payload['preview_manifest']['handles']:
                raise PermissionError('confirmed bytes differ from no-capability preview')
            payload.update(request_digest=prepared.request_digest,evidence_digest=prepared.evidence_digest)
            conn.execute("UPDATE research_paid_approvals SET payload_json=?,payload_digest=?,state='confirmed',version=version+1 WHERE id=? AND state='draft'",(canonical(payload).decode(),digest(canonical(payload)),preview_ref))
            conn.execute('UPDATE research_controls SET version=version+1,updated_at=? WHERE id=?',(timestamp,row['research_id']))
            result=dict(approval_ref=preview_ref,preview_version=expected_preview_version,task_id=tid,step_id=sid,mode='offline_probe',request_digest=prepared.request_digest,evidence_digest=prepared.evidence_digest,may_send=False)
            ResearchService._remember(conn,pid,'paid-confirm','approval:'+preview_ref,key,operation_digest,result)
            return current_receipt(result)


def erase_paid_private_inputs(store,conn,pid,job_id,*,owner_lease=None):
    version=conn.execute('SELECT version FROM research_schema').fetchone()[0]
    if version in (1,2,3,4,5):return
    if version not in (6,7,8,9,10,11,12,13,14,15):raise ResearchError('SCHEMA_UNSUPPORTED',503,'删除记录版本不支持。')
    if version==7:
        from .store import ResearchStore
        ResearchStore._check_v7(conn)
    elif version==8:
        from .store import ResearchStore
        ResearchStore._check_v8(conn)
    elif version==9:
        from .store import ResearchStore
        ResearchStore._check_v9(conn)
    elif version in (10,11,12,13,14,15):
        from .store import ResearchStore
        ResearchStore.check_runtime_version(conn)
    job=conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'",(job_id,)).fetchone()
    principal=conn.execute('SELECT * FROM research_principals WHERE id=?',(pid,)).fetchone()
    if (not job or not principal or principal['status']!='deleting' or principal['normalized_email']!=job['owner_email']
            or principal['session_generation']!=job['session_generation'] or principal['gate_id']!=job['gate_id']
            or job['database_binding']!=digest(str(store.path).encode())):raise PermissionError('actual deletion job required')
    if version in (10,11,12,13,14,15):
        from .formula_runtime import erase_for_deletion
        erase_for_deletion(conn,store=store,lease=owner_lease,pid=pid,job_id=job_id)
    conn.execute("UPDATE research_paid_approvals SET state='revoked',payload_json=NULL,version=version+1 WHERE principal_id=?",(pid,))
    if version in (9,10,11,12,13,14,15):
        from .method_result import erase_for_deletion
        erase_for_deletion(conn,store=store,lease=owner_lease,pid=pid,job_id=job_id)
    else:conn.execute("UPDATE research_provider_sessions SET candidate_json=NULL WHERE approval_id IN (SELECT id FROM research_paid_approvals WHERE principal_id=?)",(pid,))
    conn.execute("UPDATE research_dispatch_permits SET authorization_context_json=NULL,budget_basis_json=NULL,gate_identity_json=NULL WHERE paid_approval_ref IN (SELECT id FROM research_paid_approvals WHERE principal_id=?)",(pid,))
