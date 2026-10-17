"""A2 native consumers of a preprovisioned synthetic Auth+Research database."""
import importlib
import multiprocessing
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import pytest
from .test_private_auth_store import private,native,raw
from .test_research_persistence import problem
from research import ResearchStore,ResearchService
from research.authorization import AccountIdentity,AuthorizationGate
from research.errors import ResearchError
from services.auth_store import AuthStore
from services import runtime_paths as paths,sqlite_utils
from .test_research_persistence import stack,post
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs
from .test_research_paid_api import paid_api
from .test_research_lifecycle import lifecycle,delete
from .test_private_registration import register_private_user,corrupt_auth_fixture,FIXTURE_SECRET


@pytest.fixture
def prepared(private,monkeypatch):
    email='a2-owner@example.invalid'
    user,token=register_private_user(monkeypatch,email)
    import jwt
    claims=jwt.decode(token,os.getenv('JWT_SECRET') or FIXTURE_SECRET,algorithms=['HS256'])
    auth=AuthStore(private);generation=user['session_generation']
    gate=auth.owner_gate_id(email)
    folder=private.parent/'research-locks';lock=folder/(gate+'.lock')
    actor=AccountIdentity(email,generation,claims['jti'],claims['exp'])
    store=ResearchStore(auth)
    from research.schemas import CreateResearchRequest
    rid=ResearchService(store).create(actor,CreateResearchRequest(problem=problem()),'a2-preprovision')['data']['research']['id']
    return dict(path=private,auth=auth,store=store,actor=actor,rid=rid,gate=gate,lock=lock)


def test_formal_constructor_and_read_transaction_use_only_native_ro(private,native):
    before=private.read_bytes();store=ResearchStore(AuthStore(private))
    from research.paid_control import _SCOPES,_current_scope
    with store.transaction() as conn:
        assert conn.isolation_level is None and conn.row_factory is sqlite3.Row and conn.in_transaction
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert conn.execute('PRAGMA secure_delete').fetchone()[0]==1
        assert conn.execute('SELECT research_method_guard_version()').fetchone()[0]==9
        scope=_SCOPES[id(conn)];assert scope.conn is conn and scope.pid==os.getpid() and scope.write is False
        with pytest.raises(PermissionError):_current_scope(conn)
        with pytest.raises(sqlite3.OperationalError):conn.execute("INSERT INTO auth_users VALUES('x','free','s','g','active')")
    assert not scope.active and id(conn) not in _SCOPES
    assert private.read_bytes()==before
    assert all(args[0]==':memory:' or args[0]==private.as_uri()+'?mode=ro' for args,_kw,_conn in native)


def test_real_rw_commit_and_rollback_preserve_domain_scope(prepared):
    store=prepared['store']
    with store.transaction(write=True) as conn:
        conn.execute("INSERT INTO revoked_sessions(jti,revoked_at) VALUES('synthetic-commit','synthetic')")
    with pytest.raises(RuntimeError):
        with store.transaction(write=True) as conn:
            conn.execute("INSERT INTO revoked_sessions(jti,revoked_at) VALUES('synthetic-rollback','synthetic')")
            raise RuntimeError('synthetic transaction failure')
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM revoked_sessions WHERE jti='synthetic-commit'").fetchone()[0]==1
        assert conn.execute("SELECT count(*) FROM revoked_sessions WHERE jti='synthetic-rollback'").fetchone()[0]==0


@pytest.mark.parametrize('operation',['_migrate_v4','_migrate_v5','_migrate_v6','_migrate_v7','_migrate_v8','_migrate_v9','_migrate_v8_if_ready','_migrate_v9_if_ready'])
def test_every_migration_entry_rejects_formal_before_native_open(private,native,operation):
    store=ResearchStore(AuthStore(private));start=len(native);before=private.read_bytes()
    with pytest.raises(RuntimeError):getattr(store,operation)()
    assert len(native)==start and private.read_bytes()==before


