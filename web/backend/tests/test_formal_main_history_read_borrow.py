"""Actual Main history read loans; no admission/factory/permission positives."""
import asyncio
import contextvars
import os
import sqlite3
import subprocess
from pathlib import Path
import sys
import threading
import types
from uuid import uuid4

import httpx
import pytest

from .test_formal_main_admission import prepared, smtp, login, BETA


async def wait_event(event, timeout=5):
    end=asyncio.get_running_loop().time()+timeout
    while not event.is_set():
        assert asyncio.get_running_loop().time()<end, 'owned read phase did not finish'
        await asyncio.sleep(.01)


def test_actual_main_registers_before_auth_and_includes_bad_single_segment_ids(prepared):
    main,admission,_,messages=prepared;observed=[];watch={'active':False}
    def audit(event,args):
        if event=='sqlite3.connect/handle' and watch['active']:
            worker=admission._READ_WORKER.get()
            observed.append((worker is not None, worker.stage if worker is not None else None))
    sys.addaudithook(audit)
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                admission.close_source(binding,deadline_monotonic=__import__('time').monotonic()+10)
                receipt=binding.source_receipt
                try:
                    watch['active']=True
                    for suffix in ('records','source-raw-preparations'):
                        response=await client.get('/api/research/not-a-uuid/'+suffix,params={'task_id':str(uuid4()),'kind':'sources'} if suffix=='records' else {'task_id':str(uuid4())})
                        assert response.status_code==404,response.text
                        assert admission.history_reads_closed(binding)
                finally:watch['active']=False
                assert observed and all(present for present,_ in observed)
                assert {'identity','service'} <= {stage for _,stage in observed}
                assert admission.source_closed(binding) and binding.source_receipt is receipt and not binding.source_errors
                with pytest.raises(TypeError):admission.MainHistoryReadBorrow()
                token=admission._READ_CONTEXT.set(object())
                try:
                    from services.sqlite_utils import connect_private_auth
                    with pytest.raises(RuntimeError):connect_private_auth(binding.service.store.path,readonly=True)
                finally:admission._READ_CONTEXT.reset(token)
                assert admission.history_reads_closed(binding)
                with pytest.raises(RuntimeError):
                    await admission.drain_history_reads(binding,deadline_monotonic=__import__('time').monotonic()+1)
    asyncio.run(run())


@pytest.mark.parametrize('phase',['parent','journal'])
def test_partial_auth_birth_retires_real_handles_and_preserves_primary(prepared,monkeypatch,phase):
    main,admission,paths,messages=prepared;seen=[];watch={'active':False}
    original_check=paths.PrivateAuthFile.check
    def check(witness):
        worker=admission._READ_WORKER.get()
        if watch['active'] and phase=='parent' and not seen and worker is not None and worker.stage=='identity':
            assert witness.parent_fd is not None;seen.append(witness)
            raise paths.RuntimePathError('owned after-parent-birth fault')
        return original_check(witness)
    monkeypatch.setattr(paths.PrivateAuthFile,'check',check)
    def audit(event,args):
        if event=='sqlite3.connect/handle' and watch['active'] and phase=='journal' and not seen:
            worker=admission._READ_WORKER.get()
            if worker is not None and worker.stage=='identity':
                conn=args[0];seen.append(conn)
                execute=conn.execute
                def after_return(self,sql,*args,**kwargs):
                    if sql=='PRAGMA journal_mode':raise sqlite3.DatabaseError('owned post-return journal fault')
                    return execute(sql,*args,**kwargs)
                conn.execute=types.MethodType(after_return,conn)
    sys.addaudithook(audit)
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app,raise_app_exceptions=False),base_url=BETA) as client:
                await login(client,messages)
                watch['active']=True
                try:response=await client.get('/api/research/not-a-uuid/records')
                finally:watch['active']=False
                assert response.status_code==(500 if phase=='parent' else 503),response.text
                assert seen and admission.history_reads_closed(binding)
                if phase=='parent':assert seen[0].parent_fd is None
                else:
                    with pytest.raises(sqlite3.ProgrammingError):seen[0].in_transaction
    asyncio.run(run())


