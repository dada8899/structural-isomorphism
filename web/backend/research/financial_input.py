"""Native owner-supplied registry storage. No calculations, provider or result birth."""
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from uuid import uuid4
from typing import Literal,TypedDict

from .authorization import AccountIdentity
from .errors import ResearchError,not_found
from .financial_policy import canonical
from .financial_import import parse_owner_csv,_preview_binding
from . import financial_input_schemas as types
from .financial_input_guard import REGISTRIES,RESULTS,COLUMNS,KEYS,_write_scope


class FinancialInputProvisionReceipt(TypedDict):
    schema_version: Literal[15]
    financial_protocol: Literal[9]
    financial_input_protocol: Literal[2]
    journal_mode: Literal['wal']
    database_identity: list[int]
    backup_scope: Literal['in_memory_algorithm_recovery_only']


def _hash(value):return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _json(raw,cap):
    if type(raw) is not str or len(raw.encode('utf-8'))>cap:raise ValueError('bounded stored JSON required')
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:raise ValueError('duplicate key')
            out[key]=value
        return out
    def reject(_):raise ValueError('strict number required')
    value=json.loads(raw,object_pairs_hook=pairs,parse_float=reject,parse_constant=reject,
                     parse_int=lambda s:int(s) if len(s.lstrip('-'))<=20 else reject(s))
    types._json_shape(value)
    if canonical(value)!=raw:raise ValueError('noncanonical stored JSON')
    return value


def confirmation_digest(request):
    envelope={'schema_version':'structure-research-v1','contract_revision':types.CONTRACT,'data':request.model_dump(mode='json')}
    checked=types.decode_financial_registry_confirmation(canonical(envelope).encode('utf-8'))
    return _hash(checked.model_dump(mode='json'))


def history_query(pairs):
    if len(pairs)>2 or len({k for k,_ in pairs})!=len(pairs) or any(k not in ('limit','cursor') for k,_ in pairs):
        raise types.FinancialImportError('INVALID_JSON_OR_FIELDS',field='request')
    values=dict(pairs);limit=values.get('limit','20');cursor=values.get('cursor')
    if type(limit) is not str or re.fullmatch(r'[1-9]|1[0-9]|20',limit,re.ASCII) is None:
        raise types.FinancialImportError('INVALID_JSON_OR_FIELDS',field='request')
    if cursor is not None:
        from .service import ResearchService
        try:ResearchService._id(cursor)
        except ResearchError:raise types.FinancialImportError('INVALID_JSON_OR_FIELDS',field='request') from None
    return int(limit),cursor


def _context(conn,service,identity,rid,*,write=False):
    pid=service._principal_in(conn,identity)
    control=service.authorization.check(conn,identity,pid,rid,scope='write' if write else 'read')
    return pid,control


