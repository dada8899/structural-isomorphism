"""Current cache data and genuine borrowed consumers; no DOC producer grant."""
import asyncio
import contextvars
from copy import deepcopy
from dataclasses import asdict,replace
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from uuid import uuid4
import subprocess
import sys

import httpx
import pytest

from research.source_document_access import current_cache_policy_data,cache_policy_matches,require_private_cache
from research.source_document_raw import (CONTRACT,catalog,request_output_data,RawPrepPlan,RawPrepRequestReceipt,
    RawPrepBundleReceipt,decode_plan_spec,rawprep_draft,encode_raw)
from research.evidence_repository import verify_raw_output_data,raw_bundle_projection_data
from research.evidence_schemas import canonical,sha256
from research.errors import ResearchError
from web.backend.tests.test_source_document_raw import data_records,uid,H,T,commitment_data
from web.backend.tests.test_formal_main_admission import prepared,smtp,login,BETA,envelope
from web.backend.tests.test_formal_main_source_supervisor import create
from web.backend.tests.test_source_document_raw_lifecycle import paper_approval


def test_current_mapping_is_data_and_does_not_require_network_expiry_or_old_ref_equality():
    policy=current_cache_policy_data()
    assert policy['private_cache_expires_at'] is None
    for target in catalog():assert cache_policy_matches(policy,**asdict(target.doc_ref),purpose=CONTRACT)
    historical=data_records()[0]
    assert asdict(historical.plan.access_profile_ref)!=policy['current_access_ref']
    # A legal future Root mapping may differ from the original acquisition.
    # These are pure data examples, not approval of this example ref or a read.
    changed=deepcopy(policy);changed['revision']=2
    changed['current_access_ref']={'id':'future-root-approved-example','revision':2,'digest':'b'*64}
    changed['current_policy_sha256']='c'*64
    assert cache_policy_matches(changed,doc_id=catalog()[0].doc_ref.doc_id,doc_version=1,purpose=CONTRACT)
    assert not any('network' in key or 'expiry' in key for key in policy)
    with pytest.raises(PermissionError):require_private_cache({'ready':True},catalog()[0].doc_ref,purpose=CONTRACT)


@pytest.mark.parametrize('variant',['missing','revoked','purpose','doc','version','bool_version','profile','policy','expiry','provider'])
def test_unknown_revoked_or_wrong_current_mapping_is_closed_data(variant):
    policy=current_cache_policy_data();doc_id=catalog()[0].doc_ref.doc_id;version=1;purpose=CONTRACT
    if variant=='missing':policy=None
    elif variant=='revoked':policy['allowed']=False
    elif variant=='purpose':purpose='display_excerpt'
    elif variant=='doc':doc_id='unknown'
    elif variant=='version':version=2
    elif variant=='bool_version':version=True
    elif variant=='profile':policy['current_access_ref']=None
    elif variant=='policy':policy['current_policy_sha256']='bad'
    elif variant=='expiry':policy['private_cache_expires_at']='2020-01-01T00:00:00Z'
    else:policy['provider_input']=True
    assert not cache_policy_matches(policy,doc_id=doc_id,doc_version=version,purpose=purpose)


def row_data(record,kind,raw=None):
    payload=encode_raw(record)
    return {'id':record.id,'kind':kind,'research_id':record.research_id,'input_revision':record.input_revision,
        'task_id':record.task_id,'attempt':record.attempt,'payload':payload,'payload_digest':sha256(payload.encode()),
        'raw':raw,'extracted':None,'discovery':None}


def output_data():
    plan,artifact,receipt,body=data_records();c=commitment_data(plan,artifact,receipt)
    request={'id':artifact.request_id,**{k:v for k,v in c['request'].items() if k!='request_id'},
        'outcome':'SUCCEEDED','execution_closed':1,'closure_ref':receipt.id,'closure_proof':canonical(c),
        'started_at':T,'ended_at':T,'http_status':200,'safe_code':'none'}
    request['owner_gate_identity']=canonical(request['owner_gate_identity']);request['task_gate_identity']=canonical(request['task_gate_identity'])
    return plan,request,receipt,row_data(receipt,'executions'),artifact,row_data(artifact,'snapshots',body),H


