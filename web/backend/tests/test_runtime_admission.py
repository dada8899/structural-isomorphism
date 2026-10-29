"""Real import/request boundaries in isolated processes; no gate stubs."""
from pathlib import Path
import json
import os
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'web/backend'

# Every filesystem mutation and database connection is rejected before it can
# happen. .env loading is suppressed: tests use synthetic process configuration.
PRELUDE = r'''
import asyncio, builtins, io, json, os, pathlib, socket, sqlite3, sys
import dotenv
import httpx
from starlette.staticfiles import StaticFiles
os.environ.clear()
os.environ.update(TEST_ENV)
sys.dont_write_bytecode = True
sys.path[:0] = [BACKEND, ROOT]
dotenv.load_dotenv = lambda *a, **k: False
attempts = []
class PreventWrite(RuntimeError): pass
real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

def guarded_open(real):
    def call(file, mode='r', *a, **k):
        if isinstance(mode, str) and any(c in mode for c in 'wax+'):
            attempts.append('file-write')
            raise PreventWrite('unexpected file write')
        return real(file, mode, *a, **k)
    return call
builtins.open = guarded_open(real_open)
io.open = guarded_open(real_io_open)
def os_open(path, flags, *a, **k):
    if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        attempts.append('os-write')
        raise PreventWrite('unexpected os write')
    return real_os_open(path, flags, *a, **k)
os.open = os_open

def deny_mutation(*a, **k):
    attempts.append('fs-mutation')
    raise PreventWrite('unexpected filesystem mutation')
for name in ('mkdir', 'rename', 'replace', 'unlink', 'remove', 'rmdir', 'chmod', 'symlink', 'link'):
    setattr(os, name, deny_mutation)
def no_db(*a, **k):
    attempts.append('sqlite')
    raise PreventWrite('unexpected database connection')
sqlite3.connect = no_db
real_socket = socket.socket
class NoNetwork(real_socket):
    def __init__(self, family=socket.AF_INET, *a, **k):
        if family in (socket.AF_INET, socket.AF_INET6):
            attempts.append('network')
            raise PreventWrite('unexpected network socket')
        super().__init__(family, *a, **k)
socket.socket = NoNetwork
'''


def isolated(tmp_path, body, *, prod=True):
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': str(tmp_path / 'unused-home'),
           'PYTHONDONTWRITEBYTECODE': '1', 'STRUCTURAL_ENV': 'prod' if prod else 'dev',
           'AUTH_ENABLED': 'true'}
    script = (f'ROOT={str(ROOT)!r}\nBACKEND={str(BACKEND)!r}\nTEST_ENV={env!r}\n'
              + PRELUDE + '\n' + body)
    result = subprocess.run([sys.executable, '-B', '-c', script], cwd=BACKEND,
                            env=env, text=True, capture_output=True, timeout=40)
    assert result.returncode == 0, (result.stdout[-3500:], result.stderr[-3500:])
    lines = [line for line in result.stdout.splitlines() if line.startswith('R2_RESULT:')]
    assert len(lines) == 1, result.stdout[-3500:]
    return json.loads(lines[0][len('R2_RESULT:'):])


@pytest.mark.parametrize('first', ['logging', 'legacy-auth', 'legacy-history', 'unknown-profile'])
def test_fresh_formal_import_has_no_file_or_database_side_effects(tmp_path, first):
    value = isolated(tmp_path, f'''
first = {first!r}
if first == 'unknown-profile':
    os.environ.pop('STRUCTURAL_ENV')
    import logging_config
    logging_config.get_logger('structural.bootstrap').info('startup.bootstrap')
    # Model the effective profile being set by main's environment loader.
    dotenv.load_dotenv = lambda *a, **k: os.environ.update(STRUCTURAL_ENV='prod') or False
elif first == 'logging':
    import logging_config
    logging_config.get_logger('structural.bootstrap').info('startup.bootstrap')
elif first == 'legacy-auth':
    import api.auth
else:
    import api.history
import main
assert main._IS_PROD is True
assert attempts == [], attempts
print('R2_RESULT:' + json.dumps({{'attempts': attempts, 'prod': main._IS_PROD}}))
''')
    assert value == {'attempts': [], 'prod': True}


