"""Exact Auth/Research pairs at both existing-only offline formula ports."""
from contextlib import closing
import sqlite3
import pytest
from research import ResearchStore
from research.financial_guard import install_default_hook
from research.formula_runtime import provision_formula_v10,recover_formula_journal
from services.auth_registration import bootstrap_private_runtime
from services.auth_store import AuthStore
from .test_private_runtime_bootstrap import roots
from .test_research_persistence import stack
from .test_research_formula_delivery import v9,_configure_private_root


def current_auth_with_complete_v9(path):
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA foreign_keys=OFF');conn.execute('BEGIN IMMEDIATE')
        objects=conn.execute("SELECT type,name FROM sqlite_schema WHERE name LIKE 'research_%'").fetchall()
        for kind in ('trigger','index','table'):
            for row in objects:
                if row['type']==kind:conn.execute('DROP '+kind.upper()+' "'+row['name']+'"')
        wanted=ResearchStore._current_structure_declarations(version=9)
        for kind in ('table','index','trigger'):
            for name,(actual,_,forms) in wanted.items():
                if actual==kind and name.startswith('research_'):conn.execute(forms[0])
        conn.execute('INSERT INTO research_schema VALUES(1,9)');conn.commit()
        conn.execute('PRAGMA foreign_keys=ON');install_default_hook(conn);conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='auth-provision-v1'
        ResearchStore._check_structure_version(conn,9);ResearchStore._check_v9(conn)
        conn.rollback()


@pytest.mark.parametrize('operation',[recover_formula_journal,provision_formula_v10])
def test_complete_current_auth_with_complete_research9_rejects_before_journal_or_ddl(roots,monkeypatch,operation):
    bootstrap_private_runtime();path=roots/'auth.sqlite3';current_auth_with_complete_v9(path)
    original=sqlite3.connect;stat=path.stat();before=path.read_bytes();sql=[]
    def connect(*args,**kwargs):
        conn=original(*args,**kwargs);conn.set_trace_callback(sql.append);return conn
    with monkeypatch.context() as observe:
        observe.setattr(sqlite3,'connect',connect)
        with pytest.raises(PermissionError,match='Auth and research profile pair'):
            operation(path)
    assert sql and not any('journal_mode' in statement.lower() for statement in sql)
    assert not any(statement.lstrip().upper().startswith(('CREATE','DROP','ALTER','INSERT','UPDATE','DELETE','REPLACE')) for statement in sql)
    assert path.read_bytes()==before
    assert (path.stat().st_dev,path.stat().st_ino)==(stat.st_dev,stat.st_ino)
    assert not path.with_name(path.name+'.formula-maintenance').exists()
    with closing(original(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)) as conn:
        assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==9


def test_legacy_auth_research9_provisions10_and_legacy10_recovers_readonly_compatibility(v9,monkeypatch):
    _,path,rid,_=v9;path=_configure_private_root(path,monkeypatch)
    assert recover_formula_journal(path)['current_app_compatible'] is False
    result=provision_formula_v10(path);assert result['schema_version']==10
    recovered=recover_formula_journal(path)
    assert recovered['schema_version']==10 and recovered['current_app_compatible'] is False
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)) as conn:
        conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='legacy_auth'
        assert conn.execute('SELECT id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]==rid


def test_current_auth_research13_remains_exactly_supported(roots):
    bootstrap_private_runtime();path=roots/'auth.sqlite3'
    result=recover_formula_journal(path)
    assert result['schema_version']==13 and result['current_app_compatible'] is True and result['schema_repaired'] is False
    store=ResearchStore(AuthStore(path))
    with store.transaction() as conn:ResearchStore._check_v13(conn)


def test_historical_current_auth_research11_recovers_without_app_admission(roots,tmp_path):
    # Use the already reviewed old producer/code closure and the actual 10->11
    # maintainer; no current bootstrap, marker edits or synthetic old schema.
    from .test_research_plan_schema_v12 import old11
    path,inode,original,before=old11(roots,tmp_path)
    result=recover_formula_journal(path)
    assert result['schema_version']==11 and result['current_app_compatible'] is False and result['schema_repaired'] is False
    assert path.stat().st_ino==inode
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn)
        conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='auth-provision-v1'
        ResearchStore._check_v11(conn)
        assert [tuple(row) for row in conn.execute('SELECT result_ref,admission_json,receipt_json,result_json,commit_json FROM research_formula_runs')]==before
        assert conn.execute('SELECT result_ref FROM research_formula_runs').fetchone()[0]==original['ref']
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_historical_current_auth_research12_recovers_without_app_admission(roots,tmp_path):
    # The frozen R12 producer executes the original HTTP/worker path and keeps
    # its original saved plan, ledger and provenance; recovery only reads it.
    from .test_research_native_schema_v13 import old12,TABLES
    import json
    path,identity,original,before=old12(roots,tmp_path)
    result=recover_formula_journal(path)
    assert result['schema_version']==12 and result['current_app_compatible'] is False and result['schema_repaired'] is False
    assert (path.stat().st_dev,path.stat().st_ino)==identity
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn)
        conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='auth-provision-v1'
        ResearchStore._check_v12(conn)
        assert {table:[tuple(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid')] for table in TABLES}==before
        saved=conn.execute('SELECT result_ref,result_json,commit_json FROM research_plan_dispatches').fetchone()
        assert saved['result_ref']==original['ref']
        assert json.loads(saved['result_json'])==original['result']['data']['content']
        assert json.loads(saved['commit_json'])['recorded_at']==original['result']['data']['content']['recorded_at']
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
