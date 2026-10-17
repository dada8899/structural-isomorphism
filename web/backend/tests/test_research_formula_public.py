"""Draft DTOs reuse the approved science parsers; no execution or authorization."""
from copy import deepcopy
import ast
import importlib.util
import json
from pathlib import Path
import traceback
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from research import formula_public as public
from research import formula_schemas as science

# Reuse existing finite fixture builders as data. No worker, tests or network run.
_path=Path(__file__).resolve().parents[3]/"tests"/"test_research_formula.py"
_spec=importlib.util.spec_from_file_location("existing_formula_fixture_data",_path)
_existing=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_existing)
side=_existing.side
request=_existing.request
closed_side=_existing.closed_side
condition=_existing.condition


def draft_side(form):return {k:v for k,v in form.items() if k not in {"id","revision","source_refs"}}
def draft_request(data):return {"comparison_scope":data["comparison_scope"],"left":draft_side(data["left"]),
    "right":None if data["right"] is None else draft_side(data["right"]),"requested_checks":data["requested_checks"],"sample_points":data["sample_points"]}


@pytest.mark.parametrize("template",["little","mm1","passive_decay","linear_stable"])
def test_draft_reuses_actual_approved_component_parsers(template):
    form=side(template);raw=draft_side(form)
    parsed=public.parse_formula_draft(raw)
    old=science.FormulaInput.parse(form).data()
    assert parsed.data()==draft_side(old)
    view=public.formula_draft_view(raw)
    assert view["formula"]==parsed.data()
    for key in ("authorization_verified","execution_attested","source_facts_verified","display_checked"):assert view[key] is False
    assert not {"id","task_id","research_id","source_refs"}&parsed.data().keys()


@pytest.mark.parametrize("scope",public.SCOPES)
def test_three_scopes_and_all_four_check_kinds_are_content_only(scope):
    raw=draft_request(request(scope=scope))
    parsed=public.parse_comparison_draft(raw)
    assert parsed.data()["comparison_scope"]==scope
    assert parsed.data()["requested_checks"]==list(public.CHECKS)
    assert len(parsed.content_digest)==64 and not hasattr(parsed,"task_id")


@pytest.mark.parametrize("field,value",[("id","client-id"),("task_id","client-task"),("research_id","client-research"),
    ("source_refs",[]),("source_facts_verified",True),("still_authorized",True),("callback",True),("checked",True)])
def test_untrusted_draft_cannot_supply_authoritative_context(field,value):
    data=draft_side(side());data[field]=value
    with pytest.raises(public.FormulaPublicError):public.parse_formula_draft(data)


@pytest.mark.parametrize("change",[{"family":"arbitrary"},{"template_id":"ou_process"},{"family":"queue_flow","template_id":"linear_stable"}])
def test_unregistered_family_or_template_is_rejected_without_solver(change):
    with pytest.raises(public.FormulaPublicError) as stopped:public.parse_formula_draft(draft_side(side())|change)
    assert stopped.value.reason=="formula_not_supported"


@pytest.mark.parametrize("node",[{"op":"call","name":"eval"},{"op":"symbol","id":"x","unknown":True},
    {"op":"const","value":True},{"op":"const","value":float('inf')},{"op":"const","value":"NaN"},
    {"op":"pow_int","base":{"op":"symbol","id":"x"},"exponent":True}])
def test_ast_is_only_old_strict_json_nodes(node):
    data=draft_side(side());data["expression"]=node
    with pytest.raises(public.FormulaPublicError):public.parse_formula_draft(data)


def test_no_new_recursive_parser_or_string_execution():
    data=draft_side(side());data["original_display"]='__import__("os").system("not executed")'
    with patch("subprocess.Popen",side_effect=AssertionError("no process")),patch("builtins.eval",side_effect=AssertionError("no eval")):
        view=public.formula_draft_view(data)
    assert view["formula"]["original_display"]==data["original_display"] and view["display_checked"] is False


def test_units_aliases_and_declarations_remain_strict_shape_only():
    data=draft_side(side());data["symbols"][0]["unit_id"]="invented"
    with pytest.raises(public.FormulaPublicError):public.parse_formula_draft(data)
    data=draft_side(side());data["symbols"].append(deepcopy(data["symbols"][0]))
    with pytest.raises(public.FormulaPublicError):public.parse_formula_draft(data)
    for value in (1,"true"):
        data=draft_side(side());data["assumptions"][0]["declared_satisfied"]=value
        with pytest.raises(public.FormulaPublicError):public.parse_formula_draft(data)
    data=draft_side(side());data["assumptions"][0]["declared_satisfied"]=True
    assert public.formula_draft_view(data)["condition_assessment"]=="declarations_only"


@pytest.mark.parametrize("change",[{"comparison_scope":"fourth_scope"},{"requested_checks":["solve_anything"]},
    {"requested_checks":["template","template"]},{"sample_points":[True]},{"sample_points":["NaN"]},
    {"sample_points":["0","-0"]},{"task_id":"forged"},{"still_authorized":True}])
def test_comparison_scope_and_points_reuse_original_bounds(change):
    with pytest.raises(public.FormulaPublicError):public.parse_comparison_draft(draft_request(request())|change)


def test_single_side_allows_only_template_and_dimensions():
    data=draft_request(request());data["right"]=None
    with pytest.raises(public.FormulaPublicError):public.parse_comparison_draft(data)
    data["requested_checks"]=["template","dimensions"]
    assert public.parse_comparison_draft(data).data()["right"] is None


def test_display_bounds_unicode_body_limit_and_duplicate_json():
    data=draft_side(side());data["original_display"]="观"*2048
    assert public.parse_formula_draft(data).data()["original_display"]==data["original_display"]
    for value in ("观"*2049,"bad\u200btext","bad\ud800"):
        data["original_display"]=value
        with pytest.raises(public.FormulaPublicError):public.parse_formula_draft(data)
    with pytest.raises(public.FormulaPublicError):public.parse_formula_draft('{"family":"one","family":"two"}')
    with pytest.raises(public.FormulaPublicError) as stopped:public.parse_formula_draft({"extra":"观"*23000})
    assert stopped.value.reason=="formula_payload_limit"


def test_draft_content_copies_cannot_mutate_canonical_data():
    raw=draft_side(side());result=public.parse_formula_draft(raw);digest=result.content_digest
    returned=result.data();returned["expression"]={"op":"const","value":"99"};raw["symbols"].clear()
    assert result.content_digest==digest and result.data()["symbols"]


@pytest.mark.parametrize("helper",["side","comparison","view","constructor"])
@pytest.mark.parametrize("caller",["value","scientific"])
def test_input_error_does_not_expose_outer_private_context(helper,caller):
    canary="PRIVATE-FORMULA-DRAFT-CANARY"
    try:
        if caller=="value":raise ValueError(canary)
        raise science.FormulaInputError(canary)
    except ValueError:
        with pytest.raises(public.FormulaPublicError) as caught:
            if helper=="side":public.parse_formula_draft({"private":canary})
            elif helper=="comparison":public.parse_comparison_draft({"private":canary})
            elif helper=="view":public.formula_draft_view({"private":canary})
            else:public.FormulaDraft()
        safe=caught.value
        assert BaseException.__dict__["__context__"].__get__(safe) is None
        assert BaseException.__dict__["__cause__"].__get__(safe) is None
        assert safe.__suppress_context__ is False
        assert canary not in str(safe)+repr(vars(safe))+"".join(traceback.format_exception(type(safe),safe,safe.__traceback__))
