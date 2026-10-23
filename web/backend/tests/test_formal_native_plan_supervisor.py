"""Actual Main closed-native and wait-boundary evidence; no live authority.

The Linux grant/key/worker/paid positive remains the separately authorized A/B/C
integration gate. Tests do not install a fake registry or relax a SQL producer.
"""
import time
import threading
from pathlib import Path
import pytest
from research import native_plan_supervisor as c
from research.errors import ResearchError


def test_unregistered_scopes_and_receipts_cannot_install_or_authorize():
    for action in (
        lambda:c.prepare_main_context(object(),object()),
        lambda:c.require_startup_scope({'ready':True},object()),
        lambda:c.require_lifecycle_scope({'action':'revoke'},object(),object(),action='revoke'),
        lambda:c.require_slot({'stop_fd':0},object(),object(),task_id='fake',purpose='phenomenon_plan_v1',mode='execute'),
        lambda:c.require_worker(object(),object(),object(),startup_scope=object()),
        lambda:c.require_worker_retired(None,object(),object(),lifecycle_scope={'action':'retire'}),
        lambda:c.bounded_revoke_transaction({'action':'revoke'},object(),object()),
    ):
        with pytest.raises((ResearchError,RuntimeError,AttributeError,TypeError)):action()
    assert c.database_budget('/synthetic/unbound') is None
    assert c.safe_status(object())==('closed','FUNDING_CLOSED')


@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),float('-inf'),0,-1,'20'])
def test_absolute_cleanup_deadline_rejects_invalid_values(value):
    with pytest.raises(ValueError):c._deadline(value)


def test_actual_main_missing_b_keeps_source_history_and_shared_birth_budget(tmp_path):
    from .test_research_evidence_method_plan import actual
    from services import formal_admission
    from research import source_supervisor
    with actual(tmp_path) as (service,client,store,actor):
        binding=formal_admission._STATE[id(service.app)]
        scope=binding.native_context;native=binding.native_supervisor
        assert type(scope) is c.MainStartupScope and scope.store is binding.service.store
        assert scope.store.storage_identity==store.storage_identity and scope.store.path==store.path
        assert c._CONTEXTS[id(service.app)] is scope and native.context is scope
        assert native.session is None and native.worker is None and native._resources==()
        assert c.safe_status(service.app)==('closed','FUNDING_CLOSED')
        deadline=time.monotonic()+3
        while source_supervisor._REGISTRY[id(service.app)]._state!='READY':
            source=source_supervisor._REGISTRY[id(service.app)]
            if source._failure:
                import traceback
                detail=[(type(e).__name__,[(Path(frame.filename).name,frame.lineno,frame.name) for frame in traceback.extract_tb(e.__traceback__)]) for e in source._errors]
                raise AssertionError(('source lifecycle failure',detail))
            assert time.monotonic()<deadline;time.sleep(.01)
        source=source_supervisor._REGISTRY[id(service.app)]
        budgets=c._THREADS[source._thread]
        assert len(budgets)==1 and budgets[0].scope is scope and budgets[0].scope.budget is scope.budget
        assert scope.budget._deadline is None
        with pytest.raises(ResearchError):c.require_startup_scope(scope,scope.store)  # actual different thread
        with pytest.raises((TypeError,AttributeError)):scope.store=object()
        status,value=client.request('GET','/api/research/'+service.seed.research_id)
        assert status==200 and value['data']['research']['id']==service.seed.research_id
        with store.transaction() as conn:
            assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
            assert conn.execute('SELECT count(*) FROM research_plan_native_funding').fetchone()[0]==0
            assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==0
    assert id(service.app) not in c._CONTEXTS and id(service.app) not in c._SUPERVISORS
    assert not source._thread.is_alive()


