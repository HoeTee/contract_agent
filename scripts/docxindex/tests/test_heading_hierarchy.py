from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PROJECT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from docxindex.detection import find_first_body_start, find_tail_start, heading_level
from docxindex.indexing.hierarchy import build_hierarchy_for_range
from docxindex.schema import BodyItem


def item(index: int, text: str, kind: str = "p") -> BodyItem:
    prefix = "tbl" if kind == "tbl" else "p"
    return BodyItem(
        kind=kind,
        anchor=f"{prefix}_{index:04d}",
        body_child_index=index,
        text=text,
        xml_path=f"/document/body/{prefix}[{index}]",
    )


class HeadingHierarchyTest(unittest.TestCase):
    def test_standard_heading_levels_are_unchanged(self) -> None:
        self.assertEqual(heading_level(item(1, "第一条 合同内容")), 1)
        self.assertEqual(heading_level(item(2, "一、服务范围")), 2)
        self.assertEqual(heading_level(item(3, "（一）服务地点")), 3)
        self.assertIsNone(heading_level(item(4, "1.具体要求")))

    def test_agreement_fallback_has_dense_three_level_hierarchy(self) -> None:
        items = [
            item(1, "一、合作总则"),
            item(2, "（一）合作原则"),
            item(3, "1.语音通信"),
            item(4, "（2）金融业务合作"),
            item(5, "2、现金管理业务"),
            item(6, "二、合作机制"),
        ]

        nodes = build_hierarchy_for_range(
            items,
            0,
            len(items),
            "body",
            "body",
            use_cn_comma_as_level1=True,
            split_long_nodes=False,
        )

        self.assertEqual([node.title for node in nodes], ["一、合作总则", "二、合作机制"])
        self.assertEqual([node.title for node in nodes[0].children], ["（一）合作原则", "（2）金融业务合作"])
        self.assertEqual([node.title for node in nodes[0].children[0].children], ["1.语音通信"])
        self.assertEqual([node.title for node in nodes[0].children[1].children], ["2、现金管理业务"])

    def test_sentence_with_signing_word_does_not_start_tail(self) -> None:
        items = [
            item(1, "一、合作总则"),
            item(2, "（一）双方本着自愿、平等原则签署本协议。"),
            item(3, "二、合作内容"),
            item(4, "甲方（单位盖章）：\n乙方（单位盖章）：", kind="tbl"),
        ]

        self.assertEqual(find_first_body_start(items), 0)
        self.assertEqual(find_tail_start(items, 0, len(items)), 3)


if __name__ == "__main__":
    unittest.main()
