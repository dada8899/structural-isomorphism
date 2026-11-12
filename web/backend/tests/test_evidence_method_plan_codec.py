"""Golden complete wire bytes and finite strict candidate validation."""
import copy,json
from pathlib import Path
import pytest
from research import evidence_method_plan_schemas as t,evidence_method_plan_codec as c
from research.provider_schemas import digest
from .test_evidence_method_plan_schemas import sample,FIXTURE

def candidate():return c.strict_json(c.PROTOCOL_BYTES,8192)['example']

def test_exact_protocol_input_and_outbound_golden_bytes():
    assert (FIXTURE/'protocol.json').read_bytes()==c.PROTOCOL_BYTES
    value=t.SelectedEvidenceMethodInput.model_validate(sample());raw=c.request_bytes(value).raw
    assert raw==(FIXTURE/'golden-request.json').read_bytes()
    assert len(raw)==3966 and digest(raw)=='683acb060409ebf6e15b9a6cde58e6c854ae7cba74a0357c90deb4b4398ff653'
    assert c.parse_candidate(json.dumps(candidate()).encode(),value).candidates==()

@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1.0}',b'{"x":true,"y":'+b'['*25+b'0'+b']'*25+b'}',b'\xef\xbb\xbf{}'])
def test_duplicate_float_nonfinite_depth_and_bom_are_rejected(raw):
    with pytest.raises(ValueError):c.strict_json(raw,65536)

@pytest.mark.parametrize('change',['foreign_handle','duplicate_handle','no_question','authority','url','too_large'])
def test_candidate_is_a_bounded_unverified_data_object(change):
    data=candidate()
    if change=='foreign_handle':data['gaps'][0]['evidence_handles']=['e2']
    elif change=='duplicate_handle':data['gaps'][0]['evidence_handles']=['e1','e1']
    elif change=='no_question':data['clarification_questions']=[]
    elif change=='authority':data['verified']=True
    elif change=='url':data['summary']='See https://example.invalid/method'
    else:data['summary']='x'*17000
    with pytest.raises(ValueError):c.parse_candidate(json.dumps(data).encode(),t.SelectedEvidenceMethodInput.model_validate(sample()))


def selection():
    from research.provider_schemas import digest
    value=t.SelectedEvidenceMethodInput.model_validate(sample());handle=value.handles[0]
    rid='00000000-0000-4000-8000-000000000001';pid='00000000-0000-4000-8000-000000000002'
    entry=dict(handle='e1',source_id='00000000-0000-4000-8000-000000000003',source_revision=1,excerpt_id='00000000-0000-4000-8000-000000000004',
        source_task_id='00000000-0000-4000-8000-000000000005',attempt=1,raw_digest='a'*64,extracted_digest='b'*64,discovery_digest='c'*64,
        excerpt_payload_digest='d'*64,snapshot_payload_digest='e'*64,permission_basis_digest='f'*64,start=0,end=len(handle.quote),quote_sha256=digest(handle.quote.encode()),
        title=handle.title,canonical_url='https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0015032',attribution=handle.attribution,
        read_scope=handle.read_scope,origin=handle.origin,acquired_at='2026-10-20T00:00:00.000000Z',information_cutoff='2026-10-20T00:00:00.000000Z')
    return value,t.SelectionManifest(root=dict(research_id=rid,input_revision=1,input_digest='a'*64,approved_research_version=7),owner=dict(principal_id=pid,generation_digest=digest(('1'*32).encode()),owner_epoch=1,acl_epoch=1),entries=[entry])


def consent():
    from research import evidence_method_plan as plan,plan_native_runtime as flow
    value,manifest=selection();q=flow.quote(evidence_method=True)
    # Pure protocol data: no session/JTI, Owner, scope or native authority.
    cp=t.PreviewConsent(protocol='evidence-method-preview-consent-v1',domain=c.content_domain(value,manifest,'a'*64),principal_id=manifest.owner.principal_id,generation='1'*32,research_id=manifest.root.research_id,input_revision=1,input_digest=manifest.root.input_digest,owner_epoch=1,acl_epoch=1,preview_research_version=7,execution_research_version=8,selection_manifest=manifest,exact_input=value,quote_digest=digest(c.bounded(q,16384)))
    return cp,q


def test_complete_future_envelopes_have_conservative_admission_and_no_capability():
    cp,q=consent();bounds=c.admission_capacity(cp,q)
    assert bounds['result_shell_bytes']<=12288 and bounds['complete_result_bound']<=28672
    raw=c.request_bytes(cp.exact_input).raw
    assert c.decode_request(raw,cp.domain,cp.exact_input,cp.selection_manifest)==cp.exact_input
    assert 'task_id' not in cp.model_dump() and 'nonce' not in cp.model_dump()
    assert cp.preview_research_version==7 and cp.execution_research_version==8


