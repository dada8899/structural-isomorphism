"""V8 exact migration, process interruption and raw SQLite provenance guards."""
import multiprocessing
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from .test_research_persistence import stack,create
from .test_research_paid_schema import snapshot,rows
from api import auth
from research import ResearchStore
from research.errors import ResearchError
from research.financial_guard import JOB_ORIGIN_COLUMNS,V8_JOB_GUARDS,install_default_hook


@pytest.fixture(autouse=True)
def _historical_v8_profile(monkeypatch):
    monkeypatch.setattr(ResearchStore,'_migrate_v9',lambda self:None)


@pytest.fixture
def v7(stack,monkeypatch):
    client,path=stack
    with monkeypatch.context() as old:
        old.setattr(ResearchStore,'_migrate_v8',lambda self:None)
        create(client);store=ResearchStore(auth._store())
    # Genuine legacy schema with a nonempty unsigned job; no synthetic source.
    with store.transaction(write=True) as conn:
        conn.execute("INSERT INTO auth_deletion_jobs(id,owner_key,gate_id,cleanup_binding,database_binding,state,created_at) VALUES(?,?,?,?,?,'completed',?)",
            (str(uuid4()),'legacy-owner',str(uuid4()),'legacy-cleanup','legacy-database','2026-10-17T00:00:00.000000Z'))
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==7
    return path,store


def test_complete_v7_upgrade_preserves_all_old_columns_values_objects_and_lock_inodes(v7):
    path,store=v7;before=snapshot(path)
    inodes={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    ResearchStore(auth._store())
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==8
        for table,(columns,values) in before[1].items():
            if table=='research_schema':continue
            assert [tuple(r) for r in conn.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM "'+table+'" ORDER BY rowid')]==values
        assert conn.execute('SELECT origin_version,origin_digest FROM auth_deletion_jobs').fetchone()[:]==(None,None)
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    after=snapshot(path)
    assert {r[:3] for r in after[0] if r[0]=='table'}=={r[:3] for r in before[0] if r[0]=='table'}
    for obj in before[0]:
        if obj[1]!='auth_deletion_jobs':assert obj in after[0]
    assert inodes=={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    ResearchStore(auth._store())


def test_v8_also_accepts_actual_historical_auth_job_alter_layout(v7):
    path,store=v7
    with store.transaction(write=True) as conn:
        original=dict(conn.execute('SELECT * FROM auth_deletion_jobs').fetchone())
        conn.execute('DROP INDEX auth_one_pending_deletion');conn.execute('DROP TABLE auth_deletion_jobs')
        conn.execute(ResearchStore._auth_job_baseline_forms()[1])
        conn.execute("CREATE UNIQUE INDEX auth_one_pending_deletion ON auth_deletion_jobs(owner_key) WHERE state!='completed'")
        conn.execute('INSERT INTO auth_deletion_jobs('+','.join(original)+') VALUES('+','.join('?' for _ in original)+')',tuple(original.values()))
    store._migrate_v8()
    with store.transaction() as conn:
        upgraded=dict(conn.execute('SELECT * FROM auth_deletion_jobs').fetchone())
        assert {key:upgraded[key] for key in original}==original
        assert upgraded['origin_version'] is upgraded['origin_digest'] is None
    ResearchStore(auth._store())


FAULT_SQL=tuple('ALTER TABLE auth_deletion_jobs ADD COLUMN '+name+' '+ddl for name,ddl in JOB_ORIGIN_COLUMNS)+V8_JOB_GUARDS+('UPDATE research_schema SET version=8 WHERE id=1',)


@pytest.mark.parametrize('position',range(len(FAULT_SQL)+1))
def test_every_v8_alter_guard_marker_and_commit_failure_preserves_exact_v7(v7,monkeypatch,position):
    path,store=v7;before=snapshot(path);connect=sqlite3.connect;hit=[]
    class Fault(sqlite3.Connection):
        def execute(self,sql,*a,**k):
            if position<len(FAULT_SQL) and sql==FAULT_SQL[position]:hit.append(True);raise sqlite3.OperationalError('owned V8 fault')
            return super().execute(sql,*a,**k)
        def commit(self):
            if position==len(FAULT_SQL):hit.append(True);raise sqlite3.OperationalError('owned V8 commit fault')
            return super().commit()
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Fault,**k))
        with pytest.raises(sqlite3.OperationalError):store._migrate_v8()
    assert hit and snapshot(path)==before
    ResearchStore(auth._store())


def _crash_v8(path,cut):
    from services.auth_store import AuthStore
    store=ResearchStore.__new__(ResearchStore);store.path=Path(path);store.auth_store=AuthStore(Path(path))
    connect=sqlite3.connect
    target={'column':FAULT_SQL[0],'guard':V8_JOB_GUARDS[-1],'marker':FAULT_SQL[-1]}.get(cut)
    class Crash(sqlite3.Connection):
        def execute(self,sql,*a,**k):
            result=super().execute(sql,*a,**k)
            if sql==target:os._exit(61)
            return result
        def commit(self):
            if cut=='before_commit':os._exit(61)
            super().commit()
            if cut=='after_commit':os._exit(62)
    sqlite3.connect=lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Crash,**k)
    store._migrate_v8()


