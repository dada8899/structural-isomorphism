"""Financial9 single native plan. No external activation is installed."""
import json,os,time
from pathlib import Path
from uuid import uuid4
from .authorization import AuthorizationGate
from .errors import ResearchError,not_found
from .provider_schemas import canonical,digest,strict_json
from .paid_control import require_authenticated_action,_owner_binding
from .plan_preview_codec import plan_preview_request,template_digest
from .phenomenon_plan import parse_plan_candidate,make_plan_manifest
from .plan_native_schemas import NativePlanQuote,NativePlanResult,CONTRACT
from . import plan_native as ports,plan_native_financial as finance
from .plan_runtime import _input,UPPER,stamp,codec_digest

FUNDING,PREVIEWS,RUNS=finance.NAMES
_CAPS={};_FACTORY=object()

def uid():return str(uuid4())
def envelope(data):return {'schema_version':'structure-research-v1','contract_revision':CONTRACT,'data':data}
def row(conn,table,key):return conn.execute('SELECT * FROM '+table+' WHERE id=?',(key,)).fetchone()
def _write(conn,lease,table,key,values,verify):return finance._write(conn,lease,table,key,values,verify,_factory=finance._FACTORY)
def code_digest():
    from . import plan_native,plan_native_runtime,plan_native_schemas,plan_native_financial
    return digest(canonical({Path(m.__file__).name:digest(Path(m.__file__).read_bytes()) for m in (plan_native,plan_native_runtime,plan_native_schemas,plan_native_financial)}))


def _authority(conn,store,lease,consent,*,owned=None):
    _owner_binding(conn,store,consent['principal_id'],lease)
    funding=row(conn,FUNDING,1);pair=ports.installation(store)
    if not funding or not pair:raise PermissionError('native economic binding unavailable')
    provision,resource=pair
    if owned is not None:
        require_return(owned,resource,consent['dispatch_id'],consent['nonce'],consent['admission_digest'],consent['producer_digest'])
    else:provision.require()
    if (funding['account_id'],funding['economic_binding'],funding['authority_digest'])!=(consent['account_id'],consent['economic_binding'],consent['authority_digest']):raise PermissionError('native original economic binding differs')
    return funding,resource


def _active(conn,store,pid,generation):
    funding=row(conn,FUNDING,1);pair=ports.installation(store)
    if not funding or not pair:raise ResearchError('FUNDING_CLOSED',503,'原生资金执行尚未绑定；当前仅可预览本次费用上限。')
    if funding['principal_id']!=pid or funding['generation']!=generation:raise ResearchError('FUNDING_GRANT_REQUIRED',403,'当前账户未获得原生资金授权。')
    if finance.unresolved(conn,funding['account_id']):raise ResearchError('RECONCILIATION_REQUIRED',409,'同一账本仍有未核对发送。')
    provision,resource=pair;provision.require();resource.require()
    if funding['state']!='authorized' or funding['runtime_digest']!=provision.data()['runtime_digest']:raise ResearchError('FUNDING_CLOSED',503,'原生资金授权当前关闭。')
    return funding,resource


def quote():
    now=int(time.time())
    return NativePlanQuote(protocol='financial9-native-quote-v1',revision=uid(),purpose='phenomenon_plan_v1',provider='deepseek',model='deepseek-flash',declared_model_version='DeepSeek-V4.1-Flash-1017',declaration_observed_on='2026-10-18',currency='CNY',scale=6,
        peak_input_hit_units_per_million=40000,peak_input_miss_units_per_million=2000000,peak_output_units_per_million=8000000,context_bound=1048576,provider_output_bound=393216,max_output_tokens=4096,
        approved_upper_units=UPPER,codec_digest=codec_digest(),issued_at=now,valid_until=now+60,price_source='https://api-docs.deepseek.com/zh-cn/quick_start/pricing/')


