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

  function trackPlausible(event, props) {
    try {
      if (typeof window.plausible === 'function') {
        window.plausible(event, props ? { props: props } : undefined);
      }
    } catch (e) {}
  }

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
    window._analyzeMeta = {
      credibility: (detail && detail.credibility) || null,
      similarity: (detail && typeof detail.similarity === 'number') ? detail.similarity : undefined,
      a: (detail && detail.source) || {},
      b: {
        original_query: (detail && detail.query) || '',
        description: (detail && (detail.rewritten_query || detail.query)) || '',
      },
      is_query_mode: true,
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
    const expStatus = exp.status || 'planned';
    const allowedStatuses = EXPERIMENT_TRANSITIONS[expStatus] || [expStatus];
    const chip = (group, opt, selected) => `
      <button type="button" class="rf-chip${selected ? ' rf-chip--on' : ''}"
              data-group="${group}" data-value="${opt.v}" aria-pressed="${selected ? 'true' : 'false'}">${escapeHtml(opt.label)}</button>`;

    panel.innerHTML = `
      <div class="report-followup__head">
        <h3 class="report-followup__title">验证这次迁移</h3>
        <p class="report-followup__sub">把建议变成一个可检验的最小实验，并记录真实结果。内容只保存在这份报告中。</p>
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
            if (msg) { msg.textContent = '已保存'; msg.className = 'report-followup__msg report-followup__msg--ok'; }
            window.setTimeout(() => renderFollowup(reportId, saved), 350);
            trackPlausible('Report Followup', { action_status: body.action_status, outcome: body.outcome || 'none' });
          })
          .catch((err) => {
            console.warn('[report] followup save failed:', err);
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
        trackPlausible('Report Revisit Nudge Dismissed');
      });
    }
    trackPlausible('Report Revisit Nudge Shown');
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
        console.warn('[report] followup load failed:', err);
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
    el.innerHTML = (
      '<div class="report-meta__row">' +
        '<h1 class="report-meta__query">' + escapeHtml(data.query || '未命名报告') + '</h1>' +
        '<div class="report-meta__attrs">' +
          (created ? '<span>📅 ' + escapeHtml(created) + '</span>' : '') +
          ' <span>👁 ' + (data.view_count || 0) + ' 次浏览</span>' +
          ' <span class="report-meta__model">' + escapeHtml(data.model || '') + '</span>' +
          (data.is_partial ? ' <span class="report-meta__partial">⚠ 未完整生成</span>' : '') +
        '</div>' +
      '</div>'
    );
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
      .then((data) => {
        const loading = document.getElementById('report-loading');
        if (loading) loading.hidden = true;

        renderMeta(null, data);

        const sectionsContainer = document.getElementById('analyze-sections');
        if (sectionsContainer) {
          renderReport(data.payload || {}, sectionsContainer, data);
        }

        // SESSION-17 V1: render the core insight card on the saved/shared
        // page too, using analyze.js's renderTldrCard (it reads the same
        // window._finalReport + window._analyzeMeta we just populated).
        if (typeof window.renderTldrCard === 'function') {
          try { window.renderTldrCard(); } catch (e) { /* non-fatal */ }
        }

        if (typeof window.renderDecisionBrief === 'function') {
          window.renderDecisionBrief({
            query: data.query,
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

        // Stash persisted info so window._m14_submitFeedback can POST.
        // P1-5: also pick up the share token from the API response on the
        // /report/<id> route, so a user viewing their own report still
        // gets a share bar.
        const shareToken = route.kind === 'share'
          ? route.value
          : (data.share_token || null);
        const shareUrl = shareToken
          ? (window.location.origin + '/report/share/' + shareToken)
          : null;
        window._persistedReport = {
          id: data.id,
          share_token: shareToken,
          share_url: shareUrl,
          is_partial: !!data.is_partial,
        };
        // Render the share bar (re-uses analyze.js's renderShareBar)
        // whenever we have a share token, regardless of route kind.
        if (window._m14_renderShareBar && shareToken) {
          window._m14_renderShareBar(window._persistedReport);
        }

        // SESSION-17 V6: load + render the report→action→outcome follow-up
        // panel below the action_plan section.
        if (data.id) loadFollowup(data.id, data.created_at);

        trackPlausible('Report Share Page Viewed', {
          referrer: document.referrer ? 'external' : 'direct',
          is_partial: !!data.is_partial,
        });
      })
      .catch((err) => {
        // P0-4: never surface a raw error (e.g. a JSON SyntaxError from an
        // HTML error page) to the user. Friendly copy only; details to
        // the console.
        console.error('[report] load failed:', err);
        if (String(err).indexOf('404') !== -1) {
          // Keep the richer static HTML copy (points at /reports). (R-02)
          showError();
        } else {
          showError('报告暂时加载不出来，请稍后重试。');
        }
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