def test_actual_formal_asgi_without_lifespan_blocks_all_consumers_and_static(tmp_path):
    value = isolated(tmp_path, r'''
import main
import api.auth as auth
import api.history as history
import api.favorites as favorites
import auth.api_key as api_key
import services.search_service as search_service
from services.runtime_paths import FormalAdmissionError
reached = []
def trap(*a, **k):
    reached.append('consumer')
    raise AssertionError('consumer entered before admission')
auth._store = trap
history.get_db = trap
favorites._data_file = trap
api_key.resolve_tier_from_request = trap
search_service.SearchService = trap
StaticFiles.get_response = trap
paths = [
    ('GET', '/api/history'), ('POST', '/api/history'), ('DELETE', '/api/history/1'),
    ('GET', '/api/auth/me'), ('POST', '/api/auth/request-link'),
    ('GET', '/api/favorites'), ('POST', '/api/favorites'),
    ('GET', '/api/me/export'), ('DELETE', '/api/me'),
    ('GET', '/api/privacy/export'), ('DELETE', '/api/privacy/delete'),
    ('GET', '/assets/data/papers-manifest.json'), ('GET', '/phase/samples/anything'),
    ('POST', '/phase/api/waitlist'), ('GET', '/api/health?deep=1'),
    ('OPTIONS', '/api/history'), ('HEAD', '/assets/data/papers-manifest.json'),
]
async def check():
    # ASGITransport intentionally sends no lifespan event, as lifespan=off does.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='https://example.invalid') as client:
        for method, path in paths:
            response = await client.request(method, path, content=b'{"email":"fixture@example.invalid"}',
                headers={'X-API-Key': 'synthetic-key', 'X-Device-ID': 'synthetic-device',
                         'Origin': 'https://example.invalid'})
            assert response.status_code == 503, (method, path, response.status_code)
            assert response.headers['cache-control'] == 'no-store'
        # Neither an environment switch nor counterfeit ready state unlocks it.
        os.environ.update(STRUCTURAL_ENV='dev', STRUCTURAL_RUNTIME_ADMITTED='true')
        main.app.state.runtime_admitted = True
        main.app_state.update(search=object(), artifact={'artifact_id': 'fake'}, runtime_admitted=True)
        for method, path in paths:
            response = await client.request(method, path)
            assert response.status_code == 503
asyncio.run(check())
assert not reached and not attempts, (reached, attempts)
print('R2_RESULT:' + json.dumps({'requests': len(paths) * 2, 'consumers': reached, 'attempts': attempts}))
''')
    assert value == {'requests': 34, 'consumers': [], 'attempts': []}


def test_real_formal_lifespan_and_direct_health_are_closed_before_initializers(tmp_path):
    value = isolated(tmp_path, r'''
import main
import research
import services.search_service as search_service
import services.runtime_paths as paths
from services import formal_admission
from services.runtime_paths import FormalAdmissionError, RuntimePathError, require_formal_admission
import threading
# Real configuration validation precedes admission. No private runtime has
# been provisioned: these task-owned canonical roots must remain absent.
state = pathlib.Path(TEST_ENV['HOME']).parent / 'unprovisioned-formal-state'
cache = state.parent / 'unprovisioned-formal-cache'
assert not state.exists() and not cache.exists()
paths.STATE_ROOT, paths.CACHE_ROOT, paths.LOG_ROOT = state, cache, state / 'logs'
os.environ.update(AUTH_SITE_ROLE='beta', AUTH_LINK_BASE_URL='https://beta.structural.bytedance.city',
    JWT_SECRET='A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3',
    STRUCTURAL_PRIVACY_HMAC_KEY='0123456789abcdef' * 4,
    SMTP_HOST='fixture.invalid', SMTP_PORT='587', SMTP_FROM_EMAIL='sender@example.invalid',
    ADMIN_NOTIFICATION_EMAIL='admin@example.invalid', AUTH_DATA_DIR=str(state),
    AUTH_TRUSTED_PROXY_IPS='127.0.0.1')
config_checks = []
original_config = main.auth_api._validate_production_config
def checked_config():
    config_checks.append('config')
    return original_config()
main.auth_api._validate_production_config = checked_config
reached = []
def trap(*a, **k):
    reached.append('initializer')
    raise AssertionError('initializer entered')
# Bind the actual factories consumed by formal_admission.initialize, rather
# than an unused AuthStore alias or a replacement admission predicate.
main.auth_api._store = trap
research.ResearchStore = trap
research.ResearchService = trap
search_service.SearchService = trap
births = []
original_open, original_close = os.open, os.close
def watched_open(*args, **kwargs):
    fd = original_open(*args, **kwargs)
    info = os.fstat(fd)
    births.append({'fd': fd, 'identity': (info.st_dev, info.st_ino, info.st_mode),
                   'creator': threading.get_ident(), 'closed': False, 'same_creator': False})
    return fd
def watched_close(fd, *args, **kwargs):
    info = os.fstat(fd)
    record = next((item for item in reversed(births) if item['fd'] == fd and not item['closed']), None)
    same = (record is not None and record['identity'] == (info.st_dev, info.st_ino, info.st_mode)
            and record['creator'] == threading.get_ident())
    result = original_close(fd, *args, **kwargs)
    if record is not None:
        record['closed'], record['same_creator'] = True, same
    assert same, 'read-only descriptor did not close through its actual creator'
    return result
def unadmitted():
    assert id(main.app) not in formal_admission._STATE
    try:
        require_formal_admission(main.app)
    except FormalAdmissionError as error:
        assert type(error) is FormalAdmissionError
    else:
        raise AssertionError('unadmitted consumer was accepted')
async def check():
    unadmitted()
    for deep in (0, 1):
        assert (await main.health(deep=deep)).status_code == 503
    os.open, os.close = watched_open, watched_close
    try:
        try:
            async with main.lifespan(main.app):
                raise AssertionError('formal startup admitted')
        except RuntimePathError as error:
            assert type(error) is RuntimePathError
    finally:
        os.open, os.close = original_open, original_close
    unadmitted()
    for deep in (0, 1):
        main.app_state.update(search=object(), artifact={'artifact_id': 'fake'})
        assert (await main.health(deep=deep)).status_code == 503
asyncio.run(check())
assert config_checks == ['config', 'config']
assert not state.exists() and not cache.exists()
assert all(item['closed'] and item['same_creator'] for item in births)
assert not reached and not attempts, (reached, attempts)
print('R2_RESULT:' + json.dumps({'initializers': reached, 'attempts': attempts,
    'config_checks': len(config_checks), 'readonly_fd_born': len(births),
    'readonly_fd_closed': sum(item['closed'] for item in births),
    'readonly_same_creator': all(item['same_creator'] for item in births) if births else None}))
''')
    assert value.pop('config_checks') == 2
    born, closed = value.pop('readonly_fd_born'), value.pop('readonly_fd_closed')
    same_creator = value.pop('readonly_same_creator')
    assert type(born) is int and born >= 0 and closed == born
    assert same_creator is (True if born else None)
    assert value == {'initializers': [], 'attempts': []}


