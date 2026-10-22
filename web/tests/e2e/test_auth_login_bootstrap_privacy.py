"""Actual Main/browser bootstrap privacy; no replacement Auth or browser state."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, quote, unquote, urlsplit

import pytest
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = 'https://beta.structural.bytedance.city'
EMAIL = 'bootstrap-owner@example.invalid'
pytestmark = pytest.mark.e2e

# Observe the actual listener registration after calling the original native
# method. This is a schedule probe, never a replacement listener or readiness.
LISTENER_PROBE = """(() => {const original=EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener=function(type){
    const result=Reflect.apply(original,this,arguments);
    if(this instanceof HTMLFormElement && this.id==='auth-login-form' && type==='submit')
      window.__observedLoginListener=true;
    return result;
  };
})();"""


@asynccontextmanager
async def actual_browser(tmp_path, *, javascript=True):
    from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService
    service = None
    browser = context = None
    facts = {'scope': 'actual Main, verified owned TLS bridge and synthetic loopback SMTP', 'requests': []}
    releases = []
    try:
        with FormalMainBrowserService(tmp_path / 'actual-main') as service, service.browser_bridge() as bridge:
            facts['ports'] = [service.port, service._smtp.port]
            async with async_playwright() as runtime:
                browser = await runtime.chromium.launch()
                context = await browser.new_context(java_script_enabled=javascript)
                context.set_default_timeout(8000)
                try:
                    async with bridge.routed(context):
                        await context.add_init_script(LISTENER_PROBE)
                        page = await context.new_page()
                        def observe(request):
                            path = urlsplit(request.url).path
                            allowed = ('/auth/login', '/auth/verify', '/api/auth/request-link', '/api/auth/verify', '/api/auth/me', '/research', '/reports')
                            facts['requests'].append({'method': request.method, 'path': path if path in allowed else 'OTHER',
                                'email_in_url': EMAIL in unquote(request.url)})
                        page.on('request', observe)
                        try:
                            yield page, service, context, facts, releases
                        finally:
                            for release in releases: release.set()
                finally:
                    for release in releases: release.set()
                    await context.close()
                    await browser.close()
    finally:
        facts.update(browser_disconnected=browser is None or not browser.is_connected(),
            main_thread_alive=bool(service and service.server_thread and service.server_thread.is_alive()),
            smtp_thread_alive=bool(service and service._smtp and service._smtp.thread.is_alive()),
            smtp_workers_alive=bool(service and service._smtp and any(t.is_alive() for t in service._smtp.workers)),
            fixture_root_removed=not (tmp_path / 'actual-main').exists(),
            owned_threads=[t.name for t in threading.enumerate() if t.name.startswith('formal-main-browser-')])
        (tmp_path / 'bootstrap-facts.json').write_text(json.dumps(facts, indent=2) + '\n')


async def hold_real_script(context, releases):
    held, release = asyncio.Event(), asyncio.Event()
    releases.append(release)
    async def hold(route, request):
        held.set()
        await release.wait()
        await route.fallback()
    await context.route('**/assets/js/auth-pages.js*', hold)
    return held, release


def take_actual_login_link(service):
    # Preserve the real SMTP URL including its actual next value. The generic
    # controller's token-only helper intentionally does not accept next links.
    sink = service._smtp
    with sink.lock:
        for index in range(len(sink.messages) - 1, -1, -1):
            body = sink.messages[index].get_body(preferencelist=('plain',))
            words = body.get_content().strip().split() if body is not None else []
            if not words: continue
            link = words[-1]
            parsed = urlsplit(link)
            query = parse_qs(parsed.query)
            if (parsed.scheme == 'https' and parsed.netloc == urlsplit(ORIGIN).netloc
                    and parsed.path == '/auth/verify' and not parsed.fragment
                    and set(query) <= {'token', 'next'} and len(query.get('token', [])) == 1):
                sink.messages.pop(index)
                return link
    raise AssertionError('actual canonical synthetic SMTP link unavailable')


@pytest.mark.parametrize('mode', ['javascript-disabled', 'script-held'])
def test_unbound_login_is_inert_and_forced_native_POST_has_no_private_fields(tmp_path, mode):
    async def run():
        async with actual_browser(tmp_path, javascript=mode != 'javascript-disabled') as (page, _, context, facts, releases):
            held = None
            if mode == 'script-held': held, _ = await hold_real_script(context, releases)
            await page.goto(ORIGIN + '/auth/login?next=%2Fresearch', wait_until='commit')
            if held is not None: await asyncio.wait_for(held.wait(), 5)
            email, submit, form = page.locator('#auth-email'), page.locator('#auth-submit'), page.locator('#auth-login-form')
            await expect(email).to_be_disabled()
            await expect(submit).to_be_disabled()
            await expect(form).to_have_attribute('method', 'post')
            await expect(form).to_have_attribute('action', '/auth/login')
            await expect(form).to_have_attribute('data-auth-ready', 'false')
            assert await page.evaluate('window.__observedLoginListener === true') is False
            if mode == 'javascript-disabled':
                # Playwright's text matcher intentionally ignores NOSCRIPT.
                assert '启用 JavaScript' in (await page.locator('noscript').text_content())
            # A synthetic field value alone cannot make a disabled control a
            # successful native form field or activate a disabled button.
            await email.evaluate('(element,value) => element.value=value', EMAIL)
            await submit.evaluate('button => button.click()')
            assert not any(r['path'] == '/api/auth/request-link' for r in facts['requests'])
            async with page.expect_request(lambda request: request.is_navigation_request() and urlsplit(request.url).path == '/auth/login') as navigation:
                await form.evaluate('form => HTMLFormElement.prototype.submit.call(form)')
            request = await navigation.value
            method_is_post = request.method == 'POST'
            safe_action_only = request.url == ORIGIN + '/auth/login'
            private_fields_omitted = request.post_data_buffer in (None, b'')
            # Failed assertions must not render a regression's URL or body.
            assert method_is_post and safe_action_only and private_fields_omitted
            facts.update(unbound_listener=False, forced_native_method='POST', forced_native_path='/auth/login', private_native_field_serialized=False)
            assert not any(r['email_in_url'] for r in facts['requests'])
    asyncio.run(run())


@pytest.mark.parametrize('requested,expected', [('/research', '/research'), ('https://other.invalid/private', '/reports')])
def test_real_script_release_then_JSON_SMTP_verify_cookie_safe_return_and_single_click(tmp_path, requested, expected):
    async def run():
        async with actual_browser(tmp_path) as (page, service, context, facts, releases):
            held, release = await hold_real_script(context, releases)
            await page.goto(ORIGIN + '/auth/login?next=' + quote(requested, safe=''), wait_until='commit')
            await asyncio.wait_for(held.wait(), 5)
            await expect(page.locator('#auth-submit')).to_be_disabled()
            assert await page.evaluate('window.__observedLoginListener === true') is False
            release.set()
            await expect(page.locator('#auth-login-form')).to_have_attribute('data-auth-ready', 'true')
            assert await page.evaluate('window.__observedLoginListener === true') is True
            await expect(page.locator('#auth-email')).to_be_enabled()
            await page.locator('#auth-email').fill('invalid-address')
            await page.locator('#auth-submit').click()
            assert not any(r['path'] == '/api/auth/request-link' for r in facts['requests'])
            await page.locator('#auth-email').fill(EMAIL)
            pending, allow_post = asyncio.Event(), asyncio.Event()
            releases.append(allow_post)
            async def hold_real_post(route, request):
                assert request.method == 'POST'
                pending.set()
                await allow_post.wait()
                await route.fallback()
            await context.route('**/api/auth/request-link', hold_real_post)
            await page.locator('#auth-submit').click()
            await asyncio.wait_for(pending.wait(), 5)
            await expect(page.locator('#auth-submit')).to_be_disabled()
            await page.locator('#auth-submit').evaluate('button => {button.click(); button.click();}')
            assert sum(r['path'] == '/api/auth/request-link' for r in facts['requests']) == 1
            async with page.expect_response('**/api/auth/request-link') as returned:
                allow_post.set()
            assert (await returned.value).status == 200
            await expect(page.locator('#auth-status')).to_contain_text('登录链接已发送')
            link = take_actual_login_link(service)
            try:
                try:
                    await page.goto(link)
                    await page.wait_for_url(ORIGIN + expected)
                except Exception:
                    # Browser navigation errors can include the one-time URL.
                    raise AssertionError('actual canonical SMTP verification did not finish') from None
            finally:
                link = None
            session_ok = await page.evaluate("async () => (await fetch('/api/auth/me', {credentials:'same-origin'})).status === 200")
            assert session_ok is True
            assert sum(r['path'] == '/api/auth/request-link' for r in facts['requests']) == 1
            assert not any(r['email_in_url'] for r in facts['requests'])
            facts.update(listener_before_release=False, listener_after_release=True, actual_JSON_request_link_status=200,
                         real_SMTP_token_consumed=True, actual_browser_session_verified=True, safe_final_path=expected,
                         invalid_input_sent=False, duplicate_natural_button_POSTs=0)
    asyncio.run(run())
