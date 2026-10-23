"""Synthetic pure Decimal/cost/FX behavior, not actual finance or storage."""
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest

from web.backend.tests.test_research_financial_result_v2 import owner_fixture,mutate,fixture
from web.backend.research.financial_policy import Meter,FinancialError,FinancialResourceLimit,canonical,digest
from web.backend.research.financial_input_schemas import OwnerFinancialRegistryV2
from web.backend.research.financial_evaluator import evaluate_owner_financial_v2,evaluate_financial


def test_missing_historical_op_and_missing_one_year_cost_are_separate():
    envelope,registry=owner_fixture()
    changed=mutate(envelope,lambda d:d['data']['request']['scenarios'][0]['costs'][0]['values'].pop(2))
    snapshot=evaluate_owner_financial_v2(changed,registry,meter=Meter())
    assert snapshot.historical_context[1].target_value.raw_value is None
    years=snapshot.scenarios[0].years
    assert years[0].target.operating_profit.display=='15.000000'
    assert years[2].target.operating_profit.raw_value is None
    assert years[3].target.operating_profit.raw_value is not None
    assert all(y.target.revenue.raw_value is not None and y.target.net_profit.raw_value is None for y in years)


def test_derived_129_points_and_provenance_do_not_modify_registry():
    envelope,registry=owner_fixture('USD',True);before=registry.model_dump_json()
    snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter())
    assert len(snapshot.derived_fx_evidence[0].input.points)==129
    assert snapshot.derived_fx_evidence[0].value=='7.0000000000'
    assert snapshot.historical_context[0].target_value.display=='280.000000'
    assert registry.model_dump_json()==before
    ref=snapshot.historical_context[0].target_value.provenance_ref
    provenance=next(p for p in snapshot.provenance_table if p.id==ref)
    assert provenance.derivation_refs==('h1_average',)
    assert provenance.source_refs==(registry.records[0].id,)


@pytest.mark.parametrize('damage',['date','duplicate','count','hash','130','direction','future','tiny'])
def test_derived_invalid_or_unrepresentable_rate_rejected(damage):
    envelope,registry=owner_fixture('USD',True)
    def change(d):
        fx=d['data']['request']['derived_fx_inputs'][0]
        if damage=='date':fx['points'].pop()
        elif damage=='duplicate':fx['points'][1]['date']=fx['points'][0]['date']
        elif damage=='count':fx['declared_valid_count']-=1
        elif damage=='hash':fx['declared_values_sha256']='0'*64
        elif damage=='130':fx['points'].append(fx['points'][-1])
        elif damage=='direction':fx['from_currency'],fx['to_currency']='CNY','USD'
        elif damage=='future':fx['claimed_accessed_on']='2026-12-01'
        else:
            for p in fx['points']:
                if p['value'] is not None:p['value']='0.000000000000000001'
            fx['declared_values_sha256']=digest([p['value'] for p in fx['points'] if p['value'] is not None])
    with pytest.raises((FinancialError,ValueError)):
        changed=mutate(envelope,change)
        evaluate_owner_financial_v2(changed,registry,meter=Meter())


def registry_fx(basis='media_estimate',value='7',kind='period_average'):
    envelope,registry=owner_fixture('USD');data=registry.model_dump(mode='json');index=len(data['records'])+1
    fx={'id':str(uuid4()),'key':'average_fx','row_type':'historical_fx','record_index':index,
        'physical_line_start':index+1,'physical_line_end':index+1,'kind':'owner_supplied','verification':'unverified',
        'original_available':False,'system_verified':False,'period_start':'2026-01-01','period_end':'2026-06-30',
        'period_grain':'interim','value':value,'declared_basis':basis,'source_refs':[data['records'][0]['id']],
        'from_currency':'USD','to_currency':'CNY','fx_kind':kind}
    data['records'].append(fx)
    data['key_map'].append({'key':fx['key'],'row_type':'historical_fx','record_index':index,
        'registered_id':fx['id'],'physical_line_start':index+1,'physical_line_end':index+1})
    registry=OwnerFinancialRegistryV2.model_validate_json(canonical(data))
    def change(d):
        d['data']['registry_ref']['digest']=digest(data)
        d['data']['request']['historical_fx_choices']=[{'kind':'registry','observation_id':d['data']['request']['interim_revenue_ref'],'fx_id':fx['id']}]
    return mutate(envelope,change),registry


