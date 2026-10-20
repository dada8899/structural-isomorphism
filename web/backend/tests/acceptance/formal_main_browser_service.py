"""Owned test HTTPS/SMTP for the actual Main, never a production control API.

Prepare historical data first, retain its synthetic signing environment, then
let Uvicorn run the canonical Main lifespan. No readiness, routes, sender,
feature predicates, credentials or funding installations are substituted.
"""
from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
from email import policy
from email.parser import BytesParser
from http.cookiejar import CookieJar
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[4]
for _source in (ROOT, ROOT / 'web/backend'):
    if str(_source) not in sys.path:
        sys.path.insert(0, str(_source))

from web.backend.tests.acceptance.plan_browser_service import (  # noqa: E402
    CanonicalBrowserBridge, _certificates, _OwnedHTTPSHandler,
)
from web.backend.tests.acceptance.source_history_fixture import prepared_source_history  # noqa: E402

ORIGIN = 'https://beta.structural.bytedance.city'
HOST = 'beta.structural.bytedance.city'
PREFIX = 'formal-main-browser-'
_FOREIGN_SECRETS = ('JWT_SECRET', 'STRUCTURAL_SSO_SECRET', 'STRUCTURAL_PRIVACY_HMAC_KEY',
                    'STRUCTURAL_SHARE_TOKEN_SECRET', 'SMTP_USERNAME', 'SMTP_PASSWORD',
                    'OPENROUTER_API_KEY', 'DEEPSEEK_API_KEY', 'SENTRY_DSN')
_FOREIGN_INPUTS = ('STRUCTURAL_HISTORY_DB', 'STRUCTURAL_FAVORITES_PATH', 'STRUCTURAL_DATA_DIR',
                   'STRUCTURAL_MODEL_PATH', 'STRUCTURAL_PRECOMPUTED_EMBEDDINGS',
                   'STRUCTURAL_ARTIFACT_MANIFEST', 'STRUCTURAL_KB_FILE')


class _MailHandler(socketserver.StreamRequestHandler):
    timeout = 3

    def handle(self):
        deadline = time.monotonic() + 5
        recipients = []

        def line():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('owned SMTP deadline')
            self.request.settimeout(min(3, remaining))
            data = self.rfile.readline(8193)
            if len(data) > 8192:
                raise ValueError('owned SMTP line limit')
            return data

        self.wfile.write(b'220 fixture.invalid owned SMTP\r\n')
        while True:
            command = line()
            if not command:
                return
            verb = command.split(None, 1)[0].upper()
            if verb in (b'EHLO', b'HELO'):
                self.wfile.write(b'250 fixture.invalid\r\n')
            elif verb == b'MAIL':
                self.wfile.write(b'250 ok\r\n')
            elif verb == b'RCPT':
                address = command.partition(b':')[2].strip().strip(b'<>')
                if re.fullmatch(rb'[A-Za-z0-9._+\-]+@example\.invalid', address):
                    recipients.append(address.decode('ascii'))
                    self.wfile.write(b'250 ok\r\n')
                else:
                    self.wfile.write(b'553 synthetic recipient required\r\n')
            elif verb == b'DATA' and recipients:
                self.wfile.write(b'354 send message\r\n')
                raw = bytearray()
                while True:
                    part = line()
                    if part == b'.\r\n':
                        break
                    if not part or len(raw) + len(part) > 65536:
                        raise ValueError('owned SMTP message limit')
                    raw.extend(part[1:] if part.startswith(b'..') else part)
                message = BytesParser(policy=policy.default).parsebytes(bytes(raw))
                if message['To'] not in recipients:
                    raise ValueError('owned SMTP recipient mismatch')
                with self.server.owner.lock:
                    self.server.owner.messages.append(message)
                recipients.clear()
                self.wfile.write(b'250 stored\r\n')
            elif verb == b'RSET':
                recipients.clear()
                self.wfile.write(b'250 ok\r\n')
            elif verb == b'NOOP':
                self.wfile.write(b'250 ok\r\n')
            elif verb == b'QUIT':
                self.wfile.write(b'221 done\r\n')
                return
            else:
                self.wfile.write(b'500 unsupported command\r\n')


