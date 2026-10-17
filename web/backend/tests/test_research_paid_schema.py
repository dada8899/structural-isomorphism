"""Actual v4/v5 AuthStore graph and real owner leases; synthetic money only."""
from contextlib import contextmanager
import json
import sqlite3
from uuid import uuid4

import pytest

from .test_research_persistence import stack,create,problem,post
from .test_research_c0 import start as c0_start
from .research_http_fixture import ResearchHTTPFixture
from api import auth
from research import ResearchStore,ResearchRunner,BudgetLedger
from research.authorization import AccountIdentity,AuthorizationGate
from research.errors import ResearchError
from research.transport import FixtureTransport
from research.store import V5_SCHEMA,V5_AUX,V5_GUARDS
from research.paid_control import (schema_requirements,mint_stop_authority,mint_current_paid_authority,
    mint_trusted_cost_authority,StopAuthority,CurrentPaidAuthority,TrustedCostAuthority,UPPER_ENTRYPOINTS)
from research.provider_schemas import CallContext,PriceQuote,canonical,digest
from research.provider_schemas import ProviderObservation,CostObservation,Money
from research.service import ResearchService


def rows(path):
    with sqlite3.connect(path) as conn:
        return {name:(tuple(r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')),
            conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall())
            for (name,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def snapshot(path):
    with sqlite3.connect(path) as conn:
        objects=conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name").fetchall()
    return objects,rows(path)


@pytest.fixture
def legacy(stack,tmp_path,monkeypatch):
    client,path=stack
    monkeypatch.setenv("STRUCTURAL_C0_ENABLED","true")
    provider=ResearchHTTPFixture(tmp_path/"legacy-provider.sqlite3")
    try:
        with monkeypatch.context() as old:
            old.setattr(ResearchStore,"_migrate_v5",lambda self:None)
            old.setattr(ResearchStore,"_migrate_v6",lambda self:None)
            store=ResearchStore(auth._store());BudgetLedger(store).provision_fixture(provider.port)
            # Small trusted LOCAL test prices let all four real legacy states
            # coexist under the unchanged 10000-unit fixture account cap.
            with store.transaction(write=True) as conn:
                conn.execute("DELETE FROM research_price_revisions")
                for operation in ("discover_sources","compose_report"):
                    conn.execute("INSERT INTO research_price_revisions VALUES(?,?,?,'USD',6,0,0,0,0,100,'ceil_total','2099-01-01T00:00:00.000000Z')",(str(uuid4()),conn.execute("SELECT id FROM research_funding_accounts").fetchone()[0],operation))
            provider.costs={"discover_sources":10,"compose_report":10}
            runner=ResearchRunner(store)
            ids={}
            for state in ("SETTLED","HELD","SENT","UNKNOWN"):
                rid,tid=c0_start(client,"paid-migration-"+state)
                ids[state]=(rid,tid)
                if state=="SETTLED":assert runner.run_once(tid)=="COMPLETED"
                else:
                    step=runner.prepare(tid)
                    if state!="HELD":
                        connection=runner.send(tid,step["id"])
                        FixtureTransport.finish(connection)
                        if state=="UNKNOWN":runner.unknown(tid,step["id"])
            with sqlite3.connect(path) as conn:
                assert conn.execute("SELECT version FROM research_schema").fetchone()[0]==4
                assert set(r[0] for r in conn.execute("SELECT status FROM research_reservations"))=={"HELD","SENT","UNKNOWN","SETTLED"}
                assert conn.execute("SELECT settled,held FROM research_funding_accounts").fetchone()==(20,300)
                assert conn.execute("SELECT count(*) FROM research_billing_receipts").fetchone()[0]==2
        yield client,path,store,provider,ids
    finally:provider.close()


def test_nonempty_v4_graph_migrates_preserving_every_old_column_and_inode(legacy,v5_only):
    client,path,old,provider,ids=legacy
    before=rows(path)
    locks={p.name:p.stat().st_ino for p in (path.parent/"research-locks").glob("*.lock")}
    store=ResearchStore(auth._store())
    with store.transaction() as conn:
        assert conn.execute("SELECT version FROM research_schema").fetchone()[0]==5
        for table,(columns,values) in before.items():
            if table=="research_schema":continue
            selected=",".join('"'+c+'"' for c in columns)
            assert [tuple(r) for r in conn.execute(f'SELECT {selected} FROM "{table}" ORDER BY rowid')]==values,table
        assert tuple(conn.execute("SELECT settled,held,upper_booked,initial_prepaid_units,other_use_margin_units FROM research_funding_accounts").fetchone())==(20,300,0,10000,0)
        assert conn.execute("SELECT count(*) FROM research_cost_observations").fetchone()[0]==0
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]
    assert {p.name:p.stat().st_ino for p in (path.parent/"research-locks").glob("*.lock") }==locks
    assert client.get(f"/api/research/{ids['SETTLED'][0]}").json()["data"]["budget"]["known_cost"][0]["amount_units"]==20
    assert ResearchRunner(store).run_once(ids["SETTLED"][1])=="COMPLETED" and provider.count()==4
    ResearchStore(auth._store())


_FAULTS=[(phase,name) for phase in ("CREATE TABLE","INSERT INTO","DROP TABLE","ALTER TABLE") for name in V5_SCHEMA]
_FAULTS.extend((name,None) for name in ("FUNDING_DEFAULTS","COST_TABLE","ACTIVE_INDEX","SET_VERSION","COMMIT"))
_FAULTS.extend(("DDL",sql) for sql in (*V5_AUX,*V5_GUARDS))


@pytest.mark.parametrize("phase,table",_FAULTS)
def test_every_v5_replace_boundary_rolls_back_exact_v4(legacy,monkeypatch,phase,table,v5_only):
    _,path,store,_,_=legacy
    before=snapshot(path);original=sqlite3.connect;raised=[];restored=[]
    marker=table if phase=="DDL" else (phase+" "+table+("_v5" if phase in ("CREATE TABLE","INSERT INTO","ALTER TABLE") else "")) if table else {
        "FUNDING_DEFAULTS":"UPDATE research_funding_accounts_v5 SET","COST_TABLE":"CREATE TABLE research_cost_observations",
        "ACTIVE_INDEX":"CREATE UNIQUE INDEX IF NOT EXISTS research_one_active_task","SET_VERSION":"UPDATE research_schema SET version=5","COMMIT":None}[phase]
    class Fault(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if marker and sql.startswith(marker) and not raised:
                raised.append(True);raise sqlite3.OperationalError("owned v5 boundary fault")
            return super().execute(sql,*args,**kwargs)
        def commit(self):
            if phase=="COMMIT" and self.in_transaction and not raised:
                raised.append(True);raise sqlite3.OperationalError("owned v5 boundary fault")
            return super().commit()
        def close(self):
            restored.append(self.execute("PRAGMA foreign_keys").fetchone()[0]);super().close()
    monkeypatch.setattr(sqlite3,"connect",lambda *a,**k:original(*a,**k,factory=Fault))
    with pytest.raises(sqlite3.OperationalError,match="owned v5 boundary fault"):store._migrate_v5()
    assert raised and restored==[1]
    monkeypatch.setattr(sqlite3,"connect",original)
    assert snapshot(path)==before
    ResearchStore(auth._store())


@pytest.mark.parametrize("version",[0,7,99])
def test_unknown_version_rejected_without_mutation(legacy,version):
    _,path,_,_,_=legacy
    with sqlite3.connect(path) as conn:conn.execute("UPDATE research_schema SET version=?",(version,))
    before=snapshot(path)
    with pytest.raises(ResearchError) as error:ResearchStore(auth._store())
    assert error.value.code=="SCHEMA_UNSUPPORTED" and snapshot(path)==before


def identity(client):
    claims=auth._decode_jwt(client.cookies.get("phase_session"))
    return AccountIdentity(claims["sub"],claims["gen"],claims["jti"],claims["exp"])


@pytest.fixture
def current(stack):
    client,path=stack;rid=create(client)
    store=ResearchStore(auth._store())
    with store.transaction() as conn:
        principal=conn.execute("SELECT owner_id FROM research_controls WHERE id=?",(rid,)).fetchone()[0]
    return client,path,store,rid,principal


def test_schema_hook_is_pure_and_live_has_no_automatic_funds(current):
    _,path,store,_,_=current
    before=snapshot(path);requirements=schema_requirements()
    assert requirements.version==6 and len(requirements.definition_digest)==64
    assert UPPER_ENTRYPOINTS==("schema_requirements","reserve","authorize","consume","observe","cancel")
    assert snapshot(path)==before
    with store.transaction(write=True) as conn:
        fid,binding=str(uuid4()),str(uuid4())
        conn.execute("INSERT INTO research_funding_accounts(id,binding_id,provider) VALUES(?,?,'deepseek')",(fid,binding))
        row=conn.execute("SELECT * FROM research_funding_accounts WHERE id=?",(fid,)).fetchone()
        assert row["mode"]=="live" and row["status"]=="unverified" and row["cap"]==row["upper_booked"]==row["held"]==0
        assert row["initial_prepaid_units"] is row["other_use_margin_units"] is None
        with pytest.raises(sqlite3.IntegrityError):conn.execute("INSERT INTO research_funding_accounts(id,binding_id,provider) VALUES(?,?,'deepseek')",(str(uuid4()),binding))
        with pytest.raises(sqlite3.IntegrityError):conn.execute("UPDATE research_funding_accounts SET status='active' WHERE id=?",(fid,))


@pytest.mark.parametrize("column",["cap","settled","held","upper_booked","initial_prepaid_units","other_use_margin_units"])
@pytest.mark.parametrize("value",[-1,9223372036854775808.0,0.5])
def test_money_columns_reject_negative_float_overflow(current,column,value):
    _,_,store,_,_=current
    with store.transaction(write=True) as conn:
        fid=str(uuid4())
        conn.execute("INSERT INTO research_funding_accounts(id,binding_id,provider) VALUES(?,?,'deepseek')",(fid,str(uuid4())))
        with pytest.raises(sqlite3.IntegrityError):conn.execute(f"UPDATE research_funding_accounts SET {column}=? WHERE id=?",(value,fid))


def _stop_task(client,store,rid):
    with store.transaction(write=True) as conn:
        owner=conn.execute("SELECT * FROM research_controls WHERE id=?",(rid,)).fetchone()
        grant=conn.execute("SELECT id FROM research_grants WHERE research_id=?",(rid,)).fetchone()[0]
        tid=str(uuid4())
        conn.execute("""INSERT INTO research_tasks(id,research_id,principal_id,principal_epoch,owner_epoch,acl_epoch,grant_id,auth_generation,input_revision,input_digest,start_version,execution,phase,version,policy_revision,execution_mode,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,1,?,1,'QUEUED','queued',1,'c0-fixture-v1','offline_probe','2026-10-17T00:00:00.000000Z','2026-10-17T00:00:00.000000Z')""",(tid,rid,owner["owner_id"],owner["owner_epoch"],owner["owner_epoch"],owner["acl_epoch"],grant,identity(client).generation,"a"*64))
    return tid


def test_actual_stop_capability_current_connection_lease_and_transaction(current):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid);gate=AuthorizationGate(store)
    with gate.owner_gate(pid) as lease:
        with store.transaction(write=True) as conn:
            cap=mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))
            binding=cap.require(conn,"cancel")
            assert type(cap) is StopAuthority and binding.task_id==tid and binding.principal_id==pid and binding.task_version==1
            assert not hasattr(cap,"__dict__")
            with pytest.raises(PermissionError):cap.require(conn,"consume")
            with store.transaction() as other:
                with pytest.raises(PermissionError):cap.require(other,"cancel")
        with store.transaction(write=True) as later:
            with pytest.raises(PermissionError):cap.require(later,"cancel")
    with pytest.raises((PermissionError,sqlite3.ProgrammingError)):cap.require(conn,"cancel")


