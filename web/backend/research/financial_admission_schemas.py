"""Strict financial-only data. No permission, budget write or provider source."""
from typing import Literal

from pydantic import model_validator

from .provider_schemas import (DTO,Id,Digest,Positive,Natural,Money,UsageUpperQuote,
    BudgetBasisSnapshot,canonical,digest,strict_json)
from .usage_upper import ReservedUpperMath

MAX_SNAPSHOT_BYTES=16384


class FinancialSnapshotError(ValueError):
    pass


class ProjectBudget(DTO):
    id:Literal[1]
    project_key:Literal['structure']
    funding_account_id:Id
    economic_binding:Id
    currency:Literal['CNY']
    scale:Literal[6]
    authorized_cap:Natural
    authorization_ref:Id
    authorization_digest:Digest
    database_binding:Digest
    mode:Literal['offline_probe']
    status:Literal['closed','active','blocked']
    version:Positive

    @model_validator(mode='before')
    @classmethod
    def strict_literal_integers(cls,value):
        if type(value) is dict and any(type(value.get(k)) is not int for k in ('id','scale')):
            raise ValueError('strict project integers required')
        return value


class ProjectAdmissionBinding(DTO):
    budget_id:Positive
    version:Positive
    authorized_cap:Money
    authorization_ref:Id
    authorization_digest:Digest
    database_binding:Digest
    account_id:Id
    economic_binding:Id
    funding_epoch:Positive


class ActorAdmissionBinding(DTO):
    principal_id:Id
    principal_epoch:Positive
    grant_id:Id
    grant_epoch:Positive
    approval_ref:Id
    approval_digest:Digest
    funding_permission_ref:Id
    funding_permission_digest:Digest
    scope_digest:Digest


class DispatchAdmissionBinding(DTO):
    task_id:Id
    step_id:Id
    attempt:Positive
    authorized_task_version:Positive
    authorized_step_version:Positive
    task_before:Positive
    task_after:Positive
    step_before:Positive
    step_after:Positive
    reservation_id:Id
    reservation_before:Positive
    reservation_after:Positive
    permit_id:Id
    permit_before:Literal['prepared']
    permit_after:Literal['consumed']
    dispatch_id:Id
    session_id:Id
    session_before:Positive
    session_after:Positive
    request_digest:Digest
    evidence_digest:Digest
    context_digest:Digest
    outbound_fingerprint:Digest

    @model_validator(mode='after')
    def actual_transitions(self):
        for name in ('task','step','reservation','session'):
            if getattr(self,name+'_after')!=getattr(self,name+'_before')+1:
                raise ValueError('one consumption transition required')
        if (self.authorized_task_version!=self.task_before or self.authorized_step_version!=self.step_before):
            raise ValueError('authorization version mismatch')
        return self


class FinancialAdmissionSnapshot(DTO):
    record_version:Literal['financial-admission-v1']
    producer_version:Literal['owned-budget-offline-v1']
    policy:Literal['bounded_usage_upper_v2']
    mode:Literal['offline_probe']
    purpose:Literal['method_hypothesis']
    project:ProjectAdmissionBinding
    actor:ActorAdmissionBinding
    dispatch:DispatchAdmissionBinding
    quote:UsageUpperQuote
    reserved:ReservedUpperMath
    basis:BudgetBasisSnapshot
    quote_digest:Digest
    basis_digest:Digest
    approved_upper:Money
    codec_digest:Digest
    math_version:Literal['bounded_usage_upper_v2']
    math_code_digest:Digest
    confirmed_at:Positive
    reserve_checked_at:Positive
    admitted_at:Positive
    recorded_at:Positive

    @model_validator(mode='before')
    @classmethod
    def native_json_only(cls,value):
        pending=[(value,0)];count=0
        while pending:
            item,depth=pending.pop();count+=1
            if depth>16 or count>2000:raise ValueError('bounded financial data required')
            if isinstance(item,DTO):item=item.model_dump()
            if type(item) is dict:
                if any(type(k) is not str for k in item):raise ValueError('strict keys required')
                pending.extend((child,depth+1) for child in item.values())
            elif type(item) is str:
                if len(item.encode('utf-8'))>MAX_SNAPSHOT_BYTES:raise ValueError('bounded text required')
            elif type(item) is not int:raise ValueError('native financial integers required')
        return value

    @model_validator(mode='after')
    def consistent_financial_data(self):
        p,d,q,b,r=self.project,self.dispatch,self.quote,self.basis,self.reserved
        if (p.budget_id!=1 or p.account_id!=b.account_id or p.economic_binding!=b.provider_binding_id
                or p.funding_epoch!=b.funding_epoch or b.price_revision!=q.revision
                or r.quote_revision!=q.revision or r.quote_digest!=self.quote_digest
                or self.quote_digest!=digest(canonical(q.model_dump()))
                or self.basis_digest!=digest(canonical(b.model_dump()))
                or r.dispatch_id!=d.dispatch_id or r.request_digest!=d.request_digest
                or r.reserved_upper!=self.approved_upper or self.codec_digest!=q.final_request_code_digest):
            raise ValueError('financial association mismatch')
        amounts=(p.authorized_cap,self.approved_upper,b.initial_prepaid,b.other_use_margin,b.cap,
            b.settled_actual,b.upper_booked,b.held,b.available_after_observed_consumption)
        if any(m.currency!='CNY' or type(m.scale) is not int or m.scale!=6 for m in amounts):
            raise ValueError('same native currency required')
        if b.cap.amount_units!=b.initial_prepaid.amount_units-b.other_use_margin.amount_units:
            raise ValueError('original cash basis mismatch')
        if not (self.confirmed_at<=self.reserve_checked_at<=self.admitted_at<=self.recorded_at<min(q.valid_until,b.valid_until)
                and 0<q.valid_until-self.reserve_checked_at<=60):
            raise ValueError('original admission window mismatch')
        return self


def validate_snapshot_json(raw,*,expected_digest=None):
    failed=False
    try:
        if type(raw) is not bytes:raise ValueError('bytes required')
        data=strict_json(raw,MAX_SNAPSHOT_BYTES)
        result=FinancialAdmissionSnapshot.model_validate(data)
        encoded=canonical(result.model_dump())
        if len(encoded)>MAX_SNAPSHOT_BYTES or (expected_digest is not None and digest(encoded)!=expected_digest):
            raise ValueError('snapshot digest mismatch')
    except (ValueError,TypeError,OverflowError,RecursionError):failed=True
    if failed:
        try:raise FinancialSnapshotError('invalid_financial_snapshot') from None
        except FinancialSnapshotError as safe:
            safe.__context__=None;safe.__cause__=None;safe.__suppress_context__=False
            raise
    return result
