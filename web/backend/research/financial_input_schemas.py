"""Owner declarations v2: bounded preview data, never a source or write grant."""
import hashlib
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from .errors import ResearchError
from .financial_policy import CURRENCIES, MILLION_FACTORS, FinancialError, canonical, number
from .financial_schemas import Period, day, label, text
from .schemas import Revision

CONTRACT = 'financial-input-v2'
PARSER_REVISION = 'owner-financial-csv-v1'
CSV_LIMIT = PLAN_LIMIT = 131072
WIRE_LIMIT = 794624
MAX_NODES, MAX_DEPTH = 20000, 32
CSV_HEADER = tuple('row_type,key,source_refs,url,locator,excerpt,declared_original_sha256,claimed_published_at,claimed_accessed_at,read_scope,source_chain,entity_scope,scope_kind,metric,period_start,period_end,period_grain,value,currency,unit,accounting_basis,declared_basis,alternative_refs,from_currency,to_currency,fx_kind'.split(','))
Digest = Annotated[str, Field(strict=True, pattern=r'^[0-9a-f]{64}$')]
Basis = Literal['disclosed', 'media_estimate', 'missing', 'conflicted']
Metric = Literal['revenue', 'operating_profit', 'net_profit', 'operating_cost', 'operating_expense', 'shared_cost', 'depreciation', 'sbc', 'operating_adjustment', 'capex']


class FinancialImportError(ResearchError):
    def __init__(self, code='INVALID_INPUT', *, row=None, field='csv_text', limit=False):
        message = ('财务输入超过有限预览范围。' if limit else
                   '历史行不接受假设；请把假设填入计算参数（independent）。' if code=='ASSUMPTION_IN_HISTORY' else
                   '财务输入不符合要求；请核对指定行和字段。')
        super().__init__('PAYLOAD_LIMIT' if limit else 'INPUT_INVALID', 413 if limit else 422, message)
        self.detail = {'row': row, 'field': field, 'code': code}

    def body(self):
        return {**super().body(), 'validation': self.detail.copy()}


