"""One fixed Financial8 self-observation workflow, closed outside fixtures.

Confirmation, financial dispatch and typed content are independently recorded.
The server's actual transport resource is required; JSON never grants a send.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
import json
from pathlib import Path
import time
from uuid import uuid4

from .authorization import AuthorizationGate
from .errors import ResearchError,not_found
from .provider_schemas import canonical,digest,strict_json
from .phenomenon_plan import make_plan_manifest,parse_plan_candidate
from .plan_preview_codec import plan_preview_request,template_digest
from .plan_schemas import PlanQuote,PlanResult,PlanAdmission
from . import plan_financial as finance
from .plan_transport import FixturePlanResource,OwnedPlanReturn
from .paid_control import require_authenticated_action,_owner_binding

_INSTALLATIONS={}
_SEND_CAPS={}
_SEND_FACTORY=object()
UPPER=2_129_920 # Full 1M-context miss bound plus4096 output, native micro-CNY.


def stamp():return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
def uid():return str(uuid4())
def envelope(value):return {'schema_version':'structure-research-v1','contract_revision':'funded-plan-v1','data':value}
def codec_digest():
    from . import plan_preview_codec,phenomenon_plan
    return digest(canonical({Path(m.__file__).name:digest(Path(m.__file__).read_bytes()) for m in (plan_preview_codec,phenomenon_plan)}))
def producer_code_digest():
    from . import plan_runtime,plan_transport,plan_financial,plan_schemas
    return digest(canonical({Path(m.__file__).name:digest(Path(m.__file__).read_bytes()) for m in (plan_runtime,plan_transport,plan_financial,plan_schemas)}))
def row(conn,table,key):return conn.execute('SELECT * FROM '+table+' WHERE id=?',(key,)).fetchone()
def _native_write(conn,lease,table,key,values,verify):
    # Private module code alone supplies fixed native verifiers. No public
    # service, HTTP field or installation port accepts a verifier/callback.
    return finance._write(conn,lease,table,key,values,verify=verify,_factory=finance._FACTORY)


@dataclass(frozen=True)
class _Installation:
    resource:FixturePlanResource
    path:str
    principal:str
    generation:str
    account_id:str
    economic_binding:str
    credential_incarnation:str


def install_fixture_funding(store,identity,source,resource):
    """Actual synthetic resource + existing controlled project grant, server only.

    This does not install a live credential or claim that the account is funded.
    Normal registration and HTTP callers have no installation route.
    """
    from .financial_guard import OfflineProjectRegistration
    from .paid_budget import activate_offline_in
    if type(resource) is not FixturePlanResource or type(source) is not OfflineProjectRegistration:raise TypeError('actual fixture and protected offline grant required')
    resource.require();pid=source._principal
    gate=AuthorizationGate(store)
    with gate.owner_gate(pid) as lease,store.transaction(write=True) as conn:
        def verify():_owner_binding(conn,store,pid,lease);gate.check(conn,identity,pid)
        verify();activate_offline_in(conn,store=store,actor=identity,lease=lease,source=source)
        facts=source._funding.current(conn,pid)
        if facts['binding_id']!=resource.economic_binding:raise PermissionError('credential resource economic binding differs')
        project=row(conn,'research_project_budgets',1)
        values=dict(status='fixture',principal_id=pid,generation=identity.generation,account_id=facts['account_id'],
            economic_binding=facts['binding_id'],credential_incarnation=resource.credential_incarnation,funding_epoch=facts['funding_epoch'],balance_claim=None,balance_nonce=None)
        old=row(conn,'research_plan_funding',1)
        if old:
            if any(old[k]!=v for k,v in values.items()):raise PermissionError('funding installation cannot reset a ledger or an unresolved dispatch')
        else:_native_write(conn,lease,'research_plan_funding',1,{**values,'version':1},verify)
    key=str(store.path)
    old=_INSTALLATIONS.get(key)
    if old and old.resource is not resource and old.resource.active:raise PermissionError('funding resource already installed')
    installed=_Installation(resource,key,pid,identity.generation,facts['account_id'],facts['binding_id'],resource.credential_incarnation)
    _INSTALLATIONS[key]=installed
    return installed


def uninstall_fixture_funding(store,installation):
    if _INSTALLATIONS.get(str(store.path)) is installation:_INSTALLATIONS.pop(str(store.path),None)
    installation.resource.close()


def _funding(conn,store,pid,generation):
    funding=row(conn,'research_plan_funding',1);installation=_INSTALLATIONS.get(str(store.path))
    if not funding or funding['status']!='fixture' or not installation:raise ResearchError('FUNDING_CLOSED',503,'资金执行入口尚未开放，问题已保留。')
    if (funding['principal_id']!=pid or funding['generation']!=generation or installation.principal!=pid or installation.generation!=generation):raise ResearchError('FUNDING_GRANT_REQUIRED',403,'当前账户未获得本项目资金授权。')
    finance.check_unknown(conn,funding['account_id'])
    if (funding['account_id'],funding['economic_binding'],funding['credential_incarnation'])!=(installation.account_id,installation.economic_binding,installation.credential_incarnation):raise ResearchError('FUNDING_STALE',409,'资金或凭据版本已变化，请重新预览。')
    installation.resource.require()
    account=row(conn,'research_funding_accounts',funding['account_id']);project=row(conn,'research_project_budgets',1)
    if not account or not project or project['funding_account_id']!=account['id'] or project['economic_binding']!=funding['economic_binding'] or account['binding_id']!=funding['economic_binding'] or account['funding_epoch']!=funding['funding_epoch'] or project['status']!='active' or account['status']!='active':raise ResearchError('FUNDING_STALE',409,'资金授权已变化。')
    return funding,account,project,installation


def _input(conn,service,identity,pid,rid,revision,version):
    control=service.authorization.check(conn,identity,pid,rid,scope='write')
    if control['current_revision']!=revision or control['version']!=version:raise ResearchError('REVISION_CONFLICT',409,'研究已变化，请重新预览。')
    saved=conn.execute('SELECT * FROM research_revisions WHERE research_id=? AND revision=?',(rid,revision)).fetchone()
    if not saved:raise not_found()
    problem=json.loads(saved['problem_json'])
    if problem['entry']!='phenomenon' or not problem['confirmed']:raise ResearchError('INPUT_INVALID',422,'请先保存并确认自己的现象自述。')
    try:manifest=make_plan_manifest({'input_kind':'user_observation_summary','summary':problem['original_input']})
    except ValueError:raise ResearchError('INPUT_INVALID',422,'仅支持8–1000字自己的观察自述；不能发送文献、代码或来源正文。') from None
    # This declaration and obvious-structure check do not establish ownership.
    if conn.execute('SELECT 1 FROM research_source_runs r JOIN research_tasks t ON t.id=r.task_id WHERE t.research_id=? AND t.input_revision=? LIMIT 1',(rid,revision)).fetchone():raise ResearchError('INPUT_SOURCE_UNSUPPORTED',422,'当前修订已有来源流程，请另存自己的观察自述。')
    return control,saved,plan_preview_request(manifest)


def _quote():
    now=int(time.time())
    return PlanQuote(protocol='financial8-plan-quote-v1',revision=uid(),purpose=finance.PURPOSE,provider='deepseek',model='deepseek-flash',
        declared_model_version='DeepSeek-V4.1-Flash-1017',declaration_observed_on='2026-10-18',currency='CNY',scale=6,
        peak_input_hit_units_per_million=40000,peak_input_miss_units_per_million=2000000,peak_output_units_per_million=8000000,
        context_bound=1048576,provider_output_bound=393216,max_output_tokens=4096,approved_upper_units=UPPER,
        codec_digest=codec_digest(),issued_at=now,valid_until=now+60,price_source='https://api-docs.deepseek.com/zh-cn/quick_start/pricing/')


def preview(service,identity,rid,request,key,source):
    pid=service._principal(identity);operation_digest=digest(canonical(request.model_dump(mode='json')))
    require_authenticated_action(source,identity=identity,action='plan-preview',research_id=rid,key=key,body_digest=operation_digest)
    with service.authorization.owner_gate(pid) as lease,service.store.transaction(write=True) as conn:
        control,saved,encoded=_input(conn,service,identity,pid,rid,request.input_revision,request.expected_research_version)
        funding,account,project,installation=_funding(conn,service.store,pid,identity.generation)
        def verify():_owner_binding(conn,service.store,pid,lease);service.authorization.check(conn,identity,pid,rid,scope='write')
        old=conn.execute('SELECT * FROM research_plan_previews WHERE principal_id=? AND research_id=? AND key_digest=?',(pid,rid,digest(key.encode()))).fetchone()
        if old:
            if old['operation_digest']!=operation_digest:raise ResearchError('IDEMPOTENCY_CONFLICT',409,'该操作标识已用于其他内容。')
            if old['state']!='draft' or old['expires_at']<=int(time.time()):raise ResearchError('PREVIEW_EXPIRED',409,'原预览已结束，请重新预览。')
            return envelope(_preview_view(old))
        quote=_quote();qid=uid()
        payload=dict(raw_input=encoded.manifest.input.summary,input_manifest=encoded.manifest.model_dump(mode='json'),
            input_manifest_digest=encoded.input_manifest_digest,input_digest=saved['digest'],request_digest=encoded.outbound_request_digest,
            template_digest=template_digest(),template_code_digest=codec_digest(),principal_id=pid,generation=identity.generation,
            principal_epoch=control['owner_epoch'],owner_epoch=control['owner_epoch'],acl_epoch=control['acl_epoch'],
            funding_version=funding['version'],economic_binding=funding['economic_binding'],credential_incarnation=funding['credential_incarnation'],funding_epoch=funding['funding_epoch'])
        pd=digest(canonical({'payload':payload,'quote':quote.model_dump(),'purpose':finance.PURPOSE,'input_revision':request.input_revision,'research_version':control['version']}))
        _native_write(conn,lease,'research_plan_previews',qid,dict(research_id=rid,principal_id=pid,input_revision=request.input_revision,research_version=control['version'],payload_json=canonical(payload).decode(),preview_digest=pd,request_digest=encoded.outbound_request_digest,quote_json=canonical(quote.model_dump()).decode(),expires_at=quote.valid_until,state='draft',task_id=None,key_digest=digest(key.encode()),operation_digest=operation_digest),verify)
        return envelope(_preview_view(row(conn,'research_plan_previews',qid)))


def _preview_view(value):
    payload=json.loads(value['payload_json']);quote=json.loads(value['quote_json'])
    return dict(preview_ref=value['id'],preview_digest=value['preview_digest'],request_digest=value['request_digest'],
        research_id=value['research_id'],input_revision=value['input_revision'],expected_research_version=value['research_version'],
        state='awaiting_confirmation',exact_input=payload['raw_input'],purpose=finance.PURPOSE,observation_rights='self_declared',
        approved_upper_units=quote['approved_upper_units'],currency='CNY',scale=6,quote=quote,expires_at=value['expires_at'],
        explanation='用于确定下一步查什么；文献、数学关系和现实机制尚未验证。')


def _confirmed_input(conn,service,identity,pid,preview):
    control,saved,encoded=_input(conn,service,identity,pid,preview['research_id'],preview['input_revision'],preview['research_version'])
    payload=json.loads(preview['payload_json']);quote=PlanQuote.model_validate(json.loads(preview['quote_json']))
    if quote.valid_until<=int(time.time()):raise ResearchError('PREVIEW_EXPIRED',409,'报价已过期，请重新预览。')
    if (saved['digest']!=payload['input_digest'] or encoded.manifest.input.summary!=payload['raw_input'] or encoded.input_manifest_digest!=payload['input_manifest_digest'] or encoded.outbound_request_digest!=preview['request_digest'] or template_digest()!=payload['template_digest'] or codec_digest()!=payload['template_code_digest'] or codec_digest()!=quote.codec_digest):raise ResearchError('PREVIEW_CHANGED',409,'输入、模板或报价已变化，请重新预览。')
    f,a,p,i=_funding(conn,service.store,pid,identity.generation)
    if any(payload[k]!=f[k] for k in ('economic_binding','credential_incarnation','funding_epoch')) or payload['funding_version']!=f['version']:raise ResearchError('FUNDING_STALE',409,'资金依据已变化，请重新预览。')
    return control,payload,quote,encoded,f,a,p,i


def confirm(service,identity,rid,request,key,source):
    pid=service._principal(identity);operation_digest=digest(canonical(request.model_dump(mode='json')))
    require_authenticated_action(source,identity=identity,action='plan-confirm',research_id=rid,key=key,body_digest=operation_digest)
    with service.authorization.owner_gate(pid) as lease,service.store.transaction(write=True) as conn:
        service.authorization.check(conn,identity,pid,rid,scope='write')
        replay=service._replay(conn,pid,'plan-confirm','r:'+rid,key,operation_digest)
        if replay is not None:return replay
        value=row(conn,'research_plan_previews',request.preview_ref)
        if not value or value['principal_id']!=pid or value['research_id']!=rid:raise not_found()
        if value['state']!='draft' or request.preview_digest!=value['preview_digest'] or request.request_digest!=value['request_digest'] or request.expected_research_version!=value['research_version']:raise ResearchError('PREVIEW_CHANGED',409,'确认内容已变化，请重新预览。')
        control,payload,quote,encoded,funding,account,project,installation=_confirmed_input(conn,service,identity,pid,value)
        if request.approved_upper_units!=quote.approved_upper_units:raise ResearchError('INPUT_INVALID',422,'请确认本次显示的费用上限。')
        if conn.execute("SELECT 1 FROM research_tasks WHERE research_id=? AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING')",(rid,)).fetchone():raise ResearchError('TASK_ACTIVE',409,'请先查看或停止当前任务。')
        task,step,grant,dispatch,ref,nonce=[uid() for _ in range(6)];at=stamp()
        conn.execute("INSERT INTO research_grants(id,principal_id,principal_epoch,research_id,acl_epoch,scopes,status,created_at) VALUES(?,?,?,?,?,'[\"execute\"]','active',?)",(grant,pid,control['owner_epoch'],rid,control['acl_epoch'],at))
        conn.execute("""INSERT INTO research_tasks(id,research_id,principal_id,principal_epoch,owner_epoch,acl_epoch,grant_id,auth_generation,input_revision,input_digest,start_version,execution,phase,version,policy_revision,execution_mode,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,'QUEUED','analysis',1,'funded-plan-v1','offline_probe',?,?)""",(task,rid,pid,control['owner_epoch'],control['owner_epoch'],control['acl_epoch'],grant,identity.generation,value['input_revision'],payload['input_digest'],control['version']+1,at,at))
        conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state,version) VALUES(?,?,0,'phenomenon_plan','PENDING',1)",(step,task))
        conn.execute("INSERT INTO research_attempts VALUES(?,1,'initial','funded-plan-v1',?)",(task,payload['input_digest']))
        admission=dict(protocol=finance.ADMISSION,producer_source_version='plan-producer-v1',producer_code_digest=producer_code_digest(),financial_version=8,purpose=finance.PURPOSE,producer=finance.PRODUCER,mode='fixture',
            task_id=task,step_id=step,grant_id=grant,grant_version=1,dispatch_id=dispatch,result_ref=ref,nonce=nonce,preview_ref=value['id'],preview_digest=value['preview_digest'],
            input_revision=value['input_revision'],research_id=rid,research_version=control['version']+1,quote=quote.model_dump(),approved_upper=request.approved_upper_units,**payload)
        admission=PlanAdmission.model_validate(admission).model_dump(mode='json')
        def verify():_owner_binding(conn,service.store,pid,lease);service.authorization.check(conn,identity,pid,rid,scope='write')
        _native_write(conn,lease,'research_plan_previews',value['id'],dict(state='confirmed',task_id=task),verify)
        _native_write(conn,lease,'research_plan_dispatches',dispatch,dict(task_id=task,result_ref=ref,preview_id=value['id'],account_id=account['id'],admission_version=finance.ADMISSION,financial_version=8,admission_json=canonical(admission).decode(),admission_digest=digest(canonical(admission)),upper=request.approved_upper_units,state='approved',cost_state='unreserved',safe_code=None,nonce=nonce,version=1,receipt_json=None,usage_json=None,result_json=None,commit_json=None),verify)
        conn.execute('UPDATE research_controls SET version=version+1,updated_at=? WHERE id=? AND version=?',(at,rid,control['version']))
        from .runner import event_in
        event_in(conn,task,'queued','plan_confirmed')
        result=envelope(dict(task_id=task,result_ref=ref,state='queued',funding_state='approved_not_sent',plan_generation_ran=False,recorded_at=None))
        service._remember(conn,pid,'plan-confirm','r:'+rid,key,operation_digest,result)
        return result


def _task_current(conn,store,value):
    admission=PlanAdmission.model_validate(json.loads(value['admission_json'])).model_dump(mode='json') if value['admission_json'] else None
    if not admission or digest(canonical(admission))!=value['admission_digest']:raise PermissionError('protected original admission unavailable')
    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(value['task_id'],)).fetchone()
    if not task:raise PermissionError('original task missing')
    control=AuthorizationGate(store).check_task(conn,task)
    step=conn.execute('SELECT * FROM research_steps WHERE id=? AND task_id=?',(admission['step_id'],task['id'])).fetchone()
    saved=conn.execute('SELECT * FROM research_revisions WHERE research_id=? AND revision=?',(admission['research_id'],admission['input_revision'])).fetchone()
    preview=row(conn,'research_plan_previews',value['preview_id'])
    grant=conn.execute('SELECT version FROM research_grants WHERE id=?',(admission['grant_id'],)).fetchone()
    if (not grant or grant[0]!=admission['grant_version'] or task['policy_revision']!='funded-plan-v1' or task['principal_id']!=admission['principal_id'] or task['grant_id']!=admission['grant_id']
        or task['auth_generation']!=admission['generation'] or task['input_digest']!=admission['input_digest'] or task['research_id']!=admission['research_id']
        or task['input_revision']!=admission['input_revision'] or task['principal_epoch']!=admission['principal_epoch'] or task['owner_epoch']!=admission['owner_epoch']
        or task['acl_epoch']!=admission['acl_epoch'] or control['version']!=admission['research_version'] or control['current_revision']!=admission['input_revision']
        or not saved or saved['digest']!=admission['input_digest'] or json.loads(saved['problem_json'])['original_input']!=admission['raw_input']
        or not step or step['kind']!='phenomenon_plan' or not preview or preview['state']!='confirmed' or preview['task_id']!=task['id']
        or preview['preview_digest']!=admission['preview_digest'] or preview['request_digest']!=admission['request_digest']):raise PermissionError('task and plan admission differ')
    expected=('QUEUED',1,'PENDING',1) if value['state']=='approved' else ('RUNNING',2,'SENDING',2) if value['state']=='consumed' else None
    if expected is None or (task['execution'],task['version'],step['state'],step['version'])!=expected:raise PermissionError('actual task/step transition differs')
    return admission,task,step,control


def _funding_snapshot(conn,funding,account,project):
    # This baseline is captured BEFORE GET, never inferred from a later settlement.
    return {'funding':dict(funding),'account':dict(account),'project':dict(project)}


def _money(conn,lease,account,*,held_delta=0,booked_delta=0):
    from .paid_budget import _write
    if account['held']+held_delta<0:raise PermissionError('held ledger underflow')
    changed=_write(conn,lease,'money',account['id'],'research_funding_accounts',account['id'],
        'UPDATE research_funding_accounts SET held=held+?,upper_booked=upper_booked+?,version=version+1 WHERE id=? AND version=?',
        (held_delta,booked_delta,account['id'],account['version'])).rowcount
    if changed!=1:raise PermissionError('shared economic ledger changed')
    from .paid_budget import _bump_project
    _bump_project(conn,lease)


def _financial_verifier(conn,store,lease,admission,*,owned=None):
    _owner_binding(conn,store,admission['principal_id'],lease)
    f=row(conn,'research_plan_funding',1)
    if owned is not None:
        installation=_INSTALLATIONS.get(str(store.path))
        if not installation:raise PermissionError('actual return installation unavailable')
        owned.require(installation.resource,admission['dispatch_id'],admission['nonce'],digest(canonical(admission)))
        if f and f['status']=='retired' and (f['economic_binding'],f['credential_incarnation'],f['funding_epoch'])==(admission['economic_binding'],admission['credential_incarnation'],admission['funding_epoch']):return
    if not f or f['account_id'] is None or (f['principal_id'],f['generation'],f['economic_binding'],f['credential_incarnation'],f['funding_epoch'])!=(admission['principal_id'],admission['generation'],admission['economic_binding'],admission['credential_incarnation'],admission['funding_epoch']):raise PermissionError('original funding identity differs')


def _send_financial_current(conn,store,lease,value,admission,*,account_version,project_version,funding_version):
    """First-write authorization only; authentic late costs use the verifier above."""
    _financial_verifier(conn,store,lease,admission)
    funding=row(conn,'research_plan_funding',1)
    account=row(conn,'research_funding_accounts',value['account_id'])
    project=row(conn,'research_project_budgets',1)
    if (not account or not project or funding['status']!='fixture' or project['status']!='active' or account['status']!='active'
        or funding['version']!=funding_version or project['version']!=project_version or account['version']!=account_version
        or funding['account_id']!=account['id'] or project['funding_account_id']!=account['id']
        or account['binding_id']!=admission['economic_binding'] or project['economic_binding']!=admission['economic_binding']
        or account['funding_epoch']!=admission['funding_epoch'] or account['provider']!='deepseek' or account['currency']!='CNY' or account['scale']!=6):
        raise PermissionError('current financial permission ended before first write')
    other=conn.execute("SELECT 1 FROM research_plan_dispatches WHERE account_id=? AND id!=? AND (state IN ('consumed','unknown') OR cost_state='unknown' OR (state='closed' AND cost_state='held')) LIMIT 1",(account['id'],value['id'])).fetchone()
    legacy=conn.execute("SELECT 1 FROM research_reservations WHERE account_id=? AND status='UNKNOWN' LIMIT 1",(account['id'],)).fetchone()
    if other or legacy:raise ResearchError('RECONCILIATION_REQUIRED',409,'此资金账户有其他未核对发送，暂停本次外发。')


def run_once(store,task_id):
    """Real fixture worker. Restart after consume only reconciles; never sends again."""
    gate=AuthorizationGate(store)
    with store.transaction() as conn:
        value=conn.execute('SELECT * FROM research_plan_dispatches WHERE task_id=?',(task_id,)).fetchone()
        if not value:raise not_found()
        if value['state']!='approved':return envelope(metadata(value))
        admission,task,step,control=_task_current(conn,store,value)
        pid=admission['principal_id'];dispatch=value['id'];nonce=value['nonce'];admission_digest=value['admission_digest']
    installation=_INSTALLATIONS.get(str(store.path))
    if not installation:raise ResearchError('FUNDING_CLOSED',503,'资金执行入口关闭；未发送模型请求。')
    resource=installation.resource
    if not resource.flight.acquire(blocking=False):raise ResearchError('FUNDING_BUSY',409,'同一经济账户正在核对资金，请保留原操作标识。')
    owned=None;pending=None;consumed=False;claimed=False
    try:
        with gate.owner_gate(pid) as lease,store.transaction(write=True) as conn:
            value=row(conn,'research_plan_dispatches',dispatch)
            if value['state']!='approved':return envelope(metadata(value))
            admission,task,step,control=_task_current(conn,store,value)
            quote=PlanQuote.model_validate(admission['quote'])
            if quote.valid_until<=int(time.time()) or codec_digest()!=quote.codec_digest or admission['producer_code_digest']!=producer_code_digest():raise ResearchError('PREVIEW_EXPIRED',409,'报价或模板已过期，请重新预览。')
            funding,account,project,actual=_funding(conn,store,pid,admission['generation'])
            if actual is not installation or funding['version']!=admission['funding_version'] or funding['balance_claim'] is not None:raise ResearchError('FUNDING_STALE',409,'资金版本或核对状态已变化，请重新预览。')
            verify=lambda:_financial_verifier(conn,store,lease,admission)
            _native_write(conn,lease,'research_plan_funding',1,dict(balance_claim=dispatch,balance_nonce=nonce,version=funding['version']+1),verify)
            baseline=_funding_snapshot(conn,row(conn,'research_plan_funding',1),account,project)
            claimed=True
        # UNKNOWN/claim and economic incarnation were checked before credential use.
        balance,balance_digest=resource.balance()
        with gate.owner_gate(pid) as lease,store.transaction(write=True) as conn:
            value=row(conn,'research_plan_dispatches',dispatch)
            current_admission,task,step,control=_task_current(conn,store,value)
            funding=row(conn,'research_plan_funding',1);account=row(conn,'research_funding_accounts',value['account_id']);project=row(conn,'research_project_budgets',1)
            if value['state']!='approved' or current_admission!=admission or _funding_snapshot(conn,funding,account,project)!=baseline:raise ResearchError('FUNDING_STALE',409,'余额核对期间账本或授权已变化，请重新预览。')
            resource.require();quote=PlanQuote.model_validate(admission['quote'])
            if quote.valid_until<=int(time.time()) or codec_digest()!=quote.codec_digest or admission['producer_code_digest']!=producer_code_digest():raise ResearchError('PREVIEW_EXPIRED',409,'报价已过期，请重新预览。')
            finance.check_unknown(conn,account['id'])
            exposure=account['settled']+account['upper_booked']+account['held']+value['upper']
            if exposure>min(project['authorized_cap'],account['cap']) or balance-account['other_use_margin_units']-account['held']-account['upper_booked']<value['upper']:raise ResearchError('BUDGET_EXHAUSTED',429,'共享预算或当前余额不足；本次未发送模型请求。')
            encoded=plan_preview_request(make_plan_manifest({'input_kind':'user_observation_summary','summary':admission['raw_input']}))
            if encoded.outbound_request_digest!=admission['request_digest'] or encoded.input_manifest_digest!=admission['input_manifest_digest'] or encoded.template_digest!=admission['template_digest']:raise PermissionError('confirmed bytes changed')
            verify=lambda:_financial_verifier(conn,store,lease,admission)
            _native_write(conn,lease,'research_plan_dispatches',dispatch,dict(state='reserved',cost_state='held',version=value['version']+1),verify)
            _money(conn,lease,account,held_delta=value['upper'])
            value=row(conn,'research_plan_dispatches',dispatch)
            _native_write(conn,lease,'research_plan_dispatches',dispatch,dict(state='consumed',version=value['version']+1),verify)
            conn.execute("UPDATE research_steps SET state='SENDING',version=version+1 WHERE id=? AND state='PENDING'",(step['id'],))
            from .runner import state_in
            state_in(conn,task_id,'RUNNING',safe_code='plan_dispatch_consumed')
            consumed_account_version=account['version']+1
            consumed_project_version=project['version']+1
            consumed_funding_version=funding['version']
        consumed=True
        # Preconnection has no application bytes and waits outside Owner/SQLite.
        pending=resource.prepare_post()
        # A distinct native connection proves COMMIT before the first socket write.
        with gate.owner_gate(pid) as lease:
            with store.transaction() as conn:
                value=row(conn,'research_plan_dispatches',dispatch);admission_now,task,step,control=_task_current(conn,store,value)
                account=row(conn,'research_funding_accounts',value['account_id']);funding=row(conn,'research_plan_funding',1)
                _send_financial_current(conn,store,lease,value,admission,account_version=consumed_account_version,
                    project_version=consumed_project_version,funding_version=consumed_funding_version)
                if (value['state']!='consumed' or value['nonce']!=nonce or value['admission_digest']!=admission_digest or account['version']!=consumed_account_version
                    or funding['balance_claim']!=dispatch or funding['balance_nonce']!=nonce or quote.valid_until<=int(time.time())
                    or admission_now!=admission or step['state']!='SENDING' or task['execution']!='RUNNING'):raise PermissionError('committed consumed dispatch no longer current')
            resource.require()
            # Actual resource + native lifetime, not JSON, authorizes exactly this send.
            cap=_PlanSendLease(store,resource,lease,dispatch,encoded.raw,consumed_account_version,
                consumed_project_version,consumed_funding_version,_factory=_SEND_FACTORY)
            try:pending.write_first(cap)
            finally:cap.close()
        # Neither an Owner lock nor a DB transaction spans response waiting.
        owned=pending.receive()
        owned.require(resource,dispatch,nonce,admission_digest)
        _commit_return(store,pid,dispatch,admission,owned,balance_digest)
        with store.transaction() as conn:return envelope(metadata(row(conn,'research_plan_dispatches',dispatch)))
    except BaseException:
        if claimed or not consumed:
            _end_failed(store,pid,dispatch,admission,consumed)
        raise
    finally:
        if pending:pending.close()
        if owned:owned.close()
        resource.flight.release()


def _usage_return(owned):
    """Transport usage is checked independently of model proposal validation."""
    data=strict_json(owned.body,65536)
    if owned.status!=200 or type(data) is not dict:raise ValueError('unusable provider envelope')
    usage=data.get('usage');model=data.get('model')
    if type(usage) is not dict or model!='deepseek-flash':raise ValueError('unknown usage or model')
    prompt=usage.get('prompt_tokens');completion=usage.get('completion_tokens');total=usage.get('total_tokens')
    if any(type(x) is not int for x in (prompt,completion,total)) or not 0<=prompt<=1048576 or not 0<=completion<=4096 or prompt+completion!=total:raise ValueError('usage outside approved upper')
    estimate=(prompt*2_000_000+completion*8_000_000+999999)//1_000_000
    if estimate>UPPER:raise ValueError('usage exceeds approved cap')
    return data,dict(prompt_tokens=prompt,completion_tokens=completion,total_tokens=total,usage_priced_estimate_units=estimate,
        actual_charge_units=None,cost_kind='upper_booked',booked_upper_units=UPPER,currency='CNY',scale=6)


def _commit_return(store,pid,dispatch,admission,owned,balance_digest):
    installation=_INSTALLATIONS.get(str(store.path))
    if not installation:raise PermissionError('actual return resource unavailable')
    owned.require(installation.resource,dispatch,admission['nonce'],digest(canonical(admission)))
    data=usage=proposal=None
    try:data,usage=_usage_return(owned)
    except (ValueError,TypeError):pass
    if data is not None:
        try:
            choices=data.get('choices')
            if type(choices) is not list or len(choices)!=1 or type(choices[0]) is not dict or choices[0].get('finish_reason')!='stop':raise ValueError('incomplete plan body')
            message=choices[0].get('message')
            if type(message) is not dict or type(message.get('content')) is not str:raise ValueError('invalid plan message')
            proposal=parse_plan_candidate(message['content'])
        except (ValueError,TypeError,KeyError):pass
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        value=row(conn,'research_plan_dispatches',dispatch)
        if value['state'] not in ('consumed','closed') or value['nonce']!=admission['nonce']:raise PermissionError('late return domain changed')
        verify=lambda:_financial_verifier(conn,store,lease,admission,owned=owned)
        verify();account=row(conn,'research_funding_accounts',value['account_id'])
        receipt=dict(protocol='owned-plan-http-return-v1',producer=finance.PRODUCER,mode='fixture',pid=owned.pid,
            dispatch_id=dispatch,nonce=owned.claim_nonce,admission_digest=value['admission_digest'],response_digest=digest(owned.body),status=owned.status,
            balance_evidence_digest=balance_digest,response_model=None if data is None else data['model'],declared_model_version=admission['quote']['declared_model_version'],producer_code_digest=admission['producer_code_digest'],exact_weights_verified=False)
        active=True
        try:_task_current(conn,store,value)
        except (PermissionError,ResearchError):active=False
        if usage is not None:_money(conn,lease,account,held_delta=-value['upper'],booked_delta=value['upper'])
        at=stamp();result=None
        if active and proposal is not None and usage is not None:
            result=PlanResult(protocol='owned-phenomenon-plan-result-v1',purpose=finance.PURPOSE,result_ref=value['result_ref'],task_id=value['task_id'],research_id=admission['research_id'],
                input_revision=admission['input_revision'],input_digest=admission['input_digest'],request_digest=admission['request_digest'],admission_digest=value['admission_digest'],recorded_at=at,
                execution_mode='fixture',plan_generation_ran=True,real_model_executed=False,literature_status='not_retrieved',mathematics_status='not_checked',mechanism_status='unverified',observation_rights='self_declared',query_state='draft_only',automatically_created_sources=0,proposal=proposal).model_dump(mode='json')
        commit=dict(protocol='plan-commit-v1',task_before=2,task_after=3,step_before=2,step_after=3,research_version=admission['research_version'],recorded_at=at,task_id=value['task_id'],result_ref=value['result_ref'],admission_digest=value['admission_digest'],request_digest=admission['request_digest'],result_digest=None if result is None else digest(canonical(result)),receipt_digest=digest(canonical(receipt)),usage_digest=None if usage is None else digest(canonical(usage)))
        state='closed' if value['state']=='closed' else 'returned' if usage is not None else 'unknown'
        _native_write(conn,lease,'research_plan_dispatches',dispatch,dict(state=state,safe_code='access_ended' if not active else 'saved' if result else 'body_invalid' if usage else 'send_unknown',cost_state='upper_booked' if usage is not None else 'unknown',version=value['version']+1,receipt_json=canonical(receipt).decode(),usage_json=None if usage is None else canonical(usage).decode(),result_json=None if result is None else canonical(result).decode(),commit_json=canonical(commit).decode()),verify)
        funding=row(conn,'research_plan_funding',1)
        _native_write(conn,lease,'research_plan_funding',1,dict(balance_claim=None,balance_nonce=None,version=funding['version']+1),verify)
        if active:
            from .runner import state_in
            conn.execute('UPDATE research_steps SET state=?,version=version+1 WHERE id=?',('SUCCEEDED' if result else 'UNKNOWN' if usage is None else 'FAILED',admission['step_id']))
            state_in(conn,value['task_id'],'COMPLETED' if result else 'RECONCILING' if usage is None else 'FAILED',safe_code='plan_saved' if result else 'plan_body_invalid' if usage else 'plan_send_unknown')


def _end_failed(store,pid,dispatch,admission,consumed):
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        value=row(conn,'research_plan_dispatches',dispatch)
        if not value or value['state'] not in ('approved','reserved','consumed'):return
        verify=lambda:_financial_verifier(conn,store,lease,admission)
        state='unknown' if consumed or value['state']=='consumed' else 'closed'
        _native_write(conn,lease,'research_plan_dispatches',dispatch,dict(state=state,safe_code='send_unknown' if state=='unknown' else 'not_sent',cost_state='unknown' if state=='unknown' else value['cost_state'],version=value['version']+1),verify)
        funding=row(conn,'research_plan_funding',1)
        if funding['balance_claim']==dispatch:_native_write(conn,lease,'research_plan_funding',1,dict(balance_claim=None,balance_nonce=None,version=funding['version']+1),verify)
        task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(value['task_id'],)).fetchone()
        if task and not task['stop_requested'] and task['execution'] not in ('CANCELLED','ACCESS_REVOKED'):
            from .runner import state_in
            conn.execute('UPDATE research_steps SET state=?,version=version+1 WHERE id=?',('UNKNOWN' if state=='unknown' else 'FAILED',admission['step_id']))
            state_in(conn,value['task_id'],'RECONCILING' if state=='unknown' else 'FAILED',safe_code='plan_send_unknown' if state=='unknown' else 'plan_not_sent')


def metadata(value):
    commit=json.loads(value['commit_json']) if value['commit_json'] else None
    usage=json.loads(value['usage_json']) if value['usage_json'] else None
    from .plan_transport import sending
    generating=sending(value['id']) or any(cap.active and cap.used and cap.dispatch==value['id'] for cap in _SEND_CAPS.values())
    return dict(task_id=value['task_id'],result_ref=value['result_ref'],state='saved' if value['result_json'] else 'failed_insufficient' if value['state']=='returned' else 'generating' if generating and value['state']=='consumed' else 'pending_reconciliation' if value['state'] in ('consumed','unknown') else 'failed_insufficient' if value['state']=='closed' and value['safe_code']=='not_sent' else 'cancelled' if value['state']=='closed' else 'queued',
        financial_state=value['cost_state'],safe_code=value['safe_code'],
        recorded_at=None if commit is None else commit['recorded_at'],real_model_executed=False,execution_mode='fixture',plan_generation_ran=value['result_json'] is not None,
        approved_upper_units=value['upper'],usage=usage)


class _PlanSendLease:
    __slots__=('store','resource','lease','dispatch','raw','account_version','project_version','funding_version','reference','pid','active','used')
    def __init__(self,store,resource,lease,dispatch,raw,account_version,project_version,funding_version,*,_factory=None):
        if _factory is not _SEND_FACTORY:raise TypeError('native committed dispatch required')
        self.store,self.resource,self.lease,self.dispatch,self.raw,self.account_version=store,resource,lease,dispatch,raw,account_version
        self.project_version,self.funding_version=project_version,funding_version
        self.reference,self.pid,self.active,self.used=uid(),__import__('os').getpid(),True,False
        _SEND_CAPS[self.reference]=self
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('native send capability immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('native send capability cannot cross processes')
    def consume(self,resource):
        if not self.active or self.used or self.pid!=__import__('os').getpid() or _SEND_CAPS.get(self.reference) is not self or self.resource is not resource:raise PermissionError('actual single-use native send lease required')
        self.lease.identity;resource.require()
        with self.store.transaction() as conn:
            value=row(conn,'research_plan_dispatches',self.dispatch)
            admission,task,step,control=_task_current(conn,self.store,value)
            _send_financial_current(conn,self.store,self.lease,value,admission,account_version=self.account_version,
                project_version=self.project_version,funding_version=self.funding_version)
            account=row(conn,'research_funding_accounts',value['account_id']);funding=row(conn,'research_plan_funding',1)
            if value['state']!='consumed' or task['execution']!='RUNNING' or step['state']!='SENDING' or funding['balance_claim']!=self.dispatch or funding['balance_nonce']!=value['nonce'] or account['version']!=self.account_version or digest(self.raw)!=admission['request_digest'] or codec_digest()!=admission['template_code_digest'] or producer_code_digest()!=admission['producer_code_digest'] or admission['quote']['valid_until']<=int(time.time()):raise PermissionError('committed authorization ended before first socket write')
            result=self.raw,self.dispatch,value['nonce'],value['admission_digest']
        object.__setattr__(self,'used',True)
        return result
    def close(self):object.__setattr__(self,'active',False);_SEND_CAPS.pop(self.reference,None)


def stop_in(conn,store,lease,task_id):
    value=conn.execute('SELECT * FROM research_plan_dispatches WHERE task_id=?',(task_id,)).fetchone()
    if not value or value['state'] in ('closed','returned'):return
    admission=json.loads(value['admission_json'])
    verify=lambda:_financial_verifier(conn,store,lease,admission)
    # Any consumed dispatch retains the shared held amount until an actual owned
    # return proves an upper booking. Cancellation is not proof of reaping.
    _native_write(conn,lease,'research_plan_dispatches',value['id'],dict(state='closed',safe_code='cancelled',version=value['version']+1,result_json=None),verify)
    funding=row(conn,'research_plan_funding',1)
    if value['cost_state']=='unreserved' and funding['balance_claim']==value['id']:
        _native_write(conn,lease,'research_plan_funding',1,dict(balance_claim=None,balance_nonce=None,version=funding['version']+1),verify)


def erase_in(conn,store,lease,pid,job_id):
    from .paid_control import verify_deletion_origin
    verify_deletion_origin(conn,store=store,lease=lease,job_id=job_id)
    job=conn.execute('SELECT * FROM auth_deletion_jobs WHERE id=?',(job_id,)).fetchone()
    principal=conn.execute('SELECT * FROM research_principals WHERE id=?',(pid,)).fetchone()
    if not job or job['state']!='pending' or not principal or principal['status']!='deleting' or principal['gate_id']!=job['gate_id']:raise PermissionError('actual pending deletion required')
    def verify():verify_deletion_origin(conn,store=store,lease=lease,job_id=job_id);_owner_binding(conn,store,pid,lease)
    for value in conn.execute('SELECT d.* FROM research_plan_dispatches d JOIN research_tasks t ON t.id=d.task_id WHERE t.principal_id=?',(pid,)).fetchall():
        _native_write(conn,lease,'research_plan_dispatches',value['id'],dict(state='closed',safe_code='access_ended',version=value['version']+1,admission_json=None,result_json=None,commit_json=None),verify)
    for value in conn.execute('SELECT * FROM research_plan_previews WHERE principal_id=?',(pid,)).fetchall():
        _native_write(conn,lease,'research_plan_previews',value['id'],dict(state='closed',payload_json=None,research_id=None),verify)
    funding=row(conn,'research_plan_funding',1)
    if funding and funding['principal_id']==pid:
        _native_write(conn,lease,'research_plan_funding',1,dict(status='retired',principal_id=None,generation=None,version=funding['version']+1),verify)


def next_plan_task(store):
    installation=_INSTALLATIONS.get(str(store.path))
    if installation is None:return None
    installation.resource.require()
    with store.transaction() as conn:
        value=conn.execute("SELECT task_id FROM research_plan_dispatches WHERE state='approved' ORDER BY rowid LIMIT 1").fetchone()
        return value[0] if value else None
