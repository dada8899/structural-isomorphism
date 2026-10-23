"""Canonical Main native-plan lifecycle and wait budgets. No import grants IO.

Budget facts only shorten native waits. They never replace Owner, SQL hooks,
financial producers or the sealed A/B authority and per-attempt consent chain.
"""
from dataclasses import dataclass
import hashlib
import importlib
import inspect
import math
import os
from pathlib import Path
import sqlite3
import stat
import sys
import threading
import _thread
import time
import types
from uuid import uuid4
from .errors import ResearchError
from . import native_live_grant as _LIVE_MODULE

_FACTORY=object()
_CONTEXTS=vars(sqlite3).setdefault('_structural_native_main_contexts_v1',{})
_SUPERVISORS=vars(sqlite3).setdefault('_structural_native_supervisors_v1',{})
_WORKERS={};_SLOTS={};_LIFECYCLES={};_THREADS={}
_CONTEXT_BIRTHS={};_SLOT_BIRTHS={};_LIFECYCLE_BIRTHS={}
_STOP_BIRTHS={};_STOP_SIGNALS={}
_COMPLETED_CLEANUPS={}
_THREAD_ALIVE=threading.Thread.is_alive
_THREAD_JOIN=threading.Thread.join


def _closed():return ResearchError('FUNDING_CLOSED',503,'原生后台执行尚未完成真实生命周期绑定；账户和合法历史仍可使用。')
def _uncertain():return ResearchError('CLEANUP_UNCERTAIN',503,'原生清场尚未证明；保留原句柄和债务，不会重发。')
def _busy():return ResearchError('STORE_BUSY',503,'原生受限等待暂不可用；保留原记录。',retryable=True)
def _family():return 'web.backend.services' if __package__=='web.backend.research' else 'services'
def _module(name,relative):
    value=importlib.import_module(name);expected=Path(__file__).resolve().parents[1]/relative
    if type(value) is not types.ModuleType or Path(value.__file__).resolve()!=expected or Path(value.__file__).is_symlink():raise _closed()
    return value

