"""Pure owner-declared finance data. No execution authority, I/O or persistence."""
from datetime import timedelta
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import json
import re
from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator, model_serializer, field_validator

from .financial_input_schemas import (FrozenData, FinancialRegistryRefV2,
    OwnerFinancialRegistryV2, RegisteredSourceV2, RegisteredObservationV2,
    RegisteredFXV2, UUID4, Digest)
from .financial_policy import (POLICY, YEARS, FinancialError, FinancialResourceLimit,
    canonical, digest, number, MAX_ABS, arithmetic_context, Meter)
from .financial_schemas import FinancialRequest, Period, day, label, text

OPERATION_LIMIT = 65536
PURE_LIMIT = 110592
SNAPSHOT_LIMIT = 131072
PUBLIC_LIMIT = 524288
PROFILE = 'financial-scenario-owner-v2'
QUALIFICATIONS = ('owner-supplied declarations are unverified',
    'all projected values conditional; no calibrated probabilities',
    'no historical operating margin or profit backfill',
    'missing net profit bridge remains missing',
    'cooperative limits only; no OS isolation or source verification')
Label = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,31}$')]
V = Annotated[StrictInt, Field(ge=1, le=2147483647)]
Year = Annotated[StrictInt, Field(ge=2026, le=2031)]
Currency = Literal['CNY', 'USD']


def bounded(value, cap):
    """Bound primitive shape before serialization; never trim any evidence."""
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop(); count += 1
        if count > 20000 or depth > 32:
            raise FinancialResourceLimit('JSON shape limit')
        if type(item) is dict:
            if any(type(k) is not str for k in item): raise FinancialError('JSON keys required')
            stack.extend((v, depth + 1) for pair in item.items() for v in pair)
        elif type(item) in (list,tuple):
            stack.extend((v, depth + 1) for v in item)
        elif item is not None and type(item) not in (str, int, bool):
            raise FinancialError('strict JSON primitive required')
        elif type(item) is str and len(item.encode('utf-8')) > cap:
            raise FinancialResourceLimit('JSON byte limit')
        elif type(item) is int and item.bit_length() > 64:
            raise FinancialResourceLimit('JSON integer limit')
    raw = canonical(value)
    if len(raw.encode('utf-8')) > cap: raise FinancialResourceLimit('JSON byte limit')
    return raw


