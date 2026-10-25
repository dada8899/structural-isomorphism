"""Test-only direct-raise construction evidence, never permission or API-catch proof.

Source work is cold setup; the temporary real-class initializer only inspects
bounded existing frames and primitive integers. No worker tracing is installed.
"""
from contextlib import contextmanager
import ast
import hashlib
import json
from pathlib import Path
import sys
import types

PREFIX = 'FIN3_LIMIT_OBS_V1 '
CASE = 'THREE_SCENARIOS_21_POINTS'
ROOT = Path(__file__).resolve().parents[4]
# Literal reviewed coordinates; API is compiled from the actual current source,
# while the financial closure is byte-pinned. No old whole-API hash is reused.
SITES = (('L01', 'web/backend/api/research.py', 97, '_dispatch_financial_result', 'REQUEST_WIRE_BYTES'),
 ('L02',
  'web/backend/research/financial_evaluator.py',
  260,
  'FinancialSnapshot.__post_init__',
  'SNAPSHOT_BYTES'),
 ('L03', 'web/backend/research/financial_evaluator.py', 361, 'evaluate_financial', 'DECIMAL_CONDITION'),
 ('L04', 'web/backend/research/financial_evaluator.py', 481, '_OwnerEvaluation.record', 'PROVENANCE_COUNT'),
 ('L05',
  'web/backend/research/financial_evaluator.py',
  635,
  'evaluate_owner_financial_v2',
  'EVALUATOR_DEADLINE'),
 ('L06',
  'web/backend/research/financial_evaluator.py',
  638,
  'evaluate_owner_financial_v2',
  'DECIMAL_CONDITION'),
 ('L07',
  'web/backend/research/financial_execution.py',
  188,
  'CurrentFinancialExecution.check_deadline',
  'ORIGINAL_DEADLINE'),
 ('L08', 'web/backend/research/financial_execution.py', 270, 'execute', 'COMPLETION_DEADLINE_OR_COUNT'),
 ('L09', 'web/backend/research/financial_policy.py', 40, 'number', 'INPUT_PRECISION_OR_EXPONENT'),
 ('L10', 'web/backend/research/financial_policy.py', 43, 'number', 'INPUT_EXPONENT_RANGE'),
 ('L11', 'web/backend/research/financial_policy.py', 45, 'number', 'INPUT_ABSOLUTE'),
 ('L12', 'web/backend/research/financial_policy.py', 60, 'json_cap', 'JSON_BYTES'),
 ('L13', 'web/backend/research/financial_policy.py', 73, 'Meter.tick', 'STEPS_OR_DEADLINE'),
 ('L14', 'web/backend/research/financial_policy.py', 87, 'Meter.calculate', 'COMPUTED_MAGNITUDE'),
 ('L15', 'web/backend/research/financial_result_adapter.py', 33, '_Budget.check', 'ADAPTER_DEADLINE'),
 ('L16', 'web/backend/research/financial_result_adapter.py', 49, '_bounded', 'JSON_NODES_OR_DEPTH'),
 ('L17', 'web/backend/research/financial_result_adapter.py', 64, '_bounded', 'JSON_BYTES'),
 ('L18', 'web/backend/research/financial_result_adapter.py', 68, '_bounded', 'INTEGER_BITS'),
 ('L19', 'web/backend/research/financial_result_adapter.py', 71, '_bounded', 'JSON_BYTES'),
 ('L20', 'web/backend/research/financial_result_adapter.py', 78, '_parse', 'JSON_BYTES'),
 ('L21', 'web/backend/research/financial_result_adapter.py', 81, '_parse', 'JSON_BYTES'),
 ('L22', 'web/backend/research/financial_result_v2.py', 40, 'bounded', 'JSON_NODES_OR_DEPTH'),
 ('L23', 'web/backend/research/financial_result_v2.py', 49, 'bounded', 'JSON_BYTES'),
 ('L24', 'web/backend/research/financial_result_v2.py', 51, 'bounded', 'INTEGER_BITS'),
 ('L25', 'web/backend/research/financial_result_v2.py', 53, 'bounded', 'JSON_BYTES'),
 ('L26', 'web/backend/research/financial_result_v2.py', 208, 'DerivedFXInputV1.check', 'FX_DATE_COUNT'),
 ('L27',
  'web/backend/research/financial_result_v2.py',
  264,
  'decode_financial_calculation',
  'OPERATION_BYTES_OR_TYPE'),
 ('L28', 'web/backend/research/financial_result_v2.py', 1239, '_validate_stored', 'SAVED_COLUMNS_BYTES'),
 ('L29', 'web/backend/research/financial_result_v2.py', 1268, '_saved_response', 'PUBLIC_BYTES_WITH_RESERVE'),
 ('L30', 'web/backend/research/financial_schemas.py', 49, 'tuple_limit', 'OBJECT_COUNT'),
 ('L31', 'web/backend/research/financial_schemas.py', 59, 'array', 'ARRAY_COUNT'))
