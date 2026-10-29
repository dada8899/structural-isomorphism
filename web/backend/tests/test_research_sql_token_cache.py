"""Cache only pure SQL tokens; current database checks remain uncached."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from contextlib import closing

import pytest

from .test_research_runtime_profile import current, roots
from research import ResearchStore
from research.errors import ResearchError


@pytest.fixture(autouse=True)
def fresh_token_cache():
    normalize=ResearchStore._normalize_sql
    normalize.cache_clear()
    yield normalize
    normalize.cache_clear()


def test_cache_uses_complete_sql_key_and_returns_original_immutable_tokens(fresh_token_cache):
    normalize=fresh_token_cache
    sql="CREATE TABLE research_example (value TEXT CHECK(value='a b'))"
    spaced=sql.replace('CREATE TABLE','CREATE  TABLE')
    literal=sql.replace("'a b'","'ab'")
    expected=normalize.__wrapped__(sql)
    assert normalize(sql)==expected
    assert normalize(sql) is normalize(sql)
    assert normalize(spaced)==expected
    assert normalize(literal)!=expected
    assert normalize.cache_info().misses==3
    assert normalize.cache_info().currsize==3
    assert isinstance(expected,tuple) and all(isinstance(token,tuple) for token in expected)
    with pytest.raises(TypeError):normalize(sql)[0]=('word','changed')
    assert normalize(sql)==expected


def test_exceptions_are_not_cached(fresh_token_cache):
    normalize=fresh_token_cache
    for _ in range(2):
        with pytest.raises(TypeError):normalize(None)
    assert normalize.cache_info().misses==2
    assert normalize.cache_info().currsize==0
    with pytest.raises(TypeError):normalize([])
    assert normalize.cache_info().currsize==0


def test_cache_is_bounded_and_evicts_old_complete_keys(fresh_token_cache):
    normalize=fresh_token_cache
    for number in range(1025):normalize(f'CREATE TABLE research_example_{number} (id TEXT)')
    info=normalize.cache_info()
    assert info.maxsize==1024 and info.currsize==1024 and info.misses==1025
    normalize('CREATE TABLE research_example_0 (id TEXT)')
    assert normalize.cache_info().misses==1026
    assert normalize.cache_info().currsize==1024


def test_concurrent_cache_reads_preserve_the_uncached_value(fresh_token_cache):
    normalize=fresh_token_cache
    sql='CREATE TABLE "research_example" (id TEXT PRIMARY KEY)'
    expected=normalize.__wrapped__(sql)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(normalize,[sql]*128))==[expected]*128
    assert normalize.cache_info().currsize==1


def test_warm_cache_does_not_hide_schema_changes_on_the_same_connection(current):
    store=current
    from research.store import CURRENT_RESEARCH_SCHEMA_VERSION
    reached=[]
    with pytest.raises(ResearchError) as failure:
        with store.transaction(write=True) as conn:
            assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==CURRENT_RESEARCH_SCHEMA_VERSION
            store.check_runtime_version(conn)
            reached.append('warm_current')
            conn.execute('DROP TRIGGER research_revision_no_update')
            conn.execute('CREATE TRIGGER research_revision_no_update BEFORE UPDATE ON research_revisions BEGIN SELECT 1; END')
            reached.append('changed_trigger')
            store.check_runtime_version(conn)
    assert reached==['warm_current','changed_trigger']
    assert failure.value.code=='SCHEMA_UNSUPPORTED'
    # The rejected transaction rolls back; cached drift tokens cannot poison it.
    with store.transaction() as conn:store.check_runtime_version(conn)


def test_warm_cache_does_not_hide_drift_in_a_second_database(current,tmp_path,monkeypatch):
    store=current;path=store.path
    from .test_research_formula_delivery import _configure_private_root
    from research.store import CURRENT_RESEARCH_SCHEMA_VERSION
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==CURRENT_RESEARCH_SCHEMA_VERSION
        store.check_runtime_version(conn)
    target=tmp_path/'other'/'auth.sqlite3';target.parent.mkdir()
    with closing(sqlite3.connect(path)) as original,closing(sqlite3.connect(target)) as other:original.backup(other)
    assert target.stat().st_ino!=path.stat().st_ino
    with monkeypatch.context() as second_root:
        _configure_private_root(target,second_root)
        other_store=ResearchStore(type(store.auth_store)(target))
        with other_store.transaction() as conn:other_store.check_runtime_version(conn)
        with closing(sqlite3.connect(target)) as other:
            other.execute('DROP TRIGGER research_revision_no_update')
            other.execute('CREATE TRIGGER research_revision_no_update BEFORE UPDATE ON research_revisions BEGIN SELECT 1; END')
        with pytest.raises(ResearchError) as failure:ResearchStore(type(store.auth_store)(target))
        assert failure.value.code=='SCHEMA_UNSUPPORTED'
    with store.transaction() as conn:store.check_runtime_version(conn)