def test_actual_registered_source_thread_bounds_all_wait_paths_and_stop_retry(tmp_path,monkeypatch):
    """Observe real Source-thread budget; no fake scope or financial writer.

    The test-only queue asks the already-born Source thread to exercise the
    unchanged real Owner/Auth/SQLite entry points before its original selector.
    No task is inserted, claimed, sent or replayed by this observation wrapper.
    """
    import queue,sqlite3
    from research import source_supervisor
    from research.authorization import AuthorizationGate
    from services import sqlite_utils,formal_admission
    from services.runtime_paths import HISTORY_OPEN_LOCK
    from .test_research_evidence_method_plan import actual
    commands=queue.Queue();answers=queue.Queue();busy_seen=threading.Event();gate_entries=[]
    original=source_supervisor._select;real_flock=__import__('fcntl').flock
    def tracked_flock(fd,operation):
        if threading.current_thread().name=='structure-source-supervisor' and operation & __import__('fcntl').LOCK_EX:
            gate_entries.append(True)
        return real_flock(fd,operation)
    monkeypatch.setattr(__import__('fcntl'),'flock',tracked_flock)
    def observed(store,**kwargs):
        try:operation=commands.get_nowait()
        except queue.Empty:operation=None
        if operation is not None:
            begin=time.monotonic()
            try:
                budget=sqlite_utils.native_thread_budget(store.path,store.storage_identity)
                result=operation(store)
                answers.put(('ok',result,time.monotonic()-begin,id(budget.scope.budget)))
            except BaseException as error:
                answers.put(('error',getattr(error,'code',getattr(error,'sqlite_errorname',type(error).__name__)),time.monotonic()-begin,None))
        try:return original(store,**kwargs)
        except ResearchError as error:
            if error.code=='STORE_BUSY':busy_seen.set()
            raise
    monkeypatch.setattr(source_supervisor,'_select',observed)
    with actual(tmp_path) as (service,client,store,actor):
        scope=formal_admission._STATE[id(service.app)].native_context
        source=source_supervisor._REGISTRY[id(service.app)]
        limit=time.monotonic()+3
        while source._state!='READY':assert time.monotonic()<limit;time.sleep(.01)
        with store.transaction() as conn:
            principal=conn.execute('SELECT id,gate_id FROM research_principals WHERE normalized_email=?',(actor.email,)).fetchone()
            pid,gate_id=principal['id'],principal['gate_id']
        def ask(operation):
            commands.put(operation);source._event.set()
            return answers.get(timeout=2)
        def owner_path(target):
            with AuthorizationGate(target).owner_gate(pid,timeout=0):pass
        with AuthorizationGate(store).owner_gate(pid):
            outcome=ask(owner_path)
        assert outcome[0:2]==('error','STORE_BUSY') and outcome[2]<.5 and gate_entries
        with HISTORY_OPEN_LOCK:
            receipt=ask(lambda target:target.auth_store.expected_owner_gate_identity(gate_id))
            def open_path(target):
                conn=sqlite_utils.connect_private_auth(target.path,readonly=True,expected_identity=target.storage_identity)
                conn.close()
            opening=ask(open_path)
        assert receipt[0:2]==opening[0:2]==('error','STORE_BUSY')
        assert max(receipt[2],opening[2])<.5
        def store_write(target):
            with target.transaction(write=True):pass
        def auth_write(target):
            with target.auth_store._connection() as conn:
                conn.execute('BEGIN IMMEDIATE');conn.rollback()
        with store.transaction(write=True):
            writing=ask(store_write);auth=ask(auth_write)
        assert writing[0:2]==('error','STORE_BUSY') and writing[2]<.5
        assert auth[0]=='error' and auth[1] in ('SQLITE_BUSY','SQLITE_LOCKED') and auth[2]<.5
        def snapshots(target):
            with target.transaction() as conn:first=conn.execute('PRAGMA busy_timeout').fetchone()[0]
            with target.auth_store._connection() as conn:second=conn.execute('PRAGMA busy_timeout').fetchone()[0]
            identity=target.auth_store.expected_owner_gate_identity(gate_id)
            return first,second,identity
        ready=ask(snapshots)
        assert ready[0]=='ok' and ready[1][0:2]==(0,0) and ready[3]==id(scope.budget)
        assert scope.budget._deadline is None and source._slot is None and not source._errors
        # Hold the real opening mutex through Main shutdown. Retry must notice
        # native stop without waiting for this lock or creating a fresh D.
        busy_seen.clear()
        before=time.monotonic()
        with HISTORY_OPEN_LOCK:
            source._event.set();assert busy_seen.wait(2)
            service.close()
        assert time.monotonic()-before<20
        assert scope.budget._deadline is not None
        assert source._deadline['absolute']==scope.budget._deadline
        assert not source._thread.is_alive() and not source._errors
    assert id(service.app) not in c._CONTEXTS


