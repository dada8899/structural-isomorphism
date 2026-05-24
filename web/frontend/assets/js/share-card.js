/**
 * Structural — Share card generator
 *
 * Generates a 1200x630 PNG share card for a structural mapping pair,
 * entirely on the client using Canvas. No server dependencies.
 */

const SHARE_CARD = {
  width: 1200,
  height: 630,
  padding: 64,
  bg: '#0A0A0B',
  bgAccent: '#18181B',
  textPrimary: '#FAFAF9',
  textSecondary: '#A1A1AA',
  textTertiary: '#52525B',
  accent: '#3B82F6',
};

/**
 * Wrap text to fit within a max width. Returns array of lines.
 */
function wrapText(ctx, text, maxWidth) {
  const chars = [...text]; // Works for CJK
  const lines = [];
  let current = '';
  for (const ch of chars) {
    const test = current + ch;
    if (ctx.measureText(test).width > maxWidth && current.length > 0) {
      lines.push(current);
      current = ch;
    } else {
      current = test;
    }
  }
  if (current) lines.push(current);
  return lines;
}

/**
 * Draw a rounded rectangle path (no arcTo stitching).
 */
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/**
 * Render the share card.
 * @param {{a: {name, domain, description}, b: {...}, similarity, mapping}} data
 * @returns {HTMLCanvasElement}
 */
