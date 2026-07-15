function T(key, fallback) { try { if (window.i18n && typeof window.i18n.t === "function") { var v = window.i18n.t(key); if (v && v !== key) return v; } } catch(e) {} return fallback; }

// Retrieval scores are query-relative ranking signals, not calibrated
// similarity, confidence, or probability. Public UI exposes position only.
function rankText(index) {
  return T('page.search.rank_within_query', '本次排序 #{rank}')
    .replace('{rank}', String(index + 1));
}

function resolveSearchSynthesisCandidate(candidate, results) {
  if (!candidate || typeof candidate !== 'object' ||
      typeof candidate.source_kb_id !== 'string' || !Array.isArray(results)) return null;
  const sourceId = candidate.source_kb_id;
  const matches = [];
  results.forEach((record, index) => {
    if (record && record.id === sourceId) matches.push({ record, index });
  });
  return matches.length === 1 ? matches[0] : null;
}

function synthesisGenerationMatches(expectedRun, expectedGeneration, currentRun, currentGeneration) {
  return expectedRun === currentRun && expectedGeneration === currentGeneration;
}

function guardSynthesisCallbacks(expectedRun, expectedGeneration, getCurrentState, callbacks) {
  const handlers = callbacks || {};
  const guarded = {};
  ['onText', 'onDone', 'onError'].forEach((name) => {
    guarded[name] = function guardedSynthesisCallback(...args) {
      let current;
      try { current = getCurrentState(); } catch (_) { return false; }
      if (!current || !synthesisGenerationMatches(
        expectedRun,
        expectedGeneration,
        current.run,
        current.generation,
      )) return false;
      if (typeof handlers[name] === 'function') handlers[name].apply(this, args);
      return true;
    };
  });
  return guarded;
}

if (typeof window !== 'undefined') {
  window.resolveSearchSynthesisCandidate = resolveSearchSynthesisCandidate;
}

function evidenceHtml(item, compact) {
  if (!window.StructuralEvidence) return '';
  return window.StructuralEvidence.render(
    (item && item.evidence) || window.StructuralEvidence.fallback({
      ...(item || {}), score: null, relevance: null,
    }),
    { compact: compact !== false, suppressActions: true }
  );
}

/**
 * Structural — Search results page (Phase 2)
 *
 * Layout:
 *   1. Sticky top: the user's question + search bar
 *   2. Synthesized main insight (LLM, streamed after results load)
 *   3. Result list, each card with a relevance snippet
 */

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function scrubSensitiveSearchUrl() {
  try {
    const url = new URL(window.location.href);
    ['q', 'context', 'from_query', 'text_a'].forEach((name) => url.searchParams.delete(name));
    history.replaceState(history.state || {}, '', url.pathname + url.search + url.hash);
  } catch (e) { /* remain fail-closed in the UI */ }
}

function currentSearchLang() {
  return (window.i18n && typeof window.i18n.getLang === 'function' && window.i18n.getLang() === 'en')
    ? 'en' : 'zh';
}

function hasPrivateContextKey(url) {
  try {
    return Boolean(new URL(url, window.location.origin).searchParams.get('context'));
  } catch (e) {
    return false;
  }
}

function renderPrivateContextUnavailable() {
  const summary = $('#search-summary');
  if (summary) summary.innerHTML = '';
  const container = $('#search-results');
  if (!container) return;
  container.innerHTML = `
    <div class="search-error search-context-lost" role="status" aria-live="polite">
      <h2 class="search-error__title">${T('page.search.context_lost_title', '没有可恢复的研究问题')}</h2>
      <p class="search-error__text">${T('page.search.context_lost_text', '问题不会保留在网址中。链接已过期、被重复使用，或浏览器安全存储不可用时，请返回首页重新提交。')}</p>
      <div class="search-error__actions">
        <a href="/" class="btn btn--primary">${T('page.search.context_lost_action', '返回首页重新提交')}</a>
      </div>
    </div>
  `;
}

function navigateToPrivateSearch(query, options) {
  if (typeof window.buildPrivateSearchUrl !== 'function') {
    renderPrivateContextUnavailable();
    return false;
  }
  const url = window.buildPrivateSearchUrl({
    query,
    lang: currentSearchLang(),
    force: Boolean(options && options.force),
    source: (options && options.source) || 'rewrite',
  });
  if (!url) {
    renderPrivateContextUnavailable();
    return false;
  }
  if (!hasPrivateContextKey(url)) {
    renderPrivateContextUnavailable();
    return false;
  }
  window.location.assign(url);
  return true;
}

function privateAnalyzeHref(id, query) {
  if (typeof window.buildAnalyzeUrl === 'function') {
    return window.buildAnalyzeUrl({ id: id, q: query });
  }
  // Privacy fail-closed: public id is safe, user text is never a URL fallback.
  return '/analyze?id=' + encodeURIComponent(id || '');
}

// === SESSION-17 V2 helpers ===

// A candidate is a "real cross-domain source" when the backend marks
// `cross_domain === true`. When the field is absent we treat it as true —
// the backend contract says cross_domain defaults to true when undecidable,
// so being permissive here matches that intent.
function isCrossDomain(r) {
  return r && r.cross_domain !== false;
}

