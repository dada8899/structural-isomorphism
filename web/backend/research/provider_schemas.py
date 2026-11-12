"""Unwired bounded-provider DTOs and exact arithmetic; never a funding ledger."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator

MODEL = 'deepseek-flash'
DECLARED_VERSION = 'DeepSeek-V4.1-Flash'
HOST = 'api.deepseek.com'
PATH = '/chat/completions'
REQUEST_CAP = 16 * 1024
RESPONSE_CAP = 128 * 1024
CANDIDATE_CAP = 32 * 1024
MAX_UNITS = (1 << 63) - 1
POLICY = 'deepseek-bounded-upper-v1'
Digest = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]
Id = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$')]
Natural = Annotated[StrictInt, Field(ge=0, le=MAX_UNITS)]
Positive = Annotated[StrictInt, Field(ge=1, le=2147483647)]
Handle = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-zA-Z][a-zA-Z0-9_]{0,31}$')]


class ProviderFailure(ValueError):
    """Only fixed safe codes are exposed, never raw network/model exceptions."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value: bytes):
    return hashlib.sha256(value).hexdigest()


def strict_json(raw: bytes, cap=RESPONSE_CAP):
    if type(raw) is not bytes or not 0 < len(raw) <= cap:
        raise ProviderFailure('invalid_json')
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ProviderFailure('invalid_json')
            output[key] = value
        return output
    def constant(_):
        raise ProviderFailure('invalid_json')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderFailure('invalid_json') from None


class DTO(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True, revalidate_instances='always', protected_namespaces=())


class Money(DTO):
    currency: Literal['USD', 'CNY']
    scale: Literal[6]
    amount_units: Natural


class UsageUpperQuote(DTO):
    """Untrusted v2 quote data; arithmetic and authority live elsewhere."""
    revision: Id
    policy: Literal['bounded_usage_upper_v2'] = 'bounded_usage_upper_v2'
    model: Literal['deepseek-flash'] = MODEL
    declared_version: Literal['DeepSeek-V4.1-Flash'] = DECLARED_VERSION
    currency: Literal['CNY'] = 'CNY'
    scale: Annotated[StrictInt, Field(ge=6, le=6)] = 6
    peak_input_miss_units_per_million: Natural
    peak_output_units_per_million: Natural
    context_bound: Annotated[StrictInt, Field(ge=1048576, le=2147483647)]
    output_bound: Annotated[StrictInt, Field(ge=4096, le=4096)] = 4096
    local_guard: Natural
    price_document_digest: Digest
    model_document_digest: Digest
    completion_bound_basis_digest: Digest
    final_request_code_digest: Digest
    valid_until: Positive

    @model_validator(mode='after')
    def peak_rates(self):
        if self.peak_input_miss_units_per_million<=0 or self.peak_output_units_per_million<=0:
            raise ValueError('positive native peak rates required')
        return self


def money(currency, units):
    return Money(currency=currency, scale=6, amount_units=units)


class PriceQuote(DTO):
    revision: Id
    model: Literal['deepseek-flash'] = MODEL
    declared_version: Literal['DeepSeek-V4.1-Flash'] = DECLARED_VERSION
    policy: Literal['deepseek-bounded-upper-v1'] = POLICY
    currency: Literal['USD', 'CNY']
    scale: Literal[6]
    peak_input_miss_units_per_million: Natural
    peak_input_hit_units_per_million: Natural
    peak_output_units_per_million: Natural
    c_bound: Annotated[StrictInt, Field(ge=1048576, le=2147483647)]
    o_bound: Annotated[StrictInt, Field(ge=4096, le=393216)]
    output_basis: Literal['official_maximum', 'all_completion_request_cap_verified']
    rounding_guard: Natural
    price_document_digest: Digest
    model_document_digest: Digest
    bound_basis_digest: Digest
    expected_fingerprint_digest: Digest | None = None
    valid_until: Positive

    @model_validator(mode='after')
    def bounds(self):
        if (self.peak_input_miss_units_per_million <= 0 or self.peak_output_units_per_million <= 0
                or self.peak_input_hit_units_per_million > self.peak_input_miss_units_per_million
                or (self.output_basis == 'official_maximum' and self.o_bound != 393216)
                or (self.output_basis == 'all_completion_request_cap_verified' and self.o_bound != 4096)):
            raise ValueError('invalid price basis')
        return self

    def upper(self):
        units = (self.c_bound * self.peak_input_miss_units_per_million
                 + self.o_bound * self.peak_output_units_per_million + 999999) // 1000000 + self.rounding_guard
        if units > MAX_UNITS:
            raise ProviderFailure('money_overflow')
        return money(self.currency, units)


