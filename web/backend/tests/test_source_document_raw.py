"""Data examples only: no profile approval, native receipt or real raw GET."""
from dataclasses import asdict, replace
import json
import pytest

from research.evidence_schemas import canonical,sha256,encode,decode,DataSnapshot,AnalysisPlan
from research.source_document_raw import (
    CONTRACT,PROFILE_ID,GROUP,RAW_CAP,RawPrepPlan,RawArtifact,RawPrepRequestReceipt,RawPrepBundleReceipt,
    DocRef,ProfileRef,DocObservation,TransportRetirementAudit,catalog,rawprep_draft,decode_plan_spec,
    decode_commitment,common_fingerprint,idempotency_digest,quota_state,target_digest,read_query,strict_json,
)

H='a'*64
T='2026-10-24T00:00:00.000000Z'
def uid(number):return '00000000-0000-4000-8000-'+str(number).zfill(12)


def data_records(binding=None):
    """Self-consistent typed data is intentionally not a native output."""
    binding=binding or {'research_id':uid(1),'input_revision':1,'task_id':uid(2),'attempt':1,'input_digest':H}
    body=b'<html>codec data example; no observed HTTP</html>'
    profile=ProfileRef(id='data-example',revision=1,digest=H)
    fields,*_=rawprep_draft(H)
    spec=replace(decode_plan_spec(fields),access_profile_ref=profile,rights_digest=H)
    plan=RawPrepPlan(**binding,id=uid(3),record_schema='RawPrepPlan-v1',plan=spec,created_at=T)
    observation=DocObservation(requested_target=catalog()[0],observed_final_target=catalog()[0],http_status=200,
        content_type_header='text/html',media_type='text/html',content_encoding_header=None,
        effective_content_encoding='identity',content_length=len(body),transfer_encoding_header=None,location_header=None,
        attempted_at=T,request_sent_at=T,received_at=T,observed_failure_at=None,safe_code='none',body_complete=True,
        raw_length=len(body),raw_sha256=sha256(body),observed_lower_bound=None,job_digest=H)
    artifact=RawArtifact(**binding,id=uid(4),record_schema='RawArtifact-v1',doc_ref=catalog()[0].doc_ref,
        plan_id=plan.id,request_id=uid(5),dispatch_id=uid(6),access_profile_ref=profile,rights_digest=H,
        observation=observation,raw_length=len(body),raw_sha256=sha256(body),origin='live',document_identity='unverified',
        parser_profile=None,extracted_digest=None,regions=())
    retirement=TransportRetirementAudit(protocol='doc-transport-retirement-audit-v1',request_id=uid(5),
        dispatch_id=uid(6),job_digest=H,retired_at=T,sender_reaped=True,tracker_reaped=True,ipc_closed=True,
        pipe_fds_closed=True,buffer_released=True)
    receipt=RawPrepRequestReceipt(**binding,id=uid(7),record_schema='RawPrepRequestReceipt-v1',plan_id=plan.id,
        request_id=uid(5),dispatch_id=uid(6),ordinal=1,doc_ref=artifact.doc_ref,artifact_ref=artifact.id,
        output_variant='complete_candidate',observation=observation,retirement=retirement)
    return plan,artifact,receipt,body