// Out-of-scope: the question isn't a phenomenon-shaped problem (arithmetic,
// chitchat, trivia). Show a friendly explanation, not an empty result list.
function renderOutOfScope(query, data) {
  const summaryEl = $('#search-summary');
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="search-question">
        <div class="search-question__label">${T('page.search.your_question', '你的问题')}</div>
        <div class="search-question__text">${escapeHtml(query)}</div>
      </div>
    `;
  }
  const reason = (data && data.scope_reason) || 'ok';
  const reasonCopy = {
    arithmetic: T('page.search.oos_arithmetic', '这看起来是一道算术 / 计算题——直接算就好，没有「另一个学科里的同款现象」可以借。'),
    chitchat: T('page.search.oos_chitchat', '这像是闲聊。Structural 擅长的是把一个卡住的复杂现象映射到别的学科，闲聊没有可借的结构。'),
    trivia: T('page.search.oos_trivia', '这像是一个查事实的问题。Structural 不是搜索引擎——它擅长的是给「行为像某种模式」的难题找跨学科解法。'),
  };
  const msg = reasonCopy[reason] || T('page.search.oos_default', '这个问题不太适合用跨学科结构同构来解——它没有一个可以映射到别的领域的「现象结构」。');

  const resultsEl = $('#search-results');
  if (!resultsEl) return;
  resultsEl.innerHTML = `
    <div class="assess-gate">
      <div class="assess-gate__icon" aria-hidden="true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
        </svg>
      </div>
      <h2 class="assess-gate__title">${T('page.search.oos_title', '这个问题更适合别的工具')}</h2>
      <p class="assess-gate__coaching">${msg}</p>
      <div class="assess-gate__suggestion">
        <div class="assess-gate__suggestion-label">${T('page.search.oos_what_fits', '💡 Structural 擅长什么')}</div>
        <div class="assess-gate__suggestion-text">${T('page.search.oos_what_fits_bounded', '描述一个「行为像某种模式」的难题——比如增长卡住、留存下滑或趋势反转。Structural 会寻找跨领域候选，用来生成需要验证的新假设。')}</div>
      </div>
      <div class="assess-gate__actions">
        <a href="/" class="btn btn--primary">${T('page.search.back_home', '返回首页')}</a>
        <a href="/about" class="btn btn--ghost">${T('page.search.learn_structural', '了解 Structural')}</a>
      </div>
    </div>
  `;
}

// A small inline tag marking whether a candidate is truly cross-domain
// relative to the user's surface domain.
function crossDomainTag(r) {
  if (isCrossDomain(r)) {
    return `<span class="xd-tag xd-tag--cross">${T('page.search.xd_cross', '跨领域')}</span>`;
  }
  return `<span class="xd-tag xd-tag--same">${T('page.search.xd_same', '同领域')}</span>`;
}

function renderSkeleton() {
  const container = $('#search-results');
  if (!container) return;
  container.innerHTML = `
    <div class="search-skeleton">
      ${Array.from({ length: 5 }).map(() => `
        <div class="search-skeleton__card">
          <div class="skeleton search-skeleton__line" style="width: 30%; height: 10px"></div>
          <div class="skeleton search-skeleton__line" style="width: 50%; height: 18px"></div>
          <div class="skeleton search-skeleton__line" style="width: 100%"></div>
          <div class="skeleton search-skeleton__line" style="width: 85%"></div>
        </div>
      `).join('')}
    </div>
  `;
}

// Tracks live timers so we can stop them cleanly
let _synthTimerStop = null;
let _phaseIntervalId = null;

// Phase labels rotated based on elapsed seconds — gives the user a sense of
// progress instead of a single static "loading" message.
function getSynthPhases() {
  return [
    { until: 4, text: T('page.search.phase_understanding', '正在理解你的问题') },
    { until: 9, text: T('page.search.phase_picking', '正在整理候选记录') },
    { until: 16, text: T('page.search.phase_organizing', '正在核对候选边界') },
    { until: 999, text: T('page.search.phase_almost', '马上就好') },
  ];
}

function loadingSynthHtml(candidateStatus) {
  return `
    <div class="search-synth__loading" role="status">
      <div class="search-synth__dots" aria-hidden="true"><span></span><span></span><span></span></div>
      <span class="search-synth__phase-text" id="search-synth-phase">${T('page.search.phase_understanding', '正在理解你的问题')}</span>
      <span class="elapsed-timer" id="search-synth-timer">${T('page.search.elapsed_start', '已等待 0s')}</span>
      <span class="search-synth__typical" id="search-synth-status">${escapeHtml(candidateStatus)}</span>
    </div>
  `;
}

function ensureSearchHeaderShell(query, candidateStatus) {
  const container = $('#search-summary');
  if (!container) return null;
  container.classList.add('search-summary--active');
  let question = container.querySelector('.search-question');
  let questionText = document.getElementById('search-question-text');
  let rewrite = document.getElementById('search-question-rewrite');
  let synth = document.getElementById('search-synth');

  if (!question || !questionText || !rewrite || !synth) {
    container.innerHTML = `
      <div class="search-question">
        <div class="search-question__label" id="search-question-label"></div>
        <div class="search-question__text" id="search-question-text">${escapeHtml(query)}</div>
        <div class="search-question__rewrite" id="search-question-rewrite">
          <span id="search-question-rewrite-label"></span><em id="search-question-rewrite-text"></em>
        </div>
      </div>
      <div class="search-synth search-synth--loading" id="search-synth">
        ${loadingSynthHtml(candidateStatus)}
      </div>
    `;
    question = container.querySelector('.search-question');
    questionText = document.getElementById('search-question-text');
    rewrite = document.getElementById('search-question-rewrite');
    synth = document.getElementById('search-synth');
  }

  let editBtn = document.getElementById('search-edit-btn');
  if (!editBtn && question) {
    editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'search-question__edit-btn';
    editBtn.id = 'search-edit-btn';
    editBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
    const label = document.createElement('span');
    label.textContent = T('page.search.edit', '编辑');
    editBtn.appendChild(label);
    question.insertBefore(editBtn, question.firstChild);
  }
  return { container, question, questionText, rewrite, synth, editBtn };
}

function updateSearchRewrite(query, rewritten) {
  const label = document.getElementById('search-question-rewrite-label');
  const text = document.getElementById('search-question-rewrite-text');
  if (!label || !text) return;
  const changed = typeof rewritten === 'string' && rewritten && rewritten !== query;
  label.textContent = changed
    ? T('page.search.rewritten_as', '已改写为研究问题：')
    : T('page.search.retrieval_wording', '检索表达：');
  text.textContent = changed
    ? rewritten
    : T('page.search.retrieval_original', '先按原问题检索');
}

function renderQuestionHeader(query, data) {
  const rewritten = data.rewritten_query;
  const candidateStatus = Number.isInteger(data.count)
    ? `${data.count} ${T('page.search.candidates_typical', '个候选 · 通常 8–15s')}`
    : T('page.search.candidates_loading', '候选检索中 · 结果通过校验后显示');
  const shell = ensureSearchHeaderShell(query, candidateStatus);
  if (!shell) return;
  document.getElementById('search-question-label').textContent =
    T('page.search.your_question', '你的问题');
  shell.questionText.textContent = query;
  updateSearchRewrite(query, rewritten);
  if (shell.editBtn) {
    shell.editBtn.setAttribute('aria-label', T('page.search.edit_this_question', '编辑这个问题'));
    shell.editBtn.onclick = () => enterEditMode(query);
  }

  if (data.count === 0) {
    shell.synth.className = 'search-synth search-synth--degraded';
    shell.synth.innerHTML = `
      <div class="search-synth__content">
        <div class="search-synth__label">${T('page.search.empty_title', '没有找到可用的知识库候选')}</div>
        <div class="search-synth__insight"><p>${T('page.search.empty_summary', '没有候选通过当前检索与校验；请补充变量、时间尺度或边界条件。')}</p></div>
      </div>`;
    return;
  }

  if (!Number.isInteger(data.count) && !shell.synth.classList.contains('search-synth--loading')) {
    shell.synth.className = 'search-synth search-synth--loading';
    shell.synth.innerHTML = loadingSynthHtml(candidateStatus);
  }
  const status = document.getElementById('search-synth-status');
  if (status) status.textContent = candidateStatus;
  if (Number.isInteger(data.count)) return;

  if (_synthTimerStop) { _synthTimerStop(); _synthTimerStop = null; }
  const synthTimerEl = document.getElementById('search-synth-timer');
  if (synthTimerEl && window.startElapsedTimer) {
    _synthTimerStop = window.startElapsedTimer(synthTimerEl);
  }
  if (_phaseIntervalId) { clearInterval(_phaseIntervalId); _phaseIntervalId = null; }
  const phaseEl = document.getElementById('search-synth-phase');
  const phaseStart = Date.now();
  const tickPhase = () => {
    if (!phaseEl || !document.body.contains(phaseEl)) {
      clearInterval(_phaseIntervalId);
      _phaseIntervalId = null;
      return;
    }
    const elapsed = (Date.now() - phaseStart) / 1000;
    const phases = getSynthPhases();
    const phase = phases.find(item => elapsed < item.until) || phases[phases.length - 1];
    if (phaseEl.textContent !== phase.text) phaseEl.textContent = phase.text;
  };
  tickPhase();
  _phaseIntervalId = setInterval(tickPhase, 500);
}

// === Edit mode: turn the question header into an inline form ===
function currentSearchQueryStatus(value) {
  if (typeof window.researchQueryStatus === 'function') {
    return window.researchQueryStatus(value);
  }
  const normalized = typeof value === 'string'
    ? value.normalize('NFKC').trim().split(/\s+/u).filter(Boolean).join(' ')
    : '';
  const count = Array.from(normalized).length;
  return {
    value: normalized,
    count,
    limit: 8000,
    valid: Boolean(normalized) && count <= 8000,
    error: !normalized ? 'blank_query' : count > 8000 ? 'query_too_long' : null,
  };
}

function updateSearchEditFeedback(input, submit) {
  const status = currentSearchQueryStatus(input ? input.value : '');
  const host = document.getElementById('search-edit-query-feedback');
  const counter = document.getElementById('search-edit-query-counter');
  const error = document.getElementById('search-edit-query-error');
  const actionableError = status.error && status.error !== 'blank_query';
  if (counter) counter.textContent = `${status.count.toLocaleString()} / ${status.limit.toLocaleString()}`;
  if (host) host.dataset.state = actionableError ? 'error' : 'ready';
  if (error) {
    error.hidden = !actionableError;
    error.textContent = status.error === 'query_too_long'
      ? T('page.search.query_too_long', '问题超过 8,000 字，请缩短后再提交。')
      : actionableError
        ? T('page.search.query_invalid_characters', '请移除不支持的隐藏字符或标记。')
        : '';
  }
  if (input) input.setAttribute('aria-invalid', actionableError ? 'true' : 'false');
  if (submit) submit.disabled = Boolean(actionableError);
  return status;
}

function enterEditMode(currentQuery) {
  const card = document.querySelector('.search-question');
  if (!card) return;
  card.innerHTML = `
    <div class="search-question__label">${T('page.search.edit_your_question', '编辑你的问题')}</div>
    <textarea class="search-question__editor" rows="3">${escapeHtml(currentQuery)}</textarea>
    <div class="search-question__query-feedback" id="search-edit-query-feedback" role="status" aria-live="polite">
      <span id="search-edit-query-counter">0 / 8,000</span>
      <span id="search-edit-query-error" hidden></span>
    </div>
    <div class="search-question__edit-actions">
      <button type="button" class="btn btn--ghost btn--sm" id="search-edit-cancel">${T('page.search.cancel', '取消')}</button>
      <button type="button" class="btn btn--primary btn--sm" id="search-edit-submit">${T('page.search.ask_again', '再问一次')}</button>
    </div>
    <div class="search-question__edit-hint"><kbd>⌘</kbd> + <kbd>Enter</kbd> ${T('page.search.submit_hint', '提交')}</div>
  `;
  const ta = card.querySelector('textarea');
  const submit = document.getElementById('search-edit-submit');
  if (ta) {
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
    ta.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        document.getElementById('search-edit-submit')?.click();
      }
    });
    ta.addEventListener('input', () => updateSearchEditFeedback(ta, submit));
    updateSearchEditFeedback(ta, submit);
  }
  document.getElementById('search-edit-cancel')?.addEventListener('click', () => {
    window.location.reload();
  });
  submit?.addEventListener('click', () => {
    const status = updateSearchEditFeedback(ta, submit);
    if (!status.valid) {
      if (status.error !== 'blank_query' && typeof window.announcePrivateNavigationError === 'function') {
        window.announcePrivateNavigationError(status.error);
      }
      return;
    }
    navigateToPrivateSearch(status.value, { source: 'rewrite' });
  });
}

function toParagraphs(text) {
  // Delegate to the global mdParagraphs (in utils.js) which handles
  // **bold** / *italic* / `code` / \n→<br> and splits on \n\n.
  return (window.mdParagraphs ? window.mdParagraphs(text) : '');
}

function safeModelInline(text) {
  return window.mdInline ? window.mdInline(text) : escapeHtml(text);
}

function renderCandidateBoundary(candidate) {
  if (!candidate || typeof candidate !== 'object') return '';
  const gaps = Array.isArray(candidate.evidence_gaps)
    ? candidate.evidence_gaps.filter((gap) => typeof gap === 'string' && gap).slice(0, 4)
    : [];
  const parts = [];
  if (gaps.length) {
    parts.push(`
      <div class="candidate-boundary__item">
        <div class="candidate-boundary__label">${T('page.search.evidence_gaps', '尚缺证据')}</div>
        <ul class="candidate-boundary__list">${gaps.map((gap) => `<li>${safeModelInline(gap)}</li>`).join('')}</ul>
      </div>
    `);
  }
  if (candidate.alternative_explanation) {
    parts.push(`
      <div class="candidate-boundary__item">
        <div class="candidate-boundary__label">${T('page.search.competing_explanation', '竞争解释')}</div>
        <p>${safeModelInline(candidate.alternative_explanation)}</p>
      </div>
    `);
  }
  if (candidate.failure_condition) {
    parts.push(`
      <div class="candidate-boundary__item">
        <div class="candidate-boundary__label">${T('page.search.failure_condition', '何时否定')}</div>
        <p>${safeModelInline(candidate.failure_condition)}</p>
      </div>
    `);
  }
  return parts.length ? `<div class="candidate-boundary">${parts.join('')}</div>` : '';
}

let _searchMathRuntime = null;

function containsRenderableMath(container) {
  const text = container && typeof container.textContent === 'string'
    ? container.textContent : '';
  return /(?:\$\$[^$]+\$\$|\$[^$\n]{1,200}\$|\\\([^)]*\\\)|\\\[[^\]]*\\\])/.test(text);
}

function loadSearchMathScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-search-math="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === 'true') resolve();
      else {
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', reject, { once: true });
      }
      return;
    }
    const script = document.createElement('script');
    script.src = src;
    script.defer = true;
    script.dataset.searchMath = src;
    script.addEventListener('load', () => {
      script.dataset.loaded = 'true';
      resolve();
    }, { once: true });
    script.addEventListener('error', reject, { once: true });
    document.head.appendChild(script);
  });
}

function renderSearchMath(container) {
  if (!containsRenderableMath(container)) return;
  if (typeof window.renderMathInElement === 'function') {
    if (window.renderMath) window.renderMath(container);
    return;
  }
  if (!_searchMathRuntime) {
    if (!document.querySelector('link[data-search-math-css]')) {
      const stylesheet = document.createElement('link');
      stylesheet.rel = 'stylesheet';
      stylesheet.href = '/assets/vendor/katex/katex.min.css?v=0.16.11';
      stylesheet.dataset.searchMathCss = 'true';
      document.head.appendChild(stylesheet);
    }
    _searchMathRuntime = loadSearchMathScript('/assets/vendor/katex/katex.min.js?v=0.16.11')
      .then(() => loadSearchMathScript('/assets/vendor/katex/contrib/auto-render.min.js?v=0.16.11'));
  }
  _searchMathRuntime
    .then(() => { if (window.renderMath) window.renderMath(container); })
    .catch(() => { console.warn('[search] math rendering unavailable'); });
}

function renderSynthBlock(synth) {
  const container = $('#search-synth');
  // Stop synth elapsed timer regardless of outcome
  if (_synthTimerStop) { _synthTimerStop(); _synthTimerStop = null; }
  if (!container) return;
  if (!synth || !synth.main_insight) {
    container.remove();
    return;
  }
  // Remove loading state
  container.classList.remove('search-synth--loading');
  const degraded = synth.synthesis_status === 'degraded';
  container.classList.toggle('search-synth--degraded', degraded);
  container.innerHTML = `
    <div class="search-synth__content">
      <div class="search-synth__label">${degraded
        ? T('page.search.synthesis_degraded_label', '候选比较 · 已安全降级')
        : T('page.search.synthesis_validated_label', '候选比较 · 格式已校验')}</div>
      <div class="search-synth__insight">${toParagraphs(synth.main_insight)}</div>
      ${synth.why_these_matter ? `
        <div class="search-synth__why">
          <span class="search-synth__why-tag">${T('page.search.review_boundary', '核对边界')}</span>
          <div class="search-synth__why-text">${toParagraphs(synth.why_these_matter)}</div>
        </div>
      ` : ''}
    </div>
  `;
  renderSearchMath(container);
}

function renderSynthTransportFailure(onRetry) {
  if (_synthTimerStop) { _synthTimerStop(); _synthTimerStop = null; }
  const container = $('#search-synth');
  if (!container) return;
  container.classList.remove('search-synth--loading');
  container.classList.add('search-synth--degraded');
  container.innerHTML = `
    <div class="search-synth__content">
      <div class="search-synth__label">${T('page.search.synthesis_unavailable_label', '候选比较 · 暂不可用')}</div>
      <div class="search-synth__insight"><p>${T('page.search.synthesis_unavailable_text', '检索候选仍可逐条查看；模型比较因网络或超时未完成，未展示任何未校验内容。')}</p></div>
      <button type="button" class="btn btn--secondary search-synth__retry" id="search-synth-retry">${T('page.search.retry_comparison', '重试候选比较')}</button>
    </div>
  `;
  document.getElementById('search-synth-retry')?.addEventListener('click', onRetry);
}

// State shared between renderResults and renderResultsWithSynth
let _lastQuery = '';
let _lastResults = [];
let _lastSynth = null;
let _lastV2PairsForTop = [];
let _lastStats = null;          // SESSION-17 V2: search `stats` (cross/same counts)
let _currentSearchContext = null;
let _lastForce = false;
let _activeSearchRun = 0;
let _activeSynthGeneration = 0;
let _activeSynthStream = null;

function cancelActiveSynthesis() {
  _activeSynthGeneration += 1;
  if (_activeSynthStream && _activeSynthStream.abort) {
    try { _activeSynthStream.abort(); } catch (e) { /* already closed */ }
  }
  _activeSynthStream = null;
}

function updatePrivateSearchState(patch) {
  if (typeof window.updatePrivateNavigationState !== 'function') return null;
  const updated = window.updatePrivateNavigationState(patch, { kind: 'search' });
  if (updated) _currentSearchContext = updated;
  return updated;
}

function renderResults(query, data) {
  _lastQuery = query;
  _lastResults = data.results || [];
  _lastSynth = null;
  _lastV2PairsForTop = Array.isArray(data.v2_pairs_for_top) ? data.v2_pairs_for_top : [];
  _lastStats = data.stats || null;

  const container = $('#search-results');
  if (!container) return;

  if (!data.results || data.results.length === 0) {
    container.innerHTML = `
      <div class="search-empty">
        <svg class="search-empty__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/><path d="M11 8v6M8 11h6" opacity="0.3"/>
        </svg>
        <h2 class="search-empty__title">${T('page.search.empty_title', '没有找到可用的知识库候选')}</h2>
        <p class="search-empty__text">${T('page.search.empty_text', '知识库暂时没有返回可排序的候选。<br>试着描述现象本身的<strong>行为模式</strong>，并补充变量、时间尺度或边界条件。')}</p>
        <div class="search-empty__actions">
          <a href="/" class="btn btn--primary">${T('page.search.back_home', '返回首页')}</a>
          <a href="/about" class="btn btn--ghost">${T('page.search.learn_structural', '了解 Structural')}</a>
        </div>
      </div>
    `;
    return;
  }

  // Render the raw result list immediately so the user can read + click
  // cards while synth is still streaming above. When the SSE `done` event
  // arrives, renderResultsWithSynth() rebuilds this container with the
  // primary recommendation tagged. Until then the cards show in their
  // unranked form with a soft "AI 排序中" hint at the top.
  container.innerHTML = `
    <div class="search-page__results">
      ${renderCrossDomainBanner(query, null)}
      <div class="search-page__results-title">
        <span>${T('page.search.evidence_candidates_title', '跨领域候选')} · ${data.results.length} ${T('page.search.candidates_unit', '个候选')}</span>
        <span class="search-page__results-hint">${T('page.search.results_pre_synth_hint', '模型正在比较候选 · 现在已可逐条核查')}</span>
      </div>
      <p class="search-ranking-note">${T('page.search.ranking_note', '序位只表示本次查询中的相对先后；不可跨查询比较，也不是成功概率、置信度或证据等级。')}</p>
      <div class="result-list">
        ${data.results.map((r, index) => `
          <a href="${privateAnalyzeHref(r.id, query)}" class="result-card result-card--pre-synth">
            <div class="result-card__main">
              <div class="result-card__meta">
                <span class="result-card__meta-domain">${escapeHtml(r.domain)}</span>
                <span class="result-card__meta-dot"></span>
                <span class="result-card__meta-type">${T('page.search.structure_prefix', '结构')} ${escapeHtml(r.type_id)}</span>
                ${crossDomainTag(r)}
              </div>
              <h3 class="result-card__name">${escapeHtml(r.name)}</h3>
              <p class="result-card__description">${escapeHtml(r.description)}</p>
              ${evidenceHtml(r)}
            </div>
            <div class="result-card__aside">
              <div class="result-card__rank" aria-label="${rankText(index)}">
                <span class="result-card__rank-num">#${index + 1}</span>
                <span class="result-card__rank-label">${T('page.search.within_query', '本次排序')}</span>
              </div>
              <svg class="result-card__arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
            </div>
          </a>
        `).join('')}
      </div>
    </div>
  `;
}

// SESSION-17 V2: the cross-domain guidance banner. Sits above the candidate
// list. Three states:
//   (a) no real cross-domain candidate  → honest "solve it in its own domain"
//   (b) a cross-domain candidate exists  → name it + a one-line preview of
//       what the report will reframe the problem through
//   (c) recommendedResult given          → richer preview tied to that pick
// `recommendedResult` is optional — when the synth has picked a primary, we
// pass it so the preview names the exact source.
function renderCrossDomainBanner(query, recommendedResult, resultState) {
  const results = resultState && Array.isArray(resultState.results)
    ? resultState.results : (_lastResults || []);
  const stats = resultState && resultState.stats
    ? resultState.stats : (_lastStats || {});
  const surfaceDomain = stats.surface_domain || null;

  // Count cross-domain candidates — prefer the backend stat, fall back to
  // counting the results ourselves.
  let crossCount = (typeof stats.cross_domain_count === 'number')
    ? stats.cross_domain_count
    : results.filter(isCrossDomain).length;

  // (a) No real cross-domain source — be honest, don't push a flat answer.
  if (crossCount === 0 && results.length > 0) {
    return `
      <div class="xd-banner xd-banner--same-domain">
        <div class="xd-banner__icon" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
        </div>
        <div class="xd-banner__body">
          <div class="xd-banner__title">${T('page.search.xd_none_title', '这个问题更适合在它本来的领域里解决')}</div>
          <p class="xd-banner__text">${T('page.search.xd_none_text_bounded', 'Structural 没有返回其他领域的检索候选；下面结果与问题处于同一领域。此时应优先核对本领域证据，而不是强行做跨领域迁移。')}</p>
        </div>
      </div>
    `;
  }

  if (crossCount === 0) return '';

  // (b)/(c) There IS a cross-domain source. Name the recommended one.
  // Pick the recommended result, else the first cross-domain candidate.
  const pick = (recommendedResult && isCrossDomain(recommendedResult))
    ? recommendedResult
    : results.find(isCrossDomain);
  if (!pick) return '';

  const domainStrong = `<strong>${escapeHtml(pick.domain || '')}</strong>`;
  const surfacePart = surfaceDomain
    ? T('page.search.xd_preview_with_surface', '你的问题表面属于「{surface}」。')
        .replace('{surface}', escapeHtml(surfaceDomain))
    : '';
  return `
    <div class="xd-banner xd-banner--cross">
      <div class="xd-banner__icon" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 00-2 2v3M21 8V5a2 2 0 00-2-2h-3M3 16v3a2 2 0 002 2h3M16 21h3a2 2 0 002-2v-3"/><path d="M9 12h6"/></svg>
      </div>
      <div class="xd-banner__body">
        <div class="xd-banner__title">${T('page.search.xd_preview_title', '生成报告时会发生什么')}</div>
        <p class="xd-banner__text">
          ${surfacePart}
          ${T('page.search.xd_preview_text_bounded', '点开报告后，Structural 会借用 {domain} 的候选方法生成待检验假设；是否适用仍需核对变量、边界与反证。')
              .replace('{domain}', domainStrong)}
        </p>
        <p class="xd-banner__hint">${T('page.search.xd_preview_hint_bounded', '提示：「跨领域」只表示来源领域不同，不代表迁移已经成立。')}</p>
      </div>
    </div>
  `;
}

// Render the "V2 模型识别的跨域对" section. Returns HTML string.
// Pulls from _lastV2PairsForTop (populated in renderResults).
function renderV2PairsForTop(groupsOverride) {
  const groups = Array.isArray(groupsOverride) ? groupsOverride : (_lastV2PairsForTop || []);
  if (!groups.length) return '';

  const blocks = groups.map(group => {
    const pairs = Array.isArray(group.pairs) ? group.pairs : [];
    if (!pairs.length) return '';
    const cards = pairs.map((p, pairIndex) => {
      const href = `/analyze?a_id=${encodeURIComponent(group.phenomenon_id)}&id=${encodeURIComponent(p.other_id || '')}`;
      return `
        <a href="${href}" class="v2-pair-card">
          <div class="v2-pair-card__rank" aria-label="${T('page.search.v2_pair_rank', '本组候选 #{rank}').replace('{rank}', String(pairIndex + 1))}">#${pairIndex + 1}</div>
          <div class="v2-pair-card__domain">${escapeHtml(p.other_domain || '')}</div>
          <h5 class="v2-pair-card__name">${escapeHtml(p.other_name || '')}</h5>
          ${p.reason ? `<p class="v2-pair-card__reason">${escapeHtml(p.reason)}</p>` : ''}
          ${evidenceHtml(p)}
        </a>
      `;
    }).join('');

    return `
      <div class="v2-phenom-block">
        <div class="v2-phenom-block__title">
          <span class="v2-phenom-block__name">${escapeHtml(group.phenomenon_name || '')}</span>
          <span class="v2-phenom-block__domain">（${escapeHtml(group.phenomenon_domain || '')}）</span>
          <span class="v2-phenom-block__linker">${T('page.search.v2_also_connects', '还连接到')}</span>
        </div>
        <div class="v2-pair-grid">${cards}</div>
      </div>
    `;
  }).filter(Boolean).join('');

  if (!blocks) return '';

  return `
    <section class="v2-pairs-section">
      <div class="v2-pairs-section__header">
        <div class="v2-pairs-section__label">${T('page.search.v2_pairs_label', 'V2 模型提出的跨域候选')}</div>
        <h3 class="v2-pairs-section__title">${T('page.search.v2_pairs_title', '还可以核查这些候选')}</h3>
        <p class="v2-pairs-section__sub">${T('page.search.v2_pairs_sub', 'V2 管道内部筛选的跨学科候选，不是独立验证；点击查看映射、证据缺口与反例。')}</p>
        <p class="v2-pairs-section__ranking-note">${T('page.search.v2_ranking_note', '候选序位只在当前分组内有效，不代表相似度、置信度或验证结论。')}</p>
      </div>
      ${blocks}
    </section>
  `;
}

function renderResultsWithSynth(renderState) {
  // Stop the phase rotation since synth has completed
  if (_phaseIntervalId) { clearInterval(_phaseIntervalId); _phaseIntervalId = null; }

  const state = renderState && typeof renderState === 'object' ? renderState : {};
  const query = typeof state.query === 'string' ? state.query : _lastQuery;
  const results = Array.isArray(state.results) ? state.results : _lastResults;
  const synth = state.synth || _lastSynth;
  const stats = state.stats || _lastStats;
  const v2Groups = Array.isArray(state.v2PairsForTop) ? state.v2PairsForTop : _lastV2PairsForTop;
  const container = state.container || $('#search-results');
  if (!container || !results.length) return '';

  const primary = synth && synth.primary_recommendation;
  const alternatives = (synth && synth.alternative_angles) || [];
  const snippetsById = {};
  if (synth && Array.isArray(synth.relevance_snippets)) {
    for (const s of synth.relevance_snippets) {
      if (s && typeof s.source_kb_id === 'string' && typeof s.snippet === 'string') {
        snippetsById[s.source_kb_id] = s.snippet;
      }
    }
  }
  const primaryBinding = resolveSearchSynthesisCandidate(primary, results);

  // Fallback: synth failed or malformed
  if (!primaryBinding) {
    const v2PairsHtmlFallback = renderV2PairsForTop(v2Groups);
    container.innerHTML = `
      <div class="search-page__results">
        ${renderCrossDomainBanner(query, null, { results, stats })}
        <div class="search-page__results-title">
          <span>${T('page.search.evidence_candidates_title', '跨领域候选')} · ${results.length} ${T('page.search.candidates_unit', '个候选')}</span>
        </div>
        <p class="search-ranking-note">${T('page.search.ranking_note', '序位只表示本次查询中的相对先后；不可跨查询比较，也不是成功概率、置信度或证据等级。')}</p>
        <div class="result-list">
          ${results.map((r, index) => `
            <a href="${privateAnalyzeHref(r.id, query)}" class="result-card">
              <div class="result-card__main">
                <div class="result-card__meta">
                  <span class="result-card__meta-domain">${escapeHtml(r.domain)}</span>
                  <span class="result-card__meta-dot"></span>
                  <span class="result-card__meta-type">${T('page.search.structure_prefix', '结构')} ${escapeHtml(r.type_id)}</span>
                  ${crossDomainTag(r)}
                </div>
                <h3 class="result-card__name">${escapeHtml(r.name)}</h3>
                <p class="result-card__description">${escapeHtml(r.description)}</p>
                ${evidenceHtml(r)}
              </div>
              <div class="result-card__aside">
                <div class="result-card__rank" aria-label="${rankText(index)}">
                  <span class="result-card__rank-num">#${index + 1}</span>
                  <span class="result-card__rank-label">${T('page.search.within_query', '本次排序')}</span>
                </div>
                <svg class="result-card__arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
              </div>
            </a>
          `).join('')}
        </div>
        ${v2PairsHtmlFallback}
      </div>
    `;
    return container.innerHTML;
  }

  const pickedIds = new Set([primary.source_kb_id]);
  for (const alt of alternatives) {
    if (resolveSearchSynthesisCandidate(alt, results)) pickedIds.add(alt.source_kb_id);
  }
  const others = results.filter((record) => !pickedIds.has(record && record.id));

  // === Primary card ===
  const pr = primaryBinding.record;
  const primaryIndex = primaryBinding.index;
  let primaryHtml = '';
  if (pr) {
    primaryHtml = `
      <section class="rec-primary" style="animation: fadeInUp 500ms var(--ease-out-expo) both">
        <div class="rec-primary__label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          <span>${T('page.search.primary_rec_label', '建议先核查这个候选')}</span>
        </div>
        <a href="${privateAnalyzeHref(pr.id, query)}" class="rec-primary__card">
          <div class="rec-primary__body">
            <div class="rec-primary__meta">
              <span class="rec-primary__domain">${escapeHtml(pr.domain)}</span>
              ${crossDomainTag(pr)}
              <span class="rec-primary__rank">${rankText(primaryIndex)}</span>
            </div>
            <h3 class="rec-primary__name">${escapeHtml(pr.name)}</h3>
            ${evidenceHtml(pr)}

            ${primary.reason ? `
              <div class="rec-primary__block">
                <div class="rec-primary__block-label">${T('page.search.primary_why', '为什么先核查')}</div>
                <div class="rec-primary__block-text">${window.mdInline(primary.reason)}</div>
              </div>
            ` : ''}

            ${renderCandidateBoundary(primary)}

            ${primary.what_youll_learn ? `
              <div class="rec-primary__block rec-primary__block--takeaway">
                <div class="rec-primary__block-label">${T('page.search.primary_takeaway', '下一步核查')}</div>
                <div class="rec-primary__block-text">${window.mdInline(primary.what_youll_learn)}</div>
              </div>
            ` : ''}
          </div>

          <div class="rec-primary__cta">
            <span>${T('page.search.primary_cta', '立即深度分析')}</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
          </div>
        </a>
      </section>
    `;
  }

  // === Alternative angles ===
  let altHtml = '';
  if (alternatives.length > 0) {
    const altCards = alternatives.map((alt, i) => {
      const binding = resolveSearchSynthesisCandidate(alt, results);
      if (!binding) return '';
      const r = binding.record;
      return `
        <a href="${privateAnalyzeHref(r.id, query)}" class="rec-alt" style="animation: fadeInUp 500ms var(--ease-out-expo) ${i * 80 + 100}ms both">
          <div class="rec-alt__angle">${escapeHtml(alt.angle_label || T('page.search.alt_angle_default', '补充视角'))}</div>
          <h4 class="rec-alt__name">${escapeHtml(r.name)}</h4>
          ${evidenceHtml(r)}
          <div class="rec-alt__meta">${escapeHtml(r.domain)} · ${rankText(binding.index)} ${crossDomainTag(r)}</div>
          ${alt.reason ? `<p class="rec-alt__reason">${window.mdInline(alt.reason)}</p>` : ''}
          ${renderCandidateBoundary(alt)}
          ${alt.next_check ? `
            <div class="candidate-boundary__next">
              <span>${T('page.search.next_check', '下一步核查')}</span>
              ${safeModelInline(alt.next_check)}
            </div>
          ` : ''}
          <div class="rec-alt__cta">
            ${T('page.search.deep_analysis', '深度分析')}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
          </div>
        </a>
      `;
    }).filter(Boolean).join('');

    if (altCards) {
      altHtml = `
        <section class="rec-alts">
          <div class="rec-alts__label">${T('page.search.alt_angles_label', '补充视角 — 从不同角度看你的问题')}</div>
          <div class="rec-alts__grid">${altCards}</div>
        </section>
      `;
    }
  }

  // === Other candidates (collapsible) ===
  let othersHtml = '';
  if (others.length > 0) {
    othersHtml = `
      <section class="rec-others">
        <button type="button" class="rec-others__toggle" id="rec-others-toggle">
          <span>${T('page.search.others_prefix', '其他')} ${others.length} ${T('page.search.others_suffix', '个待核查候选')}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>
        </button>
        <div class="rec-others__list" id="rec-others-list" hidden>
          ${others.map(r => {
            const origIdx = results.indexOf(r) + 1;
            const snippet = snippetsById[r.id];
            return `
              <a href="${privateAnalyzeHref(r.id, query)}" class="rec-other">
                <div class="rec-other__main">
                  <div class="rec-other__meta">
                    <span class="rec-other__domain">${escapeHtml(r.domain)}</span>
                    ${crossDomainTag(r)}
                  </div>
                  <div class="rec-other__name">${escapeHtml(r.name)}</div>
                  ${snippet ? `<p class="rec-other__snippet">${escapeHtml(snippet)}</p>` : `<p class="rec-other__desc">${escapeHtml(r.description)}</p>`}
                  ${evidenceHtml(r)}
                </div>
                <div class="rec-other__rank">#${origIdx}<span>${T('page.search.within_query', '本次排序')}</span></div>
              </a>
            `;
          }).join('')}
        </div>
      </section>
    `;
  }

  const v2PairsHtml = renderV2PairsForTop(v2Groups);

  // SESSION-17 V2: banner names the recommended cross-domain source. `pr`
  // is the synth's primary pick — pass it so the preview is specific.
  const xdBanner = renderCrossDomainBanner(query, pr || null, { results, stats });

  container.innerHTML = `
    <div class="search-page__results">
      ${xdBanner}
      ${primaryHtml}
      ${altHtml}
      ${v2PairsHtml}
      ${othersHtml}
    </div>
  `;

  renderSearchMath(container);

  const toggle = document.getElementById('rec-others-toggle');
  const list = document.getElementById('rec-others-list');
  if (toggle && list) {
    toggle.addEventListener('click', () => {
      const hidden = list.hasAttribute('hidden');
      if (hidden) {
        list.removeAttribute('hidden');
        toggle.classList.add('rec-others__toggle--open');
      } else {
        list.setAttribute('hidden', '');
        toggle.classList.remove('rec-others__toggle--open');
      }
    });
  }
  return container.innerHTML;
}

function renderError() {
  const container = $('#search-results');
  if (!container) return;
  // SESSION-17 copy SR-03: never surface the raw JS exception to the user —
  // it goes to the console only; the UI shows a fixed friendly message.
  console.error('Search request failed.');
  container.innerHTML = `
    <div class="search-error">
      <h2 class="search-error__title">${T('page.search.error_title', '搜索失败')}</h2>
      <p class="search-error__text">${T('page.search.error_text', '可能是网络问题或服务暂时不可用，请稍后重试。')}</p>
      <div class="search-error__actions" style="display: flex; gap: 12px; justify-content: center; margin-top: 20px;">
        <button type="button" class="btn btn--primary" id="search-retry-btn">${T('page.search.retry', '重试')}</button>
        <a href="/" class="btn btn--ghost">${T('page.search.rephrase', '换个说法')}</a>
      </div>
    </div>
  `;
  const retryBtn = document.getElementById('search-retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      const q = _lastQuery;
      if (q) performSearch(q);
      else renderPrivateContextUnavailable();
    });
  }
}

// Render the "this question may not fit" guidance card and pause the search.
// Returns true if the card was rendered (meaning we should NOT proceed with
// rendering results); false if the assessment passed and we proceed normally.
function maybeRenderAssessmentGate(query, data) {
  const assess = data && data.assessment;
  if (!assess) return false;
  const score = assess.worth_score;
  if (typeof score !== 'number' || score >= 3) return false;

  // Below threshold — show the coaching card instead of results.
  const coaching = assess.coaching || T('page.search.assess_coaching_default', '这个输入对 Structural 的结构候选搜索可能不太适合。');
  const suggestion = assess.rewrite_suggestion;
  const category = assess.category || T('page.search.assess_category_other', '其他');

  const summaryEl = $('#search-summary');
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="search-question">
        <div class="search-question__label">${T('page.search.your_question', '你的问题')}</div>
        <div class="search-question__text">${escapeHtml(query)}</div>
      </div>
    `;
  }

  const resultsEl = $('#search-results');
  if (!resultsEl) return true;

  resultsEl.innerHTML = `
    <div class="assess-gate">
      <div class="assess-gate__icon" aria-hidden="true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 16v-4M12 8h.01"/>
        </svg>
      </div>
      <div class="assess-gate__category">${T('page.search.assess_identified_as', '识别为：')}${escapeHtml(category)}</div>
      <h2 class="assess-gate__title">${T('page.search.assess_title', '这个问题对 Structural 来说不太典型')}</h2>
      <p class="assess-gate__coaching">${escapeHtml(coaching)}</p>

      ${suggestion ? `
        <div class="assess-gate__suggestion">
          <div class="assess-gate__suggestion-label">${T('page.search.assess_rewrite_hint', '💡 试着这样改写')}</div>
          <div class="assess-gate__suggestion-text">${escapeHtml(suggestion)}</div>
        </div>
      ` : ''}

      <div class="assess-gate__actions">
        ${suggestion ? `
          <button type="button" class="btn btn--primary" id="assess-use-suggestion">${T('page.search.assess_use_rewrite', '用这个改写')}</button>
        ` : ''}
        <button type="button" class="btn btn--secondary" id="assess-force-search">${T('page.search.assess_force_search', '还是按原文搜')}</button>
        <a href="/" class="btn btn--ghost">${T('page.search.back_home', '返回首页')}</a>
      </div>

      <details class="assess-gate__why">
        <summary>${T('page.search.assess_why_summary', '为什么 Structural 拦下了这个问题')}</summary>
        <p>${T('page.search.assess_why_p1', 'Structural 用跨学科<strong>结构比较</strong>来处理现象级问题，例如行为模式、动力学、阈值和趋势变化。它返回变量关系或方程骨架相近、值得进一步核查的候选；这不证明案例结构等价或机制一致。')}</p>
        <p>${T('page.search.assess_why_p2', '不擅长的：帮你写东西、关于产品本身的问题（比如「这个产品怎么用」）、闲聊、查事实、个人琐事——这些场景没有「另一个学科里的同款现象」可借。')}</p>
      </details>
    </div>
  `;

  // Wire actions
  const useSuggestion = document.getElementById('assess-use-suggestion');
  if (useSuggestion && suggestion) {
    useSuggestion.addEventListener('click', () => {
      navigateToPrivateSearch(suggestion, { source: 'suggestion' });
    });
  }
  const forceSearch = document.getElementById('assess-force-search');
  if (forceSearch) {
    forceSearch.addEventListener('click', () => {
      navigateToPrivateSearch(query, { force: true, source: 'rewrite' });
    });
  }
  return true;
}

