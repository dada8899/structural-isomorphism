#!/usr/bin/env python3
"""Stdlib ASGI acceptance driver; installed FastAPI/Auth/Research are real.

Run this saved file with the release interpreter. No pytest/httpx/Uvicorn,
external network, provider, production account, or paid execution is used.
Mac records unsupported and never counts as Linux mathematics verification.
"""
from __future__ import annotations
import asyncio
from contextlib import closing
from decimal import Decimal
import hashlib
from http.cookies import SimpleCookie
import json
import multiprocessing
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'web/backend'
for source in (ROOT,BACKEND):
    if str(source) not in sys.path:sys.path.insert(0,str(source))


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def check(condition,label):
    if not condition:raise AssertionError(label)


def make_app():
    from fastapi import FastAPI
    from api import auth,research
    instance=FastAPI();instance.include_router(auth.router,prefix='/api');instance.include_router(research.router,prefix='/api')
    return instance


async def request(app,method,path,data=None,*,cookie='',key=None,drop_response=False):
    target,_,query=path.partition('?');body=b'' if data is None else canonical(data).encode()
    headers=[(b'host',b'formula.test'),(b'origin',b'http://formula.test')]
    if data is not None:headers.append((b'content-type',b'application/json'))
    if cookie:headers.append((b'cookie',cookie.encode()))
    if key is not None:headers.append((b'idempotency-key',key.encode()))
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http',
        'path':target,'raw_path':target.encode(),'query_string':query.encode(),'root_path':'','headers':headers,
        'server':('formula.test',80),'client':('127.0.0.1',1)}
    received=False;status=None;response_headers=[];chunks=[]
    async def receive():
        nonlocal received
        if received:return {'type':'http.disconnect'}
        received=True;return {'type':'http.request','body':body,'more_body':False}
    async def send(message):
        nonlocal status,response_headers
        if message['type']=='http.response.start':status=message['status'];response_headers=message.get('headers',[])
        elif message['type']=='http.response.body':
            if drop_response:raise ConnectionAbortedError('owned ASGI response delivery failure')
            chunks.append(message.get('body',b''))
    await app(scope,receive,send)
    raw=b''.join(chunks);decoded=json.loads(raw) if raw else None
    return status,decoded,response_headers


def envelope(data):return {'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':data}


def side(template,prefix,values=None,amplitude='8',electrical=False):
    values=values or {};symbol=lambda role:{'op':'symbol','id':prefix+'_'+role}
    binary=lambda op,left,right:{'op':op,'left':left,'right':right}
    derivative=lambda role:{'op':'derivative','state_symbol':prefix+'_'+role,'time_symbol':prefix+'_t','order':1}
    negative=lambda node:{'op':'neg','arg':node}
    little=['same_boundary','finite_long_run_means','effective_arrivals','same_population']
    if template=='little':
        family='queue_flow';spec={'l':('count','system_count',None),'lambda':('count_per_s','effective_arrival_rate','3'),'w':('s','system_time','4')}
        node=binary('eq',symbol('l'),binary('mul',symbol('lambda'),symbol('w')));conditions=little;initial=[]
    elif template=='mm1':
        family='queue_flow';spec={'lambda':('count_per_s','effective_arrival_rate','3'),'mu':('count_per_s','service_capacity','5'),'w':('s','system_time','0.5')}
        node=binary('eq',symbol('w'),binary('div',{'op':'const','value':'1'},binary('sub',symbol('mu'),symbol('lambda'))))
        conditions=little+['poisson_arrivals','independent_exponential_service','single_server','fcfs','infinite_capacity','no_abandonment','constant_parameters','stable_regime'];initial=[]
    elif template=='passive_decay':
        family='first_order_storage';spec={'x':('V' if electrical else 'K','state_difference',None),'t':('s','time',None),
            'r':('ohm' if electrical else 'K_per_W','electrical_resistance' if electrical else 'thermal_resistance','4'),
            'c':('F' if electrical else 'J_per_K','electrical_capacity' if electrical else 'thermal_capacity','2')}
        node=binary('eq',binary('mul',symbol('c'),derivative('x')),binary('div',negative(symbol('x')),symbol('r')))
        conditions=['constant_parameters','no_external_input','positive_parameters']+(['ideal_isolated_rc'] if electrical else ['lumped_state','constant_environment'])
        initial=[{'state_symbol':prefix+'_x','at_time':'0','value':amplitude,'declared_satisfied':True}]
    else:
        family='local_recovery';spec={'delta':('one','local_state_difference',None),'t':('s','time',None),'k':('inverse_s','recovery_rate','0.25')}
        node=binary('eq',derivative('delta'),negative(binary('mul',symbol('k'),symbol('delta'))))
        conditions=['constant_parameters','no_external_input','positive_parameters','stable_equilibrium','local_linear','small_perturbation','fixed_equilibrium'];initial=[]
    return {'family':family,'template_id':template,'original_display':'Synthetic declared '+template+' equation; inspect the accompanying AST.',
        'expression':node,'symbols':[{'id':prefix+'_'+role,'role':role,'unit_id':unit,'quantity':quantity,'value':values.get(role,value)} for role,(unit,quantity,value) in spec.items()],
        'assumptions':[{'id':name,'statement':'Declared condition: '+name,'declared_satisfied':True} for name in conditions],
        'initial_conditions':initial,'boundary_conditions':[],'source_refs':[],'measure_scope':'system','time_basis':'s'}