def test_pending_cancel_rejects_the_actual_late_worker_before_private_io(prepared,monkeypatch):
    main,admission,_,messages=prepared
    from api import research
    original=research._history_worker;queued=threading.Event();release=threading.Event();done=threading.Event();outcome=[];slots=[]
    def delayed(slot):
        if slot.stage=='identity' and not slots:
            slots.append(slot);queued.set()
            assert release.wait(5),'owned pending worker not released'
            try:return original(slot)
            except BaseException as error:outcome.append(type(error));raise
            finally:done.set()
        return original(slot)
    monkeypatch.setattr(research,'_history_worker',delayed)
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                task=asyncio.create_task(client.get('/api/research/not-a-uuid/records'))
                try:
                    await wait_event(queued)
                    assert slots[0].state=='PENDING'
                    task.cancel();release.set()
                    with pytest.raises(asyncio.CancelledError):await task
                    assert slots[0].state=='CANCELLED'
                finally:
                    release.set();await wait_event(done)
                assert outcome==[admission.HistoryReadUnavailable]
                assert admission.history_reads_closed(binding)
    asyncio.run(run())


def test_active_worker_is_drained_with_actual_main_deadline_without_blocking_loop(prepared,monkeypatch):
    main,admission,_,messages=prepared
    paused=threading.Event();release=threading.Event();watch={'active':False};held=[]
    def audit(event,args):
        if event=='sqlite3.connect/handle' and watch['active'] and not held:
            worker=admission._READ_WORKER.get()
            if worker is not None and worker.stage=='identity':
                conn=args[0];held.append((conn,worker));close=conn._close_native
                def delayed(self):
                    paused.set();assert release.wait(10),'owned active close not released'
                    return close()
                conn._close_native=types.MethodType(delayed,conn)
    sys.addaudithook(audit)
    async def run():
        context=main.lifespan(main.app);await context.__aenter__()
        binding=admission._STATE[id(main.app)]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
            await login(client,messages);watch['active']=True
            task=asyncio.create_task(client.get('/api/research/not-a-uuid/records'));exit_task=None
            try:
                await wait_event(paused)
                assert held[0][1].state=='ACTIVE' and binding.history_reads
                worker=held[0][1]
                request_token=admission._READ_CONTEXT.set(worker.read);worker_token=admission._READ_WORKER.set(worker)
                try:
                    from services.sqlite_utils import connect_private_auth
                    with pytest.raises(RuntimeError):connect_private_auth(binding.service.store.path,readonly=True)
                finally:
                    admission._READ_WORKER.reset(worker_token);admission._READ_CONTEXT.reset(request_token)
                exit_task=asyncio.create_task(context.__aexit__(None,None,None))
                end=asyncio.get_running_loop().time()+5
                while binding.history_deadline is None:
                    assert asyncio.get_running_loop().time()<end
                    await asyncio.sleep(.01)
                deadline=binding.history_deadline
                assert binding.retired and id(main.app) not in admission._STATE
                assert not exit_task.done() and all(w.parent_fd is not None for w in binding.witnesses)
                ticks=[]
                for _ in range(3):ticks.append(True);await asyncio.sleep(.005)
                assert len(ticks)==3 and binding.history_deadline==deadline
            finally:
                release.set();watch['active']=False
            response=await task
            assert response.status_code==503,response.text
            await exit_task
            assert binding.history_deadline==deadline and admission.history_reads_closed(binding)
            assert all(w.parent_fd is None for w in binding.witnesses)
    asyncio.run(run())


