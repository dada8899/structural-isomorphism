"""Public DTO/schema consumers, synthetic shapes and actual offline Core output.

No provider/model/fresh-funding claims. Existing source fixtures use loopback only.
"""
from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path
import traceback
from uuid import uuid4

import pytest
from pydantic import ValidationError

from research import paid_api_public as public
from research.schemas import PaidPreviewEnvelope, PaidConfirmationEnvelope
from research.errors import ResearchError

# Existing frozen auth/DB/loopback fixtures. No application or request-reader patch.
from .test_research_persistence import stack, post
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs
from .test_research_paid_api import paid_api, preview_data, confirm_data, counts


def uid(): return str(uuid4())
def digest(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def envelope(data): return {"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":data}


def stamp(sample):
    sample["data"]["manifest_digest"]=digest(sample["data"]["manifest"])
    sample["data"]["preview_digest"]=digest({k:v for k,v in sample["data"].items() if k!="preview_digest"})
    return sample


@pytest.fixture
def preview_sample():
    # Shape fixture only; this invented example is not read source/provider evidence.
    quote="Synthetic mechanism."
    source={"source_id":uid(),"source_revision":1,"excerpt_id":uid(),"title":"Synthetic method",
        "canonical_url":"https://example.test/method?id=1","attribution":"Example Authors (2026), synthetic fixture",
        "raw_digest":"a"*64,"extracted_digest":"b"*64,"discovery_digest":"c"*64,"permission_basis_digest":"d"*64,
        "start":3,"end":3+len(quote),"quote":quote,"read_scope":"author_narrative_subset",
        "acquired_at":"2026-10-17T00:00:00.000000Z","information_cutoff":"2026-10-17","may_send_to_provider":False}
    handle={k:source[k] for k in ("source_id","source_revision","excerpt_id","title","attribution","extracted_digest","start","end","quote")}|{"handle":"e1"}
    return stamp(envelope({"preview_ref":uid(),"preview_version":1,"status":"draft","expires_at":"2026-10-17T00:00:10.000000Z",
        "bindings":{"research_id":uid(),"input_revision":1,"input_digest":"e"*64,"research_version":2},
        "purpose":"method_hypothesis","provider":"deepseek","model":"deepseek-flash","declared_model_version":"DeepSeek-V4.1-Flash",
        "execution_mode":"offline_probe","policy_revision":"bounded_usage_upper_v2",
        "quote":{"revision":uid(),"digest":"f"*64,"valid_until":"2026-10-17T00:00:20.000000Z"},
        "maximum_reserve":{"currency":"CNY","scale":6,"amount_units":3},"actual":None,"cost_label":"maximum_reserve_not_actual","max_calls":1,
        "manifest":{"problem_summary":"Synthetic saved summary","sources":[source],"handles":[handle]},
        "manifest_digest":"0"*64,"outbound_request_digest":"1"*64,"preview_digest":"2"*64,"may_send_to_provider":False,"model_analysis_ran":False}))


@pytest.fixture
def confirmation_sample(preview_sample):
    p=preview_sample["data"]
    return envelope({"approval_ref":p["preview_ref"],"preview_ref":p["preview_ref"],"preview_version":1,"preview_digest":p["preview_digest"],
        "research_version":3,"task_id":uid(),"task_version":1,"execution":"QUEUED","status":"queued","execution_mode":"offline_probe","model_analysis_ran":False})


def test_success_helpers_preserve_exact_data_and_return_independent_copies(preview_sample,confirmation_sample):
    original=deepcopy(preview_sample)
    result=public.validate_success_response("paid-preview",preview_sample)
    assert result==original and preview_sample==original
    result["data"]["manifest"]["sources"][0]["quote"]="changed"
    assert preview_sample==original
    assert public.validate_success_response("paid-confirm",confirmation_sample)==confirmation_sample


@pytest.mark.parametrize("path,value",[
    (("data","maximum_reserve","currency"),"USD"),(("data","maximum_reserve","scale"),6.0),
    (("data","maximum_reserve","amount_units"),True),(("data","maximum_reserve","amount_units"),-1),
    (("data","maximum_reserve","amount_units"),2**63),(("data","maximum_reserve","amount_units"),"3"),
    (("data","max_calls"),True),(("data","max_calls"),1.0),(("data","max_calls"),2),
    (("data","preview_version"),True),(("data","preview_version"),1.0),(("data","preview_version"),"1"),
    (("data","actual"),0),(("data","actual"),False),(("data","actual"),{}),
    (("data","may_send_to_provider"),0),(("data","may_send_to_provider"),True),
    (("data","model_analysis_ran"),0),(("data","model_analysis_ran"),True),
    (("data","execution_mode"),"live"),(("data","policy_revision"),"deepseek-bounded-upper-v1"),
    (("data","provider"),"other"),(("data","declared_model_version"),"made-up"),
    (("data","expires_at"),"2026-10-17T00:00:30.000000Z"),(("data","quote","valid_until"),"2026-13-17T00:00:20.000000Z"),
    (("data","bindings","input_revision"),True),(("data","quote","revision"),"not-a-uuid"),
])
def test_invalid_preview_types_rejected_without_coercion(preview_sample,path,value):
    target=preview_sample
    for part in path[:-1]:target=target[part]
    target[path[-1]]=value
    stamp(preview_sample)  # Isolate the type/invariant, not a stale preview digest.
    with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-preview",preview_sample)


@pytest.mark.parametrize("location",[(),("data",),("data","quote"),("data","maximum_reserve"),("data","bindings"),
    ("data","manifest"),("data","manifest","sources",0),("data","manifest","handles",0)])
def test_private_or_unknown_nested_fields_are_not_silently_dropped(preview_sample,location):
    target=preview_sample
    for part in location:target=target[part]
    target["authority"]={"private_token":"PRIVATE-SCHEMA-CANARY"}
    stamp(preview_sample)
    with pytest.raises(public.PaidPublicValidationError) as caught:public.validate_success_response("paid-preview",preview_sample)
    exc=caught.value
    assert exc.__context__ is None and exc.__cause__ is None
    text=str(exc)+repr(vars(exc))+"".join(traceback.format_exception(type(exc),exc,exc.__traceback__))
    assert "PRIVATE-SCHEMA-CANARY" not in text and "input_value" not in text


@pytest.mark.parametrize("field,value",[("start",True),("start",-1),("end",200001),("end",3),("source_revision",True),("may_send_to_provider",0),("information_cutoff","2026-02-30"),("read_scope","legacy_page_unverified"),("canonical_url","file:///private/source")])
def test_source_span_types_and_scope_rejected(preview_sample,field,value):
    preview_sample["data"]["manifest"]["sources"][0][field]=value
    stamp(preview_sample)
    with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-preview",preview_sample)


def test_manifest_correspondence_and_digest_checks(preview_sample):
    wrong=deepcopy(preview_sample);wrong["data"]["manifest"]["handles"][0]["excerpt_id"]=uid();stamp(wrong)
    with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-preview",wrong)
    for field in ("manifest_digest","preview_digest"):
        wrong=deepcopy(preview_sample);wrong["data"][field]="3"*64
        with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-preview",wrong)
    wrong=deepcopy(preview_sample)
    for name in ("sources","handles"):wrong["data"]["manifest"][name]*=2
    stamp(wrong)
    with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-preview",wrong)


def test_exact_decomposed_unicode_is_not_normalized_or_rehashed(preview_sample):
    quote="e\u0301 mechanistic description"
    for name in ("sources","handles"):
        span=preview_sample["data"]["manifest"][name][0];span.update(quote=quote,end=span["start"]+len(quote))
    stamp(preview_sample)
    result=public.validate_success_response("paid-preview",preview_sample)
    assert result==preview_sample and result["data"]["manifest"]["sources"][0]["quote"]==quote


@pytest.mark.parametrize("field,value",[("preview_version",True),("task_version",1.0),("research_version","3"),("execution_mode","live"),("model_analysis_ran",0),("execution","invented"),("status","finished"),("context",{})])
def test_confirmation_success_rejects_invalid_types_and_private_fields(confirmation_sample,field,value):
    confirmation_sample["data"][field]=value
    with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-confirm",confirmation_sample)


def test_confirmation_replay_actual_current_state_has_declared_schema(confirmation_sample):
    confirmation_sample["data"].update(execution="CANCELLED",status="cancelled",task_version=2)
    assert public.validate_success_response("paid-confirm",confirmation_sample)==confirmation_sample


def test_error_envelope_reuses_real_safe_research_error_shape(caplog):
    body=ResearchError("INPUT_INVALID",422,"研究内容不符合要求。").body()
    assert public.validate_error_response(body)==body
    for location in (body,body["error"]):
        wrong=deepcopy(body)
        (wrong if location is body else wrong["error"])["input"]="PRIVATE-ERROR-CANARY"
        with pytest.raises(public.PaidPublicValidationError) as caught:public.validate_error_response(wrong)
        assert "PRIVATE-ERROR-CANARY" not in str(caught.value)+repr(vars(caught.value))
        assert caught.value.__context__ is None
    assert "PRIVATE-ERROR-CANARY" not in caplog.text


def test_response_limit_is_real_utf8_and_rejects_cycles_or_non_json(preview_sample):
    with pytest.raises(public.PaidPublicValidationError) as caught:
        public.validate_success_response("paid-preview",{"private":"测"*180000})
    assert caught.value.reason=="public_payload_limit"  # chars <512KiB, UTF-8 bytes >512KiB.
    wrong={};wrong["cycle"]=wrong
    with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-preview",wrong)
    for value in (float("nan"),object(),"\ud800"):
        wrong=deepcopy(preview_sample);wrong["data"]["actual"]=value
        with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-preview",wrong)


@pytest.mark.parametrize("operation,model",[("paid-preview",PaidPreviewEnvelope),("paid-confirm",PaidConfirmationEnvelope)])
def test_request_schema_comes_from_original_model_and_has_no_dangling_refs(operation,model):
    body=public.request_body_schema(operation)
    schema=body["content"]["application/json"]["schema"]
    original=model.model_json_schema()
    assert body["required"] is True and schema["title"]==model.__name__
    assert schema["required"]==original["required"] and schema["additionalProperties"] is False
    data_model=model.model_fields["data"].annotation
    expected=data_model.model_json_schema()
    data=schema["properties"]["data"]
    assert set(data["properties"])==set(data_model.model_fields)
    assert data["required"]==expected["required"] and data["additionalProperties"] is False
    assert '"$ref"' not in json.dumps(schema) and '"$defs"' not in json.dumps(schema)
    if operation=="paid-preview":assert data["properties"]["excerpt_ids"]["uniqueItems"] is True
    else:
        for field in ("confirm_external_input","confirm_maximum_reserve"):
            assert data["properties"][field]["type"]=="boolean" and data["properties"][field]["const"] is True
    body["required"]=False
    assert public.request_body_schema(operation)["required"] is True


def test_original_request_runtime_strictness_is_not_replaced_by_schema_helper():
    good=envelope({"input_revision":1,"expected_research_version":1,"excerpt_ids":[uid()],"purpose":"method_hypothesis"})
    public.request_body_schema("paid-preview")
    assert PaidPreviewEnvelope.model_validate(good).data.input_revision==1
    for value in (True,1.0,"1"):
        wrong=deepcopy(good);wrong["data"]["input_revision"]=value
        with pytest.raises(ValidationError):PaidPreviewEnvelope.model_validate(wrong)
    wrong=deepcopy(good);wrong["data"]["excerpt_ids"]*=2
    with pytest.raises(ValidationError):PaidPreviewEnvelope.model_validate(wrong)


def test_original_confirmation_request_retains_explicit_strict_true_checks(preview_sample):
    view=preview_sample["data"]
    data={"preview_ref":view["preview_ref"],"expected_preview_version":view["preview_version"],"input_revision":1,
        "expected_research_version":2,"preview_digest":view["preview_digest"],"confirm_external_input":True,"confirm_maximum_reserve":True}
    public.request_body_schema("paid-confirm")
    assert PaidConfirmationEnvelope.model_validate(envelope(data)).data.confirm_external_input is True
    for name in ("confirm_external_input","confirm_maximum_reserve"):
        for value in (False,1,"true",None):
            wrong=deepcopy(data);wrong[name]=value
            with pytest.raises(ValidationError):PaidConfirmationEnvelope.model_validate(envelope(wrong))


@pytest.mark.parametrize("field,value",[("code","private@example.test"),("retryable",1),("retryable","true"),
    ("incident_id","private@example.test"),("allowed_next_actions",["send_paid"]),("allowed_next_actions",["sign_in","sign_in"]),
    ("message","private\u0000text")])
def test_error_dto_is_strict_without_reflecting_validation_material(field,value):
    error=ResearchError("INPUT_INVALID",422,"受控错误提示。").body();error["error"][field]=value
    with pytest.raises(public.PaidPublicValidationError) as caught:public.validate_error_response(error)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert "private@example.test" not in str(caught.value)+repr(vars(caught.value))


def test_quote_word_limit_and_manifest_length_remain_bounded(preview_sample):
    for name in ("sources","handles"):
        span=preview_sample["data"]["manifest"][name][0];span.update(quote="word "*21,end=span["start"]+len("word "*21))
    stamp(preview_sample)
    with pytest.raises(public.PaidPublicValidationError):public.validate_success_response("paid-preview",preview_sample)


@pytest.mark.parametrize("operation",["paid-preview","paid-confirm"])
def test_success_schema_has_only_local_public_components(operation):
    schema=public.success_response_model(operation).model_json_schema()
    def visit(value):
        if isinstance(value,dict):
            if "$ref" in value:
                assert value["$ref"].startswith("#/$defs/")
                assert value["$ref"].split("/")[-1] in schema["$defs"]
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(schema)
    text=json.dumps(schema)
    for forbidden in ("CurrentPaidAuthority","PrivateBindingRef","CallContext","BudgetBasisSnapshot","peak_input_miss_units_per_million","extracted_text","funding_epoch"):
        assert forbidden not in text


def test_public_module_has_no_private_control_codec_or_io_imports():
    tree=ast.parse(Path(public.__file__).read_text())
    imported=[node.module or "" for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
    assert not any(name.startswith(("api","provider_","paid_approval","paid_control","store","budget","usage_upper","preview_codec")) for name in imported)
    for operation in ("bad",None,True,[]):
        with pytest.raises(public.PaidPublicValidationError):public.request_body_schema(operation)
        with pytest.raises(public.PaidPublicValidationError):public.success_response_model(operation)


@pytest.mark.parametrize("operation",["paid-preview","paid-confirm"])
def test_declarations_attach_to_request_only_handler_with_resolvable_public_refs(operation):
    from fastapi import FastAPI, Request
    app=FastAPI()
    async def declaration_only(request:Request):
        raise AssertionError("schema consumer must never execute a handler")
    app.add_api_route("/contract-metadata",declaration_only,methods=["POST"],
        responses={200:{"model":public.success_response_model(operation)},422:{"model":public.ResearchPublicErrorEnvelope}},
        openapi_extra={"requestBody":public.request_body_schema(operation)})
    schema=app.openapi();op=schema["paths"]["/contract-metadata"]["post"]
    assert op["requestBody"]==public.request_body_schema(operation)
    assert op["responses"]["200"]["content"]["application/json"]["schema"]
    def check(value):
        if isinstance(value,dict):
            if "$ref" in value:
                target=schema
                for part in value["$ref"].removeprefix("#/").split("/"):target=target[part]
                assert isinstance(target,dict)
            for child in value.values():check(child)
        elif isinstance(value,list):
            for child in value:check(child)
    check(schema)


def test_actual_offline_core_preview_and_confirm_payloads_pass_without_new_execution(paid_api):
    client,_,store,rid,excerpt,_=paid_api
    result=post(client,"/api/research/"+rid+"/paid-previews",preview_data(client,rid,excerpt),"public-types-preview")
    assert result.status_code==200,result.text
    original=result.json()
    assert public.validate_success_response("paid-preview",original)==original
    confirmation=post(client,"/api/research/"+rid+"/paid-approvals",confirm_data(original["data"]),"public-types-confirm")
    assert confirmation.status_code==200,confirmation.text
    assert public.validate_success_response("paid-confirm",confirmation.json())==confirmation.json()
    assert public.validate_success_response("paid-confirm",post(client,"/api/research/"+rid+"/paid-approvals",confirm_data(original["data"]),"public-types-confirm").json())==confirmation.json()
    actual=counts(store)
    for name in ("research_reservations","research_dispatch_permits","research_cost_observations","research_provider_sessions"):
        assert actual[name]==0
