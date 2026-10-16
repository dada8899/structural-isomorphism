"""Actual HTTP/auth/DB/runner/fixture checks for the fixed offline C0 plan."""
from __future__ import annotations

import sqlite3
import json
import multiprocessing
import os
import sys
import time
from uuid import uuid4

import pytest

from .test_research_persistence import stack,problem,post
from .research_http_fixture import ResearchHTTPFixture
from api import auth, favorites, report, report_account
from research import ResearchStore,BudgetLedger,ResearchRunner
from services.report_store import ReportStore
from .test_research_persistence import login
from fastapi.testclient import TestClient


@pytest.fixture
def c0(stack,tmp_path,monkeypatch):
    client,path=stack
    monkeypatch.setenv("STRUCTURAL_C0_ENABLED","true")
    monkeypatch.setattr(report_account,"_store",ReportStore(tmp_path/"legacy-history.db"))
    monkeypatch.setattr(report,"_store",report_account._store)
    monkeypatch.setattr(favorites,"_legacy_data_file",lambda:tmp_path/"unused-legacy.jsonl")
    fixture=ResearchHTTPFixture(tmp_path/"provider.sqlite3")
    store=ResearchStore(auth._store())
    BudgetLedger(store).provision_fixture(fixture.port)
    try:yield client,path,store,fixture
    finally:fixture.close()


def start(client,key="c0-create"):
    p=problem();p["confirmed"]=True
    created=post(client,"/api/research",{"problem":p},key)
    assert created.status_code==200,created.text
    rid=created.json()["data"]["research"]["id"]
    response=post(client,f"/api/research/{rid}/tasks",{"input_revision":1,"expected_research_version":1,"mode":"research"},key+"-start")
    assert response.status_code==200,response.text
    return rid,response.json()["data"]["task"]["id"]


def view(client,rid):
    response=client.get(f"/api/research/{rid}")
    assert response.status_code==200,response.text
    return response.json()["data"]


def action(client,rid,operation,key=None):
    current=view(client,rid)
    return post(client,f"/api/research/{rid}/{operation}",{"task_id":current["task"]["id"],"expected_task_version":current["task_version"]},key or str(uuid4()))


def test_normal_actual_two_consumers_accounting_and_reopen(c0):
    client,path,store,fixture=c0
    rid,tid=start(client)
    assert view(client,rid)["execution"]=="QUEUED"
    assert ResearchRunner(store).run_once(tid)=="COMPLETED"
    data=view(client,rid)
    assert data["status"]=="insufficient" and data["evidence"]=="INSUFFICIENT"
    assert data["execution_mode"]=="offline_probe" and data["report_status"]=="notes"
    assert len(data["notes"])==2
    assert data["budget"]["known_cost"][0]["amount_units"]==7000
    assert data["budget"]["held_cost"][0]["amount_units"]==0
    assert fixture.count()==2
    assert ResearchRunner(ResearchStore(auth._store())).run_once(tid)=="COMPLETED"
    assert fixture.count()==2
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT settled,held FROM research_funding_accounts").fetchone()==(7000,0)
        assert conn.execute("SELECT count(*) FROM research_billing_receipts").fetchone()[0]==2
    events=client.get(f"/api/research/{rid}/events?task_id={tid}").json()["data"]["items"]
    assert [e["seq"] for e in events]==list(range(1,len(events)+1))


@pytest.mark.parametrize("prepared",[False,True])
def test_cancel_before_send_never_calls_fixture_and_releases_only_unsent(c0,prepared):
    client,path,store,fixture=c0
    rid,tid=start(client)
    if prepared:
        ResearchRunner(store).prepare(tid)
        assert view(client,rid)["budget"]["held_cost"][0]["amount_units"]==7000
    response=action(client,rid,"cancel","cancel-once")
    assert response.status_code==200,response.text
    assert view(client,rid)["execution"]=="CANCELLED"
    assert view(client,rid)["budget"]["held_cost"][0]["amount_units"]==0
    assert ResearchRunner(store).run_once(tid)=="CANCELLED" and fixture.count()==0
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT held FROM research_funding_accounts").fetchone()[0]==0