@pytest.mark.parametrize('target',['connection','parent'])
@pytest.mark.parametrize('when',['before','after'])
def test_close_failure_after_state_withdrawal_keeps_actual_owner_and_never_retries(request,tmp_path,monkeypatch,target,when):
    if isolated_fault_case(request,tmp_path,target+'-'+when):return
    main,admission,_,messages=request.getfixturevalue('prepared')
    from api import research
    original_worker=research._history_worker
    paused=threading.Event();release=threading.Event();watch={'active':False};held=[];attempts=[];manual=[]
    def audit(event,args):
        if event!='sqlite3.connect/handle' or not watch['active'] or held:return
        worker=admission._READ_WORKER.get()
        if worker is None or worker.stage!='identity':return
        conn=args[0]
        parent=next(r.witness for r in worker.read.resources.values() if r.kind=='directory' and r.witness is not None and r.witness.path.name=='auth.sqlite3')
        close=conn._close_native if target=='connection' else parent.close
        held.append((conn,parent,worker,close))
        def fault(self):
            attempts.append(True);paused.set();assert release.wait(10),'owned fault not released'
            if when=='after':close()
            raise OSError('owned actual read close fault')
        if target=='connection':conn._close_native=types.MethodType(fault,conn)
        else:parent.close=types.MethodType(fault,parent)
    sys.addaudithook(audit)
    def worker(slot):
        try:return original_worker(slot)
        finally:
            if held and held[0][2] is slot and when=='before':
                # The fixture injected before the physical operation and knows
                # it did not run. Clean up once on that original owning thread;
                # production does not retry or clear its sticky uncertainty.
                held[0][3]();manual.append(threading.current_thread())
    monkeypatch.setattr(research,'_history_worker',worker)
    async def run():
        context=main.lifespan(main.app);await context.__aenter__();binding=admission._STATE[id(main.app)]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app,raise_app_exceptions=False),base_url=BETA) as client:
            await login(client,messages);watch['active']=True
            task=asyncio.create_task(client.get('/api/research/not-a-uuid/records'));exit_task=None
            try:
                await wait_event(paused)
                exit_task=asyncio.create_task(context.__aexit__(None,None,None))
                end=asyncio.get_running_loop().time()+5
                while not binding.retired:
                    assert asyncio.get_running_loop().time()<end;await asyncio.sleep(.01)
                assert id(main.app) not in admission._STATE
            finally:release.set();watch['active']=False
            response=await task
            assert response.status_code==503,response.text
            with pytest.raises(RuntimeError,match='formal Main retirement uncertain'):await exit_task
            assert binding.history_errors and binding.reference in admission._RETIRED_UNCERTAIN
            assert not admission.history_reads_closed(binding)
            assert admission.source_closed(binding) and not binding.source_errors
            assert attempts==[True]
            conn,parent,slot,_=held[0]
            with pytest.raises(RuntimeError):conn.close()
            assert attempts==[True] and bool(manual)==(when=='before')
            # These are this test's separate, known startup witnesses. Request
            # uncertainty remains retained, even after safe fixture cleanup.
            for witness in binding.witnesses:
                if witness.parent_fd is not None:witness.close()
    asyncio.run(run())


_CHILD_BOOTSTRAP = r"""
import shutil,importlib.util,sys,os
path=os.environ.get('BORROW_SCIENCE_GUARD')
if path:
    spec=importlib.util.spec_from_file_location('main_smtp_task_guard',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sys.modules['main_smtp_task_guard']=module;module.install()
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
"""


def isolated_fault_case(request,tmp_path,label):
    """A sticky retired owner is never cleared to make another case pass."""
    if os.environ.get('BORROW_ISOLATED_FAULT')==label:return False
    owned=tmp_path/'isolated-fault';owned.mkdir(mode=0o700);(owned/'home').mkdir(mode=0o700)
    root=Path(__file__).resolve().parents[3]
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':str(owned/'home'),'TMPDIR':str(owned),
         'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','STRUCTURAL_ENV':'test',
         'AUTH_ENABLED':'false','BORROW_ISOLATED_FAULT':label,'STRUCTURAL_LOG_FILE':str(owned/'events.log'),
         'PYTHONPATH':os.pathsep.join((str(root/'web/backend'),str(root),os.environ.get('PYTHONPATH','')))}
    extras=[]
    guard=sys.modules.get('audit_bootstrap');science=sys.modules.get('main_smtp_task_guard')
    if guard is not None:
        env.update(REVIEW_SOURCE_ROOT=str(root),A006_AUDIT_ROOT=str(owned))
        if science is not None:env['BORROW_SCIENCE_GUARD']=science.__file__
        extras=['-p','resource_observer','-p','mail_observer']
    node=str(Path(__file__).resolve())+'::'+request.node.name
    result=subprocess.run([sys.executable,'-B','-c',_CHILD_BOOTSTRAP,'-q','-s','-p','no:logging','-p','no:cacheprovider',*extras,node,
        '--basetemp='+str(owned/'cases')],cwd=owned,env=env,capture_output=True,text=True,timeout=90)
    (owned/'stdout.log').write_text(result.stdout);(owned/'stderr.log').write_text(result.stderr)
    assert result.returncode==0,result.stdout[-7000:]+result.stderr[-1000:]
    return True