def preview(service,identity,rid,request,key,source):
    pid=service._principal(identity);operation=digest(canonical(request.model_dump(mode='json')))
    require_authenticated_action(source,identity=identity,action='plan-preview',research_id=rid,key=key,body_digest=operation)
    with service.authorization.owner_gate(pid) as lease,service.store.transaction(write=True) as conn:
        control,saved,encoded=_input(conn,service,identity,pid,rid,request.input_revision,request.expected_research_version)
        old=conn.execute('SELECT * FROM '+PREVIEWS+' WHERE principal_id=? AND research_id=? AND key_digest=?',(pid,rid,digest(key.encode()))).fetchone()
        if old:
            if old['operation_digest']!=operation:raise ResearchError('IDEMPOTENCY_CONFLICT',409,'原操作标识已用于不同内容。')
            if old['state']!='draft' or old['expires_at']<=int(time.time()):raise ResearchError('PREVIEW_EXPIRED',409,'原费用预览已结束。')
            return envelope(preview_view(old,conn,service.store))
        q=quote();ref=uid()
        consent=dict(protocol='native-plan-consent-v1',principal_id=pid,generation=identity.generation,research_id=rid,input_revision=request.input_revision,research_version=control['version'],
            owner_epoch=control['owner_epoch'],acl_epoch=control['acl_epoch'],raw_input=encoded.manifest.input.summary,input_digest=saved['digest'],input_manifest_digest=encoded.input_manifest_digest,
            request_digest=encoded.outbound_request_digest,template_digest=encoded.template_digest,template_code_digest=codec_digest(),producer_digest=code_digest())
        cd=digest(canonical({'consent':consent,'quote':q.model_dump()}))
        def verify():_owner_binding(conn,service.store,pid,lease);service.authorization.check(conn,identity,pid,rid,scope='write')
        _write(conn,lease,PREVIEWS,ref,dict(research_id=rid,principal_id=pid,input_revision=request.input_revision,research_version=control['version'],consent_json=canonical(consent).decode(),consent_digest=cd,request_digest=encoded.outbound_request_digest,quote_json=canonical(q.model_dump()).decode(),expires_at=q.valid_until,state='draft',task_id=None,key_digest=digest(key.encode()),operation_digest=operation),verify)
        return envelope(preview_view(row(conn,PREVIEWS,ref),conn,service.store))


def preview_view(value,conn,store):
    consent=json.loads(value['consent_json']);q=json.loads(value['quote_json']);funding=row(conn,FUNDING,1)
    authorized=bool(ports.installation(store) and funding and funding['state']=='authorized' and funding['principal_id']==value['principal_id'] and funding['generation']==consent['generation'])
    return dict(preview_ref=value['id'],preview_digest=value['consent_digest'],request_digest=value['request_digest'],research_id=value['research_id'],input_revision=value['input_revision'],expected_research_version=value['research_version'],
        exact_input=consent['raw_input'],purpose='phenomenon_plan_v1',observation_rights='self_declared',state='awaiting_confirmation' if authorized else 'funding_closed',can_confirm=authorized,
        funding_reason=None if authorized else 'FUNDING_CLOSED',cash_evidence='not_observed',approved_upper_units=q['approved_upper_units'],currency='CNY',scale=6,quote=q,expires_at=value['expires_at'],
        explanation='用于确定下一步查什么；文献、数学关系和现实机制尚未验证。')


def confirm(service,identity,rid,request,key,source):
    pid=service._principal(identity);operation=digest(canonical(request.model_dump(mode='json')))
    require_authenticated_action(source,identity=identity,action='plan-confirm',research_id=rid,key=key,body_digest=operation)
    with service.authorization.owner_gate(pid) as lease,service.store.transaction(write=True) as conn:
        service.authorization.check(conn,identity,pid,rid,scope='write')
        replay=service._replay(conn,pid,'native-plan-confirm','r:'+rid,key,operation)
        if replay is not None:return replay
        value=row(conn,PREVIEWS,request.preview_ref)
        if not value or value['research_id']!=rid or value['principal_id']!=pid:raise not_found()
        if value['state']!='draft' or value['consent_digest']!=request.preview_digest or value['request_digest']!=request.request_digest:raise ResearchError('PREVIEW_CHANGED',409,'原生计划确认内容不同。')
        control,saved,encoded=_input(conn,service,identity,pid,rid,value['input_revision'],value['research_version'])
        q=NativePlanQuote.model_validate(json.loads(value['quote_json']));consent=json.loads(value['consent_json'])
        if value['expires_at']<=int(time.time()) or consent['producer_digest']!=code_digest() or q.codec_digest!=codec_digest() or encoded.outbound_request_digest!=consent['request_digest']:raise ResearchError('PREVIEW_EXPIRED',409,'输入、代码或报价已变化，请重新预览。')
        if request.approved_upper_units!=q.approved_upper_units or request.expected_research_version!=control['version']:raise ResearchError('INPUT_INVALID',422,'请确认原修订和本次费用上限。')
        funding,resource=_active(conn,service.store,pid,identity.generation)
        if conn.execute("SELECT 1 FROM research_tasks WHERE research_id=? AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING')",(rid,)).fetchone():raise ResearchError('TASK_ACTIVE',409,'当前研究已有未结束任务。')
        task,step,grant,dispatch,ref,nonce=[uid() for _ in range(6)];at=stamp()
        consent.update(task_id=task,step_id=step,grant_id=grant,grant_version=1,dispatch_id=dispatch,result_ref=ref,nonce=nonce,
            account_id=funding['account_id'],economic_binding=funding['economic_binding'],authority_digest=funding['authority_digest'],funding_version=funding['version'],grant_epoch=funding['grant_epoch'],credential_incarnation=funding['credential_incarnation'],research_version=control['version']+1,quote=q.model_dump(),mode=resource.mode,producer=resource.producer)
        conn.execute("INSERT INTO research_grants(id,principal_id,principal_epoch,research_id,acl_epoch,scopes,status,created_at) VALUES(?,?,?,?,?,'[\"execute\"]','active',?)",(grant,pid,control['owner_epoch'],rid,control['acl_epoch'],at))
        conn.execute("""INSERT INTO research_tasks(id,research_id,principal_id,principal_epoch,owner_epoch,acl_epoch,grant_id,auth_generation,input_revision,input_digest,start_version,execution,phase,version,policy_revision,execution_mode,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,'QUEUED','analysis',1,'native-plan-v1',?,?,?)""",(task,rid,pid,control['owner_epoch'],control['owner_epoch'],control['acl_epoch'],grant,identity.generation,value['input_revision'],saved['digest'],control['version']+1,resource.mode,at,at))
        conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state,version) VALUES(?,?,0,'phenomenon_plan','PENDING',1)",(step,task))
        conn.execute("INSERT INTO research_attempts VALUES(?,1,'initial','native-plan-v1',?)",(task,saved['digest']))
        def verify():_owner_binding(conn,service.store,pid,lease);service.authorization.check(conn,identity,pid,rid,scope='write')
        _write(conn,lease,PREVIEWS,value['id'],dict(state='confirmed',task_id=task),verify)
        _write(conn,lease,RUNS,dispatch,dict(task_id=task,result_ref=ref,preview_id=value['id'],account_id=funding['account_id'],financial_version=9,consent_json=canonical(consent).decode(),consent_digest=digest(canonical(consent)),admission_json=None,admission_digest=None,upper=q.approved_upper_units,nonce=nonce,state='approved',cost_state='unreserved',cleanup_state='pending',version=1,receipt_json=None,usage_json=None,result_json=None,commit_json=None,safe_code=None),verify)
        conn.execute('UPDATE research_controls SET version=version+1,updated_at=? WHERE id=? AND version=?',(at,rid,control['version']))
        from .runner import event_in
        event_in(conn,task,'queued','native_plan_confirmed')
        result=envelope(dict(task_id=task,result_ref=ref,state='queued',cash_evidence='not_observed',real_model_executed=False,recorded_at=None))
        service._remember(conn,pid,'native-plan-confirm','r:'+rid,key,operation,result);return result


