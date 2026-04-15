"""
Build static HTML pages from the sample Markdown reports.

Reads phase/samples/*.md and phase/data/samples_manifest.json,
writes phase/samples/*.html + phase/samples/index.html.

Used at build time (no server-side rendering).
"""
import json
from pathlib import Path
import re

PHASE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = PHASE_DIR / "samples"
MANIFEST = PHASE_DIR / "data" / "samples_manifest.json"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Phase Detector</title>
  <meta name="description" content="{excerpt}">
  <meta property="og:title" content="{title} — Phase Detector">
  <meta property="og:description" content="{excerpt}">

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Serif+SC:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

  <style>
    :root {{
      --bg: #FAFAF9;
      --bg-elevated: #FFFFFF;
      --bg-card: #F4F4F5;
      --border: #E4E4E7;
      --border-strong: #D4D4D8;
      --text: #18181B;
      --text-secondary: #52525B;
      --text-muted: #71717A;
      --accent: #2563EB;
      --accent-dim: rgba(37, 99, 235, 0.08);
      --mono: 'JetBrains Mono', 'Menlo', monospace;
      --serif: 'Noto Serif SC', 'Times New Roman', serif;
      --sans: 'Inter', -apple-system, system-ui, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      font-size: 16px;
      line-height: 1.75;
      -webkit-font-smoothing: antialiased;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    header.site {{
      border-bottom: 1px solid var(--border);
      padding: 20px 0;
      position: sticky; top: 0;
      background: rgba(250, 250, 249, 0.88);
      backdrop-filter: saturate(180%) blur(12px);
      z-index: 100;
    }}
    .container {{ max-width: 820px; margin: 0 auto; padding: 0 24px; }}
    .nav {{ display: flex; justify-content: space-between; align-items: center; }}
    .brand {{
      display: inline-flex; align-items: center; gap: 10px;
      font-weight: 700; font-size: 16px;
    }}
    .brand-mark {{
      width: 20px; height: 20px;
      border: 1.5px solid var(--accent);
      border-radius: 50%;
      position: relative;
    }}
    .brand-mark::before {{
      content: '';
      position: absolute;
      inset: 3px;
      border-radius: 50%;
      background: var(--accent);
    }}
    .brand-beta {{
      font-size: 10px;
      padding: 2px 6px;
      background: var(--accent-dim);
      color: var(--accent);
      border-radius: 3px;
      font-weight: 600;
    }}
    nav.menu a {{
      margin-left: 20px;
      font-size: 14px;
      color: var(--text-muted);
    }}
    nav.menu a:hover {{ color: var(--text); text-decoration: none; }}

    main {{ padding: 60px 0 120px; }}

    .breadcrumb {{
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 24px;
    }}
    .breadcrumb a {{ color: var(--text-muted); }}

    .ticker-eyebrow {{
      font-family: var(--mono);
      font-size: 13px;
      color: var(--accent);
      letter-spacing: 1.5px;
      margin-bottom: 12px;
    }}

    article h1 {{
      font-family: var(--serif);
      font-size: clamp(32px, 4vw, 44px);
      font-weight: 700;
      line-height: 1.2;
      letter-spacing: -0.01em;
      margin-bottom: 16px;
    }}
    article h2 {{
      font-family: var(--serif);
      font-size: 24px;
      font-weight: 700;
      line-height: 1.3;
      margin-top: 48px;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
    }}
    article h3 {{
      font-size: 18px;
      font-weight: 600;
      line-height: 1.4;
      margin-top: 32px;
      margin-bottom: 12px;
      color: var(--text);
    }}
    article h4 {{
      font-size: 15px;
      font-weight: 600;
      margin-top: 20px;
      margin-bottom: 8px;
      color: var(--text);
    }}
    article p {{
      color: var(--text-secondary);
      margin-bottom: 16px;
    }}
    article ul, article ol {{
      color: var(--text-secondary);
      padding-left: 24px;
      margin-bottom: 16px;
    }}
    article li {{ margin-bottom: 6px; }}
    article strong {{ color: var(--text); font-weight: 600; }}
    article em {{ font-style: normal; color: var(--accent); }}

    article code {{
      font-family: var(--mono);
      font-size: 13px;
      background: var(--bg-elevated);
      padding: 2px 6px;
      border-radius: 3px;
      color: var(--text);
      border: 1px solid var(--border);
    }}
    article pre {{
      background: var(--bg-elevated);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 16px 20px;
      overflow-x: auto;
      margin-bottom: 20px;
      font-family: var(--mono);
      font-size: 13.5px;
      line-height: 1.6;
    }}
    article pre code {{
      background: none;
      padding: 0;
      border: 0;
    }}

    article table {{
      width: 100%;
      border-collapse: collapse;
      margin: 20px 0;
      font-size: 14px;
    }}
    article th, article td {{
      padding: 12px 14px;
      border: 1px solid var(--border);
      text-align: left;
    }}
    article th {{
      background: var(--bg-elevated);
      font-weight: 600;
      color: var(--text);
      font-size: 13px;
    }}
    article td {{ color: var(--text-secondary); }}

    article hr {{
      border: 0;
      border-top: 1px solid var(--border);
      margin: 48px 0;
    }}

    .disclaimer-footer {{
      margin-top: 60px;
      padding: 20px;
      background: var(--bg-elevated);
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.7;
    }}

    footer.site {{
      padding: 40px 0;
      border-top: 1px solid var(--border);
      font-size: 13px;
      color: var(--text-muted);
    }}
    .footer-row {{
      display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px;
    }}
    .footer-links a {{
      color: var(--text-muted);
      margin-left: 16px;
    }}
  </style>
</head>
<body>
  <header class="site">
    <div class="container nav">
      <a href="../" class="brand">
        <span class="brand-mark"></span>
        Phase Detector
        <span class="brand-beta">BETA</span>
      </a>
      <nav class="menu">
        <a href="../#samples">样例</a>
        <a href="../#idea">什么是结构筛选</a>
        <a href="../#waitlist">Waitlist</a>
      </nav>
    </div>
  </header>

  <main>
    <div class="container">
      <div class="breadcrumb">
        <a href="/phase">Phase Detector</a> / <a href="/phase#samples">Day 1 Samples</a> / {ticker}
      </div>
      <div class="ticker-eyebrow">{ticker} · {dynamics_family}</div>
      <article id="content"></article>

      <!-- Cross-linking: 其他 9 份样例 -->
      <aside style="margin-top: 60px; padding: 24px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-elevated);">
        <div style="font-family: var(--mono); font-size: 11px; color: var(--text-muted); letter-spacing: 1px; margin-bottom: 14px;">MORE SAMPLES · 其他公司的结构分析</div>
        <div id="more-samples" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px;"></div>
      </aside>

      <aside style="margin-top: 20px; text-align: center; padding: 18px; background: var(--bg-elevated); border-radius: 10px; border: 1px solid var(--border);">
        <div style="font-size: 14px; margin-bottom: 10px; color: var(--text-secondary);">想按数学动力学筛选全市场？</div>
        <a href="/phase/screener" style="display: inline-block; padding: 10px 24px; background: var(--accent); color: #FFFFFF; border-radius: 6px; font-weight: 600; text-decoration: none;">打开结构筛选器 →</a>
      </aside>
    </div>
  </main>

  <footer class="site">
    <div class="container footer-row">
      <div>© 2026 Phase Detector · Part of Structural Isomorphism Project</div>
      <div class="footer-links">
        <a href="../">主站</a>
        <a href="https://github.com/dada8899/structural-isomorphism">GitHub</a>
      </div>
    </div>
  </footer>

  <script>
    const mdContent = {markdown_js_string};
    const article = document.getElementById('content');
    marked.setOptions({{ breaks: false, gfm: true }});
    article.innerHTML = marked.parse(mdContent);
    document.addEventListener('DOMContentLoaded', () => {{
      if (window.renderMathInElement) {{
        renderMathInElement(article, {{
          delimiters: [
            {{left: '$$', right: '$$', display: true}},
            {{left: '$', right: '$', display: false}},
            {{left: '\\\\[', right: '\\\\]', display: true}},
            {{left: '\\\\(', right: '\\\\)', display: false}},
          ],
        }});
      }}

      // Populate "more samples" list
      const currentSlug = {current_slug_js};
      const allSamples = {all_samples_js};
      const moreContainer = document.getElementById('more-samples');
      if (moreContainer) {{
        moreContainer.innerHTML = allSamples
          .filter(s => s.slug !== currentSlug)
          .map(s => `
            <a href="/phase/samples/${{s.slug}}.html" style="display: block; padding: 12px 14px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); text-decoration: none; color: inherit; transition: all 150ms ease;" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">
              <div style="font-family: var(--mono); font-size: 10px; color: var(--accent); letter-spacing: 0.8px; margin-bottom: 4px;">${{s.ticker}}</div>
              <div style="font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 2px;">${{s.name}}</div>
              <div style="font-family: var(--mono); font-size: 10px; color: var(--text-muted);">${{s.dynamics_family}}</div>
            </a>
          `).join('');
      }}
    }});
  </script>
</body>
</html>
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Day 1 Samples — Phase Detector</title>
  <style>
    body {{ background:#FAFAF9; color:#18181B; font-family:system-ui,sans-serif; max-width:720px; margin:60px auto; padding:0 24px; }}
    h1 {{ font-family:'Noto Serif SC',serif; }}
    a {{ color:#2563EB; display:block; padding:12px 0; text-decoration:none; border-bottom:1px solid #E4E4E7; }}
    a:hover {{ background:#F4F4F5; }}
    .meta {{ color:#71717A; font-size:13px; font-family:'JetBrains Mono',monospace; }}
  </style>
</head>
<body>
  <h1>Day 1 Samples</h1>
  <p style="color:#A1A1AA">10 个跨结构类型的样例报告。点任一查看完整分析。</p>
  {links}
  <p style="margin-top:40px"><a href="../">← 回首页</a></p>
</body>
</html>
"""


def escape_js_string(s: str) -> str:
    """Escape a Python string for embedding in a JS string literal."""
    # Use JSON encoding which produces valid JS string
    return json.dumps(s, ensure_ascii=False)


def build_sample_page(slug: str, manifest_entry: dict, all_manifest: list) -> None:
    md_path = SAMPLES_DIR / f"{slug}.md"
    html_path = SAMPLES_DIR / f"{slug}.html"
    if not md_path.exists():
        print(f"[skip] {slug}: no .md file")
        return
    md_content = md_path.read_text(encoding="utf-8")
    html = HTML_TEMPLATE.format(
        title=manifest_entry.get("name", slug),
        ticker=manifest_entry.get("ticker", ""),
        dynamics_family=manifest_entry.get("dynamics_family", "Unknown"),
        excerpt=manifest_entry.get("excerpt", "")[:160].replace('"', '&quot;'),
        markdown_js_string=escape_js_string(md_content),
        current_slug_js=escape_js_string(slug),
        all_samples_js=json.dumps(all_manifest, ensure_ascii=False),
    )
    html_path.write_text(html, encoding="utf-8")
    print(f"[ok]   {slug}.html ({len(html)//1024}KB)")


def build_index(manifest: list) -> None:
    links = []
    for e in manifest:
        slug = e.get("slug", "")
        name = e.get("name", "")
        ticker = e.get("ticker", "")
        dynamics = e.get("dynamics_family", "")
        links.append(
            f'  <a href="{slug}.html"><div>{name} ({ticker})</div>'
            f'<div class="meta">{dynamics}</div></a>'
        )
    html = INDEX_TEMPLATE.format(links="\n".join(links))
    (SAMPLES_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"[ok]   samples/index.html")


def main():
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    for entry in manifest:
        build_sample_page(entry["slug"], entry, manifest)
    build_index(manifest)
    print(f"\nDone. {len(manifest)} entries in manifest.")


if __name__ == "__main__":
    main()
