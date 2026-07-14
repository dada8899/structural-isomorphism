'use strict';

const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

global.window = {
  location: {href: 'http://localhost/analyze', origin: 'http://localhost'},
  crypto: webcrypto,
};
global.location = global.window.location;
global.document = {
  addEventListener() {},
  getElementById() { return null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  documentElement: {getAttribute() { return 'zh'; }},
};
global.performance = {now() { return 0; }};
global.$ = () => null;
global.escapeHtml = value => String(value == null ? '' : value)
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

const {
  analyzeGenerationMatches,
  buildDecisionBriefModel,
  canonicalAnalyzeJson,
  commitAnalyzeReportForDisplay,
  createAnalyzeRequestContext,
  createAnalyzeTrustState,
  decisionBriefMarkdown,
  renderAnalyzeActionPlan,
  renderAnalyzeBorrowableInsights,
  renderAnalyzeHowToCombine,
  renderAnalyzeResearchDirections,
  renderAnalyzeRisksAndLimits,
  renderAnalyzeSharedStructure,
  renderAnalyzeStructuralMapping,
  renderAnalyzeTargetDomainIntro,
  setAnalyzeReportStageState,
  sharePersistedAnalyzeReport,
  sha256CanonicalAnalyzeJson,
  validateAnalyzeMetaEnvelope,
  validateAnalyzeReportEnvelope,
} = require(path.join(__dirname, '..', 'assets', 'js', 'analyze.js'));

const clone = value => JSON.parse(JSON.stringify(value));

function useEnglishFixedCopy(report) {
  report.target_domain_intro.source_limitations = [
    'Internal KB candidate only; systematic review, independent replication, and expert review are not recorded.',
  ];
  report.research_directions.status_explanation =
    'External literature was not searched; precedent and novelty remain unknown.';
  const experiment = report.how_to_combine.discriminating_experiment;
  experiment.decision_rule =
    'Continue only if the candidate hypothesis outperforms the competitor on the preregistered primary outcome; otherwise reject the candidate.';
  experiment.falsification_rule =
    'Falsify and reject the candidate if it does not outperform the competitor or the result reverses the preregistered direction.';
  experiment.stop_rule =
    'Stop the experiment without a mechanism conclusion if minimum data, data quality, or safety requirements are not met.';
  for (const action of report.action_plan.this_week) {
    action.decision_rule =
      'Continue only when the preregistered primary metric provides discriminating information; otherwise stop and review the candidate.';
    action.stop_condition =
      'Stop the action if minimum data, data quality, or safety requirements are not met.';
  }
}

function completeReport(sourceBinding, sourceRefs, source) {
  return {
    schema_version: 'deep-analysis-report-v2',
    evidence_level: 'candidate',
    generation_status: 'validated',
    shared_structure: {
      status: 'candidate',
      name: '延迟反馈候选结构',
      formal_expression: 'x(t+1)=f(x(t),u(t))',
      intuition: '延迟观测可能让局部修正产生过冲，仍需与替代解释比较。',
      observations: [{
        signal_to_check: '波动是否在反馈延迟后稳定出现。',
        candidate_implication: '若该信号在预注册数据中出现，延迟反馈值得继续比较。',
        status: 'not_checked',
      }],
      competing_explanations: ['外部冲击也可能产生相似的时间序列。'],
      evidence_gaps: ['尚缺少干预前后的对照数据。'],
      failure_conditions: ['若缩短反馈延迟后波动不变，该候选结构会减弱。'],
    },
    your_problem_breakdown: {
      summary: '需要判断反馈延迟是否值得优先测量。',
      key_variables: [{name: '反馈延迟', description: '从变化发生到观测可见的时间。', role: 'parameter'}],
      dynamics: '观测、决策和结果可能形成带延迟的闭环。',
      why_stuck: '当前记录无法区分延迟反馈与外部冲击。',
      fingerprint_revision: sourceBinding.fingerprint_revision,
      uncertain_points: ['外部冲击的频率尚不清楚。'],
    },
    target_domain_intro: {
      domain_name: source.domain,
      what_record_says: source.description,
      corresponding_phenomenon: {
        name: source.name,
        plain_description: source.description,
        source_ref_ids: [sourceRefs[0].source_ref_id],
      },
      source_limitations: ['仅为内部 KB 候选记录；系统综述、独立复现与专家审查均未记录。'],
      candidate_methods: [{
        name: '延迟敏感性检查',
        proposal_status: 'unverified_proposal',
        why_considered: '它可以帮助比较不同反馈延迟下的波动变化。',
        source_support: 'not_recorded',
        evidence_required: '需要带时间戳的输入与结果记录。',
      }],
    },
    structural_mapping: {
      status: 'untested',
      rationale: '两边都可以先用反馈延迟作为待检验参数。',
      parameter_map: [{
        source_concept: '补货延迟',
        source_explanation: '来源记录中的反馈等待时间。',
        target_concept: '决策反馈延迟',
        target_explanation: '目标问题中结果回到决策者的时间。',
        support_status: 'hypothesis',
        mapping_hypothesis: '两种延迟可能影响过冲幅度。',
        evidence_for: [],
        evidence_against: ['两边的外部冲击来源不同。'],
        observable_test: '比较缩短延迟前后的波动幅度。',
        failure_signal: '延迟变化后波动没有方向一致的变化。',
      }],
      competing_explanations: ['共同的外部周期可能造成表面相似。'],
    },
    borrowable_insights: [{
      tool: '延迟敏感性检查',
      proposal_status: 'unverified_proposal',
      why_considered: '它可能帮助判断反馈等待是否值得进一步研究。',
      translated_to_target: '先改变观测频率，再比较波动变化。',
      concrete_application: '保留其他规则不变，分阶段缩短结果反馈间隔。',
      source_support: 'not_recorded',
      transfer_status: 'untested',
      prerequisites: ['能够记录每次决策与结果的时间。'],
      failure_signal: '改变反馈间隔后主要指标没有稳定变化。',
    }],
    how_to_combine: {
      steps: ['建立当前延迟与波动的基线。', '只改变反馈间隔并保留对照。'],
      assumptions_to_verify: ['记录时间能够代表真实反馈时间。'],
      boundary_conditions: ['外部规则变化期间暂停比较。'],
      discriminating_experiment: {
        question: '缩短反馈延迟是否改变波动幅度？',
        candidate_hypothesis: '若延迟是关键因素，缩短延迟后波动会减弱。',
        competitor_hypotheses: ['外部冲击主导波动。'],
        intervention_or_measurement: '随机选择部分周期缩短反馈间隔，并保留原流程对照。',
        primary_outcome: '相邻周期变化幅度的绝对值。',
        expected_outcomes: [
          {hypothesis_id: 'candidate', role: 'candidate', expected_observation: '处理组的波动幅度下降。'},
          {hypothesis_id: 'competitor', role: 'competitor', expected_observation: '两组变化没有稳定差异。'},
        ],
        confounds: ['同期外部政策变化。'],
        minimum_data: '至少覆盖多个完整反馈周期。',
        procedure: ['记录基线周期。', '执行单一变量干预。'],
        decision_rule: '仅当候选假设在预注册主指标上优于竞争假设时继续；否则拒绝候选。',
        falsification_rule: '若候选假设未优于竞争假设，或结果方向与预注册预期相反，则证伪并拒绝候选。',
        stop_rule: '若最低数据要求、数据质量或安全边界不满足，则停止实验且不作机制结论。',
        threshold_basis: 'proposal',
        calibration_required: true,
      },
    },
    research_directions: {
      literature_status: 'not_checked',
      status_explanation: '未执行外部文献检索；先例与新颖性仍未知。',
      search_questions: ['反馈延迟如何影响闭环波动？', '哪些实验可以区分外部冲击？'],
      source_types_to_check: ['同行评审研究', '可复现实验数据'],
      suggested_references: [],
    },
    risks_and_limits: [{
      risk_name: '把时间相关误当作机制',
      severity: 'high',
      explanation: '同时出现不能排除共同外因。',
      condition: '外部环境同期发生明显变化。',
      observable_signal: '未干预变量也出现同方向变化。',
      stop_rule: '共同外因无法记录时暂停迁移判断。',
    }],
    action_plan: {
      intro: '先完成低成本测量，再决定是否进入干预。',
      if_time_short: {title: '记录反馈延迟', rationale: '该测量能够缩小解释空间。'},
      this_week: [
        {
          rank: 1,
          title: '记录反馈延迟',
          how: '为决策、反馈和结果增加统一时间戳。',
          hypothesis_id: 'candidate',
          primary_metric: '反馈间隔与波动幅度。',
          decision_rule: '仅当预注册主指标提供可区分信息时继续；否则停止并复核候选。',
          stop_condition: '若最低数据要求、数据质量或安全边界不满足，则停止该行动。',
          expected_information: '判断延迟是否值得进入下一轮实验。',
          estimated_time: '两个反馈周期',
          category: 'measurement',
          threshold_basis: 'proposal',
          calibration_required: true,
        },
        {
          rank: 2,
          title: '建立外部冲击对照',
          how: '记录同期规则与环境变化。',
          hypothesis_id: 'competitor',
          primary_metric: '外部事件与波动的同步关系。',
          decision_rule: '仅当预注册主指标提供可区分信息时继续；否则停止并复核候选。',
          stop_condition: '若最低数据要求、数据质量或安全边界不满足，则停止该行动。',
          expected_information: '排除一部分共同外因。',
          estimated_time: '一个反馈周期',
          category: 'diagnostic',
          threshold_basis: 'proposal',
          calibration_required: true,
        },
      ],
      review_trigger: '完成基线与对照记录后重新评估。',
    },
    source_binding: clone(sourceBinding),
    report_boundary: {
      conclusion_status: 'candidate_analogy',
      mechanism_status: 'not_verified',
      independent_review: 'not_recorded',
      literature_status: 'not_checked',
    },
    source_refs: clone(sourceRefs),
  };
}

async function fixture({persist = 1} = {}) {
  const query = '怎样判断反馈延迟是否造成周期性过冲?';
  const fingerprintRequest = {
    source_query: query,
    summary: '反馈延迟可能影响周期性过冲,需要对照外部冲击。',
    variables: ['反馈延迟', '波动幅度'],
    constraints: ['只能逐步调整'],
    unknowns: ['外部冲击频率'],
    revision: 2,
  };
  const projectedFingerprint = {
    summary: fingerprintRequest.summary,
    variables: fingerprintRequest.variables,
    constraints: fingerprintRequest.constraints,
    unknowns: fingerprintRequest.unknowns,
    revision: 2,
    provenance: 'user_confirmed',
  };
  const request = {
    b_id: 'source-one',
    text_a: query,
    lang: 'zh',
    persist,
    fingerprint: fingerprintRequest,
    ...(persist ? {anon_id: 'anon-test'} : {}),
  };
  const source = {
    id: 'source-one',
    name: '延迟反馈记录',
    domain: '供应链',
    type_id: 'feedback',
    description: '内部记录描述了延迟反馈下的候选波动模式。',
  };
  const sourceBinding = {
    source_kb_id: source.id,
    source_record_sha256: await sha256CanonicalAnalyzeJson(source, webcrypto),
    kb_artifact_id: 'kb-artifact-test',
    target_kind: 'query',
    target_kb_id: null,
    query_binding: 'b'.repeat(64),
    fingerprint_sha256: await sha256CanonicalAnalyzeJson(projectedFingerprint, webcrypto),
    fingerprint_revision: 2,
    lang: 'zh',
    model_id: 'test-model',
    prompt_version: 'deep-report-v2',
    schema_version: 'deep-analysis-report-v2',
  };
  const sourceRefs = [{
    source_ref_id: `kb:${source.id}`,
    source_kind: 'internal_kb',
    record_id: source.id,
    label: source.name,
    limitations: '仅为内部候选记录；不证明机制、因果、迁移有效或独立复核。',
  }];
  const meta = {
    generation_id: 'g_' + '1'.repeat(24),
    a: source,
    b: {
      id: '__query__', name: query, domain: '你的问题', type_id: 'unknown',
      description: query, original_query: query,
    },
    is_query_mode: true,
    evidence: {
      schema_version: 'evidence-envelope-v1',
      evidence_level: 'candidate',
      candidate: {status: 'recorded', kind: 'analysis_candidate', label: source.name, score: null},
      source: {
        status: 'recorded', kind: 'internal_kb', label: 'Structural internal KB candidate',
        url: null, source_review: null,
      },
      result: {
        status: 'not_recorded', provenance: 'NOT_TESTED', verdict: 'NOT_TESTED', summary: null,
      },
      independence: {status: 'not_recorded', kind: 'not_recorded', summary: null},
      counterexamples: {
        status: 'gap_recorded',
        summary: '报告必须提出证伪条件；当前未绑定任何已完成的证伪结果。',
      },
      ledger: {
        status: 'not_recorded', claim_id: null, version: null, recorded_at: null,
        artifact_sha256: null, url: null,
      },
    },
    fingerprint: projectedFingerprint,
    model: 'test-model',
    lang: 'zh',
    artifact_id: 'kb-artifact-test',
    prompt_version: 'deep-report-v2',
    schema_version: 'deep-analysis-report-v2',
    report_boundary: {
      conclusion_status: 'candidate_analogy', mechanism_status: 'not_verified',
      independent_review: 'not_recorded', literature_status: 'not_checked',
    },
    source_binding: sourceBinding,
    source_refs: sourceRefs,
    origin_candidate: null,
  };
  const report = completeReport(sourceBinding, sourceRefs, source);
  const hash = await sha256CanonicalAnalyzeJson(report, webcrypto);
  const receipt = {
    generation_id: meta.generation_id,
    report_sha256: hash,
    schema_version: 'deep-analysis-report-v2',
    from_cache: false,
  };
  const persisted = {
    id: 'r_' + '2'.repeat(16),
    share_url: 'http://localhost/report/share/' + '3'.repeat(32),
    created_at: '2026-07-14T05:30:00.000000Z',
    is_partial: false,
    origin_candidate: null,
    generation_id: meta.generation_id,
    report_sha256: hash,
  };
  const done = {
    generation_id: meta.generation_id,
    report_sha256: hash,
    report,
    from_cache: false,
  };
  return {request, meta, report, hash, receipt, persisted, done};
}

async function pairFixture() {
  const data = await fixture({persist: 0});
  data.request = {b_id: 'target-two', a_id: 'source-one', lang: 'zh', persist: 0};
  data.meta.b = {
    id: 'target-two', name: '目标记录', domain: '组织协作', type_id: 'coordination',
    description: '目标记录描述了协作节奏变化。',
  };
  data.meta.is_query_mode = false;
  data.meta.fingerprint = null;
  data.meta.source_binding.target_kind = 'kb';
  data.meta.source_binding.target_kb_id = 'target-two';
  data.meta.source_binding.query_binding = null;
  data.meta.source_binding.fingerprint_sha256 = null;
  data.meta.source_binding.fingerprint_revision = null;
  data.meta.source_refs.push({
    source_ref_id: 'kb:target-two', source_kind: 'internal_kb', record_id: 'target-two',
    label: '目标记录', limitations: '仅作为比较目标的内部记录；不能据此判断两边机制相同。',
  });
  data.report.source_binding = clone(data.meta.source_binding);
  data.report.source_refs = clone(data.meta.source_refs);
  data.report.your_problem_breakdown.fingerprint_revision = null;
  data.hash = await sha256CanonicalAnalyzeJson(data.report, webcrypto);
  data.receipt.report_sha256 = data.hash;
  data.done = {
    generation_id: data.meta.generation_id,
    report_sha256: data.hash,
    report: data.report,
    from_cache: false,
  };
  return data;
}

async function ingestThroughSections(state, data, count = 9) {
  await state.ingest('meta', clone(data.meta));
  await state.ingest('generation_progress', {stage: 'generating', attempt: 1});
  await state.ingest('generation_progress', {stage: 'validating', attempt: 1, received_chars: 200});
  await state.ingest('report_validated', clone(data.receipt));
  const keys = [
    'shared_structure', 'your_problem_breakdown', 'target_domain_intro',
    'structural_mapping', 'borrowable_insights', 'how_to_combine',
    'research_directions', 'risks_and_limits', 'action_plan',
  ];
  for (const key of keys.slice(0, count)) {
    await state.ingest('section', {key, data: clone(data.report[key])});
  }
}

test('generation guard and canonical JSON are deterministic', () => {
  assert.equal(analyzeGenerationMatches(3, 3), true);
  assert.equal(analyzeGenerationMatches(2, 3), false);
  assert.equal(canonicalAnalyzeJson({b: 2, a: ['中', true]}), '{"a":["中",true],"b":2}');
});

test('semantic guard ships without regex lookbehind for older Safari', () => {
  const source = fs.readFileSync(
    path.join(__dirname, '..', 'assets', 'js', 'analyze.js'),
    'utf8'
  );
  assert.doesNotMatch(source, /\(\?<=/);
});

test('complete report and meta fixtures pass strict contracts', async () => {
  const data = await fixture();
  assert.equal(await validateAnalyzeMetaEnvelope(data.meta, data.request, webcrypto), true);
  assert.equal(validateAnalyzeReportEnvelope(data.report, data.meta), true);
});

test('empty shell, revision drift, missing binding, strong claim, and unknown source fail', async () => {
  const data = await fixture();
  const attacks = [
    report => { report.shared_structure = {}; },
    report => { report.your_problem_breakdown.fingerprint_revision = 999; },
    report => { delete report.source_binding.target_kind; },
    report => { report.shared_structure.intuition = '研究已经证明两者同构。'; },
    report => { report.target_domain_intro.corresponding_phenomenon.source_ref_ids = ['kb:unknown']; },
  ];
  for (const attack of attacks) {
    const report = clone(data.report);
    attack(report);
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false);
  }
});

test('known overclaim variants fail while explicit cautions remain valid', async () => {
  const data = await fixture();
  const attacks = [
    '该方法适用于各类团队。', '该方法放之四海而皆准。', '无论什么团队都能奏效。',
    '在任意团队中均可奏效。', '从未出现过失败案例。', '这套方法百试百灵。',
    '实证结果支持该方案可靠落地。', '已有实验证明迁移是可靠的。',
    '数据验证了方法的稳健性。', '它们的动力学别无二致。', '二者是一回事。',
    'The method is universally applicable.', 'The transfer is flawless.',
    'The approach succeeds without exception.', 'No counterexample exists.',
    'The mechanism generalizes universally.', 'The mapping has been empirically validated.',
    'Empirical validation confirms the mapping.',
    'Both systems are governed by identical dynamics.',
    'The systems exhibit identical causal dynamics.', 'The result is conclusive.',
  ];
  for (const claim of attacks) {
    const report = clone(data.report);
    report.shared_structure.intuition = claim;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false, claim);
  }

  const pathLaundering = clone(data.report);
  pathLaundering.borrowable_insights[0].failure_signal =
    'Experiments have shown the method works.';
  assert.equal(validateAnalyzeReportEnvelope(pathLaundering, data.meta), false);
  const cautions = [
    '尚无数据验证该方法的稳健性。', '没有实验证明迁移是可靠的。',
    '目前没有研究确认二者机制相同。', '尚无实证结果支持该方案可靠落地。',
    'We have no empirical validation confirming the mapping.',
    'The mapping has not been empirically validated.',
    'No data confirms that the approach is reliable.',
    'No study has shown identical causal dynamics.',
  ];
  for (const caution of cautions) {
    const report = clone(data.report);
    report.shared_structure.intuition = caution;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), true, caution);
  }
});