def _current(conn,store,value):
    if value['consent_json'] is None:raise PermissionError('native consent erased')
    consent=json.loads(value['consent_json'])
    if digest(canonical(consent))!=value['consent_digest']:raise PermissionError('native consent digest differs')
    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(value['task_id'],)).fetchone()
    control=AuthorizationGate(store).check_task(conn,task)
    step=conn.execute('SELECT * FROM research_steps WHERE id=? AND task_id=?',(consent['step_id'],task['id'])).fetchone()
    revision=conn.execute('SELECT * FROM research_revisions WHERE research_id=? AND revision=?',(consent['research_id'],consent['input_revision'])).fetchone()
    grant=conn.execute('SELECT version FROM research_grants WHERE id=?',(consent['grant_id'],)).fetchone()
    if (task['policy_revision']!='native-plan-v1' or task['principal_id']!=consent['principal_id'] or task['grant_id']!=consent['grant_id'] or task['auth_generation']!=consent['generation']
        or task['input_digest']!=consent['input_digest'] or task['owner_epoch']!=consent['owner_epoch'] or task['acl_epoch']!=consent['acl_epoch']
        or control['version']!=consent['research_version'] or control['current_revision']!=consent['input_revision'] or not grant or grant[0]!=consent['grant_version']
        or not step or step['kind']!='phenomenon_plan' or not revision or revision['digest']!=consent['input_digest'] or json.loads(revision['problem_json'])['original_input']!=consent['raw_input']):raise PermissionError('actual native task/revision domain differs')
    expected=('QUEUED',1,'PENDING',1) if value['state'] in ('approved','reserved') else ('RUNNING',2,'SENDING',2) if value['state']=='consumed' else None
    if expected is None or (task['execution'],task['version'],step['state'],step['version'])!=expected:raise PermissionError('native execution transition differs')
    return consent,task,step,control