def test_pure_original_integrity_data_does_not_create_a_native_anchor_or_read_scope():
    assert verify_raw_output_data(*output_data()) is None
    # The same self-consistent data still cannot cross the actual read port.
    from research.source_document_access import RawReadScope
    with pytest.raises(PermissionError):RawReadScope(None,None,None,None,uid(1),uid(2))


@pytest.mark.parametrize('variant',['foreign_dispatch','replace_self_hash','orphan_ref','wrong_scope','raw_length','raw_hash',
    'missing_receipt','old_unknown','posthoc','no_body_artifact'])
def test_deep_original_output_comparisons_reject_hostile_data_without_faking_native_domain(variant):
    values=list(output_data());plan,request,receipt,rrow,artifact,arow,_=values
    if variant=='foreign_dispatch':request['dispatch_id']=uid(98)
    elif variant=='replace_self_hash':
        body=b'<html>replacement self-consistent data</html>'
        observation=replace(artifact.observation,content_length=len(body),raw_length=len(body),raw_sha256=sha256(body))
        values[2]=replace(receipt,observation=observation);values[4]=replace(artifact,observation=observation,raw_length=len(body),raw_sha256=sha256(body))
        values[3]=row_data(values[2],'executions');values[5]=row_data(values[4],'snapshots',body)
    elif variant=='orphan_ref':values[4]=replace(artifact,id=uid(99));values[5]=row_data(values[4],'snapshots',arow['raw'])
    elif variant=='wrong_scope':values[5]={**arow,'research_id':uid(99)}
    elif variant=='raw_length':values[5]={**arow,'raw':arow['raw']+b'!'}
    elif variant=='raw_hash':values[5]={**arow,'raw':b'x'*len(arow['raw'])}
    elif variant=='missing_receipt':values[3]=None
    elif variant=='old_unknown':request.update(outcome='UNKNOWN',closure_proof=canonical({'proof_version':1}))
    elif variant=='posthoc':request['execution_closed']=0
    else:
        # Known HTTP denial has no artifact even if extra ordinary data exists.
        observation=replace(receipt.observation,http_status=403,received_at=None,observed_failure_at=T,safe_code='access_denied',
            effective_content_encoding=None,body_complete=False,raw_length=None,raw_sha256=None)
        initial={**request,'outcome':'SENDING','execution_closed':0,'closure_ref':None,'closure_proof':None}
        _,failed,c=request_output_data(plan,initial,observation,receipt.retirement,artifact_ref=None,receipt_ref=receipt.id,
            admission_digest=H,producer_code_digest=H)
        values[2]=failed;values[3]=row_data(failed,'executions')
        request.update(outcome='FAILED',http_status=403,safe_code='access_denied',closure_proof=canonical(c))
    with pytest.raises(ValueError):verify_raw_output_data(*values)


def test_bundle_data_projection_is_fixed_pair_and_not_a_third_dispatch():
    plan,artifact,first,_=data_records();target=catalog()[1]
    second=replace(first,id=uid(71),request_id=uid(51),dispatch_id=uid(61),ordinal=2,doc_ref=target.doc_ref,artifact_ref=uid(41),
        observation=replace(first.observation,requested_target=target,observed_final_target=target),
        retirement=replace(first.retirement,request_id=uid(51),dispatch_id=uid(61)))
    projection=raw_bundle_projection_data(plan,((first,H),(second,'b'*64)))
    assert projection['package_state']=='RAW_PAIR_COMPLETE_UNVERIFIED' and len(projection['request_receipt_refs'])==2
    assert raw_bundle_projection_data(plan,((first,H),))['package_state']=='INCOMPLETE'
    assert raw_bundle_projection_data(plan,((first,H),),has_unknown=True)['package_state']=='RECONCILIATION_REQUIRED'
    with pytest.raises(ValueError):raw_bundle_projection_data(plan,((second,H),(first,'b'*64)))
    with pytest.raises(ValueError):raw_bundle_projection_data(plan,((first,H),(replace(second,research_id=uid(99)),'b'*64)))
    with pytest.raises(ValueError):raw_bundle_projection_data(plan,((first,H),(replace(second,id=first.id),'b'*64)))


