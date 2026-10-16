"""CP1: real saved-source read/auth and pure byte guards, never paid authority."""
from dataclasses import asdict,replace
from functools import partial
import gzip
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from .test_research_persistence import stack,app,login,post,problem
from .test_research_d1_integration import source_stack,start
from .source_http_fixture import source_server,get_local
from api import auth
from research import ResearchStore,ResearchRunner
from research.authorization import AccountIdentity,AuthorizationGate
from research.source_policy import PinnedPublicTransport
from research.provider_evidence import read_provider_eligibility,ProviderEligibleExcerpt
from research.evidence_repository import EvidenceRepository
from research.source_integration import authorizer,context_for
from research.provider_schemas import canonical,digest,ProviderFailure
from research import provider_adapter as adapter,provider_schemas as schemas


def identity(client):
    claims=auth._decode_jwt(client.cookies.get("phase_session"))
    return AccountIdentity(claims["sub"],claims["gen"],claims["jti"],claims["exp"])


@pytest.fixture
def saved(source_stack):
    client,path,rid=source_stack;tid=start(client,rid)
    store=ResearchStore(auth._store())
    with source_server() as (port,calls):
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=="COMPLETED"
        assert calls==["/discovery","/article"]
    view=client.get(f"/api/research/{rid}").json()["data"]
    with store.transaction() as conn:
        excerpt=conn.execute("SELECT id FROM research_evidence_objects WHERE kind='excerpts'").fetchone()[0]
    return client,path,store,rid,tid,view["research_version"],excerpt


def read(saved,**changes):
    client,_,store,rid,_,version,excerpt=saved
    args=dict(store=store,identity=identity(client),research_id=rid,input_revision=1,research_version=version,excerpt_ids=(excerpt,))
    args.update(changes)
    return read_provider_eligibility(**args)


def test_real_v2_publisher_proof_produces_eligibility_but_never_send_consent(saved):
    client,_,store,rid,tid,version,excerpt=saved
    with store.transaction() as conn:
        before=conn.execute("SELECT count(*) FROM research_evidence_objects").fetchone()[0]
    value=read(saved);item,=value.excerpts
    assert value.may_send_to_provider is item.may_send_to_provider is False
    assert item.read_scope=="author_narrative_subset" and item.quote.startswith("Waiting time")
    assert len(item.quote.split())<=20 and len(item.quote)<=1000
    assert item.origin=="offline_probe" and item.target_model=="deepseek-flash"
    encoded=canonical(asdict(value))
    assert b'"raw":' not in encoded and b'"extracted_text":' not in encoded
    assert len(value.manifest_digest)==64 and read(saved)==value
    with pytest.raises(ValueError):replace(item,may_send_to_provider=True)
    with pytest.raises(ValueError):replace(value,may_send_to_provider=True)
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM research_evidence_objects").fetchone()[0]==before
        for table in ("research_funding_accounts","research_reservations","research_dispatch_permits","research_cost_observations"):
            assert conn.execute("SELECT count(*) FROM "+table).fetchone()[0]==0
        assert conn.execute("SELECT used FROM research_source_chains").fetchone()[0]==2


def alter_saved_snapshot(store,kind):
    with store.transaction(write=True) as conn:
        row=dict(conn.execute("SELECT * FROM research_evidence_objects WHERE kind='snapshots'").fetchone())
        payload=json.loads(row["payload"])
        if kind=="legacy":payload["parser_version"]="plos-html-text-v1"
        elif kind=="no_ccby":
            metadata=json.loads(row["discovery"]);metadata["message"]["items"][0]["license"]=[]
            row["discovery"]=json.dumps(metadata).encode();payload["discovery_digest"]=digest(row["discovery"])
        elif kind=="bad_metadata":
            metadata=json.loads(row["discovery"]);metadata["status"]="failed"
            row["discovery"]=json.dumps(metadata).encode();payload["discovery_digest"]=digest(row["discovery"])
        elif kind=="copyright_denied":
            row["raw"]=row["raw"].replace(b"permits unrestricted use",b"no reproduction permitted")
            payload["raw_digest"]=digest(row["raw"])
        elif kind=="wrong_subset":
            row["extracted"]+=" NAVIGATION COMMENTS NOT AUTHOR TEXT"
            payload["extracted_digest"]=digest(row["extracted"].encode())
        elif kind=="gzip":
            row["raw"]=gzip.compress(row["raw"]);payload["raw_digest"]=digest(row["raw"])
        elif kind=="bad_encoding":
            row["raw"]=b"\xff\x00";payload["raw_digest"]=digest(row["raw"])
        row["payload"]=canonical(payload).decode();row["payload_digest"]=digest(row["payload"].encode())
        conn.execute("INSERT OR REPLACE INTO research_evidence_objects ("+",".join(row)+") VALUES("+",".join("?" for _ in row)+")",tuple(row.values()))


@pytest.mark.parametrize("kind",["legacy","no_ccby","bad_metadata","copyright_denied","wrong_subset","bad_encoding"])
def test_saved_cache_and_display_flags_are_not_external_permission(saved,kind):
    from research.errors import ResearchError
    alter_saved_snapshot(saved[2],kind)
    with pytest.raises(ResearchError) as error:read(saved)
    assert error.value.code=="SOURCE_PERMISSION_UNAVAILABLE"


def test_bounded_stored_gzip_is_reverified_without_refetch(saved):
    original=read(saved)
    alter_saved_snapshot(saved[2],"gzip")
    result=read(saved)
    assert result.excerpts[0].quote==original.excerpts[0].quote
    assert result.excerpts[0].raw_digest!=original.excerpts[0].raw_digest
    assert result.may_send_to_provider is False


