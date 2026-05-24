"""Generate academic PDF from Markdown paper using WeasyPrint."""
import re
from pathlib import Path

try:
    import markdown_it
except ImportError:
    import subprocess
    subprocess.check_call(['pip3', 'install', 'markdown-it-py[plugins]', '--quiet'])
    import markdown_it

from weasyprint import HTML

PAPER_DIR = Path(__file__).parent
FIGURES_DIR = PAPER_DIR / 'figures'

# Academic CSS
CSS = """
@page {
    size: A4;
    margin: 2.5cm 2cm;
    @bottom-center { content: counter(page); font-size: 10px; color: #666; }
}

body {
    font-family: "Times New Roman", "Noto Serif", "SimSun", serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #1a1a1a;
    max-width: 100%;
}

h1 {
    font-size: 18pt;
    text-align: center;
    margin-bottom: 8px;
    line-height: 1.3;
}

h1 + p, h1 + blockquote {
    text-align: center;
    font-style: italic;
    color: #555;
}

h2 {
    font-size: 14pt;
    margin-top: 24px;
    margin-bottom: 8px;
    border-bottom: 1px solid #ddd;
    padding-bottom: 4px;
}

h3 {
    font-size: 12pt;
    margin-top: 18px;
    margin-bottom: 6px;
}

p {
    text-align: justify;
    margin-bottom: 8px;
    text-indent: 0;
}

blockquote {
    border-left: 3px solid #2563eb;
    padding: 8px 16px;
    margin: 12px 0;
    background: #f8f9ff;
    font-style: italic;
}

blockquote p { text-indent: 0; margin: 4px 0; }

table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 10pt;
}

th, td {
    border: 1px solid #ccc;
    padding: 6px 10px;
    text-align: left;
}

th {
    background: #f5f5f5;
    font-weight: bold;
}

code {
    font-family: "Courier New", monospace;
    font-size: 9.5pt;
    background: #f4f4f4;
    padding: 1px 4px;
    border-radius: 2px;
}

pre {
    background: #f8f8f8;
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 9pt;
    line-height: 1.4;
    margin: 10px 0;
}

pre code {
    background: none;
    padding: 0;
}

img {
    max-width: 100%;
    display: block;
    margin: 12px auto;
}

strong { font-weight: bold; }
em { font-style: italic; }

.figure-caption {
    text-align: center;
    font-size: 10pt;
    color: #555;
    margin-top: -8px;
    margin-bottom: 16px;
}
"""

def convert_paper(input_file, output_file, css=CSS):
    """Convert Markdown paper to PDF."""
    print(f"Reading {input_file}...")
    md_text = input_file.read_text(encoding='utf-8')

    # Strip YAML frontmatter if present
    if md_text.startswith('---'):
        end = md_text.index('---', 3)
        md_text = md_text[end+3:].strip()

    # Convert figure references to actual image paths
    md_text = md_text.replace('[Figure ', '[Figure ')

    # Render Markdown to HTML
    md = markdown_it.MarkdownIt('commonmark', {'html': True})
    md.enable('table')
    html_body = md.render(md_text)

    # Wrap in full HTML
    html_full = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    print(f"Generating PDF: {output_file}...")
    HTML(string=html_full, base_url=str(PAPER_DIR)).write_pdf(str(output_file))
    print(f"Done! {output_file} ({output_file.stat().st_size / 1024:.0f} KB)")

if __name__ == '__main__':
    # English paper
    en_input = PAPER_DIR / 'paper.md'
    en_output = PAPER_DIR / 'paper-en.pdf'
    if en_input.exists():
        convert_paper(en_input, en_output)

    # Chinese paper (if exists)
    zh_input = PAPER_DIR / 'paper-zh.md'
    zh_output = PAPER_DIR / 'paper-zh.pdf'
    if zh_input.exists():
        # Use different CSS for Chinese
        zh_css = CSS.replace(
            '"Times New Roman", "Noto Serif", "SimSun", serif',
            '"PingFang SC", "Noto Sans CJK SC", "SimSun", "Times New Roman", serif'
        )
        convert_paper(zh_input, zh_output, css=zh_css)
    else:
        print("Chinese paper not ready yet, skipping...")
