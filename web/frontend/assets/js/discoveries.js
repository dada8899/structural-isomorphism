/**
 * Structural — Discoveries page
 * Renders 39 A-level cross-domain isomorphism discoveries (V2 19 + V3 20)
 * merged from three pipelines.
 */

let allDiscoveries = [];
let allTier2 = [];
let currentFilter = 'all';
let currentTier = 'a'; // 'a' = A-grade, 't2' = tier2 candidate pool

// Normalize literature_status (English or Chinese) to (class, zhLabel).
// The backend merges V2 and V3 A-level into a single feed; V2 originally used
// Chinese strings, V3 uses English. We unify here.
const STATUS_MAP = {
  // English (V3)
  'unexplored':    { cls: 'unknown', zh: '前所未有' },
  'partial':       { cls: 'partial', zh: '部分探索' },
  'established':   { cls: 'known',   zh: '已有文献' },
  // Chinese (V2 legacy)
  '未有先例':      { cls: 'unknown', zh: '前所未有' },
  '未发表':        { cls: 'unknown', zh: '前所未有' },
  '未探索':        { cls: 'unknown', zh: '前所未有' },
  '微弱探索':      { cls: 'partial', zh: '部分探索' },
  '部分探索':      { cls: 'partial', zh: '部分探索' },
  '部分讨论':      { cls: 'partial', zh: '部分探索' },
  '广泛讨论':      { cls: 'known',   zh: '已有文献' },
  '已知':          { cls: 'known',   zh: '已有文献' },
};

function statusInfo(status) {
  if (!status) return { cls: 'known', zh: '未知' };
  const exact = STATUS_MAP[status];
  if (exact) return exact;
  for (const [key, val] of Object.entries(STATUS_MAP)) {
    if (status.includes(key)) return val;
  }
  return { cls: 'known', zh: status };
}

// Render a list field that might be string, array, or missing.
function renderListField(v) {
  if (!v) return '';
  if (Array.isArray(v)) {
    return '<ul class="disc-item__list">' + v.map(x => `<li>${escapeHtml(String(x))}</li>`).join('') + '</ul>';
  }
  return `<p>${escapeHtml(String(v))}</p>`;
}

