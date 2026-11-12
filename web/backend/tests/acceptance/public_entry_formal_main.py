"""Public-entry consumer adapter for the accepted actual Main test controller.

The browser gets only real canonical responses over the existing verified TLS
bridge. Credentials come from actual loopback SMTP/registration/verify, never a
dev token, injected cookie, substitute ASGI app, or Source execution fixture.
Controller preparation retains its reviewed, private offline history scope;
public-entry consumers never preview/approve/start Source or a model task.
"""
from contextlib import AbstractContextManager
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

import pytest

from .formal_main_browser_service import FormalMainBrowserService, ORIGIN, HOST

_ACTIVE = {}


def synthetic_email(value):
    """One-to-one reserved-domain fixture mapping; never accept real mail."""
    if not isinstance(value, str) or value.count('@') != 1:
        raise ValueError('synthetic fixture address required')
    user, domain = value.rsplit('@', 1)
    if not user or domain not in ('example.test', 'example.invalid'):
        raise ValueError('reserved synthetic recipient required')
    return user + '@example.invalid'


class _PublicEntry(AbstractContextManager):
    def __init__(self, root):
        self.service = FormalMainBrowserService(root)
        self.bridge = None
        self.contexts = []
        self.source_posts = []

    def __enter__(self):
        self.service.__enter__()
        try:
            self.bridge = self.service.browser_bridge()
            if ORIGIN in _ACTIVE:
                raise RuntimeError('one public-entry controller per process required')
            _ACTIVE[ORIGIN] = self
            return self
        except BaseException as primary:
            self.service.__exit__(type(primary), primary, primary.__traceback__)
            raise

    def route_context(self, context):
        if any(item['context'] is context for item in self.contexts):
            return
        record = {'context': context, 'closed': False}
        context.on('close', lambda *_: record.__setitem__('closed', True))
        def forward(route, request):
            parsed = urlsplit(request.url)
            if request.method == 'POST' and parsed.path.endswith(('/source-preview', '/source-approvals', '/source-tasks')):
                self.source_posts.append(parsed.path)
                route.abort('blockedbyclient')
                raise AssertionError('public entry must not invoke Source execution')
            try:
                result = self.bridge.forward(request.method, request.url, request.all_headers(), request.post_data_buffer)
                grouped = {}
                for name, value in result.headers:
                    grouped.setdefault(name.lower(), []).append(value)
                headers = {name: ('\n' if name == 'set-cookie' else ', ').join(values)
                           for name, values in grouped.items()}
                route.fulfill(status=result.status, headers=headers, body=result.body)
            except (PermissionError, ValueError, OSError, TimeoutError):
                route.abort('blockedbyclient')
        record['handler'] = forward
        self.contexts.append(record)
        context.route('**/*', forward)

    def __exit__(self, kind, primary, traceback):
        errors = []
        for item in reversed(self.contexts):
            if item['closed']:
                continue
            offline = False
            try:
                item['context'].set_offline(True)
                offline = True
            except BaseException as error:
                if not item['closed']: errors.append(error)
            if offline and not item['closed']:
                try: item['context'].unroute('**/*', item['handler'])
                except BaseException as error:
                    if not item['closed']: errors.append(error)
        _ACTIVE.pop(ORIGIN, None)
        if self.source_posts:
            errors.append(AssertionError('unexpected Source POST in public-entry consumer'))
        failure = primary if primary is not None else errors[0] if errors else None
        try:
            self.service.__exit__(type(failure) if failure is not None else None, failure,
                                  failure.__traceback__ if failure is not None else None)
        except BaseException as error:
            errors.append(error)
        if errors:
            if primary is not None:
                for error in errors: primary.add_note('public-entry cleanup uncertain: ' + type(error).__name__)
            else:
                raise RuntimeError('public-entry cleanup uncertain') from errors[0]
        return False


@pytest.fixture
def server(tmp_path, page):
    with _PublicEntry(tmp_path / 'public-entry-main') as adapter:
        adapter.route_context(page.context)
        yield {'base': ORIGIN, 'path': adapter.service.seed.state_root / 'auth.sqlite3',
               'root': adapter.service.root, '_public_entry': adapter}


def _adapter(base):
    if base != ORIGIN or base not in _ACTIVE:
        raise RuntimeError('owned canonical public-entry fixture required')
    return _ACTIVE[base]


def _page(context, base):
    adapter = _adapter(base)
    adapter.route_context(context)
    pages = [page for page in context.pages if not page.is_closed()]
    page = pages[0] if pages else context.new_page()
    if not page.url.startswith(ORIGIN + '/'):
        page.goto(ORIGIN + '/auth/login')
    return page


def magic_link(server):
    """Consume the real SMTP message's original URL/next value in memory."""
    adapter = server['_public_entry']
    if _adapter(server['base']) is not adapter:
        raise RuntimeError('owned Main mailbox required')
    sink = adapter.service._smtp
    with sink.lock:
        for index in range(len(sink.messages) - 1, -1, -1):
            mail = sink.messages[index]
            part = mail.get_body(preferencelist=('plain',))
            if part is None: continue
            words = part.get_content().strip().split()
            if not words: continue
            url = words[-1]
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            if (parsed.scheme == 'https' and parsed.netloc == HOST and parsed.path == '/auth/verify'
                    and not parsed.fragment and len(query.get('token', [])) == 1):
                sink.messages.pop(index)
                return url
    raise RuntimeError('actual public-entry SMTP link unavailable')


def _post(context, base, path, body, *, key=None):
    page = _page(context, base)
    return page.evaluate('''async ({path,body,key})=>{
      const response=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},body:JSON.stringify(body)});
      return {status:response.status,body:await response.json()};
    }''', {'path': path, 'body': body, 'key': key})


def login(context, base, email='browser-a@example.test'):
    email = synthetic_email(email)
    response = _post(context, base, '/api/auth/request-link', {'email': email})
    assert response['status'] == 200
    adapter = _adapter(base)
    link = magic_link({'base': base, '_public_entry': adapter})
    token = parse_qs(urlsplit(link).query)['token'][0]
    try:
        verified = _post(context, base, '/api/auth/verify', {'token': token})
    finally:
        token = link = None
    assert verified['status'] == 200


def _entry_create(context, base, number):
    problem = {'entry': 'phenomenon', 'original_input': f'真实保存流程使用的合成现象 {number}',
        'objective': '验证保存和恢复，不构成真实研究', 'summary': f'列表研究 {number} 的合成问题摘要',
        'variables': [], 'constraints': [], 'unknowns': [], 'confirmed': True}
    result = _post(context, base, '/api/research', {'schema_version': 'structure-research-v1',
        'contract_revision': 'b1-candidate-01', 'data': {'problem': problem}}, key=str(uuid4()))
    assert result['status'] == 200
    return result['body']['data']
