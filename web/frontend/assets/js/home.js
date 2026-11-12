function T(key, fallback) { try { if (window.i18n && typeof window.i18n.t === "function") { var v = window.i18n.t(key); if (v && v !== key) return v; } } catch(e) {} return fallback; }

/**
 * Structural — Home page logic
 */

// === Demo rotations (hand-picked canonical examples) ===
// i18n helper — read current lang from window.i18n if available
function __homeLang() { try { return (window.i18n && window.i18n.getLang && window.i18n.getLang()) || 'zh'; } catch (e) { return 'zh'; } }
function __pick(zh, en) { return __homeLang() === 'en' && en ? en : zh; }

function navigatePrivateSearch(query, source) {
  if (!query) return false;
  if (typeof window.buildPrivateSearchUrl !== 'function') {
    if (window.showToast) window.showToast('安全交接组件未加载；问题没有写入链接，请刷新后重试。');
    return false;
  }
  const url = window.buildPrivateSearchUrl({
    query,
    lang: __homeLang(),
    source: source || 'home',
  });
  if (!url) return false;
  try {
    if (!new URL(url, window.location.origin).searchParams.get('context')) {
      if (window.showToast) window.showToast('未能建立安全的本地交接；问题没有写入链接。请允许当前标签页使用会话存储后重试。');
      return false;
    }
  } catch (_) { return false; }
  window.location.assign(url);
  return true;
}

function currentResearchQueryStatus(value) {
  if (typeof window.researchQueryStatus === 'function') {
    return window.researchQueryStatus(value);
  }
  const normalized = typeof value === 'string'
    ? value.normalize('NFKC').trim().split(/\s+/u).filter(Boolean).join(' ')
    : '';
  const count = Array.from(normalized).length;
  return {
    value: normalized,
    count,
    limit: 8000,
    valid: Boolean(normalized) && count <= 8000,
    error: !normalized ? 'blank_query' : count > 8000 ? 'query_too_long' : null,
  };
}

function updateHomeQueryFeedback(input, submit) {
  const status = currentResearchQueryStatus(input ? input.value : '');
  const host = document.getElementById('search-query-feedback');
  const counter = document.getElementById('search-query-counter');
  const error = document.getElementById('search-query-error');
  const actionableError = status.error && status.error !== 'blank_query';
  if (counter) counter.textContent = `${status.count.toLocaleString()} / ${status.limit.toLocaleString()}`;
  if (host) host.dataset.state = actionableError ? 'error' : 'ready';
  if (error) {
    error.hidden = !actionableError;
    error.textContent = status.error === 'query_too_long'
      ? (__homeLang() === 'en' ? 'Shorten the question before submitting.' : '请缩短问题后再提交。')
      : actionableError
        ? (__homeLang() === 'en' ? 'Remove unsupported hidden characters or markup.' : '请移除不支持的隐藏字符或标记。')
        : '';
  }
  if (input) input.setAttribute('aria-invalid', actionableError ? 'true' : 'false');
  if (submit) submit.disabled = Boolean(actionableError);
  return status;
}

