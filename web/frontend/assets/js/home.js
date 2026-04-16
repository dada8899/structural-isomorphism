/**
 * Structural — Home page logic
 */

// === Demo rotations (hand-picked canonical examples) ===
const DEMO_EXAMPLES = [
  {
    a: {
      domain: '核物理',
      name: '放射性衰变',
      desc: '不稳定的原子核自发释放粒子。释放速度只取决于当前剩余的数量——剩得越少越慢。',
    },
    b: {
      domain: '药理学',
      name: '药物浓度下降',
      desc: '口服后血液中浓度按固定比率降低。代谢速率和当前浓度成正比——越少代谢越慢。',
    },
    score: 94,
    caption: '它们看起来毫无关系，却服从<strong>完全相同</strong>的数学方程。',
  },
  {
    a: {
      domain: '微生物学',
      name: '细菌培养基中的种群增长',
      desc: '起初指数增长，接近承载量时增速骤降，最终趋于稳定——形成经典的 S 型曲线。',
    },
    b: {
      domain: '商业',
      name: '产品用户增长',
      desc: '早期口碑传播带来指数增长，市场渗透到一定程度后见顶，最终进入存量替代期。',
    },
    score: 91,
    caption: '细菌和产品，在同一条<strong>逻辑斯谛曲线</strong>上。',
  },
  {
    a: {
      domain: '流行病学',
      name: '疫情传播',
      desc: '易感人群接触感染者后被传染，一人传多人，直到免疫或隔离让传播停止。',
    },
    b: {
      domain: '传播学',
      name: '社交媒体谣言扩散',
      desc: '一个人分享，他的朋友分享，指数级蔓延。直到触达饱和或被事实核查打断。',
    },
    score: 93,
    caption: '病毒和信息，遵循<strong>同一个 SIR 模型</strong>。',
  },
  {
    a: {
      domain: '凝聚态物理',
      name: '磁铁的磁滞',
      desc: '外磁场增加时磁化缓慢变化，过阈值后突然翻转；即便磁场回到原位，磁化也不回到初始。',
    },
    b: {
      domain: '生态学',
      name: '湖泊富营养化',
      desc: '营养物缓慢增加时水质缓慢变化，过阈值后突然暴发藻华；即便减少营养，生态也难恢复。',
    },
    score: 96,
    caption: '两个系统都在同一个<strong>尖点灾变曲面</strong>上滑动。',
  },
  {
    a: {
      domain: '力学',
      name: '简谐振子',
      desc: '弹簧拉开后松手，质量块来回振荡；每次偏离平衡位置越远，回复力就越大。',
    },
    b: {
      domain: '经济学',
      name: '供需价格波动',
      desc: '价格偏离均衡时供需关系产生反作用力拉回，但惯性让它冲过均衡点，形成周期性震荡。',
    },
    score: 88,
    caption: '弹簧和市场，都服从<strong>受驱简谐振动方程</strong>。',
  },
];

// === Search box placeholders (used by single-line input only, not textarea) ===
const PLACEHOLDER_TEXTS = [
  '我们的产品增长放缓了...',
  '为什么市场会崩盘',
  '用户老客户越来越不活跃，怎么看',
  '为什么有些市场必然赢家通吃',
];

// === Typewriter placeholder ===
class Typewriter {
  constructor(input, texts) {
    this.input = input;
    this.texts = texts;
    this.idx = 0;
    this.charIdx = 0;
    this.mode = 'typing'; // typing | pausing | deleting
    this.pauseFrames = 0;
    this.running = false;
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.tick();
  }

  stop() {
    this.running = false;
  }

  tick() {
    if (!this.running) return;
    if (document.activeElement === this.input) {
      // User is typing, reset to plain placeholder
      this.input.setAttribute('placeholder', '描述一个你观察到的现象...');
      this.charIdx = 0;
      this.mode = 'typing';
      setTimeout(() => this.tick(), 800);
      return;
    }

    const current = this.texts[this.idx];
    if (this.mode === 'typing') {
      this.charIdx++;
      this.input.setAttribute('placeholder', current.slice(0, this.charIdx) + '▍');
      if (this.charIdx >= current.length) {
        this.mode = 'pausing';
        this.pauseFrames = 28; // ~2s pause
      }
      setTimeout(() => this.tick(), 55 + Math.random() * 40);
    } else if (this.mode === 'pausing') {
      this.input.setAttribute('placeholder', current);
      this.pauseFrames--;
      if (this.pauseFrames <= 0) {
        this.mode = 'deleting';
      }
      setTimeout(() => this.tick(), 80);
    } else if (this.mode === 'deleting') {
      this.charIdx--;
      this.input.setAttribute('placeholder', current.slice(0, Math.max(0, this.charIdx)) + '▍');
      if (this.charIdx <= 0) {
        this.mode = 'typing';
        this.idx = (this.idx + 1) % this.texts.length;
      }
      setTimeout(() => this.tick(), 25);
    }
  }
}