class ComputedDecimalText(str):
    """Computed Decimal50 domain; deliberately independent of input number()."""
    def __new__(cls, value):
        if type(value) is not str or len(value) > 256 or re.fullmatch(
                r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?', value) is None:
            raise FinancialError('computed decimal text required')
        try: d = Decimal(value)
        except InvalidOperation: raise FinancialError('computed decimal required') from None
        if (not d.is_finite() or d.copy_abs() > MAX_ABS or (not d and value != '0')
                or d and (len(d.as_tuple().digits) > 50 or not -249 <= d.as_tuple().exponent <= 18
                          or not -249 <= d.adjusted() <= 18 or str(d) != value)):
            raise FinancialError('computed decimal outside policy')
        return str.__new__(cls, value)


def computed(value):
    return str(ComputedDecimalText('0' if value == 0 else str(value)))


def displayed(value):
    if value is None: return None
    with arithmetic_context():
        result = Decimal(value).quantize(Decimal('.000001'), rounding=ROUND_HALF_EVEN)
    return format(Decimal(0) if result == 0 else result, '.6f')


class PeriodV2(FrozenData):
    start: str
    end: str
    grain: Literal['annual', 'interim', 'remaining']
    @model_validator(mode='after')
    def check(self):
        Period(self.start, self.end, self.grain); return self


class ParameterV2(FrozenData):
    id: Label
    value: str | None
    unit: Literal['unit', 'thousand', 'million', 'billion', 'ratio', 'fx']
    currency: Currency | None
    period: PeriodV2
    rationale: str
    source_refs: Annotated[tuple[UUID4, ...], Field(max_length=16)]
    anchor_observation_id: UUID4 | None
    independent: bool


class AnnualV2(FrozenData):
    year: Year
    parameter: ParameterV2


class CostV2(FrozenData):
    id: Label
    kind: Literal['operating_cost','operating_expense','shared_cost','depreciation','sbc','operating_adjustment']
    label: str
    mode: Literal['amount','revenue_ratio']
    coverage: Annotated[tuple[str, ...], Field(max_length=5)]
    coverage_basis: str
    values: Annotated[tuple[AnnualV2, ...], Field(max_length=6)]


class ExclusionV2(FrozenData):
    tag: str
    rationale: str
    source_refs: Annotated[tuple[UUID4, ...], Field(max_length=16)]


class AllocationV2(FrozenData):
    category_id: Label
    mode: Literal['amount','share']
    values: Annotated[tuple[AnnualV2, ...], Field(max_length=6)]


class FutureFXV2(FrozenData):
    from_currency: Currency
    to_currency: Currency
    parameter: ParameterV2


class ScenarioV2(FrozenData):
    id: Label
    label: str
    accounting_basis: str
    remaining_revenue: ParameterV2
    growth: Annotated[tuple[AnnualV2, ...], Field(max_length=5)]
    costs: Annotated[tuple[CostV2, ...], Field(max_length=16)]
    exclusions: Annotated[tuple[ExclusionV2, ...], Field(max_length=5)]
    allocations: Annotated[tuple[AllocationV2, ...], Field(max_length=8)]
    future_fx: Annotated[tuple[FutureFXV2, ...], Field(max_length=16)]


class CategoryV2(FrozenData):
    id: Label
    label: str
    definition: str
    dimension: Literal['monetization']
    excludes: Annotated[tuple[Label, ...], Field(max_length=8)]
    kind: Literal['segment','unallocated']


class SensitivityV2(FrozenData):
    scenario_id: Label
    parameter_id: Label
    points: Annotated[tuple[str, ...], Field(max_length=21)]


class RegistryFXChoiceV2(FrozenData):
    kind: Literal['registry']
    observation_id: UUID4
    fx_id: UUID4


class DerivedFXChoiceV2(FrozenData):
    kind: Literal['derived']
    observation_id: UUID4
    derivation_id: Label


class FXPointV1(FrozenData):
    date: str
    value: str | None
    @model_validator(mode='after')
    def check(self):
        day(self.date)
        if self.value is not None and number(self.value) <= 0: raise FinancialError('positive FX required')
        return self


class DerivedFXInputV1(FrozenData):
    id: Label
    source_id: UUID4
    claimed_source_version: str
    claimed_accessed_on: str
    locator: str
    from_currency: Currency
    to_currency: Currency
    period: PeriodV2
    points: Annotated[tuple[FXPointV1, ...], Field(min_length=1, max_length=129)]
    declared_valid_count: Annotated[StrictInt, Field(ge=0, le=129)]
    declared_nd_count: Annotated[StrictInt, Field(ge=0, le=129)]
    declared_values_sha256: Digest
    @model_validator(mode='after')
    def check(self):
        text(self.claimed_source_version,240); text(self.locator,240); day(self.claimed_accessed_on)
        start, end = day(self.period.start), day(self.period.end)
        if self.from_currency == self.to_currency or (end-start).days > 182:
            raise FinancialError('bounded FX period and direction required')
        dates=[]
        while start <= end:
            if start.weekday() < 5: dates.append(start.isoformat())
            if len(dates)>129: raise FinancialResourceLimit('FX date limit')
            start += timedelta(days=1)
        values=[p.value for p in self.points if p.value is not None]
        if ([p.date for p in self.points] != dates or not values
                or self.declared_valid_count != len(values)
                or self.declared_nd_count != len(self.points)-len(values)
                or digest(values) != self.declared_values_sha256):
            raise FinancialError('FX dates counts or values digest differ')
        return self


class FinancialRequestV2(FrozenData):
    entity_scope: str
    information_cutoff: str
    interim_revenue_ref: UUID4
    baseline_selection_reason: str
    historical_context_refs: Annotated[tuple[UUID4, ...], Field(max_length=16)]
    historical_fx_choices: Annotated[tuple[Annotated[RegistryFXChoiceV2 | DerivedFXChoiceV2, Field(discriminator='kind')], ...], Field(max_length=16)]
    target_currency: Currency
    categories: Annotated[tuple[CategoryV2, ...], Field(max_length=8)]
    scenarios: Annotated[tuple[ScenarioV2, ...], Field(min_length=1, max_length=3)]
    sensitivity: SensitivityV2 | None
    policy_revision: Literal['financial-scenario-v1-candidate']
    derived_fx_inputs: Annotated[tuple[DerivedFXInputV1, ...], Field(max_length=1)]
    def data(self): return self.model_dump(mode='json')
    def legacy(self):
        value=self.data(); value.pop('derived_fx_inputs')
        value['historical_fx_choices']=[{'observation_id':c.observation_id,'fx_id':c.fx_id}
            for c in self.historical_fx_choices if type(c) is RegistryFXChoiceV2]
        return FinancialRequest.parse(value)
    @model_validator(mode='after')
    def check(self):
        self.legacy()
        if len({v.observation_id for v in self.historical_fx_choices})!=len(self.historical_fx_choices):
            raise FinancialError('duplicate FX choice')
        selected={v.derivation_id for v in self.historical_fx_choices if type(v) is DerivedFXChoiceV2}
        if selected!={v.id for v in self.derived_fx_inputs}: raise FinancialError('unused or missing derivation')
        if self.interim_revenue_ref in self.historical_context_refs: raise FinancialError('duplicate baseline context')
        return self


class FinancialCalculationDataV2(FrozenData):
    input_revision: V
    expected_research_version: Annotated[StrictInt, Field(ge=1, le=2147483646)]
    registry_ref: FinancialRegistryRefV2
    request: FinancialRequestV2


class FinancialCalculationEnvelopeV2(FrozenData):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['financial-result-v2']
    data: FinancialCalculationDataV2
    def data_dict(self): return self.model_dump(mode='json')


def decode_financial_calculation(raw: bytes) -> FinancialCalculationEnvelopeV2:
    if type(raw) is not bytes or len(raw)>OPERATION_LIMIT: raise FinancialResourceLimit('operation byte limit')
    def pairs(items):
        out={}
        for k,v in items:
            if k in out: raise FinancialError('duplicate JSON key')
            out[k]=v
        return out
    def reject(_): raise FinancialError('strict JSON number required')
    try:
        data=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_float=reject,parse_constant=reject,
                        parse_int=lambda v:int(v) if len(v.lstrip('-'))<=20 else reject(v))
        return FinancialCalculationEnvelopeV2.model_validate_json(bounded(data,OPERATION_LIMIT))
    except (ValueError,UnicodeError,RecursionError,OverflowError):
        raise FinancialError('invalid financial calculation') from None


class InputStatusV2(FrozenData):
    kind: Literal['owner_supplied']
    verification: Literal['unverified']
    original_available: Literal[False]
    system_verified: Literal[False]
    qualification: Literal['conditional_on_owner_supplied_data']
    @model_validator(mode='before')
    @classmethod
    def flags(cls,value):
        if type(value) is dict and any(value.get(k) is not False for k in ('original_available','system_verified')):
            raise FinancialError('literal false required')
        return value


