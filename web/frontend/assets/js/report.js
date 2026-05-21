/**
 * Structural — Persisted Report Viewer (M1.4 PR ***REMOVED***5).
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
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&***REMOVED***39;',
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
   * Render the 9-section report into ***REMOVED***analyze-sections.
   *
   * P0-1 (SESSION-17): reuse analyze.js's `renderFinalReport`, which drives
   * the same per-section `renderers` the live /analyze page uses. This makes
   * a shared/saved report look identical to a freshly-generated one — proper
   * Chinese headings, structured cards, KaTeX formulas — instead of the old
   * raw key-value dump that exposed `if_time_short` / `this_week` etc.
   */
  function renderReport(payload, container) {
    // Expose the payload + meta the way analyze.js expects so its renderers
    // and any i18n re-render path can read them.
    window._finalReport = payload || {};

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
      showError('无效的报告 URL。');
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
          renderReport(data.payload || {}, sectionsContainer);
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
          showError('这份报告可能已被删除，或链接已失效。');
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
