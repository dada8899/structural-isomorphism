/**
 * Unit contract for the privacy-preserving /analyze handoff.
 *
 * Run: node web/frontend/tests/test_buildAnalyzeUrl.js
 */
'use strict';

const assert = require('assert');
const path = require('path');

function memoryStorage() {
  const values = new Map();
  return {
    get length() { return values.size; },
    key(index) { return Array.from(values.keys())[index] || null; },
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(String(key), String(value)); },
    removeItem(key) { values.delete(String(key)); },
    clear() { values.clear(); },
  };
}

global.sessionStorage = memoryStorage();

const {
  buildAnalyzeUrl,
  consumeAnalyzeHandoff,
  MAX_RESEARCH_QUERY_CHARS,
} = require(
  path.join(__dirname, '..', 'assets', 'js', 'utils', 'buildAnalyzeUrl.js')
);

let failed = 0;
function test(name, fn) {
  try {
    sessionStorage.clear();
    fn();
    console.log('  ok   - ' + name);
  } catch (err) {
    failed++;
    console.error('  FAIL - ' + name);
    console.error('         ' + (err && err.message ? err.message : err));
  }
}

function params(url) {
  return new URL(url, 'https://beta.structural.test').searchParams;
}

console.log('buildAnalyzeUrl privacy handoff tests');

test('analyze and Ask share the 8000-character research-query contract', function () {
  assert.strictEqual(MAX_RESEARCH_QUERY_CHARS, 8000);
});

test('question stays in sessionStorage, never in URL', function () {
  const question = 'why does X happen? a & b';
  const url = buildAnalyzeUrl({ id: 'kb-123', q: question });
  const query = params(url);
  assert.strictEqual(query.get('id'), 'kb-123');
  assert.match(query.get('handoff'), /^[0-9a-f]{16,64}$/);
  assert.strictEqual(query.get('q'), null);
  assert.ok(!url.includes(question));
  const stored = JSON.parse(sessionStorage.getItem(
    'structural_analyze_handoff:' + query.get('handoff')
  ));
  assert.strictEqual(stored.query, question);
  assert.strictEqual(stored.id, 'kb-123');
});

test('confirmed fingerprint travels inside the same local record', function () {
  const fingerprint = {
    source_query: '团队为什么恢复很慢？',
    summary: '团队在冲突后的恢复速度持续下降',
    variables: ['信任'], constraints: [], unknowns: [], revision: 1,
  };
  const url = buildAnalyzeUrl({ id: 'kb-1', q: fingerprint.source_query, fingerprint });
  const key = params(url).get('handoff');
  const stored = JSON.parse(sessionStorage.getItem('structural_analyze_handoff:' + key));
  assert.deepStrictEqual(stored.fingerprint, {
    ...fingerprint,
    source_query: '团队为什么恢复很慢?'
  });
  assert.ok(!url.includes('fingerprint'));
});

test('candidate provenance stays in the one-use local record', function () {
  const url = buildAnalyzeUrl({
    id: 'kb-1', a_id: 'kb-2', q: 'private research question',
    origin_discovery_id: 'discovery-0123456789abcdef',
    origin_contract_version: 'discovery-candidate-v2',
  });
  const query = params(url);
  assert.strictEqual(query.get('origin_discovery_id'), null);
  const handoff = consumeAnalyzeHandoff(query.get('handoff'), { id: 'kb-1', a_id: 'kb-2' });
  assert.strictEqual(handoff.origin_discovery_id, 'discovery-0123456789abcdef');
  assert.strictEqual(handoff.origin_contract_version, 'discovery-candidate-v2');
});

test('handoff is consumed once and bound to the expected ids', function () {
  const url = buildAnalyzeUrl({ id: 'b1', a_id: 'a1', q: 'private question' });
  const key = params(url).get('handoff');
  const first = consumeAnalyzeHandoff(key, { id: 'b1', a_id: 'a1' });
  assert.strictEqual(first.query, 'private question');
  assert.strictEqual(consumeAnalyzeHandoff(key, { id: 'b1', a_id: 'a1' }), null);
  assert.strictEqual(sessionStorage.getItem('structural_analyze_handoff:' + key), null);
});

test('id mismatch fails closed and still consumes the record', function () {
  const url = buildAnalyzeUrl({ id: 'expected', q: 'private question' });
  const key = params(url).get('handoff');
  assert.strictEqual(consumeAnalyzeHandoff(key, { id: 'other', a_id: null }), null);
  assert.strictEqual(consumeAnalyzeHandoff(key, { id: 'expected', a_id: null }), null);
});