@pytest.mark.parametrize("cancelled",[False,True])
def test_lost_receipt_restart_reconcile_cancelled_vs_legal_resume(c0,cancelled):
    client,path,store,fixture=c0
    rid,tid=start(client)
    fixture.drop.add("discover_sources")
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    data=view(client,rid)
    assert data["budget"]["held_cost"][0]["amount_units"]==7000
    assert data["budget"]["known_cost"][0]["amount_units"]==0 and fixture.count()==1
    if cancelled:assert action(client,rid,"cancel").status_code==200
    assert ResearchRunner(ResearchStore(auth._store())).run_once(tid)==("CANCELLED" if cancelled else "RECONCILING")
    assert fixture.count()==1
    assert action(client,rid,"reconcile").status_code==200
    result=ResearchRunner(ResearchStore(auth._store())).run_once(tid)
    assert result==("CANCELLED" if cancelled else "COMPLETED")
    data=view(client,rid)
    assert data["budget"]["held_cost"][0]["amount_units"]==0
    assert data["budget"]["known_cost"][0]["amount_units"]==(4000 if cancelled else 7000)
    assert len(data["notes"])==(0 if cancelled else 2)
    assert fixture.count()==(1 if cancelled else 2)
    with sqlite3.connect(path) as conn:
        step=conn.execute("SELECT s.id,p.dispatch_id FROM research_steps s JOIN research_dispatch_permits p ON p.step_id=s.id WHERE s.task_id=? ORDER BY s.position LIMIT 1",(tid,)).fetchone()
    assert BudgetLedger(store).settle(step[0],fixture.receipt(step[1])) is True
    assert view(client,rid)["budget"]["known_cost"][0]["amount_units"]==(4000 if cancelled else 7000)


def _run_worker(task_id,result,ready=None,go=None,one=False,crash=False,before_send=None,send_release=None,sent=None):
    if ready:ready.put(True)
    if go and not go.wait(15):return
    runner=ResearchRunner(ResearchStore(auth._store()))
    if crash or before_send is not None or sent is not None:
        original=ResearchRunner.send
        def controlled(self,*args,**kwargs):
            if before_send is not None:
                before_send.set()
                if not send_release.wait(15):raise RuntimeError("send barrier expired")
            connection=original(self,*args,**kwargs)
            if sent is not None:sent.set()
            if crash is True:os._exit(76)
            return connection
        ResearchRunner.send=controlled
    if crash=="after-settlement":
        ResearchRunner.commit_result=lambda *args,**kwargs:os._exit(77)
    try:result.put(runner.run_next(task_id) if one else runner.run_once(task_id))
    except Exception as exc:result.put(type(exc).__name__)


def _finish(processes,*queues):
    for process in processes:
        process.join(5)
        if process.is_alive():process.terminate();process.join(5)
    for queue in queues:queue.close()


def test_actual_worker_exit_and_new_process_does_not_replay_sent_request(c0):
    client,path,store,fixture=c0
    rid,tid=start(client)
    context=multiprocessing.get_context("spawn");result=context.Queue()
    worker=context.Process(target=_run_worker,args=(tid,result,None,None,False,True))
    worker.start()
    try:
        worker.join(15);assert worker.exitcode==76
        assert fixture.received.wait(3) and fixture.count()==1
        assert ResearchRunner(ResearchStore(auth._store())).run_once(tid)=="RECONCILING"
        assert fixture.count()==1 and view(client,rid)["budget"]["held_cost"][0]["amount_units"]==7000
        assert action(client,rid,"reconcile").status_code==200
        restarted=context.Process(target=_run_worker,args=(tid,result));restarted.start()
        try:assert result.get(timeout=15)=="COMPLETED"
        finally:_finish([restarted])
        assert fixture.count()==2
        assert view(client,rid)["budget"]["known_cost"][0]["amount_units"]==7000
    finally:_finish([worker],result)


