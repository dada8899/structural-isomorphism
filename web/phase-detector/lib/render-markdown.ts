// W10-D: minimal server-side markdown → HTML renderer.
//
// Why in-house: phase-detector already has zero markdown deps. Pulling in
// `marked` + `dompurify` for one weekly newsletter page would balloon the
// bundle. The newsletter source is authored by us, not user-submitted, so
// we can stay strict: only the markdown features actually used by the
// issue template render to HTML; everything else is escaped.
//
// Supported:
//   - h1..h3  (# / ## / ###)
//   - paragraphs (blank-line separated)
//   - bullet lists (- prefix), 2-space indented continuation lines
//   - blockquotes (> prefix), 2-space indented inside a list item
//   - hr  (---)
//   - inline: **bold**, *italic*, `code`, [text](url), and bare URLs
//   - HTML comments are stripped (used to hide TODOs in source)
//
// Author-facing markdown is trusted (we wrote it), so we don't run an HTML
// sanitizer. We do escape any raw < > & in text nodes to avoid accidental
// HTML breaking the page.

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function inline(s: string): string {
  // Escape first, then apply inline rules on the escaped text.
  let out = escapeHtml(s);

  // Inline code: `…` (no nested backticks)
  out = out.replace(/`([^`]+)`/g, (_, code) => `<code>${code}</code>`);

  // Links: [text](url)
  out = out.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    (_, text, url) =>
      `<a href="${url}" data-nl-link="1" target="_blank" rel="noopener noreferrer">${text}</a>`
  );

  // Bold: **…**
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Italic: *…* (after bold so we don't eat ** spans)
  out = out.replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s.,!?)]|$)/g, "$1<em>$2</em>");

  // Italic: _…_ (underscore variant). Be conservative: require word boundary
  // on both sides so we don't eat snake_case identifiers like `approaching_critical`.
  out = out.replace(
    /(^|[\s(])_([^_\s][^_]*?)_(?=[\s.,!?)]|$)/g,
    "$1<em>$2</em>"
  );

  return out;
}

interface Block {
  kind: "h1" | "h2" | "h3" | "p" | "ul" | "blockquote" | "hr";
  text?: string;
  items?: string[]; // each item may contain inline HTML + nested <br>
}

export function renderMarkdown(md: string): string {
  // Strip HTML comments first.
  const cleaned = md.replace(/<!--[\s\S]*?-->/g, "").replace(/\r\n/g, "\n");
  const lines = cleaned.split("\n");

  const blocks: Block[] = [];
  let i = 0;

  const isHr = (l: string) => /^-{3,}\s*$/.test(l);
  const isHeading = (l: string) => /^#{1,3}\s+/.test(l);
  const isListItem = (l: string) => /^- (?!- )/.test(l);
  const isBlockquote = (l: string) => /^>\s/.test(l);

  while (i < lines.length) {
    let line = lines[i];
    if (line.trim() === "") {
      i += 1;
      continue;
    }

    if (isHr(line)) {
      blocks.push({ kind: "hr" });
      i += 1;
      continue;
    }

    const m = /^(#{1,3})\s+(.*)$/.exec(line);
    if (m) {
      const level = m[1].length as 1 | 2 | 3;
      blocks.push({
        kind: ("h" + level) as "h1" | "h2" | "h3",
        text: m[2].trim(),
      });
      i += 1;
      continue;
    }

    if (isBlockquote(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && isBlockquote(lines[i])) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ kind: "blockquote", text: quoteLines.join(" ") });
      continue;
    }

    if (isListItem(line)) {
      const items: string[] = [];
      while (i < lines.length) {
        const l = lines[i];
        if (!isListItem(l)) {
          // continuation: 2-space indented quote / indented text → append to last item
          if (/^ {2}>/.test(l)) {
            // indented blockquote inside list item
            const quoteText = l.replace(/^ {2}>\s?/, "");
            items[items.length - 1] +=
              `<blockquote>${inline(quoteText)}`;
            i += 1;
            // gather subsequent indented quote lines
            while (i < lines.length && /^ {2}>/.test(lines[i])) {
              items[items.length - 1] +=
                " " + inline(lines[i].replace(/^ {2}>\s?/, ""));
              i += 1;
            }
            items[items.length - 1] += "</blockquote>";
            continue;
          }
          if (/^ {2}\S/.test(l)) {
            // 2-space indented continuation: append as inline span
            items[items.length - 1] += " " + inline(l.replace(/^ {2}/, ""));
            i += 1;
            continue;
          }
          if (l.trim() === "") {
            // blank line might end the list
            // peek ahead: if next non-blank is another list item, continue
            let j = i + 1;
            while (j < lines.length && lines[j].trim() === "") j += 1;
            if (j < lines.length && isListItem(lines[j])) {
              i = j;
              continue;
            }
            break;
          }
          break;
        }
        const text = l.replace(/^- /, "");
        items.push(inline(text));
        i += 1;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }

    // Paragraph: gather until blank line / structural break.
    const paraLines: string[] = [line];
    i += 1;
    while (i < lines.length) {
      const l = lines[i];
      if (
        l.trim() === "" ||
        isHr(l) ||
        isHeading(l) ||
        isListItem(l) ||
        isBlockquote(l)
      ) {
        break;
      }
      paraLines.push(l);
      i += 1;
    }
    blocks.push({ kind: "p", text: paraLines.join(" ") });
  }

  const parts: string[] = [];
  for (const b of blocks) {
    switch (b.kind) {
      case "hr":
        parts.push('<hr class="my-8 border-zinc-200" />');
        break;
      case "h1":
        parts.push(
          `<h1 class="serif mt-2 mb-6 text-3xl font-semibold tracking-tight text-zinc-900 md:text-4xl">${inline(
            b.text || ""
          )}</h1>`
        );
        break;
      case "h2":
        parts.push(
          `<h2 class="serif mt-10 mb-4 text-2xl font-semibold tracking-tight text-zinc-900">${inline(
            b.text || ""
          )}</h2>`
        );
        break;
      case "h3":
        parts.push(
          `<h3 class="mt-6 mb-3 text-lg font-semibold text-zinc-900">${inline(
            b.text || ""
          )}</h3>`
        );
        break;
      case "p":
        parts.push(
          `<p class="my-4 text-base leading-relaxed text-zinc-700">${inline(
            b.text || ""
          )}</p>`
        );
        break;
      case "blockquote":
        parts.push(
          `<blockquote class="my-4 border-l-2 border-zinc-300 pl-4 text-sm italic text-zinc-600">${inline(
            b.text || ""
          )}</blockquote>`
        );
        break;
      case "ul":
        {
          const li = (b.items || [])
            .map((it) => `<li class="my-2 leading-relaxed">${it}</li>`)
            .join("");
          parts.push(
            `<ul class="my-4 list-disc space-y-1 pl-6 text-zinc-700">${li}</ul>`
          );
        }
        break;
    }
  }

  return parts.join("\n");
}
