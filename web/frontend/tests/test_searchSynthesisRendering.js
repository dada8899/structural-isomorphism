'use strict';

const assert = require('assert');
const path = require('path');

global.window = { addEventListener() {} };
global.document = {
  addEventListener() {},
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
global.localStorage = { getItem() { return null; }, setItem() {} };

require(path.join(__dirname, '..', 'assets', 'js', 'utils.js'));
const {
  resolveSearchSynthesisCandidate,
  synthesisGenerationMatches,
  containsRenderableMath,
} = require(path.join(
  __dirname, '..', 'assets', 'js', 'search.js'
));

const poison = '[open](https://invented.example)<img src=x onerror=alert(1)>';
const inline = window.mdInline(poison);
const paragraphs = window.mdParagraphs(poison);

assert.ok(inline.includes('[open](https://invented.example)'));
assert.ok(inline.includes('&lt;img src=x onerror=alert(1)&gt;'));
assert.ok(!inline.includes('<a '));
assert.ok(!inline.includes('<img'));
assert.ok(!paragraphs.includes('<a '));
assert.ok(!paragraphs.includes('<img'));

const reorderedResults = [
  { id: 'kb-1', name: 'First browser row' },
  { id: 'kb-2', name: 'Second browser row' },
];
const rebound = resolveSearchSynthesisCandidate({
  source_kb_id: 'kb-2',
  result_index: 1,
}, reorderedResults);
assert.strictEqual(rebound.record.id, 'kb-2');
assert.strictEqual(rebound.index, 1);
assert.strictEqual(
  resolveSearchSynthesisCandidate({ source_kb_id: 'unknown', result_index: 1 }, reorderedResults),
  null,
);

assert.strictEqual(synthesisGenerationMatches(3, 7, 3, 7), true);
assert.strictEqual(synthesisGenerationMatches(3, 7, 4, 7), false);
assert.strictEqual(synthesisGenerationMatches(3, 7, 3, 8), false);
assert.strictEqual(containsRenderableMath({ textContent: 'No equation is present.' }), false);
assert.strictEqual(containsRenderableMath({ textContent: 'Compare $x(t)=ax(t-1)$ first.' }), true);
assert.strictEqual(containsRenderableMath({ textContent: 'The cost is $5, not a formula.' }), false);
assert.strictEqual(
  resolveSearchSynthesisCandidate(
    { source_kb_id: 'kb-2', result_index: 1 },
    [...reorderedResults, { id: 'kb-2', name: 'duplicate' }],
  ),
  null,
);

console.log('search synthesis rendering tests passed');