def test_original_main_deadline_is_sticky_after_active_reader_eventually_exits(request,tmp_path,monkeypatch):
    if isolated_fault_case(request,tmp_path,'actual-main-deadline'):return
    main,admission,_,messages=request.getfixturevalue('prepared')
    paused=threading.Event();release=threading.Event();held=[];watch={'active':False}
    def audit(event,args):
        if event=='sqlite3.connect/handle' and watch['active'] and not held:
            worker=admission._READ_WORKER.get()
            if worker is not None and worker.stage=='identity':
                conn=args[0];held.append(worker);close=conn._close_native
                def delayed(self):
                    paused.set();assert release.wait(35),'owned deadline reader not released'
                    return close()
                conn._close_native=types.MethodType(delayed,conn)
    sys.addaudithook(audit)
    async def run():
        context=main.lifespan(main.app);await context.__aenter__();binding=admission._STATE[id(main.app)]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
            await login(client,messages);watch['active']=True
            task=asyncio.create_task(client.get('/api/research/not-a-uuid/records'));exit_task=None
            try:
                await wait_event(paused);exit_task=asyncio.create_task(context.__aexit__(None,None,None))
                end=asyncio.get_running_loop().time()+5
                while binding.history_deadline is None:
                    assert asyncio.get_running_loop().time()<end;await asyncio.sleep(.01)
                deadline=binding.history_deadline;ticks=0
                while not exit_task.done():
                    assert binding.history_deadline==deadline
                    assert asyncio.get_running_loop().time()<deadline+3
                    ticks+=1;await asyncio.sleep(.02)
                with pytest.raises(RuntimeError,match='formal Main retirement uncertain'):await exit_task
                assert ticks>5 and held[0].state=='ACTIVE' and binding.history_reads
                assert binding.history_errors and not admission.history_reads_closed(binding)
                assert all(w.parent_fd is not None for w in binding.witnesses)
            finally:release.set();watch['active']=False
            response=await task
            assert response.status_code==503,response.text
            assert binding.history_deadline==deadline and binding.history_errors
            assert not admission.history_reads_closed(binding) and binding.reference in admission._RETIRED_UNCERTAIN
            for witness in binding.witnesses:
                if witness.parent_fd is not None:witness.close()
    asyncio.run(run())


def test_actual_sso_identity_rejection_still_tracks_replay_and_auth_connections(prepared):
    main,admission,_,messages=prepared;watch={'active':False};types_seen=[]
    def audit(event,args):
        if event=='sqlite3.connect/handle' and watch['active']:
            worker=admission._READ_WORKER.get()
            # Source's independent supervisor may open its own connection here.
            # Observe only this request's actual native identity worker.
            if worker is not None:
                assert worker.stage=='identity'
                types_seen.append(type(args[0]).__name__)
    sys.addaudithook(audit)
    async def run():
        from api import sso
        import jwt
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                started=await client.get('/api/sso/start',follow_redirects=False);assert started.status_code==303
                state=jwt.decode(started.cookies.get(sso._STATE_COOKIE),os.environ['STRUCTURAL_SSO_SECRET'],algorithms=['HS256'],audience='structural-beta-start',issuer=BETA)
                issued=await client.post('/api/sso/issue',json={'audience':'structural-beta','state':state['state'],'nonce':state['nonce']},headers={'Origin':BETA});assert issued.status_code==200
                exchanged=await client.post('/api/sso/exchange',json={'code':issued.json()['code'],'state':state['state']},headers={'Origin':BETA});assert exchanged.status_code==200
                watch['active']=True
                try:response=await client.get('/api/research/not-a-uuid/records')
                finally:watch['active']=False
                assert response.status_code==401,response.text
                assert 'PrivateSsoConnection' in types_seen and 'PrivateAuthConnection' in types_seen
                assert admission.history_reads_closed(binding)
    asyncio.run(run())


def test_pending_worker_withdrawal_refuses_late_private_io(prepared,monkeypatch):
    main,admission,_,messages=prepared
    from api import research
    queued=threading.Event();release=threading.Event();done=threading.Event();slots=[];outcome=[]
    original=research._history_worker
    def delayed(slot):
        if slot.stage=='identity':
            slots.append(slot);queued.set()
            try:
                assert release.wait(10)
                try:return original(slot)
                except admission.HistoryReadUnavailable as error:outcome.append(type(error));raise
            finally:done.set()
        return original(slot)
    monkeypatch.setattr(research,'_history_worker',delayed)
    async def run():
        context=main.lifespan(main.app);await context.__aenter__()
        binding=admission._STATE[id(main.app)];exit_task=None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
            await login(client,messages)
            task=asyncio.create_task(client.get('/api/research/not-a-uuid/records'))
            try:
                await wait_event(queued);assert slots[0].state=='PENDING'
                exit_task=asyncio.create_task(context.__aexit__(None,None,None))
                end=asyncio.get_running_loop().time()+5
                while not binding.retired:
                    assert asyncio.get_running_loop().time()<end;await asyncio.sleep(.01)
                assert slots[0].state=='CANCELLED' and not exit_task.done()
            finally:release.set()
            response=await task;await wait_event(done)
            assert response.status_code==503 and outcome==[admission.HistoryReadUnavailable]
            await exit_task
            assert admission.history_reads_closed(binding)
            assert all(w.parent_fd is None for w in binding.witnesses)
    asyncio.run(run())