test('source-owned quotes bypass model claim guard but status contradictions do not', async () => {
  const sourceQuote = await fixture();
  const quote = '来源记录声称研究已经证明该方案有效。';
  sourceQuote.meta.a.description = quote;
  const sourceRecord = {};
  for (const key of ['id', 'name', 'domain', 'type_id', 'description']) {
    sourceRecord[key] = sourceQuote.meta.a[key];
  }
  sourceQuote.meta.source_binding.source_record_sha256 =
    await sha256CanonicalAnalyzeJson(sourceRecord, webcrypto);
  sourceQuote.report.source_binding = clone(sourceQuote.meta.source_binding);
  sourceQuote.report.target_domain_intro.what_record_says = quote;
  sourceQuote.report.target_domain_intro.corresponding_phenomenon.plain_description = quote;
  assert.equal(
    await validateAnalyzeMetaEnvelope(sourceQuote.meta, sourceQuote.request, webcrypto), true
  );
  assert.equal(validateAnalyzeReportEnvelope(sourceQuote.report, sourceQuote.meta), true);

  const data = await fixture();
  for (const contradiction of [
    '已经完成文献检索。', '该方法是成熟工具。',
    'The literature has been reviewed.', 'This is a validated method.',
  ]) {
    const report = clone(data.report);
    report.shared_structure.intuition = contradiction;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false, contradiction);
  }
  const cautious = clone(data.report);
  cautious.shared_structure.intuition = '尚未完成文献检索。';
  assert.equal(validateAnalyzeReportEnvelope(cautious, data.meta), true);
});

