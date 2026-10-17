"""The former four open-signup scenarios now assert the approved closed release.

The old 200/create/duplicate/timeout contract is intentionally replaced, not
preserved with a development flag or a fabricated signup/SMTP response.
"""
import json
from urllib.parse import urlsplit

from web.tests.e2e.test_subscriptions_closed import subscription_site, subscription_browser


def context_for(browser, base, *, javascript=True):
    context = browser.new_context(java_script_enabled=javascript, service_workers='block')
    parsed = urlsplit(base)
    def local_only(route):
        target = urlsplit(route.request.url)
        if target.hostname == '127.0.0.1' and target.port == parsed.port:route.continue_()
        else:route.abort()
    context.route('**/*', local_only)
    return context


def test_cached_newsletter_http_client_gets_closed_without_capture(subscription_site, subscription_browser):
    base, state = subscription_site
    material = state / 'retained-newsletter-material.jsonl'
    material.write_bytes(b'retained material; no real subscriber data\n')
    before = material.read_bytes()
    context = context_for(subscription_browser, base)
    try:
        response = context.request.post(base + '/api/newsletter/subscribe',
            data=json.dumps({'email': 'OLD-CACHED-CLIENT@example.invalid', 'source': 'test'}),
            headers={'Content-Type': 'application/json'})
        assert response.status == 503
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['created'] is False and response.json()['ok'] is False
        assert 'OLD-CACHED-CLIENT' not in response.text() and 'email' not in response.json()
        assert material.read_bytes() == before
        assert 'OLD-CACHED-CLIENT' not in (state / 'server-output.txt').read_text()
    finally:context.close()


def test_closed_newsletter_static_state_visible_without_javascript(subscription_site, subscription_browser):
    # The previous successful-capture placement now has an honest no-JS state.
    base, _ = subscription_site
    context = context_for(subscription_browser, base, javascript=False)
    try:
        page = context.new_page();response = page.goto(base + '/start-here')
        assert response.status == 200
        notice = page.locator('#newsletter-start-here')
        assert notice.is_visible() and '新增订阅暂不可用' in notice.inner_text()
        assert notice.locator('form,input,button').count() == 0
        assert '已加入' not in notice.inner_text()
    finally:context.close()


def test_old_mounted_newsletter_cannot_reactivate_on_repeat(subscription_site, subscription_browser):
    # A stale mounted form is replaced; repeat mount cannot reactivate it.
    base, _ = subscription_site
    context = context_for(subscription_browser, base)
    try:
        page = context.new_page();page.goto(base + '/learn', wait_until='networkidle')
        result = page.evaluate('''() => {
          const root=document.getElementById('newsletter-learn');
          root.innerHTML='<form><input type="email"><button>订阅</button></form>';
          root.dataset.newsletterMounted='1';
          window.mountNewsletter('newsletter-learn','learn-end');
          const first=root.outerHTML;
          window.mountNewsletter('newsletter-learn','learn-end');
          return {same:first===root.outerHTML,forms:root.querySelectorAll('form,input').length,
                  state:root.dataset.newsletterMounted,text:root.textContent};
        }''')
        assert result['same'] and result['forms'] == 0 and result['state'] == 'closed'
        assert '新增订阅暂不可用' in result['text']
    finally:context.close()


def test_closed_newsletter_does_not_start_a_fetch_to_time_out(subscription_site, subscription_browser):
    # There is no subscription fetch to hang. The trap never fabricates a
    # success response, and unrelated genuine research GETs keep their behavior.
    base, _ = subscription_site
    context = context_for(subscription_browser, base)
    try:
        page = context.new_page();page.goto(base + '/discoveries', wait_until='networkidle')
        page.evaluate('''() => {
          window.__subscriptionFetchAttempts=0;
          const original=window.fetch;
          window.fetch=function(url,...args){
            if(String(url).includes('/newsletter/')||String(url).includes('/api/waitlist')){
              window.__subscriptionFetchAttempts++;
              throw new Error('closed subscription fetch must never run');
            }
            return original.call(this,url,...args);
          };
          const root=document.getElementById('newsletter-discoveries');
          root.dataset.newsletterMounted='1';
          root.innerHTML='<form><input type="email"><button>订阅</button></form>';
          window.mountNewsletter('newsletter-discoveries','discoveries-top');
          root.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
        }''')
        page.wait_for_timeout(250)
        assert page.evaluate('window.__subscriptionFetchAttempts') == 0
        assert page.locator('#newsletter-discoveries form,#newsletter-discoveries input[type=email]').count() == 0
        assert '新增订阅暂不可用' in page.locator('#newsletter-discoveries').inner_text()
    finally:context.close()
