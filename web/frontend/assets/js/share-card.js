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

window.ShareCard = { render: renderShareCard, download: downloadCanvas, copy: copyCanvasToClipboard };
