from contextlib import closing
import json
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sqlite3
import threading
import time
from uuid import uuid4

import pytest

from tests.test_external_first_answer_contract import NOW, confirm, problem, quote, revision
from web.backend.research.external_first_answer_contract import ContractError, prepare_closed_preview
from web.backend.research.external_first_answer_fixture_writer import FixtureWriter
from web.backend.research.external_first_answer_state import DDL, TABLE
from web.backend.research.provider_schemas import canonical
from web.backend.research.store import V5_SCHEMA


def setup(conn):
    conn.executescript("""
        CREATE TABLE research_controls(id TEXT PRIMARY KEY,owner_id TEXT,current_revision INT,
            version INT,owner_epoch INT,acl_epoch INT,lifecycle TEXT);
        CREATE TABLE research_principals(id TEXT PRIMARY KEY,session_generation TEXT,epoch INT,status TEXT);
        CREATE TABLE research_revisions(research_id TEXT,revision INT,digest TEXT,PRIMARY KEY(research_id,revision));
    """)
    conn.execute(V5_SCHEMA['research_funding_accounts'])
    for ddl in DDL:
        conn.execute(ddl)
    account=str(uuid4())
    conn.execute("""INSERT INTO research_funding_accounts(id,binding_id,mode,currency,provider)
                     VALUES(?,'same-account','live','CNY','deepseek')""",(account,))
    return account


def approved(conn,account,upper=1000):
    raw=problem();scope=revision(raw)
    q=quote(account_id=account,economic_binding='same-account',upper_units=upper)
    p=prepare_closed_preview(scope,raw,q,now=NOW)
    conn.execute("INSERT INTO research_principals VALUES(?,?,1,'active')",(scope.principal_id,scope.auth_generation))
    conn.execute("INSERT INTO research_controls VALUES(?,?,1,1,1,1,'active')",(scope.research_id,scope.principal_id))
    conn.execute("INSERT INTO research_revisions VALUES(?,1,?)",(scope.research_id,scope.problem_digest))
    grant=FixtureWriter.grant(scope,raw,p,q,confirm(p),balance=400_000_000,now=NOW,balance_until=NOW+30)
    return str(uuid4()),grant,scope


def balance(conn):
    return conn.execute("SELECT count(*),sum(held),sum(upper_booked) FROM research_funding_accounts").fetchone()


@pytest.mark.parametrize("unknown",[False,True])
def test_one_fixture_send_and_original_result_or_unknown_hold(unknown):
    with closing(sqlite3.connect(":memory:",isolation_level=None)) as conn:
        account=setup(conn)
        args=approved(conn,account)
        writer=FixtureWriter(conn)
        writer.confirm(*args)
        writer.reserve(*args,now=NOW)
        assert balance(conn)==(1,1000,0)
        payload=writer.consume(*args,now=NOW)
        seen=[]
        body=canonical({"status":"candidate","explanation":"若反馈滞后，动作可能过量。",
                        "assumptions":["动作改变下一轮测量。"],"next_check":"比较滞后变化。",
                        "evidence_status":"not_checked"})
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                seen.append(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200);self.end_headers()
                if not unknown:self.wfile.write(body)
        with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                with closing(HTTPConnection("127.0.0.1",server.server_port,timeout=3)) as http:
                    http.request("POST","/fixture",body=payload)
                    with http.getresponse() as response:out=response.read()
            finally:
                server.shutdown();thread.join(3)
                assert not thread.is_alive()
        assert seen==[args[1].preview.raw_request]
        with pytest.raises(ContractError,match="consume_unavailable"):
            writer.consume(*args,now=NOW)
        assert writer.finish(*args,candidate=out or None)==("unknown" if unknown else "returned")
        if unknown:
            assert balance(conn)==(1,1000,0)
            with pytest.raises(ContractError,match="result_unavailable"):writer.read(*args)
            other=approved(conn,account);writer.confirm(*other)
            with pytest.raises(ContractError,match="reconcile_original_only"):writer.reserve(*other,now=NOW)
        else:
            assert balance(conn)==(1,0,1000)
            first=writer.read(*args)
            assert json.loads(first)["candidate"]==json.loads(body) and first==writer.read(*args)
        with pytest.raises(ContractError,match="reconcile_original_only"):writer.finish(*args,candidate=body)