// === Hero inline evidence rotator ===
// Compact one-line version of DEMO_EXAMPLES that lives directly inside the hero,
// above the search box. Auto-rotates every 5.5s, manual click to advance.
let _heroIdx = 0;
let _heroInterval = null;

function renderHeroEvidence(idx, animate) {
  const wrapper = $('#hero-evidence');
  if (!wrapper) return;
  const card = wrapper.querySelector('.hero-evidence__card');
  const ex = DEMO_EXAMPLES[idx];
  if (!ex) return;
  const apply = () => {
    const set = (sel, val) => { const el = $(sel); if (el) el.textContent = val; };
    set('#he-a-domain', ex.a.domain);
    set('#he-a-name', ex.a.name);
    set('#he-a-desc', ex.a.desc || '');
    set('#he-b-domain', ex.b.domain);
    set('#he-b-name', ex.b.name);
    set('#he-b-desc', ex.b.desc || '');
    const cap = $('#he-caption');
    if (cap) cap.innerHTML = ex.caption || '';
    // Update dots
    const dots = $('#he-dots');
    if (dots) {
      dots.querySelectorAll('.hero-evidence__dot').forEach((d, i) => {
        d.setAttribute('aria-selected', i === idx ? 'true' : 'false');
        d.classList.toggle('is-active', i === idx);
      });
    }
  };
  if (animate && card) {
    card.style.opacity = '0';
    card.style.transition = 'opacity 180ms var(--ease-out)';
    setTimeout(() => {
      apply();
      card.style.opacity = '1';
    }, 180);
  } else {
    apply();
  }
}

function nextHeroEvidence() {
  _heroIdx = (_heroIdx + 1) % DEMO_EXAMPLES.length;
  renderHeroEvidence(_heroIdx, true);
}

function startHeroEvidenceTimer() {
  if (_heroInterval) clearInterval(_heroInterval);
  _heroInterval = setInterval(nextHeroEvidence, 5500);
}

function initHeroEvidence() {
  renderHeroEvidence(_heroIdx, false);
  startHeroEvidenceTimer();
  const rotateBtn = $('#he-rotate');
  if (rotateBtn) {
    rotateBtn.addEventListener('click', () => {
      nextHeroEvidence();
      startHeroEvidenceTimer();
    });
  }
  const wrapper = $('.home__hero-evidence');
  if (wrapper) {
    wrapper.addEventListener('mouseenter', () => {
      if (_heroInterval) clearInterval(_heroInterval);
    });
    wrapper.addEventListener('mouseleave', startHeroEvidenceTimer);
  }
}

// === Search form ===
function initSearch() {
  const form = $('#search-form');
  const input = $('.searchbox__input');

  if (form && input) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (q) {
        window.location.href = `/search?q=${encodeURIComponent(q)}`;
      }
    });

    // Cmd/Ctrl + Enter submits
    input.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        form.requestSubmit();
      }
    });

    // Auto-grow textarea
    if (input.tagName === 'TEXTAREA') {
      const autoGrow = () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 400) + 'px';
      };
      input.addEventListener('input', autoGrow);
    }
  }
}

// === Suggestions ===
// Curated example queries — covers PM, engineering, strategy, data, management.
// We override the server-provided list because those are too "popular science"
// for the target user (researchers/PMs/strategists).
const EXAMPLE_CHIPS = [
  '团队从 8 人扩到 25 人后决策速度慢了一半',
  '我们产品的 D30 留存卡在 18% 上不去',
  '分布式系统加机器后吞吐反而下降',
  '为什么市场越成熟，创新反而越慢',
  '实验组数据漂亮但长期指标背离',
];

function renderSuggestions(_suggestionsFromServer) {
  const container = $('#home-suggestions');
  if (!container) return;

  container.innerHTML = `
    <div class="home__suggestions-label">试试这些真实场景</div>
    ${EXAMPLE_CHIPS.map((s) => `
      <button type="button" class="chip" data-query="${escapeHtml(s)}">${escapeHtml(s)}</button>
    `).join('')}
  `;

  container.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (chip) {
      const q = chip.dataset.query;
      const input = $('.searchbox__input');
      if (input) {
        input.value = q;
        input.focus();
        setTimeout(() => {
          window.location.href = `/search?q=${encodeURIComponent(q)}`;
        }, 150);
      }
    }
  });
}

