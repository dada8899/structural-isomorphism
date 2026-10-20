"""D1 HTTP/auth/database integration with synthetic local-only inputs."""
import sqlite3
from contextlib import closing
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4
from functools import partial

import pytest

from .test_research_persistence import stack,post,problem,app,login
from .test_research_lifecycle import lifecycle
from fastapi.testclient import TestClient
from web.backend.tests.source_http_fixture import source_server,get_local,get_local_targets,drop_after_response,ARTICLE,METADATA,DOI,TITLE
from research.source_policy import PinnedPublicTransport
from research.runner import ResearchRunner
from research.store import ResearchStore
from api import auth
from .test_research_c0 import c0,start as c0_start
from .d1_legacy_history_fixture import legacy_source_history,execution_snapshot
from research.store import C0_SCHEMA
from research.authorization import AuthorizationGate
from research.errors import ResearchError


def start_current(client,rid,query="queue theory"):
    current=client.get(f"/api/research/{rid}").json()["data"]
    payload={"input_revision":current["current_problem"]["revision"],"expected_research_version":current["research_version"],"query":query}
    viewed=post(client,f"/api/research/{rid}/source-preview",payload)
    assert viewed.status_code==200,viewed.text
    approved=post(client,f"/api/research/{rid}/source-approvals",{**payload,"preview_digest":viewed.json()["data"]["preview_digest"],"confirm_external":True})
    assert approved.status_code==200,approved.text
    return post(client,f"/api/research/{rid}/source-tasks",{key:payload[key] for key in ("input_revision","expected_research_version")}|{"approval_ref":approved.json()["data"]["approval_ref"]})


@pytest.fixture
def source_stack(stack,monkeypatch):
    monkeypatch.setenv("STRUCTURAL_D1_SOURCES_ENABLED","true")
    monkeypatch.setenv("STRUCTURAL_D1_PUBLIC_GET_ENABLED","false")
    client,path=stack
    saved=problem();saved["confirmed"]=True
    created=post(client,"/api/research",{"problem":saved},"source-create")
    assert created.status_code==200,created.text
    rid=created.json()["data"]["research"]["id"]
    yield client,path,rid


def preview(client,rid):
    payload={"input_revision":1,"expected_research_version":1,"query":"queue theory"}
    response=post(client,f"/api/research/{rid}/source-preview",payload,"preview")
    assert response.status_code==200,response.text
    return payload,response.json()["data"]


def start(client,rid):
    payload,view=preview(client,rid)
    approved=post(client,f"/api/research/{rid}/source-approvals",{**payload,"preview_digest":view["preview_digest"],"confirm_external":True},"approve-source")
    assert approved.status_code==200,approved.text
    response=post(client,f"/api/research/{rid}/source-tasks",{"input_revision":1,"expected_research_version":1,"approval_ref":approved.json()["data"]["approval_ref"]},"start-source")
    assert response.status_code==200,response.text
    return response.json()["data"]["task"]["id"]


def test_real_local_http_worker_persists_exact_licensed_evidence(source_stack):
    client,path,rid=source_stack
    tid=start(client,rid)
    with source_server() as (port,calls):
        transport=PinnedPublicTransport(_worker=partial(get_local,port))
        runner=ResearchRunner(ResearchStore(auth._store()),source_transport=transport)
        assert runner.run_once(tid)=="COMPLETED"
        assert calls==["/discovery","/article"]
        assert runner.run_once(tid)=="COMPLETED"
        assert calls==["/discovery","/article"]
    view=client.get(f"/api/research/{rid}").json()["data"]
    assert view["evidence"]=="INSUFFICIENT" and view["execution_mode"]=="offline_probe"
    assert view["model_analysis_ran"] is view["statistics_ran"] is False
    assert view["source_quota"]["used"]==2 and "budget" not in view
    for kind in ("sources","excerpts","claims","reports"):
        response=client.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":kind})
        assert response.status_code==200,response.text
        assert len(response.json()["data"]["items"])==1
        assert not any(key in response.text for key in ('"raw":','"extracted":','"discovery":','"plan_json":'))
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT count(*) FROM research_funding_accounts").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_source_requests WHERE outcome='SUCCEEDED'").fetchone()[0]==2
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]


