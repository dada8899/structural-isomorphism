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


def _repoint_provenance(envelope,registry,snapshot,path,change,*,source_override=False):
    """Keep hashes, source closure, and used-entry integrity valid when corrupting."""
    from web.backend.research.financial_result_v2 import provenance_sources
    data=snapshot.data();cell=data
    for key in path:cell=cell[key]
    row=deepcopy(next(r for r in data['provenance_table'] if r['id']==cell['provenance_ref']))
    change(row)
    if not source_override:row['source_refs']=provenance_sources(registry,envelope.data.request,row)
    for key in row:
        if key!='id':row[key]=sorted(set(row[key]))
    row['id']=digest({k:v for k,v in row.items() if k!='id'});cell['provenance_ref']=row['id']
    used=set()
    def walk(value):
        if type(value) is dict:
            if 'provenance_ref' in value:used.add(value['provenance_ref'])
            for v in value.values():walk(v)
        elif type(value) is list:
            for v in value:walk(v)
    walk(data)
    entries={r['id']:r for r in data['provenance_table']};entries[row['id']]=row
    data['provenance_table']=[entries[k] for k in sorted(used)]
    return FinancialSnapshotV2.model_validate_json(canonical(data))


@pytest.mark.parametrize('case',['historical_future','bridge_future','missing_growth','wrong_year',
    'cross_scenario','missing_cost','empty_allocation','missing_observation','extra_observation','missing_cost_year'])
def test_cell_dependency_template_rejects_existing_but_inapplicable_refs(case):
    envelope,registry=owner_fixture()
    if case=='cross_scenario':
        def add(d):
            other=deepcopy(d['data']['request']['scenarios'][0]);other['id']='other'
            d['data']['request']['scenarios'].append(other)
        envelope=mutate(envelope,add)
    if case=='missing_cost_year':
        envelope=mutate(envelope,lambda d:d['data']['request']['scenarios'][0]['costs'][0]['values'].pop(2))
    snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter())
    year=('scenarios',0,'years')
    path,ref,remove={
        'historical_future':(('historical_context',0,'target_value'),'base:g_2031',False),
        'bridge_future':(('scenarios',0,'bridge','interim'),'base:remaining',False),
        'missing_growth':((*year,1,'target','revenue'),'base:g_2027',True),
        'wrong_year':((*year,1,'target','revenue'),'base:g_2031',False),
        'cross_scenario':((*year,0,'target','operating_profit'),'other:cost_2026',False),
        'missing_cost':((*year,2,'target','cost_bridge',0,'value'),'base:cost_2028',True),
        'empty_allocation':((*year,0,'target','composition','rows',0,'amount'),'base:g_2031',False),
        'missing_observation':(('historical_context',0,'target_value'),None,False),
        'extra_observation':(('historical_context',0,'target_value'),envelope.data.request.historical_context_refs[0],False),
        'missing_cost_year':((*year,2,'target','cost_bridge',0,'value'),'base:cost_2026',False),
    }[case]
    def change(row):
        if case=='missing_observation':row['observation_refs']=[]
        elif case=='extra_observation':row['observation_refs'].append(ref)
        elif remove:row['parameter_refs'].remove(ref)
        else:row['parameter_refs'].append(ref)
    changed=_repoint_provenance(envelope,registry,snapshot,path,change)
    with pytest.raises(FinancialError,match='actual dependency'):
        project_financial_snapshot_v2(envelope,registry,changed,view='table')


@pytest.mark.parametrize('kind',['registry','derived'])
def test_cell_dependency_template_requires_actual_selected_fx(kind):
    if kind=='derived':envelope,registry=owner_fixture('USD',True)
    else:
        from web.backend.tests.test_research_financial_evaluator_v2 import registry_fx
        envelope,registry=registry_fx()
    snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter())
    field='derivation_refs' if kind=='derived' else 'historical_fx_refs'
    changed=_repoint_provenance(envelope,registry,snapshot,('historical_context',0,'target_value'),
        lambda row:row.__setitem__(field,[]))
    with pytest.raises(FinancialError,match='actual dependency'):
        project_financial_snapshot_v2(envelope,registry,changed,view='chart')