test('multiple pending links are isolated and can be consumed out of order', function () {
  const firstUrl = buildAnalyzeUrl({ id: 'b1', q: 'first private question' });
  const secondUrl = buildAnalyzeUrl({ id: 'b2', q: 'second private question' });
  const firstKey = params(firstUrl).get('handoff');
  const secondKey = params(secondUrl).get('handoff');
  assert.notStrictEqual(firstKey, secondKey);
  assert.strictEqual(
    consumeAnalyzeHandoff(secondKey, { id: 'b2', a_id: null }).query,
    'second private question'
  );
  assert.strictEqual(
    consumeAnalyzeHandoff(firstKey, { id: 'b1', a_id: null }).query,
    'first private question'
  );
});

test('expired and malformed records fail closed and are removed', function () {
  const expiredKey = 'a'.repeat(32);
  sessionStorage.setItem('structural_analyze_handoff:' + expiredKey, JSON.stringify({
    version: 1,
    created_at: Date.now() - (16 * 60 * 1000),
    query: 'expired secret',
    id: 'b1',
    a_id: null,
  }));
  assert.strictEqual(
    consumeAnalyzeHandoff(expiredKey, { id: 'b1', a_id: null }),
    null
  );
  assert.strictEqual(sessionStorage.getItem('structural_analyze_handoff:' + expiredKey), null);

  const malformedKey = 'b'.repeat(32);
  sessionStorage.setItem('structural_analyze_handoff:' + malformedKey, '{bad json');
  assert.strictEqual(
    consumeAnalyzeHandoff(malformedKey, { id: 'b1', a_id: null }),
    null
  );
  assert.strictEqual(sessionStorage.getItem('structural_analyze_handoff:' + malformedKey), null);
});

test('future-dated handoffs fail closed', function () {
  const key = 'c'.repeat(32);
  sessionStorage.setItem('structural_analyze_handoff:' + key, JSON.stringify({
    version: 2,
    created_at: Date.now() + 60000,
    query: 'future secret',
    id: 'b1',
    a_id: null,
  }));
  assert.strictEqual(consumeAnalyzeHandoff(key, { id: 'b1', a_id: null }), null);
  assert.strictEqual(sessionStorage.getItem('structural_analyze_handoff:' + key), null);
});

test('id-only and empty values remain ordinary public URLs', function () {
  assert.strictEqual(buildAnalyzeUrl({ id: 'kb-456' }), '/analyze?id=kb-456');
  assert.strictEqual(buildAnalyzeUrl({}), '/analyze');
  assert.strictEqual(buildAnalyzeUrl(), '/analyze');
  assert.strictEqual(buildAnalyzeUrl({ id: '', q: '' }), '/analyze');
});

test('q-only uses a handoff and does not expose special characters', function () {
  const url = buildAnalyzeUrl({ q: 'a & b = c?' });
  assert.ok(params(url).get('handoff'));
  assert.strictEqual(params(url).get('q'), null);
  assert.ok(!url.includes('a+%26+b'));
});

test('numeric public id is coerced while private question stays local', function () {
  const url = buildAnalyzeUrl({ id: 42, q: 'hi' });
  assert.strictEqual(params(url).get('id'), '42');
  assert.ok(params(url).get('handoff'));
  assert.strictEqual(params(url).get('q'), null);
});

test('invalid ids, controls, 8001-char text, and unknown fingerprint fields fail closed', function () {
  assert.strictEqual(buildAnalyzeUrl({ id: '../escape', q: 'secret' }), '/analyze');
  assert.strictEqual(buildAnalyzeUrl({ id: 'kb-1', a_id: 'https://evil.test', q: 'secret' }), '/analyze?id=kb-1');
  assert.strictEqual(buildAnalyzeUrl({ id: 'kb-1', q: 'bad\u0000secret' }), '/analyze?id=kb-1');
  assert.strictEqual(buildAnalyzeUrl({ id: 'kb-1', q: 'x'.repeat(8001) }), '/analyze?id=kb-1');
  assert.strictEqual(buildAnalyzeUrl({
    id: 'kb-1', q: 'private question',
    fingerprint: {
      source_query: 'private question', summary: 'A sufficiently long summary',
      variables: [], constraints: [], unknowns: [], revision: 1,
      injected: true,
    },
  }), '/analyze?id=kb-1');
  assert.strictEqual(sessionStorage.length, 0);
});