async function performSearch(query, navigationContext) {
  const runId = ++_activeSearchRun;
  cancelActiveSynthesis();
  if (navigationContext) _currentSearchContext = navigationContext;
  _lastQuery = query;
  _lastForce = Boolean(
    (_currentSearchContext && _currentSearchContext.force) || getQueryParam('force') === '1'
  );
  // Paint the private question and a dimensionally stable progress shell
  // before waiting for retrieval. This makes the user's input the immediate
  // first value and prevents the final summary from pushing results downward.
  renderQuestionHeader(query, { count: null, rewritten_query: null });
  renderSkeleton();

  try {
    // Two-phase flow:
    //   1. Fire fast vector search with the raw query — renders in <1s.
    //   2. In parallel, fire /search/assess (LLM rewrite + worthiness).
    //      When it returns, either (a) show the low-fit gate if worth<3,
    //      or (b) re-run search with the rewritten query for better rankings
    //      and swap in the improved results.
    const force = _lastForce;
    const searchPromise = StructuralAPI.search(query, 20);
    const assessPromise = force
      ? Promise.resolve(null)
      : StructuralAPI.assessQuery(query).catch(() => {
          console.warn('Question assessment unavailable; continuing with bounded search.');
          return null;
        });

    const data = await searchPromise;
    if (runId !== _activeSearchRun) return;

    // SESSION-17 V2: out-of-scope questions (arithmetic / chitchat / trivia)
    // get a friendly explanation instead of an empty result list. Stop here —
    // no synth, no assessment gate.
    if (data && data.out_of_scope) {
      renderOutOfScope(query, data);
      return;
    }

    renderQuestionHeader(query, data);
    renderResults(query, data);
    updatePrivateSearchState({
      rewritten_query: data.rewritten_query || null,
      results: data.results || [],
      force,
      lang: currentSearchLang(),
    });

    // Kick off synthesis using the raw query now — once the rewritten search
    // lands, we'll re-run synthesis with the improved context.
    //
    // The transport streams progress only. Semantic model text is rendered
    // only after the backend validates the complete typed payload.
    const runSynth = (q, rewritten, results) => {
      if (!results || results.length === 0) return;
      // Cancel any prior comparison and bind every callback to this exact
      // search run + synthesis generation. Abort is advisory; a stale
      // transport callback must still be unable to mutate the current DOM.
      cancelActiveSynthesis();
      const synthGeneration = _activeSynthGeneration;

      // Keep one honest progress state; raw model deltas never enter the DOM.
      const synthEl = $('#search-synth');
      if (synthEl) {
        synthEl.classList.remove('search-synth--loading');
        synthEl.innerHTML = `
          <div class="search-synth__content">
            <div class="search-synth__label">${T('page.search.synthesis_checking_label', '候选比较 · 校验中')}</div>
            <div class="search-synth__insight search-synth__insight--streaming" aria-live="polite">
              <p>${T('page.search.synthesis_checking_text', '正在核对候选来源、证据缺口、竞争解释与失败条件…')}</p>
            </div>
          </div>
        `;
      }

      const callbacks = guardSynthesisCallbacks(
        runId,
        synthGeneration,
        () => ({ run: _activeSearchRun, generation: _activeSynthGeneration }),
        {
          onText: () => {
            // Progress contains no semantic model text. It still passes through
            // the same generation guard as terminal callbacks.
          },
          onDone: (data) => {
            _activeSynthGeneration += 1;
            _activeSynthStream = null;
            _lastSynth = data && data.result;
            renderSynthBlock(_lastSynth);
            renderResultsWithSynth();
          },
          onError: () => {
            _activeSynthGeneration += 1;
            _activeSynthStream = null;
            console.warn('Candidate comparison unavailable; using ranked candidates.');
            renderSynthTransportFailure(() => runSynth(q, rewritten, results));
            renderResultsWithSynth();
          },
        },
      );
      _activeSynthStream = StructuralAPI.synthesizeStream(q, rewritten, results, callbacks);
    };

    let currentData = data;
    runSynth(query, null, currentData.results);

    // When assessment arrives, apply gate or upgrade results.
    assessPromise.then(async assess => {
      if (runId !== _activeSearchRun) return;
      if (!assess) return;

      // Low-fit → show coaching gate (replaces results).
      if (typeof assess.worth_score === 'number' && assess.worth_score < 3) {
        cancelActiveSynthesis();
        const gateData = Object.assign({}, currentData, {
          assessment: {
            worth_score: assess.worth_score,
            category: assess.category,
            coaching: assess.coaching,
            rewrite_suggestion: assess.rewrite_suggestion,
          },
        });
        maybeRenderAssessmentGate(query, gateData);
        return;
      }

      // High-fit but rewritten → re-run search with the rewrite for better
      // rankings and swap in the improved results.
      const rewritten = assess.rewritten;
      if (rewritten && rewritten !== query) {
        try {
          const better = await StructuralAPI.search(rewritten, 20);
          if (runId !== _activeSearchRun) return;
          // SESSION-17 V2: a rewritten query can also turn out-of-scope.
          if (better && better.out_of_scope) {
            cancelActiveSynthesis();
            renderOutOfScope(query, better);
            return;
          }
          better.rewritten_query = rewritten;
          currentData = better;
          renderQuestionHeader(query, better);
          renderResults(query, better);
          updatePrivateSearchState({
            rewritten_query: rewritten,
            results: better.results || [],
            force,
            lang: currentSearchLang(),
          });
          runSynth(query, rewritten, better.results);
        } catch {
          console.warn('Rewritten-query search unavailable; keeping the first candidate set.');
        }
      }
    }).catch(() => {});

    // Record in local search history (deduped, newest first)
    try {
      if (window.addToHistory) {
        window.addToHistory({
          query,
          rewritten_query: data.rewritten_query || null,
          timestamp: Date.now(),
        });
      }
    } catch (e) { /* ignore storage quota */ }

  } catch {
    if (runId !== _activeSearchRun) return;
    cancelActiveSynthesis();
    console.error('Search flow failed.');
    renderError();
  }
}

