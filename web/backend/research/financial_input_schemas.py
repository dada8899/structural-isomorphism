"""Owner declarations v2: bounded preview data, never a source or write grant."""
import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

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


def _decode_import_json(raw: bytes):
    """Private bounded JSON primitive; fixed public decoders choose their types."""
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
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise FinancialImportError('INVALID_JSON_OR_FIELDS') from None


def decode_financial_import_preview(raw: bytes) -> FinancialImportPreviewEnvelope:
    """The unchanged preview domain, shared by reader and actual action."""
    try:return FinancialImportPreviewEnvelope.model_validate(_decode_import_json(raw))
    except ValueError:raise FinancialImportError('INVALID_JSON_OR_FIELDS') from None


UUID4 = Annotated[str, Field(strict=True, pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')]
One = Annotated[StrictInt, Field(ge=1, le=1)]
UTC = Annotated[str, Field(strict=True, pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$')]


def _utc(value):
    if datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%dT%H:%M:%S.%fZ')!=value:
        raise ValueError('strict UTC required')
    return value


class FinancialRegistryConfirmation(FinancialImportPreviewRequest):
    preview_digest: Digest
    confirmed: Literal[True]
    @field_validator('confirmed',mode='before')
    @classmethod
    def explicit_confirmation(cls,value):
        if value is not True:raise ValueError('explicit true required')
        return value


class FinancialRegistryConfirmationEnvelope(FrozenData):
    schema_version: Literal['structure-research-v1']
    contract_revision: Literal['financial-input-v2']
    data: FinancialRegistryConfirmation


def decode_financial_registry_confirmation(raw: bytes) -> FinancialRegistryConfirmationEnvelope:
    try:return FinancialRegistryConfirmationEnvelope.model_validate(_decode_import_json(raw))
    except ValueError:raise FinancialImportError('INVALID_JSON_OR_FIELDS') from None


class RegistryIdentityV2(FrozenData):
    id: UUID4
    revision: One


class FinancialRegistryRefV2(RegistryIdentityV2):
    digest: Digest


class RegistryBindingV2(FrozenData):
    research_id: UUID4
    input_revision: Revision
    problem_digest: Digest
    research_version_before: Annotated[StrictInt, Field(ge=1, le=2147483646)]
    research_version_after: Revision
    @model_validator(mode='after')
    def versions(self):
        if self.research_version_after!=self.research_version_before+1:raise ValueError('registry version sequence')
        return self


class PublicRegistryReceiptV2(FrozenData):
    received_at: UTC
    exact_received_csv_sha256: Digest
    key_based_plan_digest: Digest
    preview_digest: Digest
    _time=field_validator('received_at')(_utc)


class RegistryReceiptV2(PublicRegistryReceiptV2):
    received_ref: UUID4


class KeyMapEntryV2(FrozenData):
    key: Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,31}$')]
    row_type: Literal['source','observation','historical_fx']
    registered_id: UUID4
    record_index: Annotated[StrictInt, Field(ge=1, le=96)]
    physical_line_start: Annotated[StrictInt, Field(ge=2, le=131073)]
    physical_line_end: Annotated[StrictInt, Field(ge=2, le=131073)]


class _Registered(FrozenData):
    id: UUID4
    @field_validator('source_chain','source_refs','alternative_refs',mode='before',check_fields=False)
    @classmethod
    def json_reference_array(cls,value):
        # Pydantic 2.7's model-before hook otherwise loses JSON tuple mode.
        # Only the declared JSON array container changes; values stay strict.
        return tuple(value) if type(value) is list else value
    @model_validator(mode='before')
    @classmethod
    def no_numeric_flags(cls,value):
        if type(value) is dict and any(k in value and value[k] is not False for k in ('original_available','system_verified')):
            raise ValueError('literal false required')
        return value


class RegisteredSourceV2(_Registered,OwnerSourceV2):
    source_chain: Annotated[tuple[UUID4,...],Field(max_length=16)]


class RegisteredObservationV2(_Registered,OwnerObservationV2):
    source_refs: Annotated[tuple[UUID4,...],Field(max_length=16)]
    alternative_refs: Annotated[tuple[UUID4,...],Field(max_length=8)]


class RegisteredFXV2(_Registered,OwnerHistoricalFXV2):
    source_refs: Annotated[tuple[UUID4,...],Field(max_length=16)]


RegisteredRowV2=Annotated[RegisteredSourceV2|RegisteredObservationV2|RegisteredFXV2,Field(discriminator='row_type')]


class _RegistryOwnerDeclaration(OwnerDeclaration):
    @field_validator('original_available','system_verified',mode='before')
    @classmethod
    def false_flags(cls,value):
        if value is not False:raise ValueError('literal false required')
        return value


class _NoExecution(FrozenData):
    execution_authorized: Literal[False]=False
    @field_validator('execution_authorized',mode='before')
    @classmethod
    def no_execution(cls,value):
        if value is not False:raise ValueError('literal false required')
        return value


class PublicOwnerFinancialRegistryV2(FrozenData):
    format_version: Literal['owner-financial-registry-public-v2']
    parser_revision: Literal['owner-financial-csv-v1']
    identity: RegistryIdentityV2
    binding: RegistryBindingV2
    receipt: PublicRegistryReceiptV2
    key_map: Annotated[tuple[KeyMapEntryV2,...],Field(max_length=96)]
    records: Annotated[tuple[RegisteredRowV2,...],Field(max_length=96)]
    @model_validator(mode='after')
    def mapping(self):
        if len(self.key_map)!=len(self.records):raise ValueError('incomplete registry mapping')
        ids={r.id:r for r in self.records}
        if len(ids)!=len(self.records) or len({r.key for r in self.records})!=len(ids):raise ValueError('duplicate registry identity')
        for index,(m,r) in enumerate(zip(self.key_map,self.records),1):
            if (m.registered_id,m.key,m.row_type,m.record_index,m.physical_line_start,m.physical_line_end)!=(r.id,r.key,r.row_type,index,r.physical_line_start,r.physical_line_end) or r.record_index!=index:
                raise ValueError('registry mapping order changed')
        for kind,cap in (('source',16),('observation',64),('historical_fx',16)):
            if sum(r.row_type==kind for r in self.records)>cap:raise ValueError('registry count limit')
        for r in self.records:
            groups=[('source_chain',r.source_chain,'source')] if r.row_type=='source' else [('source_refs',r.source_refs,'source')]
            if r.row_type=='observation':groups.append(('alternative_refs',r.alternative_refs,'observation'))
            for name,refs,kind in groups:
                if len(set(refs))!=len(refs) or any(ref not in ids or ids[ref].row_type!=kind for ref in refs):raise ValueError('registry reference domain')
                if name=='alternative_refs':
                    fields=('entity_scope','scope_kind','metric','period_start','period_end','period_grain','accounting_basis')
                    if any(any(getattr(r,k)!=getattr(ids[ref],k) for k in fields) for ref in refs):raise ValueError('registry alternative differs')
        for kind,name in (('source','source_chain'),('observation','alternative_refs')):
            done=set()
            def visit(ref,path):
                if ref in path:raise ValueError('cyclic registry reference')
                if ref in done:return
                for child in getattr(ids[ref],name):visit(child,path|{ref})
                done.add(ref)
            for r in self.records:
                if r.row_type==kind:visit(r.id,set())
        return self


class OwnerFinancialRegistryV2(PublicOwnerFinancialRegistryV2):
    format_version: Literal['owner-financial-registry-v2']
    receipt: RegistryReceiptV2


class PublicFinancialRegistryProjectionV2(FrozenData):
    csv_text: Annotated[str,Field(max_length=CSV_LIMIT)]
    registry: PublicOwnerFinancialRegistryV2


class RegistryCurrentV2(FrozenData):
    input_revision: Revision
    research_version: Revision


class RegistryMetadataV2(_RegistryOwnerDeclaration,RegistryBindingV2):
    registry_ref: FinancialRegistryRefV2
    received_at: UTC
    parser_revision: Literal['owner-financial-csv-v1']
    exact_received_csv_sha256: Digest
    key_based_plan_digest: Digest
    preview_digest: Digest
    request_digest: Digest
    qualification: Literal['conditional_on_owner_supplied_data']='conditional_on_owner_supplied_data'
    _time=field_validator('received_at')(_utc)


class FinancialRegistryConfirmationData(_NoExecution):
    metadata: RegistryMetadataV2
    current: RegistryCurrentV2
    is_historical: bool
    public_projection_digest: Digest
    persisted: Literal[True]=True
    @field_validator('persisted',mode='before')
    @classmethod
    def persisted_true(cls,value):
        if value is not True:raise ValueError('literal true required')
        return value


class FinancialRegistryReadData(_NoExecution):
    metadata: RegistryMetadataV2
    current: RegistryCurrentV2
    is_historical: bool
    projection: PublicFinancialRegistryProjectionV2
    public_projection_digest: Digest


class FinancialRegistryHistoryItem(_RegistryOwnerDeclaration):
    registry_ref: FinancialRegistryRefV2
    input_revision: Revision
    problem_digest: Digest
    research_version_before: Annotated[StrictInt,Field(ge=1,le=2147483646)]
    research_version_after: Revision
    received_at: UTC
    is_historical: bool
    public_projection_digest: Digest
    qualification: Literal['conditional_on_owner_supplied_data']='conditional_on_owner_supplied_data'
    _time=field_validator('received_at')(_utc)
    @model_validator(mode='after')
    def versions(self):
        if self.research_version_after!=self.research_version_before+1:raise ValueError('registry version sequence')
        return self


class FinancialRegistryHistoryData(FrozenData):
    research_id: UUID4
    current: RegistryCurrentV2
    items: Annotated[tuple[FinancialRegistryHistoryItem,...],Field(max_length=20)]
    next_cursor: UUID4|None


class FinancialRegistryConfirmationResponse(FrozenData):
    schema_version: Literal['structure-research-v1']='structure-research-v1'
    contract_revision: Literal['financial-input-v2']=CONTRACT
    data: FinancialRegistryConfirmationData


class FinancialRegistryReadResponse(FrozenData):
    schema_version: Literal['structure-research-v1']='structure-research-v1'
    contract_revision: Literal['financial-input-v2']=CONTRACT
    data: FinancialRegistryReadData


class FinancialRegistryHistoryResponse(FrozenData):
    schema_version: Literal['structure-research-v1']='structure-research-v1'
    contract_revision: Literal['financial-input-v2']=CONTRACT
    data: FinancialRegistryHistoryData