SOURCE_PINS = {'web/backend/research/financial_evaluator.py': 'b6f4d2474680a0bc8e2868325cb1006404a8c98bce563330e8619b5ae5ca08b4',
 'web/backend/research/financial_execution.py': '3c01504b75272d1140b2a166185575812c5608f5eb9f1852657514e3cd443d79',
 'web/backend/research/financial_policy.py': '719792b41ebbfce6d69ceea25f77e1ad8ba1458d4a245750db206de9ea03cd02',
 'web/backend/research/financial_result_adapter.py': '8b784f74da182ca2b3bf2265d3d83fa6e5079644872fc91f1f30234540e083bf',
 'web/backend/research/financial_result_v2.py': 'fdaaed8e19058e41932efcbe574636469ffce3fff5ef0b6b40c6ca0eb627366f',
 'web/backend/research/financial_schemas.py': '47da16217d08dfd2dd87a0b2feb3cb17f7b19d88188b0ec6896fd08d0d6a72e7',
 'web/backend/research/financial_input_schemas.py': 'a1691d3e29827aef4d50fbc8a98320292d949ec7b62d6bc20555a921e704bb11',
 'web/backend/research/financial_input.py': 'a7f687d272482f1ca9477c051ef5232d097f4c4ed38c160ab95d331646537728',
 'web/backend/research/financial_input_guard.py': '14b70a48bb2a08d3fe649ca1dd2d4bd705dd9bac1fe48a855320d602302a8925',
 'web/backend/research/financial_import.py': 'ffda3ccacb52090a31fe129471d31bddaed7b722ae2fc89673580f7939da5395'}

_CAPS = frozenset((8192, 65536, 110592, 131072, 524288))
_ACTIVE = None
_TYPE_DICT = vars(type)['__dict__']
_OBSERVATION_KEYS = frozenset(('event', 'site', 'category', 'cap', 'operations', 'nodes', 'depth'))
_RECORD_KEYS = frozenset(('schema', 'case', 'setup', 'response', 'events', 'observations',
    'overflow', 'observer_fault', 'restore', 'catch_link'))
_CATEGORIES = {row[0]: row[4] for row in SITES}
_FALLBACK = PREFIX + '{"schema":"FIN3_LIMIT_OBS_V1","case":"THREE_SCENARIOS_21_POINTS","setup":"UNAVAILABLE","response":"UNOBSERVED","events":"0","observations":[],"overflow":false,"observer_fault":true,"restore":"UNCERTAIN","catch_link":"UNOBSERVED"}'


def _module_name(relative):
    if relative == 'web/backend/api/research.py':
        return 'api.research'
    return 'research.' + relative.rsplit('/', 1)[1][:-3]


def _code_tree(code):
    yield code
    for item in code.co_consts:
        if type(item) is types.CodeType:
            yield from _code_tree(item)


