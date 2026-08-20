from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document
from lxml import etree

from tools.document.reporting.docx_report import DocxReportGenerator


class CoreCommentWriterTest(unittest.TestCase):
    def test_table_mapping_uses_core_comment_package_shape(self) -> None:
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
                self.assertNotIn("word/commentsIds.xml", names)
                self.assertNotIn("word/commentsExtensible.xml", names)
                comments = etree.fromstring(archive.read("word/comments.xml"))
                document = etree.fromstring(archive.read("word/document.xml"))

        w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        comment = comments.find(f"{{{w}}}comment")
        self.assertIsNotNone(comment)
        self.assertEqual("AI 条款审查", comment.get(f"{{{w}}}author"))
        self.assertEqual("第一行第二行", "".join(comment.itertext()))
        self.assertIsNotNone(document.find(f".//{{{w}}}commentRangeStart"))
        self.assertIsNotNone(document.find(f".//{{{w}}}commentRangeEnd"))
        self.assertIsNotNone(document.find(f".//{{{w}}}commentReference"))


if __name__ == "__main__":
    unittest.main()