@pytest.mark.parametrize("scenario",["no-hits","unknown-permission","extra-metadata","oversized-body"])
def test_incomplete_sources_cannot_become_research_results(source_stack,scenario):
    client,path,rid=source_stack;tid=start(client,rid)
    metadata=json.loads(METADATA)
    article=ARTICLE
    if scenario=="no-hits":metadata["message"]["items"]=[]
    if scenario=="unknown-permission":article=ARTICLE.replace(b"permits unrestricted use",b"does not grant unrestricted use")
    if scenario=="extra-metadata":metadata["message"]["items"][0]["abstract"]="UNLICENSED-SYNTHETIC-CANARY"
    if scenario=="oversized-body":article=b"x"*2097153
    with source_server(metadata=json.dumps(metadata).encode(),article=article) as (port,calls):
        result=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)
    assert result==("COMPLETED" if scenario=="no-hits" else "FAILED")
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT count(*) FROM research_evidence_objects WHERE kind IN ('snapshots','excerpts','claims','reports')").fetchone()[0]==0
        assert conn.execute("SELECT used FROM research_source_chains").fetchone()[0]==len(calls)
        assert conn.execute("SELECT count(*) FROM research_source_requests WHERE outcome='UNKNOWN' AND execution_closed=0").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_funding_accounts").fetchone()[0]==0
    assert client.get(f"/api/research/{rid}").json()["data"]["evidence"]=="INSUFFICIENT"


def test_unknown_closure_preserves_original_observation_and_new_approval_uses_same_quota(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    with source_server() as (port,calls):
        runner=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(drop_after_response,port)))
        assert runner.run_once(tid)=="FAILED" and calls==["/discovery"]
        with closing(sqlite3.connect(path)) as conn,conn:
            conn.row_factory=sqlite3.Row
            old=dict(conn.execute("SELECT * FROM research_source_requests").fetchone())
            assert old["outcome"]=="UNKNOWN" and old["execution_closed"]==1 and old["closure_ref"]
            assert json.loads(old["closure_proof"])["proof_version"]==1
            assert conn.execute("SELECT used FROM research_source_chains").fetchone()[0]==1
        restarted=start_current(client,rid)
        assert restarted.status_code==200,restarted.text
        two=restarted.json()["data"]["task"]["id"]
        good=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port)))
        assert good.run_once(two)=="COMPLETED"
        with closing(sqlite3.connect(path)) as conn,conn:
            conn.row_factory=sqlite3.Row
            assert dict(conn.execute("SELECT * FROM research_source_requests WHERE id=?",(old["id"],)).fetchone())==old
            assert conn.execute("SELECT count(*) FROM research_source_chains").fetchone()[0]==1
            assert conn.execute("SELECT used FROM research_source_chains").fetchone()[0]==3
            latest=conn.execute("SELECT prior_dispatch_id,started_at FROM research_source_requests WHERE task_id=? AND semantic='discover_sources'",(two,)).fetchone()
            assert latest["prior_dispatch_id"]==old["dispatch_id"] and latest["started_at"]>old["started_at"]
        # Same normalized operation cannot buy a fresh quota through new keys.
        third=start_current(client,rid,"Queue  Theory")
        assert third.status_code==200,third.text
        assert good.run_once(third.json()["data"]["task"]["id"])=="FAILED"
        assert calls==["/discovery","/discovery","/article","/discovery"]
        exhausted=start_current(client,rid)
        assert exhausted.status_code==429,exhausted.text


def test_cancel_before_worker_has_no_get_or_evidence(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    view=client.get(f"/api/research/{rid}").json()["data"]
    cancelled=post(client,f"/api/research/{rid}/cancel",{"task_id":tid,"expected_task_version":view["task_version"]})
    assert cancelled.status_code==200,cancelled.text
    with source_server() as (port,calls):
        runner=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port)))
        assert runner.run_once(tid)=="CANCELLED" and calls==[]
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT used FROM research_source_chains").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_evidence_objects WHERE kind!='plans'").fetchone()[0]==0


def test_local_problem_revision_does_not_reset_same_outbound_query_quota(source_stack):
    client,path,rid=source_stack
    with source_server() as (port,calls):
        runner=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port)))
        for _ in range(2):
            response=start_current(client,rid)
            assert response.status_code==200,response.text
            assert runner.run_once(response.json()["data"]["task"]["id"])=="COMPLETED"
        assert len(calls)==4
        changed=problem();changed.update(confirmed=True,summary="仅修改未对外发送的问题摘要，其余查询保持一致")
        revised=post(client,f"/api/research/{rid}/revisions",{"expected_revision":1,"problem":changed})
        assert revised.status_code==200,revised.text
        refused=start_current(client,rid)
        assert refused.status_code==429,refused.text
        assert len(calls)==4
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT count(*),sum(used) FROM research_source_chains").fetchone()==(1,4)


