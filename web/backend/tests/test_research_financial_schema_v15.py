"""FIN-2 real declarations/maintenance; no marker relabel or current-code old producer."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import os
import multiprocessing
import sys
import signal

import pytest
from services.auth_registration import bootstrap_private_runtime
from services.auth_store import AuthStore
from research import ResearchStore
from research.financial_guard import install_default_hook
from research.financial_input import provision_financial_inputs_v15
from research.method_draft import provision_method_drafts_v14
from .test_private_runtime_bootstrap import roots
from .method_v13_reference import produce
from .test_research_source_terminal14 import current14 as legacy14


def image(path):
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        return {name:conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for (name,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'") if name!='research_schema'}


def inspect(path,version):
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn);conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
        getattr(ResearchStore,'_check_v'+str(version))(conn)
        assert list(map(tuple,conn.execute('SELECT * FROM research_schema')))==[(1,version)]
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        conn.rollback()


def test_real_fresh15_exact_graph_hooks_and_idempotent_bootstrap(roots):
    made=bootstrap_private_runtime();assert made['research_schema']==15 and made['created'] is True
    path=roots/'auth.sqlite3';identity=(path.stat().st_dev,path.stat().st_ino)
    assert bootstrap_private_runtime()=={'contract':'auth-provision-v1','research_schema':15,'created':False}
    assert (path.stat().st_dev,path.stat().st_ino)==identity
    store=ResearchStore(AuthStore(path))
    with store.transaction() as conn:
        ResearchStore._check_v15(conn)
        for query,expected in (("SELECT research_financial_guard_version()",7),("SELECT research_method_guard_version()",9),("SELECT research_source_guard_version()",11),("SELECT research_method_draft_guard_version()",14),("SELECT research_financial_input_guard_version()",2)):
            assert conn.execute(query).fetchone()[0]==expected
    inspect(path,15)


def test_legacy_cold_complete14_preserves_old_semantics_but_is_never15_or_formal(legacy14):
    _,store,_=legacy14
    before=image(store.path)
    with store.transaction() as conn:
        ResearchStore._check_v14(conn)
        assert AuthStore.check_offline_auth_metadata(conn)=='legacy_auth'
        assert conn.execute("SELECT count(*) FROM sqlite_schema WHERE name IN ('research_financial_registries','research_financial_results')").fetchone()[0]==0
        with pytest.raises(Exception):ResearchStore._check_v15(conn)
    assert store._formal_mode() is False
    with pytest.raises(Exception):provision_financial_inputs_v15(store.path)
    assert image(store.path)==before


@pytest.mark.parametrize('mode',['native','fixture'])
def test_exact_old13_to_real14_then15_preserves_all_original_rows_refs_time_and_inode(roots,tmp_path,mode):
    original=produce(Path(__file__).resolve().parents[3],tmp_path/'original13',roots,tmp_path/'old13.json',mode=mode)
    path=roots/'auth.sqlite3';identity=(path.stat().st_dev,path.stat().st_ino)
    before=image(path);inspect(path,13)
    assert provision_method_drafts_v14(path)['schema_version']==14;inspect(path,14)
    before14=image(path)
    assert {k:before14[k] for k in before}==before
    result=provision_financial_inputs_v15(path);assert result['schema_version']==15
    assert provision_financial_inputs_v15(path)==result
    inspect(path,15);after=image(path)
    assert {k:after[k] for k in before14}==before14
    assert after['research_financial_registries']==after['research_financial_results']==[]
    assert (path.stat().st_dev,path.stat().st_ino)==identity
    with ResearchStore(AuthStore(path)).transaction() as conn:
        assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==tuple(original['money'])
    print('FIN2_MIGRATION:'+json.dumps({'actual_old13_source_closure':len(original['source_files']),'actual_14_then_15':True,'same_inode':True,'all_old_rows_exact':True}))


@pytest.mark.parametrize('damage',['missing_guard','unknown_index','fake_marker','partial_tables'])
def test_native_current_preflight_never_repairs_damaged15(roots,damage):
    bootstrap_private_runtime();path=roots/'auth.sqlite3'
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        if damage=='missing_guard':conn.execute('DROP TRIGGER research_financial_registries_no_replace')
        elif damage=='unknown_index':conn.execute('CREATE INDEX research_financial_unknown ON research_controls(version)')
        elif damage=='fake_marker':conn.execute('UPDATE research_schema SET version=14')
        else:conn.execute('DROP TABLE research_financial_results')
        before=conn.serialize()
    with pytest.raises(Exception):AuthStore(path)
    with pytest.raises(Exception):bootstrap_private_runtime()
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:assert conn.serialize()==before


def _kill_fin2_migration(path,cut):
    """Failure-only native SQLite subclass; actual statements execute first."""
    from services import runtime_paths as paths
    paths.STATE_ROOT=Path(path).parent;paths.CACHE_ROOT=Path(path).parent.parent/'cache';paths.LOG_ROOT=Path(path).parent/'logs'
    os.environ.update(STRUCTURAL_ENV='prod',AUTH_DATA_DIR=str(paths.STATE_ROOT),STRUCTURAL_SSO_DATA_DIR=str(paths.STATE_ROOT),STRUCTURAL_PRIVACY_HMAC_KEY='0123456789abcdef'*4)
    native=sqlite3.connect
    class Fault(sqlite3.Connection):
        started=False
        def execute(self,sql,*args,**kwargs):
            result=super().execute(sql,*args,**kwargs)
            if sql.startswith('CREATE TABLE research_financial_registries '):
                self.started=True
                if cut=='registry-table':os._exit(81)
                if cut=='sigkill':os.kill(os.getpid(),signal.SIGKILL)
            if self.started:
                if cut=='result-table' and sql.startswith('CREATE TABLE research_financial_results '):os._exit(81)
                if cut=='guard' and sql.startswith('CREATE TRIGGER research_financial_results_no_replace '):os._exit(81)
                if cut=='marker' and sql.startswith('UPDATE research_schema SET version=15'):os._exit(81)
            return result
        def commit(self):
            if self.started and cut=='before-commit':os._exit(81)
            result=super().commit()
            if self.started and cut=='after-commit':os._exit(82)
            return result
    sqlite3.connect=lambda *a,**kw:native(*a,**kw) if 'factory' in kw else native(*a,factory=Fault,**kw)
    provision_financial_inputs_v15(Path(path))
    raise AssertionError('the actual requested cut did not occur')


# The installed environment also has a top-level tests package. Spawn imports
# this exact repository module rather than pytest's ambiguous collection alias.
_canonical_module='web.backend.tests.test_research_financial_schema_v15'
sys.modules[_canonical_module]=sys.modules[__name__]
_kill_fin2_migration.__module__=_canonical_module


@pytest.mark.parametrize('cut',['registry-table','result-table','guard','marker','before-commit','after-commit','sigkill'])
def test_real14_to15_process_death_recovers_complete_graph_and_original_rows(roots,tmp_path,cut):
    from research.formula_runtime import recover_formula_journal
    produce(Path(__file__).resolve().parents[3],tmp_path/'original13',roots,tmp_path/'old13.json',mode='native')
    path=roots/'auth.sqlite3';provision_method_drafts_v14(path);inspect(path,14);before=image(path)
    identity=(path.stat().st_dev,path.stat().st_ino)
    process=multiprocessing.get_context('spawn').Process(target=_kill_fin2_migration,args=(str(path),cut))
    try:
        process.start();pid=process.pid;process.join(25)
        assert not process.is_alive() and process.exitcode==(-signal.SIGKILL if cut=='sigkill' else 82 if cut=='after-commit' else 81)
    finally:
        if process.is_alive():process.kill();process.join(3)
        process.close()
    recovered=recover_formula_journal(path);version=15 if cut=='after-commit' else 14
    assert recovered['schema_version']==version and recovered['schema_repaired'] is False
    assert recovered['current_app_compatible'] is (version==15)
    inspect(path,version);after=image(path)
    assert {k:after[k] for k in before}==before and (path.stat().st_dev,path.stat().st_ino)==identity
    if version==14:provision_financial_inputs_v15(path);inspect(path,15)
    print('FIN2_KILLED_MIGRATION:'+json.dumps({'cut':cut,'child_pid':pid,'joined':True,'recovered_version':version,'same_inode':True,'old_rows_exact':True}))
