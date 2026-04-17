function T(key, fallback) { try { if (window.i18n && typeof window.i18n.t === "function") { var v = window.i18n.t(key); if (v && v !== key) return v; } } catch(e) {} return fallback; }

/**
 * Structural — Deep Analysis Report page
 *
 * Streams an 8-section research report via SSE and renders it section by section.
 */

const SECTIONS = [
  { key: 'shared_structure', label: '共享结构', label_key: 'page.analyze.section_shared_structure', num: '§0' },
  { key: 'your_problem_breakdown', label: '你的问题拆解', label_key: 'page.analyze.section_your_problem_breakdown', num: '§1' },
  { key: 'target_domain_intro', label: '源领域讲解', label_key: 'page.analyze.section_target_domain_intro', num: '§2' },
  { key: 'structural_mapping', label: '结构对照', label_key: 'page.analyze.section_structural_mapping', num: '§3' },
  { key: 'borrowable_insights', label: '可借用的工具', label_key: 'page.analyze.section_borrowable_insights', num: '§4' },
  { key: 'how_to_combine', label: '怎么结合', label_key: 'page.analyze.section_how_to_combine', num: '§5' },
  { key: 'research_directions', label: '研究方向', label_key: 'page.analyze.section_research_directions', num: '§6' },
  { key: 'risks_and_limits', label: '迁移风险', label_key: 'page.analyze.section_risks_and_limits', num: '§7' },
  { key: 'action_plan', label: '本周行动', label_key: 'page.analyze.section_action_plan', num: '§8' },
];

function sectionLabel(s) {
  return T(s.label_key, s.label);
}

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

// === Partial JSON parser (tolerant of incomplete streams) ===
function parsePartialJson(text) {
  const trimmed = text.trim();
  if (!trimmed.startsWith('{')) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    // Try progressively trimming to find a valid prefix
    for (let i = trimmed.length; i > 100; i -= 50) {
      const candidate = trimmed.substring(0, i);
      // Balance braces
      let depth = 0;
      let inString = false;
      let escape = false;
      let lastValidEnd = -1;
      for (let j = 0; j < candidate.length; j++) {
        const ch = candidate[j];
        if (escape) { escape = false; continue; }
        if (ch === '\\') { escape = true; continue; }
        if (ch === '"' && !escape) inString = !inString;
        if (inString) continue;
        if (ch === '{' || ch === '[') depth++;
        else if (ch === '}' || ch === ']') {
          depth--;
          if (depth === 0) lastValidEnd = j;
        }
      }
      if (lastValidEnd > 0) {
        try {
          return JSON.parse(candidate.substring(0, lastValidEnd + 1));
        } catch { continue; }
      }
    }
    return null;
  }
}

// === KaTeX rendering helpers ===
function renderFormula(latex) {
  if (!latex || typeof window.katex === 'undefined') {
    return `<div class="structure-block__formula">${escapeHtml(latex || '')}</div>`;
  }
  try {
    const html = window.katex.renderToString(latex, {
      throwOnError: false,
      displayMode: true,
      errorColor: 'var(--text-tertiary)',
      strict: false,
      output: 'html',
    });
    return `<div class="structure-block__formula structure-block__formula--rendered">${html}</div>`;
  } catch (e) {
    console.warn('[analyze] KaTeX render failed:', e);
    return `<div class="structure-block__formula">${escapeHtml(latex)}</div>`;
  }
}

function renderInlineMath(latex) {
  if (!latex || typeof window.katex === 'undefined') return escapeHtml(latex || '');
  try {
    return window.katex.renderToString(latex, {
      throwOnError: false,
      displayMode: false,
      errorColor: 'var(--text-tertiary)',
      strict: false,
      output: 'html',
    });
  } catch (e) {
    return escapeHtml(latex);
  }
}

// Use the global renderMath from utils.js

