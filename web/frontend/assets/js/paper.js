(function () {
  'use strict';

  const Catalog = window.StructuralPapersCatalog;
  const Markdown = window.StructuralSafeMarkdown;
  const OVERFLOW_SELECTOR = 'pre, table, .katex-display, .katex';
  let validatedManifest = null;
  let currentPaper = null;
  let overflowFrame = 0;

  function locale() {
    return Catalog && typeof Catalog.locale === 'function' ? Catalog.locale() : 'zh';
  }

  function localized(record, field) {
    return Catalog.localized(record, field, locale());
  }

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = String(value == null ? '' : value);
  }

  function syncStaticAria() {
    const english = locale() === 'en';
    const labels = [
      ['.paper-breadcrumb', english ? 'Breadcrumb' : '面包屑'],
      ['.paper-primary-actions', english ? 'Historical material actions' : '历史材料操作'],
      ['.paper-skeleton', english ? 'Loading historical Markdown' : '正在加载历史 Markdown'],
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

  function overflowLabel(element) {
    const english = locale() === 'en';
    if (element.matches('pre')) {
      return english ? 'Horizontally scrollable code block' : '可横向滚动的代码块';
    }
    if (element.matches('table')) {
      return english ? 'Horizontally scrollable data table' : '可横向滚动的数据表格';
    }
    return english ? 'Horizontally scrollable equation' : '可横向滚动的公式';
  }

  function clearManagedOverflow(element) {
    if (element.dataset.paperManagedTabindex === 'true') {
      element.removeAttribute('tabindex');
      delete element.dataset.paperManagedTabindex;
    }
    if (element.dataset.paperManagedLabel === 'true') {
      element.removeAttribute('aria-label');
      delete element.dataset.paperManagedLabel;
    }
    delete element.dataset.paperScrollable;
  }

  function syncOverflowFocusability() {
    const details = document.getElementById('paper-legacy-record');
    const article = document.getElementById('paper-article');
    if (!article) return;
    article.querySelectorAll(OVERFLOW_SELECTOR).forEach((element) => {
      const style = window.getComputedStyle(element);
      const canScroll = style.overflowX === 'auto' || style.overflowX === 'scroll';
      const actuallyOverflows = Boolean(
        details && details.open && element.clientWidth > 0 &&
        element.scrollWidth > element.clientWidth + 1 && canScroll
      );
      if (!actuallyOverflows) {
        clearManagedOverflow(element);
        return;
      }
      element.dataset.paperScrollable = 'true';
      if (element.getAttribute('tabindex') !== '0') {
        element.setAttribute('tabindex', '0');
        element.dataset.paperManagedTabindex = 'true';
      }
      if (!element.hasAttribute('aria-label') || element.dataset.paperManagedLabel === 'true') {
        element.setAttribute('aria-label', overflowLabel(element));
        element.dataset.paperManagedLabel = 'true';
      }
    });
  }

  function scheduleOverflowSync() {
    window.cancelAnimationFrame(overflowFrame);
    overflowFrame = window.requestAnimationFrame(syncOverflowFocusability);
  }

  function observation(paper, contract) {
    if (!paper.alpha) return localized(contract, 'observed_fallback');
    return locale() === 'en'
      ? `The historical record reports “${paper.alpha}”. This value is not bound to the current evidence ledger.`
      : `历史记录报告“${paper.alpha}”；该数值尚未与当前证据账本绑定。`;
  }

  function renderBoundary(paper, contract) {
    const title = localized(paper, 'title');
    const label = Catalog.STATUS_LABELS[paper.status][locale()];
    setText('paper-boundary-label', label);
    setText('paper-heading', title);
    setText('paper-breadcrumb-current', title);
    setText('paper-observed', observation(paper, contract));
    setText('paper-not-established', localized(contract, 'boundary'));
    setText('paper-next-test', localized(contract, 'next_test'));
    setText('paper-date', paper.date);
    setText('paper-class', paper.class || (locale() === 'en' ? 'Not classified' : '未分类'));
    setText(
      'paper-review-status',
      locale() === 'en'
        ? 'Historical internal material · not ledger-bound · no external review recorded'
        : '历史内部材料 · 未绑定当前账本 · 未记录外部复核',
    );
    setText(
      'paper-legacy-summary',
      locale() === 'en'
        ? 'Inspect the unnormalized historical Markdown record'
        : '查看未经当前证据标准化的历史 Markdown 原文',
    );
    setText('paper-source-label', locale() === 'en' ? 'Source code and data' : '源码与数据');
    setText('paper-download-label', locale() === 'en' ? 'Download historical Markdown' : '下载历史 Markdown');
    syncStaticAria();
    scheduleOverflowSync();
    document.title = `${title} — Structural`;
  }

  function configureLinks(paper) {
    const source = document.getElementById('paper-source');
    const download = document.getElementById('paper-download-md');
    if (source) source.href = Catalog.validateSourceUrl(paper.source_url);
    if (download) {
      download.href = Catalog.markdownUrl(paper.slug);
      download.setAttribute('download', `${paper.slug}.md`);
    }
  }

  function renderMath(target) {
    if (typeof window.renderMathInElement !== 'function') return;
    try {
      window.renderMathInElement(target, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '\\[', right: '\\]', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\(', right: '\\)', display: false },
        ],
        throwOnError: false,
        strict: 'warn',
        trust: false,
      });
      target.querySelectorAll('.katex').forEach((formula) => {
        const annotation = formula.querySelector('annotation[encoding="application/x-tex"]');
        const mathml = formula.querySelector('.katex-mathml');
        if (annotation && annotation.textContent) {
          formula.setAttribute('role', 'math');
          formula.setAttribute('aria-label', annotation.textContent);
        }
        if (mathml) mathml.setAttribute('aria-hidden', 'true');
      });
      scheduleOverflowSync();
    } catch (error) {
      console.warn('[paper] math rendering failed');
    }
  }

  async function loadMarkdown(paper) {
    const article = document.getElementById('paper-article');
    if (!article) throw new Error('Paper article root is missing');
    const response = await fetch(Catalog.markdownUrl(paper.slug), {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'text/markdown,text/plain;q=0.9' },
    });
    if (!response.ok) throw new Error(`Markdown request failed (${response.status})`);
    const declaredLength = Number(response.headers.get('content-length') || 0);
    if (declaredLength > Markdown.MAX_MARKDOWN_BYTES) {
      throw new Error('Markdown document exceeds the public rendering limit');
    }
    const markdown = await response.text();
    article.innerHTML = Markdown.render(markdown, { headingOffset: 1 });
    article.setAttribute('aria-busy', 'false');
    renderMath(article);
    scheduleOverflowSync();
  }

  function showFatalError(error) {
    const main = document.getElementById('paper-main');
    const detail = error instanceof Error ? error.message : String(error);
    if (main) {
      main.innerHTML = '';
      const section = document.createElement('section');
      section.className = 'paper-fatal-error';
      section.setAttribute('role', 'alert');
      const heading = document.createElement('h1');
      heading.textContent = locale() === 'en' ? 'Historical record not available' : '历史材料不可用';
      const message = document.createElement('p');
      message.textContent = locale() === 'en'
        ? 'This URL is not an exact member of the public catalog, or its catalog failed validation.'
        : '该 URL 不是公开目录中的精确条目，或目录未通过校验。';
      const code = document.createElement('code');
      code.textContent = detail;
      const back = document.createElement('a');
      back.href = '/papers';
      back.textContent = locale() === 'en' ? 'Back to historical materials' : '返回历史材料目录';
      section.append(heading, message, code, back);
      main.appendChild(section);
    }
  }

  function showMarkdownError(error) {
    const article = document.getElementById('paper-article');
    if (!article) return;
    article.setAttribute('aria-busy', 'false');
    article.textContent = '';
    const message = document.createElement('p');
    message.className = 'paper-load-error';
    message.setAttribute('role', 'alert');
    message.textContent = locale() === 'en'
      ? `Historical Markdown could not be loaded: ${error.message}`
      : `历史 Markdown 加载失败：${error.message}`;
    article.appendChild(message);
  }

  async function initialize() {
    if (!Catalog || !Markdown) throw new Error('Local paper safety modules are unavailable');
    const slug = Catalog.slugFromLocation(window.location);
    validatedManifest = await Catalog.loadManifest();
    currentPaper = validatedManifest.bySlug[slug];
    if (!currentPaper) throw new Error(`Unknown paper slug: ${slug}`);
    renderBoundary(currentPaper, validatedManifest.contract);
    configureLinks(currentPaper);
    await loadMarkdown(currentPaper).catch(showMarkdownError);
  }

  document.getElementById('paper-legacy-record')?.addEventListener('toggle', scheduleOverflowSync);
  window.addEventListener('resize', scheduleOverflowSync, { passive: true });
  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(() => {
      syncStaticAria();
      if (currentPaper && validatedManifest) {
        renderBoundary(currentPaper, validatedManifest.contract);
      }
    });
  }
  alignExplicitUrlLanguage();
  initialize().catch(showFatalError);
})();
