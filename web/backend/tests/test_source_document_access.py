"""Unprotected data counterexamples must never acquire native DOC authority."""
from dataclasses import replace
import json
import sqlite3
import pytest

from research.evidence_repository import DDL,EvidenceContext,EvidenceRepository
from research.evidence_schemas import encode,canonical,sha256
from research.source_document_access import (ActualAccessProfile,DocCompletion,RawReadScope,
    rawprep_read_scope,attach_access,freeze_doc_completion,finalize_doc_request,require_execution,require_private_cache)
from research.source_guard import raw_completion_forbidden
from research.errors import ResearchError
from web.backend.tests.test_source_document_raw import data_records,commitment_data,uid,H,T


@pytest.mark.parametrize('factory',[ActualAccessProfile,DocCompletion,attach_access,freeze_doc_completion,finalize_doc_request,require_execution,require_private_cache])
def test_b1_native_factories_and_finalizers_reject_data_booleans_callbacks(factory):
    with pytest.raises((PermissionError,ResearchError)):
        factory({'ready':True,'digest':H},profile_digest=H,still_authorized=lambda:True)


def test_read_scope_cannot_be_constructed_from_context_or_callback():
    with pytest.raises(PermissionError):RawReadScope(None,None,None,None,uid(1),uid(2))
    with pytest.raises(PermissionError):
        with rawprep_read_scope(None,None,None,None,uid(1),uid(2)):pass


def test_fixed_doc_data_is_rejected_before_paper_transport_can_birth_sender():
    from research.source_document_raw import catalog
    from research.source_policy import PinnedPublicTransport,SourceFailure
    calls=[]
    with pytest.raises(SourceFailure):
        PinnedPublicTransport().get(catalog()[0],still_authorized=lambda:calls.append(True) or True,owner_lease=None)
    assert not calls


def test_raw_plan_data_cannot_enter_old_session_dispatch_or_request_gate():
    from types import SimpleNamespace
    from research.source_workflow import SourceSession
    from research.source_document_raw import catalog
    plan=data_records()[0]
    # Failure-only unbound calls provide no actual session, store or permit.
    data=SimpleNamespace(plan=plan)
    with pytest.raises(ResearchError):SourceSession.run(data)
    with pytest.raises(ResearchError):
        with SourceSession.request_gate(data,plan,1,catalog()[0]):pass


def test_valid_c_data_and_null_query_cannot_unlock_native_worker_rule():
    from research.source_document_raw import rawprep_draft
    plan,artifact,receipt,_=data_records();c=commitment_data(plan,artifact,receipt)
    assert raw_completion_forbidden(None,'research_source_requests',{'closure_proof':canonical(c)})
    fields,*_=rawprep_draft(H)
    binding={'approval':{'query':None,'problem_digest':H,'plan_json':canonical(fields)}}
    assert raw_completion_forbidden(binding,'research_source_requests',{'outcome':'SENDING'})
    assert raw_completion_forbidden(binding,'research_source_requests',{'outcome':'SUCCEEDED'})
    assert raw_completion_forbidden(binding,'research_source_requests',{'outcome':'FAILED'})
    # This function is not used in close mode. Old UNKNOWN is not DocC.
    assert not raw_completion_forbidden(None,'research_source_requests',{'closure_proof':canonical({'proof_version':1})})
    with pytest.raises(ValueError):raw_completion_forbidden({'approval':{'query':None,'problem_digest':H,'plan_json':'{}'}},'research_source_requests',{})


def data_database():
    """An explicitly unprotected in-memory DB is only a negative data fixture."""
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('CREATE TABLE research_controls(id TEXT PRIMARY KEY)')
    conn.execute('INSERT INTO research_controls VALUES(?)',(uid(1),))
    for ddl in DDL:conn.execute(ddl)
    conn.execute('''CREATE TABLE research_source_requests(
        id TEXT,chain_id TEXT,task_id TEXT,step_id TEXT,semantic TEXT,target_digest TEXT,dispatch_id TEXT,
        ordinal INTEGER,write_epoch INTEGER,outcome TEXT,execution_closed INTEGER,closure_ref TEXT,closure_proof TEXT,
        owner_gate_identity TEXT,task_gate_identity TEXT,started_at TEXT,ended_at TEXT,http_status INTEGER,safe_code TEXT)''')
    return conn


def context():
    return EvidenceContext(research_id=uid(1),input_revision=1,task_id=uid(2),attempt=1,input_digest=H,
        principal_id=uid(11),principal_epoch=1,owner_epoch=1,acl_epoch=1,task_version=1,step_id=uid(9),step_version=1)


def insert_data(conn,record,kind,body=None):
    payload=encode(record)
    conn.execute('INSERT INTO research_evidence_objects VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (record.id,kind,record.research_id,record.input_revision,record.task_id,1,payload,sha256(payload.encode()),body,None,None))


@pytest.mark.parametrize('counter',['no_anchor','old_unknown','foreign_dispatch','self_hash_replacement','posthoc_missing'])
def test_self_consistent_ordinary_rows_cannot_replace_protected_request_commitment(counter):
    conn=data_database()
    try:
        plan,artifact,receipt,body=data_records();c=commitment_data(plan,artifact,receipt)
        original_c=canonical(c)
        if counter=='self_hash_replacement':
            body=b'<html>different self-consistent bytes</html>'
            observation=replace(artifact.observation,raw_length=len(body),content_length=len(body),raw_sha256=sha256(body))
            artifact=replace(artifact,observation=observation,raw_length=len(body),raw_sha256=sha256(body))
            receipt=replace(receipt,observation=observation)
        insert_data(conn,artifact,'snapshots',body);insert_data(conn,receipt,'executions');insert_data(conn,plan,'plans')
        if counter!='no_anchor':
            if counter=='foreign_dispatch':c['request']['dispatch_id']=uid(99)
            if counter=='old_unknown':proof=canonical({'proof_version':1})
            elif counter=='posthoc_missing':proof=None
            elif counter=='self_hash_replacement':proof=original_c
            else:proof=canonical(c)
            req=c['request']
            conn.execute('INSERT INTO research_source_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (artifact.request_id,req['chain_id'],artifact.task_id,req['step_id'],'fetch_source',req['target_digest'],
                 artifact.dispatch_id,1,1,'UNKNOWN' if counter=='old_unknown' else 'SUCCEEDED',1,receipt.id,proof,
                 canonical(req['owner_gate_identity']),canonical(req['task_gate_identity']),T,T,200,'none'))
        repo=EvidenceRepository(conn,lambda *args:True)
        with pytest.raises(ValueError):repo._raw_anchor(context(),artifact.id,None)
        # An ordinary self-hash row is not readable through the old paper or
        # provider port, even when this unit callback acknowledges a read.
        with pytest.raises(PermissionError):repo.get(context(),'snapshots',artifact.id)
        with pytest.raises(PermissionError):repo.put(context(),artifact,raw=body)
        with pytest.raises(PermissionError):repo.put_raw_in_completion(None,{'ready':True})
        with pytest.raises(PermissionError):repo.read_raw_candidate(context(),artifact.id,read_scope={'ready':True})
    finally:conn.close()
