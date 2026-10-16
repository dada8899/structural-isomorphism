"""Real deletion, legacy compensation, restart and cross-process fences."""
from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import uuid4
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .test_research_persistence import stack, create, problem, post, login, trusted_sso
from api import auth, research, favorites, report, report_account, sso
from errors import install_problem_handlers
from research.authorization import AuthorizationGate
from research.store import ResearchStore
from services.auth_store import AuthStore, DeletedCredentialError
from services.report_store import ReportStore

EMAIL = "research-a@example.test"
CANARY = "RESEARCH-ERASURE-CANARY-4159"


def lifecycle_app():
    app = FastAPI()
    for router in (auth.router, research.router, favorites.router, report.router, report_account.router, sso.router):
        app.include_router(router, prefix="/api")
    install_problem_handlers(app)
    return app


@pytest.fixture
def lifecycle(stack, monkeypatch):
    original, path = stack
    history = path.parent.parent / "legacy-history.db"
    monkeypatch.setattr(report_account, "_store", ReportStore(history))
    monkeypatch.setattr(report,"_store",report_account._store)
    monkeypatch.setattr(favorites,"_legacy_data_file",lambda:path.parent.parent/"unused-legacy-favorites.jsonl")
    with TestClient(lifecycle_app()) as client:
        client.cookies.update(original.cookies)
        yield client, path, history


def seed(client):
    response = post(client,"/api/research",{"problem":problem(CANARY)},"erase-create")
    assert response.status_code == 200, response.text
    rid = response.json()["data"]["research"]["id"]
    assert client.post("/api/favorites/AAPL",headers={"Origin":"http://testserver"}).status_code == 201
    item = report_account._store.create(query="legacy sample",b_id="b",lang="zh",payload={},model="fixture",creator_anon_id="legacy-anon")
    # Real legacy store preparation; no new research execution is mocked.
    report_account._store.claim_by_anon("legacy-anon",sso._subject_id(EMAIL))
    return rid,item["id"]


def delete(client):
    return client.post("/api/me/delete",json={"confirmation":"DELETE"},headers={"Origin":"http://testserver"})


def assert_fenced(client, rid):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/me/reports").status_code == 401
    assert client.get("/api/favorites").status_code == 401
    assert client.get(f"/api/research/{rid}").status_code == 401
    assert post(client,"/api/research",{"problem":problem(CANARY)},"erase-create").status_code == 401