def test_commit_then_begin_same_connection_does_not_resurrect_capability(current):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid)
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        cap=mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))
        conn.commit();conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(PermissionError):cap.require(conn,"cancel")
        with pytest.raises(PermissionError):mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))


def test_expired_lease_revoked_scope_and_read_only_transaction_cannot_mint(current):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid)
    with AuthorizationGate(store).owner_gate(pid) as lease:
        with store.transaction() as conn:
            with pytest.raises(PermissionError):mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))
        with store.transaction(write=True) as conn:
            cap=mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))
            conn.execute("UPDATE research_grants SET scopes='[]' WHERE research_id=?",(rid,))
            assert conn.execute("SELECT version FROM research_grants WHERE research_id=?",(rid,)).fetchone()[0]==2
            with pytest.raises((ResearchError,PermissionError)):cap.require(conn,"cancel")
    with store.transaction(write=True) as conn:
        with pytest.raises(PermissionError):mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))


@pytest.mark.parametrize("typ",[CurrentPaidAuthority,StopAuthority,TrustedCostAuthority])
def test_dtos_bools_and_dicts_cannot_construct_server_authority(typ):
    for value in (True,{},None):
        with pytest.raises(TypeError):typ(value,value,"consume",lambda:True)


def test_plain_cost_dto_and_untyped_context_never_make_paid_authority(current):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid)
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        for value in (True,{},None):
            with pytest.raises(PermissionError):mint_trusted_cost_authority(conn,observation=value)
        with pytest.raises(PermissionError):mint_current_paid_authority(conn,store=store,lease=lease,identity=identity(client),context={},step_id=str(uuid4()),expected_task_version=1,expected_step_version=1,operation="consume",approval_ref=str(uuid4()))