def commitment_data(plan,artifact,receipt):
    return {'record_schema':'DocRawRequestCommitment-v1',
        'scope':{k:getattr(artifact,k) for k in ('research_id','input_revision','attempt','input_digest')},
        'request':{'request_id':artifact.request_id,'dispatch_id':artifact.dispatch_id,'chain_id':uid(8),'ordinal':1,
            'task_id':artifact.task_id,'step_id':uid(9),'semantic':'fetch_source','target_digest':target_digest(catalog()[0]),
            'write_epoch':1,'owner_gate_identity':[1,2,501,384,1],'task_gate_identity':[1,3,501,384,1]},
        'document':{'doc_ref':asdict(artifact.doc_ref),'semantic_object_id':catalog()[0].semantic_object_id,
            'document_group_id':GROUP,'document_role':'disclosure','plan_id':plan.id,
            'plan_digest':sha256(canonical(asdict(plan.plan)).encode()),'catalog_digest':plan.plan.catalog_digest,
            'selection_digest':plan.plan.selection_digest,'admission_digest':H,'access_profile_ref':asdict(artifact.access_profile_ref),
            'rights_digest':H,'job_digest':H},
        'result':{'request_outcome':'SUCCEEDED','output_variant':'complete_candidate','actual_http_status':200,
            'safe_code':'none','completion_observed_at':T},
        'artifact':{'artifact_ref':artifact.id,'artifact_payload_digest':sha256(encode(artifact).encode()),
            'raw_length':artifact.raw_length,'raw_sha256':artifact.raw_sha256},
        'receipt_ref':receipt.id,'receipt_payload_digest':sha256(encode(receipt).encode()),
        'observation_digest':sha256(canonical(asdict(receipt.observation)).encode()),
        'retirement_digest':sha256(canonical(asdict(receipt.retirement)).encode()),
        'producer_protocol':'doc-raw-completion-v1','producer_code_digest':H}


def test_fixed_pair_version_and_shared_four_get_domain():
    targets=catalog()
    assert [t.document_role for t in targets]==['disclosure','filing_index']
    assert [t.doc_ref.doc_version for t in targets]==[1,1]
    assert targets[0].path.endswith('/gfs-20251231.htm') and targets[1].path.endswith('-index.html')
    expected={'operation_family':'official-document-get','purpose':'u1-issuer-disclosure-evidence','semantic_objects':[
        'hkexnews:2026012701265:smic-circular',GROUP+':20f',GROUP+':filing-index']}
    assert common_fingerprint()==sha256(canonical(expected).encode())
    assert rawprep_draft(H)[2]==rawprep_draft('b'*64)[2]
    assert quota_state([{'used':2}],False)['eligible']
    assert not quota_state([{'used':1},{'used':2}],False)['eligible']
    assert not quota_state([{'used':0}],True)['eligible']
    with pytest.raises(ValueError):quota_state([{'used':True}],False)
    with pytest.raises(ValueError):DocRef(doc_id='gfs_2025_20f',doc_version=True)
    with pytest.raises(ValueError):replace(targets[0],host='sec.gov')
    with pytest.raises(ValueError):replace(targets[0],path=targets[0].path+'?raw=1')


def test_raw_codecs_explicit_kinds_and_data_never_become_old_snapshots():
    plan,artifact,receipt,_=data_records()
    for kind,record in [('plans',plan),('snapshots',artifact),('executions',receipt)]:
        assert decode(kind,encode(record))==record
        assert type(record) not in (DataSnapshot,AnalysisPlan)
        with pytest.raises(ValueError):decode('claims',encode(record))
        value=json.loads(encode(record));value['unexpected']=None
        with pytest.raises(ValueError):decode(kind,canonical(value))
        value=json.loads(encode(record));value.pop('record_schema')
        with pytest.raises((ValueError,TypeError,KeyError)):decode(kind,canonical(value))
    bundle=RawPrepBundleReceipt(**{k:getattr(plan,k) for k in ('research_id','input_revision','task_id','attempt','input_digest')},
        id=uid(10),record_schema='RawPrepBundleReceipt-v1',plan_id=plan.id,request_receipt_refs=(receipt.id,),
        commitment_digests=(H,),raw_artifact_refs=(artifact.id,),package_state='INCOMPLETE',evidence='INSUFFICIENT',
        document_identity='unverified',model_analysis_ran=False,statistics_ran=False)
    assert decode('executions',encode(bundle))==bundle
    with pytest.raises(ValueError):replace(bundle,package_state='RAW_PAIR_COMPLETE_UNVERIFIED')
    with pytest.raises(ValueError):replace(artifact,parser_profile={'id':'parser'})
    with pytest.raises(ValueError):replace(artifact,raw_length=True)
    malformed=json.loads(encode(bundle));malformed['request_receipt_refs']=[[]]
    with pytest.raises(ValueError):decode('executions',canonical(malformed))