const DEMO_EXAMPLES = [
  {
    a: {
      domain: '核物理',   domain_en: 'Nuclear physics',
      name: '放射性衰变', name_en: 'Radioactive decay',
      desc: '不稳定的原子核自发释放粒子。释放速度只取决于当前剩余的数量——剩得越少越慢。',
      desc_en: 'Unstable nuclei spontaneously emit particles. The emission rate depends only on what\'s left — the less remaining, the slower it goes.',
    },
    b: {
      domain: '药理学',       domain_en: 'Pharmacology',
      name: '药物浓度下降',   name_en: 'Drug concentration decay',
      desc: '口服后血液中浓度按固定比率降低。代谢速率和当前浓度成正比——越少代谢越慢。',
      desc_en: 'After ingestion, blood concentration drops at a fixed fractional rate. Metabolism is proportional to the current concentration — the less present, the slower it clears.',
    },
    score: 94,
    caption: '在明确假设下，它们可用<strong>同一类数学模型</strong>描述；机制是否一致仍需验证。',
    caption_en: 'Under explicit assumptions, the same <strong>model family</strong> can describe both; shared mechanism still requires validation.',
  },
  {
    a: {
      domain: '微生物学',                    domain_en: 'Microbiology',
      name: '细菌培养基中的种群增长',         name_en: 'Bacterial population growth',
      desc: '起初指数增长，接近承载量时增速骤降，最终趋于稳定——形成经典的 S 型曲线。',
      desc_en: 'Exponential growth at first, slowing sharply near carrying capacity, finally stabilizing — the classic S-curve.',
    },
    b: {
      domain: '商业',             domain_en: 'Business',
      name: '产品用户增长',        name_en: 'Product user growth',
      desc: '早期口碑传播带来指数增长，市场渗透到一定程度后见顶，最终进入存量替代期。',
      desc_en: 'Word-of-mouth drives exponential growth early; once market penetration peaks, it enters a stock-replacement phase.',
    },
    score: 91,
    caption: '细菌增长和产品扩散都可尝试用<strong>逻辑斯谛模型族</strong>比较；参数与机制需分别检验。',
    caption_en: 'Bacterial growth and product diffusion can be compared with a <strong>logistic model family</strong>; parameters and mechanisms require separate tests.',
  },
  {
    a: {
      domain: '流行病学',    domain_en: 'Epidemiology',
      name: '疫情传播',      name_en: 'Epidemic spread',
      desc: '易感人群接触感染者后被传染，一人传多人，直到免疫或隔离让传播停止。',
      desc_en: 'Susceptibles catch the pathogen from infected contacts; each infects several others until immunity or isolation halts transmission.',
    },
    b: {
      domain: '传播学',             domain_en: 'Communication studies',
      name: '社交媒体谣言扩散',      name_en: 'Rumor diffusion on social media',
      desc: '一个人分享，他的朋友分享，指数级蔓延。直到触达饱和或被事实核查打断。',
      desc_en: 'One person shares, their friends share, spreading exponentially — until reach saturates or a fact-check interrupts it.',
    },
    score: 93,
    caption: '病毒与信息扩散可提出<strong>SIR 类候选映射</strong>；接触、恢复和传播假设并不相同。',
    caption_en: 'Virus and information diffusion invite a <strong>candidate SIR-like mapping</strong>; contact, recovery, and transmission assumptions differ.',
  },
  {
    a: {
      domain: '凝聚态物理',  domain_en: 'Condensed matter physics',
      name: '磁铁的磁滞',    name_en: 'Ferromagnetic hysteresis',
      desc: '外磁场增加时磁化缓慢变化，过阈值后突然翻转；即便磁场回到原位，磁化也不回到初始。',
      desc_en: 'Magnetization changes slowly as the external field grows, flips abruptly past a threshold; when the field returns, the state does not — it remembers.',
    },
    b: {
      domain: '生态学',    domain_en: 'Ecology',
      name: '湖泊富营养化', name_en: 'Lake eutrophication',
      desc: '营养物缓慢增加时水质缓慢变化，过阈值后突然暴发藻华；即便减少营养，生态也难恢复。',
      desc_en: 'Water quality drifts slowly as nutrients rise, then crosses a threshold and the lake erupts into algal bloom; reducing nutrients does not easily reverse it.',
    },
    score: 96,
    caption: '磁滞与湖泊翻转可用<strong>尖点灾变候选模型</strong>比较；是否适用仍需数据检验。',
    caption_en: 'Magnetic hysteresis and lake shifts can be compared with a <strong>candidate cusp-catastrophe model</strong>; data must test whether it applies.',
  },
  {
    a: {
      domain: '力学',   domain_en: 'Mechanics',
      name: '简谐振子', name_en: 'Simple harmonic oscillator',
      desc: '弹簧拉开后松手，质量块来回振荡；每次偏离平衡位置越远，回复力就越大。',
      desc_en: 'A stretched spring released — the mass oscillates back and forth; the further it strays from equilibrium, the stronger the restoring force.',
    },
    b: {
      domain: '经济学',    domain_en: 'Economics',
      name: '供需价格波动', name_en: 'Supply-demand price oscillations',
      desc: '价格偏离均衡时供需关系产生反作用力拉回，但惯性让它冲过均衡点，形成周期性震荡。',
      desc_en: 'When price departs from equilibrium, supply and demand produce a restoring force; inertia carries it past equilibrium, producing periodic oscillations.',
    },
    score: 88,
    caption: '弹簧与市场波动可提出<strong>受驱振子类比</strong>；市场反馈不等于机械回复力。',
    caption_en: 'Springs and market fluctuations invite a <strong>driven-oscillator analogy</strong>; market feedback is not a mechanical restoring force.',
  },
];