function renderShareCard(data) {
  const W = SHARE_CARD.width;
  const H = SHARE_CARD.height;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  // === Background ===
  const bg = ctx.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, SHARE_CARD.bg);
  bg.addColorStop(1, SHARE_CARD.bgAccent);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // Subtle grid decoration
  ctx.strokeStyle = 'rgba(255,255,255,0.03)';
  ctx.lineWidth = 1;
  for (let x = 0; x < W; x += 48) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  }
  for (let y = 0; y < H; y += 48) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(W, y);
    ctx.stroke();
  }

  const pad = SHARE_CARD.padding;
  const fontSans = '"Inter", "PingFang SC", -apple-system, system-ui, sans-serif';
  const fontSerif = '"Noto Serif SC", "Songti SC", serif';
  const fontMono = '"JetBrains Mono", "SF Mono", monospace';

  // === Top: Logo + URL ===
  ctx.fillStyle = SHARE_CARD.textPrimary;
  ctx.font = `500 22px ${fontSerif}`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';

  // Logo icon (two circles + line)
  const logoX = pad;
  const logoY = pad;
  ctx.strokeStyle = SHARE_CARD.textPrimary;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(logoX + 6, logoY + 10, 4, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(logoX + 20, logoY + 22, 4, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(logoX + 9, logoY + 13);
  ctx.lineTo(logoX + 17, logoY + 19);
  ctx.stroke();
  // Logo text
  ctx.fillStyle = SHARE_CARD.textPrimary;
  ctx.font = `500 22px ${fontSerif}`;
  ctx.fillText('Structural', logoX + 34, logoY + 6);

  // Right: tagline
  ctx.fillStyle = SHARE_CARD.textTertiary;
  ctx.font = `400 14px ${fontSans}`;
  ctx.textAlign = 'right';
  ctx.fillText('structural.bytedance.city', W - pad, logoY + 12);

  // === Similarity badge (center top) ===
  const simText = `${Math.round((data.similarity || 0) * 100)}% 同构`;
  ctx.textAlign = 'center';
  ctx.font = `500 16px ${fontMono}`;
  const simW = ctx.measureText(simText).width + 32;
  const simX = W / 2 - simW / 2;
  const simY = pad + 4;
  ctx.fillStyle = 'rgba(255,255,255,0.06)';
  roundRect(ctx, simX, simY, simW, 32, 16);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.lineWidth = 1;
  roundRect(ctx, simX, simY, simW, 32, 16);
  ctx.stroke();
  ctx.fillStyle = SHARE_CARD.textPrimary;
  ctx.textBaseline = 'middle';
  ctx.fillText(simText, W / 2, simY + 16);

  // === Two phenomenon cards ===
  const cardY = 180;
  const cardH = 240;
  const cardGap = 80;
  const cardW = (W - pad * 2 - cardGap) / 2;

  const drawCard = (x, item, align) => {
    // Card background
    ctx.fillStyle = 'rgba(255,255,255,0.04)';
    roundRect(ctx, x, cardY, cardW, cardH, 16);
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    ctx.lineWidth = 1;
    roundRect(ctx, x, cardY, cardW, cardH, 16);
    ctx.stroke();

    const innerPad = 32;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';

    // Domain label
    ctx.fillStyle = SHARE_CARD.textTertiary;
    ctx.font = `500 12px ${fontMono}`;
    const domain = (item.domain || '').toUpperCase();
    ctx.fillText(domain, x + innerPad, cardY + innerPad);

    // Name (large serif)
    ctx.fillStyle = SHARE_CARD.textPrimary;
    ctx.font = `400 30px ${fontSerif}`;
    const nameLines = wrapText(ctx, item.name || '', cardW - innerPad * 2);
    nameLines.slice(0, 2).forEach((line, i) => {
      ctx.fillText(line, x + innerPad, cardY + innerPad + 28 + i * 38);
    });

    // Description (clipped)
    ctx.fillStyle = SHARE_CARD.textSecondary;
    ctx.font = `400 15px ${fontSans}`;
    const descStartY = cardY + innerPad + 28 + nameLines.slice(0, 2).length * 38 + 16;
    const descLines = wrapText(ctx, item.description || '', cardW - innerPad * 2);
    const maxDescLines = Math.floor((cardY + cardH - descStartY - innerPad) / 24);
    descLines.slice(0, maxDescLines).forEach((line, i) => {
      // Truncate last line with ellipsis if needed
      if (i === maxDescLines - 1 && descLines.length > maxDescLines) {
        line = line.slice(0, -2) + '…';
      }
      ctx.fillText(line, x + innerPad, descStartY + i * 24);
    });
  };

  drawCard(pad, data.a, 'left');
  drawCard(pad + cardW + cardGap, data.b, 'right');

  // === Center connector (≅ symbol) ===
  const cx = W / 2;
  const cy = cardY + cardH / 2;

  // Circle
  ctx.fillStyle = SHARE_CARD.textPrimary;
  ctx.beginPath();
  ctx.arc(cx, cy, 34, 0, Math.PI * 2);
  ctx.fill();

  // Outer ring
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, 40, 0, Math.PI * 2);
  ctx.stroke();

  // ≅ symbol
  ctx.fillStyle = '#0A0A0B';
  ctx.font = `400 36px ${fontSerif}`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('≅', cx, cy + 2);

  // === Bottom: structure name + insight ===
  const structureName = (data.mapping && data.mapping.structure_name) || '';
  const insight = (data.mapping && data.mapping.core_insight) || '';

  const bottomY = cardY + cardH + 50;

  if (structureName) {
    // Label
    ctx.fillStyle = SHARE_CARD.textTertiary;
    ctx.font = `500 12px ${fontMono}`;
    ctx.textAlign = 'center';
    ctx.fillText('共享数学结构', W / 2, bottomY);

    // Structure name
    ctx.fillStyle = SHARE_CARD.textPrimary;
    ctx.font = `400 26px ${fontSerif}`;
    ctx.fillText(structureName, W / 2, bottomY + 22);
  }

  if (insight) {
    ctx.fillStyle = SHARE_CARD.textSecondary;
    ctx.font = `400 16px ${fontSans}`;
    ctx.textAlign = 'center';
    const insightLines = wrapText(ctx, insight, W - pad * 4);
    insightLines.slice(0, 2).forEach((line, i) => {
      ctx.fillText(line, W / 2, bottomY + 62 + i * 22);
    });
  }

  return canvas;
}

/**
 * Download the canvas as PNG.
 */
function downloadCanvas(canvas, filename = 'structural-share.png') {
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, 'image/png');
}

/**
 * Copy canvas to clipboard as PNG.
 */
async function copyCanvasToClipboard(canvas) {
  try {
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('Canvas conversion failed');
    await navigator.clipboard.write([
      new ClipboardItem({ 'image/png': blob }),
    ]);
    return true;
  } catch (e) {
    console.error('Copy to clipboard failed:', e);
    return false;
  }
}