def test_legacy_problem_fingerprinted_chains_are_grouped_without_quota_reset(tmp_path,monkeypatch):
    """R10 grouping exhausts quota; R11 keeps unproved legacy chains read-only."""
    with legacy_source_history(tmp_path,monkeypatch,"quota") as (client,path,history):
        rid=history["rid"]
        calls=history["first_calls"]+history["second_calls"]
        assert calls==["/discovery","/article","/discovery","/article"]
        view=client.get(f"/api/research/{rid}").json()["data"]
        assert view["source_quota"]["used"]==4
        before=execution_snapshot()
        with source_server() as (_port,new_calls):
            refused=start_current(client,rid)
            assert refused.status_code==409 and refused.json()["error"]["code"]=="RECONCILIATION_REQUIRED",refused.text
            assert new_calls==[] and len(calls)==4
        assert execution_snapshot()==before
        assert client.get(f"/api/research/{rid}").json()["data"]["source_quota"]["used"]==4


def test_public_source_versions_resolve_every_excerpt_and_report_reference(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    with source_server() as (port,_):
        assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=="COMPLETED"
    records={kind:client.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":kind}).json()["data"]["items"] for kind in ("sources","excerpts","claims","reports")}
    sources={(s["id"],s["revision"]):s for s in records["sources"]}
    assert len(sources)==1
    for excerpt in records["excerpts"]:
        source=sources[(excerpt["source_id"],excerpt["source_revision"])]
        assert excerpt["text_digest"]==source["extracted_text_digest"]
    for report in records["reports"]:
        assert all((ref["source_id"],ref["revision"]) in sources for ref in report["source_revisions"])
        assert all(ref in {c["id"] for c in records["claims"]} for ref in report["claim_ids"])
        assert all(ref["content_digest"]==sources[(ref["source_id"],ref["revision"])]["content_digest"] for ref in report["source_revisions"])
        assert report["created_at"] and len(report["digest"])==64
    with closing(sqlite3.connect(path)) as conn,conn:
        internal,sid,revision=conn.execute("SELECT id,json_extract(payload,'$.source_id'),json_extract(payload,'$.source_revision') FROM research_evidence_objects WHERE kind='snapshots'").fetchone()
    assert (sid,revision) in sources and internal!=sid
    public=json.dumps(records)
    assert internal not in public
    assert '"snapshot_id"' not in public and '"execution_refs"' not in public and '"snapshot_refs"' not in public


def test_public_sources_use_exact_whitelist_without_provider_reference(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    with source_server() as (port,_):
        assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=="COMPLETED"
    response=client.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":"sources"})
    assert response.status_code==200,response.text
    item,=response.json()["data"]["items"]
    assert set(item)=={"id","kind","research_id","task_id","input_revision","title","canonical_url","access","revision",
        "authors","published_at","accessed_at","retrieval_scope","content_digest","extracted_text_digest","extractor_version",
        "license_note","failure_code","execution_mode","read_scope"}
    assert '"provider_ref"' not in response.text and item["canonical_url"].startswith("https://journals.plos.org/")


def test_v2_narrative_scope_keeps_raw_and_exact_excerpt_separate(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    original=b'<p>Waiting time depends on arrivals and service variability.</p>'
    author='<p>反馈 f<span>eed</span>back links <a class="reference" href="#r1">[1]</a> to 作者叙述。</p>'.encode()
    foreign=(b'<div class="comments">FOREIGN_COMMENT</div><blockquote>FOREIGN_QUOTE</blockquote>'
             b'<span class="quoted-other">FOREIGN_OTHER</span><ol class="references"><li>FOREIGN_REF</li></ol>')
    article=ARTICLE.replace(b'<html>',b'<html><nav>FOREIGN_NAV</nav>').replace(original,foreign+author)
    with source_server(article=article) as (port,calls):
        assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=="COMPLETED"
        assert calls==["/discovery","/article"]
    data={kind:client.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":kind}).json()["data"]["items"]
          for kind in ("sources","excerpts","reports")}
    source,=data["sources"];excerpt,=data["excerpts"];report,=data["reports"]
    assert source["read_scope"]=="author_narrative_subset"
    assert source["extractor_version"]=="plos-author-narrative-subset-v2"
    ref,=report["source_revisions"]
    assert set(ref)=={"source_id","revision","content_digest","access","read_scope"}
    assert ref["read_scope"]==source["read_scope"]
    assert (ref["source_id"],ref["revision"],ref["content_digest"])==(source["id"],source["revision"],source["content_digest"])
    with closing(sqlite3.connect(path)) as conn,conn:
        payload,payload_digest,raw,extracted=conn.execute(
            "SELECT payload,payload_digest,raw,extracted FROM research_evidence_objects WHERE task_id=? AND kind='snapshots'",(tid,)).fetchone()
    assert raw==article and source["content_digest"]==hashlib.sha256(raw).hexdigest()
    assert extracted=="反馈 feedback links [1] to 作者叙述。"
    assert hashlib.sha256(payload.encode()).hexdigest()==payload_digest
    assert "read_scope" not in json.loads(payload)
    assert source["extracted_text_digest"]==hashlib.sha256(extracted.encode()).hexdigest()
    assert excerpt["start"]==0 and excerpt["end"]==len(excerpt["quote"])
    assert excerpt["quote"]==extracted[excerpt["start"]:excerpt["end"]] and len(excerpt["quote"].split())<=20
    for marker in (b'FOREIGN_NAV',b'FOREIGN_COMMENT',b'FOREIGN_QUOTE',b'FOREIGN_OTHER',b'FOREIGN_REF'):
        assert marker in raw and marker.decode() not in extracted and marker.decode() not in excerpt["quote"]
    assert not any(key in json.dumps(data) for key in ('"raw":','"extracted":','"discovery":','"provider_ref":','"snapshot_id":'))
    assert report["model_analysis_ran"] is report["statistics_ran"] is False


def test_legacy_snapshot_stays_immutable_when_new_v2_source_is_added(source_stack,monkeypatch):
    from dataclasses import replace
    import re
    from research.source_adapters.crossref_plos import CrossrefPlosChain
    from research.evidence_schemas import encode,decode

    client,path,rid=source_stack;first=start(client,rid)
    original_fetch=CrossrefPlosChain.fetch
    legacy_raw=ARTICLE.replace(b'<html>',b'<html><nav>Legacy navigation.</nav>')
    legacy_text="Legacy navigation. "+" ".join(re.findall(r'<p>(.*?)</p>',ARTICLE.decode()))
    def historical_fetch(chain,doi):
        snapshot,raw,_=original_fetch(chain,doi)
        old=replace(snapshot,parser_version="plos-html-text-v1",extracted_digest=hashlib.sha256(legacy_text.encode()).hexdigest())
        assert decode("snapshots",encode(old))==old
        with pytest.raises(ValueError):replace(old,parser_version="unregistered-parser")
        return old,raw,legacy_text
    with source_server(article=legacy_raw) as (port,_):
        monkeypatch.setattr(CrossrefPlosChain,"fetch",historical_fetch)
        assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(first)=="COMPLETED"
    old_public={kind:client.get(f"/api/research/{rid}/records",params={"task_id":first,"kind":kind}).json()["data"]["items"]
                for kind in ("sources","excerpts","reports")}
    assert old_public["sources"][0]["read_scope"]=="legacy_page_unverified"
    assert old_public["reports"][0]["source_revisions"][0]["read_scope"]=="legacy_page_unverified"
    with closing(sqlite3.connect(path)) as conn,conn:
        old_rows=conn.execute("SELECT * FROM research_evidence_objects WHERE task_id=? ORDER BY id",(first,)).fetchall()
    monkeypatch.setattr(CrossrefPlosChain,"fetch",original_fetch)
    next_task=start_current(client,rid)
    assert next_task.status_code==200,next_task.text
    second=next_task.json()["data"]["task"]["id"]
    with source_server() as (port,_):
        assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(second)=="COMPLETED"
    new_public=client.get(f"/api/research/{rid}/records",params={"task_id":second,"kind":"sources"}).json()["data"]["items"][0]
    assert new_public["read_scope"]=="author_narrative_subset" and new_public["id"]!=old_public["sources"][0]["id"]
    assert new_public["extractor_version"]=="plos-author-narrative-subset-v2"
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT * FROM research_evidence_objects WHERE task_id=? ORDER BY id",(first,)).fetchall()==old_rows
        stored=json.loads(conn.execute("SELECT payload FROM research_evidence_objects WHERE task_id=? AND kind='snapshots'",(second,)).fetchone()[0])
        assert decode("snapshots",json.dumps(stored)).parser_version=="plos-author-narrative-subset-v2"
    for kind,items in old_public.items():
        assert client.get(f"/api/research/{rid}/records",params={"task_id":first,"kind":kind}).json()["data"]["items"]==items
    assert old_public["reports"][0]["model_analysis_ran"] is old_public["reports"][0]["statistics_ran"] is False


def test_new_observation_links_closed_unknown_in_nonselected_compatible_chain(tmp_path,monkeypatch):
    """R10 links UNKNOWN observations; R11 preserves them without execution proof."""
    with legacy_source_history(tmp_path,monkeypatch,"unknown") as (client,path,history):
        rid=history["rid"];chosen=history["chosen"];other=history["other"];unknown=history["unknown"]
        assert history["first_calls"]==["/discovery"]
        assert history["second_calls"]+history["third_calls"]==["/discovery","/discovery","/article"]
        assert unknown["outcome"]=="UNKNOWN" and unknown["execution_closed"]==1
        # These exact R10 rows survive actual R11 maintenance and current login.
        with closing(sqlite3.connect(path)) as conn:
            conn.row_factory=sqlite3.Row
            current=conn.execute("SELECT r.chain_id,r.prior_dispatch_id,r.started_at FROM research_source_requests r WHERE task_id=? AND semantic='discover_sources'",(history["third"],)).fetchone()
            assert current["chain_id"]==chosen and unknown["chain_id"]==other
            assert current["prior_dispatch_id"]==unknown["dispatch_id"] and current["started_at"]>unknown["started_at"]
            assert dict(conn.execute("SELECT * FROM research_source_requests WHERE id=?",(unknown["id"],)).fetchone())==unknown
            assert conn.execute("SELECT sum(used) FROM research_source_chains").fetchone()[0]==4
        before=execution_snapshot()
        with source_server() as (_port,calls):
            refused=start_current(client,rid)
            assert refused.status_code==409 and refused.json()["error"]["code"]=="RECONCILIATION_REQUIRED",refused.text
            assert calls==[]
        assert execution_snapshot()==before
        view=client.get(f"/api/research/{rid}").json()["data"]
        assert view["source_quota"]["used"]==4 and view["source_quota"]["unknown_closed"]==1


def test_closed_unknown_remains_visible_with_original_times_after_new_observation(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    with source_server() as (port,_):
        bad=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(drop_after_response,port)))
        assert bad.run_once(tid)=="FAILED"
        before=client.get(f"/api/research/{rid}").json()["data"]
        assert before["source_quota"]["unknown_count"]==before["source_quota"]["unknown_closed"]==1
        observation=before["source_observations"][0]
        assert observation["state"]=="outcome_unknown" and observation["execution_closed"] and not observation["result_restored"]
        response=start_current(client,rid)
        assert response.status_code==200,response.text
        two=response.json()["data"]["task"]["id"]
        assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(two)=="COMPLETED"
    current=client.get(f"/api/research/{rid}").json()["data"]
    assert current["source_quota"]["unknown_count"]==current["source_quota"]["unknown_closed"]==1
    assert current["source_quota"]["unknown_unclosed"]==0 and current["source_observations"]==[observation]
    assert current["task"]["id"]!=observation["task_id"] and current["detail"]=="unknown_outcome"


def test_three_licensed_sources_share_four_request_chain_and_one_report(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    metadata=json.loads(METADATA);items=[];articles={}
    for n in range(3):
        doi="10.1371/journal.pone."+str(15032+n).zfill(7)
        title=f"Synthetic queue method {n}"
        item=json.loads(json.dumps(metadata["message"]["items"][0]));item.update(DOI=doi,title=[title]);items.append(item)
        articles[doi]=ARTICLE.replace(DOI.encode(),doi.encode()).replace(TITLE.encode(),title.encode())
    metadata["message"]["items"]=items
    with source_server(metadata=json.dumps(metadata).encode(),article=articles) as (port,calls):
        assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local_targets,port))).run_once(tid)=="COMPLETED"
        assert len(calls)==4
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT used FROM research_source_chains").fetchone()[0]==4
        assert dict(conn.execute("SELECT kind,count(*) FROM research_evidence_objects GROUP BY kind"))=={"plans":1,"executions":4,"snapshots":3,"excerpts":3,"claims":3,"reports":1}
        assert conn.execute("SELECT count(*) FROM research_funding_accounts").fetchone()[0]==0
    reports=client.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":"reports"}).json()["data"]["items"]
    assert len(reports)==1 and len(reports[0]["source_revisions"])==3
    assert reports[0]["model_analysis_ran"] is reports[0]["statistics_ran"] is False


def test_real_account_delete_purges_sources_before_task_bindings(source_stack,lifecycle):
    client,path,rid=source_stack;tid=start(client,rid)
    with source_server() as (port,_):
        assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=="COMPLETED"
    deletion_client,_,_=lifecycle
    response=deletion_client.post("/api/me/delete",json={"confirmation":"DELETE"},headers={"Origin":"http://testserver"})
    assert response.status_code==200,response.text
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT count(*) FROM research_evidence_objects").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_source_approvals").fetchone()[0]==0
        assert conn.execute("SELECT fingerprint,approval_id FROM research_source_runs").fetchone()==(None,None)
        assert conn.execute("SELECT fingerprint,research_id FROM research_source_chains").fetchone()==(None,None)
        assert conn.execute("SELECT research_id,input_digest,auth_generation FROM research_tasks").fetchone()==(None,None,None)
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]
    assert client.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":"sources"}).status_code==401
    for candidate in (path,path.with_name(path.name+"-wal")):
        if candidate.exists():assert b"Synthetic queue methods" not in candidate.read_bytes()


