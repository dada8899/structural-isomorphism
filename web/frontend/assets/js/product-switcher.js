/**
 * Phase 子产品品牌层次
 *
 * Phase Detector 是 Structural 的子产品。在所有 /phase/* 页面里，
 * 在品牌 logo 前面注入 "← Structural /" 返回链接，明确父子关系。
 *
 * 学术版（非 /phase）页面不注入任何东西 —— 学术版是主产品。
 */
(function () {
  // 已经注入过就跳过
  if (document.querySelector('.brand-back-link')) return;

  const isPhase = window.location.pathname.indexOf('/phase') === 0;
  if (!isPhase) return;

  // 注入样式
  var css =
    '.brand-wrap,.site-header__logo-wrap{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap;line-height:1}' +
    '.brand-back-link{' +
    '  font-size:13px;color:#71717A;text-decoration:none;font-weight:500;' +
    '  padding:5px 10px;border-radius:6px;transition:all .15s;white-space:nowrap;' +
    '  font-family:Inter,-apple-system,system-ui,sans-serif;' +
    '}' +
    '.brand-back-link:hover{color:#2563EB;background:rgba(37,99,235,0.08);text-decoration:none}' +
    '.brand-back-sep{color:#D4D4D8;font-weight:300;font-size:18px;user-select:none}' +
    '@media(max-width:640px){' +
    '  .brand-back-link{padding:4px 8px;font-size:12px}' +
    '}';
  var style = document.createElement('style');
  style.setAttribute('data-brand-hierarchy', '');
  style.textContent = css;
  document.head.appendChild(style);

  function mount() {
    if (document.querySelector('.brand-back-link')) return;
    var brand = document.querySelector('.brand, .site-header__logo');
    if (!brand) return;

    var wrap = brand.closest('.brand-wrap, .site-header__logo-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'brand-wrap';
      brand.parentNode.insertBefore(wrap, brand);
      wrap.appendChild(brand);
    }

    // 清理旧的 product-switcher（peer 平级切换器）
    wrap.querySelectorAll('.product-switcher').forEach(el => el.remove());

    var backLink = document.createElement('a');
    backLink.className = 'brand-back-link';
    backLink.href = '/';
    backLink.textContent = '← Structural';
    backLink.title = '返回学术版主站';

    var sep = document.createElement('span');
    sep.className = 'brand-back-sep';
    sep.textContent = '/';

    // 插入到 brand 前面
    wrap.insertBefore(backLink, brand);
    wrap.insertBefore(sep, brand);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
