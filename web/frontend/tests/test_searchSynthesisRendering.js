'use strict';

const assert = require('assert');
const path = require('path');

global.window = { addEventListener() {} };
global.document = {
  addEventListener() {},
  getElementById() { return null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
global.localStorage = { getItem() { return null; }, setItem() {} };

require(path.join(__dirname, '..', 'assets', 'js', 'utils.js'));
global.escapeHtml = window.escapeHtml;
window.buildAnalyzeUrl = ({id}) => `/analyze?id=${encodeURIComponent(id)}`;
const {
  resolveSearchSynthesisCandidate,
  synthesisGenerationMatches,
  guardSynthesisCallbacks,
  renderResultsWithSynth,
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

const callbackEvents = [];
let callbackState = {run: 4, generation: 2};
const guarded = guardSynthesisCallbacks(4, 2, () => callbackState, {
  onText: value => callbackEvents.push(['text', value]),
  onDone: value => callbackEvents.push(['done', value]),
  onError: value => callbackEvents.push(['error', value]),
});
assert.strictEqual(guarded.onText('current-progress'), true);
callbackState = {run: 5, generation: 0};
assert.strictEqual(guarded.onText('stale-progress'), false);
assert.strictEqual(guarded.onDone('stale-done'), false);
assert.strictEqual(guarded.onError('stale-error'), false);
assert.deepStrictEqual(callbackEvents, [['text', 'current-progress']]);
const throwingGuard = guardSynthesisCallbacks(4, 2, () => { throw new Error('state unavailable'); }, {
  onDone: value => callbackEvents.push(['unexpected', value]),
});
assert.strictEqual(throwingGuard.onDone('must-not-render'), false);

const apiOrder = [
  {id: 'kb-5', name: 'API row five', domain: 'biology', type_id: 'cascade', description: 'd5'},
  {id: 'kb-1', name: 'API row one', domain: 'physics', type_id: 'cascade', description: 'd1'},
  {id: 'kb-3', name: 'API row three', domain: 'ecology', type_id: 'cascade', description: 'd3'},
  {id: 'kb-2', name: 'API row two', domain: 'finance', type_id: 'cascade', description: 'd2'},
  {id: 'kb-4', name: 'API row four', domain: 'networks', type_id: 'cascade', description: 'd4'},
];
const container = {innerHTML: '', textContent: ''};
const rendered = renderResultsWithSynth({
  query: 'private reordered query',
  results: apiOrder,
  stats: {cross_domain_count: 5},
  container,
  synth: {
    primary_recommendation: {
      source_kb_id: 'kb-2',
      result_index: 0,
      reason: 'Bound by canonical source id.',
    },
    alternative_angles: [{source_kb_id: 'kb-5', result_index: 4, angle_label: 'Alternative'}],
    relevance_snippets: [],
  },
});
assert.ok(rendered.includes('API row two'));
assert.ok(rendered.includes('本次排序 #4'));
assert.ok(rendered.indexOf('API row three') < rendered.indexOf('API row four'));
assert.ok(!rendered.includes('private reordered query'));

console.log('search synthesis rendering tests passed');
