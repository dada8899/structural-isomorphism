'use strict';

const assert = require('assert');
const path = require('path');

global.window = {};
global.document = {
  readyState: 'loading',
  addEventListener() {},
  querySelector() { return null; },
  querySelectorAll() { return []; },
  documentElement: {getAttribute() { return 'zh'; }},
};

const {
  askGenerationMatches,
  buildAskRequestBody,
  normalizeAskStreamError,
  validateAnswerDonePayload,
  validateFingerprintDraft,
} = require(path.join(__dirname, '..', 'assets', 'js', 'ask.js'));

const fingerprint = {
  source_query: '库存为什么反复过冲？',
  summary: '补货反馈存在时滞，冲击可能被放大',
  variables: ['补货延迟'],
  constraints: [],
  unknowns: ['因果方向'],
  revision: 1,
};
assert.deepStrictEqual(
  buildAskRequestBody('库存为什么反复过冲？', 'zh', fingerprint),
  {query: '库存为什么反复过冲？', lang: 'zh', fingerprint},
);

const normalizedDraft = validateFingerprintDraft('q', {
  summary: '  补货反馈存在时滞  ',
  variables: '需求，需求，库存',
  constraints: '',
  unknowns: '因果方向',
});
assert.strictEqual(normalizedDraft.ok, true);
assert.deepStrictEqual(normalizedDraft.fingerprint.variables, ['需求', '库存']);
assert.strictEqual(
  validateFingerprintDraft('q', {
    summary: '补货反馈存在时滞',
    variables: 'x'.repeat(121),
    constraints: '',
    unknowns: '',
  }).ok,
  false,
);
for (const invisible of ['\u034F', '\uFE0F']) {
  assert.strictEqual(
    validateFingerprintDraft('q', {
      summary: `补货反馈${invisible}存在时滞`,
      variables: '',
      constraints: '',
      unknowns: '',
    }).ok,
    false,
  );
}
assert.deepStrictEqual(
  buildAskRequestBody('question', 'unsupported', null),
  {query: 'question', lang: 'zh'},
);
assert.deepStrictEqual(
  normalizeAskStreamError({
    code: 'budget_exceeded',
    message: 'Daily budget exceeded; try again tomorrow.',
    retryable: false,
  }),
  {
    code: 'budget_exceeded',
    message: '今日生成额度已用完，请明天再试。',
    retryable: false,
  },
);
assert.deepStrictEqual(
  normalizeAskStreamError({code: 'upstream_timeout', message: '请重试', retryable: true}),
  {code: 'upstream_timeout', message: '请重试', retryable: true},
);

assert.strictEqual(askGenerationMatches(3, 3, 3), true);
assert.strictEqual(askGenerationMatches(2, 3, 3), false);
assert.strictEqual(askGenerationMatches(3, 3, 2), false);

const cards = [
  {id: 'kb-a', name: '候选 A'},
  {id: 'kb-b', name: '候选 B'},
];
const good = {
  full_text: '候选只提供待核查线索，尚未完成机制验证 [1]',
  citations: [{idx: 1, kb_id: 'kb-a', label: '候选 A'}],
};
assert.deepStrictEqual(
  validateAnswerDonePayload(good, cards, true),
  {fullText: good.full_text, citations: good.citations},
);
assert.strictEqual(validateAnswerDonePayload(good, cards, false), null);
assert.strictEqual(
  validateAnswerDonePayload({...good, citations: [{idx: 1, kb_id: 'unknown'}]}, cards, true),
  null,
);
assert.strictEqual(
  validateAnswerDonePayload({...good, citations: [{idx: 2, kb_id: 'kb-a'}]}, cards, true),
  null,
);
assert.strictEqual(
  validateAnswerDonePayload({...good, full_text: '没有引用标记'}, cards, true),
  null,
);
assert.strictEqual(
  validateAnswerDonePayload({...good, full_text: '非 ASCII 引用 [١]'}, cards, true),
  null,
);
assert.strictEqual(
  validateAnswerDonePayload({
    full_text: '只引用第一个候选 [1]',
    citations: [
      {idx: 1, kb_id: 'kb-a'},
      {idx: 2, kb_id: 'kb-b'},
    ],
  }, cards, true),
  null,
);
assert.deepStrictEqual(
  validateAnswerDonePayload({
    full_text: '该请求不在知识库范围内。',
    citations: [],
    out_of_scope: true,
  }, cards, true),
  {fullText: '该请求不在知识库范围内。', citations: []},
);
assert.strictEqual(
  validateAnswerDonePayload({full_text: '无引用', citations: []}, cards, true),
  null,
);

console.log('ask trust contract tests passed');