def test_valid_context_and_provider_dto_still_have_no_paid_producer(current):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid)
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(tid,)).fetchone();sid=str(uuid4())
        conn.execute("UPDATE research_tasks SET policy_revision='deepseek-bounded-upper-v1' WHERE id=?",(tid,))
        conn.execute("UPDATE research_grants SET scopes='[\"read\",\"write\",\"execute\"]' WHERE id=?",(task["grant_id"],))
        grant=conn.execute("SELECT version FROM research_grants WHERE id=?",(task["grant_id"],)).fetchone()[0]
        conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state) VALUES(?,?,0,'model_report','PENDING')",(sid,tid))
        context=CallContext(principal_id=pid,principal_epoch=1,grant_id=task["grant_id"],grant_epoch=grant,owner_epoch=1,acl_epoch=1,research_id=rid,input_revision=1,input_digest="a"*64,task_id=tid,attempt=1,plan_id=str(uuid4()))
        with pytest.raises(ResearchError) as failure:
            mint_current_paid_authority(conn,store=store,lease=lease,identity=identity(client),context=context,step_id=sid,expected_task_version=1,expected_step_version=1,operation="consume",approval_ref=str(uuid4()))
        assert failure.value.code=="FEATURE_UNAVAILABLE"
        dispatch,reservation,price=str(uuid4()),str(uuid4()),str(uuid4())
        observation=ProviderObservation(context=context,dispatch_id=dispatch,request_digest="b"*64,evidence_digest="c"*64,response_digest=None,provider_ref=None,fingerprint_digest=None,usage=None,
            cost=CostObservation(reservation_id=reservation,dispatch_id=dispatch,usage_ref=None,kind="unknown",reserved_upper=Money(currency="USD",scale=6,amount_units=1),booked_upper=None,usage_priced_estimate=None,price_revision=price,basis_digest="d"*64),candidate=None,safe_code="response_unknown")
        with pytest.raises(ResearchError) as failure:mint_trusted_cost_authority(conn,observation=observation)
        assert failure.value.code=="FEATURE_UNAVAILABLE"