INPUT_STATUS={'kind':'owner_supplied','verification':'unverified','original_available':False,
    'system_verified':False,'qualification':'conditional_on_owner_supplied_data'}


class ProvenanceV2(FrozenData):
    id: Digest
    observation_refs: Annotated[tuple[UUID4, ...], Field(max_length=64)]
    parameter_refs: Annotated[tuple[str, ...], Field(max_length=498)]
    derivation_refs: Annotated[tuple[Label, ...], Field(max_length=1)]
    historical_fx_refs: Annotated[tuple[UUID4, ...], Field(max_length=16)]
    source_refs: Annotated[tuple[UUID4, ...], Field(max_length=16)]
    @model_validator(mode='after')
    def check(self):
        data=self.model_dump(mode='json'); ref=data.pop('id')
        if ref!=digest(data) or any(v!=sorted(set(v)) for v in data.values()):
            raise FinancialError('invalid interned provenance')
        return self


def valid_reason(value):
    simple={'observation_missing','observation_conflicted','historical_fx_missing','historical_fx_conflicted',
        'historical_value_missing','future_fx_assumption_missing','amount_missing','rate_or_base_missing',
        'segment_not_allocated','share_input_missing','zero_revenue_denominator','no_net_profit_projection_bridge'}
    if value in simple: return value
    if value.startswith(('parameter_missing:','cost_line_missing:')):
        label(value.split(':',1)[1]); return value
    if value.startswith('incomplete_cost_coverage:'):
        from .financial_policy import COST_TAGS
        tags=value.split(':',1)[1].split(',')
        if tags and tags==sorted(set(tags)) and not set(tags)-COST_TAGS:return value
    raise FinancialError('unknown financial gap code')


class CellV2(FrozenData):
    raw_value: str | None
    display: str | None
    currency: Currency | None
    unit: Literal['million','ratio']
    basis: Literal['disclosed','media_estimate','missing','conflicted','scenario_assumption','derived_conditional']
    reasons: Annotated[tuple[str, ...], Field(max_length=32)]
    provenance_ref: Digest
    @model_validator(mode='after')
    def check(self):
        if self.raw_value is not None: ComputedDecimalText(self.raw_value)
        if self.display != displayed(self.raw_value): raise FinancialError('display does not match raw value')
        if (self.raw_value is None)!=(self.basis in ('missing','conflicted')):
            raise FinancialError('cell null basis mismatch')
        if not self.raw_value and not self.reasons: raise FinancialError('missing cell reason required')
        if self.unit=='ratio' and self.currency is not None: raise FinancialError('ratio currency')
        if self.unit=='million' and self.currency is None: raise FinancialError('amount currency')
        for v in self.reasons: valid_reason(v)
        return self


class DerivedFXEvidenceV1(FrozenData):
    input: DerivedFXInputV1
    input_digest: Digest
    algorithm: Literal['arithmetic_mean_nonmissing_v1']
    calculation_precision: Annotated[StrictInt,Field(ge=50,le=50)]
    rounding: Literal['HALF_EVEN']
    decimal_places: Annotated[StrictInt,Field(ge=10,le=10)]
    valid_count: Annotated[StrictInt,Field(ge=1,le=129)]
    nd_count: Annotated[StrictInt,Field(ge=0,le=129)]
    values_sha256: Digest
    value: str
    verification_scope: Literal['arithmetic_only']
    source_verification: Literal['unverified']
    basis: Literal['derived_conditional']
    calculation_status: Literal['recomputed_from_supplied_series']
    @model_validator(mode='after')
    def check(self):
        if (self.input_digest!=digest(self.input.model_dump(mode='json'))
                or self.values_sha256!=self.input.declared_values_sha256
                or self.valid_count!=self.input.declared_valid_count or self.nd_count!=self.input.declared_nd_count
                or re.fullmatch(r'(?:0|[1-9][0-9]*)\.[0-9]{10}',self.value) is None
                or not 0<Decimal(self.value)<=MAX_ABS): raise FinancialError('invalid derived FX evidence')
        return self


class HistoricalCellV2(FrozenData):
    observation_ref: UUID4
    target_value: CellV2


class CostCellV2(FrozenData):
    id: Label
    kind: str
    coverage: tuple[str,...]
    coverage_basis: str
    value: CellV2


class CompositionRowV2(FrozenData):
    category_id: Label
    amount: CellV2
    share: CellV2
    included_in_allocated_sum: bool


class CompositionV2(FrozenData):
    coverage: Literal['group_missing','undefined_zero_revenue','unallocated_only','partial','declared_scenario_partition_complete_not_audited']
    rows: Annotated[tuple[CompositionRowV2,...],Field(max_length=8)]
    rounding_delta_million: str | None
    scope: Literal['unallocated includes all unmodelled revenue; missing named categories are not extra summands']


class MetricsV2(FrozenData):
    revenue: CellV2
    operating_profit: CellV2
    net_profit: CellV2
    cost_bridge: Annotated[tuple[CostCellV2,...],Field(max_length=16)]
    composition: CompositionV2


class SameTargetV2(FrozenData):
    same_as: Literal['target']


class YearResultV2(FrozenData):
    year: Year
    period: PeriodV2
    basis: Literal['bridge_estimate','conditional_scenario']
    native_currency: Currency
    target_currency: Currency
    native: MetricsV2 | SameTargetV2
    target: MetricsV2