def test_two_workers_same_task_call_two_consumers_only_once(c0):
    client,_,_,fixture=c0
    rid,tid=start(client)
    context=multiprocessing.get_context("spawn");result=context.Queue();ready=context.Queue();go=context.Event()
    workers=[context.Process(target=_run_worker,args=(tid,result,ready,go)) for _ in range(2)]
    try:
        for process in workers:process.start()
        assert ready.get(timeout=15) and ready.get(timeout=15);go.set()
        assert [result.get(timeout=15),result.get(timeout=15)]==["COMPLETED","COMPLETED"]
        assert fixture.count()==2
        assert view(client,rid)["budget"]["known_cost"][0]["amount_units"]==7000
    finally:go.set();_finish(workers,result,ready)


def test_two_real_consumers_race_for_one_shared_account(c0):
    client,path,store,fixture=c0
    fixture.costs["discover_sources"]=0
    rb,tb=start(client,"race-b")
    assert ResearchRunner(store).run_next(tb)=="RUNNING" and fixture.count()==1
    ra,ta=start(client,"race-a")
    fixture.received.clear();fixture.release.clear()
    context=multiprocessing.get_context("spawn");result=context.Queue();ready=context.Queue();go=context.Event()
    workers=[context.Process(target=_run_worker,args=(tid,result,ready,go,True)) for tid in (ta,tb)]
    try:
        for process in workers:process.start()
        assert ready.get(timeout=15) and ready.get(timeout=15);go.set()
        assert fixture.received.wait(5)
        assert result.get(timeout=5)=="WAITING_EXTERNAL"
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT held FROM research_funding_accounts").fetchone()[0] in (5000,7000)
            assert conn.execute("SELECT count(*) FROM research_reservations WHERE status IN ('HELD','SENT','UNKNOWN')").fetchone()[0]==1
        assert fixture.count()==2
        fixture.release.set()
        assert result.get(timeout=10) in ("RUNNING","COMPLETED")
    finally:fixture.release.set();go.set();_finish(workers,result,ready)


def test_inflight_delete_keeps_fee_receipt_but_no_recreated_research(c0):
    client,path,store,fixture=c0
    rid,tid=start(client)
    fixture.drop.add("discover_sources")
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    deleted=client.post("/api/me/delete",json={"confirmation":"DELETE"},headers={"Origin":"http://testserver"})
    assert deleted.status_code==200,deleted.text
    assert ResearchRunner(ResearchStore(auth._store())).run_once(tid)=="ACCESS_REVOKED"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT settled,held FROM research_funding_accounts").fetchone()==(4000,0)
        assert conn.execute("SELECT count(*) FROM research_revisions").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_step_outputs").fetchone()[0]==0
        assert conn.execute("SELECT research_id,auth_generation,input_digest FROM research_tasks WHERE id=?",(tid,)).fetchone()==(None,None,None)
    assert fixture.count()==1
    assert client.get(f"/api/research/{rid}").status_code==401


@pytest.mark.parametrize("send_first",[False,True])
def test_cancel_and_real_transport_start_are_ordered_without_waiting_response(c0,send_first):
    client,_,store,fixture=c0
    rid,tid=start(client)
    context=multiprocessing.get_context("spawn");result=context.Queue()
    before,release,sent=context.Event(),context.Event(),context.Event()
    if send_first:fixture.release.clear()
    worker=context.Process(target=_run_worker,args=(tid,result,None,None,False,False,None if send_first else before,release,sent if send_first else None))
    worker.start()
    try:
        assert (sent if send_first else before).wait(10)
        assert view(client,rid)["budget"]["held_cost"][0]["amount_units"]==7000
        response=action(client,rid,"cancel")
        assert response.status_code==200,response.text
        assert view(client,rid)["execution"]=="CANCELLED"
        assert fixture.count()==(1 if send_first else 0)
        if send_first:
            assert view(client,rid)["budget"]["held_cost"][0]["amount_units"]==7000
            fixture.release.set()
        else:release.set()
        assert result.get(timeout=10)=="CANCELLED"
        assert view(client,rid)["budget"]["held_cost"][0]["amount_units"]==0
        assert view(client,rid).get("notes",[])==[]
        assert fixture.count()==(1 if send_first else 0)
    finally:release.set();fixture.release.set();_finish([worker],result)


