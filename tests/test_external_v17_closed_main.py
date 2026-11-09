"""Actual Main on a marked isolated v17 Auth DB; no model/provider."""
import asyncio
import os
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


def test_real_v17_closed_main_preserves_login_history_and_saved_revisions(prepared,monkeypatch,capsys,tmp_path):
    main,admission,paths,messages=prepared
    from api import auth
    from services.artifact_manifest import FormalArtifactSnapshot
    from web.backend.tests.test_formal_search_profile import make_bundle,encoder,synthetic_readonly_mount
    if not os.environ.get("STRUCTURAL_ARTIFACT_MANIFEST"):
        files=make_bundle(tmp_path/"fin3-admission-search")
        for env,key in (("STRUCTURAL_DATA_DIR","data_dir"),("STRUCTURAL_KB_FILE","kb_file"),
                        ("STRUCTURAL_MODEL_PATH","model_path"),("STRUCTURAL_PRECOMPUTED_EMBEDDINGS","precomputed_embeddings"),
                        ("STRUCTURAL_ARTIFACT_MANIFEST","artifact_manifest")):
            monkeypatch.setenv(env,files[key])
        encoder.__wrapped__(monkeypatch)
        synthetic_readonly_mount.__wrapped__(monkeypatch)
    checked=[]
    original=FormalArtifactSnapshot.check_model
    def check_model(snapshot):
        from research.financial_result_v2 import calculate as native_calculate
        frame=sys._getframe(1)
        while frame is not None:
            assert frame.f_code is not native_calculate.__code__,"manual FIN3 must not read model weights"
            frame=frame.f_back
        checked.append(True)
        return original(snapshot)
    monkeypatch.setattr(FormalArtifactSnapshot,"check_model",check_model)
    with pytest.raises(PermissionError,match="actual financial Main admission caller"):
        admission._require_local_financial_calculation(main.app,None,None,None,None,None,None)
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
                before=len(checked)
                assert admission.safe_status(main.app)["base"]=="ready"
                assert len(checked)>before  # generic Main health retains actual model guard
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
                local_fin=await create(owner,"closed-v17-new-finance")
                local_body=await setup_financial(owner,local_fin,currency="CNY")
                local_result=await calculate(owner,local_fin,local_body,key="closed-v17-fin3")
                assert local_result.status_code==200,local_result.text
                result_meta=local_result.json()["data"]["metadata"]
                local_fin_url=f"/api/research/{local_fin}/financial-results/{result_meta['result_ref']}?view=table"
                local_saved=await owner.get(local_fin_url)
                assert local_saved.status_code==200 and local_result.json()["data"]["persisted"] is True
                assert result_meta["model_analysis_ran"] is False
                assert (await calculate(owner,local_fin,local_body,key="closed-v17-fin3")).json()==local_result.json()
                from research.paid_control import _current_scope,_local_financial_scope
                from research.financial_execution import require_native_scope
                with ResearchStore(auth._store()).transaction(write=True) as conn:
                    with pytest.raises(PermissionError,match="v17 deletion-only scope required"):_current_scope(conn)
                    conn.execute("CREATE TEMP TABLE research_schema (id INTEGER, version INTEGER)")
                    conn.execute("INSERT INTO temp.research_schema VALUES (1,5)")
                    with pytest.raises(PermissionError,match="v17 deletion-only scope required"):_current_scope(conn)
                    with pytest.raises(ResearchError,match="SCHEMA_UNSUPPORTED"):
                        ResearchStore.check_runtime_version(conn)
                    conn.execute("DROP TABLE temp.research_schema")
                    ResearchStore.check_runtime_version(conn)
                    with pytest.raises(PermissionError,match="local financial producer required"):_local_financial_scope(conn)
                    with pytest.raises(sqlite3.DatabaseError):
                        conn.execute("DELETE FROM research_financial_results WHERE result_ref=?",(result_meta["result_ref"],))
                    for table in ("research_plan_native_runs","research_source_runs"):
                        with pytest.raises(sqlite3.DatabaseError,match="not authorized"):
                            conn.execute("INSERT INTO "+table+" DEFAULT VALUES")
                    with pytest.raises(PermissionError,match="actual private transaction required"):
                        require_native_scope(conn,None,None,None,None)
                    for name in ("research_funding_accounts","research_source_runs","research_tasks"):
                        assert conn.execute("SELECT COUNT(*) FROM "+name).fetchone()[0]==0
                new=await create(owner,"bridge-v17-new-draft")
                revised=await owner.post("/api/research/"+new+"/revisions",
                    json=envelope({"expected_revision":1,"problem":problem()|{"original_input":"v17 回退模式的新修订"}}),
                    headers=origin|{"Idempotency-Key":"bridge-v17-new-revision"})
                assert revised.status_code==200,revised.text
                stored=revised.json()["data"]["current_problem"]
                assert stored["revision"]==2
            async with main.lifespan(main.app):
                await login(owner,messages)
                reopened_fin=await owner.get(local_fin_url)
                assert reopened_fin.status_code==200 and reopened_fin.json()==local_saved.json()
                response=await owner.get("/api/research/"+new)
                assert response.status_code==200 and response.json()["data"]["current_problem"]==stored
                async with httpx.AsyncClient(transport=transport,base_url=BETA) as other:
                    assert (await other.get("/api/research/"+new)).status_code==401
                    await login(other,messages,"other-v17@example.invalid")
                    assert (await other.get("/api/research/"+new)).status_code==404
                    assert (await other.get(local_fin_url)).status_code==404
                    assert (await calculate(other,local_fin,local_body,key="foreign-v17-fin3")).status_code==404
        assert admission._STATE.get(id(main.app)) is None
    asyncio.run(verify())
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as conn:
        assert conn.execute("SELECT version FROM research_schema").fetchone()==(17,)
        assert conn.execute("SELECT count(*) FROM research_external_first_answer_runs").fetchone()==(0,)
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]