def draft(left,right,scope='equation_form',points=None):
    return {'input_origin':'user_provided','comparison_scope':scope,'left':left,'right':right,
        'requested_checks':['template','dimensions','canonical_transform','bounded_numeric'],
        'sample_points':points or (['0'] if left['family']=='queue_flow' else ['0','1','2'])}


def problem(formula,label):
    return {'entry':'formula','original_input':'Synthetic acceptance: '+label,'objective':'Check the declared finite model comparison.',
        'summary':'Synthetic finite formula comparison and declared boundaries','variables':[],'constraints':[],'unknowns':[],
        'confirmed':True,'formula_draft':formula}


def cases():
    items=[]
    for label,template,values,scope in [('little-product','little',{'lambda':'3','w':'4','l':'12'},'expression'),
            ('little-variant','little',{'lambda':'5','w':'2.5','l':'12.5'},'expression'),
            ('mm1-product','mm1',{'lambda':'3','mu':'5','w':'0.5'},'equation_form')]:
        items.append((label,draft(side(template,'a',values),side(template,'b',values),scope),'passed','algebraic_identity' if scope=='expression' else 'conditional_model_equivalence'))
    for i,(r,c,x0,rr,cc,y0) in enumerate([('4','2','8','5','1','3'),('2','3','10','7','2','4'),('1','2','1','4','2','9')]):
        items.append(('storage-'+str(i),draft(side('passive_decay','a',{'r':r,'c':c},x0),side('passive_decay','b',{'r':rr,'c':cc},y0,True),'initial_value_problem'),'passed','conditional_model_equivalence'))
    for i,(r,c,k) in enumerate([('4','2','0.25'),('2','4','0.125'),('3','2','0.2')]):
        items.append(('local-'+str(i),draft(side('passive_decay','a',{'r':r,'c':c}),side('linear_stable','b',{'k':k})),'passed','local_approximation'))
    items.append(('unstable-mm1',draft(side('mm1','a',{'lambda':'3','mu':'3'}),side('mm1','b',{'lambda':'3','mu':'3'})),'failed','undetermined'))
    left=side('passive_decay','a',amplitude='0');right=side('passive_decay','b',amplitude='3',electrical=True)
    items.append(('zero-nonzero',draft(left,right,'initial_value_problem'),'failed','not_equivalent'))
    left=side('passive_decay','a');right=side('linear_stable','b')
    next(v for v in right['assumptions'] if v['id']=='small_perturbation')['declared_satisfied']=None
    items.append(('unknown-local-boundary',draft(left,right),'inconclusive','undetermined'))
    return items


