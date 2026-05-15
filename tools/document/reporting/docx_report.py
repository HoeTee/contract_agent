import os
import re
import shutil
import sys
from dataclasses import dataclass
from docx import Document
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


SUMMARY_COMMENT_AUTHOR = "AI审查总结"
REVIEW_COMMENT_AUTHOR = "AI条款审查"


@dataclass(frozen=True)
class ParagraphAnchor:
    """Resolved contract paragraph that can host a Word comment."""

    paragraph: Paragraph
    path: str
    normalized_text: str


class DocxReportGenerator:
    """Generates DOCX reports, including annotated copies of original contracts."""

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

        for block_index, block in enumerate(DocxReportGenerator._iter_blocks(parent), start=1):
            if isinstance(block, Paragraph):
                block_text = block.text.strip()
                normalized_text = DocxReportGenerator._normalize_text(block_text)
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
                        DocxReportGenerator._collect_paragraph_anchors(
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

        anchors = DocxReportGenerator._collect_paragraph_anchors(doc)
        best_anchor: ParagraphAnchor | None = None
        best_score = 0

        for index, anchor in enumerate(anchors):
            next_anchor = anchors[index + 1] if index + 1 < len(anchors) else None
            for ref_line in ref_lines:
                normalized_reference = DocxReportGenerator._normalize_text(ref_line)
                if not normalized_reference:
                    continue
                if len(normalized_reference) < DocxReportGenerator._minimum_match_length(normalized_reference):
                    continue
                score = DocxReportGenerator._score_anchor_match(
                    normalized_reference,
                    anchor,
                    next_anchor,
                )
                if score > best_score:
                    best_anchor = anchor
                    best_score = score

        return best_anchor

    @staticmethod
    def _get_document_start_anchor(doc: Document) -> ParagraphAnchor | None:
        """Return the first non-empty body paragraph that can host fallback comments."""
        anchors = DocxReportGenerator._collect_paragraph_anchors(doc)
        return anchors[0] if anchors else None

    @staticmethod
    def _build_unmatched_comment_text(unmatched_comments: list[dict]) -> str:
        """Build one document-start comment for issues without a reliable anchor."""
        lines = ["当前合同缺失部分内容，具体如下："]
        number = 1

        for item in unmatched_comments:
            text = item.get("comment_text", "").strip()
            if not text:
                continue
            lines.append(f"{number}. {text}")
            number += 1

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _build_summary_comment_text(summary_sections: dict | None) -> str:
        """Build the document-start summary comment from summarizer output."""
        if not summary_sections:
            return ""

        lines: list[str] = []
        overall_comment = str(summary_sections.get("overall_comment", "")).strip()
        priority_comments = summary_sections.get("priority_comments", [])

        if overall_comment:
            lines.append("总体审查总结：")
            lines.append(overall_comment)

        valid_priority_comments = [
            item.strip()
            for item in priority_comments
            if isinstance(item, str) and item.strip()
        ]
        if valid_priority_comments:
            if lines:
                lines.append("")
            lines.append("优先修改建议：")
            for index, item in enumerate(valid_priority_comments, start=1):
                lines.append(f"{index}. {item}")

        return "\n".join(lines)

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
    def _generate_standard_docx_report(content: str, output_path: str) -> str | None:
        """Generate the standard DOCX report from markdown content."""
        try:
            from htmldocx import HtmlToDocx

            html_body = DocxReportGenerator._markdown_to_html(content)
            full_html = f"<html><body>{html_body}</body></html>"
            doc = Document()
            parser = HtmlToDocx()
            parser.add_html_to_document(full_html, doc)
            doc.save(output_path)
            return output_path
        except Exception as e:
            print(f"  WARNING: DOCX generation failed: {e}", file=sys.stderr)
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
        summary_sections: dict | None = None,
    ) -> str:
        """Generate the annotated DOCX report using the cleaned contract as the base."""

        cleaned_contract_path = None
        try:
            cleaned_contract_path = clean_docx(contract_path)
            shutil.copy2(cleaned_contract_path, output_path)
            doc = Document(output_path)

            comments_data = []
            unmatched_comments = []
            matched_count = 0

            for result in results:
                criterion = result.get('criterion', '')
                cid = result.get('criterion_id', '')

                for issue in result.get('issues', []):
                    reference = issue.get('quoted_text', '')
                    comment_text = issue.get('comment_text', '')

                    matched_anchor = DocxReportGenerator._find_matching_anchor(doc, reference)

                    if matched_anchor:
                        comments_data.append({
                            'anchor': matched_anchor,
                            'comment_text': comment_text,
                            'author': REVIEW_COMMENT_AUTHOR,
                        })
                        matched_count += 1
                    else:
                        unmatched_comments.append({
                            'criterion_id': cid,
                            'criterion': criterion,
                            'issue_id': issue['issue_id'],
                            'comment_text': comment_text,
                            'reference_text': reference,
                            'author': REVIEW_COMMENT_AUTHOR,
                        })

            fallback_anchor = DocxReportGenerator._get_document_start_anchor(doc)
            summary_comment_text = DocxReportGenerator._build_summary_comment_text(summary_sections)
            summary_added = False
            if fallback_anchor and summary_comment_text:
                comments_data.insert(0, {
                    'anchor': fallback_anchor,
                    'comment_text': summary_comment_text,
                    'author': SUMMARY_COMMENT_AUTHOR,
                })
                summary_added = True

            fallback_comment_text = DocxReportGenerator._build_unmatched_comment_text(unmatched_comments)
            fallback_count = 0
            skipped_count = len(unmatched_comments)

            if fallback_anchor and fallback_comment_text:
                comments_data.insert(1 if summary_added else 0, {
                    'anchor': fallback_anchor,
                    'comment_text': fallback_comment_text,
                    'author': REVIEW_COMMENT_AUTHOR,
                })
                fallback_count = len(unmatched_comments)
                skipped_count = 0

            if comments_data:
                DocxReportGenerator._add_comments_to_doc(doc, comments_data)

            doc.save(output_path)
            print(
                f"  DOCX: {matched_count} comments anchored to contract text, "
                f"{fallback_count} missing-content comments placed at document start, "
                f"{skipped_count} skipped",
                file=sys.stderr,
            )
            return output_path

        except Exception as e:
            print(f"  WARNING: DOCX comment generation failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
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

    # ==================== Markdown HTML Helper ====================

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
    def generate_docx_report(
        content: str,
        contract_path: str = None,
        results: list = None,
        output_path: str = None,
    ) -> str | None:
        """Generate an annotated DOCX when possible, otherwise a standard DOCX report."""
        if DocxReportGenerator._can_generate_annotated_docx(contract_path, results):
            docx_path = DocxReportGenerator._generate_docx_with_comments(
                contract_path, results, output_path
            )
            if docx_path:
                return docx_path
            print(
                "  DOCX: annotated export failed, falling back to standard report DOCX.",
                file=sys.stderr,
            )

        return DocxReportGenerator._generate_standard_docx_report(content, output_path)

    @staticmethod
    def generate_annotated_docx(
        contract_path: str,
        results: list,
        output_path: str,
        summary_sections: dict | None = None,
    ) -> str | None:
        """Generate only the annotated original-contract DOCX."""
        if not DocxReportGenerator._can_generate_annotated_docx(contract_path, results):
            print(
                "  DOCX: annotated export requires a DOCX contract and non-empty results.",
                file=sys.stderr,
            )
            return None
        return DocxReportGenerator._generate_docx_with_comments(
            contract_path,
            results,
            output_path,
            summary_sections=summary_sections,
        )


