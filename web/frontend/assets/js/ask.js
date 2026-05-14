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
  // Count threads so each item gets a stable DOM id.
  var threadCounter = 0;

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

  // ============================================================
  // Init
  // ============================================================
  function initAskPage() {
    var form = qs('#ask-form');
    if (form) {
      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var input = qs('#ask-input');
        var q = input ? input.value.trim() : '';
        if (!q) return;
        submitQuery(q);
      });
      // Cmd/Ctrl+Enter submits
      var input = qs('#ask-input');
      if (input) {
        input.addEventListener('keydown', function (ev) {
          if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') {
            ev.preventDefault();
            form.requestSubmit();
          }
        });
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
        if (input) input.value = '';
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

    bindExampleChips();

    // If URL has ?q=..., auto-run that query (deep-link support)
    try {
      var qParam = new URLSearchParams(window.location.search).get('q');
      if (qParam && qParam.trim()) {
        // Tag the upcoming submit; submitQuery normalises 'empty' for
        // first-from-landing, so we keep 'deeplink' explicit instead.
        nextSubmitSource = 'deeplink';
        submitQuery(qParam.trim());
      }
    } catch (e) {}
  }

  function bindExampleChips() {
    qsa('.ask-chip[data-example-q]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        var q = chip.getAttribute('data-example-q') || '';
        if (q.trim()) {
          // W3-B: tag the source + record chip label so we know which
          // canned examples actually draw clicks.
          track('example_chip_clicked', { chip_label: (chip.textContent || '').trim().slice(0, 40) });
          nextSubmitSource = 'chip';
          submitQuery(q.trim());
        }
      });
    });
  }

  // ============================================================
  // Submit + state transition
  // ============================================================
  function submitQuery(query) {
    if (!query) return;

    // Abort any in-flight stream
    if (currentController) {
      try { currentController.abort(); } catch (e) {}
      currentController = null;
    }

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
    var item = renderThreadItem(query);
    if (item) item._t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();

    // Scroll into view
    try {
      item.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {}

    // Fire SSE
    streamAsk(query, item);
  }

  // ---- timing helper -------------------------------------------
  function elapsedSince(t0) {
    if (typeof t0 !== 'number') return 0;
    var t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    return Math.round(t1 - t0);
  }

  function renderThreadItem(query) {
    threadCounter += 1;
    var id = 'ask-item-' + threadCounter;
    var container = qs('#ask-thread-items');
    if (!container) return null;

    var html =
      '<article class="ask-thread-item" id="' + id + '" data-query="' + esc(query) + '">' +
        '<h2 class="ask-thread-item__query">' + esc(query) + '</h2>' +
        '<div class="ask-thread-item__meta" data-role="meta" hidden></div>' +
        '<div data-role="kb-section" hidden>' +
          '<div class="ask-section-label">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>' +
            '<span>知识库命中 (top 5)</span>' +
          '</div>' +
          '<div class="ask-thread-item__cards" data-role="cards"></div>' +
        '</div>' +
        '<div data-role="answer-section" hidden>' +
          '<div class="ask-section-label">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>' +
            '<span>回答</span>' +
          '</div>' +
          '<div class="ask-thread-item__answer" data-role="answer">' +
            '<span class="ask-thread-item__answer-empty">正在思考...</span>' +
          '</div>' +
          '<div class="ask-thread-item__citations-bar" data-role="citations" hidden></div>' +
        '</div>' +
        '<div data-role="similar-section" hidden>' +
          '<div class="ask-section-label">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M8.5 8.5l7 7"/></svg>' +
            '<span>结构相同的现象</span>' +
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
    return qs('#' + id);
  }

  // ============================================================
  // SSE consumer
  // ============================================================
  function streamAsk(query, item) {
    currentController = new AbortController();
    var signal = currentController.signal;
    var lang = (document.documentElement.getAttribute('lang') || 'zh').slice(0, 2);

    fetch('/api/ask/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({ query: query, lang: lang }),
      signal: signal,
    })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error('HTTP ' + resp.status);
        }
        if (!resp.body) {
          throw new Error('No response body (streaming unsupported)');
        }
        return consumeSSE(resp.body.getReader(), item);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        showError(item, err && err.message ? err.message : '未知错误', query);
      });
  }

  function consumeSSE(reader, item) {
    var decoder = new TextDecoder('utf-8');
    var buffer = '';

    function pump() {
      return reader.read().then(function (res) {
        if (res.done) {
          // Flush trailing event if any
          if (buffer.trim()) handleSSEBlock(buffer, item);
          return;
        }
        buffer += decoder.decode(res.value, { stream: true });
        // SSE events split by blank line (\n\n)
        var idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          var block = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          handleSSEBlock(block, item);
        }
        return pump();
      });
    }

    return pump();
  }

  function handleSSEBlock(block, item) {
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
      case 'answer_chunk':    return handleAnswerChunk(item, data);
      case 'answer_done':     return handleAnswerDoneEvent(item, data);
      case 'similar_phenomena': return handleSimilarEvent(item, data);
      case 'followups':       return handleFollowupsEvent(item, data);
      case 'done':            return handleDoneEvent(item, data);
      case 'error':           return showError(item, (data && data.message) || '后端错误', item.getAttribute('data-query'));
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
      empty.textContent = '找到 ' + count + ' 篇相关现象，正在生成答案…';
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

    container.innerHTML = cards.map(function (c, i) {
      var idx = i + 1;
      // Polished route: /phenomenon/{id} is the canonical URL.
      // The backend renders phenomenon.html which reads ?id= for legacy compat.
      var href = c.id ? ('/phenomenon/' + encodeURIComponent(c.id)) : '#';
      var score = (typeof c.score === 'number') ? Math.round(c.score * 100) + '%' : '';
      var name = c.name || '(未命名)';
      // Tooltip: first 100 chars of description, fall back to domain+name.
      var descRaw = c.description || c.summary || c.key_metric || '';
      var tooltip = descRaw ? String(descRaw).slice(0, 100) : (c.domain ? (c.domain + ' · ' + name) : name);
      var aria = 'View KB phenomenon: ' + name;
      return (
        '<a class="ask-kb-card" href="' + href + '" target="_blank" rel="noopener"' +
          ' data-kb-id="' + esc(c.id || '') + '"' +
          ' aria-label="' + esc(aria) + '"' +
          ' title="' + esc(tooltip) + '">' +
          '<span class="ask-kb-card__idx">' + idx + '</span>' +
          (c.domain ? '<span class="ask-kb-card__domain">' + esc(c.domain) + '</span>' : '') +
          '<span class="ask-kb-card__name">' + esc(name) + '</span>' +
          (score ? '<span class="ask-kb-card__score">相似度 ' + score + '</span>' : '') +
        '</a>'
      );
    }).join('');

    if (section) section.hidden = false;

    // Show answer skeleton placeholder
    var ansSection = item.querySelector('[data-role="answer-section"]');
    if (ansSection) ansSection.hidden = false;

    // W3-B: kb_cards_received — latency from submit to first cards.
    track('kb_cards_received', { count: cards.length, latency_ms: elapsedSince(item._t0) });

    // Attach citation-click tracker once per item. We track on the
    // *card* now (not just the [N] inline citation in renderCitations)
    // so we capture both clicks. Idempotent — re-binding the same
    // delegate is harmless because we only attach once via _ckBound.
    if (!item._ckBound) {
      item.addEventListener('click', function (ev) {
        var citEl = ev.target.closest('.ask-citation, .ask-citation-link');
        if (!citEl) return;
        var idxText = (citEl.textContent || '').match(/\d+/);
        track('citation_clicked', { idx: idxText ? parseInt(idxText[0], 10) : 0 });
      }, true);
      item._ckBound = true;
    }
  }

  function handleAnswerChunk(item, data) {
    if (!item || !data || typeof data.delta !== 'string') return;
    var answerEl = item.querySelector('[data-role="answer"]');
    if (!answerEl) return;

    // Remove placeholder on first chunk
    var empty = answerEl.querySelector('.ask-thread-item__answer-empty');
    if (empty) empty.remove();

    // W5-B: capture time-to-first-token explicitly; this is the headline
    // latency metric we are optimizing for in this sprint.
    if (!item._firstChunkAt) {
      item._firstChunkAt = elapsedSince(item._t0);
      track('first_answer_chunk', { latency_ms: item._firstChunkAt });
    }

    // Append to a running text buffer (we keep raw text, render citations on done)
    if (!item._answerBuf) item._answerBuf = '';
    item._answerBuf += data.delta;

    // Render raw text with blinking caret. Citations rendering happens
    // at answer_done so we have the full citation map.
    answerEl.innerHTML = esc(item._answerBuf) + '<span class="ask-caret" aria-hidden="true"></span>';
  }

  function handleAnswerDoneEvent(item, data) {
    if (!item || !data) return;
    var answerEl = item.querySelector('[data-role="answer"]');
    if (!answerEl) return;

    var fullText = data.full_text || item._answerBuf || '';
    var citations = data.citations || [];

    // Remove caret + render with [N] → linked badges
    answerEl.innerHTML = renderCitationsAsLinks(fullText, citations, item._cards);

    // Citations bar
    if (citations.length) {
      var barEl = item.querySelector('[data-role="citations"]');
      if (barEl) {
        var cardsById = {};
        (item._cards || []).forEach(function (c) { cardsById[c.id] = c; });
        barEl.innerHTML = citations.map(function (cit) {
          var src = cardsById[cit.kb_id];
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

  function handleDoneEvent(item, data) {
    if (!item) return;
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
    var topKbId = cards.length ? cards[0].id : '';
    // Use clean /analyze URL (no .html suffix) — matches site-wide convention
    // in search.js, discoveries.js, home.js, phenomenon.js.
    var url = '/analyze?text_a=' + encodeURIComponent(query);
    if (topKbId) url += '&b_id=' + encodeURIComponent(topKbId);

    section.innerHTML =
      '<a class="ask-thread-item__deep-cta" href="' + url + '">' +
        '<span>运行深度分析</span>' +
        '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 5l7 7-7 7"/></svg>' +
      '</a>';
    section.hidden = false;

    // W3-B: bind deep analysis click — we send `from_thread_item: true`
    // so we can disambiguate from a direct /analyze visit.
    var ctaLink = section.querySelector('.ask-thread-item__deep-cta');
    if (ctaLink) {
      ctaLink.addEventListener('click', function () {
        track('deep_analysis_triggered', { from_thread_item: true });
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
  function showError(item, message, query) {
    if (!item) return;
    var errEl = item.querySelector('[data-role="error"]');
    if (!errEl) return;
    errEl.innerHTML =
      '<div class="ask-thread-item__error">' +
        '<span>' + esc('出错了：' + (message || '请重试')) + '</span>' +
        '<button type="button" class="ask-thread-item__error-retry" data-retry-q="' + esc(query || '') + '">重试</button>' +
      '</div>';
    errEl.hidden = false;
    var retryBtn = errEl.querySelector('[data-retry-q]');
    if (retryBtn) {
      retryBtn.addEventListener('click', function () {
        var q = retryBtn.getAttribute('data-retry-q') || '';
        if (q.trim()) {
          // Remove this item, then resubmit
          var container = qs('#ask-thread-items');
          if (item && item.parentNode === container) container.removeChild(item);
          submitQuery(q.trim());
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
  } else {
    initAskPage();
  }

  // Expose for debugging
  window.__ask = {
    submitQuery: submitQuery,
    abort: function () { if (currentController) currentController.abort(); },
  };
})();
