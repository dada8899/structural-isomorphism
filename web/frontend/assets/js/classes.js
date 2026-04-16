// --- i18n helpers ---
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
let currentFilter = "manual";

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

function renderHeroStats(stats) {
  const host = document.getElementById("uc-hero-stats");
  if (!host || !stats) return;
  const items = [
    { value: stats.n_equivalence_classes, label: "等价类总数" },
    { value: stats.n_cross_domain, label: "跨 ≥2 领域" },
    { value: stats.max_members, label: "最大成员数" },
    { value: stats.max_domains, label: "最多跨越领域" },
  ];
  host.innerHTML = items
    .map(
      (x) => `
      <div class="uc-hero__stat">
        <div class="uc-hero__stat-value">${escapeHtml(x.value ?? "—")}</div>
        <div class="uc-hero__stat-label">${escapeHtml(x.label)}</div>
      </div>
    `
    )
    .join("");
}

function renderMembers(membersByDomain, hubName) {
  if (!membersByDomain || !membersByDomain.length) return "";
  const rows = membersByDomain
    .map((row) => {
      const names = row.names
        .map((n) => {
          const isHub = n === hubName;
          return `<span class="uc-members__name${isHub ? " uc-members__name--hub" : ""}">${escapeHtml(n)}${isHub ? " ★" : ""}</span>`;
        })
        .join("");
      return `
      <div class="uc-members__row">
        <div class="uc-members__domain">${escapeHtml(row.domain)}</div>
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
        return `<div class="uc-eq-line"><span class="uc-eq-math">$$${latex}$$</span></div>`;
      }
      return `<div class="uc-eq-line"><code class="uc-eq-code">${escapeHtml(p)}</code></div>`;
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

function renderPredictions(preds) {
  if (!preds || !preds.length) return "";
  return preds
    .map((p) => {
      const meta = [];
      if (L(p, "test_method")) meta.push(`<div><span class="uc-pred__meta-key">方法</span>${escapeHtml(L(p, "test_method"))}</div>`);
      if (L(p, "data_source")) meta.push(`<div><span class="uc-pred__meta-key">数据</span>${escapeHtml(L(p, "data_source"))}</div>`);
      if (L(p, "sample_size")) meta.push(`<div><span class="uc-pred__meta-key">样本量</span>${escapeHtml(L(p, "sample_size"))}</div>`);
      if (L(p, "paper_target")) meta.push(`<div><span class="uc-pred__meta-key">目标期刊</span>${escapeHtml(L(p, "paper_target"))}</div>`);
      const rationale = L(p, "rationale")
        ? `<p class="uc-pred__rationale">${escapeHtml(L(p, "rationale"))}</p>`
        : "";
      const statusCls = (L(p, "status") && (L(p, "status").includes("已验证") || L(p, "status").includes("✅")))
        ? "uc-pred__status uc-pred__status--verified"
        : "uc-pred__status";
      const paperLink = p.paper_url
        ? `<a class="uc-pred__paper-link" href="${escapeHtml(p.paper_url)}"${p.paper_title ? ` title="${escapeHtml(p.paper_title)}"` : ""}>📄 论文 →</a>`
        : "";
      return `
        <div class="uc-pred${statusCls.includes('verified') ? ' uc-pred--verified' : ''}">
          <div class="uc-pred__header">
            <div class="uc-pred__target">${escapeHtml(L(p, "target") || "")}</div>
            ${L(p, "status") ? `<span class="${statusCls}">${escapeHtml(L(p, "status"))}</span>` : ""}
            ${paperLink}
          </div>
          <p class="uc-pred__text">${escapeHtml(L(p, "prediction") || "")}</p>
          ${rationale}
          ${meta.length ? `<div class="uc-pred__meta">${meta.join("")}</div>` : ""}
        </div>
      `;
    })
    .join("");
}

function countVerifiedPredictions(cls) {
  if (!cls || !Array.isArray(cls.predictions)) return 0;
  let n = 0;
  for (const p of cls.predictions) {
    const s = (p && L(p, "status")) || "";
    if (s.includes("已验证") || s.includes("✅")) n += 1;
  }
  return n;
}

function buildBadges(cls) {
  const isLlm = cls.curation_source === "llm";
  const nVerified = countVerifiedPredictions(cls);
  const out = [];
  // Put the verified badge FIRST so it's most prominent
  if (nVerified > 0) {
    const label = nVerified === 1 ? "✅ 已实证" : `✅ 已实证 ×${nVerified}`;
    out.push(`<span class="uc-badge uc-badge--verified" title="${nVerified} 条预测已通过实证验证">${label}</span>`);
  }
  out.push(
    `<span class="uc-badge uc-badge--size">${cls.size} 成员</span>`,
    `<span class="uc-badge uc-badge--domain">${cls.n_domains} 领域</span>`,
  );
  if (cls.avg_edge_score) {
    out.push(`<span class="uc-badge uc-badge--score">avg ${cls.avg_edge_score.toFixed(2)}</span>`);
  }
  if (cls.taxonomy_match === "soc_threshold_cascade") {
    out.push(`<span class="uc-badge uc-badge--soc">SOC</span>`);
  }
  if (isLlm) {
    const confLabel = cls.confidence === "high" ? "高置信" :
                      cls.confidence === "medium" ? "中置信" : "低置信";
    const confCls = cls.confidence === "high" ? "llm-high" :
                    cls.confidence === "medium" ? "llm-med" : "llm-low";
    out.push(`<span class="uc-badge uc-badge--${confCls}">◐ LLM · ${confLabel}</span>`);
  }
  return out;
}

// Compact preview card — clickable, navigates to detail view
function renderPreviewCard(cls) {
  const uncurated = !cls.is_curated;
  const badges = buildBadges(cls);
  const extendedCounts = [];
  if (cls.shared_equations_raw && cls.shared_equations_raw.length) {
    extendedCounts.push(`${cls.shared_equations_raw.length} 方程`);
  }
  if ((currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants) && (currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants).length) {
    extendedCounts.push(`${(currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants).length} 不变量`);
  }
  if (cls.predictions && cls.predictions.length) {
    extendedCounts.push(`${cls.predictions.length} 预测`);
  }
  const hintRow = extendedCounts.length
    ? `<span class="uc-card__more-hint">${extendedCounts.join(' · ')}</span>`
    : '';

  return `
    <a class="uc-card uc-card--preview${uncurated ? " uc-card--uncurated" : ""}"
       href="/classes?id=${encodeURIComponent(cls.class_id)}"
       data-class-id="${escapeHtml(cls.class_id)}"
       data-verified="${countVerifiedPredictions(cls) > 0 ? 'true' : 'false'}">
      <div class="uc-card__head">
        <div class="uc-card__titles">
          <h2 class="uc-card__title">${escapeHtml(L(cls, "name") || "(未命名)")}</h2>
          ${cls.name_en ? `<p class="uc-card__subtitle">${escapeHtml(cls.name_en)}</p>` : ""}
        </div>
        <div class="uc-card__badges">${badges.join("")}</div>
      </div>
      <div class="uc-card__hub">
        <span class="uc-card__hub-label">Hub</span>
        <span class="uc-card__hub-name">${escapeHtml(L(cls, "hub_name") || "—")}</span>
      </div>
      ${L(cls, "summary") ? `<p class="uc-card__summary">${escapeHtml(L(cls, "summary"))}</p>` : ''}
      <div class="uc-card__footer">
        ${hintRow}
        <span class="uc-card__cta">查看详情 →</span>
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
        <h3 class="uc-detail__section-title">物理学原型</h3>
        <span class="uc-prototype">${escapeHtml(cls.physics_prototype)}</span>
      </section>
    `);
  }
  if (cls.shared_equations_raw && cls.shared_equations_raw.length) {
    sections.push(`
      <section class="uc-detail__section">
        <h3 class="uc-detail__section-title">共享方程</h3>
        <p class="uc-detail__section-sub">V3 抽取的 TeX-ish 方程，跨 pair 聚合。</p>
        ${renderEquations(cls.shared_equations_raw)}
      </section>
    `);
  }
  if ((currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants) && (currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants).length) {
    sections.push(`
      <section class="uc-detail__section">
        <h3 class="uc-detail__section-title">共享不变量</h3>
        ${renderInvariants((currentLang()==='en' && cls.invariants_en ? cls.invariants_en : cls.invariants))}
      </section>
    `);
  }
  sections.push(`
    <section class="uc-detail__section">
      <h3 class="uc-detail__section-title">成员（按领域分组，★ 为 hub）</h3>
      ${renderMembers(cls.members_by_domain, L(cls, "hub_name"))}
    </section>
  `);
  if (cls.predictions && cls.predictions.length) {
    sections.push(`
      <section class="uc-detail__section">
        <h3 class="uc-detail__section-title">可验证预测</h3>
        ${renderPredictions(cls.predictions)}
      </section>
    `);
  }
  if (cls.curation_source === "llm" && cls.notes) {
    sections.push(`
      <section class="uc-detail__section uc-detail__section--note">
        <h3 class="uc-detail__section-title">LLM 批注</h3>
        <p class="uc-note">${escapeHtml(cls.notes)}</p>
      </section>
    `);
  }

  host.innerHTML = `
    <nav class="uc-detail__breadcrumb">
      <a href="/classes" data-back-link>← 返回普适类列表</a>
    </nav>

    <header class="uc-detail__head">
      <div class="uc-detail__titles">
        <h1 class="uc-detail__title">${escapeHtml(L(cls, "name") || "(未命名)")}</h1>
        ${cls.name_en ? `<p class="uc-detail__subtitle">${escapeHtml(cls.name_en)}</p>` : ""}
      </div>
      <div class="uc-detail__badges">${badges.join("")}</div>
    </header>

    <div class="uc-detail__hub">
      <span class="uc-detail__hub-label">Hub 节点</span>
      <span class="uc-detail__hub-name">${escapeHtml(L(cls, "hub_name") || "—")}</span>
    </div>

    ${L(cls, "summary") ? `<p class="uc-detail__lede">${escapeHtml(L(cls, "summary"))}</p>` : ''}

    <div class="uc-detail__body">
      ${sections.join("")}
    </div>

    <footer class="uc-detail__footer">
      <a href="/classes" data-back-link class="uc-detail__back-btn">← 返回普适类列表</a>
    </footer>
  `;

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
}

function renderList(list) {
  const host = document.getElementById("uc-list");
  if (!host) return;
  if (!list || !list.length) {
    host.innerHTML = `<p style="color:#777;padding:40px 0;text-align:center;">没有匹配的等价类。</p>`;
    return;
  }
  host.innerHTML = list.map(renderPreviewCard).join("");

  // Intercept card clicks for SPA nav
  host.querySelectorAll('.uc-card--preview').forEach((card) => {
    card.addEventListener('click', (e) => {
      // Allow cmd/ctrl click to open in new tab
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
      e.preventDefault();
      const id = card.dataset.classId;
      if (id) navigate(id);
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

function navigate(classId, replace) {
  if (classId) {
    const cls = allClasses.find((c) => c.class_id === classId);
    if (!cls) return;
    renderDetail(cls);
    showView('detail');
    const url = `/classes?id=${encodeURIComponent(classId)}`;
    if (replace) history.replaceState({ classId }, '', url);
    else history.pushState({ classId }, '', url);
    document.title = `${L(cls, "name")} — 普适类 · Structural`;
  } else {
    showView('list');
    history.pushState({}, '', '/classes');
    document.title = '普适类 — Structural';
  }
}

function handlePopState() {
  const id = new URLSearchParams(window.location.search).get('id');
  if (id) {
    const cls = allClasses.find((c) => c.class_id === id);
    if (cls) {
      renderDetail(cls);
      showView('detail');
      document.title = `${L(cls, "name")} — 普适类 · Structural`;
      return;
    }
  }
  showView('list');
  document.title = '普适类 — Structural';
}

function applyFilter(filter) {
  currentFilter = filter;
  document.querySelectorAll(".uc-filter__btn").forEach((btn) => {
    btn.classList.toggle("uc-filter__btn--active", btn.dataset.filter === filter);
  });
  const source = filter === "manual" ? manualClasses :
                 filter === "llm" ? llmClasses : allClasses;
  renderList(source);
}

function bindFilter() {
  document.querySelectorAll(".uc-filter__btn").forEach((btn) => {
    btn.addEventListener("click", () => applyFilter(btn.dataset.filter));
  });
}

function updateFilterCounts() {
  const m = document.querySelector("[data-count-manual]");
  const l = document.querySelector("[data-count-llm]");
  const a = document.querySelector("[data-count-all]");
  if (m) m.textContent = manualClasses.length;
  if (l) l.textContent = llmClasses.length;
  if (a) a.textContent = allClasses.length;
}

async function init() {
  try {
    const data = await loadData();
    allClasses = data.classes || [];
    manualClasses = allClasses.filter((c) => c.curation_source === "manual");
    llmClasses = allClasses.filter((c) => c.curation_source === "llm");
    renderHeroStats(data.stats);
    bindFilter();
    updateFilterCounts();
    applyFilter("manual");

    // Routing: if URL has ?id=..., show detail directly
    const initialId = new URLSearchParams(window.location.search).get('id');
    if (initialId) {
      const cls = allClasses.find((c) => c.class_id === initialId);
      if (cls) {
        renderDetail(cls);
        showView('detail');
        document.title = `${L(cls, "name")} — 普适类 · Structural`;
        history.replaceState({ classId: initialId }, '', window.location.pathname + window.location.search);
      }
    }
    window.addEventListener('popstate', handlePopState);
  } catch (e) {
    console.error(e);
    const host = document.getElementById("uc-list");
    if (host) {
      host.innerHTML = `<p style="color:#c44;padding:40px 0;text-align:center;">加载数据失败：${escapeHtml(e.message)}</p>`;
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// Re-render when user flips the language toggle.
try {
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(function () {
      try {
        if (typeof render === 'function') render();
        else if (typeof renderList === 'function') renderList();
      } catch (e) { console.warn('[classes i18n rerender]', e); }
    });
  }
} catch (e) { /* i18n.js not loaded — stay on zh */ }
