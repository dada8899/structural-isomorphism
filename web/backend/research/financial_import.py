"""Fixed CSV decoder and current-owner preview. No registry, calculation or writes."""
import csv
import hashlib
import io
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from pydantic import ValidationError

from .authorization import AccountIdentity
from .errors import ResearchError
from .financial_policy import FinancialError, canonical, number
from .financial_schemas import Period, day, hash_value, label, text
from .financial_input_schemas import (
    CONTRACT, PARSER_REVISION, CSV_HEADER, CSV_LIMIT, PLAN_LIMIT, FinancialImportError,
    FinancialImportPreviewRequest, FinancialImportPreviewResponse, FinancialImportPreviewData,
    OwnerFinancialImportPlanV2, OwnerSourceV2, OwnerObservationV2, OwnerHistoricalFXV2,
)

_SOURCE = ('url', 'locator', 'excerpt', 'declared_original_sha256', 'claimed_published_at', 'claimed_accessed_at', 'read_scope', 'source_chain')
_HISTORICAL = ('period_start', 'period_end', 'period_grain', 'value', 'declared_basis', 'source_refs')
_OBSERVATION = (*_HISTORICAL, 'entity_scope', 'scope_kind', 'metric', 'currency', 'unit', 'accounting_basis', 'alternative_refs')
_FX = (*_HISTORICAL, 'from_currency', 'to_currency', 'fx_kind')
_COLUMNS = {'source': _SOURCE, 'observation': _OBSERVATION, 'historical_fx': _FX}
_REQUIRED = {'source': ('url', 'locator', 'excerpt', 'read_scope'),
             'observation': tuple(v for v in _OBSERVATION if v not in ('value', 'source_refs', 'alternative_refs')),
             'historical_fx': tuple(v for v in _FX if v not in ('value', 'source_refs'))}
_MODELS = {'source': OwnerSourceV2, 'observation': OwnerObservationV2, 'historical_fx': OwnerHistoricalFXV2}
if TYPE_CHECKING:
    from .service import ResearchService
    from .paid_control import AuthenticatedActionSource


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _refs(value, *, row, field, cap):
    values = tuple(value.split(';')) if value else ()
    try:
        if len(values) > cap or len(set(values)) != len(values): raise ValueError()
        for ref in values: label(ref)
    except (ValueError, FinancialError):
        raise FinancialImportError('INVALID_REFERENCES', row=row, field=field) from None
    return values


def _scalars(data, row):
    caps={'url':1600,'locator':240,'excerpt':1000,'read_scope':700,'entity_scope':120,'accounting_basis':240}
    for field,cap in caps.items():
        if field in data:
            try:text(data[field],cap)
            except FinancialError:raise FinancialImportError('BOUNDED_TEXT',row=row,field=field) from None
    if data['row_type']=='source':
        try:
            url=urlsplit(data['url'])
            if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:raise ValueError()
        except ValueError:raise FinancialImportError('SOURCE_URL',row=row,field='url') from None
        for field in ('claimed_published_at','claimed_accessed_at','declared_original_sha256'):
            if data[field] is not None:
                try:(hash_value if field=='declared_original_sha256' else day)(data[field])
                except FinancialError:raise FinancialImportError('CLAIM_FORMAT',row=row,field=field) from None
        if data['claimed_published_at'] is not None and data['claimed_accessed_at'] is not None and day(data['claimed_accessed_at'])<day(data['claimed_published_at']):
            raise FinancialImportError('CLAIMED_DATE_ORDER',row=row,field='claimed_accessed_at')
        return
    if data['declared_basis'] in ('scenario_assumption','assumption','independent'):
        raise FinancialImportError('ASSUMPTION_IN_HISTORY',row=row,field='declared_basis')
    for field in ('period_start','period_end'):
        try:day(data[field])
        except FinancialError:raise FinancialImportError('ISO_DAY',row=row,field=field) from None
    try:Period(data['period_start'],data['period_end'],data['period_grain'])
    except FinancialError:raise FinancialImportError('FINANCIAL_PERIOD',row=row,field='period_grain') from None
    if data['declared_basis'] in ('missing','conflicted','disclosed','media_estimate') and ((data['declared_basis'] in ('missing','conflicted')) != (data['value'] is None)):
        raise FinancialImportError('BASIS_NULL_MISMATCH',row=row,field='declared_basis')
    if data['value'] is not None:
        try:value=number(data['value'])
        except FinancialError:raise FinancialImportError('DECIMAL_TEXT',row=row,field='value') from None
        if not data['source_refs']:raise FinancialImportError('SOURCE_REQUIRED',row=row,field='source_refs')
        if (data['row_type']=='historical_fx' and value<=0 or data['row_type']=='observation' and data['metric'] not in ('operating_profit','net_profit','operating_adjustment') and value<0):
            raise FinancialImportError('VALUE_SIGN',row=row,field='value')
    if data['row_type']=='historical_fx' and data['from_currency']==data['to_currency']:
        raise FinancialImportError('FX_DIRECTION',row=row,field='to_currency')


