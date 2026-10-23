"""Explicit static bootstrap, complete metadata and idempotent file identity."""
import os
import sqlite3
from contextlib import closing
import pytest
from services import runtime_paths as paths
from services.auth_store import AuthStore,_auth_final_contracts,_legacy_auth_contracts,_auth_metadata,_LEGACY_AUTH_DDL,_AUTH_LIFECYCLE_SQL
from services.auth_registration import bootstrap_private_runtime,AUTH_REGISTRATION_DDL
from .test_research_formula_delivery import v9,_configure_private_root
from .test_research_persistence import stack


@pytest.fixture
def roots(tmp_path,monkeypatch):
    state=tmp_path.resolve()/'state';cache=tmp_path.resolve()/'cache'
    monkeypatch.setattr(paths,'STATE_ROOT',state);monkeypatch.setattr(paths,'CACHE_ROOT',cache);monkeypatch.setattr(paths,'LOG_ROOT',state/'logs')
    monkeypatch.setenv('STRUCTURAL_ENV','prod');monkeypatch.setenv('AUTH_DATA_DIR',str(state))
    monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR',str(state))
    monkeypatch.setenv('STRUCTURAL_PRIVACY_HMAC_KEY','0123456789abcdef'*4)
    return state


def test_bootstrap_actual_empty_roots_and_identity_idempotence(roots):
    assert bootstrap_private_runtime()=={'contract':'auth-provision-v1','research_schema':15,'created':True}
    before={p.name:(p.stat().st_dev,p.stat().st_ino) for p in roots.iterdir()}
    assert not bootstrap_private_runtime()['created']
    assert before=={p.name:(p.stat().st_dev,p.stat().st_ino) for p in roots.iterdir()}
    store=AuthStore(roots/'auth.sqlite3')
    with store._connection() as conn:
        conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='auth-provision-v1'
        assert conn.execute('SELECT count(*) FROM auth_users').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM auth_registration_operations').fetchone()[0]==0
        assert list(map(tuple,conn.execute('SELECT * FROM research_schema')))==[(1,15)]
        from research import ResearchStore
        ResearchStore._check_v15(conn)


@pytest.mark.parametrize('nullable',[False,True])
def test_exact_offline_old_new_metadata_pure_snapshot(nullable):
    conn=sqlite3.connect(':memory:',isolation_level=None)
    try:
        for ddl in _LEGACY_AUTH_DDL:
            if nullable:ddl=ddl.replace('session_generation TEXT NOT NULL','session_generation TEXT')
            conn.execute(ddl)
        conn.execute(_AUTH_LIFECYCLE_SQL);conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='legacy_auth'
        assert conn.in_transaction
        for ddl in AUTH_REGISTRATION_DDL:conn.execute(ddl)
        assert AuthStore.check_offline_auth_metadata(conn)=='auth-provision-v1'
        conn.execute('DROP TRIGGER registration_auth_users_insert')
        with pytest.raises(RuntimeError):AuthStore.check_offline_auth_metadata(conn)
    finally:conn.close()


def test_bootstrap_rejects_partial_and_drift_without_repair(roots):
    bootstrap_private_runtime()
    (roots/'favorites.lock').unlink()
    with pytest.raises(PermissionError):bootstrap_private_runtime()
    assert not (roots/'favorites.lock').exists()


def test_formal_constructor_does_not_bootstrap(roots):
    with pytest.raises(Exception):AuthStore(roots/'auth.sqlite3')
    assert not roots.exists()


def test_exact_offline_migration_keeps_research10_and_identity(v9,monkeypatch):
    from services.auth_registration import migrate_private_auth_registration
    from research import ResearchStore
    from research.errors import ResearchError
    from research.formula_runtime import provision_formula_v10,recover_formula_journal
    from research.financial_guard import install_default_hook
    from services.sqlite_utils import connect_private_auth
    _,db,rid,_=v9;db=_configure_private_root(db,monkeypatch)
    provision_formula_v10(db)
    identity=(db.stat().st_dev,db.stat().st_ino)
    with closing(sqlite3.connect(db,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn);conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='legacy_auth'
        ResearchStore._check_v10(conn)
    with pytest.raises(RuntimeError):AuthStore(db)
    assert migrate_private_auth_registration()['migrated']
    assert not migrate_private_auth_registration()['migrated']
    assert (db.stat().st_dev,db.stat().st_ino)==identity
    with pytest.raises(ResearchError):AuthStore(db)
    with closing(connect_private_auth(db,readonly=True,expected_identity=identity)) as conn:
        install_default_hook(conn);conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='auth-provision-v1'
        assert list(map(tuple,conn.execute('SELECT * FROM research_schema')))==[(1,10)]
        ResearchStore._check_v10(conn)
        assert conn.execute('SELECT id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]==rid
    assert recover_formula_journal(db)['current_app_compatible'] is False


def test_current_preflight_metadata_only_no_hooks_or_business_reads(roots,monkeypatch):
    bootstrap_private_runtime();db=roots/'auth.sqlite3'
    original=sqlite3.connect;forbidden=[];queries=[]
    def connect(*args,**kwargs):
        conn=original(*args,**kwargs)
        if args[0]==db.as_uri()+'?mode=ro':
            def authorize(action,table,column,*_):
                if action==sqlite3.SQLITE_READ and table not in ('sqlite_master','sqlite_schema','research_schema','auth_owner_gate_policy'):
                    forbidden.append(table);return sqlite3.SQLITE_DENY
                if action not in (sqlite3.SQLITE_READ,sqlite3.SQLITE_SELECT,sqlite3.SQLITE_PRAGMA,sqlite3.SQLITE_TRANSACTION):
                    forbidden.append(action);return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            conn.set_authorizer(authorize);conn.set_trace_callback(queries.append)
        return conn
    monkeypatch.setattr(sqlite3,'connect',connect)
    AuthStore.preflight_private(db)
    assert not forbidden and queries
    assert not any(sql.upper().startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER')) or 'guard_version(' in sql or 'write_allowed(' in sql for sql in queries)
