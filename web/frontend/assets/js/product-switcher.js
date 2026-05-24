/**
 * 品牌层次：Phase 为 Structural 的子产品
 *
 * 商业版 (/phase/*) 左上 (竖排)：
 *   ◯ Structural [beta]       ← 大号主品牌，点击回主站
 *     ↳ [商业版] Phase Detector  ← 缩进小字，子产品标识
 *
 * 学术版 (/)：不注入任何东西。
 */
(function () {
  var isPhase = window.location.pathname.indexOf('/phase') === 0;
  if (!isPhase) return;
  if (document.querySelector('.parent-brand')) return;

  // ========== 样式 ==========
  var css = [
    /* 竖排容器 */
    '.brand-group{',
    '  display:inline-flex;flex-direction:column;align-items:flex-start;',
    '  gap:3px;line-height:1;',
    '}',

    /* 主品牌（Structural）— 大号，主要视觉 */
    '.parent-brand{',
    '  display:inline-flex;align-items:center;gap:9px;',
    '  padding:4px 10px 4px 8px;',
    '  border-radius:8px;',
    '  color:#18181B;text-decoration:none !important;',
    '  font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",Georgia,serif;',
    '  font-weight:600;font-size:17.5px;',
    '  letter-spacing:-0.005em;',
    '  transition:all .18s cubic-bezier(0.4,0,0.2,1);',
    '  position:relative;',
    '  cursor:pointer;',
    '}',
    '.parent-brand:hover{',
    '  background:#EFF6FF;',
    '  color:#1E40AF;',
    '  transform:translateX(-2px);',
    '}',
    '.parent-brand__icon{',
    '  width:22px;height:22px;color:#2563EB;flex-shrink:0;',
    '}',
    '.parent-brand__text{font-weight:600}',
    '.parent-brand__beta{',
    '  font-size:9.5px;padding:2px 6px;',
    '  background:rgba(37,99,235,0.10);color:#2563EB;',
    '  border-radius:3px;letter-spacing:0.5px;font-weight:600;',
    '  font-family:Inter,-apple-system,system-ui,sans-serif;',
    '  margin-left:2px;',
    '}',
    /* hover 时显示小箭头表示可点击 */
    '.parent-brand__arrow{',
    '  font-size:13px;font-weight:600;color:#2563EB;',
    '  opacity:0;width:0;overflow:hidden;',
    '  transition:all .18s;',
    '}',
    '.parent-brand:hover .parent-brand__arrow{',
    '  opacity:1;width:14px;margin-left:2px;',
    '}',

    /* 子产品标签行（缩进显示） */
    '.sub-product-label{',
    '  display:inline-flex;align-items:center;gap:6px;',
    '  padding-left:36px;',  /* 与 Structural 文字左对齐 */
    '  font-size:11.5px;',
    '  color:#71717A;',
    '  letter-spacing:0.01em;',
    '  font-family:Inter,-apple-system,system-ui,sans-serif;',
    '  font-weight:500;',
    '}',
    '.sub-product-label__arrow{',
    '  color:#CBD5E1;font-size:14px;line-height:1;',
    '  font-weight:400;',
    '}',
    '.sub-product-label__badge{',
    '  display:inline-flex;',
    '  padding:1.5px 7px;',
    '  background:linear-gradient(135deg,#2563EB,#1D4ED8);',
    '  color:#FFFFFF;',
    '  border-radius:4px;',
    '  font-weight:600;font-size:10px;',
    '  letter-spacing:0.4px;',
    '  text-transform:uppercase;',
    '  box-shadow:0 1px 2px rgba(37,99,235,0.2);',
    '}',
    '.sub-product-label__name{',
    '  font-weight:500;color:#52525B;',
    '}',
    '.sub-product-label__beta{',
    '  font-size:9px;padding:1px 4px;',
    '  background:#F4F4F5;color:#A1A1AA;',
    '  border-radius:3px;letter-spacing:0.3px;font-weight:600;',
    '  margin-left:1px;',
    '}',

    /* 隐藏原 .brand — 子产品信息由 sub-product-label 替代 */
    '.brand-group .brand{display:none !important}',

    /* 响应式 */
    '@media(max-width:640px){',
    '  .parent-brand{padding:3px 8px 3px 6px;font-size:15.5px;gap:7px}',
    '  .parent-brand__icon{width:19px;height:19px}',
    '  .sub-product-label{padding-left:32px;font-size:10.5px}',
    '  .sub-product-label__badge{font-size:9px}',
    '}',
  ].join('');

  var style = document.createElement('style');
  style.setAttribute('data-brand-hierarchy', '');
  style.textContent = css;
  document.head.appendChild(style);

  // ========== DOM 注入 ==========
  function mount() {
    if (document.querySelector('.parent-brand')) return;

    // 清理之前版本
    document.querySelectorAll('.product-strip,.product-switcher,.brand-back-link,.brand-back-sep,.nav-back-home,.brand-chevron').forEach(el => el.remove());

    var brand = document.querySelector('.brand');
    if (!brand) return;

    var group = brand.closest('.brand-group');
    if (!group) {
      group = document.createElement('div');
      group.className = 'brand-group';
      brand.parentNode.insertBefore(group, brand);
      group.appendChild(brand);
    }

    // 大号主品牌
    var parentBrand = document.createElement('a');
    parentBrand.className = 'parent-brand';
    parentBrand.href = '/';
    parentBrand.setAttribute('aria-label', '返回 Structural 学术版主站');
    parentBrand.title = '返回 Structural 学术版主站';
    parentBrand.innerHTML =
      '<svg class="parent-brand__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
      '  <circle cx="6" cy="6" r="3"/>' +
      '  <circle cx="18" cy="18" r="3"/>' +
      '  <path d="M8.5 8.5l7 7"/>' +
      '</svg>' +
      '<span class="parent-brand__text">Structural</span>' +
      '<span class="parent-brand__beta">beta</span>' +
      '<span class="parent-brand__arrow" aria-hidden="true">←</span>';

    // 子产品缩进标签
    var subLabel = document.createElement('div');
    subLabel.className = 'sub-product-label';
    subLabel.innerHTML =
      '<span class="sub-product-label__arrow">↳</span>' +
      '<span class="sub-product-label__badge">商业版</span>' +
      '<span class="sub-product-label__name">Phase Detector</span>' +
      '<span class="sub-product-label__beta">BETA</span>';

    // 插到 group 最前面
    group.insertBefore(subLabel, group.firstChild);
    group.insertBefore(parentBrand, subLabel);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
