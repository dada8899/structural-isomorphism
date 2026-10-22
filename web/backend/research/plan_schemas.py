"""Strict Financial8/phenomenon-plan API and historical data, never authority."""
from typing import Annotated,Literal
from pydantic import Field,StrictInt,StringConstraints,field_validator
from .schemas import StrictObject,Revision
from .phenomenon_plan import PlanDTO,PhenomenonPlanCandidate,PlanPreviewManifest

Digest=Annotated[str,StringConstraints(strict=True,pattern=r'^[a-f0-9]{64}$')]
Ref=Annotated[str,StringConstraints(strict=True,min_length=1,max_length=100,pattern=r'^[a-zA-Z0-9._:-]+$')]
Units=Annotated[StrictInt,Field(ge=0,le=9223372036854775807)]

class PlanPreviewRequest(StrictObject):
    input_revision:Revision
    expected_research_version:Revision
    observation_source:Literal['own_observation']
    declaration_status:Literal['self_declared']

class PlanConfirmationRequest(StrictObject):
    preview_ref:Ref
    preview_digest:Digest
    request_digest:Digest
    expected_research_version:Revision
    approved_upper_units:Units
    confirm_outbound:Literal[True]

    @field_validator('confirm_outbound',mode='before')
    @classmethod
    def actual_boolean(cls,value):
        if value is not True:raise ValueError('explicit true required')
        return value

class PlanPreviewEnvelope(StrictObject):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['b1-candidate-01']
    data:PlanPreviewRequest

class PlanConfirmationEnvelope(StrictObject):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['b1-candidate-01']
    data:PlanConfirmationRequest

class PlanQuote(PlanDTO):
    protocol:Literal['financial8-plan-quote-v1']
    revision:Ref
    purpose:Literal['phenomenon_plan_v1']
    provider:Literal['deepseek']
    model:Literal['deepseek-flash']
    declared_model_version:Literal['DeepSeek-V4.1-Flash-1017']
    declaration_observed_on:Literal['2026-10-18']
    currency:Literal['CNY']
    scale:Literal[6]
    peak_input_hit_units_per_million:Literal[40000]
    peak_input_miss_units_per_million:Literal[2000000]
    peak_output_units_per_million:Literal[8000000]
    context_bound:Literal[1048576]
    provider_output_bound:Literal[393216]
    max_output_tokens:Literal[4096]
    approved_upper_units:Units
    codec_digest:Digest
    issued_at:StrictInt
    valid_until:StrictInt
    price_source:Literal['https://api-docs.deepseek.com/zh-cn/quick_start/pricing/']

class PlanResult(PlanDTO):
    protocol:Literal['owned-phenomenon-plan-result-v1']
    purpose:Literal['phenomenon_plan_v1']
    result_ref:Ref
    task_id:Ref
    research_id:Ref
    input_revision:Revision
    input_digest:Digest
    request_digest:Digest
    admission_digest:Digest
    recorded_at:Annotated[str,StringConstraints(strict=True,pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$')]
    execution_mode:Literal['fixture']
    plan_generation_ran:Literal[True]
    real_model_executed:Literal[False]
    literature_status:Literal['not_retrieved']
    mathematics_status:Literal['not_checked']
    mechanism_status:Literal['unverified']
    observation_rights:Literal['self_declared']
    query_state:Literal['draft_only']
    automatically_created_sources:Literal[0]
    proposal:PhenomenonPlanCandidate

class PlanPreviewView(PlanDTO):
    preview_ref:Ref
    preview_digest:Digest
    request_digest:Digest
    research_id:Ref
    input_revision:Revision
    expected_research_version:Revision
    state:Literal['awaiting_confirmation']
    exact_input:Annotated[str,StringConstraints(strict=True,min_length=8,max_length=1000)]
    purpose:Literal['phenomenon_plan_v1']
    observation_rights:Literal['self_declared']
    approved_upper_units:Units
    currency:Literal['CNY']
    scale:Literal[6]
    quote:PlanQuote
    expires_at:StrictInt
    explanation:Annotated[str,StringConstraints(strict=True,max_length=160)]

class PlanConfirmationData(PlanDTO):
    task_id:Ref
    result_ref:Ref
    state:Literal['queued']
    funding_state:Literal['approved_not_sent']
    plan_generation_ran:Literal[False]
    recorded_at:None

class PlanUsage(PlanDTO):
    prompt_tokens:Annotated[StrictInt,Field(ge=0,le=1048576)]
    completion_tokens:Annotated[StrictInt,Field(ge=0,le=4096)]
    total_tokens:Annotated[StrictInt,Field(ge=0,le=1052672)]
    usage_priced_estimate_units:Units
    actual_charge_units:None
    cost_kind:Literal['upper_booked']
    booked_upper_units:Units
    currency:Literal['CNY']
    scale:Literal[6]

class PlanRunMetadata(PlanDTO):
    task_id:Ref
    result_ref:Ref
    state:Literal['saved','failed_insufficient','pending_reconciliation','cancelled','queued','generating']
    financial_state:Literal['unreserved','held','upper_booked','unknown']
    safe_code:Literal['saved','body_invalid','send_unknown','not_sent','cancelled','access_ended']|None
    recorded_at:Annotated[str,StringConstraints(strict=True,pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$')]|None
    plan_generation_ran:bool
    real_model_executed:Literal[False]
    execution_mode:Literal['fixture']
    approved_upper_units:Units
    usage:PlanUsage|None

class PlanReadData(PlanRunMetadata):
    content:PlanResult|None

class PlanPreviewResponse(PlanDTO):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-plan-v1']
    data:PlanPreviewView

class PlanConfirmationResponse(PlanDTO):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-plan-v1']
    data:PlanConfirmationData

class PlanReadResponse(PlanDTO):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-plan-v1']
    data:PlanReadData

class PlanAdmission(PlanDTO):
    protocol:Literal['financial-admission-v2']
    financial_version:Literal[8]
    purpose:Literal['phenomenon_plan_v1']
    producer:Literal['owned-plan-fixture-v1']
    producer_source_version:Literal['plan-producer-v1']
    producer_code_digest:Digest
    mode:Literal['fixture']
    task_id:Ref
    step_id:Ref
    grant_id:Ref
    grant_version:Revision
    dispatch_id:Ref
    result_ref:Ref
    nonce:Ref
    preview_ref:Ref
    preview_digest:Digest
    input_revision:Revision
    research_id:Ref
    research_version:Revision
    quote:PlanQuote
    approved_upper:Units
    raw_input:Annotated[str,StringConstraints(strict=True,min_length=8,max_length=1000)]
    input_manifest:PlanPreviewManifest
    input_manifest_digest:Digest
    input_digest:Digest
    request_digest:Digest
    template_digest:Digest
    template_code_digest:Digest
    principal_id:Ref
    generation:Annotated[str,StringConstraints(strict=True,min_length=1,max_length=128)]
    principal_epoch:Revision
    owner_epoch:Revision
    acl_epoch:Revision
    funding_version:Revision
    economic_binding:Ref
    credential_incarnation:Ref
    funding_epoch:Revision