// === Search box placeholders (used by single-line input only, not textarea) ===
const PLACEHOLDER_TEXTS_ZH = [
  '我们的产品增长放缓了...',
  '为什么市场会崩盘',
  '用户老客户越来越不活跃，怎么看',
  '为什么有些市场必然赢家通吃',
];
const PLACEHOLDER_TEXTS_EN = [
  'Our product growth is slowing...',
  'Why do markets crash',
  'How to interpret declining retention among long-time users',
  'Why some markets inevitably end winner-take-all',
];
function PLACEHOLDER_TEXTS() {
  try { return (window.i18n && window.i18n.getLang && window.i18n.getLang() === 'en') ? PLACEHOLDER_TEXTS_EN : PLACEHOLDER_TEXTS_ZH; }
  catch (e) { return PLACEHOLDER_TEXTS_ZH; }
}

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
      this.input.setAttribute('placeholder', T("page.home.fallback_placeholder", "描述一个你观察到的现象..."));
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
    set('#he-a-domain', __pick(ex.a.domain, ex.a.domain_en));
    set('#he-a-name',   __pick(ex.a.name, ex.a.name_en));
    set('#he-a-desc',   __pick(ex.a.desc, ex.a.desc_en));
    set('#he-b-domain', __pick(ex.b.domain, ex.b.domain_en));
    set('#he-b-name',   __pick(ex.b.name, ex.b.name_en));
    set('#he-b-desc',   __pick(ex.b.desc, ex.b.desc_en));
    const cap = $('#he-caption');
    if (cap) cap.innerHTML = __pick(ex.caption, ex.caption_en) || '';
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
  // Build dot indicators (one per example) — lets users see there are more + jump to any
  const dots = $('#he-dots');
  if (dots) {
    dots.innerHTML = '';
    DEMO_EXAMPLES.forEach((_, i) => {
      const d = document.createElement('button');
      d.type = 'button';
      d.className = 'hero-evidence__dot';
      d.setAttribute('role', 'tab');
      d.setAttribute('aria-label', T('page.home.example_aria', '例子') + ' ' + (i + 1));
      d.setAttribute('aria-selected', i === 0 ? 'true' : 'false');
      if (i === 0) d.classList.add('is-active');
      d.addEventListener('click', () => {
        _heroIdx = i;
        renderHeroEvidence(i, true);
        startHeroEvidenceTimer();
      });
      dots.appendChild(d);
    });
  }

  renderHeroEvidence(_heroIdx, false);
  startHeroEvidenceTimer();

  const rotateBtn = $('#he-rotate');
  if (rotateBtn) {
    rotateBtn.addEventListener('click', () => {
      nextHeroEvidence();
      startHeroEvidenceTimer();
    });
  }

  // Click either side → pre-fill search with that phenomenon description and submit
  ['he-a-btn', 'he-b-btn'].forEach((btnId) => {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const ex = DEMO_EXAMPLES[_heroIdx];
      if (!ex) return;
      const side = btn.dataset.side === 'a' ? ex.a : ex.b;
      const q = side.desc || side.name;
      navigatePrivateSearch(q, 'example');
    });
  });

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
  const submit = form && form.querySelector('.searchbox__submit');

  if (form && input) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const status = updateHomeQueryFeedback(input, submit);
      if (!status.valid) {
        if (status.error !== 'blank_query' && typeof window.announcePrivateNavigationError === 'function') {
          window.announcePrivateNavigationError(status.error);
        }
        return;
      }
      navigatePrivateSearch(status.value, 'home');
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
    input.addEventListener('input', () => updateHomeQueryFeedback(input, submit));
    updateHomeQueryFeedback(input, submit);
  }
}

