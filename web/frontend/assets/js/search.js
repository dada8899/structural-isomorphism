
// Score display helper: map fused score [0, 1.1] to a tier label + percentage.
// Treats <0.3 as weak, 0.3-0.6 as medium, >=0.6 as strong.
function scoreTier(score) {
  const s = typeof score === 'number' ? score : 0;
  if (s >= 0.6) return { pct: Math.round(Math.min(s, 1) * 100), label: '强相似', cls: 'score--strong' };
  if (s >= 0.3) return { pct: Math.round(Math.min(s, 1) * 100), label: '中等相似', cls: 'score--medium' };
  return { pct: Math.round(Math.min(s, 1) * 100), label: '弱相关', cls: 'score--weak' };
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
const SYNTH_PHASES = [
  { until: 4, text: '正在理解你的问题' },
  { until: 9, text: '正在挑选最相关的证据' },
  { until: 16, text: '正在组织答案' },
  { until: 999, text: '马上就好' },
];

function renderQuestionHeader(query, data) {
  const container = $('#search-summary');
  if (!container) return;

  if (data.count === 0) {
    container.innerHTML = `
      <div class="search-question">
        <div class="search-question__label">你的问题</div>
        <div class="search-question__text">${escapeHtml(query)}</div>
      </div>
    `;
    return;
  }

  const rewritten = data.rewritten_query;

  container.innerHTML = `
    <div class="search-question">
      <button type="button" class="search-question__edit-btn" id="search-edit-btn" aria-label="编辑这个问题">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
        编辑
      </button>
      <div class="search-question__label">你的问题</div>
      <div class="search-question__text">${escapeHtml(query)}</div>
      ${rewritten && rewritten !== query ? `
        <div class="search-question__rewrite">
          已改写为研究问题：<em>${escapeHtml(rewritten)}</em>
        </div>
      ` : ''}
    </div>
    <div class="search-synth search-synth--loading" id="search-synth">
      <div class="search-synth__loading">
        <div class="search-synth__dots"><span></span><span></span><span></span></div>
        <span class="search-synth__phase-text" id="search-synth-phase">正在理解你的问题</span>
        <span class="elapsed-timer" id="search-synth-timer">已等待 0s</span>
        <span class="search-synth__typical">${data.count} 个候选 · 通常 8–15s</span>
      </div>
    </div>
  `;

  // Start elapsed timer for synthesis
  if (_synthTimerStop) { _synthTimerStop(); _synthTimerStop = null; }
  const synthTimerEl = document.getElementById('search-synth-timer');
  if (synthTimerEl && window.startElapsedTimer) {
    _synthTimerStop = window.startElapsedTimer(synthTimerEl);
  }

  // Start phase rotation — single source of "I'm thinking about it" progress
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
    const phase = SYNTH_PHASES.find(p => elapsed < p.until) || SYNTH_PHASES[SYNTH_PHASES.length - 1];
    if (phaseEl.textContent !== phase.text) phaseEl.textContent = phase.text;
  };
  tickPhase();
  _phaseIntervalId = setInterval(tickPhase, 500);

  // Wire the "编辑" button — turn the question text into an editable textarea
  const editBtn = document.getElementById('search-edit-btn');
  if (editBtn) {
    editBtn.addEventListener('click', () => enterEditMode(query));
  }
}

// === Edit mode: turn the question header into an inline form ===
function enterEditMode(currentQuery) {
  const card = document.querySelector('.search-question');
  if (!card) return;
  card.innerHTML = `
    <div class="search-question__label">编辑你的问题</div>
    <textarea class="search-question__editor" rows="3">${escapeHtml(currentQuery)}</textarea>
    <div class="search-question__edit-actions">
      <button type="button" class="btn btn--ghost btn--sm" id="search-edit-cancel">取消</button>
      <button type="button" class="btn btn--primary btn--sm" id="search-edit-submit">再问一次</button>
    </div>
    <div class="search-question__edit-hint"><kbd>⌘</kbd> + <kbd>Enter</kbd> 提交</div>
  `;
  const ta = card.querySelector('textarea');
  if (ta) {
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
    ta.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        document.getElementById('search-edit-submit')?.click();
      }
    });
  }
  document.getElementById('search-edit-cancel')?.addEventListener('click', () => {
    window.location.reload();
  });
  document.getElementById('search-edit-submit')?.addEventListener('click', () => {
    const newQ = (ta?.value || '').trim();
    if (!newQ) return;
    window.location.href = `/search?q=${encodeURIComponent(newQ)}`;
  });
}