// === Daily discoveries ===
function renderDaily(discoveries) {
  const grid = $('#daily-grid');
  if (!grid || !discoveries.length) return;

  grid.innerHTML = discoveries.map((d, i) => {
    const structureId = d.a.type_id || '—';
    const scorePct = formatScore(d.similarity);
    return `
      <article class="disc-card" data-a="${escapeHtml(d.a.id)}" data-b="${escapeHtml(d.b.id)}" style="animation: fadeInUp 600ms var(--ease-out-expo) ${1000 + i * 100}ms both">
        <header class="disc-card__header">
          <span class="disc-card__structure">结构 ${escapeHtml(structureId)}</span>
          <span class="disc-card__score">${scorePct}</span>
        </header>
        <div class="disc-card__item">
          <div class="disc-card__domain">${escapeHtml(d.a.domain)}</div>
          <div class="disc-card__name">${escapeHtml(d.a.name)}</div>
        </div>
        <div class="disc-card__divider">
          <span class="disc-card__divider-line"></span>
          <span class="disc-card__divider-symbol">≅</span>
          <span class="disc-card__divider-line"></span>
        </div>
        <div class="disc-card__item">
          <div class="disc-card__domain">${escapeHtml(d.b.domain)}</div>
          <div class="disc-card__name">${escapeHtml(d.b.name)}</div>
        </div>
      </article>
    `;
  }).join('');

  grid.addEventListener('click', (e) => {
    const card = e.target.closest('.disc-card');
    if (card) {
      const a = card.dataset.a;
      const b = card.dataset.b;
      if (a && b) {
        // Phase 2: jump straight to the 8-section deep analysis report,
        // matching the discoveries page CTA convention.
        window.location.href = `/analyze?a_id=${encodeURIComponent(a)}&id=${encodeURIComponent(b)}`;
      }
    }
  });
}

// === Local history chips ===
function renderHistory() {
  const section = $('#home-history');
  const chipsEl = $('#home-history-chips');
  if (!section || !chipsEl) return;

  const list = (window.getHistory && window.getHistory()) || [];
  const recent = list.slice(0, 6);
  if (recent.length === 0) {
    section.setAttribute('hidden', '');
    return;
  }
  section.removeAttribute('hidden');

  chipsEl.innerHTML = recent.map((it) => {
    const q = it && it.query ? String(it.query) : '';
    if (!q) return '';
    return `<button type="button" class="chip chip--history" data-query="${escapeHtml(q)}">${escapeHtml(q)}</button>`;
  }).filter(Boolean).join('');

  chipsEl.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip--history');
    if (!chip) return;
    const q = chip.dataset.query;
    if (q) window.location.href = `/search?q=${encodeURIComponent(q)}`;
  });
}

// === Favorited reports ===
function renderFavorites() {
  const section = $('#home-favorites');
  const listEl = $('#home-favorites-list');
  if (!section || !listEl) return;

  const favs = (window.getFavorites && window.getFavorites()) || [];
  if (favs.length === 0) {
    section.setAttribute('hidden', '');
    return;
  }
  section.removeAttribute('hidden');

  listEl.innerHTML = favs.map((f) => {
    const href = f && f.analyze_url ? f.analyze_url : '/';
    // Title fallback: a_name ≅ b_name (pair mode) → query → "(未命名查询)"
    let title = '(未命名查询)';
    if (f && f.a_name && f.b_name) {
      title = `${f.a_name} ≅ ${f.b_name}`;
    } else if (f && f.query) {
      title = f.query;
    } else if (f && f.b_name) {
      title = f.b_name;
    }
    const when = f && f.timestamp ? new Date(f.timestamp).toLocaleDateString('zh-CN') : '';
    return `
      <a href="${escapeHtml(href)}" class="home__fav-card">
        <span class="home__fav-card__star">★</span>
        <div class="home__fav-card__body">
          <div class="home__fav-card__title">${escapeHtml(title)}</div>
          ${when ? `<div class="home__fav-card__time">${escapeHtml(when)}</div>` : ''}
        </div>
        <svg class="home__fav-card__arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
      </a>
    `;
  }).join('');
}

async function loadHomeData() {
  try {
    const [suggestResp, dailyResp] = await Promise.all([
      StructuralAPI.getSuggestions(),
      StructuralAPI.getDaily(),
    ]);
    renderSuggestions(suggestResp.suggestions || []);
    renderDaily(dailyResp.discoveries || []);
  } catch (err) {
    console.error('Failed to load home data:', err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  initSearch();
  initHeroEvidence();
  renderHistory();
  renderFavorites();
  loadHomeData();

  // If the URL hash is #home-favorites (from the nav link), scroll there
  if (window.location.hash === '#home-favorites') {
    requestAnimationFrame(() => {
      const el = document.getElementById('home-favorites');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  // Typewriter placeholder — only for single-line inputs.
  // (Multi-line textarea keeps its full static placeholder.)
  const input = $('.searchbox__input');
  if (input && input.tagName !== 'TEXTAREA' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const tw = new Typewriter(input, PLACEHOLDER_TEXTS);
    tw.start();
  }
});
