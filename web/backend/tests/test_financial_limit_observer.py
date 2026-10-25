"""Pure observer controls: no Main, browser, server, DB, or action admission.

The real API dispatcher is used only before its permission/service boundary,
with a genuine synthetic Starlette Request and its original input rejection.
"""
import asyncio
import ast
import gc
import importlib
import inspect
import json
from pathlib import Path
import sys
import textwrap
import types
import weakref

import pytest
from starlette.requests import Request

from web.backend.tests.acceptance import financial_limit_observer as observer


@pytest.fixture
def loaded():
    policy = importlib.import_module('research.financial_policy')
    route = importlib.import_module('api.research')
    assert '__init__' not in vars(policy.FinancialResourceLimit)
    assert observer._ACTIVE is None
    yield policy, route
    assert observer._ACTIVE is None
    assert '__init__' not in vars(policy.FinancialResourceLimit)
    assert 'main' not in sys.modules and 'web.backend.main' not in sys.modules


def request_for(app, receive=None):
    async def oversized():
        return {'type': 'http.request', 'body': b' ' * 65537, 'more_body': False}
    scope = {'type': 'http', 'method': 'POST', 'scheme': 'https',
        'server': ('beta.structural.bytedance.city', 443), 'client': ('127.0.0.1', 1),
        'root_path': '', 'path': '/api/research/synthetic/financial-calculations',
        'raw_path': b'/api/research/synthetic/financial-calculations', 'query_string': b'',
        'headers': [(b'origin', b'https://beta.structural.bytedance.city'),
            (b'host', b'beta.structural.bytedance.city'), (b'idempotency-key', b'synthetic-observer'),
            (b'content-type', b'application/json')], 'app': app}
    return Request(scope, receive=receive or oversized)


def reject(route, app, *, receive=None, function=None):
    return asyncio.run((function or route._dispatch_financial_result)(
        request_for(app, receive), None, None, 'synthetic', 'financial-calculate'))


def records(capsys):
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith(observer.PREFIX)]
    assert lines and all(line.isascii() and len(line) + 1 <= 2048 for line in lines)
    values = [json.loads(line[len(observer.PREFIX):]) for line in lines]
    assert all(value['catch_link'] == 'UNOBSERVED' for value in values)
    return values


def test_actual_class_original_args_catch_and_direct_api_site(loaded, capsys):
    policy, route = loaded
    cls = policy.FinancialResourceLimit
    old_mro, original = cls.__mro__, cls.__init__
    app = object()
    with observer.observe_financial_limit(app) as capture:
        assert capture._setup == 'READY'
        assert cls is policy.FinancialResourceLimit and cls.__mro__ == old_mro
        error = cls('synthetic private constructor text', 7)
        assert type(error) is cls and error.args == ('synthetic private constructor text', 7)
        assert error.__cause__ is error.__context__ is error.__traceback__ is None
        result = reject(route, app)
        capture.response(result.status_code)
        assert result.status_code == 413
        assert json.loads(result.body)['error']['code'] == 'PAYLOAD_LIMIT'
    value = records(capsys)[0]
    assert cls.__init__ is original and '__init__' not in vars(cls)
    assert value['setup'] == 'READY' and value['restore'] == 'RESTORED'
    assert value['response'] == 'HTTP_413' and value['events'] == '1'
    assert value['observations'] == [{'event': 'DIRECT_RAISE_CONSTRUCTION', 'site': 'L01',
        'category': 'REQUEST_WIRE_BYTES', 'cap': None, 'operations': None, 'nodes': None, 'depth': None}]
    assert 'synthetic private constructor text' not in json.dumps(value)


