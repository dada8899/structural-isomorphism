"""Exact real R13 producers, additive14, native faults and no-Git recovery."""
from contextlib import closing
import json,multiprocessing,sqlite3,shutil
from pathlib import Path
import pytest
from services.auth_store import AuthStore
from research import ResearchStore
from research.method_draft import provision_method_drafts_v14
from research.financial_input import provision_financial_inputs_v15
from research.errors import ResearchError
from research.formula_runtime import recover_formula_journal
from research.financial_guard import install_default_hook
from .test_private_runtime_bootstrap import roots
from .method_v13_reference import produce
from .method_draft_process_fixture import kill_upgrade,read_migrated


def snapshot(path):
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        return {name:conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for (name,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'") if name!='research_schema'}


def old13(roots,tmp_path,mode='native'):
    original=produce(Path(__file__).resolve().parents[3],tmp_path/'old13',roots,tmp_path/'original.json',mode=mode)
    path=roots/'auth.sqlite3'
    return path,(path.stat().st_dev,path.stat().st_ino),original,snapshot(path)


def spawn(target,args):
    child=multiprocessing.get_context('spawn').Process(target=target,args=args)
    try:
        child.start();child.join(20);assert not child.is_alive();return child.exitcode
    finally:
        if child.is_alive():child.kill();child.join(2)
        child.close()


def check(path,version,before):
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn);conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
        (ResearchStore._check_v14 if version==14 else ResearchStore._check_v13)(conn)
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        conn.rollback()
    after=snapshot(path)
    assert {name:after[name] for name in before}==before
    if version==14:assert after['research_method_drafts']==[]


@pytest.mark.parametrize('mode',['native','fixture'])
def test_real_13_source_formula_saved_and_unknown_finance_survive_14_same_inode_ref_time(roots,tmp_path,mode):
    path,inode,original,before=old13(roots,tmp_path,mode)
    with pytest.raises(Exception):ResearchStore(AuthStore(path))
    migrated=provision_method_drafts_v14(path)
    assert migrated['schema_version']==14 and migrated['financial_protocol']==9
    assert (path.stat().st_dev,path.stat().st_ino)==inode
    assert provision_method_drafts_v14(path)==migrated
    check(path,14,before)
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn);conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
        try:
            ResearchStore._check_v14(conn)
            assert not conn.execute('PRAGMA foreign_key_check').fetchall()
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==tuple(original['money'])
            with pytest.raises(sqlite3.Error):conn.execute('UPDATE research_funding_accounts SET held=0')
        finally:conn.rollback()
    with pytest.raises(ResearchError) as rejected:AuthStore(path)
    assert rejected.value.code=='SCHEMA_UNSUPPORTED'
    before14=snapshot(path)
    assert provision_financial_inputs_v15(path)['schema_version']==15
    assert (path.stat().st_dev,path.stat().st_ino)==inode
    after15=snapshot(path)
    assert {name:after15[name] for name in before14}==before14
    with ResearchStore(AuthStore(path)).transaction() as conn:ResearchStore._check_v15(conn)
    output=tmp_path/'read.json'
    assert spawn(read_migrated,(str(path),original,str(output)))==0
    assert json.loads(output.read_text())=={'plan_results_unchanged':True,'formula_result_unchanged':True,'original_source_readable':True}


@pytest.mark.parametrize('cut',['journal','table','guard','marker','before-commit','after-commit'])
def test_actual_migration_kill_recovers_complete13_or14_and_preserves_original_rows(roots,tmp_path,cut):
    path,inode,original,before=old13(roots,tmp_path)
    assert spawn(kill_upgrade,(str(path),cut))==(82 if cut=='after-commit' else 81)
    version=14 if cut=='after-commit' else 13
    recovered=recover_formula_journal(path)
    assert recovered['schema_version']==version and recovered['current_app_compatible'] is False
    assert (path.stat().st_dev,path.stat().st_ino)==inode
    check(path,version,before)
    if version==13:provision_method_drafts_v14(path)
    check(path,14,before)
    before14=snapshot(path)
    assert provision_financial_inputs_v15(path)['schema_version']==15
    assert (path.stat().st_dev,path.stat().st_ino)==inode
    after15=snapshot(path)
    assert {name:after15[name] for name in before14}==before14
    with ResearchStore(AuthStore(path)).transaction() as conn:ResearchStore._check_v15(conn)


def test_reference_13_real_producer_is_selfcontained_in_no_git_shallow_source(tmp_path):
    current=Path(__file__).resolve().parents[3];sparse=tmp_path/'source'
    reference=Path('web/backend/tests/reference/method_v13');manifest=json.loads((current/reference/'manifest.json').read_text())
    required={Path('web/backend/tests/method_v13_history_producer.py'),Path('web/backend/tests/reference/plan_v12/problem.json'),reference/'manifest.json',reference/'deltas.json'}
    required.update(Path(name) for case in manifest['cases'].values() for name in case['files'])
    for relative in required:
        source=current/relative;assert source.is_file() and not source.is_symlink()
        target=sparse/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    assert not (sparse/'.git').exists()
    value=produce(sparse,tmp_path/'old13',tmp_path/'state',tmp_path/'original.json')
    assert value['money'][0]>0 and value['money'][1]>0 and value['results'][0]['result']['data']['content']['real_model_executed'] is False


@pytest.mark.parametrize('damage',['unknown','missing_guard','partial14'])
def test_old13_preflight_rejects_unknown_or_partial_graph_before_journal_or_ddl(roots,tmp_path,damage,monkeypatch):
    path,inode,_,before=old13(roots,tmp_path)
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        if damage=='unknown':conn.execute('CREATE INDEX research_unknown_method ON research_controls(version)')
        elif damage=='missing_guard':conn.execute('DROP TRIGGER research_native_run_domain')
        else:conn.execute('CREATE TABLE research_method_drafts (draft_ref TEXT)')
        image=conn.serialize()
    native=sqlite3.connect;mutations=[]
    class Observe(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if sql.startswith(('PRAGMA journal_mode=','CREATE ','ALTER ','UPDATE research_schema')):mutations.append(sql)
            return super().execute(sql,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',lambda *a,**kw:native(*a,**kw) if 'factory' in kw else native(*a,factory=Observe,**kw))
    with pytest.raises(Exception):provision_method_drafts_v14(path)
    assert mutations==[]
    with closing(native(path,isolation_level=None)) as conn:assert conn.serialize()==image
    assert (path.stat().st_dev,path.stat().st_ino)==inode


def test_frozen_legacy9_through13_declaration_graphs_remain_exact():
    import hashlib
    manifest=json.loads((Path(__file__).parent/'reference/method_v13/manifest.json').read_text())
    for version in (9,10,11,12,13):
        raw=json.dumps(ResearchStore._current_structure_declarations(version=version),sort_keys=True,separators=(',',':')).encode()
        assert hashlib.sha256(raw).hexdigest()==manifest['legacy_graph_sha256'][str(version)]
