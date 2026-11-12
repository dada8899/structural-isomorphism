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
        with store.transaction() as conn:
            assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
            store.check_current_structure(conn);store._check_v15(conn)
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
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
        store.check_current_structure(conn);store._check_v15(conn)


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


def test_current15_private_binding_does_not_admit_bare_research_app(private,monkeypatch):
    """Private native storage is real; an unbound prod app gains no HTTP right.

    The captured-store ENV downgrade is covered separately by the existing
    native-RO control. This request never splices environments or factories.
    """
    import socket
    from api import auth,research
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from .test_private_registration import BETA
    from .test_research_persistence import envelope
    for name,value in {'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta',
        'AUTH_LINK_BASE_URL':BETA,'JWT_SECRET':FIXTURE_SECRET,
        'STRUCTURAL_SSO_SECRET':FIXTURE_SECRET,'STRUCTURAL_RESEARCH_ENABLED':'true',
        'STRUCTURAL_SSO_DATA_DIR':str(private.parent),
        'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587',
        'SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid',
        'AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'}.items():
        monkeypatch.setenv(name,value)
    email='private-main-refusal@example.invalid'
    _,cookie=register_private_user(monkeypatch,email)
    captured=auth._store();store=ResearchStore(captured)
    identity=(private.stat().st_dev,private.stat().st_ino)
    assert captured._private_auth and store._formal_mode()
    assert captured.storage_identity==store.storage_identity==identity
    def image():
        with store.transaction() as conn:
            assert type(conn) is sqlite_utils.PrivateAuthConnection
            assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
            store._check_v15(conn)
            tables=[row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name GLOB 'research_*' ORDER BY name")]
            return {table:[tuple(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid')] for table in tables}
    application=FastAPI()
    application.include_router(auth.router,prefix='/api')
    application.include_router(research.router,prefix='/api')
    attempts=[]
    def no_network(*args,**kwargs):
        attempts.append(True)
        raise AssertionError('bare research refusal must not open a network connection')
    with TestClient(application,base_url=BETA) as client:
        client.cookies.set('phase_session',cookie)
        me=client.get('/api/auth/me')
        assert me.status_code==200 and me.json()['user']['email']==email
        before=image()
        with monkeypatch.context() as stopped:
            stopped.setattr(socket.socket,'connect',no_network)
            stopped.setattr(socket.socket,'connect_ex',no_network)
            response=client.post('/api/research',json=envelope({'problem':problem()}),
                headers={'Origin':BETA,'Idempotency-Key':'private15-bare-app-refused'})
        assert response.status_code==503 and response.json()['error']['code']=='FEATURE_UNAVAILABLE',response.text
        assert image()==before and not attempts
        assert auth._store() is captured and store.auth_store is captured
        assert captured._private_auth and store._formal_mode()
        assert captured.storage_identity==store.storage_identity==identity
        assert (private.stat().st_dev,private.stat().st_ino)==identity
