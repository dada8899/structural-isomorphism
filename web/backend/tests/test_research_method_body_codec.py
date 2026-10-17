"""Canonical bytes/digest tests only; no provenance mint, SQL or durable reader."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import ast
import hashlib
import json
from pathlib import Path
import traceback
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from research import method_body_codec as codec
from research import method_body_types as types
from .test_research_method_body_types import candidate_data,binding_data,digest


def encoded(candidate,binding):
    data=types.validate_candidate_data(candidate).model_dump(mode="json")
    return codec.encode_method_body(candidate,binding,digest(data))


def test_real_original_candidate_roundtrip_preserves_every_value(candidate_data,binding_data):
    expected=types.validate_candidate_data(candidate_data).model_dump(mode="json")
    result=encoded(candidate_data,binding_data)
    decoded=codec.decode_method_body(result.raw,binding_data,result.candidate_digest,result.envelope_digest)
    assert decoded.candidate.model_dump(mode="json")==expected
    assert decoded.header.model_dump(mode="json")==binding_data
    assert result.candidate_digest==digest(expected)
    full=json.loads(result.raw);assert result.envelope_digest==digest({k:v for k,v in full.items() if k!="envelope_digest"})
    assert len(result.raw)<=32768
    with pytest.raises(FrozenInstanceError):result.raw=b"modified"
    assert not hasattr(result,"require") and not hasattr(decoded,"mint")


def test_candidate_and_envelope_digest_domains_are_independent(candidate_data,binding_data):
    original=encoded(candidate_data,binding_data)
    changed=binding_data|{"received_at":"2026-10-17T00:00:01.000000Z"}
    later=encoded(candidate_data,changed)
    assert original.candidate_digest==later.candidate_digest and original.envelope_digest!=later.envelope_digest
    with pytest.raises(types.MethodBodyValidationError):codec.decode_method_body(later.raw,binding_data,later.candidate_digest,later.envelope_digest)
    with pytest.raises(types.MethodBodyValidationError):codec.decode_method_body(original.raw,binding_data,original.envelope_digest,original.candidate_digest)


@pytest.mark.parametrize("key",["candidate_digest","envelope_digest"])
def test_each_independent_expected_digest_is_required(candidate_data,binding_data,key):
    result=encoded(candidate_data,binding_data)
    for bad in (None,True,"bad","a"*64):
        args={"expected_candidate_digest":result.candidate_digest,"expected_envelope_digest":result.envelope_digest}
        args["expected_"+key]=bad
        with pytest.raises(types.MethodBodyValidationError):codec.decode_method_body(result.raw,binding_data,**args)


@pytest.mark.parametrize("target",["header","candidate","root"])
def test_tampering_is_rejected_even_if_attacker_recomputes_internal_hashes(candidate_data,binding_data,target):
    result=encoded(candidate_data,binding_data);raw=json.loads(result.raw)
    if target=="header":raw["header"]["authorized_task_version"]=2
    elif target=="candidate":raw["candidate"]["summary"]="Changed private body."
    else:raw["trusted"]=True
    raw["candidate_digest"]=digest(raw["candidate"])
    raw["envelope_digest"]=digest({k:v for k,v in raw.items() if k!="envelope_digest"})
    with pytest.raises(types.MethodBodyValidationError):codec.decode_method_body(json.dumps(raw).encode(),binding_data,result.candidate_digest,result.envelope_digest)


def test_canonical_encoding_no_whitespace_repair_or_partial_decode(candidate_data,binding_data):
    result=encoded(candidate_data,binding_data)
    pretty=json.dumps(json.loads(result.raw),ensure_ascii=False,indent=2).encode()
    with pytest.raises(types.MethodBodyValidationError):codec.decode_method_body(pretty,binding_data,result.candidate_digest,result.envelope_digest)
    for invalid in (None,{},b'',b'\xff',b'{}',result.raw[:-1],b'{"header":1,"header":2}',b'{"header":NaN}'):
        with pytest.raises(types.MethodBodyValidationError):codec.decode_method_body(invalid,binding_data,result.candidate_digest,result.envelope_digest)


def test_null_or_erased_data_does_not_create_a_body_or_refill_permission(binding_data):
    with pytest.raises(types.MethodBodyValidationError):codec.encode_method_body(None,binding_data,"a"*64)
    with pytest.raises(types.MethodBodyValidationError):codec.decode_method_body(None,binding_data,"a"*64,"b"*64)
    with pytest.raises(types.MethodBodyValidationError):types.validate_body_binding(binding_data|{"first_return":True,"allow_refill":True})
    # The codec does not know database lifecycle. Actual no-refill remains Core's guard.


def test_full_utf8_limit_includes_binding_and_digests(candidate_data,binding_data):
    candidate_data["summary"]="观"*1000
    mechanism=candidate_data["mechanisms"][0]
    mechanism["label"]="观"*120;mechanism["mechanism"]="观"*1200
    mechanism["variable_map"]=[{"source":"观"*120,"target":"观"*120,"rationale":"观"*400} for _ in range(12)]
    mechanism["conditions"]=[];mechanism["nontransferable"]=[]
    parsed=types.validate_candidate_data(candidate_data).model_dump(mode="json")
    size=len(json.dumps(parsed,ensure_ascii=False,separators=(",",":" )).encode())
    assert size<32768
    # Add bounded per-field text until the legal candidate fits alone but not with header.
    for count in range(6):
        mechanism["conditions"]=["观"*400]*count
        try:parsed=types.validate_candidate_data(candidate_data).model_dump(mode="json")
        except types.MethodBodyValidationError:break
        candidate_size=len(json.dumps(parsed,ensure_ascii=False,separators=(",",":" )).encode())
        try:result=codec.encode_method_body(parsed,binding_data,digest(parsed))
        except types.MethodBodyValidationError as error:
            assert error.reason=="method_body_limit" and candidate_size<32768
            return
        assert len(result.raw)<=32768
    raise AssertionError("fixture did not exercise envelope-overhead rejection")


def test_payload_limits_depth_nonfinite_and_extra_do_not_leak(candidate_data,binding_data):
    result=encoded(candidate_data,binding_data)
    for raw in (b' '*32769,'观'*11000,'{"header":1.5}'):
        with pytest.raises(types.MethodBodyValidationError):codec.decode_method_body(raw,binding_data,result.candidate_digest,result.envelope_digest)
    deep={};node=deep
    for _ in range(30):node["child"]={};node=node["child"]
    with pytest.raises(types.MethodBodyValidationError):types.validate_candidate_data(deep)


@pytest.mark.parametrize("caller",["value","pydantic"])
@pytest.mark.parametrize("action",["encode","decode","constructed"])
def test_all_codec_rejection_paths_clear_outer_private_exception_context(candidate_data,binding_data,caller,action):
    canary="PRIVATE-METHOD-CODEC-CANARY"
    result=encoded(candidate_data,binding_data)
    try:
        if caller=="value":raise ValueError(canary)
        types.MethodBodyBinding.model_validate({"input_digest":canary})
    except (ValueError,ValidationError):
        with pytest.raises(types.MethodBodyValidationError) as stopped:
            if action=="encode":codec.encode_method_body({"private":canary},binding_data,result.candidate_digest)
            elif action=="decode":codec.decode_method_body(b"{}",binding_data,result.candidate_digest,result.envelope_digest)
            else:codec.encode_method_body(candidate_data,types.MethodBodyBinding.model_validate(binding_data).model_copy(update={"input_revision":canary}),result.candidate_digest)
        safe=stopped.value
        assert BaseException.__dict__["__context__"].__get__(safe) is None
        assert BaseException.__dict__["__cause__"].__get__(safe) is None and safe.__suppress_context__ is False
        assert canary not in str(safe)+repr(vars(safe))+"".join(traceback.format_exception(type(safe),safe,safe.__traceback__))


def test_pure_codec_has_no_guard_reader_or_control_factory_dependencies(candidate_data,binding_data):
    with patch("socket.socket",side_effect=AssertionError("no network")),patch("sqlite3.connect",side_effect=AssertionError("no DB")),patch("subprocess.Popen",side_effect=AssertionError("no process")):
        result=encoded(candidate_data,binding_data)
        assert codec.decode_method_body(result.raw,binding_data,result.candidate_digest,result.envelope_digest)
    tree=ast.parse(Path(codec.__file__).read_text())
    imports=[node.module or "" for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
    assert imports==["dataclasses","method_body_types"]
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id.startswith('mint') for n in ast.walk(tree))