test('frontend mirrors backend candidate-state synonyms and safe negations', async () => {
  const data = await fixture();
  const attacks = [
    report => {
      report.borrowable_insights[0].concrete_application =
        'The transfer was successful in fifty production deployments.';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        'The method worked across fifty production deployments.';
    },
    report => {
      report.shared_structure.observations[0].signal_to_check =
        'Independent replication found the mapping robust.';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        '这项迁移在五十次生产部署中均奏效。';
    },
    report => {
      report.shared_structure.observations[0].signal_to_check =
        'Field trials support this approach.';
    },
    report => {
      report.target_domain_intro.source_limitations[0] =
        'Limited only by sample size; a third-party audit signed off on the source.';
    },
    report => {
      report.target_domain_intro.source_limitations[0] =
        '仅样本量有限；第三方审阅认定来源可靠。';
    },
    report => {
      report.how_to_combine.discriminating_experiment.decision_rule =
        'If error falls below the empirically calibrated cutoff of 0.7, continue.';
    },
    report => {
      report.how_to_combine.discriminating_experiment.decision_rule =
        '如果误差低于经实证校准的阈值0.7，则继续。';
    },
    report => {
      report.how_to_combine.discriminating_experiment.stop_rule =
        'Do not stop under any outcome.';
    },
    report => {
      report.how_to_combine.discriminating_experiment.decision_rule =
        'If any result arrives, continue in all cases.';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        'Across fifty production deployments, the transfer produced reliable results.';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        'Fifty field deployments yielded reliable performance.';
    },
    report => {
      report.shared_structure.observations[0].signal_to_check =
        'External teams reproduced the effect.';
    },
    report => {
      report.shared_structure.observations[0].signal_to_check =
        'Third-party replication corroborated the mapping.';
    },
    report => {
      report.shared_structure.observations[0].signal_to_check =
        'Deployment evidence indicates the method is robust.';
    },
    report => {
      report.target_domain_intro.source_limitations[0] =
        'Only the sample is limited; auditors deemed the source trustworthy.';
    },
    report => {
      report.research_directions.status_explanation =
        'Literature has not been formally checked; A broad survey of the literature found no prior method.';
    },
    report => {
      report.research_directions.status_explanation =
        'Literature has not been formally checked; An exhaustive search found this approach to be unprecedented.';
    },
    report => {
      report.how_to_combine.discriminating_experiment.decision_rule =
        'If error is below the threshold calibrated against empirical data, continue.';
    },
    report => {
      report.how_to_combine.discriminating_experiment.decision_rule =
        'If error is below the evidence-calibrated cutoff, continue.';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        'The effect was reproduced by an independent laboratory.';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        'Other groups reproduced the effect.';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        'An outside laboratory corroborated the mapping.';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        'Real-world use confirmed the mechanism.';
    },
    report => {
      report.borrowable_insights[0].concrete_application = '外部实验室复现了该结果。';
    },
    report => {
      report.borrowable_insights[0].concrete_application = '其他团队重复出了相同结果。';
    },
    report => {
      report.target_domain_intro.source_limitations[0] =
        'The sample is limited, but the source earned a clean audit.';
    },
    report => {
      report.target_domain_intro.source_limitations[0] =
        'The sample is limited; reviewers gave the source a clean bill of health.';
    },
    report => {
      report.research_directions.status_explanation =
        'Literature has not been formally checked; a scoping review identified this approach as novel.';
    },
    report => {
      report.research_directions.status_explanation =
        'Literature has not been formally checked; no earlier work was found after searching the literature.';
    },
    report => {
      report.research_directions.status_explanation = '文献检索后未发现更早的方法。';
    },
    report => {
      report.how_to_combine.discriminating_experiment.decision_rule =
        'If error is below the cutoff derived from historical data, continue.';
    },
    report => {
      report.how_to_combine.discriminating_experiment.decision_rule =
        'If error is below the evidence-fitted threshold, continue.';
    },
    report => {
      report.how_to_combine.discriminating_experiment.decision_rule =
        '如果误差低于根据历史数据拟合的阈值，则继续。';
    },
    report => {
      report.borrowable_insights[0].concrete_application =
        'The transfer was not successful in fifty production deployments.';
    },
    report => {
      report.shared_structure.observations[0].signal_to_check =
        'Independent replication did not find the mapping robust.';
    },
    report => {
      report.shared_structure.observations[0].signal_to_check =
        'Field trials do not support this approach.';
    },
  ];
  for (const attack of attacks) {
    const report = clone(data.report);
    attack(report);
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false);
  }

  const safe = [
    report => {
      report.structural_mapping.rationale = 'No deployment evidence is recorded.';
    },
    report => {
      report.structural_mapping.rationale = '尚无部署证据记录。';
    },
    report => {
      report.structural_mapping.rationale = 'No independent replication is recorded.';
    },
    report => {
      report.structural_mapping.rationale = '尚未记录独立复现。';
    },
    report => {
      report.structural_mapping.rationale =
        'No study has established that this is novel.';
    },
    report => {
      report.structural_mapping.rationale = '没有研究确认该方法新颖。';
    },
    report => {
      report.structural_mapping.rationale =
        'No experiments confirm that the model improves results.';
    },
  ];
  for (const caution of safe) {
    const report = clone(data.report);
    caution(report);
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), true);
  }
});

