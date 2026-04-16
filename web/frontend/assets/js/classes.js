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
      if (p.test_method) meta.push(`<div><span class="uc-pred__meta-key">方法</span>${escapeHtml(p.test_method)}</div>`);
      if (p.data_source) meta.push(`<div><span class="uc-pred__meta-key">数据</span>${escapeHtml(p.data_source)}</div>`);
      if (p.sample_size) meta.push(`<div><span class="uc-pred__meta-key">样本量</span>${escapeHtml(p.sample_size)}</div>`);
      if (p.paper_target) meta.push(`<div><span class="uc-pred__meta-key">目标期刊</span>${escapeHtml(p.paper_target)}</div>`);
      const rationale = p.rationale
        ? `<p class="uc-pred__rationale">${escapeHtml(p.rationale)}</p>`
        : "";
      const statusCls = (p.status && (p.status.includes("已验证") || p.status.includes("✅")))
        ? "uc-pred__status uc-pred__status--verified"
        : "uc-pred__status";
      const paperLink = p.paper_url
        ? `<a class="uc-pred__paper-link" href="${escapeHtml(p.paper_url)}"${p.paper_title ? ` title="${escapeHtml(p.paper_title)}"` : ""}>📄 论文 →</a>`
        : "";
      return `
        <div class="uc-pred${statusCls.includes('verified') ? ' uc-pred--verified' : ''}">
          <div class="uc-pred__header">
            <div class="uc-pred__target">${escapeHtml(p.target || "")}</div>
            ${p.status ? `<span class="${statusCls}">${escapeHtml(p.status)}</span>` : ""}
            ${paperLink}
          </div>
          <p class="uc-pred__text">${escapeHtml(p.prediction || "")}</p>
          ${rationale}
          ${meta.length ? `<div class="uc-pred__meta">${meta.join("")}</div>` : ""}
        </div>
      `;
    })
    .join("");
}

