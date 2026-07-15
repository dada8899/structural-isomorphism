'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'assets', 'js', 'analytics-consent.js'),
  'utf8'
);
const helperSource = fs.readFileSync(
  path.join(__dirname, '..', 'assets', 'js', 'analytics.js'),
  'utf8'
);
const ENDPOINT = 'https://plausible.bytedance.city/api/event';

function boot(pathname, options = {}) {
  const requests = [];
  const nodes = new Map();
  const listeners = new Map();
  let assigned = null;
  let stored = options.choice === undefined
    ? JSON.stringify({
      version: 1, essential: true, analytics: true, marketing: false, source: 'explicit',
    })
    : options.choice === null ? null : JSON.stringify(options.choice);
  const suffix = options.suffix || '';
  const location = {
    href: 'https://beta.structural.bytedance.city' + pathname + suffix,
    origin: 'https://beta.structural.bytedance.city',
    pathname,
    assign(value) { assigned = value; },
  };
  const document = {
    readyState: 'complete',
    documentElement: {lang: 'zh'},
    head: {appendChild(node) { if (node.id) nodes.set(node.id, node); }},
    body: {appendChild(node) { if (node.id) nodes.set(node.id, node); }},
    addEventListener(name, handler) { listeners.set(name, handler); },
    createElement() {
      return {
        dataset: {},
        setAttribute() {},
        remove() { nodes.delete(this.id); },
      };
    },
    getElementById(id) { return nodes.get(id) || null; },
    querySelectorAll() { return []; },
  };
  const captureFetch = (url, init) => {
    requests.push({url, init, payload: JSON.parse(init.body)});
    return Promise.resolve({status: 202});
  };
  const fetch = options.fetch || captureFetch;
  const window = {
    location,
    localStorage: {
      getItem(key) { return key === 'cookie_consent_v1' ? stored : null; },
      setItem(key, value) { if (key === 'cookie_consent_v1') stored = value; },
    },
    doNotTrack: options.dnt || '0',
    fetch,
  };
  const context = vm.createContext({
    URL,
    Date,
    JSON,
    console,
    document,
    navigator: {doNotTrack: options.dnt || '0', msDoNotTrack: '0'},
    window,
  });
  vm.runInContext(source, context, {filename: 'analytics-consent.js'});

  function choose(value) {
    const handler = listeners.get('click');
    assert.equal(typeof handler, 'function');
    handler({
      target: {
        closest(selector) {
          if (selector === '[data-analytics-choice]') {
            return {getAttribute() { return value ? 'true' : 'false'; }};
          }
          return null;
        },
      },
    });
  }

  return {
    requests,
    window,
    fetch,
    choose,
    stored: () => stored && JSON.parse(stored),
    assigned: () => assigned,
    open: window.StructuralAnalytics.open,
  };
}

test('stored consent cannot send from any private research route', () => {
  for (const pathname of [
    '/analyze', '/analyze/', '/analyze.html', '/reports', '/reports/',
    '/reports.html', '/report', '/report/', '/report.html',
    '/report/r_0123456789abcdef',
    '/report/share/0123456789abcdef0123456789abcdef',
  ]) {
    const runtime = boot(pathname);
    assert.equal(runtime.requests.length, 0, pathname);
    assert.equal(runtime.window.plausible, undefined, pathname);
    runtime.open();
    assert.equal(runtime.requests.length, 0, pathname);
    assert.equal(runtime.assigned(), '/privacy#analytics', pathname);
  }
});

test('capability-shaped paths fail closed before a pageview', () => {
  for (const pathname of [
    '/invite/abcdef0123456789abcdef0123456789',
    '/invite/550e8400-e29b-41d4-a716-446655440000',
    '/resource/550e8400-e29b-41d4-a716-446655440000',
    '/reset/user%40example.com',
    '/resource/user%2540example.com',
    '/verify/token-AbCdEf0123456789',
    '/verify/' + ['eyJhbGciOiJIUzI1NiJ9', 'eyJzdWIiOiIxMjM0NTY3ODkwIn0', 'signature00'].join('.'),
    '/resource/' + ['eyJhbGciOiJIUzI1NiJ9', 'eyJzdWIiOiIxMjM0NTY3ODkwIn0', 'signature00'].join('.'),
    '/connect/AbCdEf012345.ghIjKl678901.mnOpQr234567',
    '/resource/AbCdEf012345.ghIjKl678901.mnOpQr234567',
    '/claim/abcdefghijklmnopqrstuvwxyz0123456789',
    '/resource/abcdefghijklmnopqrstuvwxyz0123456789',
    '/callback/ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
    '/resource/ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
    '/claim/AbCdEfGhIjKlMnOpQrStUvWxYz012345',
    '/phenomenon/' + ['xoxb', '123456789012', '123456789012', 'abcdefghijklmnopqrstuvwx'].join('-'),
    '/phenomenon/abcdefghijklmnopqrstuvwxyz-0123456789',
    '/phenomenon/' + ['glpat', 'abcdefghijklmnopqrstuvwxyz0123456789'].join('-'),
  ]) {
    const runtime = boot(pathname);
    assert.equal(runtime.requests.length, 0, pathname);
    assert.equal(runtime.window.plausible, undefined, pathname);
  }
  assert.equal(boot('/paper/soc-universal-collapse-2026-05-13').requests.length, 1);
  assert.equal(boot('/paper/structural.isomorphism.research-paper').requests.length, 1);
  assert.equal(boot('/phenomenon/sci-001').requests.length, 1);
  assert.equal(boot('/pricing.html').requests.length, 1);
});

