"""Actual Main B1 denials; queued paper task is cancelled before release.

The approved failure-only handoff deadman must never fire. Retained cleanup
failures remain failures; the read-only diagnostic changes no Core result.
"""
import asyncio
import json
from pathlib import Path
import sqlite3
import threading
import time
import os
import sys
import subprocess
import httpx
import pytest
from web.backend.tests.test_formal_main_admission import prepared,smtp,login,BETA,envelope
from web.backend.tests.test_formal_main_source_supervisor import create
from web.backend.tests.test_source_document_raw import data_records,uid
from web.backend.tests.acceptance.formal_main_browser_service import _retirement_json
from research.evidence_schemas import encode,sha256
from research.source_document_raw import CONTRACT,PROFILE_ID


def raw_envelope(data):
    return {'schema_version':'structure-research-v1','contract_revision':CONTRACT,'data':data}


def physical_cleanup(binding,app):
    print('DOC_RAW_B1_RETIREMENT:'+_retirement_json(binding,app))
    assert not binding.supervisor._thread.is_alive()
    for witness in binding.witnesses:
        if witness.parent_fd is not None:witness.close()


async def paper_approval(client,base,headers):
    paper={'input_revision':1,'expected_research_version':1,'query':'queue variability'}
    preview=await client.post(base+'/source-preview',json=envelope(paper),headers=headers)
    assert preview.status_code==200
    approval=await client.post(base+'/source-approvals',json=envelope({**paper,
        'preview_digest':preview.json()['data']['preview_digest'],'confirm_external':True}),headers=headers)
    assert approval.status_code==200
    return approval.json()['data']['approval_ref']


def test_actual_main_blocked_raw_interfaces_preserve_old_approval_and_key_conflict(prepared):
    main,admission,_,messages=prepared;captured=[]
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)];captured.append(binding)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                rid=await create(client);base='/api/research/'+rid
                data={'input_revision':1,'expected_research_version':1,'rawprep_profile_id':PROFILE_ID}
                headers={'Origin':BETA,'Idempotency-Key':'raw-b1-preview'}
                preview=await client.post(base+'/source-preview',json=raw_envelope(data),headers=headers)
                assert preview.status_code==200
                value=preview.json()['data']
                assert value['can_confirm'] is False and value['availability']=='unavailable'
                assert value['blocked_reasons']==['ACCESS_IDENTITY_UNBOUND','DOC_NATIVE_UNAVAILABLE']
                assert len(value['plan']['documents'])==2 and value['quota']['remaining']==4
                assert value['plan']['access_profile_ref'] is None and value['plan']['query'] is None
                approved={**data,'preview_digest':value['preview_digest'],'confirm_external':True}
                denied=await client.post(base+'/source-approvals',json=raw_envelope(approved),headers={**headers,'Idempotency-Key':'raw-b1-approve'})
                assert denied.status_code==503 and denied.json()['error']['code']=='SOURCE_PERMISSION_UNAVAILABLE'
                start=await client.post(base+'/source-tasks',json=raw_envelope({'input_revision':1,'expected_research_version':1,'approval_ref':uid(55)}),headers={**headers,'Idempotency-Key':'raw-b1-start'})
                assert start.status_code==503
                with binding.service.store.transaction() as conn:
                    assert conn.execute('SELECT count(*) FROM research_source_approvals').fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==0
                await paper_approval(client,base,{**headers,'Idempotency-Key':'same-key-different-contract'})
                conflict=await client.post(base+'/source-approvals',json=raw_envelope(approved),headers={**headers,'Idempotency-Key':'same-key-different-contract'})
                assert conflict.status_code==409 and conflict.json()['error']['code']=='IDEMPOTENCY_CONFLICT'
                with binding.service.store.transaction() as conn:
                    assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==0
        assert binding.source_receipt.state==binding.native_receipt.state=='CLOSED'
        assert not binding.supervisor._errors and all(w.parent_fd is None for w in binding.witnesses)
        print('DOC_RAW_B1_BLOCKED:'+json.dumps({'raw_approvals':0,'raw_tasks':0,'old_paper_approval_preserved':True,'key_conflict':True,'receipt':'CLOSED'}))
    try:asyncio.run(run())
    finally:
        for binding in captured:physical_cleanup(binding,main.app)


