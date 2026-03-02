import os
from docx import Document
from pypdf import PdfReader
from datetime import datetime


class FileParser:
    """Parses DOCX, PDF, and TXT files into text chunks."""
    
    @staticmethod
    def parse_file(file_path: str) -> str:
        """Determines file type and extracts text."""
        ext = os.path.splitext(file_path)[1].lower()
        
        if not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"
            
        try:
            if ext == '.docx':
                return FileParser._parse_docx(file_path)
            elif ext == '.pdf':
                return FileParser._parse_pdf(file_path)
            elif ext == '.txt':
                return FileParser._parse_txt(file_path)
            else:
                return f"Error: Unsupported file format {ext}"
        except Exception as e:
            return f"Error parsing file: {str(e)}"

    @staticmethod
    def _parse_docx(path: str) -> str:
        doc = Document(path)
        preamble = []   # Content before the first heading
        full_text = []
        found_first_heading = False
        first_heading_level = 1  # Default if no headings found
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            # Convert DOCX heading styles to markdown
            style = para.style.name if para.style else ""
            if style.startswith("Heading"):
                try:
                    level = int(style.split()[-1])
                    level = min(level, 6)
                except (ValueError, IndexError):
                    level = 1
                if not found_first_heading:
                    first_heading_level = level
                    if preamble:
                        # Use same level as first heading so preamble is a sibling
                        full_text.append(f"{'#' * level} 合同首部信息")
                        full_text.extend(preamble)
                    found_first_heading = True
                full_text.append(f"{'#' * level} {text}")
            else:
                if found_first_heading:
                    full_text.append(text)
                else:
                    preamble.append(text)
        # If the document has no headings at all, emit preamble under a single heading
        if not found_first_heading and preamble:
            full_text.append("# 合同首部信息")
            full_text.extend(preamble)
        return "\n\n".join(full_text)

    @staticmethod
    def _parse_pdf(path: str) -> str:
        reader = PdfReader(path)
        full_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
        return "\n".join(full_text)

    @staticmethod
    def _parse_txt(path: str) -> str:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()


