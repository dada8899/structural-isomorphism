"""Small offline checks for owned startup coordinates; no browser SDK needed."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import sys

_REPOSITORY = Path(__file__).resolve().parents[4]
if str(_REPOSITORY) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY))

from starlette.applications import Starlette
from uvicorn import Config, Server
from uvicorn.lifespan.on import LifespanOn

from web.backend.tests.acceptance.formal_main_browser_service import (
    ROOT, _safe_startup_error, _StartupErrorObserver, _observe_owned_startup,
    _safe_lifespan_errors, FormalMainBrowserService,
    _safe_retirement_snapshot, _retirement_json, _retirement_error_chain,
    _retirement_frames, _retirement_thread, _RETIREMENT_LIMIT,
)

MARKER = 'SYNTHETIC_PRIVATE_MARKER'


def test_private_exception_fields_and_free_coordinates_never_leave_observer():
    private_type = type(MARKER, (RuntimeError,), {})
    namespace = {'private_type': private_type, 'marker': MARKER}
    exec(compile('def ' + MARKER + '():\n'
                 '    private_local = marker\n'
                 '    error = private_type(marker)\n'
                 '    error.add_note(marker)\n'
                 '    raise error from ValueError(marker)\n',
                 '/private/' + MARKER + '.py', 'exec'), namespace)
    try:
        namespace[MARKER]()
    except private_type as error:
        result = _safe_startup_error(error)
        assert error.__notes__ == [MARKER]
        assert str(error.__cause__) == MARKER
    encoded = json.dumps(result)
    assert MARKER not in encoded and '/private/' not in encoded
    assert result['type'] == 'OTHER'
    assert 0 < len(result['frames']) <= 8
    assert all(frame['file'] == frame['function'] == 'OTHER'
               for frame in result['frames'])


def test_literal_repository_coordinates_are_preserved_without_exception_text():
    namespace = {'marker': MARKER}
    exec(compile('def initialize():\n    raise RuntimeError(marker)\n',
                 str(ROOT / 'web/backend/services/formal_admission.py'), 'exec'), namespace)
    try:
        namespace['initialize']()
    except RuntimeError as error:
        result = _safe_startup_error(error)
    assert result['type'] == 'RuntimeError'
    assert result['frames'][-1] == {
        'file': 'web/backend/services/formal_admission.py',
        'function': 'initialize', 'line': 2}
    assert MARKER not in json.dumps(result)


def test_lifespan_chain_and_deep_router_wrappers_keep_bounded_original_coordinates():
    namespace = {'marker': MARKER}
    exec(compile('def initialize():\n    raise PermissionError(marker)\n',
                 str(ROOT / 'web/backend/services/formal_admission.py'), 'exec'), namespace)
    def nested(depth):
        if depth: return nested(depth-1)
        namespace['initialize']()
    try:
        try: nested(90)
        except PermissionError as error: raise RuntimeError(MARKER) from error
    except RuntimeError as error:
        result = _safe_lifespan_errors(error)
    assert [item['type'] for item in result] == ['RuntimeError', 'PermissionError']
    assert result[-1]['frames'][-1] == {
        'file': 'web/backend/services/formal_admission.py', 'function': 'initialize', 'line': 2}
    assert all(len(item['frames']) <= 8 for item in result)
    assert MARKER not in json.dumps(result)


def test_shutdown_observer_keeps_failure_after_server_started_without_private_fields(tmp_path):
    from types import SimpleNamespace
    service = FormalMainBrowserService(tmp_path / 'unused-owned-root')
    service.server = SimpleNamespace(started=True)
    try:
        raise PermissionError(MARKER)
    except PermissionError as error:
        service._capture_startup_error(error)
    assert service._startup_diagnostics[0]['type'] == 'PermissionError'
    assert MARKER not in json.dumps(service._startup_diagnostics)


def test_actual_starlette_shutdown_failure_is_observed_after_started_without_private_text(tmp_path):
    from types import SimpleNamespace

    @asynccontextmanager
    async def lifespan(app):
        yield
        raise PermissionError(MARKER)

    service = FormalMainBrowserService(tmp_path / 'unused-owned-root')
    service.server = SimpleNamespace(started=True)
    names = ('uvicorn.error', 'uvicorn.access', 'uvicorn.asgi')
    levels = {name: logging.getLogger(name).level for name in names}
    config = Config(Starlette(lifespan=lifespan), lifespan='on',
                    log_config=None, log_level='critical', ws='none')
    retire = _observe_owned_startup(config, service._capture_startup_error)
    try:
        async def run():
            config.load()
            actual = config.lifespan_class(config)
            assert type(actual) is LifespanOn and actual.main.__func__ is LifespanOn.main
            await actual.startup()
            assert not actual.startup_failed and not actual.error_occured
            await actual.shutdown()
            await asyncio.sleep(0)
            assert actual.shutdown_failed and actual.should_exit and actual.error_occured
            return actual

        actual = asyncio.run(run())
        assert service._startup_diagnostics[0]['type'] == 'PermissionError'
        assert any(frame['file'] == 'starlette/routing.py' and frame['function'] == 'lifespan'
                   for frame in service._startup_diagnostics[0]['frames'])
        assert MARKER not in json.dumps(service._startup_diagnostics)
    finally:
        retire()
        for name, level in levels.items():
            logging.getLogger(name).setLevel(level)
    assert not isinstance(actual.logger, _StartupErrorObserver)
    assert config.lifespan_class is LifespanOn


def test_explicit_exception_observation_preserves_original_logger_arguments():
    error = RuntimeError(MARKER)
    message, extra, answer = object(), object(), object()
    results = []

    class Logger:
        def error(self, *args, **kwargs):
            assert args == (message,)
            assert kwargs['exc_info'] is error and kwargs['extra'] is extra
            return answer

    observer = _StartupErrorObserver(Logger(), lambda value: results.append(_safe_startup_error(value)))
    assert observer.error(message, exc_info=error, extra=extra) is answer
    assert results == [{'type': 'RuntimeError', 'frames': []}]
    assert MARKER not in json.dumps(results)


def _real_lifespan(fail, *, observe=True):
    snapshots, delegated = [], []

    @asynccontextmanager
    async def lifespan(app):
        if fail:
            raise RuntimeError(MARKER)
        yield

    # Uvicorn's normal Config sets logger levels. Restore that existing side
    # effect too; the observer itself never changes global levels/handlers.
    names = ('uvicorn.error', 'uvicorn.access', 'uvicorn.asgi')
    levels = {name: logging.getLogger(name).level for name in names}
    handlers = {name: tuple(logging.getLogger(name).handlers) for name in names}
    config = Config(Starlette(lifespan=lifespan), lifespan='on',
                    log_config=None, log_level='critical', ws='none', loop='asyncio')
    retire = None
    try:
        original_app = config.app
        assert not config.loaded and 'load' not in vars(config)
        if observe:
            retire = _observe_owned_startup(config,
                lambda error: snapshots.append(_safe_startup_error(error)))
            assert not config.loaded and 'lifespan_class' not in vars(config)

        async def run():
            config.load()
            actual = config.lifespan_class(config)
            assert type(actual) is LifespanOn
            assert actual.main.__func__ is LifespanOn.main
            assert actual.send.__func__ is LifespanOn.send
            original_logger = actual.logger._logger if observe else actual.logger

            class Logger:
                def __getattr__(self, name):
                    return getattr(original_logger, name)

                def error(self, *args, **kwargs):
                    # Observe identities/count only, without retaining raw text
                    # or the live exception beyond this original call.
                    delegated.append(sys.exc_info()[0] is RuntimeError)
                    return original_logger.error(*args, **kwargs)

            if observe:
                actual.logger._logger = Logger()
            else:
                actual.logger = Logger()
            await actual.startup()
            assert actual.startup_failed is fail
            assert actual.error_occured is fail
            assert actual.should_exit is fail
            if not fail:
                await actual.shutdown()
                assert not actual.shutdown_failed
            return actual, original_logger

        actual, original_logger = asyncio.run(run())
        assert config.app is original_app
        if retire is not None:
            retire()
            retire = None
        else:
            actual.logger = original_logger
        assert config.lifespan_class is LifespanOn
        assert 'load' not in vars(config)
        assert actual.logger is original_logger
        assert MARKER not in json.dumps(snapshots)
        return snapshots, delegated
    finally:
        if retire is not None:
            retire()
        for name, level in levels.items():
            logging.getLogger(name).setLevel(level)
            assert tuple(logging.getLogger(name).handlers) == handlers[name]


def test_original_starlette_startup_failure_keeps_failure_and_captures_exception():
    snapshots, delegated = _real_lifespan(True)
    assert len(snapshots) == 1 and snapshots[0]['type'] == 'RuntimeError'
    assert any(frame['file'] == 'starlette/routing.py' and
               frame['function'] == 'lifespan' and frame['line'] > 0
               for frame in snapshots[0]['frames'])
    baseline_snapshots, baseline_delegated = _real_lifespan(True, observe=False)
    assert baseline_snapshots == []
    assert delegated == baseline_delegated == [True, False]


def test_original_starlette_normal_startup_shutdown_has_no_failure_diagnostic():
    snapshots, delegated = _real_lifespan(False)
    assert snapshots == delegated == []


def test_original_server_load_position_and_existing_instance_attribute_restored():
    @asynccontextmanager
    async def lifespan(app):
        raise RuntimeError(MARKER)
        yield

    names = ('uvicorn.error', 'uvicorn.access', 'uvicorn.asgi')
    levels = {name: logging.getLogger(name).level for name in names}
    config = Config(Starlette(lifespan=lifespan), lifespan='on',
                    log_config=None, log_level='critical', ws='none')
    original_load = config.load
    events, snapshots = [], []

    def prior_load(*args, **kwargs):
        assert args == () and kwargs == {}
        events.append(asyncio.get_running_loop().is_running())
        return original_load(*args, **kwargs)

    config.load = prior_load
    retire = _observe_owned_startup(config,
        lambda error: snapshots.append(_safe_startup_error(error)))
    try:
        assert not config.loaded and events == []
        server = Server(config)
        # The genuine failed lifespan makes original serve return before any
        # listener is created; no Server method or application is replaced.
        asyncio.run(server.serve(sockets=[]))
        assert events == [True]
        assert not server.started and server.lifespan.startup_failed
        assert type(server.lifespan) is LifespanOn
        assert len(snapshots) == 1 and MARKER not in json.dumps(snapshots)
    finally:
        retire()
        for name, level in levels.items():
            logging.getLogger(name).setLevel(level)
    assert config.load is prior_load
    assert config.lifespan_class is LifespanOn
    assert not isinstance(server.lifespan.logger, _StartupErrorObserver)


def test_original_server_load_failure_is_unchanged_and_creates_no_observer_state():
    names = ('uvicorn.error', 'uvicorn.access', 'uvicorn.asgi')
    levels = {name: logging.getLogger(name).level for name in names}
    config = Config(Starlette(), lifespan='on', log_config=None,
                    log_level='critical', ws='none')
    failure = RuntimeError(MARKER)
    events, snapshots = [], []

    def prior_load(*args, **kwargs):
        assert args == () and kwargs == {}
        events.append(asyncio.get_running_loop().is_running())
        raise failure

    config.load = prior_load
    retire = _observe_owned_startup(config,
        lambda error: snapshots.append(_safe_startup_error(error)))
    try:
        assert events == [] and not config.loaded
        try:
            asyncio.run(Server(config).serve(sockets=[]))
        except RuntimeError as error:
            assert error is failure
        else:
            raise AssertionError('original load failure was swallowed')
        assert events == [True] and not config.loaded
        assert 'lifespan_class' not in vars(config) and snapshots == []
    finally:
        retire()
        retire()
        for name, level in levels.items():
            logging.getLogger(name).setLevel(level)
    assert config.load is prior_load
    assert 'lifespan_class' not in vars(config)


def _retirement_fixture():
    """Projection-only canonical classes; no admitted lifetime or authority."""
    import os
    from services import formal_admission as admission
    from research import source_supervisor as source, source_sec_access as sec
    from research import native_plan_supervisor as native
    app = object()
    binding = object.__new__(admission._Binding)
    supervisor = object.__new__(source.SourceSupervisor)
    governor = object.__new__(sec._Governor)
    native_sup = object.__new__(native.NativePlanSupervisor)
    def put(value, **fields):
        for name, item in fields.items(): object.__setattr__(value, name, item)
    put(binding, app=app, pid=os.getpid(), factory=admission._FACTORY,
        supervisor=supervisor, source_errors=(), native_supervisor=native_sup,
        native_errors=(), source_receipt=source.SourceCleanupReceipt(
            'source-supervisor-cleanup-v1', MARKER, 'CLOSED', None, 'CLOSED'),
        native_receipt=native.NativePlanCleanupReceipt(
            'native-plan-supervisor-cleanup-v1', MARKER, 'CLOSED', 'CLOSED', None))
    put(supervisor, _binding=binding, _state='STOPPED', _failure=None,
        _slot=None, _lease=None, _thread=None, _errors=[], _sec_access=governor)
    put(governor, supervisor=supervisor, binding=binding, state='CLOSED',
        reason=None, fd=None, errors=[])
    put(native_sup, binding=binding, _state='CLOSED', _slot=None,
        worker=None, _thread=None, _errors=())
    return app, binding, supervisor, governor, native_sup


class _RetirementCanary:
    def __getattribute__(self, name): raise AssertionError('canary callback')
    def __repr__(self): raise AssertionError('canary callback')
    def __str__(self): raise AssertionError('canary callback')
    def __eq__(self, other): raise AssertionError('canary callback')
    def __bool__(self): raise AssertionError('canary callback')


def test_retirement_projection_copies_only_closed_schema_and_keeps_raw_records():
    app, binding, source, gov, native = _retirement_fixture()
    before = (binding.source_receipt, binding.source_errors, source._errors,
              binding.native_receipt, binding.native_errors, native._errors, gov.errors)
    value = _safe_retirement_snapshot(binding, app)
    assert value['observation'] == 'OBSERVED'
    assert value['source']['receipt']['state'] == value['native']['receipt']['state'] == 'CLOSED'
    assert value['source']['supervisor']['slot_retained'] is False
    assert value['source']['supervisor']['lease_retained'] is False
    assert value['source']['governor']['fd_retained'] is False
    assert value['source']['supervisor']['thread'] == {'known': True, 'alive': False}
    after = (binding.source_receipt, binding.source_errors, source._errors,
             binding.native_receipt, binding.native_errors, native._errors, gov.errors)
    assert all(first is second for first, second in zip(before, after))
    assert MARKER not in json.dumps(value) and str(ROOT) not in json.dumps(value)


def test_retirement_fake_types_and_wrong_actual_binding_never_gain_known_fields():
    app, binding, source, gov, native = _retirement_fixture()
    fake = type('SourceSupervisor', (), {'__module__': 'research.source_supervisor'})()
    fake._state = MARKER
    object.__setattr__(binding, 'supervisor', fake)
    value = _safe_retirement_snapshot(binding, app)
    assert value['source']['supervisor'] == {'present': True, 'known': False}
    assert _safe_retirement_snapshot(binding, object()) == {'observation': 'UNAVAILABLE'}
    fake_binding = type('_Binding', (), {'__module__': 'services.formal_admission'})()
    assert _safe_retirement_snapshot(fake_binding, app) == {'observation': 'UNAVAILABLE'}
    object.__setattr__(binding, 'factory', _RetirementCanary())
    assert _safe_retirement_snapshot(binding, app) == {'observation': 'UNAVAILABLE'}
    assert MARKER not in json.dumps(value)


def test_retirement_damaged_fields_and_private_extras_do_not_dispatch_callbacks():
    app, binding, source, gov, native = _retirement_fixture()
    bad = _RetirementCanary()
    object.__setattr__(source, '_state', bad)
    object.__setattr__(source, '_failure', MARKER * 1000)
    object.__setattr__(source, '_slot', bad)
    object.__setattr__(source, '_lease', bad)
    object.__setattr__(source, '_thread', bad)
    object.__setattr__(gov, 'state', bad)
    object.__setattr__(gov, 'reason', bad)
    object.__setattr__(gov, 'fd', bad)
    object.__setattr__(binding, 'source_errors', bad)
    object.__setattr__(binding.source_receipt, 'pending_task_id', bad)
    object.__setattr__(binding.source_receipt, 'state', bad)
    value = _safe_retirement_snapshot(binding, app)
    assert value['source']['supervisor']['state'] == 'OTHER'
    assert value['source']['supervisor']['failure'] == 'OTHER'
    assert value['source']['supervisor']['thread'] == {'known': False, 'alive': False}
    assert value['source']['errors']['valid'] is False
    assert value['source']['receipt']['valid'] is False
    assert value['source']['governor']['fd_known'] is False
    assert MARKER not in _retirement_json(binding, app)


def test_retirement_errors_use_exact_type_code_errno_and_ignore_all_private_extras():
    from research.errors import ResearchError
    class PrivateError(RuntimeError):
        def __getattribute__(self, name): raise AssertionError('private callback')
        def __str__(self): raise AssertionError('private callback')
        def __repr__(self): raise AssertionError('private callback')
    private = PrivateError(MARKER)
    BaseException.__setattr__(private, '__notes__', [MARKER])
    result = _retirement_error_chain(private)
    assert result == [{'type': 'OTHER', 'code': None, 'errno': None, 'frames': []}]
    error = ResearchError('STORE_BUSY', 503, MARKER)
    error.headers = {'Cookie': MARKER}
    error.extra = _RetirementCanary()
    error.add_note(MARKER)
    assert _retirement_error_chain(error)[0]['code'] == 'STORE_BUSY'
    error.code = _RetirementCanary()
    assert _retirement_error_chain(error)[0]['code'] == 'OTHER'
    assert _retirement_error_chain(OSError(9, MARKER))[0]['errno'] == 9
    assert _retirement_error_chain(OSError(999999, MARKER))[0]['errno'] is None
    assert MARKER not in json.dumps([result, _retirement_error_chain(error)])


def test_retirement_module_metadata_canary_is_not_compared_or_rendered():
    from research import errors
    error = errors.ResearchError('STORE_BUSY', 503, MARKER)
    prior = vars(errors)['__file__']
    vars(errors)['__file__'] = _RetirementCanary()
    try: value = _retirement_error_chain(error)
    finally: vars(errors)['__file__'] = prior
    assert value[0]['type'] == 'OTHER' and value[0]['code'] is None
    assert MARKER not in json.dumps(value)


def test_retirement_coordinates_require_actual_code_identity_not_caller_filename_or_equal_code():
    import types
    from research import source_supervisor as source
    def observe(function):
        try: function(None, None)
        except ValueError as error: return _retirement_frames(error)
    actual = observe(source._deadline)
    assert actual[-1]['file'] == 'web/backend/research/source_supervisor.py'
    assert actual[-1]['function'] == '_deadline'
    clone = types.FunctionType(source._deadline.__code__.replace(), vars(source))
    assert clone.__code__ == source._deadline.__code__ and clone.__code__ is not source._deadline.__code__
    assert observe(clone) == []


def test_retirement_error_lists_chains_and_json_bytes_are_bounded(monkeypatch):
    from web.backend.tests.acceptance import formal_main_browser_service as entry
    app, binding, source, gov, native = _retirement_fixture()
    chain = RuntimeError(MARKER)
    for _ in range(20):
        following = ValueError(MARKER)
        following.__cause__ = chain
        chain = following
    for value, field in ((binding, 'source_errors'), (source, '_errors'),
                         (binding, 'native_errors'), (native, '_errors'), (gov, 'errors')):
        object.__setattr__(value, field, [chain] * 100)
    encoded = _retirement_json(binding, app)
    assert len(encoded.encode('ascii')) <= _RETIREMENT_LIMIT and MARKER not in encoded
    value = json.loads(encoded)
    for errors in (value['source']['errors'], value['source']['supervisor']['errors'],
                   value['source']['governor']['errors'], value['native']['errors'],
                   value['native']['supervisor']['errors']):
        assert errors['truncated'] and len(errors['items']) == 2
        assert all(len(chain) == 2 for chain in errors['items'])
        assert all(len(error['frames']) <= 4 for chain in errors['items'] for error in chain)
    monkeypatch.setattr(entry, '_safe_retirement_snapshot', lambda *_: {'observation': 'X' * 20000})
    assert entry._retirement_json(binding, app) == '{"observation":"LIMIT"}'


def test_retirement_raw_thread_observation_never_calls_overridden_instance_methods():
    import threading
    thread = threading.Thread()
    thread.is_alive = _RetirementCanary()
    thread._wait_for_tstate_lock = _RetirementCanary()
    assert _retirement_thread(thread) == {'known': True, 'alive': False}
    thread._tstate_lock = _RetirementCanary()
    assert _retirement_thread(thread) == {'known': False, 'alive': False}
    thread._tstate_lock = None


def test_close_observation_precedes_environment_history_restore_and_preserves_original_failure(tmp_path, monkeypatch):
    import os
    from web.backend.tests.acceptance import formal_main_browser_service as entry
    app, binding, source, gov, native = _retirement_fixture()
    service = FormalMainBrowserService(tmp_path / 'unused-root')
    service.app, service._retirement_binding = app, binding
    service._server_errors = ['RuntimeError']
    service._prior = {'SYNTHETIC_RETIREMENT_TEST': 'before'}
    monkeypatch.setenv('SYNTHETIC_RETIREMENT_TEST', 'during')
    original = entry._retirement_json
    calls = []
    def observe(actual_binding, actual_app):
        assert actual_binding is binding and actual_app is app
        calls.append(os.environ['SYNTHETIC_RETIREMENT_TEST'])
        return original(actual_binding, actual_app)
    monkeypatch.setattr(entry, '_retirement_json', observe)
    class History:
        def __exit__(self, kind, error, traceback):
            assert service._retirement_binding is None
            assert os.environ['SYNTHETIC_RETIREMENT_TEST'] == 'before'
            assert json.loads(service._retirement_diagnostics)['observation'] == 'OBSERVED'
    service._history = History()
    primary = ValueError(MARKER)
    assert service.__exit__(ValueError, primary, None) is False
    assert calls == ['during'] and type(primary) is ValueError and str(primary) == MARKER
    assert any(note.startswith('owned Main retirement snapshot: ') for note in primary.__notes__)
    assert service._closed is False and service._server_errors == ['RuntimeError']


def test_retirement_diagnostic_failure_does_not_replace_main_cleanup_error(tmp_path, monkeypatch):
    from web.backend.tests.acceptance import formal_main_browser_service as entry
    app, binding, *_ = _retirement_fixture()
    service = FormalMainBrowserService(tmp_path / 'unused-root')
    service.app, service._retirement_binding = app, binding
    service._server_errors = ['MAIN_LIFESPAN_FAILED']
    def broken(*_): raise PermissionError(MARKER)
    monkeypatch.setattr(entry, '_safe_retirement_snapshot', broken)
    try: service._close()
    except RuntimeError as error:
        assert str(error) == 'owned Main cleanup uncertain: MAIN_LIFESPAN_FAILED'
        assert any('{"observation":"ERROR"}' in note for note in error.__notes__)
    else: raise AssertionError('original cleanup failure was swallowed')
    assert service._retirement_binding is None and service._closed is False


def test_capture_accepts_actual_alternate_family_registry_without_accepting_caller_substitutes(tmp_path):
    import importlib
    import os
    from services import formal_admission as plain
    alternate = importlib.import_module('web.backend.services.formal_admission')
    assert alternate is not plain and alternate._Binding is not plain._Binding
    assert alternate._STATE is plain._STATE
    service = FormalMainBrowserService(tmp_path / 'unused-root')
    service.app = object()
    binding = object.__new__(alternate._Binding)
    for name, value in {'app': service.app, 'factory': alternate._FACTORY,
                        'pid': os.getpid()}.items():
        object.__setattr__(binding, name, value)
    key = id(service.app)
    assert key not in plain._STATE
    try:
        plain._STATE[key] = binding
        service._remember_retirement_binding(plain._STATE)
        assert service._retirement_binding is binding
        service._retirement_binding = None
        service._remember_retirement_binding(dict(plain._STATE))
        assert service._retirement_binding is None
        class CallbackRegistry(dict):
            def get(self, *_): raise AssertionError('caller callback')
        service._remember_retirement_binding(CallbackRegistry(plain._STATE))
        assert service._retirement_binding is None
        fake = type('_Binding', (), {'__module__': alternate.__name__,
            '__getattribute__': _RetirementCanary.__getattribute__})()
        plain._STATE[key] = fake
        service._remember_retirement_binding(plain._STATE)
        assert service._retirement_binding is None
        plain._STATE[key] = binding
        object.__setattr__(binding, 'factory', plain._FACTORY)
        service._remember_retirement_binding(plain._STATE)
        assert service._retirement_binding is None
        object.__setattr__(binding, 'factory', alternate._FACTORY)
        object.__setattr__(binding, 'pid', _RetirementCanary())
        service._remember_retirement_binding(plain._STATE)
        assert service._retirement_binding is None
    finally:
        plain._STATE.pop(key, None)
