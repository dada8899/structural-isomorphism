/* =============================================================
 * /assets/js/ask.js — Perplexity-like ask UI client (W2-A)
 *
 * Consumes POST /api/ask/stream (SSE) and renders thread items
 * incrementally. Reuses global helpers from utils.js
 * (escapeHtml, $, $$, addToHistory) and i18n.js (window.i18n).
 *
 * Self-contained IIFE — no module imports (project convention).
 * ============================================================= */

(function () {
  'use strict';

  // ---- i18n shim (mirrors search.js head) -----------------------
  function T(key, fallback) {
    try {
      if (window.i18n && typeof window.i18n.t === 'function') {
        var v = window.i18n.t(key);
        if (v && v !== key) return v;
      }
    } catch (e) {}
    return fallback;
  }

  // ---- state ----------------------------------------------------
  // Track current in-flight stream so a new submit can abort it.
  var currentController = null;
  var currentGeneration = 0;
  // Count threads so each item gets a stable DOM id.
  var threadCounter = 0;
  var pendingFingerprintQuery = '';

  // ---- Plausible event wrapper (W3-B) ---------------------------
  // Guarded so the page does not throw when plausible.js fails to load
  // (e.g. blocked by ad-blocker / privacy mode / region block).
  function track(event, props) {
    try {
      if (typeof window.plausible === 'function') {
        window.plausible(event, props ? { props: props } : undefined);
      }
    } catch (e) {
      // Telemetry must never break the UI.
    }
  }

  // Per-thread submit source tagging: 'empty' (first), 'chip', 'followup',
  // 'deeplink'. Set by submitQuery callers; defaults to 'followup' for any
  // subsequent submit so we never double-count an empty.
  var nextSubmitSource = 'empty';

  // ============================================================
  // DOM helpers
  // ============================================================
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }
  function esc(s) {
    // Prefer global escapeHtml from utils.js; fall back if missing.
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(s);
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function buildAskRequestBody(query, lang, fingerprint) {
    var body = { query: String(query || ''), lang: lang === 'en' ? 'en' : 'zh' };
    if (fingerprint) body.fingerprint = fingerprint;
    return body;
  }

  function askGenerationMatches(itemGeneration, activeGeneration, eventGeneration) {
    return itemGeneration === activeGeneration && eventGeneration === activeGeneration;
  }

  function validateAnswerDonePayload(data, cards, answerValidated) {
    if (!answerValidated || !data || typeof data.full_text !== 'string') return null;
    var citations = Array.isArray(data.citations) ? data.citations : [];
    var cardsById = {};
    (cards || []).forEach(function (card, index) {
      if (card && card.id && !cardsById[card.id]) {
        cardsById[card.id] = { card: card, index: index + 1 };
      }
    });
    var citationIds = {};
    for (var i = 0; i < citations.length; i++) {
      var cit = citations[i];
      var bound = cit && cardsById[cit.kb_id];
      if (!bound || cit.idx !== bound.index || citationIds[cit.idx]) return null;
      citationIds[cit.idx] = true;
    }
    var markers = Array.from(data.full_text.matchAll(/\[(\d+)\]/g)).map(function (match) {
      return parseInt(match[1], 10);
    });
    var isRefusal = data.out_of_scope === true && citations.length === 0;
    if (isRefusal) return { fullText: data.full_text, citations: citations };
    if (!markers.length || markers.some(function (idx) { return !citationIds[idx]; })) return null;
    var markerIds = {};
    markers.forEach(function (idx) { markerIds[idx] = true; });
    if (Object.keys(citationIds).some(function (idx) { return !markerIds[idx]; })) return null;
    return { fullText: data.full_text, citations: citations };
  }

  // ============================================================
  // Init
  // ============================================================
  // ============================================================
  // W6-D (session #7 P1 backlog): char counter for ask + follow-up inputs.
  // Reads data-limit / data-warn from the counter <div>, updates count
  // every input event, sets data-state to '' | 'warn' | 'stop' so CSS can
  // color the count + show the "已达上限" label. The textarea's
  // `maxlength` attribute already enforces the hard stop in the browser.
  // ============================================================
  function bindCharCounter(inputSel, counterSel) {
    var inputEl = qs(inputSel);
    var counterEl = qs(counterSel);
    if (!inputEl || !counterEl) return;
    var limit = parseInt(counterEl.getAttribute('data-limit') || '8000', 10);
    var warnAt = parseInt(counterEl.getAttribute('data-warn') || String(Math.floor(limit * 0.75)), 10);
    var textSpan = counterEl.querySelector('[data-counter-text]') || counterEl;

    function update() {
      var len = (inputEl.value || '').length;
      // Hide entirely while empty so the empty state stays clean.
      if (len === 0) {
        counterEl.hidden = true;
        counterEl.removeAttribute('data-state');
        textSpan.textContent = '0 / ' + limit;
        return;
      }
      counterEl.hidden = false;
      textSpan.textContent = len + ' / ' + limit;
      var newState = '';
      if (len >= limit) newState = 'stop';
      else if (len >= warnAt) newState = 'warn';
      var prev = counterEl.getAttribute('data-state') || '';
      if (newState !== prev) {
        if (newState) counterEl.setAttribute('data-state', newState);
        else counterEl.removeAttribute('data-state');
        // Track only on state transitions to avoid spamming Plausible.
        if (newState === 'warn') track('input_warn_threshold', { limit: limit, len: len });
        if (newState === 'stop') track('input_hit_cap', { limit: limit });
      }
    }

    inputEl.addEventListener('input', update);
    // Initial paint (e.g. if textarea was prefilled by browser session).
    update();
  }

  // Scheme A: grow the empty-state textarea with its content. Starts
  // at one row (min-height 56px from CSS) and expands up to max-height,
  // after which the textarea scrolls internally.
  function autoGrow(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
    el.style.overflowY = el.scrollHeight > el.clientHeight ? 'auto' : 'hidden';
  }

  function initAskPage() {
    var form = qs('#ask-form');
    if (form) {
      var submitBtn = qs('.ask-searchbox__submit', form);
      var input = qs('#ask-input');

      // Scheme A: keep the circular submit inert until there is text.
      // SESSION-25 Variant B: also toggle `is-filled` on the form so the
      // submit can flip to solid-accent the instant text appears (per
      // Perplexity's "ready-to-fire" affordance — no need to hover first).
      function syncSubmitState() {
        if (!submitBtn) return;
        var hasText = !!(input && input.value.trim());
        submitBtn.disabled = !hasText;
        if (form && form.classList) {
          form.classList.toggle('is-filled', hasText);
        }
      }
      syncSubmitState();

      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var q = input ? input.value.trim() : '';
        if (!q) return;
        // Scheme A: lock + spin the button so the click registers
        // visually even though submitQuery swaps to the thread view.
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.classList.add('is-loading');
        }
        openFingerprintReview(q);
      });

      // Cmd/Ctrl+Enter submits
      if (input) {
        input.addEventListener('input', function () {
          autoGrow(input);
          syncSubmitState();
        });
        input.addEventListener('keydown', function (ev) {
          if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') {
            ev.preventDefault();
            form.requestSubmit();
          }
        });
        // Initial paint (handles browser-restored text).
        autoGrow(input);
        // Autofocus on landing
        try { input.focus(); } catch (e) {}
      }
    }

    var followForm = qs('#ask-followup-form');
    if (followForm) {
      followForm.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var input = qs('#ask-followup-input');
        var q = input ? input.value.trim() : '';
        if (!q) return;
        submitQuery(q);
        if (input) {
          input.value = '';
          // Reset the follow-up counter since the field emptied.
          var fc = qs('#ask-followup-char-counter');
          if (fc) {
            fc.hidden = true;
            fc.removeAttribute('data-state');
          }
        }
      });
      var fInput = qs('#ask-followup-input');
      if (fInput) {
        fInput.addEventListener('keydown', function (ev) {
          if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') {
            ev.preventDefault();
            followForm.requestSubmit();
          }
        });
      }
    }

    // W6-D: wire the counters for both inputs. Safe no-op if elements
    // missing (e.g. on alternate page layouts).
    bindCharCounter('#ask-input', '#ask-char-counter');
    bindCharCounter('#ask-followup-input', '#ask-followup-char-counter');

    bindExampleChips();

    // Migrate old external ?q links. The initial request may already exist in
    // upstream access logs; scrub immediately so history/referrers and every
    // subsequent same-origin request do not propagate the question further.
    try {
      var legacyUrl = new URL(window.location.href);
      var qParam = legacyUrl.searchParams.get('q');
      if (qParam) {
        legacyUrl.searchParams.delete('q');
        window.history.replaceState(
          window.history.state,
          '',
          legacyUrl.pathname + legacyUrl.search + legacyUrl.hash
        );
      }
      if (qParam && qParam.trim()) {
        // Tag the upcoming submit; submitQuery normalises 'empty' for
        // first-from-landing, so we keep 'deeplink' explicit instead.
        nextSubmitSource = 'deeplink';
        openFingerprintReview(qParam.trim());
      }
    } catch (e) {}
  }

  function bindExampleChips() {
    qsa('.ask-chip[data-example-q]').forEach(function (chip, index) {
      chip.addEventListener('click', function () {
        var q = chip.getAttribute('data-example-q') || '';
        if (q.trim()) {
          // A coarse position identifies the curated example without sending
          // its natural-language label to analytics.
          track('example_chip_clicked', { position: index + 1 });
          nextSubmitSource = 'chip';
          openFingerprintReview(q.trim());
        }
      });
    });
  }

  function canonicalFingerprintText(value, allowLayout) {
    var text = String(value == null ? '' : value).normalize('NFKC');
    // Keep this boundary aligned with services/input_limits.py and
    // privateNavigation.js.  Several default-ignorables (notably CGJ and
    // variation selectors) are Unicode marks rather than Cc/Cf controls.
    var defaultIgnorableRanges = [
      [0x00AD, 0x00AD], [0x034F, 0x034F], [0x061C, 0x061C],
      [0x115F, 0x1160], [0x17B4, 0x17B5], [0x180B, 0x180F],
      [0x200B, 0x200F], [0x202A, 0x202E], [0x2060, 0x206F],
      [0x3164, 0x3164], [0xFE00, 0xFE0F], [0xFEFF, 0xFEFF],
      [0xFFA0, 0xFFA0], [0x1BCA0, 0x1BCA3], [0x1D173, 0x1D17A],
      [0xE0000, 0xE0FFF]
    ];
    var forbidden = /[\p{Cc}\p{Cf}\p{Cs}]/u.test(text);
    if (!forbidden) {
      for (var char of text) {
        var codepoint = char.codePointAt(0);
        if (defaultIgnorableRanges.some(function (range) {
          return range[0] <= codepoint && codepoint <= range[1];
        })) {
          forbidden = true;
          break;
        }
      }
    }
    if (forbidden) {
      throw new Error('不能包含不可见控制字符。');
    }
    return allowLayout ? text.trim().replace(/\s+/g, ' ') : text.trim();
  }

  function splitFingerprintList(value, label) {
    var raw = String(value || '').split(/[,，、;；\n]/).map(function (part) {
      return canonicalFingerprintText(part, false);
    }).filter(Boolean);
    if (raw.length > 12) throw new Error(label + '最多填写 12 项。');
    var unique = [];
    raw.forEach(function (item) {
      if (item.length > 120) throw new Error(label + '每项最多 120 个字符。');
      if (unique.indexOf(item) === -1) unique.push(item);
    });
    return unique;
  }

  function validateFingerprintDraft(query, draft) {
    try {
      var summary = canonicalFingerprintText(draft.summary, true);
      if (summary.length < 8) throw new Error('问题摘要至少需要 8 个字符。');
      if (summary.length > 1000) throw new Error('问题摘要最多 1000 个字符。');
      return {
        ok: true,
        fingerprint: {
          source_query: String(query || ''),
          summary: summary,
          variables: splitFingerprintList(draft.variables, '关键变量'),
          constraints: splitFingerprintList(draft.constraints, '约束条件'),
          unknowns: splitFingerprintList(draft.unknowns, '未知项'),
          revision: 1
        }
      };
    } catch (err) {
      return { ok: false, error: err && err.message ? err.message : '请检查结构草案。' };
    }
  }

  function buildFingerprintDraft(query) {
    var text = String(query || '').trim();
    var variables = [];
    var constraints = [];
    var knownVariables = [
      '流失率', '留存率', '转化率', '恢复速度', '反馈延迟', '信任', '价格',
      '成本', '预算', '收入', '利润', '增长率', '故障率', '等待时间', '准确率'
    ];
    knownVariables.forEach(function (term) {
      if (text.indexOf(term) !== -1 && variables.indexOf(term) === -1) variables.push(term);
    });
    if (/恢复.{0,6}(?:慢|速度|时间)/.test(text) && variables.indexOf('恢复速度') === -1) {
      variables.push('恢复速度');
    }
    var timeMatches = text.match(/(?:在|用)?\s*\d+\s*(?:天|周|个月|月|年)(?:内|以内|之内)?/g) || [];
    timeMatches.forEach(function (value) { constraints.push(value.trim()); });
    var explicitLimits = text.match(/(?:不能|不要|不允许|不改变|不增加|不得)[^，。；;!?！？]{1,28}/g) || [];
    explicitLimits.forEach(function (value) { constraints.push(value.trim()); });
    constraints = constraints.filter(function (value, index, all) { return all.indexOf(value) === index; }).slice(0, 6);
    return {
      summary: text.slice(0, 1000),
      variables: variables.slice(0, 6),
      constraints: constraints,
      unknowns: variables.length
        ? ['这些变量之间的因果方向与可观测指标']
        : ['需要确认关键变量、可观测指标与因果方向']
    };
  }

  function saveFingerprintDraft() {
    if (!pendingFingerprintQuery) return;
    try {
      sessionStorage.setItem('structural_fingerprint_draft', JSON.stringify({
        query: pendingFingerprintQuery,
        summary: qs('#ask-fingerprint-summary').value,
        variables: qs('#ask-fingerprint-variables').value,
        constraints: qs('#ask-fingerprint-constraints').value,
        unknowns: qs('#ask-fingerprint-unknowns').value
      }));
    } catch (e) {}
  }

  function openFingerprintReview(query, initialFingerprint, initialError) {
    var panel = qs('#ask-fingerprint');
    var summary = qs('#ask-fingerprint-summary');
    if (!panel || !summary) {
      submitQuery(query, null);
      return;
    }
    pendingFingerprintQuery = String(query || '').trim();
    var draft = initialFingerprint || buildFingerprintDraft(pendingFingerprintQuery);
    try {
      var saved = JSON.parse(sessionStorage.getItem('structural_fingerprint_draft') || 'null');
      if (
        saved && saved.query === pendingFingerprintQuery &&
        ['summary', 'variables', 'constraints', 'unknowns'].every(function (key) {
          return typeof saved[key] === 'string';
        })
      ) draft = saved;
    } catch (e) {}
    summary.value = draft.summary;
    qs('#ask-fingerprint-variables').value = Array.isArray(draft.variables) ? draft.variables.join('，') : (draft.variables || '');
    qs('#ask-fingerprint-constraints').value = Array.isArray(draft.constraints) ? draft.constraints.join('，') : (draft.constraints || '');
    qs('#ask-fingerprint-unknowns').value = Array.isArray(draft.unknowns) ? draft.unknowns.join('，') : (draft.unknowns || '');
    var error = qs('#ask-fingerprint-error');
    if (error) error.textContent = initialError || '';
    panel.hidden = false;
    panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    try { qs('#ask-fingerprint-confirm').focus(); } catch (e) {}
    track('fingerprint_review_opened', { length: pendingFingerprintQuery.length });
  }

  function bindFingerprintReview() {
    var panel = qs('#ask-fingerprint');
    var confirm = qs('#ask-fingerprint-confirm');
    var cancel = qs('#ask-fingerprint-cancel');
    var skip = qs('#ask-fingerprint-skip');
    if (!panel || !confirm) return;
    qsa('input, textarea', panel).forEach(function (field) {
      field.addEventListener('input', saveFingerprintDraft);
      field.addEventListener('keydown', function (ev) {
        if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') {
          ev.preventDefault();
          confirm.click();
        }
      });
    });
    panel.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && cancel) { ev.preventDefault(); cancel.click(); }
    });
    if (cancel) cancel.addEventListener('click', function () {
      saveFingerprintDraft();
      panel.hidden = true;
      pendingFingerprintQuery = '';
      var submit = qs('.ask-searchbox__submit');
      if (submit) { submit.disabled = false; submit.classList.remove('is-loading'); }
      try { qs('#ask-input').focus(); } catch (e) {}
    });
    if (skip) skip.addEventListener('click', function () {
      var query = pendingFingerprintQuery;
      panel.hidden = true;
      pendingFingerprintQuery = '';
      try { sessionStorage.removeItem('structural_fingerprint_draft'); } catch (e) {}
      track('fingerprint_skipped', { length: query.length });
      submitQuery(query, null);
    });
    confirm.addEventListener('click', function () {
      var error = qs('#ask-fingerprint-error');
      var checked = validateFingerprintDraft(pendingFingerprintQuery, {
        summary: qs('#ask-fingerprint-summary').value,
        variables: qs('#ask-fingerprint-variables').value,
        constraints: qs('#ask-fingerprint-constraints').value,
        unknowns: qs('#ask-fingerprint-unknowns').value
      });
      if (!checked.ok) {
        if (error) error.textContent = checked.error;
        return;
      }
      var fingerprint = checked.fingerprint;
      panel.hidden = true;
      try { sessionStorage.removeItem('structural_fingerprint_draft'); } catch (e) {}
      track('fingerprint_confirmed', {
        variables: fingerprint.variables.length,
        constraints: fingerprint.constraints.length,
        unknowns: fingerprint.unknowns.length
      });
      submitQuery(pendingFingerprintQuery, fingerprint);
      pendingFingerprintQuery = '';
    });
  }

  // ============================================================
  // Submit + state transition
  // ============================================================
  function submitQuery(query, fingerprint) {
    if (!query) return;

    // Abort any in-flight stream
    if (currentController) {
      try { currentController.abort(); } catch (e) {}
      currentController = null;
    }
    currentGeneration += 1;
    var generation = currentGeneration;

    // Switch to thread state on first submit
    var emptyEl = qs('#ask-empty');
    var threadEl = qs('#ask-thread');
    var wasEmpty = emptyEl && !emptyEl.hidden;
    if (wasEmpty) {
      emptyEl.hidden = true;
    }
    if (threadEl) {
      threadEl.hidden = false;
    }

    // W3-B: ask_submitted. Source = explicit tag from upstream caller
    // (chip / deeplink) if set, else 'empty' for first-from-landing,
    // else 'followup' for any subsequent submit.
    var source = nextSubmitSource;
    if (!source || source === 'empty') {
      source = wasEmpty ? 'empty' : 'followup';
    }
    track('ask_submitted', { length: query.length, source: source });
    // Reset for next call so we do not stick at 'chip' / 'deeplink'.
    nextSubmitSource = 'followup';

    // Record in history (utils.js)
    try {
      if (typeof window.addToHistory === 'function') {
        window.addToHistory({ query: query, timestamp: Date.now() });
      }
    } catch (e) {}

    // Build new item; stamp the t0 so kb_cards / answer events can
    // compute latency relative to this submit.
    var item = renderThreadItem(query, fingerprint);
    if (item) {
      item._t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
      item._generation = generation;
    }

    // Scroll into view
    try {
      item.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {}

    // Fire SSE
    streamAsk(query, item, fingerprint || null, generation);
  }

  // ---- timing helper -------------------------------------------
  function elapsedSince(t0) {
    if (typeof t0 !== 'number') return 0;
    var t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    return Math.round(t1 - t0);
  }

  function renderThreadItem(query, fingerprint) {
    threadCounter += 1;
    var id = 'ask-item-' + threadCounter;
    var container = qs('#ask-thread-items');
    if (!container) return null;

    var html =
      '<article class="ask-thread-item" id="' + id + '" data-query="' + esc(query) + '">' +
        '<h2 class="ask-thread-item__query">' + esc(query) + '</h2>' +
        (fingerprint ? '<section class="ask-thread-item__fingerprint" aria-label="已确认的结构指纹">' +
          '<strong>已确认的结构指纹</strong><p>' + esc(fingerprint.summary) + '</p>' +
          (fingerprint.variables.length ? '<span>变量：' + esc(fingerprint.variables.join('、')) + '</span>' : '<span>变量：待验证</span>') +
          (fingerprint.constraints.length ? '<span>约束：' + esc(fingerprint.constraints.join('、')) + '</span>' : '<span>约束：待验证</span>') +
          (fingerprint.unknowns.length ? '<span>未知：' + esc(fingerprint.unknowns.join('、')) + '</span>' : '<span>未知：未填写</span>') +
        '</section>' : '') +
        '<div class="ask-thread-item__meta" data-role="meta" hidden></div>' +
        '<div data-role="kb-section" hidden>' +
          '<div class="ask-section-label">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>' +
            '<span>选择一个跨领域候选</span>' +
          '</div>' +
          '<div class="ask-thread-item__cards" data-role="cards"></div>' +
        '</div>' +
        '<div data-role="answer-section" hidden>' +
          '<div class="ask-section-label">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>' +
            '<span>回答</span>' +
          '</div>' +
          '<div class="ask-thread-item__answer" data-role="answer">' +
            '<span class="ask-thread-item__answer-empty">正在思考……</span>' +
          '</div>' +
          '<div class="ask-thread-item__citations-bar" data-role="citations" hidden></div>' +
        '</div>' +
        '<div data-role="similar-section" hidden>' +
          '<div class="ask-section-label">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M8.5 8.5l7 7"/></svg>' +
            '<span>结构相似候选（其他领域）</span>' +
          '</div>' +
          '<div class="ask-thread-item__similar" data-role="similar"></div>' +
        '</div>' +
        '<div data-role="followups-section" hidden>' +
          '<div class="ask-section-label">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>' +
            '<span>追问</span>' +
          '</div>' +
          '<div class="ask-thread-item__followups" data-role="followups"></div>' +
        '</div>' +
        '<div data-role="deep-cta-section" hidden></div>' +
        '<div data-role="error" hidden></div>' +
      '</article>';

    container.insertAdjacentHTML('beforeend', html);
    var item = qs('#' + id);
    if (item) item._fingerprint = fingerprint || null;
    return item;
  }

  // ============================================================
  // SSE consumer
  // ============================================================
  function isCurrentGeneration(item, generation) {
    return !!item && askGenerationMatches(
      item._generation,
      currentGeneration,
      generation
    );
  }

  function streamAsk(query, item, fingerprint, generation) {
    var controller = new AbortController();
    currentController = controller;
    var signal = controller.signal;
    var lang = (document.documentElement.getAttribute('lang') || 'zh').slice(0, 2);
    var requestBody = buildAskRequestBody(query, lang, fingerprint);

    fetch('/api/ask/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify(requestBody),
      signal: signal,
    })
      .then(function (resp) {
        if (!isCurrentGeneration(item, generation)) return null;
        if (!resp.ok) {
          // W6-D: surface structured `input_too_long` body (HTTP 422)
          // as a friendly inline message instead of a bare "HTTP 422".
          if (resp.status === 422) {
            return resp.json().then(function (body) {
              if (body && body.error === 'input_too_long') {
                var msg = body.message
                  || ('输入长度超过 ' + (body.limit || 8000) + ' 字限制，请精简问题或拆成两条。');
                track('input_too_long_server', { limit: body.limit, received: body.received });
                throw new Error(msg);
              }
              var detail = body && Array.isArray(body.detail) ? body.detail : [];
              var fingerprintError = detail.some(function (entry) {
                return entry && Array.isArray(entry.loc) && entry.loc.indexOf('fingerprint') !== -1;
              });
              if (fingerprintError) {
                var editError = new Error('结构草案未通过校验，请按提示修正后重试。');
                editError.code = 'fingerprint_invalid';
                throw editError;
              }
              throw new Error('HTTP 422');
            }, function () {
              throw new Error('HTTP 422');
            });
          }
          throw new Error('HTTP ' + resp.status);
        }
        if (!resp.body) {
          throw new Error('No response body (streaming unsupported)');
        }
        return consumeSSE(resp.body.getReader(), item, generation);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        if (!isCurrentGeneration(item, generation)) return;
        if (err && err.code === 'fingerprint_invalid' && fingerprint) {
          openFingerprintReview(query, fingerprint, err.message);
          return;
        }
        showError(item, '出了点问题，请重试', query, generation);
      });
  }

  function consumeSSE(reader, item, generation) {
    var decoder = new TextDecoder('utf-8');
    var buffer = '';

    function pump() {
      if (!isCurrentGeneration(item, generation)) {
        try { reader.cancel(); } catch (e) {}
        return Promise.resolve();
      }
      return reader.read().then(function (res) {
        if (!isCurrentGeneration(item, generation)) return;
        if (res.done) {
          // Flush trailing event if any
          if (buffer.trim()) handleSSEBlock(buffer, item, generation);
          return;
        }
        buffer += decoder.decode(res.value, { stream: true });
        // SSE events split by blank line (\n\n)
        var idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          var block = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          handleSSEBlock(block, item, generation);
        }
        return pump();
      });
    }

    return pump();
  }

  function normalizeAskStreamError(data) {
    var code = data && typeof data.code === 'string' ? data.code : 'stream_error';
    var retryable = !(data && data.retryable === false);
    var message = data && typeof data.message === 'string' && data.message.trim()
      ? data.message.trim()
      : T('page.ask.error_temporary', '服务暂时出了点问题');
    if (code === 'budget_exceeded') {
      message = T('page.ask.error_budget_exceeded', '今日生成额度已用完，请明天再试。');
      retryable = false;
    }
    return { code: code, message: message, retryable: retryable };
  }

  function handleSSEBlock(block, item, generation) {
    if (!isCurrentGeneration(item, generation)) return;
    // Parse "event: foo\ndata: {json}" — multi-line data is allowed
    // per spec; we concat all data: lines.
    var lines = block.split('\n');
    var event = 'message';
    var dataLines = [];
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (!line) continue;
      if (line.indexOf('event:') === 0) {
        event = line.slice(6).trim();
      } else if (line.indexOf('data:') === 0) {
        dataLines.push(line.slice(5).trim());
      }
    }
    var dataStr = dataLines.join('\n');
    var data = null;
    if (dataStr) {
      try { data = JSON.parse(dataStr); }
      catch (e) { data = { _raw: dataStr }; }
    }

    switch (event) {
      case 'meta':            return handleMetaEvent(item, data);
      case 'retrieval_done':  return handleRetrievalDoneEvent(item, data);
      case 'kb_cards':        return handleKbCardsEvent(item, data);
      case 'generation_progress': return handleGenerationProgress(item, data);
      case 'answer_validated': return handleAnswerValidated(item, data);
      case 'answer_chunk':    return handleAnswerChunk(item, data);
      case 'answer_done':     return handleAnswerDoneEvent(item, data);
      case 'similar_phenomena': return handleSimilarEvent(item, data);
      case 'followups':       return handleFollowupsEvent(item, data);
      case 'done':            return handleDoneEvent(item, data, generation);
      case 'error': {
        var normalizedError = normalizeAskStreamError(data);
        return showError(
          item,
          normalizedError.message,
          item.getAttribute('data-query'),
          generation,
          { retryable: normalizedError.retryable, code: normalizedError.code }
        );
      }
      default:                return;
    }
  }

  // ============================================================
  // Event handlers
  // ============================================================
  function handleMetaEvent(item, data) {
    if (!item || !data) return;
    var metaEl = item.querySelector('[data-role="meta"]');
    if (!metaEl) return;
    var parts = [];
    if (data.rewritten && data.rewritten !== data.query) {
      parts.push('<span class="ask-thread-item__meta-rewritten">改写：' + esc(data.rewritten) + '</span>');
    }
    if (parts.length) {
      metaEl.innerHTML = parts.join('');
      metaEl.hidden = false;
    }
  }

  // W5-B: `retrieval_done` lands ~1-2s after submit and is the user's
  // first concrete "something happened" signal. We replace the answer
  // placeholder ("正在思考...") with a tighter "找到 N 篇 → 正在生成"
  // hint so the perceived latency drops well below the LLM's own first
  // token. Full citation cards still arrive via the subsequent kb_cards.
  function handleRetrievalDoneEvent(item, data) {
    if (!item || !data) return;
    var count = (typeof data.count === 'number') ? data.count : (data.candidates ? data.candidates.length : 0);
    if (!count) return;

    // Reveal the answer section + swap placeholder text so the user sees
    // immediate motion even before the LLM ships its first token.
    var ansSection = item.querySelector('[data-role="answer-section"]');
    if (ansSection) ansSection.hidden = false;
    var answerEl = item.querySelector('[data-role="answer"]');
    var empty = answerEl && answerEl.querySelector('.ask-thread-item__answer-empty');
    if (empty) {
      empty.textContent = '找到 ' + count + ' 个相关现象，正在生成答案……';
    }

    // W3-B-ish: track when retrieval_done landed. Distinct from
    // `kb_cards_received` so we can separate retrieval latency vs cards
    // rendering latency in analytics.
    track('retrieval_done', {
      count: count,
      retrieval_ms: typeof data.retrieval_ms === 'number' ? data.retrieval_ms : 0,
      latency_ms: elapsedSince(item._t0)
    });
  }

  function handleKbCardsEvent(item, data) {
    if (!item || !data) return;
    var cards = data.cards || [];
    if (!cards.length) return;
    var section = item.querySelector('[data-role="kb-section"]');
    var container = item.querySelector('[data-role="cards"]');
    if (!container) return;

    // Store cards on item for similar/deep-cta to reference
    item._cards = cards;

    var candidates = cards.slice(0, 3);
    item._selectedCandidateId = '';
    container.setAttribute('role', 'radiogroup');
    container.setAttribute('aria-label', '选择一个跨领域候选');
    container.innerHTML = candidates.map(function (c, i) {
      var idx = i + 1;
      // Polished route: /phenomenon/{id} is the canonical URL.
      // The backend renders phenomenon.html which reads ?id= for legacy compat.
      var href = c.id ? ('/phenomenon/' + encodeURIComponent(c.id)) : '#';
      var score = (typeof c.score === 'number') ? c.score.toFixed(3) : '';
      var name = c.name || '（未命名查询）';
      // Tooltip: first 100 chars of description, fall back to domain+name.
      var descRaw = c.description || c.summary || c.key_metric || '';
      var tooltip = descRaw ? String(descRaw).slice(0, 100) : (c.domain ? (c.domain + ' · ' + name) : name);
      var aria = '选择候选：' + name;
      return (
        '<div class="ask-kb-card" data-kb-id="' + esc(c.id || '') + '">' +
          '<button type="button" class="ask-kb-card__select ask-kb-card--candidate" role="radio" aria-checked="false"' +
            ' data-kb-id="' + esc(c.id || '') + '"' +
            ' aria-label="' + esc(aria) + '"' +
            ' title="' + esc(tooltip) + '">' +
          '<span class="ask-kb-card__idx">' + idx + '</span>' +
          '<span class="ask-kb-card__body">' +
            (c.domain ? '<span class="ask-kb-card__domain">' + esc(c.domain) + '</span>' : '') +
            '<span class="ask-kb-card__name">' + esc(name) + '</span>' +
            '<span class="ask-kb-card__basis">检索候选 · ' + (score ? '检索分 ' + score : '分数未提供') + '，尚未验证</span>' +
          '</span></button>' +
          '<a class="ask-kb-card__source" href="' + href + '" target="_blank" rel="noopener"' +
            ' aria-label="查看内部 KB 记录：' + esc(name) + '">查看 KB 记录 ↗</a>' +
          '<dl class="ask-kb-card__evidence">' +
            '<div><dt>结构匹配线索</dt><dd>' + esc(c.match_basis || '该案例由检索排序返回；尚未完成结构映射核验。') + '</dd></div>' +
            (descRaw ? '<div><dt>KB 记录摘要</dt><dd>' + esc(String(descRaw).slice(0, 240)) + '</dd></div>' : '') +
            '<div><dt>反证 / 尚缺证据</dt><dd>' + esc(c.counter_evidence || '尚未完成变量、因果方向与边界条件的逐项核对。') + '</dd></div>' +
            '<div><dt>适用边界</dt><dd>' + esc(c.applicability_boundary || '只有内部 KB 摘要中的关键关系也存在于你的问题时，方法才可能迁移。') + '</dd></div>' +
          '</dl>' +
          (window.StructuralEvidence ? window.StructuralEvidence.render(c.evidence || window.StructuralEvidence.fallback(c), { compact: true }) : '') +
        '</div>'
      );
    }).join('');

    qsa('.ask-kb-card--candidate', container).forEach(function (card) {
      function selectCandidate() {
        qsa('.ask-kb-card--candidate', container).forEach(function (other) {
          var selected = other === card;
          other.setAttribute('aria-checked', selected ? 'true' : 'false');
          var shell = other.closest('.ask-kb-card');
          if (shell) shell.classList.toggle('ask-kb-card--selected', selected);
        });
        item._selectedCandidateId = card.getAttribute('data-kb-id') || '';
        renderDeepAnalysisCTA(item);
        track('candidate_selected', {
          phenomenon_id: item._selectedCandidateId || 'unknown',
          position: qsa('.ask-kb-card--candidate', container).indexOf(card) + 1
        });
      }
      card.addEventListener('click', selectCandidate);
      card.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectCandidate();
        }
      });
    });
    track('candidate_view', { count: candidates.length });

    if (section) section.hidden = false;

    // Show answer skeleton placeholder
    var ansSection = item.querySelector('[data-role="answer-section"]');
    if (ansSection) ansSection.hidden = false;

    // W3-B: kb_cards_received — latency from submit to first cards.
    track('kb_cards_received', { count: cards.length, latency_ms: elapsedSince(item._t0) });

    // W6-D (session #7 P1 backlog): citation click-through tracking.
    // We delegate one capture-phase listener on each thread item. The
    // listener handles three click surfaces:
    //   - `.ask-kb-card` (top KB card rows)
    //   - `.ask-citation` (inline [N] markers inside the answer)
    //   - `.ask-citation-link` (citations bar at the bottom)
    // Each click fires a Plausible event `citation_click` with only the
    // selected KB identifier, position and surface. Never derive analytics
    // values from the user's query: short hashes of natural-language input
    // can be reversed with a dictionary and would contradict the privacy UI.
    if (!item._ckBound) {
      item.addEventListener('click', function (ev) {
        var citEl = ev.target.closest('.ask-citation, .ask-citation-link, .ask-kb-card__source');
        if (!citEl) return;
        // Resolve position (1-based among siblings of the same kind).
        var siblings = item.querySelectorAll(
          citEl.classList.contains('ask-kb-card__source') ? '.ask-kb-card__source'
            : citEl.classList.contains('ask-citation-link') ? '.ask-citation-link'
            : '.ask-citation'
        );
        var position = 0;
        for (var i = 0; i < siblings.length; i++) {
          if (siblings[i] === citEl) { position = i + 1; break; }
        }
        // Pull phenomenon_id from the element (data-kb-id on cards, or
        // href `/phenomenon/{id}` for inline citations / citation bar).
        var phenomenonId = citEl.getAttribute('data-kb-id') ||
          (citEl.closest('.ask-kb-card') && citEl.closest('.ask-kb-card').getAttribute('data-kb-id'));
        if (!phenomenonId) {
          var href = citEl.getAttribute('href') || '';
          var m = href.match(/\/phenomenon\/([^\/?#]+)/);
          if (m) phenomenonId = decodeURIComponent(m[1]);
        }
        var surface = citEl.classList.contains('ask-kb-card__source') ? 'kb_card_source'
          : citEl.classList.contains('ask-citation-link') ? 'citation_bar'
          : 'inline';

        track('citation_click', {
          phenomenon_id: phenomenonId || 'unknown',
          position: position,
          surface: surface,
        });

      }, true);
      item._ckBound = true;
    }
  }

  function handleGenerationProgress(item, data) {
    if (!item || !data) return;
    var answerEl = item.querySelector('[data-role="answer"]');
    if (!answerEl) return;
    var placeholder = answerEl.querySelector('.ask-thread-item__answer-empty');
    if (placeholder) placeholder.textContent = '正在校验完整答案与引用…';
  }

  function handleAnswerValidated(item, data) {
    if (!item || !data || data.ok !== true) return;
    item._answerValidated = true;
  }

  function handleAnswerChunk(item, data) {
    if (!item || !data || typeof data.delta !== 'string') return;
    // Never place streamed model deltas in the DOM. The backend emits these
    // only after validation, but the browser still waits for answer_done so a
    // stale or mixed stream cannot publish a partial answer.
    if (item._answerValidated && !item._firstValidatedChunkAt) {
      item._firstValidatedChunkAt = elapsedSince(item._t0);
      track('first_validated_answer_chunk', { latency_ms: item._firstValidatedChunkAt });
    }
  }

  function handleAnswerDoneEvent(item, data) {
    if (!item || !data) return;
    var answerEl = item.querySelector('[data-role="answer"]');
    if (!answerEl) return;

    var validated = validateAnswerDonePayload(
      data,
      item._cards || [],
      item._answerValidated === true
    );
    if (!validated) {
      return showError(
        item,
        '答案或引用未通过完整性校验，请重试',
        item.getAttribute('data-query'),
        item._generation
      );
    }
    var fullText = validated.fullText;
    var citations = validated.citations;

    // Only this complete, source-bound event is allowed to publish prose.
    // A local OOS/no-card refusal has no retrieval cards, so neither the
    // retrieval_done nor kb_cards handler reveals this section. Visibility
    // follows the trusted terminal answer, not successful retrieval.
    var answerSection = item.querySelector('[data-role="answer-section"]');
    if (answerSection) answerSection.hidden = false;
    answerEl.innerHTML = renderCitationsAsLinks(fullText, citations, item._cards);

    // Citations bar
    if (citations.length) {
      var barEl = item.querySelector('[data-role="citations"]');
      if (barEl) {
        var displayCardsById = {};
        (item._cards || []).forEach(function (c) { displayCardsById[c.id] = c; });
        barEl.innerHTML = citations.map(function (cit) {
          var src = displayCardsById[cit.kb_id];
          var label = cit.label || (src ? src.name : 'source');
          // Canonical /phenomenon/{id} route.
          var href = cit.kb_id ? ('/phenomenon/' + encodeURIComponent(cit.kb_id)) : '#';
          var descRaw = src ? (src.description || src.summary || src.key_metric || '') : '';
          var tooltip = descRaw
            ? String(descRaw).slice(0, 100)
            : (src && src.domain ? (src.domain + ' · ' + label) : label);
          var aria = 'View KB phenomenon: ' + label;
          return (
            '<a class="ask-citation-link" href="' + href + '" target="_blank" rel="noopener"' +
              ' aria-label="' + esc(aria) + '"' +
              ' title="' + esc(tooltip) + '">' +
              '<span class="ask-citation-link__idx">[' + cit.idx + ']</span>' +
              '<span>' + esc(label) + '</span>' +
            '</a>'
          );
        }).join('');
        barEl.hidden = false;
      }
    }

    // Render deep-analysis CTA — links to /analyze using top KB card as B-side seed.
    renderDeepAnalysisCTA(item);

    // W3-B: answer_completed — full answer rendered (citations resolved).
    track('answer_completed', {
      chars: fullText.length,
      citations_count: citations.length,
      latency_ms: elapsedSince(item._t0)
    });
  }

  function handleSimilarEvent(item, data) {
    if (!item || !data) return;
    var phens = data.phenomena || [];
    if (!phens.length) return;
    var section = item.querySelector('[data-role="similar-section"]');
    var container = item.querySelector('[data-role="similar"]');
    if (!container) return;

    container.innerHTML = phens.slice(0, 3).map(function (p, i) {
      var href = p.kb_id ? ('/phenomenon/' + encodeURIComponent(p.kb_id)) : '#';
      var name = p.name || '';
      var descRaw = p.description || p.summary || p.key_metric || '';
      var tooltip = descRaw ? String(descRaw).slice(0, 100) : (p.domain ? (p.domain + ' · ' + name) : name);
      var aria = 'View KB phenomenon: ' + name;
      return (
        '<a class="ask-similar-card" href="' + href + '" target="_blank" rel="noopener"' +
          ' data-similar-idx="' + i + '"' +
          ' aria-label="' + esc(aria) + '"' +
          ' title="' + esc(tooltip) + '">' +
          (p.domain ? '<span class="ask-similar-card__domain">' + esc(p.domain) + '</span>' : '') +
          '<span class="ask-similar-card__name">' + esc(name) + '</span>' +
          (p.key_metric ? '<span class="ask-similar-card__metric">' + esc(p.key_metric) + '</span>' : '') +
        '</a>'
      );
    }).join('');

    if (section) section.hidden = false;

    // W3-B: bind clicks for telemetry — capture phase so we record before
    // navigation (target=_blank still allows the new tab to open).
    qsa('.ask-similar-card[data-similar-idx]', container).forEach(function (a) {
      a.addEventListener('click', function () {
        track('similar_card_clicked', { card_idx: parseInt(a.getAttribute('data-similar-idx') || '0', 10) });
      });
    });
  }

  function handleFollowupsEvent(item, data) {
    if (!item || !data) return;
    var qs_ = data.questions || [];
    if (!qs_.length) return;
    var section = item.querySelector('[data-role="followups-section"]');
    var container = item.querySelector('[data-role="followups"]');
    if (!container) return;

    container.innerHTML = qs_.slice(0, 3).map(function (q, i) {
      return (
        '<button type="button" class="ask-followup-btn" data-followup-q="' + esc(q) + '" data-followup-idx="' + i + '">' +
          '<span>' + esc(q) + '</span>' +
          '<svg class="ask-followup-btn__arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 5l7 7-7 7"/></svg>' +
        '</button>'
      );
    }).join('');

    if (section) section.hidden = false;
    bindFollowupClicks(item);
  }

  function handleDoneEvent(item, data, generation) {
    if (!isCurrentGeneration(item, generation)) return;
    // Remove caret if still present (safety net)
    var caret = item.querySelector('.ask-caret');
    if (caret) caret.remove();
    if (data && typeof data.latency_ms === 'number') {
      var metaEl = item.querySelector('[data-role="meta"]');
      if (metaEl) {
        var stamp = ' <span style="opacity:0.7">' + (data.latency_ms / 1000).toFixed(1) + 's</span>';
        // Append latency to whatever meta is already shown
        metaEl.innerHTML += stamp;
        metaEl.hidden = false;
      }
    }
    currentController = null;
  }

  // ============================================================
  // Citation rendering — replace [1], [2], ... with linked badges
  // ============================================================
  function renderCitationsAsLinks(text, citations, cards) {
    if (!text) return '';
    var cardsById = {};
    (cards || []).forEach(function (c) { cardsById[c.id] = c; });
    var citsByIdx = {};
    (citations || []).forEach(function (c) { citsByIdx[c.idx] = c; });

    // Tokenize text around [N] patterns; escape between, leave brackets as anchors.
    // Pattern: \[(\d+)\]
    var out = '';
    var re = /\[(\d+)\]/g;
    var lastIdx = 0;
    var m;
    while ((m = re.exec(text)) !== null) {
      out += esc(text.slice(lastIdx, m.index));
      var idx = parseInt(m[1], 10);
      var cit = citsByIdx[idx];
      var src = cit ? cardsById[cit.kb_id] : null;
      var href = (cit && cit.kb_id) ? ('/phenomenon/' + encodeURIComponent(cit.kb_id)) : '#';
      // Tooltip: first 100 chars of description, fall back to name·domain.
      var descRaw = src ? (src.description || src.summary || src.key_metric || '') : '';
      var title = descRaw
        ? String(descRaw).slice(0, 100)
        : (src ? (src.name + (src.domain ? ' · ' + src.domain : '')) : '引用 ' + idx);
      var srcName = src ? src.name : ('引用 ' + idx);
      var aria = 'View KB phenomenon: ' + srcName;
      out += '<a class="ask-citation" href="' + href + '" target="_blank" rel="noopener"' +
        ' aria-label="' + esc(aria) + '"' +
        ' title="' + esc(title) + '">[' + idx + ']</a>';
      lastIdx = m.index + m[0].length;
    }
    out += esc(text.slice(lastIdx));
    return out;
  }

  // ============================================================
  // Deep analysis CTA — bridge to /analyze for full pipeline
  // ============================================================
  function renderDeepAnalysisCTA(item) {
    var section = item.querySelector('[data-role="deep-cta-section"]');
    if (!section) return;
    var query = item.getAttribute('data-query') || '';
    var cards = item._cards || [];
    var selectedKbId = item._selectedCandidateId || '';
    // /analyze NEEDS a B-side phenomenon id to run — without one analyze.js
    // bails to its empty state. Hide the CTA rather than ship a dead link.
    if (!cards.length) { section.hidden = true; return; }
    if (!selectedKbId) {
      section.innerHTML = '<p class="ask-thread-item__candidate-prompt" role="status">先选择一个候选，再生成研究报告。系统不会替你默认选择 Top 1。</p>';
      section.hidden = false;
      return;
    }
    // /analyze URL contract lives in utils/buildAnalyzeUrl.js — single
    // source of truth across the site (search.js / home.js / phenomenon.js).
    var url = window.buildAnalyzeUrl({
      id: selectedKbId,
      q: query,
      fingerprint: item._fingerprint || null
    });
    var separator = url.indexOf('?') === -1 ? '?' : '&';
    var privateUrl = url + separator + 'persist=0';
    var savedUrl = url + separator + 'persist=1';

    section.innerHTML =
      '<a class="ask-thread-item__deep-cta" href="' + privateUrl + '">' +
        '<span>生成研究报告</span>' +
        '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 5l7 7-7 7"/></svg>' +
      '</a>' +
      '<label class="ask-thread-item__save-choice">' +
        '<input type="checkbox" data-role="save-report-choice">' +
        '<span><strong>保存到这台设备的报告列表</strong>并生成持链可读的分享链接。未勾选时不会在服务器保存报告。</span>' +
      '</label>';
    section.hidden = false;

    // W3-B: bind deep analysis click — we send `from_thread_item: true`
    // so we can disambiguate from a direct /analyze visit.
    var ctaLink = section.querySelector('.ask-thread-item__deep-cta');
    var saveChoice = section.querySelector('[data-role="save-report-choice"]');
    if (ctaLink && saveChoice) {
      saveChoice.addEventListener('change', function () {
        ctaLink.setAttribute('href', saveChoice.checked ? savedUrl : privateUrl);
      });
    }
    if (ctaLink) {
      ctaLink.addEventListener('click', function () {
        track('deep_analysis_triggered', {
          from_thread_item: true,
          phenomenon_id: selectedKbId,
          persist_opt_in: !!(saveChoice && saveChoice.checked)
        });
      });
    }
  }

  // ============================================================
  // Followup click binding
  // ============================================================
  function bindFollowupClicks(item) {
    var btns = qsa('[data-followup-q]', item);
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var q = btn.getAttribute('data-followup-q') || '';
        if (q.trim()) {
          // W3-B: track followup click + tag the next submit as 'followup'.
          track('followup_clicked', { question_idx: parseInt(btn.getAttribute('data-followup-idx') || '0', 10) });
          nextSubmitSource = 'followup';
          submitQuery(q.trim());
        }
      });
    });
  }

  // ============================================================
  // Error handling + retry
  // ============================================================
  function showError(item, message, query, generation, options) {
    generation = generation || (item && item._generation);
    if (!isCurrentGeneration(item, generation)) return;
    options = options || {};
    var retryable = options.retryable !== false;
    var errEl = item.querySelector('[data-role="error"]');
    if (!errEl) return;
    errEl.innerHTML =
      '<div class="ask-thread-item__error">' +
        '<span>' + esc('出错了：' + (message || '请重试')) + '</span>' +
        (retryable
          ? '<button type="button" class="ask-thread-item__error-retry" data-ask-retry="true">重试</button>'
          : '') +
      '</div>';
    errEl.hidden = false;
    if (options.code) errEl.dataset.errorCode = String(options.code);
    var retryBtn = errEl.querySelector('[data-ask-retry]');
    if (retryBtn) {
      retryBtn.addEventListener('click', function () {
        var q = String(query || '');
        if (q.trim()) {
          // Remove this item, then resubmit
          var container = qs('#ask-thread-items');
          if (item && item.parentNode === container) container.removeChild(item);
          submitQuery(q.trim(), item._fingerprint || null);
        }
      });
    }
    // Also kill caret if any
    var caret = item.querySelector('.ask-caret');
    if (caret) caret.remove();
    currentController = null;
  }

  // ============================================================
  // Boot
  // ============================================================
  if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAskPage);
  document.addEventListener('DOMContentLoaded', bindFingerprintReview);
  } else {
    initAskPage();
    bindFingerprintReview();
  }

  // Expose for debugging
  window.__ask = {
    submitQuery: submitQuery,
    abort: function () {
      currentGeneration += 1;
      if (currentController) currentController.abort();
      currentController = null;
    },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      askGenerationMatches: askGenerationMatches,
      buildAskRequestBody: buildAskRequestBody,
      validateAnswerDonePayload: validateAnswerDonePayload,
      validateFingerprintDraft: validateFingerprintDraft,
      normalizeAskStreamError: normalizeAskStreamError,
    };
  }
})();