// === Suggestions ===
// Curated example queries — covers PM, engineering, strategy, data, management.
// We override the server-provided list because those are too "popular science"
// for the target user (researchers/PMs/strategists).
const EXAMPLE_CHIPS_ZH = [
  '团队从 8 人扩到 25 人后决策速度慢了一半',
  '我们产品的 D30 留存卡在 18% 上不去',
  '分布式系统加机器后吞吐反而下降',
  '为什么市场越成熟，创新反而越慢',
  '实验组数据漂亮但长期指标背离',
];
const EXAMPLE_CHIPS_EN = [
  'Team decision speed halved after growing from 8 to 25 people',
  "Our product's D30 retention is stuck at 18%",
  'Distributed system throughput drops when we add more machines',
  'Why do mature markets innovate more slowly',
  "The experiment group's metrics look great short-term but diverge long-term",
];
function EXAMPLE_CHIPS() {
  try { return (window.i18n && window.i18n.getLang && window.i18n.getLang() === 'en') ? EXAMPLE_CHIPS_EN : EXAMPLE_CHIPS_ZH; }
  catch (e) { return EXAMPLE_CHIPS_ZH; }
}

function renderSuggestions(_suggestionsFromServer) {
  const container = $('#home-suggestions');
  if (!container) return;

  container.innerHTML = `
    <div class="home__suggestions-label">${T("page.home.suggestions_label", "试试这些真实场景")}</div>
    ${EXAMPLE_CHIPS().map((s) => `
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
          navigatePrivateSearch(q, 'example');
        }, 150);
      }
    }
  });
}

// === Daily discoveries ===
// Skeleton renders 3 placeholder cards immediately so the section reserves
// space before fetchDaily() lands. Without this, the homepage footer jumps
// down by ~220px when the grid populates — a classic CLS issue.
function renderDailySkeleton() {
  const grid = $('#daily-grid');
  if (!grid || grid.children.length > 0) return;
  grid.innerHTML = Array.from({ length: 3 }).map(() => `
    <article class="disc-card disc-card--skeleton" aria-busy="true">
      <header class="disc-card__header">
        <span class="skeleton-bar skeleton-bar--w-10"></span>
        <span class="skeleton-bar skeleton-bar--w-6"></span>
      </header>
      <div class="disc-card__item">
        <span class="skeleton-bar skeleton-bar--w-8"></span>
        <span class="skeleton-bar skeleton-bar--w-14 skeleton-bar--tall"></span>
      </div>
      <div class="disc-card__divider">
        <span class="disc-card__divider-line"></span>
        <span class="disc-card__divider-symbol" aria-hidden="true">≈?</span>
        <span class="disc-card__divider-line"></span>
      </div>
      <div class="disc-card__item">
        <span class="skeleton-bar skeleton-bar--w-8"></span>
        <span class="skeleton-bar skeleton-bar--w-14 skeleton-bar--tall"></span>
      </div>
    </article>
  `).join('');
}