function renderCard(cls) {
  const uncurated = !cls.is_curated;
  const isLlm = cls.curation_source === "llm";
  const badges = [];
  badges.push(
    `<span class="uc-badge uc-badge--size">${cls.size} 成员</span>`,
    `<span class="uc-badge uc-badge--domain">${cls.n_domains} 领域</span>`
  );
  if (cls.avg_edge_score) {
    badges.push(`<span class="uc-badge uc-badge--score">avg ${cls.avg_edge_score.toFixed(2)}</span>`);
  }
  if (cls.taxonomy_match === "soc_threshold_cascade") {
    badges.push(`<span class="uc-badge uc-badge--soc">SOC</span>`);
  }
  if (isLlm) {
    const confLabel = cls.confidence === "high" ? "高置信" :
                      cls.confidence === "medium" ? "中置信" : "低置信";
    const confCls = cls.confidence === "high" ? "llm-high" :
                    cls.confidence === "medium" ? "llm-med" : "llm-low";
    badges.push(`<span class="uc-badge uc-badge--${confCls}">◐ LLM · ${confLabel}</span>`);
  }

  // Compact preview (always visible) — just the 2-line summary
  const previewParts = [];
  if (cls.summary_zh) {
    previewParts.push(`<p class="uc-card__summary">${escapeHtml(cls.summary_zh)}</p>`);
  }

  // Count of extended content to show hint
  const extendedCounts = [];
  if (cls.shared_equations_raw && cls.shared_equations_raw.length) {
    extendedCounts.push(`${cls.shared_equations_raw.length} 方程`);
  }
  if (cls.invariants && cls.invariants.length) {
    extendedCounts.push(`${cls.invariants.length} 不变量`);
  }
  if (cls.predictions && cls.predictions.length) {
    extendedCounts.push(`${cls.predictions.length} 预测`);
  }

  // Expandable sections — physics_prototype moves here
  const sections = [];

  if (cls.physics_prototype) {
    sections.push(`
      <div class="uc-card__section">
        <h3 class="uc-card__section-title">物理学原型</h3>
        <span class="uc-prototype">${escapeHtml(cls.physics_prototype)}</span>
      </div>
    `);
  }

  if (cls.shared_equations_raw && cls.shared_equations_raw.length) {
    sections.push(`
      <div class="uc-card__section">
        <h3 class="uc-card__section-title">共享方程（V3 自带，跨 pair 聚合）</h3>
        ${renderEquations(cls.shared_equations_raw)}
      </div>
    `);
  }

  if (cls.invariants && cls.invariants.length) {
    sections.push(`
      <div class="uc-card__section">
        <h3 class="uc-card__section-title">共享不变量</h3>
        ${renderInvariants(cls.invariants)}
      </div>
    `);
  }

  sections.push(`
    <div class="uc-card__section">
      <h3 class="uc-card__section-title">成员（按领域分组，★ 为 hub）</h3>
      ${renderMembers(cls.members_by_domain, cls.hub_name)}
    </div>
  `);

  if (cls.predictions && cls.predictions.length) {
    sections.push(`
      <div class="uc-card__section">
        <h3 class="uc-card__section-title">可验证预测</h3>
        ${renderPredictions(cls.predictions)}
      </div>
    `);
  }

  if (isLlm && cls.notes) {
    sections.push(`
      <div class="uc-card__section uc-card__section--note">
        <h3 class="uc-card__section-title">LLM 批注</h3>
        <p class="uc-note">${escapeHtml(cls.notes)}</p>
      </div>
    `);
  }

  const hintRow = extendedCounts.length
    ? `<div class="uc-card__more-hint">${extendedCounts.join(' · ')}</div>`
    : '';

  return `
    <article class="uc-card${uncurated ? " uc-card--uncurated" : ""}" data-expanded="false">
      <div class="uc-card__head">
        <div class="uc-card__titles">
          <h2 class="uc-card__title">${escapeHtml(cls.name_zh || "(未命名)")}</h2>
          ${cls.name_en ? `<p class="uc-card__subtitle">${escapeHtml(cls.name_en)}</p>` : ""}
        </div>
        <div class="uc-card__badges">${badges.join("")}</div>
      </div>
      <div class="uc-card__hub">
        <span class="uc-card__hub-label">Hub</span>
        <span class="uc-card__hub-name">${escapeHtml(cls.hub_name || "—")}</span>
      </div>
      ${previewParts.join("")}
      <div class="uc-card__expandable" hidden>
        ${sections.join("")}
      </div>
      <button type="button" class="uc-card__toggle" aria-expanded="false">
        <span class="uc-card__toggle-text">展开详情</span>
        ${hintRow}
        <svg class="uc-card__toggle-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
    </article>
  `;
}

function bindCardToggles(host) {
  host.querySelectorAll('.uc-card__toggle').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const card = btn.closest('.uc-card');
      if (!card) return;
      const expandable = card.querySelector('.uc-card__expandable');
      const expanded = card.dataset.expanded === 'true';
      card.dataset.expanded = expanded ? 'false' : 'true';
      btn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      btn.querySelector('.uc-card__toggle-text').textContent = expanded ? '展开详情' : '收起';
      if (expandable) {
        if (expanded) expandable.setAttribute('hidden', '');
        else expandable.removeAttribute('hidden');
      }
      // Render KaTeX only on first expand (guard against re-render)
      if (!expanded && window.renderMathInElement && card.dataset.katexRendered !== 'true') {
        try {
          window.renderMathInElement(card, {
            delimiters: [
              { left: "$$", right: "$$", display: true },
              { left: "$", right: "$", display: false },
              { left: "\\[", right: "\\]", display: true },
              { left: "\\(", right: "\\)", display: false },
            ],
            throwOnError: false,
          });
          card.dataset.katexRendered = 'true';
        } catch (_) {}
      }
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
  host.innerHTML = list.map(renderCard).join("");
  bindCardToggles(host);
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
    } catch (e) {
      console.warn("KaTeX render failed", e);
    }
  }
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