class BudgetBasisSnapshot(DTO):
    id: Id
    account_id: Id
    provider_binding_id: Id
    funding_epoch: Positive
    initial_prepaid: Money
    other_use_margin: Money
    cap: Money
    settled_actual: Money
    upper_booked: Money
    held: Money
    available_after_observed_consumption: Money
    price_revision: Id
    valid_until: Positive

    def admit(self, quote: PriceQuote, now: int):
        values = (self.initial_prepaid, self.other_use_margin, self.cap, self.settled_actual,
                  self.upper_booked, self.held, self.available_after_observed_consumption)
        if (type(now) is not int or self.valid_until <= now or quote.valid_until <= now
                or self.price_revision != quote.revision
                or any(v.currency != quote.currency or v.scale != quote.scale for v in values)
                or self.other_use_margin.amount_units > self.initial_prepaid.amount_units
                or self.cap.amount_units != self.initial_prepaid.amount_units - self.other_use_margin.amount_units):
            raise ProviderFailure('budget_unverified')
        upper = quote.upper()
        if (self.settled_actual.amount_units + self.upper_booked.amount_units + self.held.amount_units
                + upper.amount_units > self.cap.amount_units
                or self.available_after_observed_consumption.amount_units < upper.amount_units):
            raise ProviderFailure('budget_exhausted')
        return upper


class CallContext(DTO):
    principal_id: Id
    principal_epoch: Positive
    grant_id: Id
    grant_epoch: Positive
    owner_epoch: Positive
    acl_epoch: Positive
    research_id: Id
    input_revision: Positive
    input_digest: Digest
    task_id: Id
    attempt: Positive
    plan_id: Id


class EvidenceHandle(DTO):
    handle: Handle
    source_id: Id
    source_revision: Positive
    excerpt_id: Id
    title: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=300)]
    attribution: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=400)]
    extracted_digest: Digest
    extracted_text: Annotated[str, StringConstraints(strict=True, max_length=200000)] = Field(repr=False)
    start: Natural
    end: Natural
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
    display_permission: StrictBool
    may_send_to_provider: StrictBool

    @model_validator(mode='after')
    def exact_quote(self):
        if (self.display_permission is not True or self.may_send_to_provider is not True
                or '\r' in self.extracted_text or len(self.quote.split()) > 20
                or not self.start < self.end <= len(self.extracted_text)
                or self.extracted_text[self.start:self.end] != self.quote
                or digest(self.extracted_text.encode()) != self.extracted_digest):
            raise ValueError('invalid evidence handle')
        return self

    def outbound(self):
        return self.model_dump(exclude={'extracted_text', 'display_permission', 'may_send_to_provider'})


class EvidencePacket(DTO):
    context: CallContext
    handles: Annotated[tuple[EvidenceHandle, ...], Field(max_length=20)]

    @model_validator(mode='after')
    def unique(self):
        if len({v.handle for v in self.handles}) != len(self.handles):
            raise ValueError('duplicate evidence handle')
        return self

    def outbound(self):
        return {'handles': [h.outbound() for h in self.handles]}

    def binding_digest(self):
        return digest(canonical({'context': self.context.model_dump(), **self.outbound()}))


