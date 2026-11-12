// --- i18n helpers ---
function T(key, fallback) {
  try { if (window.i18n && typeof window.i18n.t === 'function') { var v = window.i18n.t(key); if (v && v !== key) return v; } } catch(e) {}
  return fallback;
}

function currentLang() {
  try { return (window.i18n && window.i18n.getLang && window.i18n.getLang()) || 'zh'; } catch (e) { return 'zh'; }
}
function L(obj, baseKey) {
  // Return obj[baseKey + '_en'] if lang=en and it exists, else obj[baseKey + '_zh']
  // or fallback to obj[baseKey].
  if (!obj) return '';
  var lang = currentLang();
  if (lang === 'en') {
    var en = obj[baseKey + '_en'];
    if (typeof en === 'string' && en.length) return en;
    if (Array.isArray(en) && en.length) return en;
  }
  var zh = obj[baseKey + '_zh'];
  if (typeof zh === 'string' && zh.length) return zh;
  if (Array.isArray(zh) && zh.length) return zh;
  return obj[baseKey];
}
function Larr(obj, baseKey) {
  var v = L(obj, baseKey);
  return Array.isArray(v) ? v : [];
}

/**
 * Structural — Universality Classes page
 * Renders equivalence classes auto-discovered from V1/V2/V3 pair data
 * via Layer 1 (graph build) + Layer 2 (hub detect + community discovery).
 */

const DATA_URL = "/assets/data/universality-classes.json";

let allClasses = [];
let manualClasses = [];
let llmClasses = [];
let unclassifiedClasses = [];
let lastFocusedClassId = null;
// Default to "all" so /classes shows every current candidate immediately.
let currentFilter = "all";

