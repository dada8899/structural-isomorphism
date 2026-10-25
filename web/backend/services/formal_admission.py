"""Process/lifespan-bound Main admission; Core facts and ENV grant nothing."""
import hashlib
import asyncio
from contextvars import ContextVar
import re
import importlib
import inspect
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import sys
import types
import time
import threading
from uuid import uuid4

_FACTORY = object()
_STATE = vars(sqlite3).setdefault('_structural_main_admission_v1', {})
_RETIRED_UNCERTAIN = vars(sqlite3).setdefault('_structural_main_retirement_uncertain_v1', {})
_CONFIG = ('STRUCTURAL_ENV', 'AUTH_ENABLED', 'AUTH_SITE_ROLE', 'AUTH_LINK_BASE_URL',
           'AUTH_DATA_DIR', 'AUTH_TRUSTED_PROXY_IPS', 'JWT_SECRET', 'STRUCTURAL_PRIVACY_HMAC_KEY',
           'STRUCTURAL_SSO_SECRET', 'STRUCTURAL_SSO_DATA_DIR', 'STRUCTURAL_HISTORY_DB',
           'STRUCTURAL_FAVORITES_PATH', 'STRUCTURAL_SHARE_TOKEN_SECRET', 'SMTP_HOST', 'SMTP_PORT',
           'SMTP_FROM_EMAIL', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_USE_SSL', 'SMTP_STARTTLS',
           'SMTP_TIMEOUT_SECONDS', 'STRUCTURAL_SSO_PHASE_ORIGIN', 'STRUCTURAL_SSO_BETA_ORIGIN',
           'ADMIN_NOTIFICATION_EMAIL', 'STRUCTURAL_ARTIFACT_MANIFEST', 'STRUCTURAL_DATA_DIR',
           'STRUCTURAL_KB_FILE', 'STRUCTURAL_MODEL_PATH', 'STRUCTURAL_PRECOMPUTED_EMBEDDINGS')
_CAPS = ('research_basic', 'source_history', 'source_execute')
_WITHDRAW_FACTORY = object()
_LIFETIME_LOCK = vars(sqlite3).setdefault('_structural_main_lifetime_lock_v1', threading.RLock())


class _Withdrawal:
    __slots__ = ('binding', 'reference', 'pid', 'factory')
    def __init__(self, binding, *, _factory=None):
        if _factory is not _WITHDRAW_FACTORY or inspect.currentframe().f_back.f_code is not withdraw.__code__:
            raise TypeError('actual Main withdrawal required')
        self.binding, self.reference, self.pid, self.factory = binding, binding.reference, os.getpid(), _factory


class FormalAdmissionWithdrawn(RuntimeError):
    """A checked normal HTTP withdrawal fact, never a Source-stop authority."""
    __slots__ = ('_binding', '_reference', '_pid', '_seal')
    def __init__(self, binding, *, _factory=None):
        if _factory is not _WITHDRAW_FACTORY or inspect.currentframe().f_back.f_code is not _Binding.check.__code__:
            raise TypeError('actual checked Main withdrawal required')
        super().__init__('formal Main admission withdrawn')
        self._binding, self._reference, self._pid, self._seal = binding, binding.reference, os.getpid(), binding.withdrawal
    @property
    def binding(self): return self._binding
    @property
    def reference(self): return self._reference
    @property
    def pid(self): return self._pid
    def __reduce__(self): raise TypeError('Main withdrawal cannot cross processes')


def _config():
    return hashlib.sha256(json.dumps({k: os.environ.get(k) for k in _CONFIG}, sort_keys=True).encode()).digest()


def _modules(app):
    from fastapi import FastAPI
    if type(app) is not FastAPI:
        raise RuntimeError('canonical Main required')
    expected = Path(__file__).resolve().parents[1] / 'main.py'
    for name in ('main', 'web.backend.main'):
        module = sys.modules.get(name)
        if (module is not None and getattr(module, 'app', None) is app
                and Path(module.__file__).resolve() == expected and not Path(module.__file__).is_symlink()):
            return module
    raise RuntimeError('canonical Main required')


def _producer(app):
    module = _modules(app)
    caller = inspect.currentframe().f_back.f_back
    codes = [value for value in compile(Path(module.__file__).read_bytes(), module.lifespan.__wrapped__.__code__.co_filename,
        'exec', dont_inherit=True).co_consts if isinstance(value, types.CodeType) and value.co_name == 'lifespan']
    if (caller.f_code is not module.lifespan.__wrapped__.__code__ or caller.f_locals.get('app') is not app
            or len(codes) != 1 or caller.f_code != codes[0] or not module._LAUNCH_FORMAL or not module._IS_PROD):
        raise RuntimeError('actual formal Main lifespan required')
    return module


def _digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('canonical source unavailable')
    return hashlib.sha256(path.read_bytes()).digest()


