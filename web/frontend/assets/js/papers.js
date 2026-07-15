(function () {
  'use strict';

  const Catalog = window.StructuralPapersCatalog;
  const GROUP_IDS = new Set(['unified', 'arxiv-drafts', 'phase-papers', 'tutorials']);
  let activeFilter = 'all';
  let validatedManifest = null;

  function language() {
    return Catalog.locale();
  }

  function localize(record, field) {
    return Catalog.localized(record, field, language());
  }

  function escape(value) {
    return Catalog.escapeHtml(value);
  }

  function formatNumber(value) {
    return value == null ? '—' : Number(value).toLocaleString('en-US');
  }

  function syncStaticAria() {
    const english = language() === 'en';
    const labels = [
      ['#papers-stats', english ? 'Historical material composition' : '历史材料构成'],
      ['#papers-filter', english ? 'Historical material type filters' : '历史材料类型筛选'],
      ['.papers-footer-note', english ? 'Historical material boundary' : '历史材料边界'],
    ];
    labels.forEach(([selector, label]) => {
      const element = document.querySelector(selector);
      if (element) element.setAttribute('aria-label', label);
    });
  }

  function alignExplicitUrlLanguage() {
    if (!window.i18n || typeof window.i18n.setLang !== 'function') return;
    try {
      const requested = new URL(window.location.href).searchParams.get('lang');
      if (requested === 'en' || requested === 'zh') window.i18n.setLang(requested);
    } catch (_error) {
      // The shared i18n bootstrap remains authoritative when URL parsing is unavailable.
    }
  }

  function observedSummary(paper, contract) {
    if (!paper.alpha) return localize(contract, 'observed_fallback');
    return language() === 'en'
      ? `The historical record reports “${paper.alpha}”. This value is not bound to the current evidence ledger.`
      : `历史记录报告“${paper.alpha}”；该数值尚未与当前证据账本绑定。`;
  }

  function detailRow(labelZh, labelEn, value) {
    const label = language() === 'en' ? labelEn : labelZh;
    return `<div><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`;
  }

  function renderBoundary(paper, contract) {
    const missing = language() === 'en'
      ? 'Not recorded in this manifest'
      : '本 manifest 未记录';
    const sample = paper.n_tail
      ? (language() === 'en'
        ? `Historical manifest field: n=${formatNumber(paper.n_tail)}; inspect the record for its definition.`
        : `历史 manifest 字段：n=${formatNumber(paper.n_tail)}；需进入记录核对口径。`)
      : missing;
    return `
      <section class="paper-result" aria-label="${escape(language() === 'en' ? 'Evidence boundary' : '证据边界')}">
        <div class="paper-result__decision">
          <div><span>${escape(language() === 'en' ? 'Recorded observation' : '记录了什么')}</span><p>${escape(observedSummary(paper, contract))}</p></div>
          <div><span>${escape(language() === 'en' ? 'What it does not establish' : '不能推出什么')}</span><p>${escape(localize(contract, 'boundary'))}</p></div>
          <div><span>${escape(language() === 'en' ? 'Next validation step' : '下一步检验')}</span><p>${escape(localize(contract, 'next_test'))}</p></div>
        </div>
        <details class="paper-result__details" data-paper-slug="${escape(paper.slug)}">
          <summary>${escape(language() === 'en' ? 'Inspect evidence fields' : '核对证据字段')}</summary>
          <dl>
            ${detailRow('证据状态', 'Evidence status', language() === 'en' ? 'Historical internal record · not promoted' : '历史内部记录 · 未升级')}
            ${detailRow('来源与许可', 'Source and license', missing)}
            ${detailRow('样本字段', 'Sample field', sample)}
            ${detailRow('方法与替代模型', 'Method and alternatives', language() === 'en' ? 'Inspect the record; not normalized here' : '进入记录核对；索引未标准化')}
            ${detailRow('预注册', 'Preregistration', missing)}
            ${detailRow('证据账本', 'Evidence ledger', language() === 'en' ? 'Not bound' : '未绑定')}
            ${detailRow('复核状态', 'Review status', language() === 'en' ? 'Internal only; no external review recorded' : '仅内部；未记录外部复核')}
          </dl>
        </details>
      </section>`;
  }

  function renderCard(paper, contract) {
    const status = Catalog.STATUS_LABELS[paper.status][language()];
    const paperClass = paper.class || '';
    return `
      <article class="paper-card${paper.feature ? ' paper-card--feature' : ''}">
        <div class="paper-card__topline">
          <span class="paper-card__status paper-card__status--${escape(paper.status)}">${escape(status)}</span>
          <time datetime="${escape(paper.date)}">${escape(paper.date)}</time>
        </div>
        <h3><a class="paper-card__title" href="${escape(Catalog.paperUrl(paper.slug))}">${escape(localize(paper, 'title'))}</a></h3>
        <div class="paper-card__meta">
          ${paperClass ? `<span class="paper-card__meta-class">${escape(paperClass)}</span>` : ''}
          <span>${escape(formatNumber(paper.words))} ${escape(language() === 'en' ? 'words' : '字')} · ${escape(paper.minutes)} ${escape(language() === 'en' ? 'min read' : '分钟阅读')}</span>
        </div>
        ${renderBoundary(paper, contract)}
        <a class="paper-card__open" href="${escape(Catalog.paperUrl(paper.slug))}">${escape(language() === 'en' ? 'Open historical record' : '打开历史记录')}<span aria-hidden="true">→</span></a>
      </article>`;
  }

  function openEvidenceSlugs() {
    return new Set(Array.from(document.querySelectorAll('.paper-result__details[open]'))
      .map((node) => node.dataset.paperSlug).filter(Boolean));
  }

  function render(validated) {
    const openSlugs = openEvidenceSlugs();
    const container = document.getElementById('papers-content');
    if (!container) throw new Error('Papers content root is missing');
    container.innerHTML = validated.manifest.groups.map((group) => `
      <section class="papers-group" data-group-id="${escape(group.id)}">
        <header class="papers-group__header">
          <h2 class="papers-group__title">${escape(localize(group, 'title'))}</h2>
          <p class="papers-group__desc">${escape(localize(group, 'desc'))}</p>
        </header>
        <div class="papers-list">${group.papers.map((paper) => renderCard(paper, validated.contract)).join('')}</div>
      </section>`).join('');
    openSlugs.forEach((slug) => {
      const element = document.querySelector(`.paper-result__details[data-paper-slug="${CSS.escape(slug)}"]`);
      if (element) element.open = true;
    });
    applyFilter(activeFilter, false);
    syncStaticAria();
    container.setAttribute('aria-busy', 'false');
  }

  function applyFilter(requestedFilter, focusButton) {
    activeFilter = requestedFilter === 'all' || GROUP_IDS.has(requestedFilter)
      ? requestedFilter
      : 'all';
    document.querySelectorAll('.papers-group').forEach((group) => {
      group.hidden = activeFilter !== 'all' && group.dataset.groupId !== activeFilter;
    });
    document.querySelectorAll('.papers-filter__btn').forEach((button) => {
      const selected = button.dataset.filter === activeFilter;
      button.classList.toggle('papers-filter__btn--active', selected);
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
      button.tabIndex = selected ? 0 : -1;
      if (selected && focusButton) button.focus();
    });
    const status = document.getElementById('papers-filter-status');
    if (status && validatedManifest) {
      const visible = activeFilter === 'all'
        ? validatedManifest.records.length
        : validatedManifest.manifest.groups.find((group) => group.id === activeFilter).papers.length;
      status.textContent = language() === 'en'
        ? `${visible} historical items shown`
        : `当前显示 ${visible} 项历史材料`;
    }
  }

  function handleFilterKeydown(event) {
    const buttons = Array.from(document.querySelectorAll('.papers-filter__btn'));
    const current = buttons.indexOf(event.target.closest('.papers-filter__btn'));
    if (current < 0) return;
    let next = null;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % buttons.length;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (current - 1 + buttons.length) % buttons.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = buttons.length - 1;
    if (next == null) return;
    event.preventDefault();
    applyFilter(buttons[next].dataset.filter, true);
  }

  function showError(error) {
    const container = document.getElementById('papers-content');
    if (!container) return;
    const detail = error instanceof Error ? error.message : String(error);
    container.setAttribute('aria-busy', 'false');
    container.innerHTML = `
      <section class="papers-error" role="alert">
        <h2>${escape(language() === 'en' ? 'Historical records unavailable' : '历史材料暂不可用')}</h2>
        <p>${escape(language() === 'en' ? 'The catalog failed a safety or consistency check. Please retry later.' : '目录未通过安全或一致性检查，请稍后重试。')}</p>
        <code>${escape(detail)}</code>
      </section>`;
  }

  const filter = document.getElementById('papers-filter');
  filter?.addEventListener('click', (event) => {
    const button = event.target.closest('.papers-filter__btn');
    if (button) applyFilter(button.dataset.filter, false);
  });
  filter?.addEventListener('keydown', handleFilterKeydown);
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(() => {
      syncStaticAria();
      if (validatedManifest) render(validatedManifest);
    });
  }
  alignExplicitUrlLanguage();

  if (!Catalog) {
    showError(new Error('Papers catalog module is unavailable'));
    return;
  }
  Catalog.loadManifest().then((validated) => {
    validatedManifest = validated;
    render(validated);
  }).catch(showError);
})();