test('sensitive route families fail closed even without token-shaped segments', () => {
  for (const pathname of [
    '/analyze', '/report/share/not-opaque', '/reports',
    '/Report/share/test-referrer-capability', '/%72eport/share/test-referrer-capability',
    '/%2572eport/share/test-referrer-capability',
    '/auth/login', '/auth/connect', '/auth/callback', '/auth-login.html',
    '/invite/welcome', '/invitation/accept', '/reset/start', '/verify/start',
    '/claim/start', '/connect/start', '/callback/start', '/oauth/start',
    '/sso/start', '/account/settings', '/me/favorites',
  ]) {
    const runtime = boot(pathname);
    assert.equal(runtime.requests.length, 0, pathname);
    assert.equal(runtime.window.plausible, undefined, pathname);
  }
  assert.equal(boot('/connections').requests.length, 0);
  assert.equal(boot('/claims-research').requests.length, 0);
});

test('malformed and over-encoded paths fail closed', () => {
  for (const pathname of ['/%E0%A4%A', '/resource/%2525252540']) {
    const runtime = boot(pathname);
    assert.equal(runtime.requests.length, 0, pathname);
    assert.equal(runtime.window.plausible, undefined, pathname);
  }
});

test('unknown and 404-style routes default to no analytics', () => {
  for (const pathname of [
    '/404', '/resource/ordinary-semantic-slug', '/future/new-page',
    '/paper/structuralisomorphismresearchpaper', '/phenomenon/plainidentifier',
  ]) {
    const runtime = boot(pathname);
    assert.equal(runtime.requests.length, 0, pathname);
    assert.equal(runtime.window.plausible, undefined, pathname);
  }
});

test('stored consent installs direct transport and sends a stripped pageview', () => {
  const runtime = boot('/discoveries', {suffix: '?q=secret#private'});
  assert.equal(runtime.window.plausible.s, 'direct');
  assert.equal(runtime.requests.length, 1);
  const request = runtime.requests[0];
  assert.equal(request.url, ENDPOINT);
  assert.equal(request.init.method, 'POST');
  assert.equal(request.init.credentials, 'omit');
  assert.equal(request.init.referrer, '');
  assert.equal(request.init.referrerPolicy, 'no-referrer');
  assert.deepEqual(
    JSON.parse(JSON.stringify(request.init.headers)),
    {'Content-Type': 'application/json'}
  );
  assert.deepEqual(request.payload, {
    name: 'pageview',
    url: 'https://beta.structural.bytedance.city/discoveries',
    domain: 'beta.structural.bytedance.city',
  });
  assert.equal(request.init.body.includes('secret'), false);
  assert.equal(request.init.body.includes('private'), false);
  assert.equal(source.includes("createElement('script')"), false);
  assert.equal(source.includes('/js/' + 'script.js'), false);
});

test('event and property allowlists drop raw href, secrets and caller URLs', () => {
  const runtime = boot('/');
  runtime.window.plausible('citation_click', {
    url: 'https://evil.invalid/report/share/top-secret',
    props: {
      phenomenon_id: 'sci-001',
      position: 2,
      surface: 'citation_bar',
      href: 'https://example.invalid/?token=secret',
      query: 'private research question',
      token: ['01234567', '89abcdef', '01234567', '89abcdef'].join(''),
      referrer: 'https://secret.invalid/',
    },
  });
  assert.equal(runtime.requests.length, 2);
  assert.deepEqual(runtime.requests[1].payload, {
    name: 'citation_click',
    url: 'https://beta.structural.bytedance.city/',
    domain: 'beta.structural.bytedance.city',
    props: {phenomenon_id: 'sci-001', position: 2, surface: 'citation_bar'},
  });
  const wire = runtime.requests[1].init.body;
  for (const forbidden of ['evil.invalid', 'href', 'token', 'query', 'referrer', 'secret']) {
    assert.equal(wire.includes(forbidden), false, forbidden);
  }
});

test('unknown events send nothing and opaque ids are removed', () => {
  const runtime = boot('/');
  runtime.window.plausible('unregistered_private_event', {
    props: {token: 'secret', href: 'https://secret.invalid/'},
  });
  assert.equal(runtime.requests.length, 1);
  runtime.window.plausible('candidate_selected', {
    props: {
      phenomenon_id: 'abcdefghijklmnopqrstuvwxyz-0123456789',
      position: 1,
    },
  });
  assert.equal(runtime.requests.length, 2);
  assert.deepEqual(runtime.requests[1].payload, {
    name: 'candidate_selected',
    url: 'https://beta.structural.bytedance.city/',
    domain: 'beta.structural.bytedance.city',
    props: {position: 1},
  });
});

