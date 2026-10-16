"""Synthetic quote arithmetic only; no funds, authority, database or network."""
from uuid import uuid4

import pytest

from web.backend.research.provider_schemas import Money, UsageObservation, UsageUpperQuote, MAX_UNITS
from web.backend.research import usage_upper as math


def quote(**changes):
    fields=dict(revision=str(uuid4()),peak_input_miss_units_per_million=7,
        peak_output_units_per_million=11,context_bound=1048576,local_guard=3,
        price_document_digest='a'*64,model_document_digest='b'*64,
        completion_bound_basis_digest='c'*64,final_request_code_digest='d'*64,valid_until=130)
    fields.update(changes)
    return UsageUpperQuote(**fields)


def usage(prompt=100,output=20,hit=0,reasoning=None):
    return UsageObservation(prompt_tokens=prompt,completion_tokens=output,total_tokens=prompt+output,
        prompt_cache_hit_tokens=hit,prompt_cache_miss_tokens=prompt-hit,cached_tokens=None,
        reasoning_tokens=reasoning)


def reserved(q):
    return math.reserve_bound(q,dispatch_id=str(uuid4()),request_digest='e'*64,now=100)


def observed(q,r,u):
    return math.observed_bound(q,r,u,dispatch_id=r.dispatch_id,request_digest=r.request_digest)


def test_low_full_and_zero_usage_use_one_f_and_keep_guard():
    q=quote();r=reserved(q)
    assert r.reserved_upper==Money(currency='CNY',scale=6,amount_units=11)
    low=observed(q,r,usage())
    assert low.observed_upper.amount_units==4
    assert observed(q,r,usage(0,0)).observed_upper.amount_units==3
    assert observed(q,r,usage(q.context_bound,4096)).observed_upper==r.reserved_upper
    assert set(low.model_dump())=={'policy','quote_revision','quote_digest','dispatch_id','request_digest',
        'reserved_upper','observed_upper','usage_binding_digest'}
    for forbidden in ('release','can_release','actual','trusted','admitted_at'):
        assert all(forbidden not in name for name in low.model_fields)


def test_cache_hit_and_reasoning_do_not_discount_or_double_charge():
    q=quote(peak_input_miss_units_per_million=1000000,peak_output_units_per_million=2000000)
    r=reserved(q)
    miss=observed(q,r,usage(100,20))
    hit=observed(q,r,usage(100,20,100,10))
    assert miss.observed_upper==hit.observed_upper
    assert hit.observed_upper.amount_units==143
    assert miss.usage_binding_digest!=hit.usage_binding_digest


@pytest.mark.parametrize('input_rate,output_rate,prompt,output,expected',[
    (1,1,1,0,1),(1,1,999999,0,1),(1,1,1000000,0,1),
    (1,1,1000001,0,2),(500000,500000,1,1,1),(500001,500000,1,1,2),
])
def test_ceil_is_on_combined_native_integer_total(input_rate,output_rate,prompt,output,expected):
    q=quote(peak_input_miss_units_per_million=input_rate,peak_output_units_per_million=output_rate,local_guard=0)
    result=observed(q,reserved(q),usage(prompt,output))
    assert result.observed_upper.amount_units==expected


@pytest.mark.parametrize('clock',[True,100.0,-1,'100',None])
def test_invalid_clock_never_produces_reserve_fact(clock):
    with pytest.raises(math.UpperMathError):math.reserve_bound(quote(),dispatch_id=str(uuid4()),request_digest='e'*64,now=clock)


@pytest.mark.parametrize('expires',[99,100,161,2000000000])
def test_expired_or_non_short_quote_cannot_start_new_reserve(expires):
    with pytest.raises(math.UpperMathError,match='quote_not_current'):reserved(quote(valid_until=expires))


def test_observation_uses_original_quote_after_expiry_without_admitted_at_parameter():
    q=quote(valid_until=101);r=reserved(q)
    assert observed(q,r,usage()).quote_digest==r.quote_digest
    with pytest.raises(math.UpperMathError):math.reserve_bound(q,dispatch_id=r.dispatch_id,request_digest=r.request_digest,now=102)
    with pytest.raises(TypeError):math.observed_bound(q,r,usage(),dispatch_id=r.dispatch_id,request_digest=r.request_digest,admitted_at=100)


@pytest.mark.parametrize('field,value',[
    ('currency','USD'),('scale',True),('policy','deepseek-bounded-upper-v1'),
    ('model','deepseek-v4-pro'),('context_bound',1048575),('context_bound',True),
    ('output_bound',4097),('peak_input_miss_units_per_million',True),
    ('peak_output_units_per_million',1.5),('local_guard',-1),
])
def test_model_construct_and_copy_cannot_bypass_quote_revalidation(field,value):
    q=quote().model_copy(update={field:value})
    with pytest.raises(math.UpperMathError,match='invalid_quote'):reserved(q)


def test_dict_or_v1_quote_shape_is_not_an_additive_v2_port():
    with pytest.raises(math.UpperMathError):reserved(quote().model_dump())