def test_real_pending_deletion_job_can_mint_stop_but_never_send(current):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid);account=identity(client)
    with AuthorizationGate(store).owner_gate(pid) as lease:
        with store.transaction() as conn:gate_id=conn.execute("SELECT gate_id FROM research_principals WHERE id=?",(pid,)).fetchone()[0]
        job=ResearchService(store).begin_account_deletion_locked(account.email,account.generation,gate_id,"synthetic cleanup binding")
        with store.transaction(write=True) as conn:
            version=conn.execute("SELECT version FROM research_tasks WHERE id=?",(tid,)).fetchone()[0]
            cap=mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=version,deletion_job_id=job)
            assert cap.require(conn,"cancel").deletion_job_id==job
            with pytest.raises(PermissionError):cap.require(conn,"consume")
            with pytest.raises((ResearchError,PermissionError)):mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=version,identity=account)
            conn.execute("UPDATE auth_deletion_jobs SET state='scrubbing' WHERE id=?",(job,))
            with pytest.raises(PermissionError):cap.require(conn,"cancel")


def bounded_rows(conn,current):
    client,_,store,rid,pid=current
    owner=conn.execute("SELECT * FROM research_controls WHERE id=?",(rid,)).fetchone()
    grant=conn.execute("SELECT id FROM research_grants WHERE research_id=?",(rid,)).fetchone()[0]
    tid,sid,fid,qid,reservation,permit,dispatch=(str(uuid4()) for _ in range(7))
    conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,cap,initial_prepaid_units,other_use_margin_units,status) VALUES(?,?,'live','deepseek',1000,1000,0,'active')",(fid,str(uuid4())))
    quote=PriceQuote(revision=qid,currency="USD",scale=6,peak_input_miss_units_per_million=1,peak_input_hit_units_per_million=0,peak_output_units_per_million=1,c_bound=1048576,o_bound=4096,output_basis="all_completion_request_cap_verified",rounding_guard=0,price_document_digest="a"*64,model_document_digest="b"*64,bound_basis_digest="c"*64,valid_until=2147483647)
    conn.execute("INSERT INTO research_price_revisions(id,account_id,operation,currency,scale,expires_at,policy_revision,quote_json,quote_digest) VALUES(?,?,'model_report','USD',6,'2099-01-01T00:00:00.000000Z','deepseek-bounded-upper-v1',?,?)",(qid,fid,canonical(quote.model_dump()).decode(),digest(canonical(quote.model_dump()))))
    conn.execute("""INSERT INTO research_tasks(id,research_id,principal_id,principal_epoch,owner_epoch,acl_epoch,grant_id,auth_generation,input_revision,input_digest,start_version,execution,phase,version,policy_revision,execution_mode,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,1,?,1,'RUNNING','analysis',1,'deepseek-bounded-upper-v1','offline_probe','2026-10-17T00:00:00.000000Z','2026-10-17T00:00:00.000000Z')""",(tid,rid,pid,owner["owner_epoch"],owner["owner_epoch"],owner["acl_epoch"],grant,identity(client).generation,"a"*64))
    conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state) VALUES(?,?,0,'model_report','SENDING')",(sid,tid))
    conn.execute("""INSERT INTO research_reservations(id,account_id,task_id,step_id,operation_key,price_revision,funding_epoch,max_cost,status,policy_revision,principal_id,auth_scope_digest,outbound_fingerprint)
        VALUES(?,?,?,?,?,?,1,2,'SENT','deepseek-bounded-upper-v1',?,?,?)""",(reservation,fid,tid,sid,str(uuid4()),qid,pid,"d"*64,"e"*64))
    conn.execute("""INSERT INTO research_dispatch_permits(id,step_id,reservation_id,dispatch_id,state,expires_at,policy_revision,request_digest,evidence_digest,price_digest,budget_basis_digest,authorization_context_digest,authorized_task_version,authorized_step_version)
        VALUES(?,?,?,?,'consumed','2099-01-01T00:00:00.000000Z','deepseek-bounded-upper-v1',?,?,?,?,?,1,1)""",(permit,sid,reservation,dispatch,"a"*64,"b"*64,digest(canonical(quote.model_dump())),"c"*64,"d"*64))
    return fid,qid,reservation,dispatch


