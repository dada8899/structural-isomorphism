function T(key, fallback) { try { if (window.i18n && typeof window.i18n.t === "function") { var v = window.i18n.t(key); if (v && v !== key) return v; } } catch(e) {} return fallback; }

/* W3-B: Plausible event wrapper — safe when plausible.js is missing
   (privacy mode / ad-blocker / region block). Telemetry must not throw. */
function trackPlausible(event, props) {
  try {
    if (typeof window.plausible === 'function') {
      window.plausible(event, props ? { props: props } : undefined);
    }
  } catch (e) {}
}

// Page-level t0 for "time to first useful card" metric — set once on load.
var _analyzePageT0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
var _tldrShownLogged = false;

/**
 * Structural — Deep Analysis Report page
 *
 * Streams an 8-section research report via SSE and renders it section by section.
 */

// Display order: answer-first. action_plan + borrowable_insights at top, then
// shared_structure (the formal-math intro) and the rest of the theory. Backend
// SSE still emits sections in its prompt order (shared_structure first,
// action_plan last); the TL;DR pinned card at the very top fills in as soon
// as action_plan arrives so the user has the "answer" even before scrolling.
// SESSION-17 V5: `risks_and_limits`（迁移风险）moved up to §3 — right after
// the answer (action_plan / borrowable_insights). The migration-risk section
// is the hardest part for a generic LLM to replicate; it must not be buried
// at §9. Backend SSE emit order is unchanged (see STREAM_ORDER) — only the
// display order shifts.
const SECTIONS = [
  { key: 'action_plan', label: '本周行动', label_key: 'page.analyze.section_action_plan', num: '§1' },
  { key: 'borrowable_insights', label: '可借用的工具', label_key: 'page.analyze.section_borrowable_insights', num: '§2' },
  { key: 'risks_and_limits', label: '借用时的坑', label_key: 'page.analyze.section_risks_and_limits', num: '§3' },
  { key: 'shared_structure', label: '共享结构', label_key: 'page.analyze.section_shared_structure', num: '§4' },
  { key: 'your_problem_breakdown', label: '你的问题拆解', label_key: 'page.analyze.section_your_problem_breakdown', num: '§5' },
  { key: 'target_domain_intro', label: '那个领域是怎么回事', label_key: 'page.analyze.section_target_domain_intro', num: '§6' },
  { key: 'structural_mapping', label: '两个问题逐项对照', label_key: 'page.analyze.section_structural_mapping', num: '§7' },
  { key: 'how_to_combine', label: '怎么结合', label_key: 'page.analyze.section_how_to_combine', num: '§8' },
  { key: 'research_directions', label: '研究方向', label_key: 'page.analyze.section_research_directions', num: '§9' },
];