test('split claims and non-discriminating duplicate hypotheses fail closed', async () => {
  const data = await fixture();
  const split = clone(data.report);
  split.shared_structure.name = '研究已经证明两者';
  split.shared_structure.formal_expression = '同构';
  assert.equal(validateAnalyzeReportEnvelope(split, data.meta), false);

  const duplicateOutcome = clone(data.report);
  duplicateOutcome.how_to_combine.discriminating_experiment.expected_outcomes[1]
    .hypothesis_id = 'candidate';
  assert.equal(validateAnalyzeReportEnvelope(duplicateOutcome, data.meta), false);

  const duplicateCompetitor = clone(data.report);
  const experiment = duplicateCompetitor.how_to_combine.discriminating_experiment;
  experiment.competitor_hypotheses.push(experiment.competitor_hypotheses[0]);
  assert.equal(validateAnalyzeReportEnvelope(duplicateCompetitor, data.meta), false);

  const duplicateObservation = clone(data.report);
  duplicateObservation.how_to_combine.discriminating_experiment.expected_outcomes[1]
    .expected_observation = duplicateObservation.how_to_combine
      .discriminating_experiment.expected_outcomes[0].expected_observation;
  assert.equal(validateAnalyzeReportEnvelope(duplicateObservation, data.meta), false);

  const missingRole = clone(data.report);
  delete missingRole.how_to_combine.discriminating_experiment.expected_outcomes[0].role;
  assert.equal(validateAnalyzeReportEnvelope(missingRole, data.meta), false);
});