const escapeHtml = (s) => {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

async function loadData() {
  const resp = await fetch(DATA_URL);
  if (!resp.ok) throw new Error(`Failed to load ${DATA_URL}: ${resp.status}`);
  return resp.json();
}

function deriveClassStats(classes) {
  const items = Array.isArray(classes) ? classes : [];
  const originalQueue = items.filter((item) => item && (item.curation_source === "manual" || item.curation_source === "llm"));
  const laterCandidates = items.filter((item) => !item || (item.curation_source !== "manual" && item.curation_source !== "llm"));
  const manual = originalQueue.filter((item) => item.curation_source === "manual");
  const llm = originalQueue.filter((item) => item.curation_source === "llm");
  return {
    total: items.length,
    originalQueue: originalQueue.length,
    originalCrossDomain: originalQueue.filter((item) => Number(item.n_domains || 0) >= 2).length,
    laterCandidates: laterCandidates.length,
    manual: manual.length,
    llm: llm.length,
    maxMembers: items.reduce((maximum, item) => Math.max(maximum, Number((item && item.size) || 0)), 0),
    maxDomains: items.reduce((maximum, item) => Math.max(maximum, Number((item && item.n_domains) || 0)), 0),
  };
}

function classDatasetSummary(stats) {
  if (currentLang() === "en") {
    return `${stats.total} candidate groups: ${stats.originalCrossDomain} cross-domain groups from the original human/AI queue and ${stats.laterCandidates} later candidates whose source is unclassified. Counts are computed from the loaded records.`;
  }
  return `当前共 ${stats.total} 个候选分组：${stats.originalCrossDomain} 个来自原始人工/AI 队列的跨域组，另有 ${stats.laterCandidates} 个后加候选（来源未分类）。所有数量均由当前加载记录计算。`;
}

function renderClassDatasetCopy(classes) {
  const stats = deriveClassStats(classes);
  const title = document.getElementById("uc-hero-title");
  const methodSummary = document.getElementById("uc-method-data-summary");
  const summary = classDatasetSummary(stats);
  if (title) {
    title.innerHTML = currentLang() === "en"
      ? `${stats.total} <em>candidate patterns</em>`
      : `${stats.total} 个<em>候选模式</em>`;
  }
  if (methodSummary) {
    methodSummary.innerHTML = currentLang() === "en"
      ? `<strong>Current data boundary</strong>: ${escapeHtml(summary)} The ${stats.laterCandidates} later candidates remain visible under a separate source filter and are not silently folded into the original queue.`
      : `<strong>当前数据边界</strong>：${escapeHtml(summary)} ${stats.laterCandidates} 个后加候选使用独立来源筛选，不会静默并入原始队列。`;
  }
  document.querySelectorAll('meta[name="description"], meta[property="og:description"], meta[name="twitter:description"]').forEach((node) => {
    node.setAttribute("content", summary);
  });
  return stats;
}

function renderHeroStats(classes) {
  const host = document.getElementById("uc-hero-stats");
  if (!host) return;
  const stats = deriveClassStats(classes);
  const items = [
    { key: "total", value: stats.total, label: T("page.classes.stat_total", "候选模式") },
    { key: "original", value: stats.originalCrossDomain, label: T("page.classes.stat_original_queue", "原队列跨域组") },
    { key: "later", value: stats.laterCandidates, label: T("page.classes.stat_later", "后加候选") },
    { key: "domains", value: stats.maxDomains, label: T("page.classes.stat_max_domains", "最多跨越领域") },
  ];
  items.forEach((item) => {
    const row = host.querySelector(`[data-stat="${item.key}"]`);
    if (!row) return;
    const value = row.querySelector(".uc-hero__stat-value");
    const label = row.querySelector(".uc-hero__stat-label");
    if (value) value.textContent = String(item.value ?? "—");
    if (label) label.textContent = item.label;
  });
  host.setAttribute("aria-busy", "false");
}

function renderMembers(membersByDomain, hubName) {
  if (!membersByDomain || !membersByDomain.length) return "";
  const isEn = currentLang() === 'en';
  const rows = membersByDomain
    .map((row) => {
      const domainLabel = (isEn && row.domain_en) ? row.domain_en : row.domain;
      const namesArr = (isEn && row.names_en && row.names_en.length) ? row.names_en : row.names;
      const namesZhArr = row.names || [];
      const names = namesArr
        .map((n, i) => {
          // Hub comparison: always use the zh-side to match hubName passed in
          const rawName = namesZhArr[i] !== undefined ? namesZhArr[i] : n;
          const isHub = rawName === hubName || n === hubName;
          return `<span class="uc-members__name${isHub ? " uc-members__name--hub" : ""}">${escapeHtml(n)}${isHub ? " ★" : ""}</span>`;
        })
        .join("");
      return `
      <div class="uc-members__row">
        <div class="uc-members__domain">${escapeHtml(domainLabel)}</div>
        <div class="uc-members__names">${names}</div>
      </div>
    `;
    })
    .join("");
  return `<div class="uc-members">${rows}</div>`;
}

// Convert pseudo-LaTeX like "du/dt = α/(1+v^n) - u" into real KaTeX.
// Conservative — if we don't recognize a pattern we leave it as pretty monospace.
function tryLatexify(raw) {
  if (!raw) return null;
  let s = raw;

  // Don't attempt if there's too much prose (too many spaces between words in Latin script)
  const wordRatio = (s.match(/\b[a-z]{4,}\b/gi) || []).length;
  if (wordRatio > 5) return null;  // looks like a prose description

  // ASCII greek → LaTeX
  const greekMap = {
    alpha: '\\alpha', beta: '\\beta', gamma: '\\gamma', delta: '\\delta',
    epsilon: '\\epsilon', zeta: '\\zeta', eta: '\\eta', theta: '\\theta',
    iota: '\\iota', kappa: '\\kappa', lambda: '\\lambda', mu: '\\mu',
    nu: '\\nu', xi: '\\xi', pi: '\\pi', rho: '\\rho', sigma: '\\sigma',
    tau: '\\tau', upsilon: '\\upsilon', phi: '\\phi', chi: '\\chi',
    psi: '\\psi', omega: '\\omega',
    Alpha: 'A', Beta: 'B', Gamma: '\\Gamma', Delta: '\\Delta',
    Theta: '\\Theta', Lambda: '\\Lambda', Pi: '\\Pi', Sigma: '\\Sigma',
    Phi: '\\Phi', Omega: '\\Omega',
  };
  for (const [k, v] of Object.entries(greekMap)) {
    s = s.replace(new RegExp('\\b' + k + '\\b', 'g'), v);
  }

  // d<var>/dt, d<var>/dx → \frac{d<var>}{dt}
  s = s.replace(/\bd(\w+)\/d(\w+)\b/g, '\\frac{d$1}{d$2}');

  // sum_j, prod_i → \sum_j, \prod_i
  s = s.replace(/\bsum_(\w+|\{[^}]+\})/g, '\\sum_{$1}');
  s = s.replace(/\bprod_(\w+|\{[^}]+\})/g, '\\prod_{$1}');
  s = s.replace(/\bint_(\w+|\{[^}]+\})/g, '\\int_{$1}');

  // Common substitutions
  s = s.replace(/->/g, '\\to ');
  s = s.replace(/<=/g, '\\leq ');
  s = s.replace(/>=/g, '\\geq ');
  s = s.replace(/!=/g, '\\neq ');
  s = s.replace(/\\infty|∞/g, '\\infty');

  // Superscripts: x^n → x^{n}, x^abc → x^{abc}, keep x^{...} as-is
  s = s.replace(/\^([A-Za-z0-9]{2,})/g, '^{$1}');
  // Subscripts: keep x_i as is, x_abc → x_{abc}
  s = s.replace(/_([A-Za-z0-9]{2,})/g, '_{$1}');

  // Fractions: <something>/(expr) → \frac{something}{expr}
  // Only when there's a clear (...) on the right
  s = s.replace(/([a-zA-Z0-9\\_^{}]+)\/\(([^()]+)\)/g, '\\frac{$1}{$2}');

  // Multiplication: * → \cdot (but leave A*B if A or B has a digit next to it? keep simple)
  s = s.replace(/\s*\*\s*/g, ' \\cdot ');

  // If there's still an unmatched `/` in the result, and it's between simple tokens, convert
  s = s.replace(/(\b[a-zA-Z]\w*)\/(\b[a-zA-Z]\w*\b)/g, '\\frac{$1}{$2}');

  return s;
}