def test_literal_31_sites_and_current_api_not_old_wholefile_pin():
    assert len(observer.SITES) == 31
    assert [r[0] for r in observer.SITES] == [f'L{i:02}' for i in range(1, 32)]
    assert 'web/backend/api/research.py' not in observer.SOURCE_PINS
    for relative in {row[1] for row in observer.SITES}:
        found = observer._direct_sites((observer.ROOT / relative).read_bytes())
        for site, filename, line, qualname, category in observer.SITES:
            if filename == relative:
                assert found[line] == qualname
    source = ast.parse((observer.ROOT / 'web/backend/research/financial_policy.py').read_bytes())
    tick = next(n for n in ast.walk(source) if isinstance(n, ast.FunctionDef) and n.name == 'tick')
    condition = next(n for n in ast.walk(tick) if isinstance(n, ast.If)).test
    assert isinstance(condition, ast.BoolOp) and isinstance(condition.op, ast.Or)
    assert ast.unparse(condition.values[0]) == 'self.operations > MAX_OPERATIONS'
    assert ast.unparse(condition.values[1]) == 'time.monotonic() > self.deadline'


def test_zero_one_two_and_overflow_are_finite(loaded, capsys):
    _, route = loaded
    app = object()
    for count in (0, 1, 2, 3, 7):
        with observer.observe_financial_limit(app) as capture:
            for _ in range(count):
                assert reject(route, app).status_code == 413
            capture.response(200)
        value = records(capsys)[0]
        assert value['response'] == 'HTTP_200'
        assert value['events'] == ('0' if count == 0 else '1' if count == 1 else '2_PLUS')
        assert len(value['observations']) == min(2, count)
        assert value['overflow'] is (count > 2)
        assert value['observer_fault'] is False


def test_late_loaded_real_module_is_memory_bound_without_callback_io(loaded, monkeypatch, capsys):
    policy, route = loaded
    name = 'research.financial_result_adapter'
    prior = sys.modules.pop(name, None)
    app = object()
    try:
        with observer.observe_financial_limit(app) as capture:
            assert name not in sys.modules
            module = importlib.import_module(name)
            assert module.FinancialResourceLimit is policy.FinancialResourceLimit
            async def late_rejection():
                module._parse(None)
            # Guard the complete capture path, not just the late lookup helper.
            original = capture._capture
            def no_io(frame):
                def forbidden(*args, **kwargs):
                    raise AssertionError('observer attempted cold work in callback')
                with monkeypatch.context() as guard:
                    guard.setattr(observer.Path, 'resolve', forbidden)
                    guard.setattr(observer.Path, 'stat', forbidden)
                    guard.setattr(observer.Path, 'read_bytes', forbidden)
                    guard.setattr(observer.hashlib, 'sha256', forbidden)
                    guard.setattr('builtins.compile', forbidden)
                    guard.setattr('builtins.__import__', forbidden)
                    original(frame)
            monkeypatch.setattr(capture, '_capture', no_io)
            result = reject(route, app, receive=late_rejection)
            capture.response(result.status_code)
            assert result.status_code == 413
        value = records(capsys)[0]
        assert value['observations'][0]['site'] == 'L20'
        assert value['observations'][0]['category'] == 'JSON_BYTES'
        assert value['observer_fault'] is False
    finally:
        sys.modules.pop(name, None)
        if prior is not None:
            sys.modules[name] = prior