test('2000, 2001, and 8000 characters survive; 8001 fails closed', function () {
  [2000, 2001, 8000].forEach(function (size) {
    const url = buildAnalyzeUrl({ id: 'kb-' + size, q: 'x'.repeat(size) });
    const key = params(url).get('handoff');
    assert.ok(key, 'expected handoff at size ' + size);
    const value = consumeAnalyzeHandoff(key, { id: 'kb-' + size, a_id: null });
    assert.strictEqual(value.query.length, size);
  });
  assert.strictEqual(
    buildAnalyzeUrl({ id: 'kb-8001', q: 'x'.repeat(8001) }),
    '/analyze?id=kb-8001'
  );
});

test('NFKC normalization is applied before storage and binding', function () {
  const url = buildAnalyzeUrl({ id: 'kb-1', q: 'ＡＢＣ mechanism' });
  const key = params(url).get('handoff');
  const value = consumeAnalyzeHandoff(key, { id: 'kb-1', a_id: null });
  assert.strictEqual(value.query, 'ABC mechanism');
});

test('default-ignorable Unicode fails closed while ordinary combining text survives', function () {
  ['\u034f', '\ufe0f', '\u200b', '\u{1bca0}', '\u{e0001}'].forEach(function (hidden) {
    assert.strictEqual(
      buildAnalyzeUrl({ id: 'kb-hidden', q: 'private' + hidden + ' question' }),
      '/analyze?id=kb-hidden'
    );
  });
  const url = buildAnalyzeUrl({ id: 'kb-accent', q: 'cafe\u0301 mechanism' });
  const key = params(url).get('handoff');
  assert.ok(key);
  assert.strictEqual(
    consumeAnalyzeHandoff(key, { id: 'kb-accent', a_id: null }).query,
    'café mechanism'
  );
});

test('storage failure is privacy fail-closed, never URL fallback', function () {
  const original = global.sessionStorage;
  global.sessionStorage = {
    get length() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
  };
  try {
    const url = buildAnalyzeUrl({ id: 'kb-9', q: 'must stay private' });
    assert.strictEqual(url, '/analyze?id=kb-9');
    assert.ok(!url.includes('must'));
  } finally {
    global.sessionStorage = original;
  }
});

test('missing or throwing Web Crypto is privacy fail-closed', function () {
  const descriptor = Object.getOwnPropertyDescriptor(global, 'crypto');
  try {
    Object.defineProperty(global, 'crypto', {
      configurable: true,
      value: undefined,
    });
    assert.strictEqual(
      buildAnalyzeUrl({ id: 'kb-crypto', q: 'must stay private' }),
      '/analyze?id=kb-crypto'
    );
    Object.defineProperty(global, 'crypto', {
      configurable: true,
      value: { getRandomValues() { throw new Error('entropy unavailable'); } },
    });
    assert.strictEqual(
      buildAnalyzeUrl({ id: 'kb-throw', q: 'must also stay private' }),
      '/analyze?id=kb-throw'
    );
    assert.strictEqual(sessionStorage.length, 0);
  } finally {
    if (descriptor) Object.defineProperty(global, 'crypto', descriptor);
    else delete global.crypto;
  }
});

test('key collisions never overwrite an existing pending handoff', function () {
  const descriptor = Object.getOwnPropertyDescriptor(global, 'crypto');
  const collidedKey = '00'.repeat(16);
  const storageKey = 'structural_analyze_handoff:' + collidedKey;
  const existingRecord = JSON.stringify({
    version: 2,
    created_at: Date.now(),
    query: 'existing private question',
    id: 'kb-existing',
    a_id: null,
    fingerprint: null,
    origin_discovery_id: null,
    origin_contract_version: null,
  });
  sessionStorage.setItem(storageKey, existingRecord);
  try {
    Object.defineProperty(global, 'crypto', {
      configurable: true,
      value: { getRandomValues(bytes) { bytes.fill(0); return bytes; } },
    });
    assert.strictEqual(
      buildAnalyzeUrl({ id: 'kb-collision', q: 'collision secret' }),
      '/analyze?id=kb-collision'
    );
    assert.strictEqual(sessionStorage.getItem(storageKey), existingRecord);
  } finally {
    if (descriptor) Object.defineProperty(global, 'crypto', descriptor);
    else delete global.crypto;
  }
});

test('a handoff is rejected when storage refuses to remove it', function () {
  const url = buildAnalyzeUrl({ id: 'kb-remove', q: 'remove secret' });
  const key = params(url).get('handoff');
  const originalRemove = sessionStorage.removeItem;
  sessionStorage.removeItem = function () {};
  try {
    assert.strictEqual(
      consumeAnalyzeHandoff(key, { id: 'kb-remove', a_id: null }),
      null
    );
  } finally {
    sessionStorage.removeItem = originalRemove;
  }
});

if (failed > 0) {
  console.error('\n' + failed + ' test(s) failed.');
  process.exit(1);
}
console.log('\nall tests passed.');