def test_actual_main_unanchored_cache_reader_and_protected_write_refusal(prepared,monkeypatch):
    main,admission,_,messages=prepared
    from research import source_supervisor as source
    from research.source_document_access import _READS
    from multiprocessing import reduction
    target=next(i for i,line in enumerate(Path(source.__file__).read_text().splitlines(),1) if 'self._event.wait(_POLL_SECONDS)' in line)
    armed,idle,release=threading.Event(),threading.Event(),threading.Event()
    observer_errors=[];captured=[];handoff_attempts=[]
    def trace(frame,event,arg):
        if frame.f_code is not source.SourceSupervisor._run_with_budget.__code__:return None
        supervisor=source._REGISTRY.get(id(main.app))
        if (event=='line' and frame.f_lineno==target and armed.is_set() and supervisor is not None
                and supervisor._state=='READY' and not idle.is_set()):
            idle.set()
            if not release.wait(15):observer_errors.append('IDLE_BARRIER_TIMEOUT')
        return trace
    prior=threading.gettrace();threading.settrace(trace)
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)];captured.append(binding)
            original_handoff = reduction.send_handle
            def no_public_capability(*args, **kwargs):
                if threading.current_thread() is binding.supervisor._thread:
                    handoff_attempts.append(True)
                    raise PermissionError('public Source send is outside this local control')
                return original_handoff(*args, **kwargs)
            monkeypatch.setattr(reduction, 'send_handle', no_public_capability)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                rid=await create(client);base='/api/research/'+rid
                headers={'Origin':BETA,'Idempotency-Key':'old-paper-approval'}
                approval=await paper_approval(client,base,headers)
                armed.set();end=time.monotonic()+5
                while not idle.is_set() and time.monotonic()<end:await asyncio.sleep(.005)
                assert idle.is_set()
                task=await client.post(base+'/source-tasks',json=envelope({'input_revision':1,'expected_research_version':1,'approval_ref':approval}),headers={**headers,'Idempotency-Key':'old-paper-queued'})
                assert task.status_code==200
                tid=task.json()['data']['task']['id']
                with binding.service.store.transaction(write=True) as conn:
                    taskrow=conn.execute('SELECT * FROM research_tasks WHERE id=?',(tid,)).fetchone()
                    _,artifact,_,body=data_records({'research_id':rid,'input_revision':1,'task_id':tid,'attempt':1,'input_digest':taskrow['input_digest']})
                    payload=encode(artifact)
                    # Ordinary evidence INSERT is possible, but cannot mint C.
                    conn.execute('INSERT INTO research_evidence_objects VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (artifact.id,'snapshots',rid,1,tid,1,payload,sha256(payload.encode()),body,None,None))
                rawread=await client.get(base+'/source-raw-preparations',params={'task_id':tid})
                # B2 keeps this entire history consumer closed pending Main's
                # real read-borrow owner. It does not open an extra cache scope.
                assert rawread.status_code==503 and rawread.json()['error']['code']=='SOURCE_PERMISSION_UNAVAILABLE'
                assert not _READS
                oldread=await client.get(base+'/records',params={'task_id':tid,'kind':'sources'})
                assert oldread.status_code==404
                badquery=await client.get(base+'/source-raw-preparations?task_id='+tid+'&task_id='+tid)
                assert badquery.status_code==422
                with binding.service.store.transaction(write=True) as conn:
                    with pytest.raises(sqlite3.DatabaseError):conn.execute('UPDATE research_source_runs SET started=1 WHERE task_id=?',(tid,))
                cancelled=await client.post(base+'/cancel',json=envelope({'task_id':tid,'expected_task_version':task.json()['data']['task']['version']}),headers={**headers,'Idempotency-Key':'cancel-before-worker-release'})
                assert cancelled.status_code==200
                assert not observer_errors and not handoff_attempts
            release.set()
        assert binding.source_receipt.state==binding.native_receipt.state=='CLOSED'
        assert not binding.supervisor._errors and not observer_errors and not handoff_attempts
        assert all(w.parent_fd is None for w in binding.witnesses)
        with binding.service.store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0]==0
        print('DOC_RAW_B1_READER:'+json.dumps({'unanchored_raw_rejected':True,'old_sources_rejected_raw':True,
            'native_writes_rejected':True,'deadman_hits':len(handoff_attempts),'barrier_errors':observer_errors,'requests':0,'gets':0,'receipt':'CLOSED'}))
    try:asyncio.run(run())
    finally:
        release.set();threading.settrace(prior)
        for binding in captured:physical_cleanup(binding,main.app)