@pytest.mark.parametrize('change', ['missing', 'module_copy', 'globals', 'code', 'descriptor'])
def test_late_foreign_missing_or_changed_referent_is_unknown(loaded, monkeypatch, capsys, change):
    _, route = loaded
    name = 'research.financial_result_adapter'
    prior = sys.modules.pop(name, None)
    app = object()
    try:
        with observer.observe_financial_limit(app) as capture:
            module = importlib.import_module(name)
            actual = module._parse
            if change == 'missing':
                monkeypatch.delitem(sys.modules, name)
            elif change == 'module_copy':
                foreign = types.ModuleType(name)
                vars(foreign).update(vars(module))
                monkeypatch.setitem(sys.modules, name, foreign)
            elif change == 'globals':
                changed = types.FunctionType(actual.__code__, dict(actual.__globals__), argdefs=actual.__defaults__)
                changed.__kwdefaults__ = actual.__kwdefaults__
                monkeypatch.setattr(module, '_parse', changed)
                actual = module._parse
            elif change == 'code':
                changed = types.FunctionType(actual.__code__.replace(co_firstlineno=actual.__code__.co_firstlineno + 1), actual.__globals__, argdefs=actual.__defaults__)
                changed.__kwdefaults__ = actual.__kwdefaults__
                monkeypatch.setattr(module, '_parse', changed)
                actual = module._parse
            else:
                monkeypatch.setattr(module, '_parse', staticmethod(actual))
            async def late_rejection():
                actual(None)
            assert reject(route, app, receive=late_rejection).status_code == 413
        value = records(capsys)[0]
        assert value['observations'][0]['site'] == 'UNKNOWN'
        assert all(value['observations'][0][key] is None for key in ('cap', 'operations', 'nodes', 'depth'))
    finally:
        # Undo temporary replacements before restoring the original family slot.
        monkeypatch.undo()
        sys.modules.pop(name, None)
        if prior is not None:
            sys.modules[name] = prior


def test_late_exception_alias_and_missing_policy_do_not_authorize_observation(loaded, monkeypatch, capsys):
    policy, route = loaded
    app = object()
    module = importlib.import_module('research.financial_result_adapter')
    with observer.observe_financial_limit(app):
        class Different(policy.FinancialResourceLimit):
            pass
        with monkeypatch.context() as change:
            change.setattr(module, 'FinancialResourceLimit', Different)
            async def wrong_class():
                module._parse(None)
            assert reject(route, app, receive=wrong_class).status_code == 413
    assert records(capsys)[0]['events'] == '0'
    with monkeypatch.context() as change:
        change.delitem(sys.modules, 'research.financial_policy')
        with observer.observe_financial_limit(app) as capture:
            assert capture._setup == 'UNAVAILABLE'
    assert records(capsys)[0]['restore'] == 'UNINSTALLED'


@pytest.mark.parametrize('kind', ['other_app', 'fake_code', 'fake_globals', 'fake_request', 'scope_subclass'])
def test_request_and_actual_function_identity_filter_only(loaded, monkeypatch, capsys, kind):
    _, route = loaded
    app = object()
    function = route._dispatch_financial_result
    with observer.observe_financial_limit(object() if kind == 'other_app' else app):
        if kind == 'fake_code':
            function = types.FunctionType(function.__code__.replace(), function.__globals__)
        elif kind == 'fake_globals':
            function = types.FunctionType(function.__code__, dict(function.__globals__))
        if kind in ('fake_request', 'scope_subclass'):
            class DerivedRequest(Request):
                pass
            class DerivedScope(dict):
                pass
            request = request_for(app)
            request = (DerivedRequest(request.scope, receive=request._receive) if kind == 'fake_request'
                else Request(DerivedScope(request.scope), receive=request._receive))
            result = asyncio.run(function(request, None, None, 'synthetic', 'financial-calculate'))
        else:
            result = reject(route, app, function=function)
        assert result.status_code == 413
    assert records(capsys)[0]['events'] == '0'


def test_nondirect_construction_is_unknown_never_free_text(loaded, capsys):
    policy, route = loaded
    app = object()
    async def indirect():
        candidate = policy.FinancialResourceLimit('DO_NOT_EMIT_exception_raw_OR_body_OR_cookie')
        raise candidate
    with observer.observe_financial_limit(app):
        assert reject(route, app, receive=indirect).status_code == 413
    value = records(capsys)[0]
    assert value['observations'][0]['site'] == 'UNKNOWN'
    assert 'DO_NOT_EMIT' not in json.dumps(value)


