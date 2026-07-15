'use strict';

const assert = require('assert');
const path = require('path');
const contracts = require(path.join(
  __dirname, '..', 'assets', 'js', 'secondary-tool-contracts.js'
));

function evidence(label, sourceKind = 'not_recorded') {
  const sourceRecorded = sourceKind === 'internal_kb';
  return {
    schema_version: 'evidence-envelope-v1',
    evidence_level: 'candidate',
    candidate: {status: 'recorded', kind: 'candidate', label, score: null},
    source: {
      status: sourceRecorded ? 'recorded' : 'not_recorded',
      kind: sourceKind,
      label: sourceRecorded ? 'Structural KB record' : null,
      url: null,
      source_review: null,
    },
    result: {
      status: sourceRecorded ? 'not_recorded' : 'recorded',
      provenance: sourceRecorded ? 'NOT_TESTED' : 'INTERNAL_AI_SCREEN',
      verdict: sourceRecorded ? 'NOT_TESTED' : 'INCONCLUSIVE',
      summary: null,
    },
    independence: {status: 'not_recorded', kind: 'not_recorded', summary: null},
    counterexamples: {status: 'not_recorded', summary: null},
    ledger: {
      status: 'not_recorded', claim_id: null, version: null, recorded_at: null,
      artifact_sha256: null, url: null,
    },
  };
}

function reference() {
  return {
    id: 'kb-1', name: '候选记录', domain: '生态学', description: '描述',
    retrieval_rank: 1, candidate_note: null,
    evidence: evidence('候选记录', 'internal_kb'),
  };
}

const requestId = 'secondary-1234567890';
assert.match(contracts.createRequestId('stress'), /^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$/);

const stress = {
  contract_version: contracts.CONTRACT_VERSION,
  request_id: requestId,
  claim: '我们像一个受延迟反馈控制的系统',
  screening_outcome: 'condition_dependent',
  screening_basis: 'internal_ai_red_team',
  source: '受控系统', target: '当前团队',
  structural_correspondences: [{
    claim: '反馈存在时滞', screening_outcome: 'breaks', stress_result: '时滞尚未测量',
  }],
  weakest_link: '时滞未测量', rationale: '需要先测量反馈延迟。',
  candidate_reference: reference(),
  evidence: evidence('我们像一个受延迟反馈控制的系统'),
};
assert.strictEqual(
  contracts.validateStressPayload(stress, requestId, stress.claim), stress
);
assert.strictEqual(contracts.validateStressPayload({...stress, verdict: 'PASS'}, requestId, stress.claim), null);
assert.strictEqual(contracts.validateStressPayload({...stress, request_id: 'secondary-wrong000'}, requestId, stress.claim), null);

const state = {
  state_id: 'hysteresis_trap', name: '滞回陷阱', definition: '路径依赖。',
  typical_signal: '去掉原因后仍不回弹。',
};
const diagnose = {
  contract_version: contracts.CONTRACT_VERSION,
  request_id: requestId,
  situation: '流程改过两次，但团队协作方式没有变化。',
  assessment_kind: 'structural_state_hypothesis',
  primary_state: state,
  secondary_state: {...state, state_id: 'cascade_fragility', name: '级联脆弱'},
  reasoning: '描述与路径依赖候选相符。', evolution: '如果条件不变，旧模式可能延续。',
  signals_to_watch: ['改流程后决策时长是否下降'], recommendations: ['先记录一轮基线'],
  candidate_reference: null,
  evidence: evidence('流程改过两次，但团队协作方式没有变化。'),
};
assert.strictEqual(
  contracts.validateDiagnosePayload(diagnose, requestId, diagnose.situation), diagnose
);
assert.strictEqual(contracts.validateDiagnosePayload({
  ...diagnose, primary_state: {...state, confidence: 0.9},
}, requestId, diagnose.situation), null);

const apply = {
  contract_version: contracts.CONTRACT_VERSION,
  request_id: requestId,
  method: '用局部反馈迭代寻找较优方案', signature: '局部反馈迭代',
  signature_origin: 'model_generated', keywords: ['局部反馈'], count: 1,
  candidates: [{
    id: 'kb-1', name: '候选记录', domain: '生态学', type_id: 'feedback',
    description: '描述', retrieval_rank: 1, candidate_note: null,
    evidence: evidence('候选记录', 'internal_kb'),
  }],
  evidence: evidence('用局部反馈迭代寻找较优方案'),
};
assert.strictEqual(contracts.validateApplyPayload(apply, requestId, apply.method), apply);
assert.strictEqual(contracts.validateApplyPayload({
  ...apply, candidates: [{...apply.candidates[0], relevance: 0.9}],
}, requestId, apply.method), null);
const scoredApply = JSON.parse(JSON.stringify(apply));
scoredApply.candidates[0].evidence.candidate.score = 0.9;
assert.strictEqual(contracts.validateApplyPayload(scoredApply, requestId, apply.method), null);
const poisonedApply = JSON.parse(JSON.stringify(apply));
poisonedApply.candidates[0].evidence.source.status = 'not_recorded';
assert.strictEqual(contracts.validateApplyPayload(poisonedApply, requestId, apply.method), null);

const documentText = '我们认为预算翻倍会让增长线性放大。';
const lint = {
  contract_version: contracts.CONTRACT_VERSION,
  request_id: requestId,
  screening_kind: 'internal_ai_document_screen',
  summary: '优先核查线性增长假设。',
  claims: [{
    claim_id: 'lint-0123456789abcdef',
    quote: '预算翻倍会让增长线性放大',
    claim_type: 'causal_judgment', structure: '投入与结果被假设为线性。',
    failure_mode: '边际回报可能递减。', review_priority: 'high',
    suggestion: '先做分段增量测试。', reference_candidate: null,
    evidence: evidence('预算翻倍会让增长线性放大'),
  }],
  evidence: evidence('用户提交的策略文档'),
};
assert.strictEqual(contracts.validateLintPayload(lint, requestId, documentText), lint);
assert.strictEqual(contracts.validateLintPayload({
  ...lint, claims: [{...lint.claims[0], quote: '模型虚构的原文'}],
}, requestId, documentText), null);
assert.strictEqual(contracts.validateLintPayload({
  ...lint, claims: [{...lint.claims[0], risk_level: 'high'}],
}, requestId, documentText), null);

console.log('secondary tool client contracts passed');
