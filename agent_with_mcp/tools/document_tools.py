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
    """Generates a formal DOCX report from structured data."""
    
    @staticmethod
    def generate_report(
        content: str, 
        contract_name: str, 
        output_dir: str = None
        ) -> str:
        """
        Creates a DOCX report with standard formatting.
        
        Args:
            content: The body text of the report (expecting markdown-like structure or plain text).
            contract_name: Name of the contract for the filename.
            output_dir: Directory to save the report.
            
        Returns:
            Absolute path to the generated report.
        """
        if output_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(project_root, "docs", "reports")
        output_dir = os.path.abspath(output_dir)
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"独立审查报告_{contract_name}_{timestamp}.docx"
        output_path = os.path.join(output_dir, filename)
        
        doc = Document()
        
        # Header
        header = doc.sections[0].header
        paragraph = header.paragraphs[0]
        paragraph.text = "独立法律审查报告 | Independent Legal Review Report"
        paragraph.style.font.name = 'SimHei'  # Optional font setting
        
        # Title
        title = doc.add_heading('独立合同审查报告', 0)
        title.alignment = 1  # Center
        
        doc.add_paragraph(f"审查对象: {contract_name}")
        doc.add_paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        doc.add_paragraph("-" * 30)
        
        # Body Content processing
        # Simple parser to handle headers in the content string
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('# '):
                doc.add_heading(line[2:], level=1)
            elif line.startswith('## '):
                doc.add_heading(line[3:], level=2)
            elif line.startswith('### '):
                doc.add_heading(line[4:], level=3)
            elif line.startswith('- ') or line.startswith('* '):
                doc.add_paragraph(line[2:], style='List Bullet')
            else:
                doc.add_paragraph(line)
        
        # Footer branding
        section = doc.sections[0]
        footer = section.footer
        p = footer.paragraphs[0]
        p.text = "本报告由 AI 法律顾问系统生成，仅供参考，不构成正式法律意见。"
        
        doc.save(output_path)
        return os.path.abspath(output_path)