def test_unknown_observations_keep_required_null_and_no_full_hash():
    observation=data_records()[1].observation
    unknown=replace(observation,observed_final_target=None,http_status=None,content_type_header=None,media_type=None,
        effective_content_encoding=None,content_length=None,request_sent_at=None,received_at=None,
        safe_code='outcome_unknown',body_complete=False,raw_length=None,raw_sha256=None)
    assert unknown.http_status is None and unknown.raw_sha256 is None
    with pytest.raises(ValueError):replace(unknown,raw_sha256=H)
    with pytest.raises(ValueError):replace(unknown,http_status=200)
    with pytest.raises(ValueError):replace(unknown,observed_lower_bound=RAW_CAP+1)
    with pytest.raises(ValueError):replace(observation,attempted_at='2026-02-30T00:00:00.000000Z')
    with pytest.raises(ValueError):replace(observation,body_complete=1)
    with pytest.raises(ValueError):replace(observation,content_type_header=None)
    with pytest.raises(ValueError):replace(observation,content_type_header='application/pdf')
    with pytest.raises(ValueError):replace(observation,content_encoding_header='gzip')


@pytest.mark.parametrize('change',['extra','missing_null','bool','old_proof','unknown','bad_ref','no_body_hash','gate','duplicate','bound'])
def test_commitment_required_fields_and_cross_rules(change):
    plan,artifact,receipt,_=data_records();value=commitment_data(plan,artifact,receipt)
    assert decode_commitment(canonical(value))==value  # Pure data, no writer permit.
    if change=='extra':value['extra']=None
    elif change=='missing_null':value['artifact'].pop('raw_length')
    elif change=='bool':value['request']['ordinal']=True
    elif change=='old_proof':value={'proof_version':1}
    elif change=='unknown':value['result']['request_outcome']='UNKNOWN'
    elif change=='bad_ref':value['document']['doc_ref']['doc_version']=2
    elif change=='no_body_hash':value['result'].update(request_outcome='FAILED',output_variant='failed_no_body',safe_code='limit')
    elif change=='gate':value['request']['owner_gate_identity'][3]=420
    if change=='duplicate':payload=canonical(value).replace('"record_schema":','"record_schema":"x","record_schema":',1)
    elif change=='bound':payload=' '*8193
    else:payload=canonical(value)
    with pytest.raises(ValueError):decode_commitment(payload)


def test_protocol_and_operation_bound_idempotency_and_strict_read_query():
    from research.schemas import (SourcePreviewEnvelope,SourceApprovalEnvelope,source_envelope,source_request_digest)
    data={'input_revision':1,'expected_research_version':1,'rawprep_profile_id':PROFILE_ID}
    raw={'schema_version':'structure-research-v1','contract_revision':CONTRACT,'data':data}
    assert source_envelope(SourcePreviewEnvelope,raw).data.rawprep_profile_id==PROFILE_ID
    for bad in [dict(data,query='queue variability'),dict(data,input_revision=True),dict(data,rawprep_profile_id='other')]:
        with pytest.raises(ValueError):source_envelope(SourcePreviewEnvelope,{**raw,'data':bad})
    with pytest.raises(ValueError):source_envelope(SourcePreviewEnvelope,{**raw,'contract_revision':'b1-candidate-01'})
    approval={**data,'preview_digest':H,'confirm_external':True}
    request=source_envelope(SourceApprovalEnvelope,{**raw,'data':approval}).data
    assert source_request_digest(request,'source-approve')==idempotency_digest('source-approve',approval)
    assert idempotency_digest('source-approve',approval)!=idempotency_digest('source-start',approval)
    assert idempotency_digest('source-approve',approval)!=sha256(canonical(approval).encode())
    assert read_query([('task_id',uid(2))])==uid(2)
    for pairs in [[],[('task_id',uid(2)),('task_id',uid(2))],[('url','https://www.sec.gov/')]]:
        with pytest.raises(ValueError):read_query(pairs)
    with pytest.raises(ValueError):strict_json('{"x":null,"x":null}')
    with pytest.raises(ValueError):strict_json('{"x":1.5}')
    with pytest.raises(ValueError):strict_json('['*1100+'0'+']'*1100)


