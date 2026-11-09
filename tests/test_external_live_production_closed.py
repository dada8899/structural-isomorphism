"""Actual v17 lifecycle must not seek any external material without proof."""
import asyncio

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA,envelope,login,prepared,problem,smtp


@pytest.mark.parametrize("pin",[False,True],ids=["no-source-pin","pin-without-entry-witness"])
def test_actual_main_defaults_closed_without_credential_or_crypto_lookup(prepared,monkeypatch,pin):
    main,admission,paths,messages=prepared
    from research.external_first_answer_catalog import provision_isolated_v17
    from research.external_first_answer_file_writer import approve_isolated_file
    from research.first_answer import provision_first_answers_v16
    from services import external_live_production as production
    path=paths.private_auth_path()
    provision_first_answers_v16(path)
    marker=path.with_name("STRUCTURE-EXTERNAL-LEDGER-FIXTURE")
    marker.write_bytes(b"isolated external ledger candidate, no provider\n");marker.chmod(0o600)
    provision_isolated_v17(approve_isolated_file(path))
    def forbidden(*_):
        pytest.fail("no credential, approval file or verifier access before entry witness")
    monkeypatch.setattr(production,"_load_credential",forbidden)
    monkeypatch.setattr(production,"_fixed_file",forbidden)
    monkeypatch.setattr(production,"_verify_runtime_files",forbidden)
    monkeypatch.setenv("STRUCTURAL_EXTERNAL_FIRST_ANSWER_ENABLED","true")
    if pin:
        monkeypatch.setattr(production,"_PINNED_POLICY",production.PinnedTargetPolicy("0"*64,"0"*64,"/no","/no",()))

    async def verify():
        async with main.lifespan(main.app):
            assert admission.safe_status(main.app)["base"]=="ready"
            assert not production._LIVE and not production._ENTRIES
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                made=await client.post("/api/research",json=envelope({"problem":problem()}),
                    headers={"Origin":BETA,"Idempotency-Key":"external-live-closed-fixture"})
                assert made.status_code==200
                data=made.json()["data"];rid=data["research"]["id"]
                assert data["capabilities"]["external_first_answer"]=="status_only"
                answer=await client.post(f"/api/research/{rid}/revisions/1/external-first-answer/preview",
                    json={"research_version":data["research_version"],"problem_digest":data["current_problem"]["digest"]},
                    headers={"Origin":BETA})
                assert answer.status_code==503
        assert not production._LIVE and admission._STATE.get(id(main.app)) is None
    asyncio.run(verify())
