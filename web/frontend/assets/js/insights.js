/**
 * Structural — Insights dashboard (B Data Flywheel, Session ***REMOVED***18).
 *
 * Fetches three aggregate endpoints and renders:
 *   - GET /api/insights/summary           → top-line stat cards
 *   - GET /api/insights/stuck-structures  → "最常卡住的问题结构" list
 *   - GET /api/insights/verified          → "已验证同构库" list
 *
 * Aggregate, non-PII data — no anon-id header needed. Each section
 * degrades to a friendly empty state on no data; a failed fetch shows
 * a quiet retry-able error without tearing down the rest of the page.
 */
(function () {
  'use strict';

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&***REMOVED***39;' }[c];
    });
  }

  function fmtDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function fmtPct(rate) {
    var n = Number(rate);
    if (isNaN(n)) return '0%';
    return Math.round(n * 100) + '%';
  }

  function trackPlausible(event, props) {
    try {
      if (typeof window.plausible === 'function') {
        window.plausible(event, props ? { props: props } : undefined);
      }
    } catch (e) { /* ignore */ }
  }

  function getJson(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function emptyHtml(title, hint) {
    return (
      '<div class="insights-empty">' +
        '<p class="insights-empty__title">' + escapeHtml(title) + '</p>' +
        '<p>' + escapeHtml(hint) + '</p>' +
      '</div>'
    );
  }

  // ---- summary stat cards ---- //

  function renderSummary(data) {
    var el = document.getElementById('insights-summary');
    if (!el) return;
    var d = data || {};
    var cards = [
      { value: d.total_reports || 0, label: '生成的研究报告' },
      { value: d.total_followups || 0, label: '收到的回访记录' },
      { value: d.worked_count || 0, label: '标记「确实管用」' },
      { value: d.verified_isomorphisms || 0, label: '已验证同构' }
    ];
    el.innerHTML = cards.map(function (c) {
      return (
        '<div class="insights-stat">' +
          '<div class="insights-stat__value">' + (parseInt(c.value, 10) || 0) + '</div>' +
          '<div class="insights-stat__label">' + escapeHtml(c.label) + '</div>' +
        '</div>'
      );
    }).join('');
  }

  // ---- stuck structures ---- //

  function stuckRowHtml(item, idx) {
    var followups = parseInt(item.followup_count, 10) || 0;
    var reports = parseInt(item.report_count, 10) || 0;
    var rateHtml = followups
      ? '<div class="insights-row__rate">' + fmtPct(item.worked_rate) + ' 管用</div>'
      : '<div class="insights-row__rate insights-row__rate--none">暂无回访</div>';
    return (
      '<div class="insights-row">' +
        '<div class="insights-row__rank">' + (idx + 1) + '</div>' +
        '<div class="insights-row__body">' +
          '<div class="insights-row__name">' + escapeHtml(item.b_id || '（未知目标）') + '</div>' +
          '<div class="insights-row__meta">' +
            reports + ' 份报告 · ' + followups + ' 次回访' +
          '</div>' +
        '</div>' +
        rateHtml +
      '</div>'
    );
  }

  function renderStuck(data) {
    var el = document.getElementById('insights-stuck');
    if (!el) return;
    var items = (data && data.items) || [];
    if (items.length === 0) {
      el.innerHTML = emptyHtml(
        '还没有足够数据',
        '等用户用起来——生成的报告多了，这里会显示大家最常卡住的问题结构。'
      );
      return;
    }
    el.innerHTML = items.map(stuckRowHtml).join('');
  }

  // ---- verified isomorphisms ---- //

  function verifiedCardHtml(item) {
    var source = escapeHtml(item.source_phenomenon || item.structure_name || '某个现象');
    var count = parseInt(item.verifier_count, 10) || 0;
    var when = fmtDate(item.last_verified_at);
    var reportId = escapeHtml(item.report_id || '');
    var problemHtml = reportId
      ? '<a class="insights-card__problem" href="/report/' + reportId + '">' +
          escapeHtml(item.problem || '（未命名问题）') + '</a>'
      : '<p class="insights-card__problem">' + escapeHtml(item.problem || '（未命名问题）') + '</p>';
    return (
      '<div class="insights-card">' +
        '<div class="insights-card__top">' +
          problemHtml +
          '<span class="insights-card__verified-tag">✓ 已验证</span>' +
        '</div>' +
        '<div class="insights-card__flow">' +
          '<span class="insights-card__chip">你的问题</span>' +
          '<span class="insights-card__flow-arrow">→ 借自 →</span>' +
          '<span class="insights-card__chip">' + source + '</span>' +
        '</div>' +
        '<div class="insights-card__meta">' +
          count + ' 人验证有效' + (when ? ' · 最近 ' + escapeHtml(when) : '') +
        '</div>' +
      '</div>'
    );
  }

  function renderVerified(data) {
    var el = document.getElementById('insights-verified');
    if (!el) return;
    var items = (data && data.items) || [];
    if (items.length === 0) {
      el.innerHTML = emptyHtml(
        '还没有已验证的同构',
        '当有用户回到报告页确认「试了，管用」，这份跨领域映射就会沉淀到这里。'
      );
      return;
    }
    el.innerHTML = items.map(verifiedCardHtml).join('');
  }

  // ---- section error fallback ---- //

  function showSectionError(elId) {
    var el = document.getElementById(elId);
    if (!el) return;
    el.innerHTML = emptyHtml('加载失败', '稍后刷新重试。若反复失败，多半是网络问题。');
  }

  function load() {
    getJson('/api/insights/summary')
      .then(renderSummary)
      .catch(function (err) {
        console.error('[insights] summary failed:', err);
        var el = document.getElementById('insights-summary');
        if (el) el.innerHTML = emptyHtml('加载失败', '稍后刷新重试。');
      });

    getJson('/api/insights/stuck-structures?limit=10')
      .then(renderStuck)
      .catch(function (err) {
        console.error('[insights] stuck-structures failed:', err);
        showSectionError('insights-stuck');
      });

    getJson('/api/insights/verified?limit=20')
      .then(renderVerified)
      .catch(function (err) {
        console.error('[insights] verified failed:', err);
        showSectionError('insights-verified');
      });

    trackPlausible('Insights Page Viewed');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