def test_records_are_private_bounded_and_hide_internal_kinds(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    for kind in ("plans","executions","snapshots","raw","discovery","__dict__"):
        assert client.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":kind}).status_code==404
    with TestClient(app()) as other:
        login(other,"d1-other@example.test")
        assert other.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":"sources"}).status_code==404
    for cursor in ("not-base64","W10=","bnVsbA==","x"*2049):
        assert client.get(f"/api/research/{rid}/records",params={"task_id":tid,"kind":"sources","cursor":cursor}).status_code==409


@pytest.mark.parametrize("query",["https://example.test","queue\ntheory","queue theory\n","排队理论","que<ry", "a"*161])
def test_query_rejects_arbitrary_urls_controls_and_unbounded_input(source_stack,query):
    client,path,rid=source_stack
    response=post(client,f"/api/research/{rid}/source-preview",{"input_revision":1,"expected_research_version":1,"query":query})
    assert response.status_code==422,response.text
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT count(*) FROM research_source_approvals").fetchone()[0]==0


def test_real_parent_sigkill_cannot_close_unknown_while_sender_owns_gate(source_stack,tmp_path):
    client,path,rid=source_stack;tid=start(client,rid)
    store=ResearchStore(auth._store());gate=AuthorizationGate(store)
    ready,go=tmp_path/"owned-sender-ready.json",tmp_path/"owned-sender-go"
    with closing(sqlite3.connect(path)) as conn:
        principal=conn.execute("SELECT principal_id FROM research_tasks WHERE id=?",(tid,)).fetchone()[0]
    root=Path(__file__).resolve().parents[3]
    environment={**os.environ,"PYTHONPATH":str(root/"web/backend")+os.pathsep+str(root)}
    guard=sys.modules.get('audit_bootstrap')
    if guard is not None:environment['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+environment['PYTHONPATH']
    with source_server() as (port,calls),(tmp_path/"owned-sender.log").open("wb") as child_log:
        parent=subprocess.Popen([sys.executable,"-m","web.backend.tests.source_http_fixture",tid,str(port),str(ready),str(go)],cwd=root,env=environment,start_new_session=True,stdout=child_log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+10
            while not ready.exists() and time.monotonic()<deadline:
                assert parent.poll() is None
                time.sleep(.02)
            assert ready.exists(),"owned sender did not arm"
            parent.kill();parent.wait(5)
            with closing(sqlite3.connect(path)) as conn:
                original=conn.execute("SELECT started_at,ended_at FROM research_source_requests WHERE task_id=?",(tid,)).fetchone()
            with pytest.raises(ResearchError) as busy:
                with gate.owner_gate(principal,timeout=.1):pytest.fail("orphan sender lost owner capability")
            assert busy.value.code=="STORE_BUSY" and calls==[]
            with closing(sqlite3.connect(path)) as conn:
                assert conn.execute("SELECT execution_closed FROM research_source_requests WHERE task_id=?",(tid,)).fetchone()[0]==0
            # Waiting is observation only. Closure still requires a fresh
            # successful exclusive acquisition, followed by task+owner proof.
            with gate.owner_gate(principal,timeout=15):pass
            recovered=ResearchRunner(store)
            assert recovered.run_once(tid)=="FAILED"
            go.write_text("released after kernel lifetime deadline")
            with closing(sqlite3.connect(path)) as conn:
                conn.row_factory=sqlite3.Row
                closed=conn.execute("SELECT * FROM research_source_requests WHERE task_id=?",(tid,)).fetchone()
                assert closed["outcome"]=="UNKNOWN" and closed["execution_closed"]==1
                assert (closed["started_at"],closed["ended_at"])==original
                assert json.loads(closed["closure_proof"])["retired_write_epoch"]==1
            again=start_current(client,rid)
            assert again.status_code==200,again.text
            new_task=again.json()["data"]["task"]["id"]
            good=ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port)))
            assert good.run_once(new_task)=="COMPLETED"
            assert calls==["/discovery","/article"]
        finally:
            if parent.poll() is None:parent.kill();parent.wait(5)
            try:os.killpg(parent.pid,signal.SIGKILL)
            except ProcessLookupError:pass


