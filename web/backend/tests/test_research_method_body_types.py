"""Pure §13 data fixtures. No actual receipt, authority, packet or source proof."""
from copy import deepcopy
import ast
import importlib.util
import hashlib
import json
from pathlib import Path
import traceback
from uuid import uuid4

import pytest
from pydantic import ValidationError
from research import method_body_types as types
from research.model_report import ModelReportCandidate

# Reuse only the original pure candidate builder; transport/packet fixtures unused.
_file=Path(__file__).resolve().parents[3]/"tests"/"test_research_provider_adapter.py"
_spec=importlib.util.spec_from_file_location("existing_method_candidate_fixture",_file)
_existing=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_existing)


def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


@pytest.fixture
def candidate_data():return _existing.candidate()


@pytest.fixture
def binding_data():
    uid=lambda:str(uuid4());session=uid()
    return {"result_ref":session,"research_id":uid(),"task_id":uid(),"step_id":uid(),"input_revision":1,"input_digest":"a"*64,
        "approval_ref":uid(),"dispatch_id":uid(),"permit_id":uid(),"approval_consumed_version":3,"permit_state":"consumed",
        "session_consumed_version":2,"authorized_task_version":1,"authorized_step_version":1,
        "request_digest":"b"*64,"evidence_digest":"c"*64,"financial_return_ref":session,"financial_return_digest":"d"*64,
        "candidate_schema":"ModelReportCandidate-v1","body_schema":"OwnedMethodBody-v1","producer_revision":"synthetic-B-data-fixture-v1",
        "execution_mode":"offline_probe","received_at":"2026-10-17T00:00:00.000000Z"}


def test_original_candidate_model_is_reused_without_a_relaxed_copy(candidate_data):
    original=ModelReportCandidate.model_validate_json(json.dumps(candidate_data))
    parsed=types.validate_candidate_data(candidate_data)
    assert type(parsed) is ModelReportCandidate
    assert parsed.model_dump(mode="json")==original.model_dump(mode="json")
    assert types.ModelReportCandidate is ModelReportCandidate


@pytest.mark.parametrize("mutation",["no_gaps","duplicate_handle","long_summary","extra","nested_extra","url","verified_claim"])
def test_original_intrinsics_and_pure_public_text_guard(candidate_data,mutation):
    if mutation=="no_gaps":candidate_data.update(mechanisms=[],gaps=[])
    elif mutation=="duplicate_handle":candidate_data["mechanisms"][0]["evidence_handles"]=["e1","e1"]
    elif mutation=="long_summary":candidate_data["summary"]="x"*1001
    elif mutation=="extra":candidate_data["checked"]=True
    elif mutation=="nested_extra":candidate_data["mechanisms"][0]["level"]="verified"
    elif mutation=="url":candidate_data["summary"]="Read https://example.invalid"
    else:candidate_data["summary"]="The success probability is 99 percent."
    with pytest.raises(types.MethodBodyValidationError):types.validate_candidate_data(candidate_data)


def test_handle_membership_is_explicitly_outside_pure_data_validation(candidate_data):
    candidate_data["mechanisms"][0]["evidence_handles"]=["different_handle"]
    assert types.validate_candidate_data(candidate_data).mechanisms[0].evidence_handles==("different_handle",)
    # No packet/authority/source reader is supplied or created by this shape check.


def test_binding_is_plain_data_and_does_not_construct_permission(binding_data):
    model=types.validate_body_binding(binding_data)
    expected=types.ExpectedMethodBodyBinding.model_validate(binding_data)
    assert types.validate_body_binding(expected).model_dump(mode="json")==binding_data
    assert model.model_dump(mode="json")==binding_data
    for absent in ("authorize","require","send","mint","current_source","conn","lease"):
        assert not hasattr(model,absent)


@pytest.mark.parametrize("field,value",[("input_revision",True),("approval_consumed_version",3.0),("session_consumed_version","2"),
    ("authorized_task_version",0),("authorized_step_version",True),("permit_state","prepared"),
    ("permit_consumed_version",2),("dispatch_consumed_version",2),("producer_revision",""),("execution_mode","live"),
    ("received_at","2026-02-30T00:00:00.000000Z"),("received_at","2026-10-17T00:00:00Z"),
    ("financial_return_ref",str(uuid4())),("request_digest",True),("evidence_digest","bad"),
    ("candidate_schema","PhenomenonPlanCandidate-v1"),("body_schema","old"),("authorized",True),("allow_refill",True)])
def test_binding_strict_fields_no_fake_versions_or_flags(binding_data,field,value):
    binding_data[field]=value
    with pytest.raises(types.MethodBodyValidationError):types.validate_body_binding(binding_data)


def test_model_construct_and_copy_are_revalidated_before_warning_dump(candidate_data,binding_data,recwarn):
    canary="PRIVATE-CONSTRUCTED-BODY-CANARY"
    bad=ModelReportCandidate.model_construct(**{**candidate_data,"summary":object()})
    with pytest.raises(types.MethodBodyValidationError):types.validate_candidate_data(bad)
    bad_header=types.MethodBodyBinding.model_validate(binding_data).model_copy(update={"input_revision":canary})
    with pytest.raises(types.MethodBodyValidationError):types.validate_body_binding(bad_header)
    assert not any(canary in str(item.message) for item in recwarn)


@pytest.mark.parametrize("caller",["value","pydantic"])
@pytest.mark.parametrize("helper",["binding","candidate","digest"])
def test_validation_failure_detaches_real_outer_error_slots(caller,helper):
    canary="PRIVATE-METHOD-TYPE-CANARY"
    try:
        if caller=="value":raise ValueError(canary)
        types.MethodBodyBinding.model_validate({"input_digest":canary})
    except (ValueError,ValidationError):
        with pytest.raises(types.MethodBodyValidationError) as stopped:
            if helper=="binding":types.validate_body_binding({"private":canary})
            elif helper=="candidate":types.validate_candidate_data({"private":canary})
            else:types.validate_expected_digest(canary)
        safe=stopped.value
        assert BaseException.__dict__["__context__"].__get__(safe) is None
        assert BaseException.__dict__["__cause__"].__get__(safe) is None and safe.__suppress_context__ is False
        assert canary not in str(safe)+repr(vars(safe))+"".join(traceback.format_exception(type(safe),safe,safe.__traceback__))


def test_model_empty_mechanisms_need_actual_nonempty_gaps(candidate_data):
    candidate_data["mechanisms"]=[]
    assert types.validate_candidate_data(candidate_data).gaps
    candidate_data["gaps"]=[]
    with pytest.raises(types.MethodBodyValidationError):types.validate_candidate_data(candidate_data)


def test_module_imports_no_body_authority_factory_or_io():
    tree=ast.parse(Path(types.__file__).read_text())
    modules=[n.module or "" for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(name.startswith(("paid_","financial_","store","api","provider_adapter","authorization")) for name in modules)


@pytest.mark.parametrize("mutation",["no_gaps","duplicate_handle"])
def test_construct_bypass_still_enforces_original_intrinsic_constraints(candidate_data,mutation):
    model=types.validate_candidate_data(candidate_data)
    if mutation=="no_gaps":bad=model.model_copy(update={"mechanisms":(),"gaps":()})
    else:
        mechanism=model.mechanisms[0].model_copy(update={"evidence_handles":("e1","e1")})
        bad=model.model_copy(update={"mechanisms":(mechanism,)})
    with pytest.raises(types.MethodBodyValidationError):types.validate_candidate_data(bad)