def test_finite_integer_domains_count_field_and_no_deadline_read(loaded):
    policy, _ = loaded
    meter = policy.Meter()
    descriptor = vars(policy.Meter)['__dict__']
    class Poison:
        def __repr__(self):
            raise AssertionError('no representation')
        def __eq__(self, other):
            raise AssertionError('no comparison')
    for operations, expected in ((0, 0), (5000, 5000), (5001, 5001), (5002, None), (True, None), (Poison(), None)):
        meter.operations = operations
        for cap in (8192, 65536, 110592, 131072, 524288, 1, True, Poison()):
            values = observer._numbers({'self': meter, 'cap': cap, 'count': 20001, 'nodes': 7, 'depth': 33}, policy.Meter, descriptor)
            assert values[0] == (cap if type(cap) is int and cap in observer._CAPS else None)
            assert values[1:] == (expected, 20001, 33)
    assert observer._numbers({'meter': Poison(), 'count': True, 'depth': 34}, policy.Meter, descriptor) == (None, None, None, None)


def test_original_constructor_failure_not_swallowed_or_replaced(loaded):
    policy, _ = loaded
    capture = observer._Observation(object())
    failure = RuntimeError('synthetic original constructor failure')
    def original(error, *args, **kwargs):
        raise failure
    wrapper = observer._make_init(capture, original, policy.FinancialResourceLimit)
    error = ValueError.__new__(policy.FinancialResourceLimit)
    with pytest.raises(RuntimeError) as caught:
        wrapper(error, 'original')
    assert caught.value is failure and capture._count == 0 and not capture._fault
    with observer.observe_financial_limit(object()):
        with pytest.raises(TypeError):
            policy.FinancialResourceLimit(unexpected='unchanged native ctor rule')


@pytest.mark.parametrize('failure', [RuntimeError, TimeoutError, asyncio.CancelledError])
def test_primary_error_cancellation_and_observer_fault_restore(loaded, monkeypatch, capsys, failure):
    policy, route = loaded
    app = object()
    with pytest.raises(failure):
        with observer.observe_financial_limit(app) as capture:
            def broken(frame):
                raise AssertionError('private observer failure')
            monkeypatch.setattr(capture, '_capture', broken)
            assert reject(route, app).status_code == 413
            raise failure()
    assert '__init__' not in vars(policy.FinancialResourceLimit)
    value = records(capsys)[0]
    assert value['observer_fault'] and value['restore'] == 'RESTORED'


def test_restore_conflict_never_overwrites_other_initializer(loaded, capsys):
    policy, _ = loaded
    cls = policy.FinancialResourceLimit
    def foreign(error, *args, **kwargs):
        ValueError.__init__(error, *args, **kwargs)
    try:
        with pytest.raises(TimeoutError):
            with observer.observe_financial_limit(object()):
                type.__setattr__(cls, '__init__', foreign)
                raise TimeoutError()
        assert vars(cls)['__init__'] is foreign
        assert records(capsys)[0]['restore'] == 'UNCERTAIN'
    finally:
        if vars(cls).get('__init__') is foreign:
            type.__delattr__(cls, '__init__')


def test_encoding_and_output_failure_do_not_hide_primary(loaded, monkeypatch, capsys):
    _, route = loaded
    app = object()
    with monkeypatch.context() as change:
        def bad_encode(record):
            raise ValueError('untrusted diagnostic serialization')
        change.setattr(observer, '_encode', bad_encode)
        with observer.observe_financial_limit(app):
            assert reject(route, app).status_code == 413
    value = records(capsys)[0]
    assert value['observer_fault'] and value['restore'] == 'UNCERTAIN'
    with monkeypatch.context() as change:
        def bad_print(*args, **kwargs):
            raise OSError('owned output unavailable')
        change.setattr('builtins.print', bad_print)
        with pytest.raises(TimeoutError):
            with observer.observe_financial_limit(app):
                raise TimeoutError()