def test_sigkill_expired_sender_then_cancel_still_blocks_sending_until_closure(source_stack,tmp_path):
    client,path,rid=source_stack;tid=start(client,rid)
    store=ResearchStore(auth._store());gate=AuthorizationGate(store)
    ready,go=tmp_path/"cancelled-sender-ready.json",tmp_path/"cancelled-sender-go"
    with closing(sqlite3.connect(path)) as conn:
        principal=conn.execute("SELECT principal_id FROM research_tasks WHERE id=?",(tid,)).fetchone()[0]
    root=Path(__file__).resolve().parents[3]
    environment={**os.environ,"PYTHONPATH":str(root/"web/backend")+os.pathsep+str(root)}
    guard=sys.modules.get('audit_bootstrap')
    if guard is not None:environment['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+environment['PYTHONPATH']
    with source_server() as (port,calls),(tmp_path/"owned-sender.log").open("wb") as child_log:
        parent=subprocess.Popen([sys.executable,"-m","web.backend.tests.source_http_fixture",tid,str(port),str(ready),str(go)],cwd=root,env=environment,start_new_session=True,stdout=child_log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+10
            while not ready.exists() and time.monotonic()<deadline:
                assert parent.poll() is None
                time.sleep(.02)
            assert ready.exists()
            parent.kill();parent.wait(5)
            with gate.owner_gate(principal,timeout=15):pass
            current=client.get(f"/api/research/{rid}").json()["data"]
            stopped=post(client,f"/api/research/{rid}/cancel",{"task_id":tid,"expected_task_version":current["task_version"]})
            assert stopped.status_code==200 and stopped.json()["data"]["execution"]=="CANCELLED"
            with closing(sqlite3.connect(path)) as conn:
                before=conn.execute("SELECT outcome,execution_closed,closure_ref,started_at,ended_at FROM research_source_requests").fetchone()
            assert before[:3]==("SENDING",0,None)
            blocked=start_current(client,rid)
            assert blocked.status_code==409 and blocked.json()["error"]["code"]=="RECONCILIATION_REQUIRED",blocked.text
            assert calls==[]
            with closing(sqlite3.connect(path)) as conn:
                assert conn.execute("SELECT count(*) FROM research_tasks").fetchone()[0]==1
                assert conn.execute("SELECT used FROM research_source_chains").fetchone()[0]==1
            assert ResearchRunner(store).run_once(tid)=="CANCELLED"
            with closing(sqlite3.connect(path)) as conn:
                after=conn.execute("SELECT outcome,execution_closed,closure_ref,started_at,ended_at FROM research_source_requests").fetchone()
            assert after[0:2]==("UNKNOWN",1) and after[2] and after[3:]==before[3:]
            next_task=start_current(client,rid)
            assert next_task.status_code==200,next_task.text
            assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(next_task.json()["data"]["task"]["id"])=="COMPLETED"
            assert calls==["/discovery","/article"]
        finally:
            if parent.poll() is None:parent.kill();parent.wait(5)
            try:os.killpg(parent.pid,signal.SIGKILL)
            except ProcessLookupError:pass


def test_preview_is_read_only_and_start_consumes_approval_atomically(source_stack):
    client,path,rid=source_stack
    payload,view=preview(client,rid)
    with closing(sqlite3.connect(path)) as conn,conn:
        for table in ("research_tasks","research_source_approvals","research_source_chains","research_evidence_objects"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_idempotency").fetchone()[0]==1
    approval_body={**payload,"preview_digest":view["preview_digest"],"confirm_external":True}
    approved=post(client,f"/api/research/{rid}/source-approvals",approval_body,"approve")
    assert approved.status_code==200,approved.text
    assert post(client,f"/api/research/{rid}/source-approvals",approval_body,"approve").json()==approved.json()
    start={"input_revision":1,"expected_research_version":1,"approval_ref":approved.json()["data"]["approval_ref"]}
    started=post(client,f"/api/research/{rid}/source-tasks",start,"start")
    assert started.status_code==200,started.text
    assert post(client,f"/api/research/{rid}/source-tasks",start,"start").json()==started.json()
    assert post(client,f"/api/research/{rid}/source-tasks",start,"new-key").status_code==409
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT count(*) FROM research_tasks").fetchone()[0]==1
        assert conn.execute("SELECT status FROM research_source_approvals").fetchone()[0]=="consumed"
        assert conn.execute("SELECT count(*) FROM research_steps").fetchone()[0]==3
        assert conn.execute("SELECT kind FROM research_evidence_objects").fetchone()[0]=="plans"
        assert conn.execute("SELECT used FROM research_source_chains").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_funding_accounts").fetchone()[0]==0
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]


@pytest.mark.parametrize("field,value",[("confirm_external",False),("confirm_external",1),("preview_digest","0"*64),("expected_research_version",2)])
def test_stale_or_implicit_confirmation_cannot_create_approval(source_stack,field,value):
    client,path,rid=source_stack
    payload,view=preview(client,rid)
    body={**payload,"preview_digest":view["preview_digest"],"confirm_external":True,field:value}
    response=post(client,f"/api/research/{rid}/source-approvals",body,"rejected")
    assert response.status_code in (409,422),response.text
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute("SELECT count(*) FROM research_source_approvals").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_tasks").fetchone()[0]==0


def downgrade_empty_sources_to_true_v3(path):
    with closing(sqlite3.connect(path,isolation_level=None)) as conn,conn:
        conn.execute("PRAGMA foreign_keys=OFF");conn.execute("BEGIN IMMEDIATE")
        for name in ("research_evidence_objects","research_source_requests","research_source_runs","research_source_chains","research_source_approvals"):
            conn.execute(f"DROP TABLE {name}")
        for name in ("research_tasks","research_steps"):
            sql=next(sql for sql in C0_SCHEMA if sql.startswith("CREATE TABLE IF NOT EXISTS "+name+" ("))
            sql=sql.replace("CREATE TABLE IF NOT EXISTS "+name,"CREATE TABLE "+name+"_v3",1)
            sql=sql.replace("IN ('c0-fixture-v1','d1-source-only-v1')","='c0-fixture-v1'").replace("IN ('offline_probe','live')","='offline_probe'")
            sql=sql.replace("IN (0,1,2)","IN (0,1)").replace("'discover_sources','fetch_source','compose_report'","'discover_sources','compose_report'")
            conn.execute(sql);conn.execute(f"INSERT INTO {name}_v3 SELECT * FROM {name}")
        conn.execute("DROP TABLE research_steps");conn.execute("DROP TABLE research_tasks")
        conn.execute("ALTER TABLE research_tasks_v3 RENAME TO research_tasks")
        conn.execute("ALTER TABLE research_steps_v3 RENAME TO research_steps")
        for sql in C0_SCHEMA:
            if sql.startswith("CREATE UNIQUE INDEX"):conn.execute(sql)
        conn.execute("UPDATE research_schema SET version=3")
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]
        conn.commit()


def database_rows(path):
    with closing(sqlite3.connect(path)) as conn,conn:
        return {name:conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
            for (name,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


@pytest.mark.parametrize("boundary",[None,"CREATE TABLE research_tasks_v4","INSERT INTO research_tasks_v4","CREATE TABLE research_steps_v4","INSERT INTO research_steps_v4","DROP TABLE research_steps","DROP TABLE research_tasks","ALTER TABLE research_tasks_v4","ALTER TABLE research_steps_v4","CREATE TABLE research_source_approvals","UPDATE research_schema SET version=4","COMMIT"])
def test_true_v3_financial_rows_migrate_or_roll_back_at_each_boundary(legacy_v4_c0,monkeypatch,boundary):
    client,path,store,provider=legacy_v4_c0
    rid,tid=c0_start(client)
    assert ResearchRunner(store).run_once(tid)=="COMPLETED"
    locks={p.name:p.stat().st_ino for p in (path.parent/"research-locks").glob("*.lock")}
    downgrade_empty_sources_to_true_v3(path)
    before=database_rows(path)
    original=sqlite3.connect
    injected=[]
    class FaultConnection(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if boundary and boundary!="COMMIT" and sql.startswith(boundary) and not injected:
                injected.append(True);raise sqlite3.OperationalError("synthetic migration fault")
            return super().execute(sql,*args,**kwargs)
        def commit(self):
            if boundary=="COMMIT" and self.in_transaction and not injected:
                # Inject only after replacement, not initializer's first txn.
                if self.execute("SELECT version FROM research_schema").fetchone()[0]==4:
                    injected.append(True);raise sqlite3.OperationalError("synthetic migration commit fault")
            return super().commit()
    def connect(*args,**kwargs):return original(*args,factory=FaultConnection,**kwargs)
    if boundary:
        monkeypatch.setattr(sqlite3,"connect",connect)
        with pytest.raises(sqlite3.OperationalError,match="synthetic migration"):
            store._migrate_v4()
        assert injected and database_rows(path)==before
        monkeypatch.setattr(sqlite3,"connect",original)
    migrated=ResearchStore(auth._store())
    after=database_rows(path)
    assert after["research_schema"]==[(1,4)]
    for table,rows in before.items():
        if table!="research_schema":assert after[table]==rows
    assert {p.name:p.stat().st_ino for p in (path.parent/"research-locks").glob("*.lock") }==locks
    assert ResearchRunner(migrated).run_once(tid)=="COMPLETED" and provider.count()==2
    assert client.get(f"/api/research/{rid}").json()["data"]["budget"]["known_cost"][0]["amount_units"]==7000


@pytest.fixture
def legacy_v4_c0(monkeypatch,request):
    monkeypatch.setattr(ResearchStore,'_initialize_current',lambda self,conn:False)
    # Keep the original v3->v4 test's real historical shape and every failure
    # boundary. Production has no bypass; v4->v5 is tested independently.
    monkeypatch.setattr(ResearchStore,"_migrate_v5",lambda self:None)
    monkeypatch.setattr(ResearchStore,"_migrate_v6",lambda self:None)
    return request.getfixturevalue("c0")
