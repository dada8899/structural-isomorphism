"""File-backed SQL guard adoption rehearsal; no Main/network/real grants."""
from contextlib import closing
import sqlite3

import pytest

from tests.test_external_first_answer_fixture_writer import setup,approved,balance
from tests.test_external_first_answer_contract import NOW
from web.backend.research.external_first_answer_contract import CAP_UNITS, MIN_RISK_MARGIN_UNITS, ContractError
from web.backend.research.external_first_answer_file_writer import (
    CandidateFileWriter, TRIGGER, _OLD, approve_isolated_file, money_trigger, install_closed_hooks, unresolved_external,
)
from web.backend.research.external_first_answer_state import TABLE
from web.backend.research.plan_native_financial import TABLES, declarations, install_hook
from web.backend.research.plan_financial import TABLES as EARLIER_TABLES
from web.backend.research.provider_schemas import canonical
from web.backend.research.store import V5_SCHEMA


def fixture(path):
    path.chmod(0o700)
    marker=path/"STRUCTURE-EXTERNAL-LEDGER-FIXTURE"
    marker.write_bytes(b"isolated external ledger candidate, no provider\n");marker.chmod(0o600)
    db=path/"ledger.sqlite3"
    conn=sqlite3.connect(db,isolation_level=None)
    db.chmod(0o600)
    account=setup(conn)
    args=approved(conn,account)
    for statement in (*TABLES,*EARLIER_TABLES,V5_SCHEMA["research_reservations"]):
        conn.execute(statement)
    conn.execute("""INSERT INTO research_plan_native_funding
      VALUES(1,'controlled_fixture','authorized',?,?,'fixture-gate','fixture-ref',?,?,'same-account',
             'fixture-incarnation',1,?,?,?,'fixture-net',NULL,NULL,1)""",
      (args[2].principal_id,args[2].auth_generation,"a"*64,account,CAP_UNITS,MIN_RISK_MARGIN_UNITS,"b"*64))
    for name in (TRIGGER,"research_native_money_no_replace","research_native_money_no_delete"):
        conn.execute(next(sql for sql in declarations() if sql.startswith("CREATE TRIGGER "+name+" ")))
    install_hook(conn)
    proof=approve_isolated_file(db)
    return conn,db,proof,args


def adopt(conn):
    original=conn.execute("SELECT sql FROM sqlite_schema WHERE name=?",(TRIGGER,)).fetchone()[0]
    new=money_trigger(original)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DROP TRIGGER "+TRIGGER)
        conn.execute(new)
        conn.commit()
    except BaseException:
        conn.rollback();raise


def test_file_shared_atomic_guard_closed_by_default_and_reopen(tmp_path):
    conn,path,proof,args=fixture(tmp_path)
    with closing(conn):
        with pytest.raises(ContractError,match="external_file_catalog_unbound"):
            CandidateFileWriter(conn,proof)
        with pytest.raises(sqlite3.IntegrityError,match="native plan money authority required"):
            conn.execute("UPDATE research_funding_accounts SET held=1")
        with pytest.raises(ContractError,match="native_catalog_not_exact"):
            money_trigger(_OLD.replace("!=1","!=0"))
        adopt(conn)
        install_closed_hooks(conn)
        with pytest.raises(sqlite3.IntegrityError,match="native plan money authority required"):
            conn.execute("UPDATE research_funding_accounts SET held=1")
        writer=CandidateFileWriter(conn,proof)
        with pytest.raises(sqlite3.IntegrityError,match="native plan money authority required"):
            conn.execute("UPDATE research_funding_accounts SET held=1")
        writer.confirm(*args)
        writer.reserve(*args,now=NOW)
        assert balance(conn)==(1,1000,0)
        assert writer.consume(*args,now=NOW)==args[1].preview.raw_request
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        install_hook(conn)
        writer=CandidateFileWriter(conn,proof)
        with pytest.raises(ContractError,match="legacy_unknown_reconcile_only"):
            writer.consume(*args,now=NOW)
        assert balance(conn)==(1,1000,0)
        assert conn.execute("SELECT state FROM "+TABLE).fetchone()==("consumed",)
        candidate=canonical({"status":"candidate","explanation":"反馈滞后可能造成超调。",
            "assumptions":["动作影响后续读数。"],"next_check":"比较不同时延的结果。","evidence_status":"not_checked"})
        assert writer.finish(*args,candidate=candidate)=="returned"
        assert balance(conn)==(1,0,1000)
        assert writer.read(*args)==writer.read(*args)
        with pytest.raises(sqlite3.IntegrityError,match="native economic account retained"):
            conn.execute("DELETE FROM research_funding_accounts")


def test_file_writer_never_releases_unknown_and_rejects_replaced_inode(tmp_path):
    conn,path,proof,args=fixture(tmp_path)
    with closing(conn):
        adopt(conn)
        writer=CandidateFileWriter(conn,proof)
        writer.confirm(*args)
        writer.reserve(*args,now=NOW)
        writer.consume(*args,now=NOW)
        writer.finish(*args)
        assert balance(conn)==(1,1000,0)
        assert conn.execute("SELECT state FROM "+TABLE).fetchone()==("unknown",)
        assert unresolved_external(conn,args[1].account_id)
        with pytest.raises(ContractError,match="reconcile_original_only"):writer.finish(*args,candidate=b"{}")
        path.rename(path.with_suffix(".saved"))
        path.touch(mode=0o600)
        with pytest.raises(ContractError,match="external_file_identity_changed"):writer.read(*args)


def test_file_atomic_state_fault_does_not_leave_orphan_hold(tmp_path):
    conn,_,proof,args=fixture(tmp_path)
    with closing(conn):
        adopt(conn)
        writer=CandidateFileWriter(conn,proof)
        writer.confirm(*args)
        conn.execute("CREATE TEMP TRIGGER fixture_fault BEFORE UPDATE ON "+TABLE+
            " WHEN NEW.state='reserved' BEGIN SELECT RAISE(ABORT,'candidate reserve fault'); END")
        with pytest.raises(sqlite3.IntegrityError,match="candidate reserve fault"):
            writer.reserve(*args,now=NOW)
        assert balance(conn)==(1,0,0)
        assert conn.execute("SELECT state,version FROM "+TABLE).fetchone()==("confirmed",1)
        assert not unresolved_external(conn,args[1].account_id)
