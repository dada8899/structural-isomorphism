"""Strict manual method drafts. References never confer execution rights."""
from typing import Annotated, Literal
from pydantic import Field, StrictInt, StringConstraints, field_validator, model_validator
from .schemas import StrictObject, Revision, bounded_text

CONTRACT='method-draft-v1'
UUID=Annotated[str,StringConstraints(strict=True,pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$')]
Digest=Annotated[str,StringConstraints(strict=True,pattern=r'^[a-f0-9]{64}$')]
Text=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=2000)]

class DraftExcerptRef(StrictObject):
    excerpt_id: UUID
    source_revision: Revision
    content_digest: Digest
    start: Annotated[StrictInt,Field(ge=0,le=200000)]
    end: Annotated[StrictInt,Field(ge=1,le=200000)]
    @model_validator(mode='after')
    def range_bound(self):
        if not self.start<self.end or self.end-self.start>1000:raise ValueError('bounded exact excerpt required')
        return self

class PlanLeadOrigin(StrictObject):
    kind: Literal['plan_lead']
    plan_contract: Literal['funded-plan-v1','funded-plan-v2']
    result_ref: UUID
    candidate_index: Annotated[StrictInt,Field(ge=0,le=4)]
    lead_index: Annotated[StrictInt,Field(ge=0,le=1)]

class CatalogOrigin(StrictObject):
    kind: Literal['kb_record']
    artifact_id: Annotated[str,StringConstraints(strict=True,min_length=1,max_length=200)]
    record_id: Annotated[str,StringConstraints(strict=True,min_length=1,max_length=200)]
    record_digest: Digest

class UserMethodOrigin(StrictObject):
    kind: Literal['user_proposed']
    label: Annotated[str,StringConstraints(strict=True,min_length=1,max_length=120)]
    description: Text

class DraftTestPlan(StrictObject):
    question: Text
    measurement: Text
    primary_outcome: Text
    falsification: Text
    stop_rule: Text

class MethodDraftRequest(StrictObject):
    input_revision: Revision
    expected_research_version: Revision
    excerpt_refs: Annotated[list[DraftExcerptRef],Field(min_length=1,max_length=20)]
    origin: Annotated[PlanLeadOrigin|CatalogOrigin|UserMethodOrigin,Field(discriminator='kind')]
    method: Text
    mapping: Annotated[list[Text],Field(min_length=1,max_length=20)]
    nontransferable: Annotated[list[Text],Field(min_length=1,max_length=20)]
    competing_explanations: Annotated[list[Text],Field(min_length=1,max_length=20)]
    test_plan: DraftTestPlan
    formula_result_ref: UUID|None=None
    supersedes_ref: UUID|None=None
    @model_validator(mode='after')
    def bounded(self):
        if len({r.excerpt_id for r in self.excerpt_refs})!=len(self.excerpt_refs):raise ValueError('unique references required')
        def check(value):
            if isinstance(value,str):bounded_text(value,2000,1)
            elif isinstance(value,dict):
                for item in value.values():check(item)
            elif isinstance(value,list):
                for item in value:check(item)
        check(self.model_dump(mode='json'))
        from .provider_schemas import canonical
        if len(canonical(self.model_dump(mode='json')))>65536:raise ValueError('bounded request required')
        return self

class MethodDraftEnvelope(StrictObject):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['method-draft-v1']
    data: MethodDraftRequest

class MethodDraftMetadata(StrictObject):
    draft_ref: UUID
    input_revision: Revision
    problem_digest: Digest
    research_version_before: Revision
    research_version_after: Revision
    created_at: Annotated[str,StringConstraints(strict=True,pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$')]
    content_digest: Digest
    is_historical: bool
    origin_kind: Literal['plan_lead','kb_record','user_proposed']
    validation_status: Literal['unverified']='unverified'
    execution_status: Literal['not_executed']='not_executed'

class DraftSourceSummary(StrictObject):
    excerpt_id: UUID
    snapshot_id: UUID
    source_id: UUID
    source_revision: Revision
    content_digest: Digest
    raw_digest: Digest
    excerpt_digest: Digest
    snapshot_digest: Digest
    start: Annotated[StrictInt,Field(ge=0,le=200000)]
    end: Annotated[StrictInt,Field(ge=1,le=200000)]
    quote: Annotated[str,StringConstraints(strict=True,min_length=1,max_length=1000)]
    title: Annotated[str,StringConstraints(strict=True,max_length=500)]
    canonical_url: Annotated[str,StringConstraints(strict=True,max_length=2048)]
    licence_basis: Annotated[str,StringConstraints(strict=True,max_length=700)]
    task_id: UUID
    attempt: Literal[1]
    input_revision: Revision

class ResolvedUserOrigin(UserMethodOrigin):
    mode: Literal['user_proposed']
    verification: Literal['unverified']

class ResolvedPlanOrigin(PlanLeadOrigin):
    label: Text
    lead: Text
    mode: Literal['fixture','controlled_fixture','native_live']
    producer: Literal['owned-plan-fixture-v1','core-controlled-native-v1','owned-native-plan-runtime-v1']
    result_digest: Digest
    input_revision: Revision
    verification: Literal['unverified']

class DraftFormulaOutcome(StrictObject):
    check_kind: Literal['template','dimensions','canonical_transform','bounded_numeric']
    status: Literal['passed','failed','inconclusive','unsupported','resource_limit']
    relation: Literal['algebraic_identity','conditional_model_equivalence','local_approximation','partial_structure','not_equivalent','undetermined']

from .schemas import FormulaRunMetadata
class DraftFormulaLink(StrictObject):
    result_ref: UUID
    metadata: FormulaRunMetadata
    result_digest: Digest
    input_revision: Revision
    comparison_scope: Literal['expression','equation_form','initial_value_problem']
    outcomes: Annotated[list[DraftFormulaOutcome],Field(min_length=1,max_length=4)]
    execution_attested: bool

class MethodDraftContent(StrictObject):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['method-draft-v1']
    request: MethodDraftRequest
    sources: Annotated[list[DraftSourceSummary],Field(min_length=1,max_length=20)]
    origin: Annotated[ResolvedPlanOrigin|ResolvedUserOrigin,Field(discriminator='kind')]
    formula: DraftFormulaLink|None

class MethodDraftData(StrictObject):
    metadata: MethodDraftMetadata
    content: MethodDraftContent

class MethodDraftResponse(StrictObject):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['method-draft-v1']
    data: MethodDraftData

class MethodDraftHistoryData(StrictObject):
    items: Annotated[list[MethodDraftMetadata],Field(max_length=20)]
    next_cursor: UUID|None

class MethodDraftHistoryResponse(StrictObject):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['method-draft-v1']
    data: MethodDraftHistoryData