def insert_cost(conn,ids,usage,**changes):
    fid,price,reservation,dispatch=ids
    data=dict(id=str(uuid4()),account_id=fid,reservation_id=reservation,dispatch_id=dispatch,policy_revision="deepseek-bounded-upper-v1",kind="estimated_upper",response_digest="a"*64,usage_ref="b"*64,provider_response_ref="synthetic-response",usage_json=json.dumps(usage),observation_digest="d"*64,reserved_upper=2,booked_upper=2,actual_charge=None,usage_priced_estimate_units=1,price_revision=price,basis_digest="c"*64,safe_code="ok",observed_at="2026-10-17T00:00:00.000000Z")
    data.update(changes)
    conn.execute("INSERT INTO research_cost_observations ("+",".join(data)+") VALUES("+",".join("?" for _ in data)+")",tuple(data.values()))


_USAGE={"prompt_tokens":2,"completion_tokens":1,"total_tokens":3,"prompt_cache_hit_tokens":1,"prompt_cache_miss_tokens":1,"cached_tokens":1,"reasoning_tokens":0}


def test_cost_is_append_only_no_actual_or_private_body_and_policy_does_not_wash(current):
    _,_,store,_,_=current
    with store.transaction(write=True) as conn:
        ids=bounded_rows(conn,current)
        conn.execute("SAVEPOINT original_cost")
        insert_cost(conn,ids,_USAGE)
        assert tuple(conn.execute("SELECT reserved_upper,booked_upper,actual_charge FROM research_cost_observations").fetchone())==(2,2,None)
        for sql in ("DELETE FROM research_cost_observations","UPDATE research_cost_observations SET actual_charge=0"):
            with pytest.raises(sqlite3.IntegrityError):conn.execute(sql)
        conn.execute("ROLLBACK TO original_cost");conn.execute("RELEASE original_cost")
        assert conn.execute("SELECT count(*) FROM research_cost_observations").fetchone()[0]==0
        for changes in ({"actual_charge":0},{"booked_upper":1},{"basis_digest":"f"*64},{"usage_json":'{"content":"SECRET"}'},{"usage_json":'{"prompt_tokens":true}'},{"usage_json":json.dumps({**_USAGE,"total_tokens":4})}):
            with pytest.raises(sqlite3.IntegrityError):insert_cost(conn,ids,_USAGE,**changes)
            assert conn.execute("SELECT count(*) FROM research_cost_observations").fetchone()[0]==0
        insert_cost(conn,ids,_USAGE)
        with pytest.raises(sqlite3.IntegrityError):conn.execute("UPDATE research_reservations SET policy_revision='c0-fixture-v1' WHERE id=?",(ids[2],))