class FrozenData(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class OwnerDeclaration(FrozenData):
    kind: Literal['owner_supplied'] = 'owner_supplied'
    verification: Literal['unverified'] = 'unverified'
    original_available: Literal[False] = False
    system_verified: Literal[False] = False


class RowLocation(OwnerDeclaration):
    key: Annotated[str, Field(min_length=1, max_length=32, pattern=r'^[a-z][a-z0-9_]{0,31}$')]
    record_index: Annotated[StrictInt, Field(ge=1, le=96)]
    physical_line_start: Annotated[StrictInt, Field(ge=2, le=131073)]
    physical_line_end: Annotated[StrictInt, Field(ge=2, le=131073)]

    @model_validator(mode='after')
    def location(self):
        label(self.key)
        if self.physical_line_end < self.physical_line_start:
            raise FinancialError('invalid CSV location')
        return self


class OwnerSourceV2(RowLocation):
    row_type: Literal['source']
    url: Annotated[str, Field(min_length=1, max_length=1600)]
    locator: Annotated[str, Field(min_length=1, max_length=240)]
    excerpt: Annotated[str, Field(min_length=1, max_length=1000)]
    received_excerpt_sha256: Digest
    declared_original_sha256: Digest | None
    claimed_published_at: str | None
    claimed_accessed_at: str | None
    read_scope: Annotated[str, Field(min_length=1, max_length=700)]
    source_chain: Annotated[tuple[str, ...], Field(max_length=16)]

    @model_validator(mode='after')
    def declaration(self):
        text(self.url, 1600); text(self.locator, 240); text(self.excerpt, 1000); text(self.read_scope, 700)
        url = urlsplit(self.url)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise FinancialError('invalid source URL')
        for value in (self.claimed_published_at, self.claimed_accessed_at):
            if value is not None: day(value)
        if self.claimed_published_at is not None and self.claimed_accessed_at is not None and day(self.claimed_accessed_at) < day(self.claimed_published_at):
            raise FinancialError('invalid claimed dates')
        if self.received_excerpt_sha256 != hashlib.sha256(self.excerpt.encode('utf-8')).hexdigest():
            raise FinancialError('received excerpt differs')
        return self


class OwnerHistoricalValueV2(RowLocation):
    period_start: str
    period_end: str
    period_grain: Literal['annual', 'interim', 'remaining']
    value: str | None
    declared_basis: Basis
    source_refs: Annotated[tuple[str, ...], Field(max_length=16)]

    @model_validator(mode='after')
    def historical(self):
        Period(self.period_start, self.period_end, self.period_grain)
        if (self.declared_basis in ('missing', 'conflicted')) != (self.value is None):
            raise FinancialError('declared basis and null disagree')
        if self.value is not None:
            number(self.value)
            if not self.source_refs: raise FinancialError('numeric historical value needs source')
        return self


class OwnerObservationV2(OwnerHistoricalValueV2):
    row_type: Literal['observation']
    entity_scope: Annotated[str, Field(min_length=1, max_length=120)]
    scope_kind: Literal['group', 'segment', 'app']
    metric: Metric
    currency: Literal['CNY', 'USD']
    unit: Literal['unit', 'thousand', 'million', 'billion']
    accounting_basis: Annotated[str, Field(min_length=1, max_length=240)]
    alternative_refs: Annotated[tuple[str, ...], Field(max_length=8)]

    @model_validator(mode='after')
    def observation(self):
        text(self.entity_scope, 120); text(self.accounting_basis, 240)
        if self.currency not in CURRENCIES or self.unit not in MILLION_FACTORS:
            raise FinancialError('unsupported amount')
        if self.value is not None and self.metric not in ('operating_profit', 'net_profit', 'operating_adjustment') and number(self.value) < 0:
            raise FinancialError('negative revenue or cost')
        return self


class OwnerHistoricalFXV2(OwnerHistoricalValueV2):
    row_type: Literal['historical_fx']
    from_currency: Literal['CNY', 'USD']
    to_currency: Literal['CNY', 'USD']
    fx_kind: Literal['period_average', 'spot']

    @model_validator(mode='after')
    def fx(self):
        if self.from_currency == self.to_currency or self.value is not None and number(self.value) <= 0:
            raise FinancialError('invalid FX direction or rate')
        return self


OwnerRowV2 = Annotated[OwnerSourceV2 | OwnerObservationV2 | OwnerHistoricalFXV2, Field(discriminator='row_type')]


class OwnerFinancialImportPlanV2(FrozenData):
    contract: Literal['owner-financial-key-plan-v2'] = 'owner-financial-key-plan-v2'
    parser_revision: Literal['owner-financial-csv-v1'] = PARSER_REVISION
    records: Annotated[tuple[OwnerRowV2, ...], Field(max_length=96)]


class FinancialImportPreviewRequest(FrozenData):
    input_revision: Revision
    expected_research_version: Revision
    csv_text: Annotated[str, Field(max_length=CSV_LIMIT)]


class FinancialImportPreviewEnvelope(FrozenData):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['financial-input-v2']
    data: FinancialImportPreviewRequest


class FinancialImportPreviewData(OwnerDeclaration):
    research_id: str
    input_revision: Revision
    problem_digest: Digest
    expected_research_version: Revision
    parser_revision: Literal['owner-financial-csv-v1'] = PARSER_REVISION
    exact_received_csv_sha256: Digest
    key_based_plan_digest: Digest
    preview_digest: Digest
    plan: OwnerFinancialImportPlanV2
    persisted: Literal[False] = False
    execution_authorized: Literal[False] = False
    qualifications: tuple[Literal['owner_declarations_not_verified', 'claimed_dates_not_verified_as_of', 'preview_only_no_save_or_execution'], ...] = (
        'owner_declarations_not_verified', 'claimed_dates_not_verified_as_of', 'preview_only_no_save_or_execution')


class FinancialImportPreviewResponse(FrozenData):
    schema_version: Literal['structure-research-v1'] = 'structure-research-v1'
    contract_revision: Literal['financial-input-v2'] = CONTRACT
    data: FinancialImportPreviewData


def _json_shape(value):
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop(); count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise FinancialImportError('JSON_SHAPE_LIMIT', limit=True)
        if type(item) is dict:
            pending.extend((v, depth + 1) for pair in item.items() for v in pair)
        elif type(item) is list:
            pending.extend((v, depth + 1) for v in item)


def decode_financial_import_preview(raw: bytes) -> FinancialImportPreviewEnvelope:
    """Single decoder for the bounded HTTP reader AND actual action verifier."""
    if type(raw) is not bytes or len(raw) > WIRE_LIMIT:
        raise FinancialImportError('WIRE_LIMIT', limit=True)
    def pairs(items):
        value = {}
        for key, child in items:
            if key in value: raise ValueError('duplicate key')
            value[key] = child
        return value
    def rejected(_): raise ValueError('strict JSON number required')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=rejected,
                           parse_constant=rejected, parse_int=lambda v: int(v) if len(v.lstrip('-')) <= 20 else rejected(v))
        _json_shape(value)
        data=value.get('data') if type(value) is dict else None
        csv_value=data.get('csv_text') if type(data) is dict else None
        if type(csv_value) is str and len(csv_value.encode('utf-8'))>CSV_LIMIT:
            raise FinancialImportError('CSV_LIMIT',limit=True)
        result = FinancialImportPreviewEnvelope.model_validate(value)
        if len(result.data.csv_text.encode('utf-8')) > CSV_LIMIT:
            raise FinancialImportError('CSV_LIMIT', limit=True)
        return result
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise FinancialImportError('INVALID_JSON_OR_FIELDS') from None
