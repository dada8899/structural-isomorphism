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
        <span class="ph-hero__meta-type">结构 ${escapeHtml(p.type_id)}</span>
      </div>
      <h1 class="ph-hero__name">${escapeHtml(p.name)}</h1>
      <p class="ph-hero__description">${escapeHtml(p.description)}</p>
    </div>
  `;
}

function renderHeroCompact(p) {
  return `
    <div class="ph-hero-compact">
      <div class="ph-hero-compact__label">关于这个现象</div>
      <div class="ph-hero-compact__meta">
        <span class="ph-hero__meta-domain">${escapeHtml(p.domain)}</span>
        <span class="ph-hero__meta-type">结构 ${escapeHtml(p.type_id)}</span>
      </div>
      <h2 class="ph-hero-compact__name">${escapeHtml(p.name)}</h2>
      <p class="ph-hero-compact__description">${escapeHtml(p.description)}</p>
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
          跨领域的同构现象
          <span class="ph-section__badge">${filtered.length}</span>
        </h2>
        <p class="ph-section__caption">点击任意一个现象，查看它和当前现象的结构映射</p>
      </header>
      <div class="ph-cross">
        ${filtered.map((x, i) => `
          <a class="ph-cross__card" href="/phenomenon/${encodeURIComponent(currentId)}?pair=${encodeURIComponent(x.id)}" style="animation: fadeInUp 500ms var(--ease-out-expo) ${i * 40}ms both">
            <div class="ph-cross__card-main">
              <span class="ph-cross__card-domain">${escapeHtml(x.domain)} · 结构 ${escapeHtml(x.type_id)}</span>
              <h3 class="ph-cross__card-name">${escapeHtml(x.name)}</h3>
              <p class="ph-cross__card-desc">${escapeHtml(x.description)}</p>
            </div>
            <div class="ph-cross__card-score">${Math.round((x.score || 0) * 100)}</div>
          </a>
        `).join('')}
      </div>
    </section>
  `;
}

/**
 * "More answers to your question" — recommends based on the user's original query,
 * not the current phenomenon. Used in from_query mode.
 */
function renderMoreAnswers(queryResults, currentId, fromQuery) {
  if (!queryResults || queryResults.length === 0) return '';
  const filtered = queryResults.filter(x => x.id !== currentId).slice(0, 6);
  if (filtered.length === 0) return '';

  return `
    <section class="ph-section ph-section--primary">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">继续探索你的问题</span>
          <h2 class="ph-section__title">你问题的其他答案</h2>
        </div>
        <p class="ph-section__caption">和“${escapeHtml(fromQuery)}”结构最相似的其他现象。点进去看它们如何映射到你的问题。</p>
      </header>
      <div class="ph-cross">
        ${filtered.map((x, i) => `
          <a class="ph-cross__card" href="/phenomenon/${encodeURIComponent(x.id)}?from_query=${encodeURIComponent(fromQuery)}" style="animation: fadeInUp 500ms var(--ease-out-expo) ${i * 40}ms both">
            <div class="ph-cross__card-main">
              <span class="ph-cross__card-domain">${escapeHtml(x.domain)} · 结构 ${escapeHtml(x.type_id)}</span>
              <h3 class="ph-cross__card-name">${escapeHtml(x.name)}</h3>
              <p class="ph-cross__card-desc">${escapeHtml(x.description)}</p>
            </div>
            <div class="ph-cross__card-score">${Math.round((x.score || 0) * 100)}</div>
          </a>
        `).join('')}
      </div>
      <div class="ph-section__footer">
        <a href="/search?q=${encodeURIComponent(fromQuery)}" class="btn btn--ghost">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          返回所有结果
        </a>
      </div>
    </section>
  `;
}

function renderSameStructure(items, opts = {}) {
  if (!items || items.length === 0) return '';
  const caption = opts.emphasize
    ? '这些现象共享同一个数学骨架，可相互迁移。'
    : '共享相同数学结构的其他已知现象';
  return `
    <section class="ph-section ph-section--muted">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">开阔视野</span>
          <h2 class="ph-section__title">同一结构的其他现象</h2>
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
          </a>
        `).join('')}
      </div>
    </section>
  `;
}

