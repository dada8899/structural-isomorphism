"""Finite formula content DTOs, not tasks, source facts or execution permission.

Drafts contain no server IDs/source records. Private reported-result models only
validate supplied content for the adapter; their presence never attests a worker.
"""
from dataclasses import dataclass,asdict
from decimal import Decimal
import json
import re
from typing import Annotated,Literal

from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,StringConstraints,AfterValidator
from . import formula_schemas as scientific
from .formula_policy import TEMPLATES,UNITS

INPUT_CAP=64*1024
RESULT_CAP=512*1024
SCOPES=("expression","equation_form","initial_value_problem")
CHECKS=("template","dimensions","canonical_transform","bounded_numeric")


class FormulaPublicError(ValueError):
    def __init__(self,reason="invalid_formula_content"):
        self.reason=reason
        super().__init__("Formula content could not be validated.")


def _fail(reason):
    try:raise FormulaPublicError(reason) from None
    except FormulaPublicError as safe:
        safe.__context__=None;safe.__cause__=None;safe.__suppress_context__=False
        raise


class _Limit(Exception):pass


def _json_data(payload,cap):
    if type(payload) is bytes:
        if len(payload)>cap:raise _Limit()
        payload=payload.decode("utf-8")
    if type(payload) is str:
        if len(payload)>cap or len(payload.encode())>cap:raise _Limit()
        def pairs(items):
            result={}
            for key,value in items:
                if key in result:raise ValueError("duplicate key")
                result[key]=value
            return result
        def reject(_):raise ValueError("strict JSON number required")
        payload=json.loads(payload,object_pairs_hook=pairs,parse_float=reject,parse_constant=reject,
            parse_int=lambda v:int(v) if len(v.lstrip("-"))<=20 else reject(v))
    if type(payload) is not dict:raise ValueError("object required")
    count=size=0;stack=[(payload,0)]
    while stack:
        value,depth=stack.pop();count+=1
        if count>20000 or depth>24:raise _Limit()
        if type(value) is dict:
            for key,child in value.items():
                if type(key) is not str:raise ValueError("string key required")
                stack.extend(((key,depth+1),(child,depth+1)))
        elif type(value) is list:stack.extend((child,depth+1) for child in value)
        elif type(value) is str:
            size+=len(value.encode())
            if size>cap:raise _Limit()
        elif type(value) is int:
            if value.bit_length()>64:raise ValueError("integer limit")
        elif value is not None and type(value) is not bool:raise ValueError("plain JSON required")
    raw=scientific.canonical(payload)
    if len(raw.encode())>cap:raise _Limit()
    return json.loads(raw)


@dataclass(frozen=True,slots=True,init=False)
class FormulaDraft:
    _json:str
    def __init__(self,*args,**kwargs):_fail("use_formula_draft_parser")
    def data(self):return json.loads(self._json)
    @property
    def content_digest(self):return scientific.digest(self.data())


@dataclass(frozen=True,slots=True,init=False)
class FormulaComparisonDraft:
    _json:str
    def __init__(self,*args,**kwargs):_fail("use_formula_comparison_parser")
    def data(self):return json.loads(self._json)
    @property
    def content_digest(self):return scientific.digest(self.data())


def _draft_value(cls,data):
    value=object.__new__(cls);object.__setattr__(value,"_json",scientific.canonical(data));return value