test('proposal reasons cannot launder source attribution, including Unicode disguises', async () => {
  const data = await fixture();
  for (const attribution of [
    '某研究机构在医院部署并证明了这套方法。',
    'National Foo Institute deploys this method.',
    'National Foo Institute ｄｅｐｌｏｙｓ this method.',
    '某研究机构在医院部\u034F署这套方法。',
  ]) {
    const method = clone(data.report);
    method.target_domain_intro.candidate_methods[0].why_considered = attribution;
    assert.equal(validateAnalyzeReportEnvelope(method, data.meta), false, attribution);
    const insight = clone(data.report);
    insight.borrowable_insights[0].why_considered = attribution;
    assert.equal(validateAnalyzeReportEnvelope(insight, data.meta), false, attribution);
  }
});

test('Unicode and markup cannot hide completed-evidence or isomorphism claims', async () => {
  const data = await fixture();
  for (const disguised of [
    '研究已经证\u034F明两者同构。',
    '研究已经证**明两者同构。',
    'The mapping has been ｖａｌｉｄａｔｅｄ.',
    'This method has been val\u034Fidated.',
  ]) {
    const report = clone(data.report);
    report.shared_structure.intuition = disguised;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false, disguised);
  }
});

test('meta must be fully bound to the request and source digest', async () => {
  const data = await fixture();
  for (const mutate of [
    meta => { meta.b.description = '另一条问题'; },
    meta => { meta.source_binding.source_record_sha256 = 'a'.repeat(64); },
    meta => { meta.source_binding.fingerprint_revision = 999; },
    meta => { delete meta.source_binding.query_binding; },
    meta => { meta.evidence.evidence_level = 'replicated'; },
    meta => { meta.source_refs[0].label = '伪造来源'; },
  ]) {
    const meta = clone(data.meta);
    mutate(meta);
    assert.equal(await validateAnalyzeMetaEnvelope(meta, data.request, webcrypto), false);
  }
});

test('pair mode binds both roles and rejects target-only source citations', async () => {
  const data = await pairFixture();
  assert.equal(await validateAnalyzeMetaEnvelope(data.meta, data.request, webcrypto), true);
  assert.equal(validateAnalyzeReportEnvelope(data.report, data.meta), true);
  const attack = clone(data.report);
  attack.target_domain_intro.corresponding_phenomenon.source_ref_ids = ['kb:target-two'];
  assert.equal(validateAnalyzeReportEnvelope(attack, data.meta), false);
  const swapped = clone(data.meta);
  swapped.source_binding.source_kb_id = 'target-two';
  assert.equal(await validateAnalyzeMetaEnvelope(swapped, data.request, webcrypto), false);
});

test('method candidates are visibly labelled as model proposals without source support', async () => {
  const data = await fixture();
  const targetHtml = renderAnalyzeTargetDomainIntro(data.report.target_domain_intro);
  const insightHtml = renderAnalyzeBorrowableInsights(data.report.borrowable_insights);
  for (const html of [targetHtml, insightHtml]) {
    assert.match(html, /模型提出/);
    assert.match(html, /来源未支持/);
    assert.match(html, /待核查/);
  }
  assert.doesNotMatch(targetHtml, /成熟工具/);
  assert.doesNotMatch(insightHtml, /在源领域中它解决什么/);
});

test('observation prose renders only as an explicitly unverified signal', async () => {
  const data = await fixture();
  const html = renderAnalyzeSharedStructure(data.report.shared_structure);
  assert.match(html, /未验证的输入 \/ 来源线索/);
  assert.match(html, /没有实验或独立复现支持，不能据此判断两边机制相同/);
  assert.doesNotMatch(html, /已观察到的共性/);
});

test('experiment and action rules use only closed bilingual copy', async () => {
  const data = await fixture();
  const english = clone(data.report);
  useEnglishFixedCopy(english);
  assert.equal(validateAnalyzeReportEnvelope(english, data.meta), false);
  const englishMeta = clone(data.meta);
  englishMeta.lang = 'en';
  englishMeta.source_binding.lang = 'en';
  english.source_binding.lang = 'en';
  assert.equal(validateAnalyzeReportEnvelope(english, englishMeta), true);
  assert.equal(validateAnalyzeReportEnvelope(data.report, englishMeta), false);

  for (const mutate of [
    report => { report.how_to_combine.discriminating_experiment.decision_rule += ' '; },
    report => { report.how_to_combine.discriminating_experiment.falsification_rule = 'Never reject.'; },
    report => { report.how_to_combine.discriminating_experiment.stop_rule = 'Continue forever.'; },
    report => { report.how_to_combine.discriminating_experiment.threshold_basis = 'user'; },
    report => { report.action_plan.this_week[0].decision_rule = 'Proceed for every outcome.'; },
    report => { report.action_plan.this_week[0].stop_condition = 'Never stop.'; },
    report => { report.action_plan.this_week[0].threshold_basis = 'source'; },
  ]) {
    const attack = clone(data.report);
    mutate(attack);
    assert.equal(validateAnalyzeReportEnvelope(attack, data.meta), false);
  }

  const experimentHtml = renderAnalyzeHowToCombine(data.report.how_to_combine);
  const actionHtml = renderAnalyzeActionPlan(data.report.action_plan);
  assert.match(experimentHtml, /仅当候选假设在预注册主指标上优于竞争假设时继续/);
  assert.match(experimentHtml, /若最低数据要求、数据质量或安全边界不满足/);
  assert.match(actionHtml, /仅当预注册主指标提供可区分信息时继续/);
  assert.match(actionHtml, /则停止该行动/);
});