class BridgeV2(FrozenData):
    interim: CellV2
    remaining_assumption: CellV2
    target_interim: CellV2
    target_remaining: CellV2
    qualification: Literal['2026E, never annualized historical actual']


class ScenarioResultV2(FrozenData):
    id: Label
    label: str
    accounting_basis: str
    bridge: BridgeV2
    years: Annotated[tuple[YearResultV2,...],Field(min_length=6,max_length=6)]
    parameter_basis: Literal['scenario_assumption']
    exclusions: tuple[ExclusionV2,...]
    qualification: Literal['source_linked_conditional_unreviewed','mechanical_assumption_demonstration_not_validated_forecast']


class SensitivityResultV2(FrozenData):
    parameter_ref: str
    point: str
    case_input_digest: Digest
    years: tuple[Year,...]
    target_revenue: tuple[str | None,...]
    target_operating_profit: tuple[str | None,...]


class FinancialSnapshotV2(FrozenData):
    snapshot_schema: Literal['financial-snapshot-owner-v2']
    policy_revision: Literal['financial-scenario-v1-candidate']
    request_digest: Digest
    parameters_digest: Digest
    evaluation_input_digest: Digest
    registry_ref: FinancialRegistryRefV2
    target_currency: Currency
    amount_unit: Literal['million']
    display_quantization: Literal['6 decimals HALF_EVEN']
    calculation_precision: Annotated[StrictInt,Field(ge=50,le=50)]
    categories: tuple[CategoryV2,...]
    historical_context: Annotated[tuple[HistoricalCellV2,...],Field(max_length=17)]
    scenarios: Annotated[tuple[ScenarioResultV2,...],Field(min_length=1,max_length=3)]
    sensitivity: Annotated[tuple[SensitivityResultV2,...],Field(max_length=21)]
    derived_fx_evidence: Annotated[tuple[DerivedFXEvidenceV1,...],Field(max_length=1)]
    provenance_table: Annotated[tuple[ProvenanceV2,...],Field(max_length=512)]
    operations_used: Annotated[StrictInt,Field(ge=0,le=5000)]
    qualifications: tuple[str,...]
    decimal50_inexact_encountered: bool
    input_status: InputStatusV2
    def data(self): return self.model_dump(mode='json')
    @property
    def digest(self): return digest(self.data())


def input_binding(envelope,registry):
    if type(envelope) is not FinancialCalculationEnvelopeV2 or type(registry) is not OwnerFinancialRegistryV2:
        raise FinancialError('exact owner registry and full Envelope required')
    envelope=decode_financial_calculation(bounded(envelope.data_dict(),OPERATION_LIMIT).encode('utf-8'))
    registry=OwnerFinancialRegistryV2.model_validate_json(bounded(registry.model_dump(mode='json'),SNAPSHOT_LIMIT))
    operation=envelope.data_dict(); original=registry.model_dump(mode='json')
    ref=envelope.data.registry_ref
    if ((ref.id,ref.revision,ref.digest)!=(registry.identity.id,registry.identity.revision,digest(original))
            or envelope.data.input_revision!=registry.binding.input_revision
            or envelope.data.expected_research_version<registry.binding.research_version_after):
        raise FinancialError('pure input binding mismatch')
    request=operation['data']['request']
    bounded({'request':request,'registry':original},SNAPSHOT_LIMIT)
    return envelope,registry,{'request_digest':digest(operation),'parameters_digest':digest(request),
        'evaluation_input_digest':digest({'execution_profile':PROFILE,'request':request,'registry':original})}


def source_closure(registry,refs):
    sources={r.id:r for r in registry.records if type(r) is RegisteredSourceV2}
    found=set(); pending=list(refs)
    while pending:
        ref=pending.pop()
        if ref not in sources: raise FinancialError('source outside owner registry')
        if ref not in found: found.add(ref); pending.extend(sources[ref].source_chain)
    return sorted(found)


def provenance_sources(registry,request,data):
    observations={r.id:r for r in registry.records if type(r) is RegisteredObservationV2}
    rates={r.id:r for r in registry.records if type(r) is RegisteredFXV2}
    params={s.id+':'+p.id:p for s in request.legacy().scenarios for p in s.parameters()}
    derived={v.id:v for v in request.derived_fx_inputs}
    refs=[]
    for name,items in (('observation_refs',observations),('historical_fx_refs',rates),('parameter_refs',params)):
        for ref in data[name]:
            if ref not in items:raise FinancialError('provenance reference outside input')
            refs.extend(items[ref].source_refs)
    for ref in data['derivation_refs']:
        if ref not in derived:raise FinancialError('provenance derivation outside input')
        refs.append(derived[ref].source_id)
    return source_closure(registry,refs)


@dataclass(frozen=True)
class _SymbolicCell:
    """Dependency and availability only. No financial numbers are evaluated."""
    known: bool | None
    currency: str | None
    observation_refs: tuple = ()
    parameter_refs: tuple = ()
    derivation_refs: tuple = ()
    historical_fx_refs: tuple = ()
    source_refs: tuple = ()


_INHERIT = object()


def _symbol_union(*cells,known=_INHERIT,currency=_INHERIT):
    return _SymbolicCell(all(c.known for c in cells) if known is _INHERIT else known,
        cells[0].currency if currency is _INHERIT else currency,
        **{name:tuple(sorted({r for c in cells for r in getattr(c,name)})) for name in
            ('observation_refs','parameter_refs','derivation_refs','historical_fx_refs','source_refs')})