// === Section renderers ===
const renderers = {
  shared_structure(data) {
    if (!data) return '';
    return `
      <div class="structure-block">
        <div class="structure-block__name">${escapeHtml(data.name || '—')}</div>
        ${data.formal_expression ? renderFormula(data.formal_expression) : ''}
        ${data.intuition ? `<div class="structure-block__intuition">${escapeHtml(data.intuition)}</div>` : ''}
      </div>
    `;
  },

  your_problem_breakdown(data) {
    if (!data) return '';
    const vars = data.key_variables || [];
    return `
      ${data.summary ? `<p>${escapeHtml(data.summary)}</p>` : ''}

      ${vars.length > 0 ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_key_variables', '关键变量')}</h3>
        <div class="variables">
          ${vars.map(v => `
            <div class="variable">
              <span class="variable__name">${escapeHtml(v.name || '')}</span>
              <span class="variable__desc">${escapeHtml(v.description || '')}</span>
              ${v.role ? `<span class="variable__role">${escapeHtml(v.role)}</span>` : '<span></span>'}
            </div>
          `).join('')}
        </div>
      ` : ''}

      ${data.dynamics ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_dynamics', '动力学')}</h3>
        <p>${escapeHtml(data.dynamics)}</p>
      ` : ''}

      ${data.why_stuck ? `
        <div class="callout callout--warning">
          <div class="callout__label">${T('page.analyze.sub_why_stuck', '为什么卡壳')}</div>
          <div class="callout__text">${escapeHtml(data.why_stuck)}</div>
        </div>
      ` : ''}
    `;
  },

  target_domain_intro(data) {
    if (!data) return '';
    const phenom = data.corresponding_phenomenon || {};
    const thinkers = data.key_thinkers || [];
    const tools = data.mature_tools || [];
    return `
      <h3 class="section__subtitle">${escapeHtml(data.domain_name || T('page.analyze.sub_source_domain', '源领域'))}</h3>
      ${data.what_it_studies ? `<p>${escapeHtml(data.what_it_studies)}</p>` : ''}

      ${phenom.name ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_corresponding_phenomenon', '这个领域里的对应现象')}：${escapeHtml(phenom.name)}</h3>
        ${phenom.plain_description ? `<p>${escapeHtml(phenom.plain_description)}</p>` : ''}
        ${phenom.discovery_history ? `<p><strong>${T('page.analyze.sub_discovery_history', '发现历史')}：</strong>${escapeHtml(phenom.discovery_history)}</p>` : ''}
      ` : ''}

      ${thinkers.length > 0 ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_key_thinkers', '关键人物')}</h3>
        <div class="thinkers">
          ${thinkers.map(t => `
            <div class="thinker">
              <span class="thinker__year">${escapeHtml(String(t.year || ''))}</span>
              <span class="thinker__name">${escapeHtml(t.name || '')}</span>
              <span class="thinker__contribution">${escapeHtml(t.contribution || '')}</span>
            </div>
          `).join('')}
        </div>
      ` : ''}

      ${tools.length > 0 ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_mature_tools', '成熟工具')}</h3>
        <div class="tools-list">
          ${tools.map(t => `
            <div class="tool">
              <div class="tool__name">${escapeHtml(t.name || '')}</div>
              <div class="tool__brief">${escapeHtml(t.brief || '')}</div>
            </div>
          `).join('')}
        </div>
      ` : ''}
    `;
  },

  structural_mapping(data) {
    if (!data) return '';
    const params = data.parameter_map || [];
    return `
      ${data.rationale ? `<p>${escapeHtml(data.rationale)}</p>` : ''}

      ${params.length > 0 ? `
        <div class="param-map">
          ${params.map(p => `
            <div class="param-row">
              <div class="param-row__pair">
                <div class="param-row__side">
                  <div class="param-row__side-label">${T('page.analyze.sub_source_domain', '源领域')}</div>
                  <div class="param-row__concept">${escapeHtml(p.source_concept || '')}</div>
                  <div class="param-row__explain">${escapeHtml(p.source_explanation || '')}</div>
                </div>
                <div class="param-row__arrow">↔</div>
                <div class="param-row__side">
                  <div class="param-row__side-label">${T('page.analyze.sub_your_problem', '你的问题')}</div>
                  <div class="param-row__concept">${escapeHtml(p.target_concept || '')}</div>
                  <div class="param-row__explain">${escapeHtml(p.target_explanation || '')}</div>
                </div>
              </div>
              ${p.isomorphism_reason ? `<div class="param-row__reason">${escapeHtml(p.isomorphism_reason)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      ` : ''}
    `;
  },

  borrowable_insights(data) {
    if (!Array.isArray(data) || data.length === 0) return '';
    const md = window.mdInline || ((s) => escapeHtml(s || ''));
    const mdb = window.mdBlock || ((s) => escapeHtml(s || ''));
    return data.map((ins, i) => `
      <div class="insight">
        <div class="insight__header">
          <span class="insight__number">${String(i + 1).padStart(2, '0')}</span>
          <span class="insight__tool">${md(ins.tool || '')}</span>
        </div>
        ${ins.what_it_solves_in_source ? `
          <div class="insight__subsection">
            <span class="insight__subsection-label">${T('page.analyze.sub_what_it_solves', '在源领域中它解决什么')}</span>
            <div class="insight__subsection-text">${md(ins.what_it_solves_in_source)}</div>
          </div>
        ` : ''}
        ${ins.translated_to_target ? `
          <div class="insight__subsection">
            <span class="insight__subsection-label">${T('page.analyze.sub_translated_to_target', '翻译到你的问题')}</span>
            <div class="insight__subsection-text">${md(ins.translated_to_target)}</div>
          </div>
        ` : ''}
        ${ins.concrete_application ? `
          <div class="insight__subsection insight__apply">
            <span class="insight__subsection-label">${T('page.analyze.sub_concrete_application', '具体怎么用')}</span>
            <div class="insight__subsection-text insight__subsection-text--block">${mdb(ins.concrete_application)}</div>
          </div>
        ` : ''}
      </div>
    `).join('');
  },

  how_to_combine(data) {
    if (!data) return '';
    const steps = data.steps || [];
    const assumptions = data.assumptions_to_verify || [];
    return `
      ${steps.length > 0 ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_execution_steps', '执行步骤')}</h3>
        <div class="steps">
          ${steps.map(s => `<div class="step">${escapeHtml(s)}</div>`).join('')}
        </div>
      ` : ''}

      ${assumptions.length > 0 ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_assumptions', '需要验证的假设')}</h3>
        <ul style="padding-left: 24px; font-size: var(--fs-14); color: var(--text-secondary); line-height: var(--lh-relaxed);">
          ${assumptions.map(a => `<li style="margin-bottom: 8px;">${escapeHtml(a)}</li>`).join('')}
        </ul>
      ` : ''}

      ${data.boundary_conditions ? `
        <div class="callout">
          <div class="callout__label">${T('page.analyze.sub_boundary_conditions', '边界条件')}</div>
          <div class="callout__text">${escapeHtml(data.boundary_conditions)}</div>
        </div>
      ` : ''}
    `;
  },

  research_directions(data) {
    if (!data) return '';
    const status = data.literature_status || '';
    let statusClass = 'known';
    if (status.includes('未有') || status.includes('未探索')) statusClass = 'novel';
    else if (status.includes('部分') || status.includes('微弱')) statusClass = 'partial';

    const refs = data.suggested_references || [];

    return `
      <div class="research-status research-status--${statusClass}">
        ${T('page.analyze.sub_literature_status', '文献状态')} · ${escapeHtml(status || T('page.analyze.status_unknown', '未知'))}
      </div>

      ${data.status_explanation ? `<p>${escapeHtml(data.status_explanation)}</p>` : ''}

      ${data.if_novel_opportunity ? `
        <div class="opportunity">
          <div class="opportunity__label">${T('page.analyze.sub_research_opportunity', '⭐ 潜在的研究机会')}</div>
          <div class="opportunity__text">${escapeHtml(data.if_novel_opportunity)}</div>
        </div>
      ` : ''}

      ${refs.length > 0 ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_suggested_references', '建议参考')}</h3>
        <div class="references">
          ${refs.map(r => `
            <div class="reference">
              <div class="reference__title">${escapeHtml(r.title || '')}</div>
              ${r.note ? `<div class="reference__note">${escapeHtml(r.note)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      ` : ''}
    `;
  },

  risks_and_limits(data) {
    if (!Array.isArray(data) || data.length === 0) return '';
    return `
      <div class="risks">
        ${data.map(r => {
          const sev = (r.severity || '').trim();
          let sevClass = 'low';
          let sevLabel = T('page.analyze.severity_low', '低');
          if (sev === '高') { sevClass = 'high'; sevLabel = T('page.analyze.severity_high', '高'); }
          else if (sev === '中') { sevClass = 'medium'; sevLabel = T('page.analyze.severity_medium', '中'); }
          else if (sev === '低') { sevClass = 'low'; sevLabel = T('page.analyze.severity_low', '低'); }
          else if (sev) { sevLabel = sev; }
          return `
            <div class="risk">
              <span class="risk__severity risk__severity--${sevClass}">${escapeHtml(sevLabel)}</span>
              <div>
                <div class="risk__name">${escapeHtml(r.risk_name || '')}</div>
                <div class="risk__explain">${escapeHtml(r.explanation || '')}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  },

  action_plan(data) {
    if (!data) return '';
    const ifShort = data.if_time_short;
    const items = Array.isArray(data.this_week) ? data.this_week : [];
    const intro = data.intro;
    const followup = data.next_week_followup;

    const md = window.mdInline || ((s) => escapeHtml(s || ''));
    const mdb = window.mdBlock || ((s) => escapeHtml(s || ''));

    // The LLM often writes "how" as "1. xxx 2. yyy 3. zzz" inline. Normalize
    // this into real line breaks so mdBlock can render it as an <ol>.
    const normalizeSteps = (text) => {
      if (!text) return '';
      const s = String(text).trim();
      // If already has newlines, trust the LLM
      if (s.includes('\n')) return s;
      // Match inline "1. ... 2. ... 3. ..." patterns and split
      const m = s.match(/^\s*1[\.、]\s*.+/);
      if (m) {
        // Split on digit-period-space patterns while keeping the delimiters
        return s.replace(/(\d+[\.、])\s*/g, '\n$1 ').trim();
      }
      return s;
    };

    const itemHtml = (it, idx) => {
      const rank = it.rank || (idx + 1);
      const isOptional = rank >= 4;
      return `
        <li class="action-item ${isOptional ? 'action-item--optional' : 'action-item--core'}">
          <div class="action-item__header">
            <span class="action-item__rank">${rank}</span>
            <h3 class="action-item__title">${md(it.title || '')}</h3>
            ${it.estimated_time ? `<span class="action-item__time">${escapeHtml(it.estimated_time)}</span>` : ''}
          </div>
          ${it.how ? `
            <div class="action-item__row">
              <span class="action-item__row-label">${T('page.analyze.action_how', '怎么做')}</span>
              <div class="action-item__row-text action-item__row-text--block">${mdb(normalizeSteps(it.how))}</div>
            </div>
          ` : ''}
          ${it.verification ? `
            <div class="action-item__row">
              <span class="action-item__row-label">${T('page.analyze.action_verification', '验证指标')}</span>
              <div class="action-item__row-text">${md(it.verification)}</div>
            </div>
          ` : ''}
          ${it.expected_impact ? `
            <div class="action-item__row">
              <span class="action-item__row-label">${T('page.analyze.action_expected', '预期产出')}</span>
              <div class="action-item__row-text">${md(it.expected_impact)}</div>
            </div>
          ` : ''}
        </li>
      `;
    };

    return `
      ${intro ? `<p class="action-plan__intro">${md(intro)}</p>` : ''}

      ${ifShort ? `
        <div class="action-pinned">
          <div class="action-pinned__label">${T('page.analyze.action_if_only_one', '⭐ 如果你只能做一件事')}</div>
          <h3 class="action-pinned__title">${md(ifShort.title || '')}</h3>
          ${ifShort.rationale ? `<p class="action-pinned__rationale">${md(ifShort.rationale)}</p>` : ''}
        </div>
      ` : ''}

      ${items.length > 0 ? `
        <h3 class="section__subtitle">${T('page.analyze.action_full_plan', '本周完整计划')}</h3>
        <ol class="action-list">
          ${items.map(itemHtml).join('')}
        </ol>
      ` : ''}

      ${followup ? `
        <div class="action-followup">
          <span class="action-followup__label">${T('page.analyze.action_next_week', '下周回头看')}</span>
          <p class="action-followup__text">${md(followup)}</p>
        </div>
      ` : ''}
    `;
  },
};

// === Progress tracker ===
function renderProgress() {
  const el = $('#analyze-progress');
  if (!el) return;
  el.innerHTML = SECTIONS.map(s => `
    <button class="analyze-progress__item" data-key="${s.key}">${escapeHtml(sectionLabel(s))}</button>
  `).join('');

  el.addEventListener('click', (e) => {
    const btn = e.target.closest('.analyze-progress__item');
    if (btn) {
      const target = $(`#section-${btn.dataset.key}`);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
}

function updateProgress(activeKey, doneKeys) {
  $$('.analyze-progress__item').forEach(el => {
    const key = el.dataset.key;
    el.classList.toggle('active', key === activeKey);
    el.classList.toggle('done', doneKeys.has(key));
  });
}

// === Render all sections into the container ===
function renderSections(container) {
  container.innerHTML = SECTIONS.map(s => `
    <section class="section" id="section-${s.key}" data-key="${s.key}">
      <div class="section__number">${s.num}</div>
      <h2 class="section__title">${escapeHtml(sectionLabel(s))}</h2>
      <div class="section__body" id="section-body-${s.key}"></div>
    </section>
  `).join('');
}

function updateSection(key, data) {
  const renderer = renderers[key];
  if (!renderer) return;
  const body = $(`#section-body-${key}`);
  if (!body) return;
  const html = renderer(data);
  if (html) {
    body.innerHTML = html;
    const section = $(`#section-${key}`);
    if (section && !section.classList.contains('revealed')) {
      section.classList.add('revealed');
    }
  }
}

// === Header renderers ===
function renderHeader(meta) {
  const el = $('#analyze-header');
  if (!el) return;
  const isQuery = meta.is_query_mode;
  const a = meta.a;
  const b = meta.b;

  const questionText = isQuery ? (b.original_query || b.description || '') : b.name;
  const label = isQuery ? T('page.analyze.header_your_question', '你的问题') : T('page.analyze.header_comparison', '对比分析');
  const targetStrong = isQuery ? T('page.analyze.header_your_question', '你的问题') : escapeHtml(b.domain);

  el.innerHTML = `
    <div class="analyze-header__label">${escapeHtml(label)}</div>
    <h1 class="analyze-header__question">${escapeHtml(questionText)}</h1>
    <div class="analyze-header__bridge">
      <span>${T('page.analyze.header_borrow_from', '从 {source} 借用答案').replace('{source}', `<strong>${escapeHtml(a.domain)} · ${escapeHtml(a.name)}</strong>`)}</span>
      <svg class="analyze-header__bridge-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
      <span>${T('page.analyze.header_apply_to', '应用到 {target}').replace('{target}', `<strong>${targetStrong}</strong>`)}</span>
      <span style="color: var(--text-tertiary); font-family: var(--font-mono); font-size: var(--fs-12); margin-left: 8px;">${T('page.analyze.header_similarity', '{pct}% 结构相似').replace('{pct}', Math.round((meta.similarity || 0) * 100))}</span>
    </div>
  `;
}

// === Progress overlay updates ===
function updateLoadingProgress(chars) {
  const line = $('#analyze-loading .analyze-loading__progress-line');
  if (!line) {
    const loading = $('#analyze-loading');
    if (loading) {
      const p = document.createElement('div');
      p.className = 'analyze-loading__progress-line';
      loading.appendChild(p);
    }
  }
  const lineEl = $('#analyze-loading .analyze-loading__progress-line');
  if (lineEl) {
    lineEl.textContent = T('page.analyze.loading_progress_line', '已生成 {chars} 字 · LLM 正在写研究报告').replace('{chars}', chars);
  }
}

// === Final render: all sections at once with stagger animation ===
function renderFinalReport(report) {
  const container = $('#analyze-sections');
  if (!container) return;

  container.innerHTML = SECTIONS.map((s, i) => {
    const renderer = renderers[s.key];
    const data = report[s.key];
    const html = renderer ? renderer(data) : '';
    return `
      <section class="section" id="section-${s.key}" data-key="${s.key}" style="animation-delay: ${i * 150}ms">
        <div class="section__number">${s.num}</div>
        <h2 class="section__title">${escapeHtml(sectionLabel(s))}</h2>
        <div class="section__body">${html || '<p style="color:var(--text-tertiary)">—</p>'}</div>
      </section>
    `;
  }).join('');

  // Mark all progress items as done
  const allKeys = new Set(SECTIONS.map(s => s.key));
  updateProgress(null, allKeys);
}

// === Section-by-section rendering ===
// Create empty placeholders for all sections upfront (hidden initially).
// As `section` events arrive, fill each one and animate it in.
function pendingBodyHtml() {
  return `
    <div class="section__wait">
      ${window.hourglassSvg ? window.hourglassSvg() : ''}
      <span class="section__wait-label">${T('page.analyze.status_waiting', '等待中')}</span>
    </div>
  `;
}

// Approximate ETA per section based on observed averages.
// Used to give the user a "已 4s / 约 8s" sense of progress instead of an
// open-ended elapsed counter that just keeps climbing.
const SECTION_ETA = {
  shared_structure: 6,
  your_problem_breakdown: 7,
  target_domain_intro: 9,
  structural_mapping: 8,
  borrowable_insights: 10,
  how_to_combine: 8,
  research_directions: 6,
  risks_and_limits: 5,
  action_plan: 8,
};

function streamingBodyHtml(key) {
  const eta = SECTION_ETA[key] || 8;
  return `
    <div class="section__streaming-indicator">
      ${window.hourglassSvg ? window.hourglassSvg() : ''}
      <span>${T('page.analyze.status_generating_section', '正在生成这一部分')}</span>
      <span class="elapsed-timer section__stream-timer" data-eta="${eta}">${T('page.analyze.timer_elapsed_eta', '已 {s}s / 约 {eta}s').replace('{s}', '0').replace('{eta}', eta)}</span>
    </div>
    <div class="shimmer-line"></div>
  `;
}

function renderSectionSkeleton() {
  const container = $('#analyze-sections');
  if (!container) return;
  container.innerHTML = SECTIONS.map(s => `
    <section class="section section--pending" id="section-${s.key}" data-key="${s.key}">
      <div class="section__number">${s.num}</div>
      <h2 class="section__title">${escapeHtml(sectionLabel(s))}</h2>
      <div class="section__body">${pendingBodyHtml()}</div>
    </section>
  `).join('');
}

// Stop function for the currently-streaming section's elapsed timer.
let _currentStreamTimerStop = null;

function setStreamingSection(key) {
  // Clear previous streaming marker + timer
  if (_currentStreamTimerStop) {
    _currentStreamTimerStop();
    _currentStreamTimerStop = null;
  }
  let streamingEl = null;
  $$('.section').forEach(el => {
    if (el.classList.contains('section--revealed')) return;
    const k = el.dataset.key;
    if (k === key) {
      el.classList.remove('section--pending');
      el.classList.add('section--streaming');
      streamingEl = el;
      const body = el.querySelector('.section__body');
      if (body) {
        body.innerHTML = streamingBodyHtml(key);
        const timerEl = body.querySelector('.section__stream-timer');
        if (timerEl && window.startElapsedTimer) {
          const eta = Number(timerEl.getAttribute('data-eta')) || 8;
          // Custom format that shows "已 Xs / 约 Ys"
          _currentStreamTimerStop = window.startElapsedTimer(timerEl, {
            format: (s) => T('page.analyze.timer_elapsed_eta', '已 {s}s / 约 {eta}s').replace('{s}', s).replace('{eta}', eta),
          });
        }
      }
    } else if (!el.classList.contains('section--revealed')) {
      el.classList.remove('section--streaming');
      el.classList.add('section--pending');
      const body = el.querySelector('.section__body');
      if (body && !body.querySelector('.section__wait')) {
        body.innerHTML = pendingBodyHtml();
      }
    }
  });
  // Auto-scroll the currently-generating section into view (only after the
  // first section, otherwise the page jumps before user even sees the loading)
  if (streamingEl && _currentStreamTimerStop) {
    requestAnimationFrame(() => {
      const rect = streamingEl.getBoundingClientRect();
      const offset = rect.top + window.scrollY - 120;
      // Only scroll if the section isn't already comfortably in view
      if (rect.top < 80 || rect.top > window.innerHeight * 0.6) {
        window.scrollTo({ top: offset, behavior: 'smooth' });
      }
    });
  }
}

function revealSection(key, data) {
  const section = $(`#section-${key}`);
  if (!section) return;
  const renderer = renderers[key];
  if (!renderer) return;
  const body = section.querySelector('.section__body');
  if (!body) return;
  const html = renderer(data);
  if (html) {
    // Stop the stream timer if this section was the streaming one
    if (section.classList.contains('section--streaming') && _currentStreamTimerStop) {
      _currentStreamTimerStop();
      _currentStreamTimerStop = null;
    }
    body.innerHTML = html;
    section.classList.remove('section--pending');
    section.classList.remove('section--streaming');
    section.classList.add('section--revealed');
    // Auto-render any inline math in this section (like $...$ in descriptions)
    window.renderMath(body);
  }
}

function updateProgressState(receivedKeys, currentStreamingKey) {
  $$('.analyze-progress__item').forEach(el => {
    const key = el.dataset.key;
    el.classList.toggle('done', receivedKeys.has(key));
    el.classList.toggle('active', key === currentStreamingKey);
  });
}

// === Main streaming loop ===
function streamAnalysis(params) {
  const url = `/api/analyze/stream?${params.toString()}`;
  console.log('[analyze] Opening SSE:', url);
  const es = new EventSource(url);

  let meta = null;
  const receivedKeys = new Set();
  let finalReport = null;
  let firstSectionSeen = false;

  // Start the overall elapsed timer for the loading block
  let stopLoadingTimer = null;
  const loadingTimerEl = $('#analyze-loading-timer');
  if (loadingTimerEl && window.startElapsedTimer) {
    stopLoadingTimer = window.startElapsedTimer(loadingTimerEl);
  }

  es.addEventListener('meta', (e) => {
    console.log('[analyze] meta received');
    meta = JSON.parse(e.data);
    // Stash for the favorite button so it can include a/b names in the entry
    window._analyzeMeta = meta;
    renderHeader(meta);
    renderProgress();
    renderSectionSkeleton();
    // Mark the first section as the currently-streaming one
    if (SECTIONS.length > 0) {
      setStreamingSection(SECTIONS[0].key);
    }
    // If this report is already favorited, back-fill the stored entry with names
    if (window.refreshFavoriteWithMeta) {
      window.refreshFavoriteWithMeta(meta);
    }
  });

  es.addEventListener('section', (e) => {
    const { key, data } = JSON.parse(e.data);
    console.log('[analyze] section:', key);
    receivedKeys.add(key);
    // Incrementally build window._finalReport so the "复制为简报" button
    // can work even before the `done` event arrives.
    if (!window._finalReport) window._finalReport = {};
    window._finalReport[key] = data;
    revealSection(key, data);

    // First section arriving — hide the big loading block
    if (!firstSectionSeen) {
      firstSectionSeen = true;
      if (stopLoadingTimer) { stopLoadingTimer(); stopLoadingTimer = null; }
      const loading = $('#analyze-loading');
      if (loading) {
        loading.classList.add('analyze-loading--fading');
        setTimeout(() => loading.remove(), 400);
      }
    }

    // Advance the streaming marker to the next pending section
    const nextKey = SECTIONS.find(s => !receivedKeys.has(s.key))?.key;
    if (nextKey) {
      setStreamingSection(nextKey);
    }
    updateProgressState(receivedKeys, nextKey);
  });

  es.addEventListener('text', (e) => {
    const chunk = JSON.parse(e.data);
    // Update loading progress line (before the first section arrives)
    if (!firstSectionSeen) {
      updateLoadingProgress(chunk.total_length || 0);
    }
  });

  es.addEventListener('done', (e) => {
    console.log('[analyze] done received');
    const data = JSON.parse(e.data);
    if (data.report) {
      finalReport = data.report;
      // Stash so the "复制为简报" button can read it
      window._finalReport = finalReport;
      // Ensure all sections are rendered (in case some were missed)
      for (const s of SECTIONS) {
        if (!receivedKeys.has(s.key) && finalReport[s.key]) {
          receivedKeys.add(s.key);
          revealSection(s.key, finalReport[s.key]);
        }
      }
    }
    if (stopLoadingTimer) { stopLoadingTimer(); stopLoadingTimer = null; }
    if (_currentStreamTimerStop) { _currentStreamTimerStop(); _currentStreamTimerStop = null; }
    const loading = $('#analyze-loading');
    if (loading) loading.remove();
    updateProgressState(receivedKeys, null);
    es.close();
  });

  // Backend may emit a `retry` event when the first generation attempt fails
  // and it is about to try again. Show a soft hint in the loading block.
  es.addEventListener('retry', (e) => {
    console.warn('[analyze] retry event:', e && e.data);
    const titleEl = $('#analyze-loading .analyze-loading__title');
    const hintEl = $('#analyze-loading .analyze-loading__hint');
    if (titleEl) titleEl.textContent = T('page.analyze.retry_first', '首次生成失败，正在重试...');
    if (hintEl) hintEl.textContent = T('page.analyze.retry_first_hint', '模型刚刚没稳定输出，我们换个角度再来一次。');
  });

  es.addEventListener('error', (e) => {
    // The backend emits explicit `error` events (with JSON data) when it
    // gives up. Distinct from the transport-level `es.onerror` below.
    let data = {};
    try {
      data = JSON.parse(e.data || '{}');
    } catch {
      console.error('[analyze] error event (no data):', e);
      return;
    }
    console.error('[analyze] stream error:', data);
    if (stopLoadingTimer) { stopLoadingTimer(); stopLoadingTimer = null; }
    if (_currentStreamTimerStop) { _currentStreamTimerStop(); _currentStreamTimerStop = null; }
    renderStreamError({
      message: data.message || data.error || T("page.analyze.error_title", "生成失败"),
      retryable: data.retryable,
      raw: data,
    });
    try { es.close(); } catch {}
  });

  es.onerror = (err) => {
    console.error('[analyze] EventSource error:', err);
    if (stopLoadingTimer) { stopLoadingTimer(); stopLoadingTimer = null; }
    if (_currentStreamTimerStop) { _currentStreamTimerStop(); _currentStreamTimerStop = null; }
    // Only surface a user-facing error if we haven't rendered anything yet.
    // Mid-stream disconnect leaves existing sections readable.
    if (receivedKeys.size === 0) {
      renderStreamError({
        message: T('page.analyze.error_hint', '连接中断，可能是网络或 LLM 响应超时'),
        retryable: undefined, // unknown — default to refresh-retry
      });
    }
    try { es.close(); } catch {}
  };
}

// === Render an error state in place of the loading block ===
// `retryable === false`  → show "重试" button (user can click to re-request)
// otherwise              → show T("page.analyze.btn_retry", "刷新重试") (full reload) as the safer default
function renderStreamError({ message, retryable }) {
  const loading = $('#analyze-loading');
  if (!loading) return;
  const msg = escapeHtml(message || T("page.analyze.error_title", "生成失败"));
  const canSoftRetry = retryable !== false;
  const buttonHtml = canSoftRetry
    ? `<a href="javascript:location.reload()" class="btn btn--primary">${T("page.analyze.btn_retry", "刷新重试")}</a>`
    : `<button type="button" class="btn btn--primary" id="analyze-retry-btn">${T('page.analyze.btn_retry_soft', '重试')}</button>`;
  loading.innerHTML = `
    <h2 class="analyze-loading__title" style="color: var(--danger, #dc2626)">${T("page.analyze.error_title", "生成失败")}</h2>
    <p class="analyze-loading__hint">${msg}</p>
    <p style="margin-top: 16px; display: flex; gap: 12px; justify-content: center;">
      ${buttonHtml}
      <a href="/" class="btn btn--ghost">${T("page.analyze.btn_back_home", "返回首页")}</a>
    </p>
  `;
  // Ensure the loading block is visible (it may have been fading out)
  loading.classList.remove('analyze-loading--fading');

  const retryBtn = document.getElementById('analyze-retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      // Reinitialize the full stream without a page reload
      const bId = getQueryParam('id');
      const q = getQueryParam('q');
      const aId = getQueryParam('a_id');
      if (!bId) { location.reload(); return; }
      const p = new URLSearchParams();
      p.set('b_id', bId);
      if (q) p.set('text_a', q);
      else if (aId) p.set('a_id', aId);
      loading.innerHTML = `
        <div class="analyze-loading__dots">
          <span class="analyze-loading__dot"></span>
          <span class="analyze-loading__dot"></span>
          <span class="analyze-loading__dot"></span>
        </div>
        <h2 class="analyze-loading__title">${T('page.analyze.loading_title', '正在生成深度分析报告')}</h2>
        <p class="analyze-loading__hint">${T('page.analyze.loading_hint_long', '我们正在写一份跨学科迁移研究报告。')}</p>
        <div class="analyze-loading__timer-row">
          <span class="elapsed-timer" id="analyze-loading-timer">${T('page.analyze.timer_waiting', '已等待 0s')}</span>
          <span class="analyze-loading__typical">${T('page.analyze.timer_typical', '通常需 30–60s')}</span>
        </div>
      `;
      streamAnalysis(p);
    });
  }
}

// === Brief builder ===
// Pulls fields from window._finalReport (built incrementally as sections
// arrive) plus window._analyzeMeta (set on the SSE meta event) and shapes
// them into a clean Markdown brief suitable for pasting into Notion / Slack /
// email. No LLM call — pure local extraction.
function buildBriefMarkdown() {
  const meta = window._analyzeMeta || {};
  const r = window._finalReport || {};
  const a = meta.a || {};
  const b = meta.b || {};
  const isQuery = meta.is_query_mode;

  const userQuery = isQuery ? (b.original_query || b.description || '') : '';
  const targetLabel = isQuery ? T('page.analyze.header_your_question', '你的问题') : `${b.domain || ''} · ${b.name || ''}`;
  const url = window.location.href;

  // Helper: strip $...$ math markers and **bold** for plain markdown context
  const clean = (s) => (s || '').replace(/\$([^$]+)\$/g, '$1');

  const struct = r.shared_structure || {};
  const insights = Array.isArray(r.borrowable_insights) ? r.borrowable_insights : [];
  const risks = Array.isArray(r.risks_and_limits) ? r.risks_and_limits : [];
  const action = r.action_plan || {};
  const actions = Array.isArray(action.this_week) ? action.this_week : [];
  const ifShort = action.if_time_short;

  const lines = [];
  lines.push(`# ${T('page.analyze.brief_title', 'Structural · 跨学科分析简报')}`);
  lines.push('');
  if (userQuery) {
    lines.push(`> **${T('page.analyze.brief_your_question', '你的问题')}**: ${userQuery}`);
  }
  lines.push(`> **${T('page.analyze.brief_analogy', '跨学科类比')}**: ${a.domain || ''} · ${a.name || ''}  ↔  ${targetLabel}`);
  if (struct.name) {
    lines.push(`> **${T('page.analyze.brief_shared_structure', '共享结构')}**: ${struct.name}`);
  }
  if (typeof meta.similarity === 'number') {
    lines.push(`> **${T('page.analyze.brief_similarity', '结构相似度')}**: ${Math.round(meta.similarity * 100)}%`);
  }
  lines.push('');

  // Core insight
  if (struct.intuition) {
    lines.push(`## ${T('page.analyze.brief_one_liner', '一句话核心')}`);
    lines.push(clean(struct.intuition));
    lines.push('');
  }

  // Top 3 borrowable insights — translated_to_target is the punchy summary
  if (insights.length > 0) {
    lines.push(`## ${T('page.analyze.brief_top_insights', '三条最关键的洞察')}`);
    insights.slice(0, 3).forEach((ins, i) => {
      const tool = ins.tool || '';
      const translated = clean(ins.translated_to_target || '');
      lines.push(`${i + 1}. **${tool}** — ${translated}`);
    });
    lines.push('');
  }

  // Action plan — the money shot
  if (ifShort) {
    lines.push(`## ${T('page.analyze.action_if_only_one', '⭐ 如果你只能做一件事')}`);
    lines.push(`**${ifShort.title || ''}**`);
    if (ifShort.rationale) lines.push(clean(ifShort.rationale));
    lines.push('');
  }

  if (actions.length > 0) {
    lines.push(`## ${T('page.analyze.brief_weekly_actions', '本周行动清单')}`);
    actions.forEach((it) => {
      const rank = it.rank || '?';
      const time = it.estimated_time ? ` _（${it.estimated_time}）_` : '';
      const optional = (it.rank || 0) >= 4 ? ' (optional)' : '';
      lines.push(`${rank}. **${clean(it.title || '')}**${time}${optional}`);
      if (it.how) lines.push(`   - ${T('page.analyze.action_how', '怎么做')}：${clean(it.how)}`);
      if (it.verification) lines.push(`   - ${T('page.analyze.brief_verify', '验证')}：${clean(it.verification)}`);
      if (it.expected_impact) lines.push(`   - ${T('page.analyze.brief_expected', '预期')}：${clean(it.expected_impact)}`);
    });
    lines.push('');
  }

  if (action.next_week_followup) {
    lines.push(`## ${T('page.analyze.action_next_week', '下周回头看')}`);
    lines.push(clean(action.next_week_followup));
    lines.push('');
  }

  // Risks
  if (risks.length > 0) {
    lines.push(`## ${T('page.analyze.section_risks_and_limits', '迁移风险')}`);
    risks.slice(0, 3).forEach((rk) => {
      const sev = rk.severity ? `[${rk.severity}] ` : '';
      lines.push(`- ${sev}**${rk.risk_name || ''}** — ${clean(rk.explanation || '')}`);
    });
    lines.push('');
  }

  lines.push('---');
  lines.push(`_${T('page.analyze.brief_footer', '来自 [Structural]')}(${url})_`);

  return lines.join('\n');
}

// === Share + favorite action bar (in the breadcrumb) ===
function initAnalyzeActions() {
  // Brief / 1-pager export
  const briefBtn = document.getElementById('analyze-brief-btn');
  if (briefBtn) {
    briefBtn.addEventListener('click', async () => {
      if (!window._finalReport || Object.keys(window._finalReport).length === 0) {
        if (window.showToast) window.showToast(T('page.analyze.toast_still_generating', '报告还在生成中，请稍后再点'));
        return;
      }
      const md = buildBriefMarkdown();
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(md);
        } else {
          const ta = document.createElement('textarea');
          ta.value = md;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
        }
        if (window.showToast) window.showToast(T('page.analyze.toast_brief_copied', '已复制为 Markdown 简报，可以粘贴到 Notion / Slack / 邮件'));
      } catch (err) {
        console.error('[analyze] brief copy failed:', err);
        if (window.showToast) window.showToast(T('page.analyze.toast_copy_failed_perm', '复制失败，请检查浏览器权限'));
      }
    });
  }

  const shareBtn = document.getElementById('analyze-share-btn');
  if (shareBtn) {
    shareBtn.addEventListener('click', async () => {
      const url = window.location.href;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(url);
        } else {
          // Fallback for older browsers / insecure contexts
          const ta = document.createElement('textarea');
          ta.value = url;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
        }
        if (window.showToast) window.showToast(T('page.analyze.toast_link_copied', '链接已复制，可以分享给朋友'));
      } catch (err) {
        console.error('[analyze] copy failed:', err);
        if (window.showToast) window.showToast(T('page.analyze.toast_copy_failed_manual', '复制失败，请手动复制地址栏 URL'));
      }
    });
  }

  const favBtn = document.getElementById('analyze-fav-btn');
  if (!favBtn) return;

  const bId = getQueryParam('id');
  const q = getQueryParam('q');
  const aId = getQueryParam('a_id');

  // Build a fresh entry on every read; pulls a_name/b_name from window._analyzeMeta
  // (set when the SSE meta event arrives — may be null at click time if user is fast)
  const buildEntry = () => {
    const m = window._analyzeMeta;
    return {
      query: q || '',
      a_id: aId || (m && m.a && m.a.id) || null,
      b_id: bId || null,
      a_name: (m && m.a && m.a.name) || null,
      b_name: (m && m.b && m.b.name) || null,
      a_domain: (m && m.a && m.a.domain) || null,
      b_domain: (m && m.b && m.b.domain) || null,
      analyze_url: window.location.pathname + window.location.search,
      timestamp: Date.now(),
    };
  };

  const syncFavUi = () => {
    const active = window.isFavorited ? window.isFavorited(buildEntry()) : false;
    favBtn.classList.toggle('is-active', active);
    favBtn.setAttribute('aria-pressed', active ? 'true' : 'false');
    const icon = document.getElementById('analyze-fav-icon');
    const label = document.getElementById('analyze-fav-label');
    if (icon) icon.textContent = active ? '★' : '☆';
    if (label) label.textContent = active ? T('page.analyze.fav_active', '已收藏') : T('page.analyze.btn_fav', '收藏');
  };

  syncFavUi();

  favBtn.addEventListener('click', () => {
    if (!window.toggleFavorite) return;
    const { favorited } = window.toggleFavorite(buildEntry());
    syncFavUi();
    if (window.updateFavBadge) window.updateFavBadge();
    if (window.showToast) {
      window.showToast(favorited ? T('page.analyze.toast_fav_added', '已添加到收藏') : T('page.analyze.toast_fav_removed', '已移出收藏'));
    }
  });

  // Hook for the meta event handler — refresh the stored entry with names
  // if the report is already favorited (so the homepage card shows a real title).
  window.refreshFavoriteWithMeta = (meta) => {
    if (!meta) return;
    const fresh = buildEntry();
    if (window.isFavorited && window.isFavorited(fresh) && window.upsertFavorite) {
      window.upsertFavorite(fresh);
    }
    syncFavUi();
  };
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  initAnalyzeActions();

  const bId = getQueryParam('id');
  const q = getQueryParam('q');
  const aId = getQueryParam('a_id');

  if (!bId) {
    window.location.href = '/';
    return;
  }

  const params = new URLSearchParams();
  params.set('b_id', bId);
  if (q) {
    params.set('text_a', q);
  } else if (aId) {
    params.set('a_id', aId);
  } else {
    // No context to analyze against — just send back to phenomenon detail
    window.location.href = `/phenomenon/${encodeURIComponent(bId)}`;
    return;
  }

  streamAnalysis(params);
});