test('all model-authored narrative fields share the candidate-state invariant', async () => {
  const data = await fixture();
  const attacks = [
    'The estimated cutoff is 0.7.',
    'The fitted cutoff is 0.7.',
    'The trained cutoff is 0.7.',
    'The mapping attained robust production performance.',
    'Independent replication.',
    '五十次生产运行可靠。',
    'This is a candidate comparison, and the approach attained robust performance in production.',
    'The proposed model was trained on production data and achieved robust performance.',
    'For this candidate, the approach delivered consistent gains in live operations.',
    '候选尚未验证，但该方法在五十次生产运行中表现可靠。',
    'National Foo Institute deploys this method. What evidence should we collect?',
    'This method is used by National Foo Institute. Should we test transfer?',
    'The method is not trivial but has been validated.',
    'National Foo Institute does not hesitate and uses this method.',
    '国家研究所不犹豫并使用该方法。',
    'National Foo Institute does not use this method.',
    '国家研究所没有使用该方法。',
    'Clinicians rely on it.',
    'A 2024 study proposed this method.',
    '张三等提出了该方法。',
    'Smith et al. introduced this method.',
    'The method reduced error by half.',
    'The model outperformed all baselines.',
    'The approach delivered better results.',
    'The method produced a lower error rate.',
    'The intervention improved stability.',
    '该方法将误差降低了一半。',
    '模型优于所有基线。',
    '该方案取得了更好的结果。',
    '干预改善了稳定性。',
  ];
  for (const claim of attacks) {
    const report = clone(data.report);
    report.structural_mapping.rationale = claim;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false, claim);
  }

  const safe = [
    'The cutoff should be estimated from preregistered data.',
    '需要独立复现来核查这个候选。',
    'The proposed model must be trained before its production performance is tested.',
    'For this candidate, test whether the approach could deliver gains in live operations.',
    '对于这个候选，需要测试该方法能否在生产运行中表现可靠。',
    'Has National Foo Institute deployed this method?',
    '国家研究所是否部署了该方法？',
    'The method has not been empirically validated.',
    'No deployment evidence is recorded.',
    '尚无部署证据记录。',
    'No independent replication is recorded.',
    '尚未记录独立复现。',
    'No study has established that this is novel.',
    '没有研究确认该方法新颖。',
    'No tests confirm that the model improves results.',
    'No measurements confirm that the model improves results.',
    'No replications confirm that the model improves results.',
    '没有实验确认模型改善了结果。',
    'It is unknown whether hospitals use this method.',
    '医院是否使用该方法仍未知。',
    'Using a lag model could help compare feedback delay.',
    '使用滞后模型可能帮助比较反馈延迟。',
  ];
  for (const text of safe) {
    const report = clone(data.report);
    report.structural_mapping.rationale = text;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), true, text);
  }
});

test('scope-bound qualifiers do not launder presupposed or coordinated facts', async () => {
  const data = await fixture();
  const attacks = [
    'It is uncertain why hospitals use this method.',
    'It is unknown when clinicians adopted this method.',
    'It is unclear how the method works.',
    'It is unknown why data show improvement.',
    '尚不清楚医院为何使用该方法。',
    '未知医院何时部署了该方法。',
    '不确定该方法为什么有效。',
    'The candidate report notes hospitals use this method.',
    'The hypothesis says Smith et al. introduced this method.',
    'The report may be incomplete but hospitals use this method.',
    'This could be wrong but the method works.',
    '这可能只是候选但医院使用了该方法。',
    'Is it surprising that hospitals use this method?',
    'Was it unexpected that the model outperformed all baselines?',
    'Do we know why clinicians adopted this method?',
    'Can we explain why the method works?',
    'Does the report explain how data show improvement?',
    '是否令人惊讶的是医院使用了该方法？',
    '能否解释为什么该方法有效？',
    'Does it matter that the method works?',
    'Is the fact that hospitals use it relevant?',
    'Hospitals use unknown methods.',
    'Clinicians adopted uncertain workflows.',
    'The method is effective unknown to us.',
    '医院使用未知方法。',
    '医院采用不确定的工作流。',
    'How should we celebrate the fact that hospitals use this method?',
    'How could we explain why the method works?',
    'How should we reward clinicians who adopted this method?',
    'The report may explain why the method works.',
    'A model could show why hospitals use this method.',
    '报告可能解释为什么该方法有效。',
    '模型可能显示医院为何使用该方法。',
    'Check whether the report is complete but hospitals use this method.',
    'Test whether weather matters while clinicians adopt this workflow.',
    '检查天气是否变化但医院使用该方法。',
    'Clinicians are known to use this method.',
    'Hospitals continue to deploy this method.',
    'The source is reported to introduce this workflow.',
    'Researchers were found to adopt this approach.',
    'No deployment evidence is recorded but hospitals use this method.',
    'No independent replication is recorded and the method works.',
    '尚无部署证据记录但医院使用该方法。',
    '尚未记录独立复现但该方法有效。',
    'No evidence shows why hospitals use this method.',
    'Data do not show when clinicians adopted this method.',
    'No evidence shows weather matters because hospitals use this method.',
    '没有证据显示医院为何使用该方法。',
    '没有数据显示医院何时采用该方法。',
  ];
  for (const claim of attacks) {
    const report = clone(data.report);
    report.structural_mapping.rationale = claim;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false, claim);
  }
});

test('ordinary adoption empirical evidence and causal outcomes default to unverified', async () => {
  const data = await fixture();
  const attacks = [
    'Doctors use this method.', 'Engineers deploy this model.',
    'Google adopted this workflow.', 'NASA uses this method.',
    'Users rely on this method.', 'OpenAI developed this method.',
    '医生使用该方法。', '工程师采用了该流程。',
    '用户依赖该方法。', '谷歌开发了该方法。', '政府部署该方法。',
    'The method is widely used.', 'This approach is adopted across teams.',
    'The workflow is used in practice.', '该方法被广泛使用。',
    '该流程在实践中被采用。',
    'The technique works.', 'The tool is effective.',
    'The pipeline improves accuracy.', 'The framework reduced errors.',
    'The policy is reliable.', '该技术有效。', '该工具提高准确率。',
    '该管线降低了误差。', '该框架可靠。', '该策略成功。', '该政策有效。',
    'The architecture causes failure.', 'The protocol drives instability.',
    'The queue explains the pattern.', 'The design prevents errors.',
    '架构导致失败。', '协议驱动不稳定。',
    '延迟解释波动。', '队列解释了该模式。', '设计防止错误。',
    'Telemetry shows improvement.', 'Logs confirm reliability.',
    'A survey found higher accuracy.', 'Observations indicate success.',
    '日志确认可靠性。', '调查发现准确率更高。', '观察表明成功。',
    'An arXiv preprint proposed this method.', 'A patent describes this workflow.',
    'Documentation introduces the algorithm.', 'A textbook describes this approach.',
    '预印本提出了该方法。', '某专利描述了该流程。',
    '文档介绍了该算法。', '教科书描述了该方案。',
  ];
  for (const claim of attacks) {
    const report = clone(data.report);
    report.structural_mapping.rationale = claim;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false, claim);
  }
});

