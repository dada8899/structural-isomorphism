"""Generate academic PDF using fpdf2 (pure Python, no system deps)."""
import re
from pathlib import Path
from fpdf import FPDF

PAPER_DIR = Path(__file__).parent
FIGURES_DIR = PAPER_DIR / 'figures'

class AcademicPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        if self.page_no() > 1:
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, 'Beyond Semantic Similarity: Cross-Domain Structural Isomorphism Detection', align='C')
            self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, str(self.page_no()), align='C')

    def chapter_title(self, title, level=1):
        if level == 1:
            self.set_font('Helvetica', 'B', 16)
            self.ln(8)
        elif level == 2:
            self.set_font('Helvetica', 'B', 13)
            self.ln(6)
        else:
            self.set_font('Helvetica', 'B', 11)
            self.ln(4)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 7 if level == 1 else 6, title)
        self.ln(3)

    def body_text(self, text):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(26, 26, 26)
        # Handle bold and italic
        self.multi_cell(0, 5, text)
        self.ln(2)

    def add_figure(self, img_path, caption=''):
        if img_path.exists():
            # Fit image to page width with margins
            self.image(str(img_path), x=25, w=160)
            if caption:
                self.set_font('Helvetica', 'I', 9)
                self.set_text_color(100, 100, 100)
                self.multi_cell(0, 4, caption, align='C')
            self.ln(4)

    def add_table_row(self, cells, header=False):
        self.set_font('Helvetica', 'B' if header else '', 9)
        col_width = (self.w - 40) / len(cells)
        for cell in cells:
            self.cell(col_width, 6, str(cell)[:40], border=1, align='C' if header else 'L')
        self.ln()

def parse_markdown(md_text):
    """Parse markdown into structured blocks."""
    blocks = []
    lines = md_text.split('\n')
    current_para = []

    for line in lines:
        # Headers
        if line.startswith('# ') and not line.startswith('## '):
            if current_para:
                blocks.append(('para', ' '.join(current_para)))
                current_para = []
            blocks.append(('h1', line[2:].strip()))
        elif line.startswith('## '):
            if current_para:
                blocks.append(('para', ' '.join(current_para)))
                current_para = []
            blocks.append(('h2', line[3:].strip()))
        elif line.startswith('### '):
            if current_para:
                blocks.append(('para', ' '.join(current_para)))
                current_para = []
            blocks.append(('h3', line[4:].strip()))
        elif line.startswith('> '):
            if current_para:
                blocks.append(('para', ' '.join(current_para)))
                current_para = []
            blocks.append(('quote', line[2:].strip()))
        elif line.startswith('| '):
            if current_para:
                blocks.append(('para', ' '.join(current_para)))
                current_para = []
            # Parse table row
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if not all(c.replace('-', '').replace(':', '') == '' for c in cells):
                blocks.append(('table_row', cells))
        elif line.strip() == '':
            if current_para:
                blocks.append(('para', ' '.join(current_para)))
                current_para = []
        elif line.startswith('---') and len(line.strip()) <= 5:
            if current_para:
                blocks.append(('para', ' '.join(current_para)))
                current_para = []
        else:
            # Clean markdown formatting for plain text
            clean = line.strip()
            clean = re.sub(r'\*\*(.*?)\*\*', r'\1', clean)
            clean = re.sub(r'\*(.*?)\*', r'\1', clean)
            clean = re.sub(r'`(.*?)`', r'\1', clean)
            clean = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', clean)
            current_para.append(clean)

    if current_para:
        blocks.append(('para', ' '.join(current_para)))

    return blocks

def generate_pdf(md_file, output_file, is_chinese=False):
    """Generate PDF from markdown file."""
    print(f"Reading {md_file}...")
    md_text = md_file.read_text(encoding='utf-8')

    # Strip YAML frontmatter
    if md_text.startswith('---'):
        end = md_text.index('---', 3)
        md_text = md_text[end+3:].strip()

    blocks = parse_markdown(md_text)

    pdf = AcademicPDF()
    pdf.add_page()

    # For Chinese, we'd need a Unicode font - skip for now, use English
    in_table = False

    for btype, content in blocks:
        if btype == 'h1':
            pdf.chapter_title(content, 1)
        elif btype == 'h2':
            pdf.chapter_title(content, 2)
        elif btype == 'h3':
            pdf.chapter_title(content, 3)
        elif btype == 'quote':
            pdf.set_font('Helvetica', 'I', 10)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(0, 5, '  ' + content)
            pdf.ln(2)
        elif btype == 'table_row':
            pdf.add_table_row(content, header=not in_table)
            in_table = True
        elif btype == 'para':
            in_table = False
            # Check for figure references
            if '[Figure' in content or 'fig' in content.lower():
                # Try to find and insert figure
                for fig in FIGURES_DIR.glob('*.png'):
                    if fig.stem.split('_')[0] in content.lower():
                        pdf.add_figure(fig)
                        break
            pdf.body_text(content)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_file))
    print(f"Done! {output_file} ({output_file.stat().st_size / 1024:.0f} KB)")

if __name__ == '__main__':
    # English PDF
    en_input = PAPER_DIR / 'paper.md'
    en_output = PAPER_DIR / 'paper-en.pdf'
    generate_pdf(en_input, en_output)
