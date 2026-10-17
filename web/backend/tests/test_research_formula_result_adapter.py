"""Reuse real finite pure-core outputs, never the isolated/product checker."""
from copy import deepcopy
import json
import ast
from pathlib import Path
import traceback
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from research import formula_schemas as science
from research import formula_policy as policy
from research.formula_check import evaluate_fixed_templates,FormulaChecker
from research import formula_public as public
from research import formula_result_adapter as adapter
from .test_research_formula_public import side,request,closed_side,condition


def content(data):
    expected=science.FormulaCheckInput.parse(data)
    result=evaluate_fixed_templates(expected).data()  # Pure math fixture, no task/worker created.
    return expected,result


def project(expected,result):
    return adapter.project_formula_result(result,expected_input=expected,expected_output_digest=result["output_digest"]).data()


@pytest.mark.parametrize("scope",public.SCOPES)
def test_actual_pure_core_result_keeps_scope_outcomes_limits_and_data_only_flags(scope):
    expected,result=content(request(scope=scope))
    with patch.object(FormulaChecker,"check",side_effect=AssertionError("no checker")),patch.object(policy,"comparison",side_effect=AssertionError("no comparison")),patch.object(policy,"numeric_result",side_effect=AssertionError("no math")):
        view=project(expected,result)
    assert view["comparison_scope"]==scope and view["outcomes"]==result["outcomes"]
    assert view["limitations"]==result["limitations"] and view["reported_resource_guard"]=="pure_core_not_a_sandbox"
    assert not {"id","research_id","task_id","server_id"}&view.keys()
    assert all(view[k] is False for k in ("authorization_verified","execution_attested","source_facts_verified","display_checked"))


@pytest.mark.parametrize("case,relation",[("literal","algebraic_identity"),("thermal-electric","conditional_model_equivalence"),
    ("local","local_approximation"),("partial","partial_structure")])
def test_all_four_positive_relation_classes_are_not_upgraded(case,relation):
    if case=="literal":data=request(scope="expression")
    elif case=="thermal-electric":data=request(side("passive_decay"),side("passive_decay","b",electrical=True),checks=["canonical_transform"])
    elif case=="local":data=request(side("passive_decay"),side("linear_stable","b"),checks=["canonical_transform"])
    else:data=request(closed_side(),closed_side(prefix="b"),checks=["canonical_transform"])
    expected,result=content(data);view=project(expected,result)
    assert next(v for v in view["outcomes"] if v["check_kind"]=="canonical_transform")["relation"]==relation
    assert view["execution_attested"] is False


@pytest.mark.parametrize("status",["failed","inconclusive","unsupported","resource_limit"])
def test_negative_and_incomplete_statuses_are_preserved(status):
    if status=="failed":data=request(side("mm1",values={"lambda":"4","mu":"3"}),side("mm1","b"))
    elif status=="inconclusive":
        left=side();condition(left,"same_population",None);data=request(left)
    elif status=="unsupported":
        left=side();left["template_id"]="unregistered";data=request(left)
    else:data=request(side("passive_decay",values={"r":"1e12","c":"1e12"}),side("passive_decay","b"))
    expected,result=content(data);view=project(expected,result)
    assert status in {v["status"] for v in view["outcomes"]}
    assert view["outcomes"]==result["outcomes"]


def test_zero_nonzero_ivp_counterexample_is_not_equivalent_without_hiding_other_outcomes():
    expected,result=content(request(side("passive_decay",amplitude="0"),side("passive_decay","b",amplitude="2"),scope="initial_value_problem"))
    view=project(expected,result)
    assert any(v["relation"]=="not_equivalent" for v in view["outcomes"])
    assert any(v["status"]=="failed" for v in view["outcomes"])


def test_numeric_samples_tolerance_and_trace_are_exact_copies():
    expected,result=content(request(side("passive_decay"),side("passive_decay","b",electrical=True)))
    view=project(expected,result)
    numeric=next(v for v in view["outcomes"] if v["check_kind"]=="bounded_numeric")
    assert numeric["tolerance"]["absolute"]=="1e-10"
    assert numeric["tolerance"]["relative"]=="1e-8"
    assert numeric["relation"]=="undetermined" and numeric["samples"]
    assert view["outcomes"]==result["outcomes"]


def test_curated_reference_never_becomes_product_retrieval_or_source_fact():
    expected,result=content(request())
    view=project(expected,result)
    assert all(v["declared_provenance"]=="curated_reference" for v in view["source_references"])
    assert all(v["reference_status"]=="supplied_reference_not_authorized_here" for v in view["source_references"])
    assert all(v["locator_exposed"] is False for v in view["source_references"])
    data=request();data["left"]["source_refs"][0].update(provenance="product_excerpt",locator="/private/PRIVATE-LOCATOR-CANARY")
    expected,result=content(data);view=project(expected,result)
    assert view["source_references"][0]["declared_provenance"]=="product_excerpt" and view["source_facts_verified"] is False
    assert "PRIVATE-LOCATOR-CANARY" not in json.dumps(view)


def test_display_text_is_not_checked_and_returned_copies_do_not_mutate_result():
    data=request();data["left"]["original_display"]="different formula text; no relation to supplied AST"
    expected,result=content(data);copy=deepcopy(result)
    typed=adapter.project_formula_result(result,expected_input=expected,expected_output_digest=result["output_digest"])
    view=typed.data();assert view["display_checked"] is False
    assert view["formula_displays"][0]["original_display"]==data["left"]["original_display"]
    view["outcomes"].clear()
    assert typed.data()["outcomes"] and result==copy