def test_active_raw_request_cancel_keeps_original_source_until_creator_finally(prepared,monkeypatch):
    main,admission,_,messages=prepared
    from research import source_integration
    from api import research
    failures=[];native_worker=research._history_worker
    def observed_worker(slot):
        try:return native_worker(slot)
        except Exception as error:
            failures.append((slot.stage,type(error).__name__,str(error)));raise
    monkeypatch.setattr(research,'_history_worker',observed_worker)
    from .test_formal_main_admission import envelope,problem
    original=source_integration.raw_preparations
    queued=threading.Event();release=threading.Event();done=threading.Event();held=[]
    def delayed(*args,**kwargs):
        worker=admission._READ_WORKER.get();held.append(worker)
        assert worker.stage=='raw' and worker.read.source is kwargs['request_source']
        queued.set()
        try:
            assert release.wait(10)
            assert worker.read.source.active
            return original(*args,**kwargs)
        finally:done.set()
    monkeypatch.setattr(source_integration,'raw_preparations',delayed)
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                made=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':'borrow-raw-cancel-create'})
                assert made.status_code==200,made.text
                rid=made.json()['data']['research']['id']
                task=asyncio.create_task(client.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':str(uuid4())}))
                try:
                    try:await wait_event(queued,timeout=15)
                    except AssertionError:pytest.fail(repr(failures))
                    read=held[0].read;source=read.source
                    task.cancel();await asyncio.sleep(0)
                    # AnyIO may defer outer cancellation until this original
                    # active worker returns. Cancellation cannot retire it.
                    assert held[0].state=='ACTIVE' and source.active and binding.history_reads
                finally:
                    release.set()
                    if held:await wait_event(done)
                with pytest.raises(asyncio.CancelledError):await task
                end=asyncio.get_running_loop().time()+5
                while not admission.history_reads_closed(binding):
                    assert asyncio.get_running_loop().time()<end;await asyncio.sleep(.01)
                assert not source.active and held[0].state=='RETIRED'
    asyncio.run(run())


def test_source_closed_real_history_records_keep_current_acl_and_original_receipt(tmp_path,monkeypatch,smtp):
    import importlib,secrets,time
    from web.backend.tests.acceptance.source_history_fixture import prepared_source_history
    root=Path(__file__).resolve().parents[3]
    with prepared_source_history(root,tmp_path/'history',target_revision=False) as seed:
        port,messages=smtp
        for key,value in {'STRUCTURAL_SHARE_TOKEN_SECRET':secrets.token_urlsafe(48),
                'SMTP_HOST':'127.0.0.1','SMTP_PORT':str(port),'SMTP_FROM_EMAIL':'sender@example.invalid',
                'ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','SMTP_STARTTLS':'false',
                'SMTP_USE_SSL':'false','SMTP_TIMEOUT_SECONDS':'2'}.items():monkeypatch.setenv(key,value)
        for key in ('STRUCTURAL_HISTORY_DB','STRUCTURAL_FAVORITES_PATH','STRUCTURAL_DATA_DIR',
                'STRUCTURAL_MODEL_PATH','STRUCTURAL_PRECOMPUTED_EMBEDDINGS','STRUCTURAL_ARTIFACT_MANIFEST',
                'SMTP_USERNAME','SMTP_PASSWORD','OPENROUTER_API_KEY','DEEPSEEK_API_KEY','SENTRY_DSN'):
            monkeypatch.delenv(key,raising=False)
        main=importlib.import_module('main')
        from services import formal_admission as admission
        async def run():
            async with main.lifespan(main.app):
                binding=admission._STATE[id(main.app)]
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                    await login(client,messages,seed.email)
                    admission.close_source(binding,deadline_monotonic=time.monotonic()+10)
                    receipt=binding.source_receipt
                    assert admission.source_closed(binding)
                    path='/api/research/'+seed.research_id
                    pages={}
                    for kind in ('sources','excerpts','claims','reports'):
                        response=await client.get(path+'/records',params={'task_id':seed.source_task_id,'kind':kind})
                        assert response.status_code==200,response.text
                        pages[kind]=response.json()['data']['items'];assert pages[kind]
                        assert admission.history_reads_closed(binding)
                        assert binding.source_receipt is receipt and not binding.source_errors
                    assert all(item['accessed_at']==seed.acquired_at for item in pages['sources'])
                    for ref in seed.excerpt_refs:
                        item=next(item for item in pages['excerpts'] if item['id']==ref['excerpt_id'])
                        assert (item['source_revision'],item['text_digest'],item['start'],item['end'])==(
                            ref['source_revision'],ref['content_digest'],ref['start'],ref['end'])
                    raw=await client.get(path+'/source-raw-preparations',params={'task_id':seed.source_task_id})
                    # Ordinary Source13 snapshots provide no raw-preparation record.
                    assert raw.status_code==503 and raw.json()['error']['code']=='STORE_UNAVAILABLE'
                    assert 'data' not in raw.json()
                    assert admission.history_reads_closed(binding)
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as other:
                        await login(other,messages,'borrow-other@example.invalid')
                        denied=await other.get(path+'/records',params={'task_id':seed.source_task_id,'kind':'excerpts'})
                        assert denied.status_code==404 and 'data' not in denied.json()
                    old=httpx.Cookies(client.cookies)
                    assert (await client.post('/api/auth/logout',headers={'Origin':BETA})).status_code==200
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA,cookies=old) as revoked:
                        denied=await revoked.get(path+'/records',params={'task_id':seed.source_task_id,'kind':'excerpts'})
                        assert denied.status_code==401 and 'data' not in denied.json()
                    await login(client,messages,seed.email)
                    assert (await client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':BETA})).status_code==200
                    await login(client,messages,seed.email)
                    denied=await client.get(path+'/records',params={'task_id':seed.source_task_id,'kind':'excerpts'})
                    assert denied.status_code==404 and 'data' not in denied.json()
                    assert admission.history_reads_closed(binding) and binding.source_receipt is receipt and not binding.source_errors
        asyncio.run(run())


def test_real_alternate_namespace_connection_uses_the_same_active_request(prepared,monkeypatch):
    import importlib
    from api import research
    main,admission,paths,messages=prepared
    other_paths=importlib.import_module('web.backend.services.runtime_paths')
    other_utils=importlib.import_module('web.backend.services.sqlite_utils')
    other_admission=importlib.import_module('web.backend.services.formal_admission')
    for attr in ('STATE_ROOT','CACHE_ROOT','LOG_ROOT'):monkeypatch.setattr(other_paths,attr,getattr(paths,attr))
    assert other_admission._READ_CONTEXT is admission._READ_CONTEXT
    observed=[];native_identity=research._identity
    def observe_identity(request):
        # Keep the real credential producer and its exact result. The extra
        # readonly native open occurs after its return, outside audit callbacks.
        identity=native_identity(request)
        worker=admission._READ_WORKER.get()
        assert worker is not None and worker.stage=='identity'
        store=worker.read.binding.service.store
        with other_utils.connect_private_auth(store.path,readonly=True,expected_identity=store.storage_identity) as conn:
            assert conn._history_read_resource.worker is worker
            assert conn.execute('SELECT 1').fetchone()[0]==1
        assert conn._native_close_state=='closed' and conn._history_file is None
        observed.append(worker)
        return identity
    monkeypatch.setattr(research,'_identity',observe_identity)
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                response=await client.get('/api/research/not-a-uuid/records')
                assert response.status_code==404,response.text
                assert observed and admission.history_reads_closed(binding)
    asyncio.run(run())


def test_actual_main_missing_history_binding_is_unavailable_before_and_after_lifespan(prepared):
    main,admission,_,_=prepared
    async def check(client):
        assert id(main.app) not in admission._STATE
        assert (await client.get('/api/research')).status_code==503
        for suffix in ('records','source-raw-preparations'):
            response=await client.get('/api/research/not-a-uuid/'+suffix)
            assert response.status_code==503,response.text
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app,raise_app_exceptions=False),base_url=BETA) as client:
            await check(client)
            async with main.lifespan(main.app):
                binding=admission._STATE[id(main.app)]
                assert admission.history_reads_closed(binding)
            assert binding.retired and admission.history_reads_closed(binding)
            await check(client)
            assert not binding.history_reads and not binding.history_errors
    asyncio.run(run())