// Re-render header + progress + revealed sections when language toggles.
// Pending / streaming sections keep their placeholder (T() is resolved on paint).
try {
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(function () {
      try {
        // Header
        if (window._analyzeMeta) renderHeader(window._analyzeMeta);
        // Progress rail labels
        var rail = document.getElementById('analyze-progress');
        if (rail) {
          rail.querySelectorAll('.analyze-progress__item').forEach(function (el) {
            var k = el.dataset.key;
            var sec = SECTIONS.find(function (s) { return s.key === k; });
            if (sec) el.textContent = sectionLabel(sec);
          });
        }
        // Section titles
        document.querySelectorAll('.section').forEach(function (el) {
          var k = el.dataset.key;
          var sec = SECTIONS.find(function (s) { return s.key === k; });
          if (!sec) return;
          var titleEl = el.querySelector('.section__title');
          if (titleEl) titleEl.textContent = sectionLabel(sec);
          // Re-render already-revealed bodies so sub-headings pick up new lang.
          if (el.classList.contains('section--revealed') && window._finalReport && window._finalReport[k]) {
            var body = el.querySelector('.section__body');
            var renderer = renderers[k];
            if (body && renderer) {
              var html = renderer(window._finalReport[k]);
              if (html) {
                body.innerHTML = html;
                if (window.renderMath) window.renderMath(body);
              }
            }
          }
        });
        // Favorite button label
        var favLabel = document.getElementById('analyze-fav-label');
        if (favLabel) {
          var active = favLabel.parentElement && favLabel.parentElement.classList.contains('is-active');
          favLabel.textContent = active
            ? T('page.analyze.fav_active', '已收藏')
            : T('page.analyze.btn_fav', '收藏');
        }
      } catch (e) { console.warn('[analyze] onChange re-render failed:', e); }
    });
  }
} catch (e) {}
