function T(key, fallback) { try { if (window.i18n && typeof window.i18n.t === "function") { var v = window.i18n.t(key); if (v && v !== key) return v; } } catch(e) {} return fallback; }

var _tldrShownLogged = false;

/**
 * Structural — Deep Analysis Report page
 *
 * Receives a nine-section report envelope and renders it only after full validation.
 */

// Display order: answer-first. action_plan + borrowable_insights at top, then
// shared_structure (the formal-math intro) and the rest of the theory. Backend
// SSE still emits sections in its prompt order (shared_structure first,
// action_plan last). Those events update content-free progress only; the TL;DR
// and every section appear together after the complete envelope passes validation.
// SESSION-17 V5: `risks_and_limits`（迁移风险）moved up to §3 — right after
// the answer (action_plan / borrowable_insights). The migration-risk section
// is the hardest part for a generic LLM to replicate; it must not be buried
// at §9. Backend SSE emit order is unchanged (see STREAM_ORDER) — only the
// display order shifts.
const SECTIONS = [
  { key: 'action_plan', label: '本周行动', label_key: 'page.analyze.section_action_plan', num: '§1' },
  { key: 'borrowable_insights', label: '可借用的工具', label_key: 'page.analyze.section_borrowable_insights', num: '§2' },
  { key: 'risks_and_limits', label: '借用时的坑', label_key: 'page.analyze.section_risks_and_limits', num: '§3' },
  { key: 'shared_structure', label: '候选结构', label_key: 'page.analyze.section_shared_structure', num: '§4' },
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

// === KaTeX rendering helpers ===
const ANALYZE_MATH_BACKGROUND_DELAY_MS = 8000;
const ANALYZE_MATH_ASSETS = Object.freeze([
  Object.freeze({
    id: 'style', tag: 'link',
    url: '/assets/vendor/katex/katex.min.css?v=0.16.11',
  }),
  Object.freeze({
    id: 'core', tag: 'script',
    url: '/assets/vendor/katex/katex.min.js?v=0.16.11',
    ready: () => typeof window.katex?.renderToString === 'function',
  }),
  Object.freeze({
    id: 'auto-render', tag: 'script',
    url: '/assets/vendor/katex/contrib/auto-render.min.js?v=0.16.11',
    ready: () => typeof window.renderMathInElement === 'function',
  }),
]);
let _analyzeMathRuntimePromise = null;
let _analyzeMathBackgroundTimer = null;

function analyzeMathRuntimeReady() {
  return ANALYZE_MATH_ASSETS.slice(1).every(asset => asset.ready());
}

function analyzeMathAssetHref(asset) {
  const origin = new URL(window.location.href).origin;
  const resolved = new URL(asset.url, `${origin}/`);
  if (resolved.origin !== origin || `${resolved.pathname}${resolved.search}` !== asset.url) {
    throw new Error('Analyze math asset URL is not same-origin');
  }
  return resolved.href;
}

function loadAnalyzeMathAsset(asset) {
  if (asset.ready && asset.ready()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const selector = `[data-analyze-math-asset="${asset.id}"]`;
    let node = document.querySelector(selector);
    let created = false;
    const loaded = () => {
      node.dataset.analyzeMathState = 'loaded';
      if (asset.ready && !asset.ready()) {
        reject(new Error('Analyze math runtime did not initialize'));
        return;
      }
      resolve();
    };
    const failed = () => {
      node.dataset.analyzeMathState = 'failed';
      reject(new Error('Analyze math asset failed to load'));
    };
    if (node) {
      if (node.dataset.analyzeMathState === 'loaded') {
        loaded();
        return;
      }
      if (node.dataset.analyzeMathState === 'failed') {
        failed();
        return;
      }
    } else {
      node = document.createElement(asset.tag);
      created = true;
      node.dataset.analyzeMathAsset = asset.id;
      if (asset.tag === 'link') {
        node.rel = 'stylesheet';
        node.href = analyzeMathAssetHref(asset);
      } else {
        node.src = analyzeMathAssetHref(asset);
        node.async = true;
      }
    }
    node.addEventListener('load', loaded, { once: true });
    node.addEventListener('error', failed, { once: true });
    if (created) document.head.appendChild(node);
  });
}

function renderKatexHtml(latex, displayMode) {
  if (!latex || typeof window.katex?.renderToString !== 'function') return null;
  try {
    return window.katex.renderToString(latex, {
      throwOnError: false,
      displayMode,
      errorColor: 'var(--text-tertiary)',
      strict: false,
      trust: false,
      maxSize: 10,
      maxExpand: 1000,
      output: 'html',
    });
  } catch (_) {
    return null;
  }
}

function renderFormula(latex) {
  const html = renderKatexHtml(latex, true);
  if (html === null) {
    return `<div class="structure-block__formula">${escapeHtml(latex || '')}</div>`;
  }
  return `<div class="structure-block__formula structure-block__formula--rendered">${html}</div>`;
}

function renderInlineMath(latex) {
  const html = renderKatexHtml(latex, false);
  return html === null ? escapeHtml(latex || '') : html;
}

function enhanceAnalyzeMath(root) {
  if (!root || !analyzeMathRuntimeReady()) return false;
  root.querySelectorAll(
    '.structure-block__formula:not(.structure-block__formula--rendered)'
  ).forEach((node) => {
    const latex = node.textContent || '';
    if (!latex || latex.length > 500) return;
    const html = renderKatexHtml(latex, true);
    if (html === null) return;
    node.innerHTML = html;
    node.classList.add('structure-block__formula--rendered');
  });
  if (typeof window.renderMath === 'function') window.renderMath(root);
  return true;
}

function requestAnalyzeMathRuntime() {
  if (_analyzeMathRuntimePromise) return _analyzeMathRuntimePromise;
  _analyzeMathRuntimePromise = ANALYZE_MATH_ASSETS.reduce(
    (chain, asset) => chain.then(() => loadAnalyzeMathAsset(asset)),
    Promise.resolve()
  ).then(() => {
    if (!analyzeMathRuntimeReady()) throw new Error('Analyze math runtime is incomplete');
    enhanceAnalyzeMath(document.getElementById('analyze-sections'));
    return true;
  }).catch(() => {
    console.warn('[analyze] optional math rendering unavailable');
    return false;
  });
  return _analyzeMathRuntimePromise;
}

function scheduleAnalyzeMathRuntime() {
  if (_analyzeMathRuntimePromise || _analyzeMathBackgroundTimer !== null) return;
  _analyzeMathBackgroundTimer = setTimeout(() => {
    _analyzeMathBackgroundTimer = null;
    requestAnalyzeMathRuntime();
  }, ANALYZE_MATH_BACKGROUND_DELAY_MS);
}

// Use the global renderMath from utils.js

