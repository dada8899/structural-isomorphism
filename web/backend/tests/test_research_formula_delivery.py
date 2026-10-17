"""Actual V9/V10 SQLite, HTTP and local-child boundaries; no network/model."""
from contextlib import closing
import os
import sqlite3
from pathlib import Path
import pytest
from .test_research_persistence import stack,create,post,problem

from api import auth
from research import ResearchStore
from research.formula_runtime import formula_maintenance,FormulaMaintenance
from research.errors import ResearchError

def snapshot(path):
    conn=sqlite3.connect(path)
    try:
        objects=conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name").fetchall()
        rows={name:(tuple(r[1] for r in conn.execute('PRAGMA table_info("'+name+'")')),
            conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall())
            for (name,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        return objects,rows
    finally:conn.close()

@pytest.fixture
def v9(stack,monkeypatch):
    client,path=stack
    with monkeypatch.context() as legacy:
        legacy.setattr(ResearchStore,"_initialize_current",lambda self,conn:False)
        rid=create(client)
    store=ResearchStore(auth._store())
    os.chmod(path,0o600)
    return client,path,rid,store


def test_v10_explicit_maintenance_preserves_old_rows_refs_and_inode(v9):
    _,path,rid,store=v9
    before=snapshot(path);inode=path.stat().st_ino
    with formula_maintenance(store) as maintenance:
        store.migrate_formula_v10(maintenance=maintenance)
        assert maintenance.conn.execute('PRAGMA foreign_keys').fetchone()[0]==1
    assert path.stat().st_ino==inode
    after=snapshot(path)
    for name,(columns,values) in before[1].items():
        if name!='research_schema':assert after[1][name]==(columns,values)
    reopened=ResearchStore(auth._store())
    with reopened.transaction() as conn:
        reopened._check_v10(conn)
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==10
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    with pytest.raises(PermissionError):store.migrate_formula_v10(maintenance=True)


def test_maintenance_verified_backup_restores_same_database_inode(v9):
    _,path,_,store=v9;before=snapshot(path);inode=path.stat().st_ino
    with formula_maintenance(store) as maintenance:
        store.migrate_formula_v10(maintenance=maintenance)
        maintenance.restore()
    assert snapshot(path)==before and path.stat().st_ino==inode


@pytest.mark.parametrize('change',['missing','unknown','half'])
def test_v9_preflight_rejects_damaged_graph_before_mutation(v9,change):
    _,path,_,store=v9
    with closing(sqlite3.connect(path)) as conn, conn:
        if change=='missing':conn.execute('DROP TRIGGER research_method_no_replace')
        elif change=='unknown':conn.execute('CREATE INDEX unknown_formula_idx ON research_tasks(phase)')
        else:conn.execute('CREATE TABLE research_formula_revisions (id TEXT)')
    before=snapshot(path)
    with pytest.raises(ResearchError):
        with formula_maintenance(store):pass
    assert snapshot(path)==before


def test_actual_wal_reader_prevents_maintenance_in_bounded_time(v9):
    _,path,_,store=v9
    reader=sqlite3.connect(path,isolation_level=None);reader.execute('BEGIN');reader.execute('SELECT * FROM research_controls').fetchall()
    import time
    start=time.monotonic()
    try:
        with pytest.raises(sqlite3.OperationalError):
            with formula_maintenance(store):pass
        assert time.monotonic()-start<1
        assert reader.in_transaction
    finally:reader.rollback();reader.close()
    with formula_maintenance(store) as maintenance:store.migrate_formula_v10(maintenance=maintenance)


@pytest.mark.parametrize('point',range(9))
def test_each_rebuild_stage_fault_rolls_back_complete_v9(v9,monkeypatch,point):
    _,path,_,store=v9;before=snapshot(path);hit=[]
    from research.formula_runtime import FORMULA_DDL
    targets=('CREATE TABLE research_tasks_v10','CREATE TABLE research_steps_v10','INSERT INTO research_tasks_v10',
        'DROP TABLE research_steps','DROP TABLE research_tasks','ALTER TABLE research_tasks_v10',
        FORMULA_DDL[0],FORMULA_DDL[-1],'UPDATE research_schema SET version=10')
    connect=sqlite3.connect
    class Fault(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if sql.startswith(targets[point]):hit.append(True);raise sqlite3.OperationalError('owned migration fault')
            return super().execute(sql,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,factory=Fault,**k))
    with pytest.raises(sqlite3.OperationalError):
        with formula_maintenance(store) as maintenance:
            with pytest.raises(sqlite3.OperationalError):store.migrate_formula_v10(maintenance=maintenance)
            assert maintenance.conn.execute('PRAGMA foreign_keys').fetchone()[0]==1
            raise sqlite3.OperationalError('owned propagated fault')
    assert hit and snapshot(path)==before


def test_v10_default_deny_and_replacement_with_recursive_triggers_off(v9):
    _,path,_,store=v9
    with formula_maintenance(store) as maintenance:store.migrate_formula_v10(maintenance=maintenance)
    with store.transaction(write=True) as conn:
        conn.execute('PRAGMA recursive_triggers=OFF')
        for sql in ("INSERT INTO research_formula_revisions VALUES('forged',1,'{}','"+'a'*64+"')",
                "UPDATE research_formula_runs SET result_json='{}'",'DELETE FROM research_formula_runs'):
            with pytest.raises(sqlite3.DatabaseError):conn.execute(sql)
    with closing(sqlite3.connect(path)) as conn, conn:
        with pytest.raises(sqlite3.DatabaseError):conn.execute("INSERT INTO research_formula_revisions VALUES('forged',1,'{}','"+'a'*64+"')")


def test_exact_cold_install_v10_and_late_completed_peer_reopen(stack):
    client,path=stack
    rid=create(client)
    store=ResearchStore(auth._store())
    with store.transaction() as conn:store._check_v10(conn)
    before=snapshot(path)
    reopened=ResearchStore(auth._store())
    with reopened.transaction() as conn:reopened._check_v10(conn)
    assert snapshot(path)==before


@pytest.mark.parametrize('maintenance_attempt',[False,True])
def test_failed_maintenance_preserves_real_peer_wal_and_later_parent_commit(v9,maintenance_attempt):
    _,path,_,store=v9
    import subprocess,sys,json
    child="""import sqlite3,sys,json
c=sqlite3.connect(sys.argv[1],isolation_level=None,timeout=.2)
try:
 if sys.argv[2]=='write':c.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('peer@example.invalid','free','synthetic','generation')")
 print(json.dumps([r[0] for r in c.execute('SELECT email FROM auth_users ORDER BY email')]))
finally:c.close()
"""
    def peer(operation='read'):
        result=subprocess.run([sys.executable,'-B','-c',child,str(path),operation],capture_output=True,text=True,timeout=5)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    parent=sqlite3.connect(path,isolation_level=None)
    try:
        parent.execute('BEGIN');parent.execute('SELECT count(*) FROM auth_users').fetchall()
        if maintenance_attempt:
            with pytest.raises(sqlite3.OperationalError):
                with formula_maintenance(store):pass
        peer()
        assert path.with_name(path.name+'-wal').exists() and path.with_name(path.name+'-shm').exists()
        parent.rollback()
        parent.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('parent@example.invalid','free','synthetic','generation')")
        parent.commit()
        assert 'parent@example.invalid' in peer()
        assert {'parent@example.invalid','peer@example.invalid'}<=set(peer('write'))
    finally:parent.close()


def test_maintenance_closes_every_native_resource_after_cleanup_failure(v9,monkeypatch):
    _,path,_,store=v9
    from research import formula_runtime
    native_connect=sqlite3.connect;opened=[];closed=[]
    class Fault(sqlite3.Connection):
        def close(self):
            closed.append(id(self));return super().close()
    def connect(*args,**kwargs):
        conn=native_connect(*args,factory=Fault,**kwargs);opened.append(id(conn));return conn
    monkeypatch.setattr(sqlite3,'connect',connect)
    monkeypatch.setattr(formula_runtime,'_require_fk_on',lambda conn:(_ for _ in ()).throw(sqlite3.OperationalError('owned cleanup fault')))
    with pytest.raises(sqlite3.OperationalError,match='owned cleanup fault'):
        with formula_maintenance(store):pass
    assert set(opened)==set(closed)
    # Acquiring from a new FD proves the maintenance flock was released too.
    import fcntl
    fd=os.open(str(path)+'.formula-maintenance',os.O_RDWR|os.O_NOFOLLOW)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    finally:os.close(fd)


def test_v10_retains_exact_method_hook_check(v9):
    _,_,_,store=v9
    with formula_maintenance(store) as maintenance:store.migrate_formula_v10(maintenance=maintenance)
    with store.transaction() as conn:
        conn.create_function('research_method_guard_version',0,lambda:8)
        with pytest.raises(ResearchError):store._check_v10(conn)


def test_bad_auth_policy_refuses_maintenance_before_any_mutation(v9):
    _,path,_,store=v9
    with closing(sqlite3.connect(path)) as conn, conn:conn.execute('UPDATE auth_owner_gate_policy SET fingerprint=?',('0'*64,))
    before=snapshot(path)
    with pytest.raises(RuntimeError,match='configuration mismatch'):
        with formula_maintenance(store):pass
    assert snapshot(path)==before


def test_replaced_inode_is_rejected_before_journal_mutation(v9,monkeypatch):
    _,path,_,store=v9;native=sqlite3.connect
    other=path.with_name('replacement.sqlite3');old=path.with_name('original.sqlite3')
    source=native(path);dest=native(other)
    try:source.backup(dest)
    finally:dest.close();source.close()
    os.chmod(other,0o600);swapped=[];mutations=[]
    class Observe(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            result=super().execute(sql,*args,**kwargs)
            if sql=='PRAGMA journal_mode=DELETE':mutations.append(path.stat().st_ino)
            return result
    def connect(value,*args,**kwargs):
        if str(value).startswith(path.as_uri()) and '?mode=ro' in str(value) and not swapped:
            os.replace(path,old);os.replace(other,path);swapped.append(True)
        return native(value,*args,factory=Observe,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',connect)
    with pytest.raises(PermissionError,match='inode changed'):
        with formula_maintenance(store):pass
    assert not mutations


def test_native_maintenance_open_does_not_recreate_disappearing_path(v9,monkeypatch):
    _,path,_,store=v9;native=sqlite3.connect;hit=[]
    original=path.with_name('moved-original.sqlite3')
    def raced(value,*args,**kwargs):
        if str(value) in (str(path),path.as_uri()+'?mode=rw') and not hit:
            os.replace(path,original);hit.append(True)
        return native(value,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',raced)
    with pytest.raises((PermissionError,sqlite3.OperationalError)):
        with formula_maintenance(store):pass
    assert hit and not path.exists()


def _configure_private_root(path,patch=None):
    import importlib
    path=Path(path).resolve();state=path.parent
    state.chmod(0o700);path.chmod(0o600)
    cache=state.parent/'private-cache';logs=state/'logs'
    for folder in (cache,logs):folder.mkdir(mode=0o700,exist_ok=True)
    for namespace in ('services.runtime_paths','web.backend.services.runtime_paths'):
        module=importlib.import_module(namespace)
        if patch is None:module.STATE_ROOT=state;module.CACHE_ROOT=cache;module.LOG_ROOT=logs
        else:
            for name,value in (('STATE_ROOT',state),('CACHE_ROOT',cache),('LOG_ROOT',logs)):patch.setattr(module,name,value)
    if patch is None:os.environ['AUTH_DATA_DIR']=str(state);os.environ['STRUCTURAL_ENV']='prod'
    else:patch.setenv('AUTH_DATA_DIR',str(state));patch.setenv('STRUCTURAL_ENV','prod')
    return path


def test_explicit_offline_provisioning_then_actual_formal_construct_write_and_reopen(v9,monkeypatch):
    client,path,rid,store=v9
    from research.formula_runtime import provision_formula_v10,recover_formula_journal
    from services.auth_store import AuthStore
    old=dict(os.environ)
    try:
        path=_configure_private_root(path,monkeypatch)
        with pytest.raises((ResearchError,RuntimeError)):AuthStore(path)
        result=provision_formula_v10(path)
        assert result['schema_version']==10 and result['backup_scope']=='in_memory_algorithm_recovery_only'
        assert recover_formula_journal(path)['current_app_compatible'] is False
        from services.auth_registration import migrate_private_auth_registration,admit_private_gate
        from .test_research_paid_producers import identity
        actor=identity(client)
        assert migrate_private_auth_registration()['migrated'] is True
        assert admit_private_gate(AuthStore.owner_key(actor.email))['admitted'] is True
        assert recover_formula_journal(path)['current_app_compatible'] is True
        real=ResearchStore(AuthStore(path))
        with real.transaction(write=True) as conn:
            assert conn.execute('SELECT count(*) FROM research_controls WHERE id=?',(rid,)).fetchone()[0]==1
            with pytest.raises(sqlite3.Error):
                conn.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('after-provision@example.invalid','free','synthetic','g')")
        from research import ResearchService
        from research.schemas import RevisionRequest
        ResearchService(real).revise(actor,rid,RevisionRequest(expected_revision=1,problem=problem('after-provision')),'after-provision-revise')
        reopened=ResearchStore(AuthStore(path))
        with reopened.transaction() as conn:
            assert not conn.execute("SELECT 1 FROM auth_users WHERE email='after-provision@example.invalid'").fetchone()
            assert conn.execute('SELECT revision FROM research_revisions WHERE research_id=? ORDER BY revision DESC',(rid,)).fetchone()[0]==2
            assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
    finally:
        os.environ.clear();os.environ.update(old)


def _formula_migration_kill(path,cut):
    path=_configure_private_root(Path(path))
    from research.formula_runtime import provision_formula_v10
    native=sqlite3.connect
    targets={'journal':'PRAGMA journal_mode=DELETE','create':'CREATE TABLE research_tasks_v10',
        'drop':'DROP TABLE research_tasks','marker':'UPDATE research_schema SET version=10'}
    class Crash(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            value=super().execute(sql,*args,**kwargs)
            if cut in targets and sql.startswith(targets[cut]):os._exit(81)
            return value
        def commit(self):
            try:version=super().execute('SELECT version FROM research_schema').fetchone()[0]
            except sqlite3.Error:version=None
            if version==10 and cut=='before-commit':os._exit(81)
            value=super().commit()
            if version==10 and cut=='after-commit':os._exit(82)
            return value
    sqlite3.connect=lambda *a,**k:native(*a,**k) if 'factory' in k else native(*a,factory=Crash,**k)
    provision_formula_v10(path)
    raise AssertionError('owned kill point was not reached')


@pytest.mark.parametrize('cut',['journal','create','drop','marker','before-commit','after-commit'])
def test_real_process_death_recovers_only_complete_profile_and_wal(v9,cut,monkeypatch):
    _,path,rid,store=v9
    import multiprocessing
    from web.backend.tests.test_research_formula_delivery import _formula_migration_kill as target
    old=dict(os.environ);inode=path.stat().st_ino
    context=multiprocessing.get_context('spawn');child=context.Process(target=target,args=(str(path),cut))
    try:
        child.start();child.join(10);assert not child.is_alive() and child.exitcode==(82 if cut=='after-commit' else 81)
        path=_configure_private_root(path,monkeypatch)
        from research.formula_runtime import recover_formula_journal,provision_formula_v10
        from services.auth_store import AuthStore
        recovered=recover_formula_journal(path)
        assert recovered['schema_version']==(10 if cut=='after-commit' else 9)
        assert recovered['current_app_compatible'] is False
        assert path.stat().st_ino==inode
        if cut!='after-commit':
            with pytest.raises((ResearchError,RuntimeError)):AuthStore(path)
            provision_formula_v10(path)
        from services.auth_registration import migrate_private_auth_registration,admit_private_gate
        from .test_research_paid_producers import identity
        assert migrate_private_auth_registration()['migrated'] is True
        assert admit_private_gate(AuthStore.owner_key(identity(v9[0]).email))['admitted'] is True
        assert recover_formula_journal(path)['current_app_compatible'] is True
        current=ResearchStore(AuthStore(path))
        with current.transaction() as conn:
            current._check_v10(conn)
            assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
            assert conn.execute('SELECT 1 FROM research_controls WHERE id=?',(rid,)).fetchone()
    finally:
        if child.is_alive():child.terminate();child.join(2)
        child.close();os.environ.clear();os.environ.update(old)


def test_populated_v9_tasks_events_source_and_legacy_method_financial_refs_survive_exactly(v9,monkeypatch):
    client,path,rid,store=v9
    from research import BudgetLedger,ResearchRunner
    from research.formula_schemas import digest,canonical
    from .test_research_formula_lifecycle import _seed_source
    from uuid import uuid4
    monkeypatch.setenv('STRUCTURAL_C0_ENABLED','true')
    revised=problem();revised['confirmed']=True
    response=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':revised})
    assert response.status_code==200,response.text
    BudgetLedger(store).provision_fixture(1,ttl_seconds=600) # Stored dummy port; never opens transport.
    response=post(client,f'/api/research/{rid}/tasks',{'input_revision':2,'expected_research_version':2,'mode':'research'})
    assert response.status_code==200,response.text
    task=response.json()['data']['task']['id'];ResearchRunner(store).prepare(task)
    _seed_source(path,rid)
    with store.transaction(write=True) as conn:
        pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
        account=conn.execute('SELECT id FROM research_funding_accounts').fetchone()[0]
        permit=conn.execute('SELECT * FROM research_dispatch_permits').fetchone();approval=str(uuid4());session=str(uuid4())
        conn.execute("""INSERT INTO research_paid_approvals(id,principal_id,research_id,payload_json,payload_digest,state,mode,policy_revision,funding_source_ref,account_id,task_id,dispatch_id,expires_at,created_at)
            VALUES(?,?,?,'{}',?,'draft','offline_probe','bounded_usage_upper_v2','synthetic-old-reference',?,?,?,2000000000,'2026-10-17T00:00:00Z')""",(approval,pid,rid,'a'*64,account,task,permit['dispatch_id']))
        # Genuine legacy_unproved metadata. No fresh body/receipt or execution
        # attestation is forged to populate a migration test.
        conn.execute("INSERT INTO research_provider_sessions(id,approval_id,dispatch_id,permit_id,mode,binding_digest,state) VALUES(?,?,?,?,'offline_probe',?,'created')",(session,approval,permit['dispatch_id'],permit['id'],'b'*64))
    before=snapshot(path)
    for table in ('research_tasks','research_steps','research_task_events','research_evidence_objects','research_funding_accounts','research_reservations','research_dispatch_permits','research_paid_approvals','research_provider_sessions'):
        assert before[1][table][1],table
    with formula_maintenance(store) as capability:store.migrate_formula_v10(maintenance=capability)
    after=snapshot(path)
    for table,(columns,values) in before[1].items():
        if table!='research_schema':assert after[1][table]==(columns,values),table
    response=client.get(f'/api/research/{rid}')
    assert response.status_code==200,response.text
    assert response.json()['data']['task']['id']==task


@pytest.mark.parametrize('helper',['_migrate_v8_if_ready','_migrate_v9_if_ready'])
def test_completed_v10_helpers_recheck_complete_graph_instead_of_only_marker(stack,helper):
    client,path=stack;create(client);store=ResearchStore(auth._store())
    with store.transaction(write=True) as conn:conn.execute('DROP TRIGGER research_method_birth')
    before=snapshot(path)
    with pytest.raises(ResearchError):getattr(store,helper)()
    assert snapshot(path)==before