class _Binding:
    __slots__ = ('app', 'pid', 'reference', 'factory', 'origin', 'config', 'roots', 'paths',
                 'sources', 'service', 'facts', 'witnesses', 'favorites_lock', 'search', 'active', 'retired',
                 'supervisor', 'source_module', 'source_receipt', 'source_deadline', 'source_errors', 'withdrawal',
                 'native_module','native_context','native_supervisor','native_receipt','native_deadline','native_errors',
                 'history_reads','history_errors','history_deadline','history_accepting')

    def __init__(self, app, *, _factory=None):
        if (_factory is not _FACTORY or inspect.currentframe().f_back.f_code is not initialize.__code__):
            raise RuntimeError('native Main initialization required')
        self.app, self.pid, self.reference = app, os.getpid(), str(uuid4())
        self.factory, self.origin, self.config = _factory, __name__, _config()
        self.witnesses, self.search, self.active, self.retired = [], None, False, False
        self.supervisor = self.source_module = self.source_receipt = self.source_deadline = None
        self.source_errors = ()
        self.withdrawal = None
        self.native_module=self.native_context=self.native_supervisor=self.native_receipt=self.native_deadline=None
        self.native_errors=()
        self.history_reads, self.history_errors, self.history_deadline = {}, (), None
        self.history_accepting = True

    def __repr__(self):
        return '<formal Main native binding>'

    def __reduce__(self):
        raise TypeError('Main admission cannot cross processes')

    def check(self, *, published=True):
        origin = sys.modules.get(self.origin)
        if (origin is None or type(self) is not getattr(origin, '_Binding', None) or self.factory is not origin._FACTORY
                or self.pid != os.getpid() or self.config != _config()):
            raise RuntimeError('Main lifespan admission unavailable')
        _modules(self.app)
        if self.roots != (self.paths.STATE_ROOT, self.paths.CACHE_ROOT, self.paths.LOG_ROOT):
            raise RuntimeError('Main private roots changed')
        if any(_digest(path) != value for path, value in self.sources.items()):
            raise RuntimeError('Main source changed')
        for witness in self.witnesses:
            witness.check()
        parent = self.witnesses[0].parent_fd
        lock = os.stat('favorites.lock', dir_fd=parent, follow_symlinks=False)
        data = os.stat('favorites.jsonl', dir_fd=parent, follow_symlinks=False)
        if self.paths.PrivateFavoritesFile._regular(lock) != self.favorites_lock:
            raise RuntimeError('Main favorites lock changed')
        self.paths.PrivateFavoritesFile._regular(data)
        if self.search is not None:
            self.search._formal_snapshot.check_model()
        # Resource/config/source diagnostics precede the normal stop fact.
        with _LIFETIME_LOCK:
            if self.retired or _STATE.get(id(self.app)) is not self or (published and not self.active):
                if _withdrawal_record(self):
                    raise FormalAdmissionWithdrawn(self, _factory=_WITHDRAW_FACTORY)
                raise RuntimeError('Main lifespan admission unavailable')


def initialize(app):
    """Only actual Main lifespan may build from real, existing consumers."""
    main = _producer(app)
    if os.environ.get('STRUCTURAL_ENV') != 'prod' or os.getenv('AUTH_ENABLED', '').lower() not in ('1', 'true', 'yes'):
        raise RuntimeError('explicit formal account profile required')
    retire(app)
    binding = _Binding(app, _factory=_FACTORY)
    _STATE[id(app)] = binding
    try:
        main.auth_api._validate_production_config()
        api_family = main.auth_api.__package__
        service_family = 'web.backend.services' if api_family == 'web.backend.api' else 'services'
        research_family = 'web.backend.research' if api_family == 'web.backend.api' else 'research'
        paths = importlib.import_module(service_family + '.runtime_paths')
        repository = Path(main.__file__).resolve().parents[2]
        public = [Path(main.FRONTEND_DIR)]
        for route in app.routes:
            directory = getattr(getattr(route, 'app', None), 'directory', None)
            if directory is not None:
                public.append(Path(directory))
        paths.RuntimePaths.inspect_formal(repository=repository, public_roots=public)
        binding.paths, binding.roots = paths, (paths.STATE_ROOT, paths.CACHE_ROOT, paths.LOG_ROOT)
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                raise RuntimeError('formal logging must be stdout only')
        auth = main.auth_api._store()
        package = importlib.import_module(research_family)
        store = package.ResearchStore(auth)
        service = package.ResearchService(store)
        # C2 calls the exact public C1 in its own real guarded RO transaction.
        facts = service.runtime_capability_facts()
        if facts.profile.checked_pid != os.getpid() or facts.basic_read_write.state != 'profile_verified':
            raise RuntimeError('current Core profile not verified')
        binding.service, binding.facts = service, facts
        history = importlib.import_module(api_family + '.history')
        report = importlib.import_module(api_family + '.report')
        account = importlib.import_module(api_family + '.report_account')
        connections = importlib.import_module(api_family + '.connections')
        export = importlib.import_module(api_family + '.privacy.export')
        delete = importlib.import_module(api_family + '.privacy.delete')
        with history._HISTORY_STORE_LOCK:
            stores = [history.get_db(), report._get_store(), account._get_store(), connections._get_store(), connections._get_p3_store()]
            expected = paths.STATE_ROOT / 'history.db'
            if any(value.db_path != expected for value in stores) or export._history_db() != expected or delete._history_db() != expected:
                raise RuntimeError('formal history consumers differ')
        sso = importlib.import_module(api_family + '.sso')
        sso._secret()
        sso._phase_origin()
        sso._beta_origin()
        importlib.import_module(service_family + '.report_store')._share_secret()
        replay = sso.get_replay_store()
        for factory, path in ((paths.PrivateAuthFile, auth.path), (paths.PrivateHistoryFile, expected),
                              (paths.PrivateSsoFile, replay.path)):
            witness = factory.acquire(path)
            binding.witnesses.append(witness)
        favorites = paths.PrivateFavoritesFile().acquire()
        try:
            binding.favorites_lock = favorites.lock_identity
        finally:
            favorites.close()
        binding.sources = {Path(module.__file__): _digest(module.__file__) for module in
            (main, sys.modules[__name__], paths, importlib.import_module(service_family + '.sqlite_utils'),
             importlib.import_module(api_family + '.research'), importlib.import_module(research_family + '.runtime_profile'),
             importlib.import_module(research_family + '.store'))}
        binding.check(published=False)
        return binding
    except BaseException as primary:
        try:
            retire(app)
        except BaseException as cleanup:
            primary.add_note('Main initialization cleanup uncertain: ' + type(cleanup).__name__)
        raise