// === Section renderers ===
const renderers = {
  shared_structure(data) {
    if (!data) return '';
    const observations = data.observations || [];
    const competitors = data.competing_explanations || [];
    const gaps = data.evidence_gaps || [];
    const failures = data.failure_conditions || [];
    return `
      <div class="structure-block">
        <div class="research-status research-status--partial">${T('page.analyze.candidate_only', '候选类比 · 机制未验证')}</div>
        <div class="structure-block__name">${escapeHtml(data.name || '—')}</div>
        ${data.formal_expression ? renderFormula(data.formal_expression) : ''}
        ${data.intuition ? `<div class="structure-block__intuition">${escapeHtml(data.intuition)}</div>` : ''}
        ${observations.length ? `
          <h3 class="section__subtitle">${T('page.analyze.unverified_signals', '未验证的输入 / 来源线索')}</h3>
          <div class="research-status research-status--partial">${T('page.analyze.unverified_signals_notice', '这些文字仅是待核查线索；没有实验或独立复现支持，不能据此判断两边机制相同。')}</div>
          <ul>${observations.map(item => `
            <li>
              <strong>${escapeHtml(item.signal_to_check || '')}</strong>
              <div>${escapeHtml(item.candidate_implication || '')}</div>
            </li>
          `).join('')}</ul>
        ` : ''}
        ${competitors.length ? `<h3 class="section__subtitle">${T('page.analyze.competing_explanations', '竞争解释')}</h3><ul>${competitors.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}
        ${gaps.length ? `<h3 class="section__subtitle">${T('page.analyze.evidence_gaps', '证据缺口')}</h3><ul>${gaps.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}
        ${failures.length ? `<h3 class="section__subtitle">${T('page.analyze.failure_conditions', '什么情况下应否定')}</h3><ul>${failures.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}
      </div>
    `;
  },

  your_problem_breakdown(data) {
    if (!data) return '';
    const vars = data.key_variables || [];
    const uncertain = data.uncertain_points || [];
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
      ${uncertain.length ? `
        <h3 class="section__subtitle">${T('page.analyze.uncertain_points', '仍待确认')}</h3>
        <ul>${uncertain.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
      ` : ''}
    `;
  },

  target_domain_intro(data) {
    if (!data) return '';
    const phenom = data.corresponding_phenomenon || {};
    const methods = data.candidate_methods || [];
    const limitations = data.source_limitations || [];
    return `
      <h3 class="section__subtitle">${escapeHtml(data.domain_name || T('page.analyze.sub_source_domain', '源领域'))}</h3>
      ${data.what_record_says ? `<p>${escapeHtml(data.what_record_says)}</p>` : ''}

      ${phenom.name ? `
        <h3 class="section__subtitle">${T('page.analyze.sub_corresponding_phenomenon', '这个领域里的对应现象')}：${escapeHtml(phenom.name)}</h3>
        ${phenom.plain_description ? `<p>${escapeHtml(phenom.plain_description)}</p>` : ''}
      ` : ''}

      ${methods.length > 0 ? `
        <h3 class="section__subtitle">${T('page.analyze.candidate_methods', '模型提出的方法候选')}</h3>
        <div class="callout callout--warning">
          <div class="callout__label">${T('page.analyze.proposal_unverified', '模型提出 · 来源未支持 · 待核查')}</div>
          <div class="callout__text">${T('page.analyze.candidate_methods_notice', '以下方法不是来源记录中的既有结论，使用前需要另行核查。')}</div>
        </div>
        <div class="tools-list">
          ${methods.map(method => `
            <div class="tool">
              <div class="tool__name">${escapeHtml(method.name || '')}</div>
              <div class="tool__brief"><strong>${T('page.analyze.why_considered', '为什么值得考虑')}：</strong>${escapeHtml(method.why_considered || '')}</div>
              <div class="tool__brief"><strong>${T('page.analyze.source_support', '来源支持')}：</strong>${T('page.analyze.source_support_not_recorded', '未记录')}</div>
              <div class="tool__brief"><strong>${T('page.analyze.evidence_required', '需要的证据')}：</strong>${escapeHtml(method.evidence_required || '')}</div>
            </div>
          `).join('')}
        </div>
      ` : ''}
      ${limitations.length ? `
        <div class="callout callout--warning">
          <div class="callout__label">${T('page.analyze.source_limitations', '来源边界')}</div>
          <ul>${limitations.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
        </div>
      ` : ''}
    `;
  },

  structural_mapping(data) {
    if (!data) return '';
    const params = data.parameter_map || [];
    const competitors = data.competing_explanations || [];
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
              ${p.mapping_hypothesis ? `<div class="param-row__reason"><strong>${T('page.analyze.mapping_hypothesis', '待验证对应')}：</strong>${escapeHtml(p.mapping_hypothesis)}</div>` : ''}
              ${(p.evidence_against || []).length ? `<div class="param-row__reason"><strong>${T('page.analyze.evidence_against', '当前反证 / 缺口')}：</strong>${(p.evidence_against || []).map(escapeHtml).join('；')}</div>` : ''}
              ${p.observable_test ? `<div class="param-row__reason"><strong>${T('page.analyze.observable_test', '可观测检验')}：</strong>${escapeHtml(p.observable_test)}</div>` : ''}
              ${p.failure_signal ? `<div class="param-row__reason"><strong>${T('page.analyze.failure_signal', '失败信号')}：</strong>${escapeHtml(p.failure_signal)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      ` : ''}
      ${competitors.length ? `
        <h3 class="section__subtitle">${T('page.analyze.competing_explanations', '竞争解释')}</h3>
        <ul>${competitors.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
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
        <div class="research-status research-status--partial">${T('page.analyze.proposal_unverified', '模型提出 · 来源未支持 · 待核查')}</div>
        ${ins.why_considered ? `
          <div class="insight__subsection">
            <span class="insight__subsection-label">${T('page.analyze.why_considered', '为什么值得考虑')}</span>
            <div class="insight__subsection-text">${md(ins.why_considered)}</div>
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
        ${(ins.prerequisites || []).length ? `
          <div class="insight__subsection">
            <span class="insight__subsection-label">${T('page.analyze.prerequisites', '前提条件')}</span>
            <div class="insight__subsection-text">${(ins.prerequisites || []).map(item => escapeHtml(item)).join('；')}</div>
          </div>
        ` : ''}
        ${ins.failure_signal ? `
          <div class="insight__subsection">
            <span class="insight__subsection-label">${T('page.analyze.failure_signal', '失败信号')}</span>
            <div class="insight__subsection-text">${escapeHtml(ins.failure_signal)}</div>
          </div>
        ` : ''}
      </div>
    `).join('');
  },

  how_to_combine(data) {
    if (!data) return '';
    const steps = data.steps || [];
    const assumptions = data.assumptions_to_verify || [];
    const boundaries = Array.isArray(data.boundary_conditions)
      ? data.boundary_conditions : (data.boundary_conditions ? [data.boundary_conditions] : []);
    const experiment = data.discriminating_experiment || null;
    const expectedOutcomes = experiment && Array.isArray(experiment.expected_outcomes)
      ? experiment.expected_outcomes : [];
    const competitorHypotheses = experiment && Array.isArray(experiment.competitor_hypotheses)
      ? experiment.competitor_hypotheses : [];
    const confounds = experiment && Array.isArray(experiment.confounds) ? experiment.confounds : [];
    const procedure = experiment && Array.isArray(experiment.procedure) ? experiment.procedure : [];
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

      ${boundaries.length ? `
        <div class="callout">
          <div class="callout__label">${T('page.analyze.sub_boundary_conditions', '边界条件')}</div>
          <ul>${boundaries.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
        </div>
      ` : ''}
      ${experiment ? `
        <h3 class="section__subtitle">${T('page.analyze.discriminating_experiment', '可区分实验')}</h3>
        <div class="callout">
          <div class="callout__label">${escapeHtml(experiment.question || '')}</div>
          <div class="callout__text"><strong>${T('page.analyze.candidate_hypothesis', '候选假设')}：</strong>${escapeHtml(experiment.candidate_hypothesis || '')}</div>
          ${competitorHypotheses.length ? `<div class="callout__text"><strong>${T('page.analyze.competitor_hypotheses', '竞争假设')}：</strong><ul>${competitorHypotheses.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>` : ''}
          <div class="callout__text"><strong>${T('page.analyze.intervention_or_measurement', '干预或测量')}：</strong>${escapeHtml(experiment.intervention_or_measurement || '')}</div>
          <div class="callout__text"><strong>${T('page.analyze.primary_outcome', '主要结果')}：</strong>${escapeHtml(experiment.primary_outcome || '')}</div>
          ${expectedOutcomes.length ? `<div class="callout__text"><strong>${T('page.analyze.expected_outcomes', '分假设预期')}：</strong><ul>${expectedOutcomes.map(item => {
            const role = item.role === 'candidate'
              ? T('page.analyze.role_candidate', '候选')
              : T('page.analyze.role_competitor', '竞争');
            return `<li><span class="research-status research-status--partial">${escapeHtml(role)}</span> <strong>${escapeHtml(item.hypothesis_id || '')}</strong>：${escapeHtml(item.expected_observation || '')}</li>`;
          }).join('')}</ul></div>` : ''}
          ${confounds.length ? `<div class="callout__text"><strong>${T('page.analyze.confounds', '混杂因素')}：</strong>${confounds.map(item => escapeHtml(item)).join('；')}</div>` : ''}
          <div class="callout__text"><strong>${T('page.analyze.minimum_data', '最低数据要求')}：</strong>${escapeHtml(experiment.minimum_data || '')}</div>
          ${procedure.length ? `<div class="callout__text"><strong>${T('page.analyze.procedure', '实验步骤')}：</strong><ol>${procedure.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ol></div>` : ''}
          <div class="callout__text"><strong>${T('page.analyze.decision_rule', '决策规则')}：</strong>${escapeHtml(experiment.decision_rule || '')}</div>
          <div class="callout__text"><strong>${T('page.analyze.falsification_rule', '证伪规则')}：</strong>${escapeHtml(experiment.falsification_rule || '')}</div>
          <div class="callout__text"><strong>${T('page.analyze.stop_rule', '停止规则')}：</strong>${escapeHtml(experiment.stop_rule || '')}</div>
          <div class="research-status research-status--partial">${T('page.analyze.threshold_proposal_calibration', '阈值依据：提案 · 必须校准后使用')}</div>
        </div>
      ` : ''}
    `;
  },

  research_directions(data) {
    if (!data) return '';
    const questions = data.search_questions || [];
    const sourceTypes = data.source_types_to_check || [];

    return `
      ${data.status_explanation ? `<p>${escapeHtml(data.status_explanation)}</p>` : ''}
      ${questions.length ? `<h3 class="section__subtitle">${T('page.analyze.search_questions', '下一步文献检索问题')}</h3><ul>${questions.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}
      ${sourceTypes.length ? `<p><strong>${T('page.analyze.source_types', '优先核查的来源类型')}：</strong>${sourceTypes.map(item => escapeHtml(item)).join('、')}</p>` : ''}
    `;
  },

  risks_and_limits(data) {
    if (!Array.isArray(data) || data.length === 0) return '';
    return `
      <div class="risks">
        ${data.map(r => {
          const severity = {
            high: {className: 'high', label: T('page.analyze.severity_high', '高')},
            medium: {className: 'medium', label: T('page.analyze.severity_medium', '中')},
            low: {className: 'low', label: T('page.analyze.severity_low', '低')},
          }[r.severity] || {className: 'low', label: T('page.analyze.severity_unknown', '未标注')};
          return `
            <div class="risk">
              <span class="risk__severity risk__severity--${severity.className}">${escapeHtml(severity.label)}</span>
              <div>
                <div class="risk__name">${escapeHtml(r.risk_name || '')}</div>
                <div class="risk__explain">${escapeHtml(r.explanation || '')}</div>
                ${r.condition ? `<div class="risk__explain"><strong>${T('page.analyze.risk_condition', '触发条件')}：</strong>${escapeHtml(r.condition)}</div>` : ''}
                ${r.observable_signal ? `<div class="risk__explain"><strong>${T('page.analyze.observable_signal', '可观测信号')}：</strong>${escapeHtml(r.observable_signal)}</div>` : ''}
                ${r.stop_rule ? `<div class="risk__explain"><strong>${T('page.analyze.stop_rule', '停止规则')}：</strong>${escapeHtml(r.stop_rule)}</div>` : ''}
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
    const followup = data.review_trigger;

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
      return `
        <li class="action-item action-item--core">
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
          ${it.primary_metric ? `
            <div class="action-item__row">
              <span class="action-item__row-label">${T('page.analyze.action_verification', '主要指标')}</span>
              <div class="action-item__row-text">${md(it.primary_metric)}</div>
            </div>
          ` : ''}
          ${it.decision_rule ? `
            <div class="action-item__row">
              <span class="action-item__row-label">${T('page.analyze.decision_rule', '决策规则')}</span>
              <div class="action-item__row-text">${md(it.decision_rule)}</div>
            </div>
          ` : ''}
          ${it.stop_condition ? `
            <div class="action-item__row">
              <span class="action-item__row-label">${T('page.analyze.stop_rule', '停止规则')}</span>
              <div class="action-item__row-text">${md(it.stop_condition)}</div>
            </div>
          ` : ''}
          <div class="action-item__row">
            <span class="action-item__row-label">${T('page.analyze.threshold_basis', '阈值依据')}</span>
            <div class="action-item__row-text">${T('page.analyze.threshold_proposal_calibration', '提案 · 必须校准后使用')}</div>
          </div>
          ${it.expected_information ? `
            <div class="action-item__row">
              <span class="action-item__row-label">${T('page.analyze.action_expected', '预期获得的信息')}</span>
              <div class="action-item__row-text">${md(it.expected_information)}</div>
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
            ? [T('page.analyze.rank0_check_mapping', '逐项核对每个候选对应，优先检验最容易失效的一项')]
            : [T('page.analyze.rank0_check_generic', '先找出这个候选类比最容易被否定的一环，再定义可观测检验')]);
      return `
        <li class="action-item action-item--rank0">
          <div class="action-item__header">
            <span class="action-item__rank action-item__rank--zero">0</span>
            <h3 class="action-item__title">${T('page.analyze.rank0_title', '先定义如何否定这个候选')}</h3>
            <span class="action-item__time">${T('page.analyze.rank0_time', '15–30 分钟')}</span>
          </div>
          <p class="action-item__rank0-why">${T('page.analyze.rank0_why', '当前只有候选映射，尚未完成机制层面的检验。在执行任何迁移动作前，先用数据区分它与竞争解释。')}</p>
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

// A report boundary is categorical provenance, never a confidence score.
function renderCredibilityBadge(boundary) {
  const b = boundary || {};
  if (b.conclusion_status !== 'candidate_analogy') return '';
  return `<div class="cred-badge">
    <span class="cred-badge__chip cred--mid">${T('page.analyze.candidate_only', '候选类比')}</span>
    <span class="cred-badge__chip">${T('page.analyze.mechanism_not_verified', '机制未验证')}</span>
    <span class="cred-badge__chip">${T('page.analyze.review_not_recorded', '未记录独立复核')}</span>
  </div>`;
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
  const boundary = r.report_boundary || meta.report_boundary || null;

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
  // Record the first transition locally so repeat renders stay idempotent.
  if (!_tldrShownLogged) {
    _tldrShownLogged = true;
  }

  const md = window.mdInline || ((s) => escapeHtml(s || ''));
  // "Pending" = the complete validated report has not been published yet.
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
  const badgeHtml = renderCredibilityBadge(boundary);

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
      <span>${T('page.analyze.header_inspect_candidate', '检查来自 {source} 的候选线索').replace('{source}', `<strong>${escapeHtml(a.domain)} · ${escapeHtml(a.name)}</strong>`)}</span>
      <svg class="analyze-header__bridge-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
      <span>${T('page.analyze.header_test_against', '在 {target} 中检验对应、反证和边界').replace('{target}', `<strong>${targetStrong}</strong>`)}</span>
    </div>
    ${window.StructuralEvidence ? window.StructuralEvidence.render(meta.evidence || window.StructuralEvidence.fallback(a), { compact: true, kbUrl: a.id ? '/phenomenon/' + encodeURIComponent(a.id) : '' }) : ''}
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

function clearStreamPreview() {
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
      <section class="section section--revealed" id="section-${s.key}" data-key="${s.key}" style="animation-delay: ${i * 150}ms">
        <div class="section__number">${s.num}</div>
        <h2 class="section__title">${escapeHtml(sectionLabel(s))}</h2>
        <div class="section__body">${html || '<p style="color:var(--text-tertiary)">—</p>'}</div>
      </section>
    `;
  }).join('');
  if (analyzeMathRuntimeReady()) enhanceAnalyzeMath(container);

  // Mark all progress items as done
  const allKeys = new Set(SECTIONS.map(s => s.key));
  updateProgress(null, allKeys);
}

// The backend releases section events only after the complete report passes
// schema, evidence and source validation. Keep one honest overall phase during
// generation; the nine section events are a protocol burst, not nine timers.

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
    })
    .catch((err) => {
      console.warn('[analyze] feedback failed');
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

function updateProgressState(receivedKeys) {
  $$('.analyze-progress__item').forEach(el => {
    const key = el.dataset.key;
    el.classList.toggle('done', receivedKeys.has(key));
    el.classList.remove('active');
  });
}

let _activeAnalyzeStream = null;
let _lastAnalyzePayload = null;
let _analyzeGeneration = 0;

const DEEP_REPORT_SECTION_KEYS = STREAM_ORDER.slice();

function analyzeGenerationMatches(expected, current) {
  return Number.isInteger(expected) && expected === current;
}

function isPlainObject(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function collectSourceRefIds(value, key, out) {
  if (Array.isArray(value)) {
    if (key === 'source_ref_ids') {
      value.forEach(item => { if (typeof item === 'string') out.add(item); });
    } else {
      value.forEach(item => collectSourceRefIds(item, key, out));
    }
    return;
  }
  if (!isPlainObject(value)) return;
  Object.keys(value).forEach(childKey => collectSourceRefIds(value[childKey], childKey, out));
}

const ANALYZE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const ANALYZE_REQUEST_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
const ANALYZE_SHA256_RE = /^[0-9a-f]{64}$/;
const ANALYZE_GENERATION_RE = /^g_[0-9a-f]{24}$/;
const ANALYZE_REPORT_ID_RE = /^r_[0-9a-f]{16}$/;
const ANALYZE_SHARE_TOKEN_RE = /^[0-9a-f]{32}$/;
const ANALYZE_CONTROL_RE = /[\p{Cc}\p{Cf}\p{Cs}]/u;
const ANALYZE_MAX_PUBLIC_CHARS = 24000;
const ANALYZE_MAX_CANONICAL_CHARS = 96000;
const ANALYZE_MAX_STREAM_BYTES = 512000;

function hasExactKeys(value, keys) {
  if (!isPlainObject(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = keys.slice().sort();
  return actual.length === expected.length &&
    actual.every((key, index) => key === expected[index]);
}

function hasOnlyKeys(value, allowed) {
  return isPlainObject(value) && Object.keys(value).every(key => allowed.includes(key));
}

function textWithin(value, minimum, maximum, allowEmpty = false) {
  if (typeof value !== 'string' || ANALYZE_CONTROL_RE.test(value)) return false;
  const length = Array.from(value).length;
  if (value !== value.trim() || length > maximum) return false;
  return allowEmpty ? length >= minimum : length >= Math.max(1, minimum);
}

function textList(value, minimum, maximum, textMaximum) {
  return Array.isArray(value) && value.length >= minimum && value.length <= maximum &&
    value.every(item => textWithin(item, 1, textMaximum));
}

function objectList(value, minimum, maximum, validator) {
  return Array.isArray(value) && value.length >= minimum && value.length <= maximum &&
    value.every(validator);
}

function strictInteger(value, minimum, maximum) {
  return Number.isSafeInteger(value) && value >= minimum && value <= maximum;
}

function deepEqualCanonical(left, right) {
  try { return canonicalAnalyzeJson(left) === canonicalAnalyzeJson(right); } catch (_) { return false; }
}

function canonicalAnalyzeJson(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') {
    return JSON.stringify(value);
  }
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new TypeError('non-canonical number');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalAnalyzeJson).join(',') + ']';
  }
  if (isPlainObject(value)) {
    return '{' + Object.keys(value).sort().map(key =>
      JSON.stringify(key) + ':' + canonicalAnalyzeJson(value[key])
    ).join(',') + '}';
  }
  throw new TypeError('value is not canonical JSON');
}

async function sha256CanonicalAnalyzeJson(value, cryptoImpl) {
  const provider = cryptoImpl || (typeof window !== 'undefined' && window.crypto);
  if (!provider || !provider.subtle || typeof provider.subtle.digest !== 'function' ||
      typeof TextEncoder === 'undefined') {
    throw new Error('WebCrypto SHA-256 is unavailable');
  }
  const canonical = canonicalAnalyzeJson(value);
  if (canonical.length > ANALYZE_MAX_CANONICAL_CHARS) {
    throw new Error('canonical report is too large');
  }
  const digest = await provider.subtle.digest('SHA-256', new TextEncoder().encode(canonical));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

function validateReportBoundary(value) {
  return hasExactKeys(value, [
    'conclusion_status', 'mechanism_status', 'independent_review', 'literature_status',
  ]) && value.conclusion_status === 'candidate_analogy' &&
    value.mechanism_status === 'not_verified' &&
    value.independent_review === 'not_recorded' &&
    value.literature_status === 'not_checked';
}

function validateSourceBinding(value) {
  if (!hasExactKeys(value, [
    'source_kb_id', 'source_record_sha256', 'kb_artifact_id', 'target_kind',
    'target_kb_id', 'query_binding', 'fingerprint_sha256', 'fingerprint_revision',
    'lang', 'model_id', 'prompt_version', 'schema_version',
  ]) || !ANALYZE_ID_RE.test(value.source_kb_id || '') ||
      !ANALYZE_SHA256_RE.test(value.source_record_sha256 || '') ||
      !textWithin(value.kb_artifact_id, 1, 120) ||
      !['query', 'kb'].includes(value.target_kind) ||
      !['zh', 'en'].includes(value.lang) || !textWithin(value.model_id, 1, 120) ||
      value.prompt_version !== 'deep-report-v2' ||
      value.schema_version !== 'deep-analysis-report-v2') return false;
  const fingerprintAbsent = value.fingerprint_sha256 === null && value.fingerprint_revision === null;
  const fingerprintPresent = ANALYZE_SHA256_RE.test(value.fingerprint_sha256 || '') &&
    strictInteger(value.fingerprint_revision, 1, 1000);
  if (!fingerprintAbsent && !fingerprintPresent) return false;
  if (value.target_kind === 'query') {
    return value.target_kb_id === null && ANALYZE_SHA256_RE.test(value.query_binding || '');
  }
  return ANALYZE_ID_RE.test(value.target_kb_id || '') && value.query_binding === null;
}

function validateSourceRefs(value) {
  if (!objectList(value, 1, 8, item => hasExactKeys(item, [
    'source_ref_id', 'source_kind', 'record_id', 'label', 'limitations',
  ]) && ANALYZE_ID_RE.test(item.source_ref_id || '') &&
    item.source_kind === 'internal_kb' && ANALYZE_ID_RE.test(item.record_id || '') &&
    textWithin(item.label, 1, 240) && textWithin(item.limitations, 1, 400))) return false;
  const sourceIds = value.map(item => item.source_ref_id);
  return new Set(sourceIds).size === sourceIds.length;
}

function validateCandidateObservation(value) {
  return hasExactKeys(value, ['signal_to_check', 'candidate_implication', 'status']) &&
    textWithin(value.signal_to_check, 1, 400) &&
    textWithin(value.candidate_implication, 1, 400) && value.status === 'not_checked';
}

function validateSharedStructure(value) {
  return hasExactKeys(value, [
    'status', 'name', 'formal_expression', 'intuition', 'observations',
    'competing_explanations', 'evidence_gaps', 'failure_conditions',
  ]) && value.status === 'candidate' && textWithin(value.name, 1, 120) &&
    textWithin(value.formal_expression, 1, 500) &&
    textWithin(value.intuition, 1, 700) &&
    objectList(value.observations, 1, 5, validateCandidateObservation) &&
    textList(value.competing_explanations, 1, 5, 400) &&
    textList(value.evidence_gaps, 1, 5, 400) &&
    textList(value.failure_conditions, 1, 5, 400);
}

function validateProblemVariable(value) {
  return hasExactKeys(value, ['name', 'description', 'role']) &&
    textWithin(value.name, 1, 80) && textWithin(value.description, 1, 400) &&
    ['state', 'parameter', 'input', 'constraint', 'output'].includes(value.role);
}

function validateProblemBreakdown(value) {
  return hasExactKeys(value, [
    'summary', 'key_variables', 'dynamics', 'why_stuck',
    'fingerprint_revision', 'uncertain_points',
  ]) && textWithin(value.summary, 1, 1200) &&
    objectList(value.key_variables, 1, 8, validateProblemVariable) &&
    textWithin(value.dynamics, 1, 700) && textWithin(value.why_stuck, 1, 700) &&
    (value.fingerprint_revision === null || strictInteger(value.fingerprint_revision, 1, 1000)) &&
    textList(value.uncertain_points, 1, 5, 400);
}

function validateCorrespondingPhenomenon(value) {
  return hasExactKeys(value, ['name', 'plain_description', 'source_ref_ids']) &&
    textWithin(value.name, 1, 120) && textWithin(value.plain_description, 1, 1200) &&
    Array.isArray(value.source_ref_ids) && value.source_ref_ids.length >= 1 &&
    value.source_ref_ids.length <= 3 && value.source_ref_ids.every(id => ANALYZE_ID_RE.test(id));
}

const ANALYZE_UNSUPPORTED_SOURCE_ATTRIBUTION = /(?:\b(?:uses?|used|using|deploys?|deployed|adopts?|adopted|implements?|implemented|develop(?:s|ed)?|introduce[sd]?|publish(?:es|ed)?|demonstrat(?:e|es|ed)|prove[sd]?|according\s+to|says?|states?|reports?|indicates?|describes?|notes?|claims?|asserts?|mentions?)\b|(?:使用|采用|部署|应用|提出|开发|发表|证明|研究表明|数据显示|指出|声称|报告|显示|描述|说明|提及))/i;
const ANALYZE_NEGATED_COMPLETION_PREFIX = /(?:\b(?:(?:has|have|had|is|are|was|were|do|does|did|can|could|will|would|should|must)\s+not(?:\s+been|\s+be)?(?:\s+(?:empirically|independently|externally|formally))?|not|never|without)\s*$|\b(?:do|does|did)\s+not\s+(?:find|show|support|confirm|validate|verify)\b[^,.!?，。！？；;]{0,24}$|\bno\s+(?:evidence|study|data|result)s?\b[^,.!?，。！？；;]{0,24}$|(?:尚未|尚无|未经|未|没有|并未|不曾|无法|不能)(?:被|能|能够|可以|足以|完成|进行|得到)?\s*$|(?:尚未|未|没有)记录[^,.!?，。！？；;]{0,8}$|(?:未|没有|并未)(?:发现|表明|显示|支持|确认|验证)[^,.!?，。！？；;]{0,20}$|(?:没有|无)(?:证据|研究|数据|结果)[^,.!?，。！？；;]{0,20}$)/i;
const ANALYZE_NEGATED_COMPLETION_SUFFIX = /^\s*(?:(?:has|have|had|is|are|was|were|do|does|did)\s+not(?:\s+been|\s+be)?|(?:do|does|did)\s+not\s+(?:find|show|support|confirm|validate|verify)|not|never|unverified|unknown|(?:尚未|未|没有|并未)(?:发现|表明|显示|支持|确认|验证)?|不成立|未知|待核查)/i;
const ANALYZE_SOURCE_LIMIT_MARKER = /(?:\b(?:not|no|without|missing|unknown|unreviewed|unchecked|limited|requires?|needs?|cannot|does\s+not|has\s+not|have\s+not)\b|(?:尚未|未|不|无|缺|未知|尚|需要|不能|无法|仅|只是|不是|待))/i;
const ANALYZE_LITERATURE_NOT_CHECKED_MARKER = /(?:\b(?:not|no|without|has\s+not|have\s+not).{0,28}(?:check|search|review|literature)|(?:未|没有|尚未|无).{0,20}(?:检索|核查|检查|综述|文献)|(?:文献|研究).{0,16}(?:未|没有|尚未|无))/i;
const ANALYZE_POSITIVE_SOURCE_REVIEW_STATE = /(?:\b(?:third[- ]party|independent|external)\s+(?:audit|review)\b.{0,40}\b(?:signed\s+off|approved|validated|verified|confirmed)\b|\b(?:third[- ]party|independent|external)\s+(?:audit|review)\b.{0,40}\bfound\b.{0,20}\b(?:source\s+)?(?:reliable|valid|credible)\b|(?:第三方|独立|外部).{0,8}(?:审计|审阅|复核).{0,24}(?:认定|确认|签字|批准|通过).{0,12}(?:来源)?(?:可靠|有效|可信)?)/i;
const ANALYZE_POSITIVE_LITERATURE_STATE = /(?:\b(?:comprehensive|systematic|complete)\s+(?:literature\s+)?(?:review|search).{0,36}\b(?:confirms?|establishes?|proves?|shows?)\b|\b(?:the\s+)?(?:first|novel)\s+(?:such\s+)?(?:method|approach|study|finding)\b|(?:系统|全面|完整).{0,10}(?:检索|综述|搜索).{0,24}(?:确认|证明|表明|显示)|(?:首个|首次提出|新颖方法|全新方法))/i;
const ANALYZE_SOURCE_LIMITATION_COPY = new Set([
  '仅为内部 KB 候选记录；系统综述、独立复现与专家审查均未记录。',
  'Internal KB candidate only; systematic review, independent replication, and expert review are not recorded.',
]);
const ANALYZE_LITERATURE_STATUS_COPY = new Set([
  '未执行外部文献检索；先例与新颖性仍未知。',
  'External literature was not searched; precedent and novelty remain unknown.',
]);
const ANALYZE_LANGUAGE_BOUND_COPY = {
  zh: {
    sourceLimitation: '仅为内部 KB 候选记录；系统综述、独立复现与专家审查均未记录。',
    literatureStatus: '未执行外部文献检索；先例与新颖性仍未知。',
    experimentDecision: '仅当候选假设在预注册主指标上优于竞争假设时继续；否则拒绝候选。',
    experimentFalsification: '若候选假设未优于竞争假设，或结果方向与预注册预期相反，则证伪并拒绝候选。',
    experimentStop: '若最低数据要求、数据质量或安全边界不满足，则停止实验且不作机制结论。',
    actionDecision: '仅当预注册主指标提供可区分信息时继续；否则停止并复核候选。',
    actionStop: '若最低数据要求、数据质量或安全边界不满足，则停止该行动。',
  },
  en: {
    sourceLimitation: 'Internal KB candidate only; systematic review, independent replication, and expert review are not recorded.',
    literatureStatus: 'External literature was not searched; precedent and novelty remain unknown.',
    experimentDecision: 'Continue only if the candidate hypothesis outperforms the competitor on the preregistered primary outcome; otherwise reject the candidate.',
    experimentFalsification: 'Falsify and reject the candidate if it does not outperform the competitor or the result reverses the preregistered direction.',
    experimentStop: 'Stop the experiment without a mechanism conclusion if minimum data, data quality, or safety requirements are not met.',
    actionDecision: 'Continue only when the preregistered primary metric provides discriminating information; otherwise stop and review the candidate.',
    actionStop: 'Stop the action if minimum data, data quality, or safety requirements are not met.',
  },
};
const ANALYZE_EXPERIMENT_DECISION_COPY = new Set([
  '仅当候选假设在预注册主指标上优于竞争假设时继续；否则拒绝候选。',
  'Continue only if the candidate hypothesis outperforms the competitor on the preregistered primary outcome; otherwise reject the candidate.',
]);
const ANALYZE_EXPERIMENT_FALSIFICATION_COPY = new Set([
  '若候选假设未优于竞争假设，或结果方向与预注册预期相反，则证伪并拒绝候选。',
  'Falsify and reject the candidate if it does not outperform the competitor or the result reverses the preregistered direction.',
]);
const ANALYZE_EXPERIMENT_STOP_COPY = new Set([
  '若最低数据要求、数据质量或安全边界不满足，则停止实验且不作机制结论。',
  'Stop the experiment without a mechanism conclusion if minimum data, data quality, or safety requirements are not met.',
]);
const ANALYZE_ACTION_DECISION_COPY = new Set([
  '仅当预注册主指标提供可区分信息时继续；否则停止并复核候选。',
  'Continue only when the preregistered primary metric provides discriminating information; otherwise stop and review the candidate.',
]);
const ANALYZE_ACTION_STOP_COPY = new Set([
  '若最低数据要求、数据质量或安全边界不满足，则停止该行动。',
  'Stop the action if minimum data, data quality, or safety requirements are not met.',
]);
const ANALYZE_STRUCTURED_HYPOTHESIS_FIELD_KEYS = new Set([
  'candidate_hypothesis', 'competitor_hypotheses', 'mapping_hypothesis',
  'candidate_implication', 'expected_observation', 'expected_information',
]);
const ANALYZE_ACTION_IMPERATIVE_FIELD_KEYS = new Set([
  'steps', 'procedure', 'how', 'intervention_or_measurement',
  'concrete_application', 'translated_to_target', 'observable_test', 'signal_to_check',
]);
const ANALYZE_CONDITIONAL_RULE_FIELD_KEYS = new Set([
  'decision_rule', 'falsification_rule', 'stop_rule', 'stop_condition',
]);
const ANALYZE_STATE_PROSPECTIVE_PREFIX = /(?:\b(?:needs?|requires?|should|must|would|could|may|might|will|planned|planning|proposed)(?:\s+still)?(?:\s+to)?(?:\s+be)?\s*$|\b(?:must|should|will|would|could)\s+be\s+\w+ed\s+before[^,.!?，。！？；;]{0,80}(?:is|are|be)?\s*$|(?:未来|计划|拟|待|尚需|需要|需|必要|应当|应该|必须)(?:被|进行)?[^.!?。！？；;]{0,12}$|(?:会|可能|也许)(?:被|进行)?\s*$|(?:能否|是否|有无)\s*$)/i;
const ANALYZE_STATE_PROSPECTIVE_SUFFIX = /^\s*(?:(?:would|could|should|must|will)\s+(?:be\s+)?(?:needed|required|planned|proposed|tested|checked|estimated|fitted|trained|calibrated|validated|replicated|reviewed)|(?:is|are|was|were|remains?)\s+(?:unknown|uncertain)|to\s+be\s+(?:tested|checked|estimated|fitted|trained|calibrated|validated|replicated|reviewed))\b|^\s*(?:仍?需|需要|待|拟|计划|尚未|有待|(?:仍|尚)(?:为|是)?(?:未知|不确定))/i;
const ANALYZE_QUESTION_STATE_QUALIFIER = /^\s*(?:(?:whether|is|are|was|were|do|does|did|has|have|had|can|could|should|would|will)\b|(?:是否|能否|有没有))/i;
const ANALYZE_PRESUPPOSITIONAL_QUESTION = /^\s*(?:is|are|was|were|do|does|did|has|have|had|can|could|should|would|will)\b(?:(?![.!?]).){0,160}\b(?:that|why|when|how)\b|^\s*how\s+(?:should|could|would|can|may|might|must)\b(?:(?![.!?]).){0,120}\b(?:why|when|fact\s+that|who)\b|^\s*(?:(?![.!?]).){0,80}\b(?:may|might|could|would)\b(?:(?![.!?]).){0,48}\b(?:explain|show|know)\b(?:(?![.!?]).){0,32}\b(?:why|when|how)\b|^\s*(?:是否|能否)(?:(?![。！？]).){0,80}(?:令人)?(?:惊讶|意外|事实|为什么|为何|何时|如何)|^\s*(?:(?![。！？]).){0,80}(?:可能|也许|能够|可以)(?:(?![。！？]).){0,32}(?:解释|显示|知道|了解)(?:(?![。！？]).){0,24}(?:为什么|为何|何时|如何)|^\s*(?:是否|能否)(?:(?![。！？]).){0,24}(?:解释|知道|了解)(?:(?![。！？]).){0,24}(?:为什么|为何|何时|如何)/i;
const ANALYZE_PROSPECTIVE_WH_PREFIX = /^\s*how\s+(?:should|could|would|can|may|might|must)\b(?:(?!\b(?:now\s+that|because|after|given|but|although|while|yet|fact\s+that|why|when)\b).){0,48}\b(?:test|check|assess|measure|compare|evaluate|verify|review|design|determine)\b(?:(?!\b(?:but|although|while|yet|why|when|how)\b).){0,48}\bwhether\b(?:(?!\b(?:but|although|while|yet)\b).){0,48}$|^\s*如何(?:测试|检验|核查|检查|评估|比较|测量|验证|设计|确定)(?:(?!已经|既然|因为|之后|以后).){0,24}$/i;
const ANALYZE_PROSPECTIVE_ACTION_QUESTION = /^\s*(?:how\s+(?:should|could|would|can|may|might|must|to)\s+(?:test|check|assess|measure|compare|evaluate|verify|review|design|determine)\b|如何(?:测试|检验|核查|检查|评估|比较|测量|验证|设计|确定))/i;
const ANALYZE_EXPLICIT_CHECK_PREFIX = /(?:\b(?:check|test|assess|determine|evaluate|verify|review|search)\b(?:(?!\b(?:but|although|while|yet)\b).){0,80}\bwhether\b(?:(?!\b(?:but|although|while|yet)\b).){0,48}$|(?:核查|检查|测试|检验|评估|搜索|检索)(?:(?!但|但是|不过|然而|同时).){0,40}(?:是否|有无|能否)(?:(?!但|但是|不过|然而|同时).){0,24}$)/i;
const ANALYZE_PURPOSE_PREFIX = /(?:\b(?:in\s+order\s+to|aims?\s+to|plans?\s+to|designed\s+to|intended\s+to|proposed\s+to)\s*$|(?:用于|以便|用来|旨在|计划)\s*$)/i;
const ANALYZE_OUTCOME_BOUND_QUALIFIER_PREFIX = /(?:\b(?:may|might|could|would)(?:\s+(?:possibly|potentially))?\s+(?:not\s+)?(?:be\s+)?$|\b(?:possibly|potentially)\s+(?:not\s+)?(?:be\s+)?$|\b(?:may|might|could|would)\s+consider(?:\s+using)?\s*$|\b(?:may|might|could|would)\b(?:(?!\b(?:but|although|while|yet|and)\b).){0,32}$|(?:可能|也许)(?:会|是|为|有)?\s*$|(?:可能|也许)(?:(?!但|但是|不过|然而|同时|并且|且).){0,24}$|(?:可以|可)考虑\s*$|(?:无法|不能|不可)\s*$)/i;
const ANALYZE_MODAL_EVIDENCE_SCOPE_PREFIX = /(?:\b(?:may|might|could|would)\s+(?:show|confirm|indicate|find|report|demonstrate|reveal|cause|drive|produce|explain|prevent|determine|trigger|create|induce|control|govern|lead\s+to|result\s+in)\b(?:(?!\b(?:but|although|while|yet)\b).){0,48}$|(?:可能|也许)(?:会)?(?:显示|确认|表明|发现|报告|证明|证实|揭示|导致|驱动|产生|解释|防止|阻止|造成|引发|决定|控制|支配)(?:(?!但|但是|不过|然而|同时).){0,24}$)/i;
const ANALYZE_OUTCOME_BOUND_CONDITIONAL_PREFIX = /(?:^\s*(?:if|unless|only\s+(?:if|when))\b(?:(?!\b(?:but|although|though|yet)\b).){0,96}$|^\s*(?:若|如果|除非|仅当)(?:(?!但|但是|不过|然而).){0,48}$)/i;
const ANALYZE_FAILURE_SIGNAL_CONDITIONAL_SUFFIX = /^(?:(?![.!?。！？；;]).){0,48}(?:\b(?:then|otherwise)\b.{0,16}\b(?:stop|reject|abandon|falsif\w*|do\s+not\s+continue)\b|(?:时|则|就).{0,12}(?:停止|否定|拒绝|放弃|证伪|不再继续))/i;
const ANALYZE_FAILURE_SIGNAL_COMMAND_PREFIX = /^\s*(?:stop|reject|abandon|falsif\w*|do\s+not\s+continue)\s+(?:if|when|unless)\b(?:(?!\b(?:but|although|while|yet)\b).){0,96}$/i;
const ANALYZE_RULE_COMMAND_CONDITIONAL_PREFIX = /^\s*(?:continue\s+only\s+(?:if|when)|(?:falsif\w*|reject|stop|abandon)(?:(?!\b(?:but|although|while|yet)\b).){0,64}\b(?:if|when|unless)\b)(?:(?!\b(?:but|although|while|yet)\b).){0,96}$/i;
const ANALYZE_COMPLETED_TENSE_OUTCOME = /(?:\b(?:worked|improved|reduced|lowered|boosted|increased|decreased|outperformed|delivered|produced|achieved|yielded|failed|worsened|degraded|adopted|deployed|introduced|developed|used|showed|confirmed|found|reported|demonstrated|revealed)\b|(?:已经|已|曾经|曾).{0,12}(?:有效|奏效|成功|改善|提升|降低|减少|优于|增加|实现|取得|产生|失败|恶化|部署|采用|使用|提出|介绍|开发|显示|确认))/i;
const ANALYZE_EPISTEMIC_OUTCOME_LEFT = /(?:\bno\s+evidence\s+(?:that|whether|(?:shows?|showed|shown|supports?|supported|confirms?|confirmed|establish(?:es|ed)?)\s+(?:that|whether))(?:(?!\b(?:but|although|though|yet)\b).){0,80}$|\bno\s+(?:data|results?|stud(?:y|ies)|experiments?|tests?|measurements?|replications?)\b.{0,24}\b(?:shows?|showed|shown|supports?|supported|confirms?|confirmed|establish(?:es|ed)?)\s+(?:that|whether)(?:(?!\b(?:but|although|though|yet)\b).){0,80}$|\b(?:evidence|data|stud(?:y|ies)|results?)\s+(?:do|does|did)\s+not\s+(?:show|support|confirm|establish)\s+(?:that|whether)(?:(?!\b(?:but|although|though|yet)\b).){0,80}$|\b(?:(?:is|are|remains?)\s+)?(?:not\s+known|unknown|unclear|uncertain)\s+whether(?:(?!\b(?:but|although|though|yet)\b).){0,80}$|(?:没有|尚无)(?:实证)?(?:证据|数据|结果).{0,24}(?:表明|显示|支持|确认|证明|证实|验证)(?:(?!但|但是|不过|然而|同时|为什么|为何|何时|如何|因为|由于).){0,48}$|(?:没有|尚无)(?:实验|测试|测量|复现|研究).{0,20}(?:表明|显示|支持|确认|证明|证实)(?:(?!但|但是|不过|然而|同时|为什么|为何|何时|如何|因为|由于).){0,48}$|(?:尚不清楚|仍不清楚|不确定|未知|仍未知|尚未知|不能确定|无法确定)(?:(?!为什么|为何|何时|如何|因为|由于).){0,24}(?:是否|能否|有无)(?:(?!但|但是|不过|然而).){0,48}$)/i;
const ANALYZE_EPISTEMIC_OUTCOME_RIGHT = /(?:^\s*no\s+stud(?:y|ies)\b.{0,40}\b(?:shows?|showed|shown|supports?|supported|confirms?|confirmed|establish(?:es|ed)?)\b|^\s*(?:没有|尚无)研究.{0,24}(?:表明|显示|支持|确认|证明|证实))/i;
const ANALYZE_UNRECORDED_STATE = /(?:\bno\s+(?:deployment\s+evidence|(?:independent\s+)?replication)\s+(?:is\s+)?recorded\b|\b(?:deployment\s+evidence|(?:independent\s+)?replication)\s+(?:is|has)\s+not\s+(?:been\s+)?recorded\b|(?:尚无部署证据记录|尚未记录(?:独立)?复现|(?:独立)?复现尚未记录))/i;
const ANALYZE_UNRECORDED_STATE_EXACT = /^(?:\s*(?:\bno\s+(?:deployment\s+evidence|(?:independent\s+)?replication)\s+(?:is\s+)?recorded\b|\b(?:deployment\s+evidence|(?:independent\s+)?replication)\s+(?:is|has)\s+not\s+(?:been\s+)?recorded\b|(?:尚无部署证据记录|尚未记录(?:独立)?复现|(?:独立)?复现尚未记录))\s*)$/i;
const ANALYZE_UNRECORDED_OUTCOME_LEFT = /(?:\bno\s+(?:deployment\s+evidence|(?:independent\s+)?replication)\s+(?:is\s+)?recorded|\b(?:deployment\s+evidence|(?:independent\s+)?replication)\s+(?:is|has)\s+not\s+(?:been\s+)?recorded|(?:尚无部署证据记录|尚未记录(?:独立)?复现|(?:独立)?复现尚未记录))\s*$/i;
const ANALYZE_BOUND_EPISTEMIC_CLAUSE = /^\s*(?:there\s+(?:is|are)\s+)?no\s+(?:evidence|data|results?|stud(?:y|ies)|experiments?|tests?|measurements?|replications?)\b(?:(?!\b(?:but|although|while|yet|because)\b).){0,40}\b(?:shows?|showed|shown|supports?|supported|confirms?|confirmed|establish(?:es|ed)?)\s+(?:that|whether)\b(?:(?!\b(?:but|although|while|yet|because)\b).){0,120}$|^\s*(?:没有|尚无)(?:实证)?(?:证据|数据|结果|实验|测试|测量|复现|研究)(?:(?!但|但是|不过|然而|同时|为什么|为何|何时|如何|因为|由于).){0,40}(?:表明|显示|支持|确认|证明|证实|验证)(?:(?!但|但是|不过|然而|同时|为什么|为何|何时|如何|因为|由于).){0,120}$/i;
const ANALYZE_BOUND_NEGATED_EVIDENCE_CLAUSE = /^\s*(?:the\s+)?(?:evidence|data|results?|stud(?:y|ies))\s+(?:do|does|did)\s+not\s+(?:show|support|confirm|establish)\s+(?:that|whether)\b(?:(?!\b(?:but|although|while|yet|because)\b).){0,120}$/i;
const ANALYZE_GERUND_MODAL_CLAUSE = /^\s*(?:using|applying)\b(?:(?!\b(?:but|although|while|yet)\b).){0,80}\b(?:may|might|could|would|can)\b|^\s*(?:使用|采用|应用)(?:(?!但|但是|不过|然而|同时).){0,48}(?:可能|也许|可以|能够|能)/i;
const ANALYZE_ACTION_INSTRUCTION_PREFIX = /^\s*(?:for\b[^,.!?，。！？]{0,32},\s*|(?:为|对|在|将|把)[^,，。！？]{0,32})$/i;
const ANALYZE_NOMINAL_EXPLANATION_PREFIX = /(?:缩小|扩大|比较|评估|探索|界定|避免(?:后续)?|统一|固定|调整|保持)\s*$/;
const ANALYZE_NOMINAL_EXPLANATION_SUFFIX = /^\s*(?:空间|框架|变量|模型|方案|候选|路径|范围|能力|方式|口径)/;
const ANALYZE_NEGATED_NEGATIVE_CANDIDATE_STATE = /(?:\b(?:no\s+longer|anything\s+but|far\s+from|not|isn't|aren't|wasn't|weren't|cannot\s+be\s+(?:considered|called|treated\s+as)|can't\s+be\s+(?:considered|called|treated\s+as))\s+(?:unvalidated|unverified|untested|untrained|uncalibrated|unreviewed|unreplicated|unsupported)\b|(?:不是|并非|绝非|不再|不能算|不可视为).{0,8}(?:没有.{0,6}(?:部署|验证|测试|训练|校准|复现)(?:过)?|未(?:部署|验证|测试|训练|校准|复现)|未经(?:验证|测试|训练|校准|复现)))/i;
const ANALYZE_METHOD_ARTIFACT_CONTEXT = /(?:\b(?:threshold|cutoff|parameter|coefficient|model|estimator|mapping|method|approach|benchmark)\b|(?:阈值|截点|临界值|参数|系数|模型|估计器|映射|方法|方案|基准))/i;
const ANALYZE_COMPLETED_METHOD_STATE = /(?:\b(?:estimated|fitted|trained|calibrated|tuned|optimized|derived|benchmarked|validated|verified|tested)\b|(?:已|经)?(?:估计|拟合|训练|校准|调优|优化|导出|测定|验证|测试)(?:过|完成)?)/i;
const ANALYZE_OPERATIONAL_RESULT_CONTEXT = /(?:\b(?:production|operational|field|real[- ]world)\s+(?:performance|runs?|operations?|deployments?|trials?|use)\b|\b(?:production|field)\s+evidence\b|\bperformance\s+in\s+production\b|\blive\s+operations?\b|(?:生产|现场|真实世界)(?:性能|表现|运行|操作|部署|试验|应用|证据))/i;
const ANALYZE_POSITIVE_OPERATIONAL_STATE = /(?:\b(?:attained|achieved|delivered|yielded|reached|successful|reliable|robust|effective|stable|worked|succeeded|confirmed|validated)\b|(?:达到|取得|实现|产生|可靠|稳健|有效|稳定|成功|奏效|确认|验证))/i;
const ANALYZE_COMPLETED_EVIDENCE_ARTIFACT = /(?:\b(?:independent|third[- ]party|external)\s+replication\b|\bexternal\s+validation\b|\bexpert\s+review\b|(?:独立|第三方|外部)(?:复现|验证)|专家(?:审查|复核))/i;
const ANALYZE_ASSERTED_NEGATIVE_EVIDENCE_RESULT = /(?:\b(?:transfer|method|approach|mapping|mechanism)\b.{0,48}\b(?:was|were|is|are)\s+not\s+(?:successful|robust|reliable|effective|valid)\b.{0,48}\b(?:deployments?|trials?|cases?)\b|\b(?:independent|third[- ]party)\s+replication\b.{0,48}\b(?:do|does|did)\s+not\s+(?:find|show|support|confirm|validate|verify)\b|\bfield\s+trials?\b.{0,48}\b(?:do|does|did)\s+not\s+(?:find|show|support|confirm|validate|verify)\b|(?:迁移|方法|方案|映射|机制).{0,32}(?:部署|试验|案例).{0,20}(?:未成功|不成功|失败|不可靠|不稳健|无效)|(?:独立|第三方)复现.{0,24}(?:未发现|没有发现|不支持|未确认|未验证)|现场试验.{0,24}(?:未发现|没有发现|不支持|未确认|未验证))/i;
const ANALYZE_EXTERNAL_ACTOR_CONTEXT = /(?:\b(?:[A-Z][\w-]+\s+){1,6}(?:Institute|University|Hospital|Clinic|Company|Corporation|Laborator(?:y|ies)|Agency|Foundation|Center|Centre|Team|Group|Organization|Organisation)\b|\b(?:hospitals?|clinics?|universit(?:y|ies)|institutes?|researchers?|clinicians?|organizations?|organisations?|companies|laborator(?:y|ies)|agencies|centers?|centres?|(?:research|clinical|external)\s+teams?)\b|(?:研究机构|研究所|大学|医院|诊所|公司|企业|实验室|政府机构|基金会|中心|外部团队|第三方团队))/i;
const ANALYZE_EXTERNAL_PERSON_CONTEXT = /(?:\b(?:Dr|Professor|Prof)\.?\s+[A-Z][a-z]+\b|\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b)/;
const ANALYZE_EXTERNAL_ADOPTION_STATE = /(?:\b(?:(?:rely|relies)\s+on|reliance\s+on|uses?|used|using|adopts?|adopted|deploys?|deployed|implements?|implemented|operates?|operated|develops?|developed|introduces?|introduced)\b|(?:依赖|使用|采用|部署|实施|落地|运行|开发|提出|介绍))/i;
const ANALYZE_SOURCE_ATTRIBUTION_CONTEXT = /(?:\b(?:the\s+source|source|source\s+(?:record|material|entry)|internal\s+record|record|entry)\b|(?:来源|来源记录|内部记录|该来源|这个来源|来源材料|来源条目|记录|条目))/i;
const ANALYZE_EMPIRICAL_SUBJECT_CONTEXT = /(?:\b(?:method|model|approach|intervention|mapping|transfer|system|algorithm|workflow)\b|(?:方法|模型|方案|干预|映射|迁移|系统|算法|工作流))/i;
const ANALYZE_COMPLETED_EMPIRICAL_OUTCOME = /(?:\b(?:works?|worked|effective|successful|accurate|reliable|robust|valid|improves?|improved|reduces?|reduced|lowers?|lowered|boosts?|boosted|increases?|increased|decreases?|decreased|outperforms?|outperformed|delivers?|delivered|produces?|produced|achieves?|achieved|yields?|yielded|fails?|failed|ineffective|inaccurate|unreliable|worsens?|worsened|degrades?|degraded)\b|(?:有效|奏效|成功|准确|可靠|稳健|改善|提升|降低|减少|优于|增加|实现|取得|产生|无效|不准确|失败|恶化|劣化|没有奏效))/i;
const ANALYZE_EMPIRICAL_EVIDENCE_CONTEXT = /(?:\b(?:data|measurements?|observed\s+results?|results?|experiments?|benchmarks?|studies|evidence|analyses|tests?)\b|(?:数据|测量|观察结果|结果|实验|基准|研究|证据|分析|测试))/i;
const ANALYZE_EMPIRICAL_EVIDENCE_OUTCOME = /(?:\b(?:shows?|showed|confirms?|confirmed|indicates?|indicated|finds?|found|reports?|reported|demonstrates?|demonstrated|reveals?|revealed)\b|(?:表明|确认|显示|发现|报告|证明|证实|揭示))/i;
const ANALYZE_LITERATURE_FACT_ASSERTION = /(?:\b(?:no|some|existing|prior|previous|related)\s+(?:work|research|stud(?:y|ies)|literature)\b|\bthere\s+(?:is|are)\s+(?:no|some)\s+(?:prior\s+|related\s+)?(?:work|research|stud(?:y|ies)|literature)\b|\b(?:has|have)\s+(?:never\s+|already\s+)?been\s+studied\b|\b(?:never|not)\s+(?:been\s+)?studied\b|\b(?:is|are|was|were)\s+(?:not\s+)?novel\b|(?:已有|现有|此前|先前|相关).{0,8}(?:研究|工作(?!流)|文献)|(?:没有|不存在|从未).{0,8}(?:相关)?(?:研究|工作(?!流)|文献|有人研究)|(?:想法|方法|方案|研究).{0,8}(?:并不|不是|很|具有)?新颖)/i;
const ANALYZE_LITERATURE_ATTRIBUTION_CONTEXT = /(?:\b(?:stud(?:y|ies)|papers?|research|literature|articles?|publications?|preprints?|patents?|theses|thesis|dissertations?|books?|textbooks?|documentation|docs?|web\s+sources?|reports?|datasets?)\b|\b[A-Z][a-z]+\s+et\s+al\b\.?|(?:研究|论文|文献|文章|预印本|专利|学位论文|书籍|教科书|文档|网页|网站|报告|数据集|[\u3400-\u9fff]{2,8}等(?:人)?))/i;
const ANALYZE_LITERATURE_ATTRIBUTION_OUTCOME = /(?:\b(?:propose[sd]?|introduce[sd]?|develop(?:s|ed)?|reports?|reported|describes?|described|uses?|used|publish(?:es|ed)?|studied)\b|(?:提出|介绍|开发|报告|描述|使用|发表))/i;
const ANALYZE_INVENTED_CITATION_SHAPE = /(?:\b[A-Z][a-z]+\s+et\s+al\.?\s*[,(]?\s*(?:19|20)\d{2}\)?|\bsee\s+[A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?\s*,?\s*(?:19|20)\d{2}\b|\baccording\s+to\s+[A-Z][a-z]+\s*\((?:19|20)\d{2}\)|\b[A-Z][A-Za-z-]*(?:\s+[A-Z][A-Za-z-]*)?\s+published\b.{0,48}\b(?:19|20)\d{2}\b|参见.{0,32}[（(](?:19|20)\d{2}[）)]|《[^》]{1,40}》.{0,24}发表.{0,24}(?:19|20)\d{2})/i;
const ANALYZE_CAUSAL_MECHANISM_ASSERTION = /(?:\b(?:causes?|drives?|produces?|explains?|prevents?|determines?|triggers?|creates?|induces?|controls?|governs?)\b|\b(?:leads?\s+to|results?\s+in)\b|(?:导致|驱动|产生|解释(?=[了着过\u3400-\u9fffA-Za-z0-9])|防止|阻止|造成|引发|决定(?!是否|能否|要不要)|控制|支配))/i;
const ANALYZE_CAUSAL_SUBJECT_CONTEXT = /(?:\b(?:feedback|delay|variable|factor|mechanism|mapping|intervention|method|model|approach|workflow|algorithm|system|parameter|signal)\b|(?:反馈|延迟|变量|因素|机制|映射|干预|措施|方法|模型|方案|工作流|算法|系统|参数|信号))/i;

function analyzeHasAnyView(text, pattern) {
  return analyzeClaimViews(text).some(view => pattern.test(view));
}

function analyzeHasUnnegatedMatch(text, pattern) {
  return analyzeClaimViews(text).some(view => {
    const matcher = new RegExp(pattern.source, pattern.flags.includes('g')
      ? pattern.flags : `${pattern.flags}g`);
    let match;
    while ((match = matcher.exec(view)) !== null) {
      const prefix = view.slice(Math.max(0, match.index - 64), match.index);
      if (!ANALYZE_NEGATED_COMPLETION_PREFIX.test(prefix)) return true;
    }
    return false;
  });
}

function analyzeClaimClauses(text) {
  const clauses = [];
  const seen = new Set();
  for (const view of analyzeClaimViews(text)) {
    const clauseView = view.replace(/\bet\s+al\./gi, 'et al');
    for (const rawClause of clauseView.split(/[,.!?;，。！？；\n]+/u)) {
      const clause = rawClause.trim();
      if (clause && !seen.has(clause)) {
        seen.add(clause);
        clauses.push(clause);
      }
    }
  }
  return clauses;
}

function analyzeHasAssertedConceptPair(text, {
  contextPattern, outcomePattern, allowProspective = true,
}) {
  for (const clause of analyzeClaimClauses(text)) {
    const matcher = new RegExp(outcomePattern.source, outcomePattern.flags.includes('g')
      ? outcomePattern.flags : `${outcomePattern.flags}g`);
    let outcome;
    while ((outcome = matcher.exec(clause)) !== null) {
      const windowText = clause.slice(
        Math.max(0, outcome.index - 120),
        Math.min(clause.length, outcome.index + outcome[0].length + 120)
      );
      if (!contextPattern.test(windowText)) continue;
      const prefix = clause.slice(Math.max(0, outcome.index - 96), outcome.index);
      const suffix = clause.slice(
        outcome.index + outcome[0].length,
        Math.min(clause.length, outcome.index + outcome[0].length + 48)
      );
      if (ANALYZE_NEGATED_COMPLETION_PREFIX.test(prefix)) continue;
      if (ANALYZE_NEGATED_COMPLETION_SUFFIX.test(suffix)) continue;
      if (allowProspective &&
          (ANALYZE_PROSPECTIVE_EVIDENCE_QUALIFIER.test(prefix) ||
           ANALYZE_PROSPECTIVE_EVIDENCE_QUALIFIER.test(suffix))) continue;
      return true;
    }
  }
  return false;
}

function analyzeHasAssertedCalibratedThreshold(text) {
  for (const clause of analyzeClaimClauses(text)) {
    if (!ANALYZE_THRESHOLD_CONTEXT.test(clause)) continue;
    const matcher = new RegExp(
      ANALYZE_CALIBRATED_OUTCOME.source,
      `${ANALYZE_CALIBRATED_OUTCOME.flags}g`
    );
    let outcome;
    while ((outcome = matcher.exec(clause)) !== null) {
      const prefix = clause.slice(Math.max(0, outcome.index - 96), outcome.index);
      const suffix = clause.slice(
        outcome.index + outcome[0].length,
        Math.min(clause.length, outcome.index + outcome[0].length + 48)
      );
      if (ANALYZE_NEGATED_COMPLETION_PREFIX.test(prefix)) continue;
      if (ANALYZE_NEGATED_COMPLETION_SUFFIX.test(suffix)) continue;
      if (ANALYZE_PROSPECTIVE_THRESHOLD_QUALIFIER.test(prefix)) continue;
      return true;
    }
  }
  return false;
}

function validateCandidateMethod(value) {
  return hasExactKeys(value, [
    'name', 'proposal_status', 'why_considered', 'source_support', 'evidence_required',
  ]) && textWithin(value.name, 1, 120) &&
    value.proposal_status === 'unverified_proposal' &&
    textWithin(value.why_considered, 1, 400) && value.source_support === 'not_recorded' &&
    textWithin(value.evidence_required, 1, 400);
}

function validateTargetDomainIntro(value) {
  return hasExactKeys(value, [
    'domain_name', 'what_record_says', 'corresponding_phenomenon',
    'source_limitations', 'candidate_methods',
  ]) && textWithin(value.domain_name, 1, 120) &&
    textWithin(value.what_record_says, 1, 700) &&
    validateCorrespondingPhenomenon(value.corresponding_phenomenon) &&
    textList(value.source_limitations, 1, 1, 400) && value.source_limitations.every(
      item => ANALYZE_SOURCE_LIMITATION_COPY.has(item) &&
        analyzeHasAnyView(item, ANALYZE_SOURCE_LIMIT_MARKER) &&
        !analyzeHasUnnegatedMatch(item, ANALYZE_POSITIVE_SOURCE_REVIEW_STATE) &&
        !analyzeHasAssertedConceptPair(item, {
          contextPattern: ANALYZE_SOURCE_REVIEW_CONTEXT,
          outcomePattern: ANALYZE_POSITIVE_SOURCE_REVIEW_OUTCOME,
          allowProspective: false,
        })
    ) &&
    objectList(value.candidate_methods, 1, 4, validateCandidateMethod);
}

function validateParameterMap(value) {
  return hasExactKeys(value, [
    'source_concept', 'source_explanation', 'target_concept', 'target_explanation',
    'support_status', 'mapping_hypothesis', 'evidence_for', 'evidence_against',
    'observable_test', 'failure_signal',
  ]) && textWithin(value.source_concept, 1, 120) &&
    textWithin(value.source_explanation, 1, 400) &&
    textWithin(value.target_concept, 1, 120) &&
    textWithin(value.target_explanation, 1, 400) && value.support_status === 'hypothesis' &&
    textWithin(value.mapping_hypothesis, 1, 400) && textList(value.evidence_for, 0, 4, 240) &&
    textList(value.evidence_against, 1, 4, 240) &&
    textWithin(value.observable_test, 1, 400) && textWithin(value.failure_signal, 1, 400);
}

function validateStructuralMapping(value) {
  return hasExactKeys(value, ['status', 'rationale', 'parameter_map', 'competing_explanations']) &&
    value.status === 'untested' && textWithin(value.rationale, 1, 700) &&
    objectList(value.parameter_map, 1, 8, validateParameterMap) &&
    textList(value.competing_explanations, 1, 5, 400);
}

function validateBorrowableInsight(value) {
  return hasExactKeys(value, [
    'tool', 'proposal_status', 'why_considered', 'translated_to_target',
    'concrete_application', 'source_support', 'transfer_status', 'prerequisites',
    'failure_signal',
  ]) && textWithin(value.tool, 1, 120) &&
    value.proposal_status === 'unverified_proposal' &&
    textWithin(value.why_considered, 1, 700) &&
    textWithin(value.translated_to_target, 1, 700) &&
    textWithin(value.concrete_application, 1, 1200) &&
    value.source_support === 'not_recorded' && value.transfer_status === 'untested' &&
    textList(value.prerequisites, 1, 5, 240) &&
    textWithin(value.failure_signal, 1, 400);
}

function validateExpectedOutcome(value) {
  return hasExactKeys(value, ['hypothesis_id', 'role', 'expected_observation']) &&
    textWithin(value.hypothesis_id, 1, 80) &&
    ['candidate', 'competitor'].includes(value.role) &&
    textWithin(value.expected_observation, 1, 400);
}

function analyzeSemanticKey(value) {
  return value.normalize('NFKD').replace(/\p{M}/gu, '').normalize('NFKC')
    .toLocaleLowerCase('en-US').replace(/[^\p{L}\p{N}_\u3400-\u9fff]+/gu, ' ').trim();
}

const ANALYZE_UNFALSIFIABLE_RULE = /(?:\b(?:continue|proceed).{0,16}\bregardless\b|\bregardless\s+of\s+(?:the\s+)?outcome\b|\bno\s+(?:observed\s+)?result.{0,20}\bfalsif|\bcannot\s+be\s+falsified\b|\bnever\s+stop\b|\balways\s+continue\b|\b(?:do\s+not|don't)\s+stop\b.{0,24}\b(?:any|every|all)\s+(?:outcome|result|case)s?\b|\bcontinue\b.{0,16}\b(?:in\s+)?all\s+(?:cases|outcomes|results)\b|(?:无论|不管).{0,16}(?:结果|观察).{0,12}(?:继续|通过)|(?:任何|所有).{0,12}(?:结果|观察).{0,12}(?:不能|无法|不会).{0,6}证伪|(?:不|不要|不得).{0,8}(?:停止|终止).{0,16}(?:任何|所有|无论).{0,8}(?:结果|情形|情况)|(?:任何|所有|无论).{0,12}(?:结果|情形|情况).{0,12}(?:都|均|仍)?(?:不停|不停止|继续)|(?:无法|不能|不会)被?证伪|(?:永不|从不)停止|始终继续)/i;
const ANALYZE_CONDITIONAL_RULE = /(?:\b(?:if|when|unless|only\s+if|otherwise)\b|(?:若|如果|当|仅当|否则))/i;
const ANALYZE_FALSIFICATION_RULE = /(?:\b(?:falsif|reject|stop|abandon|fail|do\s+not\s+continue)\w*\b|(?:否定|证伪|停止|放弃|拒绝|不再继续|不支持))/i;
const ANALYZE_STOP_RULE = /(?:\b(?:stop|abort|pause|terminate|do\s+not\s+proceed)\w*\b|(?:停止|终止|暂停|不进入|不继续))/i;
const ANALYZE_VALIDATED_THRESHOLD = /(?:\b(?:validated|verified|measured|established|fixed)\s+(?:cutoff|threshold)\b|\bno\s+calibration\s+(?:is\s+)?needed\b|\bempirically\s+calibrated\s+(?:cutoff|threshold)\b|(?:已验证|已测量|已确认|固定).{0,8}(?:阈值|截点|临界值)|(?:经|已)?实证校准.{0,6}(?:阈值|截点|临界值)|(?:无需|不需要|不用).{0,6}校准)/i;
const ANALYZE_EVIDENCE_ACTIVITY_CONTEXT = /(?:\b(?:production|field)\s+deployments?\b|\bdeployments?\b|\bfield\s+trials?\b|\b(?:independent|third[- ]party)\s+replication\b|\b(?:independent|outside|external)\s+laborator(?:y|ies)\b|\b(?:external|other)\s+(?:teams?|groups?)\b|\breal[- ]world\s+use\b|\bdeployment\s+evidence\b|(?:生产|现场)?部署|现场试验|(?:独立|第三方)复现|(?:外部|其他)(?:实验室|团队|小组)|现实应用|部署证据)/i;
const ANALYZE_POSITIVE_EVIDENCE_OUTCOME = /(?:\b(?:successful|reliable|robust|effective|valid|worked|succeeded|reproduced|corroborated|supports?|confirmed|validated)\b|(?:奏效|有效|可靠|稳健|成功|复现|重复|佐证|支持|确认|验证))/i;
const ANALYZE_PROSPECTIVE_EVIDENCE_QUALIFIER = /(?:\b(?:if|whether|future|planned|proposed|needs?|requires?|(?:would|could|may|might|should|must)\s+(?:test|assess|check|evaluate)|to\s+(?:test|determine|assess|check|evaluate))\b|(?:若|如果|能否|是否|未来|计划|拟|待|需要|需|用于(?:测试|确定|评估|核查)))/i;
const ANALYZE_SOURCE_REVIEW_CONTEXT = /(?:\b(?:auditors?|audit|reviewers?|review)\b|(?:审计|审阅|复核))/i;
const ANALYZE_POSITIVE_SOURCE_REVIEW_OUTCOME = /(?:\b(?:deemed|found|considered|certified|approved|signed\s+off|trustworthy|reliable|credible|validated|verified)\b|(?:认定|确认|签字|批准|通过|可靠|可信|有效))/i;
const ANALYZE_LITERATURE_COMPLETION_CONTEXT = /(?:\b(?:broad|exhaustive|comprehensive|systematic|complete)\b.{0,24}\b(?:literature|survey|search|review)\b|\bscoping\s+review\b|\bsearching\s+the\s+literature\b|(?:广泛|全面|穷尽|系统|完整).{0,12}(?:文献|调查|检索|搜索|综述)|文献(?:检索|搜索|综述))/i;
const ANALYZE_LITERATURE_NOVELTY_OUTCOME = /(?:\bno\s+prior\b|\bunprecedented\b|\b(?:first|novel)\s+(?:method|approach|study|finding)\b|(?:无先例|前所未有|首个|首次|新颖))/i;
const ANALYZE_THRESHOLD_CONTEXT = /(?:\b(?:threshold|cutoff)\b|(?:阈值|截点|临界值))/i;
const ANALYZE_CALIBRATED_OUTCOME = /(?:\b(?:calibrated|derived|fitted|tuned|optimized|measured|fixed|established)\b|(?:校准|拟合|导出|优化|测定|确定))/i;
const ANALYZE_PROSPECTIVE_THRESHOLD_QUALIFIER = /(?:\b(?:needs?|requires?|must|should|has\s+to|is\s+to)\s+(?:still\s+)?(?:to\s+)?(?:be\s+)?$|(?:需要|需|必须|应当|待).{0,8}$)/i;

function validateDiscriminatingExperiment(value) {
  if (!(hasExactKeys(value, [
    'question', 'candidate_hypothesis', 'competitor_hypotheses',
    'intervention_or_measurement', 'primary_outcome', 'expected_outcomes',
    'confounds', 'minimum_data', 'procedure', 'decision_rule', 'falsification_rule',
    'stop_rule', 'threshold_basis', 'calibration_required',
  ]) && textWithin(value.question, 1, 400) &&
    textWithin(value.candidate_hypothesis, 1, 400) &&
    textList(value.competitor_hypotheses, 1, 4, 400) &&
    textWithin(value.intervention_or_measurement, 1, 700) &&
    textWithin(value.primary_outcome, 1, 240) &&
    objectList(value.expected_outcomes, 2, 6, validateExpectedOutcome) &&
    textList(value.confounds, 1, 6, 240) && textWithin(value.minimum_data, 1, 240) &&
    textList(value.procedure, 2, 8, 400) && textWithin(value.decision_rule, 1, 400) &&
    textWithin(value.falsification_rule, 1, 400) && textWithin(value.stop_rule, 1, 400) &&
    ANALYZE_EXPERIMENT_DECISION_COPY.has(value.decision_rule) &&
    ANALYZE_EXPERIMENT_FALSIFICATION_COPY.has(value.falsification_rule) &&
    ANALYZE_EXPERIMENT_STOP_COPY.has(value.stop_rule) &&
    value.threshold_basis === 'proposal' &&
    value.calibration_required === true)) return false;
  if (new Set(value.competitor_hypotheses).size !== value.competitor_hypotheses.length ||
      value.competitor_hypotheses.map(analyzeSemanticKey)
        .includes(analyzeSemanticKey(value.candidate_hypothesis))) return false;
  const competitorKeys = value.competitor_hypotheses.map(analyzeSemanticKey);
  if (new Set(competitorKeys).size !== competitorKeys.length) return false;
  const outcomeIds = value.expected_outcomes.map(item => item.hypothesis_id.toLocaleLowerCase('en-US'));
  const observations = value.expected_outcomes.map(item => analyzeSemanticKey(item.expected_observation));
  const roles = value.expected_outcomes.map(item => item.role);
  const rules = [value.decision_rule, value.falsification_rule, value.stop_rule];
  return new Set(outcomeIds).size === outcomeIds.length &&
    new Set(observations).size === observations.length && roles.filter(role => role === 'candidate').length === 1 &&
    roles.includes('competitor') && new Set(rules.map(analyzeSemanticKey)).size === rules.length &&
    rules.every(rule => !analyzeHasAnyView(rule, ANALYZE_UNFALSIFIABLE_RULE)) &&
    analyzeHasAnyView(value.decision_rule, ANALYZE_CONDITIONAL_RULE) &&
    analyzeHasAnyView(value.falsification_rule, ANALYZE_FALSIFICATION_RULE) &&
    analyzeHasAnyView(value.stop_rule, ANALYZE_STOP_RULE) &&
    (value.threshold_basis !== 'proposal' ||
      rules.every(rule =>
        !analyzeHasUnnegatedMatch(rule, ANALYZE_VALIDATED_THRESHOLD) &&
        !analyzeHasAssertedCalibratedThreshold(rule)));
}

function validateHowToCombine(value) {
  return hasExactKeys(value, [
    'steps', 'assumptions_to_verify', 'boundary_conditions', 'discriminating_experiment',
  ]) && textList(value.steps, 2, 6, 400) &&
    textList(value.assumptions_to_verify, 1, 6, 400) &&
    textList(value.boundary_conditions, 1, 6, 400) &&
    validateDiscriminatingExperiment(value.discriminating_experiment);
}

function validateResearchDirections(value) {
  return hasExactKeys(value, [
    'literature_status', 'status_explanation', 'search_questions',
    'source_types_to_check', 'suggested_references',
  ]) && value.literature_status === 'not_checked' &&
    textWithin(value.status_explanation, 1, 700) &&
    ANALYZE_LITERATURE_STATUS_COPY.has(value.status_explanation) &&
    analyzeHasAnyView(value.status_explanation, ANALYZE_LITERATURE_NOT_CHECKED_MARKER) &&
    !analyzeHasUnnegatedMatch(value.status_explanation, ANALYZE_POSITIVE_LITERATURE_STATE) &&
    !analyzeHasAssertedConceptPair(value.status_explanation, {
      contextPattern: ANALYZE_LITERATURE_COMPLETION_CONTEXT,
      outcomePattern: ANALYZE_LITERATURE_NOVELTY_OUTCOME,
      allowProspective: false,
    }) &&
    textList(value.search_questions, 2, 6, 400) &&
    textList(value.source_types_to_check, 1, 5, 240) &&
    Array.isArray(value.suggested_references) && value.suggested_references.length === 0;
}

function validateRiskAndLimit(value) {
  return hasExactKeys(value, [
    'risk_name', 'severity', 'explanation', 'condition', 'observable_signal', 'stop_rule',
  ]) && textWithin(value.risk_name, 1, 120) &&
    ['high', 'medium', 'low'].includes(value.severity) &&
    textWithin(value.explanation, 1, 700) && textWithin(value.condition, 1, 400) &&
    textWithin(value.observable_signal, 1, 400) && textWithin(value.stop_rule, 1, 400);
}

function validatePriorityAction(value) {
  if (!(hasExactKeys(value, [
    'rank', 'title', 'how', 'hypothesis_id', 'primary_metric', 'decision_rule',
    'stop_condition', 'expected_information', 'estimated_time', 'category',
    'threshold_basis', 'calibration_required',
  ]) && strictInteger(value.rank, 1, 3) && textWithin(value.title, 1, 80) &&
    textWithin(value.how, 1, 700) && textWithin(value.hypothesis_id, 1, 80) &&
    textWithin(value.primary_metric, 1, 240) && textWithin(value.decision_rule, 1, 400) &&
    textWithin(value.stop_condition, 1, 400) &&
    ANALYZE_ACTION_DECISION_COPY.has(value.decision_rule) &&
    ANALYZE_ACTION_STOP_COPY.has(value.stop_condition) &&
    textWithin(value.expected_information, 1, 400) && textWithin(value.estimated_time, 1, 80) &&
    ['measurement', 'diagnostic', 'experiment'].includes(value.category) &&
    value.threshold_basis === 'proposal' &&
    value.calibration_required === true)) return false;
  return analyzeSemanticKey(value.decision_rule) !== analyzeSemanticKey(value.stop_condition) &&
    !analyzeHasAnyView(value.decision_rule, ANALYZE_UNFALSIFIABLE_RULE) &&
    !analyzeHasAnyView(value.stop_condition, ANALYZE_UNFALSIFIABLE_RULE) &&
    (value.threshold_basis !== 'proposal' ||
      (!analyzeHasUnnegatedMatch(value.decision_rule, ANALYZE_VALIDATED_THRESHOLD) &&
       !analyzeHasAssertedCalibratedThreshold(value.decision_rule) &&
       !analyzeHasUnnegatedMatch(value.stop_condition, ANALYZE_VALIDATED_THRESHOLD) &&
       !analyzeHasAssertedCalibratedThreshold(value.stop_condition)));
}

function validateActionPlan(value) {
  if (!hasExactKeys(value, ['intro', 'if_time_short', 'this_week', 'review_trigger']) ||
      !textWithin(value.intro, 1, 700) ||
      !hasExactKeys(value.if_time_short, ['title', 'rationale']) ||
      !textWithin(value.if_time_short.title, 1, 80) ||
      !textWithin(value.if_time_short.rationale, 1, 400) ||
      !objectList(value.this_week, 2, 3, validatePriorityAction) ||
      !textWithin(value.review_trigger, 1, 400)) return false;
  if (value.if_time_short.title !== value.this_week[0].title) return false;
  return value.this_week.every((item, index) => item.rank === index + 1);
}

const ANALYZE_NON_PUBLIC_KEYS = new Set([
  'schema_version', 'evidence_level', 'generation_status', 'status', 'role',
  'source_ref_ids', 'source_ref_id', 'source_kind', 'record_id', 'support_status',
  'transfer_status', 'literature_status', 'severity', 'hypothesis_id', 'category',
  'threshold_basis', 'proposal_status', 'source_support',
  'source_limitations', 'status_explanation',
]);
const ANALYZE_SERVER_SOURCE_QUOTE_PATHS = new Set([
  'target_domain_intro.domain_name',
  'target_domain_intro.what_record_says',
  'target_domain_intro.corresponding_phenomenon.name',
  'target_domain_intro.corresponding_phenomenon.plain_description',
]);
const ANALYZE_NEGATABLE_CLAIM_PATTERNS = [
  /(?:已经|严格|完全|必然|确定|证实|证明|确认).{0,18}(?:同构|相同|一致|共享机制|成立)/i,
  /(?:本质上|实际上|就是).{0,12}(?:同一|相同|一致|同构|共享机制)/i,
  /(?:两者|它们|双方).{0,10}(?:同构|共享机制|机制一致|机制相同)/i,
  /(?:直接答案|照着做|保证成功|一定有效|必然有效|十拿九稳|稳操胜券)/i,
  /(?:保证|确保|肯定|必定|一定).{0,10}(?:成功|有效|适用|可迁移|能迁移|成立)/i,
  /(?:所有|全部|任何|每个|每种|无一例外).{0,30}(?:有效|奏效|适用|迁移|成立)/i,
  /(?:实验|研究|数据|结果|证据|测试|实证).{0,24}(?:证明|证实|确认|验证|显示|表明).{0,36}(?:有效|可靠|迁移|同构|共享机制|成立)/i,
  /\b(?:experiments?|studies?|data|results?|evidence|tests?)\s+(?:have\s+|has\s+)?(?:already\s+)?(?:shown?|demonstrated?|proved?|proven|confirmed?|validated?|established?)\b.{0,44}\b(?:works?|effective|transfers?|migrates?|reliable|stable|isomorphic|shared\s+mechanism|valid)\b/i,
  /\b(?:strictly|proven|confirmed|definitely|certainly)\s+(?:isomorphic|identical|the same)\b/i,
  /\b(?:same|shared)\s+(?:underlying\s+)?mechanism\b/i,
  /\b(?:direct answer|guaranteed|will certainly work|must work)\b/i,
  /\b(?:all|every|any)\b.{0,30}\b(?:works?|applies?|transfers?|effective|valid)\b/i,
  /\b(?:mapping|method|mechanism|approach|transfer).{0,40}(?:validated|verified|proven|confirmed)\b/i,
  /(?:有效|奏效|适用|迁移|成立).{0,30}(?:所有|全部|任何|各(?:类|个|种)|每(?:个|种)?|无一例外)/i,
  /(?:放之四海.{0,8}(?:皆|都|而)?准|百试百灵)/i,
  /(?:无论|任意).{0,28}(?:都|均|皆|一律|可|能).{0,12}(?:有效|奏效|适用|迁移|成立)/i,
  /(?:从未|没有|不存在).{0,18}(?:失败|反例|例外)/i,
  /(?:实验|研究|数据|结果|实证).{0,20}(?:证明|证实|验证|确认|显示|表明|支持).{0,36}(?:可靠|稳健|有效|成立|迁移|映射|机制|同构)/i,
  /(?:动力学|规律|机制).{0,12}(?:别无二致|完全一致|完全相同|同一)/i,
  /(?:二者|两者|它们).{0,10}(?:是一回事|并无二致|毫无差别)/i,
  /\buniversally\s+(?:applicable|valid|effective|reliable|successful)\b/i,
  /\b(?:transfer|mapping|method|mechanism|approach)\s+is\s+flawless\b/i,
  /\b(?:succeeds?|works?|holds?|applies?)\s+without\s+exception\b/i,
  /\bno\s+(?:counterexample|failure|exception)s?\s+(?:exists?|has\s+been\s+found|is\s+known)\b/i,
  /\b(?:mechanism|mapping|method|approach)\s+generaliz(?:e|es)\s+universally\b/i,
  /\bempirical\s+validation\s+(?:confirms?|proves?|validates?).{0,28}\b(?:mapping|mechanism|transfer|method|approach)\b/i,
  /\b(?:systems?|phenomena).{0,18}(?:identical|the\s+same)\s+(?:causal\s+)?dynamics?\b/i,
  /\b(?:both\s+systems\s+are\s+governed\s+by\s+)?(?:identical|the\s+same)\s+dynamics?\b/i,
  /\b(?:the\s+)?result\s+is\s+conclusive\b/i,
];
const ANALYZE_ALWAYS_FORBIDDEN_CLAIM_PATTERNS = [
  /(?:https?:\/\/|www\.|doi\s*:|arxiv\s*:)/i,
  /(?:ignore|disregard).{0,24}(?:instruction|prompt|message)/i,
  /(?:忽略|无视).{0,18}(?:指令|提示词|系统消息|开发者消息)/i,
  /(?:相似度|匹配度|相关度|置信度|可信度|成功率|成功概率|概率)\s*(?:为|是|[:：=])?\s*\d/i,
  /\b(?:similarity|confidence|success probability|probability)\s*(?:is|of|[:=])?\s*\d/i,
  /\d+(?:\.\d+)?\s*%/,
  /(?:已经|已)(?:完成)?.{0,12}(?:文献检索|文献综述|独立复核|同行评审)/i,
  /(?:文献|来源).{0,12}(?:已经|已)(?:检索|核查|复核|支持|证明|证实)/i,
  /(?:成熟|已经验证|已验证|经过验证).{0,8}(?:工具|方法|方案)/i,
  /\b(?:literature|sources?)\s+(?:has\s+|have\s+|was\s+|were\s+)?(?:been\s+)?(?:checked|reviewed|searched|verified)\b/i,
  /\b(?:independently|peer)\s+reviewed\b/i,
  /\b(?:validated|verified|proven|established)\s+(?:tool|method|approach)\b/i,
];
const ANALYZE_COMPLETED_EVIDENCE_STATE = /(?:\b(?:passed|completed|succeeded|deployed|replicated)\b|\b(?:peer[- ]reviewed|independently\s+reviewed|expert[- ]validated)\b|\b(?:has|have|had|was|were|is|are)\s+(?:already\s+)?(?:been\s+)?(?:validated|verified|confirmed|established|proven|demonstrated)\b|\bpeer\s+review.{0,24}\b(?:established|confirmed|validated|proved)\b|(?:已经|已|曾经|现已).{0,12}(?:通过|完成|成功|部署|复现|复制|验证|证实|确认|证明|建立)|(?:经过|得到).{0,8}(?:验证|证实|确认|证明|独立复核|同行评审)|(?:同行评审|独立(?:专家)?复核|专家确认).{0,12}(?:确认|通过|建立|证明|完成)|\b(?:transfer|method|approach|mapping|mechanism)\s+(?:was|were)\s+(?:successful|robust|reliable)\b|\b(?:method|approach|transfer|mapping|mechanism)\s+(?:worked|succeeded)\b.{0,40}\b(?:deployments?|trials?|cases?)\b|\bindependent\s+replication\s+(?:found|showed|confirmed|established)\b.{0,50}\b(?:robust|reliable|valid|successful|works?)\b|\bfield\s+trials?\s+(?:support|supported|confirm|confirmed|validate|validated)\b|(?:迁移|方法|方案|映射|机制).{0,32}(?:部署|试验|案例).{0,12}(?:均|都|已经|已|曾).{0,4}(?:奏效|有效|成功|可靠|稳健)|(?:独立复现|现场试验).{0,24}(?:支持|确认|表明).{0,12}(?:稳健|可靠|有效|成功))/i;
function claimHasClearNegation(text, index, matchedText) {
  const prefix = text.slice(Math.max(0, index - 80), index);
  return /(?:(?:没有|尚无)(?:研究|实验|数据|证据|结果)(?:能够|可以|足以)?|尚未|尚无|没有证据(?:表明|支持|显示)?|没有|无法|不能|不可|并非|而非|并不|未经|未|不|no\s+(?:data|study|evidence|result).{0,36}(?:shows?|shown|confirms?|confirmed)?|no evidence(?:\s+(?:shows?|supports?))?|(?:do|does|did) not (?:prove|confirm|show|imply)|cannot (?:prove|confirm|show|imply)|(?:we\s+)?(?:has|have) no|has not|have not|not|no)\s*$/i
    .test(prefix) || /\b(?:has|have|is|was|were)\s+not\s+(?:been\s+)?(?:empirically\s+)?/i
      .test(matchedText || '');
}

function collectAnalyzePublicTextFields(value, path, out) {
  const pathKey = path.join('.');
  if (ANALYZE_SERVER_SOURCE_QUOTE_PATHS.has(pathKey)) return;
  if (Array.isArray(value)) {
    value.forEach(item => collectAnalyzePublicTextFields(item, path, out));
  } else if (isPlainObject(value)) {
    Object.keys(value).forEach(child =>
      collectAnalyzePublicTextFields(value[child], [...path, child], out));
  } else if (typeof value === 'string' && path.length &&
      !ANALYZE_NON_PUBLIC_KEYS.has(path[path.length - 1])) {
    out.push({path, text: value});
  }
}

function analyzeClaimViews(text) {
  const base = text.normalize('NFKC');
  const linked = base.replace(/!?(?:\[([^\]]*)\])\([^)]*\)/g, '$1');
  const withoutTags = linked.replace(/<[^>]{0,200}>/g, '');
  const candidates = [
    base,
    withoutTags,
    withoutTags.replace(/(\w)\s*([*_~`]+)\s*(\w+)\s*\2/gu, '$1$3'),
    withoutTags.replace(/[\\*_~`#>|\[\](){}]/g, ''),
    withoutTags.replace(/\s*[\\*_~`#>|]+\s*/g, ''),
  ];
  const views = [];
  const seen = new Set();
  for (const candidate of candidates) {
    for (const value of [
      candidate,
      candidate.normalize('NFKD').replace(/\p{M}/gu, ''),
    ]) {
      const normalized = value.normalize('NFKC');
      if (!seen.has(normalized)) {
        seen.add(normalized);
        views.push(normalized);
      }
    }
  }
  return views;
}

function analyzeContainsMixedScriptConfusable(text) {
  const tokens = text.normalize('NFKC').match(/[\p{L}\p{M}]+/gu) || [];
  return tokens.some(token => Array.from(token).length >= 4 &&
    /\p{Script=Latin}/u.test(token) &&
    (/\p{Script=Cyrillic}/u.test(token) || /\p{Script=Greek}/u.test(token)));
}

function analyzeStateMatchIsProspective(clause, path, prefix, suffix) {
  if (ANALYZE_PRESUPPOSITIONAL_QUESTION.test(clause)) return false;
  return ANALYZE_QUESTION_STATE_QUALIFIER.test(clause) ||
    ANALYZE_PROSPECTIVE_ACTION_QUESTION.test(clause) ||
    ANALYZE_PROSPECTIVE_WH_PREFIX.test(prefix) ||
    ANALYZE_EXPLICIT_CHECK_PREFIX.test(prefix) ||
    ANALYZE_PURPOSE_PREFIX.test(prefix) ||
    ANALYZE_STATE_PROSPECTIVE_PREFIX.test(prefix) ||
    ANALYZE_STATE_PROSPECTIVE_SUFFIX.test(suffix);
}

function analyzeUnverifiedFactIsQualified(
  clause, path, prefix, suffix, localWindow, outcomeText, allowHypotheticalPath
) {
  const field = path.length ? path[path.length - 1] : '';
  const strippedClause = clause.trim();
  if (ANALYZE_PRESUPPOSITIONAL_QUESTION.test(strippedClause)) return false;
  if (ANALYZE_UNRECORDED_STATE_EXACT.test(strippedClause) ||
      ANALYZE_BOUND_EPISTEMIC_CLAUSE.test(strippedClause) ||
      ANALYZE_BOUND_NEGATED_EVIDENCE_CLAUSE.test(strippedClause) ||
      ANALYZE_GERUND_MODAL_CLAUSE.test(strippedClause)) {
    return true;
  }
  if (allowHypotheticalPath && ANALYZE_STRUCTURED_HYPOTHESIS_FIELD_KEYS.has(field) &&
      !ANALYZE_COMPLETED_TENSE_OUTCOME.test(localWindow)) {
    return true;
  }
  if (allowHypotheticalPath && ANALYZE_ACTION_IMPERATIVE_FIELD_KEYS.has(field) &&
      (!prefix.trim() || ANALYZE_ACTION_INSTRUCTION_PREFIX.test(prefix.slice(-80)))) {
    return true;
  }
  if (outcomeText === '解释' &&
      ANALYZE_NOMINAL_EXPLANATION_PREFIX.test(prefix.slice(-32)) &&
      ANALYZE_NOMINAL_EXPLANATION_SUFFIX.test(suffix.slice(0, 32))) {
    return true;
  }
  if (analyzeStateMatchIsProspective(clause, path, prefix, suffix)) return true;
  const left = `${prefix.slice(-160)}${outcomeText}`;
  const right = `${outcomeText}${suffix.slice(0, 160)}`;
  return ANALYZE_UNRECORDED_OUTCOME_LEFT.test(left) ||
    ANALYZE_EPISTEMIC_OUTCOME_LEFT.test(left) ||
    ANALYZE_EPISTEMIC_OUTCOME_RIGHT.test(right) ||
    ANALYZE_OUTCOME_BOUND_QUALIFIER_PREFIX.test(prefix.slice(-48)) ||
    ANALYZE_MODAL_EVIDENCE_SCOPE_PREFIX.test(prefix.slice(-120)) ||
    ANALYZE_OUTCOME_BOUND_CONDITIONAL_PREFIX.test(prefix.slice(-120)) ||
    (field === 'failure_signal' &&
      ANALYZE_FAILURE_SIGNAL_CONDITIONAL_SUFFIX.test(suffix.slice(0, 80))) ||
    (field === 'failure_signal' &&
      ANALYZE_FAILURE_SIGNAL_COMMAND_PREFIX.test(prefix.slice(-120))) ||
    (ANALYZE_CONDITIONAL_RULE_FIELD_KEYS.has(field) &&
      ANALYZE_RULE_COMMAND_CONDITIONAL_PREFIX.test(prefix.slice(-160))) ||
    ANALYZE_PURPOSE_PREFIX.test(prefix);
}

function analyzeHasAssertedUnverifiedFact(
  text, path, outcomePattern, contextPattern = null, allowHypotheticalPath = false
) {
  for (const clause of analyzeClaimClauses(text)) {
    const matcher = new RegExp(outcomePattern.source, outcomePattern.flags.includes('g')
      ? outcomePattern.flags : `${outcomePattern.flags}g`);
    let outcome;
    while ((outcome = matcher.exec(clause)) !== null) {
      const windowText = clause.slice(
        Math.max(0, outcome.index - 120),
        Math.min(clause.length, outcome.index + outcome[0].length + 120)
      );
      if (contextPattern && !contextPattern.test(windowText)) continue;
      const prefix = clause.slice(Math.max(0, outcome.index - 120), outcome.index);
      const suffix = clause.slice(
        outcome.index + outcome[0].length,
        Math.min(clause.length, outcome.index + outcome[0].length + 120)
      );
      if (analyzeUnverifiedFactIsQualified(
        clause, path, prefix, suffix, windowText, outcome[0], allowHypotheticalPath
      )) continue;
      return true;
    }
  }
  return false;
}

function analyzeHasAssertedStateMarker(text, pattern, path) {
  for (const clause of analyzeClaimClauses(text)) {
    const matcher = new RegExp(pattern.source, pattern.flags.includes('g')
      ? pattern.flags : `${pattern.flags}g`);
    let match;
    while ((match = matcher.exec(clause)) !== null) {
      const prefix = clause.slice(Math.max(0, match.index - 96), match.index);
      const suffix = clause.slice(
        match.index + match[0].length,
        Math.min(clause.length, match.index + match[0].length + 96)
      );
      const windowText = clause.slice(
        Math.max(0, match.index - 120),
        Math.min(clause.length, match.index + match[0].length + 120)
      );
      if (ANALYZE_NEGATED_COMPLETION_PREFIX.test(prefix) ||
          ANALYZE_NEGATED_COMPLETION_SUFFIX.test(suffix)) continue;
      if (ANALYZE_UNRECORDED_STATE_EXACT.test(clause.trim())) continue;
      if (analyzeStateMatchIsProspective(clause, path, prefix, suffix)) continue;
      return true;
    }
  }
  return false;
}

function analyzeHasAssertedCandidateStatePair(text, path, contextPattern, outcomePattern) {
  for (const clause of analyzeClaimClauses(text)) {
    const matcher = new RegExp(outcomePattern.source, outcomePattern.flags.includes('g')
      ? outcomePattern.flags : `${outcomePattern.flags}g`);
    let outcome;
    while ((outcome = matcher.exec(clause)) !== null) {
      const windowText = clause.slice(
        Math.max(0, outcome.index - 120),
        Math.min(clause.length, outcome.index + outcome[0].length + 120)
      );
      if (!contextPattern.test(windowText)) continue;
      const prefix = clause.slice(Math.max(0, outcome.index - 96), outcome.index);
      const suffix = clause.slice(
        outcome.index + outcome[0].length,
        Math.min(clause.length, outcome.index + outcome[0].length + 96)
      );
      if (ANALYZE_NEGATED_COMPLETION_PREFIX.test(prefix) ||
          ANALYZE_NEGATED_COMPLETION_SUFFIX.test(suffix)) continue;
      if (analyzeStateMatchIsProspective(clause, path, prefix, suffix)) continue;
      return true;
    }
  }
  return false;
}

function analyzePublicTextCrossesBoundary(text, path = []) {
  if (analyzeContainsMixedScriptConfusable(text)) return true;
  return analyzeClaimViews(text).some(normalized => {
    const negatableCrossed = ANALYZE_NEGATABLE_CLAIM_PATTERNS.some(pattern => {
      const match = pattern.exec(normalized);
      return !!match && !claimHasClearNegation(normalized, match.index, match[0]);
    });
    return negatableCrossed ||
      ANALYZE_ASSERTED_NEGATIVE_EVIDENCE_RESULT.test(normalized) ||
      analyzeHasAssertedStateMarker(normalized, ANALYZE_COMPLETED_EVIDENCE_STATE, path) ||
      analyzeHasAssertedCandidateStatePair(
        normalized, path, ANALYZE_EVIDENCE_ACTIVITY_CONTEXT, ANALYZE_POSITIVE_EVIDENCE_OUTCOME
      ) ||
      analyzeHasAssertedCandidateStatePair(
        normalized, path, ANALYZE_LITERATURE_COMPLETION_CONTEXT,
        ANALYZE_LITERATURE_NOVELTY_OUTCOME
      ) ||
      ANALYZE_ALWAYS_FORBIDDEN_CLAIM_PATTERNS.some(pattern => pattern.test(normalized));
  });
}

function publicClaimsAreCandidateOnly(report) {
  const fields = [];
  const generated = {};
  ['schema_version', 'evidence_level', 'generation_status', ...DEEP_REPORT_SECTION_KEYS]
    .forEach(key => { generated[key] = report[key]; });
  // The structured flattener excludes only four exact server-owned quotation
  // paths. Every other model-writable narrative leaf shares one state policy.
  collectAnalyzePublicTextFields(generated, [], fields);
  const texts = fields.map(field => field.text);
  if (texts.reduce((total, text) => total + Array.from(text).length, 0) > ANALYZE_MAX_PUBLIC_CHARS) {
    return false;
  }
  if (fields.some(({path, text}) => analyzePublicTextCrossesBoundary(text, path))) return false;
  if (fields.some(({path, text}) =>
    ANALYZE_NEGATED_NEGATIVE_CANDIDATE_STATE.test(text) ||
    analyzeHasAssertedUnverifiedFact(
      text, path, ANALYZE_LITERATURE_FACT_ASSERTION
    ) || analyzeHasAssertedUnverifiedFact(
      text, path, ANALYZE_LITERATURE_ATTRIBUTION_OUTCOME,
      ANALYZE_LITERATURE_ATTRIBUTION_CONTEXT
    ) || ANALYZE_INVENTED_CITATION_SHAPE.test(text) ||
    analyzeHasAssertedCandidateStatePair(
      text, path, ANALYZE_METHOD_ARTIFACT_CONTEXT, ANALYZE_COMPLETED_METHOD_STATE
    ) || analyzeHasAssertedCandidateStatePair(
      text, path, ANALYZE_OPERATIONAL_RESULT_CONTEXT, ANALYZE_POSITIVE_OPERATIONAL_STATE
    ) || analyzeHasAssertedStateMarker(
      text, ANALYZE_COMPLETED_EVIDENCE_ARTIFACT, path
    ) || analyzeHasAssertedUnverifiedFact(
      text, path, ANALYZE_EXTERNAL_ADOPTION_STATE, null, true
    ) || analyzeHasAssertedUnverifiedFact(
      text, path, ANALYZE_UNSUPPORTED_SOURCE_ATTRIBUTION, ANALYZE_SOURCE_ATTRIBUTION_CONTEXT
    ) || analyzeHasAssertedUnverifiedFact(
      text, path, ANALYZE_COMPLETED_EMPIRICAL_OUTCOME, null, true
    ) || analyzeHasAssertedUnverifiedFact(
      text, path, ANALYZE_EMPIRICAL_EVIDENCE_OUTCOME, null, true
    ) || analyzeHasAssertedUnverifiedFact(
      text, path, ANALYZE_CAUSAL_MECHANISM_ASSERTION, null, true
    ))) return false;
  const punctuation = /[。！？；.!?;：:]$/u;
  for (let index = 0; index + 1 < texts.length; index += 1) {
    const left = texts[index].trimEnd();
    const right = texts[index + 1].trimStart();
    if (!punctuation.test(left) && !/^[。！？；.!?;：:]/u.test(right) &&
        analyzePublicTextCrossesBoundary(left.slice(-80) + right.slice(0, 80))) return false;
  }
  return true;
}

function validateAnalyzeReportLanguage(report, lang) {
  const copy = ANALYZE_LANGUAGE_BOUND_COPY[lang];
  if (!copy) return false;
  const experiment = report.how_to_combine.discriminating_experiment;
  return report.target_domain_intro.source_limitations.length === 1 &&
    report.target_domain_intro.source_limitations[0] === copy.sourceLimitation &&
    report.research_directions.status_explanation === copy.literatureStatus &&
    experiment.decision_rule === copy.experimentDecision &&
    experiment.falsification_rule === copy.experimentFalsification &&
    experiment.stop_rule === copy.experimentStop &&
    report.action_plan.this_week.every(action =>
      action.decision_rule === copy.actionDecision && action.stop_condition === copy.actionStop);
}

function validateAnalyzeReportEnvelope(report, expectedMeta) {
  const expected = [
    'schema_version', 'evidence_level', 'generation_status', ...DEEP_REPORT_SECTION_KEYS,
    'source_binding', 'report_boundary', 'source_refs',
  ];
  if (!hasExactKeys(report, expected) || report.schema_version !== 'deep-analysis-report-v2' ||
      report.evidence_level !== 'candidate' || report.generation_status !== 'validated' ||
      !validateSharedStructure(report.shared_structure) ||
      !validateProblemBreakdown(report.your_problem_breakdown) ||
      !validateTargetDomainIntro(report.target_domain_intro) ||
      !validateStructuralMapping(report.structural_mapping) ||
      !objectList(report.borrowable_insights, 1, 4, validateBorrowableInsight) ||
      !validateHowToCombine(report.how_to_combine) ||
      !validateResearchDirections(report.research_directions) ||
      !objectList(report.risks_and_limits, 1, 6, validateRiskAndLimit) ||
      !validateActionPlan(report.action_plan) || !validateSourceBinding(report.source_binding) ||
      !validateReportBoundary(report.report_boundary) || !validateSourceRefs(report.source_refs)) {
    return false;
  }
  if (report.your_problem_breakdown.fingerprint_revision !==
      report.source_binding.fingerprint_revision) return false;
  const refsById = new Map(report.source_refs.map(item => [item.source_ref_id, item]));
  const referenced = new Set();
  collectSourceRefIds(report, '', referenced);
  if (!referenced.size || [...referenced].some(id => !refsById.has(id))) return false;
  const sourceRefs = report.source_refs.filter(
    item => item.record_id === report.source_binding.source_kb_id
  );
  if (sourceRefs.length !== 1) return false;
  if (report.source_binding.target_kind === 'kb' && report.source_refs.filter(
    item => item.record_id === report.source_binding.target_kb_id
  ).length !== 1) return false;
  const sourceRefId = sourceRefs[0].source_ref_id;
  const sourceDerived = [
    report.target_domain_intro.corresponding_phenomenon.source_ref_ids,
  ];
  if (sourceDerived.some(ids => ids.length !== 1 || ids[0] !== sourceRefId)) return false;
  if (expectedMeta && (!deepEqualCanonical(report.source_binding, expectedMeta.source_binding) ||
      !deepEqualCanonical(report.source_refs, expectedMeta.source_refs) ||
      !deepEqualCanonical(report.report_boundary, expectedMeta.report_boundary))) return false;
  try {
    if (canonicalAnalyzeJson(report).length > ANALYZE_MAX_CANONICAL_CHARS) return false;
  } catch (_) { return false; }
  const expectedLang = expectedMeta && expectedMeta.source_binding
    ? expectedMeta.source_binding.lang : null;
  return (!expectedMeta || (expectedMeta.lang === expectedLang &&
    validateAnalyzeReportLanguage(report, expectedLang))) && publicClaimsAreCandidateOnly(report);
}

function normalizeAnalyzeRequestText(value, maximum, allowLayout) {
  if (typeof value !== 'string') return null;
  let normalized = value.normalize('NFKC');
  if (ANALYZE_CONTROL_RE.test(normalized.replace(allowLayout ? /[\t\n\r]/g : /$^/, ''))) {
    return null;
  }
  normalized = allowLayout ? normalized.trim().split(/\s+/u).join(' ') : normalized.trim();
  const length = Array.from(normalized).length;
  return length >= 1 && length <= maximum ? normalized : null;
}

function normalizeAnalyzeFingerprint(value, query) {
  if (!hasOnlyKeys(value, [
    'source_query', 'summary', 'variables', 'constraints', 'unknowns', 'revision',
  ]) || !Object.prototype.hasOwnProperty.call(value, 'source_query') ||
      !Object.prototype.hasOwnProperty.call(value, 'summary')) return null;
  const sourceQuery = normalizeAnalyzeRequestText(value.source_query, 8000, true);
  const summary = normalizeAnalyzeRequestText(value.summary, 1000, true);
  if (sourceQuery !== query || !summary || Array.from(summary).length < 8) return null;
  const normalized = { source_query: sourceQuery, summary };
  for (const key of ['variables', 'constraints', 'unknowns']) {
    const items = value[key] === undefined ? [] : value[key];
    if (!Array.isArray(items) || items.length > 12) return null;
    normalized[key] = items.map(item => normalizeAnalyzeRequestText(item, 120, false));
    if (normalized[key].some(item => item === null)) return null;
  }
  const revision = value.revision === undefined ? 1 : value.revision;
  if (!strictInteger(revision, 1, 1000)) return null;
  normalized.revision = revision;
  return normalized;
}

function normalizeAnalyzeRequest(value) {
  if (!hasOnlyKeys(value, [
    'b_id', 'a_id', 'text_a', 'lang', 'persist', 'anon_id', 'fingerprint',
    'origin_discovery_id', 'origin_contract_version',
  ]) || !ANALYZE_REQUEST_ID_RE.test(value.b_id || '')) return null;
  const lang = value.lang === undefined ? 'zh' : value.lang;
  const persist = value.persist === undefined ? 0 : value.persist;
  if (!['zh', 'en'].includes(lang) || !strictInteger(persist, 0, 1)) return null;
  const hasQuery = value.text_a !== undefined && value.text_a !== null;
  const hasSourceId = value.a_id !== undefined && value.a_id !== null;
  if (hasQuery === hasSourceId) return null;
  const normalized = { b_id: value.b_id, lang, persist };
  if (hasQuery) {
    const query = normalizeAnalyzeRequestText(value.text_a, 8000, true);
    if (!query) return null;
    normalized.text_a = query;
    if (value.fingerprint !== undefined && value.fingerprint !== null) {
      normalized.fingerprint = normalizeAnalyzeFingerprint(value.fingerprint, query);
      if (!normalized.fingerprint) return null;
    }
  } else {
    if (!ANALYZE_REQUEST_ID_RE.test(value.a_id || '') || value.fingerprint != null) return null;
    normalized.a_id = value.a_id;
  }
  if (value.anon_id !== undefined && value.anon_id !== null) {
    const anonId = normalizeAnalyzeRequestText(value.anon_id, 128, false);
    if (!anonId || persist !== 1) return null;
    normalized.anon_id = anonId;
  }
  const hasOriginId = value.origin_discovery_id !== undefined && value.origin_discovery_id !== null;
  const hasOriginVersion = value.origin_contract_version !== undefined &&
    value.origin_contract_version !== null;
  if (hasOriginId !== hasOriginVersion || (hasOriginId && hasQuery)) return null;
  if (hasOriginId) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(value.origin_discovery_id) ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(value.origin_contract_version)) return null;
    normalized.origin_discovery_id = value.origin_discovery_id;
    normalized.origin_contract_version = value.origin_contract_version;
  }
  return normalized;
}

function projectedAnalyzeFingerprint(value) {
  if (!value) return null;
  return {
    summary: value.summary,
    variables: value.variables.slice(),
    constraints: value.constraints.slice(),
    unknowns: value.unknowns.slice(),
    revision: value.revision,
    provenance: 'user_confirmed',
  };
}

function validateAnalyzeOrigin(value, request) {
  if (!request.origin_discovery_id) return value === null;
  return hasExactKeys(value, [
    'discovery_id', 'contract_version', 'candidate_family_id', 'tier', 'pair',
    'origin_content_id',
  ]) && value.discovery_id === request.origin_discovery_id &&
    value.contract_version === request.origin_contract_version &&
    textWithin(value.candidate_family_id, 1, 128) &&
    ['priority_review', 'candidate_pool'].includes(value.tier) &&
    hasExactKeys(value.pair, ['a_id', 'b_id']) && value.pair.a_id === request.a_id &&
    value.pair.b_id === request.b_id && /^origin-[0-9a-f]{24}$/.test(value.origin_content_id || '');
}

function validateAnalyzeEvidenceEnvelope(value, source, lang) {
  const candidateLabel = source.name == null || String(source.name).trim() === ''
    ? null : Array.from(String(source.name).trim()).slice(0, 1000).join('');
  const expected = {
    schema_version: 'evidence-envelope-v1',
    evidence_level: 'candidate',
    candidate: {
      status: 'recorded', kind: 'analysis_candidate', label: candidateLabel, score: null,
    },
    source: {
      status: 'recorded', kind: 'internal_kb', label: 'Structural internal KB candidate',
      url: null, source_review: null,
    },
    result: {
      status: 'not_recorded', provenance: 'NOT_TESTED', verdict: 'NOT_TESTED', summary: null,
    },
    independence: {status: 'not_recorded', kind: 'not_recorded', summary: null},
    counterexamples: {
      status: 'gap_recorded',
      summary: lang === 'en'
        ? 'The report must propose falsifiers; no completed falsification result is bound.'
        : '报告必须提出证伪条件；当前未绑定任何已完成的证伪结果。',
    },
    ledger: {
      status: 'not_recorded', claim_id: null, version: null, recorded_at: null,
      artifact_sha256: null, url: null,
    },
  };
  return deepEqualCanonical(value, expected);
}

function sourceSnapshotFromMeta(meta) {
  const source = meta.a;
  const bounded = (value, maximum, fallback) => {
    const text = value == null ? '' : String(value).trim();
    return Array.from(text || fallback).slice(0, maximum).join('');
  };
  return {
    domain_name: bounded(source.domain, 120, 'Internal source record'),
    what_record_says: bounded(
      source.description, 700, 'The internal source record contains no public description.'
    ),
    phenomenon_name: bounded(source.name, 120, 'Internal source record'),
    plain_description: bounded(
      source.description, 1200, 'The internal source record contains no public description.'
    ),
  };
}

async function validateAnalyzeMetaEnvelope(meta, rawRequest, cryptoImpl) {
  const request = normalizeAnalyzeRequest(rawRequest);
  if (!request || !hasExactKeys(meta, [
    'generation_id', 'a', 'b', 'is_query_mode', 'evidence', 'fingerprint', 'model',
    'lang', 'artifact_id', 'prompt_version', 'schema_version', 'report_boundary',
    'source_binding', 'source_refs', 'origin_candidate',
  ]) || !ANALYZE_GENERATION_RE.test(meta.generation_id || '') ||
      !isPlainObject(meta.a) || !isPlainObject(meta.b) || !isPlainObject(meta.evidence) ||
      meta.lang !== request.lang || !textWithin(meta.model, 1, 120) ||
      !textWithin(meta.artifact_id, 1, 120) || meta.prompt_version !== 'deep-report-v2' ||
      meta.schema_version !== 'deep-analysis-report-v2' ||
      !validateReportBoundary(meta.report_boundary) ||
      !validateSourceBinding(meta.source_binding) || !validateSourceRefs(meta.source_refs) ||
      !validateAnalyzeOrigin(meta.origin_candidate, request) ||
      !validateAnalyzeEvidenceEnvelope(meta.evidence, meta.a, request.lang)) return false;
  const binding = meta.source_binding;
  if (binding.lang !== request.lang || binding.model_id !== meta.model ||
      binding.kb_artifact_id !== meta.artifact_id ||
      binding.prompt_version !== meta.prompt_version ||
      binding.schema_version !== meta.schema_version) return false;
  const queryMode = Object.prototype.hasOwnProperty.call(request, 'text_a');
  if (meta.is_query_mode !== queryMode || String(meta.a.id || '') !==
      (queryMode ? request.b_id : request.a_id) || String(meta.b.id || '') !==
      (queryMode ? '__query__' : request.b_id) || binding.source_kb_id !==
      (queryMode ? request.b_id : request.a_id)) return false;
  if (queryMode) {
    if (binding.target_kind !== 'query' || binding.target_kb_id !== null ||
        meta.b.description !== request.text_a || meta.b.original_query !== request.text_a) return false;
  } else if (binding.target_kind !== 'kb' || binding.target_kb_id !== request.b_id ||
      binding.query_binding !== null) return false;
  const projectedFingerprint = projectedAnalyzeFingerprint(request.fingerprint);
  if (!deepEqualCanonical(meta.fingerprint, projectedFingerprint)) return false;
  if (projectedFingerprint) {
    if (binding.fingerprint_revision !== projectedFingerprint.revision ||
        binding.fingerprint_sha256 !== await sha256CanonicalAnalyzeJson(
          projectedFingerprint, cryptoImpl
        )) return false;
  } else if (binding.fingerprint_revision !== null || binding.fingerprint_sha256 !== null) {
    return false;
  }
  const sourceRecord = {};
  for (const key of ['id', 'name', 'domain', 'type_id', 'description']) {
    sourceRecord[key] = meta.a[key] === undefined ? null : meta.a[key];
  }
  if (binding.source_record_sha256 !== await sha256CanonicalAnalyzeJson(sourceRecord, cryptoImpl)) {
    return false;
  }
  if (meta.source_refs.length !== (queryMode ? 1 : 2) ||
      meta.source_refs[0].record_id !== binding.source_kb_id ||
      meta.source_refs[0].source_ref_id !== `kb:${binding.source_kb_id}`) return false;
  const expectedRef = (record, target) => {
    const rawLabel = record.name || record.id || 'Internal KB record';
    const label = Array.from(String(rawLabel)).slice(0, 240).join('');
    const limitations = target
      ? (request.lang === 'en'
        ? 'Internal target record used only for comparison; it does not show that the mechanisms are the same.'
        : '仅作为比较目标的内部记录；不能据此判断两边机制相同。')
      : (request.lang === 'en'
        ? 'Internal candidate record only; it does not establish mechanism, causality, transfer success, or independent review.'
        : '仅为内部候选记录；不证明机制、因果、迁移有效或独立复核。');
    return {label, limitations};
  };
  const expectedSourceRef = expectedRef(meta.a, false);
  if (meta.source_refs[0].label !== expectedSourceRef.label ||
      meta.source_refs[0].limitations !== expectedSourceRef.limitations) return false;
  if (!queryMode && (meta.source_refs[1].record_id !== request.b_id ||
      meta.source_refs[1].source_ref_id !== `kb:${request.b_id}`)) return false;
  if (!queryMode) {
    const expectedTargetRef = expectedRef(meta.b, true);
    if (meta.source_refs[1].label !== expectedTargetRef.label ||
        meta.source_refs[1].limitations !== expectedTargetRef.limitations) return false;
  }
  return true;
}

const ANALYZE_SECTION_VALIDATORS = {
  shared_structure: validateSharedStructure,
  your_problem_breakdown: validateProblemBreakdown,
  target_domain_intro: validateTargetDomainIntro,
  structural_mapping: validateStructuralMapping,
  borrowable_insights: value => objectList(value, 1, 4, validateBorrowableInsight),
  how_to_combine: validateHowToCombine,
  research_directions: validateResearchDirections,
  risks_and_limits: value => objectList(value, 1, 6, validateRiskAndLimit),
  action_plan: validateActionPlan,
};

function validateAnalyzeReceipt(value, meta) {
  return hasExactKeys(value, [
    'generation_id', 'report_sha256', 'schema_version', 'from_cache',
  ]) && value.generation_id === meta.generation_id &&
    ANALYZE_SHA256_RE.test(value.report_sha256 || '') &&
    value.schema_version === 'deep-analysis-report-v2' && typeof value.from_cache === 'boolean';
}

function validateAnalyzeProgress(value, lastByAttempt) {
  if (!isPlainObject(value) || !['generating', 'retrying', 'validating'].includes(value.stage) ||
      !strictInteger(value.attempt, 1, 2)) return false;
  if (value.stage === 'generating' || value.stage === 'retrying') {
    if (!hasExactKeys(value, ['stage', 'attempt']) ||
        (value.stage === 'generating' && value.attempt !== 1) ||
        (value.stage === 'retrying' && value.attempt !== 2) ||
        lastByAttempt.has(value.attempt) ||
        (value.stage === 'retrying' && !lastByAttempt.has(1))) return false;
    lastByAttempt.set(value.attempt, 0);
    return true;
  }
  if (!hasExactKeys(value, ['stage', 'attempt', 'received_chars']) ||
      !strictInteger(value.received_chars, 0, ANALYZE_MAX_CANONICAL_CHARS)) return false;
  const previous = lastByAttempt.get(value.attempt);
  if (previous === undefined || value.received_chars < previous) return false;
  lastByAttempt.set(value.attempt, value.received_chars);
  return true;
}

function validateAnalyzePersisted(value, request, meta, receipt) {
  if (request.persist !== 1 || !hasExactKeys(value, [
    'id', 'share_url', 'created_at', 'is_partial', 'origin_candidate',
    'generation_id', 'report_sha256',
  ]) || !ANALYZE_REPORT_ID_RE.test(value.id || '') ||
      typeof value.share_url !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(value.created_at || '') ||
      !Number.isFinite(Date.parse(value.created_at)) || value.is_partial !== false ||
      value.generation_id !== receipt.generation_id ||
      value.report_sha256 !== receipt.report_sha256 ||
      !deepEqualCanonical(value.origin_candidate, meta.origin_candidate)) return false;
  try {
    const current = new URL(window.location.href);
    const share = new URL(value.share_url, current);
    const match = share.pathname.match(/^\/report\/share\/([0-9a-f]{32})$/);
    return share.origin === current.origin && share.username === '' && share.password === '' &&
      !!match && ANALYZE_SHARE_TOKEN_RE.test(match[1]) &&
      share.search === '' && share.hash === '';
  } catch (_) { return false; }
}

function sourceSnapshotMatchesReport(report, meta) {
  const snapshot = sourceSnapshotFromMeta(meta);
  const intro = report.target_domain_intro;
  return intro.domain_name === snapshot.domain_name &&
    intro.what_record_says === snapshot.what_record_says &&
    intro.corresponding_phenomenon.name === snapshot.phenomenon_name &&
    intro.corresponding_phenomenon.plain_description === snapshot.plain_description;
}

function createAnalyzeTrustState(rawRequest, cryptoImpl) {
  const request = normalizeAnalyzeRequest(rawRequest);
  if (!request) throw new TypeError('Analyze request context is invalid');
  let meta = null;
  let receipt = null;
  let persisted = null;
  let completed = false;
  let failed = false;
  const sections = Object.create(null);
  let nextSectionIndex = 0;
  const progressByAttempt = new Map();

  const reject = (message) => {
    failed = true;
    throw new Error(message);
  };

  return {
    async ingest(type, value) {
      if (failed) throw new Error('Analyze trust state has failed');
      if (completed) throw new Error('Analyze terminal event was duplicated');
      if (type === 'error') {
        if (receipt || nextSectionIndex || persisted) return reject('error arrived after report release');
        if (!hasOnlyKeys(value, ['code', 'message', 'retryable']) ||
            !textWithin(value.message, 1, 1200) || typeof value.retryable !== 'boolean' ||
            (value.code !== undefined && !ANALYZE_ID_RE.test(value.code))) {
          return reject('invalid Analyze error envelope');
        }
        completed = true;
        return { type: 'error', error: value };
      }
      if (type === 'meta') {
        if (meta || receipt || nextSectionIndex) return reject('meta was duplicated or out of order');
        if (!await validateAnalyzeMetaEnvelope(value, request, cryptoImpl)) {
          return reject('meta is not bound to the request');
        }
        meta = value;
        return { type: 'meta', meta };
      }
      if (!meta) return reject('event arrived before meta');
      if (type === 'generation_progress') {
        if (receipt || !validateAnalyzeProgress(value, progressByAttempt)) {
          return reject('progress event is invalid or out of order');
        }
        return { type: 'generation_progress', progress: value };
      }
      if (type === 'report_validated') {
        if (receipt || nextSectionIndex || persisted || !validateAnalyzeReceipt(value, meta)) {
          return reject('validation receipt is invalid or duplicated');
        }
        receipt = value;
        return { type: 'report_validated', receipt };
      }
      if (!receipt) return reject('report content arrived before validation receipt');
      if (type === 'section') {
        if (persisted || !hasExactKeys(value, ['key', 'data'])) {
          return reject('section is invalid or arrived after persistence');
        }
        const expectedKey = DEEP_REPORT_SECTION_KEYS[nextSectionIndex];
        if (value.key !== expectedKey || !ANALYZE_SECTION_VALIDATORS[value.key](value.data)) {
          return reject('section is invalid, duplicated, or out of order');
        }
        sections[value.key] = value.data;
        nextSectionIndex += 1;
        return { type: 'section', key: value.key, data: value.data };
      }
      if (type === 'persisted') {
        if (persisted || nextSectionIndex !== DEEP_REPORT_SECTION_KEYS.length ||
            !validateAnalyzePersisted(value, request, meta, receipt)) {
          return reject('persisted event is invalid, duplicated, or out of order');
        }
        persisted = value;
        return { type: 'persisted', persisted };
      }
      if (type === 'done') {
        if (!hasExactKeys(value, ['generation_id', 'report_sha256', 'report', 'from_cache']) ||
            nextSectionIndex !== DEEP_REPORT_SECTION_KEYS.length ||
            value.generation_id !== receipt.generation_id ||
            value.report_sha256 !== receipt.report_sha256 ||
            value.from_cache !== receipt.from_cache ||
            !validateAnalyzeReportEnvelope(value.report, meta) ||
            !sourceSnapshotMatchesReport(value.report, meta) ||
            DEEP_REPORT_SECTION_KEYS.some(key =>
              !deepEqualCanonical(sections[key], value.report[key])
            )) return reject('done event failed report binding');
        const computed = await sha256CanonicalAnalyzeJson(value.report, cryptoImpl);
        if (computed !== receipt.report_sha256) return reject('report hash mismatch');
        completed = true;
        return { type: 'done', report: value.report, persisted, meta };
      }
      return reject('unknown Analyze event');
    },
  };
}

function resetAnalyzeResultState() {
  window._finalReport = null;
  window._persistedReport = null;
  window._analyzeMeta = null;
  _tldrShownLogged = false;
  setAnalyzeReportStageState('loading');
  clearStreamPreview();
  const share = document.getElementById('analyze-share-bar');
  if (share) share.hidden = true;
  const tldr = document.getElementById('analyze-tldr');
  if (tldr) { tldr.hidden = true; tldr.replaceChildren(); }
  const brief = document.getElementById('decision-brief-root');
  if (brief) brief.replaceChildren();
  const sections = document.getElementById('analyze-sections');
  if (sections) sections.replaceChildren();
  const progress = document.getElementById('analyze-progress');
  if (progress) progress.replaceChildren();
}

function setAnalyzeReportStageState(state) {
  const stage = document.getElementById('analyze-report-stage');
  if (!stage) return;
  const ready = state === 'ready';
  stage.classList.toggle('analyze-report-stage--ready', ready);
  stage.dataset.state = state;
  stage.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
  const loading = document.getElementById('analyze-loading');
  if (loading) {
    const failed = state === 'error';
    loading.setAttribute('role', failed ? 'alert' : 'status');
    loading.setAttribute('aria-live', failed ? 'assertive' : 'polite');
  }
}

function decodeAnalyzeEventBlock(block) {
  let eventName = 'message';
  const data = [];
  block.split(/\r?\n/).forEach((line) => {
    if (line.startsWith('event:')) eventName = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  });
  return { type: eventName, data: data.join('\n') };
}

const ANALYZE_EVENT_TYPES = new Set([
  'meta', 'generation_progress', 'report_validated', 'section', 'persisted', 'done', 'error',
]);

/**
 * Minimal EventSource-compatible facade backed by POST + ReadableStream.
 * Sensitive inputs stay in the JSON body and never enter URL/history/referrer.
 */
function openAnalyzeStream(payload) {
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
      if (_activeAnalyzeStream === connection) _activeAnalyzeStream = null;
    },
  };

  const emit = (type, data) => {
    (listeners.get(type) || []).slice().forEach((handler) => {
      try {
        const result = handler({ data });
        if (result && typeof result.then === 'function') {
          result.catch(transportError);
        }
      } catch (error) {
        console.error('[analyze] stream event handler failed');
        transportError(error);
      }
    });
  };
  const transportError = (error) => {
    if (closed) return;
    if (typeof connection.onerror === 'function') connection.onerror(error);
  };

  // Defer the request one microtask so streamAnalysis can register every
  // event listener before a mocked/fixture response emits its first chunk.
  Promise.resolve().then(async () => {
    timeoutId = setTimeout(() => {
      if (closed || terminal) return;
      controller.abort();
      transportError(new Error(T('page.analyze.error_timeout', '生成超时，请稍后重试')));
    }, 300000);
    try {
      const response = await fetch('/api/analyze/stream', {
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
        const detail = problem && (problem.message || problem.detail);
        emit('error', JSON.stringify({
          message: typeof detail === 'string' ? detail : `HTTP ${response.status}`,
          retryable: response.status >= 500,
        }));
        terminal = true;
        return;
      }
      if (!response.body) throw new Error('Streaming response is unavailable');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let receivedBytes = 0;
      while (!closed) {
        const part = await reader.read();
        receivedBytes += part.value ? part.value.byteLength : 0;
        if (receivedBytes > ANALYZE_MAX_STREAM_BYTES) {
          throw new Error('Analyze stream exceeded its byte limit');
        }
        buffer += decoder.decode(part.value || new Uint8Array(), { stream: !part.done });
        let boundary;
        while ((boundary = buffer.search(/\r?\n\r?\n/)) !== -1) {
          const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)[0];
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + separator.length);
          if (!block.trim()) continue;
          const event = decodeAnalyzeEventBlock(block);
          if (terminal || !ANALYZE_EVENT_TYPES.has(event.type)) {
            throw new Error('Analyze stream protocol violation');
          }
          if (event.type === 'done' || event.type === 'error') terminal = true;
          emit(event.type, event.data);
        }
        if (part.done) {
          if (buffer.trim()) throw new Error('Analyze stream ended with a partial event');
          break;
        }
      }
      if (!closed && !terminal) throw new Error('Stream ended before completion');
    } catch (error) {
      if (!closed && !(error && error.name === 'AbortError')) transportError(error);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }
  });

  return connection;
}

function commitAnalyzeReportForDisplay(report, persisted, render) {
  window._finalReport = report;
  window._persistedReport = persisted || null;
  try {
    render();
  } catch (error) {
    resetAnalyzeResultState();
    throw error;
  }
}

// === Main streaming loop ===
function streamAnalysis(payload) {
  if (_activeAnalyzeStream) _activeAnalyzeStream.close();
  const generation = ++_analyzeGeneration;
  resetAnalyzeResultState();
  _lastAnalyzePayload = JSON.parse(JSON.stringify(payload || {}));
  let trust = null;
  try { trust = createAnalyzeTrustState(payload); } catch (_) {
    renderStreamError({
      message: T('page.analyze.error_protocol', '报告校验协议异常，未展示正文。'),
      retryable: false,
    });
    return;
  }
  const es = openAnalyzeStream(payload);
  _activeAnalyzeStream = es;

  const receivedKeys = new Set();
  let terminalHandled = false;
  let protocolQueue = Promise.resolve();
  const current = () => analyzeGenerationMatches(generation, _analyzeGeneration);
  let stopLoadingTimer = null;

  const stopTimers = () => {
    if (stopLoadingTimer) { stopLoadingTimer(); stopLoadingTimer = null; }
  };
  const protocolFailure = (message) => {
    if (!current() || terminalHandled) return;
    terminalHandled = true;
    stopTimers();
    resetAnalyzeResultState();
    renderStreamError({ message, retryable: true });
    try { es.close(); } catch {}
  };
  const parseEvent = (raw) => {
    if (typeof raw !== 'string' || raw.length > ANALYZE_MAX_STREAM_BYTES) {
      throw new Error('Analyze event is too large');
    }
    return JSON.parse(raw);
  };
  const enqueue = (type, event, onAccepted) => {
    protocolQueue = protocolQueue.then(async () => {
      if (!current() || terminalHandled) return;
      const accepted = await trust.ingest(type, parseEvent(event.data));
      if (!current() || terminalHandled) return;
      await onAccepted(accepted);
    }).catch(() => {
      protocolFailure(T(
        'page.analyze.error_unvalidated',
        '报告完整性或来源绑定校验失败，未展示正文。'
      ));
    });
    return protocolQueue;
  };

  const loadingTimerEl = $('#analyze-loading-timer');
  if (loadingTimerEl && window.startElapsedTimer) {
    stopLoadingTimer = window.startElapsedTimer(loadingTimerEl);
  }

  es.addEventListener('meta', e => enqueue('meta', e, ({ meta }) => {
    window._analyzeMeta = meta;
    renderHeader(meta);
    renderProgress();
    renderTldrCard();
    if (window.refreshFavoriteWithMeta) window.refreshFavoriteWithMeta(meta);
  }));

  es.addEventListener('generation_progress', e => enqueue(
    'generation_progress', e, ({ progress }) => {
      updateLoadingProgress(progress.received_chars || 0);
      const title = $('#analyze-loading .analyze-loading__title');
      if (title) {
        if (progress.stage === 'retrying') {
          title.textContent = T(
            'page.analyze.retry_first', '首次输出未通过校验，正在重新生成'
          );
        } else if (progress.stage === 'validating') {
          title.textContent = T(
            'page.analyze.validating_complete', '正在进行完整性与来源校验'
          );
        } else {
          title.textContent = T(
            'page.analyze.generating_candidate', '正在生成候选研究报告'
          );
        }
      }
    }
  ));

  es.addEventListener('report_validated', e => enqueue('report_validated', e, () => {}));

  es.addEventListener('section', e => enqueue('section', e, ({ key }) => {
    receivedKeys.add(key);
    updateProgressState(receivedKeys);
  }));

  es.addEventListener('persisted', e => enqueue('persisted', e, () => {}));

  es.addEventListener('done', e => enqueue('done', e, accepted => {
    commitAnalyzeReportForDisplay(accepted.report, accepted.persisted, () => {
      renderFinalReport(accepted.report);
      if (accepted.persisted) {
        renderShareBar(accepted.persisted);
        renderDecisionBrief({
          reportId: accepted.persisted.id,
          createdAt: accepted.persisted.created_at,
          partial: false,
          allowExperiment: true,
        });
      }
      updateProgressState(receivedKeys);
      renderTldrCard();
      if (!accepted.persisted) renderDecisionBrief();
    });
    stopTimers();
    const loading = $('#analyze-loading');
    setAnalyzeReportStageState('ready');
    if (loading) loading.remove();
    terminalHandled = true;
    es.close();
  }));

  es.addEventListener('error', e => enqueue('error', e, ({ error }) => {
    stopTimers();
    resetAnalyzeResultState();
    renderStreamError({ message: error.message, retryable: error.retryable });
    terminalHandled = true;
    try { es.close(); } catch {}
  }));

  es.onerror = () => {
    if (!current() || terminalHandled) return;
    terminalHandled = true;
    stopTimers();
    resetAnalyzeResultState();
    renderStreamError({
      message: T('page.analyze.error_hint', '连接中断，未展示任何未完成报告'),
      retryable: true,
    });
    try { es.close(); } catch {}
  };
}

// === Render an error state in place of the loading block ===
// A deterministic non-retryable failure must not offer a button that loops
// into the same outcome (for example a daily budget or scope refusal).
function renderStreamError({ message, retryable }) {
  const loading = $('#analyze-loading');
  if (!loading) return;
  setAnalyzeReportStageState('error');
  // After meta arrives we hide the loading block via .analyze-loading--hidden
  // (display:none). An error event needs to bring it back so the user sees
  // the failure copy.
  loading.classList.remove('analyze-loading--hidden');
  const msg = escapeHtml(message || T("page.analyze.error_title", "生成失败"));
  const buttonHtml = retryable === false
    ? ''
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
      if (!_lastAnalyzePayload || !_lastAnalyzePayload.b_id) { location.reload(); return; }
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
          <span class="analyze-loading__typical">${T('page.analyze.timer_typical', '约需 2–3 分钟 · 完成证据与来源校验后一次呈现')}</span>
        </div>
      `;
      streamAnalysis(_lastAnalyzePayload);
    });
  }
}

// === Brief builder ===
// Pulls fields from the complete validated window._finalReport plus
// window._analyzeMeta (set on the SSE meta event) and shapes
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
  lines.push(`> **${T('page.analyze.brief_analogy', '待验证的跨领域候选')}**: ${a.domain || ''} · ${a.name || ''}  ↔  ${targetLabel}`);
  if (struct.name) {
    lines.push(`> **${T('page.analyze.brief_shared_structure', '候选结构')}**: ${struct.name}`);
  }
  lines.push(`> **${T('page.analyze.brief_boundary', '证据边界')}**: ${T('page.analyze.mechanism_not_verified', '机制未验证')} · ${T('page.analyze.review_not_recorded', '未记录独立复核')}`);
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
      lines.push(`${rank}. **${clean(it.title || '')}**${time}`);
      if (it.how) lines.push(`   - ${T('page.analyze.action_how', '怎么做')}：${clean(it.how)}`);
      if (it.primary_metric) lines.push(`   - ${T('page.analyze.brief_verify', '主要指标')}：${clean(it.primary_metric)}`);
      if (it.decision_rule) lines.push(`   - ${T('page.analyze.decision_rule', '决策规则')}：${clean(it.decision_rule)}`);
      if (it.stop_condition) lines.push(`   - ${T('page.analyze.stop_rule', '停止规则')}：${clean(it.stop_condition)}`);
      if (it.expected_information) lines.push(`   - ${T('page.analyze.brief_expected', '预期获得的信息')}：${clean(it.expected_information)}`);
    });
    lines.push('');
  }

  if (action.review_trigger) {
    lines.push(`## ${T('page.analyze.action_next_week', '下周回头看')}`);
    lines.push(clean(action.review_trigger));
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
  const firstAction = (Array.isArray(plan.this_week) && plan.this_week[0]) || null;
  return {
    problem: ctx.query || target.original_query || target.description || '',
    fingerprint, source, structure,
    mechanism: structure.intuition || structure.mechanism || structure.name || '',
    boundary: risks[0] ? [risks[0].risk_name, risks[0].explanation].filter(Boolean).join('：') : '',
    hypothesis: firstAction ? (firstAction.how || firstAction.expected_information || '') : '',
    metric: firstAction ? (firstAction.primary_metric || '') : '',
    reportId: ctx.reportId || ((window._persistedReport || {}).id) || '',
    model: ctx.model || meta.model || '',
    promptVersion: ctx.promptVersion || meta.prompt_version || '',
    createdAt: ctx.createdAt || ((window._persistedReport || {}).created_at) || '',
    partial: !!(ctx.partial || ((window._persistedReport || {}).is_partial)),
    allowExperiment: ctx.allowExperiment !== false,
    evidence: ctx.evidence || meta.evidence || null,
  };
}

function decisionBriefMarkdown(model) {
  const m = model || buildDecisionBriefModel();
  const unsupported = 'UNSUPPORTED — 当前报告没有这项证据';
  const safe = (value) => String(value || '').replace(/([\\`*_{}\[\]()<>#+\-.!|$^])/g, '\\$1').replace(/\r?\n/g, '\n> ');
  const fp = m.fingerprint || {};
  const sourceName = safe([m.source.domain, m.source.name].filter(Boolean).join(' · ')) || unsupported;
  const evidence = window.StructuralEvidence ? window.StructuralEvidence.normalize(m.evidence || window.StructuralEvidence.fallback(m.source)) : null;
  return [
    '# Structural · 决策简报', '',
    '> 状态：内部决策草稿；检索到的结构线索不能证明两边机制相同。', '',
    '## 问题', safe(m.problem) || unsupported, '',
    '## 经用户确认的结构指纹', safe(fp.summary) || unsupported, '',
    '## 选中候选', sourceName, '',
    '## 待检验的机制假设', safe(m.mechanism) || unsupported, '',
    '## 边界与优先反证', safe(m.boundary) || unsupported, '',
    '## 7 天最小实验',
    `- 假设：${safe(m.hypothesis) || unsupported}`,
    `- 核心指标：${safe(m.metric) || unsupported}`,
    '- 结论规则：只有记录真实结果后，才可将线索升级为已验证迁移。', '',
    '## 来源与版本',
    `- 报告 ID：${safe(m.reportId) || unsupported}`,
    `- 候选来源：${m.source.id ? `${window.location.origin}/phenomenon/${encodeURIComponent(m.source.id)}` : unsupported}`,
    `- 来源类型：${evidence && evidence.source.kind === 'external_source' ? '经核查的外部来源' : 'Structural 内部 KB 记录'}`,
    `- 证据等级：${evidence ? safe(evidence.evidence_level) : 'candidate'}`,
    `- 结果来源：${evidence ? safe(evidence.result.provenance) : 'NOT_TESTED'}`,
    `- 独立性：${evidence && evidence.independence.status !== 'not_recorded' ? safe(evidence.independence.summary || evidence.independence.kind) : unsupported}`,
    `- 证据账本：${evidence && evidence.ledger.status === 'bound' ? safe(evidence.ledger.claim_id + ' · ' + evidence.ledger.version) : unsupported}`,
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
      ${window.StructuralEvidence ? window.StructuralEvidence.render(m.evidence || window.StructuralEvidence.fallback(m.source), { compact: true, kbUrl: m.source.id ? '/phenomenon/' + encodeURIComponent(m.source.id) : '' }) : ''}
      <div class="decision-brief__grid">
        <div class="decision-brief__item decision-brief__item--wide"><span class="decision-brief__label">你的问题</span><p class="decision-brief__value">${value(m.problem)}</p></div>
        <div class="decision-brief__item"><span class="decision-brief__label">经用户确认的结构指纹</span><p class="decision-brief__value">${value(fp.summary)}</p></div>
        <div class="decision-brief__item"><span class="decision-brief__label">选中候选</span><p class="decision-brief__value">${value(sourceName)}</p></div>
        <div class="decision-brief__item"><span class="decision-brief__label">待检验的机制假设</span><p class="decision-brief__value">${value(m.mechanism)}</p></div>
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
      .then(() => { message.textContent = '实验已保存；7 天后回来记录真实结果。'; })
      .catch((err) => { saveButton.disabled = false; console.warn('[decision-brief] save failed'); message.textContent = '没保存成功，请检查报告所有权后重试。'; });
  });
}

window.buildDecisionBriefModel = buildDecisionBriefModel;
window.decisionBriefMarkdown = decisionBriefMarkdown;
window.renderDecisionBrief = renderDecisionBrief;

// === Share + favorite action bar (in the breadcrumb) ===
async function copyAnalyzeText(text) {
  if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  if (!document.execCommand('copy')) throw new Error('copy command rejected');
  document.body.removeChild(ta);
}

function persistedAnalyzeShareUrl() {
  const raw = window._persistedReport && window._persistedReport.share_url;
  if (typeof raw !== 'string' || !raw) return '';
  try {
    const url = new URL(raw, window.location.href);
    const match = url.pathname.match(/^\/report\/share\/([0-9a-f]{32})$/);
    if (url.origin !== window.location.origin || url.username || url.password ||
        url.search || url.hash || !match || !ANALYZE_SHARE_TOKEN_RE.test(match[1])) return '';
    return url.href;
  } catch (_) {
    return '';
  }
}

async function sharePersistedAnalyzeReport() {
  const shareUrl = persistedAnalyzeShareUrl();
  if (!shareUrl) {
    if (window.showToast) window.showToast(T(
      'page.analyze.toast_share_requires_save',
      '当前报告尚未保存，地址栏链接无法恢复报告。请先复制简报，或重新生成时选择保存。'
    ));
    return false;
  }
  try {
    await copyAnalyzeText(shareUrl);
    if (window.showToast) window.showToast(T(
      'page.analyze.toast_link_copied', '报告分享链接已复制'
    ));
    return true;
  } catch (_) {
    console.error('[analyze] capability link copy failed');
    if (window.showToast) window.showToast(T(
      'page.analyze.toast_share_copy_failed', '复制失败，请使用下方分享栏或复制简报。'
    ));
    return false;
  }
}

function createAnalyzeRequestContext({
  bId, aId, query, fingerprint, originDiscoveryId, originContractVersion,
}) {
  return {
    bId: bId || null,
    aId: aId || null,
    query: typeof query === 'string' ? query : '',
    fingerprint: fingerprint || null,
    originDiscoveryId: originDiscoveryId || null,
    originContractVersion: originContractVersion || null,
  };
}

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
        console.error('[analyze] brief copy failed');
        if (window.showToast) window.showToast(T('page.analyze.toast_copy_failed_perm', '复制失败，请检查浏览器权限'));
      }
    });
  }

  const shareBtn = document.getElementById('analyze-share-btn');
  if (shareBtn) {
    shareBtn.addEventListener('click', sharePersistedAnalyzeReport);
  }

  const favBtn = document.getElementById('analyze-fav-btn');
  if (!favBtn) return;

  const requestContext = window._analyzeRequestContext || {};
  const bId = requestContext.bId || getQueryParam('id');
  const q = requestContext.query || '';
  const aId = requestContext.aId || getQueryParam('a_id');
  const confirmedFingerprint = requestContext.fingerprint || null;
  const originDiscoveryId = requestContext.originDiscoveryId || getQueryParam('origin_discovery_id');
  const originContractVersion = requestContext.originContractVersion || getQueryParam('origin_contract_version');
  const ENTITY_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
  const DISCOVERY_ID_RE = /^discovery-[0-9a-f]{16}$/;
  const BOOKMARK_ID_RE = /^bm_[0-9a-f]{24}$/;
  const MAX_RESEARCH_QUERY_CHARS = (window.StructuralInputLimits &&
    window.StructuralInputLimits.researchQueryChars) || 8000;
  const CONTROL_RE = /[\p{Cc}\p{Cf}]/u;
  const HTML_TAG_RE = /<\s*\/?\s*(?:[A-Za-z]|!)[^>]*>/;
  let remoteBookmark = null;
  let favoriteRequestPending = false;

  const safeText = (value, maximum, allowLayout = false) => {
    if (typeof value !== 'string') return '';
    const normalized = value.normalize('NFKC').trim();
    if (!normalized || normalized.length > maximum || HTML_TAG_RE.test(normalized)) return '';
    for (const char of normalized) {
      if (!CONTROL_RE.test(char)) continue;
      if (allowLayout && ['\n', '\r', '\t'].includes(char)) continue;
      return '';
    }
    return normalized;
  };

  const normalizeFingerprint = (raw, query) => {
    if (raw == null) return null;
    if (typeof raw !== 'object' || Array.isArray(raw)) return null;
    const allowed = new Set(['source_query', 'summary', 'variables', 'constraints', 'unknowns', 'revision']);
    if (Object.keys(raw).some((key) => !allowed.has(key))) return null;
    const sourceQuery = safeText(raw.source_query, MAX_RESEARCH_QUERY_CHARS, true);
    const summary = safeText(raw.summary, 1000, true);
    if (!sourceQuery || sourceQuery !== query || summary.length < 8) return null;
    const normalized = { source_query: sourceQuery, summary };
    for (const field of ['variables', 'constraints', 'unknowns']) {
      const values = raw[field] == null ? [] : raw[field];
      if (!Array.isArray(values) || values.length > 12) return null;
      const cleaned = values.map((item) => safeText(item, 120));
      if (cleaned.some((item) => !item)) return null;
      normalized[field] = cleaned;
    }
    const revision = raw.revision == null ? 1 : raw.revision;
    if (!Number.isInteger(revision) || revision < 1 || revision > 1000) return null;
    normalized.revision = revision;
    return normalized;
  };

  const sameTypedValue = (left, right) => JSON.stringify(left || null) === JSON.stringify(right || null);

  // Build a fresh entry on every read; pulls a_name/b_name from window._analyzeMeta
  // (set when the SSE meta event arrives — may be null at click time if user is fast)
  const buildEntry = () => {
    const m = window._analyzeMeta;
    return {
      query: q || '',
      a_id: aId || (m && m.a && m.a.id) || null,
      b_id: bId || null,
      fingerprint: confirmedFingerprint,
      origin_discovery_id: originDiscoveryId || null,
      origin_contract_version: originContractVersion || null,
      a_name: (m && m.a && m.a.name) || null,
      b_name: (m && m.b && m.b.name) || null,
      a_domain: (m && m.a && m.a.domain) || null,
      b_domain: (m && m.b && m.b.domain) || null,
      analyze_url: ENTITY_ID_RE.test(bId || '') ? '/analyze?id=' + encodeURIComponent(bId) : '/analyze',
      timestamp: Date.now(),
    };
  };

  const safeAnalysisHref = (targetId) => ENTITY_ID_RE.test(targetId || '')
    ? '/analyze?id=' + encodeURIComponent(targetId)
    : '';

  const buildServerPayload = () => {
    const entry = buildEntry();
    const query = safeText(entry.query, MAX_RESEARCH_QUERY_CHARS, true);
    const sourceId = entry.a_id ? String(entry.a_id).trim() : null;
    const targetId = String(entry.b_id || '').trim();
    if (!query || !safeAnalysisHref(targetId) || (sourceId && !ENTITY_ID_RE.test(sourceId))) return null;
    const fingerprint = normalizeFingerprint(entry.fingerprint, query);
    if (entry.fingerprint != null && !fingerprint) return null;
    const hasOrigin = entry.origin_discovery_id != null || entry.origin_contract_version != null;
    if (hasOrigin && (!DISCOVERY_ID_RE.test(entry.origin_discovery_id || '') ||
        entry.origin_contract_version !== 'discovery-candidate-v2')) return null;
    const candidateTitle = safeText(entry.b_name, 240);
    const title = candidateTitle
      ? candidateTitle
      : query.slice(0, 240);
    return {
      kind: 'structural_analysis',
      title,
      query,
      source_id: sourceId,
      target_id: targetId,
      ...(fingerprint ? { fingerprint } : {}),
      ...(hasOrigin ? {
        origin_discovery_id: entry.origin_discovery_id,
        origin_contract_version: entry.origin_contract_version,
      } : {}),
    };
  };

  const currentLocalFavorite = () => {
    if (!window.getFavorites) return null;
    const entry = buildEntry();
    return window.getFavorites().find((item) => item && (
      item.b_id === entry.b_id && item.query === entry.query &&
      (item.a_id || null) === (entry.a_id || null)
    )) || null;
  };

  const bookmarkMatchesCurrent = (bookmark) => {
    const payload = buildServerPayload();
    const allowed = new Set([
      'schema_version', 'bookmark_id', 'kind', 'title', 'query', 'source_id',
      'target_id', 'fingerprint', 'origin_discovery_id',
      'origin_contract_version', 'href', 'source', 'created_at'
    ]);
    if (!payload || !bookmark || Object.keys(bookmark).some((key) => !allowed.has(key)) ||
        bookmark.schema_version !== 'bookmark-v2' || bookmark.kind !== 'structural_analysis' ||
        bookmark.source !== 'Structural' ||
        !BOOKMARK_ID_RE.test(bookmark.bookmark_id || '') ||
        bookmark.query !== payload.query || bookmark.target_id !== payload.target_id ||
        (bookmark.source_id || null) !== payload.source_id ||
        !sameTypedValue(bookmark.fingerprint, payload.fingerprint) ||
        (bookmark.origin_discovery_id || null) !== (payload.origin_discovery_id || null) ||
        (bookmark.origin_contract_version || null) !== (payload.origin_contract_version || null)) return false;
    return bookmark.href === safeAnalysisHref(bookmark.target_id);
  };

  const restoreLocalFavorite = (previous) => {
    if (!previous || !window.toggleFavorite) return;
    if (!window.isFavorited || !window.isFavorited(previous)) window.toggleFavorite(previous);
    if (window.upsertFavorite) window.upsertFavorite(previous);
  };

  const favoriteToast = (message) => {
    if (window.showToast) window.showToast(message);
  };

  const readProblem = async (response) => {
    try { return await response.json(); } catch (_) { return {}; }
  };

  const syncFavUi = () => {
    const active = (window.isFavorited ? window.isFavorited(buildEntry()) : false) || !!remoteBookmark;
    favBtn.classList.toggle('is-active', active);
    favBtn.setAttribute('aria-pressed', active ? 'true' : 'false');
    favBtn.disabled = favoriteRequestPending;
    const icon = document.getElementById('analyze-fav-icon');
    const label = document.getElementById('analyze-fav-label');
    if (icon) icon.textContent = active ? '★' : '☆';
    if (label) label.textContent = active ? T('page.analyze.fav_active', '已收藏') : T('page.analyze.btn_fav', '收藏');
  };

  syncFavUi();

  favBtn.addEventListener('click', async () => {
    if (favoriteRequestPending) return;
    if (!window.toggleFavorite) return;
    const existingLocal = currentLocalFavorite();
    const existingRemote = remoteBookmark;
    const wasFavorited = !!existingLocal || !!existingRemote;

    if (!wasFavorited) {
      const entry = buildEntry();
      window.toggleFavorite(entry);
      if (window.upsertFavorite) window.upsertFavorite(entry);
      syncFavUi();
      if (window.updateFavBadge) window.updateFavBadge();

      const payload = buildServerPayload();
      if (!payload) {
        favoriteToast(T('page.analyze.toast_fav_sync_later', '已保存在本机，账户同步稍后重试'));
        return;
      }
      favoriteRequestPending = true;
      syncFavUi();
      try {
        const response = await fetch('/api/favorites/bookmarks', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const problem = await readProblem(response);
          if (response.status === 401) {
            favoriteToast(T('page.analyze.toast_fav_local_login', '已保存在本机，登录后同步'));
          } else if (response.status === 409 && problem.error === 'credential_conflict') {
            favoriteToast(T('page.analyze.toast_fav_account_confirm', '已保存在本机，请重新确认账户后同步'));
          } else if (response.status === 429) {
            favoriteToast(T('page.analyze.toast_fav_quota', '已保存在本机，账户收藏已达上限'));
          } else {
            favoriteToast(T('page.analyze.toast_fav_sync_later', '已保存在本机，账户同步稍后重试'));
          }
          return;
        }
        const data = await response.json();
        if (!data || !bookmarkMatchesCurrent(data.bookmark)) throw new Error('invalid bookmark confirmation');
        remoteBookmark = data.bookmark;
        if (window.upsertFavorite) {
          window.upsertFavorite({
            ...buildEntry(),
            server_bookmark_id: data.bookmark.bookmark_id,
            server_href: data.bookmark.href,
          });
        }
        favoriteToast(T('page.analyze.toast_fav_synced', '已同步到账户'));
      } catch (error) {
        console.warn('[analyze] favorite sync failed');
        favoriteToast(T('page.analyze.toast_fav_sync_later', '已保存在本机，账户同步稍后重试'));
      } finally {
        favoriteRequestPending = false;
        syncFavUi();
      }
      return;
    }

    const remoteId = (existingLocal && BOOKMARK_ID_RE.test(existingLocal.server_bookmark_id || '')
      ? existingLocal.server_bookmark_id : null) ||
      (existingRemote && existingRemote.bookmark_id);
    if (existingLocal) window.toggleFavorite(existingLocal);
    remoteBookmark = null;
    syncFavUi();
    if (window.updateFavBadge) window.updateFavBadge();

    if (!remoteId) {
      favoriteToast(T('page.analyze.toast_fav_removed_local', '已从本机收藏移除'));
      return;
    }
    favoriteRequestPending = true;
    syncFavUi();
    try {
      const response = await fetch('/api/favorites/bookmarks/' + encodeURIComponent(remoteId), {
        method: 'DELETE', credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      favoriteToast(T('page.analyze.toast_fav_removed_account', '已从账户收藏移除'));
    } catch (error) {
      console.warn('[analyze] favorite removal failed');
      remoteBookmark = existingRemote;
      restoreLocalFavorite(existingLocal);
      favoriteToast(T('page.analyze.toast_fav_remove_failed', '账户移除未完成，收藏仍然保留'));
    } finally {
      favoriteRequestPending = false;
      syncFavUi();
      if (window.updateFavBadge) window.updateFavBadge();
    }
  });

  // A second signed-in device has no localStorage mirror. Hydrate only this
  // report's state from the typed account response, and accept server links
  // only when they exactly match the canonical URL rebuilt from typed fields.
  fetch('/api/favorites', { credentials: 'same-origin' })
    .then(async (response) => {
      if (!response.ok) return null;
      return response.json();
    })
    .then((data) => {
      if (!data || !Array.isArray(data.bookmarks)) return;
      remoteBookmark = data.bookmarks.find(bookmarkMatchesCurrent) || null;
      if (remoteBookmark && currentLocalFavorite() && window.upsertFavorite) {
        window.upsertFavorite({
          ...buildEntry(),
          server_bookmark_id: remoteBookmark.bookmark_id,
          server_href: remoteBookmark.href,
        });
      }
      syncFavUi();
    })
    .catch(() => { /* local state remains authoritative while offline */ });

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

  const bId = getQueryParam('id');
  const aId = getQueryParam('a_id');
  const originDiscoveryId = getQueryParam('origin_discovery_id');
  const originContractVersion = getQueryParam('origin_contract_version');
  const handoffKey = getQueryParam('handoff');

  // Legacy links may still carry `q`. Consume it only for this migration
  // window and synchronously remove every sensitive field from the visible
  // URL/history before any API call or user interaction. New links never put
  // these fields in the URL at all.
  const legacyQuery = getQueryParam('q') || getQueryParam('text_a') || '';
  let handoff = null;
  if (handoffKey && typeof window.consumeAnalyzeHandoff === 'function') {
    handoff = window.consumeAnalyzeHandoff(handoffKey, { id: bId, a_id: aId });
  }
  try {
    const cleanUrl = new URL(window.location.href);
    ['q', 'text_a', 'fingerprint', 'anon_id', 'handoff'].forEach((name) => {
      cleanUrl.searchParams.delete(name);
    });
    window.history.replaceState(null, '', cleanUrl.pathname + cleanUrl.search + cleanUrl.hash);
  } catch (_) { /* a restrictive test fixture may not implement history */ }

  const q = handoff && typeof handoff.query === 'string'
    ? handoff.query
    : legacyQuery;
  const confirmedFingerprint = handoff && handoff.fingerprint
    ? handoff.fingerprint
    : null;
  window._analyzeRequestContext = createAnalyzeRequestContext({
    bId,
    aId,
    query: q,
    fingerprint: confirmedFingerprint,
    originDiscoveryId,
    originContractVersion,
  });

  initHeaderScroll();
  initAnalyzeActions();

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
    setAnalyzeReportStageState('idle');
    return;
  }

  const payload = {
    b_id: bId,
    lang: (document.documentElement.getAttribute('lang') || '').toLowerCase().startsWith('en')
      ? 'en'
      : 'zh',
    persist: 0,
  };
  if (q) {
    payload.text_a = q;
    if (confirmedFingerprint) payload.fingerprint = confirmedFingerprint;
  } else if (aId) {
    payload.a_id = aId;
  } else {
    const loadingEl = $('#analyze-loading');
    if (loadingEl) {
      loadingEl.innerHTML =
        '<h2 class="analyze-loading__title">分析上下文已失效</h2>' +
        '<p class="analyze-loading__hint">为了不把你的问题写进浏览器历史，这段上下文只在当前标签页短暂保留，且只能读取一次。</p>' +
        '<p style="margin-top:20px"><a href="/" class="report-errorcard__cta">返回首页重新开始</a></p>';
    }
    setAnalyzeReportStageState('idle');
    return;
  }

  // Preserve candidate provenance only as a complete pair. The backend
  // rebinds both values to the current catalog and rejects stale/mismatched
  // links; the browser never upgrades evidence from URL text alone.
  if (originDiscoveryId !== null) payload.origin_discovery_id = originDiscoveryId;
  if (originContractVersion !== null) payload.origin_contract_version = originContractVersion;

  // Persistence and capability-link creation require explicit opt-in.
  // Missing/invalid values remain private and never reach the report store.
  // anon_id is only attached when persistence was explicitly selected.
  const persistFlag = getQueryParam('persist');
  if (persistFlag === '1') {
    payload.persist = 1;
    try {
      let anonId = localStorage.getItem('anonId');
      if (!anonId) {
        anonId = (window.crypto && window.crypto.randomUUID)
          ? window.crypto.randomUUID()
          : ('anon-' + Math.random().toString(36).slice(2) + '-' + Date.now().toString(36));
        localStorage.setItem('anonId', anonId);
      }
      payload.anon_id = anonId;
    } catch (e) { /* localStorage may be blocked; skip silently */ }
  }

  scheduleAnalyzeMathRuntime();
  streamAnalysis(payload);
});

// Re-render header + progress + validated sections when language toggles.
// Pending sections contain progress-only placeholders, never report prose.
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
      } catch (e) { console.warn('[analyze] onChange re-render failed'); }
    });
  }
} catch (e) {}

if (typeof window !== 'undefined') {
  window.StructuralAnalyzeTrust = Object.freeze({
    canonicalAnalyzeJson,
    sha256CanonicalAnalyzeJson,
    validateAnalyzeReportEnvelope,
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    ANALYZE_MATH_BACKGROUND_DELAY_MS,
    ANALYZE_MATH_ASSETS,
    analyzeGenerationMatches,
    analyzeMathRuntimeReady,
    buildDecisionBriefModel,
    canonicalAnalyzeJson,
    commitAnalyzeReportForDisplay,
    createAnalyzeRequestContext,
    createAnalyzeTrustState,
    decisionBriefMarkdown,
    enhanceAnalyzeMath,
    renderAnalyzeActionPlan: renderers.action_plan,
    renderAnalyzeBorrowableInsights: renderers.borrowable_insights,
    renderAnalyzeHowToCombine: renderers.how_to_combine,
    renderAnalyzeResearchDirections: renderers.research_directions,
    renderAnalyzeRisksAndLimits: renderers.risks_and_limits,
    renderAnalyzeSharedStructure: renderers.shared_structure,
    renderAnalyzeStructuralMapping: renderers.structural_mapping,
    renderAnalyzeTargetDomainIntro: renderers.target_domain_intro,
    requestAnalyzeMathRuntime,
    setAnalyzeReportStageState,
    sharePersistedAnalyzeReport,
    sha256CanonicalAnalyzeJson,
    validateAnalyzeMetaEnvelope,
    validateAnalyzeReportEnvelope,
  };
}