@pytest.mark.parametrize('change',['extra','system','model','tools','stream','input','manifest','scope'])
def test_entire_outbound_bytes_and_data_domain_must_match(change):
    cp,q=consent();raw=c.request_bytes(cp.exact_input).raw;data=c.strict_json(raw,16384);domain=cp.domain;manifest=cp.selection_manifest
    if change=='extra':data['new']=True
    elif change=='system':data['messages'][0]['content']+=' x'
    elif change=='model':data['model']='other'
    elif change=='tools':data['tools']=[]
    elif change=='stream':data['stream']=True
    elif change=='input':data['messages'][1]['content']=data['messages'][1]['content'].replace('queue grows','queue shrinks')
    elif change=='manifest':
        changed=manifest.model_dump(mode='json');changed['entries'][0]['raw_digest']='0'*64;manifest=t.SelectionManifest.model_validate(changed)
    else:domain=t.OutboundDomain.model_validate({**domain.model_dump(mode='json'),'outbound_scope_digest':'0'*64})
    with pytest.raises(ValueError):c.decode_request(c.bounded(data,16384),domain,cp.exact_input,manifest)


def test_declared_field_counts_can_still_exceed_combined_bytes_and_are_not_truncated():
    cp,q=consent();data=cp.model_dump(mode='json')
    handles=[];entries=[]
    for index in range(8):
        handle={**data['exact_input']['handles'][0],'handle':'e'+str(index+1),'title':'长'*300,'attribution':'署'*400,'quote':'文'*1000}
        entry={**data['selection_manifest']['entries'][0],**{k:handle[k] for k in ('handle','title','attribution')},'excerpt_id':'00000000-0000-4000-8000-'+str(index+1).zfill(12),'quote_sha256':digest(handle['quote'].encode()),'end':1000}
        handles.append(handle);entries.append(entry)
    value=t.SelectedEvidenceMethodInput.model_validate({**data['exact_input'],'handles':handles})
    with pytest.raises(c.EvidenceMethodLimit):c.request_bytes(value)
    assert len(value.handles)==8 and all(len(h.quote)==1000 for h in value.handles)


def method_candidate():
    return dict(candidate_kind='mathematical_method',label='Queue relation candidate',mechanism_hypothesis='Accumulation might explain the observation.',method_name='A named candidate method',
        formula_proposal=dict(text='service rate',basis='quoted_subset',evidence_handles=['e1']),evidence_links=[dict(handle='e1',role='condition',proposed_support='Context only',missing_support='Mature-method assumptions are absent.')],
        variable_map=[dict(method_variable='rate',target_variable='observed completions',rationale='A candidate mapping requiring measurement.',evidence_handles=['e1'])],
        applicability=[dict(condition='Stable measurement window',evidence_handles=['e1'],gap='The supplied passage does not establish stability.')],
        competing_explanations=['A changing arrival process may explain the queue.'],nontransferable=['Physical mechanisms do not automatically transfer.'],
        counterexamples_or_falsifiers=[dict(statement='No accumulation under a stable arrival rate.',evidence_handles=['e1'])],
        verification_plan=dict(question='Does accumulation persist?',measurements=['Observe arrivals'],comparison='Compare stable windows',primary_outcome='Queue size',falsification='No difference',stop_rule='Stop with incomplete measurements',inputs_needed=['Arrival timestamps']),
        gaps=[dict(code='formula_not_recoverable',detail='No established formula is supplied.',evidence_handles=['e1'])])


@pytest.mark.parametrize('change',['missing_name','not_quoted','no_formula_handle','unverified_no_gap','duplicate_link'])
def test_math_names_exact_quote_and_formula_gaps_are_required(change):
    value=t.SelectedEvidenceMethodInput.model_validate(sample());data=candidate();proposal=method_candidate();data['candidates']=[proposal]
    if change=='missing_name':proposal['method_name']=None
    elif change=='not_quoted':proposal['formula_proposal']['text']='x = y'
    elif change=='no_formula_handle':proposal['formula_proposal']['text']='supplied';proposal['formula_proposal']['evidence_handles']=[]
    elif change=='unverified_no_gap':
        proposal['formula_proposal']['basis']='unverified_proposal';proposal['gaps'][0]['code']='maturity_not_established'
    else:proposal['formula_proposal']['text']='supplied';proposal['evidence_links']*=2
    with pytest.raises(ValueError):c.parse_candidate(json.dumps(data).encode(),value)


def test_valid_candidate_remains_only_an_unverified_method_proposal():
    data=candidate();proposal=method_candidate();proposal['formula_proposal']['text']='supplied passage';data['candidates']=[proposal]
    value=c.parse_candidate(json.dumps(data).encode(),t.SelectedEvidenceMethodInput.model_validate(sample()))
    assert value.candidates[0].method_name=='A named candidate method'
    assert value.candidates[0].gaps[0].code=='formula_not_recoverable'
    assert 'verified' not in value.model_fields and 'authority' not in value.model_fields
