"""Actual v17 Main routes, synthetic registered shared account, local HTTP only."""
import asyncio
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import sqlite3
import threading
from uuid import uuid4

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA,envelope,login,prepared,problem,smtp
from web.backend.tests.test_research_first_answer import identity


@pytest.mark.parametrize("unknown",[False,True],ids=["completed","unknown-held"])
def test_main_external_controlled_preview_confirm_status_and_original_result(prepared,unknown):
    main,admission,paths,messages=prepared
    from api import auth
    from research import first_answer,plan_native,plan_native_financial,plan_financial
    from research.errors import ResearchError
    from research.external_first_answer_catalog import provision_isolated_v17
    from research.external_first_answer_controlled import controlled_runtime
    from research.external_first_answer_file_writer import approve_isolated_file
    from research.store import ResearchStore
    path=paths.private_auth_path()
    original_inode=path.stat().st_ino
    first_answer.provision_first_answers_v16(path)
    origin={"Origin":BETA}
    calls=[]
    candidate={"status":"candidate","explanation":"如果反馈滞后，累积调整可能引起超调。",
        "assumptions":["动作会改变下一轮测量。"],"next_check":"记录动作和生效的时点。","evidence_status":"not_checked"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            assert self.path=="/fixture-external-first-answer"
            calls.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200);self.end_headers()
            if not unknown:self.wfile.write(json.dumps(candidate,ensure_ascii=False).encode())

    async def verify(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
            async with main.lifespan(main.app):
                await login(client,messages)
                original="为什么每次晚一轮校正时容易反复超调？"
                made=await client.post("/api/research",json=envelope({"problem":problem()|{"original_input":original}}),
                    headers=origin|{"Idempotency-Key":"controlled-external-draft"})
                assert made.status_code==200,made.text
                data=made.json()["data"]
                rid=data["research"]["id"]
                store=ResearchStore(auth._store())
                actor=identity(client)
                authority=plan_native.create_controlled_runtime_fixture_authority(
                    store,actor,server,approved_cap_units=300_000_000,risk_margin_units=2_129_920)
                provision=plan_native.issue_native_provision(store,authority)
                permit=plan_native.mint_runtime_permit(provision)
                resource=plan_native.open_plan_resource(permit)
                try:
                    plan_native.install_native_funding(store,provision,resource)
                finally:
                    plan_native.retire_installation(store)
                assert calls==[]
            marker=path.with_name("STRUCTURE-EXTERNAL-LEDGER-FIXTURE")
            marker.write_bytes(b"isolated external ledger candidate, no provider\n");marker.chmod(0o600)
            proof=approve_isolated_file(path)
            provision_isolated_v17(proof)
            base=f"/api/research/{rid}/revisions/1/external-first-answer"
            expected={"research_version":data["research_version"],"problem_digest":data["current_problem"]["digest"]}
            key=str(uuid4())
            async with main.lifespan(main.app):
                assert (await client.post(base+"/preview",json=expected,headers=origin)).status_code==503
                with controlled_runtime(main.app,proof,server,balance=400_000_000):
                    offered=await client.post(base+"/preview",json=expected,headers=origin)
                    assert offered.status_code==200,offered.text
                    preview=offered.json()
                    assert preview["exact_question"]==original and preview["may_send"] is True and calls==[]
                    body={k:preview[k] for k in ("preview_digest","request_digest","upper_units")}
                    body.update(purpose="external-first-answer-question-v1",confirm_exact_question=True,
                                confirm_maximum_cost=True,declares_right_to_send=True)
                    headers=origin|{"Idempotency-Key":key}
                    denied=await client.post(base+"/confirm",json=body|{"confirm_maximum_cost":False},headers=headers)
                    assert denied.status_code==422 and calls==[]
                    response=await client.post(base+"/confirm",json=body,headers=headers)
                    assert response.status_code==200,response.text
                    operation=response.json()
                    assert operation["status"]==("unknown" if unknown else "completed")
                    assert operation["operation_key"]==key and len(calls)==1
                    sent=json.loads(json.loads(calls[0])["messages"][1]["content"])
                    assert sent=={"contract":"external-first-answer-question-only-v1","question":original}
                    assert (await client.post(base+"/confirm",json=body,headers=headers)).json()==operation
                    mismatch=await client.post(base+"/confirm",json=body|{"upper_units":body["upper_units"]+1},headers=headers)
                    assert mismatch.status_code==409 and len(calls)==1
                assert (await client.get(base+"/status",headers=headers)).json()==operation
                result=await client.get(base+"/result",headers=headers)
                if unknown:assert result.status_code==404
                else:
                    assert result.status_code==200 and result.json()["candidate"]==candidate
                    assert result.json()["review_required"] is True
                assert (await client.get(base+"/status",headers={"Idempotency-Key":str(uuid4())})).status_code==404
                async with httpx.AsyncClient(transport=client._transport,base_url=BETA) as other:
                    await login(other,messages,"external-other@example.invalid")
                    assert (await other.get(base+"/status",headers=headers)).status_code==404
            async with main.lifespan(main.app):
                assert (await client.get(base+"/status",headers=headers)).json()==operation
                assert (await client.post(base+"/preview",json=expected,headers=origin)).status_code==503
            assert admission._STATE.get(id(main.app)) is None

    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
        worker=threading.Thread(target=server.serve_forever);worker.start()
        try:asyncio.run(verify(server))
        finally:
            server.shutdown();worker.join(4)
            assert not worker.is_alive()
    assert path.stat().st_ino==original_inode and len(calls)==1
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as conn:
        row=conn.execute("SELECT id,held,upper_booked FROM research_funding_accounts").fetchone()
        assert conn.execute("SELECT count(*) FROM research_funding_accounts").fetchone()==(1,)
        assert row[1:]==((5000,0) if unknown else (0,5000))
        assert plan_native_financial.unresolved(conn,row[0]) is unknown
        if unknown:
            with pytest.raises(ResearchError,match="RECONCILIATION_REQUIRED"):
                plan_financial.check_unknown(conn,row[0])
        else:plan_financial.check_unknown(conn,row[0])
        assert conn.execute("SELECT count(*) FROM research_plan_native_runs").fetchone()==(0,)