def _direct_sites(raw):
    """Cold AST proof, including the closest real function/class owner."""
    tree = ast.parse(raw)
    result = {}
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.owners = []
        def visit_ClassDef(self, node):
            self.owners.append(node.name)
            self.generic_visit(node)
            self.owners.pop()
        def visit_FunctionDef(self, node):
            self.owners.append(node.name)
            self.generic_visit(node)
            self.owners.pop()
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Raise(self, node):
            call = node.exc
            if (type(call) is ast.Call and type(call.func) is ast.Name
                    and call.func.id == 'FinancialResourceLimit'):
                result[node.lineno] = '.'.join(self.owners)
    visitor = Visitor()
    visitor.visit(tree)
    return result


def _function_code(namespace, qualname):
    """Finite plain-dictionary lookups; never bind a caller descriptor."""
    parts = qualname.split('.')
    if not 1 <= len(parts) <= 4:
        return None
    value = namespace.get(parts[0])
    for part in parts[1:]:
        try:
            # Calling type.__getattribute__ still runs metaclass data
            # descriptors. This captured native getset reads only tp_dict.
            fields = _TYPE_DICT.__get__(value, type(value))
        except TypeError:
            return None
        if type(fields) is not types.MappingProxyType:
            return None
        value = fields.get(part)
    if (type(value) is not types.FunctionType or value.__globals__ is not namespace
            or type(value.__module__) is not str or type(namespace.get('__name__')) is not str
            or value.__module__ != namespace['__name__'] or type(value.__qualname__) is not str
            or value.__qualname__ != qualname):
        return None
    return value.__code__


def _integer(value, maximum):
    return value if type(value) is int and 0 <= value <= maximum else None


def _numbers(local, meter_class, meter_dict):
    """No property, raw text, deadline, clock, encoding, or object retained."""
    cap = local.get('cap')
    cap = cap if type(cap) is int and cap in _CAPS else None
    operations = None
    for key in ('meter', 'self'):
        candidate = local.get(key)
        if type(candidate) is meter_class:
            fields = meter_dict.__get__(candidate, meter_class)
            if type(fields) is dict:
                operations = _integer(fields.get('operations'), 5001)
            break
    return cap, operations, _integer(local.get('count'), 20001), _integer(local.get('depth'), 33)


def _encode(record):
    """One closed ASCII record; fail closed even if test state was corrupted."""
    if type(record) is not dict or set(record) != _RECORD_KEYS:
        raise ValueError('observer record shape')
    if any(type(record[key]) is not str for key in ('schema', 'case', 'setup', 'response', 'events', 'restore', 'catch_link')):
        raise ValueError('observer closed string fields')
    if (record['schema'] != 'FIN3_LIMIT_OBS_V1' or record['case'] != CASE
            or record['setup'] not in ('READY', 'UNAVAILABLE')
            or record['response'] not in ('HTTP_200', 'HTTP_413', 'OTHER', 'UNOBSERVED')
            or record['events'] not in ('0', '1', '2_PLUS')
            or record['restore'] not in ('RESTORED', 'UNINSTALLED', 'UNCERTAIN')
            or record['catch_link'] != 'UNOBSERVED'
            or type(record['overflow']) is not bool or type(record['observer_fault']) is not bool):
        raise ValueError('observer record domain')
    rows = record['observations']
    if type(rows) is not list or len(rows) > 2:
        raise ValueError('observer event bound')
    for row in rows:
        if type(row) is not dict or set(row) != _OBSERVATION_KEYS:
            raise ValueError('observer observation shape')
        if any(type(row[key]) is not str for key in ('event', 'site', 'category')):
            raise ValueError('observer closed observation strings')
        site = row['site']
        if (type(site) is not str or site not in (*_CATEGORIES, 'UNKNOWN')
                or row['event'] != 'DIRECT_RAISE_CONSTRUCTION'
                or row['category'] != _CATEGORIES.get(site, 'UNKNOWN')):
            raise ValueError('observer site domain')
        for key, maximum in (('operations', 5001), ('nodes', 20001), ('depth', 33)):
            if row[key] is not None and _integer(row[key], maximum) is None:
                raise ValueError('observer finite integer')
        if row['cap'] is not None and (type(row['cap']) is not int or row['cap'] not in _CAPS):
            raise ValueError('observer cap domain')
    line = PREFIX + json.dumps(record, ensure_ascii=True, separators=(',', ':'))
    if not line.isascii() or len(line) + 1 > 2048:
        raise ValueError('observer record byte bound')
    return line


