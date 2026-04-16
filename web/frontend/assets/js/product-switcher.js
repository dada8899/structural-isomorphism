/**
 * Product switcher chip (🎓 学术版 ↔ 💼 商业版)
 * Auto-injects CSS + HTML into any page's header.
 * Works on both academic (/) pages and commercial (/phase) pages.
 */
(function () {
  if (document.querySelector('.product-switcher')) return;

  var css =
    '.site-header__logo-wrap,.brand-wrap{display:inline-flex;align-items:center;gap:14px;flex-wrap:wrap}' +
    '.product-switcher{display:inline-flex;align-items:center;gap:2px;padding:2px;background:rgba(0,0,0,0.04);border:1px solid rgba(0,0,0,0.08);border-radius:999px;font-size:12px}' +
    '.product-switcher__seg{padding:5px 12px;border-radius:999px;color:#52525B;text-decoration:none;transition:all .15s;white-space:nowrap;font-weight:500;font-family:inherit}' +
    '.product-switcher__seg:hover{color:#18181B;text-decoration:none}' +
    '.product-switcher__seg--active{background:#FFFFFF;color:#2563EB;box-shadow:0 1px 2px rgba(0,0,0,0.06);border:1px solid rgba(37,99,235,0.18)}' +
    '@media (max-width:640px){.product-switcher{margin-top:4px}}';

  var style = document.createElement('style');
  style.setAttribute('data-product-switcher', '');
  style.textContent = css;
  document.head.appendChild(style);

  var isPhase = window.location.pathname.indexOf('/phase') === 0;

  var segAcademic = isPhase
    ? '<a class="product-switcher__seg" href="/">🎓 学术版</a>'
    : '<span class="product-switcher__seg product-switcher__seg--active" aria-current="page">🎓 学术版</span>';
  var segCommercial = isPhase
    ? '<span class="product-switcher__seg product-switcher__seg--active" aria-current="page">💼 商业版</span>'
    : '<a class="product-switcher__seg" href="/phase">💼 商业版</a>';

  var switcher = document.createElement('div');
  switcher.className = 'product-switcher';
  switcher.setAttribute('role', 'tablist');
  switcher.setAttribute('aria-label', '产品切换');
  switcher.innerHTML = segAcademic + segCommercial;

  function mount() {
    if (document.querySelector('.product-switcher')) return;
    var logo = document.querySelector('.site-header__logo, .brand');
    if (!logo) return;
    var wrapClass = isPhase ? 'brand-wrap' : 'site-header__logo-wrap';
    var wrap = logo.closest('.' + wrapClass);
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = wrapClass;
      var parent = logo.parentNode;
      parent.insertBefore(wrap, logo);
      wrap.appendChild(logo);
    }
    wrap.appendChild(switcher);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