// The order backend SSE actually emits sections in (matches the LLM prompt's
// JSON schema order). Used to pick which still-pending section to mark as
// "正在生成" — without this we'd jump around the page randomly.
const STREAM_ORDER = [
  'shared_structure',
  'your_problem_breakdown',
  'target_domain_intro',
  'structural_mapping',
  'borrowable_insights',
  'how_to_combine',
  'research_directions',
  'risks_and_limits',
  'action_plan',
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

    // SESSION-17 V5: Rank-0 verification action. Before executing any
    // cross-domain migration, the user should first self-check whether the
    // analogy even holds. This is pinned ABOVE the full plan as "Rank 0" —
    // the engine isn't changed; this is a fixed, honest pre-flight step.
    // Concrete check items are pulled from the report's own
    // how_to_combine.assumptions_to_verify when available, otherwise a
    // generic "does the structural mapping survive contact with reality" prompt.
    const renderRankZero = () => {
      const report = window._finalReport || {};
      const combine = report.how_to_combine || {};
      const assumptions = Array.isArray(combine.assumptions_to_verify)
        ? combine.assumptions_to_verify.slice(0, 3) : [];
      const mapping = report.structural_mapping || {};
      const pairs = Array.isArray(mapping.parameter_map) ? mapping.parameter_map : [];
      const checks = assumptions.length > 0
        ? assumptions
        : (pairs.length > 0
            ? [T('page.analyze.rank0_check_mapping', '逐项核对上面「两个问题逐项对照」里的每一对——有没有哪一对其实是牵强的')]
            : [T('page.analyze.rank0_check_generic', '问自己：这个类比里最容易不成立的一环是什么？先验证它')]);
      return `
        <li class="action-item action-item--rank0">
          <div class="action-item__header">
            <span class="action-item__rank action-item__rank--zero">0</span>
            <h3 class="action-item__title">${T('page.analyze.rank0_title', '先自检：这个类比成不成立')}</h3>
            <span class="action-item__time">${T('page.analyze.rank0_time', '15–30 分钟')}</span>
          </div>
          <p class="action-item__rank0-why">${T('page.analyze.rank0_why', '下面的迁移动作全部建立在「你的问题和那个领域结构相同」这个假设上。先花半小时验证它再执行——类比一旦不成立，后面做得越多越偏。')}</p>
          <div class="action-item__row">
            <span class="action-item__row-label">${T('page.analyze.rank0_how_label', '怎么验证')}</span>
            <ul class="action-item__rank0-checks">
              ${checks.map(c => `<li>${md(c)}</li>`).join('')}
            </ul>
          </div>
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

      ${(items.length > 0 || ifShort) ? `
        <h3 class="section__subtitle">${T('page.analyze.action_full_plan', '本周完整计划')}</h3>
        <ol class="action-list">
          ${renderRankZero()}
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
      // W3-B: user clicked the progress nav to jump to / expand a section.
      trackPlausible('analyze_section_expanded', { section_name: btn.dataset.key || 'unknown' });
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

// === Core insight card (SESSION-17 V1 + V4) ===
// Lives above the section list. The single most valuable thing on the page:
//   1. one counter-intuitive insight  (shared_structure.intuition)
//   2. three things to do right now   (action_plan.this_week, top 3)
//   3. a credibility badge            (meta.credibility — V4)
// The 9 sections below it default to a quieter, secondary role.
// Reused verbatim by the saved/shared report page (report.js).

// Map a similarity score [0,1] into a calm confidence tier.
function credibilityTier(sim) {
  const s = typeof sim === 'number' ? sim : 0;
  if (s >= 0.55) return { label: T('page.analyze.cred_high', '高匹配置信度'), cls: 'cred--high' };
  if (s >= 0.38) return { label: T('page.analyze.cred_mid', '中等匹配置信度'), cls: 'cred--mid' };
  return { label: T('page.analyze.cred_low', '匹配置信度偏低'), cls: 'cred--low' };
}

// Build the V4 credibility badge from meta.credibility — REAL fields only.
// Never invents numbers; if a field is missing, that line is simply omitted.
function renderCredibilityBadge(credibility) {
  const c = credibility || {};
  // B Data Flywheel closure — real human-verification count. `human_verified_count`
  // may be absent on older persisted reports → Number() coerces undefined to NaN,
  // so we guard with a finite check and only show the badge when > 0 (never
  // displays "0 人验证" — absence of a badge is the honest zero state).
  const hvCount = Number(c.human_verified_count);
  const hasHuman = Number.isFinite(hvCount) && hvCount > 0;
  if (typeof c.similarity !== 'number' && !c.has_verified_pairs && !hasHuman) return '';
  const parts = [];
  if (hasHuman) {
    parts.push(`
      <span class="cred-badge__chip cred-badge__chip--human">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
        <span>${T('page.analyze.cred_human', '✓ {n} 人验证这个跨域迁移真的有效').replace('{n}', hvCount)}</span>
      </span>`);
  }
  if (typeof c.similarity === 'number') {
    const tier = credibilityTier(c.similarity);
    const pct = Math.round(Math.max(0, Math.min(1, c.similarity)) * 100);
    parts.push(`
      <span class="cred-badge__chip ${tier.cls}">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
        <span>${tier.label} · ${pct}%</span>
      </span>`);
  }
  if (c.has_verified_pairs && c.verified_pair_count > 0) {
    const n = c.verified_pair_count;
    parts.push(`
      <span class="cred-badge__chip cred-badge__chip--verified">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
        <span>${T('page.analyze.cred_verified', '这个跨域映射有 {n} 个经 AI 评审验证过的同构对').replace('{n}', n)}</span>
      </span>`);
  }
  if (!parts.length) return '';
  return `<div class="cred-badge">${parts.join('')}</div>`;
}

function renderTldrCard() {
  const el = document.getElementById('analyze-tldr');
  if (!el) return;
  const r = window._finalReport || {};
  const action = r.action_plan || {};
  const ifShort = action.if_time_short;
  const struct = r.shared_structure || {};
  const items = Array.isArray(action.this_week) ? action.this_week : [];
  const meta = window._analyzeMeta || {};
  const credibility = meta.credibility || null;

  // The counter-intuitive insight: prefer shared_structure.intuition; if that
  // isn't in yet, fall back to the "if you only do one thing" rationale.
  const insightText = struct.intuition || (ifShort && ifShort.rationale) || '';

  // Don't show the card until we have either the insight or the action plan —
  // otherwise we'd flash an empty box right when the page loads.
  if (!insightText && !ifShort && items.length === 0) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  // W3-B: tldr_card_shown — fired exactly once per page, on the first
  // transition from hidden → visible.
  if (!_tldrShownLogged) {
    _tldrShownLogged = true;
    var _now = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    trackPlausible('tldr_card_shown', {
      time_to_first_section_ms: Math.round(_now - _analyzePageT0)
    });
  }

  const md = window.mdInline || ((s) => escapeHtml(s || ''));
  // "Pending" = the action plan hasn't streamed in yet.
  const isPending = items.length === 0 && !ifShort;
  el.classList.toggle('analyze-tldr--pending', isPending);

  // --- 1. counter-intuitive insight ---
  const insightHtml = insightText
    ? `<p class="analyze-tldr__insight">${md(insightText)}</p>`
    : `<div class="analyze-tldr__waiting">
         <span class="analyze-tldr__waiting-dot"></span>
         <span>${T('page.analyze.tldr_waiting', '核心洞察正在生成…')}</span>
       </div>`;

  // --- 2. three immediate actions (top 3 of this_week) ---
  let actionsHtml = '';
  const top3 = items.slice(0, 3);
  if (top3.length > 0) {
    actionsHtml = `
      <div class="analyze-tldr__actions">
        <div class="analyze-tldr__actions-label">${T('page.analyze.tldr_actions_label', '现在就能做的三件事')}</div>
        <ol class="analyze-tldr__actions-list">
          ${top3.map((it) => `<li>${md(it.title || '')}</li>`).join('')}
        </ol>
      </div>`;
  } else if (!isPending && ifShort) {
    // No this_week list but we have "if only one thing" — surface that.
    actionsHtml = `
      <div class="analyze-tldr__actions">
        <div class="analyze-tldr__actions-label">${T('page.analyze.tldr_one_action_label', '如果只做一件事')}</div>
        <ol class="analyze-tldr__actions-list">
          <li>${md(ifShort.title || '')}</li>
        </ol>
      </div>`;
  } else if (isPending) {
    actionsHtml = `
      <div class="analyze-tldr__actions analyze-tldr__actions--pending">
        <div class="analyze-tldr__actions-label">${T('page.analyze.tldr_actions_label', '现在就能做的三件事')}</div>
        <div class="analyze-tldr__waiting">
          <span class="analyze-tldr__waiting-dot"></span>
          <span>${T('page.analyze.tldr_actions_waiting', '本周行动正在生成…')}</span>
        </div>
      </div>`;
  }

  // --- 3. credibility badge (V4) ---
  const badgeHtml = renderCredibilityBadge(credibility);

  const moreHtml = items.length
    ? `<a href="#section-action_plan" class="analyze-tldr__more">${T('page.analyze.tldr_more', '完整 {n} 步清单').replace('{n}', items.length)} ↓</a>`
    : '';

  el.innerHTML = `
    <div class="analyze-tldr__label">${T('page.analyze.tldr_label', '核心洞察')}</div>
    ${insightHtml}
    ${actionsHtml}
    ${badgeHtml}
    ${moreHtml}
  `;
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
    lineEl.textContent = T('page.analyze.loading_progress_line', '已生成 {chars} 字 · AI 正在写研究报告').replace('{chars}', chars);
  }
}

// === Live typewriter preview of the stream (last ~280 chars) ===
// Backend already streams `chunk.content` (delta text) inside each `text`
// SSE event. We accumulate it and paint the tail as a "what's being written
// right now" preview so the user sees motion instead of just a char counter.
let _streamBuffer = '';
function appendStreamContent(delta) {
  if (!delta) return;
  _streamBuffer += String(delta);
  // Keep memory bounded
  if (_streamBuffer.length > 5000) {
    _streamBuffer = _streamBuffer.slice(-5000);
  }
  const loading = $('#analyze-loading');
  if (!loading) return;
  let previewEl = loading.querySelector('.analyze-loading__stream-preview');
  if (!previewEl) {
    previewEl = document.createElement('div');
    previewEl.className = 'analyze-loading__stream-preview';
    loading.appendChild(previewEl);
  }
  // Show last ~280 chars; strip JSON syntax for legibility
  let tail = _streamBuffer.slice(-280);
  tail = tail
    .replace(/[{}"\[\]]+/g, ' ')
    .replace(/\\n/g, ' ')
    .replace(/\\"/g, '')
    .replace(/[,:]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  previewEl.textContent = tail || '...';
}
function clearStreamPreview() {
  _streamBuffer = '';
  const previewEl = $('#analyze-loading .analyze-loading__stream-preview');
  if (previewEl) previewEl.remove();
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

// =====================================================================
// Session #16 M1.4 — share-bar + feedback wiring
// =====================================================================

function renderShareBar(persistedPayload) {
  const bar = document.getElementById('analyze-share-bar');
  if (!bar || !persistedPayload || !persistedPayload.share_url) return;
  const urlInput = document.getElementById('analyze-share-url');
  if (urlInput) urlInput.value = persistedPayload.share_url;
  const partial = document.getElementById('analyze-share-bar__partial');
  if (partial) {
    partial.hidden = !persistedPayload.is_partial;
  }
  bar.hidden = false;
  // Wire copy + open buttons (idempotent — fine to bind multiple times,
  // but we guard with a data flag).
  const copyBtn = document.getElementById('analyze-share-copy');
  if (copyBtn && !copyBtn.dataset.wired) {
    copyBtn.dataset.wired = '1';
    copyBtn.addEventListener('click', () => {
      const url = (urlInput && urlInput.value) || '';
      if (!url) return;
      const done = () => {
        const orig = copyBtn.textContent;
        copyBtn.textContent = T('page.analyze.share_copied', '已复制');
        setTimeout(() => { copyBtn.textContent = orig; }, 1500);
        trackPlausible('Report Share Clicked', { via: 'copy' });
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done).catch(() => {
          // Fallback: select + execCommand
          urlInput.select();
          try { document.execCommand('copy'); done(); } catch (e) {}
        });
      } else {
        urlInput.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
      }
    });
  }
  const openBtn = document.getElementById('analyze-share-open');
  if (openBtn && !openBtn.dataset.wired) {
    openBtn.dataset.wired = '1';
    openBtn.addEventListener('click', () => {
      const url = (urlInput && urlInput.value) || '';
      if (url) {
        trackPlausible('Report Share Clicked', { via: 'open' });
        window.open(url, '_blank', 'noopener');
      }
    });
  }
  // Wire overall feedback buttons.
  bar.querySelectorAll('.analyze-vote').forEach((btn) => {
    if (btn.dataset.wired) return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', () => submitFeedback(btn));
  });
}

function submitFeedback(btn) {
  const persisted = window._persistedReport;
  if (!persisted || !persisted.id) return;
  const section = btn.dataset.section || '';
  const vote = parseInt(btn.dataset.vote, 10);
  if (vote !== 1 && vote !== -1) return;
  // Optimistic UI — bump the counter immediately, roll back on error.
  const countEl = btn.querySelector('.analyze-vote__count');
  const prevCount = countEl ? parseInt(countEl.textContent, 10) || 0 : 0;
  if (countEl) countEl.textContent = String(prevCount + 1);
  btn.classList.add('analyze-vote--active');
  // Mark its opposite as inactive (flip semantics).
  const opposite = btn.parentElement.querySelector(
    '.analyze-vote' + (vote === 1 ? '--down' : '--up')
  );
  if (opposite) opposite.classList.remove('analyze-vote--active');

  let anonId = '';
  try { anonId = localStorage.getItem('anonId') || ''; } catch (e) {}
  fetch('/api/report/' + encodeURIComponent(persisted.id) + '/feedback', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Anon-Id': anonId,
    },
    body: JSON.stringify({
      section: section || null,
      vote: vote,
    }),
  })
    .then((r) => r.ok ? r.json() : Promise.reject('HTTP ' + r.status))
    .then((body) => {
      // The #analyze-vote-*-count spans are the OVERALL share-bar counters.
      // Only sync them for an overall vote — a section vote returns that
      // section's counts and must not overwrite the overall display.
      if (!section) {
        const up = document.getElementById('analyze-vote-up-count');
        const down = document.getElementById('analyze-vote-down-count');
        if (up) up.textContent = String(body.total_up || 0);
        if (down) down.textContent = String(body.total_down || 0);
      }
      trackPlausible('Report Feedback', {
        section: section || 'overall',
        vote: vote === 1 ? 'up' : 'down',
        is_partial: !!persisted.is_partial,
      });
    })
    .catch((err) => {
      console.warn('[analyze] feedback failed:', err);
      // Roll back optimistic counter.
      if (countEl) countEl.textContent = String(prevCount);
      btn.classList.remove('analyze-vote--active');
    });
}

// Expose so the share-page (report.js) can reuse the same submitFeedback.
window._m14_submitFeedback = submitFeedback;
window._m14_renderShareBar = renderShareBar;
// SESSION-17 V1: expose the core insight card renderer so report.js can
// render the same card on the saved/shared report page.
window.renderTldrCard = renderTldrCard;

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
    renderTldrCard(); // shows the "答案准备中" placeholder right away
    // Mark the first section in the backend's emit order as currently
    // streaming, not whatever is at the top of the display order.
    if (STREAM_ORDER.length > 0) {
      setStreamingSection(STREAM_ORDER[0]);
    }
    // Once meta lands, the page has 4 "still working" signals already (TL;DR
    // placeholder pulsing dot + section skeleton breathGlow + section title
    // pulsing dot + sticky progress nav). The big analyze-loading block is
    // redundant noise from here. HIDE it (display:none) but DON'T remove it
    // — the error and retry handlers repaint into this same element, so the
    // node must remain in the DOM. It gets fully removed once the first
    // section actually arrives (existing handler below).
    if (stopLoadingTimer) { stopLoadingTimer(); stopLoadingTimer = null; }
    const loading = $('#analyze-loading');
    if (loading) {
      loading.classList.add('analyze-loading--fading');
      // After the fade-out animation, hide via display:none. Stays in DOM.
      setTimeout(() => {
        if (loading.parentNode) loading.classList.add('analyze-loading--hidden');
      }, 400);
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

    // Advance the streaming marker to the next pending section. Use the
    // backend stream order (not display order) so the highlight follows what
    // is actually being generated.
    const nextKey = STREAM_ORDER.find(k => !receivedKeys.has(k));
    if (nextKey) {
      setStreamingSection(nextKey);
    }
    updateProgressState(receivedKeys, nextKey);
    // Refresh the TL;DR pinned card as new sections land
    renderTldrCard();
  });

  es.addEventListener('text', (e) => {
    const chunk = JSON.parse(e.data);
    // Update loading progress line (before the first section arrives)
    if (!firstSectionSeen) {
      updateLoadingProgress(chunk.total_length || 0);
    }
    // Typewriter preview: paint the latest delta into a live "正在写" pane
    if (chunk.content) {
      appendStreamContent(chunk.content);
    }
  });

  // Session #16 M1.4 — handles the new `persisted` SSE event emitted
  // when persist=1. Payload: {id, share_token, share_url, created_at,
  // is_partial}. We stash the id (for feedback POSTs) and render the
  // sticky share-bar.
  es.addEventListener('persisted', (e) => {
    try {
      const payload = JSON.parse(e.data);
      window._persistedReport = payload;
      renderShareBar(payload);
      renderDecisionBrief({
        reportId: payload.id,
        createdAt: payload.created_at,
        partial: payload.is_partial,
        allowExperiment: true,
      });
      trackPlausible('Report Persisted', { is_partial: !!payload.is_partial });
    } catch (err) {
      console.warn('[analyze] persisted parse error:', err);
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
    renderTldrCard();
    renderDecisionBrief();
    es.close();
  });

  // Backend may emit a `retry` event when the first generation attempt fails
  // and it is about to try again. Show a soft hint in the loading block.
  es.addEventListener('retry', (e) => {
    console.warn('[analyze] retry event:', e && e.data);
    // Make sure the loading block is visible again — meta-arrival path has
    // hidden it via .analyze-loading--hidden, but a retry warrants surfacing
    // the message there.
    const loadingBlock = $('#analyze-loading');
    if (loadingBlock) {
      loadingBlock.classList.remove('analyze-loading--hidden');
      loadingBlock.classList.remove('analyze-loading--fading');
    }
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
  // After meta arrives we hide the loading block via .analyze-loading--hidden
  // (display:none). An error event needs to bring it back so the user sees
  // the failure copy.
  loading.classList.remove('analyze-loading--hidden');
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
          <span class="analyze-loading__typical">${T('page.analyze.timer_typical', '约需 2–3 分钟 · 报告会分段逐步出现')}</span>
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

// Compact, evidence-bounded action surface. It only extracts fields already
// present in the report; absent evidence stays visibly unsupported.
function buildDecisionBriefModel(context) {
  const r = window._finalReport || {};
  const meta = window._analyzeMeta || {};
  const ctx = context || window._decisionBriefContext || {};
  const source = ctx.source || meta.a || {};
  const target = meta.b || {};
  const fingerprint = ctx.fingerprint || meta.fingerprint || r._fingerprint || null;
  const structure = r.shared_structure || {};
  const risks = Array.isArray(r.risks_and_limits) ? r.risks_and_limits : [];
  const plan = r.action_plan || {};
  const firstAction = (Array.isArray(plan.this_week) && plan.this_week[0]) || plan.if_time_short || {};
  return {
    problem: ctx.query || target.original_query || target.description || '',
    fingerprint, source, structure,
    mechanism: structure.intuition || structure.mechanism || structure.name || '',
    boundary: risks[0] ? [risks[0].risk_name, risks[0].explanation].filter(Boolean).join('：') : '',
    hypothesis: firstAction.verification || firstAction.rationale || firstAction.title || '',
    metric: firstAction.expected_impact || '',
    reportId: ctx.reportId || ((window._persistedReport || {}).id) || '',
    model: ctx.model || meta.model || '',
    promptVersion: ctx.promptVersion || meta.prompt_version || '',
    createdAt: ctx.createdAt || ((window._persistedReport || {}).created_at) || '',
    partial: !!(ctx.partial || ((window._persistedReport || {}).is_partial)),
    allowExperiment: ctx.allowExperiment !== false,
  };
}

function decisionBriefMarkdown(model) {
  const m = model || buildDecisionBriefModel();
  const unsupported = 'UNSUPPORTED — 当前报告没有这项证据';
  const safe = (value) => String(value || '').replace(/([\\`*_{}\[\]()<>#+\-.!|$^])/g, '\\$1').replace(/\r?\n/g, '\n> ');
  const fp = m.fingerprint || {};
  const sourceName = safe([m.source.domain, m.source.name].filter(Boolean).join(' · ')) || unsupported;
  return [
    '# Structural · 决策简报', '',
    '> 状态：内部决策草稿；检索到的结构线索尚未构成机制验证。', '',
    '## 问题', safe(m.problem) || unsupported, '',
    '## 经用户确认的结构指纹', safe(fp.summary) || unsupported, '',
    '## 选中候选', sourceName, '',
    '## 可能共享的机制', safe(m.mechanism) || unsupported, '',
    '## 边界与优先反证', safe(m.boundary) || unsupported, '',
    '## 7 天最小实验',
    `- 假设：${safe(m.hypothesis) || unsupported}`,
    `- 核心指标：${safe(m.metric) || unsupported}`,
    '- 结论规则：只有记录真实结果后，才可将线索升级为已验证迁移。', '',
    '## 来源与版本',
    `- 报告 ID：${safe(m.reportId) || unsupported}`,
    `- 候选来源：${m.source.id ? `${window.location.origin}/phenomenon/${encodeURIComponent(m.source.id)}` : unsupported}`,
    `- 模型：${safe(m.model) || unsupported}`,
    `- Prompt：${safe(m.promptVersion) || unsupported}`,
    `- 生成时间：${safe(m.createdAt) || unsupported}`,
    `- 完整性：${m.partial ? 'PARTIAL — 报告未完整生成' : '完整报告（不等于机制已验证）'}`,
    '', '---', `来源页面：${safe(window.location.href)}`,
  ].join('\n');
}

function renderDecisionBrief(context) {
  const root = document.getElementById('decision-brief-root');
  if (!root || !window._finalReport || !Object.keys(window._finalReport).length) return;
  window._decisionBriefContext = { ...(window._decisionBriefContext || {}), ...(context || {}) };
  const m = buildDecisionBriefModel(window._decisionBriefContext);
  const unsupported = '<span class="decision-brief__unsupported">当前报告没有这项证据</span>';
  const value = (text) => text ? escapeHtml(text) : unsupported;
  const fp = m.fingerprint || {};
  const sourceName = [m.source.domain, m.source.name].filter(Boolean).join(' · ');
  const todayDate = new Date();
  const localDate = (date) => [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
  const today = localDate(todayDate);
  const deadlineDate = new Date(todayDate);
  deadlineDate.setDate(deadlineDate.getDate() + 7);
  const deadline = localDate(deadlineDate);
  const canCreate = !!(m.reportId && m.allowExperiment && fp.summary && m.source.id);
  root.innerHTML = `
    <section class="decision-brief" aria-labelledby="decision-brief-title">
      <p class="decision-brief__eyebrow">下一步 · 一页决策简报</p>
      <h2 class="decision-brief__title" id="decision-brief-title">先决定做什么，再读完整报告</h2>
      <p class="decision-brief__lede">把这份报告压缩成一个可反驳的 7 天实验。这里展示的是检索与分析线索，不是已经验证的机制。</p>
      <span class="decision-brief__status">内部决策草稿 · 未经实证验证</span>
      <div class="decision-brief__grid">
        <div class="decision-brief__item decision-brief__item--wide"><span class="decision-brief__label">你的问题</span><p class="decision-brief__value">${value(m.problem)}</p></div>
        <div class="decision-brief__item"><span class="decision-brief__label">经用户确认的结构指纹</span><p class="decision-brief__value">${value(fp.summary)}</p></div>
        <div class="decision-brief__item"><span class="decision-brief__label">选中候选</span><p class="decision-brief__value">${value(sourceName)}</p></div>
        <div class="decision-brief__item"><span class="decision-brief__label">可能共享的机制</span><p class="decision-brief__value">${value(m.mechanism)}</p></div>
        <div class="decision-brief__item"><span class="decision-brief__label">优先反证 / 适用边界</span><p class="decision-brief__value">${value(m.boundary)}</p></div>
        <div class="decision-brief__item decision-brief__item--wide"><span class="decision-brief__label">建议的 7 天实验</span><p class="decision-brief__value">${value(m.hypothesis)}</p></div>
      </div>
      <div class="decision-brief__actions">
        <button type="button" class="decision-brief__button" id="decision-brief-download">下载 .md</button>
        ${canCreate ? '<button type="button" class="decision-brief__button decision-brief__button--primary" id="decision-brief-create">创建 7 天实验</button>' : ''}
      </div>
      ${canCreate ? `<div class="decision-brief__experiment" id="decision-brief-experiment" hidden>
        <div class="decision-brief__form">
          <label class="decision-brief__field decision-brief__field--wide">可验证假设<textarea id="decision-brief-hypothesis" maxlength="2000" rows="2">${escapeHtml(m.hypothesis)}</textarea></label>
          <label class="decision-brief__field">截止日期<input id="decision-brief-deadline" type="date" min="${today}" max="${deadline}" value="${deadline}"></label>
          <label class="decision-brief__field">核心指标<input id="decision-brief-metric" maxlength="200" value="${escapeHtml(m.metric)}" placeholder="例如完成率"></label>
          <label class="decision-brief__field decision-brief__field--wide">停止条件<input id="decision-brief-stop" maxlength="1000" placeholder="何时停止或判定无效"></label>
        </div>
        <div class="decision-brief__actions" style="margin-top:12px"><button type="button" class="decision-brief__button decision-brief__button--primary" id="decision-brief-save">保存实验</button><span id="decision-brief-message" role="status" aria-live="polite"></span></div>
      </div>` : ''}
      <p class="decision-brief__meta">报告 ${escapeHtml(m.reportId || '未保存')} · 模型 ${escapeHtml(m.model || '未记录')} · Prompt ${escapeHtml(m.promptVersion || '未记录')} · ${m.partial ? 'PARTIAL' : '完整性以报告记录为准'}</p>
    </section>`;

  document.getElementById('decision-brief-download').addEventListener('click', () => {
    const blob = new Blob([decisionBriefMarkdown(m)], { type: 'text/markdown;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    const safeId = String(m.reportId || 'draft').replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 80) || 'draft';
    link.download = `structural-decision-brief-${safeId}.md`;
    document.body.appendChild(link); link.click(); link.remove();
    const objectUrl = link.href; setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  });
  if (!canCreate) return;
  document.getElementById('decision-brief-create').addEventListener('click', () => {
    document.getElementById('decision-brief-experiment').hidden = false;
    document.getElementById('decision-brief-hypothesis').focus();
  });
  document.getElementById('decision-brief-save').addEventListener('click', () => {
    const read = (id) => (document.getElementById(id).value || '').trim();
    const hypothesis = read('decision-brief-hypothesis');
    const message = document.getElementById('decision-brief-message');
    if (!hypothesis) { message.textContent = '请先写明可验证的假设'; document.getElementById('decision-brief-hypothesis').focus(); return; }
    const deadlineValue = read('decision-brief-deadline');
    const metric = read('decision-brief-metric');
    const stopCondition = read('decision-brief-stop');
    if (!deadlineValue) { message.textContent = '请选择实验截止日期'; document.getElementById('decision-brief-deadline').focus(); return; }
    if (deadlineValue < today || deadlineValue > deadline) { message.textContent = '截止日期需在今天至 7 天内'; document.getElementById('decision-brief-deadline').focus(); return; }
    if (!metric) { message.textContent = '请填写核心指标'; document.getElementById('decision-brief-metric').focus(); return; }
    if (!stopCondition) { message.textContent = '请填写停止条件，避免事后改写结论'; document.getElementById('decision-brief-stop').focus(); return; }
    const saveButton = document.getElementById('decision-brief-save');
    if (saveButton.disabled) return;
    saveButton.disabled = true;
    message.textContent = '保存中…';
    let anonId = ''; try { anonId = localStorage.getItem('anonId') || ''; } catch (_) {}
    fetch('/api/report/' + encodeURIComponent(m.reportId) + '/followup', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...(anonId ? { 'X-Anon-Id': anonId } : {}) },
      body: JSON.stringify({ action_status: 'planned', outcome: '', experiment: {
        hypothesis, status: 'planned', deadline: deadlineValue,
        primary_metric: metric, stop_condition: stopCondition,
      } }),
    }).then((res) => { if (!res.ok) throw new Error('HTTP ' + res.status); return res.json(); })
      .then(() => { message.textContent = '实验已保存；7 天后回来记录真实结果。'; trackPlausible('Decision Brief Experiment Created'); })
      .catch((err) => { saveButton.disabled = false; console.warn('[decision-brief] save failed:', err); message.textContent = '没保存成功，请检查报告所有权后重试。'; });
  });
}

window.buildDecisionBriefModel = buildDecisionBriefModel;
window.decisionBriefMarkdown = decisionBriefMarkdown;
window.renderDecisionBrief = renderDecisionBrief;

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
  // Session #16 M1.4 — report.html reuses this file for its section
  // renderers but does NOT want the analyze SSE boot to fire.
  if (window._suppressAnalyzeBoot) return;

  initHeaderScroll();
  initAnalyzeActions();

  const bId = getQueryParam('id');
  const q = getQueryParam('q');
  const aId = getQueryParam('a_id');

  if (!bId) {
    // SESSION-17 P2-4: don't silently bounce to "/". The "分析" nav item
    // can land here with no context — show a friendly empty state that
    // points the user back to the question box instead.
    const loadingEl = $('#analyze-loading');
    if (loadingEl) {
      loadingEl.innerHTML =
        '<h2 class="analyze-loading__title">从一个问题开始分析</h2>' +
        '<p class="analyze-loading__hint">在首页描述一个你卡住的复杂问题，' +
        'Structural 会为你生成一份跨领域研究报告。</p>' +
        '<p style="margin-top:20px"><a href="/" class="report-errorcard__cta">' +
        '回到首页，开始一个分析</a></p>';
    }
    return;
  }

  const params = new URLSearchParams();
  params.set('b_id', bId);
  if (q) {
    params.set('text_a', q);
    try {
      const rawFingerprint = sessionStorage.getItem('structural_pending_fingerprint');
      if (rawFingerprint) {
        const parsedFingerprint = JSON.parse(rawFingerprint);
        if (parsedFingerprint && parsedFingerprint.source_query === q) {
          params.set('fingerprint', rawFingerprint);
        }
        sessionStorage.removeItem('structural_pending_fingerprint');
      }
    } catch (e) {
      try { sessionStorage.removeItem('structural_pending_fingerprint'); } catch (_) {}
    }
  } else if (aId) {
    params.set('a_id', aId);
  } else {
    // No context to analyze against — just send back to phenomenon detail
    window.location.href = `/phenomenon/${encodeURIComponent(bId)}`;
    return;
  }

  // Persistence and capability-link creation require explicit opt-in.
  // Missing/invalid values remain private and never reach the report store.
  // anon_id is only attached when persistence was explicitly selected.
  const persistFlag = getQueryParam('persist');
  if (persistFlag === '1') {
    params.set('persist', '1');
    try {
      let anonId = localStorage.getItem('anonId');
      if (!anonId) {
        anonId = (window.crypto && window.crypto.randomUUID)
          ? window.crypto.randomUUID()
          : ('anon-' + Math.random().toString(36).slice(2) + '-' + Date.now().toString(36));
        localStorage.setItem('anonId', anonId);
      }
      params.set('anon_id', anonId);
    } catch (e) { /* localStorage may be blocked; skip silently */ }
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
        // TL;DR pinned card — re-render so labels and "完整 N 步清单" pick up new lang
        try { renderTldrCard(); } catch (e) {}
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
