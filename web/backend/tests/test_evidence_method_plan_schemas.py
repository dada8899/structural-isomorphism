"""Strict data only; no native registry or Main enablement."""
import copy,json
from pathlib import Path
import pytest
from research import evidence_method_plan_schemas as t
from research import evidence_method_plan_codec as c
FIXTURE=Path(__file__).parent/'fixtures/evidence_method_plan/v1'

def sample():return json.loads((FIXTURE/'golden-input.json').read_bytes())

def test_selected_order_visible_text_and_frozen_data():
    value=t.SelectedEvidenceMethodInput.model_validate(sample())
    assert value.handles[0].read_scope=='author_narrative_subset'
    with pytest.raises(Exception):value.purpose='other'

@pytest.mark.parametrize('change',['extra','purpose','handle','duplicate','word_limit','controls','bool','float'])
def test_strict_input_rejects_ambiguous_or_foreign_fields(change):
    data=sample()
    if change=='extra':data['authority']=True
    elif change=='purpose':data['purpose']='phenomenon_plan_v1'
    elif change=='handle':data['handles'][0]['handle']='e2'
    elif change=='duplicate':data['handles']*=2
    elif change=='word_limit':data['handles'][0]['quote']=' '.join(['x']*21)
    elif change=='controls':data['problem_context']['summary']='bad\u200b hidden text'
    elif change=='bool':data['handles'][0]['origin']=True
    else:data['problem_context']['summary']=1.5
    with pytest.raises(ValueError):t.SelectedEvidenceMethodInput.model_validate(data)