class _DependencyPlan:
    """Finite template expectation derived exclusively from immutable inputs.

    Presence/null checks choose branches; no Decimal operations, raw result
    values, evaluator calls or newly created Meter participate in this plan.
    """
    def __init__(self,request,registry):
        self.request=request; self.registry=registry; self.parsed=request.legacy()
        self.observations={r.id:r for r in registry.records if type(r) is RegisteredObservationV2}
        self.rates={r.id:r for r in registry.records if type(r) is RegisteredFXV2}
        self.params={s.id+':'+p.id:p for s in self.parsed.scenarios for p in s.parameters()}
        self.derived={v.id:v for v in request.derived_fx_inputs}
        self.choices={v.observation_id:v for v in request.historical_fx_choices}
        if request.interim_revenue_ref not in self.observations:raise FinancialError('baseline outside input')
        self.native=self.observations[request.interim_revenue_ref].currency

    def observation(self,ref):
        if ref not in self.observations:raise FinancialError('historical reference outside input')
        row=self.observations[ref]
        return _SymbolicCell(row.value is not None,row.currency,observation_refs=(ref,))

    def parameter(self,p,scenario):
        return _SymbolicCell(p.value is not None,p.currency,
            observation_refs=(p.anchor_observation_id,) if p.anchor_observation_id and not p.independent else (),
            parameter_refs=(scenario.id+':'+p.id,))

    def future(self,cell,currency,period,scenario):
        if cell.currency==currency:return cell
        fx=next((v['parameter'] for v in scenario.future_fx
            if (v['from_currency'],v['to_currency'],v['parameter'].period)==(cell.currency,currency,period)),None)
        if fx is None:return _symbol_union(cell,known=False,currency=currency)
        # The numerical future() consumes the FX Parameter, not its optional
        # contextual anchor as an additional observed amount.
        rate=_SymbolicCell(fx.value is not None,None,parameter_refs=(scenario.id+':'+fx.id,))
        return _symbol_union(cell,rate,currency=currency)

    def money(self,p,currency,scenario):
        return self.future(self.parameter(p,scenario),currency,p.period,scenario)

    def historical(self,ref):
        cell=self.observation(ref)
        if cell.currency==self.request.target_currency:return cell
        choice=self.choices.get(ref)
        if choice is None:return _symbol_union(cell,known=False,currency=self.request.target_currency)
        if type(choice) is DerivedFXChoiceV2:
            if choice.derivation_id not in self.derived:raise FinancialError('derived reference outside input')
            rate=_SymbolicCell(True,None,derivation_refs=(choice.derivation_id,))
        else:
            if choice.fx_id not in self.rates:raise FinancialError('FX reference outside input')
            rate=_SymbolicCell(self.rates[choice.fx_id].value is not None,None,historical_fx_refs=(choice.fx_id,))
        return _symbol_union(cell,rate,currency=self.request.target_currency)

    def scale(self,cell,p,scenario):
        return _symbol_union(cell,self.parameter(p,scenario),currency=cell.currency)

    def share(self,amount,group):
        # Zero-denominator and null branches have the same dependency union;
        # determining a numerical zero here would repeat financial arithmetic.
        return _symbol_union(amount,group,known=None,currency=None)

    def metrics(self,revenue,scenario,year):
        from .financial_policy import COST_TAGS
        costs=[]; covered=set(); profit=revenue
        for line in scenario.costs:
            covered.update(line.coverage)
            item=next((v for v in line.values if v.year==year),None)
            if item is None:cost=_SymbolicCell(False,revenue.currency)
            elif line.mode=='revenue_ratio':cost=self.scale(revenue,item.parameter,scenario)
            else:cost=self.money(item.parameter,revenue.currency,scenario)
            costs.append(cost); profit=_symbol_union(profit,cost)
        covered.update(e['tag'] for e in scenario.exclusions)
        profit=_symbol_union(profit,_SymbolicCell(True,revenue.currency,
            source_refs=tuple(sorted({r for e in scenario.exclusions for r in e['source_refs']}))),
            known=profit.known and not (COST_TAGS-covered))
        composition=[]; total=_SymbolicCell(True,revenue.currency)
        for category in self.request.categories:
            if category.kind=='unallocated':continue
            allocation=next((a for a in scenario.allocations if a['category_id']==category.id),None)
            item=next((v for v in allocation['values'] if v.year==year),None) if allocation else None
            if item is None:amount=_SymbolicCell(False,revenue.currency)
            elif allocation['mode']=='share':amount=self.scale(revenue,item.parameter,scenario)
            else:amount=self.money(item.parameter,revenue.currency,scenario)
            composition.append((amount,self.share(amount,revenue)))
            # Only a numerically present allocation enters the allocated sum.
            # Its presence follows input null/FX availability, not snapshot data.
            if amount.known:total=_symbol_union(total,amount)
        residue=_symbol_union(revenue,total)
        composition.append((residue,self.share(residue,revenue)))
        return {'revenue':revenue,'operating_profit':profit,
            'net_profit':_SymbolicCell(False,revenue.currency),'costs':costs,'composition':composition}

    def scenario(self,scenario):
        h1=self.observation(self.request.interim_revenue_ref)
        h2=self.money(scenario.remaining_revenue,self.native,scenario)
        target_h1=self.historical(self.request.interim_revenue_ref)
        target_h2=self.money(scenario.remaining_revenue,self.request.target_currency,scenario)
        bridge={'interim':h1,'remaining_assumption':h2,'target_interim':target_h1,'target_remaining':target_h2}
        native=_symbol_union(h1,h2); target=_symbol_union(target_h1,target_h2); years=[]
        for year in YEARS:
            if year>2026:
                growth=next(v.parameter for v in scenario.growth if v.year==year)
                native=self.scale(native,growth,scenario)
                target=self.future(native,self.request.target_currency,
                    Period(f'{year}-01-01',f'{year}-12-31','annual'),scenario)
            row={'target':self.metrics(target,scenario,year)}
            if self.native!=self.request.target_currency:row['native']=self.metrics(native,scenario,year)
            years.append(row)
        return bridge,years

    def entries(self):
        for i,ref in enumerate((self.request.interim_revenue_ref,)+self.request.historical_context_refs):
            yield ('historical_context',i,'target_value'),self.historical(ref)
        for i,scenario in enumerate(self.parsed.scenarios):
            bridge,years=self.scenario(scenario)
            for name,cell in bridge.items():yield ('scenarios',i,'bridge',name),cell
            for j,row in enumerate(years):
                for currency,values in row.items():
                    prefix=('scenarios',i,'years',j,currency)
                    for name in ('revenue','operating_profit','net_profit'):yield (*prefix,name),values[name]
                    for k,cell in enumerate(values['costs']):yield (*prefix,'cost_bridge',k,'value'),cell
                    for k,(amount,share) in enumerate(values['composition']):
                        yield (*prefix,'composition','rows',k,'amount'),amount
                        yield (*prefix,'composition','rows',k,'share'),share

    def provenance(self,cell):
        entry={name:list(getattr(cell,name)) for name in
            ('observation_refs','parameter_refs','derivation_refs','historical_fx_refs')}
        refs=list(cell.source_refs)
        for name,items in (('observation_refs',self.observations),('parameter_refs',self.params),('historical_fx_refs',self.rates)):
            for ref in entry[name]:
                if ref not in items:raise FinancialError('dependency outside input')
                refs.extend(items[ref].source_refs)
        for ref in entry['derivation_refs']:refs.append(self.derived[ref].source_id)
        entry['source_refs']=source_closure(self.registry,refs)
        return {'id':digest(entry),**entry}


