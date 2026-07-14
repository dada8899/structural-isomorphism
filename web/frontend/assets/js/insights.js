/**
 * Structural — Insights dashboard (B Data Flywheel, Session #18).
 *
 * Public outcome aggregation is paused. The three endpoints expose only the
 * stable pause status, and this page renders explanatory paused states that
 * are independent of participant activity.
 */
(function () {
  'use strict';

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
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

  // Empty / error state. `variant` controls the tone:
  //   'growing' — no data yet, but that's expected early on (positive framing)
  //   'error'   — a fetch failed (quiet, retry-able tone)
  // The growing variant carries a soft icon so the section reads as
  // "数据在积累中", not "坏了".
  function emptyHtml(title, hint, variant) {
    var v = variant || 'growing';
    var icon = v === 'error'
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v5h-5"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16v-3M13 16v-6M18 16v-9"/><circle cx="8" cy="13" r="0.6" fill="currentColor"/></svg>';
    return (
      '<div class="insights-empty insights-empty--' + v + '">' +
        '<span class="insights-empty__icon" aria-hidden="true">' + icon + '</span>' +
        '<p class="insights-empty__title">' + escapeHtml(title) + '</p>' +
        '<p class="insights-empty__hint">' + escapeHtml(hint) + '</p>' +
      '</div>'
    );
  }

  // ---- paused summary ---- //

  function renderSummary(data) {
    var el = document.getElementById('insights-summary');
    if (!el) return;
    el.innerHTML = emptyHtml(
      '公开结果聚合已暂停',
      '当前不会展示人数、档位、排序或结果类别；新增或撤回记录都不会改变公开页面。'
    );
  }

  // ---- paused stuck-structure surface ---- //

  function renderStuck(data) {
    var el = document.getElementById('insights-stuck');
    if (!el) return;
    el.innerHTML = emptyHtml(
      '排行已关闭',
      '暂停期间不按真实参与人数生成、筛选或排序任何问题结构。'
    );
  }

  // ---- paused user-outcome surface ---- //

  function renderVerified(data) {
    var el = document.getElementById('insights-verified');
    if (!el) return;
    el.innerHTML = emptyHtml(
      '公开用户结果已关闭',
      '实验结果仍可作为你的私有研究记录保存，但不会出现在公开卡片或可信度提示中。'
    );
  }

  // ---- section error fallback ---- //

  function showSectionError(elId) {
    var el = document.getElementById(elId);
    if (!el) return;
    el.innerHTML = emptyHtml('这部分没加载出来', '稍后刷新重试。若反复失败，多半是网络问题。', 'error');
  }

  function load() {
    getJson('/api/insights/summary')
      .then(renderSummary)
      .catch(function (err) {
        console.error('[insights] summary failed');
        var el = document.getElementById('insights-summary');
        if (el) el.innerHTML = emptyHtml('总览没加载出来', '稍后刷新重试。', 'error');
      });

    getJson('/api/insights/stuck-structures')
      .then(renderStuck)
      .catch(function (err) {
        console.error('[insights] stuck structures failed');
        showSectionError('insights-stuck');
      });

    getJson('/api/insights/verified')
      .then(renderVerified)
      .catch(function (err) {
        console.error('[insights] verified results failed');
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