def test_nonfinal_is_not_free_then_distinct_final_receipt_settles_once(c0):
    client,_,store,fixture=c0
    rid,tid=start(client);fixture.final=False
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    data=view(client,rid)
    assert data["budget"]["known_cost"][0]["amount_units"]==0
    assert data["budget"]["held_cost"][0]["amount_units"]==7000 and data["notes"]==[]
    with store.transaction() as conn:dispatch=conn.execute("SELECT dispatch_id FROM research_dispatch_permits").fetchone()[0]
    fixture.change_receipt(dispatch,final=True,receipt_ref="final-"+dispatch)
    fixture.final=True
    assert action(client,rid,"reconcile").status_code==200
    assert ResearchRunner(store).run_once(tid)=="COMPLETED"
    assert fixture.count()==2 and view(client,rid)["budget"]["known_cost"][0]["amount_units"]==7000


@pytest.mark.parametrize("invalid",[True,1.5,-1,9223372036854775808])
def test_invalid_provider_money_stays_unknown_and_never_retries(c0,invalid):
    client,_,store,fixture=c0
    rid,tid=start(client);fixture.costs["discover_sources"]=invalid
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    assert fixture.count()==1
    data=view(client,rid)
    assert data["budget"]["known_cost"][0]["amount_units"]==0
    assert data["budget"]["held_cost"][0]["amount_units"]==7000
    assert data["notes"]==[]
    assert ResearchRunner(store).run_once(tid)=="RECONCILING" and fixture.count()==1


def test_fee_over_reservation_is_preserved_and_blocks_next_consumer(c0):
    client,path,store,fixture=c0
    rid,tid=start(client);fixture.costs["discover_sources"]=12000
    assert ResearchRunner(store).run_once(tid)=="WAITING_EXTERNAL"
    assert fixture.count()==1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT settled,held,status FROM research_funding_accounts").fetchone()==(12000,0,"blocked")
        assert conn.execute("SELECT cost FROM research_billing_receipts").fetchone()[0]==12000
    assert view(client,rid)["budget"]["anomaly"] is True


@pytest.mark.parametrize("expired",["snapshot","price"])
def test_expired_snapshot_or_price_blocks_before_http(stack,tmp_path,monkeypatch,expired):
    client,_=stack;monkeypatch.setenv("STRUCTURAL_C0_ENABLED","true")
    fixture=ResearchHTTPFixture(tmp_path/"provider.sqlite3")
    try:
        store=ResearchStore(auth._store())
        BudgetLedger(store).provision_fixture(fixture.port,ttl_seconds=-1 if expired=="snapshot" else 60,price_ttl_seconds=-1 if expired=="price" else 60)
        rid,tid=start(client)
        assert ResearchRunner(store).run_once(tid)=="WAITING_EXTERNAL"
        assert fixture.count()==0 and view(client,rid)["detail"]=="budget_unverified"
    finally:fixture.close()


def test_task_start_and_cancellation_idempotency_and_untrusted_fields(c0):
    client,_,store,fixture=c0
    rid,tid=start(client)
    original={"input_revision":1,"expected_research_version":1,"mode":"research"}
    replay=post(client,f"/api/research/{rid}/tasks",original,"c0-create-start")
    assert replay.status_code==200 and replay.json()["data"]["task"]["id"]==tid
    for field,value in (("provider_url","http://example.invalid"),("cost",0),("execution","COMPLETED")):
        bad=post(client,f"/api/research/{rid}/tasks",{**original,field:value})
        assert bad.status_code==422
    current=view(client,rid)
    body={"task_id":tid,"expected_task_version":current["task_version"]}
    first=post(client,f"/api/research/{rid}/cancel",body,"cancel")
    assert first.status_code==200
    assert post(client,f"/api/research/{rid}/cancel",body,"cancel").json()==first.json()
    assert fixture.count()==0


def test_task_revision_binding_and_original_cookie_revocation(c0):
    client,_,store,fixture=c0
    rid,tid=start(client)
    changed=post(client,f"/api/research/{rid}/revisions",{"expected_revision":1,"problem":problem("新的已保存问题")})
    assert changed.status_code==200
    current=view(client,rid)
    assert current["task"] is None and current["other_active_task_id"]==tid
    assert ResearchRunner(store).run_once(tid)=="COMPLETED"
    assert view(client,rid)["task"] is None
    historic=client.get(f"/api/research/{rid}?task_id={tid}").json()["data"]
    assert historic["is_historical"] is True and historic["current_problem"]["revision"]==1
    assert historic["research"]["current_revision"]==2
    cookie=client.cookies.get("phase_session")
    client.post("/api/auth/logout",headers={"Origin":"http://testserver"})
    client.cookies.set("phase_session",cookie)
    assert client.get(f"/api/research/{rid}?task_id={tid}").status_code==401