/**
 * Direct-access extras: structure block + CTA into the 8-section deep analyze report.
 * Shown only when user lands on /phenomenon/:id with no ?pair / ?from_query context.
 */
function renderStructureBlock(p) {
  if (!p || !p.type_id) return '';
  return `
    <section class="ph-section ph-section--muted">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">结构类型</span>
          <h2 class="ph-section__title">
            结构 ${escapeHtml(p.type_id)}
            <span class="ph-section__badge">数学骨架</span>
          </h2>
        </div>
        <p class="ph-section__caption">这个编号代表一类共享的数学结构，不同领域的许多现象都落在同一个骨架之下。</p>
      </header>
      <p class="ph-about__text">${escapeHtml(p.name)} 属于结构 ${escapeHtml(p.type_id)}。沿着这个骨架，你可以在其他领域找到行为高度相似的现象，并把它们的成熟做法迁移到当前问题上。</p>
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
          <span class="ph-section__eyebrow">V2 管道</span>
          <h2 class="ph-section__title">V2 模型识别的跨域同构</h2>
        </div>
        <p class="ph-section__caption">这个现象在 V2 管道里被发现连接到 ${count} 个其他领域的现象。每对都经过 LLM 评分。</p>
      </header>
      <div class="ph-v2-hub__grid">
        ${pairs.map((x, i) => {
          const simPct = Math.round((x.similarity || 0) * 100);
          const scoreClass = x.score >= 5 ? 'ph-v2-pair-card__score-badge--hi' : 'ph-v2-pair-card__score-badge--lo';
          const href = `/analyze?a_id=${encodeURIComponent(currentId)}&id=${encodeURIComponent(x.other_id)}`;
          return `
            <a class="ph-v2-pair-card" href="${href}" style="animation: fadeInUp 500ms var(--ease-out-expo) ${i * 30}ms both">
              <div class="ph-v2-pair-card__sim">${simPct}%</div>
              <div class="ph-v2-pair-card__domain">${escapeHtml(x.other_domain || '')}</div>
              <h3 class="ph-v2-pair-card__name">${escapeHtml(x.other_name || '')}</h3>
              <p class="ph-v2-pair-card__reason">${escapeHtml(x.reason || '')}</p>
              <div class="ph-v2-pair-card__score-badge ${scoreClass}">V2 ${x.score} 分</div>
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
  const href = `/analyze?id=${encodeURIComponent(p.id)}&q=${encodeURIComponent(q)}`;
  return `
    <section class="ph-section ph-section--primary ph-cta-analyze">
      <header class="ph-section__header">
        <div>
          <span class="ph-section__eyebrow">深度分析</span>
          <h2 class="ph-section__title">发起这个现象的跨学科迁移研究</h2>
        </div>
        <p class="ph-section__caption">8 段跨学科深度分析，约 60-90 秒流式生成</p>
      </header>
      <p class="ph-about__text">以 ${escapeHtml(p.name)} 为起点，让 LLM 沿着它的数学骨架跨越领域边界，生成一份 8 段结构化迁移报告：共享结构 → 参数对照 → 方法借用 → 行动建议。</p>
      <div class="ph-cta-analyze__actions">
        <a href="${href}" class="btn btn--primary ph-cta-analyze__btn">
          生成深度分析报告
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
        </a>
        <span class="ph-cta-analyze__hint">8 段跨学科迁移研究</span>
      </div>
    </section>
  `;
}

/**
 * Get the last search from sessionStorage, if it matches the current query.
 * Returns null otherwise (and triggers a re-fetch).
 */
function getStashedSearchResults(query) {
  try {
    const raw = sessionStorage.getItem('structural_last_search');
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed.query !== query) return null;
    // 30 min TTL
    if (Date.now() - (parsed.timestamp || 0) > 30 * 60 * 1000) return null;
    return parsed.results || [];
  } catch {
    return null;
  }
}

async function fetchSearchResults(query) {
  try {
    const data = await StructuralAPI.search(query, 20);
    return data.results || [];
  } catch (e) {
    console.error('Re-search failed:', e);
    return [];
  }
}

