'use strict';

const assert = require('assert');
const path = require('path');

function memoryStorage() {
  const values = new Map();
  return {
    get length() { return values.size; },
    key(index) { return Array.from(values.keys())[index] || null; },
    getItem(key) { return values.has(String(key)) ? values.get(String(key)) : null; },
    setItem(key, value) { values.set(String(key), String(value)); },
    removeItem(key) { values.delete(String(key)); },
    clear() { values.clear(); },
  };
}

global.sessionStorage = memoryStorage();
const domNodes = new Map();
function fakeElement(tagName) {
  return {
    tagName: String(tagName || '').toUpperCase(),
    id: '',
    className: '',
    children: [],
    dataset: {},
    style: {},
    attributes: {},
    parentNode: null,
    setAttribute(name, value) { this.attributes[name] = String(value); },
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
    replaceChildren() { this.children = []; },
    insertBefore(child) { child.parentNode = this; this.children.unshift(child); if (child.id) domNodes.set(child.id, child); },
    remove() { if (this.id) domNodes.delete(this.id); },
    focus() { this.focused = true; },
  };
}
const mainElement = fakeElement('main');
global.document = {
  documentElement: { lang: 'zh-CN' },
  body: fakeElement('body'),
  querySelector(selector) { return selector === 'main' ? mainElement : null; },
  getElementById(id) { return domNodes.get(id) || null; },
  createElement: fakeElement,
};
global.CustomEvent = class CustomEvent {
  constructor(type, options) { this.type = type; this.detail = options && options.detail; }
};
global.window = {
  location: { href: 'https://beta.structural.test/search' },
  dispatchedEvents: [],
  dispatchEvent(event) { this.dispatchedEvents.push(event); return true; },
};
global.history = {
  state: null,
  replaceState(state, _title, url) {
    this.state = state;
    window.location.href = new URL(url, window.location.href).href;
  },
};

let cryptoCounter = 0;
function deterministicCrypto() {
  return {
    getRandomValues(bytes) {
      cryptoCounter += 1;
      bytes.fill(cryptoCounter % 255 || 1);
      return bytes;
    },
  };
}

function setCrypto(provider) {
  Object.defineProperty(globalThis, 'crypto', {
    value: provider,
    configurable: true,
    writable: true,
  });
}

const nav = require(path.join(
  __dirname, '..', 'assets', 'js', 'utils', 'privateNavigation.js'
));

let failures = 0;
function test(name, fn) {
  try {
    sessionStorage.clear();
    history.state = null;
    window.location.href = 'https://beta.structural.test/search';
    window.dispatchedEvents = [];
    domNodes.clear();
    mainElement.children = [];
    cryptoCounter = 0;
    setCrypto(deterministicCrypto());
    fn();
    console.log('  ok   - ' + name);
  } catch (error) {
    failures += 1;
    console.error('  FAIL - ' + name);
    console.error('         ' + error.message);
  }
}

function params(url) {
  return new URL(url, 'https://beta.structural.test').searchParams;
}

console.log('private navigation tests');

test('search query is local, consumed once, scrubbed, and moved to history.state', () => {
  const secret = 'confidential board recovery question';
  const url = nav.buildPrivateSearchUrl({ query: secret, lang: 'en', force: true, source: 'home' });
  assert.strictEqual(params(url).get('q'), null);
  assert.strictEqual(params(url).get('lang'), 'en');
  assert.strictEqual(params(url).get('force'), '1');
  assert.ok(params(url).get('context'));
  assert.ok(!url.includes(secret));
  window.location.href = 'https://beta.structural.test' + url;
  const context = nav.resolvePrivateNavigationContext({
    kind: 'search', key: params(url).get('context'), lang: 'en', force: true,
  });
  assert.strictEqual(context.query, secret);
  assert.strictEqual(new URL(window.location.href).searchParams.get('context'), null);
  assert.strictEqual(history.state.structuralPrivateNavigation.query, secret);
  assert.strictEqual(nav.consumePrivateNavigationContext(params(url).get('context'), { kind: 'search' }), null);
});