@pytest.mark.parametrize('field,value',[
    ('prompt_tokens',True),('completion_tokens',1.0),('total_tokens',-1),
    ('prompt_cache_hit_tokens',101),('prompt_cache_miss_tokens',1),
    ('cached_tokens',1),('reasoning_tokens',21),
])
def test_invalid_usage_never_produces_observed_result(field,value):
    q=quote();r=reserved(q);bad=usage().model_copy(update={field:value})
    with pytest.raises(math.UpperMathError):observed(q,r,bad)


@pytest.mark.parametrize('u',[None,{},False])
def test_missing_usage_does_not_produce_a_zero_or_releasable_bound(u):
    q=quote()
    with pytest.raises(math.UpperMathError):observed(q,reserved(q),u)


@pytest.mark.parametrize('prompt,output',[(1048577,0),(0,4097)])
def test_consistent_usage_over_token_cap_is_still_rejected(prompt,output):
    q=quote()
    with pytest.raises(math.UpperMathError,match='usage_out_of_bound'):observed(q,reserved(q),usage(prompt,output))


@pytest.mark.parametrize('field,value',[
    ('quote_revision',str(uuid4())),('quote_digest','f'*64),('dispatch_id',str(uuid4())),
    ('request_digest','f'*64),('reserved_upper',Money(currency='USD',scale=6,amount_units=11)),
    ('reserved_upper',Money(currency='CNY',scale=6,amount_units=0)),
    ('policy','bounded_full_u_v1'),
])
def test_reservation_and_dispatch_quote_binding_must_match(field,value):
    q=quote();r=reserved(q);bad=r.model_copy(update={field:value})
    with pytest.raises(math.UpperMathError):math.observed_bound(q,bad,usage(),dispatch_id=r.dispatch_id,request_digest=r.request_digest)


def test_quote_rate_or_expiry_change_is_a_different_f_not_a_refresh():
    q=quote();r=reserved(q)
    for changed in (q.model_copy(update={'valid_until':131}),q.model_copy(update={'local_guard':4}),
                    q.model_copy(update={'peak_output_units_per_million':12})):
        with pytest.raises(math.UpperMathError,match='binding_mismatch'):observed(changed,r,usage())


def test_overflow_never_returns_partial_money_or_clips_to_reserve():
    with pytest.raises(math.UpperMathError,match='money_overflow'):reserved(quote(peak_input_miss_units_per_million=MAX_UNITS))
    with pytest.raises(math.UpperMathError,match='money_overflow'):reserved(quote(local_guard=MAX_UNITS))


def test_unexpected_observed_above_reserved_is_not_min_clipped(monkeypatch):
    q=quote();r=reserved(q);original=math._f
    def anomalous(quote,inputs,outputs):
        if inputs==100:return Money(currency='CNY',scale=6,amount_units=r.reserved_upper.amount_units+1)
        return original(quote,inputs,outputs)
    monkeypatch.setattr(math,'_f',anomalous)
    with pytest.raises(math.UpperMathError,match='observed_exceeds_reserved'):observed(q,r,usage())


def test_real_legacy_price_quote_type_cannot_enter_v2_math():
    from tests.test_research_provider_adapter import quote as legacy_quote
    with pytest.raises(math.UpperMathError,match='v2_typed_quote_required'):reserved(legacy_quote())


def test_incomplete_constructed_usage_is_not_completed_with_zeroes():
    data=usage().model_dump();data.pop('completion_tokens')
    incomplete=UsageObservation.model_construct(**data)
    q=quote()
    with pytest.raises(math.UpperMathError,match='invalid_observation'):observed(q,reserved(q),incomplete)


def test_same_counts_in_another_dispatch_have_a_distinct_usage_binding_digest():
    q=quote();first=reserved(q);second=reserved(q)
    assert observed(q,first,usage()).usage_binding_digest!=observed(q,second,usage()).usage_binding_digest
    with pytest.raises(math.UpperMathError):math.observed_bound(q,first,usage(),dispatch_id=second.dispatch_id,request_digest=first.request_digest)


def test_quote_ttl_boundary_and_frozen_fact_revalidation():
    q=quote(valid_until=160);r=reserved(q)
    assert r.reserved_upper.amount_units==11
    with pytest.raises(ValueError):r.quote_digest='0'*64
    bad=r.model_copy(update={'reserved_upper':Money.model_construct(currency='CNY',scale=6,amount_units=True)})
    with pytest.raises(math.UpperMathError):observed(q,bad,usage())


@pytest.mark.parametrize('field,value',[('scale',6.0),('amount_units',11.0),('amount_units',-1)])
def test_forged_native_money_cannot_hide_float_scale_or_amount(field,value):
    q=quote();r=reserved(q)
    bad=r.model_copy(update={'reserved_upper':r.reserved_upper.model_copy(update={field:value})})
    with pytest.raises(math.UpperMathError):observed(q,bad,usage())


def test_incomplete_constructed_money_is_a_safe_error_not_an_observed_fact():
    q=quote();r=reserved(q)
    bad=r.model_copy(update={'reserved_upper':Money.model_construct(currency='CNY',amount_units=11)})
    with pytest.raises(math.UpperMathError,match='invalid_observation'):observed(q,bad,usage())
