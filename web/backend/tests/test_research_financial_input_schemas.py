"""FIN-1 pure decoder controls; these never install Main or a write authority."""
import csv
import hashlib
import io
import json

import pytest

from research.financial_import import parse_owner_csv
from research.financial_input_schemas import (
    CONTRACT, CSV_HEADER, CSV_LIMIT, WIRE_LIMIT, FinancialImportError,
    FinancialImportPreviewEnvelope, FinancialImportPreviewResponse, decode_financial_import_preview,
)
from research.financial_policy import canonical


def sample_rows():
    return [dict(row_type='source', key='statement', url='https://example.invalid/statement', locator='owner says page 3',
                 excerpt='e\u0301 reported "100"\nowner supplied only', read_scope='owner-selected excerpt',
                 claimed_published_at='2026-08-01', claimed_accessed_at='2026-08-02'),
            dict(row_type='observation', key='interim', source_refs='statement', entity_scope='Example group',
                 scope_kind='group', metric='revenue', period_start='2026-01-01', period_end='2026-06-30',
                 period_grain='interim', value='1e+02', currency='USD', unit='million',
                 accounting_basis='owner stated GAAP', declared_basis='disclosed'),
            dict(row_type='historical_fx', key='average', source_refs='statement',
                 period_start='2026-01-01', period_end='2026-06-30', period_grain='interim',
                 value='7.000', from_currency='USD', to_currency='CNY', fx_kind='period_average', declared_basis='media_estimate')]


def csv_text(rows=None):
    stream=io.StringIO(newline=''); writer=csv.writer(stream,lineterminator='\n')
    writer.writerow(CSV_HEADER)
    for row in sample_rows() if rows is None else rows:writer.writerow([row.get(k,'') for k in CSV_HEADER])
    return stream.getvalue()


def preview_body(text=None):
    return {'schema_version':'structure-research-v1','contract_revision':CONTRACT,
            'data':{'input_revision':1,'expected_research_version':1,'csv_text':csv_text() if text is None else text}}


def test_exact_declarations_record_order_locations_and_decimal_text():
    value=csv_text(); plan=parse_owner_csv(value)
    assert [r.row_type for r in plan.records]==['source','observation','historical_fx']
    assert [r.record_index for r in plan.records]==[1,2,3]
    assert [(r.physical_line_start,r.physical_line_end) for r in plan.records]==[(2,3),(4,4),(5,5)]
    source,obs,fx=plan.records
    assert source.excerpt==sample_rows()[0]['excerpt'] and 'e\u0301' in source.excerpt
    assert source.received_excerpt_sha256==hashlib.sha256(source.excerpt.encode()).hexdigest()
    assert (obs.value,fx.value)==('1e+02','7.000')
    assert all(r.kind=='owner_supplied' and r.verification=='unverified' and not r.system_verified and not r.original_available for r in plan.records)
    assert not any(name in canonical(plan.model_dump(mode='json')) for name in ('received_at','received_ref','retained_original_ref','curated_commit'))
    assert parse_owner_csv(value)==plan


@pytest.mark.parametrize('kind',['observation','historical_fx'])
@pytest.mark.parametrize('basis',['missing','conflicted'])
def test_missing_and_conflicted_remain_null(kind,basis):
    rows=sample_rows(); row=next(r for r in rows if r['row_type']==kind)
    row.update(value='',declared_basis=basis)
    parsed=next(r for r in parse_owner_csv(csv_text(rows)).records if r.row_type==kind)
    assert parsed.value is None and parsed.declared_basis==basis and parsed.verification=='unverified'