def _admission():return _module(_family()+'.formal_admission',Path('services/formal_admission.py'))
def _live():return _LIVE_MODULE
def _code_digest(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise _closed()
    return hashlib.sha256(path.read_bytes()).digest()

def _birth(factory,*names):
    frame=inspect.currentframe().f_back.f_back
    try:
        if factory is not _FACTORY or frame.f_globals is not globals() or frame.f_code not in tuple(_NATIVE_CODES[name] for name in names):raise TypeError('fixed native C factory required')
    finally:del frame

def _deadline(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise ValueError('finite absolute deadline required')
    return float(value)

class _Sealed:
    __slots__=()
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('native lifecycle object immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('native lifecycle cannot cross processes')

class _MainBudget(_Sealed):
    __slots__=('scope','pid','_deadline')
    def __init__(self,scope,*,_factory=None):
        _birth(_factory,'prepare_main_context');self.scope,self.pid,self._deadline=scope,os.getpid(),None
    def shrink(self,value):
        frame=inspect.currentframe().f_back
        try:
            if frame.f_globals is not globals() or frame.f_code not in (_NATIVE_CODES['shrink_main_deadline'],_NATIVE_CODES['request_main_stop']):raise _uncertain()
        finally:del frame
        value=_deadline(value)
        if self.pid!=os.getpid() or _CONTEXTS.get(id(self.scope.binding.app)) is not self.scope:raise _uncertain()
        object.__setattr__(self,'_deadline',value if self._deadline is None else min(value,self._deadline))

class MainStartupScope(_Sealed):
    __slots__=('store','binding','reference','epoch','pid','thread','budget','binding_reference','_release','_release_code','_main','_main_code','_withdraw','_withdraw_code','_images')
    def __init__(self,service,binding,main,admission,*,_factory=None):
        _birth(_factory,'prepare_main_context')
        self.store,self.binding,self.reference,self.epoch=service.store,binding,str(uuid4()),object()
        self.pid,self.thread=os.getpid(),threading.current_thread()
        self.binding_reference=binding.reference;self._release,self._release_code=admission.release,admission.release.__code__
        self._main,self._main_code=main,main.lifespan.__wrapped__.__code__
        self._withdraw,self._withdraw_code=admission.withdraw,admission.withdraw.__code__
        self._images={Path(module.__file__):_code_digest(module.__file__) for module in
            (sys.modules[__name__],_LIVE_MODULE,importlib.import_module(__package__+'.plan_native_runtime'),importlib.import_module(__package__+'.authorization'),importlib.import_module(__package__+'.store'),
             _module(_family()+'.auth_store',Path('services/auth_store.py')),_module(_family()+'.auth_registration',Path('services/auth_registration.py')),
             _module(_family()+'.sqlite_utils',Path('services/sqlite_utils.py')))}
        self.budget=None


def _scope_identity(scope,store=None):
    if type(scope) is not MainStartupScope or scope.pid!=os.getpid() or _CONTEXTS.get(id(scope.binding.app)) is not scope:raise _closed()
    if store is not None:_same_store(scope,store)
    birth=_CONTEXT_BIRTHS.get(id(scope))
    if birth!=(scope,scope.store,scope.binding,scope.binding_reference,scope.reference,scope.pid,scope.thread,scope.epoch) or scope.binding.pid!=scope.pid or scope.binding.reference!=scope.binding_reference:raise _closed()
    return scope


def _same_store(scope,store):
    from .store import ResearchStore
    if (type(store) is not ResearchStore or not store._formal_mode() or store.path!=scope.store.path
            or store.storage_identity!=scope.store.storage_identity or store.auth_store.storage_identity!=scope.store.storage_identity):raise _closed()


def _full_context(scope,*,published=False):
    _scope_identity(scope)
    for path,expected in scope._images.items():
        if _code_digest(path)!=expected:raise _closed()
    scope.binding.check(published=published)


def prepare_main_context(service,binding)->MainStartupScope:
    from .service import ResearchService
    from .store import ResearchStore
    admission=_admission();main=admission._producer(binding.app)
    if type(service) is not ResearchService or type(service.store) is not ResearchStore or type(binding) is not admission._Binding or binding.service is not service:raise _closed()
    binding.check()
    if id(binding.app) in _CONTEXTS:raise _uncertain()
    scope=MainStartupScope(service,binding,main,admission,_factory=_FACTORY)
    _CONTEXTS[id(binding.app)]=scope
    _CONTEXT_BIRTHS[id(scope)]=(scope,scope.store,binding,binding.reference,scope.reference,scope.pid,scope.thread,scope.epoch)
    binding.native_module=sys.modules[__name__];binding.native_context=scope
    object.__setattr__(scope,'budget',_MainBudget(scope,_factory=_FACTORY))
    for path,value in scope._images.items():binding.sources[path]=value
    return scope


def require_startup_scope(scope,store,*,session=None)->None:
    _scope_identity(scope,store)
    if threading.current_thread() is not scope.thread:raise _closed()
    _full_context(scope,published=True)
    if session is not None:
        live=_live()
        if type(session) is not live.NativeLiveSession or live._SESSIONS.get(getattr(session,'reference',None)) is not session or session.startup_scope is not scope or session.store is not scope.store or session.state!='starting':raise _closed()


class _ThreadBudget(_Sealed):
    __slots__=('scope','thread','source','supervisor','lifecycle','active','pid','_expired_cleanup')
    def __init__(self,scope,*,source=None,supervisor=None,lifecycle=None,expired_cleanup=False,_factory=None):
        _birth(_factory,'source_thread_budget','start','_worker_main','BoundedRevokeTransaction.__enter__','retire','join')
        self.scope,self.thread,self.source,self.supervisor,self.lifecycle=scope,threading.current_thread(),source,supervisor,lifecycle
        self.active,self.pid=False,os.getpid();self._expired_cleanup=expired_cleanup
    def __enter__(self):
        _scope_identity(self.scope)
        if self.thread is not threading.current_thread() or self.pid!=os.getpid():raise _closed()
        _THREADS.setdefault(self.thread,[]).append(self);object.__setattr__(self,'active',True)
        try:
            self.check();return self
        except ResearchError as error:
            if self._expired_cleanup and error.code=='STORE_BUSY':return self
            self.__exit__(*sys.exc_info());raise
        except BaseException:
            self.__exit__(*sys.exc_info());raise
    def __exit__(self,*args):
        values=_THREADS.get(self.thread,[])
        if not values or values[-1] is not self:raise _uncertain()
        values.pop();object.__setattr__(self,'active',False)
        if not values:_THREADS.pop(self.thread,None)
    def limit(self):
        values=[self.scope.budget._deadline]
        if self.source is not None:values.append(self.source._deadline.get('absolute'))
        if self.supervisor is not None:values.append(self.supervisor._deadline)
        if self.lifecycle is not None:values.append(self.lifecycle.deadline_monotonic)
        values=[value for value in values if value is not None]
        return min(values) if values else None
    def check(self):
        if self.pid!=os.getpid() or not self.active or self.thread is not threading.current_thread() or self not in _THREADS.get(self.thread,()) or _CONTEXTS.get(id(self.scope.binding.app)) is not self.scope:raise _closed()
        for value in _THREADS[self.thread]:
            limit=value.limit()
            if limit is not None and time.monotonic()>=limit:raise _busy()
    def progress(self):
        try:self.check();return 0
        except BaseException:return 1


def database_budget(path,identity=None):
    """Memory-only registered thread lookup; no SQL or authorization callback."""
    stack=_THREADS.get(threading.current_thread(),())
    if not stack:return None
    current=stack[-1];current.check();scope=current.scope
    if Path(path)!=scope.store.path or (identity is not None and tuple(identity)!=scope.store.storage_identity):raise _closed()
    # Every nested context is checked; none may widen an outer deadline.
    for value in stack:value.check()
    return current


def source_thread_budget(supervisor):
    scope=_CONTEXTS.get(id(supervisor._binding.app));_scope_identity(scope,supervisor._service.store)
    source=_module(__package__+'.source_supervisor',Path('research/source_supervisor.py'))
    frame=inspect.currentframe().f_back
    try:
        if type(supervisor) is not source.SourceSupervisor or source._REGISTRY.get(id(scope.binding.app)) is not supervisor or supervisor._binding is not scope.binding or threading.current_thread() is not supervisor._thread or frame.f_code is not source.SourceSupervisor._run.__code__ or frame.f_globals is not vars(source):raise _closed()
    finally:del frame
    return _ThreadBudget(scope,source=supervisor,_factory=_FACTORY)


def shrink_main_deadline(scope,*,deadline_monotonic):
    _scope_identity(scope)
    frame=inspect.currentframe().f_back
    try:
        if frame.f_globals is not vars(scope._main) or frame.f_code is not scope._main_code or frame.f_locals.get('app') is not scope.binding.app or threading.current_thread() is not scope.thread:raise _uncertain()
    finally:del frame
    scope.budget.shrink(deadline_monotonic)
    return scope.budget._deadline


@dataclass(frozen=True,slots=True)
class NativePlanCleanupReceipt:
    contract:str
    supervisor_ref:str
    state:str
    reason:str
    pending_task_id:str|None

class NativePlanStartFailure(RuntimeError):
    def __init__(self,supervisor):
        super().__init__('native plan start incomplete');self._supervisor=supervisor
    @property
    def supervisor(self):return self._supervisor
    @property
    def resources(self):return tuple(self._supervisor._resources)
    def __reduce__(self):raise TypeError('partial native start cannot be serialized')

class NativePlanWorkerLease(_Sealed):
    __slots__=('supervisor','session','thread','pid','epoch','reference','_native_lock','_native_ident')
    def __init__(self,supervisor,*,_factory=None):
        _birth(_factory,'start')
        self.supervisor,self.session,self.thread=supervisor,supervisor.session,supervisor._thread
        self.pid,self.epoch,self.reference=os.getpid(),supervisor.epoch,object()
        self._native_lock=self._native_ident=None;_WORKERS[self.reference]=self

class NativeLifecycleScope(_Sealed):
    __slots__=('supervisor','session','action','pid','thread','epoch','reference','_deadline')
    def __init__(self,supervisor,action,deadline,*,_factory=None):
        _birth(_factory,'start','retire','_revoke_invalid')
        self.supervisor,self.session,self.action=supervisor,supervisor.session,action
        self.pid,self.thread,self.epoch,self.reference=os.getpid(),threading.current_thread(),supervisor.epoch,object()
        self._deadline=_deadline(deadline);_LIFECYCLES[self.reference]=self
        _LIFECYCLE_BIRTHS[self.reference]=(self,supervisor,self.session,action,self.pid,self.thread,self.epoch,self._deadline)
    @property
    def deadline_monotonic(self):
        root=self.supervisor.context.budget._deadline
        return min(self._deadline,root) if root is not None else self._deadline

class NativePlanSlotLease(_Sealed):
    __slots__=('supervisor','session','worker','task_id','purpose','dispatch','epoch','pid','thread','reference','stop_fd','stop_fd_identity','_write_fd','_write_identity','active')
    def __init__(self,supervisor,task_id,purpose,dispatch,read_fd,write_fd,*,_factory=None):
        _birth(_factory,'_worker_main')
        self.supervisor,self.session,self.worker=supervisor,supervisor.session,supervisor.worker
        self.task_id,self.purpose,self.dispatch=task_id,purpose,dispatch
        self.epoch,self.pid,self.thread,self.reference=supervisor._slot_epoch,os.getpid(),threading.current_thread(),object()
        self.stop_fd,self._write_fd=read_fd,write_fd
        self.stop_fd_identity=_pipe_identity(read_fd);self._write_identity=_pipe_identity(write_fd);self.active=True
        _SLOTS[self.reference]=self
        _SLOT_BIRTHS[self.reference]=(self,supervisor,self.session,self.worker,task_id,purpose,dispatch,self.epoch,self.pid,self.thread,read_fd,self.stop_fd_identity,write_fd,self._write_identity)


def _pipe_identity(fd):
    if type(fd) is not int or fd<0 or os.get_blocking(fd) or os.get_inheritable(fd):raise _uncertain()
    info=os.fstat(fd)
    if not stat.S_ISFIFO(info.st_mode):raise _uncertain()
    return info.st_dev,info.st_ino


def _supervisor_memory(supervisor):
    if type(supervisor) is not NativePlanSupervisor or supervisor.pid!=os.getpid() or _SUPERVISORS.get(id(supervisor.binding.app)) is not supervisor:raise _closed()
    _scope_identity(supervisor.context)


def _supervisor_identity(supervisor):
    if type(supervisor) is not NativePlanSupervisor or supervisor.pid!=os.getpid() or _SUPERVISORS.get(id(supervisor.binding.app)) is not supervisor:raise _closed()
    _scope_identity(supervisor.context,supervisor.service.store)


def require_worker(worker,store,session,*,startup_scope)->None:
    if type(worker) is not NativePlanWorkerLease or _WORKERS.get(getattr(worker,'reference',None)) is not worker:raise _closed()
    sup=worker.supervisor;_supervisor_identity(sup);require_startup_scope(startup_scope,store,session=session)
    if sup.context is not startup_scope or worker.session is not session or sup.session is not session or worker.pid!=os.getpid() or worker.epoch is not sup.epoch or worker.thread is not sup._thread or type(worker.thread) is not threading.Thread or not _THREAD_ALIVE(worker.thread) or type(worker._native_lock) is not _thread.LockType or not worker._native_lock.locked():raise _closed()


def require_lifecycle_scope(scope,store,session,*,action)->None:
    if type(scope) is not NativeLifecycleScope or _LIFECYCLES.get(getattr(scope,'reference',None)) is not scope:raise _closed()
    sup=scope.supervisor;_supervisor_identity(sup);_same_store(sup.context,store)
    if _LIFECYCLE_BIRTHS.get(scope.reference)!=(scope,sup,scope.session,scope.action,scope.pid,scope.thread,scope.epoch,scope._deadline):raise _closed()
    if action not in ('retire','recover','revoke') or scope.action!=action or scope.session is not session or sup.session is not session or scope.pid!=os.getpid() or scope.epoch is not sup.epoch or scope.thread is not threading.current_thread():raise _closed()
    if time.monotonic()>=scope.deadline_monotonic:raise _uncertain()
    # Full intrinsic checks precede normal-stop recognition. A sealed HTTP withdrawal is
    # accepted only for this actual Main's cleanup, never for new sends.
    try:_full_context(sup.context,published=False)
    except BaseException as error:
        admission=_admission();admission.validate_withdrawal(error,sup.binding)
        if not sup._main_stop:raise _closed()


def require_slot(scope,store,session,*,task_id,purpose,mode)->None:
    if type(scope) is not NativePlanSlotLease or _SLOTS.get(getattr(scope,'reference',None)) is not scope:raise _closed()
    sup=scope.supervisor;_supervisor_identity(sup);_same_store(sup.context,store)
    if _SLOT_BIRTHS.get(scope.reference)!=(scope,sup,scope.session,scope.worker,scope.task_id,scope.purpose,scope.dispatch,scope.epoch,scope.pid,scope.thread,scope.stop_fd,scope.stop_fd_identity,scope._write_fd,scope._write_identity):raise _closed()
    if (mode not in ('execute','cleanup') or not scope.active or scope.session is not session or sup.session is not session
            or scope.pid!=os.getpid() or scope.thread is not threading.current_thread() or scope.thread is not sup._thread
            or scope.worker is not sup.worker or _WORKERS.get(scope.worker.reference) is not scope.worker or scope.worker._native_ident!=threading.get_ident() or type(scope.worker._native_lock) is not _thread.LockType or not scope.worker._native_lock.locked()
            or scope.epoch!=sup._slot_epoch or scope.task_id!=task_id or scope.purpose!=purpose
            or sup._slot is not scope or _pipe_identity(scope.stop_fd)!=scope.stop_fd_identity or _pipe_identity(scope._write_fd)!=scope._write_identity):raise _closed()
    if mode=='execute':
        if sup._stop.is_set() or sup._state!='READY' or session.state!='executable':
            _raise_stopping(sup,scope)
            raise _closed()
        try:_full_context(sup.context,published=True)
        except BaseException as error:
            # Main may withdraw after the preceding execute-state check.
            # The canonical withdrawal seal and actual stop birth are both
            # necessary; intrinsic corruption is never a normal stop.
            admission=_admission()
            if type(error) is not admission.FormalAdmissionWithdrawn:raise
            admission.validate_withdrawal(error,sup.binding)
            _raise_stopping(sup,scope)


def require_worker_retired(worker,store,session,*,lifecycle_scope)->None:
    require_lifecycle_scope(lifecycle_scope,store,session,action='retire');sup=lifecycle_scope.supervisor
    if sup._slot is not None:raise _uncertain()
    if worker is None:
        if sup.worker is not None or sup._worker_born or sup._thread is not None:raise _uncertain()
    elif type(worker) is not NativePlanWorkerLease or _WORKERS.get(getattr(worker,'reference',None)) is not worker or worker is not sup.worker or worker.session is not session or worker.thread is not sup._thread or worker.pid!=os.getpid() or worker.epoch is not sup.epoch:raise _uncertain()
    if worker is not None:_require_thread_retired(worker.thread,worker._native_lock)
    # Physical retirement grants no financial reconciliation or new readiness.
    # A has already attempted every B resource before asking for this proof.


def _require_thread_retired(thread,native_lock):
    if type(thread) is not threading.Thread or _THREAD_ALIVE(thread) or type(native_lock) is not _thread.LockType or native_lock.locked():raise _uncertain()


def _direct_error_origin(error,code,name,status):
    """Pure origin predicate, never a stop/authority proof by itself."""
    if type(error) is not ResearchError or error.code!=name or error.status!=status:return False
    trace=error.__traceback__
    if trace is None:return False
    while trace.tb_next is not None:trace=trace.tb_next
    return trace.tb_frame.f_code is code


def _direct_denial(error,code):return _direct_error_origin(error,code,'FUNDING_CLOSED',503)


class _NativeStopping(Exception):
    def __init__(self,supervisor,intent,slot,*,_factory=None):
        _birth(_factory,'_raise_stopping')
        Exception.__init__(self,'native preclaim stop')
        _STOP_SIGNALS[self]=(supervisor,intent,slot)
    def __reduce__(self):raise TypeError('native stop cannot be serialized')


def _stop_proof(sup,slot):
    _supervisor_identity(sup)
    intent=_STOP_BIRTHS.get(sup.reference)
    if intent is None or intent[:5]!=(sup,sup.context,sup.session,sup.epoch,sup.pid):raise _closed()
    kind,origin_slot,slot_epoch=intent[5:]
    if threading.current_thread() is not sup._thread or not sup._stop.is_set():raise _closed()
    if slot is not None and slot is not origin_slot:
        # The same selected task may have crossed the last stop check before
        # withdrawal, then born its pipe. It has not entered runtime's try.
        if origin_slot is not None or slot.supervisor is not sup or slot.session is not sup.session or slot.epoch!=slot_epoch+1:raise _closed()
    if kind=='main':
        try:_full_context(sup.context,published=False)
        except BaseException as error:_admission().validate_withdrawal(error,sup.binding)
    elif kind=='retire':require_lifecycle_scope(sup._retire_scope,sup.service.store,sup.session,action='retire')
    else:raise _closed()
    session=sup.session;live=_live()
    if type(session) is not live.NativeLiveSession or live._SESSIONS.get(session.reference) is not session or session.startup_scope is not sup.context or session.uncertainty or session.state not in ('executable','cleanup_only'):raise _closed()
    # Do not normalize simultaneous grant/Auth/code/key/inode damage as a stop.
    session.grant._current();session.flight._held();session.credential.require_current(session)
    return intent


def _raise_stopping(sup,slot):
    intent=_stop_proof(sup,slot)
    raise _NativeStopping(sup,intent,slot,_factory=_FACTORY)


def _expected_preclaim_stop(sup,error):
    # Only the loop's current check or runtime's pre-try installation/slot
    # check can exit normally. Post-claim runtime cleanup errors are not lost.
    from . import plan_native_runtime as runtime
    record=_STOP_SIGNALS.pop(error,None) if type(error) is _NativeStopping else None
    if runtime.run_once.__code__ is not _RUNTIME_STOP_CODE or _live().NativeLiveSession.require.__code__ is not _LIVE_REQUIRE_CODE:return False
    trace=error.__traceback__;seen_runtime=False
    while trace is not None:
        if trace.tb_frame.f_code is runtime.run_once.__code__:
            seen_runtime=True
            if trace.tb_lineno>=_RUNTIME_TRY_LINE:return False
        trace=trace.tb_next
    if type(error) is _NativeStopping:
        if record is None or record[0] is not sup or record[1] is not _STOP_BIRTHS.get(sup.reference):return False
        _stop_proof(sup,record[2]);return True
    live=_live()
    if not _direct_denial(error,live.NativeLiveSession.require.__code__):return False
    tail=error.__traceback__
    while tail.tb_next is not None:tail=tail.tb_next
    if tail.tb_frame.f_locals.get('self') is not sup.session:return False
    # A nested intrinsic failure has another final frame and cannot pass this.
    if sup.session.state!='cleanup_only':return False
    _stop_proof(sup,sup._slot if seen_runtime else None);return True


def _stop_raise_sites(raw,filename,kind):
    """Pure exact-source coordinates, not a stop or cleanup capability."""
    tree=_ast.parse(raw)
    if kind=='channel':
        body=next(n for n in tree.body if isinstance(n,_ast.ClassDef) and n.name=='_Channel')
        function=next(n for n in body.body if isinstance(n,_ast.FunctionDef) and n.name=='wait')
        expected=('select.select([stop], [], [], 0)[0]','stop is not None and stop in r')
        outer=next(v for v in compile(raw,filename,'exec').co_consts if type(v) is types.CodeType and v.co_name=='_Channel')
        code=next(v for v in outer.co_consts if type(v) is types.CodeType and v.co_name=='wait')
    elif kind=='dns':
        function=next(n for n in tree.body if isinstance(n,_ast.FunctionDef) and n.name=='_wait')
        expected=('stop_fd in ready',)
        code=next(v for v in compile(raw,filename,'exec').co_consts if type(v) is types.CodeType and v.co_name=='_wait')
    else:raise ValueError('fixed native stop source required')
    sites=[]
    for expression in expected:
        test=_ast.dump(_ast.parse(expression,mode='eval').body)
        matches=[n for n in _ast.walk(function) if isinstance(n,_ast.If) and _ast.dump(n.test)==test]
        if len(matches)!=1 or len(matches[0].body)!=1:raise ValueError('fixed native stop branch required')
        node=matches[0].body[0]
        if not isinstance(node,_ast.Raise) or not isinstance(node.exc,_ast.Call) or not isinstance(node.exc.func,_ast.Name) or node.exc.func.id!='InterruptedError':raise ValueError('fixed native stop raise required')
        sites.append(node.lineno)
    return code,tuple(sites)


def _io_stop_snapshot(sup,error,slot,proof):
    if type(error) is not InterruptedError:return None
    trace=error.__traceback__
    if trace is None:return None
    while trace.tb_next is not None:trace=trace.tb_next
    resource=proof._record[2]
    for name,relative,kind in (('plan_runtime_transport','services/plan_runtime_transport.py','channel'),('native_dns_process','services/native_dns_process.py','dns')):
        module=sys.modules.get(_family()+'.'+name)
        if module is None:continue
        path=Path(__file__).resolve().parents[1]/relative
        if Path(module.__file__)!=path or path.is_symlink():raise _closed()
        raw=path.read_bytes()
        if len(raw)>262144:raise _closed()
        code,sites=_stop_raise_sites(raw,str(path),kind)
        actual=module._Channel.wait if kind=='channel' else module._wait
        if actual.__code__!=code or trace.tb_frame.f_globals is not vars(module) or trace.tb_frame.f_code is not actual.__code__ or trace.tb_lineno not in sites:continue
        values=trace.tb_frame.f_locals;fd=values.get('stop' if kind=='channel' else 'stop_fd')
        if type(fd) is not int or fd!=slot.stop_fd or _pipe_identity(fd)!=slot.stop_fd_identity:raise _closed()
        if kind=='channel':
            channel=values.get('self')
            if type(channel) is not module._Channel or channel.owner is not resource or channel.slot_scope is not slot or channel.pid!=os.getpid():raise _closed()
            if trace.tb_lineno==sites[1] and fd not in values.get('r',()):raise _closed()
        else:
            if fd not in values.get('ready',()):raise _closed()
            compiled=compile(raw,str(path),'exec')
            resolve_code=next(v for v in compiled.co_consts if type(v) is types.CodeType and v.co_name=='resolve_native_host')
            if module.resolve_native_host.__code__!=resolve_code:raise _closed()
            chain=error.__traceback__;matched=False
            while chain is not None:
                if (chain.tb_frame.f_code is module.resolve_native_host.__code__ and chain.tb_frame.f_globals is vars(module)
                        and chain.tb_frame.f_locals.get('resource') is resource and chain.tb_frame.f_locals.get('scope') is slot):matched=True
                chain=chain.tb_next
            if not matched:raise _closed()
        import select
        if not select.select([fd],[],[],0)[0]:raise _closed()
        intent=_stop_proof(sup,slot)
        return (error,intent,slot,kind,trace.tb_lineno)
    return None


def _expected_attempt_stop(sup,error):
    candidate=_COMPLETED_CLEANUPS.pop(error,None)
    if candidate is None:return False
    owner,slot,proof,io_stop=candidate
    if owner is not sup or type(proof) is not _runtime_stop_source.NativeAttemptCleanupProof or proof._primary is not error or proof._record[1] is not sup.session or proof._record[3] is not slot:raise _closed()
    if type(error) is _NativeStopping:
        record=_STOP_SIGNALS.pop(error,None)
        if record is None or record[0] is not sup or record[2] is not slot or record[1] is not _STOP_BIRTHS.get(sup.reference):return False
    elif _direct_denial(error,_LIVE_REQUIRE_CODE):
        trace=error.__traceback__
        while trace.tb_next is not None:trace=trace.tb_next
        if trace.tb_frame.f_locals.get('self') is not sup.session or sup.session.state!='cleanup_only':return False
    elif io_stop is None or io_stop[:3]!=(error,_STOP_BIRTHS.get(sup.reference),slot):return False
    _stop_proof(sup,slot);return True


class NativePlanSupervisor(_Sealed):
    __slots__=('service','binding','context','reference','epoch','pid','session','worker','_thread','_worker_born','_activation','_event','_stop','_slot','_slot_epoch','_state','_deadline','_main_stop','_resources','_errors','_readiness','_receipt','_start_failed','_retire_scope','_pending_task_id')
    def __init__(self,service,binding,context,*,_factory=None):
        _birth(_factory,'start')
        self.service,self.binding,self.context=service,binding,context
        self.reference,self.epoch,self.pid=str(uuid4()),object(),os.getpid()
        self.session=self.worker=self._thread=None;self._worker_born=False
        self._activation,self._event,self._stop=threading.Event(),threading.Event(),threading.Event()
        self._slot=None;self._slot_epoch=0;self._state='STARTING';self._deadline=None;self._main_stop=False
        self._resources=();self._errors=();self._readiness=();self._receipt=None;self._start_failed=False;self._retire_scope=None;self._pending_task_id=None


def start(service,binding):
    admission=_admission();admission._producer(binding.app)
    scope=_CONTEXTS.get(id(binding.app));require_startup_scope(scope,service.store)
    if scope.binding is not binding or binding.service is not service or id(binding.app) in _SUPERVISORS:raise _closed()
    sup=NativePlanSupervisor(service,binding,scope,_factory=_FACTORY);_SUPERVISORS[id(binding.app)]=sup
    live=_live();stage='entry'
    try:
        with _ThreadBudget(scope,supervisor=sup,_factory=_FACTORY):
            b=live._b_module()
            getter=getattr(b,'entry_directory_witness',None)
            bpath=Path(b.__file__);raw=bpath.read_bytes()
            if len(raw)>262144:raise _closed()
            expected=next((value for value in compile(raw,str(bpath),'exec').co_consts if type(value) is types.CodeType and value.co_name=='entry_directory_witness'),None)
            if type(getter) is not types.FunctionType or getter.__globals__ is not vars(b) or getter.__code__!=expected:raise _closed()
            entry=getter(scope)
            stage='grant'
            grant=live.read_native_live_grant(service.store,main_context=scope);object.__setattr__(sup,'_resources',sup._resources+(grant,))
            stage='flight'
            flight=live.claim_live_flight(service.store,grant,main_context=scope);object.__setattr__(sup,'_resources',sup._resources+(flight,))
            credential=b.load_native_live_credential(entry,grant,flight,main_context=scope);object.__setattr__(sup,'_resources',sup._resources+(credential,))
            session=live.bind_live_authority(service.store,grant,flight,credential,main_context=scope)
            object.__setattr__(sup,'session',session);object.__setattr__(sup,'_resources',sup._resources+(session,))
            live.install_live_session(service.store,session,main_context=scope)
            recovery=NativeLifecycleScope(sup,'recover',time.monotonic()+20,_factory=_FACTORY)
            with service.store.transaction() as conn:
                account=__import__('json').loads(session.facts)['account_id']
                pending=conn.execute("SELECT task_id FROM research_plan_native_runs WHERE account_id=? AND (state IN ('approved','reserved','consumed','unknown') OR cost_state IN ('held','unknown')) ORDER BY id LIMIT 1",(account,)).fetchone()
                object.__setattr__(sup,'_pending_task_id',pending[0] if pending else None)
            try:
                with _ThreadBudget(scope,supervisor=sup,lifecycle=recovery,_factory=_FACTORY):live.recover_live_session(session,lifecycle_scope=recovery)
            except ResearchError as error:
                if live.recover_live_session.__code__ is not _LIVE_RECOVER_CODE or not _direct_error_origin(error,_LIVE_RECOVER_CODE,'RECONCILIATION_REQUIRED',409):raise
                object.__setattr__(sup,'_readiness',(error,));object.__setattr__(sup,'_state','STOPPING')
                return sup  # No activation; real partial resources still need join.
            object.__setattr__(sup,'_pending_task_id',None)
            thread=threading.Thread(target=_worker_main,args=(sup,),name='structure-native-plan-supervisor',daemon=False)
            object.__setattr__(sup,'_thread',thread);worker=NativePlanWorkerLease(sup,_factory=_FACTORY);object.__setattr__(sup,'worker',worker)
            object.__setattr__(sup,'_worker_born',True);thread.start()
            if type(thread._tstate_lock) is not _thread.LockType or not thread._tstate_lock.locked():raise _uncertain()
            object.__setattr__(worker,'_native_lock',thread._tstate_lock);object.__setattr__(worker,'_native_ident',thread.ident)
            live.activate_live_session(session,startup_scope=scope,worker=worker)
            object.__setattr__(sup,'_state','READY');sup._activation.set()
            return sup
    except BaseException as error:
        if stage=='grant' and not sup._resources and type(error) is live.NativeLiveGrantAbsent:
            try:
                _full_context(scope,published=True)
                live.require_optional_grant_absent(error,service.store,main_context=scope)
            except BaseException as invalid:error=invalid
            else:
                object.__setattr__(sup,'_state','CLOSED');return sup
        # A missing implementation/configuration before any resource birth is
        # native-only closed, and cannot poison base/Source/history admission.
        if stage=='entry' and not sup._resources and type(error) is ResearchError and error.code=='FUNDING_CLOSED':
            object.__setattr__(sup,'_state','CLOSED');return sup
        if type(error) is live.NativeLiveStartFailure:
            if type(error.handle) is live.NativeLiveSession:object.__setattr__(sup,'session',error.handle)
            object.__setattr__(sup,'_resources',sup._resources+error.resources)
        b=sys.modules.get(_family()+'.native_live_credentials')
        failure=getattr(b,'NativeCredentialStartFailure',None) if b else None
        if failure is not None and type(error) is failure:
            object.__setattr__(sup,'_resources',sup._resources+tuple(error.resources)+(error.handle,))
        object.__setattr__(sup,'_errors',sup._errors+(error,));object.__setattr__(sup,'_start_failed',True)
        object.__setattr__(sup,'_state','CLEANUP_UNCERTAIN');sup._stop.set();sup._activation.set();sup._event.set()
        raise NativePlanStartFailure(sup) from None


def _select(supervisor):
    from . import plan_native_runtime as runtime
    facts=__import__('json').loads(supervisor.session.facts)
    with supervisor.service.store.transaction() as conn:
        rows=conn.execute('SELECT id,task_id,consent_json FROM '+runtime.RUNS+" WHERE account_id=? AND state='approved' ORDER BY id LIMIT 1",(facts['account_id'],)).fetchall()
        if not rows:return None
        value=rows[0];consent=__import__('json').loads(value['consent_json'])
        purpose=runtime._confirmed_purpose(consent)
        if consent['authority_digest']!=hashlib.sha256(supervisor.session.facts).hexdigest():raise _closed()
        return value['task_id'],purpose,value['id']


def _worker_main(sup):
    sup._activation.wait();authority_error=False
    try:
        with _ThreadBudget(sup.context,supervisor=sup,_factory=_FACTORY):
            while not sup._stop.is_set():
                try:sup.session.require()
                except BaseException:
                    authority_error=True;raise
                try:selected=_select(sup)
                except ResearchError as error:
                    if error.code!='STORE_BUSY':raise
                    selected=None
                if selected is None:sup._event.wait(.1);sup._event.clear();continue
                if sup._stop.is_set():break
                task,purpose,dispatch=selected;object.__setattr__(sup,'_pending_task_id',task);read_fd=write_fd=None;slot=None
                cleanup_primary=cleanup_candidate=io_stop=None
                try:
                    read_fd,write_fd=os.pipe2(os.O_NONBLOCK|os.O_CLOEXEC) if hasattr(os,'pipe2') else os.pipe()
                    os.set_blocking(read_fd,False);os.set_blocking(write_fd,False);os.set_inheritable(read_fd,False);os.set_inheritable(write_fd,False)
                    object.__setattr__(sup,'_slot_epoch',sup._slot_epoch+1)
                    slot=NativePlanSlotLease(sup,task,purpose,dispatch,read_fd,write_fd,_factory=_FACTORY);object.__setattr__(sup,'_slot',slot)
                    from .plan_native_runtime import run_once
                    try:run_once(sup.service.store,task,slot_scope=slot)
                    except BaseException as error:
                        cleanup_primary=error
                        cleanup_candidate=_runtime_stop_source.take_native_attempt_cleanup(sup.service.store,sup.session,slot,task_id=task,primary=error)
                        if cleanup_candidate is not None:io_stop=_io_stop_snapshot(sup,error,slot,cleanup_candidate)
                        raise
                finally:
                    # B's synchronous attempt must have retired every borrowed
                    # FD/DNS actor before this slot can retire its own pipe.
                    faults=[]
                    try:
                        if slot is not None:
                            for resource in sup.session.resources:
                                try:
                                    if resource.retire_unhanded() is not None:raise _uncertain()
                                except BaseException as error:faults.append(error)
                        if faults:raise _uncertain() from faults[0]
                        if slot is not None:object.__setattr__(slot,'active',False)
                        for fd,identity in ((read_fd,slot.stop_fd_identity if slot else None),(write_fd,slot._write_identity if slot else None)):
                            if fd is None:continue
                            try:
                                if identity is not None and _pipe_identity(fd)!=identity:raise _uncertain()
                                os.close(fd)
                            except BaseException as error:faults.append(error)
                        if faults:raise _uncertain() from faults[0]
                        if slot is not None:object.__setattr__(slot,'active',False);_SLOTS.pop(slot.reference,None);_SLOT_BIRTHS.pop(slot.reference,None)
                        object.__setattr__(sup,'_slot',None)
                        if cleanup_candidate is not None:_COMPLETED_CLEANUPS[cleanup_primary]=(sup,slot,cleanup_candidate,io_stop)
                    finally:
                        if slot is not None:_runtime_stop_source._discard_native_attempt_cleanup(slot)
    except BaseException as error:
        try:expected=_expected_attempt_stop(sup,error) or _expected_preclaim_stop(sup,error)
        except BaseException as invalid:error=invalid;expected=False
        if expected:return
        object.__setattr__(sup,'_errors',sup._errors+(error,));object.__setattr__(sup,'_state','CLEANUP_UNCERTAIN')
        if authority_error and not sup._main_stop and sup._retire_scope is None:
            try:_revoke_invalid(sup)
            except BaseException as cleanup:object.__setattr__(sup,'_errors',sup._errors+(cleanup,))
    finally:
        for primary,record in tuple(_COMPLETED_CLEANUPS.items()):
            if record[0] is sup:_COMPLETED_CLEANUPS.pop(primary,None)
        for signal,record in tuple(_STOP_SIGNALS.items()):
            if record[0] is sup:_STOP_SIGNALS.pop(signal,None)
        sup._event.set()


def request_session_stop(session)->None:
    live=_LIVE_MODULE
    if type(session) is not live.NativeLiveSession or live._SESSIONS.get(getattr(session,'reference',None)) is not session:raise _closed()
    scope=session.startup_scope
    if type(scope) is not MainStartupScope:raise _closed()
    sup=_SUPERVISORS.get(id(scope.binding.app));_supervisor_memory(sup)
    if sup.session is not session:raise _closed()
    sup._stop.set();sup._activation.set();sup._event.set()
    slot=sup._slot
    if slot is not None and slot.active:
        try:
            if _SLOTS.get(slot.reference) is not slot or slot.session is not session or slot.pid!=os.getpid() or _pipe_identity(slot._write_fd)!=slot._write_identity:raise _uncertain()
            os.write(slot._write_fd,b'!')
        except BlockingIOError:pass
        except OSError:
            if slot.active:raise _uncertain()
            # The worker proved all borrowers retired before marking inactive.
            # Skipping a wake here is not a pipe-closure or join receipt.


def request_main_stop(supervisor,binding)->None:
    scope=_CONTEXTS.get(id(binding.app));_scope_identity(scope)
    frame=inspect.currentframe().f_back
    try:
        if (scope.binding is not binding or frame.f_code is not scope._withdraw_code or frame.f_globals is not scope._withdraw.__globals__
                or scope._withdraw.__code__ is not scope._withdraw_code or threading.current_thread() is not scope.thread):raise _uncertain()
    finally:del frame
    if scope.budget._deadline is None:scope.budget.shrink(time.monotonic()+20)
    if supervisor is None:
        if id(binding.app) in _SUPERVISORS:raise _uncertain()
        return
    _supervisor_memory(supervisor);object.__setattr__(supervisor,'_main_stop',True)
    _STOP_BIRTHS.setdefault(supervisor.reference,(supervisor,scope,supervisor.session,supervisor.epoch,supervisor.pid,'main',supervisor._slot,supervisor._slot_epoch))
    supervisor._stop.set();supervisor._activation.set();supervisor._event.set()
    if supervisor.session is not None:request_session_stop(supervisor.session)


def _revoke_invalid(supervisor):
    if threading.current_thread() is not supervisor._thread:raise _closed()
    if supervisor.session is None:return
    deadline=time.monotonic()+20
    object.__setattr__(supervisor,'_deadline',deadline if supervisor._deadline is None else min(deadline,supervisor._deadline))
    scope=NativeLifecycleScope(supervisor,'revoke',supervisor._deadline,_factory=_FACTORY)
    from .plan_native import revoke_live_funding
    revoke_live_funding(supervisor.service.store,supervisor.session,lifecycle_scope=scope)


class BoundedRevokeTransaction(_Sealed):
    __slots__=('scope','store','session','_budget','_owner','_transaction','_lease','_conn','_entered')
    def __init__(self,scope,store,session,*,_factory=None):
        _birth(_factory,'bounded_revoke_transaction')
        self.scope,self.store,self.session=scope,store,session
        self._budget=self._owner=self._transaction=self._lease=self._conn=None;self._entered=()
    def __enter__(self):
        require_lifecycle_scope(self.scope,self.store,self.session,action='revoke')
        if self.scope.deadline_monotonic<=time.monotonic():raise _uncertain()
        object.__setattr__(self,'_budget',_ThreadBudget(self.scope.supervisor.context,supervisor=self.scope.supervisor,lifecycle=self.scope,_factory=_FACTORY))
        self._budget.__enter__();object.__setattr__(self,'_entered',(self._budget,))
        try:
            from .authorization import AuthorizationGate
            pid=__import__('json').loads(self.session.facts)['principal_id']
            object.__setattr__(self,'_owner',AuthorizationGate(self.store).owner_gate(pid,timeout=0))
            object.__setattr__(self,'_lease',self._owner.__enter__());object.__setattr__(self,'_entered',self._entered+(self._owner,))
            object.__setattr__(self,'_transaction',self.store.transaction(write=True))
            object.__setattr__(self,'_conn',self._transaction.__enter__());object.__setattr__(self,'_entered',self._entered+(self._transaction,))
            self._budget.check();return self._lease,self._conn
        except BaseException:
            self.__exit__(*sys.exc_info());raise
    def __exit__(self,*args):
        errors=[]
        for value in reversed(self._entered):
            try:value.__exit__(*args)
            except BaseException as error:errors.append(error)
        object.__setattr__(self,'_entered',())
        if errors:raise _uncertain() from errors[0]


def bounded_revoke_transaction(lifecycle_scope,store,session):
    require_lifecycle_scope(lifecycle_scope,store,session,action='revoke')
    return BoundedRevokeTransaction(lifecycle_scope,store,session,_factory=_FACTORY)


def retire(supervisor,*,deadline_monotonic):
    _supervisor_identity(supervisor);deadline=min(_deadline(deadline_monotonic),time.monotonic()+20)
    object.__setattr__(supervisor,'_deadline',deadline if supervisor._deadline is None else min(deadline,supervisor._deadline))
    if supervisor.session is not None:
        scope=NativeLifecycleScope(supervisor,'retire',supervisor._deadline,_factory=_FACTORY)
        object.__setattr__(supervisor,'_retire_scope',scope)
        _STOP_BIRTHS.setdefault(supervisor.reference,(supervisor,supervisor.context,supervisor.session,supervisor.epoch,supervisor.pid,'retire',supervisor._slot,supervisor._slot_epoch))
    supervisor._stop.set();supervisor._activation.set();supervisor._event.set()
    if supervisor.session is not None:
        require_lifecycle_scope(scope,supervisor.service.store,supervisor.session,action='retire')
        request_session_stop(supervisor.session)
        with _ThreadBudget(supervisor.context,supervisor=supervisor,lifecycle=scope,_factory=_FACTORY):supervisor.session.retire(lifecycle_scope=scope)
    object.__setattr__(supervisor,'_state','STOPPING')


def join(supervisor,*,deadline_monotonic)->NativePlanCleanupReceipt:
    _supervisor_identity(supervisor);deadline=_deadline(deadline_monotonic)
    errors=[]
    try:retire(supervisor,deadline_monotonic=deadline)
    except BaseException as error:errors.append(error)
    deadline=min(deadline,supervisor._deadline)
    if supervisor._thread is not None:
        try:_THREAD_JOIN(supervisor._thread,max(0.,deadline-time.monotonic()))
        except BaseException as error:errors.append(error)
        if _THREAD_ALIVE(supervisor._thread):errors.append(_uncertain())
    # Even failed retirement/join must attempt its own B/key/IO closes.
    # An expired context still blocks every new DB/Owner access; it only lets
    # known physical close attempts run, with no renewed wait allowance.
    if supervisor.session is not None:
        try:
            with _ThreadBudget(supervisor.context,supervisor=supervisor,expired_cleanup=True,_factory=_FACTORY):supervisor.session.close()
        except BaseException as error:errors.append(error)
    else:
        live=_live();flights=[]
        for resource in reversed(supervisor._resources):
            if type(resource) is live.NativeLiveFlightLease:flights.append(resource);continue
            try:resource.close()
            except BaseException as error:errors.append(error)
        # An uncertain partial birth never releases the global exclusion lock
        # merely because another close attempt happened to return.
        if not errors and not supervisor._errors:
            for flight in flights:
                try:flight.close()
                except BaseException as error:errors.append(error)
    if supervisor._slot is not None:errors.append(_uncertain())
    if errors or supervisor._errors:
        object.__setattr__(supervisor,'_errors',supervisor._errors+tuple(errors));object.__setattr__(supervisor,'_state','CLEANUP_UNCERTAIN')
        receipt=NativePlanCleanupReceipt('native-plan-supervisor-cleanup-v1',supervisor.reference,'CLEANUP_UNCERTAIN','CLEANUP_UNCERTAIN',supervisor._slot.task_id if supervisor._slot else supervisor._pending_task_id)
    else:
        object.__setattr__(supervisor,'_state','CLOSED')
        receipt=NativePlanCleanupReceipt('native-plan-supervisor-cleanup-v1',supervisor.reference,'CLOSED','CLOSED',None)
    object.__setattr__(supervisor,'_receipt',receipt);return receipt


def _probe_worker(supervisor):
    worker=supervisor.worker
    if (type(worker) is not NativePlanWorkerLease or _WORKERS.get(getattr(worker,'reference',None)) is not worker
            or worker.supervisor is not supervisor or worker.session is not supervisor.session or worker.pid!=os.getpid()
            or worker.epoch is not supervisor.epoch or worker.thread is not supervisor._thread
            or type(worker.thread) is not threading.Thread or not _THREAD_ALIVE(worker.thread)
            or worker._native_ident!=worker.thread.ident or type(worker._native_lock) is not _thread.LockType
            or not worker._native_lock.locked()):raise _closed()


def require_available(app,service)->None:
    sup=_SUPERVISORS.get(id(app));_supervisor_identity(sup);_same_store(sup.context,service.store)
    if sup._state!='READY' or sup._stop.is_set() or sup.session is None or sup.worker is None or sup._thread is None or not _THREAD_ALIVE(sup._thread) or type(sup.worker._native_lock) is not _thread.LockType or not sup.worker._native_lock.locked():raise _closed()
    _probe_worker(sup);sup.session.require()
    from .plan_native_financial import unresolved
    with service.store.transaction() as conn:
        account=__import__('json').loads(sup.session.facts)['account_id']
        if unresolved(conn,account):raise _closed()


def safe_status(app):
    try:
        sup=_SUPERVISORS.get(id(app));require_available(app,sup.service)
        return 'per_run_guard_required','NATIVE_OWNER_READY_SLOT_REQUIRED'
    except (ResearchError,PermissionError,OSError,AttributeError,TypeError,RuntimeError):return 'closed','FUNDING_CLOSED'


def closed(supervisor):
    _supervisor_identity(supervisor)
    receipt=supervisor._receipt
    return (not supervisor._errors and type(receipt) is NativePlanCleanupReceipt and receipt.supervisor_ref==supervisor.reference
        and receipt.state=='CLOSED' and receipt.pending_task_id is None and supervisor._slot is None
        and (supervisor._thread is None or not _THREAD_ALIVE(supervisor._thread))
        and (supervisor.session is None or supervisor.session.state=='closed'))


def no_native_birth(scope):
    _scope_identity(scope)
    return id(scope.binding.app) not in _SUPERVISORS


def release_main_context(scope):
    _scope_identity(scope)
    frame=inspect.currentframe().f_back
    try:
        if frame.f_globals is not scope._release.__globals__ or frame.f_code is not scope._release_code or frame.f_locals.get('binding') is not scope.binding:raise _uncertain()
    finally:del frame
    sup=_SUPERVISORS.get(id(scope.binding.app))
    if sup is not None and not closed(sup):raise _uncertain()
    if any(value.scope is scope for values in _THREADS.values() for value in values):raise _uncertain()
    if sup is not None:_SUPERVISORS.pop(id(scope.binding.app),None)
    if sup is not None:_STOP_BIRTHS.pop(sup.reference,None)
    _CONTEXTS.pop(id(scope.binding.app),None);_CONTEXT_BIRTHS.pop(id(scope),None)


_NATIVE_CODES={name:value.__code__ for name,value in tuple(globals().items()) if type(value) is types.FunctionType and value.__globals__ is globals()}
_NATIVE_CODES['BoundedRevokeTransaction.__enter__']=BoundedRevokeTransaction.__enter__.__code__

# Freeze the existing runtime pre-claim try boundary from its actual source;
# no caller-supplied line number or mutable stage marker can grant normal exit.
import ast as _ast
from . import plan_native_runtime as _runtime_stop_source
_runtime_tree=_ast.parse(Path(_runtime_stop_source.__file__).read_bytes())
_runtime_function=next(n for n in _runtime_tree.body if isinstance(n,_ast.FunctionDef) and n.name=='run_once')
_RUNTIME_TRY_LINE=next(n.lineno for n in _runtime_function.body if isinstance(n,_ast.Try))
_RUNTIME_STOP_CODE=_runtime_stop_source.run_once.__code__
_LIVE_REQUIRE_CODE=_LIVE_MODULE.NativeLiveSession.require.__code__
_LIVE_RECOVER_CODE=_LIVE_MODULE.recover_live_session.__code__
