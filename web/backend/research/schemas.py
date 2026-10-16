"""Strict, bounded inputs for the first research lifecycle checkpoint."""
from __future__ import annotations

import unicodedata
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, field_validator

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


class ProblemInput(StrictObject):
    entry: Literal["phenomenon", "formula", "research"]
    original_input: str
    objective: str
    summary: str
    variables: Annotated[list[Variable], Field(max_length=12)]
    constraints: Annotated[list[str], Field(max_length=12)]
    unknowns: Annotated[list[str], Field(max_length=12)]
    confirmed: StrictBool

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
