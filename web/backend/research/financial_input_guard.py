"""Financial-input protocol 2. Fixed native registry and owned-result writers."""
from contextlib import contextmanager
import json
import os
import sqlite3
import sys
import threading

from .errors import ResearchError

REGISTRIES='research_financial_registries'
RESULTS='research_financial_results'
PROTECTED=(REGISTRIES,RESULTS)
_WRITES={}


def _u(name):
    x=f"replace({name},'-','')"
    return f"{name} TEXT NOT NULL CHECK(typeof({name})='text' AND length({name})=36 AND length({x})=32 AND {x} NOT GLOB '*[^0-9a-f]*' AND substr({name},9,1)='-' AND substr({name},14,1)='-' AND substr({name},19,1)='-' AND substr({name},24,1)='-' AND substr({name},15,1)='4' AND substr({name},20,1) IN ('8','9','a','b'))"


def _h(name):
    return f"{name} TEXT NOT NULL CHECK(typeof({name})='text' AND length({name})=64 AND {name} NOT GLOB '*[^0-9a-f]*')"


def _v(name,low=1,high=2147483647):
    return f"{name} INTEGER NOT NULL CHECK(typeof({name})='integer' AND {name} BETWEEN {low} AND {high})"


def _j(name,cap,kind='object'):
    return f"{name} TEXT NOT NULL CHECK(typeof({name})='text' AND json_valid({name}) AND json_type({name})='{kind}' AND length(CAST({name} AS BLOB))<={cap})"


def _t(name):
    pattern='[0-9]'*4+'-'+'[0-9]'*2+'-'+'[0-9]'*2+'T'+'[0-9]'*2+':'+'[0-9]'*2+':'+'[0-9]'*2+'.'+'[0-9]'*6+'Z'
    return f"{name} TEXT NOT NULL CHECK(typeof({name})='text' AND length({name})=27 AND {name} GLOB '{pattern}')"


_COMMON=(
    _u('research_id'),_u('principal_id'),_v('input_revision'),_h('problem_digest'),
    _v('principal_epoch'),_v('owner_epoch'),_v('acl_epoch'),_h('auth_generation_digest'),
    _j('owner_gate_identity_json',1024,'array')+' CHECK(json_array_length(owner_gate_identity_json)=5)',
    _v('research_version_before',high=2147483646),_v('research_version_after')+' CHECK(research_version_after=research_version_before+1)',_h('request_digest'))
COMMON_COLUMNS=('research_id','principal_id','input_revision','problem_digest','principal_epoch','owner_epoch','acl_epoch','auth_generation_digest','owner_gate_identity_json','research_version_before','research_version_after','request_digest')
REGISTRY_COLUMNS=(*COMMON_COLUMNS,'registry_ref','registry_revision','format_version','parser_revision','received_ref','received_at','csv_text','exact_received_csv_sha256','key_based_plan_digest','preview_digest','key_map_json','registry_json','registry_digest')
RESULT_COLUMNS=(*COMMON_COLUMNS,'result_ref','result_type','registry_ref','registry_revision','registry_digest','run_id','recorded_at','policy_revision','producer_revision','execution_code_digest','execution_status','operations_used','operation_json','expectation_json','execution_receipt_json','snapshot_json','snapshot_digest')
COLUMNS={REGISTRIES:REGISTRY_COLUMNS,RESULTS:RESULT_COLUMNS}
KEYS={REGISTRIES:'registry_ref',RESULTS:'result_ref'}
_FKS=('FOREIGN KEY(research_id) REFERENCES research_controls(id)',
      'FOREIGN KEY(principal_id) REFERENCES research_principals(id)',
      'FOREIGN KEY(research_id,input_revision) REFERENCES research_revisions(research_id,revision)')