function renderEquations(eqs) {
  if (!eqs || !eqs.length) return "";
  const items = eqs.map((e) => {
    const raw = (e && e.raw) || "";
    if (!raw) return "";

    // Split "Label: math" when a short label exists
    let label = "";
    let body = raw;
    const labelMatch = raw.match(/^([^:：]{2,40})[:：]\s+(.+)$/s);
    if (labelMatch && !/[=+\-\\^*/()]/.test(labelMatch[1])) {
      label = labelMatch[1].trim();
      body = labelMatch[2].trim();
    }

    // Split body by ; into multiple lines (equations)
    const parts = body.split(/\s*;\s+/).map((p) => p.trim()).filter(Boolean);

    const renderedParts = parts.map((p) => {
      const latex = tryLatexify(p);
      if (latex) {
        return `<div class="uc-eq-line" tabindex="0"><span class="uc-eq-math">$$${latex}$$</span></div>`;
      }
      return `<div class="uc-eq-line" tabindex="0"><code class="uc-eq-code">${escapeHtml(p)}</code></div>`;
    }).join("");

    const header = label ? `<div class="uc-eq-label">${escapeHtml(label)}</div>` : "";
    return `<div class="uc-eq-block">${header}${renderedParts}</div>`;
  }).join("");

  return `<div class="uc-eq-list">${items}</div>`;
}

function renderInvariants(invariants) {
  if (!invariants || !invariants.length) return "";
  return `
    <ul class="uc-inv-list">
      ${invariants.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}
    </ul>
  `;
}

// Historical prediction objects contain free-form internal prose and workflow
// metadata. The public renderer deliberately projects only auditable fields;
// raw prediction/rationale/status/paper fields never enter the DOM.
function historicalStatisticTokens(rawValue) {
  const text = String(rawValue || "");
  const numberPattern = /[−+-]?\d[\d,]*(?:\.\d+)?(?:[eE][−+-]?\d+|[⁻⁺]?[\u2070\u00b9\u00b2\u00b3\u2074-\u2079]+)?(?:\s*%|\s*±\s*[−+-]?\d[\d,]*(?:\.\d+)?)?/g;
  const values = text.match(numberPattern) || [];
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean))).slice(0, 12);
}

function publicPredictionView(prediction) {
  const item = prediction || {};
  return Object.freeze({
    target: L(item, "target") || "",
    testMethod: L(item, "test_method") || "",
    dataSource: L(item, "data_source") || "",
    sampleSize: L(item, "sample_size") || "",
    historicalStatistics: historicalStatisticTokens(L(item, "prediction") || ""),
  });
}

function renderPredictions(preds) {
  if (!Array.isArray(preds) || !preds.length) return "";
  return preds.map((prediction) => {
    const view = publicPredictionView(prediction);
    const meta = [];
    if (view.testMethod) meta.push(`<div><span class="uc-pred__meta-key">${T("page.classes.pred_meta_method", "方法")}</span>${escapeHtml(view.testMethod)}</div>`);
    if (view.dataSource) meta.push(`<div><span class="uc-pred__meta-key">${T("page.classes.pred_meta_data", "数据")}</span>${escapeHtml(view.dataSource)}</div>`);
    if (view.sampleSize) meta.push(`<div><span class="uc-pred__meta-key">${T("page.classes.pred_meta_sample", "样本量")}</span>${escapeHtml(view.sampleSize)}</div>`);
    const statistic = view.historicalStatistics.length
      ? `<div class="uc-pred__historical-stat"><span class="uc-pred__meta-key">${T("page.classes.pred_meta_historical_stat", "历史记录数值")}</span>${view.historicalStatistics.map(escapeHtml).join(" · ")}</div>`
      : "";
    const boundary = T(
      "page.classes.pred_boundary",
      currentLang() === "en"
        ? "Historical internal record · not bound to the current evidence ledger · cannot prove a shared mechanism"
        : "历史内部记录 · 未绑定当前证据账本 · 不能证明共享机制",
    );
    return `
      <div class="uc-pred">
        <div class="uc-pred__header">
          <div class="uc-pred__target">${escapeHtml(view.target || T("page.classes.pred_target_unknown", "目标未记录"))}</div>
          <span class="uc-pred__record-label">${T("page.classes.pred_record_label", "历史内部记录")}</span>
        </div>
        ${meta.length ? `<div class="uc-pred__meta">${meta.join("")}</div>` : ""}
        ${statistic}
        <p class="uc-pred__boundary">${escapeHtml(boundary)}</p>
      </div>
    `;
  }).join("");
}

