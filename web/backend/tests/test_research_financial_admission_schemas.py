"""Synthetic data-shape checks only: no admission, money or server clock proof."""
from copy import deepcopy
from uuid import uuid4

import pytest

from research.financial_admission_schemas import FinancialSnapshotError,validate_snapshot_json
from research.provider_schemas import UsageUpperQuote,BudgetBasisSnapshot,Money,canonical,digest
from research.usage_upper import reserve_bound


@pytest.fixture
def financial_sample():
    uid=lambda:str(uuid4());money=lambda n:Money(currency='CNY',scale=6,amount_units=n)
    account,binding,dispatch,revision=uid(),uid(),uid(),uid()
    quote=UsageUpperQuote(revision=revision,context_bound=1048576,peak_input_miss_units_per_million=1,
        peak_output_units_per_million=2,local_guard=1,price_document_digest='a'*64,model_document_digest='b'*64,
        completion_bound_basis_digest='c'*64,final_request_code_digest='d'*64,valid_until=1060)
    basis=BudgetBasisSnapshot(id=uid(),account_id=account,provider_binding_id=binding,funding_epoch=1,
        initial_prepaid=money(1000),other_use_margin=money(0),cap=money(1000),settled_actual=money(0),
        upper_booked=money(0),held=money(0),available_after_observed_consumption=money(1000),price_revision=revision,valid_until=2000)
    reserved=reserve_bound(quote,dispatch_id=dispatch,request_digest='e'*64,now=1000)
    return dict(record_version='financial-admission-v1',producer_version='owned-budget-offline-v1',policy='bounded_usage_upper_v2',
        mode='offline_probe',purpose='method_hypothesis',
        project=dict(budget_id=1,version=1,authorized_cap=money(10).model_dump(),authorization_ref=uid(),
            authorization_digest='f'*64,database_binding='a'*64,account_id=account,economic_binding=binding,funding_epoch=1),
        actor=dict(principal_id=uid(),principal_epoch=1,grant_id=uid(),grant_epoch=1,approval_ref=uid(),approval_digest='b'*64,
            funding_permission_ref=uid(),funding_permission_digest='c'*64,scope_digest='d'*64),
        dispatch=dict(task_id=uid(),step_id=uid(),attempt=1,authorized_task_version=1,authorized_step_version=1,
            task_before=1,task_after=2,step_before=1,step_after=2,reservation_id=uid(),reservation_before=1,reservation_after=2,
            permit_id=uid(),permit_before='prepared',permit_after='consumed',dispatch_id=dispatch,session_id=uid(),
            session_before=1,session_after=2,request_digest='e'*64,evidence_digest='a'*64,context_digest='b'*64,outbound_fingerprint='c'*64),
        quote=quote.model_dump(),reserved=reserved.model_dump(),basis=basis.model_dump(),
        quote_digest=digest(canonical(quote.model_dump())),basis_digest=digest(canonical(basis.model_dump())),
        approved_upper=reserved.reserved_upper.model_dump(),codec_digest='d'*64,math_version='bounded_usage_upper_v2',math_code_digest='f'*64,
        confirmed_at=999,reserve_checked_at=1000,admitted_at=1001,recorded_at=1002)


def test_financial_data_is_roundtrippable_without_becoming_permission(financial_sample):
    raw=canonical(financial_sample)
    value=validate_snapshot_json(raw,expected_digest=digest(raw))
    assert value.model_dump()==financial_sample
    assert not hasattr(value,'require') and not hasattr(value,'trusted')


@pytest.mark.parametrize('path,value',[
    (('project','budget_id'),True),(('project','authorized_cap','scale'),6.0),
    (('project','authorized_cap','amount_units'),'10'),(('project','authorized_cap','amount_units'),-1),
    (('project','account_id'),str(uuid4())),(('project','funding_epoch'),2),
    (('actor','email'),'private@example.invalid'),(('actor','cookie'),'PRIVATE-CANARY'),
    (('dispatch','summary'),'PRIVATE-CANARY'),(('dispatch','permit_after'),'prepared'),
    (('dispatch','step_after'),1),(('dispatch','authorized_task_version'),2),
    (('quote_digest',),'0'*64),(('basis_digest',),'0'*64),(('codec_digest',),'0'*64),
    (('recorded_at',),1060),(('admitted_at',),900),(('mode',),'live'),
    (('purpose',),'phenomenon_plan_v1'),(('producer_version',),'owned-loopback-return-v1'),
    (('approved_upper','amount_units'),4),
])
def test_invalid_or_private_fields_never_become_financial_snapshot(financial_sample,path,value):
    sample=deepcopy(financial_sample);node=sample
    for key in path[:-1]:node=node[key]
    node[path[-1]]=value
    with pytest.raises(FinancialSnapshotError) as caught:validate_snapshot_json(canonical(sample))
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert 'PRIVATE' not in str(caught.value) and 'private@example' not in str(caught.value)


@pytest.mark.parametrize('bad',[b'{}',b'{"mode":1,"mode":2}',b'NaN',b'x'*16385,b'{"scale":6.0}'],ids=['empty','duplicate','nonfinite','cap','float'])
def test_malformed_oversized_and_duplicate_json_rejected(bad):
    with pytest.raises(FinancialSnapshotError):validate_snapshot_json(bad)


def test_expected_digest_must_match(financial_sample):
    with pytest.raises(FinancialSnapshotError):validate_snapshot_json(canonical(financial_sample),expected_digest='0'*64)