@pytest.mark.parametrize('index,field,value',[
    (0,'url','file:///private/report'),(0,'url','https://user:pass@example.invalid/report'),
    (0,'excerpt','secret\x00value'),(0,'read_scope','x'*701),(0,'locator','x'*241),(0,'excerpt','x'*1001),
    (0,'declared_basis','disclosed'),(0,'claimed_published_at','2026-8-01'),
    (0,'claimed_accessed_at','2026-07-31'),(0,'declared_original_sha256','A'*64),
    (1,'unit','yuan'),(1,'currency','EUR'),(1,'metric','gmv'),(1,'value','01'),
    (1,'value','1e999'),(1,'value','-1'),(1,'value','NaN'),(1,'declared_basis','scenario_assumption'),
    (1,'declared_basis','missing'),(1,'source_refs',''),(1,'period_end','2027-01-01'),
    (2,'declared_basis','missing'),(2,'declared_basis',''),(2,'value','0'),(2,'source_refs',''),
    (2,'from_currency','CNY'),(2,'alternative_refs','interim'),
])
def test_row_constraints_reject_without_echo(index,field,value):
    rows=sample_rows(); rows[index][field]=value
    with pytest.raises(FinancialImportError) as raised:parse_owner_csv(csv_text(rows))
    body=raised.value.body()
    assert set(body['validation'])=={'row','field','code'} and body['validation']['row']>=2
    assert rows[0]['excerpt'] not in json.dumps(body,ensure_ascii=False)


@pytest.mark.parametrize('mutation', ['duplicate','dangling','wrong-domain','source-cycle','alternative-cycle','incompatible','empty-reference'])
def test_reference_domains_cycles_and_compatibility(mutation):
    rows=sample_rows()
    if mutation=='duplicate':rows[1]['key']='statement'
    elif mutation=='dangling':rows[1]['source_refs']='absent'
    elif mutation=='wrong-domain':rows[1]['source_refs']='average'
    elif mutation=='source-cycle':rows[0]['source_chain']='statement'
    elif mutation=='empty-reference':rows[1]['source_refs']='statement;'
    else:
        other={**rows[1],'key':'other','alternative_refs':'interim'};rows.append(other)
        rows[1]['alternative_refs']='other'
        if mutation=='incompatible':other['metric']='operating_profit';other['alternative_refs']=''
    with pytest.raises(FinancialImportError):parse_owner_csv(csv_text(rows))


@pytest.mark.parametrize('value', ['\ufeff'+csv_text(),csv_text()+'\n',csv_text().replace('row_type,key','key,row_type',1),
                                  csv_text()+','.join(CSV_HEADER)+'\n',csv_text().replace('statement,','state"ment,',1)])
def test_exact_csv_grammar_and_header(value):
    with pytest.raises(FinancialImportError):parse_owner_csv(value)


def test_decoder_csv_and_wire_caps_are_separate_from_old_operation_limit():
    value=preview_body('x'*CSV_LIMIT)
    raw=canonical(value).encode()
    assert len(raw)>65536 and decode_financial_import_preview(raw).data.csv_text=='x'*CSV_LIMIT
    assert decode_financial_import_preview(raw+b' '*(WIRE_LIMIT-len(raw))).data.csv_text=='x'*CSV_LIMIT
    for excess in (canonical(preview_body('x'*(CSV_LIMIT+1))).encode(),raw+b' '*(WIRE_LIMIT-len(raw)+1)):
        with pytest.raises(FinancialImportError) as raised:decode_financial_import_preview(excess)
        assert raised.value.status==413


@pytest.mark.parametrize('raw',[
    b'\xff',b'{"schema_version":1,"schema_version":2}',b'{"data":NaN}',b'{"data":1.2}',
    canonical({**preview_body(),'extra':True}).encode(),
    canonical(preview_body()).replace('"input_revision":1','"input_revision":true').encode(),
    b'{"nested":'+b'['*40+b'0'+b']'*40+b'}',
    b'{"nested":['+b'0,'*20000+b'0]}',
])
def test_strict_json_duplicates_numbers_fields_shape_and_safe_errors(raw):
    with pytest.raises(FinancialImportError):decode_financial_import_preview(raw)


def test_count_limits_and_plan_size_reject_whole_input():
    rows=[{**sample_rows()[0],'key':'s'+str(i)} for i in range(17)]
    with pytest.raises(FinancialImportError) as raised:parse_owner_csv(csv_text(rows))
    assert raised.value.detail['code']=='ROW_COUNT_LIMIT'
    rows=[{**sample_rows()[0],'key':'s'+str(i).zfill(31),'url':'https://example.invalid/'+'u'*1500,
           'excerpt':'\t'*1000,'read_scope':'\t'*700,'locator':'\t'*240} for i in range(16)]
    refs=';'.join(r['key'] for r in rows)
    rows.extend({**sample_rows()[1],'key':'o'+str(i),'source_refs':refs,'entity_scope':'e'*120,'accounting_basis':'a'*240} for i in range(64))
    # CSV is small; JSON escaping plus typed provenance/location exceeds the plan cap.
    value=csv_text(rows);assert len(value.encode())<=CSV_LIMIT
    with pytest.raises(FinancialImportError) as raised:parse_owner_csv(value)
    assert raised.value.detail['code']=='PLAN_LIMIT'