@pytest.mark.parametrize('scope',['other_operating_profit','same_scenario_cost'])
def test_exclusion_sources_apply_only_to_own_scenario_operating_profit(scope):
    envelope,registry=owner_fixture();data=registry.model_dump(mode='json')
    source=deepcopy(data['records'][0]);index=len(data['records'])+1
    source.update(id=str(uuid4()),key='exclusion_source',record_index=index,
        physical_line_start=index+1,physical_line_end=index+1)
    data['records'].append(source)
    data['key_map'].append({'key':source['key'],'row_type':'source','registered_id':source['id'],
        'record_index':index,'physical_line_start':index+1,'physical_line_end':index+1})
    registry=OwnerFinancialRegistryV2.model_validate_json(canonical(data))
    def setup(d):
        d['data']['registry_ref']['digest']=digest(data);scenario=d['data']['request']['scenarios'][0]
        other=deepcopy(scenario);other['id']='other';d['data']['request']['scenarios'].append(other)
        scenario['costs'][0]['coverage'].remove('sbc')
        scenario['exclusions']=[{'tag':'sbc','rationale':'explicit synthetic exclusion','source_refs':[source['id']]}]
    envelope=mutate(envelope,setup);snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter())
    path=(('scenarios',1,'years',0,'target','operating_profit') if scope=='other_operating_profit'
        else ('scenarios',0,'years',0,'target','cost_bridge',0,'value'))
    changed=_repoint_provenance(envelope,registry,snapshot,path,
        lambda row:row['source_refs'].append(source['id']),source_override=True)
    with pytest.raises(FinancialError,match='actual dependency'):
        project_financial_snapshot_v2(envelope,registry,changed,view='summary')


def test_symbolic_null_allocation_branches_and_views_do_not_run_numeric_kernel(monkeypatch):
    envelope,registry=owner_fixture('USD',True)
    def setup(d):
        scenario=d['data']['request']['scenarios'][0]
        template=deepcopy(scenario['remaining_revenue'])
        def parameter(name,value,period,unit='fx'):
            item=deepcopy(template);item.update(id=name,value=value,period=period,unit=unit,currency=None if unit=='fx' else 'USD')
            return item
        scenario['future_fx']=[{'from_currency':'USD','to_currency':'CNY',
            'parameter':parameter('remaining_fx','7',template['period'])}]
        values=[]
        for year in range(2026,2032):
            period={'start':f'{year}-01-01','end':f'{year}-12-31','grain':'annual'}
            scenario['future_fx'].append({'from_currency':'USD','to_currency':'CNY',
                'parameter':parameter(f'fx_{year}',None if year==2028 else '7',period)})
            values.append({'year':year,'parameter':parameter(f'amount_{year}','10',period,'million')})
        scenario['allocations']=[{'category_id':'advertising','mode':'amount','values':values}]
        scenario['costs'][0]['mode']='amount'
        for value in scenario['costs'][0]['values']:
            value['parameter'].update(value='50',unit='million',currency='USD')
    envelope=mutate(envelope,setup);meter=Meter()
    snapshot=evaluate_owner_financial_v2(envelope,registry,meter=meter)
    year=snapshot.scenarios[0].years[2]
    assert year.target.revenue.raw_value is None and year.native.revenue.raw_value is not None
    unallocated=next(p for p in snapshot.provenance_table if p.id==year.target.composition.rows[-1].amount.provenance_ref)
    assert 'base:fx_2028' in unallocated.parameter_refs and 'base:amount_2028' not in unallocated.parameter_refs
    count=meter.operations
    def forbidden(*a,**k):pytest.fail('projection ran numerical evaluator or new Meter')
    monkeypatch.setattr('web.backend.research.financial_evaluator._OwnerEvaluation.scenario',forbidden)
    monkeypatch.setattr(Meter,'__init__',forbidden);monkeypatch.setattr(Meter,'calculate',forbidden)
    for view in ('summary','table','chart'):
        assert project_financial_snapshot_v2(envelope,registry,snapshot,view=view).view==view
    assert snapshot.operations_used==meter.operations==count


@pytest.mark.parametrize('baseline',['zero','missing'])
def test_symbolic_composition_keeps_zero_and_null_dependencies(baseline):
    envelope,registry=owner_fixture();data=registry.model_dump(mode='json')
    data['records'][1].update(value='0' if baseline=='zero' else None,
        declared_basis='media_estimate' if baseline=='zero' else 'missing')
    registry=OwnerFinancialRegistryV2.model_validate_json(canonical(data))
    def setup(d):
        d['data']['registry_ref']['digest']=digest(data);scenario=d['data']['request']['scenarios'][0]
        scenario['remaining_revenue']['value']='0'
        values=[]
        for year in range(2026,2032):
            p=deepcopy(scenario['remaining_revenue']);p.update(id=f'allocated_{year}',unit='million',value='0',
                period={'start':f'{year}-01-01','end':f'{year}-12-31','grain':'annual'})
            values.append({'year':year,'parameter':p})
        scenario['allocations']=[{'category_id':'advertising','mode':'amount','values':values}]
    envelope=mutate(envelope,setup);snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter())
    rows=snapshot.scenarios[0].years[0].target.composition.rows
    assert rows[0].share.raw_value is None
    assert 'base:allocated_2026' in next(p for p in snapshot.provenance_table
        if p.id==rows[-1].amount.provenance_ref).parameter_refs
    assert project_financial_snapshot_v2(envelope,registry,snapshot,view='table').view=='table'