def _decode_row(conn,row):
    """Verify immutable private bytes; this function does not grant a scope."""
    data=_json(row['registry_json'],131072)
    body=types.OwnerFinancialRegistryV2.model_validate_json(canonical(data))
    if _hash(data)!=row['registry_digest'] or canonical(body.model_dump(mode='json'))!=row['registry_json']:
        raise ValueError('registry digest differs')
    if (body.format_version!=row['format_version'] or body.parser_revision!=row['parser_revision']
            or body.identity.id!=row['registry_ref'] or body.identity.revision!=row['registry_revision']
            or any(getattr(body.binding,k)!=row[k] for k in ('research_id','input_revision','problem_digest','research_version_before','research_version_after'))
            or any(getattr(body.receipt,k)!=row[k] for k in ('received_ref','received_at','exact_received_csv_sha256','key_based_plan_digest','preview_digest'))
            or canonical([m.model_dump(mode='json') for m in body.key_map])!=row['key_map_json']):
        raise ValueError('registry scalar binding differs')
    gate=_json(row['owner_gate_identity_json'],1024)
    if type(gate) is not list or len(gate)!=5 or any(type(v) is not int or not 0<=v<2**64 for v in gate):raise ValueError('invalid stored owner identity')
    original=conn.execute('SELECT digest,problem_json FROM research_revisions WHERE research_id=? AND revision=?',(row['research_id'],row['input_revision'])).fetchone()
    if original is None or original['digest']!=row['problem_digest'] or _hash(json.loads(original['problem_json']))!=row['problem_digest']:
        raise ValueError('registry original problem differs')
    plan=parse_owner_csv(row['csv_text'])
    binding=_preview_binding(row['csv_text'],plan,row['research_id'],row['input_revision'],row['problem_digest'],row['research_version_before'])
    if (binding['exact_received_csv_sha256']!=row['exact_received_csv_sha256'] or binding['key_based_plan_digest']!=row['key_based_plan_digest'] or _hash(binding)!=row['preview_digest']):
        raise ValueError('registry original preview differs')
    reverse={m.registered_id:m.key for m in body.key_map};records=[]
    for registered in body.records:
        record=registered.model_dump(mode='json');record.pop('id')
        for field in ('source_chain','source_refs','alternative_refs'):
            if field in record:record[field]=[reverse[ref] for ref in record[field]]
        records.append(record)
    if records!=plan.model_dump(mode='json')['records']:raise ValueError('registry mapping or declaration differs')
    request=types.FinancialRegistryConfirmation(input_revision=row['input_revision'],expected_research_version=row['research_version_before'],csv_text=row['csv_text'],preview_digest=row['preview_digest'],confirmed=True)
    if confirmation_digest(request)!=row['request_digest']:raise ValueError('registry confirmation differs')
    return body


def _response(row,body,control):
    public=types.PublicOwnerFinancialRegistryV2(format_version='owner-financial-registry-public-v2',parser_revision=body.parser_revision,
        identity=body.identity,binding=body.binding,
        receipt=types.PublicRegistryReceiptV2(received_at=body.receipt.received_at,exact_received_csv_sha256=body.receipt.exact_received_csv_sha256,
            key_based_plan_digest=body.receipt.key_based_plan_digest,preview_digest=body.receipt.preview_digest),key_map=body.key_map,records=body.records)
    projection=types.PublicFinancialRegistryProjectionV2(csv_text=row['csv_text'],registry=public)
    metadata=types.RegistryMetadataV2(**body.binding.model_dump(),registry_ref=types.FinancialRegistryRefV2(id=body.identity.id,revision=1,digest=row['registry_digest']),
        received_at=row['received_at'],parser_revision=body.parser_revision,exact_received_csv_sha256=row['exact_received_csv_sha256'],key_based_plan_digest=row['key_based_plan_digest'],preview_digest=row['preview_digest'],request_digest=row['request_digest'])
    result=types.FinancialRegistryReadResponse(data=types.FinancialRegistryReadData(metadata=metadata,
        current=types.RegistryCurrentV2(input_revision=control['current_revision'],research_version=control['version']),
        is_historical=row['input_revision']!=control['current_revision'],projection=projection,public_projection_digest=_hash(projection.model_dump(mode='json'))))
    _response_cap(result, future=True)
    return result


def _response_cap(result,*,future=False):
    raw=canonical(result.model_dump(mode='json')).encode('utf-8');extra=0
    if future:
        current=result.data.current
        extra=sum(10-len(str(v)) for v in (current.input_revision,current.research_version))
        extra+=5-len(str(result.data.is_historical).lower())
    if len(raw)+extra>524288:raise ResearchError('PAYLOAD_LIMIT',413,'完整财务读回内容超过上限，请减少输入后重新预览。')


def _load(conn,service,identity,rid,ref):
    pid,control=_context(conn,service,identity,rid)
    row=conn.execute('SELECT * FROM '+REGISTRIES+' WHERE registry_ref=? AND research_id=? AND principal_id=?',(ref,rid,pid)).fetchone()
    if row is None:raise not_found()
    try:
        body=_decode_row(conn,row)
        if control['current_revision']<row['input_revision'] or control['version']<row['research_version_after']:
            raise ValueError('registry current version precedes creation')
        return _response(row,body,control)
    except (ValueError,TypeError,KeyError,RecursionError,types.FinancialImportError):
        raise ResearchError('STORE_UNAVAILABLE',503,'财务注册记录当前无法完整核对。') from None


