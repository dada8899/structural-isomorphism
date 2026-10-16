"""Pure bounded_usage_upper_v2 arithmetic, never admission or ledger authority.

Only Core may establish a real dispatch, a fresh approved native quote and a
complete trusted final usage observation persisted for that dispatch. These
frozen output DTOs record mathematical consistency, not those database facts.
No release/actual/trusted flags are returned. Core alone performs atomic ledger
changes. In particular, an observation may use its originally bound quote after
expiry; this module takes no client-supplied admitted_at to certify legality.
Old fixture/v1 quotes and historical amounts never enter this v2 calculation.
Ceil/guard and the at-most-60-second remaining quote window are local policy,
not provider invoice rounding or proof of an official completion billing limit.
"""
from __future__ import annotations

from typing import Literal

from .provider_schemas import (
    DTO, Digest, Id, MAX_UNITS, Money, UsageObservation, UsageUpperQuote,
    canonical, digest,
)

MAX_QUOTE_REMAINING_SECONDS = 60


class UpperMathError(ValueError):
    """Fixed error codes only; no partial observed or releasable result."""


class ReservedUpperMath(DTO):
    policy: Literal['bounded_usage_upper_v2'] = 'bounded_usage_upper_v2'
    quote_revision: Id
    quote_digest: Digest
    dispatch_id: Id
    request_digest: Digest
    reserved_upper: Money


class ObservedUpperMath(ReservedUpperMath):
    observed_upper: Money
    usage_binding_digest: Digest


def _quote(value):
    if type(value) is not UsageUpperQuote:
        raise UpperMathError('v2_typed_quote_required')
    try:
        return UsageUpperQuote.model_validate(value)
    except ValueError:
        raise UpperMathError('invalid_quote') from None


def _f(quote, inputs, outputs):
    if (type(inputs) is not int or type(outputs) is not int
            or not 0 <= inputs <= quote.context_bound or not 0 <= outputs <= quote.output_bound):
        raise UpperMathError('usage_out_of_bound')
    # Bounds in the reviewed DTO keep both products finite and small Python
    # integers. No intermediate float or monetary rounding is permitted.
    numerator = (inputs * quote.peak_input_miss_units_per_million
                 + outputs * quote.peak_output_units_per_million)
    units = (numerator + 999999) // 1000000 + quote.local_guard
    if not 0 <= units <= MAX_UNITS:
        raise UpperMathError('money_overflow')
    return Money(currency=quote.currency, scale=quote.scale, amount_units=units)


def reserve_bound(quote: UsageUpperQuote, *, dispatch_id: str, request_digest: str, now: int) -> ReservedUpperMath:
    """Calculate U for a current quote; `now` is Core's clock, not admission proof."""
    quote = _quote(quote)
    if type(now) is not int or now < 0:
        raise UpperMathError('invalid_clock')
    if not 0 < quote.valid_until - now <= MAX_QUOTE_REMAINING_SECONDS:
        raise UpperMathError('quote_not_current')
    try:
        return ReservedUpperMath(quote_revision=quote.revision,
            quote_digest=digest(canonical(quote.model_dump())), dispatch_id=dispatch_id,
            request_digest=request_digest, reserved_upper=_f(quote, quote.context_bound, quote.output_bound))
    except UpperMathError:
        raise
    except ValueError:
        raise UpperMathError('invalid_binding') from None


def observed_bound(quote: UsageUpperQuote, reserved: ReservedUpperMath, usage: UsageObservation,
                   *, dispatch_id: str, request_digest: str) -> ObservedUpperMath:
    """Compute Uobs from the same frozen F; never refresh a late quote or book money.

    Core must check real original admission and trusted persisted final usage
    before calling. Syntactically matching digests/DTOs do not prove either.
    """
    quote = _quote(quote)
    if type(reserved) is not ReservedUpperMath or type(usage) is not UsageObservation:
        raise UpperMathError('typed_observation_required')
    original_money = getattr(reserved, 'reserved_upper', None)
    if (type(original_money) is not Money or type(getattr(original_money, 'scale', None)) is not int
            or type(getattr(original_money, 'amount_units', None)) is not int):
        raise UpperMathError('invalid_observation')
    try:
        reserved = ReservedUpperMath.model_validate(reserved)
        usage = UsageObservation.model_validate(usage)
    except ValueError:
        raise UpperMathError('invalid_observation') from None
    quote_digest = digest(canonical(quote.model_dump()))
    if (reserved.quote_revision != quote.revision or reserved.quote_digest != quote_digest
            or reserved.dispatch_id != dispatch_id or reserved.request_digest != request_digest
            or reserved.reserved_upper != _f(quote, quote.context_bound, quote.output_bound)):
        raise UpperMathError('reservation_binding_mismatch')
    observed = _f(quote, usage.prompt_tokens, usage.completion_tokens)
    if observed.amount_units > reserved.reserved_upper.amount_units:
        raise UpperMathError('observed_exceeds_reserved')
    return ObservedUpperMath(**reserved.model_dump(), observed_upper=observed,
        usage_binding_digest=digest(canonical({'usage': usage.model_dump(), 'dispatch_id': dispatch_id,
            'request_digest': request_digest, 'quote_digest': quote_digest})))
