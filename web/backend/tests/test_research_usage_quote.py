"""Pure synthetic v2 quote types: no price lookup, F, account or authority."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from research.provider_schemas import UsageUpperQuote,Money,PriceQuote,canonical,digest


def fields():
    return dict(revision=str(uuid4()),peak_input_miss_units_per_million=1,peak_output_units_per_million=2,
        context_bound=1048576,local_guard=1,price_document_digest='a'*64,model_document_digest='b'*64,
        completion_bound_basis_digest='c'*64,final_request_code_digest='d'*64,valid_until=2000000000)


def test_additive_quote_is_frozen_native_cny_data_without_arithmetic_or_authority():
    quote=UsageUpperQuote(**fields())
    assert quote.policy=='bounded_usage_upper_v2' and quote.currency=='CNY' and quote.scale==6
    assert quote.model=='deepseek-flash' and quote.declared_version=='DeepSeek-V4.1-Flash'
    assert quote.output_bound==4096
    assert UsageUpperQuote.model_validate(quote.model_dump())==quote
    assert len(digest(canonical(quote.model_dump())))==64
    assert Money(currency=quote.currency,scale=quote.scale,amount_units=1).amount_units==1
    for name in ('upper','F','reserve','consume','release','can_release','actual_charge','trusted','verified'):
        assert not hasattr(quote,name)
    with pytest.raises(ValidationError):quote.local_guard=2


@pytest.mark.parametrize('field,value',[
    ('policy','deepseek-bounded-upper-v1'),('currency','USD'),('currency','cny'),('scale',5),('scale',6.0),('scale',True),
    ('model','other'),('declared_version','other'),('context_bound',1048575),('context_bound',2147483648),
    ('context_bound',True),('context_bound',1048576.0),('output_bound',4097),('output_bound',4096.0),('output_bound',True),
    ('peak_input_miss_units_per_million',0),('peak_input_miss_units_per_million',True),('peak_input_miss_units_per_million',-1),
    ('peak_output_units_per_million',0),('peak_output_units_per_million',2.0),('peak_output_units_per_million',9223372036854775808),
    ('local_guard',-1),('local_guard',True),('local_guard',0.1),('local_guard',9223372036854775808),
    ('valid_until',0),('valid_until',True),('valid_until',2000000000.0),('revision','invalid'),
    ('price_document_digest','short'),('model_document_digest','g'*64),('completion_bound_basis_digest','A'*64),
    ('final_request_code_digest','0'*63),('verified',True),('can_release',True),('price',{}),('account_id',str(uuid4())),
])
def test_quote_rejects_wrong_policy_units_bounds_bool_and_self_verification(field,value):
    data=fields();data[field]=value
    with pytest.raises(ValidationError):UsageUpperQuote(**data)


def test_guard_zero_and_native_int63_endpoints_are_data_not_f_result():
    data=fields();data.update(local_guard=0,context_bound=2147483647,
        peak_input_miss_units_per_million=9223372036854775807,peak_output_units_per_million=9223372036854775807)
    quote=UsageUpperQuote(**data)
    assert quote.local_guard==0 and quote.context_bound==2147483647
    # The future sole arithmetic helper must reject an overflowing product;
    # accepting individually bounded DTO fields is not a computed fee proof.
    assert not hasattr(quote,'upper')


def test_v2_data_cannot_validate_as_legacy_v1_quote():
    with pytest.raises(ValidationError):PriceQuote.model_validate(UsageUpperQuote(**fields()).model_dump())
