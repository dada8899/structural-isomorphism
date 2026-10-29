"""Whole UTF-8 revision projection budget; no truncation or partial writes."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest

from .test_research_persistence import stack,post
from research.schemas import ProblemInput
from research.projection import projection_bytes,require_revision_budget,REVISION_PROJECTION_BUDGET,ResearchProjection
from research import ResearchStore
from research.errors import ResearchError
from api import auth
from .test_research_method_body_types import binding_data


def maximum_problem():
    emoji='😀'
    return ProblemInput.model_validate(dict(entry='phenomenon',original_input=emoji*4000,objective=emoji*1000,summary=emoji*1000,
        variables=[dict(id='v'+str(i).zfill(31),label=emoji*120,role='constraint',unit_id='count_per_workday',observation=emoji*400,provenance='system_proposed') for i in range(12)],
        constraints=[emoji*120]*12,unknowns=[emoji*120]*12,confirmed=False)).model_dump(mode='json',exclude={'formula_draft'})


def test_cumulative_actual_unicode_revision_save_is_atomic_and_old_records_remain_readable(stack):
    client,_=stack;body=maximum_problem()
    created=post(client,'/api/research',{'problem':body},'budget-create')
    assert created.status_code==200,created.text
    rid=created.json()['data']['research']['id'];store=ResearchStore(auth._store())
    for revision in range(1,5):
        response=post(client,f'/api/research/{rid}/revisions',{'expected_revision':revision,'problem':body},'budget-rev-'+str(revision))
        assert response.status_code==200,response.text
    with store.transaction() as conn:
        before=[tuple(r) for r in conn.execute('SELECT * FROM research_revisions ORDER BY revision')]
        cache=conn.execute('SELECT count(*) FROM research_idempotency').fetchone()[0]
    rejected=post(client,f'/api/research/{rid}/revisions',{'expected_revision':5,'problem':body},'budget-overflow')
    assert rejected.status_code==413 and rejected.json()['error']['code']=='PAYLOAD_LIMIT'
    with store.transaction() as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM research_revisions ORDER BY revision')]==before
        assert conn.execute('SELECT count(*) FROM research_idempotency').fetchone()[0]==cache
        assert conn.execute('SELECT current_revision,version FROM research_controls').fetchone()[:]==(5,5)
    read=client.get(f'/api/research/{rid}')
    assert read.status_code==200 and len(read.content)<=512*1024,read.text[:100]
    assert len(read.json()['data']['revisions'])==5
    assert all(r['original_input']==body['original_input'] for r in read.json()['data']['revisions'])


def test_revision_budget_counts_both_array_and_largest_selected_copy():
    # Exact byte boundary, not a character count or a single current record.
    padding=REVISION_PROJECTION_BUDGET//2-4
    record={'x':'a'*padding};records=[record]
    while projection_bytes(records)+projection_bytes(record)>REVISION_PROJECTION_BUDGET:record['x']=record['x'][:-1]
    require_revision_budget(records)
    record['x']+='😀'
    with pytest.raises(ResearchError):require_revision_budget(records)


def test_over_budget_key_is_unconsumed_and_concurrent_save_cannot_bypass_limit(stack):
    client,_=stack;body=maximum_problem()
    created=post(client,'/api/research',{'problem':body},'atomic-budget-create');rid=created.json()['data']['research']['id']
    for revision in range(1,5):assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':revision,'problem':body},'atomic-'+str(revision)).status_code==200
    assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':5,'problem':body},'unconsumed-budget-key').status_code==413
    from .test_research_persistence import problem
    payload={'expected_revision':5,'problem':problem('Smaller revision fits after an over-budget attempt')}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda key:post(client,f'/api/research/{rid}/revisions',payload,key),['unconsumed-budget-key','concurrent-budget-key']))
    assert sorted(r.status_code for r in responses)==[200,409],[r.text for r in responses]
    store=ResearchStore(auth._store())
    with store.transaction() as conn:
        assert conn.execute('SELECT count(*) FROM research_revisions WHERE research_id=?',(rid,)).fetchone()[0]==6
        require_revision_budget(ResearchProjection.revision_records(conn,rid))


def test_legacy_overlimit_is_explicit_413_without_truncating_or_rewriting(stack):
    from research.service import canonical,digest
    client,_=stack;body=maximum_problem();rid=post(client,'/api/research',{'problem':body}).json()['data']['research']['id']
    store=ResearchStore(auth._store())
    # Simulate saved pre-budget revisions, never a provider candidate or authority.
    with store.transaction(write=True) as conn:
        for revision in range(2,10):conn.execute('INSERT INTO research_revisions VALUES(?,?,?,?,?)',(rid,revision,canonical(body),digest(body),'2026-10-17T00:00:00.000000Z'))
        conn.execute('UPDATE research_controls SET current_revision=9,version=9 WHERE id=?',(rid,))
        before=[tuple(row) for row in conn.execute('SELECT * FROM research_revisions WHERE research_id=? ORDER BY revision',(rid,))]
        keys=conn.execute('SELECT count(*) FROM research_idempotency').fetchone()[0]
    read=client.get(f'/api/research/{rid}')
    assert read.status_code==413 and read.json()['error']['code']=='PAYLOAD_LIMIT',read.text
    assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':9,'problem':body},'old-overflow-save').status_code==413
    with store.transaction() as conn:
        assert [tuple(row) for row in conn.execute('SELECT * FROM research_revisions WHERE research_id=? ORDER BY revision',(rid,))]==before
        assert conn.execute('SELECT count(*) FROM research_idempotency').fetchone()[0]==keys


def test_complete_envelope_extreme_preserves_128k_headroom_with_real_outbound_cap(stack,binding_data,record_property):
    """Complete shape witness, separate from actual B/typed authorization tests.

    Revisions use real HTTP saves. Method body uses the canonical data codec;
    citations use the exact final outbound template, not unconstrained fields.
    No constructed DTO here is passed to a protected reader or writer.
    """
    from copy import deepcopy
    from research.projection import ResearchProjection,RESEARCH_RESPONSE_LIMIT
    from research.provider_schemas import EvidencePacket,EvidenceHandle,CallContext,canonical,digest,ProviderFailure
    from research.provider_adapter import prepare_request,final_request_bytes
    from research.method_body_codec import encode_method_body,decode_method_body
    from research.method_body_types import MethodBodyValidationError
    from research.service import digest as problem_digest
    client,_=stack;body=maximum_problem();body['confirmed']=True
    rid=post(client,'/api/research',{'problem':body},'whole-budget-create').json()['data']['research']['id']
    for revision in range(1,5):assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':revision,'problem':body},'whole-budget-'+str(revision)).status_code==200
    store=ResearchStore(auth._store())
    with store.transaction() as conn:records=ResearchProjection.revision_records(conn,rid)
    thin=dict(body,original_input='😀'*4000,objective='',summary='Boundary witness',variables=[],constraints=[],unknowns=[])
    record={'research_id':rid,'revision':6,**thin,'digest':problem_digest(thin),'created_at':'2026-10-17T00:00:00.000000Z'}
    remaining=REVISION_PROJECTION_BUDGET-projection_bytes([*records,record])-max(map(projection_bytes,records))
    assert 0<=remaining<=1000,remaining
    thin['objective']='a'*remaining
    saved=post(client,f'/api/research/{rid}/revisions',{'expected_revision':5,'problem':thin},'whole-budget-boundary')
    assert saved.status_code==200,saved.text
    with store.transaction() as conn:
        records=ResearchProjection.revision_records(conn,rid)
        assert projection_bytes(records)+max(map(projection_bytes,records))==REVISION_PROJECTION_BUDGET
        with pytest.raises(ResearchError):
            require_revision_budget([*records[:-1],dict(records[-1],objective=records[-1]['objective']+'a')])
        envelope=ResearchProjection.build(conn,conn.execute('SELECT * FROM research_controls WHERE id=?',(rid,)).fetchone())
    # Choose the largest original question, as an explicit historical task can.
    envelope['data']['current_problem']=max(records,key=projection_bytes)
    candidate={'summary':'😀'*1000,'mechanisms':[dict(label='Shape witness',mechanism='😀'*1200,
        variable_map=[dict(source='😀'*120,target='😀'*120,rationale='😀'*400) for _ in range(8)],
        conditions=[],nontransferable=[],evidence_handles=['e1'])],
        'competing_explanations':[],'validation_plan':dict(measurement='m',outcome='o',falsification='f',stop_rule='s'),'gaps':['Unverified shape only']}
    # Move one legal field up to the complete canonical codec limit.
    best=None;low,high=0,2000
    while low<=high:
        size=(low+high)//2;trial=deepcopy(candidate)
        trial['mechanisms'][0]['conditions']=['a'*min(400,size-offset) for offset in range(0,size,400)]
        try:encoded=encode_method_body(trial,binding_data,digest(canonical(trial)))
        except MethodBodyValidationError:high=size-1
        else:best=(trial,encoded);low=size+1
    assert best is not None
    candidate,encoded=best
    decoded=decode_method_body(encoded.raw,binding_data,encoded.candidate_digest,encoded.envelope_digest)
    assert 32760<len(encoded.raw)<=32768
    context=CallContext(principal_id=str(uuid4()),principal_epoch=1,grant_id=str(uuid4()),grant_epoch=1,owner_epoch=1,acl_epoch=1,
        research_id=rid,input_revision=1,input_digest='a'*64,task_id=str(uuid4()),attempt=1,plan_id=str(uuid4()))
    handles=[]
    for index in range(20):
        text='😀'*20
        handles.append(EvidenceHandle(handle='e'+str(index+1),source_id=str(uuid4()),source_revision=2147483647,excerpt_id=str(uuid4()),
            title='😀'*20,attribution='😀'*20,extracted_text=text,extracted_digest=digest(text.encode()),start=0,end=len(text),quote=text,
            display_permission=True,may_send_to_provider=True))
    packet=EvidencePacket(context=context,handles=tuple(handles));prepared=prepare_request('a'*1000,packet)
    # Saturate the exact request cap with validated credit text, including JSON
    # escaping overhead. Unbounded 20-field citation sums are not admitted.
    for index in range(len(handles)):
        low,high=0,280;best_handle=handles[index]
        while low<=high:
            size=(low+high)//2;trial=handles[index].model_copy(update={'title':'😀'*20+'a'*size})
            proposed=[*handles];proposed[index]=trial
            try:proposal=prepare_request('a'*1000,EvidencePacket(context=context,handles=tuple(proposed)))
            except ProviderFailure:high=size-1
            else:best_handle=trial;low=size+1
        handles[index]=best_handle
        packet=EvidencePacket(context=context,handles=tuple(handles));prepared=prepare_request('a'*1000,packet)
        if len(prepared.raw)==16384:break
    final=final_request_bytes(prepared)
    assert len(final)==16384 and digest(final)==prepared.request_digest and packet.binding_digest()==prepared.evidence_digest
    citations=[handle.outbound() for handle in packet.handles]
    method=dict(schema_version='MethodHypothesisResultView-v1',result_ref=binding_data['result_ref'],input_revision=1,input_digest='a'*64,
        candidate_schema=binding_data['candidate_schema'],body_schema=binding_data['body_schema'],producer_revision=binding_data['producer_revision'],
        received_at=binding_data['received_at'],candidate_digest=encoded.candidate_digest,envelope_digest=encoded.envelope_digest,is_historical=True,
        execution_mode='offline_probe',model_analysis_ran=False,status='qualified_report',evidence='INSUFFICIENT',assessment='llm_inference',review='unreviewed',
        sections=decoded.candidate.model_dump(mode='json'),citations=citations)
    history=[dict(task_id=str(uuid4()),input_revision=2147483647,input_digest='a'*64,start_version=2147483647,execution='WAITING_EXTERNAL',
        is_historical=True,received_at='2026-10-17T00:00:00.000000Z',result_status='unavailable') for _ in range(20)]
    envelope['data'].update(method_result=method,method_result_state='available',is_historical=True,task_history=history,next_task_id=str(uuid4()),
        task=dict(id=str(uuid4()),version=2147483647,execution='COMPLETED',phase='synthesis',attempt=1,input_revision=2147483647,stop_requested=False,policy_revision='bounded_usage_upper_v2'),
        task_version=2147483647,task_event_cursor=2147483647,execution='COMPLETED',status='insufficient',report_status='qualified_report')
    full_size=projection_bytes(envelope)
    assert full_size<=RESEARCH_RESPONSE_LIMIT
    assert full_size-REVISION_PROJECTION_BUDGET<128*1024
    # Full serialization also covers the mutually exclusive legacy notes path.
    legacy=deepcopy(envelope);legacy['data'].pop('method_result');legacy['data']['notes']=['😀'*1200]*2
    assert projection_bytes(legacy)<=RESEARCH_RESPONSE_LIMIT
    for name,value in dict(revision_budget_bytes=REVISION_PROJECTION_BUDGET,method_body_bytes=len(encoded.raw),
        final_outbound_request_bytes=len(final),citations_bytes=projection_bytes(citations),task_history_bytes=projection_bytes(history),
        complete_envelope_bytes=full_size,remaining_response_bytes=RESEARCH_RESPONSE_LIMIT-full_size,legacy_envelope_bytes=projection_bytes(legacy)).items():
        record_property(name,value)
