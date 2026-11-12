"""Product's three families as actual inputs, plus development-only variants.

These are not independent held-out acceptance cases or Linux evidence on Mac.
No expected result is substituted into the API or persistence layer.
"""
import sys
import pytest
from .test_research_persistence import stack
from .test_research_formula_public import side,request,draft_request
from .test_research_formula_lifecycle import create_formula,formula_problem,check


def cases():
    queue=[]
    for number,(arrival,wait,count) in enumerate((('3','4','12'),('5','2.5','12.5'))):
        left=side('little',values={'lambda':arrival,'w':wait,'l':count})
        right=side('little','b',values={'lambda':arrival,'w':wait,'l':count})
        queue.append((f'little-{number}',request(left,right,scope='expression',points=['0']),'algebraic_identity'))
    queue.append(('mm1-variant',request(side('mm1',values={'lambda':'2','mu':'6','w':'0.25'}),side('mm1','b',values={'lambda':'2','mu':'6','w':'0.25'}),points=['0']),'conditional_model_equivalence'))
    storage=[]
    for number,(r,c,x0,rr,cc,y0) in enumerate((('4','2','8','5','1','3'),('2','3','10','7','2','4'),('1','2','1','4','2','9'))):
        storage.append((f'passive-{number}',request(side('passive_decay',values={'r':r,'c':c},amplitude=x0),side('passive_decay','b',electrical=True,values={'r':rr,'c':cc},amplitude=y0),scope='initial_value_problem',points=['0','1','2']),'conditional_model_equivalence'))
    local=[]
    for number,(r,c,k) in enumerate((('4','2','0.25'),('2','4','0.125'),('3','2','0.2'))):
        local.append((f'local-{number}',request(side('passive_decay',values={'r':r,'c':c}),side('linear_stable','b',values={'k':k}),scope='equation_form',points=['0','1','2']),'local_approximation'))
    return queue+storage+local


@pytest.mark.parametrize('name,data,relation',cases(),ids=[v[0] for v in cases()])
def test_product_inputs_run_through_actual_saved_snapshot_and_guarded_api(stack,name,data,relation):
    client,path=stack
    problem=formula_problem();problem['formula_draft']={'input_origin':'user_provided',**draft_request(data)}
    rid,body=create_formula(client,problem)
    started=check(client,rid,body)
    assert started.status_code==200,started.text
    ref=started.json()['data']['result_ref'];opened=client.get(f'/api/research/{rid}/formula-results/{ref}')
    assert opened.status_code==200,opened.text
    result=opened.json()['data'];outcomes={item['check_kind']:item for item in result['result']['outcomes']}
    if sys.platform=='linux':
        assert result['provenance']['execution_attested'] is True
        assert outcomes['canonical_transform']['status']=='passed'
        assert outcomes['canonical_transform']['relation']==relation
        assert outcomes['bounded_numeric']['status']=='passed'
        assert outcomes['bounded_numeric']['relation']=='undetermined'
        if name=='passive-0':
            samples=outcomes['bounded_numeric']['samples']
            assert [v['left']['physical_time'] for v in samples]==['0','8','16']
            assert [v['right']['physical_time'] for v in samples]==['0','5','10']
    else:
        assert result['provenance']['execution_attested'] is False
        assert {item['status'] for item in outcomes.values()}=={'unsupported'}
        assert result['provenance']['resource_guard']=='not_executed'
    assert result['result']['execution_attested'] is False