// SESSION-17 design P1-1: render a friendly fallback instead of leaving the
// skeleton cards stuck forever when /api/daily returns empty or fails.
function renderDailyEmpty() {
  const grid = $('#daily-grid');
  if (!grid) return;
  grid.innerHTML =
    '<p class="home__daily-empty" style="grid-column:1/-1;text-align:center;' +
    'color:var(--text-secondary,#52525b);font-size:14px;padding:32px 0;">' +
    T('page.home.daily_empty', '今日发现暂时加载不出来，先去') +
    ' <a href="/discoveries" style="color:var(--brand-accent,#2563EB);text-decoration:underline;text-underline-offset:3px;">' +
    T('page.home.daily_empty_link', '查看全部候选队列') + '</a>' +
    T('page.home.daily_empty_punctuation', '。') + '</p>';
}

function normalizeDailyCandidate(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  if (raw.schema_version !== 'discovery-candidate-v2') return null;
  if (typeof raw.discovery_id !== 'string' || !raw.discovery_id) return null;
  if (Object.prototype.hasOwnProperty.call(raw, 'similarity') ||
      Object.prototype.hasOwnProperty.call(raw, 'isomorphism_confidence')) return null;
  if (!raw.evidence || raw.evidence.evidence_level !== 'candidate') return null;
  const pair = raw.pair;
  if (!pair || !pair.a || !pair.b) return null;
  for (const side of [pair.a, pair.b]) {
    if (typeof side.id !== 'string' || !side.id || !side.name || !side.domain) return null;
  }
  return raw;
}

function dailyLocalized(value) {
  if (!value || typeof value !== 'object') return '';
  const selected = __homeLang() === 'en' ? value.en : value.zh;
  return typeof selected === 'string' && selected.trim()
    ? selected.trim()
    : (typeof value.zh === 'string' ? value.zh.trim() : '');
}

function renderDaily(discoveries) {
  const grid = $('#daily-grid');
  if (!grid) return;
  const clean = Array.isArray(discoveries) ? discoveries.map(normalizeDailyCandidate) : [];
  if (clean.length !== 3 || clean.some((item) => !item) ||
      new Set(clean.map((item) => item.discovery_id)).size !== 3) {
    renderDailyEmpty();
    return;
  }

  grid.innerHTML = clean.map((d, i) => {
    const aName = dailyLocalized(d.pair.a.name);
    const bName = dailyLocalized(d.pair.b.name);
    const aDomain = dailyLocalized(d.pair.a.domain);
    const bDomain = dailyLocalized(d.pair.b.domain);
    const href = `/discoveries?candidate=${encodeURIComponent(d.discovery_id)}`;
    const aria = T(
      'page.home.daily_candidate_aria',
      '待验证候选联系：{a} 与 {b}。查看证据缺口。'
    ).replace('{a}', aName).replace('{b}', bName);
    return `
      <a class="disc-card" href="${escapeHtml(href)}" aria-label="${escapeHtml(aria)}" style="animation: fadeInUp 600ms var(--ease-out-expo) ${1000 + i * 100}ms both">
        <header class="disc-card__header">
          <span class="disc-card__structure">${T('page.home.daily_candidate', '待验证候选')}</span>
          <span class="disc-card__status">${T('page.home.daily_unreviewed', '来源未独立复核')}</span>
        </header>
        <div class="disc-card__item">
          <div class="disc-card__domain">${escapeHtml(aDomain)}</div>
          <div class="disc-card__name">${escapeHtml(aName)}</div>
        </div>
        <div class="disc-card__divider">
          <span class="disc-card__divider-line"></span>
          <span class="disc-card__divider-symbol" aria-hidden="true">≈?</span>
          <span class="disc-card__divider-line"></span>
        </div>
        <div class="disc-card__item">
          <div class="disc-card__domain">${escapeHtml(bDomain)}</div>
          <div class="disc-card__name">${escapeHtml(bName)}</div>
        </div>
        <p class="disc-card__boundary">${T('page.home.daily_boundary', '≈? 表示待检验的结构联系；它不能证明两边机制相同。')}</p>
        <span class="disc-card__open">${T('page.home.daily_open', '查看证据缺口')} <span aria-hidden="true">→</span></span>
      </a>
    `;
  }).join('');
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
    if (q) navigatePrivateSearch(q, 'history');
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

  listEl.innerHTML = favs.map((f, index) => {
    const targetId = f && /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(f.b_id || '') ? f.b_id : '';
    const href = targetId ? '/analyze?id=' + encodeURIComponent(targetId) : '/reports#research-favorites';
    // Title fallback: a_name ≅ b_name (pair mode) → query → "(未命名查询)"
    let title = T('page.home.no_title', '(未命名查询)');
    if (f && f.a_name && f.b_name) {
      title = `${f.a_name} ≅ ${f.b_name}`;
    } else if (f && f.query) {
      title = f.query;
    } else if (f && f.b_name) {
      title = f.b_name;
    }
    const when = f && f.timestamp ? new Date(f.timestamp).toLocaleDateString(__homeLang() === 'en' ? 'en-US' : 'zh-CN') : '';
    return `
      <a href="${escapeHtml(href)}" class="home__fav-card" data-local-favorite="${index}">
        <span class="home__fav-card__star">★</span>
        <div class="home__fav-card__body">
          <div class="home__fav-card__title">${escapeHtml(title)}</div>
          ${when ? `<div class="home__fav-card__time">${escapeHtml(when)}</div>` : ''}
        </div>
        <svg class="home__fav-card__arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
      </a>
    `;
  }).join('');

  listEl.onclick = (event) => {
    const link = event.target.closest('[data-local-favorite]');
    if (!link) return;
    const favorite = favs[Number(link.dataset.localFavorite)];
    if (!favorite || !favorite.query || !favorite.b_id || typeof window.buildAnalyzeUrl !== 'function') return;
    event.preventDefault();
    const destination = window.buildAnalyzeUrl({
      id: favorite.b_id,
      a_id: favorite.a_id,
      q: favorite.query,
      fingerprint: favorite.fingerprint,
      origin_discovery_id: favorite.origin_discovery_id,
      origin_contract_version: favorite.origin_contract_version,
    });
    try {
      if (!new URL(destination, window.location.origin).searchParams.get('handoff')) {
        if (window.showToast) window.showToast('未能建立安全的本地交接；问题没有写入链接。请允许当前标签页使用会话存储后重试。');
        return;
      }
    } catch (_) { return; }
    window.location.assign(destination);
  };
}