def publish(app, binding, search=None):
    _producer(app)
    if _STATE.get(id(app)) is not binding:
        raise RuntimeError('actual pending Main binding required')
    binding.check(published=False)
    if search is not None:
        family = 'web.backend.services' if binding.service.__module__.startswith('web.') else 'services'
        expected = importlib.import_module(family + '.search_service').SearchService
        if type(search) is not expected or not search.formal or search.kb_size <= 0 or not search.artifact or search._formal_snapshot is None:
            raise RuntimeError('actual formal search resource required')
        search._formal_snapshot.check_model()
    binding.search, binding.active = search, True


def require(app, capability):
    if capability not in _CAPS:
        raise RuntimeError('formal capability unavailable')
    binding = _STATE.get(id(app))
    types = []
    for name in ('services.formal_admission', 'web.backend.services.formal_admission'):
        module = sys.modules.get(name)
        if module is not None and Path(module.__file__).resolve() == Path(__file__).resolve():
            types.append(module._Binding)
    if type(binding) not in types:
        raise RuntimeError('formal Main not initialized')
    try:
        binding.check()
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError('formal Main native resource unavailable') from None
    if capability == 'source_execute':
        try:
            if source_module(binding).require_available(app, binding.service) is not None:
                raise RuntimeError('Source availability returned data')
        except Exception:
            raise RuntimeError('formal Source supervisor unavailable') from None
        return None
    facts = binding.facts
    fact = {'research_basic': facts.basic_read_write, 'source_history': facts.source_history,
            'source_execute': facts.source_execute}[capability]
    if fact.state != 'profile_verified':
        raise RuntimeError('formal capability unavailable')
    return None


def safe_status(app):
    require(app, 'research_basic')
    binding = _STATE[id(app)]
    try:
        require(app, 'source_execute')
        source_status = 'ready'
    except RuntimeError:
        source_status = 'unavailable'
    return {'base': 'ready', 'research_basic': binding.facts.basic_read_write.reason,
            'source_history': binding.facts.source_history.reason, 'source_execute': source_status,
            'math': binding.facts.local_math.reason, 'native_planner': (binding.native_module.safe_status(app)[1] if binding.native_context is not None else binding.facts.native_planner.reason),
            'search': 'ready' if binding.search is not None else 'ARTIFACTS_UNBOUND'}


def source_module(binding):
    """Use the startup service's canonical family, including alternate imports."""
    family = binding.service.__module__.rsplit('.', 1)[0]
    module = importlib.import_module(family + '.source_supervisor')
    expected = Path(__file__).resolve().parents[1] / 'research/source_supervisor.py'
    if Path(module.__file__).resolve() != expected or Path(module.__file__).is_symlink():
        raise RuntimeError('canonical Source module required')
    return module


def pin_source_module(app, binding, module):
    _producer(app)
    binding.check()
    if source_module(binding) is not module:
        raise RuntimeError('canonical Source module required')
    # Freeze code before starting the thread: its binding.check may already
    # iterate this map as soon as Core.start returns from Thread.start.
    binding.source_module = module
    binding.sources[Path(module.__file__)] = _digest(module.__file__)


def attach_source(app, binding, module, supervisor):
    _producer(app)
    binding.check()
    if binding.source_module is not module or type(supervisor) is not module.SourceSupervisor:
        raise RuntimeError('actual Source startup handle required')
    binding.supervisor = supervisor


def attach_native(app,binding,module,supervisor):
    _producer(app);binding.check()
    if binding.native_module is not module or type(supervisor) is not module.NativePlanSupervisor or supervisor.binding is not binding or supervisor.context is not binding.native_context:raise RuntimeError('actual native startup handle required')
    binding.native_supervisor=supervisor


def withdraw(app):
    """Revoke HTTP before waiting on G; keep local native witnesses alive."""
    with _LIFETIME_LOCK:
        binding = _STATE.get(id(app))
        if binding is not None:
            binding.history_accepting = False
            for read in tuple(binding.history_reads.values()):
                for worker in read.workers.values():
                    if worker.state == 'PENDING':object.__setattr__(worker,'state','CANCELLED')
    if binding is None:
        return
    error = None
    if binding.native_context is not None:
        try:
            if binding.native_module.request_main_stop(binding.native_supervisor,binding) is not None:raise RuntimeError('native stop returned data')
        except BaseException as failure:error=failure
    if binding.supervisor is not None and not source_closed(binding):
        try:
            if binding.source_module.request_main_stop(binding.supervisor, binding) is not None:
                raise RuntimeError('Main stop coordination returned data')
        except BaseException as failure:
            error = failure
    with _LIFETIME_LOCK:
        if _STATE.get(id(app)) is not binding:
            return None
        binding.withdrawal = _Withdrawal(binding, _factory=_WITHDRAW_FACTORY) if error is None else None
        binding.active, binding.retired = False, True
        for read in tuple(binding.history_reads.values()):
            for worker in read.workers.values():
                if worker.state == 'PENDING':object.__setattr__(worker, 'state', 'CANCELLED')
        _STATE.pop(id(app), None)
    if error is not None:
        _RETIRED_UNCERTAIN[binding.reference] = (binding, binding.supervisor, (error,))
        raise RuntimeError('Main stop coordination uncertain') from None
    return binding