def _pause_native_raw_retirement(admission,paused,release,held,monkeypatch):
    import inspect
    lines,start=inspect.getsourcelines(admission.end_history_worker)
    target=start+next(i for i,line in enumerate(lines) if '_READ_WORKER.reset(worker.token)' in line)
    native_code=admission.end_history_worker.__code__
    from api import research
    native_worker=research._history_worker
    previous=threading.gettrace();paused.observations=[]
    def observe(frame,event,arg):
        if event=='call' and frame.f_code.co_name=='end_history_worker':
            actual=frame.f_locals.get('worker')
            paused.observations.append({'stage':getattr(actual,'stage',None),'same_code':frame.f_code is native_code})
        if frame.f_code is not native_code:return None
        if event=='line' and frame.f_lineno==target:
            worker=frame.f_locals['worker']
            paused.observations.append({'line':target,'stage':worker.stage,'ended':worker.read.ended})
            if worker.stage=='raw' and not held and not worker.read.ended:
                assert worker.read.source is not None and worker.read.source.active
                held.append(worker);paused.set()
                assert release.wait(5),'owned retirement point not released'
        return observe
    def traced_worker(slot):
        if slot.stage!='raw':
            import time,json
            started=time.monotonic();outcome='returned';kind=None
            paused.observations.append({'entered_stage':slot.stage})
            try:
                result=native_worker(slot);kind=type(result).__name__;return result
            except BaseException as error:
                outcome='raised:'+type(error).__name__;raise
            finally:
                print('BORROW_R1_STAGE:'+json.dumps({'stage':slot.stage,'seconds':time.monotonic()-started,
                    'outcome':outcome,'result_kind':kind,'thread':threading.get_ident()}),flush=True)
        import time,json,hashlib
        started=time.monotonic();old=sys.gettrace();sys.settrace(observe);outcome='returned'
        try:return native_worker(slot)
        except BaseException as error:
            outcome='raised:'+type(error).__name__;raise
        finally:
            sys.settrace(old)
            print('BORROW_R1_TRACE:'+json.dumps({'native_module':native_worker.__module__,
                'native_worker_sha256':hashlib.sha256(Path(native_worker.__code__.co_filename).read_bytes()).hexdigest(),
                'same_input_slot':slot is held[0] if held else False,'stage':slot.stage,'thread':threading.get_ident(),
                'seconds':time.monotonic()-started,'trace_restored':sys.gettrace() is old,'outcome':outcome}),flush=True)
    monkeypatch.setattr(research,'_history_worker',traced_worker)
    return previous