function countPublicPredictionRecords(cls) {
  if (!cls || !Array.isArray(cls.predictions)) return 0;
  return cls.predictions.map(publicPredictionView).filter((view) => (
    view.target || view.testMethod || view.dataSource || view.sampleSize || view.historicalStatistics.length
  )).length;
}

// SESSION-18 (D): build a hook-style headline for a universality class
// straight from its real fields. Like discoveries, this picks from several
// sentence patterns keyed off the class's REAL signals so the 26 classes
// don't all read off one mechanical template:
//   · domains      — its real member fields
//   · n_domains    — how broadly it reaches
//   · name         — the class name
//   · class_id     — stable index so the choice is deterministic
function classHeadline(cls) {
  const name = L(cls, 'name') || '';
  const domains = (currentLang() === 'en' ? cls.domains_en : cls.domains) || cls.domains || [];
  const en = currentLang() === 'en';
  const nDom = cls.n_domains || domains.length || 0;

  // Pick two distinct, human-readable domains for the hook.
  const picked = [];
  for (const dmn of domains) {
    if (dmn && !picked.includes(dmn)) picked.push(dmn);
    if (picked.length === 2) break;
  }

  // Deterministic per-class index from class_id.
  const idStr = String(cls.class_id || name || '');
  let seed = 0;
  for (let i = 0; i < idStr.length; i++) seed = (seed + idStr.charCodeAt(i)) % 997;

  if (en) {
    if (picked.length === 2) {
      const enSet = [
        `Candidate structural grouping: ${picked[0]} and ${picked[1]}. Check the variable mapping and evidence.`,
        `A pattern to test between ${picked[0]} and ${picked[1]}, not an established law.`,
        `Testable structural mapping: ${picked[0]} and ${picked[1]}.`,
      ];
      return enSet[seed % enSet.length];
    }
    return `Candidate pattern across ${nDom || 'many'} fields: ${name}`;
  }

  if (picked.length === 2) {
    if (nDom >= 9) {
      const poolWide = [
        `候选结构组覆盖 ${nDom} 个领域，包括${picked[0]}和${picked[1]}；覆盖范围不等于规律成立。`,
        `候选映射：${picked[0]}、${picked[1]}等 ${nDom} 个领域；先核对变量、证据与反例。`,
        `${picked[0]}和${picked[1]}出现在一个广域候选组中，仍需逐项验证。`,
      ];
      return poolWide[seed % poolWide.length];
    }
    const pool = [
      `候选结构映射：${picked[0]}与${picked[1]}，需要核对变量和证据。`,
      `${picked[0]}与${picked[1]}可能共享一个待检验模式。`,
      `把${picked[0]}和${picked[1]}作为候选类比，先寻找反例。`,
    ];
    return pool[seed % pool.length];
  }
  return `覆盖 ${nDom || '多个'} 个领域的候选模式：${name}`;
}

// Absolute share URL for a single class.
function classShareUrl(cls) {
  return location.origin + '/classes?c=' + encodeURIComponent(cls.class_id);
}

// Seed text for the /analyze prefill — the class's hub phenomenon, which is
// a concrete real example the user can edit into their own problem.
function classAnalyzeSeed(cls) {
  return L(cls, 'hub_name') || L(cls, 'name') || '';
}

// CTA target. /analyze needs a real KB phenomenon id; the hub's id ships in
// the class data as `hub_id`. When it resolves we deep-link straight into
// /analyze via the shared buildAnalyzeUrl() builder (utils/buildAnalyzeUrl.js,
// single source of truth for the URL contract). When it doesn't — the 3
// post-build classes whose hub isn't a KB phenomenon — we degrade to /search
// so the CTA still does something useful instead of dead-ending on the
// analyze empty state.
function classAnalyzeHref(cls) {
  var seed = classAnalyzeSeed(cls);
  if (cls && cls.hub_id) {
    return window.buildAnalyzeUrl({ id: cls.hub_id, q: seed });
  }
  return '#';
}

