from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PROJECT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from docx_retrieval.indexing.llm_summary import _summary_content
from docx_retrieval.indexing.token_budget import estimate_tokens
from docx_retrieval.schema import DocumentNode


class SummaryBudgetTest(unittest.TestCase):
    def test_table_summary_reads_more_content_than_normal_node(self) -> None:
        text = "项目金额为人民币一百元。" * 1200
        self.assertGreater(estimate_tokens(text), 6000)
        self.assertLess(estimate_tokens(text), 20000)
        common = {
            "title": "费用清单",
            "text": text,
            "summary": "",
            "start_anchor": "tbl_0001",
            "end_anchor": "tbl_0001",
        }
        table = DocumentNode(node_id="table", node_type="table", **common)
        section = DocumentNode(node_id="section", node_type="section", **common)

        self.assertEqual(_summary_content(table), text)
        self.assertLess(len(_summary_content(section)), len(text))


if __name__ == "__main__":
    unittest.main()
