// --- i18n helpers ---
function T(key, fallback) {
  try { if (window.i18n && typeof window.i18n.t === 'function') { var v = window.i18n.t(key); if (v && v !== key) return v; } } catch(e) {}
  return fallback;
}

function currentLang() {
  try { return (window.i18n && window.i18n.getLang && window.i18n.getLang()) || 'zh'; } catch (e) { return 'zh'; }
}
function L(obj, baseKey) {
  if (!obj) return '';
  var lang = currentLang();
  if (lang === 'en') {
    var en = obj[baseKey + '_en'];
    if (typeof en === 'string' && en.length) return en;
    if (Array.isArray(en) && en.length) return en;
  }
  // Discovery items use raw field names like a_name, not a_name_zh
  return obj[baseKey];
}

function LT(value) {
  if (!value || typeof value !== 'object') return '';
  if (currentLang() === 'en') return value.en || value.zh || '';
  return value.zh || value.en || '';
}

function LL(value) {
  if (!value || typeof value !== 'object') return [];
  const selected = currentLang() === 'en' ? (value.en || value.zh) : (value.zh || value.en);
  return Array.isArray(selected) ? selected : [];
}

function normalizeDiscovery(raw) {
  if (!raw || raw.schema_version !== 'discovery-candidate-v2') throw new Error('Unsupported discovery schema');
  if (!raw.pair || !raw.pair.a || !raw.pair.b || !raw.pair.a.id || !raw.pair.b.id) throw new Error('Invalid discovery pair');
  if (!raw.candidate_summary || !raw.validation_plan || !raw.readiness || !raw.provenance) throw new Error('Incomplete discovery candidate');
  return {
    ...raw,
    a_id: raw.pair.a.id,
    b_id: raw.pair.b.id,
    a_name: raw.pair.a.name.zh,
    a_name_en: raw.pair.a.name.en,
    b_name: raw.pair.b.name.zh,
    b_name_en: raw.pair.b.name.en,
    a_domain: raw.pair.a.domain.zh,
    a_domain_en: raw.pair.a.domain.en,
    b_domain: raw.pair.b.domain.zh,
    b_domain_en: raw.pair.b.domain.en,
    shared_equations: Array.isArray(raw.candidate_equations) ? raw.candidate_equations : [],
    variable_mapping_normalized: raw.candidate_variable_mapping || {},
  };
}

function renderVariableMapping(mapping) {
  if (!mapping || typeof mapping !== 'object') return '';
  return Object.entries(mapping)
    .map(([left, right]) => left === '__unmapped_notes__'
      ? `${T('page.discoveries.mapping_note', '未结构化备注')}：${escapeHtml(String(right))}`
      : `${escapeHtml(left)} → ${escapeHtml(String(right))}`)
    .join(' · ');
}

/** Structural candidate-review queue. */

let allDiscoveries = [];
let allTier2 = [];
let currentFilter = 'all';
const PAGE_SIZE = 12;
let visibleLimit = PAGE_SIZE;
const expandedDiscoveryIds = new Set();
// Stable deep links use the content-derived candidate id. Rank is only the
// current queue position and must never identify a scientific candidate.
let pendingFocusId = null;
let deepLinkNotice = '';
let dataLoaded = false;

function discoveryHeadline(d) {
  return LT(d.candidate_summary);
}

// Absolute share URL pointing at this specific discovery.
function discoveryShareUrl(d) {
  return location.origin + '/discoveries?candidate=' + encodeURIComponent(d.discovery_id);
}

// Attach the share-action row + hook headline interactions to a card.
function wireDiscoveryShare(article, d) {
  const host = article.querySelector('.disc-item__share');
  if (!host || !window.ShareCard || !window.ShareCard.buildActions) return;
  const headline = discoveryHeadline(d);
  const actions = window.ShareCard.buildActions({
    url: discoveryShareUrl(d),
    shareTitle: headline,
    shareText: headline + (currentLang() === 'en' ? ' — Structural candidate review' : ' — Structural 候选核查'),
    filename: 'structural-discovery-' + d.rank + '.png',
    compact: true,
    cardData: {
      eyebrow: (currentLang() === 'en' ? 'Cross-domain candidate #' : '跨领域候选 #') + d.rank,
      headline: headline,
      lineA: (L(d, 'a_domain') || '') + ' · ' + (L(d, 'a_name') || ''),
      lineB: (L(d, 'b_domain') || '') + ' · ' + (L(d, 'b_name') || ''),
      footnote: currentLang() === 'en' ? 'AI-ranked candidate · evidence review incomplete' : 'AI 排序候选 · 证据核查未完成',
      url: 'structural.bytedance.city',
    },
  });
  host.appendChild(actions);
}
let currentTier = 'a'; // 'a' = priority-review candidates, 't2' = candidate pool
// P0-4 (SESSION-17): when the data fetch fails we show a friendly error
// state. The i18n re-render fires renderList() again later; keep the error.
let loadFailed = false;