def _side(data):
    scientific.fields(data,("family","template_id","original_display","expression","symbols","assumptions","initial_conditions","boundary_conditions","measure_scope"))
    family=scientific.bounded(data["family"],40);template=scientific.bounded(data["template_id"],40)
    if template not in TEMPLATES or TEMPLATES[template]!=family:_fail("formula_not_supported")
    symbols=tuple(scientific.Symbol.parse(v) for v in scientific.sequence(data["symbols"],12))
    if len({v.id for v in symbols})!=len(symbols) or len({v.role for v in symbols})!=len(symbols):raise ValueError("bijection required")
    if any(v.unit_id not in UNITS for v in symbols):_fail("formula_not_supported")
    assumptions=tuple(scientific.Condition.parse(v) for v in scientific.sequence(data["assumptions"],24))
    boundaries=tuple(scientific.Condition.parse(v) for v in scientific.sequence(data["boundary_conditions"],24))
    initials=tuple(scientific.InitialValue.parse(v) for v in scientific.sequence(data["initial_conditions"],1))
    if len(assumptions)+len(boundaries)+len(initials)>24:raise _Limit()
    if len({v.id for v in assumptions+boundaries})!=len(assumptions+boundaries):raise ValueError("duplicate condition")
    node=scientific.Node.parse(data["expression"])
    return {"family":family,"template_id":template,"original_display":scientific.bounded(data["original_display"],2048),
        "expression":node.data(),"symbols":[asdict(v) for v in symbols],"assumptions":[asdict(v) for v in assumptions],
        "initial_conditions":[asdict(v) for v in initials],"boundary_conditions":[asdict(v) for v in boundaries],
        "measure_scope":scientific.bounded(data["measure_scope"],20)}


def parse_formula_draft(payload):
    reason=None
    try:
        data=_side(_json_data(payload,INPUT_CAP));value=_draft_value(FormulaDraft,data)
    except FormulaPublicError:raise
    except (_Limit,scientific.FormulaLimit):reason="formula_payload_limit"
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError,UnicodeError):reason="invalid_formula_content"
    if reason:_fail(reason)
    return value


def parse_comparison_draft(payload):
    reason=None
    try:
        data=_json_data(payload,INPUT_CAP)
        scientific.fields(data,("comparison_scope","left","right","requested_checks","sample_points"))
        if type(data["comparison_scope"]) is not str or data["comparison_scope"] not in SCOPES:raise ValueError("explicit scope required")
        checks=scientific.sequence(data["requested_checks"],4)
        if not checks or any(type(v) is not str or v not in CHECKS for v in checks) or len(checks)!=len(set(checks)):raise ValueError("fixed checks required")
        if data["right"] is None and set(checks)-{"template","dimensions"}:raise ValueError("comparison requires both sides")
        points=[scientific.decimal_text(v) for v in scientific.sequence(data["sample_points"],256)]
        if len(points)!=len(set(points)):raise ValueError("duplicate point")
        result={"comparison_scope":data["comparison_scope"],"left":_side(data["left"]),
            "right":None if data["right"] is None else _side(data["right"]),"requested_checks":list(checks),"sample_points":points}
        _json_data(result,INPUT_CAP);value=_draft_value(FormulaComparisonDraft,result)
    except FormulaPublicError:raise
    except (_Limit,scientific.FormulaLimit):reason="formula_payload_limit"
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError,UnicodeError):reason="invalid_formula_content"
    if reason:_fail(reason)
    return value


class _DTO(BaseModel):
    model_config=ConfigDict(strict=True,extra="forbid",frozen=True,revalidate_instances="always",protected_namespaces=())


def _text(value):return scientific.bounded(value,400)
def _uuid(value):return scientific.uuid(value)
def _decimal(value):scientific.decimal_text(value);return value

def _rational(value):
    if re.fullmatch(r"-?(?:0|[1-9][0-9]{0,77})(?:/[1-9][0-9]{0,77})?",value) is None:raise ValueError("bounded rational text required")
    return value


def _numeric(value):
    if len(value)>128 or re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?",value) is None:raise ValueError("bounded numeric text required")
    number=Decimal(value)
    if not number.is_finite() or number.copy_abs()>Decimal("1e12"):raise ValueError("finite derived value required")
    return value


Text=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=400),AfterValidator(_text)]
UUIDText=Annotated[str,StringConstraints(strict=True),AfterValidator(_uuid)]
Digest=Annotated[str,StringConstraints(strict=True,pattern=r"^[0-9a-f]{64}$")]
Revision=Annotated[StrictInt,Field(ge=1,le=2147483647)]
DecimalText=Annotated[str,StringConstraints(strict=True),AfterValidator(_decimal)]
RationalText=Annotated[str,StringConstraints(strict=True,max_length=160),AfterValidator(_rational)]
NumericText=Annotated[str,StringConstraints(strict=True,max_length=128),AfterValidator(_numeric)]
Scope=Literal["expression","equation_form","initial_value_problem"]
CheckKind=Literal["template","dimensions","canonical_transform","bounded_numeric"]
Status=Literal["passed","failed","inconclusive","unsupported","resource_limit"]
Relation=Literal["algebraic_identity","conditional_model_equivalence","local_approximation","partial_structure","not_equivalent","undetermined"]