test('newsletter link analytics exports only a coarse destination', () => {
  const runtime = boot('/learn');
  runtime.window.plausible('newsletter_link_click', {
    props: {
      issue: '2026-W19',
      destination: 'external',
      href: 'https://phase.bytedance.city/?invite=private',
    },
  });
  assert.deepEqual(runtime.requests[1].payload.props, {
    issue: '2026-W19',
    destination: 'external',
  });
  assert.equal(runtime.requests[1].init.body.includes('phase.bytedance.city'), false);
  assert.equal(runtime.requests[1].init.body.includes('invite'), false);
});

test('analytics helper rejects unknown names and never derives a raw href prop', () => {
  const calls = [];
  let click = null;
  const window = {
    location: {
      href: 'https://beta.structural.bytedance.city/newsletter/001',
      origin: 'https://beta.structural.bytedance.city',
    },
    plausible(name, options) { calls.push({name, options}); },
  };
  const document = {
    readyState: 'complete',
    body: {dataset: {}},
    addEventListener() {},
  };
  vm.runInContext(helperSource, vm.createContext({URL, document, window}), {
    filename: 'analytics.js',
  });
  window.analytics.track('private_unknown', {href: 'https://secret.invalid/'});
  assert.equal(calls.length, 0);
  const container = {
    addEventListener(name, handler) {
      assert.equal(name, 'click');
      click = handler;
    },
  };
  window.analytics.trackLinkClicks(container, {issue: '001'});
  click({
    target: {
      tagName: 'A',
      href: 'https://phase.bytedance.city/?invite=private#token',
    },
  });
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [{
    name: 'newsletter_link_click',
    options: {props: {issue: '001', destination: 'external'}},
  }]);
  assert.equal(JSON.stringify(calls).includes('invite'), false);
  assert.equal(JSON.stringify(calls).includes('token'), false);
});

test('explicit allow, revoke and stale references stay fail closed', () => {
  const runtime = boot('/', {choice: null});
  assert.equal(runtime.requests.length, 0);
  assert.equal(runtime.window.plausible, undefined);
  runtime.choose(true);
  assert.equal(runtime.requests.length, 1);
  const stale = runtime.window.plausible;
  runtime.window.plausible('thank_you_view', {props: {source: 'main_site'}});
  assert.equal(runtime.requests.length, 2);
  runtime.choose(false);
  assert.equal(runtime.window.plausible, undefined);
  stale('thank_you_view', {props: {source: 'main_site'}});
  assert.equal(runtime.requests.length, 2);
  runtime.choose(true);
  assert.equal(runtime.requests.length, 3);
  stale('thank_you_view', {props: {source: 'main_site'}});
  assert.equal(runtime.requests.length, 3);
  runtime.window.plausible('thank_you_view', {props: {source: 'main_site'}});
  assert.equal(runtime.requests.length, 4);
});

test('DNT overrides stored consent and rewrites the saved choice', () => {
  const runtime = boot('/', {dnt: '1'});
  assert.equal(runtime.requests.length, 0);
  assert.equal(runtime.window.plausible, undefined);
  assert.equal(runtime.stored().analytics, false);
  assert.equal(runtime.stored().source, 'dnt');
});

test('analytics=true without an explicit saved source is not consent', () => {
  const runtime = boot('/', {
    choice: {version: 1, essential: true, analytics: true, marketing: false},
  });
  assert.equal(runtime.requests.length, 0);
  assert.equal(runtime.window.plausible, undefined);
});

test('a route becoming sensitive blocks the installed function', () => {
  const runtime = boot('/discoveries');
  assert.equal(runtime.requests.length, 1);
  runtime.window.location.pathname = '/report/share/private-token';
  runtime.window.location.href = 'https://beta.structural.bytedance.city/report/share/private-token';
  runtime.window.plausible('discoveries_loaded', {props: {count: 10, latency_ms: 20}});
  assert.equal(runtime.requests.length, 1);
});

test('analytics does not wrap or alter unrelated fetch calls', async () => {
  const runtime = boot('/');
  assert.equal(runtime.window.fetch, runtime.fetch);
  const body = JSON.stringify({hello: 'world'});
  await runtime.window.fetch('/api/unrelated', {method: 'PUT', body});
  const request = runtime.requests.at(-1);
  assert.equal(request.url, '/api/unrelated');
  assert.equal(request.init.method, 'PUT');
  assert.equal(request.init.body, body);
});

test('transport failures are silent and leave the page callable', async () => {
  let attempts = 0;
  const runtime = boot('/', {
    fetch() {
      attempts += 1;
      if (attempts === 1) throw new Error('offline');
      return Promise.reject(new Error('blocked'));
    },
  });
  assert.equal(attempts, 1);
  assert.equal(runtime.window.plausible.s, 'direct');
  assert.doesNotThrow(() => {
    runtime.window.plausible('thank_you_view', {props: {source: 'main_site'}});
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(attempts, 2);
});
