"""Actual Main on a marked isolated v17 Auth DB; no model/provider."""
import asyncio
from pathlib import Path
import runpy
import sqlite3
import sys
from contextlib import closing

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA,envelope,login,prepared,problem,smtp
from web.backend.tests.test_research_financial_registries import create
from web.backend.tests.test_research_financial_results_v2 import setup_financial,calculate
from web.backend.tests.test_research_first_answer import candidate,identity


def test_real_v17_closed_main_preserves_login_history_and_saved_revisions(prepared,monkeypatch,capsys):
    main,admission,paths,messages=prepared
    from api import auth
    from research import first_answer,native_plan_supervisor,source_supervisor
    from research.external_first_answer_catalog import require_dispatch_admission
    from research.errors import ResearchError
    from research.service import ResearchService
    from research.store import ResearchStore
    path=paths.private_auth_path()
    first_answer.provision_first_answers_v16(path)
    before_inode=path.stat().st_ino
    origin={"Origin":BETA}
    transport=httpx.ASGITransport(app=main.app)

    async def verify():
        async with httpx.AsyncClient(transport=transport,base_url=BETA) as owner:
            async with main.lifespan(main.app):
                await login(owner,messages)
                rid=await create(owner,"bridge-v17-existing-answer")
                data=(await owner.get("/api/research/"+rid)).json()["data"]
                service=ResearchService(ResearchStore(auth._store()))
                answer=first_answer.save(service,identity(owner),rid,input_revision=1,
                    problem_digest=data["current_problem"]["digest"],research_version=data["research_version"],
                    key="bridge-local-answer",answer=candidate())
                finance=await create(owner,"bridge-v17-existing-finance")
                finished=await calculate(owner,finance,await setup_financial(owner,finance,currency="USD"),key="bridge-v17-existing-fin3")
                assert finished.status_code==200,finished.text
                fin_ref=finished.json()["data"]["metadata"]["result_ref"]
                fin_url=f"/api/research/{finance}/financial-results/{fin_ref}?view=table"
                fin=(await owner.get(fin_url)).json()
            marker=path.with_name("STRUCTURE-EXTERNAL-LEDGER-FIXTURE")
            marker.write_bytes(b"isolated external ledger candidate, no provider\n");marker.chmod(0o600)
            script=Path(__file__).resolve().parents[1]/"scripts/bootstrap-private-runtime.py"
            monkeypatch.setattr(sys,"argv",[str(script),"--offline-migrate-external-fallback"])
            runpy.run_path(str(script),run_name="__main__")
            assert '"schema": 17' in capsys.readouterr().out
            assert path.stat().st_ino==before_inode
            monkeypatch.setattr(native_plan_supervisor,"start",lambda *_:pytest.fail("v17 must not start a paid worker"))
            monkeypatch.setattr(source_supervisor,"start",lambda *_:pytest.fail("v17 must not start an outbound source worker"))
            async with main.lifespan(main.app):
                assert admission.safe_status(main.app)["base"]=="ready"
                assert admission.safe_status(main.app)["native_planner"]=="FUNDING_CLOSED"
                with pytest.raises(ResearchError,match="FEATURE_UNAVAILABLE"):require_dispatch_admission()
                ans=(await owner.get(f"/api/research/{rid}/revisions/1/first-answer"))
                assert ans.status_code==200 and ans.json()==answer
                loaded=await owner.get("/api/research/"+rid)
                assert loaded.json()["data"]["capabilities"]["external_first_answer"]=="status_only"
                external=f"/api/research/{rid}/revisions/1/external-first-answer"
                headers={"Idempotency-Key":"e09160ad-396a-4edc-a383-e54c48ba728f"}
                for action in ("status","result"):
                    absent=await owner.get(external+"/"+action,headers=headers)
                    assert absent.status_code==404 and absent.json()["error"]["code"]=="NOT_FOUND"

                reopened=await owner.get(fin_url)
                assert reopened.status_code==200 and reopened.json()==fin
                new=await create(owner,"bridge-v17-new-draft")
                revised=await owner.post("/api/research/"+new+"/revisions",
                    json=envelope({"expected_revision":1,"problem":problem()|{"original_input":"v17 回退模式的新修订"}}),
                    headers=origin|{"Idempotency-Key":"bridge-v17-new-revision"})
                assert revised.status_code==200,revised.text
                stored=revised.json()["data"]["current_problem"]
                assert stored["revision"]==2
            async with main.lifespan(main.app):
                await login(owner,messages)
                response=await owner.get("/api/research/"+new)
                assert response.status_code==200 and response.json()["data"]["current_problem"]==stored
                async with httpx.AsyncClient(transport=transport,base_url=BETA) as other:
                    assert (await other.get("/api/research/"+new)).status_code==401
                    await login(other,messages,"other-v17@example.invalid")
                    assert (await other.get("/api/research/"+new)).status_code==404
        assert admission._STATE.get(id(main.app)) is None
    asyncio.run(verify())
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as conn:
        assert conn.execute("SELECT version FROM research_schema").fetchone()==(17,)
        assert conn.execute("SELECT count(*) FROM research_external_first_answer_runs").fetchone()==(0,)
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]