function buildBadges(cls) {
  const nRecorded = countPublicPredictionRecords(cls);
  const out = [];
  if (nRecorded > 0) {
    const recordedLabel = T("page.classes.badge_recorded", "有历史内部记录");
    const label = nRecorded === 1 ? recordedLabel : `${recordedLabel} ×${nRecorded}`;
    const title = currentLang() === "en"
      ? `${nRecorded} historical internal records; not external validation`
      : `${nRecorded} 条历史内部记录；不代表外部验证`;
    out.push(`<span class="uc-badge uc-badge--recorded" title="${escapeHtml(title)}">${label}</span>`);
  }
  out.push(
    `<span class="uc-badge uc-badge--size">${cls.size} ${T("page.classes.badge_members", "成员")}</span>`,
    `<span class="uc-badge uc-badge--domain">${cls.n_domains} ${T("page.classes.badge_domains", "领域")}</span>`,
  );
  if (cls.avg_edge_score) {
    out.push(`<span class="uc-badge uc-badge--score">avg ${cls.avg_edge_score.toFixed(2)}</span>`);
  }
  if (cls.taxonomy_match === "soc_threshold_cascade") {
    out.push(`<span class="uc-badge uc-badge--soc">SOC</span>`);
  }
  if (cls.curation_source === "manual") {
    out.push(`<span class="uc-badge uc-badge--source-manual">${T("page.classes.badge_source_manual", "人工队列来源")}</span>`);
  } else if (cls.curation_source === "llm") {
    const confLabel = cls.confidence === "high" ? T("page.classes.llm_high", "高置信") :
                      cls.confidence === "medium" ? T("page.classes.llm_medium", "中置信") : T("page.classes.llm_low", "低置信");
    const confCls = cls.confidence === "high" ? "llm-high" :
                    cls.confidence === "medium" ? "llm-med" : "llm-low";
    out.push(`<span class="uc-badge uc-badge--${confCls}">◐ ${T("page.classes.badge_source_llm", "AI 队列来源")} · ${confLabel}</span>`);
  } else {
    out.push(`<span class="uc-badge uc-badge--source-unclassified">${T("page.classes.badge_source_unclassified", "后加候选 · 来源未分类")}</span>`);
  }
  return out;
}

// Compact preview card — clickable, navigates to detail view
function renderPreviewCard(cls) {
  const uncurated = !cls.is_curated;
  const badges = buildBadges(cls);
  const extendedCounts = [];
  if (cls.shared_equations_raw && cls.shared_equations_raw.length) {
    extendedCounts.push(`${cls.shared_equations_raw.length} ${T("page.classes.count_equations", "方程")}`);
  }
  if ((currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants) && (currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants).length) {
    extendedCounts.push(`${(currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants).length} ${T("page.classes.count_invariants", "不变量")}`);
  }
  if (cls.predictions && cls.predictions.length) {
    extendedCounts.push(`${cls.predictions.length} ${T("page.classes.count_predictions", "预测")}`);
  }
  const hintRow = extendedCounts.length
    ? `<span class="uc-card__more-hint">${extendedCounts.join(' · ')}</span>`
    : '';

  return `
    <a class="uc-card uc-card--preview${uncurated ? " uc-card--uncurated" : ""}"
       href="/classes?id=${encodeURIComponent(cls.class_id)}"
       data-class-id="${escapeHtml(cls.class_id)}"
       data-evidence-recorded="${countPublicPredictionRecords(cls) > 0 ? 'true' : 'false'}">
      <div class="uc-card__head">
        <div class="uc-card__titles">
          <h2 class="uc-card__title">${escapeHtml(L(cls, "name") || T("page.classes.untitled", "(未命名)"))}</h2>
          ${cls.name_en ? `<p class="uc-card__subtitle">${escapeHtml(cls.name_en)}</p>` : ""}
        </div>
        <div class="uc-card__badges">${badges.join("")}</div>
      </div>
      <p class="uc-card__hook">${escapeHtml(classHeadline(cls))}</p>
      <div class="uc-card__hub">
        <span class="uc-card__hub-label">Hub</span>
        <span class="uc-card__hub-name">${escapeHtml(L(cls, "hub_name") || "—")}</span>
      </div>
      ${L(cls, "summary") ? `<p class="uc-card__summary">${escapeHtml(L(cls, "summary"))}</p>` : ''}
      <div class="uc-card__footer">
        ${hintRow}
        <span class="uc-card__cta">${T("page.classes.card_cta", "查看详情 →")}</span>
      </div>
    </a>
  `;
}