class NativeBalanceLease(ports._Sealed):
    __slots__=('store','resource','claim','consent','baseline','pid','reference','active','used')
    def __init__(self,store,resource,claim,consent,baseline,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('actual committed native balance claim required')
        self.store,self.resource,self.claim,self.consent,self.baseline=store,resource,claim,canonical(consent),canonical(baseline)
        self.pid,self.reference,self.active,self.used=os.getpid(),uid(),True,False;_CAPS[self.reference]=self
    def consume(self,resource):
        if not self.active or self.used or self.pid!=os.getpid() or _CAPS.get(self.reference) is not self or resource is not self.resource:raise PermissionError('native balance lease retired')
        with self.store.transaction() as conn:
            consent=strict_json(self.consent,32768)
            value=row(conn,RUNS,consent['dispatch_id']);_current(conn,self.store,value)
            funding=row(conn,FUNDING,1);account=row(conn,'research_funding_accounts',value['account_id'])
            if canonical([dict(funding),dict(account)])!=self.baseline or finance.unresolved(conn,account['id']):raise PermissionError('balance pre-GET claim/ledger changed')
        object.__setattr__(self,'used',True);return self.claim
    def close(self):object.__setattr__(self,'active',False);_CAPS.pop(self.reference,None)


class NativePlanSendLease(ports._Sealed):
    __slots__=('store','resource','lease','dispatch','raw','account_version','funding_version','pid','reference','active','used')
    def __init__(self,store,resource,lease,dispatch,raw,account_version,funding_version,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('actual native consumed claim required')
        self.store,self.resource,self.lease,self.dispatch,self.raw,self.account_version,self.funding_version=store,resource,lease,dispatch,raw,account_version,funding_version
        self.pid,self.reference,self.active,self.used=os.getpid(),uid(),True,False;_CAPS[self.reference]=self
    def consume(self,resource):
        if not self.active or self.used or self.pid!=os.getpid() or _CAPS.get(self.reference) is not self or resource is not self.resource:raise PermissionError('single native send lease required')
        self.lease.identity;resource.require()
        with self.store.transaction() as conn:
            value=row(conn,RUNS,self.dispatch);consent,task,step,control=_current(conn,self.store,value)
            funding,actual=_authority(conn,self.store,self.lease,consent)
            account=row(conn,'research_funding_accounts',value['account_id'])
            if funding['state']!='authorized' or account['status']!='unverified' or account['binding_id']!=consent['economic_binding'] or funding['grant_epoch']!=consent['grant_epoch'] or funding['credential_incarnation']!=consent['credential_incarnation'] or funding['version']!=self.funding_version or account['version']!=self.account_version or funding['balance_claim']!=self.dispatch or funding['balance_nonce']!=value['nonce'] or finance.unresolved(conn,account['id'],excluding=self.dispatch):raise PermissionError('current native money authority ended')
            if code_digest()!=consent['producer_digest'] or codec_digest()!=consent['template_code_digest'] or consent['quote']['valid_until']<=int(time.time()) or digest(self.raw)!=consent['request_digest']:raise PermissionError('native confirmed source/quote/bytes changed')
            result=self.raw,self.dispatch,value['nonce'],value['admission_digest'],consent['producer_digest']
        object.__setattr__(self,'used',True);return result
    def close(self):object.__setattr__(self,'active',False);_CAPS.pop(self.reference,None)


def require_balance(balance,resource,claim):
    if type(resource) is ports.ControlledNativeResource:
        if type(balance) is not ports.OwnedBalanceReceipt:raise PermissionError('actual controlled native balance required')
    else:
        module=ports.importlib.import_module(ports._family()+'.plan_runtime_transport')
        if type(balance) is not module.OwnedBalanceReceipt:raise PermissionError('canonical native balance type required')
    balance.require(resource,claim)


def require_return(owned,resource,dispatch,nonce,admission_digest,producer_digest):
    if type(resource) is ports.ControlledNativeResource:
        if type(owned) is not ports.OwnedNativeReturn:raise PermissionError('actual controlled native return required')
    else:
        module=ports.importlib.import_module(ports._family()+'.plan_runtime_transport')
        if type(owned) is not module.OwnedNativeReturn:raise PermissionError('canonical native return type required')
    owned.require(resource,dispatch,nonce,admission_digest,producer_digest)


def _money(conn,lease,account,held_delta,booked_delta,verify):
    if account['held']+held_delta<0:raise PermissionError('native held underflow')
    _write(conn,lease,'research_funding_accounts',account['id'],dict(held=account['held']+held_delta,upper_booked=account['upper_booked']+booked_delta,version=account['version']+1),verify)


def run_once(store,task_id):
    gate=AuthorizationGate(store)
    with store.transaction() as conn:
        value=conn.execute('SELECT * FROM '+RUNS+' WHERE task_id=?',(task_id,)).fetchone()
        if not value:raise not_found()
        if value['state']!='approved':return envelope(metadata(value))
        consent,task,step,control=_current(conn,store,value);pid=consent['principal_id'];dispatch=value['id']
    pair=ports.installation(store)
    if not pair:raise ResearchError('FUNDING_CLOSED',503,'原生执行资源当前关闭。')
    provision,resource=pair
    if not resource.flight.acquire(blocking=False):raise ResearchError('FUNDING_BUSY',409,'同一原生资金资源正在执行。')
    balance=balance_cap=pending=send=owned=None;primary=None;admission=None
    try:
        with gate.owner_gate(pid) as lease,store.transaction(write=True) as conn:
            value=row(conn,RUNS,dispatch);consent,task,step,control=_current(conn,store,value)
            funding,actual=_active(conn,store,pid,consent['generation'])
            account=row(conn,'research_funding_accounts',value['account_id'])
            if actual is not resource or funding['balance_claim'] is not None or funding['version']!=consent['funding_version']:raise ResearchError('FUNDING_STALE',409,'原资金版本已变化，请重新预览。')
            if consent['producer_digest']!=code_digest() or consent['quote']['valid_until']<=int(time.time()):raise ResearchError('PREVIEW_EXPIRED',409,'原生报价已过期，请重新预览。')
            verify=lambda:_authority(conn,store,lease,consent)
            _write(conn,lease,FUNDING,1,dict(balance_claim=dispatch,balance_nonce=value['nonce'],version=funding['version']+1),verify)
            baseline=[dict(row(conn,FUNDING,1)),dict(account)]
        claim=(dispatch,consent['nonce'])
        balance_cap=NativeBalanceLease(store,resource,claim,consent,baseline,_factory=_FACTORY)
        balance=resource.balance(balance_cap);require_balance(balance,resource,claim)
        with gate.owner_gate(pid) as lease,store.transaction(write=True) as conn:
            value=row(conn,RUNS,dispatch);current,task,step,control=_current(conn,store,value)
            funding=row(conn,FUNDING,1);account=row(conn,'research_funding_accounts',value['account_id'])
            if current!=consent or [dict(funding),dict(account)]!=baseline or funding['state']!='authorized' or finance.unresolved(conn,account['id']):raise ResearchError('FUNDING_STALE',409,'余额观察期间权限或账本已变化。')
            if consent['quote']['valid_until']<=int(time.time()) or code_digest()!=consent['producer_digest']:raise ResearchError('PREVIEW_EXPIRED',409,'原生报价或代码已变化。')
            exposure=account['settled']+account['upper_booked']+account['held']+value['upper']
            available=balance.balance_units-funding['risk_margin_units']-account['held']-account['upper_booked']
            if exposure>funding['approved_cap_units'] or available<value['upper']:raise ResearchError('BUDGET_EXHAUSTED',429,'项目剩余授权或当前可用余额不足；未发送模型请求。')
            encoded=plan_preview_request(make_plan_manifest({'input_kind':'user_observation_summary','summary':consent['raw_input']}))
            if encoded.outbound_request_digest!=consent['request_digest'] or encoded.input_manifest_digest!=consent['input_manifest_digest']:raise PermissionError('native approved bytes differ')
            admission=dict(protocol='financial-admission-v3',financial_version=9,mode=resource.mode,producer=resource.producer,consent_digest=value['consent_digest'],quote=consent['quote'],
                observed_balance=balance.audit(),ledger_before=dict(account),funding_before=dict(funding),request_digest=consent['request_digest'],producer_digest=consent['producer_digest'])
            verify=lambda:_authority(conn,store,lease,consent)
            _money(conn,lease,account,value['upper'],0,verify)
            _write(conn,lease,RUNS,dispatch,dict(state='reserved',cost_state='held',admission_json=canonical(admission).decode(),admission_digest=digest(canonical(admission)),version=value['version']+1),verify)
            account_version=account['version']+1;funding_version=funding['version']
        # DNS/TLS waits before consume, with neither Owner nor SQLite held.
        pending=resource.prepare_post()
        with gate.owner_gate(pid) as lease,store.transaction(write=True) as conn:
            value=row(conn,RUNS,dispatch);current,task,step,control=_current(conn,store,value)
            funding,actual=_authority(conn,store,lease,consent);account=row(conn,'research_funding_accounts',value['account_id'])
            if value['state']!='reserved' or funding['state']!='authorized' or funding['version']!=funding_version or account['version']!=account_version or finance.unresolved(conn,account['id'],excluding=dispatch):raise PermissionError('native authority changed during prepare')
            if consent['quote']['valid_until']<=int(time.time()) or code_digest()!=consent['producer_digest']:raise PermissionError('native quote changed during prepare')
            verify=lambda:_authority(conn,store,lease,consent)
            _write(conn,lease,RUNS,dispatch,dict(state='consumed',version=value['version']+1),verify)
            conn.execute("UPDATE research_steps SET state='SENDING',version=version+1 WHERE id=? AND state='PENDING'",(consent['step_id'],))
            from .runner import state_in
            state_in(conn,task_id,'RUNNING',safe_code='native_plan_consumed')
        with gate.owner_gate(pid) as lease:
            # Send cap checks the durable consumption using another connection.
            send=NativePlanSendLease(store,resource,lease,dispatch,encoded.raw,account_version,funding_version,_factory=_FACTORY)
            pending.write_first(send)
        owned=pending.receive()
        require_return(owned,resource,dispatch,consent['nonce'],digest(canonical(admission)),consent['producer_digest'])
        _commit_return(store,pid,dispatch,owned,consent,admission)
    except BaseException as error:
        primary=error
        try:_fail(store,pid,dispatch)
        except BaseException:
            # Keep the original failure; durable claim/held remains fail closed.
            ports.retire_attempts(resource)
    finally:
        errors=ports.retire_attempts(send,pending,owned,balance,balance_cap)
        if errors:errors+=ports.retire_attempts(resource)
        errors+=ports.retire_attempts(flight=resource.flight)
        try:_cleanup(store,pid,dispatch,errors)
        except BaseException as cleanup_error:
            ports.retire_attempts(resource)
            if primary is None:primary=cleanup_error
        if errors and primary is None:primary=ResearchError('CLEANUP_UNCERTAIN',503,'原生资源退休不完整；保留原结果标识，不会重发。')
    if primary is not None:raise primary
    with store.transaction() as conn:return envelope(metadata(row(conn,RUNS,dispatch)))


def _usage(owned):
    data=strict_json(owned.body,65536)
    if owned.status!=200 or type(data) is not dict or data.get('model')!='deepseek-flash':raise ValueError('untrusted native provider envelope')
    usage=data.get('usage')
    if type(usage) is not dict:raise ValueError('native usage unavailable')
    prompt,completion,total=(usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens'))
    if any(type(x) is not int for x in (prompt,completion,total)) or not 0<=prompt<=1048576 or not 0<=completion<=4096 or total!=prompt+completion:raise ValueError('native usage outside bound')
    return data,dict(protocol='native-plan-cost-v1',financial_version=9,prompt_tokens=prompt,completion_tokens=completion,total_tokens=total,booked_upper_units=UPPER,actual_charge_units=None,currency='CNY',scale=6)


def _commit_return(store,pid,dispatch,owned,original_consent,original_admission):
    resource=ports.installation(store)[1]
    with store.transaction() as conn:
        value=row(conn,RUNS,dispatch);consent=json.loads(value['consent_json']) if value['consent_json'] else original_consent
        # The exact original consent remains in the worker-owned immutable send
        # chain; deletion can erase the DB copy without erasing financial facts.
        if consent is None:raise PermissionError('native erased return needs original worker domain')
        admission=json.loads(value['admission_json']) if value['admission_json'] else original_admission
        if admission is None or digest(canonical(admission))!=value['admission_digest'] or admission['consent_digest']!=value['consent_digest']:raise PermissionError('original native admission differs')
        context={**consent,'admission_digest':value['admission_digest']}
    require_return(owned,resource,dispatch,consent['nonce'],value['admission_digest'],consent['producer_digest'])
    data=usage=proposal=None
    try:data,usage=_usage(owned)
    except (ValueError,TypeError):pass
    if data is not None:
        try:
            choices=data.get('choices')
            if type(choices) is not list or len(choices)!=1 or type(choices[0]) is not dict or choices[0].get('finish_reason')!='stop':raise ValueError('native body invalid')
            message=choices[0].get('message')
            if type(message) is not dict or type(message.get('content')) is not str:raise ValueError('native body invalid')
            proposal=parse_plan_candidate(message['content'])
        except (ValueError,TypeError):pass
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        value=row(conn,RUNS,dispatch)
        if value['state'] not in ('consumed','closed'):raise PermissionError('native return domain ended')
        verify=lambda:_authority(conn,store,lease,context,owned=owned)
        verify();account=row(conn,'research_funding_accounts',value['account_id'])
        active=True
        try:_current(conn,store,value)
        except (PermissionError,ResearchError):active=False
        if usage is not None:_money(conn,lease,account,-value['upper'],value['upper'],verify)
        at=stamp();result=None
        if active and proposal is not None and usage is not None:
            result=NativePlanResult(protocol='owned-native-plan-result-v2',purpose='phenomenon_plan_v1',result_ref=value['result_ref'],task_id=value['task_id'],research_id=consent['research_id'],input_revision=consent['input_revision'],
                input_digest=consent['input_digest'],request_digest=consent['request_digest'],consent_digest=value['consent_digest'],admission_digest=value['admission_digest'],recorded_at=at,
                execution_mode=resource.mode,producer=resource.producer,real_model_executed=resource.mode=='native_live',weight_identity_verified=False,literature_status='not_retrieved',mathematics_status='not_checked',mechanism_status='unverified',observation_rights='self_declared',query_state='draft_only',automatically_created_sources=0,proposal=proposal).model_dump(mode='json')
        receipt=dict(protocol='owned-native-return-v2',mode=owned.mode,dispatch=dispatch,nonce=consent['nonce'],admission_digest=value['admission_digest'],producer_digest=consent['producer_digest'],runtime_digest=admission['funding_before']['runtime_digest'],response_digest=digest(owned.body),status=owned.status,provider_model_label=None if data is None else data['model'],weight_identity_verified=False)
        commit=dict(protocol='native-plan-commit-v1',task_id=value['task_id'],result_ref=value['result_ref'],recorded_at=at,consent_digest=value['consent_digest'],admission_digest=value['admission_digest'],
            result_digest=None if result is None else digest(canonical(result)),receipt_digest=digest(canonical(receipt)),usage_digest=None if usage is None else digest(canonical(usage)),task_before=2,task_after=3,step_before=2,step_after=3)
        state='closed' if value['state']=='closed' else 'returned' if usage else 'unknown'
        _write(conn,lease,RUNS,dispatch,dict(state=state,cost_state='upper_booked' if usage else 'unknown',version=value['version']+1,receipt_json=canonical(receipt).decode(),usage_json=None if usage is None else canonical(usage).decode(),result_json=None if result is None else canonical(result).decode(),commit_json=canonical(commit).decode(),safe_code='access_ended' if not active else 'saved' if result else 'body_invalid' if usage else 'send_unknown'),verify)
        funding=row(conn,FUNDING,1);_write(conn,lease,FUNDING,1,dict(balance_claim=None,balance_nonce=None,version=funding['version']+1),verify)
        if active:
            from .runner import state_in
            conn.execute('UPDATE research_steps SET state=?,version=version+1 WHERE id=?',('SUCCEEDED' if result else 'FAILED' if usage else 'UNKNOWN',consent['step_id']))
            state_in(conn,value['task_id'],'COMPLETED' if result else 'FAILED' if usage else 'RECONCILING',safe_code='native_plan_saved' if result else 'native_plan_body_invalid' if usage else 'native_send_unknown')


def _fail(store,pid,dispatch):
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        value=row(conn,RUNS,dispatch)
        if not value or value['state'] not in ('approved','reserved','consumed'):return
        consent=json.loads(value['consent_json'])
        def verify():_owner_binding(conn,store,pid,lease)
        state='unknown' if value['state']=='consumed' else 'closed';cost='unknown' if state=='unknown' else 'unreserved'
        if value['state']=='reserved':
            account=row(conn,'research_funding_accounts',value['account_id']);_money(conn,lease,account,-value['upper'],0,verify)
        _write(conn,lease,RUNS,dispatch,dict(state=state,cost_state=cost,version=value['version']+1,safe_code='send_unknown' if state=='unknown' else 'not_sent'),verify)
        funding=row(conn,FUNDING,1)
        if funding['balance_claim']==dispatch:_write(conn,lease,FUNDING,1,dict(balance_claim=None,balance_nonce=None,version=funding['version']+1),verify)
        task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(value['task_id'],)).fetchone()
        if not task['stop_requested']:
            from .runner import state_in
            conn.execute('UPDATE research_steps SET state=?,version=version+1 WHERE id=?',('UNKNOWN' if state=='unknown' else 'FAILED',consent['step_id']))
            state_in(conn,value['task_id'],'RECONCILING' if state=='unknown' else 'FAILED',safe_code='native_send_unknown' if state=='unknown' else 'native_not_sent')


def _cleanup(store,pid,dispatch,errors):
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        value=row(conn,RUNS,dispatch)
        def verify():_owner_binding(conn,store,pid,lease)
        _write(conn,lease,RUNS,dispatch,dict(cleanup_state='uncertain' if errors else 'clean',version=value['version']+1),verify)
        if errors:
            funding=row(conn,FUNDING,1)
            if funding['state']=='authorized':_write(conn,lease,FUNDING,1,dict(state='blocked',version=funding['version']+1),verify)


def metadata(value):
    commit=json.loads(value['commit_json']) if value['commit_json'] else None
    consent=json.loads(value['consent_json']) if value['consent_json'] else None
    return dict(task_id=value['task_id'],result_ref=value['result_ref'],state='saved' if value['result_json'] else 'failed_insufficient' if value['state']=='returned' else 'pending_reconciliation' if value['state'] in ('consumed','unknown') else 'cancelled' if value['state']=='closed' and value['safe_code']!='not_sent' else 'failed_insufficient' if value['state']=='closed' else 'generating' if value['state']=='reserved' else 'queued',
        financial_version=9,execution_mode=consent['mode'] if consent else None,real_model_executed=bool(consent and consent['mode']=='native_live' and value['result_json']),cost_state=value['cost_state'],cleanup_state=value['cleanup_state'],safe_code=value['safe_code'],recorded_at=None if commit is None else commit['recorded_at'])


def read(service,identity,rid,ref,source):
    require_authenticated_action(source,identity=identity,action='plan-read',research_id=rid,task_id=ref)
    pid=service._principal(identity)
    with service.store.transaction() as conn:
        service.authorization.check(conn,identity,pid,rid)
        value=conn.execute('SELECT r.* FROM '+RUNS+' r JOIN research_tasks t ON t.id=r.task_id WHERE r.result_ref=? AND t.research_id=? AND t.principal_id=?',(ref,rid,pid)).fetchone()
        if not value:raise not_found()
        result=None
        if value['result_json']:
            result=NativePlanResult.model_validate(json.loads(value['result_json'])).model_dump(mode='json')
            consent=json.loads(value['consent_json']);admission=json.loads(value['admission_json']);commit=json.loads(value['commit_json']);receipt=json.loads(value['receipt_json'])
            task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(value['task_id'],)).fetchone();step=conn.execute('SELECT * FROM research_steps WHERE id=?',(consent['step_id'],)).fetchone()
            saved=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(rid,consent['input_revision'])).fetchone()
            if (value['state']!='returned' or task['execution']!='COMPLETED' or task['policy_revision']!='native-plan-v1' or task['version']!=3 or not step or step['task_id']!=task['id'] or step['kind']!='phenomenon_plan' or step['state']!='SUCCEEDED' or step['version']!=3
                or digest(canonical(consent))!=value['consent_digest'] or digest(canonical(admission))!=value['admission_digest'] or not saved or saved[0]!=consent['input_digest']
                or result['result_ref']!=value['result_ref'] or result['task_id']!=task['id'] or result['research_id']!=rid or result['input_digest']!=task['input_digest'] or result['recorded_at']!=commit['recorded_at']
                or commit['result_digest']!=digest(canonical(result)) or commit['receipt_digest']!=digest(canonical(receipt)) or receipt['admission_digest']!=value['admission_digest']):raise ResearchError('RESULT_UNAVAILABLE',503,'原生计划记录当前无法完整核对；不会重新外发。')
        return envelope({**metadata(value),'content':result})