def test_raw_formal_http_and_websocket_never_receive_or_call_inner_app(tmp_path):
    value = isolated(tmp_path, r'''
from services.runtime_paths import FormalAdmissionMiddleware
messages = []
async def forbidden(*a, **k): raise AssertionError('inner app or receive called')
async def send(message): messages.append(message)
async def check():
    gate = FormalAdmissionMiddleware(forbidden, formal=True)
    await gate({'type': 'http', 'path': '/api/history'}, forbidden, send)
    assert [m['type'] for m in messages] == ['http.response.start', 'http.response.body']
    assert messages[0]['status'] == 503
    messages.clear()
    await gate({'type': 'websocket', 'path': '/api/auth/me'}, forbidden, send)
    assert messages == [{'type': 'websocket.close', 'code': 1013}]
asyncio.run(check())
assert not attempts
print('R2_RESULT:' + json.dumps({'closed': True, 'attempts': attempts}))
''')
    assert value == {'closed': True, 'attempts': []}


def test_development_asgi_still_enters_history_handler_without_lifespan(tmp_path):
    value = isolated(tmp_path, r'''
import main
import api.history as history
# Explicit dev configuration keeps the old log behavior; guards prevent these
# test-observed attempts from actually creating any directory/file.
assert attempts and all(x in ('file-write', 'fs-mutation') for x in attempts)
attempts.clear()
class FakeDB:
    def list_recent(self, device_id, limit):
        assert device_id == 'synthetic-device'
        return []
history._db = FakeDB()
async def check():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='https://example.invalid') as client:
        response = await client.get('/api/history', headers={'X-Device-ID': 'synthetic-device'})
        assert response.status_code == 200, response.status_code
        assert response.json() == {'items': [], 'count': 0}
asyncio.run(check())
assert not attempts
print('R2_RESULT:' + json.dumps({'dev_route': 'reachable', 'attempts': attempts}))
''', prod=False)
    assert value == {'dev_route': 'reachable', 'attempts': []}


def test_formal_logging_never_even_resolves_a_sink_and_closes_only_owned_handlers(monkeypatch):
    import logging
    import logging_config as config
    monkeypatch.setenv('STRUCTURAL_ENV', 'prod')
    monkeypatch.setenv('STRUCTURAL_LOG_FILE', '/unapproved/public/log.jsonl')
    attempts = []
    def forbidden(*a, **k):
        attempts.append('sink')
        raise AssertionError('file sink was probed')
    monkeypatch.setattr(config, '_resolve_log_path', forbidden)
    monkeypatch.setattr(config, '_ensure_log_dir', forbidden)
    monkeypatch.setattr(logging.handlers, 'RotatingFileHandler', forbidden)
    root = logging.getLogger()
    owned, unrelated = logging.StreamHandler(), logging.StreamHandler()
    owned._structlog_owned = True
    closed = []
    monkeypatch.setattr(owned, 'close', lambda: closed.append('owned'))
    monkeypatch.setattr(unrelated, 'close', lambda: closed.append('unrelated'))
    root.addHandler(owned)
    root.addHandler(unrelated)
    try:
        assert config.configure_logging(log_file=Path('/unapproved/path')) is None
        assert closed == ['owned']
        assert unrelated in root.handlers and owned not in root.handlers
        with pytest.raises(RuntimeError):config.current_log_file()
        assert not attempts
    finally:
        root.removeHandler(unrelated)
