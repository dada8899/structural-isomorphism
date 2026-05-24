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
    // Outcome only matters once the user has actually tried.
    const showOutcome = curStatus === 'tried' || curStatus === 'in_progress';

    const chip = (group, opt, selected) => `
      <button type="button" class="rf-chip${selected ? ' rf-chip--on' : ''}"
              data-group="${group}" data-value="${opt.v}">${escapeHtml(opt.label)}</button>`;

    panel.innerHTML = `
      <div class="report-followup__head">
        <h3 class="report-followup__title">我试过了吗 · 结果如何</h3>
        <p class="report-followup__sub">记一笔。下次回到这份报告时，能看到你当时做到哪一步。</p>
      </div>
      ${st.action_status ? `<div class="report-followup__saved" id="rf-saved-hint">上次记录：${escapeHtml((FOLLOWUP_STATUS.find(x => x.v === curStatus) || {}).label || curStatus)}${curOutcome ? ' · ' + escapeHtml((FOLLOWUP_OUTCOME.find(x => x.v === curOutcome) || {}).label || curOutcome) : ''}</div>` : ''}
      <div class="report-followup__field">
        <span class="report-followup__label">进展</span>
        <div class="rf-chips" id="rf-status">
          ${FOLLOWUP_STATUS.map(o => chip('status', o, o.v === curStatus)).join('')}
        </div>
      </div>
      <div class="report-followup__field" id="rf-outcome-field" ${showOutcome ? '' : 'hidden'}>
        <span class="report-followup__label">结果</span>
        <div class="rf-chips" id="rf-outcome">
          ${FOLLOWUP_OUTCOME.map(o => chip('outcome', o, o.v === curOutcome)).join('')}
        </div>
      </div>
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
    const sel = { status: curStatus, outcome: curOutcome };

    panel.querySelectorAll('.rf-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        const group = btn.dataset.group;
        const value = btn.dataset.value;
        // Toggle within group — clicking the active chip clears it.
        const wasOn = btn.classList.contains('rf-chip--on');
        panel.querySelectorAll(`.rf-chip[data-group="${group}"]`)
          .forEach(b => b.classList.remove('rf-chip--on'));
        if (!wasOn) btn.classList.add('rf-chip--on');
        sel[group] = wasOn ? '' : value;
        // Show/hide the outcome field based on status.
        if (group === 'status') {
          const of = document.getElementById('rf-outcome-field');
          const reveal = sel.status === 'tried' || sel.status === 'in_progress';
          if (of) of.hidden = !reveal;
        }
      });
    });

    const submitBtn = document.getElementById('rf-submit');
    if (submitBtn) {
      submitBtn.addEventListener('click', () => {
        const msg = document.getElementById('rf-msg');
        if (!sel.status) {
          if (msg) { msg.textContent = '先选一个进展'; msg.className = 'report-followup__msg report-followup__msg--err'; }
          return;
        }
        const note = (document.getElementById('rf-note') || {}).value || '';
        const body = { action_status: sel.status };
        if (sel.outcome) body.outcome = sel.outcome;
        if (note.trim()) body.note = note.trim().slice(0, 2000);

        submitBtn.disabled = true;
        if (msg) { msg.textContent = '保存中…'; msg.className = 'report-followup__msg'; }

        fetch('/api/report/' + encodeURIComponent(reportId) + '/followup', {
          method: 'POST',
          headers: Object.assign({ 'Content-Type': 'application/json' }, anonHeaders()),
          body: JSON.stringify(body),
        })
          .then((r) => r.ok ? r.json() : Promise.reject('HTTP ' + r.status))
          .then(() => {
            submitBtn.disabled = false;
            if (msg) { msg.textContent = '已保存'; msg.className = 'report-followup__msg report-followup__msg--ok'; }
            trackPlausible('Report Followup', { action_status: sel.status, outcome: sel.outcome || 'none' });
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
          '<p class="report-followup__nudge-sub">花 10 秒记一笔，帮我们沉淀「真的管用」的跨领域方法。</p>' +
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
        // GET failing shouldn't block the panel — show the empty form.
        console.warn('[report] followup load failed:', err);
        renderFollowup(reportId, null);
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