def _quote_syntax(value):
    # csv.reader(strict=True) still accepts quotes inside an unquoted field.
    # Require the fixed comma/double-quote grammar rather than guessing dialects.
    state, line = 'start', 1
    for char in value:
        if state == 'quoted':
            if char == '"': state = 'after_quote'
        elif state == 'after_quote':
            if char == '"': state = 'quoted'
            elif char == ',': state = 'start'
            elif char in '\r\n': state = 'start'
            else: raise FinancialImportError('CSV_SYNTAX', row=line)
        elif char == '"':
            if state != 'start': raise FinancialImportError('CSV_SYNTAX', row=line)
            state = 'quoted'
        elif char == ',' or char in '\r\n': state = 'start'
        else: state = 'unquoted'
        if char == '\n': line += 1
    if state == 'quoted': raise FinancialImportError('CSV_SYNTAX', row=line)


def _validate_graph(records):
    by_key = {row.key: row for row in records}
    for row in records:
        links = [('source_chain', row.source_chain, 'source')] if row.row_type == 'source' else [('source_refs', row.source_refs, 'source')]
        if row.row_type == 'observation': links.append(('alternative_refs', row.alternative_refs, 'observation'))
        for field, refs, kind in links:
            for ref in refs:
                other = by_key.get(ref)
                if other is None or other.row_type != kind:
                    raise FinancialImportError('REFERENCE_DOMAIN', row=row.physical_line_start, field=field)
                if field == 'alternative_refs':
                    names = ('entity_scope', 'scope_kind', 'metric', 'period_start', 'period_end', 'period_grain', 'accounting_basis')
                    if any(getattr(row, k) != getattr(other, k) for k in names):
                        raise FinancialImportError('INCOMPATIBLE_ALTERNATIVE', row=row.physical_line_start, field=field)
    for kind, field in (('source', 'source_chain'), ('observation', 'alternative_refs')):
        done = set()
        def visit(key, path):
            if key in path:
                raise FinancialImportError('REFERENCE_CYCLE', row=by_key[key].physical_line_start, field=field)
            if key in done: return
            for ref in getattr(by_key[key], field): visit(ref, path | {key})
            done.add(key)
        for row in records:
            if row.row_type == kind: visit(row.key, set())