async function loadHomeData() {
  // Settle each independently so one failing endpoint can't leave the other
  // section's skeleton stuck (SESSION-17 design P1-1).
  const [suggestRes, dailyRes] = await Promise.allSettled([
    StructuralAPI.getSuggestions(),
    StructuralAPI.getDaily(),
  ]);
  if (suggestRes.status === 'fulfilled') {
    renderSuggestions(suggestRes.value.suggestions || []);
  } else {
    console.error('[home] suggestions load failed');
  }
  if (dailyRes.status === 'fulfilled') {
    renderDaily(dailyRes.value.discoveries || []);
  } else {
    console.error('[home] daily discoveries load failed');
    renderDailyEmpty();
  }
}

function initUsecaseSamples() {
  // Each clickable "试一下" sample submits a search with its data-usecase-q value
  document.querySelectorAll('.usecase__sample--clickable').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const q = btn.getAttribute('data-usecase-q');
      if (q) {
        navigatePrivateSearch(q, 'example');
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  initSearch();
  initHeroEvidence();
  initUsecaseSamples();
  renderHistory();
  renderFavorites();
  // Reserve daily-discoveries grid space immediately so the section below
  // doesn't jump down when fetchDaily() lands (~300ms later).
  renderDailySkeleton();
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
    const tw = new Typewriter(input, PLACEHOLDER_TEXTS());
    tw.start();
  }
});

// Re-render hero evidence + daily + favorites when language toggles
try {
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(function () {
      try { renderHeroEvidence(_heroIdx, false); } catch (e) {}
      try { renderHistory(); renderFavorites(); loadHomeData(); } catch (e) {}
    });
  }
} catch (e) {}