function toParagraphs(text) {
  // Delegate to the global mdParagraphs (in utils.js) which handles
  // **bold** / *italic* / `code` / \n→<br> and splits on \n\n.
  return (window.mdParagraphs ? window.mdParagraphs(text) : '');
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
  container.innerHTML = `
    <div class="search-synth__content">
      <div class="search-synth__label">主洞察 · AI 合成</div>
      <div class="search-synth__insight">${toParagraphs(synth.main_insight)}</div>
      ${synth.why_these_matter ? `
        <div class="search-synth__why">
          <span class="search-synth__why-tag">为什么这有用</span>
          <div class="search-synth__why-text">${toParagraphs(synth.why_these_matter)}</div>
        </div>
      ` : ''}
    </div>
  `;
  // Render any inline math
  if (window.renderMath) window.renderMath(container);
}

// State shared between renderResults and renderResultsWithSynth
let _lastQuery = '';
let _lastResults = [];
let _lastSynth = null;
let _lastV2PairsForTop = [];

function renderResults(query, data) {
  _lastQuery = query;
  _lastResults = data.results || [];
  _lastSynth = null;
  _lastV2PairsForTop = Array.isArray(data.v2_pairs_for_top) ? data.v2_pairs_for_top : [];

  const container = $('#search-results');
  if (!container) return;

  if (!data.results || data.results.length === 0) {
    container.innerHTML = `
      <div class="search-empty">
        <svg class="search-empty__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/><path d="M11 8v6M8 11h6" opacity="0.3"/>
        </svg>
        <h2 class="search-empty__title">没有找到足够相似的现象</h2>
        <p class="search-empty__text">
          知识库暂时没有结构相似的匹配。<br>
          试着描述现象本身的<strong>行为模式</strong>，而不是问题或结论。
        </p>
        <div class="search-empty__actions">
          <a href="/" class="btn btn--primary">返回首页</a>
          <a href="/about" class="btn btn--ghost">了解 Structural</a>
        </div>
      </div>
    `;
    return;
  }

  // Quiet placeholder while synth is loading — no breathing, no second timer.
  // The breathing/timer/phase rotation lives in the synth card above (single
  // source of "I'm working" feedback).
  container.innerHTML = `
    <div class="search-page__results">
      <div class="rec-placeholder rec-placeholder--quiet">
        <span class="rec-placeholder__text">推荐和证据将在合成完成后展开...</span>
      </div>
    </div>
  `;
}

// Render the "V2 模型识别的跨域对" section. Returns HTML string.
// Pulls from _lastV2PairsForTop (populated in renderResults).
function renderV2PairsForTop() {
  const groups = _lastV2PairsForTop || [];
  if (!groups.length) return '';

  const blocks = groups.map(group => {
    const pairs = Array.isArray(group.pairs) ? group.pairs : [];
    if (!pairs.length) return '';
    const cards = pairs.map(p => {
      const simPct = typeof p.similarity === 'number' ? Math.round(p.similarity * 100) : null;
      const href = `/analyze?a_id=${encodeURIComponent(group.phenomenon_id)}&id=${encodeURIComponent(p.other_id || '')}`;
      return `
        <a href="${href}" class="v2-pair-card">
          ${simPct !== null ? `<div class="v2-pair-card__sim">${simPct}%</div>` : ''}
          <div class="v2-pair-card__domain">${escapeHtml(p.other_domain || '')}</div>
          <h5 class="v2-pair-card__name">${escapeHtml(p.other_name || '')}</h5>
          ${p.reason ? `<p class="v2-pair-card__reason">${escapeHtml(p.reason)}</p>` : ''}
        </a>
      `;
    }).join('');

    return `
      <div class="v2-phenom-block">
        <div class="v2-phenom-block__title">
          <span class="v2-phenom-block__name">${escapeHtml(group.phenomenon_name || '')}</span>
          <span class="v2-phenom-block__domain">（${escapeHtml(group.phenomenon_domain || '')}）</span>
          <span class="v2-phenom-block__linker">还连接到</span>
        </div>
        <div class="v2-pair-grid">${cards}</div>
      </div>
    `;
  }).filter(Boolean).join('');

  if (!blocks) return '';

  return `
    <section class="v2-pairs-section">
      <div class="v2-pairs-section__header">
        <div class="v2-pairs-section__label">V2 模型识别的跨域对</div>
        <h3 class="v2-pairs-section__title">V2 还看到了这些联系</h3>
        <p class="v2-pairs-section__sub">V2 管道独立筛选过的跨学科同构对，不在向量检索流里。点击查看深度分析。</p>
      </div>
      ${blocks}
    </section>
  `;
}