def test_money_rolls_back_when_state_write_aborts_and_owner_fence_rejects():
    with closing(sqlite3.connect(":memory:",isolation_level=None)) as conn:
        account=setup(conn);args=approved(conn,account)
        writer=FixtureWriter(conn);writer.confirm(*args)
        conn.execute("CREATE TEMP TRIGGER injected BEFORE UPDATE ON "+TABLE+
                     " WHEN NEW.state='reserved' BEGIN SELECT RAISE(ABORT,'fixture state fault'); END")
        with pytest.raises(sqlite3.IntegrityError,match="fixture state fault"):writer.reserve(*args,now=NOW)
        assert balance(conn)==(1,0,0)
        assert conn.execute("SELECT state FROM "+TABLE).fetchone()==("confirmed",)
        conn.execute("DROP TRIGGER injected")
        conn.execute("UPDATE research_controls SET acl_epoch=2")
        with pytest.raises(ContractError,match="revision_or_owner_changed"):writer.reserve(*args,now=NOW)
        assert balance(conn)==(1,0,0)


def test_two_connections_cannot_overbook_one_shared_account():
    uri=f"file:{uuid4()}?mode=memory&cache=shared"
    with closing(sqlite3.connect(uri,uri=True,isolation_level=None)) as setup_conn:
        account=setup(setup_conn)
        args=[approved(setup_conn,account,upper=200_000_000) for _ in range(2)]
        writer=FixtureWriter(setup_conn)
        for item in args:writer.confirm(*item)
        barrier=threading.Barrier(2)
        outcomes=[]
        def reserve(item):
            with closing(sqlite3.connect(uri,uri=True,isolation_level=None)) as conn:
                worker=FixtureWriter(conn)
                barrier.wait(3)
                for _ in range(50):
                    try:
                        worker.reserve(*item,now=NOW)
                        outcomes.append("reserved")
                        return
                    except sqlite3.OperationalError as exc:
                        if "locked" not in str(exc):raise
                        time.sleep(.005)
                    except ContractError as exc:
                        outcomes.append(str(exc))
                        return
        threads=[threading.Thread(target=reserve,args=(item,)) for item in args]
        for thread in threads:thread.start()
        for thread in threads:thread.join(4)
        assert not any(thread.is_alive() for thread in threads)
        assert sorted(outcomes)==["reserved","shared_budget_exhausted"]
        assert balance(setup_conn)==(1,200_000_000,0)


def test_no_fixture_writer_on_any_file_backed_database(tmp_path):
    with closing(sqlite3.connect(tmp_path/"not-a-fixture.sqlite3")) as conn:
        with pytest.raises(ContractError,match="isolated_fixture_required"):
            FixtureWriter(conn)


def test_existing_bookings_consume_the_same_cap_and_raw_money_write_stays_closed():
    with closing(sqlite3.connect(":memory:",isolation_level=None)) as conn:
        account=setup(conn)
        # Existing fixture exposure in the same physical ledger, before hooks.
        conn.execute("UPDATE research_funding_accounts SET settled=220000000,upper_booked=79000000")
        args=approved(conn,account,upper=2_000_000)
        writer=FixtureWriter(conn);writer.confirm(*args)
        with pytest.raises(ContractError,match="shared_budget_exhausted"):writer.reserve(*args,now=NOW)
        with pytest.raises(sqlite3.IntegrityError,match="money denied"):
            conn.execute("UPDATE research_funding_accounts SET upper_booked=0")
        assert balance(conn)==(1,0,79_000_000)
