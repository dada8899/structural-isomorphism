/**
 * Structural — Discoveries page
 */

let allDiscoveries = [];
let allTier2 = [];
let currentFilter = 'all';
let currentTier = 'a'; // 'a' = A-grade, 't2' = tier2 candidate pool

const STATUS_CLASS = {
  '未有先例': 'unknown',
  '未发表': 'unknown',
  '未探索': 'unknown',
  '微弱探索': 'partial',
  '部分探索': 'partial',
  '部分讨论': 'partial',
  '广泛讨论': 'known',
  '已知': 'known',
};

function statusClass(status) {
  for (const [key, cls] of Object.entries(STATUS_CLASS)) {
    if (status && status.includes(key)) return cls;
  }
  return 'known';
}

// Render the 5-dim score radar-ish grid (novelty/rigor/feasibility/impact/writability)
// Shown only when the discovery comes from v2 (has `dim_scores`).
function renderDimScores(scores) {
  if (!scores) return '';
  const dims = [
    { key: 'novelty',     label: '创新性' },
    { key: 'rigor',       label: '严谨性' },
    { key: 'feasibility', label: '可行性' },
    { key: 'impact',      label: '影响力' },
    { key: 'writability', label: '可写性' },
  ];
  const rows = dims
    .map(d => ({ ...d, score: scores[d.key] }))
    .filter(d => typeof d.score === 'number' && d.score > 0);
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

  const unknownCount = (stats.by_status['未有先例'] || 0) + (stats.by_status['未探索'] || 0);
  // v2 scores are 0-10 with decimals (e.g. 9.65). Count >=9.5 as "top tier"
  const topTier = Object.entries(stats.by_score || {})
    .filter(([k]) => parseFloat(k) >= 9)
    .reduce((sum, [, v]) => sum + v, 0);

  statsEl.innerHTML = `
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${count}</div>
      <div class="disc-hero__stat-label">A 级发现</div>
    </div>
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${topTier || count}</div>
      <div class="disc-hero__stat-label">五维加权 ≥ 9</div>
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

  const unknownCount = (stats.by_status['未有先例'] || 0) + (stats.by_status['未探索'] || 0);
  const partialCount = (stats.by_status['微弱探索'] || 0) + (stats.by_status['部分探索'] || 0) + (stats.by_status['部分讨论'] || 0);
  const knownCount = total - unknownCount - partialCount;
  const tier2Count = allTier2.length;

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
          已知 <span class="disc-filter__count">${knownCount}</span>
        </button>
      </div>
    ` : `
      <div class="disc-filter-row">
        <p class="disc-tier2-hint">5 分顶级池筛出、但未进入 A 级的 <strong>${tier2Count}</strong> 条跨域对。这些条目只有基础的同构判断和相似度，没有完整的 5 维深度分析，但质量仍值得探索。</p>
      </div>
    `}
  `;

  // Tier tab click handler
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

function renderList() {
  const listEl = $('#disc-list');
  if (!listEl) return;

  // Tier 2 has a completely different renderer (simpler card, no deep analysis)
  if (currentTier === 't2') {
    renderTier2List(listEl);
    return;
  }

  const filtered = currentFilter === 'all'
    ? allDiscoveries
    : allDiscoveries.filter(d => statusClass(d.literature_status) === currentFilter);

  if (filtered.length === 0) {
    listEl.innerHTML = `<p style="text-align:center; color: var(--text-tertiary); padding: var(--space-7) 0">没有匹配的发现</p>`;
    return;
  }

  listEl.innerHTML = filtered.map((d, i) => {
    const stClass = statusClass(d.literature_status);
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
            <p class="disc-item__verdict">${escapeHtml(d.one_line_verdict || d.paper_title || '')}</p>
            <div class="disc-item__meta">
              ${d.rating ? `<span class="disc-item__meta-tag disc-item__meta-tag--rating">等级 ${escapeHtml(d.rating)}</span>` : ''}
              <span class="disc-item__meta-tag disc-item__meta-tag--${stClass}">
                ${escapeHtml(d.literature_status)}
              </span>
              <span class="disc-item__meta-tag">同构置信度 ${d.isomorphism_confidence}%</span>
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
            ${d.equations ? `
              <div class="disc-item__equations">${escapeHtml(d.equations)}</div>
            ` : ''}

            ${renderDimScores(d.dim_scores)}

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
                <p>${escapeHtml(d.blocking_mechanisms)}</p>
              </div>
            ` : ''}
            ${d.literature_detail ? `
              <div class="disc-item__detail-block">
                <h4>潜在风险</h4>
                <p>${escapeHtml(d.literature_detail)}</p>
              </div>
            ` : ''}
            ${d.execution_plan ? `
              <div class="disc-item__detail-block" style="grid-column: 1 / -1">
                <h4>执行方案</h4>
                <p>${escapeHtml(d.execution_plan)}</p>
              </div>
            ` : ''}
            ${d.impact_scope || d.impact_detail ? `
              <div class="disc-item__detail-block" style="grid-column: 1 / -1">
                <h4>实用价值</h4>
                <p>${d.impact_scope ? `<strong>${escapeHtml(d.impact_scope)}</strong> · ` : ''}${escapeHtml(d.impact_detail || '')}</p>
              </div>
            ` : ''}
            ${d.full_analysis ? `
              <details class="disc-item__full-analysis" style="grid-column: 1 / -1">
                <summary>完整深度分析（5 维全文）</summary>
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

  // Attach expand click (onclick assign replaces any previous handler on re-render)
  listEl.onclick = (e) => {
    if (e.target.closest('a')) return;
    const item = e.target.closest('.disc-item');
    if (item) {
      item.classList.toggle('disc-item--expanded');
      // Render any math in the expanded detail
      if (item.classList.contains('disc-item--expanded') && window.renderMath) {
        const detail = item.querySelector('.disc-item__detail');
        if (detail) window.renderMath(detail);
      }
    }
  };
}

// === Tier 2 renderer — simpler cards (no deep analysis fields) ===
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
          <span class="disc-t2-item__sim-num">${Math.round(d.similarity * 100)}</span>
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