def _validate_dependencies(request,registry,data,by_id,*,meter=None):
    plan=_DependencyPlan(request,registry)
    for path,expected in plan.entries():
        if meter is not None:meter.tick()
        cell=data
        try:
            for key in path:cell=cell[key]
            actual=by_id[cell['provenance_ref']].model_dump(mode='json')
        except (KeyError,IndexError,TypeError):raise FinancialError('dependency cell path differs') from None
        if actual!=plan.provenance(expected):raise FinancialError('cell actual dependency differs')
        if expected.known is not None and (cell['raw_value'] is not None)!=expected.known:
            raise FinancialError('cell input availability differs')


def validate_snapshot(envelope,registry,snapshot,*,_meter=None):
    if _meter is not None and type(_meter) is not Meter:raise FinancialError('exact validation Meter required')
    envelope,registry,bindings=input_binding(envelope,registry)
    if type(snapshot) is not FinancialSnapshotV2: raise FinancialError('exact v2 snapshot required')
    raw=bounded(snapshot.data(),SNAPSHOT_LIMIT)
    snapshot=FinancialSnapshotV2.model_validate_json(raw); data=snapshot.data()
    if (any(data[k]!=v for k,v in bindings.items()) or snapshot.registry_ref!=envelope.data.registry_ref
            or snapshot.input_status.model_dump(mode='json')!=INPUT_STATUS
            or snapshot.qualifications!=QUALIFICATIONS or snapshot.target_currency!=envelope.data.request.target_currency
            or snapshot.categories!=envelope.data.request.categories): raise FinancialError('snapshot binding differs')
    bounded({'operation':envelope.data_dict(),'snapshot':data},PURE_LIMIT)
    request=envelope.data.request; parsed=request.legacy()
    if [v.observation_ref for v in snapshot.historical_context]!=[request.interim_revenue_ref,*request.historical_context_refs]:
        raise FinancialError('historical selection differs')
    if len(snapshot.scenarios)!=len(parsed.scenarios):raise FinancialError('scenario count differs')
    by_id={p.id:p for p in snapshot.provenance_table}
    if [p.id for p in snapshot.provenance_table]!=sorted(by_id):raise FinancialError('provenance order or duplicates')
    used=set()
    def walk(value):
        if type(value) is dict:
            if 'raw_value' in value:
                cell=CellV2.model_validate_json(canonical(value)); used.add(cell.provenance_ref)
                if cell.provenance_ref not in by_id:raise FinancialError('dangling cell provenance')
            else:
                for child in value.values():walk(child)
        elif type(value) is list:
            for child in value:walk(child)
    walk(data)
    if used!=set(by_id):raise FinancialError('unused provenance')
    for output,scenario in zip(snapshot.scenarios,parsed.scenarios):
        if ((output.id,output.label,output.accounting_basis)!=(scenario.id,scenario.label,scenario.accounting_basis)
                or output.exclusions!=request.scenarios[[s.id for s in parsed.scenarios].index(scenario.id)].exclusions):
            raise FinancialError('scenario metadata differs')
        expected_qualification=('source_linked_conditional_unreviewed' if all(p.source_refs for p in scenario.parameters())
            else 'mechanical_assumption_demonstration_not_validated_forecast')
        if output.qualification!=expected_qualification:raise FinancialError('scenario qualification differs')
        baseline=next(r for r in registry.records if r.id==request.interim_revenue_ref)
        def amount(cell,currency):
            if cell.currency!=currency or cell.unit!='million':raise FinancialError('cell amount scope differs')
        for name in ('interim','remaining_assumption','target_interim','target_remaining'):
            amount(getattr(output.bridge,name),request.target_currency if name.startswith('target') else baseline.currency)
        for row,year in zip(output.years,YEARS):
            if (row.year!=year or row.period.model_dump(mode='json')!={'start':f'{year}-01-01','end':f'{year}-12-31','grain':'annual'}
                    or row.basis!=('bridge_estimate' if year==2026 else 'conditional_scenario')
                    or row.target_currency!=request.target_currency or row.native_currency!=baseline.currency
                    or (type(row.native) is SameTargetV2)!=(baseline.currency==request.target_currency)):
                raise FinancialError('year metadata differs')
            for values,currency in ((row.native,row.native_currency),(row.target,row.target_currency)):
                if type(values) is SameTargetV2:
                    if row.native_currency!=row.target_currency:raise FinancialError('invalid native alias')
                    continue
                if values.net_profit.raw_value is not None:raise FinancialError('net profit projection unsupported')
                for cell in (values.revenue,values.operating_profit,values.net_profit):amount(cell,currency)
                if len(values.cost_bridge)!=len(scenario.costs):raise FinancialError('cost count differs')
                for cost,expected in zip(values.cost_bridge,scenario.costs):
                    if (cost.id,cost.kind,cost.coverage,cost.coverage_basis)!=(expected.id,expected.kind,expected.coverage,expected.coverage_basis):
                        raise FinancialError('cost metadata differs')
                    amount(cost.value,currency)
                cats=[v.id for v in request.categories if v.kind!='unallocated']+[v.id for v in request.categories if v.kind=='unallocated']
                if [v.category_id for v in values.composition.rows]!=cats:raise FinancialError('composition categories differ')
                for part in values.composition.rows:
                    amount(part.amount,currency)
                    if part.share.unit!='ratio' or part.share.currency is not None:raise FinancialError('share scope differs')
                    if part.included_in_allocated_sum!=(part.amount.raw_value is not None):raise FinancialError('composition inclusion differs')
                rounding=values.composition.rounding_delta_million
                if rounding is not None and (re.fullmatch(r'-?(?:0|[1-9][0-9]*)\.[0-9]{6}',rounding) is None or Decimal(rounding).copy_abs()>MAX_ABS):
                    raise FinancialError('invalid composition rounding delta')
    for historical in snapshot.historical_context:
        if historical.target_value.currency!=request.target_currency or historical.target_value.unit!='million':
            raise FinancialError('historical cell scope differs')
    if [e.input for e in snapshot.derived_fx_evidence]!=list(request.derived_fx_inputs):raise FinancialError('derived input differs')
    _validate_dependencies(request,registry,data,by_id,meter=_meter)
    expected=parsed.sensitivity
    if len(snapshot.sensitivity)!=(len(expected['points']) if expected else 0):raise FinancialError('sensitivity length differs')
    if expected:
        for row,point in zip(snapshot.sensitivity,expected['points']):
            variant=request.data(); variant['sensitivity']=None
            _change_parameter(variant,expected['scenario_id'],expected['parameter_id'],point)
            if (row.parameter_ref!=expected['scenario_id']+':'+expected['parameter_id'] or row.point!=point
                    or row.years!=YEARS or len(row.target_revenue)!=6 or len(row.target_operating_profit)!=6
                    or row.case_input_digest!=digest({'execution_profile':PROFILE,'request':variant,'registry':registry.model_dump(mode='json')})):
                raise FinancialError('sensitivity binding differs')
            for value in row.target_revenue+row.target_operating_profit:
                if value is not None and re.fullmatch(r'-?(?:0|[1-9][0-9]*)\.[0-9]{6}',value) is None:
                    raise FinancialError('invalid sensitivity display')
            variant_request=FinancialRequestV2.model_validate_json(canonical(variant))
            plan=_DependencyPlan(variant_request,registry)
            scenario=next(s for s in plan.parsed.scenarios if s.id==expected['scenario_id'])
            _,years=plan.scenario(scenario)
            for i,year in enumerate(years):
                for key,values in (('revenue',row.target_revenue),('operating_profit',row.target_operating_profit)):
                    if _meter is not None:_meter.tick()
                    if (values[i] is not None)!=year['target'][key].known:
                        raise FinancialError('sensitivity input availability differs')
    return envelope,registry,snapshot