def _confirmation(read):
    data=read.data
    result=types.FinancialRegistryConfirmationResponse(data=types.FinancialRegistryConfirmationData(metadata=data.metadata,current=data.current,is_historical=data.is_historical,public_projection_digest=data.public_projection_digest))
    _response_cap(result,future=True)
    return result


@contextmanager
def _save_transaction(service,pid):
    # Only the post-body commit/close acknowledgement is uncertain here.
    # Never repeat a write or claim a rollback after SQLite may have committed.
    ready=[False]
    try:
        with service.authorization.owner_gate(pid) as lease,service.store.transaction(write=True) as conn:
            yield conn,lease,ready
    except (ResearchError,sqlite3.Error,OSError,RuntimeError,ValueError):
        if ready[0]:
            raise ResearchError('RESPONSE_UNAVAILABLE',503,'响应暂时无法核对，操作可能已保存。请保留原操作标识，核对原记录。') from None
        raise


def save_registry(service,identity,rid,request:types.FinancialRegistryConfirmation,key,source)->types.FinancialRegistryConfirmationResponse:
    from .paid_control import require_authenticated_action
    from .service import ResearchService,now
    from .store import ResearchStore
    if type(service) is not ResearchService or type(service.store) is not ResearchStore or type(identity) is not AccountIdentity or type(request) is not types.FinancialRegistryConfirmation:
        raise PermissionError('actual registry confirmation required')
    rid=service._id(rid);request_digest=confirmation_digest(request)
    require_authenticated_action(source,identity=identity,action='financial-registry-save',research_id=rid,key=key,body_digest=request_digest)
    pid=service._principal(identity)
    with _save_transaction(service,pid) as (conn,lease,commit_ready):
        _,control=_context(conn,service,identity,rid,write=True)
        service.authorization.check(conn,identity,pid,rid,scope='read')
        replay=service._replay(conn,pid,'financial-registry-save','r:'+rid,key,request_digest)
        if replay is not None:
            if type(replay) is not dict or set(replay)!={'registry_ref'}:raise ResearchError('STORE_UNAVAILABLE',503,'财务保存回执当前无法核对。')
            saved=_load(conn,service,identity,rid,service._id(replay['registry_ref']))
            if saved.data.metadata.request_digest!=request_digest:raise ResearchError('STORE_UNAVAILABLE',503,'财务保存回执当前无法核对。')
            return _confirmation(saved)
        if control['version']>=2147483647:raise ResearchError('VERSION_CONFLICT',409,'研究版本已达上限。')
        if control['current_revision']!=request.input_revision or control['version']!=request.expected_research_version:
            raise ResearchError('REVISION_CONFLICT',409,'问题或版本已变化，请重新读取后预览。')
        original=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',(rid,request.input_revision)).fetchone()
        if original is None:raise ResearchError('STORE_UNAVAILABLE',503,'原问题当前无法核对。')
        plan=parse_owner_csv(request.csv_text)
        preview=_preview_binding(request.csv_text,plan,rid,request.input_revision,original['digest'],control['version'])
        if _hash(preview)!=request.preview_digest:raise ResearchError('REVISION_CONFLICT',409,'预览与确认内容不同，请重新预览。')
        ref,received=str(uuid4()),str(uuid4());at=now();mapping=[];records=[]
        ids={r.key:str(uuid4()) for r in plan.records}
        for row in plan.records:
            mapping.append(types.KeyMapEntryV2(key=row.key,row_type=row.row_type,registered_id=ids[row.key],record_index=row.record_index,physical_line_start=row.physical_line_start,physical_line_end=row.physical_line_end))
            record=row.model_dump(mode='json');record['id']=ids[row.key]
            for field in ('source_chain','source_refs','alternative_refs'):
                if field in record:record[field]=[ids[k] for k in record[field]]
            model={'source':types.RegisteredSourceV2,'observation':types.RegisteredObservationV2,'historical_fx':types.RegisteredFXV2}[row.row_type]
            records.append(model.model_validate_json(canonical(record)))
        body=types.OwnerFinancialRegistryV2(format_version='owner-financial-registry-v2',parser_revision=types.PARSER_REVISION,
            identity=types.RegistryIdentityV2(id=ref,revision=1),binding=types.RegistryBindingV2(research_id=rid,input_revision=request.input_revision,problem_digest=original['digest'],research_version_before=control['version'],research_version_after=control['version']+1),
            receipt=types.RegistryReceiptV2(received_ref=received,received_at=at,exact_received_csv_sha256=preview['exact_received_csv_sha256'],key_based_plan_digest=preview['key_based_plan_digest'],preview_digest=request.preview_digest),key_map=tuple(mapping),records=tuple(records))
        principal=conn.execute('SELECT * FROM research_principals WHERE id=?',(pid,)).fetchone()
        encoded=canonical(body.model_dump(mode='json'));map_json=canonical([v.model_dump(mode='json') for v in mapping])
        if len(encoded.encode())>131072 or len(map_json.encode())>32768:raise ResearchError('PAYLOAD_LIMIT',413,'完整财务注册内容超过上限。')
        values=dict(research_id=rid,principal_id=pid,input_revision=request.input_revision,problem_digest=original['digest'],principal_epoch=principal['epoch'],owner_epoch=control['owner_epoch'],acl_epoch=control['acl_epoch'],
            auth_generation_digest=hashlib.sha256(identity.generation.encode()).hexdigest(),owner_gate_identity_json=canonical(list(lease.identity)),research_version_before=control['version'],research_version_after=control['version']+1,request_digest=request_digest,
            registry_ref=ref,registry_revision=1,format_version=body.format_version,parser_revision=types.PARSER_REVISION,received_ref=received,received_at=at,csv_text=request.csv_text,
            exact_received_csv_sha256=preview['exact_received_csv_sha256'],key_based_plan_digest=preview['key_based_plan_digest'],preview_digest=request.preview_digest,key_map_json=map_json,registry_json=encoded,registry_digest=_hash(body.model_dump(mode='json')))
        _decode_row(conn,values)
        future={**dict(control),'version':control['version']+1};response=_confirmation(_response(values,body,future))
        columns=COLUMNS[REGISTRIES];ordered=tuple(values[k] for k in columns)
        with _write_scope(conn,service,lease,REGISTRIES,'INSERT',ordered,identity=identity,source=source,key=key,request=request):
            conn.execute('INSERT INTO '+REGISTRIES+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',ordered)
        require_authenticated_action(source,identity=identity,action='financial-registry-save',research_id=rid,key=key,body_digest=request_digest)
        service.authorization.check(conn,identity,pid,rid,scope='write')
        if conn.execute('UPDATE research_controls SET version=version+1,updated_at=? WHERE id=? AND version=? AND current_revision=?',(at,rid,control['version'],request.input_revision)).rowcount!=1:
            raise ResearchError('REVISION_CONFLICT',409,'研究已变化，未保存此财务注册。')
        service._remember(conn,pid,'financial-registry-save','r:'+rid,key,request_digest,{'registry_ref':ref})
        commit_ready[0]=True
        return response


def read_registry(service,identity,rid,ref,source)->types.FinancialRegistryReadResponse:
    from .paid_control import require_authenticated_action
    rid=service._id(rid);ref=service._id(ref)
    require_authenticated_action(source,identity=identity,action='financial-registry-read',research_id=rid,task_id=ref)
    with service.store.transaction() as conn:
        result=_load(conn,service,identity,rid,ref)
        require_authenticated_action(source,identity=identity,action='financial-registry-read',research_id=rid,task_id=ref)
        return result


def history(service,identity,rid,limit,cursor,source)->types.FinancialRegistryHistoryResponse:
    from .paid_control import require_authenticated_action
    rid=service._id(rid)
    if type(limit) is not int or not 1<=limit<=20:raise types.FinancialImportError(field='request')
    if cursor is not None:service._id(cursor)
    body_digest=_hash({'limit':limit,'cursor':cursor})
    require_authenticated_action(source,identity=identity,action='financial-registry-history',research_id=rid,body_digest=body_digest)
    with service.store.transaction() as conn:
        pid,control=_context(conn,service,identity,rid);args=[rid,pid];where=''
        if cursor is not None:
            try:anchor=_load(conn,service,identity,rid,cursor)
            except ResearchError as error:
                if error.code!='NOT_FOUND':raise
                raise ResearchError('REVISION_CONFLICT',409,'历史页已变化，请重新读取。') from None
            at=anchor.data.metadata.received_at;where=' AND (received_at<? OR (received_at=? AND registry_ref<?))';args.extend((at,at,cursor))
        rows=conn.execute('SELECT registry_ref FROM '+REGISTRIES+' WHERE research_id=? AND principal_id=?'+where+' ORDER BY received_at DESC,registry_ref DESC LIMIT ?',(*args,limit+1)).fetchall()
        items=[]
        for row in rows[:limit]:
            saved=_load(conn,service,identity,rid,row[0]).data;m=saved.metadata
            items.append(types.FinancialRegistryHistoryItem(registry_ref=m.registry_ref,input_revision=m.input_revision,problem_digest=m.problem_digest,research_version_before=m.research_version_before,research_version_after=m.research_version_after,received_at=m.received_at,is_historical=saved.is_historical,public_projection_digest=saved.public_projection_digest))
        result=types.FinancialRegistryHistoryResponse(data=types.FinancialRegistryHistoryData(research_id=rid,current=types.RegistryCurrentV2(input_revision=control['current_revision'],research_version=control['version']),items=tuple(items),next_cursor=rows[limit-1][0] if len(rows)>limit else None))
        _response_cap(result)
        require_authenticated_action(source,identity=identity,action='financial-registry-history',research_id=rid,body_digest=body_digest)
        return result


def erase_in(conn,service,lease,pid,job_id):
    counts={}
    for table in (RESULTS,REGISTRIES):
        rows=conn.execute('SELECT '+','.join(COLUMNS[table])+' FROM '+table+' WHERE principal_id=?',(pid,)).fetchall()
        for row in rows:
            with _write_scope(conn,service,lease,table,'DELETE',tuple(row),job_id=job_id):
                conn.execute('DELETE FROM '+table+' WHERE '+KEYS[table]+'=?',(row[KEYS[table]],))
        counts[table]=len(rows)
    return counts


def provision_financial_inputs_v15(path)->FinancialInputProvisionReceipt:
    from .formula_runtime import _offline_maintenance,_check_profile
    from .store import ResearchStore
    from .financial_input_guard import DDL
    with _offline_maintenance(path,(14,15)) as (target,cap):
        conn=cap.conn;cap.require(target);conn.execute('BEGIN EXCLUSIVE')
        try:
            version=_check_profile(conn,target,(14,15))
            if version==14:
                for sql in DDL:conn.execute(sql)
                if conn.execute('UPDATE research_schema SET version=15 WHERE id=1 AND version=14').rowcount!=1:raise PermissionError('financial input marker CAS failed')
            ResearchStore._check_v15(conn)
            if conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('financial input FK failure')
            cap.require(target);conn.commit()
        except BaseException:conn.rollback();raise
        identity=cap.identity
    return {'schema_version':15,'financial_protocol':9,'financial_input_protocol':2,'journal_mode':'wal','database_identity':list(identity),'backup_scope':'in_memory_algorithm_recovery_only'}


# Capture actual native producers once. Replacing an exported function with a
# caller wrapper cannot turn that wrapper's frame into a permitted writer.
_WRITE_PRODUCERS=(save_registry,erase_in)