def test_actual_start_return_then_attach_failure_preserves_local_handle_and_closes(tmp_path,monkeypatch):
    from services import formal_admission
    from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService
    from research import source_supervisor
    captured=[]
    def fail_attach(app,binding,module,supervisor):
        assert type(supervisor) is c.NativePlanSupervisor and c._SUPERVISORS[id(app)] is supervisor
        assert binding.native_supervisor is None
        captured.append((app,binding,supervisor))
        raise OSError('owned attach-boundary fault')
    monkeypatch.setattr(formal_admission,'attach_native',fail_attach)
    service=FormalMainBrowserService(tmp_path/'attach-failure-main')
    with pytest.raises(RuntimeError):
        with service:raise AssertionError('startup cannot succeed after actual attach failure')
    assert len(captured)==1
    app,binding,supervisor=captured[0]
    assert binding.native_supervisor is supervisor and supervisor._receipt.supervisor_ref==supervisor.reference
    assert supervisor._receipt.state=='CLOSED' and not supervisor._errors
    assert not service.server_thread.is_alive() and id(app) not in c._CONTEXTS
    assert id(app) not in c._SUPERVISORS and id(app) not in source_supervisor._REGISTRY


def test_budget_and_slot_dtos_never_open_native_database_or_mint_worker(monkeypatch):
    from services import sqlite_utils
    for cls,args in (
        (c.MainStartupScope,(object(),object(),object(),object())),
        (c.NativePlanWorkerLease,(object(),)),
        (c.NativeLifecycleScope,(object(),'revoke',time.monotonic()+20)),
        (c.NativePlanSlotLease,(object(),'fake','phenomenon_plan_v1','fake',0,1)),
    ):
        with pytest.raises(TypeError):cls(*args,_factory=c._FACTORY)
    fake=object.__new__(c.NativePlanSlotLease)
    with pytest.raises(ResearchError):c.require_slot(fake,object(),object(),task_id='fake',purpose='phenomenon_plan_v1',mode='execute')
    # A mutable module callback is not the canonical budget lookup.
    monkeypatch.setattr(c,'database_budget',lambda *args: {'deadline':time.monotonic()+20})
    with pytest.raises(RuntimeError):sqlite_utils.native_thread_budget('/no/runtime/read')


def test_actual_main_startup_scope_rejects_changed_birth_and_other_callers(tmp_path,monkeypatch):
    """A real Main-thread startup scope is not live/network authority.

    Observe the original binding check before either worker starts. Temporary
    negative mutations are restored before continuing; no registry is forged.
    """
    from services import formal_admission
    from .test_research_evidence_method_plan import actual
    original=formal_admission._Binding.check;observed=[];inside=False
    def check(binding,**kwargs):
        nonlocal inside
        result=original(binding,**kwargs)
        scope=c._CONTEXTS.get(id(binding.app))
        if scope is not None and not inside and not observed:
            inside=True
            try:
                c.require_startup_scope(scope,scope.store)
                for name,value in (('pid',-1),('epoch',object()),('reference','different-birth')):
                    before=getattr(scope,name);object.__setattr__(scope,name,value)
                    try:
                        with pytest.raises(ResearchError):c.require_startup_scope(scope,scope.store)
                    finally:object.__setattr__(scope,name,before)
                before=scope.store._storage_identity
                object.__setattr__(scope.store,'_storage_identity',(before[0],before[1]+1))
                try:
                    with pytest.raises((ResearchError,RuntimeError)):c.require_startup_scope(scope,scope.store)
                finally:object.__setattr__(scope.store,'_storage_identity',before)
                c.require_startup_scope(scope,scope.store);observed.append(scope)
            finally:
                inside=False
                monkeypatch.setattr(formal_admission._Binding,'check',original)
        return result
    monkeypatch.setattr(formal_admission._Binding,'check',check)
    with actual(tmp_path) as (service,client,store,actor):
        assert len(observed)==1
        scope=observed[0]
        with pytest.raises(ResearchError):c.require_startup_scope(scope,scope.store)
        with pytest.raises(RuntimeError):c.prepare_main_context(scope.binding.service,scope.binding)
        assert scope.binding.native_context is scope and scope.binding.native_supervisor.session is None
