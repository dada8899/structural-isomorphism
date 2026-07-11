/**
 * Structural — Shared site chrome (SESSION-17 P0-2 / P0-3).
 *
 * Single source of truth for the site header + footer. Every .html page
 * has an empty `<header class="site-header">` / `<footer class="site-footer">`;
 * this script fills both with identical markup so navigation is consistent
 * across the whole site.
 *
 * Core nav (product decision, SESSION-17): 首页 / 分析 / 我的报告 / 关于.
 * Mobile (<=720px): the inline nav collapses into an iOS-style hamburger
 * drawer so phone users can still reach every core page.
 */
(function () {
  'use strict';

  // i18n helper — falls back to the zh string when i18n.js is absent.
  function T(key, fallback) {
    try {
      if (window.i18n && typeof window.i18n.t === 'function') {
        var v = window.i18n.t(key);
        if (v && v !== key) return v;
      }
    } catch (e) {}
    return fallback;
  }

  // Core navigation — 4 items only (SESSION-17 product decision).
  var NAV = [
    { href: '/', key: 'nav.home', label: '首页' },
    { href: '/analyze', key: 'nav.analyze', label: '分析' },
    { href: '/tools', key: 'nav.tools', label: '工具' },
    { href: '/reports', key: 'nav.reports', label: '我的报告' },
    {
      href: 'https://phase.bytedance.city/auth/login',
      key: 'nav.auth',
      label: 'Phase 账户 ↗',
      external: true
    },
    { href: '/about', key: 'nav.about', label: '关于' },
  ];

  // Pages that live under the 工具 hub (SESSION-18) — visiting any of them
  // marks 工具 as the current nav item.
  var TOOLS_PATHS = [
    '/tools', '/whitespace', '/apply', '/stress-test', '/lint',
    '/diagnose', '/insights', '/discoveries', '/classes',
    '/connections',
  ];

  // Footer links — kept short and identical everywhere.
  var FOOTER_LINKS = [
    { href: '/about', key: 'footer.about', label: '关于', external: false },
    { href: '/reports', key: 'nav.reports', label: '我的报告', external: false },
    { href: '/privacy', key: 'footer.privacy', label: '隐私政策', external: false },
    { href: 'https://github.com/dada8899/structural-isomorphism', key: 'footer.github', label: 'GitHub', external: true },
  ];

  // Decide which nav item is the "current" page so we can mark it.
  function currentPath() {
    var p = window.location.pathname.replace(/\/+$/, '') || '/';
    // /report/<id> and /report/share/<token> count as the analysis flow.
    if (p === '/report' || p.indexOf('/report/') === 0) return '/reports';
    if (p === '/index.html') return '/';
    // strip a trailing .html so /about.html matches /about
    var noExt = p.replace(/\.html$/, '');
    // SESSION-18 — any tool page highlights the 工具 hub.
    if (TOOLS_PATHS.indexOf(noExt) !== -1) return '/tools';
    return noExt || '/';
  }

  var LOGO_SVG =
    '<svg class="site-header__logo-mark" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" ' +
    'stroke-linejoin="round" aria-hidden="true">' +
    '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/>' +
    '<path d="M8.5 8.5l7 7"/></svg>';

  function navLinksHtml(extraClass) {
    var cur = currentPath();
    return NAV.map(function (item) {
      var isCurrent = item.href === cur;
      return (
        '<a href="' + item.href + '" class="' + extraClass + '"' +
        (item.external ? ' target="_blank" rel="noopener"' : '') +
        (isCurrent ? ' aria-current="page"' : '') +
        ' data-i18n="' + item.key + '">' + item.label + '</a>'
      );
    }).join('');
  }

  function renderHeader() {
    var header = document.querySelector('.site-header');
    if (!header) return;
    // If a page already hand-wrote its header inner, replace it so every
    // page ends up identical.
    header.innerHTML =
      '<div class="site-header__inner">' +
        '<a href="/" class="site-header__logo" aria-label="Structural 首页">' +
          LOGO_SVG +
          'Structural<span class="beta-badge" data-i18n="beta.badge">beta</span>' +
        '</a>' +
        '<nav class="site-header__nav" aria-label="主导航">' +
          navLinksHtml('site-header__nav-link') +
          '<button type="button" class="site-header__lang-toggle" id="lang-toggle" ' +
            'aria-label="切换语言"><span data-i18n-lang-label>EN</span></button>' +
        '</nav>' +
        '<button type="button" class="site-header__menu-btn" id="site-menu-btn" ' +
          'aria-label="打开菜单" aria-expanded="false" aria-controls="site-menu-drawer">' +
          '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" ' +
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
            'aria-hidden="true">' +
            '<path d="M3 6h18M3 12h18M3 18h18"/></svg>' +
        '</button>' +
      '</div>';

    // Mobile drawer — appended to <body>, sits above everything.
    var drawer = document.getElementById('site-menu-drawer');
    if (!drawer) {
      drawer = document.createElement('div');
      drawer.id = 'site-menu-drawer';
      drawer.className = 'site-menu';
      drawer.setAttribute('hidden', '');
      document.body.appendChild(drawer);
    }
    drawer.innerHTML =
      '<div class="site-menu__scrim" data-menu-close></div>' +
      '<nav class="site-menu__panel" aria-label="移动导航">' +
        '<div class="site-menu__head">' +
          '<span class="site-menu__title">Structural</span>' +
          '<button type="button" class="site-menu__close" data-menu-close ' +
            'aria-label="关闭菜单">' +
            '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" ' +
              'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
              'aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>' +
          '</button>' +
        '</div>' +
        navLinksHtml('site-menu__link') +
      '</nav>';

    wireMenu();
    wireLangToggle();
  }

  // i18n.js wires #lang-toggle once at its own boot; since site-chrome may
  // inject the button afterwards, wire it here too (idempotent).
  function wireLangToggle() {
    var btn = document.getElementById('lang-toggle');
    if (!btn || btn.__chromeWired) return;
    btn.__chromeWired = true;
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      try {
        if (window.i18n && typeof window.i18n.toggleLang === 'function') {
          window.i18n.toggleLang();
        }
      } catch (err) {}
    });
  }

  function wireMenu() {
    var btn = document.getElementById('site-menu-btn');
    var drawer = document.getElementById('site-menu-drawer');
    if (!btn || !drawer) return;

    function open() {
      drawer.removeAttribute('hidden');
      // next frame so the CSS transition runs from the hidden state
      requestAnimationFrame(function () {
        drawer.classList.add('site-menu--open');
      });
      btn.setAttribute('aria-expanded', 'true');
      document.body.style.overflow = 'hidden';
    }
    function close() {
      drawer.classList.remove('site-menu--open');
      btn.setAttribute('aria-expanded', 'false');
      document.body.style.overflow = '';
      // wait out the transition before re-hiding from the a11y tree
      setTimeout(function () {
        if (!drawer.classList.contains('site-menu--open')) {
          drawer.setAttribute('hidden', '');
        }
      }, 240);
    }

    btn.addEventListener('click', open);
    drawer.addEventListener('click', function (e) {
      if (e.target.closest('[data-menu-close]')) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && drawer.classList.contains('site-menu--open')) {
        close();
      }
    });
  }

  function renderFooter() {
    var footer = document.querySelector('.site-footer');
    if (!footer) return;
    var year = new Date().getFullYear();
    var links = FOOTER_LINKS.map(function (l) {
      var attrs = l.external ? ' target="_blank" rel="noopener"' : '';
      return (
        '<a class="site-footer__link" href="' + l.href + '"' + attrs +
        ' data-i18n="' + l.key + '">' + l.label + '</a>'
      );
    }).join('');
    footer.innerHTML =
      '<div class="site-footer__inner">' +
        '<div class="site-footer__copyright" data-i18n="footer.copyright">' +
          '© ' + year + ' Structural · 换个学科找答案</div>' +
        '<div class="site-footer__links">' + links + '</div>' +
      '</div>';
  }

  function boot() {
    renderHeader();
    renderFooter();
    if (typeof window.initHeaderScroll === 'function') {
      window.initHeaderScroll();
    }
    // Re-run i18n over the whole page so the freshly-injected header/footer
    // nodes pick up translations (site-chrome may run before/after i18n boot).
    try {
      if (window.i18n && typeof window.i18n.render === 'function') {
        window.i18n.render();
      }
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
