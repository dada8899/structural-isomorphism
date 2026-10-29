"""Current-authorized read-only plan history; never recomputes or dispatches."""
import json
from .errors import ResearchError,not_found
from .paid_control import require_authenticated_action
from .provider_schemas import canonical,digest
from .plan_schemas import PlanResult,PlanAdmission
from .plan_runtime import envelope,metadata,_task_current


def read(service,identity,rid,ref,source):
    require_authenticated_action(source,identity=identity,action='plan-read',research_id=rid,task_id=ref)
    with service.store.transaction() as conn:return read_in(conn,service,identity,rid,ref)

def read_in(conn,service,identity,rid,ref):
    pid=service._principal_in(conn,identity)
    service.authorization.check(conn,identity,pid,rid)
    value=conn.execute('SELECT d.* FROM research_plan_dispatches d JOIN research_tasks t ON t.id=d.task_id WHERE d.result_ref=? AND t.research_id=? AND t.principal_id=?',(ref,rid,pid)).fetchone()
    if not value:raise not_found()
    body=metadata(value)
    if value['result_json'] is None:return envelope({**body,'content':None})
    try:
        result=PlanResult.model_validate(json.loads(value['result_json']))
        admission=PlanAdmission.model_validate(json.loads(value['admission_json'])).model_dump(mode='json');commit=json.loads(value['commit_json']);receipt=json.loads(value['receipt_json']);usage=json.loads(value['usage_json'])
        task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(value['task_id'],)).fetchone()
        step=conn.execute('SELECT * FROM research_steps WHERE id=?',(admission['step_id'],)).fetchone()
        revision=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(rid,admission['input_revision'])).fetchone()
        if (value['state']!='returned' or task['execution']!='COMPLETED' or task['policy_revision']!='funded-plan-v1' or not step or step['task_id']!=task['id'] or step['kind']!='phenomenon_plan' or step['state']!='SUCCEEDED'
            or task['version']!=commit['task_after'] or step['version']!=commit['step_after'] or commit['task_after']!=commit['task_before']+1 or commit['step_after']!=commit['step_before']+1
            or task['research_id']!=admission['research_id'] or task['principal_id']!=admission['principal_id'] or task['input_revision']!=admission['input_revision'] or task['input_digest']!=admission['input_digest']
            or not revision or revision[0]!=admission['input_digest'] or digest(canonical(admission))!=value['admission_digest'] or result.admission_digest!=value['admission_digest']
            or result.result_ref!=value['result_ref'] or result.task_id!=value['task_id'] or result.research_id!=rid or result.input_revision!=admission['input_revision'] or result.input_digest!=admission['input_digest'] or result.request_digest!=admission['request_digest']
            or commit['result_ref']!=value['result_ref'] or commit['task_id']!=task['id'] or commit['admission_digest']!=value['admission_digest'] or commit['recorded_at']!=result.recorded_at
            or commit['result_digest']!=digest(canonical(result.model_dump(mode='json'))) or commit['receipt_digest']!=digest(canonical(receipt)) or commit['usage_digest']!=digest(canonical(usage))
            or receipt['producer_code_digest']!=admission['producer_code_digest'] or receipt['dispatch_id']!=value['id'] or receipt['nonce']!=value['nonce'] or receipt['admission_digest']!=value['admission_digest']):raise ValueError('plan domain mismatch')
    except (ValueError,TypeError,KeyError):raise ResearchError('RESULT_UNAVAILABLE',503,'原计划记录当前无法完整核对；不会重新调用模型。') from None
    return envelope({**body,'content':result.model_dump(mode='json')})


def history(conn,rid,*,task_ids=None):
    exists=conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_plan_dispatches'").fetchone()
    if not exists:return []
    if task_ids is not None and not task_ids:return []
    query='SELECT d.* FROM research_plan_dispatches d JOIN research_tasks t ON t.id=d.task_id WHERE t.research_id=?'
    args=[rid]
    if task_ids is not None:
        if len(task_ids)>20:raise ValueError('bounded existing history page required')
        query+=' AND t.id IN ('+','.join('?' for _ in task_ids)+')';args.extend(task_ids)
    return [metadata(value) for value in conn.execute(query+' ORDER BY t.start_version DESC,t.id DESC LIMIT 20',args)]
