"""Native read-only structural preflight; no app constructors or row access."""
from contextlib import contextmanager
import hashlib
import importlib
import sqlite3
from uuid import uuid4

import pytest

from .test_research_persistence import stack,create
from .test_research_financial_schema_v7 import registry_inputs
from research import ResearchStore
from research.errors import ResearchError
from api import auth


@pytest.fixture
def current(stack):
    client,path=stack;create(client);store=ResearchStore(auth._store())
    with sqlite3.connect(path) as conn:conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    return path,store


@contextmanager
def native_ro(path,*,row=False):
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True,isolation_level=None)
    if row:conn.row_factory=sqlite3.Row
    conn.execute('BEGIN')
    try:yield conn
    finally:conn.set_authorizer(None);conn.rollback();conn.close()


def byte_image(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def deny_nonmetadata(conn):
    reads=[];pragmas=[];forbidden=[]
    allowed_pragmas={'table_xinfo','foreign_key_list','index_list','index_xinfo'}
    def guard(action,first,second,db,source):
        if action==sqlite3.SQLITE_READ:
            reads.append((db,first,second))
            if db!='main' or first not in ('sqlite_master','sqlite_schema','research_schema'):
                forbidden.append((action,first));return sqlite3.SQLITE_DENY
        elif action==sqlite3.SQLITE_PRAGMA:
            pragmas.append((db,first,second))
            if first not in allowed_pragmas or db!='main':forbidden.append((action,first));return sqlite3.SQLITE_DENY
        elif action not in (sqlite3.SQLITE_SELECT,):
            forbidden.append((action,first));return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    conn.set_authorizer(guard)
    return reads,pragmas,forbidden


@pytest.mark.parametrize('namespace',['research.store','web.backend.research.store'])
@pytest.mark.parametrize('row',[False,True])
def test_native_ro_without_udfs_checks_current_graph_in_existing_snapshot(current,monkeypatch,namespace,row):
    path,_=current;before=byte_image(path)
    cls=importlib.import_module(namespace).ResearchStore
    with native_ro(path,row=row) as conn:
        with pytest.raises(sqlite3.OperationalError):conn.execute('SELECT research_method_guard_version()')
        with pytest.raises(sqlite3.OperationalError):conn.execute('INSERT INTO research_schema VALUES(2,9)')
        reads,pragmas,forbidden=deny_nonmetadata(conn);statements=[];conn.set_trace_callback(statements.append)
        def no_connection(*args,**kwargs):raise AssertionError('structural check opened another connection')
        with monkeypatch.context() as patch:
            patch.setattr(sqlite3,'connect',no_connection)
            patch.setattr(cls,'__init__',lambda *a,**k:(_ for _ in ()).throw(AssertionError('store constructed')))
            cls.check_current_structure(conn)
        assert conn.in_transaction and not forbidden
        assert pragmas and all(db=='main' for db,_,_ in pragmas)
        assert reads and all(table in ('sqlite_master','sqlite_schema','research_schema') for _,table,_ in reads)
        assert all(sql.startswith(('SELECT ','PRAGMA main.')) for sql in statements)
        assert not any(word in sql.lower() for sql in statements for word in ('foreign_key_check','guard_version','write_allowed'))
        conn.set_authorizer(None)
        with pytest.raises(sqlite3.OperationalError):conn.execute('SELECT research_method_guard_version()')
    assert byte_image(path)==before


def test_snapshot_must_already_exist_and_checker_never_starts_it(current):
    path,_=current
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True,isolation_level=None)
    statements=[];conn.set_trace_callback(statements.append)
    try:
        with pytest.raises(ResearchError):ResearchStore.check_current_structure(conn)
        assert not conn.in_transaction and statements==[]
    finally:conn.close()


@pytest.mark.parametrize('marker',['missing','multiple','old','unknown','text'])
def test_invalid_version_markers_are_rejected_without_writes(current,marker):
    path,_=current
    with sqlite3.connect(path) as conn:
        if marker=='missing':conn.execute('DELETE FROM research_schema')
        elif marker=='multiple':conn.execute('PRAGMA ignore_check_constraints=ON');conn.execute('INSERT INTO research_schema VALUES(2,9)')
        else:conn.execute('UPDATE research_schema SET version=?',(8 if marker=='old' else 99 if marker=='unknown' else 'unrecognized',))
        conn.commit();conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before=byte_image(path)
    with native_ro(path) as conn:
        _,pragmas,forbidden=deny_nonmetadata(conn)
        with pytest.raises(ResearchError) as rejected:ResearchStore.check_current_structure(conn)
        assert rejected.value.code=='SCHEMA_UNSUPPORTED' and not forbidden and pragmas==[]
    assert byte_image(path)==before