def test_direct_consumer_calls_without_actual_worker_do_no_private_io():
    from research.source_integration import raw_preparations
    for source in (None,{'ready':True},lambda:True):
        with pytest.raises((RuntimeError,PermissionError,ResearchError)):raw_preparations(None,None,uid(1),uid(2),request_source=source)


@pytest.mark.parametrize('shape',['empty','complete','subclass'])
def test_unregistered_scope_identity_precedes_every_claimed_connection_operation(shape):
    from research.source_document_access import RawReadScope
    calls=[]
    class ConnectionTrap:
        @property
        def in_transaction(self):calls.append('property');raise AssertionError('claimed property used')
        def execute(self,*args,**kwargs):calls.append('execute');raise AssertionError('claimed SQL used')
    class ForeignScope(RawReadScope):pass
    fake=object.__new__(ForeignScope if shape=='subclass' else RawReadScope)
    if shape!='empty':
        for key,value in {'conn':ConnectionTrap(),'service':None,'identity':None,'source':None,'research_id':uid(1),
                'task_id':uid(2),'pid':os.getpid(),'thread':threading.current_thread(),'active':True}.items():object.__setattr__(fake,key,value)
    with pytest.raises(PermissionError):require_private_cache(fake,catalog()[0].doc_ref,purpose=CONTRACT)
    assert calls==[]


async def queued_then_cancelled(client,binding,main,monkeypatch):
    """Actual paper admission; original task mutex excludes every sender."""
    from research import authorization
    import fcntl,inspect
    from multiprocessing import reduction
    held,release=threading.Event(),threading.Event();attempts=[];original_flock=fcntl.flock;original_send=reduction.send_handle
    code=authorization._source_task_gate.__wrapped__.__code__
    def barrier(fd,operation):
        value=original_flock(fd,operation)
        if (threading.current_thread() is binding.supervisor._thread and inspect.currentframe().f_back.f_code is code
                and operation==fcntl.LOCK_EX|fcntl.LOCK_NB):
            held.set()
            if not release.wait(5):raise TimeoutError('owned queued task primitive expired')
        return value
    def no_public_capability(*args,**kwargs):
        if threading.current_thread() is binding.supervisor._thread:
            attempts.append(True);raise PermissionError('public Source send is outside this local control')
        return original_send(*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(fcntl,'flock',barrier);patch.setattr(reduction,'send_handle',no_public_capability)
        rid=await create(client);base='/api/research/'+rid;headers={'Origin':BETA,'Idempotency-Key':'b3-paper-approval'}
        approval=await paper_approval(client,base,headers)
        try:
            response=await client.post(base+'/source-tasks',json=envelope({'input_revision':1,'expected_research_version':1,'approval_ref':approval}),headers={**headers,'Idempotency-Key':'b3-paper-task'})
            assert response.status_code==200
            task=response.json()['data']['task'];end=time.monotonic()+3
            while not held.is_set() and time.monotonic()<end:await asyncio.sleep(.005)
            assert held.is_set()
            cancelled=await client.post(base+'/cancel',json=envelope({'task_id':task['id'],'expected_task_version':task['version']}),headers={**headers,'Idempotency-Key':'b3-before-send-cancel'})
            assert cancelled.status_code==200
        finally:release.set()
        end=time.monotonic()+3
        while binding.supervisor._slot is not None and time.monotonic()<end:await asyncio.sleep(.005)
        assert not attempts and binding.supervisor._slot is None
    with binding.service.store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0]==0
    return rid,task['id']


