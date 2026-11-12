function T(key, fallback) { try { if (window.i18n && typeof window.i18n.t === "function") { var v = window.i18n.t(key); if (v && v !== key) return v; } } catch(e) {} return fallback; }

/**
 * Structural — Phenomenon detail page
 *
 * Data flow:
 *   1. Load phenomenon by ID from URL
 *   2. Render hero + cross-domain similar + same-structure lists
 *   3. If ?pair=otherId, also render the LLM mapping between the two
 */

function getPathId() {
  const m = window.location.pathname.match(/^\/phenomenon\/([^/?]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

// Resolve phenomenon id from URL — supports both path (/phenomenon/:id)
// and query-param (/phenomenon?id=xxx) deep-link forms. The latter is what
// share-card and external links typically produce.
function resolvePhenomenonId() {
  return getPathId() || getQueryParam('id');
}

// The API payload is language-bound. A language change must fetch a fresh
// payload; only same-language registry refreshes may reuse the current data.
let _phData = null;
let _phId = null;
let _phPairId = null;
let _phNavigationContext = null;
let _phDataLang = null;
let _phRequestedLang = null;
let _phLoadGeneration = 0;
let _phActiveMappingStream = null;

function currentPhenomenonLang() {
  try {
    return window.i18n && window.i18n.getLang && window.i18n.getLang() === 'en' ? 'en' : 'zh';
  } catch (e) {
    return 'zh';
  }
}

function phenomenonCopy(zh, en) {
  return currentPhenomenonLang() === 'en' ? en : zh;
}

function closeActiveMappingStream() {
  if (_phActiveMappingStream) {
    try { _phActiveMappingStream.close(); } catch (e) { /* already closed */ }
    _phActiveMappingStream = null;
  }
}

function renderCandidateEvidence(item, compact = true) {
  if (!window.StructuralEvidence) return '';
  return window.StructuralEvidence.render(
    (item && item.evidence) || window.StructuralEvidence.fallback(item || {}),
    { compact, suppressActions: true }
  );
}

function renderRetrievalRank(index, className = 'ph-cross__card-score') {
  if (!Number.isInteger(index) || index < 0) return '';
  const label = phenomenonCopy('本组序位', 'Group rank');
  const boundary = phenomenonCopy('不可跨查询比较，不是概率', 'not comparable across queries; not a probability');
  return `<div class="${className}" aria-label="${label} ${index + 1}，${boundary}"><span>${label}</span><strong>#${index + 1}</strong><small>${boundary}</small></div>`;
}

function mappingObjectHasOnly(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function mappingText(value, maxLength, allowEmpty = false) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if ((!allowEmpty && !text) || text.length > maxLength || /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(text)) return null;
  const confirmed = /本质上(?:是)?同一(?:件事|回事)|(?:结构同构|共享机制)(?:已经|已|得到)?(?:确认|证实|证明|成立)|必然(?:成立|适用|有效)|(?:are|is)\s+(?:structurally\s+)?isomorphic|(?:the\s+)?same\s+underlying\s+mechanism|(?:has\s+been|is)\s+(?:proven|confirmed|validated)|validated\s+mapping/i;
  return confirmed.test(text) ? null : text;
}

function boundedPublicText(value, maxLength, allowEmpty = false) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if ((!allowEmpty && !text) || text.length > maxLength || /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(text)) return null;
  return text;
}

function normalizeMappingSide(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const side = {
    id: boundedPublicText(value.id, 120),
    name: boundedPublicText(value.name, 500),
    domain: boundedPublicText(value.domain, 200),
    type_id: boundedPublicText(value.type_id, 120),
    description: boundedPublicText(value.description, 8000),
    original_query: value.original_query == null ? null : boundedPublicText(value.original_query, 8000),
  };
  const required = ['id', 'name', 'domain', 'type_id', 'description'];
  if (required.some((key) => side[key] === null)) return null;
  if (value.original_query != null && side.original_query === null) return null;
  return side;
}

function normalizeMoreAnswer(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const similarity = typeof value.retrieval_similarity === 'number'
    ? value.retrieval_similarity
    : value.score;
  const row = {
    id: boundedPublicText(value.id, 120),
    name: boundedPublicText(value.name, 500),
    domain: boundedPublicText(value.domain, 200),
    type_id: boundedPublicText(value.type_id, 120),
    description: boundedPublicText(value.description, 2500),
    retrieval_similarity: typeof similarity === 'number' && Number.isFinite(similarity)
      && similarity >= 0 && similarity <= 1 ? similarity : null,
  };
  if (['id', 'name', 'domain', 'type_id', 'description'].some((key) => row[key] === null)) return null;
  if (value.evidence && typeof value.evidence === 'object' && !Array.isArray(value.evidence)) row.evidence = value.evidence;
  return row;
}

function normalizeMoreAnswers(items) {
  return Array.isArray(items) ? items.map(normalizeMoreAnswer).filter(Boolean) : [];
}

function normalizeCandidateMapping(value) {
  const fields = [
    'schema_version', 'evidence_level', 'generation_status', 'structure_name',
    'formula', 'candidate_rationale', 'parameter_mapping', 'validation_suggestions',
    'alternative_explanations', 'failure_conditions', 'why_worth_testing'
  ];
  if (!mappingObjectHasOnly(value, fields)) return null;
  if (value.schema_version !== 'candidate-mapping-v2' || value.evidence_level !== 'candidate') return null;
  if (!['generated', 'fallback'].includes(value.generation_status)) return null;

  const structureName = mappingText(value.structure_name, 200);
  const formula = mappingText(value.formula, 500, true);
  const rationale = mappingText(value.candidate_rationale, 1200);
  const why = mappingText(value.why_worth_testing, 1000);
  if (structureName === null || formula === null || rationale === null || why === null) return null;
  if (!Array.isArray(value.parameter_mapping) || value.parameter_mapping.length > 8) return null;
  if (!Array.isArray(value.validation_suggestions) || value.validation_suggestions.length < 1 || value.validation_suggestions.length > 5) return null;
  if (!Array.isArray(value.alternative_explanations) || value.alternative_explanations.length < 1 || value.alternative_explanations.length > 5) return null;
  if (!Array.isArray(value.failure_conditions) || value.failure_conditions.length < 1 || value.failure_conditions.length > 5) return null;

  const parameterMapping = value.parameter_mapping.map((row) => {
    if (!mappingObjectHasOnly(row, ['a_term', 'a_symbol', 'b_term', 'b_symbol', 'note'])) return null;
    const mapped = {
      a_term: mappingText(row.a_term, 160), a_symbol: mappingText(row.a_symbol, 80, true),
      b_term: mappingText(row.b_term, 160), b_symbol: mappingText(row.b_symbol, 80, true),
      note: mappingText(row.note, 500)
    };
    return Object.values(mapped).some((item) => item === null) ? null : mapped;
  });
  const suggestions = value.validation_suggestions.map((row) => {
    if (!mappingObjectHasOnly(row, ['title', 'description', 'scenario', 'failure_signal'])) return null;
    const mapped = {
      title: mappingText(row.title, 160), description: mappingText(row.description, 1000),
      scenario: mappingText(row.scenario, 500), failure_signal: mappingText(row.failure_signal, 500)
    };
    return Object.values(mapped).some((item) => item === null) ? null : mapped;
  });
  const alternatives = value.alternative_explanations.map((item) => mappingText(item, 500));
  const failures = value.failure_conditions.map((item) => mappingText(item, 500));
  if ([...parameterMapping, ...suggestions, ...alternatives, ...failures].some((item) => item === null)) return null;
  return {
    schema_version: value.schema_version,
    evidence_level: value.evidence_level,
    generation_status: value.generation_status,
    structure_name: structureName,
    formula,
    candidate_rationale: rationale,
    parameter_mapping: parameterMapping,
    validation_suggestions: suggestions,
    alternative_explanations: alternatives,
    failure_conditions: failures,
    why_worth_testing: why
  };
}

function renderLoadingHero() {
  const container = $('#ph-content');
  container.innerHTML = `
    <div class="ph-hero">
      <div class="skeleton" style="width: 120px; height: 10px; margin-bottom: 16px"></div>
      <div class="skeleton" style="width: 60%; height: 48px; margin-bottom: 16px"></div>
      <div class="skeleton" style="width: 90%; height: 14px; margin-bottom: 8px"></div>
      <div class="skeleton" style="width: 80%; height: 14px"></div>
    </div>
  `;
}

function renderHero(p) {
  return `
    <div class="ph-hero">
      <div class="ph-hero__meta">
        <span class="ph-hero__meta-domain">${escapeHtml(p.domain)}</span>
        <span class="ph-hero__meta-type">${T('page.phenomenon.structure_prefix', '候选结构')} ${escapeHtml(p.type_id)}</span>
      </div>
      <h1 class="ph-hero__name">${escapeHtml(p.name)}</h1>
      <p class="ph-hero__description">${escapeHtml(p.description)}</p>
      ${renderCandidateEvidence(p, false)}
    </div>
  `;
}

function renderHeroCompact(p) {
  return `
    <div class="ph-hero-compact">
      <div class="ph-hero-compact__label">${T('page.phenomenon.about_label', '关于这个现象')}</div>
      <div class="ph-hero-compact__meta">
        <span class="ph-hero__meta-domain">${escapeHtml(p.domain)}</span>
        <span class="ph-hero__meta-type">${T('page.phenomenon.structure_prefix', '候选结构')} ${escapeHtml(p.type_id)}</span>
      </div>
      <h2 class="ph-hero-compact__name">${escapeHtml(p.name)}</h2>
      <p class="ph-hero-compact__description">${escapeHtml(p.description)}</p>
      ${renderCandidateEvidence(p)}
    </div>
  `;
}

function renderCrossDomainList(items, currentId) {
  const filtered = items.filter(x => x.id !== currentId).slice(0, 6);
  if (filtered.length === 0) return '';

  return `
    <section class="ph-section">
      <header class="ph-section__header">
        <h2 class="ph-section__title">
          ${T('page.phenomenon.cross_domain_title', '跨领域结构类比候选')}
          <span class="ph-section__badge">${filtered.length}</span>
        </h2>
        <p class="ph-section__caption">${T('page.phenomenon.cross_domain_caption', '点击任意候选，查看待检验的变量与结构映射')}</p>
      </header>
      <div class="ph-cross">
        ${filtered.map((x, i) => `
          <a class="ph-cross__card" href="/phenomenon/${encodeURIComponent(currentId)}?pair=${encodeURIComponent(x.id)}" style="animation: fadeInUp 500ms var(--ease-out-expo) ${i * 40}ms both">
            <div class="ph-cross__card-main">
              <span class="ph-cross__card-domain">${escapeHtml(x.domain)} · ${T('page.phenomenon.structure_prefix', '候选结构')} ${escapeHtml(x.type_id)}</span>
              <h3 class="ph-cross__card-name">${escapeHtml(x.name)}</h3>
              <p class="ph-cross__card-desc">${escapeHtml(x.description)}</p>
            </div>
            ${renderRetrievalRank(i)}
            ${renderCandidateEvidence(x)}
          </a>
        `).join('')}
      </div>
    </section>
  `;
}

/**
 * "More candidates for your question" — based on the user's original query,
 * not the current phenomenon. Query text remains inside a typed local context.
 */
function renderMoreAnswers(queryResults, currentId, navigationContext) {
  queryResults = normalizeMoreAnswers(queryResults);
  if (queryResults.length === 0) return '';
  const filtered = queryResults.filter(x => x.id !== currentId).slice(0, 6);
  if (filtered.length === 0) return '';
  const fromQuery = navigationContext.query;

  return `
    <section class="ph-section ph-section--primary">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">${T('page.phenomenon.more_answers_eyebrow', '继续探索你的问题')}</span>
          <h2 class="ph-section__title">${T('page.phenomenon.more_answers_title', '你问题的其他类比候选')}</h2>
        </div>
        <p class="ph-section__caption">${T('page.phenomenon.more_answers_caption_prefix', '与"')}${escapeHtml(fromQuery)}${T('page.phenomenon.more_answers_caption_suffix', '"的其他检索候选。点进去查看待检验的映射与证据缺口。')}</p>
      </header>
      <div class="ph-cross">
        ${filtered.map((x, i) => `
          <button type="button" class="ph-cross__card" data-private-phenomenon-id="${escapeHtml(x.id)}" style="width:100%;text-align:left;font:inherit;animation: fadeInUp 500ms var(--ease-out-expo) ${i * 40}ms both">
            <div class="ph-cross__card-main">
              <span class="ph-cross__card-domain">${escapeHtml(x.domain)} · ${T('page.phenomenon.structure_prefix', '候选结构')} ${escapeHtml(x.type_id)}</span>
              <h3 class="ph-cross__card-name">${escapeHtml(x.name)}</h3>
              <p class="ph-cross__card-desc">${escapeHtml(x.description)}</p>
            </div>
            ${renderRetrievalRank(i)}
            ${renderCandidateEvidence(x)}
          </button>
        `).join('')}
      </div>
      <div class="ph-section__footer">
        <button type="button" class="btn btn--ghost" data-private-search-return>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          ${T('page.phenomenon.back_all_results', '返回所有结果')}
        </button>
      </div>
    </section>
  `;
}

function renderSameStructure(items, opts = {}) {
  if (!items || items.length === 0) return '';
  const caption = opts.emphasize
    ? T('page.phenomenon.same_structure_caption_emphasize', '这些现象被归入同一候选骨架；迁移前需核对变量、边界与反例。')
    : T('page.phenomenon.same_structure_caption_default', '被归入同一候选结构标签的其他现象');
  return `
    <section class="ph-section ph-section--muted">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">${T('page.phenomenon.same_structure_eyebrow', '开阔视野')}</span>
          <h2 class="ph-section__title">${T('page.phenomenon.same_structure_title', '同一候选结构下的其他现象')}</h2>
        </div>
        <p class="ph-section__caption">${escapeHtml(caption)}</p>
      </header>
      <div class="ph-cross">
        ${items.map((x, i) => `
          <a class="ph-cross__card" href="/phenomenon/${encodeURIComponent(x.id)}" style="animation: fadeInUp 500ms var(--ease-out-expo) ${i * 40}ms both">
            <div class="ph-cross__card-main">
              <span class="ph-cross__card-domain">${escapeHtml(x.domain)}</span>
              <h3 class="ph-cross__card-name">${escapeHtml(x.name)}</h3>
              <p class="ph-cross__card-desc">${escapeHtml(x.description)}</p>
            </div>
            ${renderCandidateEvidence(x)}
          </a>
        `).join('')}
      </div>
    </section>
  `;
}

/**
 * Direct-access extras: structure block + CTA into the 8-section deep analyze report.
 * Shown only when user lands on /phenomenon/:id without a pair or typed query context.
 */
function renderStructureBlock(p) {
  if (!p || !p.type_id) return '';
  return `
    <section class="ph-section ph-section--muted">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">${T('page.phenomenon.structure_type_eyebrow', '候选结构类型')}</span>
          <h2 class="ph-section__title">
            ${T('page.phenomenon.structure_prefix', '候选结构')} ${escapeHtml(p.type_id)}
            <span class="ph-section__badge">${T('page.phenomenon.math_skeleton_badge', '候选骨架')}</span>
          </h2>
        </div>
        <p class="ph-section__caption">${T('page.phenomenon.structure_type_caption', '这是检索与组织用的候选结构标签；归类不代表机制已经相同。')}</p>
      </header>
      <p class="ph-about__text">${escapeHtml(p.name)} ${T('page.phenomenon.belongs_to_structure', '当前归入候选结构')} ${escapeHtml(p.type_id)}${T('page.phenomenon.structure_type_text', '。可沿该候选骨架寻找可比现象，将其他领域的做法改写成待检验假设；采用前仍需验证适用边界。')}</p>
    </section>
  `;
}

/**
 * V2 hub: render all cross-domain pairs the v2 pipeline found for this
 * phenomenon (LLM-rated 4-5). Shown only on direct access.
 */
function renderV2Pairs(pairs, currentId) {
  if (!pairs || pairs.length === 0) return '';
  const count = pairs.length;
  return `
    <section class="ph-section ph-v2-hub">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">${T('page.phenomenon.v2_eyebrow', 'V2 管道')}</span>
          <h2 class="ph-section__title">${T('page.phenomenon.v2_title', 'V2 模型提出的跨域候选')}</h2>
        </div>
        <p class="ph-section__caption">${T('page.phenomenon.v2_caption_prefix', 'V2 管道为这个现象生成了')} ${count} ${T('page.phenomenon.v2_caption_suffix', '个其他领域候选。序位只表示当前列表的排列，来源核对、证伪与独立复现仍未完成。')}</p>
      </header>
      <div class="ph-v2-hub__grid">
        ${pairs.map((x, i) => {
          const href = `/analyze?a_id=${encodeURIComponent(currentId)}&id=${encodeURIComponent(x.other_id)}`;
          return `
            <a class="ph-v2-pair-card" href="${href}" style="animation: fadeInUp 500ms var(--ease-out-expo) ${i * 30}ms both">
              ${renderRetrievalRank(i, 'ph-v2-pair-card__sim')}
              <div class="ph-v2-pair-card__domain">${escapeHtml(x.other_domain || '')}</div>
              <h3 class="ph-v2-pair-card__name">${escapeHtml(x.other_name || '')}</h3>
              <p class="ph-v2-pair-card__reason">${escapeHtml(x.candidate_reason || '')}</p>
              ${renderCandidateEvidence(x)}
            </a>
          `;
        }).join('')}
      </div>
    </section>
  `;
}

function renderAnalyzeCTA(p) {
  if (!p || !p.id) return '';
  const q = p.name || '';
  const href = typeof window.buildAnalyzeUrl === 'function'
    ? window.buildAnalyzeUrl({ id: p.id, q })
    : `/analyze?id=${encodeURIComponent(p.id)}`;
  return `
    <section class="ph-section ph-section--primary ph-cta-analyze">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">${T('page.phenomenon.analyze_eyebrow', '研究草案')}</span>
          <h2 class="ph-section__title">${T('page.phenomenon.analyze_title', '发起这个现象的跨学科候选迁移研究')}</h2>
        </div>
        <p class="ph-section__caption">${T('page.phenomenon.analyze_caption', '9 段跨学科研究草案，通常 2–3 分钟流式生成')}</p>
      </header>
      <p class="ph-about__text">${T('page.phenomenon.analyze_text_prefix', '以')} ${escapeHtml(p.name)} ${T('page.phenomenon.analyze_text_suffix', '为起点，让 AI 沿候选骨架检索跨域类比，生成结构化研究草案：候选结构 → 参数对照 → 方法假设 → 验证建议。草案不等于机制确认。')}</p>
      <div class="ph-cta-analyze__actions">
        <a href="${href}" class="btn btn--primary ph-cta-analyze__btn">
          ${T('page.phenomenon.analyze_btn', '生成待验证研究草案')}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
        </a>
        <span class="ph-cta-analyze__hint">${T('page.phenomenon.analyze_hint', '9 段跨学科候选迁移研究')}</span>
      </div>
    </section>
  `;
}

function privateNavigationOptions(context) {
  return {
    query: context.query,
    rewritten_query: context.rewritten_query,
    results: context.results,
    force: context.force,
    lang: currentPhenomenonLang(),
    source: 'phenomenon',
  };
}

function privateNavigationUnavailable() {
  if (typeof window.announcePrivateNavigationError === 'function') {
    window.announcePrivateNavigationError('helper_unavailable');
  }
}

function navigateBackToPrivateSearch(context) {
  if (!context || typeof window.buildPrivateSearchUrl !== 'function') {
    privateNavigationUnavailable();
    return false;
  }
  const destination = window.buildPrivateSearchUrl(privateNavigationOptions(context));
  if (!destination) return false;
  window.location.assign(destination);
  return true;
}

function attachPrivateQueryNavigation(root, context) {
  if (!root || !context) return;
  root.querySelectorAll('[data-private-phenomenon-id]').forEach((control) => {
    control.addEventListener('click', () => {
      if (typeof window.buildPrivatePhenomenonUrl !== 'function') {
        privateNavigationUnavailable();
        return;
      }
      const destination = window.buildPrivatePhenomenonUrl({
        ...privateNavigationOptions(context),
        id: control.getAttribute('data-private-phenomenon-id') || '',
      });
      if (destination) window.location.assign(destination);
    });
  });
  root.querySelectorAll('[data-private-search-return]').forEach((control) => {
    control.addEventListener('click', () => navigateBackToPrivateSearch(context));
  });
}

function syncPrivateSearchBreadcrumb(context) {
  const backLink = $('#ph-crumb-back');
  const backSep = $('#ph-crumb-back-sep');
  if (!backLink || !backSep) return;
  backLink.onclick = null;
  if (!context) {
    backLink.setAttribute('hidden', '');
    backSep.setAttribute('hidden', '');
    backLink.removeAttribute('href');
    return;
  }
  backLink.removeAttribute('hidden');
  backSep.removeAttribute('hidden');
  backLink.setAttribute('href', '#');
  backLink.onclick = (event) => {
    event.preventDefault();
    navigateBackToPrivateSearch(context);
  };
}

function renderMappingLoading() {
  return `
    <div class="mapping-loading" role="status" aria-live="polite" aria-busy="true">
      <div class="mapping-loading__dots">
        <span class="mapping-loading__dot"></span>
        <span class="mapping-loading__dot"></span>
        <span class="mapping-loading__dot"></span>
      </div>
      <div class="mapping-loading__text">${T('page.phenomenon.mapping_loading_text', '正在生成两个现象之间的候选结构映射')}</div>
      <div class="mapping-loading__hint">${T('page.phenomenon.mapping_loading_hint', 'LLM 生成可能需要 5-10 秒')}</div>
    </div>
  `;
}

function renderMappingError(err) {
  return `
    <div class="search-error" role="alert" aria-live="assertive">
      <div class="search-error__title">${T('page.phenomenon.mapping_error_title', '映射生成失败')}</div>
      <div class="search-error__text">${escapeHtml(err.message || String(err))}</div>
      <button type="button" class="btn btn--ghost ph-mapping-retry" data-mapping-retry>
        ${phenomenonCopy('重试生成', 'Try again')}
      </button>
    </div>
  `;
}

function renderMappingPair(a, b, similarity, mapping) {
  const normalized = normalizeCandidateMapping(mapping);
  if (!normalized) {
    return renderMappingError(new Error(phenomenonCopy('候选映射未通过安全校验', 'The candidate mapping failed validation')));
  }
  mapping = normalized;
  const params = mapping.parameter_mapping || [];
  const actions = mapping.validation_suggestions || [];
  const alternatives = mapping.alternative_explanations || [];
  const failures = mapping.failure_conditions || [];
  const hasFormula = mapping.formula && mapping.formula.trim();
  // Query mode deliberately transfers from the known KB phenomenon (A)
  // toward the user's question (B). Keep that direction visible throughout.
  const isQueryMode = b.id === '__query__';
  const bName = isQueryMode ? (b.original_query || b.name) : b.name;
  const bDesc = isQueryMode
    ? (b.description && b.description !== b.original_query
        ? `${T('page.phenomenon.rewritten_as', '用于检索的候选改写：')}${b.description}`
        : '')
    : b.description;

  return `
    <section class="ph-mapping">
      <!-- Pair head -->
      <div class="mapping-pair${isQueryMode ? ' mapping-pair--query' : ''}">
        <div class="mapping-pair__heads">
          <div class="mapping-pair__head">
            <span class="mapping-pair__head-domain">${escapeHtml(a.domain)}</span>
            <h2 class="mapping-pair__head-name">${escapeHtml(a.name)}</h2>
            <p class="mapping-pair__head-desc">${escapeHtml(a.description)}</p>
          </div>
          <div class="mapping-pair__connector">
            <div class="mapping-pair__symbol" aria-label="candidate mapping">≈?</div>
          </div>
          <div class="mapping-pair__head mapping-pair__head--right">
            <span class="mapping-pair__head-domain">${escapeHtml(b.domain)}</span>
            <h2 class="mapping-pair__head-name">${escapeHtml(bName)}</h2>
            ${bDesc ? `<p class="mapping-pair__head-desc">${escapeHtml(bDesc)}</p>` : ''}
          </div>
        </div>

        <div class="mapping-boundary" role="note">
          <strong>${mapping.generation_status === 'fallback'
            ? phenomenonCopy('生成未完成，仅显示安全占位', 'Generation incomplete; safe placeholder only')
            : phenomenonCopy('待验证候选，不是研究结论', 'Untested candidate, not a research finding')}</strong>
          <span>${phenomenonCopy('候选序位只表示当前列表的排列；变量对应、因果方向、边界条件和反例仍需验证。', 'Candidate order only describes the current list; variables, causal direction, boundaries and counterexamples remain untested.')}</span>
        </div>

        ${mapping.structure_name ? `
          <div class="mapping-pair__structure">
            <div class="mapping-pair__structure-label">${T('page.phenomenon.shared_structure_label', '候选共享结构（待验证）')}</div>
            <div class="mapping-pair__structure-name">${escapeHtml(mapping.structure_name)}</div>
            ${hasFormula ? `<div class="mapping-pair__formula">${escapeHtml(mapping.formula)}</div>` : ''}
            <p class="mapping-pair__insight">${escapeHtml(mapping.candidate_rationale)}</p>
          </div>
        ` : ''}
      </div>

      ${params.length > 0 ? `
        <div class="param-mapping">
          <div class="param-mapping__title">
            <div class="param-mapping__title-label">${T('page.phenomenon.param_mapping_label', '参数对照')}</div>
            <div class="param-mapping__title-hint">${T('page.phenomenon.param_mapping_hint', 'AI 提出的 A ↔ B 变量对应，需领域数据验证')}</div>
          </div>
          <div class="param-mapping__grid">
            <div class="param-mapping__head">${escapeHtml(a.domain)} · ${escapeHtml(a.name)}</div>
            <div></div>
            <div class="param-mapping__head param-mapping__head--right">${escapeHtml(b.domain)} · ${escapeHtml(b.name)}</div>

            ${params.map(p => `
              <div class="param-mapping__row">
                <div class="param-mapping__row-a">
                  <span class="param-mapping__term">${escapeHtml(p.a_term || '')}</span>
                  ${p.a_symbol ? `<span class="param-mapping__symbol">${escapeHtml(p.a_symbol)}</span>` : ''}
                </div>
                <div class="param-mapping__connector">↔</div>
                <div class="param-mapping__row-b">
                  <span class="param-mapping__term">${escapeHtml(p.b_term || '')}</span>
                  ${p.b_symbol ? `<span class="param-mapping__symbol">${escapeHtml(p.b_symbol)}</span>` : ''}
                </div>
                ${p.note ? `<div class="param-mapping__note">${escapeHtml(p.note)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      <div class="mapping-tests" aria-label="${phenomenonCopy('反证与适用边界', 'Falsification and boundaries')}">
        <section class="mapping-tests__card">
          <h3>${phenomenonCopy('还可能是什么', 'What else could explain it')}</h3>
          <ul>${alternatives.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
        </section>
        <section class="mapping-tests__card mapping-tests__card--failure">
          <h3>${phenomenonCopy('何时应否定或停止', 'When to reject or stop')}</h3>
          <ul>${failures.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
        </section>
      </div>

      ${actions.length > 0 ? `
        <div class="ph-actions">
          <header class="ph-actions__header">
            <div class="ph-actions__title">${phenomenonCopy('可区分的验证计划', 'Discriminating validation plan')}</div>
            <div class="ph-actions__subtitle">${phenomenonCopy('先检验候选映射，再决定是否迁移任何方法。', 'Test the candidate mapping before transferring any method.')}</div>
          </header>
          ${actions.map((act, i) => `
            <div class="ph-action">
              <div class="ph-action__number">${i + 1}</div>
              <div class="ph-action__main">
                <div class="ph-action__title">${escapeHtml(act.title || '')}</div>
                <div class="ph-action__description">${escapeHtml(act.description || '')}</div>
                <div class="ph-action__scenario"><strong>${phenomenonCopy('测试场景：', 'Test context: ')}</strong>${escapeHtml(act.scenario)}</div>
                <div class="ph-action__failure"><strong>${phenomenonCopy('失败信号：', 'Failure signal: ')}</strong>${escapeHtml(act.failure_signal)}</div>
              </div>
            </div>
          `).join('')}
        </div>
      ` : ''}

      ${mapping.why_worth_testing ? `
        <div class="ph-why">
          <div class="ph-why__icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
          </div>
          <div class="ph-why__content">
            <div class="ph-why__label">${T('page.phenomenon.why_important_label', '为什么值得检验')}</div>
            <div class="ph-why__text">${escapeHtml(mapping.why_worth_testing)}</div>
          </div>
        </div>
      ` : ''}

      <div class="ph-share">
        <div class="ph-share__text">
          <div class="ph-share__label">${T('page.phenomenon.share_label', '分享这个候选映射')}</div>
          <div class="ph-share__hint">${T('page.phenomenon.share_hint', '生成带待验证边界的图片，避免把候选映射误传为已确认发现')}</div>
        </div>
        <div class="ph-share__actions">
          <button type="button" class="btn btn--secondary btn--sm" id="share-preview">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/></svg>
            ${T('page.phenomenon.share_preview', '预览')}
          </button>
          <button type="button" class="btn btn--secondary btn--sm" id="share-copy">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            ${T('page.phenomenon.share_copy', '复制图片')}
          </button>
          <button type="button" class="btn btn--primary btn--sm" id="share-download">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
            ${T('page.phenomenon.share_download', '下载图片')}
          </button>
        </div>
      </div>
    </section>
  `;
}

// Attach share handlers after rendering (called from streamMapping done handler)
function attachShareHandlers(a, b, similarity, mapping) {
  const safeMapping = normalizeCandidateMapping(mapping);
  if (!safeMapping) return;
  const dataForCard = { a, b, retrieval_similarity: null, mapping: safeMapping };
  const safeName = `${(a.name || '').replace(/[^\w\u4e00-\u9fa5-]/g, '')}-${(b.name || '').replace(/[^\w\u4e00-\u9fa5-]/g, '')}.png`;

  const previewBtn = document.getElementById('share-preview');
  const copyBtn = document.getElementById('share-copy');
  const dlBtn = document.getElementById('share-download');

  if (previewBtn) {
    previewBtn.addEventListener('click', () => {
      const canvas = ShareCard.render(dataForCard);
      ShareCard.openModal(canvas, safeName);
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const canvas = ShareCard.render(dataForCard);
      const ok = await ShareCard.copy(canvas);
      showToast(ok ? T('page.phenomenon.toast_copied', '已复制到剪贴板') : T('page.phenomenon.toast_copy_failed', '复制失败，请改用下载'));
    });
  }

  if (dlBtn) {
    dlBtn.addEventListener('click', () => {
      const canvas = ShareCard.render(dataForCard);
      ShareCard.download(canvas, safeName);
      showToast(T('page.phenomenon.toast_downloaded', '已下载'));
    });
  }
}

function decodeMappingEventBlock(block) {
  let eventName = 'message';
  const data = [];
  block.split(/\r?\n/).forEach((line) => {
    if (line.startsWith('event:')) eventName = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  });
  return { type: eventName, data: data.join('\n') };
}

function openMappingStream(payload) {
  const controller = new AbortController();
  const listeners = new Map();
  let closed = false;
  let terminal = false;
  let timeoutId = null;
  const connection = {
    onerror: null,
    addEventListener(type, handler) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(handler);
    },
    close() {
      if (closed) return;
      closed = true;
      if (timeoutId) clearTimeout(timeoutId);
      controller.abort();
      if (_phActiveMappingStream === connection) _phActiveMappingStream = null;
    },
  };
  const emit = (type, data) => {
    (listeners.get(type) || []).slice().forEach((handler) => {
      try { handler({ data }); } catch (_) { /* UI handler owns its safe state */ }
    });
  };
  const transportError = (error) => {
    if (!closed && typeof connection.onerror === 'function') connection.onerror(error);
  };

  Promise.resolve().then(async () => {
    timeoutId = setTimeout(() => {
      if (closed || terminal) return;
      controller.abort();
      transportError(new Error('mapping_timeout'));
    }, 180000);
    try {
      const response = await fetch('/api/mapping/stream', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok) {
        let problem = null;
        try { problem = await response.json(); } catch (_) { problem = null; }
        emit('error', JSON.stringify({
          message: problem && typeof problem.error === 'string'
            ? problem.error : `HTTP ${response.status}`,
        }));
        terminal = true;
        return;
      }
      if (!response.body) throw new Error('mapping_stream_unavailable');
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      while (!closed) {
        const part = await reader.read();
        buffer += decoder.decode(part.value || new Uint8Array(), { stream: !part.done });
        let boundary;
        while ((boundary = buffer.search(/\r?\n\r?\n/)) !== -1) {
          const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)[0];
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + separator.length);
          if (!block.trim()) continue;
          const event = decodeMappingEventBlock(block);
          if (event.type === 'done' || event.type === 'error') terminal = true;
          emit(event.type, event.data);
        }
        if (part.done) break;
      }
      if (!closed && !terminal) throw new Error('mapping_stream_incomplete');
    } catch (error) {
      if (!closed && !(error && error.name === 'AbortError')) transportError(error);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }
  });
  return connection;
}

function streamMapping(aSource, bId, slot, fallbackA, fallbackB) {
  // aSource is either { kind: 'id', value: 'xxx' } or { kind: 'text', value: '...' }
  const payload = { b_id: bId, lang: currentPhenomenonLang() };
  if (aSource.kind === 'id') {
    payload.a_id = aSource.value;
  } else {
    payload.text_a = aSource.value;
  }
  const es = openMappingStream(payload);
  _phActiveMappingStream = es;
  let meta = null;
  let scrolled = false;
  let completed = false;

  const eventData = (event) => {
    try {
      const value = JSON.parse(event.data || '{}');
      return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
    } catch {
      return null;
    }
  };

  const closeStream = () => {
    es.close();
    if (_phActiveMappingStream === es) _phActiveMappingStream = null;
  };

  const showRecoverableError = (error) => {
    slot.innerHTML = renderMappingError(error);
    const retry = slot.querySelector('[data-mapping-retry]');
    if (retry) {
      retry.addEventListener('click', () => {
        closeActiveMappingStream();
        slot.innerHTML = renderMappingLoading();
        streamMapping(aSource, bId, slot, fallbackA, fallbackB);
      }, { once: true });
    }
  };

  const renderValidatedMapping = (value) => {
    if (!meta) return false;
    const mapping = normalizeCandidateMapping(value);
    if (!mapping) return false;
    slot.innerHTML = renderMappingPair(meta.a, meta.b, meta.retrieval_similarity, mapping);
    if (window.renderMath) window.renderMath(slot);
    attachShareHandlers(meta.a, meta.b, meta.retrieval_similarity, mapping);
    return true;
  };

  es.addEventListener('meta', (e) => {
    const rawMeta = eventData(e);
    const rawA = rawMeta ? normalizeMappingSide(rawMeta.a) : null;
    const rawB = rawMeta ? normalizeMappingSide(rawMeta.b) : null;
    if (!rawMeta || rawMeta.schema_version !== 'mapping-stream-meta-v2'
        || !rawA || !rawB
        || typeof rawMeta.retrieval_similarity !== 'number'
        || !Number.isFinite(rawMeta.retrieval_similarity)
        || rawMeta.retrieval_similarity < -1 || rawMeta.retrieval_similarity > 1) {
      completed = true;
      showRecoverableError(new Error(phenomenonCopy('映射元数据无效', 'Invalid mapping metadata')));
      closeStream();
      return;
    }
    const translatedA = normalizeMappingSide(fallbackA);
    const translatedB = normalizeMappingSide(fallbackB);
    meta = {
      a: translatedA && translatedA.id === rawA.id ? translatedA : rawA,
      b: translatedB && translatedB.id === rawB.id ? translatedB : rawB,
      retrieval_similarity: rawMeta.retrieval_similarity,
    };
    slot.innerHTML = renderMappingStreaming(meta.a, meta.b, meta.retrieval_similarity, 0);
    if (!scrolled) {
      scrolled = true;
      requestAnimationFrame(() => {
        slot.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  });

  es.addEventListener('cache', (e) => {
    const data = eventData(e);
    if (!data || !renderValidatedMapping(data.mapping)) {
      completed = true;
      showRecoverableError(new Error(phenomenonCopy('缓存映射未通过校验', 'Cached mapping failed validation')));
      closeStream();
    }
  });

  es.addEventListener('text', (e) => {
    const chunk = eventData(e);
    if (!meta || !chunk || typeof chunk.total_length !== 'number' || !Number.isFinite(chunk.total_length)) return;
    const totalLength = Math.max(0, Math.min(100000, Math.floor(chunk.total_length)));
    slot.innerHTML = renderMappingStreaming(meta.a, meta.b, meta.retrieval_similarity, totalLength);
  });

  es.addEventListener('done', (e) => {
    const data = eventData(e);
    completed = true;
    if (!data || !renderValidatedMapping(data.mapping)) {
      showRecoverableError(new Error(phenomenonCopy('候选映射未通过安全校验', 'The candidate mapping failed validation')));
    }
    closeStream();
  });

  es.addEventListener('error', (e) => {
    const data = eventData(e);
    completed = true;
    const safeCodes = ['upstream_timeout', 'upstream_unreachable', 'upstream_error', 'invalid_mapping_output'];
    const code = data && safeCodes.includes(data.message) ? data.message : 'upstream_error';
    console.error('[phenomenon] mapping stream failed');
    showRecoverableError(new Error(phenomenonCopy('暂时无法生成可复核的候选映射', 'A reviewable candidate mapping is temporarily unavailable')));
    closeStream();
  });

  es.onerror = (err) => {
    if (completed) return;
    console.error('[phenomenon] stream transport failed');
    completed = true;
    showRecoverableError(new Error(T('page.phenomenon.connection_lost', '连接中断')));
    closeStream();
  };
}

function renderMappingStreaming(a, b, similarity, charCount) {
  const queryMode = b.id === '__query__';
  const bName = queryMode ? (b.original_query || b.name) : b.name;
  const bDesc = queryMode && b.description === b.original_query ? '' : b.description;
  return `
    <section class="ph-mapping">
      <div class="mapping-pair${queryMode ? ' mapping-pair--query' : ''}">
        <div class="mapping-pair__heads">
          <div class="mapping-pair__head">
            <span class="mapping-pair__head-domain">${escapeHtml(a.domain)}</span>
            <h2 class="mapping-pair__head-name">${escapeHtml(a.name)}</h2>
            <p class="mapping-pair__head-desc">${escapeHtml(a.description)}</p>
          </div>
          <div class="mapping-pair__connector">
            <div class="mapping-pair__symbol" aria-label="candidate mapping">≈?</div>
          </div>
          <div class="mapping-pair__head mapping-pair__head--right">
            <span class="mapping-pair__head-domain">${escapeHtml(b.domain)}</span>
            <h2 class="mapping-pair__head-name">${escapeHtml(bName)}</h2>
            ${bDesc ? `<p class="mapping-pair__head-desc">${escapeHtml(bDesc)}</p>` : ''}
          </div>
        </div>
      </div>
      <div class="mapping-loading" style="margin-top: var(--space-4)">
        <div class="mapping-loading__dots">
          <span class="mapping-loading__dot"></span>
          <span class="mapping-loading__dot"></span>
          <span class="mapping-loading__dot"></span>
        </div>
        <div class="mapping-loading__text">${T('page.phenomenon.mapping_streaming_text', '正在生成待验证的候选结构映射')}</div>
        <div class="mapping-loading__hint">${charCount > 0 ? `${T('page.phenomenon.mapping_received_prefix', '已接收')} ${charCount} ${T('page.phenomenon.mapping_received_suffix', '字')}` : T('page.phenomenon.mapping_starting', '即将开始…')}</div>
      </div>
    </section>
  `;
}

async function loadPhenomenon(id, pairId, navigationContext, requestedLang) {
  const lang = requestedLang === 'en' ? 'en' : 'zh';
  const generation = ++_phLoadGeneration;
  closeActiveMappingStream();
  renderLoadingHero();
  _phId = id;
  _phPairId = pairId;
  _phNavigationContext = navigationContext;
  _phData = null;
  _phDataLang = null;
  _phRequestedLang = lang;
  const crumbName = $('#ph-crumb-name');
  if (crumbName) crumbName.textContent = lang === 'en' ? 'Phenomenon' : '现象';
  document.title = lang === 'en' ? 'Phenomenon — Structural' : '现象详情 — Structural';

  try {
    const data = await StructuralAPI.getPhenomenon(id);
    if (generation !== _phLoadGeneration || currentPhenomenonLang() !== lang) return;
    _phData = data;
    _phDataLang = lang;
    _phRequestedLang = null;
    renderPhenomenon(data, id, pairId, navigationContext);
  } catch (err) {
    if (generation !== _phLoadGeneration || currentPhenomenonLang() !== lang) return;
    _phRequestedLang = null;
    renderPhenomenonError(err);
  }
}

function renderPhenomenon(data, id, pairId, navigationContext) {
  const p = data.phenomenon;
  if (!p) {
    renderPhenomenonError(new Error(T('page.phenomenon.not_found', '现象未找到')));
    return;
  }

  // Update title and breadcrumb
  document.title = `${p.name} — Structural`;
  const crumbName = $('#ph-crumb-name');
  if (crumbName) crumbName.textContent = p.name;

  syncPrivateSearchBreadcrumb(navigationContext);

  const container = $('#ph-content');

  // Layout depends on whether user came from a query or from a pair click
  if (navigationContext) {
    // "From search" flow: the mapping is the main event.
    // Below the fold: more answers to the user's original question,
    // then a compact view of this phenomenon, then cross-structure options.
    container.innerHTML = `
      <div id="ph-mapping-slot" class="ph-mapping-hero"></div>
      <div class="ph-secondary">
        <div id="ph-more-answers-slot"></div>
        <div id="ph-about-slot"></div>
        ${renderSameStructure(data.same_structure || [])}
      </div>
    `;

    // Mapping stream
    const slot = $('#ph-mapping-slot');
    slot.innerHTML = renderMappingLoading();
    streamMapping({ kind: 'text', value: navigationContext.query }, id, slot, p, null);

    const moreSlot = $('#ph-more-answers-slot');
    if (moreSlot) {
      moreSlot.innerHTML = renderMoreAnswers(navigationContext.results, id, navigationContext);
      attachPrivateQueryNavigation(moreSlot, navigationContext);
    }

    // "About this phenomenon" — compact hero with a link to deep-dive
    const aboutSlot = $('#ph-about-slot');
    if (aboutSlot) {
      aboutSlot.innerHTML = `
        <section class="ph-section ph-section--muted">
          <header class="ph-section__header">
            <div>
              <span class="ph-section__eyebrow">${T('page.phenomenon.about_label', '关于这个现象')}</span>
              <h2 class="ph-section__title">${escapeHtml(p.name)}</h2>
            </div>
            <p class="ph-section__caption">${escapeHtml(p.domain)} · ${T('page.phenomenon.structure_prefix', '候选结构')} ${escapeHtml(p.type_id)}</p>
          </header>
          <p class="ph-about__text">${escapeHtml(p.description)}</p>
          ${renderCandidateEvidence(p)}
          <div class="ph-section__footer">
            <a href="/phenomenon/${encodeURIComponent(id)}" class="btn btn--ghost">
              ${T('page.phenomenon.view_full_info', '查看这个现象的完整信息')}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
            </a>
          </div>
        </section>
      `;
    }
  } else if (pairId) {
    // "Pair click" flow: same as before — mapping between two KB phenomena
    container.innerHTML = `
      ${renderHero(p)}
      <div id="ph-mapping-slot"></div>
      ${renderCrossDomainList(data.similar || [], id)}
      ${renderSameStructure(data.same_structure || [])}
    `;
    const slot = $('#ph-mapping-slot');
    slot.innerHTML = renderMappingLoading();
    const translatedPair = [...(data.similar || []), ...(data.same_structure || [])]
      .find((item) => item && item.id === pairId) || null;
    streamMapping({ kind: 'id', value: id }, pairId, slot, p, translatedPair);
  } else {
    // Direct access: hero + structure block + analyze CTA + cross-domain + same-structure + v2 hub
    const hasSameStructure = (data.same_structure || []).length > 0;
    container.innerHTML = `
      ${renderHero(p)}
      ${renderStructureBlock(p)}
      ${renderAnalyzeCTA(p)}
      ${renderCrossDomainList(data.similar || [], id)}
      ${renderSameStructure(data.same_structure || [], { emphasize: hasSameStructure })}
      ${renderV2Pairs(data.v2_pairs || [], id)}
    `;
  }
}

function renderPhenomenonError(err) {
  console.error('[phenomenon] load failed');
  const container = $('#ph-content');
  const isNotFound = /\b404\b/.test(err.message || '');
  if (isNotFound) {
    // Match the full-page /404 empty state: "现象未被收录"
    document.title = T('page.phenomenon.not_found_title', phenomenonCopy('没找到 — Structural', 'Not found — Structural'));
    const crumbName = $('#ph-crumb-name');
    if (crumbName) crumbName.textContent = T('page.phenomenon.not_found_crumb', phenomenonCopy('未找到', 'Not found'));
    container.innerHTML = `
      <div class="search-empty" style="padding: var(--space-8) var(--space-5); text-align: center;">
        <div style="font-family: var(--font-serif); font-size: 96px; line-height: 1; color: var(--text-primary); letter-spacing: var(--ls-tighter); margin-bottom: var(--space-4);">404</div>
        <h2 class="search-empty__title">${T('page.phenomenon.not_found_title_body', phenomenonCopy('这个现象还没有被收录', "This phenomenon hasn't been indexed yet"))}</h2>
        <p class="search-empty__text">${T('page.phenomenon.not_found_text', phenomenonCopy('你要找的现象不存在。<br>也许我们的知识库还没有覆盖到它。', "The phenomenon you're looking for doesn't exist.<br>Our knowledge base may not cover it yet."))}</p>
        <div class="search-empty__actions">
          <a href="/" class="btn btn--primary btn--lg">${T('page.phenomenon.back_home', phenomenonCopy('返回首页', 'Back to home'))}</a>
          <a href="/discoveries" class="btn btn--ghost">${T('page.phenomenon.view_discoveries', phenomenonCopy('查看精选发现', 'View featured discoveries'))}</a>
        </div>
      </div>
    `;
  } else {
    container.innerHTML = `
      <div class="search-empty">
        <svg class="search-empty__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
        </svg>
        <h2 class="search-empty__title">${T('page.phenomenon.load_failed', phenomenonCopy('未能加载此现象', 'Failed to load this phenomenon'))}</h2>
        <p class="search-empty__text">${T('page.phenomenon.load_failed_text', phenomenonCopy('当前语言的现象记录加载失败。请重试，或返回首页继续探索。', 'The phenomenon record failed to load in the selected language. Try again or return home to keep exploring.'))}</p>
        <div class="search-empty__actions">
          <a href="/" class="btn btn--primary">${T('page.phenomenon.back_home', phenomenonCopy('返回首页', 'Back to home'))}</a>
        </div>
      </div>
    `;
  }
}

function resolvePhenomenonNavigationContext(id) {
  let params;
  try { params = new URLSearchParams(window.location.search); } catch (_) { return null; }
  const stateContext = history.state && history.state.structuralPrivateNavigation;
  const hasTypedState = stateContext && stateContext.kind === 'phenomenon';
  const hasSensitiveNavigation = params.has('context') || params.has('q') ||
    params.has('from_query') || params.has('text_a');
  if (!hasSensitiveNavigation && !hasTypedState) return null;
  if (typeof window.resolvePrivateNavigationContext !== 'function') {
    try {
      ['context', 'q', 'from_query', 'text_a'].forEach((name) => params.delete(name));
      history.replaceState(history.state || {}, '', window.location.pathname +
        (params.toString() ? '?' + params.toString() : '') + window.location.hash);
    } catch (_) { /* error UI remains fail closed */ }
    privateNavigationUnavailable();
    return null;
  }
  return window.resolvePrivateNavigationContext({
    kind: 'phenomenon',
    id,
    key: params.get('context'),
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  const id = resolvePhenomenonId();
  const pair = getQueryParam('pair');
  if (id) {
    const navigationContext = resolvePhenomenonNavigationContext(id);
    loadPhenomenon(id, pair, navigationContext, currentPhenomenonLang());
  } else {
    // No phenomenon id in URL — redirect to home.
    window.location.replace('/');
  }
});

// Re-render when language toggles
try {
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(function () {
      try {
        if (!_phId) return;
        const nextLang = currentPhenomenonLang();
        if (_phData && _phDataLang === nextLang) {
          // The language did not change; this is the i18n registry completing
          // its async load. Re-rendering same-language data is safe.
          closeActiveMappingStream();
          renderPhenomenon(_phData, _phId, _phPairId, _phNavigationContext);
        } else if (_phRequestedLang !== nextLang) {
          // A real language change invalidates the API payload. Clear the old
          // language immediately and fetch a new payload; generation checks
          // prevent a slower prior request from overwriting the new language.
          loadPhenomenon(_phId, _phPairId, _phNavigationContext, nextLang);
        }
      } catch (e) { /* ignore */ }
    });
  }
} catch (e) {}