test('reload and back-forward restore only the matching typed history state', () => {
  const firstUrl = nav.buildPrivateSearchUrl({ query: 'first', source: 'history' });
  window.location.href = 'https://beta.structural.test' + firstUrl;
  nav.resolvePrivateNavigationContext({ kind: 'search', key: params(firstUrl).get('context') });
  const firstState = JSON.parse(JSON.stringify(history.state));
  assert.strictEqual(nav.resolvePrivateNavigationContext({ kind: 'search' }).query, 'first');

  const secondUrl = nav.buildPrivateSearchUrl({ query: 'second', source: 'history' });
  window.location.href = 'https://beta.structural.test' + secondUrl;
  nav.resolvePrivateNavigationContext({ kind: 'search', key: params(secondUrl).get('context') });
  const secondState = JSON.parse(JSON.stringify(history.state));

  history.state = firstState;
  assert.strictEqual(nav.resolvePrivateNavigationContext({ kind: 'search' }).query, 'first');
  history.state = secondState;
  assert.strictEqual(nav.resolvePrivateNavigationContext({ kind: 'search' }).query, 'second');
});

test('multiple links remain isolated when consumed out of order', () => {
  const first = nav.buildPrivateSearchUrl({ query: 'alpha', source: 'example' });
  const second = nav.buildPrivateSearchUrl({ query: 'beta', source: 'example' });
  const firstKey = params(first).get('context');
  const secondKey = params(second).get('context');
  assert.notStrictEqual(firstKey, secondKey);
  assert.strictEqual(nav.consumePrivateNavigationContext(secondKey, { kind: 'search' }).query, 'beta');
  assert.strictEqual(nav.consumePrivateNavigationContext(firstKey, { kind: 'search' }).query, 'alpha');
});

test('phenomenon context binds id and carries typed result cards without URL text', () => {
  const results = [{
    id: 'candidate-2', name: 'Grid cascade', domain: 'Power systems',
    type_id: 'T1', description: 'A bounded public record', score: 0.8,
  }];
  const url = nav.buildPrivatePhenomenonUrl({
    id: 'candidate-1', query: 'private source question', results,
    lang: 'en', source: 'search_result',
  });
  assert.ok(url.startsWith('/phenomenon/candidate-1?'));
  assert.strictEqual(params(url).get('from_query'), null);
  assert.ok(!url.includes('private'));
  const key = params(url).get('context');
  assert.strictEqual(nav.consumePrivateNavigationContext(key, {
    kind: 'phenomenon', id: 'wrong-id'
  }), null);

  const retry = nav.buildPrivatePhenomenonUrl({
    id: 'candidate-1', query: 'private source question', results,
    lang: 'en', source: 'search_result',
  });
  const context = nav.consumePrivateNavigationContext(params(retry).get('context'), {
    kind: 'phenomenon', id: 'candidate-1'
  });
  assert.strictEqual(context.results[0].id, 'candidate-2');
  assert.strictEqual(context.results[0].retrieval_similarity, 0.8);
});

test('legacy q, from_query and text_a are scrubbed and rejected', () => {
  window.location.href = 'https://beta.structural.test/search?q=old+private+query&lang=en';
  const context = nav.resolvePrivateNavigationContext({
    kind: 'search', legacyQuery: 'old private query', lang: 'en', source: 'legacy'
  });
  assert.strictEqual(context, null);
  assert.strictEqual(new URL(window.location.href).searchParams.get('q'), null);
  assert.strictEqual(new URL(window.location.href).searchParams.get('lang'), 'en');
  assert.strictEqual(window.dispatchedEvents.at(-1).detail.code, 'legacy_query_rejected');

  window.location.href = 'https://beta.structural.test/phenomenon/x?from_query=secret&text_a=secret';
  assert.strictEqual(nav.resolvePrivateNavigationContext({ kind: 'phenomenon', id: 'x' }), null);
  assert.strictEqual(new URL(window.location.href).searchParams.get('from_query'), null);
  assert.strictEqual(new URL(window.location.href).searchParams.get('text_a'), null);
});

