"""Canonical §13 data codec, never a provenance mint, writer or durable reader.

Core must supply independently controlled expectations. Recomputing expectations
from the same raw body can only demonstrate internal content consistency.
NULL/erasure/no-refill and source permissions require the future Core guard.
"""
from dataclasses import dataclass,field
import hashlib

from .method_body_types import (OwnedMethodBodyData,
    MethodBodyValidationError,MAX_BODY_BYTES,_canonical,_json_data,_Limit,_fail,
    validate_body_binding,validate_candidate_data,validate_expected_digest)


@dataclass(frozen=True,slots=True)
class EncodedMethodBodyData:
    raw:bytes=field(repr=False)
    candidate_digest:str
    envelope_digest:str


def encode_method_body(candidate_data,expected_binding,expected_candidate_digest):
    """Encode validated content, not an actual OwnedReceipt or source capability."""
    binding=validate_body_binding(expected_binding)
    expected_candidate_digest=validate_expected_digest(expected_candidate_digest)
    candidate=validate_candidate_data(candidate_data).model_dump(mode="json")
    digest=hashlib.sha256(_canonical(candidate)).hexdigest()
    if digest!=expected_candidate_digest:_fail("method_body_candidate_digest_mismatch")
    content={"header":binding.model_dump(mode="json"),"candidate":candidate,"candidate_digest":digest}
    envelope_digest=hashlib.sha256(_canonical(content)).hexdigest()
    raw=_canonical({**content,"envelope_digest":envelope_digest})
    if len(raw)>MAX_BODY_BYTES:_fail("method_body_limit")
    return EncodedMethodBodyData(raw,digest,envelope_digest)


def decode_method_body(raw,expected_binding,expected_candidate_digest,expected_envelope_digest):
    """Strict canonical content decode. No callback, authority or storage lookup."""
    binding=validate_body_binding(expected_binding)
    candidate_digest=validate_expected_digest(expected_candidate_digest)
    envelope_digest=validate_expected_digest(expected_envelope_digest)
    if type(raw) not in {bytes,str}:_fail("method_body_bytes_required")
    reason=None
    try:
        data=_json_data(raw)
        if set(data)!={"header","candidate","candidate_digest","envelope_digest"}:raise ValueError("exact envelope required")
        actual_binding=validate_body_binding(data["header"])
        if _canonical(actual_binding.model_dump(mode="json"))!=_canonical(binding.model_dump(mode="json")):
            _fail("method_body_binding_mismatch")
        encoded=encode_method_body(data["candidate"],binding,candidate_digest)
        if data["candidate_digest"]!=candidate_digest or data["envelope_digest"]!=envelope_digest or encoded.envelope_digest!=envelope_digest:
            _fail("method_body_envelope_digest_mismatch")
        original=raw if type(raw) is bytes else raw.encode("utf-8")
        if original!=encoded.raw:_fail("method_body_not_canonical")
        result=OwnedMethodBodyData.model_validate_json(encoded.raw)
    except MethodBodyValidationError:raise
    except _Limit:reason="method_body_limit"
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError,UnicodeError):reason="invalid_method_body_data"
    if reason:_fail(reason)
    return result
