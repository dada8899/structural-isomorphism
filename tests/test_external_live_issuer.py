"""Actual marked v17 Main and synthetic dedicated loader; no provider requests."""
import asyncio
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

import httpx
import pytest

from tests.test_external_first_answer_issuer_contract import enrollment, NOW, uuid
from web.backend.tests.test_formal_main_admission import BETA,envelope,login,prepared,problem,smtp
from web.backend.tests.test_research_first_answer import identity


def test_real_v17_main_attestation_signed_one_shot_loader_and_sender_retirement(prepared,tmp_path):
    main,admission,paths,messages=prepared
    from api import auth
    from research import first_answer,plan_native
    from research.external_first_answer_catalog import provision_isolated_v17
    from research.external_first_answer_contract import ContractError
    from research.external_first_answer_file_writer import approve_isolated_file
    from research.external_first_answer_issuer_contract import StartupBinding,CREDENTIAL_ENTRY,CREDENTIAL_ID
    from research.store import ResearchStore
    from services.external_live_issuer import RehearsalCredential,activate_live_external_issuer,rehearse_external_loader
    path=paths.private_auth_path()
    first_answer.provision_first_answers_v16(path)
    approval_dir=tmp_path/"issuer-approval"
    approval_dir.mkdir(mode=0o700)
    scratch,fake,key,sign=enrollment.__wrapped__(approval_dir)

    async def verify(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
            async with main.lifespan(main.app):
                await login(client,messages)
                made=await client.post("/api/research",json=envelope({"problem":problem()}),
                    headers={"Origin":BETA,"Idempotency-Key":"issuer-owner-fixture"})
                assert made.status_code==200
                store=ResearchStore(auth._store())
                actor=identity(client)
                authority=plan_native.create_controlled_runtime_fixture_authority(
                    store,actor,server,approved_cap_units=300_000_000,risk_margin_units=2_129_920)
                provision=plan_native.issue_native_provision(store,authority)
                permit=plan_native.mint_runtime_permit(provision)
                resource=plan_native.open_plan_resource(permit)
                try:plan_native.install_native_funding(store,provision,resource)
                finally:plan_native.retire_installation(store)
                with store.transaction() as conn:
                    row=conn.execute("""SELECT f.account_id,f.economic_binding,f.credential_incarnation,f.principal_id,
                        f.generation,f.owner_gate_id,a.funding_epoch,p.epoch
                        FROM research_plan_native_funding f JOIN research_funding_accounts a ON a.id=f.account_id
                        JOIN research_principals p ON p.id=f.principal_id WHERE f.id=1""").fetchone()
                    overrides=dict(zip(("account_id","economic_binding","credential_incarnation","owner_principal",
                        "owner_generation","owner_gate_id","funding_epoch","owner_epoch"),row))
                overrides.update(database_dev=store.storage_identity[0],database_ino=store.storage_identity[1])
            marker=path.with_name("STRUCTURE-EXTERNAL-LEDGER-FIXTURE")
            marker.write_bytes(b"isolated external ledger candidate, no provider\n");marker.chmod(0o600)
            provision_isolated_v17(approve_isolated_file(path))
            actual=StartupBinding.model_validate(fake.model_dump()|overrides)
            raw=sign(binding=actual.model_dump(mode="json"))
            calls=[]
            def loader(cap,witness):
                with pytest.raises(ContractError,match="external_loader_claim_rejected"):
                    cap.claim(witness,entry=CREDENTIAL_ENTRY,credential_id="structural-deepseek-api-key")
                cap.claim(witness,entry=CREDENTIAL_ENTRY,credential_id=CREDENTIAL_ID)
                with pytest.raises(ContractError,match="external_loader_claim_rejected"):
                    cap.claim(witness,entry=CREDENTIAL_ENTRY,credential_id=CREDENTIAL_ID)
                calls.append("claimed")
                return RehearsalCredential()
            async with main.lifespan(main.app):
                with pytest.raises(ContractError,match="live_external_issuer_unbound"):
                    activate_live_external_issuer(main.app)
                other=StartupBinding.model_validate(actual.model_dump()|{"database_ino":actual.database_ino+1})
                with pytest.raises(ContractError,match="external_main_attestation_rejected"):
                    with rehearse_external_loader(main.app,scratch,sign(binding=other.model_dump(mode="json")),other,key,loader,now=NOW):
                        pytest.fail("different physical account DB must fail")
                assert calls==[] and not list(scratch.glob("spent-*"))
                with rehearse_external_loader(main.app,scratch,raw,actual,key,loader,now=NOW) as handle:
                    handle.require(main.app,live=False)
                    with pytest.raises(ContractError,match="live_external_issuer_unbound"):
                        handle.require(main.app)
                    assert calls==["claimed"]
                with pytest.raises(ContractError,match="external_sender_handle_retired"):
                    handle.require(main.app,live=False)
                with pytest.raises(ContractError,match="startup_challenge_already_consumed"):
                    with rehearse_external_loader(main.app,scratch,raw,actual,key,loader,now=NOW):
                        pytest.fail("consumed challenge must not reach loader")
                assert calls==["claimed"]
                failed=StartupBinding.model_validate(actual.model_dump()|{"startup_id":uuid()})
                failed_raw=sign(binding=failed.model_dump(mode="json"))
                def no_claim(*_):
                    return RehearsalCredential()
                with pytest.raises(ContractError,match="external_loader_receipt_rejected"):
                    with rehearse_external_loader(main.app,scratch,failed_raw,failed,key,no_claim,now=NOW):
                        pytest.fail("loader must claim")
                with pytest.raises(ContractError,match="startup_challenge_already_consumed"):
                    with rehearse_external_loader(main.app,scratch,failed_raw,failed,key,loader,now=NOW):
                        pytest.fail("failure does not restore challenge")
            assert admission._STATE.get(id(main.app)) is None
    class DenyHTTP(BaseHTTPRequestHandler):
        def do_POST(self):pytest.fail("provider POST is out of scope")
        def do_GET(self):pytest.fail("provider GET is out of scope")
    # The existing synthetic account registration factory expects an owned
    # bound loopback socket. There is no serving thread or provider request.
    with ThreadingHTTPServer(("127.0.0.1",0),DenyHTTP) as server:
        asyncio.run(verify(server))
