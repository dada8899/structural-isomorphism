"""Strict evidence-method data. None of these models is an execution grant."""
from datetime import datetime
import re
import unicodedata
from typing import Annotated, Literal, get_args, get_origin

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

CONTRACT = 'funded-evidence-method-v1'
PURPOSE = 'evidence_method_plan_v1'
INPUT_TEMPLATE = 'SelectedEvidenceMethodInput-v1'
CANDIDATE_SCHEMA = 'EvidenceMethodPlanCandidate-v1'
RESULT_SCHEMA = 'OwnedEvidenceMethodPlanResult-v1'
CODEC_REVISION = 'evidence-method-codec-v1-candidate'


def visible(value):
    if not value.strip() or any(unicodedata.category(c) in ('Cc','Cf','Cs') and c not in '\n\t' for c in value):
        raise ValueError('visible bounded text required')
    return value


def text(cap, minimum=1):return Annotated[str, Field(strict=True,min_length=minimum,max_length=cap), AfterValidator(visible)]
def seq(kind, minimum, maximum):return Annotated[tuple[kind,...], Field(min_length=minimum,max_length=maximum)]
H=Annotated[str,Field(strict=True,min_length=64,max_length=64,pattern=r'^[0-9a-f]{64}$')]
R=Annotated[str,Field(strict=True,min_length=36,max_length=36,pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')]
G=Annotated[str,Field(strict=True,min_length=32,max_length=32,pattern=r'^[0-9a-f]{32}$')]
V=Annotated[StrictInt,Field(ge=1,le=2147483647)]
N=Annotated[StrictInt,Field(ge=0,le=9223372036854775807)]
E=Annotated[StrictInt,Field(ge=0,le=253402300799)]
Ref=Annotated[str,Field(strict=True,min_length=1,max_length=100,pattern=r'^[a-zA-Z0-9._:-]+$')]
Handle=Literal['e1','e2','e3','e4','e5','e6','e7','e8']
Origin=Literal['live','offline_probe']
Mode=Literal['controlled_fixture','native_live']
Producer=Literal['core-controlled-native-v1','owned-native-plan-runtime-v1']
def utc(value):
    if datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%dT%H:%M:%S.%fZ')!=value:raise ValueError('exact UTC required')
    return value
U=Annotated[str,Field(strict=True,min_length=27,max_length=27,pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$'),AfterValidator(utc)]
PLOS=Annotated[str,Field(strict=True,max_length=160,pattern=r'^https://journals\.plos\.org/plosone/article\?id=10\.1371/journal\.pone\.[0-9]{7}$')]
Handles=seq(Handle,0,4)


class Data(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True,revalidate_instances='always',protected_namespaces=())
    @model_validator(mode='before')
    @classmethod
    def strict_literals_and_arrays(cls,value):
        if type(value) is not dict:return value
        result=value.copy()
        for name,field in cls.model_fields.items():
            if name not in result:continue
            annotation=field.annotation
            if get_origin(annotation) is Literal:
                choices=get_args(annotation)
                if not any(type(result[name]) is type(c) and result[name]==c for c in choices):raise ValueError('exact literal required')
            if get_origin(annotation) is tuple and type(result[name]) is list:result[name]=tuple(result[name])
        return result


class ProblemContext(Data):
    kind:Literal['owner_problem_summary']
    declaration:Literal['self_declared']
    summary:text(1000,8)


class SelectedHandle(Data):
    handle:Handle
    title:text(300)
    attribution:text(400)
    quote:text(1000)
    read_scope:Literal['author_narrative_subset']
    origin:Origin
    @model_validator(mode='after')
    def short_quote(self):
        if len(self.quote.split())>20:raise ValueError('short quote required')
        return self


class SelectedEvidenceMethodInput(Data):
    input_template:Literal['SelectedEvidenceMethodInput-v1']
    purpose:Literal['evidence_method_plan_v1']
    problem_context:ProblemContext
    handles:seq(SelectedHandle,1,8)
    @model_validator(mode='after')
    def ordered_handles(self):
        if tuple(h.handle for h in self.handles)!=tuple('e'+str(i+1) for i in range(len(self.handles))):raise ValueError('ordered unique handles required')
        return self


class Gap(Data):
    code:Literal['method_identity_missing','formula_not_recoverable','assumptions_not_supported','maturity_not_established','evidence_scope_limited','source_not_live','no_transfer_validation']
    detail:text(400)
    evidence_handles:Handles


class FormulaProposal(Data):
    text:text(700)
    basis:Literal['quoted_subset','unverified_proposal']
    evidence_handles:Handles


class EvidenceLink(Data):
    handle:Handle
    role:Literal['context','mechanism','method_identity','formula','assumption','condition','counterexample']
    proposed_support:text(240)
    missing_support:text(240)


class VariableMap(Data):
    method_variable:text(80)
    target_variable:text(120)
    rationale:text(240)
    evidence_handles:Handles


class Applicability(Data):
    condition:text(240)
    evidence_handles:Handles
    gap:text(240)|None


class Falsifier(Data):
    statement:text(400)
    evidence_handles:Handles


class VerificationPlan(Data):
    question:text(240)
    measurements:seq(text(240),1,5)
    comparison:text(240)
    primary_outcome:text(240)
    falsification:text(400)
    stop_rule:text(240)
    inputs_needed:seq(text(240),1,8)


class MethodCandidate(Data):
    candidate_kind:Literal['mechanism','mathematical_method']
    label:text(120)
    mechanism_hypothesis:text(700)
    method_name:text(160)|None
    formula_proposal:FormulaProposal|None
    evidence_links:seq(EvidenceLink,1,8)
    variable_map:seq(VariableMap,0,10)
    applicability:seq(Applicability,1,6)
    competing_explanations:seq(text(400),1,4)
    nontransferable:seq(text(240),1,5)
    counterexamples_or_falsifiers:seq(Falsifier,1,4)
    verification_plan:VerificationPlan
    gaps:seq(Gap,1,8)
    @model_validator(mode='after')
    def named_mathematics(self):
        if self.candidate_kind=='mathematical_method' and self.method_name is None:raise ValueError('method name required')
        return self


class EvidenceMethodPlanCandidate(Data):
    summary:text(700)
    candidates:seq(MethodCandidate,0,3)
    gaps:seq(Gap,1,8)
    clarification_questions:seq(text(240),0,3)
    @model_validator(mode='after')
    def untrusted_candidate(self):
        if not self.candidates and not self.clarification_questions:raise ValueError('clarification required')
        pending=[self.model_dump(mode='json')]
        forbidden=re.compile(r'https?://|www\.|\b10\.\d{4,9}/|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|```|<script|(?:^|\n)\s*(?:sudo\s|curl\s|wget\s|python[0-9]*\s+-|bash\s+-)',re.I)
        while pending:
            item=pending.pop()
            if type(item) is dict:pending.extend(item.values())
            elif type(item) is list:pending.extend(item)
            elif type(item) is str and forbidden.search(item):raise ValueError('candidate is bounded explanatory data only')
        return self


class ManifestRoot(Data):
    research_id:R
    input_revision:V
    input_digest:H
    approved_research_version:V


class ManifestOwner(Data):
    principal_id:R
    generation_digest:H
    owner_epoch:V
    acl_epoch:V


class ManifestEntry(Data):
    handle:Handle
    source_id:R
    source_revision:V
    excerpt_id:R
    source_task_id:R
    attempt:Literal[1]
    raw_digest:H
    extracted_digest:H
    discovery_digest:H
    excerpt_payload_digest:H
    snapshot_payload_digest:H
    permission_basis_digest:H
    start:Annotated[StrictInt,Field(ge=0,le=199999)]
    end:Annotated[StrictInt,Field(ge=1,le=200000)]
    quote_sha256:H
    title:text(300)
    canonical_url:PLOS
    attribution:text(400)
    read_scope:Literal['author_narrative_subset']
    origin:Origin
    acquired_at:U
    information_cutoff:U
    @model_validator(mode='after')
    def span(self):
        if self.start>=self.end:raise ValueError('exact source span required')
        return self


class SelectionManifest(Data):
    root:ManifestRoot
    owner:ManifestOwner
    entries:seq(ManifestEntry,1,8)
    @model_validator(mode='after')
    def sequence(self):
        if tuple(e.handle for e in self.entries)!=tuple('e'+str(i+1) for i in range(len(self.entries))) or len({e.excerpt_id for e in self.entries})!=len(self.entries):raise ValueError('unique ordered source selection required')
        return self


class ContentDomain(Data):
    purpose:Literal['evidence_method_plan_v1']
    input_template:Literal['SelectedEvidenceMethodInput-v1']
    candidate_schema:Literal['EvidenceMethodPlanCandidate-v1']
    result_schema:Literal['OwnedEvidenceMethodPlanResult-v1']
    codec_revision:Literal['evidence-method-codec-v1-candidate']
    template_digest:H
    template_code_digest:H
    producer_digest:H
    selection_digest:H
    selected_input_digest:H
    request_digest:H


class OutboundDomain(ContentDomain):
    outbound_scope_digest:H


class EvidenceMethodQuote(Data):
    protocol:Literal['financial9-evidence-method-quote-v1']
    revision:R
    purpose:Literal['evidence_method_plan_v1']
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
    approved_upper_units:Literal[2129920]
    codec_digest:H
    issued_at:E
    valid_until:E
    price_source:Literal['https://api-docs.deepseek.com/zh-cn/quick_start/pricing/']
    @model_validator(mode='after')
    def life(self):
        if self.valid_until!=self.issued_at+60:raise ValueError('fixed quote lifetime required')
        return self


class PreviewConsent(Data):
    protocol:Literal['evidence-method-preview-consent-v1']
    domain:OutboundDomain
    principal_id:R
    generation:G
    research_id:R
    input_revision:V
    input_digest:H
    owner_epoch:V
    acl_epoch:V
    preview_research_version:V
    execution_research_version:V
    selection_manifest:SelectionManifest
    exact_input:SelectedEvidenceMethodInput
    quote_digest:H
    @model_validator(mode='after')
    def version_binding(self):
        if self.execution_research_version!=self.preview_research_version+1:raise ValueError('execution version binding differs')
        if (self.research_id,self.input_revision,self.input_digest,self.preview_research_version)!=(self.selection_manifest.root.research_id,self.selection_manifest.root.input_revision,self.selection_manifest.root.input_digest,self.selection_manifest.root.approved_research_version):raise ValueError('selection root differs')
        if (self.principal_id,self.owner_epoch,self.acl_epoch)!=(self.selection_manifest.owner.principal_id,self.selection_manifest.owner.owner_epoch,self.selection_manifest.owner.acl_epoch):raise ValueError('selection owner differs')
        from .provider_schemas import digest
        if digest(self.generation.encode())!=self.selection_manifest.owner.generation_digest:raise ValueError('selection generation differs')
        if tuple(h.handle for h in self.exact_input.handles)!=tuple(e.handle for e in self.selection_manifest.entries):raise ValueError('selection handle order differs')
        for handle,entry in zip(self.exact_input.handles,self.selection_manifest.entries):
            if (handle.title,handle.attribution,handle.read_scope,handle.origin,digest(handle.quote.encode()))!=(entry.title,entry.attribution,entry.read_scope,entry.origin,entry.quote_sha256):raise ValueError('selection exact input differs')
        return self


class ConfirmedConsent(PreviewConsent):
    protocol:Literal['evidence-method-consent-v1']
    task_id:R
    step_id:R
    grant_id:R
    grant_version:V
    dispatch_id:R
    result_ref:R
    nonce:R
    account_id:R
    economic_binding:Ref
    authority_digest:H
    funding_version:V
    grant_epoch:V
    credential_incarnation:Ref
    mode:Mode
    producer:Producer
    quote:EvidenceMethodQuote
    task_outbound_scope_digest:H
    @model_validator(mode='after')
    def producer_mode(self):
        if self.producer=='core-controlled-native-v1' and self.mode!='controlled_fixture':raise ValueError('actual controlled producer mode differs')
        return self


class BalanceAudit(Data):
    protocol:Literal['owned-balance-v1']
    mode:Mode
    balance_units:N
    currency:Literal['CNY']
    observed_at:E
    response_digest:H
    credential_incarnation:Ref


class LedgerBefore(Data):
    id:R
    binding_id:Ref
    fixture_port:Annotated[StrictInt,Field(ge=1,le=65535)]|None
    mode:Literal['fixture','live']
    currency:Literal['USD','CNY']
    scale:Literal[6]
    funding_epoch:V
    cap:N
    settled:N
    held:N
    status:Literal['active','unverified','reconciling','blocked']
    snapshot_id:Ref|None
    version:V
    provider:Literal['fixture','deepseek']
    initial_prepaid_units:N|None
    other_use_margin_units:N|None
    upper_booked:N


class FundingBefore(Data):
    id:Literal[1]
    mode:Mode
    state:Literal['authorized','blocked','retired']
    principal_id:R|None
    generation:G|None
    owner_gate_id:R
    authority_ref:Ref
    authority_digest:H
    account_id:R
    economic_binding:Ref
    credential_incarnation:Ref
    grant_epoch:V
    approved_cap_units:N
    risk_margin_units:N
    runtime_digest:H
    network_ref:Ref
    balance_claim:R|None
    balance_nonce:R|None
    version:V


class EvidenceMethodAdmission(Data):
    protocol:Literal['financial9-evidence-method-admission-v1']
    financial_version:Literal[9]
    domain:OutboundDomain
    task_outbound_scope_digest:H
    mode:Mode
    producer:Producer
    consent_digest:H
    quote:EvidenceMethodQuote
    observed_balance:BalanceAudit
    ledger_before:LedgerBefore
    funding_before:FundingBefore


class ResultCitation(Data):
    handle:Handle
    source_id:R
    source_revision:V
    excerpt_id:R
    source_task_id:R
    source_input_revision:V
    raw_digest:H
    extracted_digest:H
    discovery_digest:H
    start:Annotated[StrictInt,Field(ge=0,le=199999)]
    end:Annotated[StrictInt,Field(ge=1,le=200000)]
    quote:text(1000)
    title:text(300)
    canonical_url:PLOS
    attribution:text(400)
    read_scope:Literal['author_narrative_subset']
    origin:Origin
    acquired_at:U
    @model_validator(mode='after')
    def span(self):
        if self.start>=self.end or len(self.quote.split())>20:raise ValueError('exact short citation required')
        return self


class OwnedEvidenceMethodPlanResult(Data):
    protocol:Literal['owned-evidence-method-plan-result-v1']
    domain:OutboundDomain
    task_outbound_scope_digest:H
    result_ref:R
    task_id:R
    research_id:R
    input_revision:V
    input_digest:H
    consent_digest:H
    admission_digest:H
    recorded_at:U
    execution_mode:Mode
    producer:Producer
    real_model_executed:StrictBool
    weight_identity_verified:Literal[False]
    literature_status:Literal['selected_stored_excerpts_only']
    maturity_status:Literal['candidate_unverified']
    mathematics_status:Literal['not_checked']
    mechanism_status:Literal['unverified']
    transfer_status:Literal['not_validated']
    automatically_created_sources:Literal[0]
    source_origin:Literal['live','offline_probe','mixed']
    citations:seq(ResultCitation,1,8)
    candidate:EvidenceMethodPlanCandidate
    @model_validator(mode='after')
    def mode_truth(self):
        origins={c.origin for c in self.citations}
        if self.real_model_executed!=(self.execution_mode=='native_live') or self.producer=='core-controlled-native-v1' and self.execution_mode!='controlled_fixture':raise ValueError('actual producer truth differs')
        if self.source_origin!=('mixed' if len(origins)>1 else next(iter(origins))):raise ValueError('actual source origin differs')
        return self


class OwnedReturnReceipt(Data):
    protocol:Literal['owned-evidence-method-return-v1']
    domain:OutboundDomain
    task_outbound_scope_digest:H
    dispatch:R
    nonce:R
    mode:Mode
    producer:Producer
    runtime_digest:H
    consent_digest:H
    admission_digest:H
    response_digest:H
    status:Annotated[StrictInt,Field(ge=100,le=599)]
    provider_model_label:Annotated[str,Field(strict=True,max_length=120,pattern=r'^[\x20-\x7e]*$')]|None
    weight_identity_verified:Literal[False]


class EvidenceMethodCommit(Data):
    protocol:Literal['evidence-method-commit-v1']
    domain:OutboundDomain
    task_outbound_scope_digest:H
    task_id:R
    step_id:R
    result_ref:R
    recorded_at:U
    consent_digest:H
    admission_digest:H
    result_digest:H|None
    receipt_digest:H
    usage_digest:H|None
    preview_research_version:V
    execution_research_version:V
    task_before:Literal[2]
    task_after:Literal[3]
    step_before:Literal[2]
    step_after:Literal[3]


class EvidenceMethodPreviewRequest(Data):
    input_revision:V
    expected_research_version:V
    excerpt_refs:seq(R,1,8)
    context_declaration:Literal['self_declared']
    @model_validator(mode='after')
    def unique_refs(self):
        if len(set(self.excerpt_refs))!=len(self.excerpt_refs):raise ValueError('unique selection required')
        return self


class EvidenceMethodConfirmRequest(Data):
    preview_ref:R
    preview_digest:H
    request_digest:H
    selection_manifest_digest:H
    expected_research_version:V
    approved_upper_units:N
    confirm_outbound:Literal[True]


class EvidenceMethodPreviewEnvelope(Data):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-evidence-method-v1']
    data:EvidenceMethodPreviewRequest


class EvidenceMethodConfirmEnvelope(Data):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-evidence-method-v1']
    data:EvidenceMethodConfirmRequest


class PublicSourceRef(Data):
    handle:Handle
    source_id:R
    source_revision:V
    excerpt_id:R
    source_task_id:R
    source_input_revision:V
    raw_digest:H
    extracted_digest:H
    discovery_digest:H
    start:Annotated[StrictInt,Field(ge=0,le=199999)]
    end:Annotated[StrictInt,Field(ge=1,le=200000)]
    quote_sha256:H
    canonical_url:PLOS
    read_scope:Literal['author_narrative_subset']
    origin:Origin
    acquired_at:U


class EvidenceMethodPreviewData(Data):
    preview_ref:R
    preview_digest:H
    research_id:R
    input_revision:V
    research_version:V
    purpose:Literal['evidence_method_plan_v1']
    input_template:Literal['SelectedEvidenceMethodInput-v1']
    candidate_schema:Literal['EvidenceMethodPlanCandidate-v1']
    selection_manifest_digest:H
    selected_input_digest:H
    request_digest:H
    template_digest:H
    outbound_scope_digest:H
    exact_input:SelectedEvidenceMethodInput
    source_references:seq(PublicSourceRef,1,8)
    quote:EvidenceMethodQuote
    approved_upper_units:N
    expires_at:E
    cash_evidence:Literal['not_observed']
    state:Literal['awaiting_confirmation','funding_closed']
    can_confirm:StrictBool
    funding_reason:Literal['FUNDING_CLOSED','FUNDING_GRANT_REQUIRED','FUNDING_STALE']|None
    model_analysis_ran:Literal[False]
    real_model_executed:Literal[False]
    @model_validator(mode='after')
    def displayed_binding(self):
        if self.can_confirm!=(self.state=='awaiting_confirmation') or (self.funding_reason is None)!=self.can_confirm:raise ValueError('funding display differs')
        if self.approved_upper_units!=self.quote.approved_upper_units or self.expires_at!=self.quote.valid_until:raise ValueError('quote display differs')
        if tuple(r.handle for r in self.source_references)!=tuple(h.handle for h in self.exact_input.handles):raise ValueError('display order differs')
        return self


class EvidenceMethodConfirmData(Data):
    task_id:R
    result_ref:R
    input_revision:V
    execution_research_version:V
    purpose:Literal['evidence_method_plan_v1']
    selection_manifest_digest:H
    request_digest:H
    state:Literal['queued']
    funding_state:Literal['approved_not_sent']
    cost_state:Literal['unreserved']
    cash_evidence:Literal['not_observed']
    financial_version:Literal[9]
    real_model_executed:Literal[False]
    model_analysis_ran:Literal[False]
    recorded_at:None


class EvidenceMethodMeta(Data):
    task_id:R
    result_ref:R
    research_id:R
    input_revision:V
    input_digest:H
    selection_manifest_digest:H
    request_digest:H
    purpose:Literal['evidence_method_plan_v1']
    state:Literal['queued','generating','saved','failed_insufficient','pending_reconciliation','cancelled']
    cost_state:Literal['unreserved','held','upper_booked','unknown']
    cleanup_state:Literal['pending','clean','uncertain']
    safe_code:Literal['access_ended','saved','body_invalid','send_unknown','not_sent','cancelled']|None
    recorded_at:U|None
    execution_mode:Mode|None
    real_model_executed:StrictBool|None
    is_historical:StrictBool


class EvidenceMethodReadData(Data):
    metadata:EvidenceMethodMeta
    content_state:Literal['none','available','unavailable']
    unavailable_reason:Literal['SOURCE_PERMISSION_UNAVAILABLE','SOURCE_UNAVAILABLE']|None
    content:OwnedEvidenceMethodPlanResult|None
    @model_validator(mode='after')
    def content_truth(self):
        if self.content_state=='available':
            if self.content is None or self.unavailable_reason is not None:raise ValueError('available body required')
        elif self.content is not None or (self.content_state=='none')!=(self.unavailable_reason is None):raise ValueError('unavailable body must be withheld')
        return self


Cursor=Annotated[str,Field(strict=True,max_length=2048,pattern=r'^[A-Za-z0-9_-]+$')]
class EvidenceMethodListData(Data):
    items:seq(EvidenceMethodMeta,0,20)
    next_cursor:Cursor|None


class EvidenceMethodPreviewResponse(Data):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-evidence-method-v1']
    data:EvidenceMethodPreviewData


class EvidenceMethodConfirmResponse(Data):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-evidence-method-v1']
    data:EvidenceMethodConfirmData


class EvidenceMethodReadResponse(Data):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-evidence-method-v1']
    data:EvidenceMethodReadData


class EvidenceMethodListResponse(Data):
    schema_version:Literal['structure-research-v1']
    contract_revision:Literal['funded-evidence-method-v1']
    data:EvidenceMethodListData


EvidenceMethodErrorCode=Literal['AUTH_REQUIRED','AUTHORIZATION_STALE','FUNDING_GRANT_REQUIRED','NOT_FOUND','REVISION_CONFLICT','IDEMPOTENCY_CONFLICT','PREVIEW_CHANGED','PREVIEW_EXPIRED','TASK_ACTIVE','FUNDING_BUSY','FUNDING_STALE','SOURCE_PERMISSION_UNAVAILABLE','RECONCILIATION_REQUIRED','PAYLOAD_LIMIT','INPUT_INVALID','BUDGET_EXHAUSTED','FEATURE_UNAVAILABLE','FUNDING_CLOSED','STORE_UNAVAILABLE','RESULT_UNAVAILABLE','RESPONSE_UNAVAILABLE','CLEANUP_UNCERTAIN']
class EvidenceMethodPublicError(Data):
    code:EvidenceMethodErrorCode
    message:text(400)
    retryable:Literal[False]
    allowed_next_actions:seq(Literal['sign_in'],0,1)
    incident_id:R
    @model_validator(mode='after')
    def actions(self):
        if self.allowed_next_actions!=(('sign_in',) if self.code=='AUTH_REQUIRED' else ()):raise ValueError('fixed error actions required')
        return self


class EvidenceMethodErrorResponse(Data):
    error:EvidenceMethodPublicError