test('2000, 2001 and 8000 characters pass while 8001 and controls fail closed', () => {
  [2000, 2001, 8000].forEach((size) => {
    const url = nav.buildPrivateSearchUrl({ query: 'x'.repeat(size), source: 'home' });
    assert.ok(params(url).get('context'), 'missing context at ' + size);
  });
  assert.strictEqual(nav.buildPrivateSearchUrl({ query: 'x'.repeat(8001), source: 'home' }), null);
  assert.strictEqual(nav.buildPrivateSearchUrl({ query: 'bad\u0000query', source: 'home' }), null);
});

test('every backend default-ignorable range fails before a handoff is created', () => {
  const ranges = [
    [0x00AD, 0x00AD], [0x034F, 0x034F], [0x061C, 0x061C],
    [0x115F, 0x1160], [0x17B4, 0x17B5], [0x180B, 0x180F],
    [0x200B, 0x200F], [0x202A, 0x202E], [0x2060, 0x206F],
    [0x3164, 0x3164], [0xFE00, 0xFE0F], [0xFEFF, 0xFEFF],
    [0xFFA0, 0xFFA0], [0x1BCA0, 0x1BCA3], [0x1D173, 0x1D17A],
    [0xE0000, 0xE0FFF],
  ];
  const boundaries = new Set();
  ranges.forEach(([start, end]) => {
    boundaries.add(start);
    boundaries.add(end);
  });
  boundaries.forEach((codepoint) => {
    const hidden = String.fromCodePoint(codepoint);
    const before = sessionStorage.length;
    assert.strictEqual(
      nav.buildPrivateSearchUrl({query: 'alpha' + hidden + 'beta', source: 'home'}),
      null,
      'accepted U+' + codepoint.toString(16).toUpperCase()
    );
    assert.strictEqual(
      sessionStorage.length,
      before,
      'created a handoff for U+' + codepoint.toString(16).toUpperCase()
    );
  });
  assert.strictEqual(sessionStorage.length, 0);
});

test('ordinary combining accents remain legal and are NFKC-normalized', () => {
  const url = nav.buildPrivateSearchUrl({query: 'cafe\u0301 mechanism', source: 'home'});
  assert.ok(url);
  const context = nav.consumePrivateNavigationContext(params(url).get('context'), {
    kind: 'search',
  });
  assert.strictEqual(context.query, 'caf\u00e9 mechanism');
});

test('expired and unknown records are consumed and rejected', () => {
  const expired = 'a'.repeat(32);
  sessionStorage.setItem('structural_private_navigation:' + expired, JSON.stringify({
    version: 1, kind: 'search', created_at: Date.now() - 16 * 60 * 1000,
    query: 'expired', rewritten_query: null, lang: 'zh', force: false,
    source: 'home', phenomenon_id: null, results: [],
  }));
  assert.strictEqual(nav.consumePrivateNavigationContext(expired, { kind: 'search' }), null);
  const unknown = 'b'.repeat(32);
  sessionStorage.setItem('structural_private_navigation:' + unknown, JSON.stringify({
    version: 1, kind: 'search', created_at: Date.now(), query: 'secret',
    rewritten_query: null, lang: 'zh', force: false, source: 'home',
    phenomenon_id: null, results: [], injected: true,
  }));
  assert.strictEqual(nav.consumePrivateNavigationContext(unknown, { kind: 'search' }), null);
});