class _MailServer(socketserver.ThreadingTCPServer):
    block_on_close = False
    request_queue_size = 8

    def process_request(self, request, address):
        worker = threading.Thread(target=self._owned_request, args=(request, address),
                                  name=PREFIX + 'smtp-connection')
        with self.owner.lock:
            self.owner.workers.append(worker)
            self.owner.sockets.add(request)
        try:
            worker.start()
        except BaseException:
            self.shutdown_request(request)
            with self.owner.lock:
                self.owner.sockets.discard(request)
            raise

    def _owned_request(self, request, address):
        try:
            self.process_request_thread(request, address)
        finally:
            with self.owner.lock:
                self.owner.sockets.discard(request)

    def handle_error(self, request, address):
        with self.owner.lock:
            self.owner.failures.append('SMTP_HANDLER_FAILED')


class _MailSink:
    def __init__(self):
        self.lock = threading.Lock()
        self.messages, self.workers, self.failures = [], [], []
        self.sockets = set()
        self.server = _MailServer(('127.0.0.1', 0), _MailHandler)
        self.server.owner = self
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': .05}, name=PREFIX + 'smtp')

    @property
    def port(self):
        return self.server.server_address[1]

    def start(self):
        self.thread.start()

    def take_latest_magic_token(self):
        with self.lock:
            for position in range(len(self.messages) - 1, -1, -1):
                message = self.messages[position]
                body = message.get_body(preferencelist=('plain',))
                if body is None:
                    continue
                words = body.get_content().strip().split()
                if not words:
                    continue
                parsed = urlsplit(words[-1])
                query = parse_qs(parsed.query)
                if (parsed.scheme == 'https' and parsed.netloc == HOST and parsed.path == '/auth/verify'
                        and not parsed.fragment and set(query) == {'token'} and len(query['token']) == 1
                        and 0 < len(query['token'][0]) <= 8192):
                    self.messages.pop(position)
                    return query['token'][0]
        raise RuntimeError('no pending canonical synthetic login mail')

    def close(self):
        errors = []
        if self.thread.is_alive():
            try:
                self.server.shutdown()
            except BaseException as error:
                errors.append(type(error).__name__)
        with self.lock:
            sockets, workers = list(self.sockets), list(self.workers)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        try:
            self.server.server_close()
        except BaseException as error:
            errors.append(type(error).__name__)
        deadline = time.monotonic() + 5
        for worker in (self.thread, *workers):
            if worker.ident is not None:
                try:
                    worker.join(max(0, deadline - time.monotonic()))
                except BaseException as error:
                    errors.append(type(error).__name__)
            if worker.is_alive():
                errors.append('SMTP_THREAD_UNREAPED')
        with self.lock:
            self.messages.clear()
            errors.extend(self.failures)
        if errors:
            raise RuntimeError('owned SMTP cleanup uncertain: ' + ','.join(errors))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise PermissionError('owned Main client does not follow redirects')


class _HttpsClient:
    """Actual verified TLS and an initially empty, server-populated CookieJar."""
    def __init__(self, port, certificate):
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            _OwnedHTTPSHandler(port, certificate), urllib.request.HTTPCookieProcessor(self.cookies), _NoRedirect())

    def request(self, method, path, data=None, *, key=None):
        parsed = urlsplit(path)
        if (method not in ('GET', 'HEAD', 'POST') or not path.startswith('/api/')
                or len(path) > 8192 or parsed.scheme or parsed.netloc or parsed.fragment):
            raise ValueError('fixed canonical Main API required')
        headers = {'Origin': ORIGIN}
        raw = None if data is None else json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        if raw is not None:
            if len(raw) > 65536:
                raise ValueError('owned Main request limit')
            headers['Content-Type'] = 'application/json'
        if key is not None:
            headers['Idempotency-Key'] = key
        request = urllib.request.Request(ORIGIN + path, data=raw, method=method, headers=headers)
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(524289)
            if len(body) > 524288:
                raise ValueError('owned Main response limit')
            return response.status, json.loads(body) if body else None