def _change_parameter(request,scenario_id,parameter_id,point):
    def change(value):
        if type(value) is dict:
            for k,v in value.items():
                if k=='value' and value.get('id')==parameter_id:value[k]=point
                else:change(v)
        elif type(value) is list:
            for v in value:change(v)
    for scenario in request['scenarios']:
        if scenario['id']==scenario_id:change(scenario)


class SummarySourceV2(FrozenData):
    id: UUID4
    kind: Literal['owner_supplied']
    verification: Literal['unverified']
    original_available: Literal[False]
    system_verified: Literal[False]
    read_scope: str
    source_chain: tuple[UUID4,...]


class AvailabilityV2(FrozenData):
    revenue: bool
    operating_profit: bool
    net_profit: bool


class SummaryYearV2(FrozenData):
    year: Year
    available: AvailabilityV2
    composition_coverage: str


class SummaryScenarioV2(FrozenData):
    id: Label
    label: str
    qualification: str
    years: tuple[SummaryYearV2,...]


class SummaryValueV2(FrozenData):
    information_cutoff: str
    target_currency: Currency
    amount_unit: Literal['million']
    sources: tuple[SummarySourceV2,...]
    scenarios: tuple[SummaryScenarioV2,...]
    qualifications: tuple[str,...]
    gap_codes: tuple[str,...]
    assumption_refs: tuple[str,...]
    derivation_refs: tuple[Label,...]