def test_unavailable_source_and_nested_owner_do_not_patch_or_leak(loaded, monkeypatch, capsys):
    policy, route = loaded
    app = object()
    with observer.observe_financial_limit(app) as outer:
        wrapper = vars(policy.FinancialResourceLimit)['__init__']
        with observer.observe_financial_limit(app) as inner:
            assert inner._setup == 'UNAVAILABLE'
            assert vars(policy.FinancialResourceLimit)['__init__'] is wrapper
        assert vars(policy.FinancialResourceLimit)['__init__'] is wrapper
        assert reject(route, app).status_code == 413
    values = records(capsys)
    assert values[0]['restore'] == 'UNINSTALLED' and values[1]['restore'] == 'RESTORED'
    with monkeypatch.context() as change:
        change.setattr(observer, 'SOURCE_PINS', {**observer.SOURCE_PINS, 'web/backend/research/financial_policy.py': '0' * 64})
        with observer.observe_financial_limit(app) as capture:
            assert capture._setup == 'UNAVAILABLE' and '__init__' not in vars(policy.FinancialResourceLimit)
    assert records(capsys)[0]['setup'] == 'UNAVAILABLE'
    assert outer._app is outer._policy_module is outer._exception_class is None
    assert outer._specs == outer._modules == outer._codes == outer._anchors == {}


def test_no_request_frame_or_exception_survives_context(loaded, capsys):
    _, route = loaded
    class App:
        pass
    app = App()
    request = request_for(app)
    request_ref, app_ref = weakref.ref(request), weakref.ref(app)
    with observer.observe_financial_limit(app) as capture:
        result = asyncio.run(route._dispatch_financial_result(request, None, None, 'synthetic', 'financial-calculate'))
        assert result.status_code == 413
    del request, app, result
    gc.collect()
    assert request_ref() is app_ref() is None
    assert capture._app is None and observer._ACTIVE is None
    records(capsys)


def test_private_hot_path_has_no_io_compile_hash_clock_or_import():
    functions = (observer._make_init, observer._Observation._capture, observer._Observation._site,
        observer._Observation._memory_code, observer._Observation._raw_module, observer._Observation._request_scope,
        observer._function_code, observer._numbers, observer._integer)
    forbidden = {'open', 'read', 'read_bytes', 'write', 'write_text', 'resolve', 'stat', 'compile',
        'sha256', 'digest', 'monotonic', 'perf_counter', 'time', 'import_module', '__import__'}
    for function in functions:
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))
        calls = [n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else '' for n in ast.walk(tree) if isinstance(n, ast.Call)]
        assert not forbidden.intersection(calls)
    # Two maximum-domain observations and all metadata fit the hard line cap.
    sample = {'schema': 'FIN3_LIMIT_OBS_V1', 'case': observer.CASE, 'setup': 'READY', 'response': 'HTTP_413',
        'events': '2_PLUS', 'observations': [{'event': 'DIRECT_RAISE_CONSTRUCTION', 'site': row[0],
            'category': row[4], 'cap': 524288, 'operations': 5001, 'nodes': 20001, 'depth': 33}
            for row in (observer.SITES[7], observer.SITES[12])],
        'overflow': True, 'observer_fault': False, 'restore': 'RESTORED', 'catch_link': 'UNOBSERVED'}
    assert len(observer._encode(sample)) + 1 <= 2048
    sample['catch_link'] = 'SAME_INSTANCE'
    with pytest.raises(ValueError):
        observer._encode(sample)


@pytest.mark.parametrize('levels, expected', [(5, '1'), (80, '0')])
def test_request_stack_scan_is_bounded_to_sixty_four_frames(loaded, capsys, levels, expected):
    policy, route = loaded
    app = object()
    def recurse(remaining):
        if remaining:
            return recurse(remaining - 1)
        raise policy.FinancialResourceLimit('private deep synthetic failure')
    async def deep_rejection():
        recurse(levels)
    with observer.observe_financial_limit(app):
        assert reject(route, app, receive=deep_rejection).status_code == 413
    value = records(capsys)[0]
    assert value['events'] == expected
    if expected == '1':
        assert value['observations'][0]['site'] == 'UNKNOWN'


