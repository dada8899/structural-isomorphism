(function () {
  'use strict';

  const MAX_MARKDOWN_BYTES = 512000;
  const REPOSITORY_URL = 'https://github.com/dada8899/structural-isomorphism/';
  const ALLOWED_TAGS = new Set([
    'A', 'BLOCKQUOTE', 'BR', 'CODE', 'DEL', 'EM', 'H2', 'H3', 'H4', 'H5', 'H6',
    'HR', 'LI', 'OL', 'P', 'PRE', 'STRONG', 'TABLE', 'TBODY', 'TD', 'TH',
    'THEAD', 'TR', 'UL',
  ]);
  const TOKEN_OPEN = '\uE000';
  const TOKEN_CLOSE = '\uE001';

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function safeHref(value) {
    if (typeof value !== 'string') return '';
    const href = value.trim();
    if (!href || /[\u0000-\u0020\u007f\\]/.test(href)) return '';
    if (/^#[a-zA-Z0-9._:-]*$/.test(href)) return href;
    if (/^\/(?!\/)[a-zA-Z0-9._~!$&'()*+,;=:@%/?#-]*$/.test(href)) return href;
    if (/^\.\.\/(?:v4|tutorials)\/[a-zA-Z0-9._/-]+$/.test(href) && !href.includes('..', 3)) {
      const repositoryPath = href.slice(3);
      return `${REPOSITORY_URL}blob/main/${repositoryPath}`;
    }
    let parsed;
    try {
      parsed = new URL(href);
    } catch (_error) {
      return '';
    }
    if (
      parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' ||
      parsed.username || parsed.password || parsed.port || parsed.hash || parsed.search ||
      !parsed.pathname.startsWith('/dada8899/structural-isomorphism/')
    ) return '';
    return parsed.toString();
  }

  function formatEmphasis(value) {
    return value
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
      .replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
      .replace(/(^|[^_])_([^_\n]+)_(?!_)/g, '$1<em>$2</em>');
  }

  function renderInline(rawValue) {
    const tokens = [];
    let value = String(rawValue).replace(/[\uE000\uE001]/g, '\uFFFD');
    function token(html) {
      const index = tokens.push(html) - 1;
      return `${TOKEN_OPEN}${index}${TOKEN_CLOSE}`;
    }

    value = value.replace(/(`+)([\s\S]*?)\1/g, (_match, _ticks, code) => {
      return token(`<code>${escapeHtml(code.replace(/^ | $/g, ''))}</code>`);
    });
    value = value.replace(
      /\[([^\]\n]{1,500})\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,
      (_match, label, rawHref) => {
        const href = safeHref(rawHref);
        if (!href) return label;
        const external = href.startsWith('https://');
        const attributes = external ? ' target="_blank" rel="noopener noreferrer"' : '';
        return token(`<a href="${escapeHtml(href)}"${attributes}>${formatEmphasis(escapeHtml(label))}</a>`);
      },
    );
    value = formatEmphasis(escapeHtml(value));
    value = value.replace(/ {2}\n/g, '<br>');
    value = value.replace(/\n/g, ' ');
    tokens.forEach((html, index) => {
      value = value.split(`${TOKEN_OPEN}${index}${TOKEN_CLOSE}`).join(html);
    });
    return value;
  }

  function splitTableRow(line) {
    let value = line.trim();
    if (value.startsWith('|')) value = value.slice(1);
    if (value.endsWith('|')) value = value.slice(0, -1);
    const cells = [];
    let current = '';
    let escaped = false;
    for (const character of value) {
      if (escaped) {
        current += character;
        escaped = false;
      } else if (character === '\\') {
        current += character;
        escaped = true;
      } else if (character === '|') {
        cells.push(current.trim());
        current = '';
      } else {
        current += character;
      }
    }
    cells.push(current.trim());
    return cells;
  }

  function isTableSeparator(line) {
    const cells = splitTableRow(line);
    return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
  }

  function isBlockStart(lines, index) {
    const line = lines[index] || '';
    const next = lines[index + 1] || '';
    return (
      !line.trim() || /^ {0,3}(#{1,6})\s+/.test(line) || /^ {0,3}(```+|~~~+)/.test(line) ||
      /^ {0,3}(?:[-*_]\s*){3,}$/.test(line) || /^\s*>/.test(line) ||
      /^\s*[-+*]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line) ||
      (line.includes('|') && isTableSeparator(next))
    );
  }

  function renderTable(lines, start) {
    const headings = splitTableRow(lines[start]);
    let index = start + 2;
    const rows = [];
    while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
      rows.push(splitTableRow(lines[index]));
      index += 1;
    }
    const width = headings.length;
    const head = headings.map((cell) => `<th scope="col">${renderInline(cell)}</th>`).join('');
    const body = rows.map((row) => {
      const normalized = Array.from({ length: width }, (_unused, cellIndex) => row[cellIndex] || '');
      return `<tr>${normalized.map((cell) => `<td>${renderInline(cell)}</td>`).join('')}</tr>`;
    }).join('');
    return {
      html: `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`,
      next: index,
    };
  }

  function renderBlocks(markdown, headingOffset) {
    const lines = String(markdown).replace(/\r\n?/g, '\n').split('\n');
    const output = [];
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) {
        index += 1;
        continue;
      }

      const fence = line.match(/^ {0,3}(```+|~~~+)\s*([a-zA-Z0-9_-]{0,40})\s*$/);
      if (fence) {
        const marker = fence[1][0];
        const minimum = fence[1].length;
        const code = [];
        index += 1;
        while (index < lines.length && !new RegExp(`^ {0,3}${marker}{${minimum},}\\s*$`).test(lines[index])) {
          code.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) index += 1;
        const languageClass = fence[2] ? ` class="language-${escapeHtml(fence[2].toLowerCase())}"` : '';
        output.push(`<pre><code${languageClass}>${escapeHtml(code.join('\n'))}</code></pre>`);
        continue;
      }

      const heading = line.match(/^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
      if (heading) {
        const level = Math.min(6, heading[1].length + headingOffset);
        output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        index += 1;
        continue;
      }
      if (/^ {0,3}(?:[-*_]\s*){3,}$/.test(line)) {
        output.push('<hr>');
        index += 1;
        continue;
      }
      if (line.includes('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
        const table = renderTable(lines, index);
        output.push(table.html);
        index = table.next;
        continue;
      }
      if (/^\s*>/.test(line)) {
        const quote = [];
        while (index < lines.length && /^\s*>/.test(lines[index])) {
          quote.push(lines[index].replace(/^\s*>\s?/, ''));
          index += 1;
        }
        output.push(`<blockquote>${renderBlocks(quote.join('\n'), headingOffset)}</blockquote>`);
        continue;
      }

      const list = line.match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);
      if (list) {
        const ordered = /^\d/.test(list[1]);
        const tag = ordered ? 'ol' : 'ul';
        const items = [];
        while (index < lines.length) {
          const item = lines[index].match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);
          if (!item || /^\d/.test(item[1]) !== ordered) break;
          items.push(`<li>${renderInline(item[2])}</li>`);
          index += 1;
        }
        output.push(`<${tag}>${items.join('')}</${tag}>`);
        continue;
      }

      const paragraph = [line.trim()];
      index += 1;
      while (index < lines.length && !isBlockStart(lines, index)) {
        paragraph.push(lines[index].trim());
        index += 1;
      }
      output.push(`<p>${renderInline(paragraph.join('\n'))}</p>`);
    }
    return output.join('');
  }

  function sanitizeRenderedHtml(html) {
    const template = document.createElement('template');
    template.innerHTML = html;

    function sanitizeChildren(parent) {
      Array.from(parent.children).forEach((element) => {
        if (!ALLOWED_TAGS.has(element.tagName)) {
          element.replaceWith(document.createTextNode(element.textContent || ''));
          return;
        }
        Array.from(element.attributes).forEach((attribute) => {
          const name = attribute.name.toLowerCase();
          const allowed = (
            (element.tagName === 'A' && ['href', 'target', 'rel'].includes(name)) ||
            (element.tagName === 'CODE' && name === 'class') ||
            (element.tagName === 'TH' && name === 'scope')
          );
          if (!allowed || name.startsWith('on')) element.removeAttribute(attribute.name);
        });
        if (element.tagName === 'A') {
          const href = safeHref(element.getAttribute('href') || '');
          if (!href) {
            element.removeAttribute('href');
            element.removeAttribute('target');
            element.removeAttribute('rel');
          } else {
            element.setAttribute('href', href);
            if (href.startsWith('https://')) {
              element.setAttribute('target', '_blank');
              element.setAttribute('rel', 'noopener noreferrer');
            } else {
              element.removeAttribute('target');
              element.removeAttribute('rel');
            }
          }
        }
        if (element.tagName === 'CODE' && element.hasAttribute('class')) {
          const className = element.getAttribute('class') || '';
          if (!/^language-[a-z0-9_-]{1,40}$/.test(className)) element.removeAttribute('class');
        }
        if (element.tagName === 'TH') element.setAttribute('scope', 'col');
        sanitizeChildren(element);
      });
    }

    sanitizeChildren(template.content);
    return template.innerHTML;
  }

  function render(markdown, options) {
    if (typeof markdown !== 'string') throw new Error('Markdown input must be text');
    if (new TextEncoder().encode(markdown).length > MAX_MARKDOWN_BYTES) {
      throw new Error('Markdown document exceeds the public rendering limit');
    }
    const requestedOffset = options && Number.isInteger(options.headingOffset)
      ? options.headingOffset
      : 1;
    const headingOffset = Math.min(5, Math.max(1, requestedOffset));
    return sanitizeRenderedHtml(renderBlocks(markdown, headingOffset));
  }

  window.StructuralSafeMarkdown = Object.freeze({
    MAX_MARKDOWN_BYTES,
    render,
    safeHref,
    sanitizeRenderedHtml,
  });
})();