def test_background_grant_is_not_the_logged_out_browser_jti(c0):
    client,_,store,fixture=c0
    rid,tid=start(client)
    client.post("/api/auth/logout",headers={"Origin":"http://testserver"})
    assert ResearchRunner(store).run_once(tid)=="COMPLETED" and fixture.count()==2
    client.cookies.clear();login(client)
    assert view(client,rid)["execution"]=="COMPLETED"


@pytest.mark.parametrize("field,value",[("currency","CNY"),("scale",3),("scale",True)])
def test_receipt_money_cannot_change_currency_or_scale(c0,field,value):
    client,_,store,fixture=c0
    rid,tid=start(client);setattr(fixture,field,value)
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    assert view(client,rid)["budget"]["held_cost"][0]["amount_units"]==7000
    assert fixture.count()==1


def test_final_without_fee_is_unknown_not_zero(c0):
    client,_,store,fixture=c0
    rid,tid=start(client);fixture.costs["discover_sources"]=None
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    data=view(client,rid)
    assert data["budget"]["known_cost"][0]["amount_units"]==0 and data["budget"]["held_cost"][0]["amount_units"]==7000
    assert data["budget"]["unknown_count"]==1 and data["notes"]==[]


def test_bill_aggregation_overflow_retains_actual_receipt_and_blocks(c0):
    client,path,store,fixture=c0
    rid,tid=start(client);fixture.costs["compose_report"]=9223372036854775807
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT cost,status FROM research_billing_receipts ORDER BY rowid DESC LIMIT 1").fetchone()==(9223372036854775807,"anomaly")
        assert conn.execute("SELECT settled,held,status FROM research_funding_accounts").fetchone()==(4000,5000,"blocked")
    assert view(client,rid)["budget"]["anomaly"] is True and fixture.count()==2


def test_known_fee_missing_output_is_failed_not_fabricated(c0):
    client,_,store,fixture=c0
    rid,tid=start(client);fixture.notes=False
    assert ResearchRunner(store).run_once(tid)=="FAILED"
    data=view(client,rid)
    assert data["notes"]==[] and data["budget"]["known_cost"][0]["amount_units"]==4000
    assert data["budget"]["held_cost"][0]["amount_units"]==0 and fixture.count()==1


def test_unknown_cannot_be_restarted_with_new_key_or_client_fee_claim(c0):
    client,_,store,fixture=c0
    rid,tid=start(client);fixture.drop.add("discover_sources")
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    assert action(client,rid,"cancel").status_code==200
    current=view(client,rid)
    retried=post(client,f"/api/research/{rid}/tasks",{"input_revision":1,"expected_research_version":current["research_version"],"mode":"research"})
    assert retried.status_code==409
    bad=post(client,f"/api/research/{rid}/reconcile",{"task_id":tid,"expected_task_version":current["task_version"],"cost":0,"final":True})
    assert bad.status_code==422 and fixture.count()==1


def test_budget_and_events_are_private_per_task_not_account(c0):
    client,_,store,fixture=c0
    rid,tid=start(client)
    ResearchRunner(store).prepare(tid)
    with TestClient(client.app) as other:
        login(other,"c0-other@example.test")
        assert other.get(f"/api/research/{rid}").status_code==404
        assert other.get(f"/api/research/{rid}/events?task_id={tid}").status_code==404
        ro,to=start(other,"other-task")
        data=view(other,ro)
        assert data["budget"]["held_cost"][0]["amount_units"]==0
        assert "fixture_port" not in json.dumps(data) and "binding_id" not in json.dumps(data) and "cap" not in data["budget"]


