"""Isolated SQL state shape only: the fixture hook is not Native authority."""
from contextlib import closing
import sqlite3
from uuid import uuid4

import pytest

from web.backend.research.external_first_answer_contract import PURPOSE
from web.backend.research.external_first_answer_state import DDL, GUARD, TABLE, StoredRunFence, consumer_boundary


def identifier():
    return str(uuid4())


@pytest.fixture
def db():
    # Identity-only FK parents, no balances, funding authority or mock ledger.
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE research_controls(id TEXT PRIMARY KEY);
            CREATE TABLE research_principals(id TEXT PRIMARY KEY);
            CREATE TABLE research_revisions(research_id TEXT, revision INTEGER, PRIMARY KEY(research_id,revision));
            CREATE TABLE research_funding_accounts(id TEXT PRIMARY KEY);
            CREATE TABLE research_reservations(id TEXT PRIMARY KEY);
        """)
        for ddl in DDL:
            conn.execute(ddl)
        rid,pid,account,reservation=[identifier() for _ in range(4)]
        for table,value in (("research_controls",rid),("research_principals",pid),
                            ("research_funding_accounts",account),("research_reservations",reservation)):
            conn.execute("INSERT INTO "+table+" VALUES(?)",(value,))
        conn.execute("INSERT INTO research_revisions VALUES(?,1)",(rid,))
        record=(identifier(),rid,pid,1,1,"a"*64,"b"*64,"c"*64,"d"*64,account,1,5_000,
                "confirmed",1,None,None,None,None)
        yield conn,record,record[0]


def insert(conn, row, *, replace=False):
    conn.execute(("INSERT OR REPLACE" if replace else "INSERT")+" INTO "+TABLE+" VALUES("+",".join("?" for _ in row)+")",row)


def test_uninstalled_writer_does_not_allow_any_sql_birth(db):
    conn,row,_=db
    with pytest.raises(sqlite3.OperationalError, match=GUARD):
        insert(conn,row)
    conn.create_function(GUARD,3,lambda *_:0)
    with pytest.raises(sqlite3.IntegrityError,match="insert denied"):
        insert(conn,row)
    assert conn.execute("SELECT count(*) FROM "+TABLE).fetchone()==(0,)


def test_unknown_cannot_replay_replace_erase_or_change_economic_binding(db):
    conn,row,reservation=db
    # Only to exercise SQL transition constraints in an isolated database.
    conn.create_function(GUARD,3,lambda *_:1)
    insert(conn,row)
    conn.execute("UPDATE "+TABLE+" SET state='reserved',version=2,reservation_ref=?",(reservation,))
    conn.execute("UPDATE "+TABLE+" SET state='consumed',version=3")
    conn.execute("UPDATE "+TABLE+" SET state='unknown',version=4")
    snapshot=conn.execute("SELECT * FROM "+TABLE).fetchone()
    for statement in ("UPDATE "+TABLE+" SET state='reserved',version=5",
                      "UPDATE "+TABLE+" SET request_digest='changed',version=5",
                      "UPDATE "+TABLE+" SET state='closed_unsent',version=5,reservation_ref=NULL",
                      "DELETE FROM "+TABLE):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement)
    with pytest.raises(sqlite3.IntegrityError):
        insert(conn,(identifier(),)+row[1:],replace=True)
    assert conn.execute("SELECT * FROM "+TABLE).fetchone()==snapshot


def test_known_return_requires_receipt_and_remains_immutable(db):
    conn,row,reservation=db
    conn.create_function(GUARD,3,lambda *_:1)
    insert(conn,row)
    conn.execute("UPDATE "+TABLE+" SET state='reserved',version=2,reservation_ref=?",(reservation,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE "+TABLE+" SET state='returned',version=3,receipt_digest=?",("e"*64,))
    conn.execute("UPDATE "+TABLE+" SET state='consumed',version=3")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE "+TABLE+" SET state='returned',version=4")
    conn.execute("UPDATE "+TABLE+" SET state='returned',version=4,receipt_digest=?,candidate_digest=?,candidate_json=?",("e"*64,"f"*64,'{}'))
    assert conn.execute("SELECT state,receipt_digest,candidate_digest FROM "+TABLE).fetchone()==("returned","e"*64,"f"*64)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE "+TABLE+" SET candidate_digest=NULL,version=5")


@pytest.mark.parametrize("state,action", [
    ("confirmed","shared_native_writer_unbound"),("reserved","shared_native_writer_unbound"),
    ("consumed","reconcile_original_only"),("unknown","reconcile_original_only"),
    ("returned","read_authorized_original_only"),("closed_unsent","closed_no_send"),
])
def test_consumer_cannot_reserve_consume_or_send_any_saved_shape(state,action):
    row=StoredRunFence(run_id=identifier(),purpose=PURPOSE,scope_digest="a"*64,request_digest="b"*64,
                       account_id=identifier(),funding_epoch=1,state=state,version=1)
    assert consumer_boundary(row,"a"*64,"b"*64)=={
        "state":"closed","next_action":action,"may_reserve":False,"may_consume":False,"may_send":False}
    assert consumer_boundary(row,"c"*64,"b"*64)["next_action"]==(
        "reconcile_original_only" if state in ("consumed","unknown") else "binding_changed_no_send")