class CallPermit(DTO):
    id: Id
    account_id: Id
    provider_binding_id: Id
    funding_epoch: Positive
    dispatch_id: Id
    reservation_id: Id
    context: CallContext
    request_digest: Digest
    evidence_digest: Digest
    price_digest: Digest
    price_revision: Id
    budget_basis_digest: Digest
    gate_identity: tuple[StrictInt, StrictInt, StrictInt, StrictInt, StrictInt]
    expires_at: Positive


class DispatchApproval(DTO):
    """Produced only by the future server's current-permission admission callback."""
    permit: CallPermit
    budget: BudgetBasisSnapshot


class ConsumeReceipt(DTO):
    """Return from the caller's atomic one-time permit consumption, not a fee receipt."""
    permit: CallPermit
    approval_digest: Digest


class UsageObservation(DTO):
    prompt_tokens: Natural
    completion_tokens: Natural
    total_tokens: Natural
    prompt_cache_hit_tokens: Natural
    prompt_cache_miss_tokens: Natural
    cached_tokens: Natural | None
    reasoning_tokens: Natural | None

    @model_validator(mode='after')
    def coherent(self):
        if (self.prompt_tokens != self.prompt_cache_hit_tokens + self.prompt_cache_miss_tokens
                or self.total_tokens != self.prompt_tokens + self.completion_tokens
                or (self.cached_tokens is not None and self.cached_tokens != self.prompt_cache_hit_tokens)
                or (self.reasoning_tokens is not None and self.reasoning_tokens > self.completion_tokens)):
            raise ValueError('invalid usage')
        return self


def parse_usage(value, price):
    if type(value) is not dict:
        raise ProviderFailure('usage_unknown')
    try:
        raw = dict(value)
        has_details = 'prompt_tokens_details' in raw
        details = raw.pop('prompt_tokens_details', None)
        completion = raw.pop('completion_tokens_details', {})
        if ((has_details and (type(details) is not dict or not set(details) <= {'cached_tokens'}
                             or ('cached_tokens' in details and type(details['cached_tokens']) is not int)))
                or type(completion) is not dict or not set(completion) <= {'reasoning_tokens'}):
            raise ValueError('invalid usage')
        result = UsageObservation(**raw, cached_tokens=details.get('cached_tokens') if has_details else None,
                                  reasoning_tokens=completion.get('reasoning_tokens'))
        if result.prompt_tokens > price.c_bound or result.completion_tokens > price.o_bound:
            raise ProviderFailure('usage_over_bound')
        return result
    except ProviderFailure:
        raise
    except (ValueError, TypeError, KeyError):
        raise ProviderFailure('usage_unknown') from None


class CostObservation(DTO):
    reservation_id: Id
    dispatch_id: Id
    usage_ref: Digest | None
    kind: Literal['estimated_upper', 'unknown']
    actual_charge: None = None
    reserved_upper: Money
    booked_upper: Money | None
    usage_priced_estimate: Money | None
    policy: Literal['deepseek-bounded-upper-v1'] = POLICY
    price_revision: Id
    basis_digest: Digest


def usage_binding_digest(dispatch_id, request_digest, evidence_digest, price_revision, response_digest, usage):
    return digest(canonical({'dispatch_id': dispatch_id, 'request_digest': request_digest,
        'evidence_digest': evidence_digest, 'price_revision': price_revision, 'model': MODEL,
        'response_digest': response_digest, 'usage': usage.model_dump()}))


