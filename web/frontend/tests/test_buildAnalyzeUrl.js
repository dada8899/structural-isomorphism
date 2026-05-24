/**
 * Unit test for utils/buildAnalyzeUrl.js — single source of truth for the
 * /analyze page URL contract. SESSION-21 §1 patched four callers; this test
 * locks the builder behavior so future drift is caught.
 *
 * Run: node web/frontend/tests/test_buildAnalyzeUrl.js
 * Exit non-zero on any assertion failure.
 *
 * No test framework dependency on purpose — the main frontend has no JS test
 * harness yet, and node's built-in `assert` is sufficient for a pure helper.
 */
'use strict';

const assert = require('assert');
const path = require('path');

const { buildAnalyzeUrl } = require(
  path.join(__dirname, '..', 'assets', 'js', 'utils', 'buildAnalyzeUrl.js')
);

let failed = 0;
function test(name, fn) {
  try {
    fn();
    console.log('  ok   - ' + name);
  } catch (err) {
    failed++;
    console.error('  FAIL - ' + name);
    console.error('         ' + (err && err.message ? err.message : err));
  }
}

console.log('buildAnalyzeUrl tests');

// 1. Happy path: id + q produces the canonical form.
test('id + q -> /analyze?id=...&q=...', function () {
  const url = buildAnalyzeUrl({ id: 'kb-123', q: 'why does X happen' });
  // URLSearchParams uses + for spaces, encodes per application/x-www-form-urlencoded.
  assert.strictEqual(url, '/analyze?id=kb-123&q=why+does+X+happen');
});

// 2. id-only is valid (matches /analyze CTA from search results).
test('id only -> /analyze?id=...', function () {
  assert.strictEqual(
    buildAnalyzeUrl({ id: 'kb-456' }),
    '/analyze?id=kb-456'
  );
});

// 3. q-only is valid (whitespace lead without anchor_id).
test('q only -> /analyze?q=...', function () {
  assert.strictEqual(
    buildAnalyzeUrl({ q: '研究问题' }),
    '/analyze?q=%E7%A0%94%E7%A9%B6%E9%97%AE%E9%A2%98'
  );
});

// 4. a_id third param shows up when set.
test('id + q + a_id -> all three params', function () {
  const url = buildAnalyzeUrl({ id: 'b1', q: 'q1', a_id: 'a1' });
  assert.strictEqual(url, '/analyze?id=b1&q=q1&a_id=a1');
});

// 5. Empty object -> bare /analyze (no trailing ?).
test('empty opts -> /analyze (no query string)', function () {
  assert.strictEqual(buildAnalyzeUrl({}), '/analyze');
  assert.strictEqual(buildAnalyzeUrl(), '/analyze');
});

// 6. Null / undefined / empty-string values are dropped, not stringified.
test('null / undefined / empty drop out', function () {
  assert.strictEqual(buildAnalyzeUrl({ id: null, q: undefined }), '/analyze');
  assert.strictEqual(buildAnalyzeUrl({ id: '', q: '' }), '/analyze');
  assert.strictEqual(
    buildAnalyzeUrl({ id: 'x', q: '', a_id: null }),
    '/analyze?id=x'
  );
});

// 7. Special chars in q are url-encoded (the SESSION-21 bug class).
test('special chars in q get encoded', function () {
  const url = buildAnalyzeUrl({ q: 'a & b = c?' });
  // & = ? all need encoding.
  assert.ok(url.includes('a+%26+b+%3D+c%3F'), 'expected encoded chars, got: ' + url);
  assert.ok(!url.includes('a & b'), 'raw special chars leaked: ' + url);
});

// 8. Numeric id coerces to string (defensive — callers may pass typed data).
test('numeric id coerces to string', function () {
  assert.strictEqual(
    buildAnalyzeUrl({ id: 42, q: 'hi' }),
    '/analyze?id=42&q=hi'
  );
});

// 9. Contract-lock: the param NAMES must be id/q/a_id, NOT backend API names.
// This is the exact bug SESSION-21 fixed (callers using text_a/b_id). If
// anyone "fixes" this builder to match the API, the test catches it.
test('uses frontend param names (id/q), not API names (text_a/b_id)', function () {
  const url = buildAnalyzeUrl({ id: 'kb-1', q: 'hello' });
  assert.ok(url.includes('id=kb-1'), 'must use id=, got: ' + url);
  assert.ok(url.includes('q=hello'), 'must use q=, got: ' + url);
  assert.ok(!url.includes('text_a='), 'must NOT leak API name text_a: ' + url);
  assert.ok(!url.includes('b_id='), 'must NOT leak API name b_id: ' + url);
});

if (failed > 0) {
  console.error('\n' + failed + ' test(s) failed.');
  process.exit(1);
}
console.log('\nall tests passed.');
