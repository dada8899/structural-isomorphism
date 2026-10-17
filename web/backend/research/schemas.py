"""Strict, bounded inputs for the first research lifecycle checkpoint."""
from __future__ import annotations

import unicodedata
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, field_validator, model_validator

SCHEMA_VERSION = "structure-research-v1"
CONTRACT_REVISION = "b1-candidate-01"
Revision = Annotated[StrictInt, Field(ge=1, le=2147483647)]
Identifier = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]{0,31}$")]


def bounded_text(value: str, maximum: int, minimum: int = 0, *, normalize: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError("text required")
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in "\t\n" for c in value):
        raise ValueError("control characters are not allowed")
    result = unicodedata.normalize("NFC", value) if normalize else value
    if not minimum <= len(result) <= maximum:
        raise ValueError("text length outside allowed range")
    return result


class StrictObject(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResearchIndexQuery(StrictObject):
    limit: Annotated[StrictInt, Field(ge=1, le=20)] = 20
    cursor: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1024, pattern=r"^[A-Za-z0-9_-]+$")] | None = None


class Variable(StrictObject):
    id: Identifier
    label: str
    role: Literal["state", "parameter", "input", "constraint", "output"]
    unit_id: Literal["one", "count", "s", "workday", "count_per_s", "count_per_workday", "inverse_s", "inverse_workday", "K", "J_per_K", "K_per_W", "V", "A", "ohm", "F"] | None
    observation: str | None
    provenance: Literal["user_observed", "user_assumed", "system_proposed"]

    @field_validator("label")
    @classmethod
    def label_bound(cls, value):
        return bounded_text(value, 120)

    @field_validator("observation")
    @classmethod
    def observation_bound(cls, value):
        return None if value is None else bounded_text(value, 400)


class FormulaSideDraft(StrictObject):
    family: Literal["queue_flow", "first_order_storage", "local_recovery"]
    template_id: Literal["little", "mm1", "passive_decay", "linear_stable"]
    original_display: str
    expression: dict | None
    symbols: Annotated[list[dict], Field(max_length=12)]
    assumptions: Annotated[list[dict], Field(max_length=24)]
    initial_conditions: Annotated[list[dict], Field(max_length=1)]
    boundary_conditions: Annotated[list[dict], Field(max_length=24)]
    source_refs: Annotated[list[dict], Field(max_length=20)] = []
    measure_scope: str
    time_basis: Literal["s", "workday", "from_symbol_units"] = "from_symbol_units"

    @model_validator(mode="after")
    def approved_components(self):
        from .formula_schemas import FormulaInputError,FormulaLimit,Node,Symbol,Condition,InitialValue,SourceRef,bounded
        from .formula_policy import TEMPLATES,UNITS
        if TEMPLATES[self.template_id]!=self.family:raise ValueError('template family mismatch')
        bounded(self.original_display,2048);bounded(self.measure_scope,20)
        if self.expression is not None:Node.parse(self.expression)
        symbols=[Symbol.parse(v) for v in self.symbols]
        if len({v.id for v in symbols})!=len(symbols) or len({v.role for v in symbols})!=len(symbols):raise ValueError('symbol bijection required')
        if any(v.unit_id not in UNITS for v in symbols):raise ValueError('registered unit required')
        from .formula_policy import basis
        bases={basis(v.unit_id) for v in symbols if basis(v.unit_id) is not None}
        if self.time_basis!='from_symbol_units' and bases!={self.time_basis}:raise ValueError('declared time basis must match symbols')
        conditions=[Condition.parse(v) for v in self.assumptions+self.boundary_conditions]
        if len({v.id for v in conditions})!=len(conditions):raise ValueError('duplicate condition')
        initials=[InitialValue.parse(v) for v in self.initial_conditions]
        if len(conditions)+len(initials)>24:raise ValueError('condition limit')
        sources=[SourceRef.parse(v) for v in self.source_refs]
        if len({v.id for v in sources})!=len(sources):raise ValueError('duplicate source')
        return self