function preparePendingCandidate() {
  if (!dataLoaded || !pendingFocusId) return;
  const priorityIndex = allDiscoveries.findIndex((row) => row.discovery_id === pendingFocusId);
  const poolIndex = allTier2.findIndex((row) => row.discovery_id === pendingFocusId);
  if (priorityIndex >= 0) {
    currentTier = 'a';
    currentFilter = 'all';
    visibleLimit = Math.max(PAGE_SIZE, priorityIndex + 1);
    deepLinkNotice = '';
    return;
  }
  if (poolIndex >= 0) {
    currentTier = 't2';
    currentFilter = 'all';
    visibleLimit = Math.max(PAGE_SIZE, poolIndex + 1);
    deepLinkNotice = '';
    return;
  }
  deepLinkNotice = currentLang() === 'en'
    ? 'This candidate link is unavailable. Choose a candidate from the review queue.'
    : '这条候选链接不可用，请从核查队列中重新选择。';
  pendingFocusId = null;
}

function paginationMarkup(tier, shown, total) {
  const status = currentLang() === 'en'
    ? `Showing ${shown} of ${total} candidates`
    : `已显示 ${shown} / ${total} 条候选`;
  const remaining = Math.max(0, total - shown);
  return `<div class="disc-pagination">
    <p class="disc-pagination-status" role="status" aria-live="polite">${status}</p>
    ${remaining ? `<button type="button" class="disc-load-more" data-load-more="${tier}">
      ${currentLang() === 'en' ? `Show ${Math.min(PAGE_SIZE, remaining)} more candidates` : `再显示 ${Math.min(PAGE_SIZE, remaining)} 条候选`}
    </button>` : ''}
  </div>`;
}