def _withdrawal_record(binding):
    origin = sys.modules.get(binding.origin)
    record = binding.withdrawal
    return (origin is not None and type(record) is origin._Withdrawal
            and record.factory is origin._WITHDRAW_FACTORY and record.binding is binding
            and record.reference == binding.reference and record.pid == binding.pid == os.getpid()
            and binding.retired and not binding.active and _STATE.get(id(binding.app)) is not binding)


def validate_withdrawal(error, binding):
    """No I/O, callback or C2. Core separately checks its native stop intent."""
    try:
        _owned(binding)
        origin = sys.modules[binding.origin]
        if (type(error) is not origin.FormalAdmissionWithdrawn or error.binding is not binding
                or error.reference != binding.reference or error.pid != binding.pid
                or error._seal is not binding.withdrawal or not _withdrawal_record(binding)):
            raise RuntimeError('Main withdrawal fact mismatch')
    except Exception:
        raise RuntimeError('Main withdrawal fact mismatch') from None
    return None


def _owned(binding):
    origin = sys.modules.get(binding.origin)
    if (origin is None or type(binding) is not origin._Binding or binding.factory is not origin._FACTORY
            or binding.pid != os.getpid()):
        raise RuntimeError('actual Main resource owner required')


def close_source(binding, *, deadline_monotonic):
    """Only actual Core results are recorded; no caller receipt/authority input."""
    _owned(binding)
    if type(deadline_monotonic) not in (int, float) or not math.isfinite(deadline_monotonic):
        raise RuntimeError('finite Main deadline required')
    if source_closed(binding):
        return binding.source_receipt
    if binding.source_deadline is None:
        binding.source_deadline = deadline_monotonic
    if binding.source_deadline != deadline_monotonic:
        raise RuntimeError('Source deadline cannot be reset')
    supervisor = binding.supervisor
    if supervisor is None:
        return None
    module = binding.source_module
    errors = []
    try:
        module.retire(supervisor, deadline_monotonic=deadline_monotonic)
    except BaseException as error:
        errors.append(error)
    try:
        receipt = module.join(supervisor, deadline_monotonic=deadline_monotonic)
        if (type(receipt) is not module.SourceCleanupReceipt
                or receipt.contract != 'source-supervisor-cleanup-v1'
                or receipt.supervisor_ref != supervisor.reference):
            raise RuntimeError('Source cleanup receipt mismatch')
        binding.source_receipt = receipt
    except BaseException as error:
        errors.append(error)
    binding.source_errors = tuple(errors)
    if not source_closed(binding):
        _RETIRED_UNCERTAIN[binding.reference] = (binding, supervisor, tuple(errors))
        raise RuntimeError('Source retirement uncertain') from None
    return binding.source_receipt


def source_closed(binding):
    """Recheck the actual Core result and ref, never cache a closure boolean."""
    _owned(binding)
    if binding.supervisor is None:
        return True
    receipt, module = binding.source_receipt, binding.source_module
    return (not binding.source_errors and type(receipt) is module.SourceCleanupReceipt
            and receipt.contract == 'source-supervisor-cleanup-v1'
            and receipt.supervisor_ref == binding.supervisor.reference
            and receipt.state == 'CLOSED' and receipt.reason == 'CLOSED' and receipt.pending_task_id is None)


def close_native(binding,*,deadline_monotonic):
    _owned(binding)
    if binding.native_context is None:return None
    if type(deadline_monotonic) not in (int,float) or not math.isfinite(deadline_monotonic):raise RuntimeError('finite Main deadline required')
    binding.native_deadline=deadline_monotonic if binding.native_deadline is None else min(binding.native_deadline,deadline_monotonic)
    if binding.native_supervisor is None:
        if not binding.native_module.no_native_birth(binding.native_context):raise RuntimeError('native partial handle missing')
        return None
    errors=[]
    try:binding.native_module.retire(binding.native_supervisor,deadline_monotonic=binding.native_deadline)
    except BaseException as error:errors.append(error)
    try:
        receipt=binding.native_module.join(binding.native_supervisor,deadline_monotonic=binding.native_deadline)
        if type(receipt) is not binding.native_module.NativePlanCleanupReceipt or receipt.contract!='native-plan-supervisor-cleanup-v1' or receipt.supervisor_ref!=binding.native_supervisor.reference:raise RuntimeError('native cleanup receipt mismatch')
        binding.native_receipt=receipt
    except BaseException as error:errors.append(error)
    binding.native_errors=tuple(errors)
    if not native_closed(binding):raise RuntimeError('native retirement uncertain')
    return binding.native_receipt


def native_closed(binding):
    _owned(binding)
    if binding.native_context is None:return True
    if binding.native_errors:return False
    if binding.native_supervisor is None:return binding.native_module.no_native_birth(binding.native_context)
    receipt=binding.native_receipt
    return (type(receipt) is binding.native_module.NativePlanCleanupReceipt and receipt.supervisor_ref==binding.native_supervisor.reference
        and receipt.contract=='native-plan-supervisor-cleanup-v1' and receipt.state=='CLOSED' and binding.native_module.closed(binding.native_supervisor))


