"""Real old producer -> complete11 -> offline12; original formula stays exact."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import pytest
from api import auth,research
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.auth_store import AuthStore
from research import ResearchStore
from research.source_guard import provision_source_v11
from research.plan_financial import provision_plan_v12
from .test_private_runtime_bootstrap import roots
from .test_private_registration import BETA,SECRET,link,verify
from .source_v10_reference import produce


def old11(roots,tmp_path):
    original=produce(Path(__file__).resolve().parents[3],tmp_path/'old10',roots,tmp_path/'old10.json')
    path=roots/'auth.sqlite3';inode=path.stat().st_ino
    assert provision_source_v11(path)['schema_version']==11 and path.stat().st_ino==inode
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row
        before=[tuple(row) for row in conn.execute('SELECT result_ref,admission_json,receipt_json,result_json,commit_json FROM research_formula_runs')]
    return path,inode,original,before


def test_real_complete11_to12_same_inode_formula_ref_time_and_old_source_permission(roots,monkeypatch,tmp_path):
    path,inode,original,before=old11(roots,tmp_path)
    result=provision_plan_v12(path)
    assert result['schema_version']==12 and result['financial_protocol']==8 and path.stat().st_ino==inode
    assert provision_plan_v12(path)==result
    with ResearchStore(AuthStore(path)).transaction() as conn:
        assert [tuple(row) for row in conn.execute('SELECT result_ref,admission_json,receipt_json,result_json,commit_json FROM research_formula_runs')]==before
        assert conn.execute('SELECT consent_origin,consent_digest FROM research_source_approvals').fetchone()[:]==(None,None)
        assert conn.execute('SELECT count(*) FROM research_plan_dispatches').fetchone()[0]==0
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
    settings={'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':BETA,'JWT_SECRET':SECRET,'STRUCTURAL_SSO_SECRET':SECRET,
        'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'}
    for k,v in settings.items():monkeypatch.setenv(k,v)
    monkeypatch.setattr(auth,'_AUTH_STORES',{});mail=[];monkeypatch.setattr(auth,'_send_email',lambda to,subject,text:mail.append(text));monkeypatch.setattr(research,'enabled',lambda:True)
    app=FastAPI();app.include_router(auth.router,prefix='/api');app.include_router(research.router,prefix='/api')
    with TestClient(app,base_url=BETA) as client:
        assert verify(client,link(client,mail)).status_code==200
        opened=client.get('/api/research/'+original['rid']+'/formula-results/'+original['ref'])
        assert opened.status_code==200 and opened.json()['data']==original['result']
        view=client.get('/api/research/'+original['rid'])
        assert view.status_code==200 and view.json()['data']['formula_check']['result_ref']==original['ref']


@pytest.mark.parametrize('cut',['journal','rebuild','resource','marker','before-commit','after-commit'])
def test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes(roots,tmp_path,cut):
    import multiprocessing
    from .plan_process_fixture import kill_upgrade
    from research.formula_runtime import recover_formula_journal
    from research.financial_guard import install_default_hook
    path,inode,original,before=old11(roots,tmp_path)
    child=multiprocessing.get_context('spawn').Process(target=kill_upgrade,args=(str(path),cut))
    try:
        child.start();child.join(12)
        assert not child.is_alive() and child.exitcode==(82 if cut=='after-commit' else 81)
    finally:
        if child.is_alive():child.kill();child.join(2)
        child.close()
    version=12 if cut=='after-commit' else 11
    recovered=recover_formula_journal(path)
    assert recovered['schema_version']==version and recovered['current_app_compatible'] is (version==12)
    assert path.stat().st_ino==inode
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;install_default_hook(conn);conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
        (ResearchStore._check_v12 if version==12 else ResearchStore._check_v11)(conn)
        assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0]==1 and conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert [tuple(row) for row in conn.execute('SELECT result_ref,admission_json,receipt_json,result_json,commit_json FROM research_formula_runs')]==before
        conn.rollback()
    if version==11:
        assert provision_plan_v12(path)['schema_version']==12
    with ResearchStore(AuthStore(path)).transaction() as conn:assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==12
