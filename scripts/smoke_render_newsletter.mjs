// W10-D smoke: import render-markdown.ts via Node 22 type-strip, render
// the issue-001 markdown, verify expected structure exists.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");

const { renderMarkdown } = await import(
  path.join(REPO_ROOT, "web/phase-detector/lib/render-markdown.ts")
);

const md = fs.readFileSync(
  path.join(REPO_ROOT, "docs/community/newsletters/issue-001-2026-05-15.md"),
  "utf8"
);
const stripped = md.replace(/^# .*\n+/m, "");
const html = renderMarkdown(stripped);

const checks = [
  { name: "h2 count >= 6", ok: (html.match(/<h2/g) || []).length >= 6 },
  { name: "ul count >= 2", ok: (html.match(/<ul/g) || []).length >= 2 },
  { name: "li count >= 10", ok: (html.match(/<li/g) || []).length >= 10 },
  { name: "blockquote present", ok: /<blockquote/.test(html) },
  { name: "phase flips ticker AFRM", ok: /AFRM/.test(html) },
  { name: "phase flips ticker COIN", ok: /COIN/.test(html) },
  { name: "phase flips ticker DDOG", ok: /DDOG/.test(html) },
  { name: "block-bootstrap mentioned", ok: /block-bootstrap/.test(html) },
  { name: "arxiv section header", ok: /watching/.test(html) },
  { name: "outbound CTA link", ok: /phase\.bytedance\.city/.test(html) },
  { name: "github archive link", ok: /github\.com\/dada8899\/structural-isomorphism/.test(html) },
];

let failed = 0;
for (const c of checks) {
  console.log(c.ok ? "✓" : "✗", c.name);
  if (!c.ok) failed++;
}

console.log(`\nHTML length: ${html.length} chars`);
console.log(`Snippet (first 400):\n${html.slice(0, 400)}`);

if (failed > 0) {
  console.error(`\n${failed} checks FAILED`);
  process.exit(1);
} else {
  console.log(`\nAll ${checks.length} checks passed`);
}