def test_symbolic_sensitivity_rejects_unjustified_null_without_recalculation():
    envelope,registry=owner_fixture()
    envelope=mutate(envelope,lambda d:d['data']['request'].__setitem__('sensitivity',
        {'scenario_id':'base','parameter_id':'g_2027','points':['0.1']}))
    snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter());data=snapshot.data()
    data['sensitivity'][0]['target_revenue'][0]=None
    changed=FinancialSnapshotV2.model_validate_json(canonical(data))
    with pytest.raises(FinancialError,match='sensitivity input availability'):
        project_financial_snapshot_v2(envelope,registry,changed,view='chart')



@pytest.fixture
def inert_stored_result():
    """Consistent synthetic saved DTO only; no Store/Main/native authority."""
    from web.backend.research import financial_result_v2 as result
    from web.backend.research.financial_execution import PRODUCER,PROFILE
    from web.backend.research.financial_policy import POLICY
    envelope,registry=owner_fixture();snapshot=evaluate_owner_financial_v2(envelope,registry,meter=Meter())
    ref=envelope.data.registry_ref.model_dump(mode='json');at='2026-10-17T00:00:00.000000Z'
    row={'research_id':registry.binding.research_id,'principal_id':str(uuid4()),'input_revision':1,
        'problem_digest':registry.binding.problem_digest,'principal_epoch':1,'owner_epoch':1,'acl_epoch':1,
        'auth_generation_digest':'a'*64,'owner_gate_identity':[1,2,3,4,5],
        'research_version_before':2,'research_version_after':3,'request_digest':snapshot.request_digest,
        'result_ref':str(uuid4()),'result_type':'financial_scenario_v2','registry_ref':ref['id'],
        'registry_revision':1,'registry_digest':ref['digest'],'run_id':str(uuid4()),'recorded_at':at,
        'policy_revision':POLICY,'producer_revision':PRODUCER,'execution_code_digest':'e'*64,
        'execution_status':'completed','operations_used':snapshot.operations_used,'snapshot_digest':snapshot.digest}
    receipt={'receipt_schema':'financial-local-execution-v2','producer_revision':PRODUCER,'execution_profile':PROFILE,
        'policy_revision':POLICY,'execution_code_digest':row['execution_code_digest'],'run_id':row['run_id'],'status':'completed',
        'http':{'action':'financial-calculate','method':'POST','endpoint':'calculate_research_financial',
            'source_ref':str(uuid4()),'key_digest':'b'*64,'request_digest':snapshot.request_digest,
            'session_jti_digest':'c'*64,'session_expires_at':1},
        'binding':{**{k:row[k] for k in ('research_id','principal_id','principal_epoch','auth_generation_digest',
            'owner_epoch','acl_epoch','input_revision','problem_digest')},'registry_ref':ref,
            'registry_origin_digest':digest({'registry_ref':ref,'parser_revision':registry.parser_revision,
                **registry.receipt.model_dump(mode='json')})},
        'native':{'pid':1,'thread_id':1,'transaction_ref':str(uuid4()),'main_binding_ref':str(uuid4()),
            'database_identity':[1,2],'owner_gate_identity':row['owner_gate_identity']},
        'parameters_digest':snapshot.parameters_digest,'evaluation_input_digest':snapshot.evaluation_input_digest,
        'snapshot_digest':snapshot.digest,'timing':{'started_at':at,'completed_at':at,'recorded_at':at,'elapsed_monotonic_ns':0},
        'guard':{'kind':'cooperative','deadline_ms':2000,'max_operations':5000,
            'operations_used':snapshot.operations_used,'os_isolation_attested':False},
        'qualification':'conditional_on_owner_supplied_data','model_analysis_ran':False}
    expectation={k:row[k] for k in ('result_ref','research_id','principal_id','input_revision','problem_digest',
        'request_digest','producer_revision','policy_revision','execution_code_digest','run_id','snapshot_digest',
        'recorded_at','research_version_before','research_version_after')}
    expectation.update(expectation_schema='financial-result-expectation-v2',registry_ref=ref,
        parameters_digest=snapshot.parameters_digest,evaluation_input_digest=snapshot.evaluation_input_digest,
        execution_profile=PROFILE,receipt_digest=digest(receipt),calculation_status='calculated_under_assumptions',
        qualification='conditional_on_owner_supplied_data',u2_goal_status=result._u2_status(snapshot),model_analysis_ran=False)
    stored=result.StoredFinancialResultV2.model_validate_json(canonical({'row_binding':row,'operation':envelope.data_dict(),
        'expectation':expectation,'execution_receipt':receipt,'snapshot':snapshot.data()}))
    return stored,registry