test('typed paths preserve only bound uncertainty and genuine action commands', async () => {
  const data = await fixture();
  for (const question of [
    'When did the model outperform all baselines?',
    'Which source introduced this workflow?',
    'Why did hospitals adopt this method?',
    'How did data show improvement?',
    '哪些来源提出了该方法？',
  ]) {
    const report = clone(data.report);
    report.research_directions.search_questions[0] = question;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false, question);
  }
  const pathAttacks = [
    report => { report.how_to_combine.steps[0] = 'The method works.'; },
    report => {
      report.how_to_combine.discriminating_experiment.procedure[0] =
        'The method is effective.';
    },
    report => {
      report.how_to_combine.discriminating_experiment.intervention_or_measurement =
        'The model outperformed all baselines.';
    },
    report => { report.borrowable_insights[0].failure_signal = 'The method works.'; },
  ];
  for (const attack of pathAttacks) {
    const report = clone(data.report);
    attack(report);
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false);
  }
  for (const safe of [
    'Do hospitals use this method?', 'Can the method work?', '该方法是否有效？',
    'How should we test whether the method works?',
    '如何测试该方法是否有效？',
    'How could we check whether hospitals use this method?',
    'Check whether hospitals use this method.', '检查医院是否使用该方法。',
    'The procedure is designed to test whether the method works.',
    'There is no evidence that hospitals use this method.',
    '没有证据表明医院使用该方法。',
    'The technique may work.', '该技术可能有效。',
    'The architecture may cause failure.', '架构可能导致失败。',
    'Telemetry may show improvement.', '日志可能显示改善。',
    '可以考虑使用该方法进行候选比较。',
    '先固定比较方案，避免后续解释口径漂移。',
  ]) {
    const report = clone(data.report);
    report.structural_mapping.rationale = safe;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), true, safe);
  }
  for (const question of ['Do hospitals use this method?', '医院是否使用该方法？']) {
    const report = clone(data.report);
    report.research_directions.search_questions[0] = question;
    assert.equal(validateAnalyzeReportEnvelope(report, data.meta), true, question);
  }
  const imperative = clone(data.report);
  imperative.how_to_combine.steps[0] = 'Use this method only as a candidate comparison.';
  assert.equal(validateAnalyzeReportEnvelope(imperative, data.meta), true);
  const failureSignal = clone(data.report);
  failureSignal.borrowable_insights[0].failure_signal =
    'Stop if the candidate does not improve the held-out outcome.';
  assert.equal(validateAnalyzeReportEnvelope(failureSignal, data.meta), true);
});

test('proposal fields reject asserted source facts without rejecting generic use wording', async () => {
  const data = await fixture();
  for (const attribution of [
    'The source record uses this method across hospitals.',
    'The source introduced this workflow.',
    'The source did not introduce this workflow.',
    'According to the source, this method is standard practice.',
    '来源记录使用该方法。',
    '来源提出了这个工作流。',
    '该来源没有提出这个工作流。',
    '该来源将其应用于医院。',
  ]) {
    for (const field of ['why_considered', 'evidence_required']) {
      const report = clone(data.report);
      report.target_domain_intro.candidate_methods[0][field] = attribution;
      assert.equal(validateAnalyzeReportEnvelope(report, data.meta), false, attribution);
    }
  }
  for (const safe of [
    'Using a lag model could help compare feedback delay.',
    '使用滞后模型可能帮助比较反馈延迟。',
  ]) {
    const method = clone(data.report);
    method.target_domain_intro.candidate_methods[0].why_considered = safe;
    assert.equal(validateAnalyzeReportEnvelope(method, data.meta), true, safe);
    const insight = clone(data.report);
    insight.borrowable_insights[0].why_considered = safe;
    assert.equal(validateAnalyzeReportEnvelope(insight, data.meta), true, safe);
  }
});

test('renderers expose the complete discriminating experiment and exact enum severity', async () => {
  const data = await fixture();
  const experimentHtml = renderAnalyzeHowToCombine(data.report.how_to_combine);
  for (const expected of [
    '候选假设', '竞争假设', '干预或测量', '处理组的波动幅度下降。',
    '两组变化没有稳定差异。', '候选', '竞争', '混杂因素', '最低数据要求',
    '实验步骤', '阈值依据：提案 · 必须校准后使用',
  ]) assert.match(experimentHtml, new RegExp(expected));

  const mapping = clone(data.report.structural_mapping);
  mapping.competing_explanations = ['<img src=x onerror=alert(1)>'];
  const mappingHtml = renderAnalyzeStructuralMapping(mapping);
  assert.match(mappingHtml, /竞争解释/);
  assert.match(mappingHtml, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(mappingHtml, /<img/);

  const riskHtml = renderAnalyzeRisksAndLimits(data.report.risks_and_limits);
  assert.match(riskHtml, /risk__severity--high/);
  assert.match(riskHtml, />高<\/span>/);
  const actionHtml = renderAnalyzeActionPlan(data.report.action_plan);
  assert.equal((actionHtml.match(/提案 · 必须校准后使用/g) || []).length, 2);

  const researchHtml = renderAnalyzeResearchDirections(data.report.research_directions);
  assert.equal((researchHtml.match(/未执行外部文献检索/g) || []).length, 1);
  assert.doesNotMatch(researchHtml, /文献状态\s*·/);
});

test('decision brief uses current PriorityAction fields without title-as-hypothesis fallback', async () => {
  const data = await fixture();
  window._finalReport = data.report;
  window._analyzeMeta = data.meta;
  window._persistedReport = data.persisted;
  const model = buildDecisionBriefModel();
  const first = data.report.action_plan.this_week[0];
  assert.equal(model.hypothesis, first.how);
  assert.equal(model.metric, first.primary_metric);
  assert.notEqual(model.hypothesis, first.title);
  const markdown = decisionBriefMarkdown(model);
  assert.match(markdown, new RegExp(first.primary_metric));
  assert.match(markdown, new RegExp(first.how));
});

test('handoff context preserves fingerprint and candidate origin without putting query in href', () => {
  const fingerprint = {source_query: 'private question', summary: 'private confirmed summary'};
  const context = createAnalyzeRequestContext({
    bId: 'source-one', aId: null, query: 'private question', fingerprint,
    originDiscoveryId: 'discovery-0123456789abcdef',
    originContractVersion: 'discovery-candidate-v2',
  });
  assert.deepEqual(context.fingerprint, fingerprint);
  assert.equal(context.originDiscoveryId, 'discovery-0123456789abcdef');
  assert.equal(context.originContractVersion, 'discovery-candidate-v2');
  assert.equal(Object.prototype.hasOwnProperty.call(context, 'href'), false);
});

test('share copies only a validated persisted capability URL', async () => {
  const writes = [];
  const toasts = [];
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(global, 'navigator');
  Object.defineProperty(global, 'navigator', {
    value: {clipboard: {async writeText(value) { writes.push(value); }}},
    configurable: true,
  });
  try {
    window.showToast = value => toasts.push(value);
    window._persistedReport = null;
    assert.equal(await sharePersistedAnalyzeReport(), false);
    assert.deepEqual(writes, []);
    assert.match(toasts.at(-1), /尚未保存/);

    window._persistedReport = {share_url: 'http://localhost/report/share/' + '3'.repeat(32)};
    assert.equal(await sharePersistedAnalyzeReport(), true);
    assert.deepEqual(writes, ['http://localhost/report/share/' + '3'.repeat(32)]);

    window._persistedReport = {share_url: 'https://attacker.invalid/report/share/' + '3'.repeat(32)};
    assert.equal(await sharePersistedAnalyzeReport(), false);
    assert.equal(writes.length, 1);
  } finally {
    if (navigatorDescriptor) {
      Object.defineProperty(global, 'navigator', navigatorDescriptor);
    } else {
      delete global.navigator;
    }
  }
});

test('loading UI states atomic publication honestly and has no section timing theater', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'assets', 'js', 'analyze.js'), 'utf8');
  const html = fs.readFileSync(path.join(__dirname, '..', '..', 'frontend', 'analyze.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '..', 'assets', 'css', 'analyze.css'), 'utf8');
  assert.doesNotMatch(source, /SECTION_ETA|setStreamingSection|window\.scrollTo/);
  assert.equal((source.match(/page\.analyze\.timer_typical/g) || []).length, 1);
  assert.match(source, /正在生成候选研究报告/);
  assert.match(source, /正在进行完整性与来源校验/);
  assert.match(html, /完成证据与来源校验后一次呈现/);
  assert.match(html, /id="analyze-report-stage"[\s\S]*aria-busy="true"/);
  assert.match(css, /\.analyze-report-stage[\s\S]*min-height: 29rem/);
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*min-height: 43rem/);
  assert.match(source, /setAnalyzeReportStageState\('ready'\);\s*if \(loading\) loading\.remove\(\)/);
  assert.doesNotMatch(html, /分段逐步出现/);
});