function renderResultsWithSynth() {
  // Stop the phase rotation since synth has completed
  if (_phaseIntervalId) { clearInterval(_phaseIntervalId); _phaseIntervalId = null; }

  const query = _lastQuery;
  const results = _lastResults;
  const synth = _lastSynth;
  const container = $('#search-results');
  if (!container || !results.length) return;

  const primary = synth && synth.primary_recommendation;
  const alternatives = (synth && synth.alternative_angles) || [];
  const snippetsByIdx = {};
  if (synth && Array.isArray(synth.relevance_snippets)) {
    for (const s of synth.relevance_snippets) {
      if (typeof s.index === 'number') snippetsByIdx[s.index] = s.snippet;
    }
  }

  // Fallback: synth failed or malformed
  if (!primary || typeof primary.result_index !== 'number') {
    const v2PairsHtmlFallback = renderV2PairsForTop();
    container.innerHTML = `
      <div class="search-page__results">
        <div class="search-page__results-title">
          <span>跨领域证据 · ${results.length} 个候选</span>
        </div>
        <div class="result-list">
          ${results.map(r => `
            <a href="/analyze?id=${encodeURIComponent(r.id)}&q=${encodeURIComponent(query)}" class="result-card">
              <div class="result-card__main">
                <div class="result-card__meta">
                  <span class="result-card__meta-domain">${escapeHtml(r.domain)}</span>
                  <span class="result-card__meta-dot"></span>
                  <span class="result-card__meta-type">结构 ${escapeHtml(r.type_id)}</span>
                </div>
                <h3 class="result-card__name">${escapeHtml(r.name)}</h3>
                <p class="result-card__description">${escapeHtml(r.description)}</p>
              </div>
              <div class="result-card__aside">
                <div class="result-card__score">
                  <span class="result-card__score-num">${scoreTier(r.score).pct}</span><span class="result-card__score-unit">%</span>
                </div>
                <svg class="result-card__arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
              </div>
            </a>
          `).join('')}
        </div>
        ${v2PairsHtmlFallback}
      </div>
    `;
    return;
  }

  const pickedIndexes = new Set([primary.result_index]);
  for (const alt of alternatives) {
    if (typeof alt.result_index === 'number') pickedIndexes.add(alt.result_index);
  }
  const others = results.filter((_, idx) => !pickedIndexes.has(idx + 1));

  // === Primary card ===
  const pr = results[primary.result_index - 1];
  let primaryHtml = '';
  if (pr) {
    primaryHtml = `
      <section class="rec-primary" style="animation: fadeInUp 500ms var(--ease-out-expo) both">
        <div class="rec-primary__label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          <span>推荐先看这一个</span>
        </div>
        <a href="/analyze?id=${encodeURIComponent(pr.id)}&q=${encodeURIComponent(query)}" class="rec-primary__card">
          <div class="rec-primary__body">
            <div class="rec-primary__meta">
              <span class="rec-primary__domain">${escapeHtml(pr.domain)}</span>
              <span class="rec-primary__score">${scoreTier(pr.score).pct}% · ${scoreTier(pr.score).label}</span>
            </div>
            <h3 class="rec-primary__name">${escapeHtml(pr.name)}</h3>

            ${primary.reason ? `
              <div class="rec-primary__block">
                <div class="rec-primary__block-label">为什么首推</div>
                <div class="rec-primary__block-text">${window.mdInline(primary.reason)}</div>
              </div>
            ` : ''}

            ${primary.what_youll_learn ? `
              <div class="rec-primary__block rec-primary__block--takeaway">
                <div class="rec-primary__block-label">你会得到</div>
                <div class="rec-primary__block-text">${window.mdInline(primary.what_youll_learn)}</div>
              </div>
            ` : ''}
          </div>

          <div class="rec-primary__cta">
            <span>立即深度分析</span>
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
      const r = results[alt.result_index - 1];
      if (!r) return '';
      return `
        <a href="/analyze?id=${encodeURIComponent(r.id)}&q=${encodeURIComponent(query)}" class="rec-alt" style="animation: fadeInUp 500ms var(--ease-out-expo) ${i * 80 + 100}ms both">
          <div class="rec-alt__angle">${escapeHtml(alt.angle_label || '补充视角')}</div>
          <h4 class="rec-alt__name">${escapeHtml(r.name)}</h4>
          <div class="rec-alt__meta">${escapeHtml(r.domain)} · ${scoreTier(r.score).pct}%</div>
          ${alt.reason ? `<p class="rec-alt__reason">${window.mdInline(alt.reason)}</p>` : ''}
          <div class="rec-alt__cta">
            深度分析
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
          </div>
        </a>
      `;
    }).filter(Boolean).join('');

    if (altCards) {
      altHtml = `
        <section class="rec-alts">
          <div class="rec-alts__label">补充视角 — 从不同角度看你的问题</div>
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
          <span>其他 ${others.length} 个候选证据</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>
        </button>
        <div class="rec-others__list" id="rec-others-list" hidden>
          ${others.map(r => {
            const origIdx = results.indexOf(r) + 1;
            const snippet = snippetsByIdx[origIdx];
            return `
              <a href="/analyze?id=${encodeURIComponent(r.id)}&q=${encodeURIComponent(query)}" class="rec-other">
                <div class="rec-other__main">
                  <div class="rec-other__meta">
                    <span class="rec-other__domain">${escapeHtml(r.domain)}</span>
                  </div>
                  <div class="rec-other__name">${escapeHtml(r.name)}</div>
                  ${snippet ? `<p class="rec-other__snippet">${escapeHtml(snippet)}</p>` : `<p class="rec-other__desc">${escapeHtml(r.description)}</p>`}
                </div>
                <div class="rec-other__score">${scoreTier(r.score).pct}%</div>
              </a>
            `;
          }).join('')}
        </div>
      </section>
    `;
  }

  const v2PairsHtml = renderV2PairsForTop();

  container.innerHTML = `
    <div class="search-page__results">
      ${primaryHtml}
      ${altHtml}
      ${v2PairsHtml}
      ${othersHtml}
    </div>
  `;

  // Render inline math in recommendation text
  if (window.renderMath) window.renderMath(container);

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
}

function renderError(err) {
  const container = $('#search-results');
  if (!container) return;
  const detail = escapeHtml(err && (err.message || String(err)) || '未知错误');
  container.innerHTML = `
    <div class="search-error">
      <h2 class="search-error__title">搜索失败</h2>
      <p class="search-error__text">可能是网络问题或服务暂时不可用。</p>
      <p class="search-error__detail" style="color: var(--text-tertiary); font-size: var(--fs-12); margin-top: 4px;">${detail}</p>
      <div class="search-error__actions" style="display: flex; gap: 12px; justify-content: center; margin-top: 20px;">
        <button type="button" class="btn btn--primary" id="search-retry-btn">重试</button>
        <a href="/" class="btn btn--ghost">换个说法</a>
      </div>
    </div>
  `;
  const retryBtn = document.getElementById('search-retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      const q = _lastQuery || getQueryParam('q');
      if (q) performSearch(q);
      else window.location.href = '/';
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
  const coaching = assess.coaching || '这个输入对 Structural 的同构搜索可能不太适合。';
  const suggestion = assess.rewrite_suggestion;
  const category = assess.category || '其他';

  const summaryEl = $('#search-summary');
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="search-question">
        <div class="search-question__label">你的问题</div>
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
      <div class="assess-gate__category">识别为：${escapeHtml(category)}</div>
      <h2 class="assess-gate__title">这个问题对 Structural 来说不太典型</h2>
      <p class="assess-gate__coaching">${escapeHtml(coaching)}</p>

      ${suggestion ? `
        <div class="assess-gate__suggestion">
          <div class="assess-gate__suggestion-label">💡 试着这样改写</div>
          <div class="assess-gate__suggestion-text">${escapeHtml(suggestion)}</div>
        </div>
      ` : ''}

      <div class="assess-gate__actions">
        ${suggestion ? `
          <button type="button" class="btn btn--primary" id="assess-use-suggestion">用这个改写</button>
        ` : ''}
        <button type="button" class="btn btn--secondary" id="assess-force-search">还是按原文搜</button>
        <a href="/" class="btn btn--ghost">返回首页</a>
      </div>

      <details class="assess-gate__why">
        <summary>为什么 Structural 拦下了这个问题</summary>
        <p>Structural 是一个跨学科<strong>结构同构</strong>引擎，最擅长的是把"<em>现象级</em>"的问题（比如行为模式、动力学、临界点、趋势变化）映射到其他学科里结构相同的案例。</p>
        <p>不擅长的：写作请求、元问题（"这个产品怎么用"）、闲聊、纯事实查询、纯个人琐事——这些场景我们没有可借用的"另一个学科里的同构现象"。</p>
      </details>
    </div>
  `;

  // Wire actions
  const useSuggestion = document.getElementById('assess-use-suggestion');
  if (useSuggestion && suggestion) {
    useSuggestion.addEventListener('click', () => {
      window.location.href = `/search?q=${encodeURIComponent(suggestion)}`;
    });
  }
  const forceSearch = document.getElementById('assess-force-search');
  if (forceSearch) {
    forceSearch.addEventListener('click', () => {
      // Re-run the search with the assessment gate disabled
      const url = new URL(window.location.href);
      url.searchParams.set('force', '1');
      window.location.href = url.toString();
    });
  }
  return true;
}

async function performSearch(query) {
  _lastQuery = query;
  renderSkeleton();

  try {
    // Two-phase flow:
    //   1. Fire fast vector search with the raw query — renders in <1s.
    //   2. In parallel, fire /search/assess (LLM rewrite + worthiness).
    //      When it returns, either (a) show the low-fit gate if worth<3,
    //      or (b) re-run search with the rewritten query for better rankings
    //      and swap in the improved results.
    const force = getQueryParam('force');
    const searchPromise = StructuralAPI.search(query, 20);
    const assessPromise = force
      ? Promise.resolve(null)
      : StructuralAPI.assessQuery(query).catch(err => {
          console.warn('Assess failed, proceeding without gate:', err);
          return null;
        });

    const data = await searchPromise;

    renderQuestionHeader(query, data);
    renderResults(query, data);

    // Kick off synthesis using the raw query now — once the rewritten search
    // lands, we'll re-run synthesis with the improved context.
    const runSynth = (q, rewritten, results) => {
      if (!results || results.length === 0) return;
      StructuralAPI.synthesize(q, rewritten, results)
        .then(synth => {
          _lastSynth = synth;
          renderSynthBlock(synth);
          renderResultsWithSynth();
        })
        .catch(err => {
          console.error('Synthesize failed:', err);
          const synthEl = $('#search-synth');
          if (synthEl) synthEl.remove();
          renderResultsWithSynth();
        });
    };

    let currentData = data;
    runSynth(query, null, currentData.results);

    // When assessment arrives, apply gate or upgrade results.
    assessPromise.then(async assess => {
      if (!assess) return;

      // Low-fit → show coaching gate (replaces results).
      if (typeof assess.worth_score === 'number' && assess.worth_score < 3) {
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
          better.rewritten_query = rewritten;
          currentData = better;
          renderQuestionHeader(query, better);
          renderResults(query, better);
          runSynth(query, rewritten, better.results);
          // Update session stash with the better results
          try {
            sessionStorage.setItem('structural_last_search', JSON.stringify({
              query,
              rewritten_query: rewritten,
              results: better.results,
              timestamp: Date.now(),
            }));
          } catch (e) { /* quota */ }
        } catch (err) {
          console.warn('Rewritten-query re-search failed:', err);
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

    // Stash initial results for the detail page's "more answers" section
    try {
      sessionStorage.setItem('structural_last_search', JSON.stringify({
        query,
        rewritten_query: data.rewritten_query,
        results: data.results,
        timestamp: Date.now(),
      }));
    } catch (e) { /* quota / private mode */ }
  } catch (err) {
    console.error('Search failed:', err);
    renderError(err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  const q = getQueryParam('q');
  if (q) {
    performSearch(q);
  } else {
    window.location.href = '/';
  }
});