@pytest.mark.parametrize('fault',['missing','path','identity','config','promote','downgrade'])
def test_captured_profile_and_binding_never_fall_back_to_create(private,native,monkeypatch,fault):
    if fault=='promote':
        monkeypatch.setenv('STRUCTURAL_ENV','dev');store=ResearchStore(AuthStore(private));monkeypatch.setenv('STRUCTURAL_ENV','prod')
    else:store=ResearchStore(AuthStore(private))
    start=len(native)
    if fault=='missing':private.unlink()
    elif fault=='path':store.path=private.with_name('other.sqlite3')
    elif fault=='identity':store.auth_store._storage_identity=(0,0)
    elif fault=='config':monkeypatch.setenv('AUTH_DATA_DIR','')
    elif fault=='downgrade':monkeypatch.setenv('STRUCTURAL_ENV','dev')
    if fault=='downgrade':
        with store.transaction() as conn:assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==10
        assert all(args[0].endswith('?mode=ro') for args,_kw,_conn in native[start:])
    else:
        with pytest.raises((RuntimeError,OSError)):
            with store.transaction():pass
        assert len(native)==start
    assert not private.with_name('other.sqlite3').exists()
    if fault=='missing':assert not private.exists()


@pytest.mark.parametrize('fault',['missing-table','missing-guard','unknown','old-marker','policy','fk'])
def test_formal_full_v9_and_policy_checks_never_repair(private,fault):
    with raw(private) as conn:
        if fault=='missing-table':conn.execute('DROP TABLE research_source_runs')
        elif fault=='missing-guard':conn.execute('DROP TRIGGER '+next(r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='trigger' AND name LIKE 'research_method_%'")))
        elif fault=='unknown':conn.execute('CREATE TABLE research_unexpected(value TEXT)')
        elif fault=='old-marker':conn.execute('UPDATE research_schema SET version=8')
        elif fault=='policy':conn.execute("UPDATE auth_owner_gate_policy SET fingerprint='wrong'")
        else:conn.execute('INSERT INTO research_revisions VALUES(?,?,?,?,?)',(str(uuid4()),1,'{}','a'*64,'synthetic'))
    before=private.read_bytes()
    with pytest.raises((RuntimeError,ResearchError,sqlite3.Error)):ResearchStore(AuthStore(private))
    assert private.read_bytes()==before


@pytest.mark.parametrize('point',['hook','pragma'])
def test_initialization_failure_closes_real_native_connection_and_parent_fd(private,native,monkeypatch,point):
    store=ResearchStore(AuthStore(private));before=len(native)
    if point=='hook':
        import research.store as module
        monkeypatch.setattr(module,'install_default_hook',lambda _conn:(_ for _ in ()).throw(RuntimeError('synthetic hook failure')))
    else:
        execute=sqlite_utils.PrivateAuthConnection.execute
        def failed(conn,sql,*args,**kwargs):
            if sql=='PRAGMA foreign_keys=ON':raise sqlite3.OperationalError('synthetic pragma failure')
            return execute(conn,sql,*args,**kwargs)
        monkeypatch.setattr(sqlite_utils.PrivateAuthConnection,'execute',failed)
    with pytest.raises((RuntimeError,ResearchError)):
        with store.transaction():pass
    assert len(native)==before+1
    assert native[-1][2]._history_file is None


@pytest.mark.parametrize('operation',['_migrate_v4','_migrate_v5','_migrate_v6','_migrate_v7','_migrate_v8','_migrate_v9'])
def test_development_migration_hook_failure_closes_native_connection_without_partial_writes(private,native,monkeypatch,operation):
    import research.store as module
    monkeypatch.setenv('STRUCTURAL_ENV','dev');store=ResearchStore(AuthStore(private))
    before=private.read_bytes();start=len(native)
    monkeypatch.setattr(module,'install_default_hook',lambda _conn:(_ for _ in ()).throw(RuntimeError('synthetic migration hook failure')))
    with pytest.raises(RuntimeError):getattr(store,operation)()
    assert len(native)==start+1 and private.read_bytes()==before


def test_plain_auth_dto_cannot_replace_captured_native_auth_store(private,native):
    from types import SimpleNamespace
    identity=(private.stat().st_dev,private.stat().st_ino)
    fake=SimpleNamespace(path=private,_private_auth=True,storage_identity=identity,preflight_private=lambda _:identity)
    start=len(native)
    with pytest.raises(paths.RuntimePathError):ResearchStore(fake)
    assert len(native)==start


@pytest.mark.parametrize('fault',['inode','file-mode','parent-mode','symlink','sidecar'])
def test_hot_private_file_drift_is_rejected_before_native_open(private,native,fault):
    store=ResearchStore(AuthStore(private));start=len(native)
    if fault in ('inode','symlink'):
        retired=private.with_name('retired.db');private.rename(retired)
        if fault=='inode':private.write_bytes(retired.read_bytes());private.chmod(0o600)
        else:private.symlink_to(retired)
    elif fault=='file-mode':private.chmod(0o644)
    elif fault=='parent-mode':private.parent.chmod(0o755)
    else:
        side=private.with_name(private.name+'-journal');side.write_bytes(b'unsafe sidecar');side.chmod(0o644)
    with pytest.raises((RuntimeError,OSError)):
        with store.transaction():pass
    assert len(native)==start


@pytest.mark.parametrize('fault',['guard','table','marker'])
def test_cached_formal_store_does_not_hide_current_schema_damage(private,fault):
    store=ResearchStore(AuthStore(private))
    with raw(private) as conn:
        if fault=='guard':conn.execute('DROP TRIGGER research_method_birth')
        elif fault=='table':conn.execute('CREATE TABLE research_unapproved(value TEXT)')
        else:conn.execute('UPDATE research_schema SET version=8')
    before=private.read_bytes()
    with pytest.raises(ResearchError):
        with store.transaction():pass
    assert private.read_bytes()==before


def _peer(db,operation,output):
    db=Path(db)
    for name,value in [('STATE_ROOT',db.parent),('CACHE_ROOT',db.parent.parent/'cache'),('LOG_ROOT',db.parent/'logs')]:setattr(paths,name,value)
    os.environ['STRUCTURAL_ENV']='prod';os.environ['AUTH_DATA_DIR']=str(db.parent)
    try:
        auth=AuthStore(db);store=ResearchStore(auth)
        if operation in ('missing-map','missing-lock'):
            gate=auth.owner_gate_id('a2-owner@example.invalid')
            with AuthorizationGate(auth).owner_gate_id(gate):pass
            raise AssertionError('missing owner prerequisite was accepted')
    except (RuntimeError,OSError) as exc:
        if not operation.startswith('missing-'):raise
        output.put(dict(rejected=type(exc).__name__,database_exists=db.exists()));return
    if operation=='write':
        with store.transaction(write=True) as conn:conn.execute("INSERT INTO revoked_sessions(jti,revoked_at) VALUES('synthetic-child','synthetic')")
    with store.transaction() as conn:output.put([r[0] for r in conn.execute('SELECT jti FROM revoked_sessions ORDER BY jti')])


def peer(db,operation):
    from web.backend.tests.test_research_private_storage import _peer as target
    ctx=multiprocessing.get_context('spawn');output=ctx.Queue();child=ctx.Process(target=target,args=(str(db),operation,output))
    try:
        child.start();value=output.get(timeout=20);child.join(5);assert child.exitcode==0;return value
    finally:
        if child.is_alive():child.terminate();child.join(3)
        child.close();output.close();output.join_thread()


def test_same_pid_peer_close_and_cross_process_commits_do_not_drop_wal(private):
    store=ResearchStore(AuthStore(private))
    with store.transaction() as parent:
        parent.execute('SELECT count(*) FROM auth_users').fetchall()
        with store.transaction() as neighbour:neighbour.execute('SELECT count(*) FROM auth_users').fetchall()
        assert peer(private,'read')==[]
        assert all(private.with_name(private.name+s).exists() for s in ('-wal','-shm'))
    with store.transaction(write=True) as conn:conn.execute("INSERT INTO revoked_sessions(jti,revoked_at) VALUES('synthetic-parent','synthetic')")
    assert peer(private,'read')==['synthetic-parent']
    assert peer(private,'write')==['synthetic-child','synthetic-parent']
    assert peer(private,'read')==['synthetic-child','synthetic-parent']


def test_new_process_missing_main_database_cannot_create_it(private):
    private.unlink();before=sorted(p.name for p in private.parent.iterdir())
    value=peer(private,'missing-db')
    assert value['rejected'] and value['database_exists'] is False
    assert sorted(p.name for p in private.parent.iterdir())==before


@pytest.mark.parametrize('fault',['missing-map','missing-lock'])
def test_new_process_missing_owner_prerequisites_cannot_create_mapping_or_lock(prepared,fault):
    if fault=='missing-map':
        with raw(prepared['path']) as conn,corrupt_auth_fixture(conn,'auth_owner_gates'):conn.execute('DELETE FROM auth_owner_gates')
    else:prepared['lock'].unlink()
    before=prepared['path'].read_bytes();names=sorted(p.name for p in prepared['lock'].parent.iterdir())
    value=peer(prepared['path'],fault)
    assert value['rejected'] and value['database_exists'] is True
    assert prepared['path'].read_bytes()==before
    assert sorted(p.name for p in prepared['lock'].parent.iterdir())==names


@pytest.mark.parametrize('namespace',['research.store','web.backend.research.store'])
def test_dual_namespace_consumes_same_auth_inode(private,namespace,monkeypatch):
    module=importlib.import_module(namespace);auth_module=importlib.import_module('web.backend.services.auth_store' if namespace.startswith('web.') else 'services.auth_store')
    if namespace.startswith('web.'):
        from web.backend.services import runtime_paths as other
        for name in ('STATE_ROOT','CACHE_ROOT','LOG_ROOT'):monkeypatch.setattr(other,name,getattr(paths,name))
    store=module.ResearchStore(auth_module.AuthStore(private))
    assert store.storage_identity==(private.stat().st_dev,private.stat().st_ino)
    with store.transaction() as conn:assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==10


def test_checkpoint_busy_is_not_reported_as_erasure_success(private):
    store=ResearchStore(AuthStore(private));reader=sqlite_utils.connect_private_auth(private,readonly=True)
    try:
        reader.execute('BEGIN');reader.execute('SELECT count(*) FROM auth_users').fetchall()
        with store.transaction(write=True) as conn:conn.execute("INSERT INTO revoked_sessions(jti,revoked_at) VALUES('synthetic-checkpoint','synthetic')")
        with pytest.raises(ResearchError) as rejected:store.checkpoint_erasure()
        assert rejected.value.code=='STORE_BUSY'
    finally:reader.close()
    store.checkpoint_erasure()


def _stage_formal_adjacent_assets(db):
    """Test-only stopped fixture setup, never production partial-root repair.

    Source/paid preparation retains its declared isolated profile. Only the
    absent empty adjacent resources are materialized from the reviewed offline
    bootstrap declarations, under the same actual private parent. Existing
    resources must match their full declaration graph and are never repaired.
    """
    from services.auth_registration import (_fresh_history,_fresh_sso,_graph,_expected_graph,_safe_file,_create_file)
    witness=paths.PrivateAuthFile.acquire(db)
    try:
        for name,create in [('history.db',_fresh_history),('sso_replay.sqlite3',_fresh_sso)]:
            try:info=os.stat(name,dir_fd=witness.parent_fd,follow_symlinks=False);fresh=False
            except FileNotFoundError:
                _create_file(witness.parent_fd,name)
                info=os.stat(name,dir_fd=witness.parent_fd,follow_symlinks=False);fresh=True
            _safe_file(info);identity=(info.st_dev,info.st_ino)
            for suffix in ('-wal','-shm','-journal'):
                try:side=os.stat(name+suffix,dir_fd=witness.parent_fd,follow_symlinks=False)
                except FileNotFoundError:continue
                _safe_file(side)
                assert info.st_size>0,'orphan adjacent fixture sidecar'
            conn=sqlite3.connect((db.parent/name).as_uri()+('?mode=rw' if fresh else '?mode=ro'),uri=True,
                isolation_level=None,factory=sqlite_utils.ClosingConnection)
            try:
                conn.execute('BEGIN EXCLUSIVE' if fresh else 'BEGIN')
                if fresh:create(conn)
                assert _graph(conn)==_expected_graph(create),'complete adjacent fixture graph required'
                assert not conn.execute('PRAGMA foreign_key_check').fetchall()
                if fresh:
                    conn.commit()
                    assert conn.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
                else:
                    assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
                    conn.rollback()
                assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            finally:conn.close()
            current=os.stat(name,dir_fd=witness.parent_fd,follow_symlinks=False);_safe_file(current)
            assert (current.st_dev,current.st_ino)==identity
        for name in ('favorites.jsonl','favorites.lock','account_deletion_audit.jsonl'):
            try:info=os.stat(name,dir_fd=witness.parent_fd,follow_symlinks=False)
            except FileNotFoundError:
                _create_file(witness.parent_fd,name);info=os.stat(name,dir_fd=witness.parent_fd,follow_symlinks=False)
            _safe_file(info)
            # This fixture has not produced any legacy Favorites/audit data;
            # an unexpected existing payload is refused, never overwritten.
            assert info.st_size==0,'unexpected existing adjacent fixture payload'
        witness.check()
    finally:witness.close()


def test_staged_adjacent_existing_resources_keep_actual_identity_and_bytes(private):
    names=('history.db','sso_replay.sqlite3','favorites.jsonl','favorites.lock','account_deletion_audit.jsonl')
    before={name:((private.with_name(name).stat().st_dev,private.with_name(name).stat().st_ino),private.with_name(name).read_bytes()) for name in names}
    _stage_formal_adjacent_assets(private)
    after={name:((private.with_name(name).stat().st_dev,private.with_name(name).stat().st_ino),private.with_name(name).read_bytes()) for name in names}
    assert before==after


def test_staged_adjacent_drift_is_refused_without_repair(private):
    target=private.with_name('sso_replay.sqlite3')
    with raw(target) as conn:conn.execute('CREATE TABLE unexpected_adjacent_data(value TEXT)')
    before=target.read_bytes()
    with pytest.raises(AssertionError):_stage_formal_adjacent_assets(private)
    assert target.read_bytes()==before


@pytest.mark.parametrize('fault',['file-mode','sidecar'])
def test_staged_adjacent_unsafe_file_is_refused_before_native_open(private,native,fault):
    target=private.with_name('history.db')
    if fault=='file-mode':target.chmod(0o644)
    else:
        side=target.with_name(target.name+'-wal');side.write_bytes(b'unsafe');side.chmod(0o644)
    with pytest.raises(PermissionError):_stage_formal_adjacent_assets(private)
    assert not native


def _formal_delete(formal_paid,monkeypatch):
    """Actual prod delete router; original paid route remains isolated."""
    from api import auth,favorites,sso,report,report_account
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from .test_private_registration import BETA
    client,db,store,*_=formal_paid;state=db.parent
    with monkeypatch.context() as formal:
        for name,value in {'STRUCTURAL_ENV':'prod','AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':BETA,
            'AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),'STRUCTURAL_HISTORY_DB':str(state/'history.db'),
            'STRUCTURAL_FAVORITES_PATH':str(state/'favorites.jsonl'),'STRUCTURAL_SSO_BETA_ORIGIN':BETA,
            'STRUCTURAL_SSO_PHASE_ORIGIN':'https://phase.bytedance.city','SMTP_HOST':'fixture.invalid','SMTP_PORT':'587',
            'SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid',
            'AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','STRUCTURAL_SHARE_TOKEN_SECRET':'synthetic-share-secret'}.items():formal.setenv(name,value)
        formal.setattr(report,'_store',None);formal.setattr(report_account,'_store',None)
        formal.setattr(sso,'_REPLAY_STORES',{})
        formal.setattr(favorites,'_legacy_data_file',lambda:state/'absent-legacy-favorites.jsonl')
        assert auth._store() is store.auth_store and store.path==db
        application=FastAPI();application.include_router(auth.router,prefix='/api')
        with TestClient(application,base_url=BETA) as deletion:
            deletion.cookies.set(auth._COOKIE_NAME,client.cookies.get(auth._COOKIE_NAME))
            return deletion.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':BETA})


@pytest.fixture
def formal_paid(request,tmp_path,monkeypatch,record_property):
    """Actual offline HTTP composition with captured formal storage objects.

    The public Main remains closed. The test-only route profile is restored
    after capturing the real preprovisioned Auth object; downgrade cannot turn
    either storage object into a dev connection or creation path.
    """
    import json
    import stat
    from uuid import UUID
    from api import auth
    from services.auth_registration import bootstrap_private_runtime
    # Resolve the original paid/source producers only after a real current
    # Auth runtime and account exist. Legacy Auth + Research11 is not an
    # admissible maintenance pair and cannot be made current by a marker edit.
    state=tmp_path.resolve()/'auth';cache=tmp_path.resolve()/'private-cache'
    for name,value in [('STATE_ROOT',state),('CACHE_ROOT',cache),('LOG_ROOT',state/'logs')]:monkeypatch.setattr(paths,name,value)
    for name,value in {'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),
        'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,
        'JWT_SECRET':'research-synthetic-auth-secret-32-characters',
        'STRUCTURAL_SSO_SECRET':'research-synthetic-sso-secret-32-characters'}.items():monkeypatch.setenv(name,value)
    bootstrap_private_runtime()
    monkeypatch.setattr(auth,'_AUTH_STORES',{})
    register_private_user(monkeypatch,'research-a@example.test')
    original_auth=AuthStore(state/'auth.sqlite3')
    monkeypatch.setattr(auth,'_store',lambda:original_auth)
    paid_api=request.getfixturevalue('paid_api')
    client,db,development_store,rid,excerpt,resolver=paid_api
    assert db==original_auth.path and development_store.auth_store is original_auth
    def inspect(label,path,kind,*,phase,required=True):
        try:info=path.lstat()
        except FileNotFoundError:
            record_property('formal_paid_mode.'+label+'.'+phase,json.dumps({'exists':False}))
            assert not required,'missing synthetic prerequisite: '+label
            return None
        actual='directory' if stat.S_ISDIR(info.st_mode) else 'regular' if stat.S_ISREG(info.st_mode) else 'symlink' if stat.S_ISLNK(info.st_mode) else 'other'
        record_property('formal_paid_mode.'+label+'.'+phase,json.dumps(dict(exists=True,type=actual,uid=info.st_uid,
            mode=format(stat.S_IMODE(info.st_mode),'04o'),nlink=info.st_nlink),sort_keys=True))
        assert actual==kind and info.st_uid==os.geteuid(),label
        assert info.st_nlink==1 if kind=='regular' else info.st_nlink>=1,label
        return info
    # The actual source/paid producers retain their declared isolated route
    # profile, while all Auth/Research connections remain captured and native.
    assert db.name=='auth.sqlite3' and db.is_absolute()
    inspect('state_root',db.parent,'directory',phase='before')
    inspect('auth.sqlite3',db,'regular',phase='before')
    with development_store.transaction() as conn:
        gates={row[0] for row in conn.execute('SELECT gate_id FROM auth_owner_gates')}
        marker=[tuple(row) for row in conn.execute('SELECT id,version FROM research_schema')]
        assert len(marker)==1 and marker[0][0]==1 and type(marker[0][1]) is int and marker[0][1] in (9,10,11,12,13)
        version=marker[0][1]
        ResearchStore._check_structure_version(conn,version)
        source_gates=[]
        for task in conn.execute('SELECT id,policy_revision FROM research_tasks'):
            if version in (11,12,13) and task['policy_revision']=='d1-source-only-v1':
                resource=conn.execute('SELECT owner_gate_id,admission_version,task_gate_identity FROM research_source_resources WHERE task_id=?',(task['id'],)).fetchone()
                run=conn.execute('SELECT task_gate_identity FROM research_source_runs WHERE task_id=?',(task['id'],)).fetchone()
                assert resource and run and resource['admission_version']=='source-admission-v1'
                assert resource['owner_gate_id'] in gates
                assert type(resource['task_gate_identity']) is str and resource['task_gate_identity']==run['task_gate_identity']
                identity=json.loads(resource['task_gate_identity'])
                assert type(identity) is list and len(identity)==5 and all(type(value) is int for value in identity)
                assert identity[0]>=0 and identity[1]>0 and identity[2:]==[os.geteuid(),0o600,1]
                source_gates.append((task['id'],tuple(identity)))
            else:gates.add(task['id'])
    db.parent.chmod(0o700);db.chmod(0o600)
    assert stat.S_IMODE(inspect('state_root',db.parent,'directory',phase='after').st_mode)==0o700
    assert stat.S_IMODE(inspect('auth.sqlite3',db,'regular',phase='after').st_mode)==0o600
    for suffix in ('-wal','-shm','-journal'):
        path=db.with_name(db.name+suffix);label=db.name+suffix
        if inspect(label,path,'regular',phase='before',required=False) is not None:path.chmod(0o600)
        after=inspect(label,path,'regular',phase='after',required=False)
        if after is not None:assert stat.S_IMODE(after.st_mode)==0o600,label
    db=db.resolve()
    cache=db.parent.parent/'private-cache';logs=db.parent/'logs'
    for label,folder in (('cache',cache),('logs',logs)):
        inspect(label,folder,'directory',phase='before',required=False)
        folder.mkdir(mode=0o700,exist_ok=True)
        assert stat.S_IMODE(inspect(label,folder,'directory',phase='after').st_mode)==0o700,label
    for name,value in [('STATE_ROOT',db.parent),('CACHE_ROOT',cache),('LOG_ROOT',logs)]:monkeypatch.setattr(paths,name,value)
    audit=db.parent/'account_deletion_audit.jsonl'
    inspect('audit',audit,'regular',phase='before',required=False)
    audit.write_bytes(b'');audit.chmod(0o600)
    assert stat.S_IMODE(inspect('audit',audit,'regular',phase='after').st_mode)==0o600
    lock_root=db.parent/'research-locks'
    assert stat.S_IMODE(inspect('lock_root',lock_root,'directory',phase='checked').st_mode)==0o700
    for gate in sorted(gates):
        assert type(gate) is str and str(UUID(gate,version=4))==gate
        label='lock.'+gate
        assert stat.S_IMODE(inspect(label,lock_root/(gate+'.lock'),'regular',phase='checked').st_mode)==0o600,label
    for task_id,identity in source_gates:
        assert type(task_id) is str and str(UUID(task_id,version=4))==task_id
        info=inspect('source-lock.'+task_id,lock_root/('source-'+task_id+'.lock'),'regular',phase='checked')
        assert (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)==identity
    monkeypatch.setenv('STRUCTURAL_ENV','prod')
    from research.formula_runtime import provision_formula_v10,recover_formula_journal
    from services.auth_registration import migrate_private_auth_registration,admit_private_gate
    # Recovery validates the entire actual Auth/Research graph under the real
    # exclusive maintainer. A numeric marker alone is never fixture admission.
    profile=recover_formula_journal(db)
    if profile['schema_version']==9:provision_formula_v10(db)
    elif profile['schema_version'] not in (10,11,12,13):raise AssertionError('unsupported complete offline fixture graph')
    with raw(db) as conn:
        conn.execute('BEGIN');auth_profile=AuthStore.check_offline_auth_metadata(conn)
    migrate_private_auth_registration()
    if profile['schema_version'] in (9,10):
        from research.source_guard import provision_source_v11
        provision_source_v11(db)
    if profile['schema_version'] in (9,10,11):
        from research.plan_financial import provision_plan_v12
        provision_plan_v12(db)
    if profile['schema_version'] in (9,10,11,12):
        from research.plan_native_financial import provision_native_v13
        provision_native_v13(db)
    with raw(db) as conn:owners=[tuple(row) for row in conn.execute('SELECT owner_key,gate_id FROM auth_owner_gates')]
    held=AuthStore(db)
    for owner,gate in owners:
        if auth_profile=='legacy_auth':admit_private_gate(owner)
        with AuthorizationGate(held).owner_gate_id(gate) as lease:
            assert lease.identity[:2]==held.expected_owner_gate_identity(gate)
    _stage_formal_adjacent_assets(db)
    store=ResearchStore(held)
    monkeypatch.setattr(auth,'_store',lambda:held)
    monkeypatch.setenv('STRUCTURAL_ENV','test')
    return client,db,store,rid,excerpt,resolver


@pytest.mark.parametrize('withdraw',['paid-grant','source','cancel'])
def test_formal_native_paid_result_rechecks_withdrawal_and_keeps_cost(formal_paid,withdraw):
    from .test_research_paid_budget_loop import execution
    from research.paid_provider_session import persist_budget_return
    client,_,store,rid,excerpt,_=formal_paid
    with execution(formal_paid) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        if withdraw=='cancel':
            cancelled=post(client,f'/api/research/{rid}/cancel',{'task_id':result['task_id'],'expected_task_version':2},'formal-cancel')
            assert cancelled.status_code==200,cancelled.text
        else:
            with store.transaction(write=True) as conn:
                if withdraw=='paid-grant':conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
                else:conn.execute("DELETE FROM research_evidence_objects WHERE kind='snapshots' AND research_id=?",(rid,))
        reconciled=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':3 if withdraw=='cancel' else 2},'formal-cost-after-withdrawal')
        assert reconciled.status_code==200 and reconciled.json()['data']['method_result'] is None,reconciled.text
        with store.transaction() as conn:
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,2)
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
        assert wire['requests']==1


def test_formal_native_typed_http_commit_and_read_keep_original_body(formal_paid):
    from .test_research_paid_budget_loop import execution
    from research.paid_provider_session import persist_budget_return
    client,_,store,rid,_,_=formal_paid
    with execution(formal_paid) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'formal-typed-commit')
        assert response.status_code==200,response.text
        report=response.json()['data']['method_result'];assert report['result_ref']==session.id and report['received_at']==receipt._time
        assert report['model_analysis_ran'] is False and report['evidence']=='INSUFFICIENT'
        reopened=client.get(f'/api/research/{rid}',params={'task_id':result['task_id']})
        assert reopened.status_code==200 and reopened.json()['data']['method_result']==report,reopened.text
        assert wire['requests']==1


def test_formal_native_delete_before_late_return_keeps_body_closed(formal_paid,monkeypatch):
    from .test_research_paid_budget_loop import execution
    from research.paid_provider_session import persist_budget_return
    from research.paid_budget import observe_in
    client,_,store,rid,_,_=formal_paid
    with execution(formal_paid) as (session,result,wire,pid):
        receipt=session.receive()
        erased=_formal_delete(formal_paid,monkeypatch);assert erased.status_code==200,erased.text
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            observe_in(conn,store=store,lease=lease,return_ref=session.id)
            assert conn.execute('SELECT candidate_json,method_commit_json,body_origin_state FROM research_provider_sessions').fetchone()[:]==(None,None,'closed')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,2)
        assert client.get(f'/api/research/{rid}').status_code==401
        assert wire['requests']==1