async def checked_request(app,method,path,data=None,**kwargs):
    status,result,headers=await request(app,method,path,data,**kwargs)
    check(status==200,'unexpected HTTP status '+str(status)+' at '+path)
    return result,headers


async def run_cases(root):
    app=make_app()
    login,_=await checked_request(app,'POST','/api/auth/request-link',{'email':'formula-synthetic@example.invalid'})
    verified,headers=await checked_request(app,'POST','/api/auth/verify',{'token':login['dev_token']})
    jar=SimpleCookie()
    for name,value in headers:
        if name.lower()==b'set-cookie':jar.load(value.decode())
    from api import auth
    cookie=auth._COOKIE_NAME+'='+jar[auth._COOKIE_NAME].value
    results=[];first=None
    for label,formula,status,relation in cases():
        created,_=await checked_request(app,'POST','/api/research',envelope({'problem':problem(formula,label)}),cookie=cookie,key=str(uuid4()))
        body=created['data'];rid=body['research']['id'];meta=body['current_problem']['formula_snapshot']
        payload={'input_revision':1,'expected_research_version':body['research_version'],'formula_digest':meta['formula_digest'],'confirm_formula_input':True};key=str(uuid4())
        started,_=await checked_request(app,'POST',f'/api/research/{rid}/formula-checks',envelope(payload),cookie=cookie,key=key)
        ref=started['data']['result_ref'];check(started['data']['state']=='returned','formula run did not return')
        opened,_=await checked_request(app,'GET',f'/api/research/{rid}/formula-results/{ref}',cookie=cookie)
        data=opened['data'];outcomes={item['check_kind']:item for item in data['result']['outcomes']}
        check(data['state']=='available','stored result is unavailable')
        check(data['result']['execution_attested'] is False,'pure adapter gained execution authority')
        if sys.platform=='linux':
            check(data['provenance']['execution_attested'] is True,'Linux bounded worker did not attest')
            check(outcomes['canonical_transform']['status']==status and outcomes['canonical_transform']['relation']==relation,'declared case outcome differs: '+label)
            check(outcomes['bounded_numeric']['relation'] in ('undetermined','not_equivalent'),'numeric samples became identity')
            if label=='storage-0':
                check([v['left']['physical_time'] for v in outcomes['bounded_numeric']['samples']]==['0','8','16'],'left physical time differs')
                check([v['right']['physical_time'] for v in outcomes['bounded_numeric']['samples']]==['0','5','10'],'right physical time differs')
        else:check({v['status'] for v in outcomes.values()}=={'unsupported'},'unsupported host executed a formula')
        with closing(sqlite3.connect((root/'auth/auth.sqlite3').as_uri()+'?mode=ro',uri=True)) as conn:
            receipt=json.loads(conn.execute('SELECT receipt_json FROM research_formula_runs WHERE result_ref=?',(ref,)).fetchone()[0])
        results.append({'case':label,'result_ref':ref,'recorded_at':data['metadata']['formula_result_recorded_at'],
            'child_pid':receipt['child_pid'],'reaped':receipt['reaped'],'exitcode':receipt['exitcode'],
            'guard':receipt['resource_guard'],'code_version':receipt['code_version'],'outcomes':list(outcomes.values())})
        replay,_=await checked_request(app,'POST',f'/api/research/{rid}/formula-checks',envelope(payload),cookie=cookie,key=key)
        check(replay['data']['result_ref']==ref and replay['data']['formula_result_recorded_at']==data['metadata']['formula_result_recorded_at'],'idempotency changed the original result')
        if first is None:first=(rid,ref,started['data']['task_id'],payload,key,data,formula)
    rid,ref,task,payload,key,original,formula=first
    changed=problem(formula,'saved new revision')
    await checked_request(app,'POST',f'/api/research/{rid}/revisions',envelope({'expected_revision':1,'problem':changed}),cookie=cookie,key=str(uuid4()))
    historical,_=await checked_request(app,'GET',f'/api/research/{rid}?task_id={task}',cookie=cookie)
    check(historical['data']['is_historical'] is True and historical['data']['formula_check']['result_ref']==ref,'original formula history was not preserved')
    stale,_,_=await request(app,'POST',f'/api/research/{rid}/formula-checks',envelope(payload),cookie=cookie,key=str(uuid4()))
    check(stale==409,'historical formula was silently made executable again')
    process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--read-child',rid,ref],input=cookie.encode(),capture_output=True,timeout=10,env=os.environ.copy())
    check(process.returncode==0,'fresh reader process failed')
    lines=[line for line in process.stdout.decode().splitlines() if line.startswith('FORMULA_CHILD_RESULT ')]
    check(len(lines)==1,'fresh child result missing')
    fresh=json.loads(lines[0].split(' ',1)[1]);check(fresh==original,'fresh process changed same ref, result, or original recorded time')
    # A genuine committed response delivery failure: retry only the original
    # idempotency key, then prove the same stored ref and no second computation.
    created,_=await checked_request(app,'POST','/api/research',envelope({'problem':problem(formula,'lost response')}),cookie=cookie,key=str(uuid4()))
    lost=created['data'];lost_rid=lost['research']['id'];lost_payload={'input_revision':1,'expected_research_version':1,'formula_digest':lost['current_problem']['formula_snapshot']['formula_digest'],'confirm_formula_input':True};lost_key=str(uuid4())
    try:await request(app,'POST',f'/api/research/{lost_rid}/formula-checks',envelope(lost_payload),cookie=cookie,key=lost_key,drop_response=True)
    except ConnectionAbortedError:pass
    else:raise AssertionError('owned response delivery fault was not reached')
    recovered,_=await checked_request(app,'POST',f'/api/research/{lost_rid}/formula-checks',envelope(lost_payload),cookie=cookie,key=lost_key)
    with closing(sqlite3.connect(root/'auth/auth.sqlite3')) as conn:
        check(conn.execute('SELECT count(*) FROM research_tasks WHERE research_id=?',(lost_rid,)).fetchone()[0]==1,'lost response caused recomputation')
        check(conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==0,'formula entered paid ledger')
    cancellation=await cancel_case(app,cookie,root)
    return {'cases':results,'fresh_process_same_ref':True,'original_result_recorded_at':original['metadata']['formula_result_recorded_at'],
        'history_readonly':True,'lost_response_same_ref':recovered['data']['result_ref'],'cancellation':cancellation}