class ProviderObservation(DTO):
    execution_mode: Literal['offline_probe'] = 'offline_probe'
    context: CallContext
    dispatch_id: Id
    request_digest: Digest
    evidence_digest: Digest
    declared_version: Literal['DeepSeek-V4.1-Flash'] = DECLARED_VERSION
    response_digest: Digest | None
    response_model: Literal['deepseek-flash'] | None = None
    provider_ref: Annotated[str, StringConstraints(strict=True, pattern=r'^[a-zA-Z0-9._:-]{1,120}$')] | None
    fingerprint_digest: Digest | None
    usage: UsageObservation | None
    cost: CostObservation
    candidate: Annotated[str, StringConstraints(strict=True, max_length=32768)] | None = Field(repr=False)
    safe_code: Literal['ok', 'body_invalid', 'access_ended', 'response_unknown', 'usage_unknown', 'usage_over_bound', 'model_drift', 'deadline', 'response_limit', 'send_unknown']

    @model_validator(mode='after')
    def bound_observation(self):
        if self.cost.dispatch_id != self.dispatch_id:
            raise ValueError('observation dispatch mismatch')
        if self.usage is None:
            if (self.cost.kind != 'unknown' or self.cost.booked_upper is not None
                    or self.cost.usage_ref is not None or self.cost.usage_priced_estimate is not None):
                raise ValueError('unknown usage cannot be booked')
        elif (self.response_model != MODEL or self.cost.kind != 'estimated_upper'
                or self.cost.booked_upper != self.cost.reserved_upper
                or self.response_digest is None
                or self.cost.usage_ref != usage_binding_digest(self.dispatch_id, self.request_digest,
                    self.evidence_digest, self.cost.price_revision, self.response_digest, self.usage)
                or self.cost.usage_priced_estimate is None
                or self.cost.usage_priced_estimate.currency != self.cost.reserved_upper.currency
                or self.cost.usage_priced_estimate.amount_units > self.cost.reserved_upper.amount_units):
            raise ValueError('invalid upper observation')
        if self.safe_code == 'ok' and (self.candidate is None or self.usage is None):
            raise ValueError('successful body requires usage')
        return self


def cost_intent(permit, price, basis, usage, *, response_digest=None):
    upper = price.upper()
    estimate = None
    if usage is not None:
        total = (usage.prompt_cache_hit_tokens * price.peak_input_hit_units_per_million
                 + usage.prompt_cache_miss_tokens * price.peak_input_miss_units_per_million
                 + usage.completion_tokens * price.peak_output_units_per_million)
        units = (total + 999999) // 1000000
        if units > MAX_UNITS:
            raise ProviderFailure('money_overflow')
        estimate = money(price.currency, units)
    return CostObservation(reservation_id=permit.reservation_id, dispatch_id=permit.dispatch_id,
        usage_ref=usage_binding_digest(permit.dispatch_id, permit.request_digest, permit.evidence_digest,
            price.revision, response_digest, usage) if usage else None,
        kind='estimated_upper' if usage else 'unknown', reserved_upper=upper,
        booked_upper=upper if usage else None, usage_priced_estimate=estimate,
        price_revision=price.revision, basis_digest=digest(canonical(basis.model_dump())))


class OfflineTransportLimits(DTO):
    """Token validation limits, deliberately not a price or budget quote."""
    c_bound:Annotated[StrictInt,Field(ge=1048576,le=2147483647)]
    o_bound:Annotated[StrictInt,Field(ge=4096,le=4096)] = 4096
    expected_fingerprint_digest:Digest | None = None


class OfflineTransportReturn(DTO):
    """Received data only; ordinary construction grants no source authority."""
    execution_mode:Literal['offline_probe'] = 'offline_probe'
    context:CallContext
    dispatch_id:Id
    request_digest:Digest
    evidence_digest:Digest
    response_digest:Digest | None
    response_model:Literal['deepseek-flash'] | None
    provider_ref:Annotated[str,StringConstraints(strict=True,pattern=r'^[a-zA-Z0-9._:-]{1,120}$')] | None
    fingerprint_digest:Digest | None
    usage:UsageObservation | None
    candidate:Annotated[str,StringConstraints(strict=True,max_length=32768)] | None = Field(repr=False)
    safe_code:Literal['ok','body_invalid','access_ended','response_unknown','usage_unknown','usage_over_bound','model_drift','deadline','response_limit','send_unknown']
