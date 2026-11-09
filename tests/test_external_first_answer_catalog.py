"""Exact canonical schema transition on temporary private SQLite, no sender."""
from contextlib import closing
import sqlite3
from uuid import uuid4

import pytest

from web.backend.tests.test_formal_main_admission import prepared,smtp
from research.errors import ResearchError
from research.external_first_answer_catalog import (
    inspect_closed_bridge, project_result, project_status, provision_isolated_v17, require_dispatch_admission,
)
from research.external_first_answer_contract import SavedRevisionScope, parse_unverified_candidate
from research.external_first_answer_file_writer import approve_isolated_file
from research.financial_guard import install_default_hook
from research.first_answer import provision_first_answers_v16
from research.provider_schemas import canonical,digest
from research.store import ResearchStore


def approved(path):
    marker=path.with_name("STRUCTURE-EXTERNAL-LEDGER-FIXTURE")
    marker.write_bytes(b"isolated external ledger candidate, no provider\n");marker.chmod(0o600)
    return approve_isolated_file(path)


def test_actual_canonical_v16_to_v17_and_closed_bridge_same_inode(prepared):
    _,_,paths,_=prepared
    path=paths.private_auth_path()
    provision_first_answers_v16(path)
    proof=approved(path)
    result=provision_isolated_v17(proof)
    assert result=={"schema":17,"external_first_answer":"status_only","database_same_inode":True,"may_send":False}
    assert provision_isolated_v17(proof)==result
    assert inspect_closed_bridge(proof)=={k:v for k,v in result.items() if k!="database_same_inode"}
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row
        install_default_hook(conn);conn.execute("BEGIN")
        ResearchStore._check_v17(conn)
        with pytest.raises(ResearchError,match="SCHEMA_UNSUPPORTED"):
            ResearchStore._check_v16(conn)
        conn.rollback()
    with pytest.raises(ResearchError,match="FEATURE_UNAVAILABLE"):
        require_dispatch_admission()


def test_actual_catalog_abort_keeps_original_v16_complete(prepared,monkeypatch):
    _,_,paths,_=prepared
    path=paths.private_auth_path()
    provision_first_answers_v16(path)
    proof=approved(path)
    def reject(cls,conn):
        assert conn.execute("SELECT version FROM research_schema").fetchone()[0]==17
        raise ContractError("synthetic validation failure")
    from research.external_first_answer_contract import ContractError
    with monkeypatch.context() as fault:
        fault.setattr(ResearchStore,"_check_v17",classmethod(reject))
        with pytest.raises(ContractError,match="synthetic validation failure"):
            provision_isolated_v17(proof)
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row
        install_default_hook(conn);conn.execute("BEGIN")
        ResearchStore._check_v16(conn)
        assert conn.execute("SELECT count(*) FROM sqlite_schema WHERE name='research_external_first_answer_runs'").fetchone()[0]==0
        conn.rollback()


def scope_and_row(state):
    scope=SavedRevisionScope(principal_id=str(uuid4()),auth_generation="0"*32,principal_epoch=1,
        owner_epoch=1,acl_epoch=1,research_id=str(uuid4()),input_revision=1,research_version=1,problem_digest="a"*64)
    key=str(uuid4())
    row={"id":key,"research_id":scope.research_id,"principal_id":scope.principal_id,"input_revision":1,
         "research_version":1,"scope_digest":digest(canonical(scope.model_dump(mode="json"))),"state":state}
    return scope,row,key


@pytest.mark.parametrize("state,expected",[
    ("confirmed","pending"),("reserved","accepted"),("consumed","unknown"),("unknown","unknown"),
    ("returned","completed"),("closed_unsent","not_sent"),
])
def test_status_preserves_the_original_binding_and_does_not_infer_absence(state,expected):
    scope,row,key=scope_and_row(state)
    value=project_status(row,scope,key)
    assert value["status"]==expected and value["operation_key"]==key
    assert value["contract_revision"]=="external-first-answer-v1"
    for bad,key_or in ((None,key),(row,str(uuid4())),(row|{"scope_digest":"b"*64},key)):
        with pytest.raises(ResearchError,match="NOT_FOUND"):
            project_status(bad,scope,key_or)


def test_result_is_separate_and_revalidates_stored_digest_and_body():
    scope,row,key=scope_and_row("returned")
    candidate={"status":"clarification","question":"动作和结果之间隔了多久？"}
    stored=canonical(parse_unverified_candidate(canonical(candidate)))
    saved=row|{"candidate_json":stored.decode(),"candidate_digest":digest(stored)}
    value=project_result(saved,scope,key)
    assert value["result_digest"]==digest(stored) and value["review_required"] is True
    assert value["candidate"]==candidate and "status" not in value
    for bad in (saved|{"candidate_digest":"f"*64},saved|{"state":"unknown"},saved|{"candidate_json":None}):
        with pytest.raises(ResearchError,match="NOT_FOUND"):
            project_result(bad,scope,key)


def test_bridge_reopens_with_real_owner_identity_but_missing_key_is_never_not_sent(prepared):
    import asyncio
    import httpx
    from api import auth
    from research.authorization import AccountIdentity
    from research.external_first_answer_catalog import read_bridge_status
    from web.backend.tests.test_formal_main_admission import BETA,envelope,login,problem
    main,_,paths,messages=prepared

    async def seed():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                made=await client.post("/api/research",json=envelope({"problem":problem()}),
                    headers={"Origin":BETA,"Idempotency-Key":"external-bridge-synthetic"})
                assert made.status_code==200
                c=auth._decode_jwt(client.cookies.get("phase_session"))
                return made.json()["data"]["research"]["id"],AccountIdentity(c["sub"],c["gen"],c["jti"],c["exp"])
    rid,owner=asyncio.run(seed())
    path=paths.private_auth_path()
    provision_first_answers_v16(path)
    proof=approved(path)
    provision_isolated_v17(proof)
    assert inspect_closed_bridge(proof)["external_first_answer"]=="status_only"
    with pytest.raises(ResearchError,match="NOT_FOUND"):
        read_bridge_status(proof,owner,rid,1,str(uuid4()))
    with pytest.raises(ResearchError,match="AUTH_REQUIRED"):
        read_bridge_status(proof,AccountIdentity(owner.email,"f"*32,owner.jti,owner.expires_at),rid,1,str(uuid4()))


def test_preview_public_projection_never_exposes_request_bytes():
    from research.external_first_answer_catalog import project_closed_preview
    from research.external_first_answer_contract import QuoteBinding, PURPOSE, PROJECT
    raw=canonical({"entry":"research","original_input":"反馈滞后会不会改变恢复时间？",
                   "objective":"","summary":"公开问题测试，摘要不发送","variables":[],
                   "constraints":[],"unknowns":[],"confirmed":False})
    scope,_,_=scope_and_row("confirmed")
    scope=SavedRevisionScope.model_validate(scope.model_dump()|{"problem_digest":digest(raw)})
    quote=QuoteBinding(purpose=PURPOSE,project_ref=PROJECT,provider="deepseek",model="deepseek-flash",
        account_id=str(uuid4()),economic_binding="synthetic-account",funding_epoch=1,quote_id=str(uuid4()),
        price_basis_digest="a"*64,currency="CNY",scale=6,upper_units=2000,issued_at=10,valid_until=30)
    view=project_closed_preview(scope,raw,quote,now=15)
    assert set(view)=={"contract_revision","purpose","metadata","exact_question","target","provider","model",
                       "currency","scale","upper_units","preview_digest","request_digest","valid_until","may_send"}
    assert view["may_send"] is False and view["metadata"]["problem_digest"]==digest(raw)
