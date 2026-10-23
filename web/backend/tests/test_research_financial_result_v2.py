"""Synthetic pure DTO/projection tests. No native registry, HTTP or database."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import hashlib
from uuid import uuid4

import pytest

from web.backend.research.financial_schemas import (
    SourceSnapshot,SourceRegistry,FinancialObservation,FinancialAmount,Period)
from web.backend.research.financial_input_schemas import OwnerFinancialRegistryV2
from web.backend.research.financial_policy import canonical,digest,FinancialError,FinancialResourceLimit,Meter,number
from web.backend.research.financial_result_v2 import (
    FinancialSnapshotV2,ComputedDecimalText,decode_financial_calculation,
    project_financial_snapshot_v2,bounded,OPERATION_LIMIT,PURE_LIMIT,PUBLIC_LIMIT,SNAPSHOT_LIMIT)
from web.backend.research.financial_evaluator import evaluate_owner_financial_v2


def fixture(currency='CNY'):
    """Independent synthetic v1 fixture, never adapted from an owner registry.

    Keep this local: backend tests and root tests have distinct `tests` packages.
    """
    from web.backend.research.financial_policy import POLICY,COST_TAGS
    def annual(y):return {'start':f'{y}-01-01','end':f'{y}-12-31','grain':'annual'}
    def parameter(name,value,year=2026,unit='ratio',currency=None,period=None):
        return {'id':name,'value':value,'unit':unit,'currency':currency,'period':period or annual(year),
            'rationale':'explicit synthetic independent assumption','source_refs':[],
            'anchor_observation_id':None,'independent':True}
    source=SourceSnapshot(str(uuid4()),'curated_record','https://example.org/synthetic',
        '2026-08-01','2026-10-17','synthetic curated table, not actual original evidence',(),
        'a'*64,'b'*40,'synthetic.md#L1',None,None,None)
    period=Period('2026-01-01','2026-06-30','interim')
    observations=tuple(FinancialObservation(str(uuid4()),metric,'synthetic_group','group',period,
        FinancialAmount(value,currency,'million'),'synthetic_basis',basis,refs)
        for metric,value,basis,refs in (('revenue','40','media_estimate',(source.id,)),
            ('operating_profit',None,'missing',()),('net_profit',None,'conflicted',(source.id,))))
    registry=SourceRegistry((source,),observations)
    scenario={'id':'base','label':'synthetic case','accounting_basis':'synthetic_basis',
        'remaining_revenue':parameter('remaining','60',unit='million',currency=currency,
            period={'start':'2026-07-01','end':'2026-12-31','grain':'remaining'}),
        'growth':[{'year':y,'parameter':parameter(f'g_{y}','0.1',y)} for y in range(2027,2032)],
        'costs':[{'id':'all_costs','kind':'operating_cost','label':'synthetic full envelope','mode':'revenue_ratio',
            'coverage':sorted(COST_TAGS),'coverage_basis':'all five covered exactly once',
            'values':[{'year':y,'parameter':parameter(f'cost_{y}','0.85',y)} for y in range(2026,2032)]}],
        'exclusions':[],'allocations':[],'future_fx':[]}
    categories=[{'id':'advertising','label':'synthetic advertising','definition':'declared advertising only',
        'dimension':'monetization','excludes':['unallocated'],'kind':'segment'},
        {'id':'unallocated','label':'unallocated','definition':'everything else','dimension':'monetization',
            'excludes':['advertising'],'kind':'unallocated'}]
    return {'entity_scope':'synthetic_group','information_cutoff':'2026-10-17','interim_revenue_ref':observations[0].id,
        'baseline_selection_reason':'synthetic media estimate, not official data',
        'historical_context_refs':[o.id for o in observations[1:]],'historical_fx_choices':[],
        'target_currency':'CNY','categories':categories,'scenarios':[scenario],'sensitivity':None,'policy_revision':POLICY},registry


def owner_fixture(currency='CNY',derived=False):
    request,old=fixture(currency)
    records=[]; mapping=[]
    def append(row,kind,key):
        index=len(records)+1
        row.update(key=key,row_type=kind,record_index=index,physical_line_start=index+1,physical_line_end=index+1,
            kind='owner_supplied',verification='unverified',original_available=False,system_verified=False)
        records.append(row)
        mapping.append({k:row[k] for k in ('key','row_type','record_index','physical_line_start','physical_line_end')})
        mapping[-1]['registered_id']=row['id']
    for s in old.sources:
        append({'id':s.id,'url':s.url,'locator':'synthetic:p1','excerpt':'synthetic evidence',
            'received_excerpt_sha256':hashlib.sha256(b'synthetic evidence').hexdigest(),'declared_original_sha256':None,
            'claimed_published_at':s.published_at,'claimed_accessed_at':s.accessed_at,
            'read_scope':s.read_scope,'source_chain':list(s.source_chain)},'source','source')
    for i,o in enumerate(old.observations):
        append({'id':o.id,'entity_scope':o.entity_scope,'scope_kind':o.scope_kind,'metric':o.metric,
            'period_start':o.period.start,'period_end':o.period.end,'period_grain':o.period.grain,
            'value':o.amount.value,'currency':o.amount.currency,'unit':o.amount.unit,'accounting_basis':o.accounting_basis,
            'declared_basis':o.evidence_basis,'source_refs':list(o.source_refs),'alternative_refs':list(o.alternative_refs)},'observation',f'obs_{i}')
    request['derived_fx_inputs']=[]
    if derived:
        points=[]; current=date(2026,1,1)
        while current<=date(2026,6,30):
            if current.weekday()<5:points.append({'date':current.isoformat(),'value':'7' if len(points)%9 else None})
            current+=timedelta(days=1)
        values=[p['value'] for p in points if p['value'] is not None]
        request['derived_fx_inputs']=[{'id':'h1_average','source_id':old.sources[0].id,
            'claimed_source_version':'synthetic-v1','claimed_accessed_on':'2026-10-17','locator':'synthetic:dates',
            'from_currency':'USD','to_currency':'CNY','period':{'start':'2026-01-01','end':'2026-06-30','grain':'interim'},
            'points':points,'declared_valid_count':len(values),'declared_nd_count':len(points)-len(values),
            'declared_values_sha256':digest(values)}]
        request['historical_fx_choices']=[{'kind':'derived','observation_id':old.observations[0].id,'derivation_id':'h1_average'}]
    registry=OwnerFinancialRegistryV2.model_validate_json(canonical({'format_version':'owner-financial-registry-v2',
        'parser_revision':'owner-financial-csv-v1','identity':{'id':str(uuid4()),'revision':1},
        'binding':{'research_id':str(uuid4()),'input_revision':1,'problem_digest':'a'*64,
            'research_version_before':1,'research_version_after':2},
        'receipt':{'received_ref':str(uuid4()),'received_at':'2026-10-17T00:00:00.000000Z',
            'exact_received_csv_sha256':'b'*64,'key_based_plan_digest':'c'*64,'preview_digest':'d'*64},
        'key_map':mapping,'records':records}))
    envelope={'schema_version':'structure-research-v1','contract_revision':'financial-result-v2',
        'data':{'input_revision':1,'expected_research_version':2,
            'registry_ref':{'id':registry.identity.id,'revision':1,'digest':digest(registry.model_dump(mode='json'))},'request':request}}
    return decode_financial_calculation(canonical(envelope).encode()),registry


def mutate(envelope,change):
    data=envelope.data_dict();change(data)
    return decode_financial_calculation(canonical(data).encode())


def test_full_envelope_domains_and_projection_same_snapshot_without_evaluation(monkeypatch):
    envelope,registry=owner_fixture();meter=Meter()
    snapshot=evaluate_owner_financial_v2(envelope,registry,meter=meter)
    assert snapshot.operations_used==meter.operations
    assert snapshot.request_digest==digest(envelope.data_dict())
    assert snapshot.parameters_digest==digest(envelope.data.request.data())
    assert snapshot.evaluation_input_digest!=snapshot.request_digest
    monkeypatch.setattr('web.backend.research.financial_evaluator.evaluate_owner_financial_v2',lambda *a,**k:pytest.fail('projection recomputed'))
    outputs={v:project_financial_snapshot_v2(envelope,registry,snapshot,view=v).model_dump(mode='json') for v in ('summary','table','chart')}
    assert all(set(v)=={'view','input_status','value'} for v in outputs.values())
    assert outputs['chart']['value']['chart_spec']['snapshot_digest']==snapshot.digest
    values=[r['target']['revenue']['display'] for r in outputs['table']['value']['scenarios'][0]['years']]
    assert outputs['chart']['value']['chart_spec']['series'][0]['values']==values
    assert values==['100.000000','110.000000','121.000000','133.100000','146.410000','161.051000']
    assert 'category_id' not in outputs['chart']['value']['chart_spec']['series'][0]
    assert 'received_ref' not in canonical(outputs)
    assert all(not v['input_status']['system_verified'] for v in outputs.values())


@pytest.mark.parametrize('value',['0.33333333333333333333333333333333333333333333333333','1E-40','1E-249','0','1000000000000000000'])
def test_computed_domain_is_separate_from_input(value):
    assert str(ComputedDecimalText(value))==value
    if len(value)>24 or value in ('1E-40','1E-249'):
        with pytest.raises(FinancialError):number(value)


@pytest.mark.parametrize('value',['-0','0.0','NaN','Infinity','1e-40','1E-250','1E+19','1.000000000000000000000000000000000000000000000000001'])
def test_computed_rejects_noncanonical_or_outside_decimal50(value):
    with pytest.raises(FinancialError):ComputedDecimalText(value)


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":0.1}',b'{}',b' '*65537])
def test_strict_decoder(raw):
    with pytest.raises((FinancialError,ValueError)):decode_financial_calculation(raw)


@pytest.mark.parametrize('field,value',[('input_revision',2),('expected_research_version',1)])
def test_pure_registry_binding_is_consistency_not_permission(field,value):
    envelope,registry=owner_fixture()
    changed=mutate(envelope,lambda d:d['data'].__setitem__(field,value))
    with pytest.raises(FinancialError):evaluate_owner_financial_v2(changed,registry,meter=Meter())
    with pytest.raises(FinancialError):evaluate_owner_financial_v2(envelope,registry.model_dump(mode='json'),meter=Meter())


@pytest.mark.parametrize('kind',['display','reference','extra_provenance','ancestry','unknown_cell_field'])
def test_projection_rejects_damaged_snapshot(kind):
    envelope,registry=owner_fixture();snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter())
    data=snapshot.data();cell=data['scenarios'][0]['years'][0]['target']['revenue']
    if kind=='display':cell['display']='999.000000'
    elif kind=='reference':cell['provenance_ref']='0'*64
    elif kind=='unknown_cell_field':cell['trusted']=True
    elif kind=='extra_provenance':
        row={k:[] for k in ('observation_refs','parameter_refs','derivation_refs','historical_fx_refs','source_refs')}
        row['parameter_refs']=['unknown:parameter'];row['id']=digest(row)
        data['provenance_table'].append(row);data['provenance_table'].sort(key=lambda r:r['id'])
    else:
        row=next(r for r in data['provenance_table'] if r['source_refs']);old=row['id'];row['source_refs']=[]
        row['id']=digest({k:v for k,v in row.items() if k!='id'})
        def replace(v):
            if type(v) is dict:
                for k,x in v.items():
                    if k=='provenance_ref' and x==old:v[k]=row['id']
                    else:replace(x)
            elif type(v) is list:
                for x in v:replace(x)
        replace(data);data['provenance_table'].sort(key=lambda r:r['id'])
        if old==row['id']:data['provenance_table'].append(deepcopy(row))
    with pytest.raises((FinancialError,ValueError)):
        changed=FinancialSnapshotV2.model_validate_json(canonical(data))
        project_financial_snapshot_v2(envelope,registry,changed,view='table')


@pytest.mark.parametrize('cap',[OPERATION_LIMIT,PURE_LIMIT,SNAPSHOT_LIMIT,PUBLIC_LIMIT])
def test_size_limits_exact_utf8_and_shape(cap):
    assert len(bounded('x'*(cap-2),cap).encode())==cap
    with pytest.raises(FinancialResourceLimit):bounded('x'*(cap-1),cap)
    with pytest.raises(FinancialResourceLimit):bounded(['x']*20001,cap)
    nested=0
    for _ in range(34):nested=[nested]
    with pytest.raises(FinancialResourceLimit):bounded(nested,cap)