def history(conn,rid,task_ids=None):
    if not conn.execute("SELECT 1 FROM sqlite_schema WHERE name=?",(RUNS,)).fetchone():return []
    query='SELECT r.* FROM '+RUNS+' r JOIN research_tasks t ON t.id=r.task_id WHERE t.research_id=?';args=[rid]
    if task_ids is not None:
        if not task_ids:return []
        query+=' AND t.id IN ('+','.join('?' for _ in task_ids)+')';args.extend(task_ids)
    return [metadata(value) for value in conn.execute(query+' ORDER BY t.start_version DESC,t.id DESC LIMIT 20',args)]


def stop_in(conn,store,lease,task_id):
    value=conn.execute('SELECT * FROM '+RUNS+' WHERE task_id=?',(task_id,)).fetchone()
    if not value or value['state'] in ('returned','closed'):return
    consent=json.loads(value['consent_json'])
    def verify():_owner_binding(conn,store,consent['principal_id'],lease)
    cost=value['cost_state']
    if value['state']=='reserved':
        account=row(conn,'research_funding_accounts',value['account_id']);_money(conn,lease,account,-value['upper'],0,verify);cost='unreserved'
    _write(conn,lease,RUNS,value['id'],dict(state='closed',cost_state=cost,version=value['version']+1,safe_code='cancelled'),verify)
    funding=row(conn,FUNDING,1)
    if value['state'] in ('approved','reserved') and funding['balance_claim']==value['id']:_write(conn,lease,FUNDING,1,dict(balance_claim=None,balance_nonce=None,version=funding['version']+1),verify)