def _make_init(observation, original, exception_class):
    def observed_init(error, *args, **kwargs):
        # This call is deliberately outside the observation error boundary.
        # Its native argument semantics and any original failure propagate.
        original(error, *args, **kwargs)
        try:
            if observation._armed and type(error) is exception_class:
                frame = sys._getframe(1)
                try:
                    observation._capture(frame)
                finally:
                    del frame
        except BaseException:
            observation._fault = True
        return None
    return observed_init


class _Observation:
    def __init__(self, app):
        self._app = app
        self._setup, self._response, self._restore = 'UNAVAILABLE', 'UNOBSERVED', 'UNINSTALLED'
        self._count, self._observations = 0, []
        self._overflow = self._fault = self._armed = self._attempted = False
        self._exception_class = self._wrapper = self._meter_class = self._meter_dict = None
        self._request_class = self._request_dict = None
        self._policy_module = self._policy_globals = None
        self._specs, self._modules, self._codes, self._anchors = {}, {}, {}, {}
        self._route_path = str(ROOT / 'web/backend/api/research.py')

    def response(self, status):
        self._response = ('HTTP_200' if status == 200 else 'HTTP_413' if status == 413 else 'OTHER') if type(status) is int else 'OTHER'

    def _raw_module(self, name, path):
        module = sys.modules.get(name)
        if type(module) is not types.ModuleType:
            return None
        namespace = types.ModuleType.__getattribute__(module, '__dict__')
        if (type(namespace) is not dict or type(namespace.get('__name__')) is not str or namespace['__name__'] != name
                or type(namespace.get('__file__')) is not str or namespace['__file__'] != path):
            return None
        return module, namespace

    def _prepare(self):
        policy_path = str(ROOT / 'web/backend/research/financial_policy.py')
        policy = self._raw_module('research.financial_policy', policy_path)
        if policy is None or self._app is None:
            raise ValueError('actual loaded financial policy required')
        self._policy_module, self._policy_globals = policy
        namespace = self._policy_globals
        cls, base, meter = (namespace.get(name) for name in ('FinancialResourceLimit', 'FinancialError', 'Meter'))
        if (type(cls) is not type or type(base) is not type or type(meter) is not type
                or cls.__mro__ != (cls, base, ValueError, Exception, BaseException, object)
                or '__init__' in vars(cls) or '__init__' in vars(base)
                or cls.__init__ is not ValueError.__init__
                or cls.__module__ != 'research.financial_policy' or cls.__qualname__ != 'FinancialResourceLimit'):
            raise ValueError('original financial exception class required')
        self._exception_class, self._meter_class = cls, meter
        self._meter_dict = vars(meter).get('__dict__')
        if type(self._meter_dict) is not types.GetSetDescriptorType:
            raise ValueError('native Meter dictionary required')
        relatives = set(SOURCE_PINS) | {'web/backend/api/research.py'}
        for relative in sorted(relatives):
            path = ROOT / relative
            if path.is_symlink() or path.resolve() != path or path.stat().st_size > 1048576:
                raise ValueError('fixed observer source required')
            raw = path.read_bytes()
            if relative in SOURCE_PINS and hashlib.sha256(raw).hexdigest() != SOURCE_PINS[relative]:
                raise ValueError('financial observer source changed')
            code_groups = {}
            for code in _code_tree(compile(raw, str(path), 'exec', dont_inherit=True)):
                code_groups.setdefault(code.co_qualname, []).append(code)
            expected = {name: codes[0] for name, codes in code_groups.items() if len(codes) == 1}
            rows = tuple(row for row in SITES if row[1] == relative)
            direct = _direct_sites(raw)
            if any(direct.get(row[2]) != row[3] or row[3] not in expected for row in rows):
                raise ValueError('literal direct raise changed')
            self._specs[str(path)] = (relative, _module_name(relative), expected, {row[2]: row for row in rows})
            for family in ('research.', 'web.backend.research.') if relative.startswith('web/backend/research/') else ('api.', 'web.backend.api.'):
                name = family + relative.rsplit('/', 1)[1][:-3]
                loaded = sys.modules.get(name)
                if loaded is not None:
                    if type(loaded) is not types.ModuleType:
                        raise ValueError('actual financial module required')
                    fields = types.ModuleType.__getattribute__(loaded, '__dict__')
                    if 'FinancialResourceLimit' in fields and fields['FinancialResourceLimit'] is not cls:
                        raise ValueError('financial exception alias differs')
            loaded = self._raw_module(_module_name(relative), str(path))
            if loaded is not None:
                self._modules[_module_name(relative)] = loaded
                for row in rows:
                    code = _function_code(loaded[1], row[3])
                    if code is None or code.co_filename != str(path) or code.co_qualname != row[3] or code != expected[row[3]]:
                        raise ValueError('loaded financial function differs')
                    self._codes[(_module_name(relative), row[3])] = code
        route_path = str(ROOT / 'web/backend/api/research.py')
        route = self._raw_module('api.research', route_path)
        if route is None:
            raise ValueError('actual loaded financial route required')
        from starlette.requests import Request
        self._request_class = Request
        if route[1].get('Request') is not Request:
            raise ValueError('actual Request class required')
        for ancestor in Request.__mro__:
            descriptor = vars(ancestor).get('__dict__')
            if type(descriptor) is types.GetSetDescriptorType:
                self._request_dict = descriptor
                break
        if self._request_dict is None:
            raise ValueError('native Request dictionary required')
        expected = self._specs[route_path][2]
        for name in ('_dispatch_financial_result', '_calculate_financial_in_request'):
            code = _function_code(route[1], name)
            if code is None or code.co_filename != route_path or code.co_qualname != name or code != expected[name]:
                raise ValueError('actual financial request frame changed')
            self._anchors[name] = code
        if route[1].get('_FINANCIAL_BRIDGE') is not route[1].get('_calculate_financial_in_request'):
            raise ValueError('fixed financial bridge required')
        # The Meter class is unchanged; source-equivalent methods are checked
        # before installing the only permitted temporary class attribute.
        policy_expected = self._specs[policy_path][2]
        for name in ('Meter.__init__', 'Meter.tick', 'Meter.calculate', 'Meter.display'):
            code = _function_code(namespace, name)
            if code is None or code.co_filename != policy_path or code.co_qualname != name or code != policy_expected[name]:
                raise ValueError('original Meter methods required')

    def _install(self):
        global _ACTIVE
        if _ACTIVE is not None:
            return
        _ACTIVE = self
        self._prepare()
        cls = self._exception_class
        self._wrapper = _make_init(self, cls.__init__, cls)
        self._attempted = True
        type.__setattr__(cls, '__init__', self._wrapper)
        self._armed, self._setup = True, 'READY'

    def _memory_code(self, path, qualname):
        spec = self._specs.get(path)
        if spec is None:
            return None
        _, name, expected, _ = spec
        loaded = self._raw_module(name, path)
        if loaded is None:
            return None
        bound = self._modules.get(name)
        if bound is not None and (bound[0] is not loaded[0] or bound[1] is not loaded[1]):
            return None
        # API imports the real exception into its dispatch locals, whereas
        # financial modules have the fixed module-global reference.
        if (name != 'api.research' or 'FinancialResourceLimit' in loaded[1]) and loaded[1].get('FinancialResourceLimit') is not self._exception_class:
            return None
        actual = _function_code(loaded[1], qualname)
        if (actual is None or type(actual.co_filename) is not str or type(actual.co_qualname) is not str
                or actual.co_filename != path or actual.co_qualname != qualname or actual != expected.get(qualname)):
            return None
        key = (name, qualname)
        if key in self._codes and self._codes[key] is not actual:
            return None
        # Late binding only uses already-present real dictionaries/code. All
        # source reads, AST validation and compilation finished in _prepare.
        self._modules[name] = loaded
        self._codes[key] = actual
        return loaded[1], actual

    def _site(self, frame):
        path = frame.f_code.co_filename
        if type(path) is not str:
            return None
        spec = self._specs.get(path)
        row = spec[3].get(frame.f_lineno) if spec else None
        if row is None:
            return None
        bound = self._memory_code(frame.f_code.co_filename, row[3])
        if bound is None or frame.f_globals is not bound[0] or frame.f_code is not bound[1]:
            return None
        if row[0] == 'L01' and frame.f_locals.get('FinancialResourceLimit') is not self._exception_class:
            return None
        return row

    def _request_scope(self, frame):
        name = frame.f_code.co_name
        if type(name) is not str or name not in self._anchors or frame.f_code is not self._anchors[name]:
            return False
        bound = self._memory_code(self._route_path, name)
        if bound is None or frame.f_globals is not bound[0] or frame.f_code is not bound[1]:
            return False
        request = frame.f_locals.get('request')
        if type(request) is not self._request_class:
            return False
        fields = self._request_dict.__get__(request, self._request_class)
        scope = fields.get('scope') if type(fields) is dict else None
        return type(scope) is dict and scope.get('app') is self._app

    def _capture(self, caller):
        if (sys.modules.get('research.financial_policy') is not self._policy_module
                or types.ModuleType.__getattribute__(self._policy_module, '__dict__') is not self._policy_globals
                or self._policy_globals.get('FinancialResourceLimit') is not self._exception_class):
            return
        row = self._site(caller)
        cap = operations = nodes = depth = None
        if row is not None:
            cap, operations, nodes, depth = _numbers(caller.f_locals, self._meter_class, self._meter_dict)
        frame, matched = caller, False
        try:
            for _ in range(64):
                if frame is None:
                    break
                if row is not None and operations is None and self._site(frame) is not None:
                    _, operations, _, _ = _numbers(frame.f_locals, self._meter_class, self._meter_dict)
                if self._request_scope(frame):
                    matched = True
                    break
                frame = frame.f_back
        finally:
            del frame
        if not matched:
            return
        observation = {'event': 'DIRECT_RAISE_CONSTRUCTION',
            'site': row[0] if row else 'UNKNOWN', 'category': row[4] if row else 'UNKNOWN',
            'cap': cap, 'operations': operations, 'nodes': nodes, 'depth': depth}
        self._count = min(3, self._count + 1)
        if len(self._observations) < 2:
            self._observations.append(observation)
        else:
            self._overflow = True

    def _close(self):
        global _ACTIVE
        self._armed = False
        try:
            if self._attempted:
                cls = self._exception_class
                if vars(cls).get('__init__') is self._wrapper:
                    type.__delattr__(cls, '__init__')
                    self._restore = 'RESTORED'
                else:
                    self._restore = 'UNCERTAIN'
        except BaseException:
            self._restore = 'UNCERTAIN'
            self._fault = True
        finally:
            if _ACTIVE is self:
                _ACTIVE = None
            self._app = self._exception_class = self._wrapper = None
            self._meter_class = self._meter_dict = self._request_class = self._request_dict = None
            self._policy_module = self._policy_globals = None
            self._specs.clear(); self._modules.clear(); self._codes.clear(); self._anchors.clear()

    def _record(self):
        return {'schema': 'FIN3_LIMIT_OBS_V1', 'case': CASE, 'setup': self._setup,
            'response': self._response, 'events': ('0', '1', '2_PLUS')[min(2, self._count)],
            'observations': self._observations.copy(), 'overflow': self._overflow,
            'observer_fault': self._fault, 'restore': self._restore, 'catch_link': 'UNOBSERVED'}

    def _emit(self):
        try:
            line = _encode(self._record())
        except BaseException:
            line = _FALLBACK
        try:
            print(line, flush=True)
        except BaseException:
            # Output is diagnostic only; never replace the primary test error.
            pass


@contextmanager
def observe_financial_limit(app):
    """Scope to the one already-prepared real browser POST; no permission port."""
    observation = _Observation(app)
    try:
        try:
            observation._install()
        except BaseException:
            observation._fault = True
        yield observation
    finally:
        observation._close()
        observation._emit()