/**
 * Render a hook-style share card for a single discovery / universality class.
 * Education-asset variant (Session #18): a bold headline-driven layout,
 * lighter than the dark mapping card above. Light background, big serif hook.
 * @param {{headline, eyebrow, lineA, lineB, footnote, url}} data
 * @returns {HTMLCanvasElement}
 */
function renderHookCard(data) {
  const W = SHARE_CARD.width;
  const H = SHARE_CARD.height;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  const INK = '#18181B';
  const SUB = '#52525B';
  const FAINT = '#A1A1AA';
  const ACCENT = '#3B82F6';
  const pad = SHARE_CARD.padding;
  const fontSans = '"Inter", "PingFang SC", -apple-system, system-ui, sans-serif';
  const fontSerif = '"Noto Serif SC", "Songti SC", serif';

  // === Background — warm off-white with a faint dot grid ===
  ctx.fillStyle = '#FAFAF9';
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(0,0,0,0.035)';
  for (let x = pad; x < W - pad; x += 40) {
    for (let y = 150; y < H - 120; y += 40) {
      ctx.beginPath();
      ctx.arc(x, y, 1.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // === Top: logo + eyebrow ===
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  // logo mark
  ctx.strokeStyle = INK;
  ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.arc(pad + 6, pad + 10, 4, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.arc(pad + 20, pad + 22, 4, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(pad + 9, pad + 13); ctx.lineTo(pad + 17, pad + 19); ctx.stroke();
  ctx.fillStyle = INK;
  ctx.font = `500 22px ${fontSerif}`;
  ctx.fillText('Structural', pad + 34, pad + 6);
  // eyebrow (right)
  if (data.eyebrow) {
    ctx.fillStyle = ACCENT;
    ctx.font = `600 14px ${fontSans}`;
    ctx.textAlign = 'right';
    ctx.fillText(data.eyebrow, W - pad, pad + 12);
  }

  // === Headline — the hook, large serif, up to 3 lines ===
  ctx.textAlign = 'left';
  ctx.fillStyle = INK;
  ctx.font = `600 52px ${fontSerif}`;
  const headlineLines = wrapText(ctx, data.headline || '', W - pad * 2).slice(0, 3);
  let hy = 168;
  headlineLines.forEach((line) => {
    ctx.fillText(line, pad, hy);
    hy += 66;
  });

  // === A ≅ B pairing line ===
  let py = hy + 22;
  if (data.lineA || data.lineB) {
    ctx.font = `500 26px ${fontSans}`;
    ctx.fillStyle = SUB;
    const aText = data.lineA || '';
    const bText = data.lineB || '';
    ctx.fillText(aText, pad, py);
    const aW = ctx.measureText(aText).width;
    ctx.fillStyle = ACCENT;
    ctx.font = `400 26px ${fontSerif}`;
    ctx.fillText('  ≅  ', pad + aW, py);
    const symW = ctx.measureText('  ≅  ').width;
    ctx.fillStyle = SUB;
    ctx.font = `500 26px ${fontSans}`;
    ctx.fillText(bText, pad + aW + symW, py);
  }

  // === Footnote / structure name ===
  if (data.footnote) {
    ctx.fillStyle = FAINT;
    ctx.font = `400 18px ${fontSans}`;
    const fnLines = wrapText(ctx, data.footnote, W - pad * 2).slice(0, 2);
    fnLines.forEach((line, i) => {
      ctx.fillText(line, pad, py + 50 + i * 26);
    });
  }

  // === Bottom URL ===
  ctx.fillStyle = FAINT;
  ctx.font = `400 16px ${fontSans}`;
  ctx.textAlign = 'left';
  ctx.fillText(data.url || 'structural.bytedance.city', pad, H - pad - 4);

  return canvas;
}

/**
 * Build a share-action row (copy link + native share + image card) for a
 * single education asset. Returns an HTMLElement to be appended into a card.
 *
 * @param {{
 *   url: string,            // absolute share URL
 *   shareTitle: string,     // text for navigator.share
 *   shareText: string,      // body text for navigator.share
 *   cardData: object,       // payload for renderHookCard
 *   filename: string,       // download filename for the PNG
 *   compact: boolean        // smaller variant
 * }} opts
 */
function buildShareActions(opts) {
  const wrap = document.createElement('div');
  wrap.className = 'share-actions' + (opts.compact ? ' share-actions--compact' : '');

  // --- Copy link ---
  const copyBtn = document.createElement('button');
  copyBtn.type = 'button';
  copyBtn.className = 'share-actions__btn';
  copyBtn.innerHTML =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>' +
    '<span>复制链接</span>';
  copyBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    let ok = false;
    try {
      await navigator.clipboard.writeText(opts.url);
      ok = true;
    } catch (_) {
      // Fallback for non-secure contexts
      try {
        const ta = document.createElement('textarea');
        ta.value = opts.url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand('copy');
        document.body.removeChild(ta);
      } catch (_2) { ok = false; }
    }
    const span = copyBtn.querySelector('span');
    span.textContent = ok ? '已复制 ✓' : '复制失败';
    copyBtn.classList.toggle('share-actions__btn--done', ok);
    setTimeout(() => {
      span.textContent = '复制链接';
      copyBtn.classList.remove('share-actions__btn--done');
    }, 2000);
  });
  wrap.appendChild(copyBtn);

  // --- Native share (mobile) — only if supported ---
  if (typeof navigator !== 'undefined' && navigator.share) {
    const shareBtn = document.createElement('button');
    shareBtn.type = 'button';
    shareBtn.className = 'share-actions__btn';
    shareBtn.innerHTML =
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98"/></svg>' +
      '<span>分享</span>';
    shareBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      navigator.share({
        title: opts.shareTitle || 'Structural',
        text: opts.shareText || '',
        url: opts.url,
      }).catch(() => {});
    });
    wrap.appendChild(shareBtn);
  }

  // --- Generate image card ---
  const imgBtn = document.createElement('button');
  imgBtn.type = 'button';
  imgBtn.className = 'share-actions__btn';
  imgBtn.innerHTML =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>' +
    '<span>生成图片卡片</span>';
  imgBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    try {
      const canvas = renderHookCard(opts.cardData || {});
      openShareCardModal(canvas, opts.filename || 'structural-card.png');
    } catch (err) {
      console.error('Share card render failed:', err);
    }
  });
  wrap.appendChild(imgBtn);

  return wrap;
}

