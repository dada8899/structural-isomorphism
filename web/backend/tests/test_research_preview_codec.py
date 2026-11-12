"""No-capability preview serialization from current saved credited excerpts."""
from dataclasses import asdict
from uuid import uuid4
import json
import time

import pytest
from pydantic import ValidationError

from .test_research_paid_approval import approved_inputs,preview,identity
from .test_research_d1_integration import source_stack
from .test_research_persistence import stack
from research.authorization import AuthorizationGate
from research.paid_approval import packet_authority
from research.provider_evidence import read_confirmed_provider_packet
from research.preview_codec import PreviewOutboundHandle,preview_request,PreviewRequest
from research.provider_schemas import canonical,digest,ProviderFailure
from research.provider_adapter import prepare_request,DeepSeekAdapter
from research.usage_upper import preview_bound
from research.paid_approval import OfflineFundingResolver,PaidApprovalService
from research.provider_schemas import UsageUpperQuote
from research.errors import ResearchError


def counts(store):
    with store.transaction() as conn:
        return {table:conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('research_tasks','research_grants','research_reservations','research_dispatch_permits','research_cost_observations')}


def test_preview_manifest_has_complete_credit_and_no_execution_or_capability(approved_inputs):
    client,_,store,_,_,_,resolver=approved_inputs;before=counts(store)
    _,draft=preview(approved_inputs)
    assert counts(store)==before
    assert 'Example A, Example B (2026)' in draft['manifest']['sources'][0]['attribution']
    assert all(item['may_send_to_provider'] is False for item in draft['manifest']['sources'])
    for item in draft['manifest']['handles']:
        assert set(item)=={'handle','source_id','source_revision','excerpt_id','title','attribution','extracted_digest','start','end','quote'}
        assert 'may_send_to_provider' not in item and 'extracted_text' not in item
    with store.transaction() as conn:
        payload=json.loads(conn.execute('SELECT payload_json FROM research_paid_approvals').fetchone()[0])
        for key in ('task_id','attempt','context','plan_id','grant_id','dispatch_id'):assert key not in payload
    data=preview_request(draft['manifest']['problem_summary'],tuple(PreviewOutboundHandle.model_validate(item) for item in draft['manifest']['handles']))
    assert type(data) is PreviewRequest and data.outbound_request_digest==draft['outbound_request_digest']
    assert draft['manifest_digest']==digest(canonical(draft['manifest']))
    public=draft['preview_view'];unsigned={key:value for key,value in public.items() if key!='preview_digest'}
    assert public['preview_digest']==digest(canonical(unsigned))
    assert public['maximum_reserve']==preview_bound(resolver._quote,now=int(time.time())).upper_bound.model_dump()
    assert public['actual'] is None and public['model_analysis_ran'] is False
    assert set(public['quote'])=={'revision','digest','valid_until'}
    assert not any(hasattr(data,key) for key in ('context','packet','task_id','dispatch_id','may_send_to_provider'))
    body=json.loads(data.raw)
    assert body['max_tokens']==4096 and body['thinking']=={'type':'disabled'} and body['stream'] is False
    assert 'tools' not in body and body['tool_choice']=='none'
    requests=[]
    adapter=DeepSeekAdapter.offline_probe(connection_factory=lambda *_:requests.append(True),credential_loader=lambda _:'synthetic')
    with pytest.raises(ProviderFailure):adapter.preconnect(data)
    assert requests==[]


def test_confirmation_has_identical_outbound_bytes_but_independent_context_digest(approved_inputs):
    client,_,store,_,pid,_,_=approved_inputs;service,draft=preview(approved_inputs)
    prior=preview_request(draft['manifest']['problem_summary'],tuple(PreviewOutboundHandle.model_validate(item) for item in draft['manifest']['handles']))
    result=service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'stable-packet')
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        proof=packet_authority(conn,store,identity(client),lease,result['approval_ref'])
        packet=read_confirmed_provider_packet(conn,store,identity(client),proof)
        final=prepare_request(draft['manifest']['problem_summary'],packet)
        assert final.raw==prior.raw and final.request_digest==draft['outbound_request_digest']
        assert final.evidence_digest!=draft['manifest_digest']
        assert final.packet.context.task_id==result['task_id']
        assert result['task_id'].encode() not in prior.raw
        altered=packet.model_copy(update={'context':packet.context.model_copy(update={'task_id':str(uuid4())})})
        changed=prepare_request(draft['manifest']['problem_summary'],altered)
        assert changed.raw==prior.raw and changed.evidence_digest!=final.evidence_digest


@pytest.mark.parametrize('forged',[{'may_send_to_provider':True},{'context':{}},{'extracted_text':'full text'},{'max_tokens':8192}])
def test_preview_handle_never_accepts_privilege_or_execution_fields(approved_inputs,forged):
    _,draft=preview(approved_inputs)
    with pytest.raises(ValidationError):PreviewOutboundHandle.model_validate({**draft['manifest']['handles'][0],**forged})


def test_preview_complete_template_and_sources_stay_within_original_byte_cap():
    handles=tuple(PreviewOutboundHandle(handle='e'+str(n),source_id=str(uuid4()),source_revision=1,excerpt_id=str(uuid4()),title='Synthetic',attribution='Synthetic creator (2026)',extracted_digest='a'*64,start=0,end=1000,quote='中'*1000) for n in range(20))
    with pytest.raises(ProviderFailure,match='request_limit'):preview_request('Bounded summary',handles)
    with pytest.raises(TypeError):preview_request('Bounded summary',handles,max_tokens=8192)


@pytest.mark.parametrize('delta',[-1,3600])
def test_preview_rejects_expired_or_unbounded_ttl_on_real_server_clock(approved_inputs,delta):
    client,_,store,rid,pid,ref,resolver=approved_inputs
    quote=UsageUpperQuote.model_validate({**resolver._quote.model_dump(),'valid_until':int(time.time())+delta})
    source=OfflineFundingResolver(principal_id=pid,quote=quote,basis=resolver._basis,approved_upper=resolver._upper)
    try:
        view=client.get('/api/research/'+rid).json()['data'];before=counts(store)
        with pytest.raises(ResearchError) as error:PaidApprovalService(store,funding_resolver=source).preview(identity(client),rid,1,view['research_version'],(ref,))
        assert error.value.code=='BUDGET_UNVERIFIED' and counts(store)==before
    finally:source.close()