def test_lifetime_cap_and_currency_do_not_change_with_epoch_and_alias(current):
    _,_,store,_,_=current
    with store.transaction(write=True) as conn:
        fid,_,_,_=bounded_rows(conn,current)
        conn.execute("UPDATE research_funding_accounts SET settled=1001,held=2,upper_booked=3,status='blocked',funding_epoch=2 WHERE id=?",(fid,))
        assert tuple(conn.execute("SELECT cap,settled,held,upper_booked FROM research_funding_accounts WHERE id=?",(fid,)).fetchone())==(1000,1001,2,3)
        for statement in ("cap=2000","initial_prepaid_units=2000","other_use_margin_units=1","binding_id='alias'","currency='CNY'","funding_epoch=1"):
            with pytest.raises(sqlite3.IntegrityError):conn.execute("UPDATE research_funding_accounts SET "+statement+" WHERE id=?",(fid,))
        with pytest.raises(sqlite3.IntegrityError,match="price account currency binding"):
            conn.execute("INSERT INTO research_price_revisions(id,account_id,operation,currency,scale,expires_at,policy_revision,quote_json,quote_digest) VALUES(?,?,'model_report','CNY',6,'2099','deepseek-bounded-upper-v1','{}',?)",(str(uuid4()),fid,"a"*64))


def test_legacy_unknown_cannot_turn_upper_or_change_policy(legacy):
    _,_,old,_,_=legacy
    store=ResearchStore(auth._store())
    with store.transaction(write=True) as conn:
        row=conn.execute("SELECT id FROM research_reservations WHERE status='UNKNOWN'").fetchone()
        with pytest.raises(sqlite3.IntegrityError):conn.execute("UPDATE research_reservations SET status='UPPER_BOOKED' WHERE id=?",(row[0],))
        with pytest.raises(sqlite3.IntegrityError):conn.execute("UPDATE research_reservations SET policy_revision='deepseek-bounded-upper-v1' WHERE id=?",(row[0],))
        assert conn.execute("SELECT status FROM research_reservations WHERE id=?",(row[0],)).fetchone()[0]=="UNKNOWN"


