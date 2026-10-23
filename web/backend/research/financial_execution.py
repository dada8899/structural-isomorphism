"""Fixed local financial producer. No provider, external I/O or paid admission."""
import hashlib
import importlib
import os
from pathlib import Path
import sys
import threading
import time
import types
from uuid import uuid4

from .financial_policy import POLICY,Meter,canonical,digest,FinancialError,FinancialResourceLimit

PRODUCER='owned-financial-local-v2-r1'
PROFILE='financial-scenario-owner-v2'
_FACTORY=object()
_CONTEXTS={}
_RETURNS={}
_CODE_FILES=('financial_execution.py','financial_result_v2.py','financial_evaluator.py','financial_policy.py',
    'financial_schemas.py','financial_input_schemas.py','financial_input.py','financial_input_guard.py','financial_import.py')


def _function(function):
    module=sys.modules.get(function.__module__)
    path=Path(getattr(module,'__file__','')).resolve()
    if (type(function) is not types.FunctionType or function.__globals__ is not vars(module)
            or Path(function.__code__.co_filename).resolve()!=path or path.is_symlink()
            or not path.is_relative_to(Path(__file__).resolve().parents[1]) or path.stat().st_size>1048576):
        raise PermissionError('canonical native function required')
    def codes(code):
        yield code
        for value in code.co_consts:
            if type(value) is types.CodeType:yield from codes(value)
    found=[c for c in codes(compile(path.read_bytes(),function.__code__.co_filename,'exec',dont_inherit=True))
        if c.co_qualname==function.__qualname__]
    if len(found)!=1 or found[0]!=function.__code__:raise PermissionError('native function source changed')
    return function


def require_calculate_frame(values):
    from . import financial_result_v2 as result
    function=_function(result._CALCULATE_PRODUCER)
    frame=sys._getframe(1)
    try:
        while frame and frame.f_code is not function.__code__:frame=frame.f_back
        if not frame or frame.f_globals is not vars(result) or any(frame.f_locals.get(k) is not v for k,v in values.items()):
            raise PermissionError('fixed calculation frame required')
    finally:del frame


def _main_binding(app,service):
    from .runtime_profile import require_formal_application
    _function(require_formal_application)(app,'research_basic')
    family='web.backend.services' if __package__=='web.backend.research' else 'services'
    module=importlib.import_module(family+'.formal_admission')
    expected=Path(__file__).resolve().parents[1]/'services/formal_admission.py'
    if Path(module.__file__).resolve()!=expected or Path(module.__file__).is_symlink():raise PermissionError('canonical Main module required')
    _function(module.require)(app,'research_basic')
    binding=module._STATE.get(id(app))
    if (type(binding) is not module._Binding or binding.factory is not module._FACTORY or binding.app is not app
            or binding.pid!=os.getpid() or not binding.active or binding.retired):raise PermissionError('actual Main binding required')
    _function(type(binding).check)(binding)
    other=binding.service.store;store=service.store
    if (type(store) is not type(other) or store.path!=other.path or store.storage_identity!=other.storage_identity
            or store.auth_store is not other.auth_store or store.storage_identity is None):
        raise PermissionError('same Main private storage required')
    return binding


def require_request(service,identity,rid,envelope,key,source,request_app):
    from starlette.requests import Request
    from . import financial_result_v2 as result
    from .service import ResearchService
    from .store import ResearchStore
    from .authorization import AccountIdentity,AuthorizationGate
    from .paid_control import require_authenticated_action
    family='web.backend.api' if __package__=='web.backend.research' else 'api'
    route=importlib.import_module(family+'.research')
    bridge=_function(route._FINANCIAL_BRIDGE);endpoint=_function(route.calculate_research_financial)
    if (type(service) is not ResearchService or type(service.store) is not ResearchStore or type(identity) is not AccountIdentity
            or type(service.authorization) is not AuthorizationGate or service.authorization.store is not service.store
            or type(envelope) is not result.FinancialCalculationEnvelopeV2):raise PermissionError('actual account calculation required')
    for fn in (ResearchService._principal_in,AuthorizationGate.check,AuthorizationGate.check_account,
            require_authenticated_action,route._identity,result._CALCULATE_PRODUCER):_function(fn)
    frame=sys._getframe(1)
    try:
        while frame and frame.f_code is not bridge.__code__:frame=frame.f_back
        values={'service':service,'identity':identity,'rid':rid,'envelope':envelope,'key':key,'source':source}
        if (not frame or frame.f_globals is not vars(route) or any(frame.f_locals.get(k) is not v for k,v in values.items())):
            raise PermissionError('actual financial Request frame required')
        request=frame.f_locals.get('request')
    finally:del frame
    if (type(request) is not Request or request.app is not request_app or request.method!='POST'
            or request.scope.get('endpoint') is not endpoint or getattr(request.scope.get('route'),'endpoint',None) is not endpoint
            or request.path_params.get('research_id')!=rid or request.query_params
            or request.headers.get('idempotency-key')!=key):raise PermissionError('actual financial route binding required')
    parsed=result.decode_financial_calculation(getattr(request,'_body',None))
    if parsed.data_dict()!=envelope.data_dict():raise PermissionError('financial request body changed')
    require_authenticated_action(source,identity=identity,action='financial-calculate',research_id=rid,key=key,
        body_digest=digest(envelope.data_dict()))
    return request,_main_binding(request_app,service)


