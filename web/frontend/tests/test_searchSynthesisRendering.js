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
  renderRetiredComparison,
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

// Render the retired state with the actual bilingual catalog, without a
// query argument or fake research handoff. Existing renderer cases stay above.
const fs = require('fs');
const vm = require('vm');
const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'assets/data/i18n/content.json'), 'utf8'));
const oldGet = global.document.getElementById;
const oldDollar = global.$;
const retiredContainer = {innerHTML: '', classList: {add() {}, remove() {}}};
global.document.getElementById = id => id === 'search-synth' ? retiredContainer : null;
global.$ = selector => selector === '#search-synth' ? retiredContainer : null;
for (const lang of ['zh', 'en', 'zh']) {
  window.i18n = {t: key => catalog[key] ? catalog[key][lang] : key};
  renderRetiredComparison();
  assert.ok(retiredContainer.innerHTML.includes(catalog['page.search.retired_comparison_status'][lang]));
  assert.ok(retiredContainer.innerHTML.includes(catalog['page.search.research_no_transfer'][lang]));
  assert.ok(retiredContainer.innerHTML.includes('href="/research"'));
  assert.ok(!retiredContainer.innerHTML.includes('retry'));
  assert.ok(!retiredContainer.innerHTML.includes('?context='));
}
delete window.i18n;
global.document.getElementById = oldGet;
if (oldDollar === undefined) delete global.$;
else global.$ = oldDollar;

async function testApiRefusals() {
  const apiSource = fs.readFileSync(path.join(__dirname, '..', 'assets/js/api.js'), 'utf8');
  const rawCanary = 'DO_NOT_EXPOSE_SERVER_DETAIL_OR_PRIVATE_INPUT';
  const retired = {status: 503, code: 'FEATURE_UNAVAILABLE', retryable: false, detail: rawCanary};
  async function run(status, payload, type = 'application/problem+json', mode = 'http') {
    const timers = new Map(); let timerId = 0; let clearCount = 0; const errors = []; let requests = 0;
    const context = {window: {}, AbortController, TextDecoder, console,
      setTimeout(fn) { timers.set(++timerId, fn); return timerId; },
      clearTimeout(id) { timers.delete(id); clearCount += 1; },
      fetch: async (_url, options) => {
        requests += 1;
        if (mode === 'network') throw new Error(rawCanary);
        if (mode === 'forged-network') throw Object.assign(new Error(rawCanary), {code:'FEATURE_UNAVAILABLE',status:503});
        if (mode === 'timeout') return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(Object.assign(new Error(rawCanary), {name:'AbortError'}))));
        return {ok:false,status,headers:{get:()=>type},text:async()=>typeof payload === 'string' ? payload : JSON.stringify(payload)};
      },
    };
    vm.createContext(context);vm.runInContext(apiSource, context);
    context.window.StructuralAPI.synthesizeStream('synthetic private question', null, [{id:'kb-1'}], {onError:error=>errors.push(error)});
    if (mode === 'timeout') Array.from(timers.values())[0]();
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(errors.length, 1);assert.equal(requests, 1);assert.equal(timers.size, 0);assert.ok(clearCount > 0);
    assert.ok(!errors[0].message.includes(rawCanary));
    return {error:errors[0],api:context.window.StructuralAPI};
  }
  const valid = await run(503, retired);
  assert.equal(valid.error.code, 'FEATURE_UNAVAILABLE');assert.equal(valid.error.status, 503);
  await assert.rejects(valid.api.assessQuery('synthetic'), error => error.code === 'FEATURE_UNAVAILABLE' && !error.message.includes(rawCanary));
  for (const [status, body, type] of [
    [500,retired], [503,{...retired,code:'UPSTREAM_UNAVAILABLE'}],
    [503,{...retired,retryable:true}], [503,{...retired,status:500}],
    [503,{error:{code:'FEATURE_UNAVAILABLE'}}], [503,'{broken'],
    [503,retired,'text/html'], [503,{detail:'FEATURE_UNAVAILABLE'}],
  ]) assert.equal((await run(status,body,type)).error.code, undefined);
  assert.equal((await run(0,null,'','network')).error.code, undefined);
  assert.equal((await run(0,null,'','forged-network')).error.code, undefined);
  assert.equal((await run(0,null,'','timeout')).error.message, 'synthesis_timeout');
  const ordinary = await run(500, retired);
  await assert.rejects(ordinary.api.assessQuery('synthetic'), error => error.status === 500 && error.code === undefined && !error.message.includes(rawCanary));
  console.log('retired comparison API, rendering and safe-error contracts passed');
}
testApiRefusals().catch(error => { console.error(error); process.exitCode = 1; });