def test_existing_initializer_unavailable_and_no_arbitrary_class_lookup(loaded, capsys):
    policy, _ = loaded
    cls = policy.FinancialResourceLimit
    def prior(error, *args, **kwargs):
        ValueError.__init__(error, *args, **kwargs)
    try:
        type.__setattr__(cls, '__init__', prior)
        with observer.observe_financial_limit(object()) as capture:
            assert capture._setup == 'UNAVAILABLE'
        assert vars(cls)['__init__'] is prior
        assert records(capsys)[0]['restore'] == 'UNINSTALLED'
    finally:
        type.__delattr__(cls, '__init__')
    class Poison:
        @property
        def __class__(self):
            raise AssertionError('untrusted __class__ property invoked')
    assert observer._function_code({'Owner': Poison(), '__name__': 'synthetic'}, 'Owner.member') is None


def test_original_step_short_circuit_retains_5001_without_reading_clock(loaded, capsys):
    policy, route = loaded
    app = object()
    meter = policy.Meter()
    meter.operations = 5000  # Pure boundary fixture; original deadline/code stay unchanged.
    async def step_rejection():
        meter.tick()
    with observer.observe_financial_limit(app):
        assert reject(route, app, receive=step_rejection).status_code == 413
    row = records(capsys)[0]['observations'][0]
    assert row['site'] == 'L13' and row['operations'] == 5001
    assert row['category'] == 'STEPS_OR_DEADLINE'  # Do not assert deadline elapsed.


@pytest.mark.parametrize('kind, expected_count, expected_depth', [('nodes', 20001, 1), ('depth', 34, 33)])
def test_existing_bounded_count_depth_and_cap_are_observed(loaded, capsys, kind, expected_count, expected_depth):
    _, route = loaded
    result = importlib.import_module('research.financial_result_v2')
    app = object()
    if kind == 'nodes':
        value = [None] * 20000
    else:
        value = None
        for _ in range(33):
            value = [value]
    async def bounded_rejection():
        result.bounded(value, 131072)
    with observer.observe_financial_limit(app):
        assert reject(route, app, receive=bounded_rejection).status_code == 413
    row = records(capsys)[0]['observations'][0]
    assert row['site'] == 'L22' and row['cap'] == 131072
    assert row['nodes'] == expected_count and row['depth'] == expected_depth
    assert row['operations'] is None


def test_poison_module_dictionary_fields_are_not_user_callbacks(loaded, monkeypatch, capsys):
    _, route = loaded
    app = object()
    module = importlib.import_module('research.financial_result_adapter')
    actual = module._parse
    class Poison:
        def __eq__(self, other):
            raise AssertionError('untrusted module equality callback')
    foreign = types.ModuleType('research.financial_result_adapter')
    vars(foreign).update(vars(module))
    vars(foreign)['__name__'] = Poison()
    with observer.observe_financial_limit(app):
        with monkeypatch.context() as change:
            change.setitem(sys.modules, 'research.financial_result_adapter', foreign)
            async def rejection():
                actual(None)
            assert reject(route, app, receive=rejection).status_code == 413
    record = records(capsys)[0]
    assert record['observations'][0]['site'] == 'UNKNOWN' and record['observer_fault'] is False
    class Owner:
        @property
        def member(self):
            raise AssertionError('untrusted class descriptor callback')
    assert observer._function_code({'Owner': Owner, '__name__': 'synthetic'}, 'Owner.member') is None


def test_class_dictionary_probe_never_invokes_metaclass_property():
    class DangerousMeta(type):
        @property
        def __dict__(cls):
            raise AssertionError('metaclass dictionary property must not execute')
    class Owner(metaclass=DangerousMeta):
        member = property(lambda self: None)
    assert observer._function_code({'Owner': Owner, '__name__': 'synthetic'}, 'Owner.member') is None
