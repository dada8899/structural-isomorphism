"""V9 four-column overlay, no old provenance upgrade, fault rollback."""
import sqlite3
import multiprocessing
import os
from pathlib import Path
import pytest
from .test_research_persistence import stack,create
from .test_research_paid_schema import snapshot
from research import ResearchStore
from research.financial_guard import METHOD_COLUMNS,METHOD_GUARDS
from research.errors import ResearchError
from api import auth


@pytest.fixture
def v8(stack,monkeypatch):
    client,path=stack
    with monkeypatch.context() as old:
        old.setattr(ResearchStore,'_initialize_current',lambda self,conn:False)
        old.setattr(ResearchStore,'_migrate_v9',lambda self:None)
        create(client);store=ResearchStore(auth._store())
    return path,store


def test_exact_v8_to_v9_preserves_old_objects_rows_and_creates_no_table(v8):
    path,store=v8;before=snapshot(path);ResearchStore(auth._store());after=snapshot(path)
    assert {r[1] for r in before[0] if r[0]=='table'}=={r[1] for r in after[0] if r[0]=='table'}
    for row in before[0]:
        if row[1]!='research_provider_sessions':assert row in after[0]
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==9
        for table,(columns,values) in before[1].items():
            if table=='research_schema':continue
            assert [tuple(r) for r in conn.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM "'+table+'" ORDER BY rowid')]==values


FAULTS=tuple('ALTER TABLE research_provider_sessions ADD COLUMN '+name+' '+ddl for name,ddl in METHOD_COLUMNS)+METHOD_GUARDS+('UPDATE research_schema SET version=9 WHERE id=1',)


@pytest.mark.parametrize('point',range(len(FAULTS)+1))
def test_each_v9_alter_guard_marker_and_commit_failure_rolls_back_exact_v8(v8,monkeypatch,point):
    path,store=v8;before=snapshot(path);connect=sqlite3.connect;hit=[]
    class Fault(sqlite3.Connection):
        def execute(self,sql,*a,**k):
            if point<len(FAULTS) and sql==FAULTS[point]:hit.append(True);raise sqlite3.OperationalError('owned V9 fault')
            return super().execute(sql,*a,**k)
        def commit(self):
            if point==len(FAULTS):hit.append(True);raise sqlite3.OperationalError('owned V9 commit fault')
            return super().commit()
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Fault,**k))
        with pytest.raises(sqlite3.OperationalError):store._migrate_v9()
    assert hit and snapshot(path)==before
    ResearchStore(auth._store())


@pytest.mark.parametrize('change',['column','guard','missing','changed','unknown','legacy-aux'])
def test_partial_or_damaged_v9_is_rejected_without_repair(v8,change):
    path,store=v8
    if change in ('missing','changed','unknown','legacy-aux'):store._migrate_v9()
    with store.transaction(write=True) as conn:
        if change=='column':conn.execute(FAULTS[0])
        elif change=='guard':conn.execute("CREATE TRIGGER research_method_birth BEFORE INSERT ON research_provider_sessions BEGIN SELECT 1; END")
        elif change in ('missing','changed'):
            conn.execute('DROP TRIGGER research_method_birth')
            if change=='changed':conn.execute("CREATE TRIGGER research_method_birth BEFORE INSERT ON research_provider_sessions BEGIN SELECT 1; END")
        elif change=='legacy-aux':conn.execute("CREATE TRIGGER owned_paid_fault BEFORE UPDATE OF state ON research_paid_approvals WHEN NEW.state='confirmed' BEGIN SELECT RAISE(ABORT,'owned confirmation fault'); END")
        else:conn.execute('CREATE INDEX unknown_method_idx ON research_provider_sessions(body_origin_state)')
    before=snapshot(path)
    with pytest.raises(ResearchError):ResearchStore(auth._store())
    assert snapshot(path)==before


def _migration_crash(path,cut):
    from services.auth_store import AuthStore
    store=ResearchStore.__new__(ResearchStore);store.path=Path(path);store.auth_store=AuthStore(Path(path))
    connect=sqlite3.connect;target={'column':FAULTS[0],'guard':METHOD_GUARDS[-1],'marker':FAULTS[-1]}.get(cut)
    class Crash(sqlite3.Connection):
        def execute(self,sql,*a,**k):
            result=super().execute(sql,*a,**k)
            if sql==target:os._exit(81)
            return result
        def commit(self):
            if cut=='before-commit':os._exit(81)
            super().commit()
            if cut=='after-commit':os._exit(82)
    sqlite3.connect=lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Crash,**k)
    store._migrate_v9()


@pytest.mark.parametrize('cut',['column','guard','marker','before-commit','after-commit'])
def test_actual_migration_process_death_preserves_complete_v8_or_v9(v8,cut):
    path,store=v8;before=snapshot(path)
    inodes={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    from web.backend.tests.test_research_method_schema_v9 import _migration_crash as target
    child=multiprocessing.get_context('spawn').Process(target=target,args=(str(path),cut))
    try:
        child.start();child.join(15);assert not child.is_alive() and child.exitcode==(82 if cut=='after-commit' else 81)
    finally:
        if child.is_alive():child.terminate();child.join(3)
        child.close()
    if cut!='after-commit':assert snapshot(path)==before
    ResearchStore(auth._store())
    assert inodes=={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
