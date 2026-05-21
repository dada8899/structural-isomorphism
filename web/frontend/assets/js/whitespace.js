/* A2 Whitespace Map — research whitespace heatmap + leads list.
   Loads the precomputed matrix from /api/whitespace/*, renders a heatmap
   and a ranked leads list. Each lead links to /analyze with prefilled
   ?text_a= (research question) + ?b_id= (anchor phenomenon). */
(function () {
  'use strict';

  var esc = window.escapeHtml || function (s) { return String(s == null ? '' : s); };

  // Per-row, only show this many top-similarity domains in the heatmap so
  // 183 columns stay scannable. Filled domains are always kept.
  var ROW_TOP_DOMAINS = 24;

  var state = {
    matrix: null,   // /api/whitespace/matrix payload
    leads: [],      // full leads array
  };

  function $(id) { return document.getElementById(id); }

  function show(el) { if (el) el.hidden = false; }
  function hide(el) { if (el) el.hidden = true; }

  // --- One-sentence research claim for a lead ---
  function leadClaim(lead) {
    return '「' + esc(lead.domain) + '」领域里，大概率存在属于 ' +
      '<em>' + esc(lead.class_name) + '</em> 的现象，但目前还没有人去验证。';
  }

  // --- Build the /analyze prefill URL for a lead ---
  function analyzeUrl(lead) {
    var question = lead.domain + '中是否存在属于「' + lead.class_name +
      '」的结构？以「' + (lead.anchor_name || '') + '」为切入点验证。';
    var p = new URLSearchParams();
    p.set('text_a', question);
    if (lead.anchor_id) p.set('b_id', lead.anchor_id);
    return '/analyze?' + p.toString();
  }

  // --- Render the heatmap matrix ---
  function renderMatrix() {
    var m = state.matrix;
    var host = $('ws-matrix');
    if (!host || !m) return;
    var classes = m.classes || [];
    var matrix = m.matrix || {};
    var frag = document.createDocumentFragment();

    classes.forEach(function (cls) {
      var cells = matrix[cls.class_id] || {};
      // Rank this row's domains by score; keep filled + top-N.
      var domains = Object.keys(cells);
      domains.sort(function (a, b) {
        return (cells[b].score || 0) - (cells[a].score || 0);
      });
      var pick = [];
      var seen = {};
      domains.forEach(function (d) {
        if (cells[d].state === 'filled') { pick.push(d); seen[d] = 1; }
      });
      for (var i = 0; i < domains.length && pick.length < ROW_TOP_DOMAINS; i++) {
        if (!seen[domains[i]]) { pick.push(domains[i]); seen[domains[i]] = 1; }
      }
      // Keep within-row order = score desc for visual coherence.
      pick.sort(function (a, b) {
        return (cells[b].score || 0) - (cells[a].score || 0);
      });

      var row = document.createElement('div');
      row.className = 'ws-matrix__row';
      row.setAttribute('role', 'row');

      var label = document.createElement('div');
      label.className = 'ws-matrix__label';
      label.textContent = cls.class_name || cls.class_id;
      label.title = cls.class_name || cls.class_id;
      row.appendChild(label);

      var cellsWrap = document.createElement('div');
      cellsWrap.className = 'ws-matrix__cells';
      pick.forEach(function (dom) {
        var c = cells[dom];
        var cell = document.createElement('div');
        cell.className = 'ws-cell ws-cell--' + c.state;
        cell.setAttribute('role', 'cell');
        var stateLabel = c.state === 'filled' ? '已验证'
          : (c.state === 'lead' ? '研究空白' : '结构不相关');
        cell.title = (cls.class_name || cls.class_id) + ' × ' + dom +
          ' — ' + stateLabel + '（相似度 ' + (c.score || 0).toFixed(2) + '）';
        if (c.state === 'lead') {
          cell.tabIndex = 0;
          cell.dataset.classId = cls.class_id;
          cell.dataset.domain = dom;
          cell.setAttribute('aria-label', '研究空白：' + cls.class_name + ' × ' + dom);
        }
        cellsWrap.appendChild(cell);
      });
      row.appendChild(cellsWrap);
      frag.appendChild(row);
    });

    host.innerHTML = '';
    host.appendChild(frag);

    // Clicking a lead cell scrolls to + highlights the matching lead card.
    host.addEventListener('click', function (e) {
      var cell = e.target.closest('.ws-cell--lead');
      if (cell) focusLead(cell.dataset.classId, cell.dataset.domain);
    });
    host.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var cell = e.target.closest('.ws-cell--lead');
      if (cell) { e.preventDefault(); focusLead(cell.dataset.classId, cell.dataset.domain); }
    });
  }

  // --- Scroll to + highlight a specific lead card ---
  function focusLead(classId, domain) {
    var card = document.querySelector(
      '.ws-lead[data-class-id="' + (classId || '').replace(/"/g, '') +
      '"][data-domain="' + (domain || '').replace(/"/g, '') + '"]');
    if (!card) {
      // The lead may be filtered out — clear filters and re-render first.
      var cs = $('ws-filter-class'), ds = $('ws-filter-domain');
      if (cs) cs.value = '';
      if (ds) ds.value = '';
      renderLeads();
      card = document.querySelector(
        '.ws-lead[data-class-id="' + (classId || '').replace(/"/g, '') +
        '"][data-domain="' + (domain || '').replace(/"/g, '') + '"]');
    }
    if (!card) return;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.add('ws-lead--highlight');
    setTimeout(function () { card.classList.remove('ws-lead--highlight'); }, 2400);
  }

  // --- Render the (possibly filtered) leads list ---
  function renderLeads() {
    var host = $('ws-leads');
    var emptyEl = $('ws-leads-empty');
    if (!host) return;
    var classFilter = ($('ws-filter-class') || {}).value || '';
    var domainFilter = ($('ws-filter-domain') || {}).value || '';

    var rows = state.leads.filter(function (l) {
      if (classFilter && l.class_id !== classFilter) return false;
      if (domainFilter && l.domain !== domainFilter) return false;
      return true;
    });

    host.innerHTML = '';
    if (rows.length === 0) { show(emptyEl); return; }
    hide(emptyEl);

    var frag = document.createDocumentFragment();
    rows.forEach(function (lead) {
      var card = document.createElement('article');
      card.className = 'ws-lead';
      card.dataset.classId = lead.class_id;
      card.dataset.domain = lead.domain;

      var anchorHtml = '';
      if (lead.anchor_name) {
        anchorHtml = '<p class="ws-lead__anchor">切入点现象：<b>' +
          esc(lead.anchor_name) + '</b>' +
          (lead.anchor_desc ? ' — ' + esc(lead.anchor_desc) : '') + '</p>';
      }

      card.innerHTML =
        '<div class="ws-lead__top">' +
          '<span class="ws-lead__tag ws-lead__tag--class">' + esc(lead.class_name) + '</span>' +
          '<span class="ws-lead__tag ws-lead__tag--domain">' + esc(lead.domain) + '</span>' +
          '<span class="ws-lead__score">相似度 ' + (lead.score || 0).toFixed(3) + '</span>' +
        '</div>' +
        '<p class="ws-lead__claim">' + leadClaim(lead) + '</p>' +
        anchorHtml +
        '<div class="ws-lead__actions">' +
          '<a class="ws-btn ws-btn--primary" href="' + esc(analyzeUrl(lead)) +
            '">生成验证方案 →</a>' +
        '</div>';
      frag.appendChild(card);
    });
    host.appendChild(frag);
  }

  // --- Populate the filter dropdowns ---
  function buildFilters() {
    var classSel = $('ws-filter-class');
    var domainSel = $('ws-filter-domain');
    if (classSel && state.matrix) {
      (state.matrix.classes || []).forEach(function (c) {
        var o = document.createElement('option');
        o.value = c.class_id;
        o.textContent = c.class_name || c.class_id;
        classSel.appendChild(o);
      });
    }
    if (domainSel) {
      // Domains that actually appear in at least one lead.
      var doms = {};
      state.leads.forEach(function (l) { doms[l.domain] = 1; });
      Object.keys(doms).sort().forEach(function (d) {
        var o = document.createElement('option');
        o.value = d;
        o.textContent = d;
        domainSel.appendChild(o);
      });
    }
    if (classSel) classSel.addEventListener('change', renderLeads);
    if (domainSel) domainSel.addEventListener('change', renderLeads);
    var reset = $('ws-filter-reset');
    if (reset) {
      reset.addEventListener('click', function () {
        if (classSel) classSel.value = '';
        if (domainSel) domainSel.value = '';
        renderLeads();
      });
    }
  }

  // --- Stats line ---
  function renderStats() {
    var el = $('ws-stats');
    var meta = (state.matrix && state.matrix.meta) || {};
    if (!el) return;
    el.innerHTML =
      '<span><b>' + (meta.n_classes || 0) + '</b> 个普适类</span>' +
      '<span><b>' + (meta.n_domains || 0) + '</b> 个领域</span>' +
      '<span><b>' + (meta.n_filled || 0) + '</b> 个已验证格子</span>' +
      '<span><b>' + (meta.n_leads || state.leads.length) + '</b> 个研究空白选题</span>';
    show(el);
  }

  // --- Data fetch ---
  function fetchJson(path) {
    return fetch('/api' + path, { headers: { 'Content-Type': 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
  }

  function init() {
    var loading = $('ws-loading');
    var errorEl = $('ws-error');

    Promise.all([
      fetchJson('/whitespace/matrix'),
      fetchJson('/whitespace/leads?limit=500'),
    ]).then(function (res) {
      state.matrix = res[0] || null;
      state.leads = (res[1] && res[1].leads) || [];

      hide(loading);

      if (!state.matrix || state.matrix.available === false ||
          !(state.matrix.classes || []).length) {
        show(errorEl);
        return;
      }

      renderStats();
      renderMatrix();
      buildFilters();
      renderLeads();
      show($('ws-matrix-section'));
      show($('ws-leads-section'));
    }).catch(function (err) {
      console.error('[whitespace] load failed:', err);
      hide(loading);
      show(errorEl);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
