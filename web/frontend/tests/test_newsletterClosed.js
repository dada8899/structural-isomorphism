'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '../../..');
const script = fs.readFileSync(path.join(root, 'web/frontend/assets/js/newsletter.js'), 'utf8');

function runtime(mounted) {
  const writes = [];
  const node = {dataset: {newsletterMounted: mounted}, value: '<form class="newsletter-form"><input type="email"><button>订阅</button></form>'};
  Object.defineProperty(node, 'innerHTML', {
    set(value) { writes.push(value); node.value = value; },
    get() { return node.value; },
  });
  const prohibited = () => { throw new Error('closed widget attempted collection'); };
  const window = {fetch: prohibited, plausible: prohibited, analytics: {track: prohibited}};
  const document = {getElementById(id) { return id === 'fixture' ? node : null; }};
  vm.runInNewContext(script, {window, document, fetch: prohibited, XMLHttpRequest: prohibited,
    setTimeout: prohibited, navigator: {sendBeacon: prohibited}}, {filename: 'newsletter.js'});
  return {window, node, writes};
}

test('old mounted form is replaced and repeated mounting is idempotent', () => {
  for (const previous of ['1', undefined]) {
    const {window, node, writes} = runtime(previous);
    window.mountNewsletter('fixture', 'start-here-essay-end');
    assert.match(node.innerHTML, /新增订阅暂不可用/);
    assert.match(node.innerHTML, /既有订阅请查看原邮件/);
    assert.doesNotMatch(node.innerHTML, /<(?:form|input|button)\b|type=["']email/);
    assert.equal(node.dataset.newsletterMounted, 'closed');
    window.mountNewsletter('fixture', 'learn-end');
    assert.equal(writes.length, 1);
    window.mountNewsletter('missing', 'discoveries-top');
  }
});

test('all three placements have a meaningful no-JS fallback and a new cache key', () => {
  for (const [page, id] of [['start-here', 'newsletter-start-here'], ['learn', 'newsletter-learn'], ['discoveries', 'newsletter-discoveries']]) {
    const html = fs.readFileSync(path.join(root, `web/frontend/${page}.html`), 'utf8');
    const start = html.indexOf(`id="${id}"`);
    assert.notEqual(start, -1);
    assert.match(html.slice(start, start + 800), /新增订阅暂不可用/);
    assert.match(html, /newsletter\.js\?v=20261017closed1/);
    assert.doesNotMatch(html, /<script[^>]+src=["'][^"']*\/waitlist\.js/);
  }
});

test('homepage preserves research controls and removes its capture form and inline handler', () => {
  const html = fs.readFileSync(path.join(root, 'web/frontend/index.html'), 'utf8');
  assert.match(html, /id="start-research"[^>]+href="\/research"/);
  assert.match(html, /id="ask-form"[^>]+method="post"[^>]+action="\/research"/);
  assert.match(html, /id="research-next"/);
  assert.match(html, /新增订阅暂不可用/);
  assert.doesNotMatch(html, /id="waitlist-(?:form|email)"|fetch\(['"]\/api\/waitlist|utm_source|waitlist_signup/);
});

test('the release frontend has no consumer for the retained external waitlist script', () => {
  const frontend = path.join(root, 'web/frontend');
  const pages = fs.readdirSync(frontend).filter(name => name.endsWith('.html'));
  for (const name of pages) {
    const html = fs.readFileSync(path.join(frontend, name), 'utf8');
    assert.doesNotMatch(html, /<script[^>]+src=["'][^"']*\/waitlist\.js/, name);
    assert.doesNotMatch(html, /id=["']waitlist-form["']/, name);
  }
  assert.ok(fs.existsSync(path.join(frontend, 'assets/js/waitlist.js')));
});