@pytest.mark.parametrize('kind,count',[('observation',65),('historical_fx',17)])
def test_other_record_count_caps(kind,count):
    base=sample_rows();template=next(r for r in base if r['row_type']==kind)
    rows=[base[0],*[{**template,'key':'r'+str(i)} for i in range(count)]]
    with pytest.raises(FinancialImportError) as raised:parse_owner_csv(csv_text(rows))
    assert raised.value.detail['code']=='ROW_COUNT_LIMIT'


def test_all_record_count_boundaries_are_available_within_byte_cap():
    base=sample_rows()
    rows=[{**base[0],'key':'s'+str(i)} for i in range(16)]
    rows.extend({**base[1],'key':'o'+str(i),'source_refs':'s0'} for i in range(64))
    rows.extend({**base[2],'key':'f'+str(i),'source_refs':'s0'} for i in range(16))
    assert len(parse_owner_csv(csv_text(rows)).records)==96


def test_typed_exports_have_only_the_one_preview_contract():
    request=FinancialImportPreviewEnvelope.model_json_schema();response=FinancialImportPreviewResponse.model_json_schema()
    assert request['additionalProperties'] is False
    assert response['$defs']['OwnerHistoricalFXV2']['properties']['declared_basis']['enum']==['disclosed','media_estimate','missing','conflicted']
    assert 'confirmed' not in request['$defs']['FinancialImportPreviewRequest']['properties']


def test_golden_csv_plan_preview_digest_and_typed_exports(tmp_path):
    value=csv_text();plan=parse_owner_csv(value)
    csv_digest=hashlib.sha256(value.encode()).hexdigest()
    plan_digest=hashlib.sha256(canonical(plan.model_dump(mode='json')).encode()).hexdigest()
    binding={'contract':CONTRACT,'parser_revision':'owner-financial-csv-v1',
             'research_id':'12345678-1234-4234-8234-123456789abc','input_revision':1,
             'problem_digest':'a'*64,'expected_research_version':1,
             'exact_received_csv_sha256':csv_digest,'key_based_plan_digest':plan_digest}
    preview_digest=hashlib.sha256(canonical(binding).encode()).hexdigest()
    assert csv_digest=='e5b053b7c8ba654fde7bd0187e70b3c80edd6df39f952abafcfba815a0f20990'
    assert plan_digest=='c818a6c2fcfe452274824fcfaf8ad8c9b38fe8565251953d4108b45071c3e0e9'
    assert preview_digest=='a6b9f6df9c0b4a904848f4b9b17ee50193e2b448ac8af07c38f7e5bd59ad3f57'
    golden={'scope':'parser_golden_only_not_Main_authority','binding':binding,'preview_digest':preview_digest,
            'plan':plan.model_dump(mode='json')}
    (tmp_path/'legal.csv').write_text(value,encoding='utf-8',newline='')
    (tmp_path/'golden.json').write_text(canonical(golden)+'\n',encoding='utf-8')
    (tmp_path/'preview-request.schema.json').write_text(canonical(FinancialImportPreviewEnvelope.model_json_schema())+'\n',encoding='utf-8')
    (tmp_path/'preview-response.schema.json').write_text(canonical(FinancialImportPreviewResponse.model_json_schema())+'\n',encoding='utf-8')
    with pytest.raises(FinancialImportError) as rejected:parse_owner_csv('\ufeff'+value)
    (tmp_path/'rejected.json').write_text(canonical({'mutation':'BOM_PREFIX','validation':rejected.value.detail})+'\n',encoding='utf-8')
    print('FINANCIAL_GOLDEN:'+json.dumps({'csv':csv_digest,'plan':plan_digest,'preview':preview_digest,'exports':str(tmp_path)}))