async def cancel_case(app,cookie,root):
    formula=draft(side('passive_decay','a'),side('passive_decay','b',electrical=True),'initial_value_problem',
        [str(Decimal(i)/Decimal(16)) for i in range(256)])
    created,_=await checked_request(app,'POST','/api/research',envelope({'problem':problem(formula,'cancel actual owned worker')}),cookie=cookie,key=str(uuid4()))
    body=created['data'];rid=body['research']['id'];payload={'input_revision':1,'expected_research_version':1,
        'formula_digest':body['current_problem']['formula_snapshot']['formula_digest'],'confirm_formula_input':True}
    running=asyncio.create_task(checked_request(app,'POST',f'/api/research/{rid}/formula-checks',envelope(payload),cookie=cookie,key=str(uuid4())))
    task=None;pids=[];deadline=time.monotonic()+4
    try:
        while time.monotonic()<deadline:
            with closing(sqlite3.connect(root/'auth/auth.sqlite3',timeout=.01)) as conn:
                row=conn.execute("SELECT id,version FROM research_tasks WHERE research_id=? AND execution='RUNNING'",(rid,)).fetchone()
            children=multiprocessing.active_children()
            if row and children:task=row;pids=[p.pid for p in children];break
            if running.done():break
            await asyncio.sleep(.001)
        check(task is not None,'actual cancel window was not observed; do not claim cancellation coverage')
        cancelled,_=await checked_request(app,'POST',f'/api/research/{rid}/cancel',envelope({'task_id':task[0],'expected_task_version':task[1]}),cookie=cookie,key=str(uuid4()))
        completed,_=await asyncio.wait_for(asyncio.shield(running),6)
        check(cancelled['data']['execution']=='CANCELLED' and completed['data']['state']=='closed','cancel did not close original claim')
        with closing(sqlite3.connect(root/'auth/auth.sqlite3')) as conn:
            check(conn.execute('SELECT state,result_json,receipt_json FROM research_formula_runs WHERE task_id=?',(task[0],)).fetchone()==('closed',None,None),'late body filled cancelled claim')
        for pid in pids:
            try:os.kill(pid,0)
            except ProcessLookupError:continue
            raise AssertionError('owned cancelled child was not reaped')
        return {'claimed_task_id':task[0],'child_pids':pids,'claim_closed':True,'late_body_absent':True,'reaped':True,
            'cancel_response_means':'stop_requested; reaping independently observed after owner returned'}
    finally:
        if not running.done():await asyncio.wait_for(asyncio.shield(running),6)


