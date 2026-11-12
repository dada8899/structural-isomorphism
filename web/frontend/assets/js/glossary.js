/**
 * Structural — GlossaryTooltip (vanilla JS)
 *
 * Auto-wraps the FIRST occurrence of each known jargon term inside the
 * page's main content area with a hoverable tooltip that explains the term
 * in plain language.
 *
 * Why FIRST occurrence: subsequent uses are visually noisy. The reader
 * just needs to learn it once on the page.
 *
 * Why auto-wrap (vs. manual <span> in HTML): every page changes copy
 * frequently. Centralizing the term list here means one edit, not 13.
 *
 * Mobile: hover doesn't exist. Tap the underlined term to toggle the
 * tooltip. Tap outside or scroll to dismiss.
 *
 * Researcher pages (paper.html, papers.html, taxonomy-v2.html) opt OUT
 * by virtue of not loading this script — those readers already know
 * the jargon and the tooltip would be visual debt for them.
 */
(function () {
  'use strict';

  // The 7 terms that genuinely appear in user-facing copy as of session #5.
  // Each: short plain-language gloss (~30-50 chars). Keep terse — long
  // tooltips defeat the "60-second understanding" goal.
  const GLOSSARY = {
    '临界翻转': '系统从一种稳态突然跳到另一种稳态。例：湖泊从清澈到富营养化。',
    '临界级联': '一个小触发引起链式反应、雪崩式蔓延。例：电网级联停电。',
    '临界放缓': '在一些模型中，系统接近阈值时受扰后的恢复会变慢。它是待核查的预警特征，单独出现不能证明即将翻转。',
    '临界边缘': '描述系统接近某个假定阈值的候选状态。临界点是否真实存在，仍需数据、对照和替代模型比较。',
    '普适类': '物理学中，在明确假设下可能共享大尺度临界行为的一组系统。这里的同名标签只是候选分类，不代表跨领域机制一致。',
    '标度律': '描述一个量如何随尺度变化的关系，常写成 y ~ x^α。相近指数仍需误差分析和替代分布比较，不能单独确认普适类。',
    '临界假说': '一个待检验假设：现象可能与接近临界点有关。需要预先写清指标、对照、替代解释和失败条件。',
    // W3-B (session #7): Glossary v2 expansion — five new terms that
    // recur across discoveries / classes / paper copy.
    '相变': '系统的宏观状态在参数变化时发生质变，例如水的液气变化。市场、银行和神经系统中的用法通常是候选类比，不自动构成物理相变。',
    '标度形式': '用公式描述不同尺度之间的关系，例如 P(s) ~ s^(-α)。相似公式只提供比较线索；大小事件是否有共同生成过程，仍需数据检验。',
    '涌现': '整体出现而单个组件不具备的性质。例如许多车辆相互作用后形成拥堵；具体机制仍需按系统解释。',
    '反馈环': '系统输出反过来影响输入。正反馈可能放大变化，负反馈可能抑制变化；相似反馈图只是比较线索，不证明机制相同。',
    '阈值效应': '当某个变量低于阈值时系统几乎不变，超过阈值后剧变。森林大火的燃料密度、神经元的电位、产品的传播率，都有阈值效应。',
    // SESSION-17 copy AB-01: explain the high-frequency physics terms that
    // the about / classes / paper copy uses without a plain-language gloss.
    '幂律分布': '一种重尾候选分布：多数观测较小，少数很大。是否真是幂律，需要和对数正态、指数等替代模型比较。',
    '幂律': '形如 y ~ x^(-α) 的数学关系。有限样本看起来像直线并不够，仍需拟合区间、误差和替代模型检验。',
    '自组织临界': '一种模型假说：系统可能在持续驱动下靠近临界状态，而不需外部精确调参。真实系统是否符合它需要数据和对照。',
    '结构同构': '在明确假设下，把两个现象的变量关系或方程骨架对齐来比较。它不代表两个现象是同一回事，也不代表机制一致。',
    '级联': '一个小触发引起链式反应、像多米诺骨牌一样蔓延。电网停电、银行连环挤兑都是级联。',
  };

  // Sorted longest-first so 临界翻转 matches before 临界. Otherwise the
  // greedy short match would consume the prefix and we'd lose the long form.
  const TERMS = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length);

  // Build a single regex that matches any term. Term keys are CJK so word
  // boundaries don't apply; the longest-first sort prevents ambiguity.
  const TERM_RE = new RegExp('(' + TERMS.map(escapeRegExp).join('|') + ')');

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // Tags whose text should NOT be wrapped — code-like or already-styled.
  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'CODE', 'PRE', 'A', 'BUTTON',
    'INPUT', 'TEXTAREA', 'NOSCRIPT', 'TITLE', 'KBD', 'ABBR']);

  // Class on already-wrapped spans, so we never double-wrap.
  const WRAPPED_CLASS = 'glossary-term';
  const TOOLTIP_ID = 'glossary-tooltip-active';

  // Track which terms have been wrapped already on this page (FIRST-occurrence rule).
  const seenTerms = new Set();
  let activeTooltip = null;
  let activeAnchor = null;

  function shouldSkipNode(node) {
    if (!node || !node.parentElement) return true;
    let el = node.parentElement;
    while (el) {
      if (SKIP_TAGS.has(el.tagName)) return true;
      if (el.classList && el.classList.contains(WRAPPED_CLASS)) return true;
      // Skip Plausible / analytics injected nodes
      if (el.dataset && el.dataset.skipGlossary) return true;
      el = el.parentElement;
    }
    return false;
  }

  function wrapTextNode(node) {
    const text = node.nodeValue;
    if (!text || !TERM_RE.test(text)) return;

    // Walk through all matches in order; only wrap the first instance per term.
    const fragments = [];
    let lastIdx = 0;
    let cursor = 0;
    const pattern = new RegExp(TERM_RE.source, 'g');
    let m;
    let mutated = false;
    while ((m = pattern.exec(text)) !== null) {
      const term = m[0];
      const start = m.index;
      if (seenTerms.has(term)) {
        // Skip this match — already wrapped elsewhere on the page
        continue;
      }
      // Push preceding text
      if (start > lastIdx) {
        fragments.push(document.createTextNode(text.slice(lastIdx, start)));
      }
      // Wrap term
      const span = document.createElement('span');
      span.className = WRAPPED_CLASS;
      span.tabIndex = 0;
      span.setAttribute('role', 'button');
      span.setAttribute('aria-label', term + '：' + GLOSSARY[term]);
      span.dataset.term = term;
      span.textContent = term;
      fragments.push(span);
      seenTerms.add(term);
      lastIdx = start + term.length;
      mutated = true;
    }
    if (!mutated) return;
    // Trailing text
    if (lastIdx < text.length) {
      fragments.push(document.createTextNode(text.slice(lastIdx)));
    }
    // Replace the original text node with the new fragments
    const parent = node.parentNode;
    if (!parent) return;
    fragments.forEach(f => parent.insertBefore(f, node));
    parent.removeChild(node);
  }

  function scanContainer(root) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (shouldSkipNode(node)) return NodeFilter.FILTER_REJECT;
        if (!TERM_RE.test(node.nodeValue || '')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    // Collect first so we don't mutate-while-iterating
    const targets = [];
    let n;
    while ((n = walker.nextNode())) targets.push(n);
    targets.forEach(wrapTextNode);
  }

  // === Tooltip ===
  function showTooltip(anchor) {
    hideTooltip();
    const term = anchor.dataset.term;
    const gloss = GLOSSARY[term];
    if (!gloss) return;

    const tip = document.createElement('div');
    tip.className = 'glossary-tip';
    tip.id = TOOLTIP_ID;
    tip.setAttribute('role', 'tooltip');
    tip.innerHTML =
      '<div class="glossary-tip__term">' + escapeHtml(term) + '</div>' +
      '<div class="glossary-tip__gloss">' + escapeHtml(gloss) + '</div>';
    document.body.appendChild(tip);
    positionTooltip(tip, anchor);
    activeTooltip = tip;
    activeAnchor = anchor;
    // Trigger CSS fade-in on next frame
    requestAnimationFrame(() => tip.classList.add('glossary-tip--visible'));

    // W3-B: Plausible — record which glossary term opened. Guarded so a
    // missing plausible.js (privacy / region block) does not throw.
    try {
      if (typeof window.plausible === 'function') {
        window.plausible('glossary_tooltip_opened', { props: { term: term } });
      }
    } catch (e) {}
  }

  function hideTooltip() {
    if (activeTooltip) {
      activeTooltip.remove();
      activeTooltip = null;
      activeAnchor = null;
    }
  }

  function positionTooltip(tip, anchor) {
    const r = anchor.getBoundingClientRect();
    const tipW = Math.min(320, window.innerWidth - 24);
    tip.style.maxWidth = tipW + 'px';
    // Initially position offscreen to measure
    tip.style.left = '0';
    tip.style.top = '0';
    const tipR = tip.getBoundingClientRect();

    // Horizontal: try to center on the term, clamp to viewport
    let left = r.left + r.width / 2 - tipR.width / 2 + window.scrollX;
    left = Math.max(12 + window.scrollX, Math.min(left, window.scrollX + window.innerWidth - tipR.width - 12));
    // Vertical: prefer above. If would overflow viewport top, place below.
    const spaceAbove = r.top;
    const spaceBelow = window.innerHeight - r.bottom;
    let top;
    let placement;
    if (spaceAbove > tipR.height + 12 || spaceAbove > spaceBelow) {
      top = r.top + window.scrollY - tipR.height - 8;
      placement = 'top';
    } else {
      top = r.bottom + window.scrollY + 8;
      placement = 'bottom';
    }
    tip.style.left = Math.round(left) + 'px';
    tip.style.top = Math.round(top) + 'px';
    tip.dataset.placement = placement;
    // Compute arrow x relative to the tooltip
    const anchorCenterX = r.left + r.width / 2 + window.scrollX;
    const arrowX = Math.max(12, Math.min(tipR.width - 12, anchorCenterX - left));
    tip.style.setProperty('--arrow-x', arrowX + 'px');
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // === Event wiring ===
  function onPointerEnter(e) {
    const t = e.target;
    if (t && t.classList && t.classList.contains(WRAPPED_CLASS)) {
      showTooltip(t);
    }
  }

  function onPointerLeave(e) {
    // Hide only if leaving to something that isn't the tooltip itself
    const to = e.relatedTarget;
    if (to && (to === activeTooltip || (activeTooltip && activeTooltip.contains(to)))) return;
    hideTooltip();
  }

  function onClick(e) {
    const t = e.target;
    if (t && t.closest && t.closest('.' + WRAPPED_CLASS)) {
      // Toggle: if same anchor is active, hide; else show
      const anchor = t.closest('.' + WRAPPED_CLASS);
      if (activeAnchor === anchor) {
        hideTooltip();
      } else {
        showTooltip(anchor);
      }
      e.preventDefault();
      return;
    }
    // Click outside any term → hide
    if (activeTooltip && !activeTooltip.contains(t)) {
      hideTooltip();
    }
  }

  function onKey(e) {
    if (e.key === 'Escape' && activeTooltip) {
      hideTooltip();
      if (activeAnchor) activeAnchor.focus();
    }
    // Enter / Space on focused term opens tooltip
    if ((e.key === 'Enter' || e.key === ' ') && document.activeElement &&
        document.activeElement.classList && document.activeElement.classList.contains(WRAPPED_CLASS)) {
      e.preventDefault();
      const a = document.activeElement;
      if (activeAnchor === a) hideTooltip();
      else showTooltip(a);
    }
  }

  function onScroll() {
    if (activeTooltip && activeAnchor) {
      positionTooltip(activeTooltip, activeAnchor);
    }
  }

  function init() {
    // Scope: <main>, falling back to <body> for pages without <main>
    const root = document.querySelector('main') || document.body;
    if (!root) return;
    scanContainer(root);
    // Re-scan after dynamic content lands (analyze.js, search.js, classes.js etc.)
    // Use a generous debounce so we don't fight async renders.
    if ('MutationObserver' in window) {
      let pending = null;
      const obs = new MutationObserver(() => {
        if (pending) return;
        pending = setTimeout(() => {
          pending = null;
          scanContainer(root);
        }, 600);
      });
      obs.observe(root, { childList: true, subtree: true });
    }
    // Wire interactions on root (delegated, so re-scan adds work transparently)
    root.addEventListener('mouseover', onPointerEnter, true);
    root.addEventListener('mouseout', onPointerLeave, true);
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
