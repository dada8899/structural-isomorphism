"""Actual V9/V10 SQLite, HTTP and local-child boundaries; no network/model."""
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
    with sqlite3.connect(path) as conn:
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
    with sqlite3.connect(path) as conn:
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
    with sqlite3.connect(path) as conn:conn.execute('UPDATE auth_owner_gate_policy SET fingerprint=?',('0'*64,))
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
