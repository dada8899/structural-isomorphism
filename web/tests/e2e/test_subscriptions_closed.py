"""Actual release pages and middleware, local-only and without model startup."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[3]
RELEASE_PYTHON = os.getenv('STRUCTURAL_RELEASE_TEST_PYTHON', str(ROOT / '.venv/bin/python'))
COLLECTORS = {'/api/newsletter/subscribe', '/api/newsletter/count', '/api/waitlist',
    '/api/waitlist/count', '/phase/api/waitlist'}
PAGES = [('/', '#research-next'), ('/start-here', '#newsletter-start-here'),
    ('/learn', '#newsletter-learn'), ('/discoveries', '#newsletter-discoveries')]

_SERVER = r'''
import sys,os,json,socket,sqlite3
from pathlib import Path
root,state,port=Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3])
sys.path[:0]=[str(root/'web/backend'),str(root)]
blocked=[]
def fail(kind):blocked.append(kind);raise RuntimeError('local subscription test blocked '+kind)
def owned(path):
 p=Path(os.fsdecode(path))
 if not p.is_absolute():p=Path.cwd()/p
 return p==state or p.is_relative_to(state)
def audit(event,args):
 if event=='import' and args[0].split('.')[0] in ('torch','transformers','sentence_transformers','huggingface_hub'):fail('model')
 if event=='open':
  value,mode,flags=args
  if isinstance(value,int):return
  text=os.fsdecode(value).lower()
  if text.endswith(('.env','.env.runtime','.bin','.safetensors','.pt','.ckpt')) or '/.ssh/' in text or '/huggingface/' in text:fail('private-or-model-file')
  writing=(isinstance(mode,str) and any(v in mode for v in 'wax+')) or (isinstance(flags,int) and flags&(os.O_CREAT|os.O_WRONLY|os.O_RDWR|os.O_APPEND|os.O_TRUNC))
  if writing and not owned(value):fail('outside-write')
 if event=='sqlite3.connect':
  from urllib.parse import urlsplit,unquote
  value=str(args[0]);target=unquote(urlsplit(value).path) if value.startswith('file:') else value
  if target!=':memory:' and not owned(target):fail('outside-sqlite')
 if event in ('os.mkdir','os.remove','os.rmdir','os.chmod'):
  if not owned(args[0]):fail('outside-mutation')
 if event in ('socket.connect','socket.bind') and args[0].family in (socket.AF_INET,socket.AF_INET6):
  if args[1][0] not in ('127.0.0.1','::1'):fail('external-network')
 if event=='socket.getaddrinfo' and args[0] not in ('127.0.0.1','localhost','::1'):fail('external-dns')
sys.addaudithook(audit)
import main,uvicorn
try:uvicorn.run(main.app,host='127.0.0.1',port=port,lifespan='off',access_log=False,log_config=None)
finally:(state/'server-audit.json').write_text(json.dumps({'blocked':blocked,'lifespan':'off','model_startup':False}))
'''


@pytest.fixture(scope='module')
def subscription_site(tmp_path_factory):
    state = tmp_path_factory.mktemp('subscription-closed-server').resolve()
    with socket.socket() as held:
        held.bind(('127.0.0.1', 0));port = held.getsockname()[1]
    env = {'PATH': '/usr/bin:/bin:/opt/homebrew/bin', 'HOME': str(state), 'TMPDIR': str(state),
        'PYTHONDONTWRITEBYTECODE': '1', 'STRUCTURAL_ENV': 'dev', 'AUTH_ENABLED': 'false',
        'STRUCTURAL_LOG_FILE': str(state / 'app.jsonl'), 'STRUCTURAL_HISTORY_DB': str(state / 'history.db')}
    base = 'http://127.0.0.1:' + str(port)
    with (state / 'server-output.txt').open('w') as output:
        process = subprocess.Popen([RELEASE_PYTHON, '-B', '-c', _SERVER, str(ROOT), str(state), str(port)],
            cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while True:
                assert process.poll() is None, (state / 'server-output.txt').read_text()[-3000:]
                try:
                    with urllib.request.urlopen(base + '/start-here', timeout=1) as response:
                        if response.status == 200:break
                except Exception:
                    pass
                assert time.monotonic() < deadline, 'local release server did not start'
                time.sleep(0.05)
            yield base, state
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    assert process.returncode == 0, (state / 'server-output.txt').read_text()[-3000:]
    report = json.loads((state / 'server-audit.json').read_text())
    assert report['blocked'] == []
    print('SUBSCRIPTIONS_SERVER_AUDIT:' + json.dumps({**report, 'returncode': process.returncode}))


@pytest.fixture(scope='module')
def subscription_browser(playwright_instance):
    browser = playwright_instance.chromium.launch(headless=True,
        args=['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost'])
    try:yield browser
    finally:browser.close()


@pytest.mark.parametrize('javascript', [True, False])
@pytest.mark.parametrize('width', [1280, 430])
@pytest.mark.parametrize('path,selector', PAGES)
def test_real_pages_explain_closed_collection_without_inputs_or_subscription_requests(
        subscription_site, subscription_browser, javascript, width, path, selector):
    base, _ = subscription_site
    port = urlsplit(base).port
    context = subscription_browser.new_context(java_script_enabled=javascript,
        viewport={'width': width, 'height': 900}, service_workers='block')
    observed = [];external = []
    def local_only(route):
        request = route.request;url = urlsplit(request.url)
        observed.append(url.path)
        if url.hostname != '127.0.0.1' or url.port != port:
            external.append(url.hostname);route.abort();return
        route.continue_()
    context.route('**/*', local_only)
    context.add_init_script("window.__subscriptionEvents=[];window.plausible=function(name){if(/newsletter|waitlist/.test(name))window.__subscriptionEvents.push(name);};")
    page = context.new_page()
    try:
        response = page.goto(base + path, wait_until='domcontentloaded')
        assert response.status == 200
        notice = page.locator(selector)
        assert notice.is_visible()
        assert '新增订阅暂不可用' in notice.inner_text()
        assert notice.locator('input,form').count() == 0
        assert page.locator('#waitlist-form').count() == 0
        if javascript and path != '/':
            page.wait_for_function('(selector)=>document.querySelector(selector).dataset.newsletterMounted==="closed"', arg=selector)
        rect = notice.bounding_box()
        assert rect is not None and rect['x'] >= -1 and rect['x'] + rect['width'] <= width + 2
        page.wait_for_timeout(250)
        assert not set(observed) & COLLECTORS
        assert not any(value.endswith('/waitlist.js') for value in observed)
        if javascript:
            assert page.evaluate('window.__subscriptionEvents') == []
        screenshot_dir = os.getenv('STRUCTURAL_SUBSCRIPTIONS_SCREENSHOTS')
        if screenshot_dir and javascript and width == 430 and path in {'/', '/learn'}:
            destination = Path(screenshot_dir)
            destination.mkdir(parents=True, exist_ok=True)
            notice.scroll_into_view_if_needed()
            name = 'home' if path == '/' else 'learn'
            page.screenshot(path=str(destination / (name + '-closed-430.png')), full_page=False)
        if path == '/':
            assert page.locator('#ask-form').get_attribute('action') == '/research'
            assert page.locator('#ask-input').count() == 1
            entry = page.locator('#start-research')
            assert entry.get_attribute('href') == '/research'
            entry.focus();page.keyboard.press('Enter')
            page.wait_for_url(base + '/research')
            assert page.locator('#problem-form').count() == 1
            assert '从你的现象' in page.locator('h1').inner_text()
            # No model/search submission or success response is mocked. Auth
            # may keep the real problem form hidden in this local fixture.
        print(json.dumps({'page': path, 'javascript': javascript, 'width': width,
            'subscription_requests': 0, 'retained_waitlist_script_requests': 0,
            'external_requests_blocked': len(external), 'research_submission_tested': False}))
    finally:context.close()