def release(binding, *, deadline_monotonic=None):
    """Close common witnesses only after actual Source ownership is CLOSED."""
    _owned(binding)
    if binding.active or _STATE.get(id(binding.app)) is binding:
        raise RuntimeError('HTTP admission must be withdrawn before common resource release')
    if not history_reads_closed(binding):
        _hold_history(binding)
        raise RuntimeError('Main history reads still own resources')
    if not source_closed(binding) or not native_closed(binding):
        _RETIRED_UNCERTAIN[binding.reference] = (binding, binding.supervisor,binding.native_supervisor, ('WORKER_NOT_CLOSED',))
        raise RuntimeError('Main common resources still owned by Source')
    errors = []
    handles = []
    for value in reversed(binding.witnesses):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            errors.append('DEADLINE')
            break
        # Retain the actual owned handle record if close becomes uncertain;
        # never re-admit it or guess closure from a cleared Python attribute.
        handles.append((value, getattr(value, 'parent_fd', None)))
        try:
            value.close()
        except BaseException as error:
            errors.append(type(error).__name__)
    if errors:
        _RETIRED_UNCERTAIN[binding.reference] = (binding, tuple(handles), tuple(errors))
        raise RuntimeError('Main resource retirement uncertain')
    if binding.native_context is not None:binding.native_module.release_main_context(binding.native_context)


def retire(app):
    """Compatibility for failed initialization/legacy callers, never wait on G."""
    binding = withdraw(app)
    if binding is not None:
        release(binding)


def preserve_retirement_uncertainty(app, binding, search, errors):
    _producer(app)
    # Retired native objects are evidence, never a usable admission entry.
    reference = binding.reference if binding is not None else str(uuid4())
    _RETIRED_UNCERTAIN[reference] = (binding, search, tuple(errors))


# These native records account for two HTTP read lifetimes. They are not
# authentication, SQL, cache, Source or funding capabilities.
_HISTORY_ROUTE = re.compile(r'/api/research/[^/]+/(records|source-raw-preparations)\Z')
class HistoryReadUnavailable(RuntimeError):
    pass


_READ_FACTORY = object()
_READ_CONTEXT = vars(sqlite3).setdefault('_structural_main_history_request_v1', ContextVar('main_history_request', default=None))
_READ_WORKER = vars(sqlite3).setdefault('_structural_main_history_worker_v1', ContextVar('main_history_worker', default=None))
_READ_FDS = vars(sqlite3).setdefault('_structural_main_history_directories_v1', {})
_READ_CODE_CACHE = {}


class _ReadRecord:
    __slots__ = ('origin', 'factory', 'pid', 'reference')
    def __init__(self, *args, **kwargs): raise TypeError('actual Main read factory required')
    def __setattr__(self, *args): raise TypeError('Main read record is immutable')
    def __reduce__(self): raise TypeError('Main read record cannot be serialized')
    def __repr__(self): return '<native Main history read record>'


class MainHistoryReadBorrow(_ReadRecord):
    __slots__ = ('binding','scope','operation','request','outer_task','api_task','thread','ended',
                 'workers','resources','identity','service','source','request_token','worker_token','event_worker')


class _HistoryWorker(_ReadRecord):
    __slots__ = ('read','stage','state','thread','token')


class _HistoryResource(_ReadRecord):
    __slots__ = ('worker','kind','state','handle','witness','identity','errors')


def _new_read_record(cls, **fields):
    frame=inspect.currentframe().f_back
    if frame.f_code not in (begin_history_read.__code__, reserve_history_worker.__code__, reserve_history_resource.__code__):
        raise TypeError('actual Main read birth required')
    value=object.__new__(cls)
    for key,item in dict(origin=__name__,factory=_READ_FACTORY,pid=os.getpid(),reference=object(),**fields).items():
        object.__setattr__(value,key,item)
    return value


def _read_origin(value, cls_name):
    origin=sys.modules.get(getattr(value,'origin',None))
    if (origin is None or type(value) is not getattr(origin,cls_name,None)
            or value.factory is not origin._READ_FACTORY or value.pid!=os.getpid()):
        raise RuntimeError('actual native Main read record required')
    return origin


def _read_owner(read):
    _read_origin(read,'MainHistoryReadBorrow');_owned(read.binding)
    if read.binding.history_reads.get(read.reference) is not read:
        raise HistoryReadUnavailable('Main history read has ended')
    return read.binding


def _native_read_caller(frame, relative, names):
    """Match native globals and compiled fixed source, not callback names."""
    module=sys.modules.get(frame.f_globals.get('__name__'))
    expected=Path(__file__).resolve().parents[1]/relative
    if (module is None or frame.f_globals is not vars(module) or Path(module.__file__).resolve()!=expected
            or Path(module.__file__).is_symlink()):
        raise RuntimeError('fixed Main read caller required')
    key=(str(expected),_digest(expected))
    code=_READ_CODE_CACHE.get(key)
    if code is None:
        code=compile(expected.read_bytes(),str(expected),'exec',dont_inherit=True)
        _READ_CODE_CACHE[key]=code
    for name in names:
        candidate=code
        try:
            for part in name.split('.'):
                candidate=next(c for c in candidate.co_consts if isinstance(c,types.CodeType) and c.co_name==part)
        except StopIteration:continue
        if frame.f_code==candidate:return module
    raise RuntimeError('fixed Main read caller required')


def history_read_path(scope):
    return (scope.get('type')=='http' and scope.get('method')=='GET'
            and type(scope.get('path')) is str and _HISTORY_ROUTE.fullmatch(scope['path']) is not None)