class FormalMainBrowserService(AbstractContextManager):
    """One owned real Main lifetime; a retained failure is never a fresh retry."""
    def __init__(self, owned_root, *, history_source=None):
        self.root = Path(owned_root).absolute()
        self.history_source = ROOT if history_source is None else Path(history_source).resolve()
        self.origin, self.stop = ORIGIN, threading.Event()
        self.seed = self.app = self.main = self.server = self.server_thread = None
        self.app_socket = self.certificate = self.client = self._smtp = self._history = None
        self._prior, self._bridges, self._server_errors = {}, [], []
        self._entered = self._closed = False

    def __repr__(self):
        return '<owned actual Main browser service>'

    def __enter__(self):
        try:
            self._start()
            return self
        except BaseException as primary:
            try:
                self._close(primary)
            except BaseException as cleanup:
                primary.add_note('owned Main startup cleanup uncertain: ' + type(cleanup).__name__)
            raise

    def _start(self):
        if self._entered or self._closed:
            raise RuntimeError('owned Main service cannot be re-entered')
        self._entered = True
        if (self.root != self.root.resolve() or self.root.exists() or self.root.is_relative_to(ROOT)
                or any(parent.is_symlink() for parent in self.root.parents)
                or not self.root.parent.is_dir()):
            raise ValueError('fresh canonical owned root outside source required')
        if any(name in os.environ for name in (*_FOREIGN_SECRETS, *_FOREIGN_INPUTS)):
            raise RuntimeError('owned Main requires an unconfigured synthetic process')
        for name in ('main', 'web.backend.main'):
            module = sys.modules.get(name)
            if module is not None:
                if (Path(module.__file__).resolve() != ROOT / 'web/backend/main.py'
                        or not module._IS_PROD or not module._LAUNCH_FORMAL):
                    raise RuntimeError('another Main profile is already imported')
                if vars(sqlite3).get('_structural_main_admission_v1', {}).get(id(module.app)) is not None:
                    raise RuntimeError('another Main lifetime is already owned')
        self._history = prepared_source_history(self.history_source, self.root, target_revision=False)
        self.seed = self._history.__enter__()
        self._smtp = _MailSink()
        self._smtp.start()
        settings = {'STRUCTURAL_SHARE_TOKEN_SECRET': secrets.token_urlsafe(48),
            'SMTP_HOST': '127.0.0.1', 'SMTP_PORT': str(self._smtp.port),
            'SMTP_FROM_EMAIL': 'sender@example.invalid', 'ADMIN_NOTIFICATION_EMAIL': 'admin@example.invalid',
            'SMTP_STARTTLS': 'false', 'SMTP_USE_SSL': 'false', 'SMTP_TIMEOUT_SECONDS': '2'}
        self._prior = {name: os.environ.get(name) for name in settings}
        os.environ.update(settings)
        self.main = importlib.import_module('main')
        if Path(self.main.__file__).resolve() != ROOT / 'web/backend/main.py' or not self.main._LAUNCH_FORMAL:
            raise RuntimeError('canonical formal Main source required')
        self.app = self.main.app
        key, self.certificate = _certificates(self.root)
        self.app_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.app_socket.bind(('127.0.0.1', 0))
        self.port = self.app_socket.getsockname()[1]
        self.app_socket.listen(16)
        import uvicorn
        config = uvicorn.Config(self.app, host='127.0.0.1', port=self.port, lifespan='on',
            ssl_keyfile=str(key), ssl_certfile=str(self.certificate), loop='asyncio', ws='none',
            log_config=None, log_level='critical', access_log=False, timeout_graceful_shutdown=5)
        self.server = uvicorn.Server(config)
        def serve():
            try:
                self.server.run(sockets=[self.app_socket])
            except BaseException as error:
                self._server_errors.append(type(error).__name__)
        self.server_thread = threading.Thread(target=serve, name=PREFIX + 'app')
        self.server_thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if not self.server_thread.is_alive() or time.monotonic() >= deadline:
                raise RuntimeError('actual Main HTTPS startup unavailable')
            time.sleep(.02)
        self.client = _HttpsClient(self.port, self.certificate)
        status, body = self.client.request('GET', '/api/health')
        if (status != 200 or body['status'] != 'limited' or body['checks']['base'] != 'ready'
                or body['checks']['source_history'] != 'CURRENT_ACL_AND_STORED_SOURCE_REQUIRED'
                or body['checks']['source_execute'] not in ('ready', 'unavailable')
                or body['checks']['native_planner'] != 'FUNDING_CLOSED'):
            raise RuntimeError('actual Main base and closed capabilities differ')
        from services import formal_admission
        formal_admission.require(self.app, 'research_basic')
        formal_admission.require(self.app, 'source_history')

    def source_status(self):
        """Observation only: no flag, receipt or authority is accepted."""
        if self.stop.is_set() or self.app is None:
            return 'unavailable'
        from services import formal_admission
        return formal_admission.safe_status(self.app)['source_execute']

    def retire_source(self):
        """Python-only actual sub-lifetime retirement; no caller authority input.

        A CLOSED Core result completes only this Source object. Main remains
        live for history; its other resources have a later teardown lifetime.
        Uncertainty retains the original fixed deadline/handles, never extends it.
        """
        if self.stop.is_set() or self.app is None:
            raise RuntimeError('owned Main service is retired')
        from services import formal_admission
        binding = formal_admission._STATE.get(id(self.app))
        if binding is None:
            raise RuntimeError('actual Main binding unavailable')
        binding.check()
        deadline = binding.source_deadline
        if deadline is None:
            deadline = time.monotonic() + 20
        formal_admission.close_source(binding, deadline_monotonic=deadline)
        if not formal_admission.source_closed(binding):
            raise RuntimeError('actual Source sub-lifetime did not close')
        return self.source_status()

    def browser_bridge(self):
        if self.stop.is_set() or self.server_thread is None or not self.server_thread.is_alive():
            raise RuntimeError('owned Main service is retired')
        bridge = CanonicalBrowserBridge(self)
        self._bridges.append(bridge)
        return bridge

    def take_latest_magic_token(self):
        if self.stop.is_set() or self._smtp is None:
            raise RuntimeError('owned Main mail sink is retired')
        return self._smtp.take_latest_magic_token()

    def _close(self, primary=None):
        if self._closed:
            return
        self.stop.set()
        errors = []
        for bridge in self._bridges:
            try:
                bridge.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread is not None and self.server_thread.ident is not None:
            try:
                # Candidate HTTP5 + application20 + observer margin5. This local
                # test wait is not evidence of a production unit's hard deadline.
                self.server_thread.join(30)
            except BaseException as error:
                errors.append(type(error).__name__)
            if self.server_thread.is_alive():
                errors.append('MAIN_THREAD_UNREAPED')
        if self.app_socket is not None:
            try:
                self.app_socket.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        if self._smtp is not None:
            try:
                self._smtp.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        errors.extend(self._server_errors)
        lifespan = getattr(self.server, 'lifespan', None)
        if lifespan is not None and (lifespan.error_occured or lifespan.startup_failed or lifespan.shutdown_failed):
            errors.append('MAIN_LIFESPAN_FAILED')
        if self.app is not None:
            from services import formal_admission
            if formal_admission._STATE.get(id(self.app)) is not None:
                errors.append('MAIN_BINDING_NOT_RETIRED')
        # A live server/handler must retain its configuration and helper scope.
        # The outer test process owns the final kill if normal reaping fails.
        live = self.server_thread is not None and self.server_thread.is_alive()
        if self._smtp is not None:
            live = live or self._smtp.thread.is_alive() or any(t.is_alive() for t in self._smtp.workers)
        if live:
            raise RuntimeError('owned Main resources remain live; root and scope retained')
        for name, value in self._prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._prior.clear()
        failure = primary if primary is not None else RuntimeError('owned Main cleanup uncertain') if errors else None
        if self._history is not None:
            try:
                self._history.__exit__(type(failure) if failure is not None else None, failure,
                                       failure.__traceback__ if failure is not None else None)
            except BaseException as error:
                errors.append(type(error).__name__)
        self._closed = not errors
        if errors:
            raise RuntimeError('owned Main cleanup uncertain: ' + ','.join(errors))

    def close(self):
        self._close()

    def __exit__(self, kind, error, traceback):
        try:
            self._close(error)
        except BaseException as cleanup:
            if error is None:
                raise
            error.add_note('owned Main cleanup uncertain: ' + type(cleanup).__name__)
        return False