def guard_probes():
    from research.formula_check import _launch,_OwnedCapture
    output=[]
    for operation,expected in [('probe_memory','memory_limited'),('probe_cpu','cpu_limited'),('probe_wall','limited')]:
        capture=_OwnedCapture();started=time.monotonic();state,_=_launch(b'',lambda:True,operation,_owned=capture)
        if sys.platform=='linux':check(state==expected,'fixed resource probe failed: '+operation)
        check(capture.reaped is True,'resource probe child was not reaped')
        output.append({'operation':operation,'state':state,'child_pid':capture.child_pid,'reaped':capture.reaped,'exitcode':capture.exitcode,'elapsed_seconds':round(time.monotonic()-started,4)})
    return output


def configure(root):
    for name,value in {'STRUCTURAL_ENV':'test','AUTH_DATA_DIR':str(root/'auth'),'AUTH_ENABLED':'true','AUTH_DEV_MODE':'true',
        'JWT_SECRET':secrets.token_hex(32),'AUTH_LINK_BASE_URL':'http://formula.test','STRUCTURAL_RESEARCH_ENABLED':'true',
        'STRUCTURAL_LOG_FILE':str(root/'server.jsonl'),'ADMIN_NOTIFICATION_EMAIL':'','STRUCTURAL_PRIVACY_HMAC_KEY':secrets.token_hex(32)}.items():os.environ[name]=value


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--read-child':
        cookie=sys.stdin.buffer.read(8192).decode()
        async def read():
            result,_=await checked_request(make_app(),'GET',f'/api/research/{sys.argv[2]}/formula-results/{sys.argv[3]}',cookie=cookie)
            return result['data']
        print('FORMULA_CHILD_RESULT '+canonical(asyncio.run(read())));return
    initial={p.pid for p in multiprocessing.active_children()};started=time.monotonic()
    temporary=tempfile.TemporaryDirectory(prefix='structure-formula-acceptance-')
    try:
        root=Path(temporary.name).resolve();configure(root)
        result=asyncio.run(run_cases(root));result['guard_probes']=guard_probes()
        from research.formula_check import execution_code_version
        result.update(driver='formula-linux-stdlib-asgi-v1',platform=sys.platform,linux_execution_verified=sys.platform=='linux',
            interpreter=str(Path(sys.executable).resolve()),python_version=sys.version.split()[0],source_code_digest=execution_code_version(),
            driver_digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cost_units=0,external_network_requests=0,
            elapsed_seconds=round(time.monotonic()-started,4))
        print('FORMULA_ACCEPTANCE_RESULT '+canonical(result))
    finally:
        try:
            for child in multiprocessing.active_children():
                if child.pid in initial:continue
                if child.is_alive():child.terminate()
                child.join(.5)
                if child.is_alive():child.kill();child.join(.5)
                child.close()
        finally:temporary.cleanup()



if __name__=='__main__':main()