function renderDetail(cls) {
  const host = document.getElementById("uc-view-detail");
  if (!host) return;

  const badges = buildBadges(cls);
  const sections = [];

  if (cls.physics_prototype) {
    sections.push(`
      <section class="uc-detail__section">
        <h3 class="uc-detail__section-title">${T("page.classes.section_prototype", "物理学原型")}</h3>
        <span class="uc-prototype">${escapeHtml(L(cls, "physics_prototype") || cls.physics_prototype)}</span>
      </section>
    `);
  }
  if (cls.shared_equations_raw && cls.shared_equations_raw.length) {
    sections.push(`
      <section class="uc-detail__section">
        <h3 class="uc-detail__section-title">${T("page.classes.section_equations", "候选共享方程")}</h3>
        <p class="uc-detail__section-sub">${T("page.classes.section_equations_sub", "V3 抽取的 TeX-ish 方程，跨 pair 聚合。")}</p>
        ${renderEquations(cls.shared_equations_raw)}
      </section>
    `);
  }
  if ((currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants) && (currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants).length) {
    sections.push(`
      <section class="uc-detail__section">
        <h3 class="uc-detail__section-title">${T("page.classes.section_invariants", "候选不变量")}</h3>
        ${renderInvariants((currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants))}
      </section>
    `);
  }
  sections.push(`
    <section class="uc-detail__section">
      <h3 class="uc-detail__section-title">${T("page.classes.section_members", "成员（按领域分组，★ 为 hub）")}</h3>
      ${renderMembers(cls.members_by_domain, cls.hub_name)}
    </section>
  `);
  if (cls.predictions && cls.predictions.length) {
    sections.push(`
      <section class="uc-detail__section">
        <h3 class="uc-detail__section-title">${T("page.classes.section_predictions", "历史分析记录（结构化公开字段）")}</h3>
        ${renderPredictions(cls.predictions)}
      </section>
    `);
  }

  host.innerHTML = `
    <nav class="uc-detail__breadcrumb">
      <a href="/classes" data-back-link>${T("page.classes.back_to_list", "← 返回普适类列表")}</a>
    </nav>

    <header class="uc-detail__head">
      <div class="uc-detail__titles">
        <h1 class="uc-detail__title">${escapeHtml(L(cls, "name") || T("page.classes.untitled", "(未命名)"))}</h1>
        ${cls.name_en ? `<p class="uc-detail__subtitle">${escapeHtml(cls.name_en)}</p>` : ""}
      </div>
      <div class="uc-detail__badges">${badges.join("")}</div>
    </header>

    <div class="uc-detail__hub">
      <span class="uc-detail__hub-label">${T("page.classes.hub_label", "Hub 节点")}</span>
      <span class="uc-detail__hub-name">${escapeHtml(L(cls, "hub_name") || "—")}</span>
    </div>

    <p class="uc-detail__hook">${escapeHtml(classHeadline(cls))}</p>

    ${L(cls, "summary") ? `<p class="uc-detail__lede">${escapeHtml(L(cls, "summary"))}</p>` : ''}

    <div class="uc-detail__cta-card">
      <div class="uc-detail__cta-text">
        <h3 class="uc-detail__cta-title">${T("page.classes.cta_title", "用这个模式分析你自己的问题")}</h3>
        <p class="uc-detail__cta-sub">${T("page.classes.cta_sub", "把你关心的现象输进去，看看哪些领域可能提供可检验的结构线索。")}</p>
      </div>
      <a class="uc-detail__cta-btn" href="${classAnalyzeHref(cls)}"${cls && cls.hub_id ? '' : ` data-private-class-query="${escapeHtml(classAnalyzeSeed(cls))}"`}>
        ${T("page.classes.cta_btn", "开始分析")}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
      </a>
    </div>

    <div class="uc-detail__body">
      ${sections.join("")}
    </div>

    <div class="uc-detail__share">
      <div class="uc-detail__share-head">
        <span class="uc-detail__share-label">${T("page.classes.share_label", "分享这个模式")}</span>
        <span class="uc-detail__share-hint">${T("page.classes.share_hint", "复制链接直达这一类，或生成图片卡片。")}</span>
      </div>
      <div class="uc-detail__share-actions"></div>
    </div>

    <footer class="uc-detail__footer">
      <a href="/classes" data-back-link class="uc-detail__back-btn">${T("page.classes.back_to_list", "← 返回普适类列表")}</a>
    </footer>
  `;

  // Wire share actions (DOM nodes for event safety).
  const shareHost = host.querySelector('.uc-detail__share-actions');
  if (shareHost && window.ShareCard && window.ShareCard.buildActions) {
    const headline = classHeadline(cls);
    const domains = (currentLang() === 'en' ? cls.domains_en : cls.domains) || cls.domains || [];
    shareHost.appendChild(window.ShareCard.buildActions({
      url: classShareUrl(cls),
      shareTitle: headline,
      shareText: headline + ' — Structural 跨领域结构同构引擎',
      filename: 'structural-class-' + cls.class_id + '.png',
      cardData: {
        eyebrow: '跨域候选分组 · ' + (cls.n_domains || domains.length) + ' 个领域',
        headline: headline,
        lineA: L(cls, 'name') || '',
        lineB: L(cls, 'physics_prototype') || cls.physics_prototype || '',
        footnote: L(cls, 'summary') || '',
        url: 'structural.bytedance.city',
      },
    }));
  }

  // KaTeX render
  if (window.renderMathInElement) {
    try {
      window.renderMathInElement(host, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\[", right: "\\]", display: true },
          { left: "\\(", right: "\\)", display: false },
        ],
        throwOnError: false,
      });
    } catch (_) {}
  }

  // Intercept back-links for SPA navigation
  host.querySelectorAll('[data-back-link]').forEach((a) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      navigate(null);
    });
  });
  const privateSearchCta = host.querySelector('[data-private-class-query]');
  if (privateSearchCta) {
    privateSearchCta.addEventListener('click', (event) => {
      event.preventDefault();
      const query = privateSearchCta.getAttribute('data-private-class-query') || '';
      if (!query || typeof window.buildPrivateSearchUrl !== 'function') {
        if (typeof window.announcePrivateNavigationError === 'function') {
          window.announcePrivateNavigationError('helper_unavailable');
        }
        return;
      }
      const destination = window.buildPrivateSearchUrl({
        query,
        lang: currentLang(),
        source: 'class',
      });
      if (destination) window.location.assign(destination);
    });
  }
}