class EvidenceV2(FrozenData):
    sources: tuple[RegisteredSourceV2,...]
    observations: tuple[RegisteredObservationV2,...]
    historical_fx: tuple[RegisteredFXV2,...]
    assumptions: FinancialRequestV2
    derived_fx_evidence: tuple[DerivedFXEvidenceV1,...]
    provenance_table: tuple[ProvenanceV2,...]
    qualifications: tuple[str,...]


class TableValueV2(FrozenData):
    scenarios: tuple[ScenarioResultV2,...]
    historical_context: tuple[HistoricalCellV2,...]
    evidence: EvidenceV2


class SeriesV2(FrozenData):
    scenario_id: Label
    metric: Literal['revenue','operating_profit','net_profit','segment_revenue']
    category_id: Label | None = None
    currency: Currency
    unit: Literal['million']
    years: tuple[Year,...]
    values: tuple[str | None,...]
    @model_validator(mode='after')
    def check(self):
        if ((self.metric=='segment_revenue')!=(self.category_id is not None)
                or self.years!=YEARS or len(self.values)!=6):raise FinancialError('chart series scope differs')
        return self
    @model_serializer(mode='wrap')
    def serialize(self,handler):
        result=handler(self)
        if self.category_id is None:result.pop('category_id',None)
        return result


class ChartSpecV2(FrozenData):
    snapshot_digest: Digest
    series: tuple[SeriesV2,...]
    connect_nulls: Literal[False]
    probability_calibrated: Literal[False]
    value_kind: Literal['absolute_amounts_display_rounded']
    sensitivity: tuple[SensitivityResultV2,...]
    @field_validator('connect_nulls','probability_calibrated',mode='before')
    @classmethod
    def flags(cls,value):
        if value is not False:raise FinancialError('literal chart flags required')
        return value


class ChartValueV2(FrozenData):
    chart_spec: ChartSpecV2
    evidence: EvidenceV2


class PublicFinancialResultV2(FrozenData):
    view: Literal['summary','table','chart']
    input_status: InputStatusV2
    value: SummaryValueV2 | TableValueV2 | ChartValueV2
    @model_validator(mode='after')
    def check(self):
        if type(self.value) is not {'summary':SummaryValueV2,'table':TableValueV2,'chart':ChartValueV2}[self.view]:
            raise FinancialError('public view shape differs')
        return self


def project_financial_snapshot_v2(envelope,registry,snapshot,*,view):
    envelope,registry,snapshot=validate_snapshot(envelope,registry,snapshot)
    if view not in ('summary','table','chart'):raise FinancialError('unsupported financial view')
    data=snapshot.data(); request=envelope.data.request
    records=[r.model_dump(mode='json') for r in registry.records]
    evidence={'sources':[r for r in records if r['row_type']=='source'],
        'observations':[r for r in records if r['row_type']=='observation'],
        'historical_fx':[r for r in records if r['row_type']=='historical_fx'],
        'assumptions':request.data(),'derived_fx_evidence':data['derived_fx_evidence'],
        'provenance_table':data['provenance_table'],'qualifications':data['qualifications']}
    if view=='table':value={k:data[k] for k in ('scenarios','historical_context')}; value['evidence']=evidence
    elif view=='chart':
        series=[]
        for scenario in data['scenarios']:
            for metric in ('revenue','operating_profit','net_profit'):
                series.append({'scenario_id':scenario['id'],'metric':metric,'currency':data['target_currency'],'unit':'million',
                    'years':list(YEARS),'values':[r['target'][metric]['display'] for r in scenario['years']]})
            for category in data['categories']:
                series.append({'scenario_id':scenario['id'],'metric':'segment_revenue','category_id':category['id'],
                    'currency':data['target_currency'],'unit':'million','years':list(YEARS),
                    'values':[next(v['amount']['display'] for v in r['target']['composition']['rows'] if v['category_id']==category['id']) for r in scenario['years']]})
        value={'chart_spec':{'snapshot_digest':snapshot.digest,'series':series,'connect_nulls':False,'probability_calibrated':False,
            'value_kind':'absolute_amounts_display_rounded','sensitivity':data['sensitivity']},'evidence':evidence}
    else:
        gaps=set()
        def collect(value):
            if type(value) is dict:
                gaps.update(value.get('reasons',[]))
                for child in value.values():collect(child)
            elif type(value) is list:
                for child in value:collect(child)
        collect(data)
        value={'information_cutoff':request.information_cutoff,'target_currency':request.target_currency,'amount_unit':'million',
            'sources':[{k:r[k] for k in ('id','kind','verification','original_available','system_verified','read_scope','source_chain')} for r in evidence['sources']],
            'scenarios':[{'id':s['id'],'label':s['label'],'qualification':s['qualification'],
                'years':[{'year':r['year'],'available':{m:r['target'][m]['raw_value'] is not None for m in ('revenue','operating_profit','net_profit')},
                    'composition_coverage':r['target']['composition']['coverage']} for r in s['years']]} for s in data['scenarios']],
            'qualifications':data['qualifications'],'gap_codes':sorted(gaps),
            'assumption_refs':[s.id+':'+p.id for s in request.legacy().scenarios for p in s.parameters()],
            'derivation_refs':[v.id for v in request.derived_fx_inputs]}
    result=PublicFinancialResultV2.model_validate_json(bounded({'view':view,'input_status':INPUT_STATUS,'value':value},PUBLIC_LIMIT))
    bounded(result.model_dump(mode='json'),PUBLIC_LIMIT)
    return result