def test_exact_rounding_and_price_overflow_are_rejected_before_send(c0):
    from research.budget import max_cost
    from research.errors import ResearchError
    price={"input_rate":1,"output_rate":1,"max_input":1,"max_output":1,"fixed_units":0,"rounding":"ceil_total"}
    assert max_cost(price)==1
    assert max_cost({**price,"rounding":"ceil_components"})==2
    with pytest.raises(ResearchError):max_cost({**price,"input_rate":9223372036854775807,"max_input":9223372036854775807})


def test_explicit_execution_grant_revocation_blocks_without_browser_session_dependency(c0):
    client,path,store,fixture=c0
    rid,tid=start(client)
    with store.transaction(write=True) as conn:
        conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(tid,))
    assert ResearchRunner(store).run_once(tid)=="ACCESS_REVOKED" and fixture.count()==0
    assert view(client,rid)["execution"]=="ACCESS_REVOKED"


def test_slow_byte_stream_has_absolute_bound_and_keeps_unknown_reservation(c0):
    client,_,store,fixture=c0
    rid,tid=start(client);fixture.drip_delay=.03
    began=time.monotonic()
    assert ResearchRunner(store).run_once(tid)=="RECONCILING"
    assert time.monotonic()-began<8
    assert fixture.count()==1 and view(client,rid)["budget"]["held_cost"][0]["amount_units"]==7000


def test_bounded_worker_selection_does_not_treat_unrequested_unknown_as_new_work(c0):
    client,_,store,fixture=c0
    first,old=start(client,"first-selection");fixture.drop.add("discover_sources")
    assert ResearchRunner(store).run_once(old)=="RECONCILING"
    second,new=start(client,"second-selection")
    assert ResearchRunner(store).run_once()=="WAITING_EXTERNAL"
    assert view(client,second)["execution"]=="WAITING_EXTERNAL"
    assert view(client,first)["execution"]=="RECONCILING" and fixture.count()==1
    assert ResearchRunner(store).run_once()=="idle"


def test_balance_drop_after_prepare_is_rechecked_before_transport(c0):
    from research.budget import now,expires
    client,path,store,fixture=c0
    rid,tid=start(client)
    ResearchRunner(store).prepare(tid)
    with store.transaction(write=True) as conn:
        account=conn.execute("SELECT * FROM research_funding_accounts").fetchone()
        snapshot=str(uuid4())
        conn.execute("INSERT INTO research_balance_snapshots VALUES(?,?,0,0,0,?,?,1,1,1)",(snapshot,account["id"],now(),expires()))
        conn.execute("UPDATE research_funding_accounts SET snapshot_id=? WHERE id=?",(snapshot,account["id"]))
    assert ResearchRunner(store).run_once(tid)=="WAITING_EXTERNAL"
    assert fixture.count()==0 and view(client,rid)["detail"]=="budget_unverified"
    assert "resume" not in view(client,rid)["allowed_next_actions"]
    assert action(client,rid,"cancel").status_code==200
    assert view(client,rid)["budget"]["held_cost"][0]["amount_units"]==0


def test_exit_after_fee_commit_can_recover_output_without_rebilling(c0):
    client,path,store,fixture=c0
    rid,tid=start(client)
    context=multiprocessing.get_context("spawn");result=context.Queue()
    worker=context.Process(target=_run_worker,args=(tid,result,None,None,False,"after-settlement"))
    worker.start()
    try:
        worker.join(15);assert worker.exitcode==77 and fixture.count()==1
        assert ResearchRunner(ResearchStore(auth._store())).run_once(tid)=="RECONCILING"
        data=view(client,rid)
        assert data["budget"]["known_cost"][0]["amount_units"]==4000
        assert data["budget"]["held_cost"][0]["amount_units"]==0 and data["notes"]==[]
        assert "request_reconciliation" in data["allowed_next_actions"]
        assert action(client,rid,"reconcile").status_code==200
        assert ResearchRunner(ResearchStore(auth._store())).run_once(tid)=="COMPLETED"
        assert fixture.count()==2 and view(client,rid)["budget"]["known_cost"][0]["amount_units"]==7000
    finally:_finish([worker],result)


_WORKER_MODULE="web.backend.tests.test_research_c0"
if __name__!=_WORKER_MODULE:
    sys.modules[_WORKER_MODULE]=sys.modules[__name__]
    _run_worker.__module__=_WORKER_MODULE
