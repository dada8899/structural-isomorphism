"""Bounded, unverified starting-plan data. No KB, search, ownership or auth proof.

Callers must separately load the current saved self-observation, check known
third-party provenance, obtain consent and apply the shared financial controls.
Lexical checks cannot identify every semantic falsehood or establish copyright.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal
import unicodedata

from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, StrictBool,
                      StrictInt, StringConstraints, ValidationError, model_validator)
from .schemas import SourcePreviewRequest

if __package__ == "web.backend.research":
    from ..services.search_synthesis import validate_candidate_public_texts
else:
    from services.search_synthesis import validate_candidate_public_texts

PURPOSE = "phenomenon_plan_v1"
INPUT_TEMPLATE = "SelfObservationPlanInput-v1"
CANDIDATE_SCHEMA = "PhenomenonPlanCandidate-v1"
CONTRACT_REVISION = "phenomenon-plan-candidate-01"
MAX_PLAN_BYTES = 16 * 1024


class PlanValidationError(ValueError):
    """Fixed safe internal failure; never a raw model/Pydantic exception."""
    def __init__(self, reason="invalid_plan_data"):
        self.reason = reason
        super().__init__("Starting-plan data could not be validated.")


def _fail(reason):
    try:
        raise PlanValidationError(reason) from None
    except PlanValidationError as safe:
        safe.__context__ = None
        safe.__cause__ = None
        safe.__suppress_context__ = False
        raise


class _Limit(Exception):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _data_digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _copy_json(value, cap=MAX_PLAN_BYTES):
    """Bound before serialization/parsing. No float, coercion or arbitrary objects."""
    if type(value) is bytes:
        if len(value)>cap: raise _Limit()
        value=value.decode("utf-8")
    if type(value) is str:
        if len(value)>cap or len(value.encode("utf-8"))>cap: raise _Limit()
        def pairs(items):
            result={}
            for key, child in items:
                if key in result: raise ValueError("duplicate JSON key")
                result[key]=child
            return result
        def reject(_): raise ValueError("invalid JSON number")
        value=json.loads(value,object_pairs_hook=pairs,parse_float=reject,parse_constant=reject,
                         parse_int=lambda s:int(s) if len(s.lstrip("-"))<=12 else reject(s))
    if type(value) is not dict: raise ValueError("plan object required")
    stack=[(value,0)];count=size=0
    while stack:
        child,depth=stack.pop();count+=1
        if count>4096 or depth>24: raise _Limit()
        if type(child) is dict:
            for key,item in child.items():
                if type(key) is not str: raise ValueError("string key required")
                stack.extend(((key,depth+1),(item,depth+1)))
        elif type(child) is list: stack.extend((item,depth+1) for item in child)
        elif type(child) is str:
            size+=len(child.encode("utf-8"))
            if size>cap:raise _Limit()
        elif type(child) is int:
            if child.bit_length()>63:raise ValueError("integer limit")
        elif child is not None and type(child) is not bool:raise ValueError("JSON data required")
    raw=_canonical(value)
    if len(raw)>cap:raise _Limit()
    return json.loads(raw)


# High-confidence structures only. Ordinary text is still data, never commands.
_STRUCTURES = re.compile(
    r"(?:\b[a-z][a-z0-9+.-]{1,24}://|\b(?:https?|file|data|javascript|mailto):|\bwww\.|\bdoi\s*:|\b10\.\d{4,9}/\S+)"
    r"|(?:`|\$\(|\$\{|#!\s*/|<\s*/?\s*(?:script|iframe|object|embed)\b)"
    r"|(?:\b(?:curl|wget|rm|chmod|chown|ssh|scp)\s+-[A-Za-z]|\b(?:bash|sh|zsh|pwsh|powershell)\s+-[A-Za-z])"
    r"|(?:\b(?:python3?|node)\s+-(?:c|e)\b|\b(?:pip3?|npm|npx)\s+(?:install|exec|run)\b)"
    r"|(?:\b(?:eval|exec|__import__)\s*\(|\b(?:Invoke-WebRequest|Invoke-Expression|Start-Process)\b)"
    r"|(?:\bSELECT\s+\*\s+FROM\b|\b(?:DROP|ALTER|CREATE)\s+TABLE\b|\bINSERT\s+INTO\b|\bDELETE\s+FROM\b)"
    r"|(?:\[[0-9]+\]|\bet\s+al\.)"
    r"|(?:[\"']?(?:verified|checked|trusted|copyright_verified|mathematically_verified)[\"']?\s*[:=]\s*(?:true|1|yes)\b)",
    re.I,
)


def _obvious_structures(texts):
    views=[unicodedata.normalize("NFKC",v) for v in texts]
    for view in views+["".join(views),"\n".join(views)]:
        if _STRUCTURES.search(view): raise ValueError("unsupported executable or source structure")


def _text(value):
    if not value.strip() or any(unicodedata.category(c) in {"Cc","Cf","Cs"} and c not in "\n\t" for c in value):
        raise ValueError("visible bounded text required")
    return value  # Preserve exact original input; never silently strip/truncate.


def _false(value):
    if value is not False:raise ValueError("false required")
    return value


Text120=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=120),AfterValidator(_text)]
Text160=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=160),AfterValidator(_text)]
Text240=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=240),AfterValidator(_text)]
Text400=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=400),AfterValidator(_text)]
Text700=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=700),AfterValidator(_text)]
Summary=Annotated[str,StringConstraints(strict=True,min_length=8,max_length=1000),AfterValidator(_text)]
FalseFlag=Annotated[StrictBool,AfterValidator(_false),Field(json_schema_extra={"const":False})]

# Reuse the frozen Source input field metadata, not a wider query grammar.
_QUERY_METADATA=tuple(SourcePreviewRequest.model_fields["query"].metadata)
_QUERY_PATTERN=next(item.pattern for item in _QUERY_METADATA if isinstance(item,StringConstraints))


def _english_query(value):
    if re.fullmatch(_QUERY_PATTERN,value) is None:raise ValueError("fixed Source query grammar required")
    _obvious_structures([value])
    return value


EnglishQuery=Annotated[str,*_QUERY_METADATA,AfterValidator(_english_query)]


class PlanDTO(BaseModel):
    model_config=ConfigDict(strict=True,extra="forbid",frozen=True,revalidate_instances="always",protected_namespaces=())


class SelfObservationPlanInput(PlanDTO):
    input_kind:Literal["user_observation_summary"]
    summary:Summary=Field(repr=False)

    @model_validator(mode="after")
    def no_obvious_external_payload(self):
        _obvious_structures([self.summary])
        return self


class PlanNomination(PlanDTO):
    label:Text120
    mechanism_hypothesis:Text700=Field(repr=False)
    why_considered:Text400=Field(repr=False)
    method_leads:Annotated[list[Text160],Field(max_length=2)]
    key_unknowns:Annotated[list[Text240],Field(min_length=1,max_length=5)]


class PlanQuerySuggestion(PlanDTO):
    candidate_index:Annotated[StrictInt,Field(ge=0,le=2)]|None
    query:EnglishQuery
    intent:Text240


class PhenomenonPlanCandidate(PlanDTO):
    summary:Text700=Field(repr=False)
    candidates:Annotated[list[PlanNomination],Field(max_length=3)]
    query_suggestions:Annotated[list[PlanQuerySuggestion],Field(max_length=5)]
    gaps:Annotated[list[Text400],Field(min_length=1,max_length=8)]
    clarification_questions:Annotated[list[Text240],Field(max_length=3)]

    @model_validator(mode="after")
    def references_and_public_text(self):
        if not self.candidates and not self.query_suggestions and not self.clarification_questions:
            raise ValueError("empty proposal needs clarification")
        queries=[];texts=[self.summary]
        for candidate in self.candidates:
            texts.extend([candidate.label,candidate.mechanism_hypothesis,candidate.why_considered,*candidate.method_leads,*candidate.key_unknowns])
        for query in self.query_suggestions:
            if query.candidate_index is not None and query.candidate_index>=len(self.candidates):
                raise ValueError("candidate index outside proposal")
            queries.append(" ".join(query.query.casefold().split()))
            texts.extend([query.query,query.intent])
        if len(queries)!=len(set(queries)):raise ValueError("duplicate query suggestion")
        texts.extend([*self.gaps,*self.clarification_questions])
        _obvious_structures(texts)
        validate_candidate_public_texts(texts)
        if len(_canonical(self.model_dump(mode="json")))>MAX_PLAN_BYTES:raise ValueError("candidate byte limit")
        return self


class PlanPreviewManifest(PlanDTO):
    schema_version:Literal["structure-research-v1"]
    contract_revision:Literal["phenomenon-plan-candidate-01"]
    purpose:Literal["phenomenon_plan_v1"]
    input_template:Literal["SelfObservationPlanInput-v1"]
    candidate_schema:Literal["PhenomenonPlanCandidate-v1"]
    observation_source:Literal["own_observation"]
    declaration_status:Literal["self_declared"]
    input:SelfObservationPlanInput=Field(repr=False)
    may_send_to_provider:FalseFlag
    model_analysis_ran:FalseFlag


class UnverifiedPhenomenonPlanView(PlanDTO):
    purpose:Literal["phenomenon_plan_v1"]
    candidate_schema:Literal["PhenomenonPlanCandidate-v1"]
    proposal:PhenomenonPlanCandidate=Field(repr=False)
    literature_status:Literal["not_retrieved"]
    mathematics_status:Literal["not_checked"]
    mechanism_status:Literal["unverified"]
    evidence_status:Literal["INSUFFICIENT"]
    execution_mode:Literal["offline_probe"]
    model_analysis_ran:FalseFlag


def _parse(model,payload):
    reason=None
    try:
        if type(payload) is model:
            result=model.model_validate(payload)  # Revalidate construct/mutated instances before dump.
        else:
            data=_copy_json(payload)
            result=model.model_validate(data)
        _copy_json(result.model_dump(mode="json"))
    except _Limit:reason="plan_payload_limit"
    except (ValidationError,ValueError,TypeError,OverflowError,RecursionError,UnicodeError):reason="invalid_plan_data"
    if reason is not None:_fail(reason)
    return result


def validate_self_observation(payload):
    """Shape/obvious-structure checks only; not ownership or saved-revision proof."""
    return _parse(SelfObservationPlanInput,payload)


def parse_plan_candidate(payload):
    """Strict all-or-nothing model data, never a source, result or auth receipt."""
    return _parse(PhenomenonPlanCandidate,payload)


def make_plan_manifest(input_data):
    observed=validate_self_observation(input_data)
    return PlanPreviewManifest(schema_version="structure-research-v1",contract_revision=CONTRACT_REVISION,
        purpose=PURPOSE,input_template=INPUT_TEMPLATE,candidate_schema=CANDIDATE_SCHEMA,
        observation_source="own_observation",declaration_status="self_declared",input=observed,
        may_send_to_provider=False,model_analysis_ran=False)


def validate_plan_manifest(payload):
    return _parse(PlanPreviewManifest,payload)


def unverified_plan_view(payload):
    candidate=parse_plan_candidate(payload)
    return UnverifiedPhenomenonPlanView(purpose=PURPOSE,candidate_schema=CANDIDATE_SCHEMA,proposal=candidate,
        literature_status="not_retrieved",mathematics_status="not_checked",mechanism_status="unverified",
        evidence_status="INSUFFICIENT",execution_mode="offline_probe",model_analysis_ran=False)