@pytest.mark.parametrize('cut',['column','guard','marker','before_commit','after_commit'])
def test_process_death_leaves_only_complete_v7_or_v8_and_same_data(v7,cut):
    path,store=v7;before=snapshot(path)
    child=multiprocessing.get_context('spawn').Process(target=_crash_v8,args=(str(path),cut))
    try:
        child.start();child.join(15);assert not child.is_alive() and child.exitcode==(62 if cut=='after_commit' else 61)
    finally:
        if child.is_alive():child.terminate();child.join(3)
        child.close()
    if cut!='after_commit':assert snapshot(path)==before
    ResearchStore(auth._store())
    with store.transaction() as conn:
        for table,(columns,values) in before[1].items():
            if table!='research_schema':assert [tuple(r) for r in conn.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM "'+table+'" ORDER BY rowid')]==values


@pytest.mark.parametrize('change',['partial-column','partial-guard','unknown-index','wrong-index','missing-index','wrong-job-ddl'])
def test_v7_drift_is_rejected_without_repair_or_version_bump(v7,change):
    path,store=v7
    with store.transaction(write=True) as conn:
        if change=='partial-column':conn.execute(FAULT_SQL[0])
        elif change=='partial-guard':conn.execute('CREATE TRIGGER auth_deletion_origin_create BEFORE INSERT ON auth_deletion_jobs BEGIN SELECT 1; END')
        elif change=='unknown-index':conn.execute('CREATE INDEX unknown_deletion_idx ON auth_deletion_jobs(gate_id)')
        elif change in ('wrong-index','missing-index'):
            conn.execute('DROP INDEX auth_one_pending_deletion')
            if change=='wrong-index':conn.execute('CREATE UNIQUE INDEX auth_one_pending_deletion ON auth_deletion_jobs(owner_key)')
        else:conn.execute('ALTER TABLE auth_deletion_jobs ADD COLUMN unknown_deletion_field TEXT')
    before=snapshot(path)
    with pytest.raises(ResearchError):ResearchStore(auth._store())
    assert snapshot(path)==before


@pytest.mark.parametrize('change',['missing-guard','wrong-guard','unknown-aux'])
def test_v8_damage_is_rejected_without_reinstallation(v7,change):
    path,store=v7;store._migrate_v8()
    with store.transaction(write=True) as conn:
        if change=='unknown-aux':conn.execute('CREATE INDEX unknown_v8_idx ON auth_deletion_jobs(gate_id)')
        else:
            conn.execute('DROP TRIGGER auth_deletion_origin_create')
            if change=='wrong-guard':conn.execute('CREATE TRIGGER auth_deletion_origin_create BEFORE INSERT ON auth_deletion_jobs BEGIN SELECT 1; END')
    before=snapshot(path)
    with pytest.raises(ResearchError):ResearchStore(auth._store())
    assert snapshot(path)==before


@pytest.mark.parametrize('raw',[False,True])
def test_unsigned_legacy_job_cannot_be_signed_or_given_half_origin(v7,raw):
    path,store=v7;store._migrate_v8()
    with sqlite3.connect(path) as conn:
        if not raw:install_default_hook(conn)
        for sql in ["UPDATE auth_deletion_jobs SET origin_version='authenticated-delete-v1',origin_digest='"+'a'*64+"'",
                    "UPDATE auth_deletion_jobs SET origin_digest='"+'a'*64+"'"]:
            with pytest.raises((sqlite3.IntegrityError,sqlite3.OperationalError)) as rejected:conn.execute(sql)
            if isinstance(rejected.value,sqlite3.OperationalError):assert 'research_financial_write_allowed' in str(rejected.value)
        # Legacy remains unsigned; origin flags and a hash never authorize V2.
        assert conn.execute('SELECT origin_version,origin_digest FROM auth_deletion_jobs').fetchone()==(None,None)