def begin_history_read(app, scope):
    frame=inspect.currentframe().f_back
    paths=_native_read_caller(frame,'services/runtime_paths.py',('FormalAdmissionMiddleware.__call__',))
    middleware=frame.f_locals.get('self');current=getattr(app,'middleware_stack',None)
    while current is not None and current is not middleware:current=getattr(current,'app',None)
    if (current is not middleware or type(middleware) is not paths.FormalAdmissionMiddleware
            or middleware.formal is not True or frame.f_locals.get('scope') is not scope
            or scope.get('app') is not app or not history_read_path(scope)):
        raise RuntimeError('actual Main history middleware required')
    binding=_STATE.get(id(app));_owned(binding)
    task=asyncio.current_task();thread=threading.current_thread()
    with _LIFETIME_LOCK:
        if binding.retired or not binding.active or not binding.history_accepting or _STATE.get(id(app)) is not binding:
            raise HistoryReadUnavailable('Main history admission withdrawn')
        read=_new_read_record(MainHistoryReadBorrow,binding=binding,scope=scope,
            operation='records' if scope['path'].endswith('/records') else 'raw',request=None,
            outer_task=task,api_task=None,thread=thread,ended=False,workers={},resources={},
            identity=None,service=None,source=None,request_token=None,worker_token=None,event_worker=None)
        worker=_new_read_record(_HistoryWorker,read=read,stage='request',state='ACTIVE',thread=thread,token=None)
        object.__setattr__(read,'event_worker',worker);read.workers[worker.reference]=worker
        binding.history_reads[read.reference]=read
    object.__setattr__(read,'request_token',_READ_CONTEXT.set(read))
    object.__setattr__(read,'worker_token',_READ_WORKER.set(worker))
    try:
        # Account for the original admission check's transient directory FDs
        # before authentication, without granting downstream admission early.
        require(app,'research_basic')
        return read
    except BaseException:
        _end_history_read(read)
        raise


def enter_history_dispatch(request):
    _native_read_caller(inspect.currentframe().f_back,'api/research.py',('_dispatch',))
    read=_READ_CONTEXT.get()
    if read is None:return False
    _read_owner(read)
    if (request.scope is not read.scope or request.app is not read.binding.app or read.ended
            or threading.current_thread() is not read.thread):
        raise RuntimeError('actual history request required')
    task=asyncio.current_task()
    with _LIFETIME_LOCK:
        if read.api_task is not None and read.api_task is not task:raise RuntimeError('history task differs')
        object.__setattr__(read,'api_task',task);object.__setattr__(read,'request',request)
    return True


def _history_worker_current():
    read=_READ_CONTEXT.get();worker=_READ_WORKER.get()
    if read is None and worker is None:return None
    _read_owner(read);_read_origin(worker,'_HistoryWorker')
    if (worker.read is not read or read.workers.get(worker.reference) is not worker or worker.state!='ACTIVE'
            or worker.thread is not threading.current_thread()):
        raise RuntimeError('actual active Main read worker required')
    if worker.stage=='request':
        task=asyncio.current_task()
        if read.ended or task not in (read.outer_task,read.api_task):raise RuntimeError('history request task differs')
    return worker



def _history_request_cancelled(read):
    return any(task is not None and task.cancelling() for task in (read.outer_task, read.api_task))

def reserve_history_worker(request, stage):
    _native_read_caller(inspect.currentframe().f_back,'api/research.py',('_history_threadpool',))
    read=_READ_CONTEXT.get();_read_owner(read)
    if (read.request is not request or request.scope is not read.scope or asyncio.current_task() is not read.api_task
            or stage not in ('identity','service','action','records','raw')):
        raise RuntimeError('fixed history stage required')
    with _LIFETIME_LOCK:
        if read.ended or _history_request_cancelled(read) or read.binding.retired or not read.binding.active or not read.binding.history_accepting or _STATE.get(id(read.binding.app)) is not read.binding:raise HistoryReadUnavailable('Main history admission withdrawn')
        if any(w.state in ('PENDING','ACTIVE') and w.stage!='request' for w in read.workers.values()):
            raise RuntimeError('history stage already pending')
        if ((stage=='identity' and read.identity is not None) or (stage=='service' and (read.identity is None or read.service is not None))
                or (stage=='action' and (read.operation!='raw' or read.service is None or read.source is not None))
                or (stage in ('records','raw') and (stage!=read.operation or read.service is None or (stage=='raw' and read.source is None)))):
            raise RuntimeError('history stage order differs')
        worker=_new_read_record(_HistoryWorker,read=read,stage=stage,state='PENDING',thread=None,token=None)
        read.workers[worker.reference]=worker
        return worker


def enter_history_worker(worker):
    _native_read_caller(inspect.currentframe().f_back,'api/research.py',('_history_worker',))
    _read_origin(worker,'_HistoryWorker');read=worker.read;_read_owner(read)
    with _LIFETIME_LOCK:
        if (read.workers.get(worker.reference) is not worker or worker.state!='PENDING' or read.ended or _history_request_cancelled(read)
                or read.binding.retired or not read.binding.active or not read.binding.history_accepting or _STATE.get(id(read.binding.app)) is not read.binding):
            if worker.state=='PENDING':object.__setattr__(worker,'state','CANCELLED')
            raise HistoryReadUnavailable('Main history worker withdrawn before IO')
        object.__setattr__(worker,'state','ACTIVE');object.__setattr__(worker,'thread',threading.current_thread())
    object.__setattr__(worker,'token',_READ_WORKER.set(worker))
    return read