// SESSION-18 (D): "学习路径" view — group the 26 classes into 3 progressive
// bands by how many domains they span, so the page reads as a curriculum
// while domain count remains a coverage label rather than evidence strength.
const PATH_BANDS = [
  {
    id: 'focused',
    title: '入门 · 聚焦少数领域',
    desc: '先从覆盖 2–4 个领域的候选分组入手，逐项核对变量映射、数据和反例。',
    test: (c) => (c.n_domains || 0) <= 4,
  },
  {
    id: 'broad',
    title: '进阶 · 跨多个领域',
    desc: '这些候选分组覆盖 5–8 个领域；范围更广也意味着异质性和错配风险更高。',
    test: (c) => (c.n_domains || 0) >= 5 && (c.n_domains || 0) <= 8,
  },
  {
    id: 'universal',
    title: '广域候选 · 覆盖较多领域',
    desc: '覆盖 9 个以上领域只表示聚类范围，不能证明各系统具有同一结构或共同机制。',
    test: (c) => (c.n_domains || 0) >= 9,
  },
];

function renderPathGroups(host, list) {
  const sorted = list.slice().sort((a, b) => (a.n_domains || 0) - (b.n_domains || 0));
  const blocks = PATH_BANDS.map((band, idx) => {
    const members = sorted.filter(band.test);
    if (!members.length) return '';
    return `
      <section class="uc-path-band">
        <div class="uc-path-band__head">
          <span class="uc-path-band__step">${idx + 1}</span>
          <div class="uc-path-band__meta">
            <h2 class="uc-path-band__title">${escapeHtml(T('page.classes.path_' + band.id + '_title', band.title))}</h2>
            <p class="uc-path-band__desc">${escapeHtml(T('page.classes.path_' + band.id + '_desc', band.desc))}</p>
          </div>
          <span class="uc-path-band__count">${members.length}</span>
        </div>
        <div class="uc-path-band__grid">${members.map(renderPreviewCard).join('')}</div>
      </section>
    `;
  }).join('');
  host.innerHTML = `<div class="uc-path">${blocks}</div>`;
}

function renderList(list) {
  const host = document.getElementById("uc-list");
  if (!host) return;
  if (!list || !list.length) {
    host.innerHTML = `<p style="color:#777;padding:40px 0;text-align:center;">${T("page.classes.no_match", "没有匹配的等价类")}。</p>`;
    return;
  }
  if (currentFilter === 'path') {
    renderPathGroups(host, list);
  } else {
    host.innerHTML = list.map(renderPreviewCard).join("");
  }

  // Intercept card clicks for SPA nav
  host.querySelectorAll('.uc-card--preview').forEach((card) => {
    card.addEventListener('click', (e) => {
      // Allow cmd/ctrl click to open in new tab
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
      e.preventDefault();
      const id = card.dataset.classId;
      if (id) {
        lastFocusedClassId = id;
        navigate(id);
      }
    });
  });
}

