from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document
from lxml import etree

from tools.document.reporting.docx_report import DocxReportGenerator


class ModernCommentCompatibilityTest(unittest.TestCase):
    def test_comment_parts_share_the_last_comment_paragraph_id(self) -> None:
        doc = Document()
        paragraph = doc.add_paragraph("合同金额为人民币一百万元。")
        anchor = DocxReportGenerator._get_document_start_anchor(doc)
        self.assertIsNotNone(anchor)

        DocxReportGenerator._add_comments_to_doc(
            doc,
            [
                {
                    "anchor": anchor,
                    "comment_text": "第一行\n第二行",
                    "author": "AI 条款审查",
                }
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "commented.docx"
            doc.save(output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("word/comments.xml", names)
                self.assertIn("word/commentsExtended.xml", names)
                self.assertIn("word/people.xml", names)
                comments = etree.fromstring(archive.read("word/comments.xml"))
                comments_ex = etree.fromstring(
                    archive.read("word/commentsExtended.xml")
                )
                people = etree.fromstring(archive.read("word/people.xml"))

        w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        w14 = "http://schemas.microsoft.com/office/word/2010/wordml"
        w15 = "http://schemas.microsoft.com/office/word/2012/wordml"
        paragraphs = comments.findall(f".//{{{w}}}p")
        self.assertEqual(2, len(paragraphs))
        para_ids = [item.get(f"{{{w14}}}paraId") for item in paragraphs]
        self.assertTrue(all(para_ids))
        self.assertEqual(len(para_ids), len(set(para_ids)))

        comment_ex = comments_ex.find(f"{{{w15}}}commentEx")
        self.assertIsNotNone(comment_ex)
        self.assertEqual(para_ids[-1], comment_ex.get(f"{{{w15}}}paraId"))
        authors = {
            item.get(f"{{{w15}}}author")
            for item in people.findall(f"{{{w15}}}person")
        }
        self.assertIn("AI 条款审查", authors)


if __name__ == "__main__":
    unittest.main()
