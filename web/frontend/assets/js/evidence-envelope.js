(function (global) {
  'use strict';

  var LEVELS = ['candidate', 'source_backed', 'analysis_recorded', 'falsification_tested', 'externally_reviewed', 'replicated'];
  var PROVENANCE = [
    'NOT_TESTED', 'INTERNAL_AI_SCREEN', 'HUMAN_ANNOTATION', 'SYNTHETIC_CONTROL',
    'INTERNAL_REAL_DATA', 'USER_RECORDED_OUTCOME', 'EXTERNAL_REVIEW', 'INDEPENDENT_REPLICATION'
  ];
  var VERDICTS = ['PASS', 'FAIL', 'REJECT', 'NULL', 'PARTIAL', 'INCONCLUSIVE', 'NOT_TESTED'];
  var COUNTEREXAMPLE_STATUSES = ['not_recorded', 'gap_recorded', 'searched', 'found', 'none_found'];
  var FALSIFICATION_COUNTEREXAMPLES = ['searched', 'found', 'none_found'];
  var ANALYSIS_PROVENANCE = ['HUMAN_ANNOTATION', 'SYNTHETIC_CONTROL', 'INTERNAL_REAL_DATA', 'EXTERNAL_REVIEW', 'INDEPENDENT_REPLICATION'];
  var FALSIFICATION_PROVENANCE = ['SYNTHETIC_CONTROL', 'INTERNAL_REAL_DATA', 'EXTERNAL_REVIEW', 'INDEPENDENT_REPLICATION'];
  var COPY = {
    zh: {
      region: '证据状态', candidate: '候选', source: '来源', result: '结果', independence: '独立性',
      counterexamples: '反证', ledger: '账本', missing: '未记录', internal: 'Structural 内部 KB 记录',
      external: '经核查的外部来源', kbLink: '查看 KB 记录', externalLink: '查看外部来源',
      level: '证据等级', candidateLevel: '候选（未升级）', score: '检索相似度', ledgerLink: '查看账本',
      source_backed: '来源可核查', analysis_recorded: '分析已记录', falsification_tested: '已做证伪检验',
      externally_reviewed: '外部复核', replicated: '独立复现',
      PASS: '通过', FAIL: '未通过', REJECT: '拒绝', NULL: '空结果', PARTIAL: '部分成立',
      INCONCLUSIVE: '证据不足', NOT_TESTED_VERDICT: '尚未测试',
      NOT_TESTED: '尚未测试', INTERNAL_AI_SCREEN: '内部 AI 筛选', HUMAN_ANNOTATION: '人工标注',
      SYNTHETIC_CONTROL: '合成对照', INTERNAL_REAL_DATA: '内部真实数据分析',
      USER_RECORDED_OUTCOME: '用户结果回填', EXTERNAL_REVIEW: '外部复核', INDEPENDENT_REPLICATION: '独立复现'
    },
    en: {
      region: 'Evidence status', candidate: 'Candidate', source: 'Source', result: 'Result', independence: 'Independence',
      counterexamples: 'Counterexamples', ledger: 'Ledger', missing: 'Not recorded', internal: 'Structural internal KB record',
      external: 'Reviewed external source', kbLink: 'View KB record', externalLink: 'View external source',
      level: 'Evidence level', candidateLevel: 'Candidate (not promoted)', score: 'Retrieval similarity', ledgerLink: 'View ledger',
      source_backed: 'Source backed', analysis_recorded: 'Analysis recorded', falsification_tested: 'Falsification tested',
      externally_reviewed: 'Externally reviewed', replicated: 'Independently replicated',
      PASS: 'Pass', FAIL: 'Fail', REJECT: 'Rejected', NULL: 'Null result', PARTIAL: 'Partial',
      INCONCLUSIVE: 'Inconclusive', NOT_TESTED_VERDICT: 'Not tested',
      NOT_TESTED: 'Not tested', INTERNAL_AI_SCREEN: 'Internal AI screen', HUMAN_ANNOTATION: 'Human annotation',
      SYNTHETIC_CONTROL: 'Synthetic control', INTERNAL_REAL_DATA: 'Internal real-data analysis',
      USER_RECORDED_OUTCOME: 'User-recorded outcome', EXTERNAL_REVIEW: 'External review', INDEPENDENT_REPLICATION: 'Independent replication'
    }
  };

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
    });
  }

  function language() {
    try {
      if (global.i18n && global.i18n.getLang) return global.i18n.getLang() === 'en' ? 'en' : 'zh';
      return document.documentElement.lang.indexOf('en') === 0 ? 'en' : 'zh';
    } catch (_error) { return 'zh'; }
  }

  function object(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  function text(value) { return typeof value === 'string' && value.trim() ? value.trim() : ''; }

  function validDate(value) {
    var raw = text(value);
    var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
    if (!match) return false;
    var stamp = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    var parsed = new Date(stamp);
    return parsed.getUTCFullYear() === Number(match[1]) && parsed.getUTCMonth() === Number(match[2]) - 1 &&
      parsed.getUTCDate() === Number(match[3]) && stamp <= Date.now();
  }

  function validHttpsUrl(value) {
    try {
      var parsed = new URL(text(value));
      return parsed.protocol === 'https:' && !!parsed.hostname && !parsed.username && !parsed.password;
    } catch (_error) { return false; }
  }

  function validLedger(value) {
    var row = object(value);
    return row.status === 'bound' && text(row.claim_id) && text(row.version) && validDate(row.recorded_at) &&
      /^[0-9a-f]{64}$/i.test(text(row.artifact_sha256)) && (!text(row.url) || validHttpsUrl(row.url));
  }

  function validExternalSource(source) {
    try {
      var review = object(source.source_review);
      return validHttpsUrl(source.url) && !!text(review.reviewer) && validDate(review.reviewed_at);
    } catch (_error) { return false; }
  }

  function normalize(raw) {
    var value = object(raw);
    var candidate = object(value.candidate);
    var source = object(value.source);
    var result = object(value.result);
    var independence = object(value.independence);
    var counterexamples = object(value.counterexamples);
    var ledger = object(value.ledger);
    var requested = LEVELS.indexOf(value.evidence_level) >= 0 ? value.evidence_level : 'candidate';
    var bound = validLedger(ledger);
    var provenance = PROVENANCE.indexOf(result.provenance) >= 0 ? result.provenance : 'NOT_TESTED';
    var verdict = VERDICTS.indexOf(result.verdict) >= 0 ? result.verdict : 'INCONCLUSIVE';
    var independenceKind = ['not_recorded', 'internal', 'human_annotation', 'external_review', 'independent_team'].indexOf(independence.kind) >= 0 ? independence.kind : 'not_recorded';
    var counterexampleStatus = COUNTEREXAMPLE_STATUSES.indexOf(counterexamples.status) >= 0 ? counterexamples.status : 'not_recorded';
    var sourceKind = ['internal_kb', 'external_source'].indexOf(source.kind) >= 0 ? source.kind : 'not_recorded';
    if (sourceKind === 'external_source' && !validExternalSource(source)) sourceKind = 'not_recorded';
    // Keep runtime parity with the backend strict-promotion quarantine. A
    // syntactically valid URL/hash is not an auditable source or artifact.
    // Promotion resumes only after a content-bound manifest is implemented.
    var promoted = false;
    if (requested !== 'candidate') promoted = promoted && sourceKind === 'external_source';
    if (['analysis_recorded', 'falsification_tested', 'externally_reviewed', 'replicated'].indexOf(requested) >= 0) promoted = promoted && ANALYSIS_PROVENANCE.indexOf(provenance) >= 0;
    if (['falsification_tested', 'externally_reviewed', 'replicated'].indexOf(requested) >= 0) promoted = promoted && FALSIFICATION_PROVENANCE.indexOf(provenance) >= 0 && ['NOT_TESTED', 'INCONCLUSIVE'].indexOf(verdict) < 0 && FALSIFICATION_COUNTEREXAMPLES.indexOf(counterexampleStatus) >= 0;
    if (['externally_reviewed', 'replicated'].indexOf(requested) >= 0) promoted = promoted && ['EXTERNAL_REVIEW', 'INDEPENDENT_REPLICATION'].indexOf(provenance) >= 0 && ['external_review', 'independent_team'].indexOf(independenceKind) >= 0;
    if (requested === 'replicated') promoted = promoted && provenance === 'INDEPENDENT_REPLICATION' && independenceKind === 'independent_team';
    return {
      schema_version: 'evidence-envelope-v1',
      evidence_level: requested === 'candidate' || promoted ? requested : 'candidate',
      candidate: { status: 'recorded', kind: text(candidate.kind) || 'unspecified_candidate', label: text(candidate.label), score: Number.isFinite(candidate.score) ? Math.max(0, Math.min(1, candidate.score)) : null },
      source: { status: sourceKind === 'not_recorded' ? 'not_recorded' : 'recorded', kind: sourceKind, label: text(source.label), url: sourceKind === 'external_source' ? text(source.url) : '', source_review: object(source.source_review) },
      result: { status: provenance === 'NOT_TESTED' ? 'not_recorded' : 'recorded', provenance: provenance, verdict: verdict, summary: text(result.summary) },
      independence: { status: independenceKind === 'not_recorded' ? 'not_recorded' : 'recorded', kind: independenceKind, summary: text(independence.summary) },
      counterexamples: { status: counterexampleStatus, summary: text(counterexamples.summary) },
      ledger: bound ? ledger : { status: 'not_recorded', claim_id: '', version: '', recorded_at: '', artifact_sha256: '', url: '' }
    };
  }

  function fallback(candidate) {
    return normalize({
      evidence_level: 'candidate',
      candidate: { kind: 'retrieval_candidate', label: candidate && candidate.name, score: candidate && candidate.score },
      source: { kind: 'internal_kb', label: 'Structural KB record' },
      result: { provenance: 'NOT_TESTED', verdict: 'NOT_TESTED' },
      independence: { status: 'not_recorded', kind: 'not_recorded' },
      counterexamples: { status: 'not_recorded' }, ledger: { status: 'not_recorded' }
    });
  }

  var i18nWired = false;
  function wireI18n() {
    if (i18nWired || !global.i18n || typeof global.i18n.onChange !== 'function') return;
    i18nWired = true;
    global.i18n.onChange(function () {
      var nodes = document.querySelectorAll('.evidence-envelope[data-evidence-json]');
      Array.prototype.forEach.call(nodes, function (node) {
        try {
          var payload = JSON.parse(decodeURIComponent(node.getAttribute('data-evidence-json') || ''));
          var options = JSON.parse(decodeURIComponent(node.getAttribute('data-evidence-options') || '%7B%7D'));
          node.outerHTML = render(payload, options);
        } catch (_error) { /* malformed DOM state stays visibly unchanged */ }
      });
    });
  }

  function render(raw, options) {
    wireI18n();
    var e = normalize(raw);
    var opts = object(options);
    var lang = language();
    var c = COPY[lang];
    var missing = '<span class="evidence-envelope__missing">' + c.missing + '</span>';
    var candidateText = e.candidate.label || e.candidate.kind;
    if (e.candidate.score !== null) candidateText += ' · ' + c.score + ' ' + Math.round(e.candidate.score * 100) + '%';
    var sourceText = missing;
    if (e.source.kind === 'internal_kb') sourceText = esc(e.source.label || c.internal);
    if (e.source.kind === 'external_source') sourceText = esc(e.source.label || c.external) + ' · ' + esc(e.source.source_review.reviewer) + ' · ' + esc(e.source.source_review.reviewed_at);
    var verdictCopy = e.result.verdict === 'NOT_TESTED' ? c.NOT_TESTED_VERDICT : c[e.result.verdict];
    var resultText = e.result.provenance === 'NOT_TESTED' ? missing : esc(c[e.result.provenance]) + ' · ' + esc(verdictCopy) + (e.result.summary ? ' · ' + esc(e.result.summary) : '');
    var independentText = e.independence.status === 'not_recorded' ? missing : esc(e.independence.summary || e.independence.kind);
    var counterText = e.counterexamples.status === 'not_recorded' ? missing : esc(e.counterexamples.summary || e.counterexamples.status);
    var ledgerText = e.ledger.status === 'bound' ? esc(e.ledger.claim_id + ' · ' + e.ledger.version + ' · ' + e.ledger.recorded_at) : missing;
    var sourceAction = '';
    var ledgerAction = '';
    if (!opts.suppressActions) {
      if (opts.kbUrl) sourceAction += '<a class="evidence-envelope__link" href="' + esc(opts.kbUrl) + '">' + c.kbLink + '</a>';
      if (e.source.kind === 'external_source' && e.source.url) sourceAction += '<a class="evidence-envelope__link" href="' + esc(e.source.url) + '" target="_blank" rel="noopener noreferrer">' + c.externalLink + '</a>';
      if (e.ledger.status === 'bound' && e.ledger.url) ledgerAction = '<a class="evidence-envelope__link" href="' + esc(e.ledger.url) + '" target="_blank" rel="noopener noreferrer">' + c.ledgerLink + '</a>';
    }
    var stateJson = encodeURIComponent(JSON.stringify(e));
    var optionJson = encodeURIComponent(JSON.stringify({ compact: !!opts.compact, suppressActions: !!opts.suppressActions, kbUrl: text(opts.kbUrl) }));
    return '<section class="evidence-envelope' + (opts.compact ? ' evidence-envelope--compact' : '') + '" aria-label="' + c.region + '" data-evidence-json="' + stateJson + '" data-evidence-options="' + optionJson + '">' +
      '<div class="evidence-envelope__level"><span>' + c.level + '</span><strong>' + (e.evidence_level === 'candidate' ? c.candidateLevel : esc(c[e.evidence_level])) + '</strong></div>' +
      '<dl class="evidence-envelope__grid">' +
      '<div><dt>' + c.candidate + '</dt><dd>' + esc(candidateText) + '</dd></div>' +
      '<div><dt>' + c.source + '</dt><dd>' + sourceText + sourceAction + '</dd></div>' +
      '<div><dt>' + c.result + '</dt><dd>' + resultText + '</dd></div>' +
      '<div><dt>' + c.independence + '</dt><dd>' + independentText + '</dd></div>' +
      '<div><dt>' + c.counterexamples + '</dt><dd>' + counterText + '</dd></div>' +
      '<div><dt>' + c.ledger + '</dt><dd>' + ledgerText + ledgerAction + '</dd></div>' +
      '</dl></section>';
  }

  global.StructuralEvidence = { LEVELS: LEVELS.slice(), PROVENANCE: PROVENANCE.slice(), normalize: normalize, fallback: fallback, render: render };
}(window));