@pytest.mark.parametrize('change',['table','column','guard','partial-unique','unknown-aux','unknown-table','view','vtab'])
def test_bad_main_objects_are_rejected_before_any_pragma_probe(current,change):
    path,_=current
    with sqlite3.connect(path) as conn:
        if change=='table':conn.execute('DROP TABLE research_idempotency')
        elif change=='column':conn.execute('ALTER TABLE research_idempotency ADD COLUMN unexpected TEXT')
        elif change=='guard':
            conn.execute('DROP TRIGGER research_method_birth')
            conn.execute('CREATE TRIGGER research_method_birth BEFORE INSERT ON research_provider_sessions BEGIN SELECT 1; END')
        elif change=='partial-unique':
            conn.execute('DROP INDEX research_one_active_task')
            conn.execute("CREATE UNIQUE INDEX research_one_active_task ON research_tasks(research_id) WHERE execution='QUEUED'")
        elif change=='unknown-aux':conn.execute('CREATE INDEX injected_aux ON research_tasks(phase)')
        elif change=='unknown-table':conn.execute('CREATE TABLE research_unrecognized(id INTEGER)')
        else:
            conn.execute('DROP TABLE research_idempotency')
            if change=='view':conn.execute('CREATE VIEW research_idempotency AS SELECT email FROM auth_users')
            else:conn.execute('CREATE VIRTUAL TABLE research_idempotency USING fts5(payload)')
        conn.commit();conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before=byte_image(path)
    with native_ro(path) as conn:
        _,pragmas,forbidden=deny_nonmetadata(conn)
        with pytest.raises(ResearchError) as rejected:ResearchStore.check_current_structure(conn)
        assert rejected.value.code=='SCHEMA_UNSUPPORTED' and not forbidden and pragmas==[]
    assert byte_image(path)==before


@pytest.mark.parametrize('shadow',['temp','attached'])
def test_same_named_temp_or_attached_objects_cannot_mask_bad_main(current,tmp_path,shadow):
    path,_=current
    with sqlite3.connect(path) as conn:
        conn.execute('UPDATE research_schema SET version=99');conn.commit();conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before=byte_image(path)
    with native_ro(path) as conn:
        if shadow=='temp':
            conn.execute('CREATE TEMP TABLE research_schema(id INTEGER,version INTEGER)')
            conn.execute('INSERT INTO temp.research_schema VALUES(1,9)')
            conn.execute('CREATE TEMP VIEW research_idempotency AS SELECT email FROM main.auth_users')
        else:
            good=tmp_path/'attached.sqlite3'
            with sqlite3.connect(good) as other:other.execute('CREATE TABLE research_schema(id INTEGER,version INTEGER)');other.execute('INSERT INTO research_schema VALUES(1,9)')
            conn.execute('ATTACH DATABASE ? AS approved_shadow',(good.resolve().as_uri()+'?mode=ro&immutable=1',))
        _,_,forbidden=deny_nonmetadata(conn)
        with pytest.raises(ResearchError):ResearchStore.check_current_structure(conn)
        assert not forbidden
    assert byte_image(path)==before


def test_fk_data_failure_is_outside_structure_but_full_checker_still_rejects(current):
    from research.financial_guard import install_default_hook
    path,_=current
    with sqlite3.connect(path) as conn:
        conn.execute('UPDATE research_controls SET owner_id=?',(str(uuid4()),));conn.commit();conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before=byte_image(path)
    with native_ro(path) as conn:
        _,_,forbidden=deny_nonmetadata(conn);ResearchStore.check_current_structure(conn);assert not forbidden
    with sqlite3.connect(path) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn)
        with pytest.raises(ResearchError) as rejected:ResearchStore._check_v9(conn)
        assert rejected.value.code=='SCHEMA_UNSUPPORTED' and rejected.value.message=='金融存储关联不匹配。'
    assert byte_image(path)==before


