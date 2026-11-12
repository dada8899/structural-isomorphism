"""Public paid DTOs and schema declarations; no auth, authority, codec or I/O.

Core must keep its manual request reader and independently verified permissions.
These types neither authorize payment nor prove that a model has run.
"""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from typing import Annotated, Literal
import unicodedata
from urllib.parse import urlsplit

from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, StrictBool,
                      StrictInt, StringConstraints, ValidationError, model_validator)

from .schemas import (PaidPreviewEnvelope, PaidConfirmationEnvelope, PaidId,
                      PaidDigest, Revision)

MAX_RESPONSE_BYTES = 512 * 1024
_MAX_DEPTH, _MAX_NODES = 32, 20000
Operation = Literal["paid-preview", "paid-confirm"]


def _exact(value):
    if any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\n\t" for c in value):
        raise ValueError("invalid exact text")
    return value


def _utc(value):
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    return value


def _date(value):
    date.fromisoformat(value)
    return value


def _false(value):
    if value is not False:
        raise ValueError("false required")
    return value


def _url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or any(c.isspace() for c in value)):
        raise ValueError("public source URL required")
    return value


Exact300 = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=300), AfterValidator(_exact)]
Exact400 = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=400), AfterValidator(_exact)]
Exact1000 = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000), AfterValidator(_exact)]
UTCText = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"), AfterValidator(_utc), Field(json_schema_extra={"format":"date-time"})]
DateText = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"), AfterValidator(_date), Field(json_schema_extra={"format":"date"})]
FalseFlag = Annotated[StrictBool, AfterValidator(_false), Field(json_schema_extra={"const":False})]
One = Annotated[StrictInt, Field(ge=1, le=1)]
Six = Annotated[StrictInt, Field(ge=6, le=6)]
Offset = Annotated[StrictInt, Field(ge=0, le=200000)]
NativeUnits = Annotated[StrictInt, Field(ge=0, le=2**63-1)]
Handle = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_-]{1,32}$")]
PublicURL = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2000), AfterValidator(_url)]
ExecutionState = Literal["QUEUED", "RUNNING", "WAITING_EXTERNAL", "CANCEL_REQUESTED", "RECONCILING", "COMPLETED", "FAILED", "CANCELLED", "ACCESS_REVOKED"]
ProductState = Literal["queued", "retrieving", "analysing", "synthesising", "completed", "insufficient", "failed", "cancelled"]
Action = Literal["view", "cancel", "refresh", "request_reconciliation", "revise", "export", "record_followup", "retry", "start", "resume", "sign_in", "return_to_library"]


class PublicDTO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True,
                              revalidate_instances="always", protected_namespaces=())


class PaidPreviewBinding(PublicDTO):
    research_id: PaidId
    input_revision: Revision
    input_digest: PaidDigest
    research_version: Revision


class PaidPreviewQuote(PublicDTO):
    revision: PaidId
    digest: PaidDigest
    valid_until: UTCText


class PaidMaximumReserve(PublicDTO):
    currency: Literal["CNY"]
    scale: Six
    amount_units: NativeUnits


class _PublicSpan(PublicDTO):
    source_id: PaidId
    source_revision: Revision
    excerpt_id: PaidId
    title: Exact300
    attribution: Exact400
    extracted_digest: PaidDigest
    start: Offset
    end: Offset
    quote: Exact1000

    @model_validator(mode="after")
    def exact_short_span(self):
        if not self.start < self.end or self.end-self.start != len(self.quote) or len(self.quote.split()) > 20:
            raise ValueError("invalid short Unicode span")
        return self


class PaidPreviewSource(_PublicSpan):
    canonical_url: PublicURL
    raw_digest: PaidDigest
    discovery_digest: PaidDigest
    permission_basis_digest: PaidDigest
    read_scope: Literal["author_narrative_subset"]
    acquired_at: UTCText
    information_cutoff: DateText
    may_send_to_provider: FalseFlag


