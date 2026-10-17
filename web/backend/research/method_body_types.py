"""§13 data-only method body types. No receipt, body source, SQL or permission.

Core supplies expectations after actual B BudgetOwnedReceipt/admission checks or
its future protected durable reader. Pure shape/digest checks cannot replace it.
"""
from datetime import datetime
import json
import re
from typing import Annotated,Literal
import unicodedata

from pydantic import BaseModel,ConfigDict,Field,StringConstraints,ValidationError,AfterValidator,model_validator
from .schemas import PaidId,PaidDigest,Revision
from .model_report import ModelReportCandidate

if __package__=="web.backend.research":
    from ..services.search_synthesis import validate_candidate_public_texts
else:
    from services.search_synthesis import validate_candidate_public_texts

BODY_SCHEMA="OwnedMethodBody-v1"
CANDIDATE_SCHEMA="ModelReportCandidate-v1"
MAX_BODY_BYTES=32*1024


class MethodBodyValidationError(ValueError):
    def __init__(self,reason="invalid_method_body_data"):
        self.reason=reason
        super().__init__("Method body data could not be validated.")


def _fail(reason):
    try:raise MethodBodyValidationError(reason) from None
    except MethodBodyValidationError as safe:
        safe.__context__=None;safe.__cause__=None;safe.__suppress_context__=False
        raise


class _Limit(Exception):pass


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")


def _json_data(payload,cap=MAX_BODY_BYTES):
    if type(payload) is bytes:
        if len(payload)>cap:raise _Limit()
        payload=payload.decode("utf-8")
    if type(payload) is str:
        if len(payload)>cap or len(payload.encode())>cap:raise _Limit()
        def pairs(items):
            value={}
            for key,child in items:
                if key in value:raise ValueError("duplicate JSON key")
                value[key]=child
            return value
        def reject(_):raise ValueError("strict JSON values required")
        payload=json.loads(payload,object_pairs_hook=pairs,parse_float=reject,parse_constant=reject,
            parse_int=lambda text:int(text) if len(text.lstrip("-"))<=12 else reject(text))
    if type(payload) is not dict:raise ValueError("plain body object required")
    stack=[(payload,0)];nodes=size=0
    while stack:
        value,depth=stack.pop();nodes+=1
        if depth>24 or nodes>12000:raise _Limit()
        if type(value) is dict:
            for key,child in value.items():
                if type(key) is not str:raise ValueError("string key required")
                stack.extend(((key,depth+1),(child,depth+1)))
        elif type(value) is list:stack.extend((child,depth+1) for child in value)
        elif type(value) is str:
            size+=len(value.encode())
            if size>cap:raise _Limit()
        elif type(value) is int:
            if value.bit_length()>63:raise ValueError("integer bound")
        elif value is not None and type(value) is not bool:raise ValueError("JSON values only")
    raw=_canonical(payload)
    if len(raw)>cap:raise _Limit()
    return json.loads(raw)


def _utc(value):
    datetime.strptime(value,"%Y-%m-%dT%H:%M:%S.%fZ")
    return value


def _text(value):
    if not value.strip() or any(unicodedata.category(c) in {"Cc","Cf","Cs"} for c in value):raise ValueError("bounded producer name required")
    return value


UTCText=Annotated[str,StringConstraints(strict=True,pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"),AfterValidator(_utc)]
ProducerText=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=64),AfterValidator(_text)]


class _DataDTO(BaseModel):
    model_config=ConfigDict(strict=True,extra="forbid",frozen=True,revalidate_instances="always",protected_namespaces=())


class MethodBodyBinding(_DataDTO):
    result_ref:PaidId
    research_id:PaidId
    task_id:PaidId
    step_id:PaidId
    input_revision:Revision
    input_digest:PaidDigest
    approval_ref:PaidId
    dispatch_id:PaidId
    permit_id:PaidId
    approval_consumed_version:Revision
    permit_state:Literal["consumed"]
    session_consumed_version:Revision
    authorized_task_version:Revision
    authorized_step_version:Revision
    request_digest:PaidDigest
    evidence_digest:PaidDigest
    financial_return_ref:PaidId
    financial_return_digest:PaidDigest
    candidate_schema:Literal["ModelReportCandidate-v1"]
    body_schema:Literal["OwnedMethodBody-v1"]
    producer_revision:ProducerText
    execution_mode:Literal["offline_probe"]
    received_at:UTCText

    @model_validator(mode="after")
    def same_existing_session_reference(self):
        if self.result_ref!=self.financial_return_ref:raise ValueError("body and return must reference the same existing session")
        return self


class ExpectedMethodBodyBinding(MethodBodyBinding):
    """Content expectations only; not evidence of their authoritative origin."""


class OwnedMethodBodyData(_DataDTO):
    header:MethodBodyBinding
    candidate:ModelReportCandidate=Field(repr=False)
    candidate_digest:PaidDigest
    envelope_digest:PaidDigest


def validate_expected_digest(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}",value) is None:_fail("method_body_expected_digest_required")
    return value


def validate_body_binding(payload):
    reason=None
    try:
        if type(payload) in {MethodBodyBinding,ExpectedMethodBodyBinding}:
            model=MethodBodyBinding.model_validate(payload)
            data=_json_data(model.model_dump(mode="json"))
        else:data=_json_data(payload)
        result=MethodBodyBinding.model_validate(data)
    except _Limit:reason="method_body_limit"
    except (ValidationError,ValueError,TypeError,OverflowError,RecursionError,UnicodeError):reason="invalid_method_body_binding"
    if reason:_fail(reason)
    return result


def validate_candidate_data(payload):
    """Reuse the original candidate and intrinsic gap/duplicate-handle checks.

    Packet handle membership/current permissions remain Core parse_candidate's
    responsibility. Shared public text filtering is not scientific verification.
    """
    reason=None
    try:
        if type(payload) is ModelReportCandidate:
            model=ModelReportCandidate.model_validate(payload)  # Before dump/warnings.
            data=_json_data(model.model_dump(mode="json"))
        else:data=_json_data(payload)
        # Original strict tuples are parsed via its original JSON entry semantics.
        result=ModelReportCandidate.model_validate_json(_canonical(data))
        if not result.mechanisms and not result.gaps:raise ValueError("missing gaps")
        for mechanism in result.mechanisms:
            if len(set(mechanism.evidence_handles))!=len(mechanism.evidence_handles):raise ValueError("duplicate handle")
        validated=result.model_dump(mode="json")
        texts=[];stack=[validated]
        while stack:
            value=stack.pop()
            if type(value) is dict:stack.extend(value.values())
            elif type(value) is list:stack.extend(value)
            elif type(value) is str:texts.append(value)
        validate_candidate_public_texts(texts)
        _json_data(validated)
    except _Limit:reason="method_body_limit"
    except (ValidationError,ValueError,TypeError,OverflowError,RecursionError,UnicodeError):reason="invalid_method_body_candidate"
    if reason:_fail(reason)
    return result
