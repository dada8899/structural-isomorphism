/** Paint the validated private question before the full Search runtime loads. */
(function bootstrapPrivateSearch(root) {
  'use strict';

  const documentRef = root && root.document;
  if (!documentRef) return;
  if (root.__structuralSearchBoot) return;

  function element(tag, className, text) {
    const node = documentRef.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function copyFor(lang) {
    return lang === 'en' ? {
      label: 'Your question',
      rewriteLabel: 'Retrieval wording: ',
      rewriteOriginal: 'starting with your original question',
      rewriteUsed: 'Rewritten as a research question: ',
      phase: 'Understanding your question',
      elapsed: 'Waited 0s',
      status: 'Retrieving candidates · shown after validation',
    } : {
      label: '你的问题',
      rewriteLabel: '检索表达：',
      rewriteOriginal: '先按原问题检索',
      rewriteUsed: '已改写为研究问题：',
      phase: '正在理解你的问题',
      elapsed: '已等待 0s',
      status: '候选检索中 · 结果通过校验后显示',
    };
  }

  function renderQuestion(context) {
    const host = documentRef.getElementById('search-summary');
    if (!host) return;
    const copy = copyFor(context.lang);
    host.classList.add('search-summary--active');
    host.dataset.searchBootstrap = 'ready';
    host.replaceChildren();

    const question = element('div', 'search-question');
    question.appendChild(element('div', 'search-question__label', copy.label));
    question.lastChild.id = 'search-question-label';
    question.appendChild(element('div', 'search-question__text', context.query));
    question.lastChild.id = 'search-question-text';

    const rewrite = element('div', 'search-question__rewrite');
    rewrite.id = 'search-question-rewrite';
    const rewritten = context.rewritten_query && context.rewritten_query !== context.query;
    rewrite.appendChild(element('span', '', rewritten ? copy.rewriteUsed : copy.rewriteLabel));
    rewrite.lastChild.id = 'search-question-rewrite-label';
    rewrite.appendChild(element('em', '', rewritten ? context.rewritten_query : copy.rewriteOriginal));
    rewrite.lastChild.id = 'search-question-rewrite-text';
    question.appendChild(rewrite);
    host.appendChild(question);

    const synth = element('div', 'search-synth search-synth--loading');
    synth.id = 'search-synth';
    const loading = element('div', 'search-synth__loading');
    loading.setAttribute('role', 'status');
    const dots = element('span', 'search-synth__dots');
    dots.setAttribute('aria-hidden', 'true');
    dots.append(element('span'), element('span'), element('span'));
    loading.appendChild(dots);
    loading.appendChild(element('span', 'search-synth__phase-text', copy.phase));
    loading.lastChild.id = 'search-synth-phase';
    loading.appendChild(element('span', 'elapsed-timer', copy.elapsed));
    loading.lastChild.id = 'search-synth-timer';
    loading.appendChild(element('span', 'search-synth__typical', copy.status));
    loading.lastChild.id = 'search-synth-status';
    synth.appendChild(loading);
    host.appendChild(synth);
  }

  function resolveContext() {
    if (typeof root.resolvePrivateNavigationContext !== 'function') {
      return { attempted: false, context: null };
    }
    try {
      const url = new URL(root.location.href);
      const context = root.resolvePrivateNavigationContext({
        kind: 'search',
        key: url.searchParams.get('context') || '',
        lang: url.searchParams.get('lang') === 'en' ? 'en' : 'zh',
        force: url.searchParams.get('force') === '1',
      });
      return { attempted: true, context };
    } catch (_) {
      return { attempted: true, context: null };
    }
  }

  const result = resolveContext();
  root.__structuralSearchBoot = Object.freeze(result);
  if (result.context) renderQuestion(result.context);
}(typeof window === 'undefined' ? null : window));