class FormulaRevisionDraft(StrictObject):
    input_origin: Literal["user_provided"]
    comparison_scope: Literal["expression", "equation_form", "initial_value_problem"]
    left: FormulaSideDraft
    right: FormulaSideDraft | None
    requested_checks: Annotated[list[Literal["template", "dimensions", "canonical_transform", "bounded_numeric"]], Field(min_length=1,max_length=4)]
    sample_points: Annotated[list[str], Field(max_length=256)]

    @model_validator(mode="after")
    def approved_comparison(self):
        from .formula_schemas import decimal_text,canonical
        if len(self.requested_checks)!=len(set(self.requested_checks)):raise ValueError('duplicate check')
        if self.right is None and set(self.requested_checks)-{'template','dimensions'}:raise ValueError('comparison requires two sides')
        points=[decimal_text(v) for v in self.sample_points]
        if len(points)!=len(set(points)):raise ValueError('duplicate sample point')
        if len(canonical(self.model_dump(mode='json')).encode())>65536:raise ValueError('formula input limit')
        return self


class FormulaCheckRequest(StrictObject):
    input_revision: Revision
    expected_research_version: Revision
    formula_digest: Annotated[str, StringConstraints(strict=True,pattern=r"^[a-f0-9]{64}$")]
    confirm_formula_input: StrictBool

    @field_validator('confirm_formula_input')
    @classmethod
    def explicit_formula_confirmation(cls,value):
        if value is not True:raise ValueError('explicit formula confirmation required')
        return value


class FormulaCheckEnvelope(StrictObject):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: FormulaCheckRequest


class ProblemInput(StrictObject):
    entry: Literal["phenomenon", "formula", "research"]
    original_input: str
    objective: str
    summary: str
    variables: Annotated[list[Variable], Field(max_length=12)]
    constraints: Annotated[list[str], Field(max_length=12)]
    unknowns: Annotated[list[str], Field(max_length=12)]
    confirmed: StrictBool
    formula_draft: FormulaRevisionDraft | None = None

    @field_validator("original_input")
    @classmethod
    def original_bound(cls, value):
        # Preserve what the user entered; normalized summaries are separate.
        return bounded_text(value, 4000, 1, normalize=False)

    @field_validator("objective")
    @classmethod
    def objective_bound(cls, value):
        return bounded_text(value, 1000)

    @field_validator("summary")
    @classmethod
    def summary_bound(cls, value):
        return bounded_text(value, 1000, 8)

    @field_validator("constraints", "unknowns")
    @classmethod
    def list_bounds(cls, values):
        return [bounded_text(value, 120) for value in values]

    @field_validator("variables")
    @classmethod
    def unique_variables(cls, values):
        if len({v.id for v in values}) != len(values):
            raise ValueError("duplicate variable id")
        return values


class CreateResearchRequest(StrictObject):
    problem: ProblemInput


class RevisionRequest(StrictObject):
    expected_revision: Revision
    problem: ProblemInput


class CreateEnvelope(StrictObject):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: CreateResearchRequest


class RevisionEnvelope(StrictObject):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: RevisionRequest


MAX_MONEY = 9223372036854775807
Units = Annotated[StrictInt, Field(ge=0, le=MAX_MONEY)]


class Money(StrictObject):
    currency: Literal["USD"]
    scale: Annotated[StrictInt, Field(ge=6, le=6)]
    amount_units: Units


class StartTaskRequest(StrictObject):
    input_revision: Revision
    expected_research_version: Revision
    mode: Literal["research"]


class TaskVersionRequest(StrictObject):
    task_id: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
    expected_task_version: Revision


class StartEnvelope(StrictObject):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: StartTaskRequest


class TaskEnvelope(StrictObject):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: TaskVersionRequest


class SourcePreviewRequest(StrictObject):
    input_revision: Revision
    expected_research_version: Revision
    query: Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z][A-Za-z -]{2,159}$")]

    @field_validator("query")
    @classmethod
    def source_query_bound(cls,value):
        if re.fullmatch(r"[A-Za-z][A-Za-z -]{2,159}",value) is None:raise ValueError("fixed academic query required")
        return value


class SourceApprovalRequest(SourcePreviewRequest):
    preview_digest: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
    confirm_external: StrictBool