test('report stage exposes loading, error, and validated states accessibly', () => {
  const classes = new Set();
  const stage = {
    dataset: {},
    classList: {
      toggle(name, active) { active ? classes.add(name) : classes.delete(name); },
    },
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
  const loading = {
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
  const original = document.getElementById;
  document.getElementById = id => id === 'analyze-report-stage' ? stage : loading;
  try {
    setAnalyzeReportStageState('loading');
    assert.equal(stage.attributes['aria-busy'], 'true');
    assert.equal(loading.attributes.role, 'status');
    assert.equal(classes.has('analyze-report-stage--ready'), false);
    setAnalyzeReportStageState('error');
    assert.equal(stage.attributes['aria-busy'], 'false');
    assert.equal(loading.attributes.role, 'alert');
    assert.equal(loading.attributes['aria-live'], 'assertive');
    setAnalyzeReportStageState('ready');
    assert.equal(stage.dataset.state, 'ready');
    assert.equal(classes.has('analyze-report-stage--ready'), true);
  } finally {
    document.getElementById = original;
  }
});

test('normal persisted stream validates before returning a displayable report', async () => {
  const data = await fixture();
  const state = createAnalyzeTrustState(data.request, webcrypto);
  window._finalReport = null;
  await ingestThroughSections(state, data);
  assert.equal(window._finalReport, null);
  await state.ingest('persisted', clone(data.persisted));
  const result = await state.ingest('done', clone(data.done));
  assert.deepEqual(result.report, data.report);
  assert.deepEqual(result.persisted, data.persisted);
});

test('missing and out-of-order sections are rejected', async () => {
  const missingData = await fixture({persist: 0});
  const missing = createAnalyzeTrustState(missingData.request, webcrypto);
  await ingestThroughSections(missing, missingData, 8);
  await assert.rejects(missing.ingest('done', clone(missingData.done)), /done event/);

  const outOfOrderData = await fixture({persist: 0});
  const outOfOrder = createAnalyzeTrustState(outOfOrderData.request, webcrypto);
  await outOfOrder.ingest('meta', clone(outOfOrderData.meta));
  await outOfOrder.ingest('report_validated', clone(outOfOrderData.receipt));
  await assert.rejects(outOfOrder.ingest('section', {
    key: 'action_plan', data: clone(outOfOrderData.report.action_plan),
  }), /out of order/);
});

test('hash mismatch and unavailable WebCrypto fail closed', async () => {
  const data = await fixture({persist: 0});
  data.receipt.report_sha256 = 'c'.repeat(64);
  data.done.report_sha256 = data.receipt.report_sha256;
  const state = createAnalyzeTrustState(data.request, webcrypto);
  await ingestThroughSections(state, data);
  await assert.rejects(state.ingest('done', clone(data.done)), /hash mismatch/);
  await assert.rejects(sha256CanonicalAnalyzeJson(data.report, {}), /WebCrypto/);
  const noCrypto = createAnalyzeTrustState(data.request, {});
  await assert.rejects(noCrypto.ingest('meta', clone(data.meta)), /WebCrypto/);
});

test('duplicate meta, persisted, and done terminal events are rejected', async () => {
  const metaData = await fixture({persist: 0});
  const duplicateMeta = createAnalyzeTrustState(metaData.request, webcrypto);
  await duplicateMeta.ingest('meta', clone(metaData.meta));
  await assert.rejects(duplicateMeta.ingest('meta', clone(metaData.meta)), /duplicated/);

  const persistData = await fixture();
  const duplicatePersisted = createAnalyzeTrustState(persistData.request, webcrypto);
  await ingestThroughSections(duplicatePersisted, persistData);
  await duplicatePersisted.ingest('persisted', clone(persistData.persisted));
  await assert.rejects(
    duplicatePersisted.ingest('persisted', clone(persistData.persisted)), /duplicated/
  );

  const doneData = await fixture({persist: 0});
  const duplicateDone = createAnalyzeTrustState(doneData.request, webcrypto);
  await ingestThroughSections(duplicateDone, doneData);
  await duplicateDone.ingest('done', clone(doneData.done));
  await assert.rejects(duplicateDone.ingest('done', clone(doneData.done)), /duplicated/);
});

test('persisted event rejects capability substitution and wrong request mode', async () => {
  const data = await fixture();
  const unsafe = createAnalyzeTrustState(data.request, webcrypto);
  await ingestThroughSections(unsafe, data);
  const payload = clone(data.persisted);
  payload.share_url = 'https://attacker.invalid/report/share/' + '3'.repeat(32);
  await assert.rejects(unsafe.ingest('persisted', payload), /persisted event/);

  const privateData = await fixture({persist: 0});
  const privateState = createAnalyzeTrustState(privateData.request, webcrypto);
  await ingestThroughSections(privateState, privateData);
  await assert.rejects(
    privateState.ingest('persisted', clone(data.persisted)), /persisted event/
  );
});

test('render exception clears all trusted globals before any report is retained', async () => {
  const data = await fixture();
  window._analyzeMeta = data.meta;
  assert.throws(() => commitAnalyzeReportForDisplay(
    data.report, data.persisted, () => { throw new Error('renderer failed'); }
  ), /renderer failed/);
  assert.equal(window._finalReport, null);
  assert.equal(window._persistedReport, null);
  assert.equal(window._analyzeMeta, null);
});