_BINDING='registry_ref,registry_revision,registry_digest,research_id,principal_id,input_revision,problem_digest'
TABLES=(
    'CREATE TABLE '+REGISTRIES+' ('+', '.join((*_COMMON,
        _u('registry_ref')+' PRIMARY KEY',_v('registry_revision',1,1),
        "format_version TEXT NOT NULL CHECK(format_version='owner-financial-registry-v2')",
        "parser_revision TEXT NOT NULL CHECK(parser_revision='owner-financial-csv-v1')",
        _u('received_ref')+' UNIQUE',_t('received_at'),
        "csv_text TEXT NOT NULL CHECK(typeof(csv_text)='text' AND length(CAST(csv_text AS BLOB))<=131072)",
        _h('exact_received_csv_sha256'),_h('key_based_plan_digest'),_h('preview_digest'),_j('key_map_json',32768,'array'),
        _j('registry_json',131072),_h('registry_digest'),'UNIQUE('+_BINDING+')',*_FKS))+')',
    'CREATE TABLE '+RESULTS+' ('+', '.join((*_COMMON,
        _u('result_ref')+' PRIMARY KEY',"result_type TEXT NOT NULL CHECK(result_type='financial_scenario_v2')",
        _u('registry_ref'),_v('registry_revision',1,1),_h('registry_digest'),_u('run_id')+' UNIQUE',_t('recorded_at'),
        "policy_revision TEXT NOT NULL CHECK(length(policy_revision) BETWEEN 1 AND 128 AND length(CAST(policy_revision AS BLOB))=length(policy_revision))",
        "producer_revision TEXT NOT NULL CHECK(length(producer_revision) BETWEEN 1 AND 128 AND length(CAST(producer_revision AS BLOB))=length(producer_revision))",
        _h('execution_code_digest'),"execution_status TEXT NOT NULL CHECK(execution_status='completed')",_v('operations_used',0,5000),
        _j('operation_json',65536),_j('expectation_json',8192),_j('execution_receipt_json',8192),_j('snapshot_json',131072),_h('snapshot_digest'),
        'CHECK(length(CAST(operation_json AS BLOB))+length(CAST(expectation_json AS BLOB))+length(CAST(execution_receipt_json AS BLOB))+length(CAST(snapshot_json AS BLOB))<=131072)',
        *_FKS,'FOREIGN KEY('+_BINDING+') REFERENCES '+REGISTRIES+'('+_BINDING+')'))+')')


def _declarations():
    ddls=[*TABLES,
        'CREATE INDEX research_financial_registry_history ON '+REGISTRIES+'(research_id,principal_id,received_at DESC,registry_ref DESC)',
        'CREATE INDEX research_financial_registry_owner ON '+REGISTRIES+'(principal_id,registry_ref)',
        'CREATE INDEX research_financial_result_history ON '+RESULTS+'(research_id,principal_id,recorded_at DESC,result_ref DESC)',
        'CREATE INDEX research_financial_result_owner ON '+RESULTS+'(principal_id,result_ref)',
        'CREATE INDEX research_financial_result_registry ON '+RESULTS+'(registry_ref)']
    for table in PROTECTED:
        def image(prefix):return 'json_array('+','.join(prefix+'.'+k for k in COLUMNS[table])+')'
        for op,prefix in (('INSERT','NEW'),('DELETE','OLD')):
            ddls.append(f"CREATE TRIGGER {table}_{op.lower()}_control BEFORE {op} ON {table} BEGIN SELECT CASE WHEN research_financial_input_allowed('{table}','{op}',{image(prefix)})!=1 THEN RAISE(ABORT,'actual financial input producer required') END; END")
        ddls.append(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'immutable financial input'); END")
        unique=('registry_ref','received_ref') if table==REGISTRIES else ('result_ref','run_id')
        duplicates=' OR '.join(('NEW.rowid=OLD.rowid',*(f'NEW.{k}=OLD.{k}' for k in unique)))
        ddls.append(f"CREATE TRIGGER {table}_no_replace BEFORE INSERT ON {table} WHEN EXISTS(SELECT 1 FROM {table} AS OLD WHERE {duplicates}) BEGIN SELECT RAISE(ABORT,'financial input replacement forbidden'); END")
    return tuple(ddls)


DDL=_declarations()


def _validate(entry):
    from .paid_control import _current_scope,_owner_binding,require_authenticated_action,verify_deletion_origin
    from .provider_schemas import digest
    from .financial_input import confirmation_digest,_decode_row
    conn,service,lease=entry['conn'],entry['service'],entry['lease']
    if (entry['pid']!=os.getpid() or entry['thread']!=threading.get_ident() or _current_scope(conn) is not entry['scope']):
        raise PermissionError('financial input scope retired')
    values=dict(zip(COLUMNS[entry['table']],entry['values']))
    principal=_owner_binding(conn,service.store,values['principal_id'],lease)
    if entry['operation']=='DELETE':
        job=verify_deletion_origin(conn,store=service.store,lease=lease,job_id=entry['job_id'])
        if (not job or job['state']!='pending' or principal['status']!='deleting'
                or principal['normalized_email']!=job['owner_email'] or principal['session_generation']!=job['session_generation']):
            raise PermissionError('actual pending financial input deletion required')
        row=conn.execute('SELECT '+','.join(COLUMNS[entry['table']])+' FROM '+entry['table']+' WHERE '+KEYS[entry['table']]+'=?',(values[KEYS[entry['table']]],)).fetchone()
        if row is None or tuple(row)!=entry['values']:raise PermissionError('financial deletion row changed')
        return
    if entry['table']==RESULTS and entry['operation']=='INSERT':
        from .financial_execution import validate_insert,_function
        _function(validate_insert)(entry,values)
        return
    if entry['table']!=REGISTRIES or entry['operation']!='INSERT':raise PermissionError('financial producer unavailable')
    identity=entry['identity']
    require_authenticated_action(entry['source'],identity=identity,action='financial-registry-save',research_id=values['research_id'],key=entry['key'],body_digest=confirmation_digest(entry['request']))
    control=service.authorization.check(conn,identity,values['principal_id'],values['research_id'],scope='write')
    if (control['current_revision']!=values['input_revision'] or control['version']!=values['research_version_before']
            or principal['epoch']!=values['principal_epoch'] or control['owner_epoch']!=values['owner_epoch'] or control['acl_epoch']!=values['acl_epoch']
            or digest(identity.generation.encode())!=values['auth_generation_digest'] or list(lease.identity)!=json.loads(values['owner_gate_identity_json'])):
        raise PermissionError('financial registry creation domain changed')
    _decode_row(conn,values)