function resolveSearchNavigation() {
  if (typeof window.resolvePrivateNavigationContext !== 'function') {
    scrubSensitiveSearchUrl();
    return null;
  }
  try {
    return window.resolvePrivateNavigationContext({
      kind: 'search',
      key: getQueryParam('context'),
      lang: currentSearchLang(),
      force: getQueryParam('force') === '1',
    });
  } catch (e) {
    scrubSensitiveSearchUrl();
    return null;
  }
}

let _initialSearchBootConsumed = false;

function takeInitialSearchBoot() {
  if (_initialSearchBootConsumed) return { handled: false, context: null };
  _initialSearchBootConsumed = true;
  const boot = window.__structuralSearchBoot;
  if (!boot || boot.attempted !== true) return { handled: false, context: null };
  return { handled: true, context: boot.context || null };
}

function restoreSearchNavigation() {
  const boot = takeInitialSearchBoot();
  const context = boot.handled ? boot.context : resolveSearchNavigation();
  if (!context) {
    _activeSearchRun += 1;
    cancelActiveSynthesis();
    _currentSearchContext = null;
    _lastQuery = '';
    renderPrivateContextUnavailable();
    return;
  }
  _currentSearchContext = context;
  performSearch(context.query, context);
}

function startSearchPage() {
  initHeaderScroll();
  restoreSearchNavigation();
}

if (typeof module === 'undefined' || !module.exports) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startSearchPage, { once: true });
  } else {
    startSearchPage();
  }
}

window.addEventListener('popstate', () => {
  restoreSearchNavigation();
});

// Re-render content when language toggles
try {
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(function () {
      try {
        const q = _lastQuery;
        if (!q) return;
        updatePrivateSearchState({ lang: currentSearchLang() });
        // Re-render all cached results with new language
        const data = {
          count: (_lastResults || []).length,
          results: _lastResults,
          rewritten_query: null,
          v2_pairs_for_top: _lastV2PairsForTop,
          stats: _lastStats,
        };
        renderQuestionHeader(q, data);
        if (_lastSynth) {
          renderSynthBlock(_lastSynth);
          renderResultsWithSynth();
        } else {
          renderResults(q, data);
        }
      } catch (e) { /* ignore */ }
    });
  }
} catch (e) {}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    resolveSearchSynthesisCandidate,
    synthesisGenerationMatches,
    guardSynthesisCallbacks,
    renderResultsWithSynth,
    containsRenderableMath,
  };
}