def test_budget_data_binding_is_outside_structure_but_full_checker_still_rejects(registry_inputs):
    from research.financial_guard import install_default_hook
    from research.financial_admission_schemas import ProjectBudget
    _,path,_,_,_,_=registry_inputs
    with sqlite3.connect(path) as conn:
        account=conn.execute('SELECT id,binding_id FROM research_funding_accounts').fetchone()
        data=ProjectBudget(id=1,project_key='structure',funding_account_id=account[0],economic_binding=account[1],currency='CNY',scale=6,
            authorized_cap=10,authorization_ref=str(uuid4()),authorization_digest='a'*64,database_binding='0'*64,mode='offline_probe',status='closed',version=1).model_dump()
        # Deliberately inconsistent DATA fixture, never a source/permission positive.
        conn.create_function('research_financial_write_allowed',2,lambda *args:1)
        conn.execute('INSERT INTO research_project_budgets('+','.join(data)+') VALUES('+','.join('?' for _ in data)+')',tuple(data.values()))
        conn.commit();conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before=byte_image(path)
    with native_ro(path) as conn:
        _,_,forbidden=deny_nonmetadata(conn);ResearchStore.check_current_structure(conn);assert not forbidden
    with sqlite3.connect(path) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn)
        with pytest.raises(ResearchError) as rejected:ResearchStore._check_v9(conn)
        assert rejected.value.code=='SCHEMA_UNSUPPORTED' and rejected.value.message=='项目预算数据库绑定不匹配。'
    assert byte_image(path)==before


def test_half_v9_overlay_is_not_repaired_or_accepted(stack,monkeypatch):
    from research.financial_guard import METHOD_COLUMNS
    client,path=stack
    with monkeypatch.context() as old:
        old.setattr(ResearchStore,'_migrate_v9',lambda self:None)
        create(client);ResearchStore(auth._store())
    with sqlite3.connect(path) as conn:
        name,ddl=METHOD_COLUMNS[0]
        conn.execute('ALTER TABLE research_provider_sessions ADD COLUMN '+name+' '+ddl)
        conn.commit();conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before=byte_image(path)
    with native_ro(path) as conn:
        _,pragmas,forbidden=deny_nonmetadata(conn)
        with pytest.raises(ResearchError):ResearchStore.check_current_structure(conn)
        assert not forbidden and pragmas==[]
    assert byte_image(path)==before


def test_unrecognized_aux_on_versioned_auth_job_is_also_rejected(current):
    path,_=current
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TRIGGER foreign_job_aux BEFORE UPDATE ON auth_deletion_jobs BEGIN SELECT 1; END')
        conn.commit();conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before=byte_image(path)
    with native_ro(path) as conn:
        _,pragmas,forbidden=deny_nonmetadata(conn)
        with pytest.raises(ResearchError):ResearchStore.check_current_structure(conn)
        assert not forbidden and pragmas==[]
    assert byte_image(path)==before


def test_existing_read_snapshot_stays_consistent_when_another_writer_changes_schema(current):
    path,_=current
    reader=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,isolation_level=None)
    try:
        reader.execute('BEGIN')
        assert reader.execute('SELECT version FROM main.research_schema').fetchone()==(9,)
        with sqlite3.connect(path) as writer:writer.execute('ALTER TABLE research_idempotency ADD COLUMN raced_column TEXT')
        _,_,forbidden=deny_nonmetadata(reader)
        ResearchStore.check_current_structure(reader)
        assert not forbidden and reader.in_transaction
        reader.set_authorizer(None);reader.rollback();reader.execute('BEGIN')
        _,pragmas,forbidden=deny_nonmetadata(reader)
        with pytest.raises(ResearchError):ResearchStore.check_current_structure(reader)
        assert not forbidden and pragmas==[]
    finally:reader.set_authorizer(None);reader.rollback();reader.close()


def test_auth_job_historical_alter_column_order_remains_accepted(current):
    from research.financial_guard import JOB_ORIGIN_COLUMNS,V8_JOB_GUARDS
    path,_=current
    legacy=ResearchStore._auth_job_baseline_forms()[1]
    expanded=legacy.rstrip()[:-1]+', '+', '.join(name+' '+ddl for name,ddl in JOB_ORIGIN_COLUMNS)+')'
    with sqlite3.connect(path) as conn:
        conn.execute('DROP TABLE auth_deletion_jobs')
        conn.execute(expanded)
        conn.execute("CREATE UNIQUE INDEX auth_one_pending_deletion ON auth_deletion_jobs(owner_key) WHERE state!='completed'")
        for ddl in V8_JOB_GUARDS:conn.execute(ddl)
        conn.commit();conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before=byte_image(path)
    with native_ro(path) as conn:
        _,_,forbidden=deny_nonmetadata(conn);ResearchStore.check_current_structure(conn);assert not forbidden
    assert byte_image(path)==before
