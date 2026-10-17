"""Explicit static bootstrap, complete metadata and idempotent file identity."""
import os
import sqlite3
import pytest
from services import runtime_paths as paths
from services.auth_store import AuthStore,_auth_final_contracts,_legacy_auth_contracts,_auth_metadata,_LEGACY_AUTH_DDL,_AUTH_LIFECYCLE_SQL
from services.auth_registration import bootstrap_private_runtime,AUTH_REGISTRATION_DDL


@pytest.fixture
def roots(tmp_path,monkeypatch):
    state=tmp_path.resolve()/'state';cache=tmp_path.resolve()/'cache'
    monkeypatch.setattr(paths,'STATE_ROOT',state);monkeypatch.setattr(paths,'CACHE_ROOT',cache);monkeypatch.setattr(paths,'LOG_ROOT',state/'logs')
    monkeypatch.setenv('STRUCTURAL_ENV','prod');monkeypatch.setenv('AUTH_DATA_DIR',str(state))
    monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR',str(state))
    monkeypatch.setenv('STRUCTURAL_PRIVACY_HMAC_KEY','0123456789abcdef'*4)
    return state


def test_bootstrap_actual_empty_roots_and_identity_idempotence(roots):
    assert bootstrap_private_runtime()=={'contract':'auth-provision-v1','research_schema':10,'created':True}
    before={p.name:(p.stat().st_dev,p.stat().st_ino) for p in roots.iterdir()}
    assert not bootstrap_private_runtime()['created']
    assert before=={p.name:(p.stat().st_dev,p.stat().st_ino) for p in roots.iterdir()}
    store=AuthStore(roots/'auth.sqlite3')
    with store._connection() as conn:
        conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='auth-provision-v1'
        assert conn.execute('SELECT count(*) FROM auth_users').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM auth_registration_operations').fetchone()[0]==0
        assert list(map(tuple,conn.execute('SELECT * FROM research_schema')))==[(1,10)]


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


def test_exact_offline_migration_keeps_research10_and_identity(roots):
    from services.auth_registration import migrate_private_auth_registration
    bootstrap_private_runtime();db=roots/'auth.sqlite3';identity=(db.stat().st_dev,db.stat().st_ino)
    conn=sqlite3.connect(db,isolation_level=None)
    try:
        for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='trigger' AND name LIKE 'registration_%'").fetchall():conn.execute('DROP TRIGGER '+row[0])
        conn.execute('DROP TABLE auth_registration_operations');conn.execute('DROP TABLE auth_registration_receipts')
    finally:conn.close()
    with pytest.raises(RuntimeError):AuthStore(db)
    assert migrate_private_auth_registration()['migrated']
    assert not migrate_private_auth_registration()['migrated']
    assert (db.stat().st_dev,db.stat().st_ino)==identity
    with AuthStore(db)._connection() as conn:
        assert list(map(tuple,conn.execute('SELECT * FROM research_schema')))==[(1,10)]