def test_current_owner_revision_and_scope_are_required_on_every_read(saved):
    from research.errors import ResearchError
    client,_,store,rid,_,version,excerpt=saved
    with TestClient(app()) as other:
        login(other,"producer-other@example.test")
        with pytest.raises(ResearchError):read(saved,identity=identity(other))
    with pytest.raises(ResearchError):read(saved,research_version=version+1)
    with pytest.raises(ResearchError):read(saved,excerpt_ids=(str(uuid4()),))
    with pytest.raises(ResearchError):read(saved,excerpt_ids=({},))
    with store.transaction(write=True) as conn:
        conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=?",(rid,))
    with pytest.raises(ResearchError):read(saved)


def packet():
    uid=lambda:str(uuid4())
    context=schemas.CallContext(principal_id=uid(),principal_epoch=1,grant_id=uid(),grant_epoch=1,owner_epoch=1,acl_epoch=1,research_id=uid(),input_revision=1,input_digest="a"*64,task_id=uid(),attempt=1,plan_id=uid())
    # Ordinary DTOs exercise request encoding only, never source/paid authority.
    return schemas.EvidencePacket(context=context,handles=())


@pytest.mark.parametrize("change",["max_tokens","thinking","tools","stream","model","duplicate","extra"])
def test_final_request_bytes_reject_override_or_duplicate_before_connection(change):
    prepared=adapter.prepare_request("Bounded offline question",packet())
    body=json.loads(prepared.raw)
    if change=="max_tokens":body[change]=8192
    elif change=="thinking":body[change]={"type":"enabled"}
    elif change=="tools":body[change]=[]
    elif change=="stream":body[change]=True
    elif change=="model":body[change]="other-model"
    else:body["extra"]=True
    raw=canonical(body)
    if change=="duplicate":raw=prepared.raw[:-1]+b',"max_tokens":4096}'
    forged=replace(prepared,raw=raw,request_digest=digest(raw))
    with pytest.raises(ProviderFailure):adapter.final_request_bytes(forged)
    calls=[]
    probe=adapter.DeepSeekAdapter.offline_probe(connection_factory=lambda *_:calls.append(True),credential_loader=lambda _:"synthetic")
    with pytest.raises(ProviderFailure):probe.preconnect(forged)
    assert calls==[]


class Sink:
    def __init__(self):self.sends=[];self.closed=False
    def settimeout(self,value):pass
    def sendall(self,value):self.sends.append(value)
    def shutdown(self,*args):pass
    def close(self):self.closed=True


def controls(prepared,lease):
    uid=lambda:str(uuid4())
    price=schemas.PriceQuote(revision=uid(),currency="USD",scale=6,peak_input_miss_units_per_million=1,peak_input_hit_units_per_million=0,peak_output_units_per_million=1,c_bound=1048576,o_bound=393216,output_basis="official_maximum",rounding_guard=1,price_document_digest="a"*64,model_document_digest="b"*64,bound_basis_digest="c"*64,valid_until=2000000000)
    money=lambda units:schemas.Money(currency="USD",scale=6,amount_units=units)
    basis=schemas.BudgetBasisSnapshot(id=uid(),account_id=uid(),provider_binding_id=uid(),funding_epoch=1,initial_prepaid=money(100),other_use_margin=money(0),cap=money(100),settled_actual=money(0),upper_booked=money(0),held=money(0),available_after_observed_consumption=money(100),price_revision=price.revision,valid_until=2000000000)
    permit=schemas.CallPermit(id=uid(),account_id=basis.account_id,provider_binding_id=basis.provider_binding_id,funding_epoch=1,dispatch_id=uid(),reservation_id=uid(),context=prepared.packet.context,request_digest=prepared.request_digest,evidence_digest=prepared.evidence_digest,price_digest=digest(canonical(price.model_dump())),price_revision=price.revision,budget_basis_digest=digest(canonical(basis.model_dump())),gate_identity=lease.identity,expires_at=2000000000)
    return price,basis,permit


@pytest.mark.parametrize("mutate",[False,True])
def test_last_send_uses_revalidated_local_immutable_bytes(tmp_path,mutate):
    prepared=adapter.prepare_request("Bounded offline question",packet());original=prepared.raw
    sink=Sink()
    probe=adapter.DeepSeekAdapter.offline_probe(connection_factory=lambda _:sink,credential_loader=lambda _:"synthetic-probe-key")
    connection=probe.preconnect(prepared)
    try:
        gate=AuthorizationGate(SimpleNamespace(path=tmp_path/"unused.sqlite3"))
        with gate.owner_gate_id(str(uuid4())) as lease:
            price,basis,permit=controls(prepared,lease)
            def authorize(ticket,request,identity):return schemas.DispatchApproval(permit=ticket,budget=basis)
            def consume(approval):
                if mutate:
                    altered=json.loads(prepared.raw);altered["max_tokens"]=8192
                    object.__setattr__(prepared,"raw",canonical(altered))
                return schemas.ConsumeReceipt(permit=permit,approval_digest=digest(canonical(approval.model_dump())))
            if mutate:
                with pytest.raises(ProviderFailure):probe.begin(connection,lease=lease,permit=permit,price=price,basis=basis,current_authorizer=authorize,consume_permit=consume)
                assert sink.sends==[]
            else:
                probe.begin(connection,lease=lease,permit=permit,price=price,basis=basis,current_authorizer=authorize,consume_permit=consume)
                raw,=sink.sends
                assert raw.split(b"\r\n\r\n",1)[1]==original
                assert adapter.final_request_bytes(prepared)==original
    finally:connection.close()


def test_public_paid_entry_stays_closed_without_loading_or_connecting():
    prepared=adapter.prepare_request("Bounded offline question",packet())
    with pytest.raises(ProviderFailure,match="paid_disabled"):adapter.DeepSeekAdapter().preconnect(prepared)