def complete_history_worker(worker, result):
    api=_native_read_caller(inspect.currentframe().f_back,'api/research.py',('_history_worker',))
    if _history_worker_current() is not worker:raise RuntimeError('actual history worker required')
    if worker.stage=='identity' and type(result) is not api.AccountIdentity:
        raise RuntimeError('actual history identity required')
    if worker.stage=='service' and (type(result) is not api.ResearchService or type(result.store) is not api.ResearchStore
            or result.store.path!=worker.read.binding.service.store.path
            or result.store.storage_identity!=worker.read.binding.service.store.storage_identity):
        raise RuntimeError('actual bound history service required')
    key={'identity':'identity','service':'service','action':'source'}.get(worker.stage)
    if key is not None:object.__setattr__(worker.read,key,result)


def cancel_history_worker(worker):
    _native_read_caller(inspect.currentframe().f_back,'api/research.py',('_history_threadpool',))
    _read_origin(worker,'_HistoryWorker')
    with _LIFETIME_LOCK:
        if worker.state=='PENDING':object.__setattr__(worker,'state','CANCELLED')


def _hold_history(binding):
    _RETIRED_UNCERTAIN[binding.reference]=(binding,tuple(binding.history_reads.values()),binding.history_errors)


def _history_failure(read, error):
    object.__setattr__(read.binding,'history_errors',(*read.binding.history_errors,error))
    _hold_history(read.binding)


def _finish_history_if_possible(read):
    # Caller owns the lifetime lock. Sticky errors are never upgraded to closed.
    if read.ended and read.source is None and not read.resources and all(w.state in ('RETIRED','CANCELLED') for w in read.workers.values()):
        read.binding.history_reads.pop(read.reference,None)


def _close_history_action(read):
    source=read.source
    if source is not None:
        try:source.close()
        except BaseException as error:
            with _LIFETIME_LOCK:_history_failure(read,error)
        else:object.__setattr__(read,'source',None)


def end_history_worker(worker):
    _native_read_caller(inspect.currentframe().f_back,'api/research.py',('_history_worker',))
    _read_origin(worker,'_HistoryWorker');read=worker.read
    if worker.thread is not threading.current_thread():raise RuntimeError('history creator thread required')
    try:
        if read.ended:_close_history_action(read)
    finally:
        _READ_WORKER.reset(worker.token)
        with _LIFETIME_LOCK:
            object.__setattr__(worker,'state','RETIRED');_finish_history_if_possible(read)


def end_history_read(read):
    _native_read_caller(inspect.currentframe().f_back,'services/runtime_paths.py',('FormalAdmissionMiddleware.__call__',))
    _end_history_read(read)


def _end_history_read(read):
    if inspect.currentframe().f_back.f_code not in (begin_history_read.__code__,end_history_read.__code__):
        raise RuntimeError('actual history request end required')
    _read_owner(read)
    with _LIFETIME_LOCK:
        object.__setattr__(read,'ended',True)
        for worker in read.workers.values():
            if worker.state=='PENDING':object.__setattr__(worker,'state','CANCELLED')
        object.__setattr__(read.event_worker,'state','RETIRED')
    try:
        # An active raw worker retains its original request source through its
        # own finally, even when the outer coroutine has been cancelled.
        with _LIFETIME_LOCK:
            active=any(w.stage!='request' and w.state=='ACTIVE' for w in read.workers.values())
        if not active:_close_history_action(read)
    finally:
        _READ_WORKER.reset(read.worker_token);_READ_CONTEXT.reset(read.request_token)
        with _LIFETIME_LOCK:_finish_history_if_possible(read)


def reserve_history_resource(kind):
    if _READ_CONTEXT.get() is None and _READ_WORKER.get() is None:return None
    frame=inspect.currentframe().f_back
    if kind=='directory':_native_read_caller(frame,'services/runtime_paths.py',('_open_runtime_directory',))
    elif kind=='connection':_native_read_caller(frame,'services/sqlite_utils.py',('connect_private_history','connect_private_auth','connect_private_sso'))
    else:raise RuntimeError('fixed history resource required')
    worker=_history_worker_current()
    if worker is None:return None
    with _LIFETIME_LOCK:
        resource=_new_read_record(_HistoryResource,worker=worker,kind=kind,state='OPENING',handle=None,witness=None,identity=None,errors=())
        worker.read.resources[resource.reference]=resource
    return resource


def _history_resource_owned(resource):
    _read_origin(resource,'_HistoryResource');read=resource.worker.read;_read_owner(read)
    if read.resources.get(resource.reference) is not resource or resource.worker.thread is not threading.current_thread():
        raise RuntimeError('actual creator-owned history resource required')
    return read


def bind_history_directory(resource, fd):
    if resource is None:return
    _native_read_caller(inspect.currentframe().f_back,'services/runtime_paths.py',('_open_runtime_directory',))
    if resource is None:return
    _history_resource_owned(resource)
    if type(fd) is not int or resource.kind!='directory' or resource.state!='OPENING':raise RuntimeError('actual directory birth required')
    with _LIFETIME_LOCK:
        object.__setattr__(resource,'handle',fd);object.__setattr__(resource,'state','LIVE')
        _READ_FDS[(os.getpid(),threading.get_ident(),fd)]=resource
    info=os.fstat(fd)
    object.__setattr__(resource,'identity',(info.st_dev,info.st_ino))


