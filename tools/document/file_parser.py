import os
import tempfile
import zipfile
from docx import Document
from pypdf import PdfReader
from lxml import etree
from tools.clean_docx import DocxCleaner


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
                clean_path = FileParser._clean_docx(file_path)
                try:
                    return FileParser._parse_docx(clean_path)
                finally:
                    if clean_path != file_path and os.path.exists(clean_path):
                        os.unlink(clean_path)
            elif ext == '.pdf':
                return FileParser._parse_pdf(file_path)
            elif ext == '.txt':
                return FileParser._parse_txt(file_path)
            else:
                return f"Error: Unsupported file format {ext}"
        except Exception as e:
            return f"Error parsing file: {str(e)}"

    @staticmethod
    def _clean_docx(path: str) -> str:
        cleaner = DocxCleaner(input_path=path)
        return cleaner.clean()

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