class ReportGenerator:
    """Generates MD, DOCX, and PDF reports from markdown content.
    
    Pipeline: Markdown → HTML → DOCX / PDF
    The MD file is saved as-is. DOCX and PDF are generated from the same
    intermediate HTML so all three formats render identically.
    """

    # Base CSS that mimics typical markdown preview styling
    _CSS_TEMPLATE = """\
body {{
    font-family: {font_family};
    font-size: 12pt;
    line-height: 1.8;
    color: #333;
    max-width: 210mm;
    margin: 0 auto;
    padding: 20px 30px;
}}
h1 {{ font-size: 22pt; border-bottom: 2px solid #333; padding-bottom: 6px; margin-top: 24px; }}
h2 {{ font-size: 18pt; border-bottom: 1px solid #aaa; padding-bottom: 4px; margin-top: 20px; }}
h3 {{ font-size: 15pt; margin-top: 16px; }}
h4 {{ font-size: 13pt; margin-top: 14px; }}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
}}
th, td {{
    border: 1px solid #999;
    padding: 6px 10px;
    text-align: left;
}}
th {{ background-color: #f0f0f0; font-weight: bold; }}
blockquote {{
    border-left: 4px solid #ccc;
    margin: 10px 0;
    padding: 8px 16px;
    color: #555;
    background-color: #f9f9f9;
}}
code {{
    background-color: #f4f4f4;
    padding: 2px 4px;
    border-radius: 3px;
    font-size: 11pt;
}}
pre {{
    background-color: #f4f4f4;
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
}}
pre code {{
    padding: 0;
    background: none;
}}
hr {{
    border: none;
    border-top: 1px solid #ccc;
    margin: 20px 0;
}}
ul, ol {{ padding-left: 24px; }}
li {{ margin-bottom: 4px; }}
strong {{ font-weight: bold; }}
em {{ font-style: italic; }}
"""

    # Font families for each output target
    _DOCX_FONTS = '"SimHei", "SimSun", "Microsoft YaHei", "Arial", sans-serif'
    # STSong-Light is a CID font built into reportlab (used by xhtml2pdf)
    _PDF_FONTS = '"STSong-Light", "SimHei", "SimSun", sans-serif'

    @staticmethod
    def _markdown_to_html(md_content: str) -> str:
        """Convert markdown text to an HTML body fragment."""
        import markdown
        extensions = [
            'tables',
            'fenced_code',
            'codehilite',
            'toc',
            'nl2br',
            'sane_lists',
        ]
        extension_configs = {
            'codehilite': {'css_class': 'highlight', 'guess_lang': False},
        }
        html_body = markdown.markdown(
            md_content,
            extensions=extensions,
            extension_configs=extension_configs,
        )
        return html_body

    @staticmethod
    def _wrap_html(html_body: str, for_pdf: bool = False) -> str:
        """Wrap an HTML body fragment in a full HTML document with CSS.
        
        Args:
            html_body: The HTML body content.
            for_pdf: If True, use CID fonts for Chinese PDF rendering.
        """
        fonts = ReportGenerator._PDF_FONTS if for_pdf else ReportGenerator._DOCX_FONTS
        css = ReportGenerator._CSS_TEMPLATE.format(font_family=fonts)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<style>
{css}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

    @staticmethod
    def generate_report(
        content: str,
        contract_name: str,
        elapsed_seconds: float = None,
    ) -> dict:
        """
        Generate MD, DOCX, and PDF reports from markdown content.

        Each format is saved in its own folder under docs/:
          - docs/reports_md/
          - docs/reports_docx/
          - docs/reports_pdf/

        Args:
            content: The report body in markdown format.
            contract_name: Name of the contract (used in filenames).
            elapsed_seconds: Total workflow elapsed time in seconds (optional).

        Returns:
            dict with keys 'md', 'docx', 'pdf' mapping to absolute file paths.
        """
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Separate output directories for each format
        md_dir = os.path.join(project_root, "docs", "reports_md")
        docx_dir = os.path.join(project_root, "docs", "reports_docx")
        pdf_dir = os.path.join(project_root, "docs", "reports_pdf")
        for d in (md_dir, docx_dir, pdf_dir):
            os.makedirs(d, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"审查报告_{contract_name}_{timestamp}"

        # Append elapsed time info to the content if provided
        if elapsed_seconds is not None:
            mins, secs = divmod(int(elapsed_seconds), 60)
            time_info = (
                f"\n\n---\n\n"
                f"## 附：报告生成信息\n\n"
                f"- **总耗时**: {mins}m {secs}s\n"
                f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            )
            content += time_info

        # 1. Save MD
        md_path = os.path.join(md_dir, f"{base_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 2. Convert markdown → HTML
        html_body = ReportGenerator._markdown_to_html(content)
        full_html = ReportGenerator._wrap_html(html_body)

        # 3. Generate DOCX from HTML
        docx_path = os.path.join(docx_dir, f"{base_name}.docx")
        try:
            from htmldocx import HtmlToDocx
            doc = Document()
            parser = HtmlToDocx()
            parser.add_html_to_document(full_html, doc)
            doc.save(docx_path)
        except Exception as e:
            print(f"  WARNING: DOCX generation failed: {e}")
            docx_path = None

        # 4. Generate PDF from HTML (with CID font for Chinese)
        pdf_html = ReportGenerator._wrap_html(html_body, for_pdf=True)
        pdf_path = os.path.join(pdf_dir, f"{base_name}.pdf")
        try:
            from xhtml2pdf import pisa
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            # Register Chinese CID font (built into reportlab, no file needed)
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
            with open(pdf_path, "wb") as pdf_file:
                pisa_status = pisa.CreatePDF(pdf_html, dest=pdf_file)
                if pisa_status.err:
                    print(f"  WARNING: PDF generation had errors (code {pisa_status.err})")
                    pdf_path = None
        except Exception as e:
            print(f"  WARNING: PDF generation failed: {e}")
            pdf_path = None

        return {
            "md": os.path.abspath(md_path),
            "docx": os.path.abspath(docx_path) if docx_path else None,
            "pdf": os.path.abspath(pdf_path) if pdf_path else None,
        }