@pytest.mark.parametrize("expected",[None,True,{},lambda:True])
def test_callback_or_boolean_is_not_a_bound_input_or_permission(expected):
    _,result=content(request())
    with pytest.raises(public.FormulaPublicError):adapter.project_formula_result(result,expected_input=expected,expected_output_digest=result["output_digest"])


def test_caller_must_supply_separate_content_digest_and_all_request_bindings():
    expected,result=content(request())
    for digest in (None,True,"bad","a"*64):
        with pytest.raises(public.FormulaPublicError):adapter.project_formula_result(result,expected_input=expected,expected_output_digest=digest)
    wrong=deepcopy(result);wrong["input_digest"]="b"*64;wrong["output_digest"]=science.digest({k:v for k,v in wrong.items() if k!="output_digest"})
    with pytest.raises(public.FormulaPublicError):project(expected,wrong)
    wrong=deepcopy(result);wrong["comparison_scope"]="expression";wrong["output_digest"]=science.digest({k:v for k,v in wrong.items() if k!="output_digest"})
    with pytest.raises(public.FormulaPublicError):project(expected,wrong)


@pytest.mark.parametrize("target",["root","formula-ref","source-ref","outcome","trace","sample","numeric","tolerance"])
def test_nested_extra_fields_reject_even_matching_new_untrusted_digest(target):
    expected,result=content(request(side("passive_decay"),side("passive_decay","b")))
    node=result
    if target=="formula-ref":node=result["formula_refs"][0]
    elif target=="source-ref":node=result["source_refs"][0]
    elif target=="outcome":node=result["outcomes"][0]
    elif target=="trace":node=next(v for v in result["outcomes"] if v["trace"])["trace"][0]
    elif target in {"sample","numeric","tolerance"}:
        numeric=next(v for v in result["outcomes"] if v["samples"])
        node=numeric["tolerance"] if target=="tolerance" else numeric["samples"][0] if target=="sample" else numeric["samples"][0]["left"]
    node["private"]="PRIVATE-RESULT-CANARY"
    result["output_digest"]=science.digest({k:v for k,v in result.items() if k!="output_digest"})
    with pytest.raises(public.FormulaPublicError):project(expected,result)


@pytest.mark.parametrize("case",["trace-chain","kind-set","sample-status","sample-point","source-provenance","formula-digest","numeric-nan"])
def test_reported_integrity_is_checked_without_math_reexecution(case):
    expected,result=content(request(side("passive_decay"),side("passive_decay","b")))
    numeric=next(v for v in result["outcomes"] if v["samples"])
    if case=="trace-chain":next(v for v in result["outcomes"] if v["trace"])["trace"][0]["input_digest"]="a"*64
    elif case=="kind-set":result["outcomes"].pop()
    elif case=="sample-status":numeric["samples"][0]["passed"]=False
    elif case=="sample-point":numeric["samples"][0]["point"]="2"
    elif case=="source-provenance":result["source_refs"][0]["provenance"]="product_excerpt"
    elif case=="formula-digest":result["formula_refs"][0]["formula_digest"]="a"*64
    else:numeric["samples"][0]["left"]["value"]="NaN"
    result["output_digest"]=science.digest({k:v for k,v in result.items() if k!="output_digest"})
    with pytest.raises(public.FormulaPublicError):project(expected,result)


def test_bad_json_unicode_duplicatekeys_and_real_byte_limit_reject():
    expected,result=content(request())
    for raw in ('{"private":1,"private":2}',b'\xff','{"private":NaN}'):
        with pytest.raises(public.FormulaPublicError):adapter.project_formula_result(raw,expected_input=expected,expected_output_digest=result["output_digest"])
    with pytest.raises(public.FormulaPublicError) as stopped:
        adapter.project_formula_result({"extra":"观"*180000},expected_input=expected,expected_output_digest=result["output_digest"])
    assert stopped.value.reason=="formula_payload_limit"


@pytest.mark.parametrize("caller",["value","pydantic"])
def test_result_error_slots_really_detach_private_outer_exception(caller):
    canary="PRIVATE-FORMULA-RESULT-CANARY"
    expected,result=content(request())
    try:
        if caller=="value":raise ValueError(canary)
        public._ReportedResult.model_validate({"input_digest":canary})
    except (ValueError,ValidationError):
        with pytest.raises(public.FormulaPublicError) as stopped:
            adapter.project_formula_result({"private":canary},expected_input=expected,expected_output_digest=result["output_digest"])
        safe=stopped.value
        assert BaseException.__dict__["__context__"].__get__(safe) is None and BaseException.__dict__["__cause__"].__get__(safe) is None
        assert safe.__suppress_context__ is False
        assert canary not in str(safe)+repr(vars(safe))+"".join(traceback.format_exception(type(safe),safe,safe.__traceback__))


def test_no_worker_database_sdk_or_network_side_effects():
    expected,result=content(request())
    with patch.object(FormulaChecker,"check",side_effect=AssertionError("no worker")),patch("socket.socket",side_effect=AssertionError("no network")),patch("sqlite3.connect",side_effect=AssertionError("no DB")),patch("subprocess.Popen",side_effect=AssertionError("no process")):
        assert project(expected,result)["execution_attested"] is False
        assert public.parse_formula_draft({k:v for k,v in expected.left.data().items() if k not in {"id","revision","source_refs"}})
    for module in (public,adapter):
        tree=ast.parse(Path(module.__file__).read_text())
        names=[n.module or "" for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        assert not any(v.startswith(("formula_check","provider","paid","api","store","budget","usage_upper")) for v in names)