class _Trace(_DTO):
    kind:Literal["constant_fold","commute","associate","rename_bijection","substitute_constant","multiply_nonzero","divide_nonzero","positive_time_scale","state_normalize"]
    input_digest:Digest
    output_digest:Digest
    precondition_ids:Annotated[list[Annotated[str,StringConstraints(strict=True,pattern=r"^[a-z][a-z0-9_]{0,31}$")]],Field(max_length=24)]


class _Exact(_DTO):
    value:RationalText
    given_output:RationalText|None
    arithmetic:Literal["exact_rational"]


class _Timescale(_DTO):
    value:RationalText
    unit_id:Literal["s"]
    meaning:Literal["time_constant_only_not_an_ivp"]
    arithmetic:Literal["exact_rational"]


class _Exp(_DTO):
    value:NumericText
    physical_time:RationalText
    tau:RationalText
    actual_state:NumericText|None
    arithmetic:Literal["bounded_exp"]
    meaning:Literal["zero_solution_no_state_normalization","normalized_initial_state","unit_response_kernel_only"]


class _Sample(_DTO):
    point:DecimalText
    left:_Exact|_Timescale|_Exp
    right:_Exact|_Timescale|_Exp
    passed:StrictBool
    comparison:Literal["exact","abs1e-10_rel1e-8_normalized_only"]


class _Tolerance(_DTO):
    absolute:Literal["1e-10"]
    relative:Literal["1e-8"]
    policy_revision:Literal["formula-policy-v1-d2-candidate"]
    scope:Literal["normalized_same_scale_samples_only"]


class _Outcome(_DTO):
    check_kind:CheckKind
    status:Status
    relation:Relation
    reason:Text
    trace:Annotated[list[_Trace],Field(max_length=64)]
    samples:Annotated[list[_Sample],Field(max_length=256)]
    tolerance:_Tolerance|None


class _FormulaRef(_DTO):
    id:UUIDText
    revision:Revision
    formula_digest:Digest
    checked_representation:Literal["validated_AST"]


class _ReportedSource(_DTO):
    id:UUIDText
    revision:Revision
    content_digest:Digest
    provenance:Literal["curated_reference","product_excerpt"]
    locator:Annotated[str,StringConstraints(strict=True,min_length=1,max_length=300),AfterValidator(lambda v:scientific.bounded(v,300))]


class _ReportedResult(_DTO):
    input_digest:Digest
    research_id:UUIDText
    input_revision:Revision
    task_id:UUIDText
    attempt:Revision
    comparison_scope:Scope
    policy_revision:Literal["formula-policy-v1-d2-candidate"]
    formula_refs:Annotated[list[_FormulaRef],Field(min_length=1,max_length=2)]
    outcomes:Annotated[list[_Outcome],Field(min_length=1,max_length=4)]
    source_refs:Annotated[list[_ReportedSource],Field(max_length=40)]
    limitations:Annotated[list[Text],Field(min_length=1,max_length=24)]
    resource_guard:Literal["pure_core_not_a_sandbox","not_executed","isolated_execution_not_completed","linux_as_baseline_plus_128mib_cpu1s_wall2s"]
    output_digest:Digest


def formula_draft_view(payload):
    """Content presentation only: no reference IDs, source assertions or checks."""
    draft=parse_formula_draft(payload)
    return {"schema_version":"formula-draft-content-v1","content_digest":draft.content_digest,
        "authorization_verified":False,"execution_attested":False,"source_facts_verified":False,"display_checked":False,
        "condition_assessment":"declarations_only","formula":draft.data()}