async def _settle_actual_read_cancellation(task,target):
    if target=='outer':
        with pytest.raises(asyncio.CancelledError):await task
    else:
        try:await task
        except asyncio.CancelledError:pass
        except RuntimeError as error:assert str(error)=='No response returned.'


@pytest.mark.parametrize('cancel_target',['api','outer'])
def test_actual_request_cancel_and_worker_retirement_hand_off_one_action_closer(prepared,monkeypatch,cancel_target):
    from .test_formal_main_admission import envelope,problem
    main,admission,_,messages=prepared
    paused=threading.Event();release=threading.Event();held=[]
    previous=_pause_native_raw_retirement(admission,paused,release,held,monkeypatch)
    async def run():
        context=main.lifespan(main.app);await context.__aenter__()
        binding=admission._STATE[id(main.app)];task=None
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                made=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':'borrow-retirement-race-create'})
                assert made.status_code==200,made.text
                rid=made.json()['data']['research']['id']
                task=asyncio.create_task(client.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':str(uuid4())}))
                try:
                    try:await wait_event(paused,timeout=15)
                    except AssertionError:pytest.fail(repr(paused.observations))
                    worker=held[0];read=worker.read;source=read.source
                    (read.api_task if cancel_target=='api' else task).cancel()
                    end=asyncio.get_running_loop().time()+2
                    while not read.ended and asyncio.get_running_loop().time()<end:await asyncio.sleep(.005)
                    assert read.ended==(cancel_target=='api')
                    assert worker.state=='ACTIVE' and source.active and read.source_close_state=='LIVE'
                finally:release.set()
                await _settle_actual_read_cancellation(task,cancel_target)
                end=asyncio.get_running_loop().time()+5
                while not admission.history_reads_closed(binding):
                    assert asyncio.get_running_loop().time()<end;await asyncio.sleep(.005)
                assert worker.state=='RETIRED' and not read.resources and read.source is None
                assert read.source_close_state=='CLOSED' and read.source_closer is None and not source.active
                assert not binding.history_errors
        finally:
            release.set()
            if task is not None and not task.done():
                task.cancel()
                try:await task
                except (asyncio.CancelledError,RuntimeError):pass
            await context.__aexit__(None,None,None)
        assert admission.source_closed(binding) and not binding.source_errors
        assert all(w.parent_fd is None for w in binding.witnesses)
    try:asyncio.run(run())
    finally:release.set();threading.settrace(previous)


@pytest.mark.parametrize('when',['before','after'])
def test_actual_action_close_inflight_holds_main_and_failure_remains_sticky(request,tmp_path,monkeypatch,when):
    if isolated_fault_case(request,tmp_path,'action-'+when):return
    from .test_formal_main_admission import envelope,problem
    from research.paid_control import AuthenticatedActionSource
    main,admission,_,messages=request.getfixturevalue('prepared')
    if when=='after':
        # Fixed parsing dependency is ordinary setup, before the timed live
        # scheduling observation. No second request or runtime grant is added.
        from research.source_document_raw import read_query
        assert callable(read_query)
    paused=threading.Event();release=threading.Event();held=[]
    close_paused=threading.Event();close_release=threading.Event();attempts=[]
    previous=_pause_native_raw_retirement(admission,paused,release,held,monkeypatch)
    original_close=AuthenticatedActionSource.close
    def close(source):
        if held and source is held[0].read.source:
            read=held[0].read
            assert not admission._LIFETIME_LOCK._is_owned()
            assert read.source_close_state=='CLOSING' and read.source_closer is held[0]
            attempts.append(threading.current_thread());close_paused.set()
            assert close_release.wait(10),'owned action close not released'
            if when=='after':original_close(source)
            raise OSError('owned action close fault')
        return original_close(source)
    async def run():
        context=main.lifespan(main.app);await context.__aenter__()
        binding=admission._STATE[id(main.app)];task=None;exit_task=None
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                made=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':'borrow-action-close-fault'})
                assert made.status_code==200,made.text
                rid=made.json()['data']['research']['id']
                task=asyncio.create_task(client.get('/api/research/'+rid+'/source-raw-preparations',params={'task_id':str(uuid4())}))
                try:
                    try:await wait_event(paused,timeout=15)
                    except AssertionError:pytest.fail(repr(paused.observations))
                    worker=held[0];read=worker.read;source=read.source
                    # Fault only after the real request, action, and raw worker
                    # have been born under their unchanged production methods.
                    monkeypatch.setattr(AuthenticatedActionSource,'close',close)
                    read.api_task.cancel()
                    end=asyncio.get_running_loop().time()+2
                    while not read.ended:
                        assert asyncio.get_running_loop().time()<end;await asyncio.sleep(.005)
                    release.set();await wait_event(close_paused)
                    assert worker.state=='RETIRED' and not read.resources
                    assert read.source_close_state=='CLOSING' and binding.history_reads
                    exit_task=asyncio.create_task(context.__aexit__(None,None,None))
                    end=asyncio.get_running_loop().time()+5
                    while binding.history_deadline is None:
                        assert asyncio.get_running_loop().time()<end;await asyncio.sleep(.005)
                    deadline=binding.history_deadline
                    assert binding.retired and id(main.app) not in admission._STATE
                    assert not exit_task.done() and all(w.parent_fd is not None for w in binding.witnesses)
                finally:release.set();close_release.set()
                await _settle_actual_read_cancellation(task,'api')
                with pytest.raises(RuntimeError,match='formal Main retirement uncertain'):await exit_task
                assert binding.history_deadline==deadline and len(attempts)==1
                assert read.source is source and read.source_close_state=='UNCERTAIN'
                assert read.source_closer is worker and binding.history_reads and binding.history_errors
                assert binding.reference in admission._RETIRED_UNCERTAIN and not admission.history_reads_closed(binding)
                assert admission.source_closed(binding) and not binding.source_errors
                assert source.active==(when=='before')
                # A second end notification cannot claim or retry the uncertain
                # close. The original read and source remain retained.
                assert all(w.state in ('RETIRED','CANCELLED') for w in read.workers.values())
                assert len(attempts)==1
        finally:
            release.set();close_release.set()
            if exit_task is None:await context.__aexit__(None,None,None)
            if held and when=='before':original_close(held[0].read.source)
            for witness in binding.witnesses:
                if witness.parent_fd is not None:witness.close()
    try:asyncio.run(run())
    finally:release.set();close_release.set();threading.settrace(previous)