@pytest.mark.parametrize('basis,value,expected',[('disclosed','7','280.000000'),('media_estimate','7','280.000000'),('missing',None,None),('conflicted',None,None)])
def test_four_registry_fx_declarations_preserved(basis,value,expected):
    envelope,registry=registry_fx(basis,value)
    snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter())
    cell=snapshot.historical_context[0].target_value
    assert cell.display==expected
    assert cell.basis==('derived_conditional' if value else basis)
    entry=next(p for p in snapshot.provenance_table if p.id==cell.provenance_ref)
    assert entry.historical_fx_refs==(registry.records[-1].id,)


def test_spot_cannot_replace_historical_average():
    envelope,registry=registry_fx(kind='spot')
    with pytest.raises(FinancialError):evaluate_owner_financial_v2(envelope,registry,meter=Meter())


@pytest.mark.parametrize('mode',['deadline','operations','subclass'])
def test_shared_caller_meter_rejects_expiry_or_exhaustion(mode):
    envelope,registry=owner_fixture();meter=Meter()
    if mode=='deadline':meter.deadline=0
    elif mode=='operations':meter.operations=5000
    else:
        class OtherMeter(Meter):pass
        meter=OtherMeter()
    with pytest.raises(FinancialError):evaluate_owner_financial_v2(envelope,registry,meter=meter)


def test_sensitivity_uses_same_meter_and_v2_digest():
    envelope,registry=owner_fixture()
    changed=mutate(envelope,lambda d:d['data']['request'].__setitem__('sensitivity',{'scenario_id':'base','parameter_id':'g_2027','points':['0.1','0.2']}))
    meter=Meter();snapshot=evaluate_owner_financial_v2(changed,registry,meter=meter)
    assert snapshot.operations_used==meter.operations
    assert len(snapshot.sensitivity)==2
    assert snapshot.sensitivity[1].target_revenue[1]=='120.000000'


def test_old_v1_exact_class_and_golden_are_unchanged():
    data,registry=fixture()
    snapshot=evaluate_financial(data,registry)
    assert [r['target']['revenue']['display'] for r in snapshot.table()[0]['years']]==['100.000000','110.000000','121.000000','133.100000','146.410000','161.051000']
    envelope,owner=owner_fixture()
    with pytest.raises(FinancialError):evaluate_financial(data,owner)
    old=deepcopy(data);old['derived_fx_inputs']=[]
    with pytest.raises(FinancialError):evaluate_financial(old,registry)


def test_actual_decimal_third_and_tiny_cost_preserve_raw_vs_display():
    envelope,registry=owner_fixture()
    data=registry.model_dump(mode='json');data['records'][1]['value']='1'
    registry=OwnerFinancialRegistryV2.model_validate_json(canonical(data))
    def change(d):
        d['data']['registry_ref']['digest']=digest(data)
        scenario=d['data']['request']['scenarios'][0]
        scenario['remaining_revenue']['value']='2'
        scenario['allocations']=[{'category_id':'advertising','mode':'amount','values':[
            {'year':y,'parameter':{'id':f'alloc_{y}','value':'1','unit':'million','currency':'CNY',
                'period':{'start':f'{y}-01-01','end':f'{y}-12-31','grain':'annual'},
                'rationale':'synthetic amount','source_refs':[],'anchor_observation_id':None,'independent':True}}
            for y in range(2026,2032)]}]
        for item in scenario['costs'][0]['values']:item['parameter']['value']='0.000000000000000001'
    changed=mutate(envelope,change)
    snapshot=evaluate_owner_financial_v2(changed,registry,meter=Meter())
    cell=snapshot.scenarios[0].years[0].target.composition.rows[0].share
    assert len(Decimal(cell.raw_value).as_tuple().digits)==50
    assert cell.display=='0.333333' and snapshot.decimal50_inexact_encountered
    # A second real computation gives a raw cost below the input magnitude floor.
    data['records'][1]['value']='0.000000000000000001'
    registry=OwnerFinancialRegistryV2.model_validate_json(canonical(data))
    def tiny(d):
        d['data']['registry_ref']['digest']=digest(data)
        s=d['data']['request']['scenarios'][0];s['remaining_revenue']['value']='0.000000000000000001';s['allocations']=[]
    changed=mutate(changed,tiny)
    result=evaluate_owner_financial_v2(changed,registry,meter=Meter())
    cost=result.scenarios[0].years[0].target.cost_bridge[0].value
    assert Decimal(cost.raw_value)==Decimal('2E-36') and cost.display=='0.000000'


