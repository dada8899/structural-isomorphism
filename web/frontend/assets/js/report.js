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

  // 9-section display order (mirror of analyze.js SECTIONS but with the
  // canonical generation order — readers want the same flow as the live
  // page, not the answer-first reshuffle).
  const SECTIONS = [
    { key: 'shared_structure',       label: '共享结构' },
    { key: 'your_problem_breakdown', label: '你的问题拆解' },
    { key: 'target_domain_intro',    label: '源领域讲解' },
    { key: 'structural_mapping',     label: '结构对照' },
    { key: 'borrowable_insights',    label: '可借用的工具' },
    { key: 'how_to_combine',         label: '怎么结合' },
    { key: 'research_directions',    label: '研究方向' },
    { key: 'risks_and_limits',       label: '迁移风险' },
    { key: 'action_plan',            label: '本周行动' },
  ];

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

  function renderValue(v) {
    // Lightweight renderer for the section payload — KEEP IT DEFENSIVE.
    // The payload originates from an LLM; never insert raw HTML.
    if (v == null) return '<em class="muted">(empty)</em>';
    if (typeof v === 'string') return '<p>' + escapeHtml(v) + '</p>';
    if (typeof v === 'number' || typeof v === 'boolean') return '<p>' + escapeHtml(String(v)) + '</p>';
    if (Array.isArray(v)) {
      if (v.length === 0) return '<em class="muted">(empty list)</em>';
      const items = v.map((item) => '<li>' + (typeof item === 'string'
        ? escapeHtml(item) : renderValue(item)) + '</li>').join('');
      return '<ul>' + items + '</ul>';
    }
    if (typeof v === 'object') {
      const rows = Object.entries(v).map(([k, val]) => {
        return '<div class="report-field"><span class="report-field__label">' +
          escapeHtml(k) + '</span>' + renderValue(val) + '</div>';
      }).join('');
      return '<div class="report-object">' + rows + '</div>';
    }
    return '<p>' + escapeHtml(String(v)) + '</p>';
  }

  function renderSection(key, label, data) {
    return (
      '<section class="report-section" id="section-' + escapeHtml(key) + '">' +
        '<h3 class="report-section__title">' + escapeHtml(label) + '</h3>' +
        '<div class="report-section__body">' + renderValue(data) + '</div>' +
        '<div class="report-section__feedback">' +
          '<button type="button" class="analyze-vote analyze-vote--up" ' +
            'data-section="' + escapeHtml(key) + '" data-vote="1">👍</button>' +
          '<button type="button" class="analyze-vote analyze-vote--down" ' +
            'data-section="' + escapeHtml(key) + '" data-vote="-1">👎</button>' +
        '</div>' +
      '</section>'
    );
  }

  function renderReport(report, container) {
    let html = '';
    for (const s of SECTIONS) {
      if (report[s.key] !== undefined) {
        html += renderSection(s.key, s.label, report[s.key]);
      }
    }
    if (!html) {
      html = '<p class="muted">(报告内容为空)</p>';
    }
    container.innerHTML = html;
    // Wire per-section feedback buttons.
    container.querySelectorAll('.analyze-vote').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (window._m14_submitFeedback) {
          window._m14_submitFeedback(btn);
        }
      });
    });
    // Render any inline math the LLM emitted.
    if (typeof window.renderMath === 'function') window.renderMath(container);
  }

  function renderMeta(meta, data) {
    const el = document.getElementById('report-meta');
    if (!el) return;
    const created = data.created_at
      ? new Date(data.created_at).toLocaleString()
      : '';
    el.innerHTML = (
      '<div class="report-meta__row">' +
        '<h1 class="report-meta__query">' + escapeHtml(data.query || '(no query)') + '</h1>' +
        '<div class="report-meta__attrs">' +
          (created ? '<span>📅 ' + escapeHtml(created) + '</span>' : '') +
          ' <span>👁 ' + (data.view_count || 0) + ' views</span>' +
          ' <span class="report-meta__model">' + escapeHtml(data.model || '') + '</span>' +
          (data.is_partial ? ' <span class="report-meta__partial">⚠ partial</span>' : '') +
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
        window._persistedReport = {
          id: data.id,
          share_token: route.kind === 'share' ? route.value : null,
          share_url: route.kind === 'share' ? window.location.href : null,
          is_partial: !!data.is_partial,
        };
        // Render the share bar (re-uses analyze.js's renderShareBar).
        if (window._m14_renderShareBar && route.kind === 'share') {
          window._m14_renderShareBar(window._persistedReport);
        }

        trackPlausible('Report Share Page Viewed', {
          referrer: document.referrer ? 'external' : 'direct',
          is_partial: !!data.is_partial,
        });
      })
      .catch((err) => {
        console.error('[report] load failed:', err);
        if (String(err).indexOf('404') !== -1) {
          showError('这份报告不存在或已被删除。');
        } else {
          showError('加载失败: ' + (err && err.message ? err.message : 'unknown'));
        }
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
