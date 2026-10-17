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


def test_current_auth_research10_remains_exactly_supported(roots):
    bootstrap_private_runtime();path=roots/'auth.sqlite3'
    result=recover_formula_journal(path)
    assert result['schema_version']==10 and result['current_app_compatible'] is True and result['schema_repaired'] is False
    store=ResearchStore(AuthStore(path))
    with store.transaction() as conn:ResearchStore._check_v10(conn)
