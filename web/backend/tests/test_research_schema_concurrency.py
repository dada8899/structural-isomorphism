"""Real SQLite initialization interleavings; no schema/checker return is faked."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import importlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest


NAMESPACES = ('research.store', 'web.backend.research.store')
MIGRATIONS = ('_migrate_v4', '_migrate_v5', '_migrate_v6', '_migrate_v7', '_migrate_v8')


def auth_for(namespace, path):
    module = 'web.backend.services.auth_store' if namespace.startswith('web.') else 'services.auth_store'
    return importlib.import_module(module).AuthStore(path)


def catalog(path):
    conn = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    try:
        return conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall()
    finally:
        conn.close()


def completed_peer(cls, auth, version, monkeypatch):
    # Stop only at a real historical migration boundary. All preceding SQL,
    # native connections, policy checks and connection hooks execute normally.
    if version==10:
        from .source_v10_cold_peer import produce
        provenance=produce(auth.path)
        print('HISTORICAL10_COLD_PEER:'+json.dumps({key:provenance[key] for key in ('version','pid','auth_graph_unchanged','native_closed_on_creator')}))
    with monkeypatch.context() as profile:
        if version not in (10,14):profile.setattr(cls,'_initialize_current',lambda self,conn:False)
        if version == 6:profile.setattr(cls, '_migrate_v7', lambda self: None)
        if version == 7:profile.setattr(cls, '_migrate_v8', lambda self: None)
        if version == 8:profile.setattr(cls, '_migrate_v9', lambda self: None)
        store = cls(auth)
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == version
        if version == 6:
            store._check_v6_inherited(conn);store._check_v7_attachments(conn)
        elif version == 7:
            store._check_v7(conn);store._check_v7_attachments(conn)
        elif version == 8:
            store._check_v8(conn);store._check_v7_attachments(conn)
        elif version==9:
            store._check_structure_version(conn,9);store._check_v9(conn)
        elif version==10:
            store._check_structure_version(conn,10);store._check_v10(conn)
        else:
            store.check_current_structure(conn);store._check_v14(conn)
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    return store


def thread_race(cls, auth, peer, monkeypatch):
    observed = threading.Event();resume = threading.Event();outcome = []
    original = cls.transaction
    armed = True

    @contextmanager
    def scheduled(self, *, write=False):
        nonlocal armed
        pause = threading.current_thread().name == 'stale-schema-reader' and not write and armed
        if pause:armed = False
        with original(self, write=write) as conn:
            if pause:
                assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_schema'").fetchone() is None
            yield conn
        if pause:
            # The read snapshot is closed before the peer's real migrations.
            observed.set()
            assert resume.wait(15), 'peer never released stale constructor'

    def construct():
        try:outcome.append(cls(auth))
        except BaseException as error:outcome.append(error)

    with monkeypatch.context() as schedule:
        schedule.setattr(cls, 'transaction', scheduled)
        thread = threading.Thread(target=construct, name='stale-schema-reader')
        thread.start()
        try:
            assert observed.wait(15), 'initial read did not complete'
            peer()
        finally:
            resume.set();thread.join(20)
        assert not thread.is_alive(), 'owned constructor thread leaked'
    assert len(outcome) == 1
    return outcome[0]


@pytest.mark.parametrize('namespace', NAMESPACES)
@pytest.mark.parametrize('version', [9, 7, 8, 6, 10, 14])
def test_stale_empty_read_accepts_only_completed_peer_and_finishes_upgrade(tmp_path, monkeypatch, record_property, namespace, version):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    cls = importlib.import_module(namespace).ResearchStore
    path = tmp_path/'auth.sqlite3';auth = auth_for(namespace, path)
    peer_image = []

    def peer():
        store = completed_peer(cls, auth, version, monkeypatch)
        with store.transaction(write=True) as conn:
            conn.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('peer@example.invalid','free','synthetic','peer')")
        peer_image.extend(catalog(path))
        record_property('actual_peer_version', version)
        record_property('actual_peer_object_count', len(peer_image))

    result = thread_race(cls, auth, peer, monkeypatch)
    assert isinstance(result, cls), repr(result)
    with result.transaction() as conn:
        expected=version if version in (10,14) else 9
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == expected
        if expected==9:result._check_structure_version(conn,9);result._check_v9(conn)
        elif expected==10:result._check_structure_version(conn,10);result._check_v10(conn)
        else:result.check_current_structure(conn);result._check_v14(conn)
        assert conn.execute('SELECT research_financial_guard_version(),research_method_guard_version(),research_method_write_allowed(?,?,?)', ('probe','','{}')).fetchone()[:] == (7,9,0)
        assert conn.execute("SELECT session_generation FROM auth_users WHERE email='peer@example.invalid'").fetchone()[0] == 'peer'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    if version in (9,10,14):assert catalog(path) == peer_image


@pytest.mark.parametrize('namespace', NAMESPACES)
def test_peer_finishes_v9_after_legacy_commit_before_first_migration(tmp_path, monkeypatch, namespace):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    cls = importlib.import_module(namespace).ResearchStore
    path = tmp_path/'auth.sqlite3';auth = auth_for(namespace, path)
    original = cls._migrate_v4;ready = threading.Event();resume = threading.Event();outcome = []

    def scheduled(self):
        if threading.current_thread().name == 'stale-legacy-initializer':
            with self.transaction() as conn:
                assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 3
            ready.set();assert resume.wait(15)
        return original(self)

    def construct():
        try:outcome.append(cls(auth))
        except BaseException as error:outcome.append(error)

    with monkeypatch.context() as schedule:
        schedule.setattr(cls,'_initialize_current',lambda self,conn:False)
        schedule.setattr(cls, '_migrate_v4', scheduled)
        thread = threading.Thread(target=construct, name='stale-legacy-initializer')
        thread.start()
        try:
            assert ready.wait(15)
            completed_peer(cls, auth, 9, monkeypatch)
            before = catalog(path)
        finally:
            resume.set();thread.join(20)
        assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], cls), repr(outcome)
    assert catalog(path) == before


@pytest.mark.parametrize('namespace', NAMESPACES)
@pytest.mark.parametrize('cold_version',[9,14])
def test_simultaneous_cold_constructors_finish_every_real_migration_boundary(tmp_path, monkeypatch, namespace,cold_version):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    cls = importlib.import_module(namespace).ResearchStore
    for attempt in range(10):
        auth = auth_for(namespace, tmp_path/str(attempt)/'auth.sqlite3')
        barrier = threading.Barrier(2);local = threading.local();original = cls.transaction

        @contextmanager
        def scheduled(self, *, write=False):
            pause = not write and not getattr(local, 'seen', False)
            if pause:local.seen = True
            with original(self, write=write) as conn:
                if pause:assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_schema'").fetchone() is None
                yield conn
            if pause:barrier.wait(15)

        def construct(_):
            return cls(auth)

        with monkeypatch.context() as schedule:
            if cold_version==9:schedule.setattr(cls,'_initialize_current',lambda self,conn:False)
            schedule.setattr(cls, 'transaction', scheduled)
            with ThreadPoolExecutor(max_workers=2) as workers:
                stores = list(workers.map(construct, range(2)))
        for store in stores:
            with store.transaction() as conn:
                assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==cold_version
                if cold_version==9:store._check_structure_version(conn,9);store._check_v9(conn)
                else:store.check_current_structure(conn);store._check_v14(conn)


@pytest.mark.parametrize('namespace', NAMESPACES)
@pytest.mark.parametrize('version', [8, 9, 10, 14])
@pytest.mark.parametrize('operation', MIGRATIONS)
def test_direct_migration_of_completed_peer_checks_real_native_graph_without_dml(tmp_path, monkeypatch, namespace, version, operation):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    cls = importlib.import_module(namespace).ResearchStore
    path = tmp_path/'auth.sqlite3';store = completed_peer(cls, auth_for(namespace, path), version, monkeypatch)
    before = catalog(path);opened = [];changes = [];connect = sqlite3.connect

    class Observed(sqlite3.Connection):
        def close(self):
            changes.append(self.total_changes)
            return super().close()

    def observed(*args, **kwargs):
        conn = connect(*args, factory=Observed, **kwargs)
        opened.append(conn)
        return conn

    with monkeypatch.context() as tracking:
        tracking.setattr(sqlite3, 'connect', observed)
        getattr(store, operation)()
    assert len(opened) == 1 and changes == [0]
    with pytest.raises(sqlite3.ProgrammingError):opened[0].execute('SELECT 1')
    assert catalog(path) == before
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == version
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1


@pytest.mark.parametrize('namespace', NAMESPACES)
@pytest.mark.parametrize('version', [8, 9, 10, 14])
@pytest.mark.parametrize('operation', MIGRATIONS)
@pytest.mark.parametrize('fault', ['half', 'unknown-aux', 'future-marker'])
def test_direct_migration_never_treats_bad_peer_as_completed(tmp_path, monkeypatch, namespace, version, operation, fault):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    module = importlib.import_module(namespace);cls = module.ResearchStore
    path = tmp_path/'auth.sqlite3';store = completed_peer(cls, auth_for(namespace, path), version, monkeypatch)
    with store.transaction(write=True) as conn:
        if fault == 'half':conn.execute('DROP TABLE research_idempotency')
        elif fault == 'unknown-aux':conn.execute('CREATE INDEX injected_aux ON research_tasks(phase)')
        else:conn.execute('UPDATE research_schema SET version='+('15' if version==14 else '11' if version==10 else '10'))
    before = catalog(path)
    with pytest.raises(module.ResearchError) as rejected:getattr(store, operation)()
    assert rejected.value.code == 'SCHEMA_UNSUPPORTED'
    assert catalog(path) == before


@pytest.mark.parametrize('namespace', NAMESPACES)
@pytest.mark.parametrize('version', [8, 9, 10, 14])
@pytest.mark.parametrize('fault', ['policy', 'foreign-key'])
def test_completed_peer_still_requires_policy_and_fk_data_even_on_fk_off_migration(tmp_path, monkeypatch, namespace, version, fault):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    module = importlib.import_module(namespace);cls = module.ResearchStore
    path = tmp_path/'auth.sqlite3';store = completed_peer(cls, auth_for(namespace, path), version, monkeypatch)
    conn = sqlite3.connect(path)
    try:
        if fault == 'policy':conn.execute("UPDATE auth_owner_gate_policy SET fingerprint='invalid-synthetic-policy'")
        else:conn.execute('INSERT INTO research_revisions VALUES(?,?,?,?,?)', ('00000000-0000-4000-8000-000000000000',1,'{}','a'*64,'synthetic'))
        conn.commit()
    finally:conn.close()
    before = catalog(path)
    with pytest.raises((RuntimeError, module.ResearchError)):
        store._migrate_v4()
    assert catalog(path) == before


@pytest.mark.parametrize('namespace', NAMESPACES)
@pytest.mark.parametrize('version', [6, 7, 8, 9, 10, 14])
@pytest.mark.parametrize('fault', ['half', 'unknown-aux', 'unknown-version', 'missing-marker'])
def test_stale_empty_read_never_repairs_or_accepts_bad_peer(tmp_path, monkeypatch, namespace, version, fault):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    module = importlib.import_module(namespace);cls = module.ResearchStore
    path = tmp_path/'auth.sqlite3';auth = auth_for(namespace, path)
    before = [];images = []

    def peer():
        store = completed_peer(cls, auth, version, monkeypatch)
        with store.transaction(write=True) as conn:
            if fault == 'half':
                if version == 6:conn.execute('DROP TABLE research_idempotency')
                else:
                    name = module.V7_GUARDS[0].split()[2] if version == 7 else module.V8_JOB_GUARDS[0].split()[2] if version == 8 else 'research_method_birth'
                    conn.execute('DROP TRIGGER '+name)
            elif fault == 'unknown-aux':conn.execute('CREATE INDEX injected_aux ON research_tasks(phase)')
            elif fault == 'unknown-version':conn.execute('UPDATE research_schema SET version='+('15' if version==14 else '11' if version==10 else '10'))
            else:conn.execute('DROP TABLE research_schema')
        before.extend(catalog(path))
        images.append(hashlib.sha256(path.read_bytes()).hexdigest())

    result = thread_race(cls, auth, peer, monkeypatch)
    assert isinstance(result, module.ResearchError) and result.code == 'SCHEMA_UNSUPPORTED', repr(result)
    assert catalog(path) == before
    assert hashlib.sha256(path.read_bytes()).hexdigest() == images[0]


@pytest.mark.parametrize('namespace', NAMESPACES)
def test_late_ordinary_sqlite_v6_marker_without_graph_never_installs_missing_tables(tmp_path, monkeypatch, namespace):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    module = importlib.import_module(namespace);cls = module.ResearchStore
    path = tmp_path/'auth.sqlite3';auth = auth_for(namespace, path);before = [];images = []

    def peer():
        conn = sqlite3.connect(path)
        try:
            conn.execute(module.SCHEMA[0]);conn.execute('INSERT INTO research_schema VALUES(1,6)');conn.commit()
        finally:conn.close()
        before.extend(catalog(path));images.append(hashlib.sha256(path.read_bytes()).hexdigest())

    result = thread_race(cls, auth, peer, monkeypatch)
    assert isinstance(result, module.ResearchError) and result.code == 'SCHEMA_UNSUPPORTED', repr(result)
    assert catalog(path) == before
    assert hashlib.sha256(path.read_bytes()).hexdigest() == images[0]


# A canonical production import in the fresh interpreter avoids importing a
# target from the ambiguous top-level "tests" package during process spawn.
CHILD = r'''
from contextlib import contextmanager
import importlib,json,os,sqlite3,sys,time
from pathlib import Path
namespace,path,ready,resume,output,cold_version,backend_root=sys.argv[1:]
sys.path.insert(0,backend_root)
cold_version=int(cold_version)
cls=importlib.import_module(namespace).ResearchStore
authmod='web.backend.services.auth_store' if namespace.startswith('web.') else 'services.auth_store'
auth=importlib.import_module(authmod).AuthStore(Path(path))
if cold_version==9:cls._initialize_current=lambda self,conn:False
original=cls.transaction;armed=True
@contextmanager
def scheduled(self,*,write=False):
    global armed
    pause=not write and armed
    if pause:armed=False
    with original(self,write=write) as conn:
        if pause:assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_schema'").fetchone() is None
        yield conn
    if pause:
        Path(ready).write_text('read snapshot closed')
        deadline=time.monotonic()+20
        while not Path(resume).exists():
            assert time.monotonic()<deadline,'parent did not release constructor'
            time.sleep(.005)
cls.transaction=scheduled
try:
    store=cls(auth)
    with store.transaction(write=True) as conn:
        if cold_version==9:store._check_structure_version(conn,9);store._check_v9(conn)
        else:store.check_current_structure(conn);store._check_v14(conn)
        conn.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('child@example.invalid','free','synthetic','child')")
    guard=sys.modules.get('audit_bootstrap')
    if guard is not None:
        closed=0
        for connection in guard.handles:
            try:connection.execute('SELECT 1')
            except sqlite3.ProgrammingError:closed+=1
            else:raise AssertionError('cold constructor child leaked a native connection')
        print('SCHEMA_COLD_CHILD_NATIVE:'+json.dumps({'pid':os.getpid(),'closed_on_creator':closed}))
    Path(output).write_text(json.dumps({'ok':True,'version':cold_version}))
except BaseException as error:
    Path(output).write_text(json.dumps({'ok':False,'error':type(error).__name__,'code':getattr(error,'code',None),'message':getattr(error,'message',str(error))}))
    raise
'''


@pytest.mark.parametrize('namespace', NAMESPACES)
@pytest.mark.parametrize('cold_version',[9,14])
def test_cold_schema_race_across_processes_and_namespaces_preserves_both_wal_commits(tmp_path, monkeypatch, namespace,cold_version):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    path = tmp_path/'auth.sqlite3';auth_for(namespace, path)
    ready = tmp_path/'ready';resume = tmp_path/'resume';output = tmp_path/'result.json'
    project_root = Path(__file__).resolve().parents[3]
    child_env = dict(os.environ)
    child_env['PYTHONPATH'] = os.pathsep.join((str(project_root), str(project_root/'web/backend'), child_env.get('PYTHONPATH', '')))
    process = subprocess.Popen([sys.executable, '-c', CHILD, namespace, str(path), str(ready), str(resume), str(output),str(cold_version),str(Path(__file__).resolve().parents[1])], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env)
    try:
        deadline = time.monotonic()+20
        while not ready.exists():
            assert process.poll() is None, process.communicate(timeout=1)
            assert time.monotonic() < deadline, 'child did not finish initial read'
            time.sleep(.005)
        other = NAMESPACES[1] if namespace == NAMESPACES[0] else NAMESPACES[0]
        cls = importlib.import_module(other).ResearchStore
        with monkeypatch.context() as profile:
            if cold_version==9:profile.setattr(cls,'_initialize_current',lambda self,conn:False)
            store = cls(auth_for(other, path))
        with store.transaction(write=True) as conn:
            conn.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('parent@example.invalid','free','synthetic','parent')")
        # Closing a same-PID native peer must not affect the child's WAL write.
        with store.transaction() as conn:assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        resume.write_text('complete v9 peer committed')
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout.decode(), stderr.decode(), output.read_text() if output.exists() else None)
        for line in stdout.decode().splitlines():
            if line.startswith('SCHEMA_COLD_CHILD_NATIVE:'):print(line)
        assert json.loads(output.read_text()) == {'ok': True, 'version': cold_version}
        with store.transaction() as conn:
            if cold_version==9:store._check_structure_version(conn,9);store._check_v9(conn)
            else:store.check_current_structure(conn);store._check_v14(conn)
            assert [tuple(row) for row in conn.execute("SELECT email,session_generation FROM auth_users ORDER BY email")] == [('child@example.invalid','child'),('parent@example.invalid','parent')]
    finally:
        if process.poll() is None:process.terminate()
        try:process.communicate(timeout=3)
        except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=3)


@pytest.mark.parametrize('namespace', NAMESPACES)
def test_late_completed_v8_unknown_managed_table_is_rejected_without_mutation(tmp_path, monkeypatch, namespace):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    module = importlib.import_module(namespace);cls = module.ResearchStore
    path = tmp_path/'auth.sqlite3';auth = auth_for(namespace, path)
    before = [];images = []

    def peer():
        store = completed_peer(cls, auth, 8, monkeypatch)
        with store.transaction(write=True) as conn:
            conn.execute('CREATE TABLE research_unexpected(value TEXT)')
        before.extend(catalog(path));images.append(hashlib.sha256(path.read_bytes()).hexdigest())

    result = thread_race(cls, auth, peer, monkeypatch)
    assert isinstance(result, module.ResearchError) and result.code == 'SCHEMA_UNSUPPORTED', repr(result)
    assert catalog(path) == before
    assert hashlib.sha256(path.read_bytes()).hexdigest() == images[0]
    conn = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    try:assert conn.execute('SELECT id,version FROM research_schema').fetchall() == [(1,8)]
    finally:conn.close()
