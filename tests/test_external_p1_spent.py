"""Durable canary exclusion, without a live handle, key or network."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import os
import sqlite3
from uuid import uuid4

import pytest

from web.backend.research.errors import ResearchError
from web.backend.research.external_first_answer_contract import ContractError
from web.backend.services import external_live_operations as operations
from web.backend.services import external_live_production as production


def test_p1_marker_survives_row_erasure_and_different_go_key(tmp_path):
    first=str(uuid4())
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.execute("CREATE TABLE research_external_first_answer_runs(research_id,input_revision,state)")
        conn.execute("INSERT INTO research_external_first_answer_runs VALUES('owner-private-record',1,'returned')")
        fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
        try:
            assert not production._p1_spent_at(fd)
            production._claim_p1_at(fd,first)
            conn.execute("DELETE FROM research_external_first_answer_runs")
            assert production._p1_spent_at(fd)
            with pytest.raises(ContractError,match="external_canary_already_spent"):
                production._claim_p1_at(fd,str(uuid4()))
        finally:os.close(fd)
    marker=tmp_path/production._P1_SPENT
    expected=hashlib.sha256(b"structure-external-first-answer-p1-operation-v1\0"+first.encode()).hexdigest()
    assert marker.read_text()==expected+"\n"
    assert marker.stat().st_mode&0o777==0o600


def test_p1_first_write_claim_is_one_across_two_contenders(tmp_path):
    fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    try:
        def claim():
            try:production._claim_p1_at(fd,str(uuid4()));return "spent"
            except ContractError as error:return str(error)
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(lambda _:claim(),range(2)))==["external_canary_already_spent","spent"]
    finally:os.close(fd)


def test_unknown_receipt_write_still_never_reopens_p1(tmp_path,monkeypatch):
    fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    try:
        with monkeypatch.context() as fault:
            def fail(_):raise OSError("synthetic fsync acknowledgement failure")
            fault.setattr(production.os,"fsync",fail)
            with pytest.raises(OSError):
                production._claim_p1_at(fd,str(uuid4()))
        assert production._p1_spent_at(fd)
        with pytest.raises(ContractError,match="external_canary_already_spent"):
            production._claim_p1_at(fd,str(uuid4()))
    finally:os.close(fd)


@pytest.mark.parametrize("state",["confirmed","reserved","consumed","unknown","returned","closed_unsent"])
def test_live_preview_refuses_any_existing_revision_state(state):
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.execute("CREATE TABLE research_external_first_answer_runs(research_id,input_revision,state)")
        conn.execute("INSERT INTO research_external_first_answer_runs VALUES('current',1,?)",(state,))
        with pytest.raises(ResearchError,match="OPERATION_ALREADY_USED"):
            operations._require_unused_revision(conn,"current",1)
        operations._require_unused_revision(conn,"current",2)