def assert_minimal_completed(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory=sqlite3.Row
        job=dict(conn.execute("SELECT * FROM auth_deletion_jobs").fetchone())
        assert job["state"] == "completed"
        assert job["owner_email"] is job["session_generation"] is None
        principal=dict(conn.execute("SELECT * FROM research_principals WHERE status='deleted'").fetchone())
        assert principal["normalized_email"] is principal["session_generation"] is None
        for table in ("research_controls","research_revisions","research_idempotency","research_grants"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    for candidate in (path,Path(str(path)+"-wal")):
        if candidate.exists():
            data=candidate.read_bytes()
            assert CANARY.encode() not in data
            assert EMAIL.encode() not in data
    return job


def test_real_account_delete_erases_body_replay_and_old_incarnation(lifecycle):
    client,path,_=lifecycle
    rid,_=seed(client)
    cookie=client.cookies.get("phase_session")
    with sqlite3.connect(path) as conn:
        before=conn.execute("SELECT id,epoch,gate_id FROM research_principals").fetchone()
    response=delete(client)
    assert response.status_code == 200,response.text
    assert response.json()["removed"]["research"]["revisions"] == 1
    assert response.json()["removed"]["favorites"]["records"] == 1
    assert response.json()["removed"]["claimed_reports"]["reports"] == 1
    assert response.json()["removed"]["authentication"]["account"] == 1
    job=assert_minimal_completed(path)
    assert auth.pending_account_deletions() == []
    assert auth.resume_account_deletion(job["id"]) == json.loads(job["result_json"])
    client.cookies.set("phase_session",cookie)
    assert_fenced(client,rid)
    client.cookies.clear()
    login(client)
    assert client.get(f"/api/research/{rid}").status_code == 404
    new_id=create(client,"erase-create")
    assert new_id != rid
    with sqlite3.connect(path) as conn:
        after=conn.execute("SELECT id,epoch,gate_id FROM research_principals WHERE status='active'").fetchone()
        assert after[0] != before[0] and after[2] == before[2]
        assert conn.execute("SELECT epoch FROM research_principals WHERE id=?",(before[0],)).fetchone()[0] == before[1]+1
    assert auth.resume_account_deletion(job["id"]) == json.loads(job["result_json"])
    assert client.get(f"/api/research/{new_id}").status_code == 200


def test_compensation_restores_legacy_bytes_but_never_access_then_local_restart_resume(lifecycle,monkeypatch):
    client,path,history=lifecycle
    rid,_=seed(client)
    sso_token=trusted_sso(EMAIL)
    with TestClient(client.app) as legacy:
        legacy.cookies.set("structural_beta_session",sso_token)
        assert legacy.get("/api/me/reports").status_code == 200
        assert legacy.get("/api/favorites").json()["tickers"] == ["AAPL"]
        favorites_before=favorites._data_file().read_bytes()
        real_delete=AuthStore.delete_account_data
        with monkeypatch.context() as fault:
            def fail(self,email,**kwargs):
                raise OSError("synthetic final-store failure")
            fault.setattr(AuthStore,"delete_account_data",fail)
            response=delete(client)
        assert response.status_code == 500
        assert response.json()["access_ended"] is True
        assert response.json()["deletion_state"] == "cleanup_pending"
        assert favorites._data_file().read_bytes() == favorites_before
        assert len(report_account._store.list_by_owner(sso._subject_id(EMAIL))) == 1
        assert_fenced(client,rid)
        assert legacy.get("/api/me/reports").status_code == 401
        assert legacy.get("/api/favorites").status_code == 401
        job_id=auth.pending_account_deletions()[0]
        old_generation=auth._store().user(EMAIL)["session_generation"]
        requested=client.post("/api/auth/request-link",json={"email":EMAIL})
        assert requested.status_code == 200
        assert requested.json() == {"ok":True}
        assert client.post("/api/auth/verify",json={"token":"unissued-pending-token"}).status_code == 400
        assert auth._store().user(EMAIL)["session_generation"] == old_generation
        assert auth._store().user(EMAIL)["lifecycle"] == "deleting"
        _resume_in_new_process(history,job_id)
        assert_minimal_completed(path)
        assert legacy.get("/api/me/reports").status_code == 401
        client.cookies.clear()
        login(client)
        assert client.get("/api/favorites").json()["tickers"] == []
        assert client.get("/api/me/reports").json()["items"] == []


def _child_setup(history):
    report_account._store=ReportStore(Path(history))
    report._store=report_account._store
    favorites._legacy_data_file=lambda:Path(history).parent/"unused-legacy-favorites.jsonl"
    return TestClient(lifecycle_app())


def _resume_child(history,job_id,result):
    try:
        with _child_setup(history):
            finished=auth.resume_account_deletion(job_id)
        result.put(("ok",finished["removed"]["research"]["revisions"]))
    except Exception as exc:
        result.put((type(exc).__name__,None))


def _resume_in_new_process(history,job_id):
    context=multiprocessing.get_context("spawn")
    result=context.Queue()
    process=context.Process(target=_resume_child,args=(str(history),job_id,result))
    process.start()
    try:
        assert result.get(timeout=20) == ("ok",1)
    finally:
        process.join(5)
        if process.is_alive():process.terminate();process.join(5)
        result.close()
    assert process.exitcode == 0


def _crash_child(history,cookie,phase):
    with _child_setup(history) as client:
        client.cookies.set("phase_session",cookie)
        from research.service import ResearchService
        # Crash after the real durable fence, before erasing research contents.
        if phase == "fence":
            ResearchService.erase_research_locked=lambda *args:os._exit(73)
        elif phase == "after-auth-delete":
            ResearchService.finish_account_deletion_locked=lambda *args:os._exit(74)
        else:
            ResearchService.record_legacy_deletion_locked=lambda *args,**kwargs:os._exit(75)
        delete(client)


@pytest.mark.parametrize("phase",["fence","after-auth-delete","before-legacy-receipt"])
def test_real_process_crash_after_fence_keeps_access_closed_and_recovers(lifecycle,phase):
    client,path,history=lifecycle
    rid,_=seed(client)
    context=multiprocessing.get_context("spawn")
    process=context.Process(target=_crash_child,args=(str(history),client.cookies.get("phase_session"),phase))
    process.start()
    try:
        process.join(15)
        assert process.exitcode == {"fence":73,"after-auth-delete":74,"before-legacy-receipt":75}[phase]
        assert_fenced(client,rid)
        with sqlite3.connect(path) as conn:
            if phase == "fence":
                assert CANARY in conn.execute("SELECT problem_json FROM research_revisions").fetchone()[0]
                assert conn.execute("SELECT status,epoch FROM research_principals").fetchone() == ("deleting",2)
                assert conn.execute("SELECT status FROM research_grants").fetchone()[0] == "revoked"
                assert conn.execute("SELECT lifecycle FROM research_controls").fetchone()[0] == "deleting"
            else:
                assert conn.execute("SELECT count(*) FROM auth_users").fetchone()[0] == 0
            job_id=conn.execute("SELECT id FROM auth_deletion_jobs WHERE state='pending'").fetchone()[0]
        with sqlite3.connect(path) as conn:
            tokens_before=conn.execute("SELECT count(*) FROM magic_tokens WHERE email=?",(EMAIL,)).fetchone()[0]
        requested=client.post("/api/auth/request-link",json={"email":EMAIL})
        assert requested.status_code == 200 and requested.json() == {"ok":True}
        assert client.post("/api/auth/verify",json={"token":"unissued-pending-token"}).status_code == 400
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT count(*) FROM magic_tokens WHERE email=?",(EMAIL,)).fetchone()[0] == tokens_before
        _resume_in_new_process(history,job_id)
        completed=assert_minimal_completed(path)
        receipt=json.loads(completed["result_json"])
        if phase == "after-auth-delete":
            assert receipt["removed"]["favorites"]["records"] == 1
            assert receipt["removed"]["claimed_reports"]["reports"] == 1
            assert receipt["removed"]["authentication"]["account"] == 1
        elif phase == "before-legacy-receipt":
            for asset,metric in (("favorites","records"),("claimed_reports","reports"),("authentication","account")):
                assert receipt["removed"][asset]["count_status"] == "unknown_after_interruption"
                assert metric not in receipt["removed"][asset]
                assert receipt["removed"][asset]["recovery_observed"][metric] == 0
        assert auth.resume_account_deletion(job_id) == receipt
    finally:
        if process.is_alive():process.terminate();process.join(5)


def _ordered_api_child(history,cookie,rid,operation,attempted,held,release,done,result,legacy_failure=False):
    original=AuthorizationGate.owner_gate_id
    @contextmanager
    def controlled_gate(self,*args,**kwargs):
        attempted.set()
        with original(self,*args,**kwargs):
            if held is not None:
                held.set()
                if not release.wait(15):raise RuntimeError("barrier expired")
            yield
    AuthorizationGate.owner_gate_id=controlled_gate
    try:
        if legacy_failure:
            AuthStore.delete_account_data=lambda *args,**kwargs:(_ for _ in ()).throw(OSError("synthetic ordered cleanup failure"))
        with _child_setup(history) as client:
            if cookie is not None:client.cookies.set("phase_session",cookie)
            if operation == "delete":
                response=delete(client)
            elif operation == "public-feedback":
                response=client.post(f"/api/report/{rid}/feedback",json={"section":None,"vote":1,"note":"ORDERED-PUBLIC-FEEDBACK"})
            else:
                response=post(client,f"/api/research/{rid}/revisions",{"expected_revision":1,"problem":problem(CANARY+"-late")},"ordered-revise")
            result.put((operation,response.status_code))
    finally:
        done.set()


@pytest.mark.parametrize("first",["write","delete"])
def test_two_real_api_processes_delete_and_write_share_one_gate(lifecycle,first):
    client,path,history=lifecycle
    rid,_=seed(client)
    context=multiprocessing.get_context("spawn")
    first_attempt,second_attempt,held,release,first_done,second_done=(context.Event() for _ in range(6))
    result=context.Queue()
    second="delete" if first=="write" else "write"
    args=(str(history),client.cookies.get("phase_session"),rid)
    one=context.Process(target=_ordered_api_child,args=(*args,first,first_attempt,held,release,first_done,result))
    two=context.Process(target=_ordered_api_child,args=(*args,second,second_attempt,None,release,second_done,result))
    processes=[]
    try:
        one.start();processes.append(one)
        assert held.wait(15)
        two.start();processes.append(two)
        assert second_attempt.wait(15)
        assert not second_done.wait(.1),"second process bypassed the held owner gate"
        release.set()
        responses=dict(result.get(timeout=20) for _ in range(2))
        assert responses["delete"] == 200
        assert responses["write"] == 200 if first=="write" else responses["write"] in (401,404)
        assert_minimal_completed(path)
        assert_fenced(client,rid)
    finally:
        release.set()
        for process in processes:
            process.join(5)
            if process.is_alive():process.terminate();process.join(5)
        result.close()


def _policy_probe(path,key,result):
    os.environ["STRUCTURAL_PRIVACY_HMAC_KEY"]=key
    try:
        store=AuthStore(Path(path))
        result.put(("ok",store.owner_gate_id(EMAIL)))
    except RuntimeError:
        result.put(("rejected",None))


def test_hmac_mismatch_process_and_live_rotation_fail_closed(lifecycle,monkeypatch):
    client,path,_=lifecycle
    create(client)
    gate=auth._store().owner_gate_id(EMAIL)
    context=multiprocessing.get_context("spawn")
    for key,expected in (("fedcba9876543210"*4,("rejected",None)),("0123456789abcdef"*4,("ok",gate))):
        result=context.Queue()
        process=context.Process(target=_policy_probe,args=(str(path),key,result))
        process.start()
        try:
            assert result.get(timeout=15) == expected
        finally:
            process.join(5)
            if process.is_alive():process.terminate();process.join(5)
            result.close()
    cached=auth._store()
    with monkeypatch.context() as rotation:
        rotation.setenv("STRUCTURAL_PRIVACY_HMAC_KEY","fedcba9876543210"*4)
        with pytest.raises(RuntimeError,match="configuration mismatch"):
            cached.owner_gate_id(EMAIL)
        with pytest.raises(RuntimeError,match="configuration mismatch"):
            ResearchStore(cached)
    assert cached.owner_gate_id(EMAIL) == gate
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM auth_owner_gates").fetchone()[0] == 1


def test_recovery_wrong_store_binding_is_rejected_before_any_other_account_cleanup(lifecycle,monkeypatch):
    client,path,_=lifecycle
    seed(client)
    with monkeypatch.context() as fault:
        fault.setattr(AuthStore,"delete_account_data",lambda *args,**kwargs:(_ for _ in ()).throw(OSError("injected")))
        assert delete(client).status_code == 500
    job=auth.pending_account_deletions()[0]
    with monkeypatch.context() as changed:
        changed.setenv("STRUCTURAL_FAVORITES_PATH",str(path.parent/"wrong-favorites.jsonl"))
        with pytest.raises(RuntimeError,match="recovery binding mismatch"):
            auth.resume_account_deletion(job)
    assert auth._store().user(EMAIL)["lifecycle"] == "deleting"
    assert auth.resume_account_deletion(job)["removed"]["research"]["revisions"] == 1


def test_busy_old_reader_keeps_scrubbing_until_real_checkpoint_succeeds(lifecycle,monkeypatch):
    client,path,_=lifecycle
    seed(client)
    reader=sqlite3.connect(path,isolation_level=None)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT problem_json FROM research_revisions").fetchall()
        response=delete(client)
        assert response.status_code == 503
        assert response.json()["access_ended"] is True
        assert "清理尚未完成" in response.json()["message"]
        with sqlite3.connect(path) as conn:
            job=conn.execute("SELECT id,state,owner_email,session_generation FROM auth_deletion_jobs").fetchone()
            assert job[1:] == ("scrubbing",None,None)
        assert auth.pending_account_deletions() == [job[0]]
        assert not auth.account_is_active(EMAIL)
    finally:
        reader.close()
    with monkeypatch.context() as forbid_legacy_replay:
        forbid_legacy_replay.setattr(auth,"_account_registry",lambda:(_ for _ in ()).throw(AssertionError("must not replay completed legacy cleanup")))
        assert auth.resume_account_deletion(job[0])["removed"]["research"]["revisions"] == 1
    assert_minimal_completed(path)


def test_copied_database_cannot_resume_original_registered_job(lifecycle,monkeypatch):
    client,path,_=lifecycle
    seed(client)
    with monkeypatch.context() as fault:
        fault.setattr(AuthStore,"delete_account_data",lambda *args,**kwargs:(_ for _ in ()).throw(OSError("injected")))
        assert delete(client).status_code == 500
    job_id=auth.pending_account_deletions()[0]
    copy_dir=path.parent.parent/"copied-db"
    copy_dir.mkdir()
    copied=copy_dir/"auth.sqlite3"
    with sqlite3.connect(path) as original,sqlite3.connect(copied) as copy:
        original.backup(copy)
    with monkeypatch.context() as changed:
        changed.setattr(auth,"_data_dir",lambda:copy_dir)
        from research.errors import ResearchError
        with pytest.raises(ResearchError,match="AUTHORIZATION_STALE"):
            auth.resume_account_deletion(job_id)
    assert auth.pending_account_deletions() == [job_id]
    assert auth.resume_account_deletion(job_id)["removed"]["research"]["revisions"] == 1


def test_v1_research_migration_keeps_existing_lock_inode_and_problem(lifecycle,monkeypatch):
    client,path,_=lifecycle
    with monkeypatch.context() as legacy:
        legacy.setattr(ResearchStore,"_migrate_v5",lambda self:None)
        rid=create(client)
    with sqlite3.connect(path) as conn:
        principal=conn.execute("SELECT id FROM research_principals").fetchone()[0]
        conn.execute("DROP TRIGGER research_principal_gate_required")
        conn.execute("ALTER TABLE research_principals DROP COLUMN gate_id")
        conn.execute("UPDATE research_schema SET version=1")
        conn.execute("DELETE FROM auth_owner_gates")
    lock=path.parent/"research-locks"/(principal+".lock")
    inode=lock.stat().st_ino
    ResearchStore(auth._store())
    assert lock.stat().st_ino == inode
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT version FROM research_schema").fetchone()[0] == 5
        assert conn.execute("SELECT gate_id FROM research_principals").fetchone()[0] == principal
    assert client.get(f"/api/research/{rid}").status_code == 200
    assert post(client,f"/api/research/{rid}/revisions",{"expected_revision":1,"problem":problem("迁移后新修订")}).status_code == 200


def test_legacy_key_without_auth_account_and_new_incarnation_share_gate_without_identity_inheritance(lifecycle,monkeypatch):
    client,path,_=lifecycle
    from auth import api_key
    key_path=path.parent/"synthetic-keys.jsonl"
    key_path.write_text(json.dumps({"key":"sk_standalone","owner_email":"standalone@example.test","tier":"pro","created_at":"2100-01-01T00:00:00Z","revoked":False})+"\n")
    monkeypatch.setenv("STRUCTURAL_API_KEYS_PATH",str(key_path))
    monkeypatch.setattr(api_key,"_store",None)
    with TestClient(client.app) as standalone:
        headers={"X-API-Key":"sk_standalone"}
        assert standalone.post("/api/favorites/AAPL",headers=headers).status_code == 201
        assert auth._store().user("standalone@example.test") is None
        old_gate=auth._store().owner_gate_id("standalone@example.test")
        assert post(standalone,"/api/research",{"problem":problem()},"key-only").status_code == 401
        login(standalone,"standalone@example.test")
        rid=create(standalone,"new-account")
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT p.gate_id FROM research_principals p JOIN research_controls r ON r.owner_id=p.id WHERE r.id=?",(rid,)).fetchone()[0] == old_gate


@pytest.mark.parametrize("sso_binding",[False,True])
def test_report_resource_lifecycle_controls_public_access_and_keeps_anonymous_legal(lifecycle,monkeypatch,sso_binding):
    owner,path,history=lifecycle
    rid,report_id=seed(owner)
    if sso_binding:
        trusted_sso(EMAIL)
    ledger=sso.SsoReplayStore(sso._data_dir()/"sso_replay.sqlite3")
    assert bool(ledger.email_for_subject(sso._subject_id(EMAIL))) is sso_binding
    store=report_account._store
    row=store.get_by_id(report_id)
    token=row["share_token"]
    anonymous=store.create(query="ordinary anonymous report",b_id="anonymous",lang="zh",payload={},model="fixture",creator_anon_id="ordinary-browser")
    public=TestClient(owner.app)
    try:
        share=f"/api/report/share/{token}"
        feedback=f"/api/report/{report_id}/feedback"
        followup=f"/api/report/{report_id}/followup"
        assert public.get(share).status_code == 200
        assert public.post(feedback,json={"section":None,"vote":1,"note":"BEFORE-FENCE-FEEDBACK"}).status_code == 200
        assert owner.post(followup,json={"action_status":"planned","note":"BEFORE-FENCE-FOLLOWUP"}).status_code == 200
        assert owner.get(followup).status_code == 200
        before_views=store.get_by_id(report_id)["view_count"]
        with monkeypatch.context() as fault:
            fault.setattr(AuthStore,"delete_account_data",lambda *args,**kwargs:(_ for _ in ()).throw(OSError("synthetic final auth cleanup failure")))
            failed=delete(owner)
        assert failed.status_code == 500 and failed.json()["access_ended"] is True
        assert store.get_by_id(report_id)["share_token"] == token
        assert_fenced(owner,rid)
        responses=[public.get(share),owner.get(f"/api/report/{report_id}"),
                   public.post(feedback,json={"section":None,"vote":1,"note":"AFTER-FENCE-FEEDBACK"}),
                   owner.post(followup,json={"action_status":"planned","note":"AFTER-FENCE-FOLLOWUP"}),owner.get(followup)]
        assert [response.status_code for response in responses] == [404]*5
        assert all("legacy sample" not in response.text and EMAIL not in response.text for response in responses)
        listed=public.get("/api/reports/mine",headers={"X-Anon-Id":"legacy-anon"})
        assert listed.status_code == 200 and listed.json()["items"] == []
        with sqlite3.connect(history) as conn:
            assert conn.execute("SELECT count(*) FROM report_feedback WHERE note='AFTER-FENCE-FEEDBACK'").fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM report_followup WHERE note='AFTER-FENCE-FOLLOWUP'").fetchone()[0] == 0
        assert store.get_by_id(report_id)["view_count"] == before_views
        anonymous_share=f"/api/report/share/{anonymous['share_token']}"
        assert public.get(anonymous_share).status_code == 200
        assert public.post(f"/api/report/{anonymous['id']}/feedback",json={"section":None,"vote":1,"note":"anonymous still allowed"}).status_code == 200
        assert public.post(f"/api/report/{anonymous['id']}/followup",headers={"X-Anon-Id":"ordinary-browser"},json={"action_status":"planned"}).status_code == 200
        auth.resume_account_deletion(auth.pending_account_deletions()[0])
        assert public.get(share).status_code == 404
        owner.cookies.clear();login(owner)
        assert public.get(share).status_code == 404
        assert owner.get("/api/me/reports").json()["items"] == []
        assert public.get(anonymous_share).status_code == 200
    finally:
        public.close()


@pytest.mark.parametrize("unresolved",["unresolved-server-owner","未知记录所属者","a"*201])
def test_unknown_persisted_report_owner_is_not_borrowed_from_visitor_cookie(lifecycle,unresolved):
    owner,_,_=lifecycle
    store=report_account._store
    item=store.create(query="unknown owner body",b_id="b",lang="zh",payload={},model="fixture",creator_anon_id="unknown-owner-browser")
    store.claim_by_anon("unknown-owner-browser",unresolved)
    assert owner.get(f"/api/report/share/{item['share_token']}").status_code == 404
    assert owner.post(f"/api/report/{item['id']}/feedback",json={"section":None,"vote":1}).status_code == 404
    assert owner.get("/api/reports/mine",headers={"X-Anon-Id":"unknown-owner-browser"}).json()["items"] == []


def test_hidden_deleting_reports_do_not_strand_legal_anonymous_pagination(lifecycle,monkeypatch):
    owner,_,_=lifecycle
    store=report_account._store
    for number in range(101):
        store.create(query=f"pending {number}",b_id="b",lang="zh",payload={},model="fixture",creator_anon_id="mixed-browser")
    store.claim_by_anon("mixed-browser",sso._subject_id(EMAIL))
    allowed=[store.create(query=f"allowed {number}",b_id="b",lang="zh",payload={},model="fixture",creator_anon_id="mixed-browser")["id"] for number in range(2)]
    with monkeypatch.context() as fault:
        fault.setattr(AuthStore,"delete_account_data",lambda *args,**kwargs:(_ for _ in ()).throw(OSError("synthetic failure")))
        assert delete(owner).status_code == 500
    with TestClient(owner.app) as public:
        first=public.get("/api/reports/mine?limit=1&offset=0",headers={"X-Anon-Id":"mixed-browser"}).json()
        second=public.get("/api/reports/mine?limit=1&offset=1",headers={"X-Anon-Id":"mixed-browser"}).json()
    assert first["has_more"] is True and second["has_more"] is False
    assert {first["items"][0]["id"],second["items"][0]["id"]} == set(allowed)


@pytest.mark.parametrize("first",["public-feedback","delete"])
def test_public_feedback_and_delete_use_same_resource_owner_gate(lifecycle,first):
    owner,_,history=lifecycle
    _,report_id=seed(owner)
    context=multiprocessing.get_context("spawn")
    first_attempt,second_attempt,held,release,first_done,second_done=(context.Event() for _ in range(6))
    result=context.Queue()
    second="delete" if first=="public-feedback" else "public-feedback"
    def child(operation,attempted,hold,done):
        cookie=owner.cookies.get("phase_session") if operation=="delete" else None
        return context.Process(target=_ordered_api_child,args=(str(history),cookie,report_id,operation,attempted,hold,release,done,result,operation=="delete"))
    one=child(first,first_attempt,held,first_done)
    two=child(second,second_attempt,None,second_done)
    processes=[]
    try:
        one.start();processes.append(one)
        assert held.wait(15)
        two.start();processes.append(two)
        assert second_attempt.wait(15)
        assert not second_done.wait(.1)
        release.set()
        responses=dict(result.get(timeout=20) for _ in range(2))
        assert responses["delete"] == 500
        assert responses["public-feedback"] == (200 if first=="public-feedback" else 404)
        with sqlite3.connect(history) as conn:
            assert conn.execute("SELECT count(*) FROM report_feedback WHERE note='ORDERED-PUBLIC-FEEDBACK'").fetchone()[0] == (1 if first=="public-feedback" else 0)
    finally:
        release.set()
        for process in processes:
            process.join(5)
            if process.is_alive():process.terminate();process.join(5)
        result.close()


def _stale_report_child(history,report_id,token,operation,reached,release,result):
    method={"feedback":"record_feedback","followup":"record_followup","view":"record_view"}[operation]
    original=getattr(ReportStore,method)
    def paused(self,*args,**kwargs):
        result.put(("expected_owner",kwargs.get("expected_owner","missing")))
        reached.set()
        if not release.wait(15):raise RuntimeError("report barrier expired")
        return original(self,*args,**kwargs)
    setattr(ReportStore,method,paused)
    with _child_setup(history) as public:
        if operation=="view":response=public.get(f"/api/report/share/{token}")
        elif operation=="followup":response=public.post(f"/api/report/{report_id}/followup",headers={"X-Anon-Id":"claim-transition"},json={"action_status":"planned","note":"TRANSITION-FOLLOWUP"})
        else:response=public.post(f"/api/report/{report_id}/feedback",json={"section":None,"vote":1,"note":"TRANSITION-FEEDBACK"})
        result.put(("status",response.status_code))


@pytest.mark.parametrize("operation",["feedback","followup","view"])
@pytest.mark.parametrize("first",["anonymous-write","claim-delete"])
def test_history_transaction_rechecks_anonymous_owner_after_real_claim_delete(lifecycle,monkeypatch,operation,first):
    owner,_,history=lifecycle
    store=report_account._store
    item=store.create(query="anonymous claim transition",b_id="b",lang="zh",payload={},model="fixture",creator_anon_id="claim-transition")
    context=multiprocessing.get_context("spawn")
    reached,release=context.Event(),context.Event()
    result=context.Queue()
    process=context.Process(target=_stale_report_child,args=(str(history),item["id"],item["share_token"],operation,reached,release,result))
    process.start()
    try:
        assert reached.wait(15)
        assert result.get(timeout=5) == ("expected_owner",None)
        if first=="anonymous-write":
            release.set()
            assert result.get(timeout=15) == ("status",200)
        assert owner.post("/api/reports/anon-proof",headers={"Origin":"http://testserver","X-Anon-Id":"claim-transition"}).status_code == 200
        assert owner.post("/api/me/reports/claim",headers={"Origin":"http://testserver"}).status_code == 200
        with monkeypatch.context() as fault:
            fault.setattr(AuthStore,"delete_account_data",lambda *args,**kwargs:(_ for _ in ()).throw(OSError("synthetic final store failure")))
            assert delete(owner).status_code == 500
        if first=="claim-delete":
            release.set()
            assert result.get(timeout=15) == ("status",404)
        with sqlite3.connect(history) as conn:
            if operation=="feedback":count=conn.execute("SELECT count(*) FROM report_feedback WHERE note='TRANSITION-FEEDBACK'").fetchone()[0]
            elif operation=="followup":count=conn.execute("SELECT count(*) FROM report_followup WHERE note='TRANSITION-FOLLOWUP'").fetchone()[0]
            else:count=conn.execute("SELECT view_count FROM reports WHERE id=?",(item["id"],)).fetchone()[0]
        assert count == (1 if first=="anonymous-write" else 0)
    finally:
        release.set();process.join(5)
        if process.is_alive():process.terminate();process.join(5)
        result.close()


def test_cold_owner_gate_creation_serializes_eight_threads_without_replacing_inode(tmp_path,monkeypatch):
    monkeypatch.setenv("STRUCTURAL_PRIVACY_HMAC_KEY","0123456789abcdef"*4)
    # Reproduce the first-creation window, not only re-open a warmed lock file.
    for number in range(20):
        parent=tmp_path/str(number)
        gate=AuthorizationGate(AuthStore(parent/"auth.sqlite3"))
        gate_id=str(uuid4())
        barrier=threading.Barrier(8)
        counter=parent/"critical-counter"
        counter.write_text("0")
        lock=parent/"research-locks"/(gate_id+".lock")
        def enter(_):
            barrier.wait(timeout=10)
            with gate.owner_gate_id(gate_id):
                # Actual file I/O yields between read/write: lost exclusion
                # loses increments, even if all opens happened to succeed.
                value=int(counter.read_text())
                counter.write_text(str(value+1))
                return lock.stat().st_ino
        with ThreadPoolExecutor(max_workers=8) as pool:
            inodes=list(pool.map(enter,range(8)))
        assert len(set(inodes)) == 1
        assert counter.read_text() == "8"
        assert lock.stat().st_ino == inodes[0]
        assert lock.stat().st_nlink == 1
        assert lock.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("tamper",["symlink","hardlink","file-permissions","directory-permissions","directory-symlink"])
def test_owner_gate_tampering_is_rejected_without_unlink_or_repair(tmp_path,monkeypatch,tamper):
    from research.errors import ResearchError
    monkeypatch.setenv("STRUCTURAL_PRIVACY_HMAC_KEY","0123456789abcdef"*4)
    gate=AuthorizationGate(AuthStore(tmp_path/"auth.sqlite3"))
    gate_id=str(uuid4())
    root=tmp_path/"research-locks"
    outside=tmp_path/"outside"
    if tamper == "directory-symlink":
        outside.mkdir(mode=0o700)
        root.symlink_to(outside,target_is_directory=True)
        with pytest.raises(ResearchError):
            with gate.owner_gate_id(gate_id):pytest.fail("entered directory symlink")
        assert root.is_symlink() and list(outside.iterdir()) == []
        return
    root.mkdir(mode=0o700)
    lock=root/(gate_id+".lock")
    if tamper == "directory-permissions":
        root.chmod(0o755)
    elif tamper == "symlink":
        outside.write_text("unchanged")
        lock.symlink_to(outside)
    else:
        lock.touch(mode=0o600)
        if tamper == "hardlink":os.link(lock,outside)
        else:lock.chmod(0o644)
    before=lock.lstat().st_ino if lock.exists() else None
    with pytest.raises((ResearchError,OSError)):
        with gate.owner_gate_id(gate_id):pytest.fail("entered tampered owner gate")
    if before is not None:assert lock.lstat().st_ino == before
    if tamper == "symlink":assert outside.read_text() == "unchanged" and lock.is_symlink()
    if tamper == "hardlink":assert lock.stat().st_nlink == outside.stat().st_nlink == 2
    if tamper == "file-permissions":assert lock.stat().st_mode & 0o777 == 0o644
    if tamper == "directory-permissions":assert root.stat().st_mode & 0o777 == 0o755


# Other legacy tests prepend web/backend to sys.path during collection. Pin
# spawned targets to the unambiguous repository package rather than whichever
# unrelated `tests` package wins in the child interpreter.
_WORKER_MODULE = "web.backend.tests.test_research_lifecycle"
if __name__ != _WORKER_MODULE:
    sys.modules[_WORKER_MODULE] = sys.modules[__name__]
    for _target in (_resume_child, _crash_child, _ordered_api_child, _policy_probe, _stale_report_child):
        _target.__module__ = _WORKER_MODULE