def test_known_no_body_and_unknown_data_cannot_be_interchanged():
    plan,artifact,receipt,_=data_records()
    value=commitment_data(plan,artifact,receipt)
    value['result'].update(request_outcome='FAILED',output_variant='failed_no_body',actual_http_status=403,safe_code='access_denied')
    value['artifact']={key:None for key in value['artifact']}
    assert decode_commitment(canonical(value))==value  # No native issuance.
    observation=replace(receipt.observation,observed_final_target=None,http_status=None,request_sent_at=None,received_at=None,
        content_length=None,effective_content_encoding=None,safe_code='unavailable',body_complete=False,raw_length=None,raw_sha256=None)
    with pytest.raises(ValueError):replace(receipt,output_variant='failed_no_body',artifact_ref=None,observation=observation)


@pytest.mark.parametrize('status',[302,403])
def test_non_200_complete_body_cannot_enter_artifact_quarantine_or_commitment(status):
    plan,artifact,receipt,_=data_records()
    observed=replace(artifact.observation,http_status=status,safe_code='access_denied')
    with pytest.raises(ValueError):replace(artifact,observation=observed)
    with pytest.raises(ValueError):replace(receipt,output_variant='quarantined_complete',observation=observed)
    c=commitment_data(plan,artifact,receipt)
    c['result'].update(request_outcome='FAILED',output_variant='quarantined_complete',actual_http_status=status,safe_code='access_denied')
    with pytest.raises(ValueError):decode_commitment(canonical(c))


def test_200_quarantine_and_non_200_no_body_remain_valid_data_only():
    plan,artifact,receipt,_=data_records()
    observed=replace(artifact.observation,safe_code='invalid_source')
    isolated=replace(artifact,observation=observed)
    isolated_receipt=replace(receipt,output_variant='quarantined_complete',observation=observed)
    assert decode('snapshots',encode(isolated))==isolated
    assert decode('executions',encode(isolated_receipt))==isolated_receipt
    c=commitment_data(plan,isolated,isolated_receipt)
    c['result'].update(request_outcome='FAILED',output_variant='quarantined_complete',safe_code='invalid_source')
    assert decode_commitment(canonical(c))==c
    for status in (302,403):
        headers_only=replace(receipt.observation,http_status=status,safe_code='access_denied',body_complete=False,
            raw_length=None,raw_sha256=None,received_at=None,observed_failure_at=T)
        no_body=replace(receipt,output_variant='failed_no_body',artifact_ref=None,observation=headers_only)
        assert decode('executions',encode(no_body))==no_body
        c=commitment_data(plan,artifact,receipt)
        c['result'].update(request_outcome='FAILED',output_variant='failed_no_body',actual_http_status=status,safe_code='access_denied')
        c['artifact']={key:None for key in c['artifact']}
        assert decode_commitment(canonical(c))==c


@pytest.mark.parametrize('status',[True,200.0,'200'])
def test_complete_http_status_requires_integer_200_without_coercion(status):
    plan,artifact,receipt,_=data_records()
    with pytest.raises(ValueError):replace(artifact.observation,http_status=status)
    c=commitment_data(plan,artifact,receipt)
    c['result'].update(request_outcome='FAILED',output_variant='quarantined_complete',actual_http_status=status,safe_code='invalid_source')
    with pytest.raises(ValueError):decode_commitment(canonical(c))