def test_open_outbound_unique_ignores_rotating_epochs_task_key_and_scope(current):
    _,_,store,_,_=current
    with store.transaction(write=True) as conn:
        fid,price,reservation,_=bounded_rows(conn,current)
        original=dict(conn.execute("SELECT * FROM research_reservations WHERE id=?",(reservation,)).fetchone())
        task=dict(conn.execute("SELECT * FROM research_tasks WHERE id=?",(original["task_id"],)).fetchone())
        conn.execute("UPDATE research_tasks SET execution='CANCELLED',stop_requested=1 WHERE id=?",(task["id"],))
        task.update(id=str(uuid4()),execution="RUNNING",stop_requested=0,start_version=2)
        conn.execute("INSERT INTO research_tasks ("+",".join(task)+") VALUES("+",".join("?" for _ in task)+")",tuple(task.values()))
        sid=str(uuid4());conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state) VALUES(?,?,0,'model_report','SENDING')",(sid,task["id"]))
        conn.execute("UPDATE research_funding_accounts SET funding_epoch=2 WHERE id=?",(fid,))
        changed={**original,"id":str(uuid4()),"task_id":task["id"],"step_id":sid,"operation_key":str(uuid4()),"funding_epoch":2,"auth_scope_digest":"f"*64}
        with pytest.raises(sqlite3.IntegrityError,match="research_reservations.account_id"):
            conn.execute("INSERT INTO research_reservations ("+",".join(changed)+") VALUES("+",".join("?" for _ in changed)+")",tuple(changed.values()))
        columns=[r[2] for r in conn.execute("PRAGMA index_info(research_bounded_open_operation)")]
        assert columns==["account_id","principal_id","outbound_fingerprint"]


@pytest.mark.parametrize("restart",["BEGIN IMMEDIATE","SAVEPOINT cached_scope"])
@pytest.mark.parametrize("api",["connection","cursor"])
def test_implicit_rollback_then_cached_restart_never_revives_stop(current,restart,api):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid)
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        executor=conn if api=="connection" else conn.cursor()
        if restart.startswith("SAVEPOINT"):
            executor.execute(restart);executor.execute("RELEASE cached_scope")
        cap=mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))
        assert cap.require(conn,"cancel").task_id==tid
        with pytest.raises(sqlite3.IntegrityError):executor.execute("INSERT OR ROLLBACK INTO research_schema(id,version) VALUES(1,5)")
        assert not conn.in_transaction
        executor.execute(restart)
        assert conn.in_transaction
        with pytest.raises(PermissionError):cap.require(conn,"cancel")
        with pytest.raises(PermissionError):mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))
        if api=="cursor":executor.close()


@pytest.mark.parametrize("ending",["commit","rollback","sql_commit","sql_rollback","executescript"])
def test_explicit_transaction_end_controls_still_retire_stop(current,ending):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid)
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        cap=mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))
        if ending=="commit":conn.commit()
        elif ending=="rollback":conn.rollback()
        elif ending=="sql_commit":conn.execute("COMMIT")
        elif ending=="sql_rollback":conn.execute("ROLLBACK")
        else:conn.executescript("SELECT 1;")
        assert not conn.in_transaction
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(PermissionError):cap.require(conn,"cancel")


def test_inner_savepoint_does_not_end_current_stop_scope(current):
    client,_,store,rid,pid=current;tid=_stop_task(client,store,rid)
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        cap=mint_stop_authority(conn,store=store,lease=lease,principal_id=pid,task_id=tid,expected_task_version=1,identity=identity(client))
        conn.execute("SAVEPOINT inner_scope");conn.execute("SELECT 1")
        conn.execute("ROLLBACK TO inner_scope");conn.execute("RELEASE inner_scope")
        assert cap.require(conn,"cancel").task_id==tid


def replace_row(conn,table,row):
    conn.execute("INSERT OR REPLACE INTO "+table+" ("+",".join('"'+key+'"' for key in row)+") VALUES("+",".join("?" for _ in row)+")",tuple(row.values()))


@pytest.mark.parametrize("conflict",["primary","binding"])
def test_funding_replace_conflicts_do_not_reset_original_cap(current,conflict):
    _,_,store,_,_=current
    with store.transaction(write=True) as conn:
        conn.execute("PRAGMA recursive_triggers=OFF")
        fid,_,_,_=bounded_rows(conn,current)
        original=dict(conn.execute("SELECT * FROM research_funding_accounts WHERE id=?",(fid,)).fetchone())
        changed={**original,"cap":2000,"initial_prepaid_units":2000}
        if conflict=="binding":changed["id"]=str(uuid4())
        else:changed["binding_id"]=str(uuid4())
        with pytest.raises(sqlite3.IntegrityError,match="replacement forbidden"):replace_row(conn,"research_funding_accounts",changed)
        assert dict(conn.execute("SELECT * FROM research_funding_accounts WHERE id=?",(fid,)).fetchone())==original
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]
        conn.execute("UPDATE research_funding_accounts SET held=held+1,version=version+1 WHERE id=?",(fid,))
        assert conn.execute("SELECT held FROM research_funding_accounts WHERE id=?",(fid,)).fetchone()[0]==original["held"]+1
        with pytest.raises(sqlite3.IntegrityError):conn.execute("DELETE FROM research_funding_accounts WHERE id=?",(fid,))


