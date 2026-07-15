/**
 * Structural — Shared site chrome (SESSION-17 P0-2 / P0-3).
 *
 * Single source of truth for the site header + footer. Every .html page
 * has an empty `<header class="site-header">` / `<footer class="site-footer">`;
 * this script fills both with identical markup so navigation is consistent
 * across the whole site.
 *
 * Core nav: 开始研究 / 工具 / 我的报告 / 关于. The logo already provides
 * the home affordance; cold-start users must never land on parameter-only
 * /analyze.
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

  // Core navigation — the homepage is the actual research workbench.
  var NAV = [
    { href: '/', key: 'nav.start_here', label: '开始研究' },
    { href: '/tools', key: 'nav.tools', label: '工具' },
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
    { href: '/reports', key: 'nav.reports', label: '我的研究', external: false },
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

  function langToggleHtml(id, className) {
    if (!window.i18n || typeof window.i18n.toggleLang !== 'function') return '';
    return '<button type="button" class="' + className + '" id="' + id + '" ' +
      'data-structural-lang-toggle aria-label="切换语言"><span data-i18n-lang-label>EN</span></button>';
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
          langToggleHtml('lang-toggle', 'site-header__lang-toggle') +
        '</nav>' +
        '<a href="/auth/login?next=%2Freports" class="site-header__account-cta" ' +
          'data-auth-state="loading" aria-live="polite">登录以同步</a>' +
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
        langToggleHtml('site-menu-lang-toggle', 'site-menu__link site-menu__lang-toggle') +
      '</nav>';

    wireMenu();
    wireLangToggle();
    wireAccountCta();
  }

  // i18n.js wires #lang-toggle once at its own boot; since site-chrome may
  // inject the button afterwards, wire it here too (idempotent).
  function wireLangToggle() {
    var buttons = document.querySelectorAll('[data-structural-lang-toggle]');
    buttons.forEach(function (btn) {
      if (btn.__structuralLangWired) return;
      btn.__structuralLangWired = true;
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        try {
          if (window.i18n && typeof window.i18n.toggleLang === 'function') {
            window.i18n.toggleLang();
          }
        } catch (err) {}
        if (btn.id === 'site-menu-lang-toggle') {
          var drawer = document.getElementById('site-menu-drawer');
          if (drawer && typeof drawer.__structuralCloseMenu === 'function') {
            drawer.__structuralCloseMenu();
          }
        }
      });
    });
  }

  function wireAccountCta() {
    var cta = document.querySelector('.site-header__account-cta');
    if (!cta || cta.__accountWired) return;
    cta.__accountWired = true;
    var authenticated = false;
    var conflicted = false;

    function render() {
      var lang = 'zh';
      try {
        if (window.i18n && typeof window.i18n.getLang === 'function') {
          lang = window.i18n.getLang();
        } else if ((document.documentElement.lang || '').toLowerCase().indexOf('en') === 0) {
          lang = 'en';
        }
      } catch (_error) {}
      cta.textContent = conflicted
        ? (lang === 'en' ? 'Confirm account' : '确认账户')
        : (authenticated
          ? (lang === 'en' ? 'My research' : '我的研究')
          : (lang === 'en' ? 'Sign in to sync' : '登录以同步'));
      cta.href = authenticated ? '/reports' : '/auth/login?next=%2Freports';
      cta.dataset.authState = conflicted ? 'conflict' : (authenticated ? 'authenticated' : 'anonymous');
    }

    if (window.i18n && typeof window.i18n.onChange === 'function') {
      window.i18n.onChange(render);
    }
    render();
    window.fetch('/api/auth/me', { credentials: 'same-origin' })
      .then(function (response) {
        authenticated = response.ok;
        if (response.ok) return {};
        return response.json().catch(function () { return {}; });
      })
      .then(function (problem) { conflicted = problem.error === 'credential_conflict'; render(); })
      .catch(function () { authenticated = false; conflicted = false; render(); });
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
        var first = drawer.querySelector('a[href], button:not([disabled])');
        if (first) first.focus();
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
          btn.focus();
        }
      }, 240);
    }
    // Language switching, the close button, the scrim and Escape all use the
    // same close/focus-restoration contract.
    drawer.__structuralCloseMenu = close;

    btn.addEventListener('click', open);
    drawer.addEventListener('click', function (e) {
      if (e.target.closest('[data-menu-close]')) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && drawer.classList.contains('site-menu--open')) {
        close();
        return;
      }
      if (e.key === 'Tab' && drawer.classList.contains('site-menu--open')) {
        var focusable = Array.prototype.slice.call(
          drawer.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')
        );
        if (!focusable.length) return;
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
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
        '<div class="site-footer__links">' + links +
          '<button type="button" class="site-footer__link site-footer__link--button" ' +
            'data-analytics-settings data-i18n="analytics.settings">分析设置</button>' +
        '</div>' +
      '</div>';
  }

  function boot() {
    renderHeader();
    renderFooter();
    if (
      window.StructuralAnalytics &&
      typeof window.StructuralAnalytics.refreshLabels === 'function'
    ) {
      window.StructuralAnalytics.refreshLabels();
    }
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
