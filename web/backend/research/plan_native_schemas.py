"""Financial9 data only. Native authority is never constructed from these DTOs."""
from typing import Annotated,Literal
from pydantic import StrictBool,StrictInt,StringConstraints,model_validator
from .plan_schemas import PlanQuote,PlanPreviewRequest,PlanConfirmationRequest,PlanDTO,Ref,Digest,Units
from .schemas import Revision
from .phenomenon_plan import PhenomenonPlanCandidate

CONTRACT='funded-plan-v2'
Timestamp=Annotated[str,StringConstraints(strict=True,pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$')]
Mode=Literal['controlled_fixture','native_live']
Producer=Literal['core-controlled-native-v1','owned-native-plan-runtime-v1']

class NativePlanQuote(PlanQuote):
    protocol:Literal['financial9-native-quote-v1']

class NativePlanPreviewEnvelope(PlanDTO):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-plan-v2']
    data:PlanPreviewRequest

class NativePlanConfirmationEnvelope(PlanDTO):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-plan-v2']
    data:PlanConfirmationRequest

class NativePlanResult(PlanDTO):
    protocol:Literal['owned-native-plan-result-v2']
    purpose:Literal['phenomenon_plan_v1']
    result_ref:Ref
    task_id:Ref
    research_id:Ref
    input_revision:Revision
    input_digest:Digest
    request_digest:Digest
    consent_digest:Digest
    admission_digest:Digest
    recorded_at:Timestamp
    execution_mode:Mode
    producer:Producer
    real_model_executed:StrictBool
    weight_identity_verified:Literal[False]
    literature_status:Literal['not_retrieved']
    mathematics_status:Literal['not_checked']
    mechanism_status:Literal['unverified']
    observation_rights:Literal['self_declared']
    query_state:Literal['draft_only']
    automatically_created_sources:Literal[0]
    proposal:PhenomenonPlanCandidate

    @model_validator(mode='after')
    def actual_producer_mode(self):
        if (self.execution_mode=='native_live')!=self.real_model_executed or (self.producer=='core-controlled-native-v1' and self.execution_mode!='controlled_fixture'):
            raise ValueError('result producer/mode truth differs')
        return self

class NativePlanPreviewView(PlanDTO):
    preview_ref:Ref
    preview_digest:Digest
    request_digest:Digest
    research_id:Ref
    input_revision:Revision
    expected_research_version:Revision
    exact_input:Annotated[str,StringConstraints(strict=True,min_length=8,max_length=1000)]
    purpose:Literal['phenomenon_plan_v1']
    observation_rights:Literal['self_declared']
    state:Literal['awaiting_confirmation','funding_closed']
    can_confirm:StrictBool
    funding_reason:Literal['FUNDING_CLOSED']|None
    cash_evidence:Literal['not_observed']
    approved_upper_units:Units
    currency:Literal['CNY']
    scale:Literal[6]
    quote:NativePlanQuote
    expires_at:StrictInt
    explanation:Annotated[str,StringConstraints(strict=True,max_length=160)]

    @model_validator(mode='after')
    def confirmation_state(self):
        if self.can_confirm!=(self.state=='awaiting_confirmation') or (self.funding_reason is None)!=self.can_confirm:
            raise ValueError('confirmation state differs')
        return self

class NativePlanConfirmationData(PlanDTO):
    task_id:Ref
    result_ref:Ref
    state:Literal['queued']
    cash_evidence:Literal['not_observed']
    real_model_executed:Literal[False]
    recorded_at:None

class NativePlanRunMetadata(PlanDTO):
    task_id:Ref
    result_ref:Ref
    state:Literal['saved','failed_insufficient','pending_reconciliation','cancelled','queued','generating']
    financial_version:Literal[9]
    execution_mode:Mode|None
    real_model_executed:StrictBool
    cost_state:Literal['unreserved','held','upper_booked','unknown']
    cleanup_state:Literal['pending','clean','uncertain']
    safe_code:Literal['access_ended','saved','body_invalid','send_unknown','not_sent','cancelled']|None
    recorded_at:Timestamp|None

class NativePlanReadData(NativePlanRunMetadata):
    content:NativePlanResult|None

class NativePlanPreviewResponse(PlanDTO):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-plan-v2']
    data:NativePlanPreviewView

class NativePlanConfirmationResponse(PlanDTO):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-plan-v2']
    data:NativePlanConfirmationData

class NativePlanReadResponse(PlanDTO):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-plan-v2']
    data:NativePlanReadData