def test_actual_closed_source_consumer_reaches_protected_anchor_rejection_and_current_owner(prepared,monkeypatch):
    from research import source_integration
    from research.evidence_repository import EvidenceRepository
    from research.source_document_access import _READS,RawReadScope
    from web.backend.tests.test_source_document_access import insert_data
    main,admission,_,messages=prepared
    missing_line=next(i for i,line in enumerate(Path(EvidenceRepository._raw_receipt_anchor.__code__.co_filename).read_text().splitlines(),1)
        if "raise ValueError('DOC protected first output absent')" in line)
    hit=[];profile_opens=[];watch={'on':False};scope_denials=[];trap_calls=[]
    def audit(event,args):
        if watch['on'] and event=='open' and str(args[0]).endswith('source-sec-access-profile.json'):
            profile_opens.append(True);raise AssertionError('history must not reopen the network profile')
    import sys
    sys.addaudithook(audit)
    code=EvidenceRepository._raw_receipt_anchor.__code__;scope_code=RawReadScope.check.__code__;prior=threading.gettrace()
    class ConnectionTrap:
        @property
        def in_transaction(self):trap_calls.append('property');raise AssertionError('foreign property used')
        def execute(self,*args,**kwargs):trap_calls.append('execute');raise AssertionError('foreign SQL used')
    def trace(frame,event,arg):
        if frame.f_code is scope_code:
            if event=='call' and not scope_denials:
                scope=frame.f_locals['self']
                # Fault only a genuine, registered scope produced by this real
                # consumer; restore its exact original fields, never a registry.
                for key,bad in (('pid',os.getpid()+1),('thread',object()),('active',False)):
                    previous=getattr(scope,key);object.__setattr__(scope,key,bad)
                    try:
                        with pytest.raises(PermissionError):require_private_cache(scope,catalog()[0].doc_ref,purpose=CONTRACT)
                        scope_denials.append(key)
                    finally:object.__setattr__(scope,key,previous)
                with pytest.raises(PermissionError):scope.check_native(ConnectionTrap())
                original_conn=scope.conn;object.__setattr__(scope,'conn',ConnectionTrap())
                try:
                    with pytest.raises(PermissionError):require_private_cache(scope,catalog()[0].doc_ref,purpose=CONTRACT)
                    scope_denials.append('foreign_connection')
                finally:object.__setattr__(scope,'conn',original_conn)
                assert not trap_calls
            return trace
        if frame.f_code is not code:return None
        if event=='exception' and frame.f_lineno==missing_line and arg[0] is ValueError:hit.append(True)
        return trace
    threading.settrace(trace)
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                rid,tid=await queued_then_cancelled(client,binding,main,monkeypatch)
                with binding.service.store.transaction(write=True) as conn:
                    task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(tid,)).fetchone()
                    _,artifact,_,body=data_records({'research_id':rid,'input_revision':1,'task_id':tid,'attempt':1,'input_digest':task['input_digest']})
                    insert_data(conn,artifact,'snapshots',body)  # Hostile orphan only, never a positive producer.
                admission.close_source(binding,deadline_monotonic=time.monotonic()+10)
                receipt=binding.source_receipt;assert admission.source_closed(binding)
                watch['on']=True
                response=await client.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':tid})
                assert response.status_code==503 and response.json()['error']['code']=='STORE_UNAVAILABLE' and 'data' not in response.json()
                assert hit and scope_denials==['pid','thread','active','foreign_connection'] and not trap_calls and not profile_opens and not _READS
                assert admission.history_reads_closed(binding) and binding.source_receipt is receipt and not binding.source_errors
                # A different real authenticated owner cannot read this task.
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as other:
                    await login(other,messages,'b3-other@example.invalid')
                    denied=await other.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':tid})
                    assert denied.status_code==404 and 'data' not in denied.json()
                old=httpx.Cookies(client.cookies)
                assert (await client.post('/api/auth/logout',headers={'Origin':BETA})).status_code==200
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA,cookies=old) as revoked:
                    denied=await revoked.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':tid})
                    assert denied.status_code==401 and 'data' not in denied.json()
                await login(client,messages)
                assert (await client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':BETA})).status_code==200
                await login(client,messages)
                denied=await client.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':tid})
                assert denied.status_code==404 and 'data' not in denied.json()
                watch['on']=False
                assert not profile_opens and admission.history_reads_closed(binding) and binding.source_receipt is receipt and not binding.source_errors
                print('B3_ACTUAL_ORPHAN_DENIAL:'+json.dumps({'actual_closed_source':True,'actual_borrow_consumer':True,
                    'protected_request_absence_reached':True,'profile_opens':0,'owner_denials':True,'gets':0,
                    'registered_scope_identity_denials':scope_denials,'claimed_connection_operations':len(trap_calls)}))
        assert binding.source_receipt.state==binding.native_receipt.state=='CLOSED' and not binding.history_errors
    try:asyncio.run(run())
    finally:watch['on']=False;threading.settrace(prior)


def test_actual_consumer_rejects_foreign_app_source_and_copied_stale_worker_before_io(prepared,monkeypatch):
    from research import source_integration
    from fastapi import FastAPI
    main,admission,_,messages=prepared
    original=source_integration.raw_preparations;state={'mode':'normal'};captured=[];raw_connects=[]
    wrong_app=FastAPI()
    def observe(service,identity,rid,task_id,**kwargs):
        worker=admission._history_worker_current()
        assert worker is not None and worker.stage=='raw'
        if state['mode']=='app':kwargs['request_app']=wrong_app
        elif state['mode']=='source':kwargs['request_source']={'ready':True}
        else:captured.append((contextvars.copy_context(),service,identity,rid,task_id,dict(kwargs)))
        return original(service,identity,rid,task_id,**kwargs)
    def audit(event,args):
        if event=='sqlite3.connect/handle':
            worker=admission._READ_WORKER.get()
            if worker is not None and worker.stage=='raw':raw_connects.append(state['mode'])
    sys.addaudithook(audit);monkeypatch.setattr(source_integration,'raw_preparations',observe)
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client)
                admission.close_source(binding,deadline_monotonic=time.monotonic()+10)
                receipt=binding.source_receipt
                for mode in ('app','source','normal'):
                    state['mode']=mode
                    response=await client.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':str(uuid4())})
                    assert response.status_code==(404 if mode=='normal' else 503) and 'data' not in response.json()
                    assert admission.history_reads_closed(binding)
                assert raw_connects and set(raw_connects)=={'normal'} and len(captured)==1
                ctx,service,identity,rid,tid,kwargs=captured[0];before=len(raw_connects)
                with pytest.raises((RuntimeError,PermissionError,ResearchError)):ctx.run(original,service,identity,rid,tid,**kwargs)
                assert len(raw_connects)==before
                with pytest.raises(ResearchError):original(service,identity,rid,tid,**kwargs)
                assert binding.source_receipt is receipt and admission.source_closed(binding) and not binding.source_errors
                print('B3_ACTUAL_CONSUMER_BOUNDARIES:'+json.dumps({'actual_worker':True,'foreign_app_raw_io':0,
                    'foreign_source_raw_io':0,'copied_stale_worker_raw_io':0,'source_receipt_unchanged':True}))
        assert binding.source_receipt.state==binding.native_receipt.state=='CLOSED' and not binding.history_errors
    asyncio.run(run())