def test_actual_source_session_transaction_retires_before_stop_without_handoff(prepared,monkeypatch):
    """Real old-paper session exercises the shared producer wrapper, no GET."""
    from research.source_workflow import SourceSession
    from multiprocessing import reduction
    main,admission,_,messages=prepared
    held,release=threading.Event(),threading.Event()
    captured=[];observer_errors=[];handoff_attempts=[]
    code=SourceSession.run.__code__
    def trace(frame,event,arg):
        if frame.f_code is not code:return None
        if event=='call':
            binding=admission._STATE.get(id(main.app))
            if binding is not None and threading.current_thread() is binding.supervisor._thread:
                captured.append(frame.f_locals['self']);held.set()
                if not release.wait(5):observer_errors.append('SESSION_BARRIER_TIMEOUT')
        return trace
    prior=threading.gettrace();threading.settrace(trace)
    original=reduction.send_handle
    def no_public_capability(*args,**kwargs):
        binding=admission._STATE.get(id(main.app))
        if binding is not None and threading.current_thread() is binding.supervisor._thread:
            handoff_attempts.append(True);raise PermissionError('public Source send is outside this local control')
        return original(*args,**kwargs)
    monkeypatch.setattr(reduction,'send_handle',no_public_capability)
    async def run():
        context=main.lifespan(main.app);await context.__aenter__()
        binding=admission._STATE[id(main.app)];observer=None;exited=False
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);base='/api/research/'+rid
                headers={'Origin':BETA,'Idempotency-Key':'source-session-wrapper'}
                approval=await paper_approval(client,base,headers)
                task=await client.post(base+'/source-tasks',json=envelope({'input_revision':1,'expected_research_version':1,'approval_ref':approval}),headers={**headers,'Idempotency-Key':'source-session-task'})
                assert task.status_code==200
                end=time.monotonic()+3
                while not held.is_set() and time.monotonic()<end:await asyncio.sleep(.005)
                assert held.is_set() and len(captured)==1
                session=captured[0]
                assert session is binding.supervisor._session and session._doc_request is None
            def after_withdraw():
                end=time.monotonic()+3
                while admission._STATE.get(id(main.app)) is not None and time.monotonic()<end:time.sleep(.005)
                if admission._STATE.get(id(main.app)) is not None:observer_errors.append('WITHDRAW_NOT_OBSERVED')
                release.set()
            observer=threading.Thread(target=after_withdraw,name='owned-doc-source-session-stop');observer.start()
            await context.__aexit__(None,None,None);exited=True;observer.join(3)
            assert not observer.is_alive() and not observer_errors and not handoff_attempts
            assert binding.source_receipt.state==binding.native_receipt.state=='CLOSED'
            assert not binding.supervisor._errors and binding.supervisor._slot is None and binding.supervisor._lease is None
            assert all(w.parent_fd is None for w in binding.witnesses)
            print('DOC_B2_ACTUAL_SESSION_STOP:'+json.dumps({'actual_session':True,'producer_transaction_returned':True,'handoff_attempts':0,'requests':0,'closed':True}))
        finally:
            release.set()
            if observer is not None:observer.join(3)
            if not exited:
                import sys
                error=sys.exc_info()[1]
                await context.__aexit__(type(error) if error is not None else None,error,error.__traceback__ if error is not None else None)
            print('DOC_B2_ACTUAL_SESSION_RETIREMENT:'+_retirement_json(binding,main.app))
    try:asyncio.run(run())
    finally:release.set();threading.settrace(prior)