test('storage failure returns no destination and exposes an accessible alert', () => {
  const original = global.sessionStorage;
  global.sessionStorage = {
    get length() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
  };
  try {
    const before = window.location.href;
    const url = nav.buildPrivateSearchUrl({ query: 'must remain private', lang: 'en', source: 'home' });
    assert.strictEqual(url, null);
    assert.strictEqual(window.location.href, before);
    const alert = document.getElementById('private-navigation-error');
    assert.ok(alert);
    assert.strictEqual(alert.attributes.role, 'alert');
    assert.strictEqual(alert.attributes['aria-live'], 'assertive');
    assert.strictEqual(alert.dataset.errorCode, 'secure_handoff_unavailable');
  } finally {
    global.sessionStorage = original;
  }
});

test('missing or throwing Web Crypto fails closed without navigation', () => {
  const before = window.location.href;
  setCrypto(undefined);
  assert.strictEqual(nav.buildPrivateSearchUrl({ query: 'secret', source: 'home' }), null);
  assert.strictEqual(window.location.href, before);
  assert.strictEqual(window.dispatchedEvents.at(-1).detail.code, 'secure_handoff_unavailable');

  setCrypto({ getRandomValues() { throw new Error('entropy unavailable'); } });
  assert.strictEqual(nav.buildPrivatePhenomenonUrl({ id: 'p-1', query: 'secret' }), null);
  assert.strictEqual(window.location.href, before);
});

test('a repeated key never falls back to an existing matching history state', () => {
  const url = nav.buildPrivateSearchUrl({ query: 'one-time only', source: 'home' });
  const key = params(url).get('context');
  window.location.href = 'https://beta.structural.test' + url;
  assert.strictEqual(nav.resolvePrivateNavigationContext({ kind: 'search', key }).query, 'one-time only');
  assert.ok(history.state.structuralPrivateNavigation);

  window.location.href = 'https://beta.structural.test/search?context=' + key;
  assert.strictEqual(nav.resolvePrivateNavigationContext({ kind: 'search', key }), null);
  assert.strictEqual(history.state.structuralPrivateNavigation, undefined);
  assert.strictEqual(new URL(window.location.href).searchParams.get('context'), null);
});

test('failed key removal rejects instead of restoring history state', () => {
  const original = global.sessionStorage;
  const backing = memoryStorage();
  global.sessionStorage = backing;
  const url = nav.buildPrivateSearchUrl({ query: 'cannot replay', source: 'history' });
  const key = params(url).get('context');
  history.state = {
    structuralPrivateNavigation: {
      version: 1, kind: 'search', created_at: Date.now(), query: 'stale state',
      rewritten_query: null, lang: 'zh', force: false, source: 'history',
      phenomenon_id: null, results: [],
    },
  };
  global.sessionStorage = {
    get length() { return backing.length; },
    key(index) { return backing.key(index); },
    getItem(name) { return backing.getItem(name); },
    setItem(name, value) { backing.setItem(name, value); },
    removeItem() { /* blocked/no-op */ },
  };
  try {
    window.location.href = 'https://beta.structural.test' + url;
    assert.strictEqual(nav.resolvePrivateNavigationContext({ kind: 'search', key }), null);
    assert.strictEqual(history.state.structuralPrivateNavigation, undefined);
  } finally {
    global.sessionStorage = original;
  }
});

test('key collisions never overwrite an existing pending handoff', () => {
  const first = nav.buildPrivateSearchUrl({ query: 'first secret', source: 'home' });
  const firstKey = params(first).get('context');
  const firstStored = sessionStorage.getItem('structural_private_navigation:' + firstKey);
  let calls = 0;
  setCrypto({
    getRandomValues(bytes) {
      calls += 1;
      bytes.fill(calls === 1 ? 1 : 2);
      return bytes;
    },
  });
  const second = nav.buildPrivateSearchUrl({ query: 'second secret', source: 'home' });
  assert.notStrictEqual(params(second).get('context'), firstKey);
  assert.strictEqual(sessionStorage.getItem('structural_private_navigation:' + firstKey), firstStored);
});

if (failures) process.exit(1);
console.log('\nall tests passed.');