def _raw_consumer_close_fault_probe(owned_root):
    with pytest.MonkeyPatch.context() as monkeypatch:
        smtp_fixture=smtp.__wrapped__()
        try:
            actual_smtp=next(smtp_fixture)
            prepared_fixture=prepared.__wrapped__(Path(owned_root),monkeypatch,actual_smtp)
            try:
                prepared_value=next(prepared_fixture)
                main,admission,_,messages=prepared_value
                from research.source_document_access import RawReadScope
                from web.backend.tests.acceptance.formal_main_browser_service import _retirement_json
                captured=[];failures=[];bindings=[];raw_code=RawReadScope.check.__code__;prior=threading.gettrace();original_close=os.close
                def trace(frame,event,arg):
                    if frame.f_code is not raw_code:return None
                    if event=='call' and not captured:
                        scope=frame.f_locals['self'];worker=admission._history_worker_current()
                        if worker is not None and worker.stage=='raw':
                            conn=scope.conn;witness=conn._history_file
                            captured.append((worker,conn,witness,witness.parent_fd,conn._history_read_resource))
                    return trace
                def fail_close(fd):
                    if captured and fd==captured[0][3] and not failures:
                        failures.append(True);raise OSError('owned B3 read parent close uncertainty')
                    return original_close(fd)
                threading.settrace(trace);monkeypatch.setattr(os,'close',fail_close)
                async def run():
                    context=main.lifespan(main.app);await context.__aenter__();binding=admission._STATE[id(main.app)];bindings.append(binding)
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                        await login(client,messages);rid,tid=await queued_then_cancelled(client,binding,main,monkeypatch)
                        admission.close_source(binding,deadline_monotonic=time.monotonic()+10);receipt=binding.source_receipt
                        response=await client.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':tid})
                        assert response.status_code==503 and 'data' not in response.json() and failures==[True]
                        worker,conn,witness,fd,resource=captured[0]
                        assert worker.read.binding is binding and worker.read.reference in binding.history_reads
                        assert binding.history_errors and not admission.history_reads_closed(binding)
                        assert resource.handle is conn and worker.read.resources and os.fstat(fd)
                        assert binding.source_receipt is receipt and admission.source_closed(binding) and not binding.source_errors
                    with pytest.raises(RuntimeError):await context.__aexit__(None,None,None)
                    assert binding.source_receipt is receipt and binding.native_receipt.state=='CLOSED' and binding.history_errors
                    assert not binding.supervisor._thread.is_alive() and any(w.parent_fd is not None for w in binding.witnesses)
                    print('B3_MAIN_OWNED_READ_UNCERTAIN:'+json.dumps({'actual_raw_consumer':True,'actual_parent_fd_retained':True,
                        'Main_history_uncertain':True,'source_still_closed':True,'Source_errors':0,'close_attempts':1,'gets':0}))
                try:asyncio.run(run())
                finally:
                    threading.settrace(prior);monkeypatch.setattr(os,'close',original_close)
                    # Only known-before-close synthetic responsibility is physically closed.
                    # Main's logical uncertain receipt is kept until this child exits.
                    if captured:original_close(captured[0][3])
                    for binding in bindings:
                        print('B3_READ_FAULT_RETIREMENT:'+_retirement_json(binding,main.app))
                        for witness in binding.witnesses:
                            if witness.parent_fd is not None:witness.close()
            except BaseException as primary:
                try:
                    with pytest.raises(StopIteration):next(prepared_fixture)
                except BaseException as cleanup:
                    raise BaseExceptionGroup('portable_fault_and_prepared_teardown',[primary,cleanup]) from None
                raise
            else:
                with pytest.raises(StopIteration):next(prepared_fixture)
        except BaseException as primary:
            try:
                with pytest.raises(StopIteration):next(smtp_fixture)
            except BaseException as cleanup:
                raise BaseExceptionGroup('portable_fault_and_smtp_teardown',[primary,cleanup]) from None
            raise
        else:
            with pytest.raises(StopIteration):next(smtp_fixture)


