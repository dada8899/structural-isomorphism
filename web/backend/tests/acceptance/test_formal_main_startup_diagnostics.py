"""Small offline checks for owned startup coordinates; no browser SDK needed."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import sys

from starlette.applications import Starlette
from uvicorn import Config
from uvicorn.lifespan.on import LifespanOn

from web.backend.tests.acceptance.formal_main_browser_service import (
    ROOT, _safe_startup_error, _StartupErrorObserver, _observe_owned_startup,
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
        config.load()
        original_class = config.lifespan_class
        original_app = config.loaded_app
        if observe:
            retire = _observe_owned_startup(config,
                lambda error: snapshots.append(_safe_startup_error(error)))

        async def run():
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
        assert config.loaded_app is original_app
        if retire is not None:
            retire()
            retire = None
        else:
            actual.logger = original_logger
        assert config.lifespan_class is original_class
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