@pytest.mark.parametrize('basis',['disclosed','media_estimate','missing','conflicted'])
def test_every_basis_future_context_is_not_historical_actual(basis):
    envelope,registry=owner_fixture();data=registry.model_dump(mode='json')
    row=data['records'][2]
    row.update(period_start='2026-07-01',period_end='2026-12-31',period_grain='remaining',
        declared_basis=basis,value='10' if basis in ('disclosed','media_estimate') else None,
        source_refs=[data['records'][0]['id']])
    registry=OwnerFinancialRegistryV2.model_validate_json(canonical(data))
    changed=mutate(envelope,lambda d:d['data']['registry_ref'].__setitem__('digest',digest(data)))
    with pytest.raises(FinancialError,match='future period'):
        evaluate_owner_financial_v2(changed,registry,meter=Meter())


def test_shared_meter_exact_5000_and_deadline_equality(monkeypatch):
    envelope,registry=owner_fixture()
    cost=evaluate_owner_financial_v2(envelope,registry,meter=Meter()).operations_used
    meter=Meter();meter.operations=5000-cost
    assert evaluate_owner_financial_v2(envelope,registry,meter=meter).operations_used==5000
    meter=Meter();meter.operations=5001-cost
    with pytest.raises(FinancialResourceLimit):evaluate_owner_financial_v2(envelope,registry,meter=meter)
    meter=Meter()
    monkeypatch.setattr('time.monotonic',lambda:meter.deadline)
    assert evaluate_owner_financial_v2(envelope,registry,meter=meter).operations_used==cost
    monkeypatch.setattr('time.monotonic',lambda:meter.deadline+0.000001)
    with pytest.raises(FinancialResourceLimit):evaluate_owner_financial_v2(envelope,registry,meter=meter)


def test_explicit_exclusion_and_source_ancestor_are_interned_completely():
    envelope,registry=owner_fixture();data=registry.model_dump(mode='json')
    parent=deepcopy(data['records'][0]);index=len(data['records'])+1
    parent.update(id=str(uuid4()),key='parent',record_index=index,physical_line_start=index+1,physical_line_end=index+1)
    data['records'][0]['source_chain']=[parent['id']]
    data['records'].append(parent)
    data['key_map'].append({'key':'parent','row_type':'source','registered_id':parent['id'],'record_index':index,
        'physical_line_start':index+1,'physical_line_end':index+1})
    registry=OwnerFinancialRegistryV2.model_validate_json(canonical(data))
    def change(d):
        d['data']['registry_ref']['digest']=digest(data)
        s=d['data']['request']['scenarios'][0]
        s['costs'][0]['coverage'].remove('sbc')
        s['exclusions']=[{'tag':'sbc','rationale':'synthetic explicitly not applicable','source_refs':[parent['id']]}]
    changed=mutate(envelope,change)
    snapshot=evaluate_owner_financial_v2(changed,registry,meter=Meter())
    assert snapshot.scenarios[0].years[0].target.operating_profit.display=='15.000000'
    cell=snapshot.scenarios[0].years[0].target.operating_profit
    entry=next(p for p in snapshot.provenance_table if p.id==cell.provenance_ref)
    assert entry.source_refs==tuple(sorted((parent['id'],data['records'][0]['id'])))


def test_legal_large_request_is_rejected_whole_when_actual_result_does_not_fit():
    from web.backend.research.financial_result_v2 import input_binding
    envelope,registry=owner_fixture('USD')
    def change(d):
        request=d['data']['request'];scenario=request['scenarios'][0]
        template=deepcopy(scenario['costs'][0])
        for i in range(15):
            cost=deepcopy(template)
            cost.update(id=f'adjust_{i}',kind='operating_adjustment',coverage=[])
            for item in cost['values']:
                item['parameter'].update(id=f'adj_{i}_{item["year"]}',value='0.01')
            scenario['costs'].append(cost)
        ids=[f'segment_{i}' for i in range(7)]+['unallocated']
        request['categories']=[{'id':name,'label':name,'definition':'synthetic mutually exclusive partition',
            'dimension':'monetization','excludes':[v for v in ids if v!=name],
            'kind':'unallocated' if name=='unallocated' else 'segment'} for name in ids]
        for i in range(7):
            values=deepcopy(template['values'])
            for item in values:
                item['parameter'].update(id=f'all_{i}_{item["year"]}',value='1',unit='million',currency='USD')
            scenario['allocations'].append({'category_id':f'segment_{i}','mode':'amount','values':values})
    changed=mutate(envelope,change)
    input_binding(changed,registry)  # Real operation and aggregate input fit.
    with pytest.raises(FinancialResourceLimit,match='JSON byte limit'):
        evaluate_owner_financial_v2(changed,registry,meter=Meter())