def self_test(owned_root):
    owned_root = Path(owned_root).absolute()
    with FormalMainBrowserService(owned_root) as service:
        client = service.client
        status, _ = client.request('POST', '/api/auth/request-link', {'email': service.seed.email})
        assert status == 200
        token = service.take_latest_magic_token()
        try:
            status, _ = client.request('POST', '/api/auth/verify', {'token': token})
        finally:
            token = None
        assert status == 200
        cookies = [cookie for cookie in client.cookies if cookie.name == 'phase_session']
        assert len(cookies) == 1 and cookies[0].secure and 'HttpOnly' in cookies[0]._rest
        query = urlencode({'task_id': service.seed.source_task_id, 'kind': 'excerpts'})
        status, result = client.request('GET', '/api/research/' + service.seed.research_id + '/records?' + query)
        assert status == 200 and result['data']['items']
        expected = {ref['excerpt_id']: ref for ref in service.seed.excerpt_refs}
        for item in result['data']['items']:
            ref = expected[item['id']]
            assert (item['source_revision'], item['text_digest'], item['start'], item['end']) == (
                ref['source_revision'], ref['content_digest'], ref['start'], ref['end'])
        # A revision containing a Source run cannot be submitted as an owned
        # observation. Save a new explicit observation through actual Main.
        problem = {'entry': 'phenomenon', 'original_input': '我观察到任务集中到达时，排队等待随积压增加。',
            'objective': '记录等待', 'summary': '合成观察自述，仅供实际Main入口测试。',
            'variables': [], 'constraints': [], 'unknowns': [], 'confirmed': True}
        revision = {'schema_version': 'structure-research-v1', 'contract_revision': 'b1-candidate-01',
                    'data': {'expected_revision': 1, 'problem': problem}}
        status, saved = client.request('POST', '/api/research/' + service.seed.research_id + '/revisions',
                                        revision, key='actual-main-https-new-observation')
        assert status == 200 and saved['data']['current_problem']['revision'] == 2
        data = {'input_revision': 2, 'expected_research_version': saved['data']['research_version'],
                'observation_source': 'own_observation', 'declaration_status': 'self_declared'}
        envelope = {'schema_version': 'structure-research-v1', 'contract_revision': 'funded-plan-v2', 'data': data}
        status, closed = client.request('POST', '/api/research/' + service.seed.research_id + '/plan-previews',
                                        envelope, key='actual-main-https-closed-preview')
        assert status == 200 and not closed['data']['can_confirm'] and closed['data']['funding_reason'] == 'FUNDING_CLOSED'
        with service.browser_bridge() as bridge:
            response = bridge.forward('GET', ORIGIN + '/assets/research.js', [])
            assert response.status == 200 and response.body == (ROOT / 'web/frontend/assets/research.js').read_bytes()
        actual_app = service.app
        source_status = service.source_status()
    from services import formal_admission
    try:
        formal_admission.require(actual_app, 'research_basic')
    except RuntimeError:
        pass
    else:
        raise AssertionError('shutdown Main binding remained usable')
    assert not owned_root.exists() and not service.server_thread.is_alive()
    return {'scope': 'actual_main_local_tls_only', 'actual_main': True, 'schema': 14,
            'history_origin': 'offline_probe', 'actual_https_history': True, 'server_issued_secure_httponly_cookie': True,
            'source_execute': source_status, 'funding': 'closed', 'real_model_executed': False,
            'public_tls_verified': False, 'browser_behavior_verified': False, 'shutdown_binding': 'rejected', 'cleanup': 'closed'}


def failure_cleanup_test(owned_root):
    class BodyFailure(Exception):
        pass
    service = FormalMainBrowserService(owned_root)
    try:
        with service:
            raise BodyFailure('owned test-body failure')
    except BodyFailure:
        pass
    else:
        raise AssertionError('test-body failure was swallowed')
    assert Path(owned_root).exists() and not service.server_thread.is_alive()
    assert service._smtp is not None and not service._smtp.thread.is_alive()
    assert not any(thread.is_alive() for thread in service._smtp.workers)
    assert all(name not in os.environ for name in _FOREIGN_SECRETS[:4])
    return {'scope': 'actual_main_body_failure_cleanup', 'threads': 'closed', 'root': 'retained', 'signing_environment': 'removed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', type=Path)
    parser.add_argument('--failure-cleanup-test', type=Path)
    args = parser.parse_args()
    if bool(args.self_test) == bool(args.failure_cleanup_test):
        parser.error('choose exactly one owned test root')
    result = self_test(args.self_test) if args.self_test else failure_cleanup_test(args.failure_cleanup_test)
    print(json.dumps(result, sort_keys=True))
