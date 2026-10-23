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