class PaidOutboundHandle(_PublicSpan):
    handle: Handle


class PaidPreviewManifest(PublicDTO):
    problem_summary: Exact1000
    sources: Annotated[list[PaidPreviewSource], Field(min_length=1, max_length=20)]
    handles: Annotated[list[PaidOutboundHandle], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def exact_correspondence(self):
        if len(self.sources) != len(self.handles):
            raise ValueError("manifest lengths differ")
        if len({s.excerpt_id for s in self.sources}) != len(self.sources) or len({h.handle for h in self.handles}) != len(self.handles):
            raise ValueError("duplicate manifest reference")
        keys = tuple(_PublicSpan.model_fields)
        for source, handle in zip(self.sources, self.handles):
            if any(getattr(source,k) != getattr(handle,k) for k in keys):
                raise ValueError("manifest and outbound handle differ")
        return self


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PaidPreviewView(PublicDTO):
    preview_ref: PaidId
    preview_version: Revision
    status: Literal["draft"]
    expires_at: UTCText
    bindings: PaidPreviewBinding
    purpose: Literal["method_hypothesis"]
    provider: Literal["deepseek"]
    model: Literal["deepseek-flash"]
    declared_model_version: Literal["DeepSeek-V4.1-Flash"]
    execution_mode: Literal["offline_probe"]
    policy_revision: Literal["bounded_usage_upper_v2"]
    quote: PaidPreviewQuote
    maximum_reserve: PaidMaximumReserve
    actual: None
    cost_label: Literal["maximum_reserve_not_actual"]
    max_calls: One
    manifest: PaidPreviewManifest
    manifest_digest: PaidDigest
    outbound_request_digest: PaidDigest
    preview_digest: PaidDigest
    may_send_to_provider: FalseFlag
    model_analysis_ran: FalseFlag

    @model_validator(mode="after")
    def public_binding_digests(self):
        if self.expires_at > self.quote.valid_until:
            raise ValueError("preview exceeds quote validity")
        if self.manifest_digest != _digest(self.manifest.model_dump(mode="json")):
            raise ValueError("manifest digest mismatch")
        if self.preview_digest != _digest(self.model_dump(mode="json", exclude={"preview_digest"})):
            raise ValueError("preview digest mismatch")
        return self


class PaidApprovalView(PublicDTO):
    approval_ref: PaidId
    preview_ref: PaidId
    preview_version: Revision
    preview_digest: PaidDigest
    research_version: Revision
    task_id: PaidId
    task_version: Revision
    execution: ExecutionState
    status: ProductState
    execution_mode: Literal["offline_probe"]
    model_analysis_ran: FalseFlag


class PaidPreviewSuccessEnvelope(PublicDTO):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: PaidPreviewView


class PaidConfirmationSuccessEnvelope(PublicDTO):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: PaidApprovalView


class ResearchPublicError(PublicDTO):
    code: Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
    message: Exact1000
    retryable: StrictBool
    allowed_next_actions: Annotated[list[Action], Field(max_length=12)]
    incident_id: PaidId

    @model_validator(mode="after")
    def unique_actions(self):
        if len(set(self.allowed_next_actions)) != len(self.allowed_next_actions):
            raise ValueError("duplicate public action")
        return self


class ResearchPublicErrorEnvelope(PublicDTO):
    error: ResearchPublicError


class PaidPublicValidationError(ValueError):
    """Internal fixed failure only. Core maps this to its existing safe errors."""
    def __init__(self, reason="invalid_public_payload"):
        self.reason = reason
        super().__init__("Paid public response could not be validated.")


def _raise_safe(reason):
    """Clear real exception slots even when called from an active outer except."""
    try:
        raise PaidPublicValidationError(reason) from None
    except PaidPublicValidationError as safe:
        safe.__context__ = None
        safe.__cause__ = None
        safe.__suppress_context__ = False
        # Bare re-raise preserves the cleared slots; a new raise would chain again.
        raise


class _Limit(Exception):
    pass


def _json_copy(payload):
    if type(payload) is not dict:
        raise ValueError("public envelope must be a plain object")
    count = string_bytes = 0
    stack = [(payload,0)]
    while stack:
        value, depth = stack.pop(); count += 1
        if depth > _MAX_DEPTH or count > _MAX_NODES:
            raise _Limit()
        if type(value) is dict:
            for key, child in value.items():
                if type(key) is not str: raise ValueError("string key required")
                stack.extend(((key,depth+1),(child,depth+1)))
        elif type(value) is list:
            stack.extend((child,depth+1) for child in value)
        elif type(value) is str:
            string_bytes += len(value.encode("utf-8"))
            if string_bytes > MAX_RESPONSE_BYTES: raise _Limit()
        elif type(value) is int:
            if value.bit_length()>64: raise ValueError("oversized JSON integer")
        elif value is not None and type(value) is not bool:
            raise ValueError("non-JSON public value")
    raw = json.dumps(payload, ensure_ascii=False, separators=(",",":"), allow_nan=False)
    if len(raw.encode("utf-8"))>MAX_RESPONSE_BYTES: raise _Limit()
    return json.loads(raw)


_REQUESTS = {"paid-preview":PaidPreviewEnvelope, "paid-confirm":PaidConfirmationEnvelope}
_SUCCESSES = {"paid-preview":PaidPreviewSuccessEnvelope, "paid-confirm":PaidConfirmationSuccessEnvelope}


def success_response_model(operation: Operation):
    if type(operation) is not str or operation not in _SUCCESSES:
        _raise_safe("unsupported_public_operation")
    return _SUCCESSES[operation]


def _validate(payload, model):
    reason = None
    try:
        data = _json_copy(payload)
        result = model.model_validate(data).model_dump(mode="json")
        result = _json_copy(result)
    except _Limit:
        reason = "public_payload_limit"
    except (ValidationError, ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
        reason = "invalid_public_payload"
    # Discard internal parse errors; the shared exit also clears caller context.
    if reason is not None:
        _raise_safe(reason)
    return result


def validate_success_response(operation: Operation, payload):
    """No filtering/drop-extra, auth proof, side effects or HTTP parsing."""
    return _validate(payload, success_response_model(operation))


def validate_error_response(payload):
    """Validate an already controlled ResearchError body, not arbitrary error text."""
    return _validate(payload, ResearchPublicErrorEnvelope)


def request_body_schema(operation: Operation):
    """OpenAPI declaration only; Core must retain manual stream/identity ordering.

    JSON Schema cannot express every Python strict-number rule or prove consent,
    provenance or current authorization. No request is parsed by this helper.
    """
    if type(operation) is not str or operation not in _REQUESTS:
        _raise_safe("unsupported_public_operation")
    schema = _REQUESTS[operation].model_json_schema()
    definitions = schema.get("$defs", {})
    def expand(value, active=()):
        if type(value) is list: return [expand(v,active) for v in value]
        if type(value) is not dict: return value
        if "$ref" in value:
            ref = value["$ref"]
            if type(ref) is not str or not ref.startswith("#/$defs/"):
                _raise_safe("unsupported_schema_reference")
            name = ref[len("#/$defs/"):].replace("~1","/").replace("~0","~")
            if name not in definitions or name in active:
                _raise_safe("unsupported_schema_reference")
            target = expand(definitions[name],active+(name,))
            siblings = {k:v for k,v in value.items() if k not in {"$ref","$defs"}}
            return {"allOf":[target,expand(siblings,active)]} if siblings else target
        return {k:expand(v,active) for k,v in value.items() if k!="$defs"}
    result = expand(schema)
    fields = result["properties"]["data"]["properties"]
    if operation=="paid-preview": fields["excerpt_ids"]["uniqueItems"] = True
    else:
        for name in ("confirm_external_input","confirm_maximum_reserve"):
            fields[name]["const"] = True
    return {"required":True,"content":{"application/json":{"schema":deepcopy(result)}}}