function renderMappingLoading() {
  return `
    <div class="mapping-loading">
      <div class="mapping-loading__dots">
        <span class="mapping-loading__dot"></span>
        <span class="mapping-loading__dot"></span>
        <span class="mapping-loading__dot"></span>
      </div>
      <div class="mapping-loading__text">正在分析两个现象之间的结构映射</div>
      <div class="mapping-loading__hint">LLM 生成可能需要 5-10 秒</div>
    </div>
  `;
}

function renderMappingError(err) {
  return `
    <div class="search-error">
      <div class="search-error__title">映射生成失败</div>
      <div class="search-error__text">${escapeHtml(err.message || String(err))}</div>
    </div>
  `;
}

function renderMappingPair(a, b, similarity, mapping) {
  const params = mapping.parameter_mapping || [];
  const actions = mapping.action_suggestions || [];
  const hasFormula = mapping.formula && mapping.formula.trim();
  const isQueryMode = a.id === '__query__';

  // In query mode, A is the user's question — render it differently
  const aName = isQueryMode ? (a.original_query || a.name) : a.name;
  const aDesc = isQueryMode
    ? (a.description && a.description !== a.original_query ? `已改写为：${a.description}` : '')
    : a.description;

  return `
    <section class="ph-mapping">
      <!-- Pair head -->
      <div class="mapping-pair${isQueryMode ? ' mapping-pair--query' : ''}">
        <div class="mapping-pair__heads">
          <div class="mapping-pair__head">
            <span class="mapping-pair__head-domain">${escapeHtml(a.domain)}</span>
            <h2 class="mapping-pair__head-name">${escapeHtml(aName)}</h2>
            ${aDesc ? `<p class="mapping-pair__head-desc">${escapeHtml(aDesc)}</p>` : ''}
          </div>
          <div class="mapping-pair__connector">
            <div class="mapping-pair__symbol">≅</div>
            <div class="mapping-pair__score">${Math.round((similarity || 0) * 100)}%</div>
          </div>
          <div class="mapping-pair__head mapping-pair__head--right">
            <span class="mapping-pair__head-domain">${escapeHtml(b.domain)}</span>
            <h2 class="mapping-pair__head-name">${escapeHtml(b.name)}</h2>
            <p class="mapping-pair__head-desc">${escapeHtml(b.description)}</p>
          </div>
        </div>

        ${mapping.structure_name ? `
          <div class="mapping-pair__structure">
            <div class="mapping-pair__structure-label">共享数学结构</div>
            <div class="mapping-pair__structure-name">${escapeHtml(mapping.structure_name)}</div>
            ${hasFormula ? `<div class="mapping-pair__formula">${escapeHtml(mapping.formula)}</div>` : ''}
            ${mapping.core_insight ? `<p class="mapping-pair__insight">${escapeHtml(mapping.core_insight)}</p>` : ''}
          </div>
        ` : ''}
      </div>

      ${params.length > 0 ? `
        <div class="param-mapping">
          <div class="param-mapping__title">
            <div class="param-mapping__title-label">参数对照</div>
            <div class="param-mapping__title-hint">A 中的每个变量，在 B 中叫什么</div>
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

      ${actions.length > 0 ? `
        <div class="ph-actions">
          <header class="ph-actions__header">
            <div class="ph-actions__title">从 ${escapeHtml(a.domain)} 借用到 ${escapeHtml(b.domain)}</div>
            <div class="ph-actions__subtitle">把源领域的成熟做法翻译成你能用的行动建议</div>
          </header>
          ${actions.map((act, i) => `
            <div class="ph-action">
              <div class="ph-action__number">${i + 1}</div>
              <div class="ph-action__main">
                <div class="ph-action__title">${escapeHtml(act.title || '')}</div>
                <div class="ph-action__description">${escapeHtml(act.description || '')}</div>
                ${act.scenario ? `<div class="ph-action__scenario">适用场景：${escapeHtml(act.scenario)}</div>` : ''}
              </div>
            </div>
          `).join('')}
        </div>
      ` : ''}

      ${mapping.why_important ? `
        <div class="ph-why">
          <div class="ph-why__icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
          </div>
          <div class="ph-why__content">
            <div class="ph-why__label">为什么这重要</div>
            <div class="ph-why__text">${escapeHtml(mapping.why_important)}</div>
          </div>
        </div>
      ` : ''}

      <div class="ph-share">
        <div class="ph-share__text">
          <div class="ph-share__label">分享这个发现</div>
          <div class="ph-share__hint">生成一张精美的图片，粘到任何地方都能传递核心洞察</div>
        </div>
        <div class="ph-share__actions">
          <button type="button" class="btn btn--secondary btn--sm" id="share-preview">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/></svg>
            预览
          </button>
          <button type="button" class="btn btn--secondary btn--sm" id="share-copy">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            复制图片
          </button>
          <button type="button" class="btn btn--primary btn--sm" id="share-download">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
            下载图片
          </button>
        </div>
      </div>
    </section>
  `;
}

// Attach share handlers after rendering (called from streamMapping done handler)
function attachShareHandlers(a, b, similarity, mapping) {
  const dataForCard = { a, b, similarity, mapping };

  const previewBtn = document.getElementById('share-preview');
  const copyBtn = document.getElementById('share-copy');
  const dlBtn = document.getElementById('share-download');

  if (previewBtn) {
    previewBtn.addEventListener('click', () => {
      const canvas = ShareCard.render(dataForCard);
      showSharePreview(canvas);
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const canvas = ShareCard.render(dataForCard);
      const ok = await ShareCard.copy(canvas);
      showToast(ok ? '已复制到剪贴板' : '复制失败，请改用下载');
    });
  }

  if (dlBtn) {
    dlBtn.addEventListener('click', () => {
      const canvas = ShareCard.render(dataForCard);
      const safeName = `${(a.name || '').replace(/[^\w\u4e00-\u9fa5-]/g, '')}-${(b.name || '').replace(/[^\w\u4e00-\u9fa5-]/g, '')}.png`;
      ShareCard.download(canvas, safeName);
      showToast('已下载');
    });
  }
}

function showSharePreview(canvas) {
  // Remove any existing modal
  document.querySelectorAll('.share-modal').forEach(m => m.remove());

  const modal = document.createElement('div');
  modal.className = 'share-modal';
  modal.innerHTML = `
    <div class="share-modal__backdrop"></div>
    <div class="share-modal__content">
      <button class="share-modal__close" aria-label="关闭">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
      <div class="share-modal__canvas-wrap"></div>
      <div class="share-modal__hint">1200 × 630 · 点击外部区域关闭</div>
    </div>
  `;

  const wrap = modal.querySelector('.share-modal__canvas-wrap');
  canvas.style.maxWidth = '100%';
  canvas.style.height = 'auto';
  canvas.style.borderRadius = '12px';
  canvas.style.boxShadow = '0 20px 60px rgba(0,0,0,0.3)';
  wrap.appendChild(canvas);

  const close = () => modal.remove();
  modal.querySelector('.share-modal__backdrop').addEventListener('click', close);
  modal.querySelector('.share-modal__close').addEventListener('click', close);
  document.addEventListener('keydown', function onEsc(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onEsc); }
  });

  document.body.appendChild(modal);
}

function streamMapping(aSource, bId, slot, fallbackA) {
  // aSource is either { kind: 'id', value: 'xxx' } or { kind: 'text', value: '...' }
  const params = new URLSearchParams();
  params.set('b_id', bId);
  if (aSource.kind === 'id') {
    params.set('a_id', aSource.value);
  } else {
    params.set('text_a', aSource.value);
  }
  const url = `/api/mapping/stream?${params.toString()}`;
  const es = new EventSource(url);
  let meta = null;
  let accumulatedText = '';
  let renderedOnce = false;
  let scrolled = false;

  const tryRenderPartial = () => {
    if (!meta || !accumulatedText) return;
    // Parse whatever valid JSON prefix we can get
    const partial = parsePartialJson(accumulatedText);
    if (!partial) {
      // Still show the streaming indicator with partial text
      if (!renderedOnce) {
        slot.innerHTML = renderMappingStreaming(meta.a, meta.b, meta.similarity, accumulatedText.length);
        renderedOnce = true;
      }
      return;
    }
    slot.innerHTML = renderMappingPair(meta.a, meta.b, meta.similarity, partial);
    renderedOnce = true;
    if (!scrolled) {
      scrolled = true;
      requestAnimationFrame(() => {
        slot.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  };

  es.addEventListener('meta', (e) => {
    meta = JSON.parse(e.data);
    slot.innerHTML = renderMappingStreaming(meta.a, meta.b, meta.similarity, 0);
    if (!scrolled) {
      scrolled = true;
      requestAnimationFrame(() => {
        slot.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  });

  es.addEventListener('cache', (e) => {
    const data = JSON.parse(e.data);
    if (meta) {
      slot.innerHTML = renderMappingPair(meta.a, meta.b, meta.similarity, data.mapping);
      if (window.renderMath) window.renderMath(slot);
      attachShareHandlers(meta.a, meta.b, meta.similarity, data.mapping);
    }
  });

  es.addEventListener('text', (e) => {
    const chunk = JSON.parse(e.data);
    accumulatedText += chunk.content;
    // Throttle partial rendering — every 300 chars
    if (accumulatedText.length % 300 < 50) {
      tryRenderPartial();
    }
  });

  es.addEventListener('done', (e) => {
    const data = JSON.parse(e.data);
    if (meta && data.mapping) {
      slot.innerHTML = renderMappingPair(meta.a, meta.b, meta.similarity, data.mapping);
      if (window.renderMath) window.renderMath(slot);
      attachShareHandlers(meta.a, meta.b, meta.similarity, data.mapping);
    }
    es.close();
  });

  es.addEventListener('error', (e) => {
    try {
      const data = JSON.parse(e.data || '{}');
      console.error('Mapping stream error:', data);
      slot.innerHTML = renderMappingError(new Error(data.message || 'Stream failed'));
    } catch {
      console.error('Mapping stream error event:', e);
      slot.innerHTML = renderMappingError(new Error('Connection lost'));
    }
    es.close();
  });

  es.onerror = (err) => {
    console.error('EventSource error:', err);
    if (!renderedOnce) {
      slot.innerHTML = renderMappingError(new Error('连接中断'));
    }
    es.close();
  };
}

function parsePartialJson(text) {
  // Try to parse the streamed JSON as it grows.
  // LLM returns a single JSON object; we can try parsing once we have enough closing braces.
  const trimmed = text.trim();
  if (!trimmed.startsWith('{')) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    // Try to extract partial fields with a lenient parse
    // Look for completed top-level keys
    try {
      // Simple recovery: find the last closing brace and try to parse up to there
      const lastBrace = trimmed.lastIndexOf('}');
      if (lastBrace > 0) {
        const candidate = trimmed.substring(0, lastBrace + 1);
        return JSON.parse(candidate);
      }
    } catch {}
    return null;
  }
}

function renderMappingStreaming(a, b, similarity, charCount) {
  return `
    <section class="ph-mapping">
      <div class="mapping-pair">
        <div class="mapping-pair__heads">
          <div class="mapping-pair__head">
            <span class="mapping-pair__head-domain">${escapeHtml(a.domain)}</span>
            <h2 class="mapping-pair__head-name">${escapeHtml(a.name)}</h2>
            <p class="mapping-pair__head-desc">${escapeHtml(a.description)}</p>
          </div>
          <div class="mapping-pair__connector">
            <div class="mapping-pair__symbol">≅</div>
            <div class="mapping-pair__score">${Math.round((similarity || 0) * 100)}%</div>
          </div>
          <div class="mapping-pair__head mapping-pair__head--right">
            <span class="mapping-pair__head-domain">${escapeHtml(b.domain)}</span>
            <h2 class="mapping-pair__head-name">${escapeHtml(b.name)}</h2>
            <p class="mapping-pair__head-desc">${escapeHtml(b.description)}</p>
          </div>
        </div>
      </div>
      <div class="mapping-loading" style="margin-top: var(--space-4)">
        <div class="mapping-loading__dots">
          <span class="mapping-loading__dot"></span>
          <span class="mapping-loading__dot"></span>
          <span class="mapping-loading__dot"></span>
        </div>
        <div class="mapping-loading__text">正在生成结构映射</div>
        <div class="mapping-loading__hint">${charCount > 0 ? `已接收 ${charCount} 字` : '即将开始…'}</div>
      </div>
    </section>
  `;
}

async function loadPhenomenon(id, pairId, fromQuery) {
  renderLoadingHero();

  try {
    const data = await StructuralAPI.getPhenomenon(id);
    const p = data.phenomenon;
    if (!p) throw new Error('现象未找到');

    // Update title and breadcrumb
    document.title = `${p.name} — Structural`;
    const crumbName = $('#ph-crumb-name');
    if (crumbName) crumbName.textContent = p.name;

    // Show "返回搜索" only if there's actually a recent query stash
    let lastQuery = null;
    try {
      const stash = sessionStorage.getItem('structural_last_search');
      if (stash) lastQuery = JSON.parse(stash).query;
    } catch (e) { /* ignore */ }
    const backLink = $('#ph-crumb-back');
    const backSep = $('#ph-crumb-back-sep');
    if (lastQuery && backLink && backSep) {
      backLink.removeAttribute('hidden');
      backSep.removeAttribute('hidden');
      backLink.setAttribute('href', `/search?q=${encodeURIComponent(lastQuery)}`);
    }

    const container = $('#ph-content');

    // Layout depends on whether user came from a query or from a pair click
    if (fromQuery) {
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
      streamMapping({ kind: 'text', value: fromQuery }, id, slot, p);

      // Load "more answers" (other results from the same query)
      (async () => {
        let queryResults = getStashedSearchResults(fromQuery);
        if (!queryResults) {
          queryResults = await fetchSearchResults(fromQuery);
        }
        const moreSlot = $('#ph-more-answers-slot');
        if (moreSlot) {
          moreSlot.innerHTML = renderMoreAnswers(queryResults, id, fromQuery);
        }
      })();

      // "About this phenomenon" — compact hero with a link to deep-dive
      const aboutSlot = $('#ph-about-slot');
      if (aboutSlot) {
        aboutSlot.innerHTML = `
          <section class="ph-section ph-section--muted">
            <header class="ph-section__header">
              <div>
                <span class="ph-section__eyebrow">关于这个现象</span>
                <h2 class="ph-section__title">${escapeHtml(p.name)}</h2>
              </div>
              <p class="ph-section__caption">${escapeHtml(p.domain)} · 结构 ${escapeHtml(p.type_id)}</p>
            </header>
            <p class="ph-about__text">${escapeHtml(p.description)}</p>
            <div class="ph-section__footer">
              <a href="/phenomenon/${encodeURIComponent(id)}" class="btn btn--ghost">
                查看这个现象的完整信息
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
      streamMapping({ kind: 'id', value: id }, pairId, slot, p);
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
  } catch (err) {
    console.error('Load phenomenon failed:', err);
    const container = $('#ph-content');
    const isNotFound = /\b404\b/.test(err.message || '');
    if (isNotFound) {
      // Match the full-page /404 empty state: "现象未被收录"
      document.title = '没找到 — Structural';
      const crumbName = $('#ph-crumb-name');
      if (crumbName) crumbName.textContent = '未找到';
      container.innerHTML = `
        <div class="search-empty" style="padding: var(--space-8) var(--space-5); text-align: center;">
          <div style="font-family: var(--font-serif); font-size: 96px; line-height: 1; color: var(--text-primary); letter-spacing: var(--ls-tighter); margin-bottom: var(--space-4);">404</div>
          <h2 class="search-empty__title">这个现象还没有被收录</h2>
          <p class="search-empty__text">你要找的现象不存在。<br>也许我们的知识库还没有覆盖到它。</p>
          <div class="search-empty__actions">
            <a href="/" class="btn btn--primary btn--lg">返回首页</a>
            <a href="/discoveries" class="btn btn--ghost">查看精选发现</a>
          </div>
        </div>
      `;
    } else {
      container.innerHTML = `
        <div class="search-empty">
          <svg class="search-empty__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
          </svg>
          <h2 class="search-empty__title">未能加载此现象</h2>
          <p class="search-empty__text">${escapeHtml(err.message)}</p>
          <div class="search-empty__actions">
            <a href="/" class="btn btn--primary">返回首页</a>
          </div>
        </div>
      `;
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  const id = getPathId();
  const pair = getQueryParam('pair');
  const fromQuery = getQueryParam('from_query');
  if (id) {
    loadPhenomenon(id, pair, fromQuery);
  } else {
    // No phenomenon id in URL — redirect to home.
    window.location.replace('/');
  }
});
