'use strict';

const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {webcrypto} = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

function element(id) {
  return {
    id,
    hidden: false,
    innerHTML: '',
    textContent: '',
    value: '',
    removed: false,
    replaceChildren() { this.innerHTML = ''; this.textContent = ''; },
    remove() { this.removed = true; elements.delete(this.id); },
  };
}

const elements = new Map();
for (const id of [
  'report-loading', 'report-error', 'report-error-msg', 'report-meta',
  'report-origin', 'analyze-share-bar', 'analyze-share-url',
  'analyze-share-bar__partial', 'analyze-vote-up-count',
  'analyze-vote-down-count', 'analyze-tldr', 'decision-brief-root',
  'analyze-sections',
]) elements.set(id, element(id));

global.window = {
  location: {
    href: 'http://localhost/report/share/' + 'c'.repeat(32),
    origin: 'http://localhost',
    pathname: '/report/share/' + 'c'.repeat(32),
  },
  crypto: webcrypto,
  _suppressAnalyzeBoot: true,
};
global.location = global.window.location;
global.document = {
  readyState: 'loading',
  addEventListener() {},
  getElementById(id) { return elements.get(id) || null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  documentElement: {getAttribute() { return 'zh'; }},
  head: {appendChild() {}},
};
global.performance = {now() { return 0; }};
global.$ = () => null;
global.escapeHtml = value => String(value == null ? '' : value)
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

require(path.join(__dirname, '..', 'assets', 'js', 'analyze.js'));
const {
  containsInternalCapability,
  renderValidatedPersistedDetail,
  resetPersistedReportState,
  validatePersistedDetail,
} = require(path.join(__dirname, '..', 'assets', 'js', 'report.js'));

const rawFixture = JSON.parse(execFileSync('python3', ['-c', [
  'import json,sys',
  "sys.path.insert(0, 'web/backend')",
  'from tests.deep_report_fixtures import report_payload',
  'print(json.dumps(report_payload(), ensure_ascii=False))',
].join(';')], {
  cwd: path.join(__dirname, '..', '..', '..'),
  encoding: 'utf8',
}));

const clone = value => JSON.parse(JSON.stringify(value));

async function currentDetail(kind) {
  const report = clone(rawFixture);
  report.action_plan.if_time_short.rationale =
    '先固定比较方案，避免后续解释口径漂移。';
  report.research_directions.source_types_to_check = [
    '待核查的研究资料', '待核查的可复现数据',
  ];
  report.your_problem_breakdown.fingerprint_revision = null;
  const source = {
    id: 'b_target',
    name: 'Target phenomenon',
    domain: 'test-domain',
    type_id: 'T',
    description: 'Internal source description for a candidate pattern.',
  };
  report.target_domain_intro.domain_name = source.domain;
  report.target_domain_intro.what_record_says = source.description;
  report.target_domain_intro.corresponding_phenomenon.name = source.name;
  report.target_domain_intro.corresponding_phenomenon.plain_description = source.description;
  report.target_domain_intro.corresponding_phenomenon.source_ref_ids = ['kb:b_target'];
  const sourceDigest = await window.StructuralAnalyzeTrust.sha256CanonicalAnalyzeJson(source);
  report.source_binding = {
    source_kb_id: 'b_target',
    source_record_sha256: sourceDigest,
    kb_artifact_id: 'artifact-test-v1',
    target_kind: 'query',
    target_kb_id: null,
    query_binding: 'a'.repeat(64),
    fingerprint_sha256: null,
    fingerprint_revision: null,
    lang: 'zh',
    model_id: 'test/deep-report-model',
    prompt_version: 'deep-report-v2',
    schema_version: 'deep-analysis-report-v2',
  };
  report.report_boundary = {
    conclusion_status: 'candidate_analogy',
    mechanism_status: 'not_verified',
    independent_review: 'not_recorded',
    literature_status: 'not_checked',
  };
  report.source_refs = [{
    source_ref_id: 'kb:b_target',
    source_kind: 'internal_kb',
    record_id: 'b_target',
    label: source.name,
    limitations: '仅为内部候选记录；不证明机制、因果、迁移有效或独立复核。',
  }];
  const detail = {
    id: 'r_0123456789abcdef',
    query: '如何区分反馈延迟与共同趋势？',
    b_id: 'b_target',
    lang: 'zh',
    payload: report,
    model: 'test/deep-report-model',
    prompt_version: 'deep-report-v2',
    created_at: '2026-07-14T00:00:00.000000Z',
    view_count: 3,
    is_partial: false,
    source: {
      id: source.id, name: source.name, domain: source.domain, type_id: source.type_id,
    },
    evidence: {
      schema_version: 'evidence-envelope-v1',
      evidence_level: 'candidate',
      candidate: {status: 'recorded', kind: 'analysis_candidate', label: source.name, score: null},
      source: {
        status: 'recorded', kind: 'internal_kb',
        label: 'Structural internal KB candidate', url: null, source_review: null,
      },
      result: {status: 'not_recorded', provenance: 'NOT_TESTED', verdict: 'NOT_TESTED', summary: null},
      independence: {status: 'not_recorded', kind: 'not_recorded', summary: null},
      counterexamples: {
        status: 'gap_recorded',
        summary: '报告必须提出证伪条件；当前未绑定任何已完成的证伪结果。',
      },
      ledger: {
        status: 'not_recorded', claim_id: null, version: null,
        recorded_at: null, artifact_sha256: null, url: null,
      },
    },
    report_sha256: await window.StructuralAnalyzeTrust.sha256CanonicalAnalyzeJson(report),
    snapshot_status: 'historical_snapshot',
  };
  if (kind === 'id') detail.share_url = '/report/share/' + 'd'.repeat(32);
  return detail;
}

async function pairDetail(kind) {
  const detail = await currentDetail(kind);
  detail.query = '';
  detail.b_id = 'target_record';
  detail.payload.source_binding.target_kind = 'kb';
  detail.payload.source_binding.target_kb_id = 'target_record';
  detail.payload.source_binding.query_binding = null;
  detail.payload.source_refs.push({
    source_ref_id: 'kb:target_record',
    source_kind: 'internal_kb',
    record_id: 'target_record',
    label: 'Target record',
    limitations: '仅作为比较目标的内部记录；不能据此判断两边机制相同。',
  });
  detail.report_sha256 = await window.StructuralAnalyzeTrust
    .sha256CanonicalAnalyzeJson(detail.payload);
  return detail;
}

test('current owner and public envelopes validate with exact route binding', async () => {
  const owner = await currentDetail('id');
  const shared = await currentDetail('share');
  assert.equal(await validatePersistedDetail(owner, {kind: 'id', value: owner.id}), true);
  assert.equal(await validatePersistedDetail(shared, {kind: 'share', value: 'c'.repeat(32)}), true);
  const pair = await pairDetail('share');
  pair.origin_candidate = {
    discovery_id: 'discovery-' + '1'.repeat(16),
    contract_version: 'discovery-candidate-v2',
    candidate_family_id: 'pair-' + '2'.repeat(12),
    tier: 'candidate_pool',
    pair: {a_id: 'b_target', b_id: 'target_record'},
    origin_content_id: 'origin-' + '3'.repeat(24),
  };
  assert.equal(await validatePersistedDetail(pair, {kind: 'share', value: 'c'.repeat(32)}), true);
  pair.origin_candidate.pair.b_id = 'wrong_target';
  assert.equal(await validatePersistedDetail(pair, {kind: 'share', value: 'c'.repeat(32)}), false);
});

test('top-level trust mismatches and capability echoes fail closed', async () => {
  const cases = [];
  const wrongId = await currentDetail('id');
  cases.push([wrongId, {kind: 'id', value: 'r_fedcba9876543210'}]);
  const absoluteShare = await currentDetail('id');
  absoluteShare.share_url = 'https://evil.test/report/share/' + 'd'.repeat(32);
  cases.push([absoluteShare, {kind: 'id', value: absoluteShare.id}]);
  const publicEcho = await currentDetail('share');
  publicEcho.share_url = null;
  cases.push([publicEcho, {kind: 'share', value: 'c'.repeat(32)}]);
  const unknown = await currentDetail('share');
  unknown.extra = 'unbound';
  cases.push([unknown, {kind: 'share', value: 'c'.repeat(32)}]);
  const nullRewrite = await currentDetail('share');
  nullRewrite.rewritten_query = null;
  cases.push([nullRewrite, {kind: 'share', value: 'c'.repeat(32)}]);
  const credibility = await currentDetail('share');
  credibility.credibility = null;
  cases.push([credibility, {kind: 'share', value: 'c'.repeat(32)}]);
  const partial = await currentDetail('share');
  partial.is_partial = true;
  cases.push([partial, {kind: 'share', value: 'c'.repeat(32)}]);
  const badTime = await currentDetail('share');
  badTime.created_at = 'not-a-date';
  cases.push([badTime, {kind: 'share', value: 'c'.repeat(32)}]);
  const badViews = await currentDetail('share');
  badViews.view_count = -1;
  cases.push([badViews, {kind: 'share', value: 'c'.repeat(32)}]);
  const wrongSource = await currentDetail('share');
  wrongSource.source.name = 'forged source';
  cases.push([wrongSource, {kind: 'share', value: 'c'.repeat(32)}]);
  const wrongEvidence = await currentDetail('share');
  wrongEvidence.evidence.result.provenance = 'INTERNAL_REAL_DATA';
  cases.push([wrongEvidence, {kind: 'share', value: 'c'.repeat(32)}]);
  const wrongMode = await currentDetail('share');
  wrongMode.b_id = 'other_target';
  cases.push([wrongMode, {kind: 'share', value: 'c'.repeat(32)}]);
  const copiedCapability = await currentDetail('share');
  copiedCapability.payload.action_plan.intro =
    'copied /report/share/' + 'e'.repeat(32);
  copiedCapability.report_sha256 = await window.StructuralAnalyzeTrust
    .sha256CanonicalAnalyzeJson(copiedCapability.payload);
  cases.push([copiedCapability, {kind: 'share', value: 'c'.repeat(32)}]);
  for (const [detail, route] of cases) {
    assert.equal(await validatePersistedDetail(detail, route), false);
  }
});

test('capability scanner catches nested browser and API routes', () => {
  assert.equal(containsInternalCapability({a: [{b: '/report/share/' + 'a'.repeat(32)}]}), true);
  assert.equal(containsInternalCapability({['/api/report/share/' + 'b'.repeat(32)]: 'x'}), true);
  assert.equal(containsInternalCapability({a: '%2Freport%2Fshare%2F' + 'c'.repeat(32)}), true);
  assert.equal(containsInternalCapability({a: '/report/share/not-a-token'}), false);
});

test('account research library never consumes or renders a share capability', () => {
  const source = fs.readFileSync(
    path.join(__dirname, '..', 'assets', 'js', 'my-reports.js'), 'utf8'
  );
  assert.doesNotMatch(source, /share_token/);
  assert.doesNotMatch(source, /\/report\/share\//);
  assert.match(source, /'\/report\/' \+ id/);
});

test('pair-mode render preserves target identity instead of forging query mode', async () => {
  const pair = await pairDetail('share');
  let meta = null;
  let decision = null;
  window.renderFinalReport = () => { meta = clone(window._analyzeMeta); };
  window.renderTldrCard = () => {};
  window.renderDecisionBrief = options => { decision = clone(options); };
  assert.equal(renderValidatedPersistedDetail(
    pair, {kind: 'share', value: 'c'.repeat(32)}
  ), true);
  assert.equal(meta.is_query_mode, false);
  assert.deepEqual(meta.b, {
    id: 'target_record', name: 'Target record', description: 'Target record',
  });
  assert.equal(decision.query, 'Target record');
  assert.match(elements.get('report-meta').innerHTML, /Target record/);
});

test('valid render commits once while a late renderer throw rolls everything back', async () => {
  const shared = await currentDetail('share');
  let renders = 0;
  window.renderFinalReport = () => {
    renders += 1;
    elements.get('analyze-sections').innerHTML = '<section>validated</section>';
  };
  window.renderTldrCard = () => {
    elements.get('analyze-tldr').innerHTML = '<strong>summary</strong>';
  };
  window.renderDecisionBrief = () => {};
  assert.equal(renderValidatedPersistedDetail(shared, {kind: 'share', value: 'c'.repeat(32)}), true);
  assert.equal(renders, 1);
  assert.equal(window._finalReport, shared.payload);

  elements.set('report-followup', element('report-followup'));
  window.renderTldrCard = () => {
    elements.get('analyze-tldr').innerHTML = '<strong>partial</strong>';
    throw new Error('adversarial renderer');
  };
  assert.throws(
    () => renderValidatedPersistedDetail(shared, {kind: 'share', value: 'c'.repeat(32)}),
    /adversarial renderer/
  );
  assert.equal(window._finalReport, null);
  assert.equal(window._analyzeMeta, null);
  assert.equal(window._persistedReport, null);
  for (const id of ['report-meta', 'analyze-sections', 'analyze-tldr',
    'decision-brief-root', 'report-origin']) {
    assert.equal(elements.get(id).innerHTML, '', id);
  }
  assert.equal(elements.get('report-meta').hidden, true);
  assert.equal(elements.get('analyze-tldr').hidden, true);
  assert.equal(elements.get('analyze-share-bar').hidden, true);
  assert.equal(elements.has('report-followup'), false);
  resetPersistedReportState();
});
