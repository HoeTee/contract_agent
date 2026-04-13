import os
import re
import shutil
from dataclasses import dataclass
from docx import Document
import fitz
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.opc.packuri import PackURI
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from datetime import datetime
from lxml import etree

from tools.document.file_cleaner import clean_docx


@dataclass(frozen=True)
class ParagraphAnchor:
    """Resolved contract paragraph that can host a Word comment."""

    paragraph: Paragraph
    path: str
    normalized_text: str


class ReportGenerator:
    """Generates MD, DOCX (with comments on original contract), and PDF reports.

    Pipeline:
    - MD: saved as-is
    - DOCX: original contract + comments (annotations) from review results
    - PDF: Markdown -> HTML -> PDF via xhtml2pdf with optimized CSS
    """

    # CSS for PDF rendering with optimized Chinese support and table layout
    _PDF_CSS = """\
@page {
    size: A4;
    margin: 20mm 15mm 20mm 15mm;
}
body {
    font-family: "ContractSerif", "ContractSans", serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #222;
}
h1 {
    font-family: "ContractSans", sans-serif;
    font-size: 18pt;
    border-bottom: 2px solid #333;
    padding-bottom: 4px;
    margin-top: 20px;
    page-break-after: avoid;
}
h2 {
    font-family: "ContractSans", sans-serif;
    font-size: 15pt;
    border-bottom: 1px solid #aaa;
    padding-bottom: 3px;
    margin-top: 16px;
    page-break-after: avoid;
}
h3 {
    font-family: "ContractSans", sans-serif;
    font-size: 13pt;
    margin-top: 14px;
    page-break-after: avoid;
}
h4 {
    font-family: "ContractSans", sans-serif;
    font-size: 12pt;
    margin-top: 12px;
    page-break-after: avoid;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    table-layout: fixed;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #999;
    padding: 4px 6px;
    text-align: left;
    font-size: 9pt;
    word-wrap: break-word;
    overflow-wrap: break-word;
    word-break: break-all;
}
th {
    background-color: #f0f0f0;
    font-weight: bold;
    font-family: "ContractSans", sans-serif;
}
blockquote {
    border-left: 3px solid #ccc;
    margin: 8px 0;
    padding: 6px 12px;
    color: #444;
    background-color: #f9f9f9;
    font-size: 10pt;
    page-break-inside: avoid;
}
code {
    background-color: #f4f4f4;
    padding: 1px 3px;
    border-radius: 2px;
    font-size: 9pt;
}
pre {
    background-color: #f4f4f4;
    padding: 8px;
    border-radius: 3px;
    overflow-x: auto;
    page-break-inside: avoid;
}
pre code {
    padding: 0;
    background: none;
}
hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 16px 0;
}
ul, ol { padding-left: 20px; }
li { margin-bottom: 3px; font-size: 11pt; }
strong { font-weight: bold; }
em { font-style: italic; }
p { margin: 4px 0; }
"""

    # ==================== DOCX Comment Helpers ====================

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for fuzzy matching: strip whitespace, punctuation variations."""
        if not text:
            return ""
        text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'[\s\u3000]+', '', text)
        text = text.replace('\uff08', '(').replace('\uff09', ')').replace('\uff1a', ':')
        text = text.replace('\uff0c', ',').replace('\u3002', '.').replace('\uff1b', ';')
        return text

    @staticmethod
    def _minimum_match_length(text: str) -> int:
        """Use a lower threshold for CJK text, which is often semantically dense."""
        return 3 if re.search(r'[\u4e00-\u9fff]', text) else 4

    @staticmethod
    def _iter_blocks(parent):
        """Yield Paragraph/Table blocks in document order for a document or cell."""
        if isinstance(parent, DocxDocument):
            parent_element = parent.element.body
        elif isinstance(parent, _Cell):
            parent_element = parent._tc
        else:
            raise TypeError(f"Unsupported block parent: {type(parent)!r}")

        for child in parent_element.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    @staticmethod
    def _collect_paragraph_anchors(parent, path_prefix: str = "") -> list[ParagraphAnchor]:
        """Collect commentable paragraphs from body text and nested table cells."""
        anchors: list[ParagraphAnchor] = []
        seen_elements: set[int] = set()

        for block_index, block in enumerate(ReportGenerator._iter_blocks(parent), start=1):
            if isinstance(block, Paragraph):
                block_text = block.text.strip()
                normalized_text = ReportGenerator._normalize_text(block_text)
                element_id = id(block._element)
                if not normalized_text or element_id in seen_elements:
                    continue
                seen_elements.add(element_id)
                anchors.append(
                    ParagraphAnchor(
                        paragraph=block,
                        path=f"{path_prefix}p{block_index}",
                        normalized_text=normalized_text,
                    )
                )
                continue

            table_path = f"{path_prefix}tbl{block_index}/"
            for row_index, row in enumerate(block.rows, start=1):
                for cell_index, cell in enumerate(row.cells, start=1):
                    anchors.extend(
                        ReportGenerator._collect_paragraph_anchors(
                            cell,
                            path_prefix=f"{table_path}r{row_index}c{cell_index}/",
                        )
                    )

        return anchors

    @staticmethod
    def _score_anchor_match(
        normalized_reference: str,
        anchor: ParagraphAnchor,
        next_anchor: ParagraphAnchor | None = None,
    ) -> int:
        """Return a simple relevance score for a reference-to-anchor match."""
        score = 0
        anchor_text = anchor.normalized_text

        if normalized_reference in anchor_text or anchor_text in normalized_reference:
            score = max(score, 100 + min(len(normalized_reference), len(anchor_text)))

        prefix_length = min(20, len(normalized_reference), len(anchor_text))
        if prefix_length >= 8 and normalized_reference[:prefix_length] == anchor_text[:prefix_length]:
            score = max(score, 60 + prefix_length)

        if next_anchor is None:
            return score

        combined_text = anchor_text + next_anchor.normalized_text
        if normalized_reference in combined_text:
            score = max(score, 90 + min(len(normalized_reference), len(combined_text)))

        combined_prefix = min(30, len(normalized_reference), len(combined_text))
        if combined_prefix >= 12 and normalized_reference[:combined_prefix] == combined_text[:combined_prefix]:
            score = max(score, 50 + combined_prefix)

        return score

    @staticmethod
    def _find_matching_anchor(doc: Document, reference_text: str) -> ParagraphAnchor | None:
        """Find the best matching contract paragraph for a quoted reference."""
        if not reference_text or not reference_text.strip():
            return None

        clean_ref = re.sub(r'^>\s*', '', reference_text, flags=re.MULTILINE)
        ref_lines = [l.strip() for l in clean_ref.split('\n') if l.strip()]

        if not ref_lines:
            return None

        anchors = ReportGenerator._collect_paragraph_anchors(doc)
        best_anchor: ParagraphAnchor | None = None
        best_score = 0

        for index, anchor in enumerate(anchors):
            next_anchor = anchors[index + 1] if index + 1 < len(anchors) else None
            for ref_line in ref_lines:
                normalized_reference = ReportGenerator._normalize_text(ref_line)
                if not normalized_reference:
                    continue
                if len(normalized_reference) < ReportGenerator._minimum_match_length(normalized_reference):
                    continue
                score = ReportGenerator._score_anchor_match(
                    normalized_reference,
                    anchor,
                    next_anchor,
                )
                if score > best_score:
                    best_anchor = anchor
                    best_score = score

        return best_anchor

    @staticmethod
    def _add_comments_to_doc(doc: Document, comments_data: list) -> Document:
        """Add Word comments to a document using OPC XML manipulation."""
        comments_part = None
        for rel in doc.part.rels.values():
            if "comments" in rel.reltype:
                comments_part = rel.target_part
                break

        if comments_part is None:
            from docx.opc.part import Part

            comments_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
                ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '</w:comments>'
            )
            comments_part = Part(
                # python-docx expects OPC part names as PackURI objects; a raw
                # string breaks package traversal during doc.save().
                partname=PackURI("/word/comments.xml"),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
                blob=comments_xml.encode('utf-8'),
                package=doc.part.package,
            )
            doc.part.relate_to(comments_part, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments")

        comments_element = etree.fromstring(comments_part.blob)
        comment_id = 0
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        for cdata in comments_data:
            anchor = cdata.get('anchor')
            comment_text = cdata.get('comment_text', '')
            author = cdata.get('author', 'AI审查助手')

            if anchor is None or not comment_text:
                continue

            comment_el = etree.SubElement(comments_element, qn('w:comment'))
            comment_el.set(qn('w:id'), str(comment_id))
            comment_el.set(qn('w:author'), author)
            comment_el.set(qn('w:date'), now_str + "Z")

            comment_lines = comment_text.split('\n')
            for line in comment_lines:
                line = line.strip()
                if not line:
                    continue
                p_el = etree.SubElement(comment_el, qn('w:p'))
                r_el = etree.SubElement(p_el, qn('w:r'))
                t_el = etree.SubElement(r_el, qn('w:t'))
                t_el.set(qn('xml:space'), 'preserve')
                t_el.text = line

            para_element = anchor.paragraph._element

            range_start = OxmlElement('w:commentRangeStart')
            range_start.set(qn('w:id'), str(comment_id))
            para_element.insert(0, range_start)

            range_end = OxmlElement('w:commentRangeEnd')
            range_end.set(qn('w:id'), str(comment_id))
            para_element.append(range_end)

            ref_run = OxmlElement('w:r')
            ref_rpr = OxmlElement('w:rPr')
            ref_style = OxmlElement('w:rStyle')
            ref_style.set(qn('w:val'), 'CommentReference')
            ref_rpr.append(ref_style)
            ref_run.append(ref_rpr)
            ref_mark = OxmlElement('w:commentReference')
            ref_mark.set(qn('w:id'), str(comment_id))
            ref_run.append(ref_mark)
            para_element.append(ref_run)

            comment_id += 1

        comments_part._blob = etree.tostring(comments_element, xml_declaration=True, encoding='UTF-8', standalone=True)

        return doc

    @staticmethod
    def _parse_review_output(review_output: str) -> dict:
        """Parse a sub-agent's review_output markdown into structured fields."""
        fields = {}
        current_field = None
        current_content = []

        for line in review_output.split('\n'):
            m = re.match(r'^-\s*\*\*(.+?)\*\*\s*[：:]\s*(.*)', line)
            if m:
                if current_field:
                    fields[current_field] = '\n'.join(current_content).strip()
                current_field = m.group(1).strip()
                first_val = m.group(2).strip()
                current_content = [first_val] if first_val else []
            elif current_field:
                current_content.append(line)

        if current_field:
            fields[current_field] = '\n'.join(current_content).strip()

        return fields

    @staticmethod
    def _build_comment_text(parsed: dict) -> str:
        """Build comment text from parsed review fields."""
        parts = []

        risk = parsed.get('风险等级', '').strip()
        if risk:
            parts.append(f"【风险等级：{risk}】")

        conclusion = parsed.get('审查结论', '').strip()
        if conclusion:
            parts.append(f"审查结论：{conclusion}")

        analysis = parsed.get('问题分析', '').strip()
        if analysis:
            parts.append(f"问题分析：{analysis}")

        suggestion = parsed.get('修改建议', '').strip()
        if suggestion:
            suggestion = re.sub(r'^>\s*', '', suggestion, flags=re.MULTILINE)
            parts.append(f"修改建议：{suggestion}")

        return '\n'.join(parts)

    @staticmethod
    def _generate_standard_docx_report(content: str, output_path: str) -> str | None:
        """Generate the standard DOCX report from markdown content."""
        try:
            from htmldocx import HtmlToDocx

            html_body = ReportGenerator._markdown_to_html(content)
            full_html = f"<html><body>{html_body}</body></html>"
            doc = Document()
            parser = HtmlToDocx()
            parser.add_html_to_document(full_html, doc)
            doc.save(output_path)
            return output_path
        except Exception as e:
            print(f"  WARNING: DOCX generation failed: {e}")
            return None

    @staticmethod
    def _can_generate_annotated_docx(contract_path: str | None, results: list | None) -> bool:
        """Return whether the original contract can be used for annotated DOCX export."""
        return bool(
            contract_path
            and results
            and os.path.exists(contract_path)
            and contract_path.lower().endswith(".docx")
        )

    @staticmethod
    def _generate_docx_with_comments(
        contract_path: str,
        results: list,
        output_path: str,
    ) -> str:
        """Generate the annotated DOCX report using the cleaned contract as the base."""

        cleaned_contract_path = None
        try:
            cleaned_contract_path = clean_docx(contract_path)
            shutil.copy2(cleaned_contract_path, output_path)
            doc = Document(output_path)

            comments_data = []
            unmatched_comments = []

            for result in results:
                review_output = result.get('review_output', '').strip()
                if not review_output:
                    continue

                criterion = result.get('criterion', '')
                cid = result.get('criterion_id', '')

                # The export path may receive raw sub-agent output (`###`) or
                # formatter output (`####`), so accept both heading levels.
                sections = re.split(r'(?=^#{3,4}\s)', review_output, flags=re.MULTILINE)

                for section in sections:
                    section = section.strip()
                    if not section:
                        continue

                    parsed = ReportGenerator._parse_review_output(section)
                    reference = parsed.get('原文引用', '')
                    comment_text = ReportGenerator._build_comment_text(parsed)

                    if not comment_text:
                        continue

                    title_match = re.match(r'^#{3,4}\s*(.+)', section)
                    check_title = title_match.group(1).strip() if title_match else criterion
                    comment_text = f"[{check_title}]\n{comment_text}"

                    matched_anchor = ReportGenerator._find_matching_anchor(doc, reference)

                    if matched_anchor:
                        comments_data.append({
                            'anchor': matched_anchor,
                            'comment_text': comment_text,
                            'author': 'AI审查助手',
                        })
                    else:
                        unmatched_comments.append({
                            'criterion_id': cid,
                            'criterion': criterion,
                            'comment_text': comment_text,
                            'reference_text': reference,
                            'author': 'AI审查助手',
                        })

            if comments_data:
                ReportGenerator._add_comments_to_doc(doc, comments_data)

            doc.save(output_path)
            matched_count = len(comments_data)
            skipped_count = len(unmatched_comments)
            print(f"  DOCX: {matched_count} comments anchored, {skipped_count} skipped (no reliable contract match)")
            return output_path

        except Exception as e:
            print(f"  WARNING: DOCX comment generation failed: {e}")
            import traceback
            traceback.print_exc()
            if os.path.exists(output_path):
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
            return None
        finally:
            if cleaned_contract_path and cleaned_contract_path != contract_path and os.path.exists(cleaned_contract_path):
                try:
                    os.unlink(cleaned_contract_path)
                except OSError:
                    pass

    # ==================== PDF Generation ====================

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
    def _wrap_html_for_pdf(html_body: str) -> str:
        """Wrap an HTML body fragment in a full HTML document with PDF-optimized CSS."""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<style>
{ReportGenerator._PDF_CSS}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

    @staticmethod
    def _build_pdf_font_css() -> tuple[str, fitz.Archive]:
        """Build CSS and a font archive for Chinese-capable PDF rendering."""
        font_dir = r"C:\Windows\Fonts"
        archive = fitz.Archive(font_dir)
        font_candidates = [
            ("ContractSans", "simhei.ttf"),
            ("ContractSerif", "simfang.ttf"),
            ("ContractSerif", "simhei.ttf"),
        ]
        css_rules = []
        seen = set()
        for family, filename in font_candidates:
            font_path = os.path.join(font_dir, filename)
            if not os.path.exists(font_path):
                continue
            key = (family, filename)
            if key in seen:
                continue
            seen.add(key)
            css_rules.append(
                f'@font-face {{ font-family: "{family}"; src: url("{filename}"); }}'
            )
        return "\n".join(css_rules), archive

    @staticmethod
    def _render_pdf_with_pymupdf(html_body: str, output_path: str) -> str:
        """Render report HTML to a paginated PDF with Chinese font support."""
        font_css, archive = ReportGenerator._build_pdf_font_css()
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<style>
{font_css}
{ReportGenerator._PDF_CSS}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
        story = fitz.Story(html=html, archive=archive)
        writer = fitz.DocumentWriter(output_path)
        page_rect = fitz.paper_rect("a4")
        content_rect = fitz.Rect(page_rect.x0 + 42, page_rect.y0 + 48, page_rect.x1 - 42, page_rect.y1 - 48)

        def rect_fn(page_num: int, _filled: fitz.Rect):
            return page_rect, content_rect, fitz.Matrix(1, 1)

        try:
            story.write(writer, rect_fn)
        finally:
            writer.close()
        return output_path

    # ==================== Main Report Generator ====================

    @staticmethod
    def generate_report(
        content: str,
        contract_name: str,
        elapsed_seconds: float = None,
        contract_path: str = None,
        results: list = None,
    ) -> dict:
        """Generate MD, DOCX, and PDF reports from markdown content."""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        md_dir = os.path.join(project_root, "docs", "reports_md")
        docx_dir = os.path.join(project_root, "docs", "reports_docx")
        pdf_dir = os.path.join(project_root, "docs", "reports_pdf")
        for d in (md_dir, docx_dir, pdf_dir):
            os.makedirs(d, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"审查报告_{contract_name}_{timestamp}"

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

        # 2. Generate DOCX report.
        # When the source contract is a DOCX, produce an annotated copy with
        # inline review comments.  Otherwise (PDF / other), fall back to a
        # standard report DOCX generated from the markdown content.
        docx_output_path = os.path.join(docx_dir, f"{base_name}.docx")
        if ReportGenerator._can_generate_annotated_docx(contract_path, results):
            docx_path = ReportGenerator._generate_docx_with_comments(
                contract_path, results, docx_output_path
            )
            if not docx_path:
                print("  DOCX: annotated export failed, falling back to standard report DOCX.")
                docx_path = ReportGenerator._generate_standard_docx_report(content, docx_output_path)
        else:
            docx_path = ReportGenerator._generate_standard_docx_report(content, docx_output_path)

        # 3. Generate the report PDF with a Chinese-capable HTML renderer.
        html_body = ReportGenerator._markdown_to_html(content)
        pdf_path = os.path.join(pdf_dir, f"{base_name}.pdf")
        try:
            ReportGenerator._render_pdf_with_pymupdf(html_body, pdf_path)
        except Exception as e:
            print(f"  WARNING: PDF generation failed: {e}")
            pdf_path = None

        return {
            "md": os.path.abspath(md_path),
            "docx": os.path.abspath(docx_path) if docx_path else None,
            "pdf": os.path.abspath(pdf_path) if pdf_path else None,
        }