def erase_in(conn,store,lease,pid,job_id):
    from .paid_control import verify_deletion_origin
    def verify():verify_deletion_origin(conn,store=store,lease=lease,job_id=job_id);_owner_binding(conn,store,pid,lease)
    verify()
    for value in conn.execute('SELECT r.* FROM '+RUNS+' r JOIN research_tasks t ON t.id=r.task_id WHERE t.principal_id=?',(pid,)).fetchall():
        cost=value['cost_state']
        if value['state']=='reserved':
            account=row(conn,'research_funding_accounts',value['account_id']);_money(conn,lease,account,-value['upper'],0,verify);cost='unreserved'
        _write(conn,lease,RUNS,value['id'],dict(state='closed',cost_state=cost,version=value['version']+1,consent_json=None,admission_json=None,result_json=None,commit_json=None,safe_code='access_ended'),verify)
    for value in conn.execute('SELECT * FROM '+PREVIEWS+' WHERE principal_id=?',(pid,)).fetchall():_write(conn,lease,PREVIEWS,value['id'],dict(state='closed',consent_json=None,research_id=None),verify)
    funding=row(conn,FUNDING,1)
    if funding and funding['principal_id']==pid:_write(conn,lease,FUNDING,1,dict(state='retired',principal_id=None,generation=None,version=funding['version']+1),verify)