// Render the 5-dim score bars. Accepts either a nested dim_scores dict OR
// flat top-level fields (novelty/rigor/feasibility/impact/writability).
function renderDimScores(d) {
  const source = d.dim_scores || d;
  const dims = [
    { key: 'novelty',     label: '创新性' },
    { key: 'rigor',       label: '严谨性' },
    { key: 'feasibility', label: '可行性' },
    { key: 'impact',      label: '影响力' },
    { key: 'writability', label: '可写性' },
  ];
  const rows = dims
    .map(dim => ({ ...dim, score: source[dim.key] }))
    .filter(dim => typeof dim.score === 'number' && dim.score > 0);
  if (rows.length === 0) return '';
  return `
    <div class="disc-item__detail-block disc-item__dims" style="grid-column: 1 / -1">
      <h4>五维评分</h4>
      <div class="disc-dims">
        ${rows.map(r => `
          <div class="disc-dim">
            <div class="disc-dim__label">${escapeHtml(r.label)}</div>
            <div class="disc-dim__bar-track">
              <div class="disc-dim__bar" style="width: ${r.score * 10}%"></div>
            </div>
            <div class="disc-dim__num">${r.score}</div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderStats(stats, count) {
  const statsEl = $('#disc-hero-stats');
  if (!statsEl) return;

  // by_status may use English (unexplored/partial/established) or Chinese keys.
  const unknownCount = allDiscoveries.filter(d => statusInfo(d.literature_status).cls === 'unknown').length;
  // "Top tier" = final_score >= 8.5 (there's no 10-scale bucket >= 9 after normalization).
  const topTier = allDiscoveries.filter(d => (d.final_score || 0) >= 8.5).length;

  statsEl.innerHTML = `
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${count}</div>
      <div class="disc-hero__stat-label">A 级发现</div>
    </div>
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${topTier}</div>
      <div class="disc-hero__stat-label">Top tier (score ≥ 8.5)</div>
    </div>
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${unknownCount}</div>
      <div class="disc-hero__stat-label">文献未探索</div>
    </div>
  `;
}

function renderFilters(stats, total) {
  const filterEl = $('#disc-filter');
  if (!filterEl) return;

  const unknownCount = allDiscoveries.filter(d => statusInfo(d.literature_status).cls === 'unknown').length;
  const partialCount = allDiscoveries.filter(d => statusInfo(d.literature_status).cls === 'partial').length;
  const knownCount = total - unknownCount - partialCount;
  const tier2Count = allTier2.length;

  const v2Count = allDiscoveries.filter(d => d.pipeline === 'V2').length;
  const v3Count = allDiscoveries.filter(d => d.pipeline === 'V3').length;

  filterEl.innerHTML = `
    <div class="disc-tier-tabs">
      <button class="disc-tier-tab ${currentTier === 'a' ? 'active' : ''}" data-tier="a">
        A 级精选 <span class="disc-tier-tab__count">${total}</span>
      </button>
      <button class="disc-tier-tab ${currentTier === 't2' ? 'active' : ''}" data-tier="t2">
        候选池 <span class="disc-tier-tab__count">${tier2Count}</span>
      </button>
    </div>
    ${currentTier === 'a' ? `
      <div class="disc-filter-row">
        <span class="disc-filter__label">文献状态</span>
        <button class="disc-filter__btn ${currentFilter === 'all' ? 'active' : ''}" data-filter="all">
          全部 <span class="disc-filter__count">${total}</span>
        </button>
        <button class="disc-filter__btn ${currentFilter === 'unknown' ? 'active' : ''}" data-filter="unknown">
          前所未有 <span class="disc-filter__count">${unknownCount}</span>
        </button>
        <button class="disc-filter__btn ${currentFilter === 'partial' ? 'active' : ''}" data-filter="partial">
          部分探索 <span class="disc-filter__count">${partialCount}</span>
        </button>
        <button class="disc-filter__btn ${currentFilter === 'known' ? 'active' : ''}" data-filter="known">
          已有文献 <span class="disc-filter__count">${knownCount}</span>
        </button>
      </div>
      <div class="disc-filter-row">
        <span class="disc-filter__label">检索管道</span>
        <button class="disc-filter__btn ${currentFilter === 'pipeline-v2' ? 'active' : ''}" data-filter="pipeline-v2">
          V2 严格 <span class="disc-filter__count">${v2Count}</span>
        </button>
        <button class="disc-filter__btn ${currentFilter === 'pipeline-v3' ? 'active' : ''}" data-filter="pipeline-v3">
          V3 StructTuple <span class="disc-filter__count">${v3Count}</span>
        </button>
      </div>
    ` : `
      <div class="disc-filter-row">
        <p class="disc-tier2-hint">V2 五分顶级池里未晋级 A 的 <strong>${tier2Count}</strong> 条跨域对。只有基础同构判断和相似度，没有完整的五维深度分析，但质量仍值得探索。</p>
      </div>
    `}
  `;

  // Event delegation for tabs + filter buttons
  filterEl.addEventListener('click', (e) => {
    const tab = e.target.closest('.disc-tier-tab');
    if (tab) {
      const newTier = tab.dataset.tier;
      if (newTier !== currentTier) {
        currentTier = newTier;
        currentFilter = 'all';
        renderFilters(stats, total);
        renderList();
      }
      return;
    }
    const btn = e.target.closest('.disc-filter__btn');
    if (!btn) return;
    $$('.disc-filter__btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    renderList();
  });
}

function applyFilter(list) {
  if (currentFilter === 'all') return list;
  if (currentFilter === 'pipeline-v2') return list.filter(d => d.pipeline === 'V2');
  if (currentFilter === 'pipeline-v3') return list.filter(d => d.pipeline === 'V3');
  return list.filter(d => statusInfo(d.literature_status).cls === currentFilter);
}

function renderList() {
  const listEl = $('#disc-list');
  if (!listEl) return;

  if (currentTier === 't2') {
    renderTier2List(listEl);
    return;
  }

  const filtered = applyFilter(allDiscoveries);

  if (filtered.length === 0) {
    listEl.innerHTML = `<p style="text-align:center; color: var(--text-tertiary); padding: var(--space-7) 0">没有匹配的发现</p>`;
    return;
  }

  listEl.innerHTML = filtered.map((d, i) => {
    const st = statusInfo(d.literature_status);
    const conf = typeof d.isomorphism_confidence === 'number'
      ? (d.isomorphism_confidence <= 1 ? Math.round(d.isomorphism_confidence * 100) : Math.round(d.isomorphism_confidence))
      : null;
    const pipelineBadge = d.pipeline
      ? `<span class="disc-item__pipeline disc-item__pipeline--${d.pipeline.toLowerCase()}">${escapeHtml(d.pipeline)}</span>`
      : '';
    const verdict = d.one_line_verdict || d.paper_title || '';

    return `
      <article class="disc-item" data-index="${i}" style="animation: fadeInUp 500ms var(--ease-out-expo) ${Math.min(i * 30, 400)}ms both">
        <header class="disc-item__header">
          <div class="disc-item__rank">#${d.rank}</div>
          <div class="disc-item__body">
            <div class="disc-item__pair">
              <div class="disc-item__side">
                <span class="disc-item__domain">${escapeHtml(d.a_domain)}</span>
                <div class="disc-item__name">${escapeHtml(d.a_name)}</div>
              </div>
              <div class="disc-item__connector">
                <div class="disc-item__symbol">≅</div>
              </div>
              <div class="disc-item__side disc-item__side--right">
                <span class="disc-item__domain">${escapeHtml(d.b_domain)}</span>
                <div class="disc-item__name">${escapeHtml(d.b_name)}</div>
              </div>
            </div>
            <p class="disc-item__verdict">${escapeHtml(verdict)}</p>
            <div class="disc-item__meta">
              ${pipelineBadge}
              ${d.rating ? `<span class="disc-item__meta-tag disc-item__meta-tag--rating">等级 ${escapeHtml(d.rating)}</span>` : ''}
              <span class="disc-item__meta-tag disc-item__meta-tag--${st.cls}">
                ${escapeHtml(st.zh)}
              </span>
              ${conf !== null ? `<span class="disc-item__meta-tag">同构置信度 ${conf}%</span>` : ''}
              ${d.isomorphism_depth ? `<span class="disc-item__meta-tag">同构深度 ${d.isomorphism_depth}/5</span>` : ''}
              ${d.time_estimate ? `<span class="disc-item__meta-tag">${escapeHtml(d.time_estimate)}</span>` : ''}
              ${d.solo_feasible ? '<span class="disc-item__meta-tag">单人可做</span>' : ''}
            </div>
          </div>
          <div class="disc-item__aside">
            <div class="disc-item__score">
              <span class="disc-item__score-num">${d.final_score}</span>
              <span class="disc-item__score-unit">/10</span>
            </div>
            <div class="disc-item__expand">
              展开
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </div>
          </div>
        </header>
        <div class="disc-item__detail">
          <div class="disc-item__detail-grid">
            ${d.shared_equation ? `
              <div class="disc-item__detail-block" style="grid-column: 1 / -1">
                <h4>共享方程骨架 (V3 StructTuple)</h4>
                <pre class="disc-item__equations">${escapeHtml(d.shared_equation)}</pre>
                ${d.variable_mapping ? `<p class="disc-item__var-map"><strong>变量映射</strong>：${escapeHtml(d.variable_mapping)}</p>` : ''}
              </div>
            ` : (Array.isArray(d.equations) && d.equations.length ? `
              <div class="disc-item__detail-block" style="grid-column: 1 / -1">
                <h4>关键方程</h4>
                <pre class="disc-item__equations">${d.equations.map(e => escapeHtml(String(e))).join('\n')}</pre>
              </div>
            ` : '')}

            ${renderDimScores(d)}

            ${d.paper_title || d.target_venue ? `
              <div class="disc-item__detail-block disc-item__paper" style="grid-column: 1 / -1">
                <h4>论文化路径</h4>
                ${d.paper_title ? `<div class="disc-item__paper-title">${escapeHtml(d.paper_title)}</div>` : ''}
                ${d.target_venue ? `<div class="disc-item__paper-venue">建议投稿：<strong>${escapeHtml(d.target_venue)}</strong></div>` : ''}
              </div>
            ` : ''}

            ${d.blocking_mechanisms ? `
              <div class="disc-item__detail-block">
                <h4>阻塞机制</h4>
                ${renderListField(d.blocking_mechanisms)}
              </div>
            ` : ''}
            ${d.risk ? `
              <div class="disc-item__detail-block">
                <h4>潜在风险</h4>
                ${renderListField(d.risk)}
              </div>
            ` : ''}
            ${d.execution_plan ? `
              <div class="disc-item__detail-block" style="grid-column: 1 / -1">
                <h4>执行方案</h4>
                ${renderListField(d.execution_plan)}
              </div>
            ` : ''}
            ${d.impact_scope || d.practical_value ? `
              <div class="disc-item__detail-block" style="grid-column: 1 / -1">
                <h4>实用价值</h4>
                <p>${d.impact_scope ? `<strong>${escapeHtml(d.impact_scope)}</strong> · ` : ''}${escapeHtml(d.practical_value || '')}</p>
              </div>
            ` : ''}
            ${d.full_analysis ? `
              <details class="disc-item__full-analysis" style="grid-column: 1 / -1">
                <summary>完整深度分析</summary>
                <div class="disc-item__full-text">${escapeHtml(d.full_analysis)}</div>
              </details>
            ` : ''}
            ${d.a_id && d.b_id ? `
              <div class="disc-item__cta">
                <a class="disc-item__cta-btn" href="/analyze?a_id=${encodeURIComponent(d.a_id)}&id=${encodeURIComponent(d.b_id)}">
                  <span class="disc-item__cta-btn-main">生成深度分析报告</span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
                </a>
                <span class="disc-item__cta-hint">8 段跨学科迁移研究 · 流式生成 60-90 秒</span>
              </div>
            ` : ''}
          </div>
        </div>
      </article>
    `;
  }).join('');

  // Expand click handler (replaces any prior handler on re-render)
  listEl.onclick = (e) => {
    if (e.target.closest('a')) return;
    const item = e.target.closest('.disc-item');
    if (item) {
      item.classList.toggle('disc-item--expanded');
      if (item.classList.contains('disc-item--expanded') && window.renderMath) {
        const detail = item.querySelector('.disc-item__detail');
        if (detail) window.renderMath(detail);
      }
    }
  };
}

// === Tier 2 renderer — simpler cards, no deep analysis ===
function renderTier2List(listEl) {
  if (!allTier2 || allTier2.length === 0) {
    listEl.innerHTML = `<p style="text-align:center; color: var(--text-tertiary); padding: var(--space-7) 0">候选池数据未加载</p>`;
    return;
  }

  listEl.innerHTML = allTier2.map((d, i) => `
    <article class="disc-t2-item" data-index="${i}" style="animation: fadeInUp 400ms var(--ease-out-expo) ${Math.min(i * 20, 300)}ms both">
      <div class="disc-t2-item__rank">#${d.rank}</div>
      <div class="disc-t2-item__body">
        <div class="disc-t2-item__pair">
          <div class="disc-t2-item__side">
            <span class="disc-t2-item__domain">${escapeHtml(d.a_domain)}</span>
            <span class="disc-t2-item__name">${escapeHtml(d.a_name)}</span>
          </div>
          <span class="disc-t2-item__symbol">≅</span>
          <div class="disc-t2-item__side disc-t2-item__side--right">
            <span class="disc-t2-item__domain">${escapeHtml(d.b_domain)}</span>
            <span class="disc-t2-item__name">${escapeHtml(d.b_name)}</span>
          </div>
        </div>
        ${d.reason ? `<p class="disc-t2-item__reason">${escapeHtml(d.reason)}</p>` : ''}
      </div>
      <div class="disc-t2-item__aside">
        <div class="disc-t2-item__sim">
          <span class="disc-t2-item__sim-num">${Math.round((d.similarity || 0) * 100)}</span>
          <span class="disc-t2-item__sim-unit">%</span>
        </div>
        ${d.a_id && d.b_id ? `
          <a class="disc-t2-item__analyze" href="/analyze?a_id=${encodeURIComponent(d.a_id)}&id=${encodeURIComponent(d.b_id)}" onclick="event.stopPropagation()">
            深度分析
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
          </a>
        ` : ''}
      </div>
    </article>
  `).join('');
}

async function loadDiscoveries() {
  try {
    const data = await (await fetch('/api/discoveries')).json();
    allDiscoveries = data.discoveries || [];
    allTier2 = data.tier2 || [];
    renderStats(data.stats || {}, data.count);
    renderFilters(data.stats || {}, data.count);
    renderList();
  } catch (err) {
    console.error('Failed to load discoveries:', err);
    $('#disc-list').innerHTML = `<p style="text-align:center; color: var(--danger); padding: var(--space-7) 0">加载失败：${escapeHtml(err.message)}</p>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  loadDiscoveries();
});