def test_actual_raw_consumer_close_failure_is_owned_by_main_after_source_closed(tmp_path):
    import signal
    owned=tmp_path/'b3-read-fault';owned.mkdir(mode=0o700)
    home=owned/'home';home.mkdir(mode=0o700)
    root=Path(__file__).resolve().parents[3]
    program=('import sys\nfrom pathlib import Path\n'
        +'sys.path[:0]='+repr([str(root/'web/backend'),str(root)])+'\n'
        +'from web.backend.tests.test_source_document_cached_history import _raw_consumer_close_fault_probe\n'
        +'_raw_consumer_close_fault_probe(Path('+repr(str(owned))+'))\n')
    environment={'PATH':os.environ.get('PATH',os.defpath),'PYTHONPATH':os.pathsep.join((str(root/'web/backend'),str(root))),
        'HOME':str(home),'TMPDIR':str(owned),'PYTHONDONTWRITEBYTECODE':'1',
        'STRUCTURAL_ENV':'test','AUTH_ENABLED':'false','AUTH_DATA_DIR':str(owned/'auth'),
        'STRUCTURAL_LOG_FILE':str(owned/'bootstrap.jsonl'),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
    with subprocess.Popen([sys.executable,'-B','-c',program],cwd=owned,env=environment,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True) as child:
        try:stdout,stderr=child.communicate(timeout=60)
        except BaseException:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait(timeout=5)
            raise
    (owned/'result.log').write_bytes(stdout+stderr)
    assert child.returncode==0,'isolated owned fault failed; retain result.log'
    assert b'B3_MAIN_OWNED_READ_UNCERTAIN:' in stdout
