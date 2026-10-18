"""Frozen real R12 -> R13: same ledger, old fixture provenance, inode and refs."""
from contextlib import closing
import json,multiprocessing,sqlite3
from pathlib import Path
import pytest
from services.auth_store import AuthStore
from research import ResearchStore
from research.financial_guard import install_default_hook
from research.formula_runtime import recover_formula_journal
from research.plan_native_financial import provision_native_v13
from .test_private_runtime_bootstrap import roots
from .plan_v12_reference import produce
from .plan_native_process_fixture import kill_upgrade,read_history

TABLES=('research_tasks','research_steps','research_task_events','research_funding_accounts','research_project_budgets','research_plan_dispatches','research_plan_previews','research_plan_funding')


def old12(roots,tmp_path):
    original=produce(Path(__file__).resolve().parents[3],tmp_path/'old12',roots,tmp_path/'old12.json')
    path=roots/'auth.sqlite3';identity=(path.stat().st_dev,path.stat().st_ino)
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        before={table:conn.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall() for table in TABLES}
    return path,identity,original,before


def verify_snapshot(path,version,before):
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn);conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
        (ResearchStore._check_v13 if version==13 else ResearchStore._check_v12)(conn)
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[] and conn.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert {t:[tuple(r) for r in conn.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in TABLES}==before
        conn.rollback()


def spawn(target,args):
    child=multiprocessing.get_context('spawn').Process(target=target,args=args)
    try:
        child.start();child.join(18)
        assert not child.is_alive()
        return child.exitcode
    finally:
        if child.is_alive():child.kill();child.join(2)
        child.close()


def test_real_old12_offline13_preserves_ledger_fixture_result_ref_time_newprocess(roots,tmp_path):
    path,identity,original,before=old12(roots,tmp_path)
    with pytest.raises(Exception):ResearchStore(AuthStore(path))
    result=provision_native_v13(path)
    assert result['schema_version']==13 and result['financial_protocol']==9
    assert (path.stat().st_dev,path.stat().st_ino)==identity
    assert provision_native_v13(path)==result
    verify_snapshot(path,13,before)
    with ResearchStore(AuthStore(path)).transaction() as conn:
        assert conn.execute('SELECT count(*) FROM research_plan_native_funding').fetchone()[0]==0
    output=tmp_path/'read.json'
    assert spawn(read_history,(str(path),original['rid'],original['ref'],str(output)))==0
    value=json.loads(output.read_text());assert value['result']==original['result']
    assert value['result']['data']['content']['real_model_executed'] is False
    assert value['result']['data']['content']['recorded_at']==original['result']['data']['content']['recorded_at']


@pytest.mark.parametrize('cut',['journal','rebuild','resource','marker','before-commit','after-commit'])
def test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger(roots,tmp_path,cut):
    path,identity,original,before=old12(roots,tmp_path)
    assert spawn(kill_upgrade,(str(path),cut))==(82 if cut=='after-commit' else 81)
    version=13 if cut=='after-commit' else 12
    recovered=recover_formula_journal(path)
    assert recovered['schema_version']==version and recovered['current_app_compatible'] is (version==13)
    assert (path.stat().st_dev,path.stat().st_ino)==identity
    verify_snapshot(path,version,before)
    if version==12:assert provision_native_v13(path)['schema_version']==13
    with ResearchStore(AuthStore(path)).transaction() as conn:assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==13


def test_real_v12_reference_producer_is_selfcontained_without_git_or_old_checkout(tmp_path):
    import shutil
    current=Path(__file__).resolve().parents[3];sparse=tmp_path/'shallow-source';reference=Path('web/backend/tests/reference/plan_v12')
    manifest=json.loads((current/reference/'manifest.json').read_text())
    required=[Path('web/backend/tests/plan_v12_history_producer.py'),*(reference/path.relative_to(current/reference) for path in (current/reference).rglob('*') if path.is_file())]
    required.extend(Path(path) for path,entry in manifest['files'].items() if entry['source']=='current_exact')
    required.append(Path('web/backend/tests/reference/method_v13/deltas.json'))
    for relative in required:
        source=current/relative;assert source.is_file() and not source.is_symlink()
        target=sparse/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    assert not (sparse/'.git').exists()
    result=produce(sparse,tmp_path/'old-package',tmp_path/'state',tmp_path/'old.json')
    assert result['result']['data']['state']=='saved' and result['result']['data']['content']['real_model_executed'] is False