def _observe_stored_raw_boundary(monkeypatch):
    from web.backend.research import financial_result_v2 as result
    original_bounded,original_canonical=result.bounded,result.canonical
    original_roundtrip=result.StoredFinancialResultV2.model_validate_json
    original_snapshot=result.validate_snapshot
    facts={'data':None,'raw':None,'canonical':0,'roundtrip':0,'snapshot':0}
    def serialise(value):
        if value is facts['data']:facts['canonical']+=1
        return original_canonical(value)
    def limit(value,cap):
        whole=type(value) is dict and set(value)=={'row_binding','operation','expectation','execution_receipt','snapshot'}
        if whole:
            assert facts['data'] is None and cap==SNAPSHOT_LIMIT
            facts['data']=value
        raw=original_bounded(value,cap)
        if whole:
            # Independent original second serialization, outside the counted
            # production binding, proves byte equality without an old-code shim.
            assert raw==original_canonical(value)
            facts['raw']=raw
        return raw
    def roundtrip(cls,raw,*args,**kwargs):
        facts['roundtrip']+=1
        assert type(raw) is str and raw is facts['raw']
        return original_roundtrip(raw,*args,**kwargs)
    def snapshot(*args,**kwargs):
        facts['snapshot']+=1
        return original_snapshot(*args,**kwargs)
    monkeypatch.setattr(result,'canonical',serialise)
    monkeypatch.setattr(result,'bounded',limit)
    monkeypatch.setattr(result.StoredFinancialResultV2,'model_validate_json',classmethod(roundtrip))
    monkeypatch.setattr(result,'validate_snapshot',snapshot)
    return facts


def test_stored_roundtrip_reuses_same_bounded_raw_and_preserves_full_validation(inert_stored_result,monkeypatch):
    from web.backend.research import financial_result_v2 as result
    stored,registry=inert_stored_result
    before=canonical(stored.model_dump(mode='json'));owner=canonical(registry.model_dump(mode='json'))
    facts=_observe_stored_raw_boundary(monkeypatch)
    saved=result._validate_stored(stored,registry)
    assert saved is not stored and canonical(saved.model_dump(mode='json'))==before
    assert digest(saved.model_dump(mode='json'))==digest(stored.model_dump(mode='json'))
    assert canonical(registry.model_dump(mode='json'))==owner
    assert result._saved_values(saved)==result._saved_values(stored)
    assert (facts['canonical'],facts['roundtrip'],facts['snapshot'])==(1,1,1)
    assert facts['raw']==before


@pytest.mark.parametrize('kind,counts',[
    ('wrong_type',(0,0,0)),('primitive',(0,0,0)),('shape',(0,0,0)),('bytes',(0,0,0)),
    ('roundtrip',(1,1,0)),('registry',(1,1,1)),('snapshot',(1,1,1)),('receipt',(1,1,1))])
def test_stored_raw_reuse_preserves_bounded_roundtrip_and_binding_rejections(inert_stored_result,monkeypatch,kind,counts):
    from web.backend.research import financial_result_v2 as result
    stored,registry=inert_stored_result
    if kind=='wrong_type':stored={}
    elif kind=='primitive':stored=stored.model_copy(update={'row_binding':stored.row_binding.model_copy(update={'owner_gate_identity':(1,2,3,4,1<<65)})})
    elif kind=='shape':
        nested=0
        for _ in range(34):nested=[nested]
        stored=stored.model_copy(update={'row_binding':stored.row_binding.model_copy(update={'owner_gate_identity':nested})})
    elif kind=='bytes':stored=stored.model_copy(update={'row_binding':stored.row_binding.model_copy(update={'request_digest':'x'*(SNAPSHOT_LIMIT+1)})})
    elif kind=='roundtrip':stored=stored.model_copy(update={'row_binding':stored.row_binding.model_copy(update={'result_ref':'invalid'})})
    elif kind=='registry':registry=registry.model_copy(update={'binding':registry.binding.model_copy(update={'input_revision':2})})
    elif kind=='snapshot':stored=stored.model_copy(update={'snapshot':stored.snapshot.model_copy(update={'operations_used':stored.snapshot.operations_used+1})})
    else:stored=stored.model_copy(update={'execution_receipt':stored.execution_receipt.model_copy(update={'snapshot_digest':'0'*64})})
    facts=_observe_stored_raw_boundary(monkeypatch)
    expected=FinancialResourceLimit if kind in ('primitive','shape','bytes') else ValueError
    with pytest.raises(expected):result._validate_stored(stored,registry)
    assert (facts['canonical'],facts['roundtrip'],facts['snapshot'])==counts