function focusCandidateAt(listEl, tier, index) {
  requestAnimationFrame(() => {
    const card = listEl.querySelector(`[data-list-index="${index}"]`);
    if (!card) return;
    const control = tier === 'a'
      ? card.querySelector('.disc-item__expand')
      : card.querySelector('.disc-t2-evidence > summary');
    (control || card).focus({ preventScroll: true });
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
}

function honorPendingFocus(listEl, tier) {
  if (!pendingFocusId) return;
  const target = document.getElementById('candidate-' + pendingFocusId);
  if (!target) return;
  target.classList.add('disc-item--focused');
  if (tier === 'a') setDiscoveryExpanded(target, true);
  const control = tier === 'a'
    ? target.querySelector('.disc-item__expand')
    : target.querySelector('.disc-t2-evidence > summary');
  pendingFocusId = null;
  deepLinkNotice = '';
  requestAnimationFrame(() => {
    (control || target).focus({ preventScroll: true });
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
}

function renderPlanField(labelZh, labelEn, value) {
  return `
    <div class="disc-plan__field">
      <dt>${escapeHtml(currentLang() === 'en' ? labelEn : labelZh)}</dt>
      <dd>${escapeHtml(LT(value) || (currentLang() === 'en' ? 'Not recorded' : '尚未记录'))}</dd>
    </div>`;
}

function renderEvidenceBoundarySummary(d) {
  const sourceCount = Number(d && d.provenance && d.provenance.recorded_source_count) || 0;
  const source = sourceCount > 0
    ? (currentLang() === 'en' ? 'source review incomplete' : '来源复核未完成')
    : (currentLang() === 'en' ? 'sources not recorded' : '来源未记录');
  return `<div class="disc-evidence-summary" role="note" aria-label="${currentLang() === 'en' ? 'Evidence boundary' : '证据边界'}">
    <span>${currentLang() === 'en' ? 'Candidate' : '候选'}</span>
    <span>${source}</span>
    <span>${currentLang() === 'en' ? 'not tested' : '尚未检验'}</span>
  </div>`;
}

function renderCandidateStructure(d, evidenceLanguage) {
  const equations = Array.isArray(d.shared_equations) ? d.shared_equations : [];
  const mapping = d.variable_mapping_normalized && typeof d.variable_mapping_normalized === 'object'
    ? d.variable_mapping_normalized
    : {};
  const hasMapping = Object.keys(mapping).length > 0;
  if (!equations.length && !hasMapping) {
    return `<div class="disc-item__detail-block" style="grid-column:1 / -1">
      <h4>${currentLang() === 'en' ? 'Candidate structure to record' : '待记录的候选结构'}</h4>
      <p>${currentLang() === 'en'
        ? 'No candidate equation or variable-to-variable mapping is recorded yet.'
        : '尚未记录待检验的候选方程，也未记录两边变量的对应关系。'}</p>
    </div>`;
  }
  return `<div class="disc-item__detail-block" style="grid-column:1 / -1">
    <h4>${currentLang() === 'en' ? 'Candidate structure to test' : '待检验的候选结构'}</h4>
    ${equations.length
      ? `<pre class="disc-item__equations">${equations.map((equation) => escapeHtml(equation)).join('\n')}</pre>`
      : `<p>${currentLang() === 'en' ? 'Candidate equation: not recorded.' : '待检验的候选方程：尚未记录。'}</p>`}
    ${hasMapping
      ? `<p class="disc-item__var-map"><strong>${currentLang() === 'en' ? 'How variables on the two sides correspond (variable mapping)' : '两边变量的对应关系（变量映射）'}</strong>：${renderVariableMapping(mapping)}</p>`
      : `<p class="disc-item__var-map"><strong>${currentLang() === 'en' ? 'Variable-to-variable mapping' : '两边变量的对应关系'}</strong>：${currentLang() === 'en' ? 'not recorded' : '尚未记录'}</p>`}
    <p class="disc-item__evidence-language">${escapeHtml(evidenceLanguage)} · ${currentLang() === 'en' ? 'A similar equation does not establish a shared mechanism.' : '方程相似不能证明两边存在同一机制。'}</p>
  </div>`;
}

function renderValidationPlan(d) {
  const plan = d.validation_plan || {};
  const gaps = Array.isArray(plan.validation_gaps) ? plan.validation_gaps : [];
  return `
    <section class="disc-plan" aria-labelledby="plan-${escapeHtml(d.discovery_id)}">
      <div class="disc-plan__header">
        <div>
          <p class="disc-plan__eyebrow">${currentLang() === 'en' ? 'Validation-plan draft' : '验证计划草案'}</p>
          <h4 id="plan-${escapeHtml(d.discovery_id)}">${currentLang() === 'en' ? 'Turn the candidate into a falsifiable test' : '把候选变成可反驳的检验'}</h4>
        </div>
        <span class="disc-plan__status">${currentLang() === 'en' ? 'Not publicly locked (not preregistered)' : '尚未公开锁定（未预注册）'}</span>
      </div>
      <dl class="disc-plan__grid">
        ${renderPlanField('假设', 'Hypothesis', plan.hypothesis)}
        ${renderPlanField('数据与来源', 'Data and sources', plan.data_needed)}
        ${renderPlanField('比较基线', 'Baseline', plan.baseline)}
        ${renderPlanField('主指标', 'Primary metric', plan.primary_metric)}
        ${renderPlanField('停止 / 失败条件', 'Stop / failure condition', plan.failure_condition)}
      </dl>
      ${gaps.length ? `
        <div class="disc-plan__gaps">
          <strong>${currentLang() === 'en' ? 'Validation gaps to complete' : '待补齐的验证缺口'}</strong>
          <ul>${gaps.map((gap) => `<li>${escapeHtml(LT(gap.label))}</li>`).join('')}</ul>
        </div>` : ''}
      <p class="disc-plan__boundary">${currentLang() === 'en'
        ? 'This draft is a starting checklist. Complete sources, metric, sample, and stop rule before treating it as a study plan.'
        : '这只是起点清单。补齐来源、指标、样本和停止规则之前，不能把它当作正式研究计划。'}</p>
    </section>`;
}

function markdownText(value) {
  return String(value == null ? '' : value)
    .replace(/[\u0000-\u001f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\\/g, '\\\\')
    .replace(/([`*_{}\[\]()#+.!|])/g, '\\$1');
}

function validationPlanMarkdown(d) {
  const p = d.validation_plan || {};
  const equations = Array.isArray(d.shared_equations) ? d.shared_equations : [];
  const mapping = d.variable_mapping_normalized && typeof d.variable_mapping_normalized === 'object'
    ? Object.entries(d.variable_mapping_normalized)
    : [];
  const sourceCount = Number(d && d.provenance && d.provenance.recorded_source_count) || 0;
  const lines = [
    '# ' + (currentLang() === 'en' ? 'Structural validation-plan draft' : 'Structural 验证计划草案'),
    '',
    `- Candidate ID: ${markdownText(d.discovery_id)}`,
    `- Evidence level: candidate`,
    `- Preregistered: no`,
    '',
    `## ${currentLang() === 'en' ? 'Candidate pair' : '候选配对'}`,
    `${markdownText(L(d, 'a_name'))} (${markdownText(L(d, 'a_domain'))}) ↔ ${markdownText(L(d, 'b_name'))} (${markdownText(L(d, 'b_domain'))})`,
    '',
    `## ${currentLang() === 'en' ? 'Candidate structure to test' : '待检验的候选结构'}`,
    `### ${currentLang() === 'en' ? 'Candidate equations' : '候选方程'}`,
  ];
  if (equations.length) equations.forEach((equation) => lines.push(`- ${markdownText(equation)}`));
  else lines.push('- ' + (currentLang() === 'en' ? 'Not recorded' : '尚未记录'));
  lines.push('', `### ${currentLang() === 'en' ? 'How variables correspond' : '两边变量的对应关系'}`);
  if (mapping.length) mapping.forEach(([left, right]) => lines.push(`- ${markdownText(left)} → ${markdownText(right)}`));
  else lines.push('- ' + (currentLang() === 'en' ? 'Not recorded' : '尚未记录'));
  lines.push(
    '',
    `## ${currentLang() === 'en' ? 'Evidence boundary' : '证据边界'}`,
    `- ${currentLang() === 'en' ? 'Recorded source entries' : '已记录来源条目'}: ${sourceCount}`,
    `- ${currentLang() === 'en' ? 'Result' : '检验结果'}: NOT_TESTED`,
    `- ${currentLang() === 'en' ? 'Publicly locked before the study' : '实验前公开锁定'}: no`,
    '',
  );
  [
    ['假设', 'Hypothesis', p.hypothesis],
    ['数据与来源', 'Data and sources', p.data_needed],
    ['比较基线', 'Baseline', p.baseline],
    ['主指标', 'Primary metric', p.primary_metric],
    ['停止 / 失败条件', 'Stop / failure condition', p.failure_condition],
  ].forEach(([zh, en, value]) => lines.push(`## ${currentLang() === 'en' ? en : zh}`, markdownText(LT(value)) || '—', ''));
  const gaps = Array.isArray(p.validation_gaps) ? p.validation_gaps : [];
  lines.push(`## ${currentLang() === 'en' ? 'Gaps to verify' : '待核对缺口'}`);
  if (gaps.length) gaps.forEach((gap) => lines.push(`- ${markdownText(LT(gap.label))}`));
  else lines.push('- ' + (currentLang() === 'en' ? 'No gap record yet' : '尚无缺口记录'));
  lines.push('', currentLang() === 'en'
    ? '> Draft only. Not a preregistration, mechanism proof, or publication plan.'
    : '> 仅为草案，不是预注册、机制证明或投稿计划。');
  return lines.join('\n');
}

function downloadValidationPlan(d) {
  const blob = new Blob([validationPlanMarkdown(d)], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `structural-validation-${d.discovery_id}.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function renderStats(stats, count) {
  const statsEl = $('#disc-hero-stats');
  if (!statsEl) return;

  statsEl.innerHTML = `
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${stats.priority_review || count || 0}</div>
      <div class="disc-hero__stat-label">${currentLang() === 'en' ? 'Priority review queue' : '优先核查队列'}</div>
    </div>
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${stats.candidate_pool || 0}</div>
      <div class="disc-hero__stat-label">${currentLang() === 'en' ? 'Candidate pool' : '候选池'}</div>
    </div>
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${stats.source_backed || 0}</div>
      <div class="disc-hero__stat-label">${currentLang() === 'en' ? 'Source-backed' : '完成来源核查'}</div>
    </div>
    <div class="disc-hero__stat">
      <div class="disc-hero__stat-num">${stats.ready_for_preregistration || 0}</div>
      <div class="disc-hero__stat-label">${currentLang() === 'en' ? 'Ready to publicly lock a study plan' : '可公开锁定研究方案'}</div>
    </div>
  `;
}

function renderFilters(stats, total) {
  const filterEl = $('#disc-filter');
  if (!filterEl) return;

  const tier2Count = allTier2.length;

  const v2Count = allDiscoveries.filter(d => d.pipeline === 'V2').length;
  const v3Count = allDiscoveries.filter(d => d.pipeline === 'V3').length;

  filterEl.innerHTML = `
    <div class="disc-tier-tabs">
      <button class="disc-tier-tab ${currentTier === 'a' ? 'active' : ''}" data-tier="a" aria-pressed="${currentTier === 'a' ? 'true' : 'false'}">
        ${T("page.discoveries.tier_curated", "优先核查")} <span class="disc-tier-tab__count">${total}</span>
      </button>
      <button class="disc-tier-tab ${currentTier === 't2' ? 'active' : ''}" data-tier="t2" aria-pressed="${currentTier === 't2' ? 'true' : 'false'}">
        ${T("page.discoveries.tier_tier2", "候选池")} <span class="disc-tier-tab__count">${tier2Count}</span>
      </button>
    </div>
    ${currentTier === 'a' ? `
      <div class="disc-filter-row">
        <span class="disc-filter__label">${currentLang() === 'en' ? 'Review lane' : '核查路径'}</span>
        <button class="disc-filter__btn ${currentFilter === 'all' ? 'active' : ''}" data-filter="all" aria-pressed="${currentFilter === 'all' ? 'true' : 'false'}">
          ${T("page.discoveries.filter_all_chip", "全部")} <span class="disc-filter__count">${total}</span>
        </button>
        <button class="disc-filter__btn ${currentFilter === 'pipeline-v2' ? 'active' : ''}" data-filter="pipeline-v2" aria-pressed="${currentFilter === 'pipeline-v2' ? 'true' : 'false'}">
          ${T("page.discoveries.pipeline_v2", "文本结构检索")} <span class="disc-filter__count">${v2Count}</span>
        </button>
        <button class="disc-filter__btn ${currentFilter === 'pipeline-v3' ? 'active' : ''}" data-filter="pipeline-v3" aria-pressed="${currentFilter === 'pipeline-v3' ? 'true' : 'false'}">
          ${T("page.discoveries.pipeline_v3", "变量关系检索")} <span class="disc-filter__count">${v3Count}</span>
        </button>
      </div>
    ` : `
      <div class="disc-filter-row">
        <p class="disc-tier2-hint">${T("page.discoveries.tier2_hint", "尚未完成深度核查的候选")} (<strong>${tier2Count}</strong>).</p>
      </div>
    `}
  `;

  // Replace the delegated handler on every locale render; do not accumulate it.
  filterEl.onclick = (e) => {
    const tab = e.target.closest('.disc-tier-tab');
    if (tab) {
      const newTier = tab.dataset.tier;
      if (newTier !== currentTier) {
        currentTier = newTier;
        currentFilter = 'all';
        visibleLimit = PAGE_SIZE;
        renderFilters(stats, total);
        renderList();
      }
      return;
    }
    const btn = e.target.closest('.disc-filter__btn');
    if (!btn) return;
    currentFilter = btn.dataset.filter;
    visibleLimit = PAGE_SIZE;
    renderFilters(stats, total);
    renderList();
  };
}

function applyFilter(list) {
  if (currentFilter === 'all') return list;
  if (currentFilter === 'pipeline-v2') return list.filter(d => d.pipeline === 'V2');
  if (currentFilter === 'pipeline-v3') return list.filter(d => d.pipeline === 'V3');
  return [];
}

function renderList() {
  const listEl = $('#disc-list');
  if (!listEl) return;
  // Keep the friendly error state if the data never loaded.
  if (loadFailed || !dataLoaded) return;

  preparePendingCandidate();

  if (currentTier === 't2') {
    renderTier2List(listEl);
    return;
  }

  const allFiltered = applyFilter(allDiscoveries);

  const filtered = allFiltered.slice(0, visibleLimit);

  if (allFiltered.length === 0) {
    listEl.innerHTML = `<p style="text-align:center; color: var(--text-tertiary); padding: var(--space-7) 0">${T("page.discoveries.empty_filter", "没有匹配的发现")}</p>`;
    return;
  }

  const notice = deepLinkNotice
    ? `<div class="disc-link-notice" role="status">${escapeHtml(deepLinkNotice)}</div>`
    : '';
  listEl.innerHTML = notice + filtered.map((d, i) => {
    const pipelineBadge = d.pipeline
      ? `<span class="disc-item__pipeline disc-item__pipeline--${d.pipeline.toLowerCase()}">${d.pipeline === 'V3' ? T('page.discoveries.pipeline_v3', '变量关系检索') : T('page.discoveries.pipeline_v2', '文本结构检索')}</span>`
      : '';
    const sourceCount = Number(d.provenance.recorded_source_count) || 0;
    const evidenceLanguage = d.evidence_language === 'zh_only'
        ? (currentLang() === 'en' ? 'Evidence fields are Chinese-only' : '证据字段仅有中文')
        : (currentLang() === 'en' ? 'Evidence fields not recorded' : '证据字段未记录');
    const blockerLabels = currentLang() === 'en'
      ? {
          candidate_equation: 'a candidate equation',
          variable_mapping: 'a variable-to-variable mapping',
          source_review: 'independent source review',
          dataset_record: 'a dataset and sampling record',
          primary_metric: 'a primary metric',
          preregistered_stop_rule: 'a stopping rule publicly locked before the study',
        }
      : {
          candidate_equation: '待检验的候选方程',
          variable_mapping: '两边变量的对应关系',
          source_review: '独立来源复核',
          dataset_record: '数据与抽样记录',
          primary_metric: '主要判断指标',
          preregistered_stop_rule: '实验前公开锁定的停止规则',
        };
    const blockers = Array.isArray(d.readiness.blockers) ? d.readiness.blockers : [];
    const missing = blockers.map((key) => blockerLabels[key]).filter(Boolean);
    const readinessText = currentLang() === 'en'
      ? `Still missing: ${missing.join(', ')}.`
      : `仍缺：${missing.join('、')}。`;
    const detailId = `disc-detail-${d.discovery_id}`;

    return `
      <article class="disc-item" id="candidate-${escapeHtml(d.discovery_id)}" data-list-index="${i}" data-rank="${d.rank}" data-discovery-id="${escapeHtml(d.discovery_id)}" tabindex="-1" style="animation: fadeInUp 500ms var(--ease-out-expo) ${Math.min(i * 30, 400)}ms both">
        <header class="disc-item__header">
          <div class="disc-item__rank">#${d.rank}</div>
          <div class="disc-item__body">
            <div class="disc-item__pair">
              <div class="disc-item__side">
                <span class="disc-item__domain">${escapeHtml(L(d, "a_domain"))}</span>
                <div class="disc-item__name">${escapeHtml(L(d, "a_name"))}</div>
              </div>
              <div class="disc-item__connector">
                <div class="disc-item__symbol" aria-label="${currentLang() === 'en' ? 'candidate similarity to test' : '待检验的候选相似'}">≈?</div>
              </div>
              <div class="disc-item__side disc-item__side--right">
                <span class="disc-item__domain">${escapeHtml(L(d, "b_domain"))}</span>
                <div class="disc-item__name">${escapeHtml(L(d, "b_name"))}</div>
              </div>
            </div>
            <p class="disc-item__verdict">${escapeHtml(LT(d.candidate_summary))}</p>
            <div class="disc-item__meta">
              ${pipelineBadge}
              <span class="disc-item__meta-tag disc-item__meta-tag--unknown">${currentLang() === 'en' ? 'Candidate · unverified' : '候选 · 未验证'}</span>
              <span class="disc-item__meta-tag">${sourceCount > 0
                ? (currentLang() === 'en' ? `${sourceCount} source record(s), review incomplete` : `${sourceCount} 条来源记录，复核未完成`)
                : (currentLang() === 'en' ? 'Sources not recorded' : '来源未记录')}</span>
              ${d.family_variant_count > 1 ? `<span class="disc-item__meta-tag">${currentLang() === 'en' ? `${d.family_variant_count} candidates share one knowledge-base phenomenon` : `同一知识库现象关联 ${d.family_variant_count} 条候选`}</span>` : ''}
            </div>
            ${renderEvidenceBoundarySummary(d)}
          </div>
          <div class="disc-item__aside">
            <span class="disc-item__queue-label">${currentLang() === 'en' ? 'Review queue' : '核查队列'}</span>
            <button type="button" class="disc-item__expand" aria-expanded="false" aria-controls="${escapeHtml(detailId)}">
              <span class="disc-item__expand-label">${T("page.discoveries.expand", "展开")}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </button>
          </div>
        </header>
        <div class="disc-item__detail" id="${escapeHtml(detailId)}" aria-hidden="true">
          <div class="disc-item__detail-grid">
            ${renderCandidateStructure(d, evidenceLanguage)}

            <div class="disc-readiness" style="grid-column:1 / -1">
              <div>
                <span class="disc-readiness__label">${currentLang() === 'en' ? 'Current decision' : '当前判断'}</span>
                <strong>${currentLang() === 'en' ? 'Not ready to publicly lock a study plan' : '尚不能公开锁定研究方案'}</strong>
              </div>
              <p>${readinessText}</p>
            </div>
            <div class="disc-item__detail-evidence" style="grid-column:1 / -1">
              ${window.StructuralEvidence ? window.StructuralEvidence.render(d.evidence || window.StructuralEvidence.fallback(d), { compact: true }) : ''}
            </div>
            <div style="grid-column:1 / -1">${renderValidationPlan(d)}</div>
            <div class="disc-item__cta">
              <button type="button" class="disc-item__cta-btn disc-plan-download" data-discovery-id="${escapeHtml(d.discovery_id)}">
                <span class="disc-item__cta-btn-main">${currentLang() === 'en' ? 'Download plan draft' : '下载验证计划草案'}</span>
              </button>
              <a class="disc-item__cta-btn disc-item__cta-btn--secondary" href="${escapeHtml(d.analyze_url)}">
                <span class="disc-item__cta-btn-main">${currentLang() === 'en' ? 'Open comparison workspace' : '打开比较工作台'}</span>
              </a>
              <span class="disc-item__cta-hint">${currentLang() === 'en' ? 'The workspace generates analysis, not proof.' : '工作台生成分析草稿，不生成证明。'}</span>
            </div>
            <div class="disc-item__detail-block disc-item__share-block" style="grid-column: 1 / -1">
              <h4>${currentLang() === 'en' ? 'Share this candidate' : '分享这条候选'}</h4>
              <p class="disc-item__share-hint">${currentLang() === 'en' ? 'Shared cards retain the candidate boundary.' : '分享卡会保留“候选、未验证”的边界。'}</p>
              <div class="disc-item__share"></div>
            </div>
          </div>
        </div>
      </article>
    `;
  }).join('') + paginationMarkup('priority', filtered.length, allFiltered.length);

  $$('.disc-item', listEl).forEach((article) => {
    setDiscoveryExpanded(article, expandedDiscoveryIds.has(article.dataset.discoveryId));
  });

  // Wire per-card share actions (DOM nodes, not innerHTML, for event safety).
  $$('.disc-item', listEl).forEach((article) => {
    const rank = parseInt(article.dataset.rank, 10);
    const d = filtered.find((x) => x.rank === rank);
    if (d) wireDiscoveryShare(article, d);
  });
  $$('.disc-plan-download', listEl).forEach((button) => {
    const d = filtered.find((row) => row.discovery_id === button.dataset.discoveryId);
    if (d) button.addEventListener('click', () => downloadValidationPlan(d));
  });

  // Honor the stable candidate id after render so the node exists.
  honorPendingFocus(listEl, 'a');

  // Expand click handler (replaces any prior handler on re-render)
  listEl.onclick = (e) => {
    const loadMore = e.target.closest('[data-load-more="priority"]');
    if (loadMore) {
      const firstNewIndex = filtered.length;
      visibleLimit += PAGE_SIZE;
      renderList();
      focusCandidateAt(listEl, 'a', firstNewIndex);
      return;
    }
    const expandButton = e.target.closest('.disc-item__expand');
    if (expandButton) return setDiscoveryExpanded(expandButton.closest('.disc-item'));
    if (e.target.closest('a, button')) return;
    const header = e.target.closest('.disc-item__header');
    if (header) setDiscoveryExpanded(header.closest('.disc-item'));
  };
}

function setDiscoveryExpanded(item, force) {
  if (!item) return;
  const expanded = typeof force === 'boolean' ? force : !item.classList.contains('disc-item--expanded');
  item.classList.toggle('disc-item--expanded', expanded);
  if (expanded) expandedDiscoveryIds.add(item.dataset.discoveryId);
  else expandedDiscoveryIds.delete(item.dataset.discoveryId);
  const button = item.querySelector('.disc-item__expand');
  const detail = item.querySelector('.disc-item__detail');
  if (button) {
    button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    const label = button.querySelector('.disc-item__expand-label');
    if (label) label.textContent = expanded
      ? (currentLang() === 'en' ? 'Collapse' : '收起')
      : (currentLang() === 'en' ? 'Expand' : '展开');
  }
  if (detail) detail.setAttribute('aria-hidden', expanded ? 'false' : 'true');
  if (expanded && detail && window.renderMath) window.renderMath(detail);
}

// === Tier 2 renderer — simpler cards, no deep analysis ===
function renderTier2List(listEl) {
  if (!allTier2 || allTier2.length === 0) {
    listEl.innerHTML = `<p style="text-align:center; color: var(--text-tertiary); padding: var(--space-7) 0">${T("page.discoveries.tier2_unloaded", "候选池数据未加载")}</p>`;
    return;
  }

  const visible = allTier2.slice(0, visibleLimit);
  listEl.innerHTML = visible.map((d, i) => `
    <article class="disc-t2-item" id="candidate-${escapeHtml(d.discovery_id)}" data-list-index="${i}" data-discovery-id="${escapeHtml(d.discovery_id)}" tabindex="-1" style="animation: fadeInUp 400ms var(--ease-out-expo) ${Math.min(i * 20, 300)}ms both">
      <div class="disc-t2-item__rank">#${d.rank}</div>
      <div class="disc-t2-item__body">
        <div class="disc-t2-item__pair">
          <div class="disc-t2-item__side">
            <span class="disc-t2-item__domain">${escapeHtml(L(d, "a_domain"))}</span>
            <span class="disc-t2-item__name">${escapeHtml(L(d, "a_name"))}</span>
          </div>
          <span class="disc-t2-item__symbol" aria-label="${currentLang() === 'en' ? 'candidate similarity to test' : '待检验的候选相似'}">≈?</span>
          <div class="disc-t2-item__side disc-t2-item__side--right">
            <span class="disc-t2-item__domain">${escapeHtml(L(d, "b_domain"))}</span>
            <span class="disc-t2-item__name">${escapeHtml(L(d, "b_name"))}</span>
          </div>
        </div>
        <p class="disc-t2-item__reason">${escapeHtml(LT(d.candidate_summary))}</p>
        ${renderEvidenceBoundarySummary(d)}
        <details class="disc-t2-evidence">
          <summary>${currentLang() === 'en' ? 'Inspect evidence fields' : '核对证据字段'}</summary>
          ${window.StructuralEvidence ? window.StructuralEvidence.render(d.evidence || window.StructuralEvidence.fallback(d), { compact: true }) : ''}
        </details>
      </div>
      <div class="disc-t2-item__aside">
        <span class="disc-t2-item__state">${currentLang() === 'en' ? 'Candidate' : '候选'}</span>
        <button type="button" class="disc-t2-item__analyze disc-plan-download" data-discovery-id="${escapeHtml(d.discovery_id)}">
          ${currentLang() === 'en' ? 'Plan draft' : '验证草案'}
        </button>
        <a class="disc-t2-item__analyze" href="${escapeHtml(d.analyze_url)}">
          ${currentLang() === 'en' ? 'Compare' : '比较'}
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
        </a>
      </div>
    </article>
  `).join('') + paginationMarkup('candidate-pool', visible.length, allTier2.length);
  $$('.disc-plan-download', listEl).forEach((button) => {
    const d = allTier2.find((row) => row.discovery_id === button.dataset.discoveryId);
    if (d) button.addEventListener('click', () => downloadValidationPlan(d));
  });
  honorPendingFocus(listEl, 't2');
  listEl.onclick = (event) => {
    if (event.target.closest('[data-load-more="candidate-pool"]')) {
      const firstNewIndex = visible.length;
      visibleLimit += PAGE_SIZE;
      renderList();
      focusCandidateAt(listEl, 't2', firstNewIndex);
    }
  };
}

// W3-B: render skeleton placeholders into the three load-driven regions
// (hero stats / filter / list) BEFORE fetch resolves so the page reserves
// vertical space and does not visibly shift when the real nodes pop in.
function renderDiscSkeletons() {
  const statsEl = $('#disc-hero-stats');
  if (statsEl) statsEl.innerHTML = '<div class="disc-skeleton-stats" aria-hidden="true"></div>';
  const filterEl = $('#disc-filter');
  // W1-B (2026-05-14): 2 rows match real render (tier-tabs + filter-row).
  if (filterEl) filterEl.innerHTML =
    '<div class="disc-skeleton-filter" aria-hidden="true"></div>' +
    '<div class="disc-skeleton-filter" aria-hidden="true"></div>';
  const listEl = $('#disc-list');
  if (listEl) listEl.innerHTML =
    '<div class="disc-skeleton-card" aria-hidden="true"></div>' +
    '<div class="disc-skeleton-card" aria-hidden="true"></div>' +
    '<div class="disc-skeleton-card" aria-hidden="true"></div>';
}

function renderLoadFailure() {
  const stats = $('#disc-hero-stats');
  const filters = $('#disc-filter');
  const list = $('#disc-list');
  if (stats) stats.innerHTML = `<p class="disc-unavailable">${currentLang() === 'en' ? 'Queue statistics are temporarily unavailable.' : '核查队列统计暂不可用。'}</p>`;
  if (filters) filters.innerHTML = `<p class="disc-unavailable">${currentLang() === 'en' ? 'Filters will return when the candidate catalog is available.' : '候选目录恢复后将重新显示筛选项。'}</p>`;
  if (!list) return;
  list.innerHTML =
    '<div class="disc-loaderror" role="alert">' +
      '<p class="disc-loaderror__text">' +
        (currentLang() === 'en' ? 'Candidate records are temporarily unavailable. Please try again.' : '候选记录暂时加载不出来，请重试。') +
      '</p>' +
      '<button type="button" class="disc-loaderror__retry" id="disc-retry">' +
        (currentLang() === 'en' ? 'Retry' : '重试') +
      '</button>' +
    '</div>';
  const retry = document.getElementById('disc-retry');
  if (retry) retry.addEventListener('click', () => {
    loadFailed = false;
    dataLoaded = false;
    renderDiscSkeletons();
    loadDiscoveries();
  });
}

async function loadDiscoveries() {
  const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
  try {
    const resp = await fetch('/api/discoveries');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    loadFailed = false;
    allDiscoveries = (data.discoveries || []).map(normalizeDiscovery);
    allTier2 = (data.tier2 || []).map(normalizeDiscovery);
    dataLoaded = true;
    preparePendingCandidate();
    window.__discStats = data.stats || {};
    renderStats(data.stats || {}, data.count);
    renderFilters(data.stats || {}, data.count);
    renderList();
    // W3-B: Plausible — record list ready
    try {
      if (typeof window.plausible === 'function') {
        const t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
        window.plausible('discoveries_loaded', {
          props: { count: data.count || 0, latency_ms: Math.round(t1 - t0) }
        });
      }
    } catch (e) {}
  } catch (err) {
    // P0-4 (SESSION-17): never surface the raw JS exception (e.g. a JSON
    // SyntaxError "Unexpected token '<'") to the user. Friendly empty state
    // with a retry button and content-free browser telemetry.
    console.error('[discoveries] load failed');
    loadFailed = true;
    dataLoaded = false;
    renderLoadFailure();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  // Read the stable content-derived candidate id once at startup. Legacy rank
  // links are not guessed because reordering could silently open another pair.
  try {
    const params = new URLSearchParams(location.search);
    const candidate = params.get('candidate');
    const legacyRank = params.get('d');
    if (candidate && /^discovery-[0-9a-f]{16}$/.test(candidate)) pendingFocusId = candidate;
    else if (candidate || legacyRank) deepLinkNotice = currentLang() === 'en'
      ? 'This legacy or malformed link cannot be mapped safely. Choose the candidate from the queue.'
      : '旧版或格式错误的链接无法安全定位，请从候选队列中重新选择。';
  } catch (e) {}
  renderDiscSkeletons();
  loadDiscoveries();
});

// Re-render on language change
try {
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(function () {
      try {
        if (loadFailed) {
          renderLoadFailure();
          return;
        }
        if (typeof renderStats === 'function' && window.__discStats) {
          renderStats(window.__discStats, (allDiscoveries || []).length);
        }
        if (typeof renderFilters === 'function' && window.__discStats) {
          renderFilters(window.__discStats, (allDiscoveries || []).length);
        }
        if (typeof renderList === 'function') renderList();
      } catch (e) { console.warn('[discoveries] rerender failed'); }
    });
  }
} catch (e) {}