@pytest.mark.parametrize("conflict",["primary","observation_unique","upper_partial_unique"])
def test_cost_replace_cannot_erase_any_immutable_unique_conflict(current,conflict):
    _,_,store,_,_=current
    with store.transaction(write=True) as conn:
        conn.execute("PRAGMA recursive_triggers=OFF")
        ids=bounded_rows(conn,current);insert_cost(conn,ids,_USAGE)
        original=dict(conn.execute("SELECT * FROM research_cost_observations").fetchone())
        changed={**original,"safe_code":"body_invalid"}
        if conflict=="primary":changed.update(observation_digest="e"*64,kind="anomaly",booked_upper=None)
        else:changed["id"]=str(uuid4())
        if conflict=="upper_partial_unique":changed["observation_digest"]="f"*64
        with pytest.raises(sqlite3.IntegrityError,match="replacement forbidden"):replace_row(conn,"research_cost_observations",changed)
        assert dict(conn.execute("SELECT * FROM research_cost_observations").fetchone())==original
        # An independent anomaly fact can still be appended without rewriting
        # the first observation or pretending an excess charge did not happen.
        insert_cost(conn,ids,_USAGE,id=str(uuid4()),observation_digest="1"*64,kind="anomaly",booked_upper=None,safe_code="conflict")
        assert conn.execute("SELECT count(*) FROM research_cost_observations").fetchone()[0]==2
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]


def test_other_immutable_financial_unique_keys_reject_replace(legacy):
    _,_,_,_,_=legacy
    store=ResearchStore(auth._store())
    with store.transaction(write=True) as conn:
        conn.execute("PRAGMA recursive_triggers=OFF")
        for table,unique in (("research_balance_snapshots",None),("research_price_revisions","operation"),("research_billing_receipts","provider_ref")):
            original=dict(conn.execute("SELECT * FROM "+table+" LIMIT 1").fetchone())
            with pytest.raises(sqlite3.IntegrityError,match="replacement forbidden"):replace_row(conn,table,original)
            if unique:
                changed={**original,"id":str(uuid4())}
                with pytest.raises(sqlite3.IntegrityError,match="replacement forbidden"):replace_row(conn,table,changed)
            assert dict(conn.execute("SELECT * FROM "+table+" WHERE id=?",(original["id"],)).fetchone())==original
        assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]


def test_ddl_tokens_preserve_identifier_and_keyword_boundaries():
    normalize=ResearchStore._normalize_sql
    baseline="CREATE TABLE research_example (id TEXT PRIMARY KEY)"
    assert normalize(baseline)==normalize('CREATE TABLE "research_example" ( id TEXT PRIMARY KEY )')
    assert normalize(baseline)!=normalize('CREATE TABLE research_example ("id TEXT" PRIMARY KEY)')
    assert normalize(baseline)!=normalize('CREATE TABLE research_example (idTEXT PRIMARY KEY)')
    assert normalize("CHECK(x='USD')")!=normalize("CHECK(x='U SD')")


def test_v5_reopen_rejects_real_quoted_column_drift_before_selecting_id(current):
    _,path,store,_,_=current
    from research.store import COST_SCHEMA
    with store.transaction(write=True) as conn:
        assert conn.execute("SELECT count(*) FROM research_cost_observations").fetchone()[0]==0
        conn.execute("DROP TABLE research_cost_observations")
        conn.execute(COST_SCHEMA.replace("id TEXT PRIMARY KEY",'"id TEXT" PRIMARY KEY',1))
    before=snapshot(path)
    with pytest.raises(ResearchError) as failure:ResearchStore(auth._store())
    assert failure.value.code=="SCHEMA_UNSUPPORTED" and snapshot(path)==before


@pytest.fixture
def v5_only(monkeypatch):
    monkeypatch.setattr(ResearchStore,"_migrate_v6",lambda self:None)
