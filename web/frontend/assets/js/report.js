/**
 * Structural — Persisted Report Viewer (M1.4 PR #5).
 *
 * Reads the URL (either /report/share/<token> or /report/<id>), fetches
 * the corresponding /api/report/share/<token> or /api/report/<id>, and
 * renders the 9-section payload.
 *
 * Reuses analyze.js's window._m14_renderShareBar / window._m14_submitFeedback
 * for the share-bar + feedback wiring so we don't duplicate that logic.
 */
(function () {
  'use strict';

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }

  // Defensive fallback renderer — only used if analyze.js's renderers are
  // unavailable for some reason. Renders human-readable text, never raw
  // English field-name key dumps.
  function renderValueFallback(v) {
    if (v == null) return '';
    if (typeof v === 'string') return '<p>' + escapeHtml(v) + '</p>';
    if (typeof v === 'number' || typeof v === 'boolean') return '<p>' + escapeHtml(String(v)) + '</p>';
    if (Array.isArray(v)) {
      if (v.length === 0) return '';
      const items = v.map((item) => '<li>' + (typeof item === 'string'
        ? escapeHtml(item) : renderValueFallback(item)) + '</li>').join('');
      return '<ul>' + items + '</ul>';
    }
    if (typeof v === 'object') {
      // Render nested objects as readable paragraphs, dropping the raw key.
      return Object.values(v).map(renderValueFallback).join('');
    }
    return '<p>' + escapeHtml(String(v)) + '</p>';
  }

  function persistedTargetContext(detail) {
    const report = detail && detail.payload;
    const binding = report && report.source_binding;
    const queryMode = !binding || binding.target_kind === 'query';
    if (queryMode) {
      return {
        isQueryMode: true,
        label: (detail && detail.query) || '',
        target: {
          original_query: (detail && detail.query) || '',
          description: (detail && detail.query) || '',
        },
      };
    }
    const refs = Array.isArray(report.source_refs) ? report.source_refs : [];
    const targetRef = refs.find(item => item.record_id === binding.target_kb_id);
    const label = targetRef ? targetRef.label : String(detail.b_id || '');
    return {
      isQueryMode: false,
      label,
      target: {
        id: detail.b_id,
        name: label,
        description: label,
      },
    };
  }

  /**
   * Render the 9-section report into #analyze-sections.
   *
   * P0-1 (SESSION-17): reuse analyze.js's `renderFinalReport`, which drives
   * the same per-section `renderers` the live /analyze page uses. This makes
   * a shared/saved report look identical to a freshly-generated one — proper
   * Chinese headings, structured cards, KaTeX formulas — instead of the old
   * raw key-value dump that exposed `if_time_short` / `this_week` etc.
   */
  function renderReport(payload, container, detail) {
    // Expose the payload + meta the way analyze.js expects so its renderers
    // and any i18n re-render path can read them.
    window._finalReport = payload || {};

    // SESSION-17 V4: persisted reports do NOT carry `meta.credibility`
    // (the report detail API only returns the 9-section `payload`). We still
    // expose a meta object so the core insight card can render, but with
    // `credibility: null` — renderCredibilityBadge() then honestly omits the
    // badge rather than inventing numbers.
    const targetContext = persistedTargetContext(detail);
    window._analyzeMeta = {
      credibility: (detail && detail.credibility) || null,
      evidence: (detail && detail.evidence) || null,
      similarity: (detail && typeof detail.similarity === 'number') ? detail.similarity : undefined,
      a: (detail && detail.source) || {},
      b: targetContext.target,
      is_query_mode: targetContext.isQueryMode,
      fingerprint: (detail && detail.fingerprint) || null,
      model: (detail && detail.model) || '',
      prompt_version: (detail && detail.prompt_version) || '',
    };

    if (typeof window.renderFinalReport === 'function') {
      window.renderFinalReport(payload || {});
    } else {
      // Fallback: should not happen (analyze.js loads before report.js).
      console.warn('[report] renderFinalReport unavailable — using fallback');
      const SECTIONS = [
        { key: 'shared_structure', label: '共享结构' },
        { key: 'your_problem_breakdown', label: '你的问题拆解' },
        { key: 'target_domain_intro', label: '源领域讲解' },
        { key: 'structural_mapping', label: '结构对照' },
        { key: 'borrowable_insights', label: '可借用的工具' },
        { key: 'how_to_combine', label: '怎么结合' },
        { key: 'research_directions', label: '研究方向' },
        { key: 'risks_and_limits', label: '迁移风险' },
        { key: 'action_plan', label: '本周行动' },
      ];
      let html = '';
      for (const s of SECTIONS) {
        if (payload && payload[s.key] !== undefined) {
          const body = renderValueFallback(payload[s.key]);
          if (body) {
            html += '<section class="section" id="section-' + s.key + '">' +
              '<h2 class="section__title">' + escapeHtml(s.label) + '</h2>' +
              '<div class="section__body">' + body + '</div></section>';
          }
        }
      }
      container.innerHTML = html || '<p class="muted">报告内容为空。</p>';
    }
    // Render any inline math the LLM emitted.
    if (typeof window.renderMath === 'function') window.renderMath(container);
  }

  function resetPersistedReportState() {
    window._finalReport = null;
    window._analyzeMeta = null;
    window._persistedReport = null;
    window._decisionBriefContext = null;
    const followup = document.getElementById('report-followup');
    if (followup) followup.remove();
    for (const id of ['report-meta', 'analyze-sections', 'analyze-tldr',
      'decision-brief-root', 'report-origin']) {
      const element = document.getElementById(id);
      if (element) {
        element.replaceChildren();
        if (id === 'report-meta' || id === 'analyze-tldr' || id === 'report-origin') {
          element.hidden = true;
        }
      }
    }
    // Keep the static controls so a successful owner render can reuse them,
    // but erase every capability-derived value and partial render state.
    const shareBar = document.getElementById('analyze-share-bar');
    if (shareBar) shareBar.hidden = true;
    const shareInput = document.getElementById('analyze-share-url');
    if (shareInput) shareInput.value = '';
    const partial = document.getElementById('analyze-share-bar__partial');
    if (partial) partial.hidden = true;
    for (const id of ['analyze-vote-up-count', 'analyze-vote-down-count']) {
      const count = document.getElementById(id);
      if (count) count.textContent = '0';
    }
  }

  function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value) &&
      (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  }

  function hasExactKeys(value, keys) {
    if (!isPlainObject(value)) return false;
    const actual = Object.keys(value).sort();
    const expected = keys.slice().sort();
    return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
  }

  function textOrNull(value, maximum) {
    return value === null || (typeof value === 'string' &&
      Array.from(value).length <= maximum);
  }

  function containsInternalCapability(value) {
    const capability = /\/(?:api\/)?report\/share\/[0-9a-f]{32}(?![0-9a-f])/i;
    const stack = [value];
    let visited = 0;
    while (stack.length) {
      const item = stack.pop();
      visited += 1;
      if (visited > 100000) return true;
      if (typeof item === 'string') {
        let candidate = item.normalize('NFKC');
        for (let round = 0; round < 2; round += 1) {
          if (capability.test(candidate)) return true;
          try { candidate = decodeURIComponent(candidate); } catch (_) { break; }
        }
      }
      if (Array.isArray(item)) stack.push.apply(stack, item);
      else if (isPlainObject(item)) {
        stack.push.apply(stack, Object.keys(item));
        stack.push.apply(stack, Object.values(item));
      }
    }
    return false;
  }

  function boundedSnapshotText(value, maximum, fallback) {
    const raw = value == null ? '' : String(value).trim();
    return Array.from(raw || fallback).slice(0, maximum).join('');
  }

  function validateSourceSnapshot(source, report) {
    if (!hasExactKeys(source, ['id', 'name', 'domain', 'type_id']) ||
        typeof source.id !== 'string' || !source.id ||
        !textOrNull(source.name, 10000) || !textOrNull(source.domain, 10000) ||
        !textOrNull(source.type_id, 10000)) return false;
    const intro = report.target_domain_intro;
    const sourceRefs = report.source_refs.filter(item =>
      item.record_id === report.source_binding.source_kb_id
    );
    const expectedLabel = Array.from(String(source.name || source.id || 'Internal KB record'))
      .slice(0, 240).join('');
    return intro.domain_name === boundedSnapshotText(source.domain, 120, 'Internal source record') &&
      intro.corresponding_phenomenon.name === boundedSnapshotText(
        source.name, 120, 'Internal source record'
      ) && sourceRefs.length === 1 && sourceRefs[0].label === expectedLabel;
  }

  function validateEvidenceEnvelope(value, source, lang) {
    if (!hasExactKeys(value, ['schema_version', 'evidence_level', 'candidate', 'source',
      'result', 'independence', 'counterexamples', 'ledger']) ||
        value.schema_version !== 'evidence-envelope-v1' || value.evidence_level !== 'candidate') {
      return false;
    }
    const candidateLabel = source.name == null || String(source.name).trim() === ''
      ? null : Array.from(String(source.name).trim()).slice(0, 1000).join('');
    const candidate = value.candidate;
    const evidenceSource = value.source;
    const result = value.result;
    const independence = value.independence;
    const counterexamples = value.counterexamples;
    const ledger = value.ledger;
    return hasExactKeys(candidate, ['status', 'kind', 'label', 'score']) &&
      candidate.status === 'recorded' && candidate.kind === 'analysis_candidate' &&
      candidate.label === candidateLabel && candidate.score === null &&
      hasExactKeys(evidenceSource, ['status', 'kind', 'label', 'url', 'source_review']) &&
      evidenceSource.status === 'recorded' && evidenceSource.kind === 'internal_kb' &&
      evidenceSource.label === 'Structural internal KB candidate' &&
      evidenceSource.url === null && evidenceSource.source_review === null &&
      hasExactKeys(result, ['status', 'provenance', 'verdict', 'summary']) &&
      result.status === 'not_recorded' && result.provenance === 'NOT_TESTED' &&
      result.verdict === 'NOT_TESTED' && result.summary === null &&
      hasExactKeys(independence, ['status', 'kind', 'summary']) &&
      independence.status === 'not_recorded' && independence.kind === 'not_recorded' &&
      independence.summary === null &&
      hasExactKeys(counterexamples, ['status', 'summary']) &&
      counterexamples.status === 'gap_recorded' && counterexamples.summary === (lang === 'en'
        ? 'The report must propose falsifiers; no completed falsification result is bound.'
        : '报告必须提出证伪条件；当前未绑定任何已完成的证伪结果。') &&
      hasExactKeys(ledger, ['status', 'claim_id', 'version', 'recorded_at',
        'artifact_sha256', 'url']) && ledger.status === 'not_recorded' &&
      ledger.claim_id === null && ledger.version === null && ledger.recorded_at === null &&
      ledger.artifact_sha256 === null && ledger.url === null;
  }

  function validateOriginCandidate(value, binding) {
    if (!hasExactKeys(value, ['discovery_id', 'contract_version', 'candidate_family_id',
      'tier', 'pair', 'origin_content_id']) ||
        !/^discovery-[0-9a-f]{16}$/.test(value.discovery_id || '') ||
        value.contract_version !== 'discovery-candidate-v2' ||
        !/^(?:anchor|pair)-[0-9a-f]{12}$/.test(value.candidate_family_id || '') ||
        !['priority_review', 'candidate_pool'].includes(value.tier) ||
        !hasExactKeys(value.pair, ['a_id', 'b_id']) ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(value.pair.a_id || '') ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(value.pair.b_id || '') ||
        !/^origin-[0-9a-f]{24}$/.test(value.origin_content_id || '')) return false;
    return binding.target_kind === 'kb' && value.pair.a_id === binding.source_kb_id &&
      value.pair.b_id === binding.target_kb_id;
  }

  async function validatePersistedDetail(data, route) {
    const trust = window.StructuralAnalyzeTrust;
    const report = data && data.payload;
    const required = ['id', 'query', 'b_id', 'lang', 'payload', 'model', 'prompt_version',
      'created_at', 'view_count', 'is_partial', 'source', 'evidence', 'report_sha256',
      'snapshot_status'];
    const optional = ['fingerprint', 'origin_candidate', 'share_url'];
    if (!isPlainObject(data) || Object.keys(data).some(key => !required.concat(optional).includes(key)) ||
        required.some(key => !Object.prototype.hasOwnProperty.call(data, key)) ||
        !route || !hasExactKeys(route, ['kind', 'value']) || !['id', 'share'].includes(route.kind) ||
        (route.kind === 'id' ? !/^r_[0-9a-f]{16}$/.test(route.value || '')
          : !/^[0-9a-f]{32}$/.test(route.value || '')) ||
        !trust || typeof trust.validateAnalyzeReportEnvelope !== 'function' ||
        typeof trust.sha256CanonicalAnalyzeJson !== 'function' || !report ||
        !/^r_[0-9a-f]{16}$/.test(data.id || '') ||
        typeof data.query !== 'string' || Array.from(data.query).length > 8000 ||
        !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(data.b_id || '') ||
        !['zh', 'en'].includes(data.lang) || typeof data.created_at !== 'string' ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(data.created_at) ||
        !Number.isFinite(Date.parse(data.created_at)) ||
        !Number.isSafeInteger(data.view_count) || data.view_count < 0 || data.is_partial !== false ||
        data.prompt_version !== 'deep-report-v2' ||
        !/^[0-9a-f]{64}$/.test(data.report_sha256 || '') ||
        !report.source_binding || data.lang !== report.source_binding.lang ||
        data.model !== report.source_binding.model_id ||
        report.source_binding.prompt_version !== data.prompt_version ||
        !['current_artifact', 'historical_snapshot'].includes(data.snapshot_status)) {
      return false;
    }
    if (route.kind === 'id') {
      if (route.value !== data.id || !/^\/report\/share\/[0-9a-f]{32}$/.test(data.share_url || '')) {
        return false;
      }
    } else if (Object.prototype.hasOwnProperty.call(data, 'share_url')) {
      return false;
    }
    const capabilityProbe = {};
    for (const [key, value] of Object.entries(data)) {
      if (key !== 'share_url') capabilityProbe[key] = value;
    }
    if (containsInternalCapability(capabilityProbe)) return false;
    const expectedMeta = {
      lang: data.lang,
      source_binding: report.source_binding,
      source_refs: report.source_refs,
      report_boundary: report.report_boundary,
    };
    if (!trust.validateAnalyzeReportEnvelope(report, expectedMeta)) return false;
    const binding = report.source_binding;
    if (!validateSourceSnapshot(data.source, report) ||
        binding.source_kb_id !== data.source.id || data.model !== binding.model_id ||
        !validateEvidenceEnvelope(data.evidence, data.source, data.lang)) return false;
    if (binding.target_kind === 'query') {
      if (!data.query || data.b_id !== binding.source_kb_id || binding.target_kb_id !== null ||
          typeof binding.query_binding !== 'string' ||
          Object.prototype.hasOwnProperty.call(data, 'origin_candidate')) return false;
    } else if (data.query !== '' || data.b_id !== binding.target_kb_id ||
        binding.query_binding !== null) return false;
    if (Object.prototype.hasOwnProperty.call(data, 'origin_candidate') &&
        !validateOriginCandidate(data.origin_candidate, binding)) return false;
    try {
      if (await trust.sha256CanonicalAnalyzeJson(report) !== data.report_sha256) {
        return false;
      }
      const hasFingerprint = Object.prototype.hasOwnProperty.call(data, 'fingerprint');
      if (binding.fingerprint_sha256 === null || binding.fingerprint_revision === null) {
        if (hasFingerprint || binding.fingerprint_sha256 !== null ||
            binding.fingerprint_revision !== null) return false;
      } else {
        if (!hasFingerprint || !hasExactKeys(data.fingerprint, ['source_query', 'summary',
          'variables', 'constraints', 'unknowns', 'revision', 'provenance']) ||
            data.fingerprint.source_query !== data.query ||
            typeof data.fingerprint.summary !== 'string' ||
            Array.from(data.fingerprint.summary).length < 8 ||
            Array.from(data.fingerprint.summary).length > 1000 ||
            !Number.isSafeInteger(data.fingerprint.revision) ||
            data.fingerprint.revision < 1 || data.fingerprint.revision > 1000 ||
            data.fingerprint.revision !== binding.fingerprint_revision ||
            data.fingerprint.provenance !== 'user_confirmed' ||
            !Array.isArray(data.fingerprint.variables) ||
            !Array.isArray(data.fingerprint.constraints) ||
            !Array.isArray(data.fingerprint.unknowns) ||
            ['variables', 'constraints', 'unknowns'].some(key =>
              data.fingerprint[key].length > 12 || data.fingerprint[key].some(item =>
                typeof item !== 'string' || !item || Array.from(item).length > 120
              ))) return false;
        const projected = {};
        for (const key of ['summary', 'variables', 'constraints', 'unknowns', 'revision', 'provenance']) {
          projected[key] = data.fingerprint[key];
        }
        if (await trust.sha256CanonicalAnalyzeJson(projected) !== binding.fingerprint_sha256) {
          return false;
        }
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  // === SESSION-17 V6: report → action → outcome follow-up loop ===
  // A quiet panel below the action_plan section. Lets the user record
  // whether they acted on the report and how it went. GETs the existing
  // state on load (back-fill), POSTs on submit.
  const FOLLOWUP_STATUS = [
    { v: 'planned', label: '打算试' },
    { v: 'in_progress', label: '正在做' },
    { v: 'tried', label: '已经试过' },
    { v: 'abandoned', label: '放弃了' },
  ];
  const FOLLOWUP_OUTCOME = [
    { v: 'worked', label: '有效' },
    { v: 'partial', label: '部分有效' },
    { v: 'no_effect', label: '没效果' },
    { v: 'too_early', label: '还太早' },
  ];
  const EXPERIMENT_STATUS = [
    { v: 'planned', label: '待开始' },
    { v: 'in_progress', label: '进行中' },
    { v: 'completed', label: '已完成' },
    { v: 'stopped', label: '已停止' },
    { v: 'abandoned', label: '已放弃' },
  ];
  const EXPERIMENT_TRANSITIONS = {
    planned: ['planned', 'in_progress', 'abandoned'],
    in_progress: ['in_progress', 'completed', 'stopped', 'abandoned'],
    completed: ['completed'], stopped: ['stopped'], abandoned: ['abandoned'],
  };
  const RESULT_OPTIONS = [
    { v: 'success', label: '成功' }, { v: 'partial', label: '部分成功' },
    { v: 'failure', label: '失败' }, { v: 'inconclusive', label: '无法判定' },
  ];
  const DECISION_OPTIONS = [
    { v: 'iterate', label: '迭代' }, { v: 'scale', label: '扩大' },
    { v: 'stop', label: '停止' }, { v: 'retest', label: '重测' },
  ];
  const LOCAL_REMINDER_KEY = 'structural_local_reminders';
  const TERMINAL_EXPERIMENTS = ['completed', 'stopped', 'abandoned'];

  function localRemindersEnabled() {
    try {
      const value = localStorage.getItem(LOCAL_REMINDER_KEY);
      return value === null || value === 'on';
    } catch (e) { return true; }
  }

  function deadlineMessage(experiment) {
    const exp = experiment || {};
    if (TERMINAL_EXPERIMENTS.includes(exp.status)) return '实验已结束，不再提醒。';
    if (!exp.deadline) return '尚未设置截止日期；保存后可在「我的报告」查看提醒。';
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(exp.deadline);
    if (!match) return '截止日期无效，请修正后保存。';
    const deadline = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    const now = new Date();
    const todayDay = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
    const deadlineDay = Date.UTC(deadline.getFullYear(), deadline.getMonth(), deadline.getDate());
    const days = (deadlineDay - todayDay) / 86400000;
    if (days < 0) return `已逾期 ${Math.abs(days)} 天；请更新实验或记录结果。`;
    if (days === 0) return '今天到期；请更新实验或记录结果。';
    if (days <= 3) return `${days} 天后到期。`;
    return `截止 ${exp.deadline}。`;
  }

  function anonHeaders() {
    let anonId = '';
    try { anonId = localStorage.getItem('anonId') || ''; } catch (e) {}
    return anonId ? { 'X-Anon-Id': anonId } : {};
  }

  // followupState holds the last-known/server state; null = nothing recorded.
  function renderFollowup(reportId, followupState) {
    // Anchor the panel right after the action_plan section.
    const anchor = document.getElementById('section-action_plan');
    if (!anchor) return;
    let panel = document.getElementById('report-followup');
    if (!panel) {
      panel = document.createElement('section');
      panel.id = 'report-followup';
      panel.className = 'report-followup';
      anchor.insertAdjacentElement('afterend', panel);
    }

    const st = followupState || {};
    const curStatus = st.action_status || '';
    const curOutcome = st.outcome || '';
    const curNote = st.note || '';
    const exp = st.experiment || {};
    const detail = st.outcome_detail || {};
    const publishToInsights = st.publish_to_insights === true;
    const expStatus = exp.status || 'planned';
    const allowedStatuses = EXPERIMENT_TRANSITIONS[expStatus] || [expStatus];
    const chip = (group, opt, selected) => `
      <button type="button" class="rf-chip${selected ? ' rf-chip--on' : ''}"
              data-group="${group}" data-value="${opt.v}" aria-pressed="${selected ? 'true' : 'false'}">${escapeHtml(opt.label)}</button>`;

    panel.innerHTML = `
      <div class="report-followup__head">
        <h3 class="report-followup__title">验证这次迁移</h3>
        <p class="report-followup__sub">把建议变成一个可检验的最小实验，并记录真实结果。默认只保存在这份报告中。</p>
      </div>
      <div class="report-reminder" id="report-reminder">
        <span id="report-reminder-message">${escapeHtml(deadlineMessage(exp))}</span>
        <label><input type="checkbox" id="report-reminder-toggle" ${localRemindersEnabled() ? 'checked' : ''}> 本地提醒</label>
        <small>仅在这台设备打开 Structural 时提示，不发送邮件或系统通知。</small>
      </div>
      ${st.action_status ? `<div class="report-followup__saved" id="rf-saved-hint">上次记录：${escapeHtml((FOLLOWUP_STATUS.find(x => x.v === curStatus) || {}).label || curStatus)}${curOutcome ? ' · ' + escapeHtml((FOLLOWUP_OUTCOME.find(x => x.v === curOutcome) || {}).label || curOutcome) : ''}</div>` : ''}
      <fieldset class="report-experiment">
        <legend>最小实验</legend>
        <div class="report-form-grid">
          <label class="report-form-field report-form-field--wide"><span>假设 <b aria-hidden="true">*</b></span><textarea id="rf-hypothesis" maxlength="2000" rows="2" placeholder="如果采用这个迁移方法，那么……">${escapeHtml(exp.hypothesis || '')}</textarea></label>
          <label class="report-form-field"><span>负责人</span><input id="rf-owner" maxlength="120" value="${escapeHtml(exp.owner || '')}" placeholder="姓名或角色"></label>
          <label class="report-form-field"><span>截止日期</span><input id="rf-deadline" type="date" value="${escapeHtml(exp.deadline || '')}"></label>
          <label class="report-form-field"><span>基线值</span><input id="rf-baseline" type="number" step="any" inputmode="decimal" value="${exp.baseline == null ? '' : escapeHtml(exp.baseline)}" placeholder="例如 0.31"></label>
          <label class="report-form-field"><span>核心指标</span><input id="rf-metric" maxlength="200" value="${escapeHtml(exp.primary_metric || '')}" placeholder="例如完成率"></label>
          <label class="report-form-field"><span>成功阈值</span><input id="rf-threshold" type="number" step="any" inputmode="decimal" value="${exp.success_threshold == null ? '' : escapeHtml(exp.success_threshold)}" placeholder="例如 0.40"></label>
          <label class="report-form-field"><span>停止条件</span><input id="rf-stop" maxlength="1000" value="${escapeHtml(exp.stop_condition || '')}" placeholder="例如达到 1000 次曝光"></label>
          <label class="report-form-field report-form-field--wide"><span>实验备注</span><textarea id="rf-exp-notes" maxlength="4000" rows="2" placeholder="分组、样本或其他约束">${escapeHtml(exp.notes || '')}</textarea></label>
        </div>
        <div class="report-followup__field">
          <span class="report-followup__label" id="rf-exp-status-label">实验状态</span>
          <div class="rf-chips" id="rf-exp-status" role="group" aria-labelledby="rf-exp-status-label">
            ${EXPERIMENT_STATUS.filter(o => allowedStatuses.includes(o.v)).map(o => chip('experiment-status', o, o.v === expStatus)).join('')}
          </div>
          ${['completed', 'stopped', 'abandoned'].includes(expStatus) ? '<p class="report-form-hint">终态保存后不可退回，确保结果已核实。</p>' : ''}
        </div>
      </fieldset>
      <fieldset class="report-outcome" id="rf-detail-field" ${['completed', 'stopped'].includes(expStatus) ? '' : 'hidden'}>
        <legend>实验结果</legend>
        <div class="report-form-grid">
          <label class="report-form-field"><span>实际指标值</span><input id="rf-actual" type="number" step="any" inputmode="decimal" value="${detail.actual_metric == null ? '' : escapeHtml(detail.actual_metric)}"></label>
          <label class="report-form-field"><span>结果判定</span><select id="rf-result"><option value="">请选择</option>${RESULT_OPTIONS.map(o => `<option value="${o.v}"${detail.result === o.v ? ' selected' : ''}>${o.label}</option>`).join('')}</select></label>
          <label class="report-form-field report-form-field--wide" id="rf-failure-wrap" ${detail.result === 'failure' ? '' : 'hidden'}><span>失败原因 <b aria-hidden="true">*</b></span><textarea id="rf-failure" maxlength="2000" rows="2">${escapeHtml(detail.failure_reason || '')}</textarea></label>
          <label class="report-form-field report-form-field--wide"><span>学到了什么</span><textarea id="rf-learning" maxlength="4000" rows="2">${escapeHtml(detail.learning || '')}</textarea></label>
          <label class="report-form-field"><span>下一步决策</span><select id="rf-decision"><option value="">请选择</option>${DECISION_OPTIONS.map(o => `<option value="${o.v}"${detail.next_decision === o.v ? ' selected' : ''}>${o.label}</option>`).join('')}</select></label>
        </div>
        <label class="report-publication-consent">
          <input type="checkbox" id="rf-publish-insights" ${publishToInsights ? 'checked' : ''}>
          <span><strong>未来公开聚合同意（当前暂停）</strong><small>默认关闭。勾选只记录你的版本化同意；当前不会公开人数、档位、排行或卡片。你可随时取消，登录账户后也可跨设备撤回；匿名设备不会成为公开参与者。</small></span>
        </label>
      </fieldset>
      <div class="report-followup__field">
        <span class="report-followup__label">备注 <span class="report-followup__optional">选填</span></span>
        <textarea class="report-followup__note" id="rf-note" rows="2" maxlength="2000"
                  placeholder="试了之后有什么发现？">${escapeHtml(curNote)}</textarea>
      </div>
      <div class="report-followup__actions">
        <button type="button" class="btn btn--primary btn--sm" id="rf-submit">保存</button>
        <span class="report-followup__msg" id="rf-msg" aria-live="polite"></span>
      </div>
    `;

    // Local selection state (seeded from server).
    const sel = { experimentStatus: expStatus };

    const reminderToggle = document.getElementById('report-reminder-toggle');
    if (reminderToggle) reminderToggle.addEventListener('change', () => {
      try { localStorage.setItem(LOCAL_REMINDER_KEY, reminderToggle.checked ? 'on' : 'off'); } catch (e) {}
      const reminderMessage = document.getElementById('report-reminder-message');
      if (reminderMessage) reminderMessage.textContent = reminderToggle.checked
        ? deadlineMessage(exp)
        : '本地提醒已关闭；' + deadlineMessage(exp);
    });

    panel.querySelectorAll('.rf-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        const group = btn.dataset.group;
        const value = btn.dataset.value;
        // Toggle within group — clicking the active chip clears it.
        const wasOn = btn.classList.contains('rf-chip--on');
        if (group === 'experiment-status' && wasOn) return;
        panel.querySelectorAll(`.rf-chip[data-group="${group}"]`)
          .forEach(b => { b.classList.remove('rf-chip--on'); b.setAttribute('aria-pressed', 'false'); });
        if (!wasOn) { btn.classList.add('rf-chip--on'); btn.setAttribute('aria-pressed', 'true'); }
        sel[group] = wasOn ? '' : value;
        if (group === 'experiment-status') {
          sel.experimentStatus = wasOn ? expStatus : value;
          const df = document.getElementById('rf-detail-field');
          if (df) df.hidden = !['completed', 'stopped'].includes(sel.experimentStatus);
        }
      });
    });

    const resultSelect = document.getElementById('rf-result');
    if (resultSelect) resultSelect.addEventListener('change', () => {
      const wrap = document.getElementById('rf-failure-wrap');
      if (wrap) wrap.hidden = resultSelect.value !== 'failure';
    });

    const submitBtn = document.getElementById('rf-submit');
    if (submitBtn) {
      submitBtn.addEventListener('click', () => {
        const msg = document.getElementById('rf-msg');
        const value = (id) => ((document.getElementById(id) || {}).value || '').trim();
        const hypothesis = value('rf-hypothesis');
        if (!hypothesis) {
          if (msg) { msg.textContent = '请先写明可验证的假设'; msg.className = 'report-followup__msg report-followup__msg--err'; }
          const field = document.getElementById('rf-hypothesis'); if (field) field.focus();
          return;
        }
        const numberOrNull = (id) => {
          const raw = value(id);
          if (raw === '') return null;
          const parsed = Number(raw);
          return Number.isFinite(parsed) ? parsed : NaN;
        };
        const experiment = { hypothesis: hypothesis, status: sel.experimentStatus };
        [['owner', 'rf-owner'], ['deadline', 'rf-deadline'], ['primary_metric', 'rf-metric'], ['stop_condition', 'rf-stop'], ['notes', 'rf-exp-notes']].forEach(([key, id]) => { experiment[key] = value(id) || null; });
        experiment.baseline = numberOrNull('rf-baseline');
        experiment.success_threshold = numberOrNull('rf-threshold');
        const note = (document.getElementById('rf-note') || {}).value || '';
        const actionByExperiment = { planned: 'planned', in_progress: 'in_progress', completed: 'tried', stopped: 'abandoned', abandoned: 'abandoned' };
        const body = { action_status: actionByExperiment[sel.experimentStatus], experiment: experiment };
        body.note = note.trim().slice(0, 2000) || null;
        if (['completed', 'stopped'].includes(sel.experimentStatus)) {
          const outcomeDetail = {
            actual_metric: numberOrNull('rf-actual'),
            result: value('rf-result') || null,
            failure_reason: value('rf-result') === 'failure' ? (value('rf-failure') || null) : null,
            learning: value('rf-learning') || null,
            next_decision: value('rf-decision') || null,
          };
          if (outcomeDetail.result === 'failure' && !outcomeDetail.failure_reason) {
            if (msg) { msg.textContent = '结果为失败时，请记录失败原因'; msg.className = 'report-followup__msg report-followup__msg--err'; }
            const field = document.getElementById('rf-failure'); if (field) field.focus();
            return;
          }
          if (!outcomeDetail.result) {
            if (msg) { msg.textContent = '请先选择实验结果判定'; msg.className = 'report-followup__msg report-followup__msg--err'; }
            const field = document.getElementById('rf-result'); if (field) field.focus();
            return;
          }
          body.outcome_detail = outcomeDetail;
          body.outcome = { success: 'worked', partial: 'partial', failure: 'no_effect', inconclusive: 'too_early' }[outcomeDetail.result];
          const publicationConsent = document.getElementById('rf-publish-insights');
          body.publish_to_insights = Boolean(publicationConsent && publicationConsent.checked);
        }

        if ([experiment.baseline, experiment.success_threshold,
          body.outcome_detail && body.outcome_detail.actual_metric].some(Number.isNaN)) {
          if (msg) { msg.textContent = '指标值必须是有效数字'; msg.className = 'report-followup__msg report-followup__msg--err'; }
          return;
        }

        submitBtn.disabled = true;
        if (msg) { msg.textContent = '保存中…'; msg.className = 'report-followup__msg'; }

        fetch('/api/report/' + encodeURIComponent(reportId) + '/followup', {
          method: 'POST',
          headers: Object.assign({ 'Content-Type': 'application/json' }, anonHeaders()),
          body: JSON.stringify(body),
        })
          .then((r) => r.ok ? r.json() : Promise.reject('HTTP ' + r.status))
          .then((saved) => {
            submitBtn.disabled = false;
            if (msg) {
              msg.textContent = TERMINAL_EXPERIMENTS.includes(sel.experimentStatus)
                ? (saved.publish_to_insights
                  ? '已保存；已记录未来公开聚合同意，但公开聚合当前暂停。'
                  : '已保存；结果保持私密，不再提醒。')
                : '已保存；可在「我的报告」查看到期状态。';
              msg.className = 'report-followup__msg report-followup__msg--ok';
            }
            const reminderMessage = document.getElementById('report-reminder-message');
            if (reminderMessage) reminderMessage.textContent = deadlineMessage(experiment);
            window.setTimeout(() => renderFollowup(reportId, saved), 350);
          })
          .catch((err) => {
            console.warn('[report] followup save failed');
            submitBtn.disabled = false;
            if (msg) { msg.textContent = '没保存成功，请稍后再试'; msg.className = 'report-followup__msg report-followup__msg--err'; }
          });
      });
    }
  }

  // Fetch any previously recorded follow-up and render the panel.
  // B Data Flywheel (Session #18) — revisit nudge. If the report is ≥3
  // days old and this device hasn't recorded an outcome yet, show a gentle
  // prompt above the followup panel asking '上次这份报告你试了吗'. The goal
  // is lifting followup-collection rate; it self-dismisses once dismissed
  // (sessionStorage) or once the user actually fills in an outcome.
  var REVISIT_NUDGE_DAYS = 3;

  // Inject the nudge styling once. Kept in JS (not analyze.css, a shared
  // stylesheet we must not touch) — scoped to .report-followup__nudge.
  function ensureNudgeStyles() {
    if (document.getElementById('rf-nudge-styles')) return;
    var s = document.createElement('style');
    s.id = 'rf-nudge-styles';
    s.textContent =
      '.report-followup__nudge{display:flex;align-items:flex-start;' +
      'justify-content:space-between;gap:12px;margin-bottom:16px;' +
      'padding:14px 16px;background:#FFF8E6;border:1px solid #F2DFA0;' +
      'border-radius:12px;}' +
      '.report-followup__nudge-body{display:flex;gap:10px;align-items:flex-start;}' +
      '.report-followup__nudge-icon{font-size:18px;line-height:1.4;}' +
      '.report-followup__nudge-title{margin:0;font-size:14px;font-weight:600;' +
      'color:#6B5400;line-height:1.5;}' +
      '.report-followup__nudge-sub{margin:2px 0 0;font-size:13px;' +
      'color:#8A7330;line-height:1.5;}' +
      '.report-followup__nudge-close{flex-shrink:0;border:0;background:none;' +
      'cursor:pointer;font-size:20px;line-height:1;color:#B59A4A;padding:0 4px;}' +
      '.report-followup__nudge-close:hover{color:#6B5400;}';
    document.head.appendChild(s);
  }

  function reportAgeDays(createdAt) {
    if (!createdAt) return 0;
    var t = new Date(createdAt).getTime();
    if (isNaN(t)) return 0;
    return (Date.now() - t) / 86400000;
  }

  function maybeRenderRevisitNudge(reportId, createdAt, followupState) {
    var st = followupState || {};
    // Already reported an outcome → no nudge needed.
    if (st.outcome) return;
    if (reportAgeDays(createdAt) < REVISIT_NUDGE_DAYS) return;
    var dismissKey = 'rf-nudge-dismissed:' + reportId;
    try {
      if (sessionStorage.getItem(dismissKey)) return;
    } catch (e) { /* sessionStorage unavailable — show anyway */ }

    var panel = document.getElementById('report-followup');
    if (!panel || document.getElementById('rf-revisit-nudge')) return;
    ensureNudgeStyles();
    var nudge = document.createElement('div');
    nudge.id = 'rf-revisit-nudge';
    nudge.className = 'report-followup__nudge';
    nudge.innerHTML =
      '<div class="report-followup__nudge-body">' +
        '<span class="report-followup__nudge-icon" aria-hidden="true">💡</span>' +
        '<div>' +
          '<p class="report-followup__nudge-title">上次这份报告你试了吗？结果如何？</p>' +
          '<p class="report-followup__nudge-sub">用一分钟记下实验与结果，帮我们沉淀「真的管用」的跨领域方法。</p>' +
        '</div>' +
      '</div>' +
      '<button type="button" class="report-followup__nudge-close" ' +
        'id="rf-nudge-close" aria-label="关闭提示">×</button>';
    panel.insertBefore(nudge, panel.firstChild);
    var closeBtn = document.getElementById('rf-nudge-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        nudge.remove();
        try { sessionStorage.setItem(dismissKey, '1'); } catch (e) {}
      });
    }
  }

  function loadFollowup(reportId, createdAt) {
    if (!reportId) return;
    fetch('/api/report/' + encodeURIComponent(reportId) + '/followup', { headers: anonHeaders() })
      .then((r) => r.ok ? r.json() : Promise.reject('HTTP ' + r.status))
      .then((data) => {
        var followup = data && data.followup;
        renderFollowup(reportId, followup);
        maybeRenderRevisitNudge(reportId, createdAt, followup);
      })
      .catch((err) => {
        // Fail closed: an empty form could overwrite a record we could not load.
        console.warn('[report] followup load failed');
        renderFollowup(reportId, null);
        const submit = document.getElementById('rf-submit');
        const msg = document.getElementById('rf-msg');
        if (submit) submit.disabled = true;
        if (msg) {
          msg.textContent = '未能读取已有记录，请刷新后重试';
          msg.className = 'report-followup__msg report-followup__msg--err';
        }
      });
  }

  function renderMeta(meta, data) {
    const el = document.getElementById('report-meta');
    if (!el) return;
    const created = data.created_at
      ? new Date(data.created_at).toLocaleString('zh-CN')
      : '';
    const displayLabel = persistedTargetContext(data).label || '未命名报告';
    el.innerHTML = (
      '<div class="report-meta__row">' +
        '<h1 class="report-meta__query">' + escapeHtml(displayLabel) + '</h1>' +
        '<div class="report-meta__attrs">' +
          (created ? '<span>📅 ' + escapeHtml(created) + '</span>' : '') +
          ' <span>👁 ' + (data.view_count || 0) + ' 次浏览</span>' +
          ' <span class="report-meta__model">' + escapeHtml(data.model || '') + '</span>' +
          (data.snapshot_status === 'historical_snapshot'
            ? ' <span class="report-meta__snapshot">生成时证据快照</span>' : '') +
          (data.is_partial ? ' <span class="report-meta__partial">⚠ 未完整生成</span>' : '') +
        '</div>' +
      '</div>'
    );
    el.hidden = false;
  }

  function renderOrigin(origin) {
    const el = document.getElementById('report-origin');
    if (!el) return;
    el.hidden = true;
    el.replaceChildren();
    if (!origin || origin.contract_version !== 'discovery-candidate-v2' ||
        !/^discovery-[0-9a-f]{16}$/.test(origin.discovery_id || '') ||
        !origin.pair || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(origin.pair.a_id || '') ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(origin.pair.b_id || '')) return;

    const copy = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = '来自精选发现中的候选';
    const detail = document.createElement('span');
    detail.textContent = '这份报告保留了源候选身份；报告和用户结果不会自动升级候选证据。';
    copy.append(title, detail);

    const link = document.createElement('a');
    link.href = '/discoveries?candidate=' + encodeURIComponent(origin.discovery_id);
    link.textContent = '返回源候选';
    el.append(copy, link);
    el.hidden = false;
  }

  function showError(msg) {
    const loading = document.getElementById('report-loading');
    if (loading) loading.hidden = true;
    const err = document.getElementById('report-error');
    if (err) err.hidden = false;
    if (msg) {
      const m = document.getElementById('report-error-msg');
      if (m) m.textContent = msg;
    }
  }

  function renderValidatedPersistedDetail(data, route) {
    resetPersistedReportState();
    try {
      const error = document.getElementById('report-error');
      if (error) error.hidden = true;
      const loading = document.getElementById('report-loading');
      if (loading) loading.hidden = true;

      renderMeta(null, data);
      renderOrigin(data.origin_candidate);

      const sectionsContainer = document.getElementById('analyze-sections');
      if (sectionsContainer) renderReport(data.payload, sectionsContainer, data);

      // A renderer exception is a trust-boundary failure, not a cosmetic
      // warning: leaving a half old/half new report would misbind evidence.
      if (typeof window.renderTldrCard === 'function') window.renderTldrCard();
      if (typeof window.renderDecisionBrief === 'function') {
        const targetContext = persistedTargetContext(data);
        window.renderDecisionBrief({
          query: targetContext.label,
          fingerprint: data.fingerprint,
          source: data.source,
          reportId: data.id,
          model: data.model,
          promptVersion: data.prompt_version,
          createdAt: data.created_at,
          partial: data.is_partial,
          allowExperiment: route.kind === 'id',
        });
      }

      window._persistedReport = route.kind === 'id' ? {
        id: data.id,
        share_url: data.share_url,
        is_partial: false,
      } : null;
      if (window._m14_renderShareBar && window._persistedReport) {
        window._m14_renderShareBar(window._persistedReport);
      }
      if (route.kind === 'id') loadFollowup(data.id, data.created_at);
      return true;
    } catch (error) {
      resetPersistedReportState();
      throw error;
    }
  }

  // Parse URL — supports /report/share/<token> and /report/<id>.
  function parseRoute() {
    const path = window.location.pathname.replace(/\/+$/, '');
    const shareMatch = path.match(/^\/report\/share\/([a-f0-9]{32})$/i);
    if (shareMatch) return { kind: 'share', value: shareMatch[1] };
    const idMatch = path.match(/^\/report\/(r_[a-f0-9]{16})$/i);
    if (idMatch) return { kind: 'id', value: idMatch[1] };
    return null;
  }

  function load() {
    const route = parseRoute();
    if (!route) {
      // Keep the static HTML error copy (which points at /reports) instead
      // of overriding it with a terse "invalid URL" line. (SESSION-17 R-02)
      showError();
      return;
    }
    const url = route.kind === 'share'
      ? '/api/report/share/' + encodeURIComponent(route.value)
      : '/api/report/' + encodeURIComponent(route.value);
    let anonId = '';
    try { anonId = localStorage.getItem('anonId') || ''; } catch (e) {}
    const headers = anonId ? { 'X-Anon-Id': anonId } : {};

    fetch(url, { headers: headers })
      .then((r) => {
        if (r.status === 404) throw new Error('404');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(async (data) => {
        if (!await validatePersistedDetail(data, route)) {
          resetPersistedReportState();
          throw new Error('invalid_report');
        }
        renderValidatedPersistedDetail(data, route);
      })
      .catch((err) => {
        // P0-4: never surface a raw error (e.g. a JSON SyntaxError from an
        // HTML error page) to the user. Friendly copy only; details to
        // content-free browser telemetry.
        resetPersistedReportState();
        console.error('[report] load failed');
        if (String(err).indexOf('404') !== -1) {
          // Keep the richer static HTML copy (points at /reports). (R-02)
          showError();
        } else if (String(err).indexOf('invalid_report') !== -1) {
          showError('这份报告未通过完整性与证据校验，请从「我的研究」重新生成。');
        } else {
          showError('报告暂时加载不出来，请稍后重试。');
        }
      });
  }

  const reportTrustApi = Object.freeze({
    containsInternalCapability,
    renderValidatedPersistedDetail,
    resetPersistedReportState,
    validatePersistedDetail,
  });
  window.StructuralReportTrust = reportTrustApi;
  if (typeof module !== 'undefined' && module.exports) module.exports = reportTrustApi;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