function showView(which) {
  const list = document.getElementById("uc-view-list");
  const detail = document.getElementById("uc-view-detail");
  const footnote = document.getElementById("uc-footnote");
  if (which === 'detail') {
    if (list) list.setAttribute('hidden', '');
    if (detail) detail.removeAttribute('hidden');
    if (footnote) footnote.setAttribute('hidden', '');
  } else {
    if (list) list.removeAttribute('hidden');
    if (detail) detail.setAttribute('hidden', '');
    if (footnote) footnote.removeAttribute('hidden');
  }
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function focusDetailEntry() {
  const detail = document.getElementById("uc-view-detail");
  const target = detail && (detail.querySelector("[data-back-link]") || detail.querySelector(".uc-detail__title"));
  if (target && typeof target.focus === "function") target.focus({ preventScroll: true });
}

function restoreOriginCardFocus() {
  if (!lastFocusedClassId) return;
  const cards = document.querySelectorAll("#uc-list .uc-card--preview");
  const target = Array.from(cards).find((card) => card.dataset.classId === lastFocusedClassId);
  if (target && typeof target.focus === "function") target.focus({ preventScroll: true });
}

function navigate(classId, replace) {
  if (classId) {
    const cls = allClasses.find((c) => c.class_id === classId);
    if (!cls) return;
    renderDetail(cls);
    showView('detail');
    focusDetailEntry();
    const url = `/classes?id=${encodeURIComponent(classId)}`;
    if (replace) history.replaceState({ classId }, '', url);
    else history.pushState({ classId }, '', url);
    document.title = `${L(cls, "name")} — ${T("nav.universality_classes", "普适类")} · Structural`;
  } else {
    renderCurrentList();
    showView('list');
    restoreOriginCardFocus();
    if (replace) history.replaceState({}, '', '/classes');
    else history.pushState({}, '', '/classes');
    document.title = T('nav.universality_classes', '普适类') + ' — Structural';
  }
}

function handlePopState() {
  const _qp = new URLSearchParams(window.location.search);
  const id = _qp.get('id') || _qp.get('c');
  if (id) {
    const cls = allClasses.find((c) => c.class_id === id);
    if (cls) {
      renderDetail(cls);
      showView('detail');
      focusDetailEntry();
      document.title = `${L(cls, "name")} — ${T("nav.universality_classes", "普适类")} · Structural`;
      return;
    }
  }
  renderCurrentList();
  showView('list');
  restoreOriginCardFocus();
  document.title = T('nav.universality_classes', '普适类') + ' — Structural';
}

function currentClassSource() {
  return currentFilter === "manual" ? manualClasses :
         currentFilter === "llm" ? llmClasses :
         currentFilter === "unclassified" ? unclassifiedClasses : allClasses;
}

function renderCurrentList() {
  renderList(currentClassSource());
}

function applyFilter(filter) {
  currentFilter = filter;
  document.querySelectorAll(".uc-filter__btn").forEach((btn) => {
    btn.classList.toggle("uc-filter__btn--active", btn.dataset.filter === filter);
  });
  // "path" groups all classes into a curriculum; manual/llm filter the flat
  // list; "all" is the flat list of everything.
  renderCurrentList();
}

function bindFilter() {
  document.querySelectorAll(".uc-filter__btn").forEach((btn) => {
    btn.addEventListener("click", () => applyFilter(btn.dataset.filter));
  });
}

function updateFilterCounts() {
  const m = document.querySelector("[data-count-manual]");
  const l = document.querySelector("[data-count-llm]");
  const u = document.querySelector("[data-count-unclassified]");
  const a = document.querySelector("[data-count-all]");
  if (m) m.textContent = manualClasses.length;
  if (l) l.textContent = llmClasses.length;
  if (u) u.textContent = unclassifiedClasses.length;
  if (a) a.textContent = allClasses.length;
}

async function init() {
  try {
    const data = await loadData();
    window.__classesData = data;
    allClasses = data.classes || [];
    manualClasses = allClasses.filter((c) => c.curation_source === "manual");
    llmClasses = allClasses.filter((c) => c.curation_source === "llm");
    unclassifiedClasses = allClasses.filter((c) => c.curation_source !== "manual" && c.curation_source !== "llm");
    renderClassDatasetCopy(allClasses);
    renderHeroStats(allClasses);
    bindFilter();
    updateFilterCounts();
    applyFilter("all");

    // Routing: if URL has ?id=... or ?c=... (SESSION-18 share alias),
    // show the detail view directly.
    const _qp = new URLSearchParams(window.location.search);
    const initialId = _qp.get('id') || _qp.get('c');
    if (initialId) {
      const cls = allClasses.find((c) => c.class_id === initialId);
      if (cls) {
        renderDetail(cls);
        showView('detail');
        document.title = `${L(cls, "name")} — ${T("nav.universality_classes", "普适类")} · Structural`;
        history.replaceState({ classId: initialId }, '', window.location.pathname + window.location.search);
      }
    }
    window.addEventListener('popstate', handlePopState);
  } catch (e) {
    // P0-4 (SESSION-17): friendly error state — never dump the raw exception.
    console.error('[classes] load failed');
    const host = document.getElementById("uc-list");
    if (host) {
      host.innerHTML = `<p style="color:var(--text-secondary,#52525b);padding:40px 0;text-align:center;font-size:14px;">${T("page.classes.load_failed", "内容暂时加载不出来，请稍后重试。")}</p>`;
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// Re-render when user flips the language toggle (or when initial ui/content.json load finishes).
function _classesRerender() {
  try {
    if (typeof window.__classesData !== 'undefined' && window.__classesData) {
      renderClassDatasetCopy(allClasses);
      renderHeroStats(allClasses);
      const qp = new URLSearchParams(window.location.search);
      const classId = qp.get('id') || qp.get('c');
      const cls = classId && allClasses.find((item) => item.class_id === classId);
      // Keep the hidden list synchronized too. A user may switch language in
      // detail view and then return without another i18n event.
      renderCurrentList();
      if (cls) {
        renderDetail(cls);
        showView('detail');
        document.title = `${L(cls, "name")} — ${T("nav.universality_classes", "普适类")} · Structural`;
      }
    } else if (typeof render === 'function') {
      render();
    }
  } catch (e) { console.warn('[classes] i18n rerender failed'); }
}
try {
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(_classesRerender);
  }
} catch (e) { /* i18n.js not loaded — stay on zh */ }