/**
 * Open a lightweight modal previewing the generated canvas with
 * download + copy-to-clipboard actions.
 */
function openShareCardModal(canvas, filename) {
  const existing = document.querySelector('.share-modal');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.className = 'share-modal';
  overlay.innerHTML =
    '<div class="share-modal__panel" role="dialog" aria-modal="true">' +
      '<button type="button" class="share-modal__close" aria-label="关闭">×</button>' +
      '<div class="share-modal__preview"></div>' +
      '<div class="share-modal__actions">' +
        '<button type="button" class="share-modal__btn share-modal__btn--primary" data-act="download">下载图片</button>' +
        '<button type="button" class="share-modal__btn" data-act="copy">复制到剪贴板</button>' +
      '</div>' +
      '<p class="share-modal__hint">分享到社交平台 · 1200×630</p>' +
    '</div>';

  // Display canvas scaled to fit
  const img = document.createElement('img');
  img.src = canvas.toDataURL('image/png');
  img.alt = '分享卡片预览';
  img.className = 'share-modal__img';
  overlay.querySelector('.share-modal__preview').appendChild(img);

  const close = () => overlay.remove();
  overlay.querySelector('.share-modal__close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.addEventListener('keydown', function esc(ev) {
    if (ev.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
  });

  overlay.querySelector('[data-act="download"]').addEventListener('click', () => {
    downloadCanvas(canvas, filename);
  });
  const copyBtn = overlay.querySelector('[data-act="copy"]');
  copyBtn.addEventListener('click', async () => {
    const ok = await copyCanvasToClipboard(canvas);
    copyBtn.textContent = ok ? '已复制 ✓' : '复制失败（请用下载）';
    setTimeout(() => { copyBtn.textContent = '复制到剪贴板'; }, 2200);
  });

  document.body.appendChild(overlay);
}

window.ShareCard = {
  render: renderShareCard,
  renderHook: renderHookCard,
  download: downloadCanvas,
  copy: copyCanvasToClipboard,
  buildActions: buildShareActions,
  openModal: openShareCardModal,
};