def test_actual_source_transaction_close_failure_retains_native_parent_fd(request,tmp_path,monkeypatch):
    """Owned child keeps logical uncertainty while explicitly closing its FD."""
    if os.environ.get('DOC_B2_TRANSACTION_FAULT_CHILD')!='close-before':
        owned=tmp_path/'doc-transaction-fault';owned.mkdir(mode=0o700)
        home=owned/'home';home.mkdir(mode=0o700)
        guard=sys.modules.get('main_smtp_task_guard')
        assert guard is not None
        packet=Path(guard.__file__).resolve().parent
        environment={name:os.environ[name] for name in ('PATH','PYTHONPATH','REVIEW_SOURCE_ROOT')}
        environment.update(HOME=str(home),TMPDIR=str(owned),A006_AUDIT_ROOT=str(owned),PYTHONDONTWRITEBYTECODE='1',
            PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',STRUCTURAL_ENV='test',AUTH_ENABLED='false',AUTH_DATA_DIR=str(owned/'auth'),
            STRUCTURAL_LOG_FILE=str(owned/'bootstrap.jsonl'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',DOC_B2_TRANSACTION_FAULT_CHILD='close-before')
        target=str(Path(__file__).resolve())+'::test_actual_source_transaction_close_failure_retains_native_parent_fd'
        result=subprocess.run([sys.executable,'-B',str(packet/'run_tests.py'),'-p','controller_mail_observer',
            '-p','a_evidence_resource_observer',target,'--basetemp='+str(owned/'cases'),'--junitxml='+str(owned/'result.xml')],
            cwd=owned,env=environment,capture_output=True,timeout=25)
        (owned/'result.log').write_bytes(result.stdout+result.stderr)
        assert result.returncode==0,'owned transaction uncertainty child failed; preserve result.log'
        assert b'DOC_B2_TRANSACTION_UNCERTAIN:' in result.stdout
        return
    main,admission,_,messages=request.getfixturevalue('prepared')
    from research.source_document_access import DocTransaction
    from research.source_spawn import SourceCleanupUncertain
    captured=[];failures=[];handoffs=[];bindings=[]
    original_close=os.close;prior=threading.gettrace()
    code=DocTransaction.__exit__.__code__
    def trace(frame,event,arg):
        if frame.f_code is not code:return None
        binding=admission._STATE.get(id(main.app))
        if (event=='call' and not captured and binding is not None
                and threading.current_thread() is binding.supervisor._thread):
            transaction=frame.f_locals['self']
            assert transaction.witness is transaction.conn._history_file
            captured.append((transaction,transaction.conn,transaction.witness,transaction.witness.parent_fd))
        return trace
    def fail_close(fd):
        if captured and fd==captured[0][3] and not failures:
            failures.append(True);raise OSError('owned Source transaction parent close uncertainty')
        return original_close(fd)
    from multiprocessing import reduction
    original_handoff=reduction.send_handle
    def no_public_capability(*args,**kwargs):
        binding=admission._STATE.get(id(main.app))
        if binding is not None and threading.current_thread() is binding.supervisor._thread:
            handoffs.append(True);raise PermissionError('public Source send is outside this local control')
        return original_handoff(*args,**kwargs)
    threading.settrace(trace);monkeypatch.setattr(os,'close',fail_close);monkeypatch.setattr(reduction,'send_handle',no_public_capability)
    async def run():
        context=main.lifespan(main.app);await context.__aenter__()
        binding=admission._STATE[id(main.app)];bindings.append(binding)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
            await login(client,messages);rid=await create(client);base='/api/research/'+rid
            headers={'Origin':BETA,'Idempotency-Key':'doc-transaction-close'}
            approval=await paper_approval(client,base,headers)
            task=await client.post(base+'/source-tasks',json=envelope({'input_revision':1,'expected_research_version':1,'approval_ref':approval}),headers={**headers,'Idempotency-Key':'doc-transaction-close-task'})
            assert task.status_code==200
            end=time.monotonic()+3
            while binding.supervisor._thread.is_alive() and time.monotonic()<end:await asyncio.sleep(.005)
            assert failures==[True] and not binding.supervisor._thread.is_alive() and not handoffs
        with pytest.raises(RuntimeError):await context.__aexit__(None,None,None)
        transaction,conn,witness,fd=captured[0]
        debt=next(error for error in binding.supervisor._errors if type(error) is SourceCleanupUncertain)
        assert debt._doc_transaction is transaction and transaction.conn is conn and transaction.witness is witness
        assert transaction.uncertain_fds==[fd] and os.fstat(fd)
        assert binding.source_receipt.state=='CLEANUP_UNCERTAIN' and binding.native_receipt.state=='CLOSED'
        assert binding.supervisor._slot is not None and any(w.parent_fd is not None for w in binding.witnesses)
        print('DOC_B2_TRANSACTION_UNCERTAIN:'+json.dumps({'actual_transaction':True,'actual_parent_fd_retained':True,
            'close_failures':1,'source_closed':False,'handoffs':0,'requests':0}))
    try:asyncio.run(run())
    finally:
        threading.settrace(prior);monkeypatch.setattr(os,'close',original_close)
        if captured:original_close(captured[0][3])
        for binding in bindings:
            print('DOC_B2_TRANSACTION_RETIREMENT:'+_retirement_json(binding,main.app))
            for witness in binding.witnesses:
                if witness.parent_fd is not None:witness.close()