def history_directory_resource(fd):
    if (os.getpid(),threading.get_ident(),fd) not in _READ_FDS:return None
    _native_read_caller(inspect.currentframe().f_back,'services/runtime_paths.py',('_close_runtime_fd','_attach_history_parent',))
    return _READ_FDS.get((os.getpid(),threading.get_ident(),fd))


def bind_history_witness(resource, witness):
    if resource is None:return
    _native_read_caller(inspect.currentframe().f_back,'services/runtime_paths.py',('_attach_history_parent',))
    if resource is not None:
        _history_resource_owned(resource);object.__setattr__(resource,'witness',witness)


def bind_history_connection(resource, conn, witness):
    if resource is None:return
    _native_read_caller(inspect.currentframe().f_back,'services/sqlite_utils.py',('connect_private_history','connect_private_auth','connect_private_sso'))
    if resource is None:return
    _history_resource_owned(resource)
    if not isinstance(conn,sqlite3.Connection) or resource.kind!='connection' or resource.state!='OPENING':raise RuntimeError('actual SQLite birth required')
    object.__setattr__(resource,'handle',conn);object.__setattr__(resource,'witness',witness)
    object.__setattr__(resource,'identity',witness.file_identity);object.__setattr__(resource,'state','LIVE')




def validate_history_resource_creator(resource):
    if resource is None:return
    _native_read_caller(inspect.currentframe().f_back,'services/runtime_paths.py',('PrivateHistoryFile.close',))
    if resource is not None:_history_resource_owned(resource)

def begin_history_resource_close(resource):
    if resource is None:return
    frame=inspect.currentframe().f_back
    if frame.f_code.co_name=='_close_runtime_fd':_native_read_caller(frame,'services/runtime_paths.py',('_close_runtime_fd',))
    else:_native_read_caller(frame,'services/sqlite_utils.py',('PrivateHistoryConnection.close',))
    if resource is None:return
    _history_resource_owned(resource)
    with _LIFETIME_LOCK:
        if resource.state not in ('LIVE','OPENING'):raise RuntimeError('history resource close cannot be retried')
        object.__setattr__(resource,'state','CLOSING')

def finish_history_resource(resource, error=None):
    if resource is None:return
    frame=inspect.currentframe().f_back
    if frame.f_code.co_name=='_close_runtime_fd':_native_read_caller(frame,'services/runtime_paths.py',('_close_runtime_fd',))
    else:_native_read_caller(frame,'services/sqlite_utils.py',('PrivateHistoryConnection.close','connect_private_history','connect_private_auth','connect_private_sso'))
    if resource is None:return
    read=_history_resource_owned(resource)
    with _LIFETIME_LOCK:
        handle = resource.handle
        if error is not None:
            object.__setattr__(resource,'state','UNCERTAIN');object.__setattr__(resource,'errors',(*resource.errors,error))
            _history_failure(read,error)
        elif resource.state!='UNCERTAIN':
            object.__setattr__(resource,'state','CLOSED');read.resources.pop(resource.reference,None)
            object.__setattr__(resource,'handle',None);object.__setattr__(resource,'witness',None)
        if resource.kind=='directory':
            key=(os.getpid(),threading.get_ident(),handle)
            if _READ_FDS.get(key) is resource:_READ_FDS.pop(key,None)
        _finish_history_if_possible(read)


def fail_history_directory_birth(resource):
    if resource is None:return
    _native_read_caller(inspect.currentframe().f_back,'services/runtime_paths.py',('_open_runtime_directory',))
    if resource is None:return
    read=_history_resource_owned(resource)
    with _LIFETIME_LOCK:
        if resource.handle is None:
            read.resources.pop(resource.reference,None);object.__setattr__(resource,'state','CLOSED')
        _finish_history_if_possible(read)


def require_history_read_consumer(service, identity, request_source=None, *, consumer='raw'):
    worker=_history_worker_current()
    if (worker is None or worker.stage!=consumer or consumer not in ('raw','records')
            or worker.read.ended or worker.read.scope.get('app') is not worker.read.binding.app
            or worker.read.service is not service or worker.read.identity is not identity
            or (consumer=='raw' and worker.read.source is not request_source)):
        raise RuntimeError('actual fixed Main history consumer required')
    return None


def history_reads_closed(binding):
    _owned(binding)
    with _LIFETIME_LOCK:return not binding.history_reads and not binding.history_errors


async def drain_history_reads(binding, *, deadline_monotonic):
    _producer(binding.app)
    frame=inspect.currentframe().f_back
    if frame.f_locals.get('binding') is not binding or frame.f_locals.get('deadline')!=deadline_monotonic:
        raise RuntimeError('original Main history deadline required')
    _owned(binding)
    if type(deadline_monotonic) not in (int,float) or not math.isfinite(deadline_monotonic):raise RuntimeError('finite Main deadline required')
    with _LIFETIME_LOCK:
        binding.history_deadline=deadline_monotonic if binding.history_deadline is None else min(binding.history_deadline,deadline_monotonic)
    while True:
        with _LIFETIME_LOCK:
            if not binding.history_reads and not binding.history_errors:return None
            if binding.history_errors:
                _hold_history(binding);raise RuntimeError('Main history cleanup uncertain')
            remaining=binding.history_deadline-time.monotonic()
            if remaining<=0:
                _history_failure(next(iter(binding.history_reads.values())),RuntimeError('Main history drain deadline'))
                raise RuntimeError('Main history drain deadline')
        await asyncio.sleep(min(.01,remaining))
