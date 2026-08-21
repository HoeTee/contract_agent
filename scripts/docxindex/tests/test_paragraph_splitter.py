from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PROJECT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from docxindex.indexing.node_factory import make_node
from docxindex.indexing.splitter import split_long_leaf
from docxindex.indexing.token_budget import estimate_tokens
from docxindex.schema import BodyItem


class ParagraphSplitterTest(unittest.TestCase):
    def test_split_uses_paragraph_boundaries_and_keeps_parent_title(self) -> None:
        texts = ["甲方应当按时付款。" * 8, "乙方应当按时交付。" * 8, "双方应当完成验收。" * 8]
        items = [
            BodyItem(
                kind="p",
                anchor=f"p_{index:04d}",
                body_child_index=index,
                text=text,
                xml_path=f"/document/body/p[{index}]",
            )
            for index, text in enumerate(texts, start=1)
        ]
        node = make_node("body/sec_001", "section", "第一条 合同履行", items, 0, len(items), 1, "body")
        target = max(1, max(estimate_tokens(text) for text in texts))

        split_long_leaf(
            node,
            items,
            0,
            len(items),
            split_threshold_tokens=1,
            chunk_target_tokens=target,
        )

        self.assertEqual([child.text for child in node.children], texts)
        self.assertEqual(
            [child.title for child in node.children],
            [
                "第一条 合同履行 / chunk 1",
                "第一条 合同履行 / chunk 2",
                "第一条 合同履行 / chunk 3",
            ],
        )


if __name__ == "__main__":
    unittest.main()