def install_hook(conn):
    pid=os.getpid()
    def allowed(table,operation,raw):
        entry=_WRITES.get(id(conn))
        if (not entry or pid!=os.getpid() or entry['conn'] is not conn or not conn.in_transaction
                or entry['table']!=table or entry['operation']!=operation):return 0
        try:
            # Reject probes/wrong images before _current_scope's v15 hook check.
            if type(raw) is not str or len(raw.encode('utf-8'))>1048576 or json.loads(raw)!=list(entry['values']):return 0
            _validate(entry)
            return 1
        except (PermissionError,ResearchError,ValueError,TypeError,OSError,sqlite3.Error):return 0
    conn.create_function('research_financial_input_allowed',3,allowed)
    conn.create_function('research_financial_input_guard_version',0,lambda:2 if pid==os.getpid() else 0)


def require_hook(conn):
    try:row=conn.execute("SELECT research_financial_input_guard_version(),research_financial_input_allowed('','INSERT','[]'),research_financial_input_allowed('research_financial_results','INSERT','[]')").fetchone()
    except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'财务输入连接守卫不可用。') from None
    if tuple(row)!=(2,0,0):raise ResearchError('SCHEMA_UNSUPPORTED',503,'财务输入连接守卫不匹配。')


def statement_allowed(conn,action,table,column):
    if action not in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE) or table not in PROTECTED:return True
    if action==sqlite3.SQLITE_UPDATE:return False
    entry=_WRITES.get(id(conn))
    return bool(entry and entry['conn'] is conn and entry['table']==table and entry['pid']==os.getpid()
                and entry['thread']==threading.get_ident() and entry['scope'].active and conn.in_transaction
                and entry['operation']==('INSERT' if action==sqlite3.SQLITE_INSERT else 'DELETE'))


@contextmanager
def _write_scope(conn,service,lease,table,operation,values,*,identity=None,source=None,key=None,request=None,job_id=None,execution=None,owned_return=None):
    from . import financial_input
    from .service import ResearchService
    from .store import ResearchStore
    from .authorization import OwnerGateLease
    from .paid_control import _current_scope
    if __package__=='web.backend.research':from ..services.sqlite_utils import PrivateAuthConnection
    else:from services.sqlite_utils import PrivateAuthConnection
    frame=sys._getframe(1)
    try:
        owner_module=financial_input
        if table==RESULTS and operation=='INSERT':
            from . import financial_result_v2
            owner_module=financial_result_v2;producer=financial_result_v2._CALCULATE_PRODUCER
            from .financial_execution import _function
            _function(producer)
        else:producer=financial_input._WRITE_PRODUCERS[0 if operation=='INSERT' else 1]
        while frame is not None and frame.f_code is not producer.__code__:frame=frame.f_back
        if (not frame or frame.f_globals is not vars(owner_module) or frame.f_locals.get('conn') is not conn or frame.f_locals.get('lease') is not lease or frame.f_locals.get('service') is not service):
            raise PermissionError('fixed financial input producer required')
    finally:del frame
    if (type(service) is not ResearchService or type(service.store) is not ResearchStore or type(lease) is not OwnerGateLease
            or type(conn) is not PrivateAuthConnection or service.store.storage_identity is None
            or conn.private_storage_identity!=service.store.storage_identity or table not in PROTECTED
            or operation not in ('INSERT','DELETE') or id(conn) in _WRITES):
        raise PermissionError('actual native financial input transaction required')
    scope=_current_scope(conn)
    entry={'conn':conn,'service':service,'lease':lease,'table':table,'operation':operation,'values':tuple(values),
           'identity':identity,'source':source,'key':key,'request':request,'job_id':job_id,'scope':scope,'pid':os.getpid(),'thread':threading.get_ident(),
           'execution':execution,'owned_return':owned_return}
    _validate(entry);_WRITES[id(conn)]=entry;scope.refresh_authorizer()
    try:yield
    finally:_WRITES.pop(id(conn),None);scope.refresh_authorizer()