def require_native_scope(conn,service,identity,pid,lease):
    from .authorization import OwnerGateLease
    from .paid_control import _current_scope,_owner_binding
    from .runtime_profile import inspect_formal_profile
    family='web.backend.services' if __package__=='web.backend.research' else 'services'
    module=importlib.import_module(family+'.sqlite_utils')
    if (type(conn) is not module.PrivateAuthConnection or type(lease) is not OwnerGateLease
            or conn.private_storage_identity!=service.store.storage_identity
            or type(conn.execute) is not types.BuiltinMethodType):raise PermissionError('actual private transaction required')
    scope=_function(_current_scope)(conn)
    if not scope.write:raise PermissionError('financial write scope required')
    _function(inspect_formal_profile)(conn)
    principal=_function(_owner_binding)(conn,service.store,pid,lease)
    service.authorization.check_account(conn,identity)
    return scope,principal


def _code_digest():
    root=Path(__file__).resolve().parent;values={}
    for name in sorted(_CODE_FILES):
        path=root/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1048576:raise PermissionError('fixed code closure required')
        values[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return digest(values)


class CurrentFinancialExecution:
    __slots__=('_entry','_owned','_started')
    def __init__(self,entry,*,_factory=None):
        frame=sys._getframe(1)
        if _factory is not _FACTORY or frame.f_code is not begin.__code__ or frame.f_globals is not globals():
            raise TypeError('fixed calculation context birth required')
        object.__setattr__(self,'_entry',entry);object.__setattr__(self,'_owned',None);object.__setattr__(self,'_started',False)
        _CONTEXTS[id(self)]=self
    def __setattr__(self,*args):raise TypeError('financial execution immutable')
    def __reduce__(self):raise TypeError('financial execution cannot be serialized')
    @property
    def envelope(self):return self._entry['envelope']
    def require(self):
        e=getattr(self,'_entry',None)
        if (_CONTEXTS.get(id(self)) is not self or not e or e['pid']!=os.getpid() or e['thread']!=threading.get_ident()):
            raise PermissionError('financial execution retired')
        require_calculate_frame({k:e[k] for k in ('conn','service','identity','rid','envelope','lease','source','registry')})
        request,binding=require_request(e['service'],e['identity'],e['rid'],e['envelope'],e['key'],e['source'],e['app'])
        scope,principal=require_native_scope(e['conn'],e['service'],e['identity'],e['principal_id'],e['lease'])
        if (request is not e['request'] or binding is not e['main'] or scope is not e['scope']
                or tuple(e['lease'].identity)!=e['gate'] or _code_digest()!=e['code_digest']):raise PermissionError('financial native origin changed')
        resolved=e['registry'].require()
        if resolved['conn'] is not e['conn'] or resolved['scope'] is not scope:raise PermissionError('registry scope changed')
        control=e['service'].authorization.check(e['conn'],e['identity'],e['principal_id'],e['rid'],scope='write')
        e['service'].authorization.check(e['conn'],e['identity'],e['principal_id'],e['rid'],scope='read')
        for name,value in (('current_revision',e['envelope'].data.input_revision),('version',e['before']),
                ('owner_epoch',e['owner_epoch']),('acl_epoch',e['acl_epoch'])):
            if control[name]!=value:raise PermissionError('financial current authorization changed')
        if principal['epoch']!=e['principal_epoch']:raise PermissionError('financial principal changed')
        return e
    def close(self):
        if self._owned is not None:_RETURNS.pop(id(self._owned),None)
        _CONTEXTS.pop(id(self),None);self._entry.clear()


class OwnedFinancialReturnV2:
    __slots__=('_context','_stored')
    def __init__(self,context,stored,*,_factory=None):
        frame=sys._getframe(1)
        if _factory is not _FACTORY or frame.f_code is not execute.__code__ or frame.f_globals is not globals():
            raise TypeError('actual financial completion required')
        object.__setattr__(self,'_context',context);object.__setattr__(self,'_stored',stored)
        _RETURNS[id(self)]=self
    def __setattr__(self,*args):raise TypeError('financial return immutable')
    def __reduce__(self):raise TypeError('financial return cannot be serialized')
    @property
    def stored(self):
        if _RETURNS.get(id(self)) is not self or self._context._owned is not self:raise PermissionError('financial return retired')
        return self._stored


def begin(conn,service,identity,rid,envelope,key,source,lease,registry,request_app):
    from .service import now
    require_calculate_frame({'conn':conn,'service':service,'identity':identity,'rid':rid,'envelope':envelope,
        'key':key,'source':source,'lease':lease,'registry':registry,'request_app':request_app})
    request,binding=require_request(service,identity,rid,envelope,key,source,request_app)
    resolved=registry.require();pid=resolved['principal_id']
    scope,principal=require_native_scope(conn,service,identity,pid,lease)
    if resolved['conn'] is not conn or resolved['scope'] is not scope:raise PermissionError('actual resolved origin required')
    control=service.authorization.check(conn,identity,pid,rid,scope='write')
    entry={'conn':conn,'service':service,'identity':identity,'rid':rid,'envelope':envelope,'key':key,'source':source,
        'lease':lease,'registry':registry,'request':request,'app':request_app,'main':binding,'scope':scope,'principal_id':pid,
        'principal_epoch':principal['epoch'],'owner_epoch':control['owner_epoch'],'acl_epoch':control['acl_epoch'],
        'before':control['version'],'gate':tuple(lease.identity),'pid':os.getpid(),'thread':threading.get_ident(),
        'code_digest':_code_digest(),'run_id':str(uuid4()),'result_ref':str(uuid4()),'transaction_ref':str(uuid4())}
    return CurrentFinancialExecution(entry,_factory=_FACTORY)


def execute(context,request,registry):
    from . import financial_result_v2 as data,financial_evaluator as engine
    from .service import now
    from .financial_input import ResolvedOwnerFinancialRegistryV2
    if type(context) is not CurrentFinancialExecution or type(registry) is not ResolvedOwnerFinancialRegistryV2:
        raise PermissionError('native financial execution required')
    e=_function(type(context).require)(context)
    if context._started or context._owned is not None or request is not e['envelope'].data.request or registry is not e['registry']:
        raise PermissionError('single fixed financial execution required')
    object.__setattr__(context,'_started',True)
    _function(engine.evaluate_owner_financial_v2)
    owner=registry.owner_data;started_at=now();started_ns=time.monotonic_ns();meter=Meter()
    snapshot=engine.evaluate_owner_financial_v2(e['envelope'],owner,meter=meter)
    data.validate_snapshot(e['envelope'],owner,snapshot)
    if time.monotonic()>meter.deadline or snapshot.operations_used!=meter.operations:
        raise FinancialResourceLimit('financial completion deadline or count')
    completed=now();elapsed=time.monotonic_ns()-started_ns
    recorded=completed;ref=e['envelope'].data.registry_ref.model_dump(mode='json')
    origin=digest({'registry_ref':ref,'parser_revision':owner.parser_revision,**owner.receipt.model_dump(mode='json')})
    row={'research_id':e['rid'],'principal_id':e['principal_id'],'input_revision':e['envelope'].data.input_revision,
        'problem_digest':owner.binding.problem_digest,'principal_epoch':e['principal_epoch'],'owner_epoch':e['owner_epoch'],
        'acl_epoch':e['acl_epoch'],'auth_generation_digest':hashlib.sha256(e['identity'].generation.encode()).hexdigest(),
        'owner_gate_identity':list(e['gate']),'research_version_before':e['before'],'research_version_after':e['before']+1,
        'request_digest':snapshot.request_digest,'result_ref':e['result_ref'],'result_type':'financial_scenario_v2',
        'registry_ref':ref['id'],'registry_revision':ref['revision'],'registry_digest':ref['digest'],'run_id':e['run_id'],
        'recorded_at':recorded,'policy_revision':POLICY,'producer_revision':PRODUCER,'execution_code_digest':e['code_digest'],
        'execution_status':'completed','operations_used':meter.operations,'snapshot_digest':snapshot.digest}
    receipt={'receipt_schema':'financial-local-execution-v2','producer_revision':PRODUCER,'execution_profile':PROFILE,
        'policy_revision':POLICY,'execution_code_digest':e['code_digest'],'run_id':e['run_id'],'status':'completed',
        'http':{'action':'financial-calculate','method':'POST','endpoint':'calculate_research_financial','source_ref':e['source'].reference,
            'key_digest':e['source'].key_digest,'request_digest':snapshot.request_digest,
            'session_jti_digest':hashlib.sha256(e['identity'].jti.encode()).hexdigest(),'session_expires_at':e['identity'].expires_at},
        'binding':{**{k:row[k] for k in ('research_id','principal_id','principal_epoch','auth_generation_digest','owner_epoch','acl_epoch','input_revision','problem_digest')},
            'registry_ref':ref,'registry_origin_digest':origin},
        'native':{'pid':e['pid'],'thread_id':e['thread'],'transaction_ref':e['transaction_ref'],'main_binding_ref':e['main'].reference,
            'database_identity':list(e['service'].store.storage_identity),'owner_gate_identity':list(e['gate'])},
        'parameters_digest':snapshot.parameters_digest,'evaluation_input_digest':snapshot.evaluation_input_digest,'snapshot_digest':snapshot.digest,
        'timing':{'started_at':started_at,'completed_at':completed,'recorded_at':recorded,'elapsed_monotonic_ns':elapsed},
        'guard':{'kind':'cooperative','deadline_ms':2000,'max_operations':5000,'operations_used':meter.operations,'os_isolation_attested':False},
        'qualification':'conditional_on_owner_supplied_data','model_analysis_ran':False}
    expectation={k:row[k] for k in ('result_ref','research_id','principal_id','input_revision','problem_digest','request_digest',
        'producer_revision','policy_revision','execution_code_digest','run_id','snapshot_digest','recorded_at','research_version_before','research_version_after')}
    expectation.update(expectation_schema='financial-result-expectation-v2',registry_ref=ref,parameters_digest=snapshot.parameters_digest,
        evaluation_input_digest=snapshot.evaluation_input_digest,execution_profile=PROFILE,receipt_digest=digest(receipt),
        calculation_status='calculated_under_assumptions',qualification='conditional_on_owner_supplied_data',
        u2_goal_status=data._u2_status(snapshot),model_analysis_ran=False)
    stored=data.StoredFinancialResultV2.model_validate_json(data.bounded({'row_binding':row,'operation':e['envelope'].data_dict(),
        'expectation':expectation,'execution_receipt':receipt,'snapshot':snapshot.data()},131072))
    stored=data._validate_stored(stored,owner)
    if time.monotonic()>meter.deadline:raise FinancialResourceLimit('financial final deadline')
    owned=OwnedFinancialReturnV2(context,stored,_factory=_FACTORY);object.__setattr__(context,'_owned',owned)
    return owned


def validate_insert(entry,values):
    from .financial_result_v2 import _saved_values,_validate_stored
    context=entry.get('execution');owned=entry.get('owned_return')
    if (type(context) is not CurrentFinancialExecution or type(owned) is not OwnedFinancialReturnV2
            or _RETURNS.get(id(owned)) is not owned or context._owned is not owned or owned._context is not context):
        raise PermissionError('actual owned financial completion required')
    e=_function(type(context).require)(context)
    if any(entry.get(k) is not e[k] for k in ('conn','service','lease','identity','source','key','request') if k not in ('request',)):
        raise PermissionError('financial insert scope differs')
    if entry.get('request') is not e['envelope'] or entry['scope'] is not e['scope']:
        raise PermissionError('financial insert operation differs')
    _validate_stored(owned.stored,e['registry'].owner_data)
    if values!=_saved_values(owned.stored):raise PermissionError('financial insert image differs')


def consume(owned):
    from . import financial_result_v2 as result
    require_calculate_frame({'owned':owned})
    if type(owned) is not OwnedFinancialReturnV2 or _RETURNS.pop(id(owned),None) is not owned:
        raise PermissionError('financial return already consumed')