def parse_owner_csv(csv_text: str) -> OwnerFinancialImportPlanV2:
    if type(csv_text) is not str:
        raise FinancialImportError('CSV_TEXT_REQUIRED')
    try: raw = csv_text.encode('utf-8')
    except UnicodeError: raise FinancialImportError('CSV_UTF8') from None
    if len(raw) > CSV_LIMIT: raise FinancialImportError('CSV_LIMIT', limit=True)
    if csv_text.startswith('\ufeff'): raise FinancialImportError('BOM_FORBIDDEN', row=1)
    _quote_syntax(csv_text)
    reader = csv.reader(io.StringIO(csv_text, newline=''), delimiter=',', quotechar='"', doublequote=True,
                        escapechar=None, skipinitialspace=False, strict=True)
    records, keys, counts = [], set(), {'source': 0, 'observation': 0, 'historical_fx': 0}
    try:
        if tuple(next(reader, ())) != CSV_HEADER: raise FinancialImportError('EXACT_HEADER_REQUIRED', row=1)
        while True:
            start = reader.line_num + 1
            values = next(reader, None)
            if values is None: break
            if not values: raise FinancialImportError('EMPTY_RECORD', row=start)
            if len(values) != len(CSV_HEADER): raise FinancialImportError('COLUMN_COUNT', row=start)
            row = dict(zip(CSV_HEADER, values)); kind = row['row_type']
            if kind not in _COLUMNS: raise FinancialImportError('ROW_TYPE', row=start, field='row_type')
            counts[kind] += 1
            if counts[kind] > {'source': 16, 'observation': 64, 'historical_fx': 16}[kind]:
                raise FinancialImportError('ROW_COUNT_LIMIT', row=start, field='row_type', limit=True)
            try: label(row['key'])
            except FinancialError: raise FinancialImportError('LOCAL_KEY', row=start, field='key') from None
            if row['key'] in keys: raise FinancialImportError('DUPLICATE_KEY', row=start, field='key')
            keys.add(row['key'])
            for field in CSV_HEADER[2:]:
                if field not in _COLUMNS[kind] and row[field] != '':
                    raise FinancialImportError('COLUMN_FORBIDDEN', row=start, field=field)
            for field in _REQUIRED[kind]:
                if row[field] == '': raise FinancialImportError('FIELD_REQUIRED', row=start, field=field)
            data = {field: row[field] for field in _COLUMNS[kind]}
            data.update(row_type=kind, key=row['key'], record_index=len(records) + 1,
                        physical_line_start=start, physical_line_end=reader.line_num)
            for field in ('source_chain', 'source_refs', 'alternative_refs'):
                if field in data: data[field] = _refs(data[field], row=start, field=field, cap=8 if field == 'alternative_refs' else 16)
            if kind == 'source':
                for field in ('declared_original_sha256', 'claimed_published_at', 'claimed_accessed_at'):
                    data[field] = data[field] or None
                data['received_excerpt_sha256'] = _sha(data['excerpt'].encode('utf-8'))
            else: data['value'] = data['value'] if data['value'] != '' else None
            _scalars(data,start)
            try: records.append(_MODELS[kind](**data))
            except ValidationError as error:
                location=error.errors(include_input=False,include_context=False)[0]['loc']
                field=location[0] if location and location[0] in CSV_HEADER else 'row_type'
                raise FinancialImportError('INVALID_DECLARATION',row=start,field=field) from None
            except (ValueError, UnicodeError):
                raise FinancialImportError('INVALID_DECLARATION', row=start, field='row_type') from None
    except csv.Error:
        raise FinancialImportError('CSV_SYNTAX', row=reader.line_num) from None
    _validate_graph(records)
    plan = OwnerFinancialImportPlanV2(records=tuple(records))
    if len(canonical(plan.model_dump(mode='json')).encode('utf-8')) > PLAN_LIMIT:
        raise FinancialImportError('PLAN_LIMIT', limit=True)
    return plan


def preview_import(service: 'ResearchService', identity: AccountIdentity, rid: str,
                   request: FinancialImportPreviewRequest, source: 'AuthenticatedActionSource') -> FinancialImportPreviewResponse:
    from .service import ResearchService
    from .store import ResearchStore
    from .paid_control import require_authenticated_action
    if type(service) is not ResearchService or type(service.store) is not ResearchStore or type(identity) is not AccountIdentity or type(request) is not FinancialImportPreviewRequest:
        raise PermissionError('actual financial preview context required')
    rid = service._id(rid)
    request_digest = _sha(canonical(request.model_dump(mode='json')).encode('utf-8'))
    require_authenticated_action(source, identity=identity, action='financial-import-preview', research_id=rid, body_digest=request_digest)
    with service.store.transaction() as conn:
        principal = service._principal_in(conn, identity)
        control = service.authorization.check(conn, identity, principal, rid, scope='write')
        if control['current_revision'] != request.input_revision or control['version'] != request.expected_research_version:
            raise ResearchError('VERSION_CONFLICT', 409, '问题已更新，请重新读取后预览。')
        problem = conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?', (rid, request.input_revision)).fetchone()
        if problem is None: raise ResearchError('STORE_UNAVAILABLE', 503, '当前问题无法核对。')
        plan = parse_owner_csv(request.csv_text)
        csv_digest = _sha(request.csv_text.encode('utf-8'))
        plan_digest = _sha(canonical(plan.model_dump(mode='json')).encode('utf-8'))
        binding = {'contract': CONTRACT, 'parser_revision': PARSER_REVISION, 'research_id': rid,
                   'input_revision': request.input_revision, 'problem_digest': problem['digest'],
                   'expected_research_version': request.expected_research_version,
                   'exact_received_csv_sha256': csv_digest, 'key_based_plan_digest': plan_digest}
        # Revalidate the actual action and account inside this same native RO snapshot.
        require_authenticated_action(source, identity=identity, action='financial-import-preview', research_id=rid, body_digest=request_digest)
        service.authorization.check(conn, identity, principal, rid, scope='write')
        return FinancialImportPreviewResponse(data=FinancialImportPreviewData(
            **{k: v for k, v in binding.items() if k != 'contract'},
            preview_digest=_sha(canonical(binding).encode('utf-8')), plan=plan))