class SourceStartRequest(StrictObject):
    input_revision: Revision
    expected_research_version: Revision
    approval_ref: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]


class SourcePreviewEnvelope(StrictObject):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: SourcePreviewRequest


class SourceApprovalEnvelope(StrictObject):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: SourceApprovalRequest


class SourceStartEnvelope(StrictObject):
    schema_version: Literal["structure-research-v1"]
    contract_revision: Literal["b1-candidate-01"]
    data: SourceStartRequest


PaidId=Annotated[str,StringConstraints(strict=True,pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
PaidDigest=Annotated[str,StringConstraints(strict=True,pattern=r"^[a-f0-9]{64}$")]


class PaidPreviewRequest(StrictObject):
    input_revision:Revision
    expected_research_version:Revision
    excerpt_ids:Annotated[list[PaidId],Field(min_length=1,max_length=20)]
    purpose:Literal['method_hypothesis']

    @field_validator('excerpt_ids')
    @classmethod
    def unique_excerpts(cls,values):
        if len(values)!=len(set(values)):raise ValueError('duplicate excerpt')
        return values


class PaidConfirmationRequest(StrictObject):
    preview_ref:PaidId
    expected_preview_version:Revision
    input_revision:Revision
    expected_research_version:Revision
    preview_digest:PaidDigest
    confirm_external_input:StrictBool
    confirm_maximum_reserve:StrictBool

    @field_validator('confirm_external_input','confirm_maximum_reserve')
    @classmethod
    def explicit_true(cls,value):
        if value is not True:raise ValueError('explicit confirmation required')
        return value


class PaidPreviewEnvelope(StrictObject):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['b1-candidate-01']
    data:PaidPreviewRequest


class PaidConfirmationEnvelope(StrictObject):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['b1-candidate-01']
    data:PaidConfirmationRequest


class FixtureResult(StrictObject):
    dispatch_id: str
    receipt_ref: Annotated[str, StringConstraints(strict=True, pattern=r"^[a-zA-Z0-9._:-]{1,120}$")]
    final: StrictBool
    cost: Money | None
    note: str | None

    @field_validator("note")
    @classmethod
    def note_bound(cls, value):
        return None if value is None else bounded_text(value, 1200)


FormulaUUID=Annotated[str,StringConstraints(strict=True,pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$')]
FormulaDigest=Annotated[str,StringConstraints(strict=True,pattern=r'^[a-f0-9]{64}$')]


class FormulaRunMetadata(StrictObject):
    result_ref: FormulaUUID
    state: Literal['claimed','returned','closed','interrupted']
    result_available: StrictBool
    input_origin: Literal['user_provided']
    formula_digest: FormulaDigest | None
    formula_result_recorded_at: Annotated[str,StringConstraints(strict=True,pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$')] | None
    math_status: None
    termination_state: Literal['not_attested','reaped','pending']
    task_completed_means_math_passed: Literal[False]
    known_cost_units: Literal[0]


class FormulaCheckData(FormulaRunMetadata):
    task_id: FormulaUUID


class FormulaCheckResponse(StrictObject):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['b1-candidate-01']
    data: FormulaCheckData


class FormulaExecutionProvenance(StrictObject):
    execution_attested: StrictBool
    execution_state: Literal['ok','unsupported','limited','memory_limited','failed']
    resource_guard: str
    owned_return_ref: FormulaUUID
    reaped: Literal[True]
    code_version: FormulaDigest
    full_input_digest: FormulaDigest
    output_digest: FormulaDigest
    formula_digest: FormulaDigest
    problem_digest: FormulaDigest
    display_AST_confirmation: Literal['user_confirmed_snapshot']
    source_origin: Literal['user_provided']
    source_facts_verified: Literal[False]
    mathematics_is_not_real_world_mechanism: Literal[True]


class FormulaResultData(StrictObject):
    metadata: FormulaRunMetadata
    state: Literal['available','unavailable']
    result: dict | None
    provenance: FormulaExecutionProvenance | None = None


class FormulaResultResponse(StrictObject):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['b1-candidate-01']
    data: FormulaResultData
