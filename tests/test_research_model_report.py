"""Strict report boundary with offline DTOs; no model, network or persistence."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from web.backend.research import provider_schemas as s
from web.backend.research import model_report as report

# Reuse only pure offline fixture builders, never execute a transport fixture.
from tests.test_research_provider_adapter import packet, candidate, quote, basis, envelope


def observation(evidence):
    price=quote();budget=basis(price)
    context=evidence.context
    permit=s.CallPermit(id=str(uuid4()),account_id=budget.account_id,provider_binding_id=budget.provider_binding_id,
        funding_epoch=budget.funding_epoch,dispatch_id=str(uuid4()),reservation_id=str(uuid4()),context=context,
        request_digest='e'*64,evidence_digest=evidence.binding_digest(),price_digest=s.digest(s.canonical(price.model_dump())),
        price_revision=price.revision,budget_basis_digest=s.digest(s.canonical(budget.model_dump())),
        gate_identity=(1,2,3,384,1),expires_at=2000000000)
    usage=s.parse_usage(envelope()['usage'],price)
    return s.ProviderObservation(context=context,dispatch_id=permit.dispatch_id,request_digest=permit.request_digest,
        evidence_digest=evidence.binding_digest(),response_digest='f'*64,provider_ref='offline-id',fingerprint_digest=None,
        response_model=s.MODEL,usage=usage,cost=s.cost_intent(permit,price,budget,usage,response_digest='f'*64),
        candidate=json.dumps(candidate()),safe_code='ok')


def test_strict_candidate_maps_only_server_hypotheses():
    evidence=packet();seen=observation(evidence)
    value=report.build_model_report(seen,evidence,lambda *_:evidence,timestamp='2026-10-17T00:00:00Z')
    assert value.id!=value.claims[0].id
    assert value.context==evidence.context and value.dispatch_id==seen.dispatch_id
    assert value.claims[0].level=='hypothesis' and value.claims[0].review=='unreviewed'
    assert value.claims[0].assessment=='llm_inference'
    assert value.claims[0].excerpt_ids==(evidence.handles[0].excerpt_id,)
    assert value.status=='qualified_report' and value.evidence=='INSUFFICIENT'
    assert value.execution_mode=='offline_probe' and value.model_analysis_ran is False
    assert value.check_refs==() and value.cost_observation_ref
    assert 'extracted_text' not in value.model_dump_json() and 'offline-id' not in value.model_dump_json()
    assert value.content_digest==s.digest(s.canonical(value.candidate.model_dump()))
    with pytest.raises(ValueError):value.id=str(uuid4())


@pytest.mark.parametrize('mutation',['id','revision','level','checked','status','tools','url','extra_mechanism','fake_handle','duplicate_handle','no_gaps','too_many','long_text','unicode_control','url_in_text','nan','duplicate_key','truncated','empty','oversize'])
def test_model_cannot_self_authorize_or_invent_refs(mutation):
    evidence=packet();value=candidate()
    if mutation in {'id','revision','level','checked','status','tools','url'}:value[mutation]='not allowed'
    elif mutation=='extra_mechanism':value['mechanisms'][0]['check_ids']=['fake']
    elif mutation=='fake_handle':value['mechanisms'][0]['evidence_handles']=['fake']
    elif mutation=='duplicate_handle':value['mechanisms'][0]['evidence_handles']=['e1','e1']
    elif mutation=='no_gaps':value.update(mechanisms=[],gaps=[])
    elif mutation=='too_many':value['mechanisms']*=4
    elif mutation=='long_text':value['summary']='x'*1001
    elif mutation=='unicode_control':value['mechanisms'][0]['mechanism']='hidden\u200bcontrol'
    elif mutation=='url_in_text':value['summary']='Fetch ftp://arbitrary.example/path'
    raw=s.canonical(value)
    if mutation=='nan':raw=b'{"summary":NaN}'
    elif mutation=='duplicate_key':raw=b'{"summary":"a","summary":"b"}'
    elif mutation=='truncated':raw=raw[:-1]
    elif mutation=='empty':raw=b''
    elif mutation=='oversize':raw=b' '*32769
    with pytest.raises(s.ProviderFailure):report.parse_candidate(raw,evidence)


@pytest.mark.parametrize('mutation',['quote','digest','offset','display','send','bool_coercion','source_revision','duplicate'])
def test_controlled_evidence_needs_exact_unicode_and_independent_permissions(mutation):
    evidence=packet();handle=evidence.handles[0]
    changes={}
    if mutation=='quote':changes['quote']='fabricated quote'
    elif mutation=='digest':changes['extracted_digest']='0'*64
    elif mutation=='offset':changes['start']=1
    elif mutation=='display':changes['display_permission']=False
    elif mutation=='send':changes['may_send_to_provider']=False
    elif mutation=='bool_coercion':changes['may_send_to_provider']=1
    elif mutation=='source_revision':changes['source_revision']=True
    mutated=handle.model_copy(update=changes)
    handles=(mutated,mutated) if mutation=='duplicate' else (mutated,)
    with pytest.raises(ValueError):s.EvidencePacket(context=evidence.context,handles=handles)


@pytest.mark.parametrize('mutation',['cancel','epoch','digest','dispatch','unknown_cost','bad_candidate','bad_time'])
def test_late_commit_revalidates_current_package_and_only_accounting_can_survive(mutation):
    evidence=packet();seen=observation(evidence);auth=lambda *_:evidence;timestamp='2026-10-17T00:00:00Z'
    if mutation=='cancel':auth=lambda *_:None
    elif mutation=='epoch':auth=lambda *_:evidence.model_copy(update={'context':evidence.context.model_copy(update={'grant_epoch':2})})
    elif mutation=='digest':seen=seen.model_copy(update={'evidence_digest':'0'*64})
    elif mutation=='dispatch':seen=seen.model_copy(update={'dispatch_id':str(uuid4())})
    elif mutation=='unknown_cost':seen=seen.model_copy(update={'cost':seen.cost.model_copy(update={'kind':'unknown','booked_upper':None})})
    elif mutation=='bad_candidate':seen=seen.model_copy(update={'candidate':'{"level":"computed_under_assumptions"}'})
    else:timestamp='not a timestamp'
    with pytest.raises(s.ProviderFailure):report.build_model_report(seen,evidence,auth,timestamp=timestamp)
    # Report admission never rewrites the existing usage/cost observation.
    assert seen.cost.actual_charge is None


def test_missing_mechanism_is_an_explicit_gap_not_empirical_success():
    value=candidate();value['mechanisms']=[]
    accepted=report.parse_candidate(s.canonical(value),packet())
    assert accepted.mechanisms==() and accepted.gaps


def test_candidate_cannot_supply_real_or_fake_d2_check_fields():
    for field in ('check_ids','check_refs','computed_under_assumptions','relation','formula_ids'):
        value=candidate();value['mechanisms'][0][field]=[]
        with pytest.raises(s.ProviderFailure):report.parse_candidate(s.canonical(value),packet())
