from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PROJECT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from docxindex.indexing.attachment_hierarchy import collect_attachment_candidates, infer_attachment_children
from docxindex.indexing.node_factory import make_node
from docxindex.llm.schemas import AttachmentHierarchyResponse
from docxindex.schema import BodyItem


def item(
    index: int,
    text: str,
    *,
    outline: int | None = None,
    centered: bool = False,
    bold: bool = False,
) -> BodyItem:
    return BodyItem(
        kind="p",
        anchor=f"p_{index:04d}",
        body_child_index=index,
        text=text,
        raw_text=text,
        xml_path=f"/document/body/p[{index}]",
        direct_outline=outline,
        alignment="center" if centered else None,
        bold_fraction=1.0 if bold else 0.0,
    )


class FakeClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.settings = SimpleNamespace(model="fake-attachment-model")

    def complete_model(self, prompt: str, schema: type[AttachmentHierarchyResponse], retries: int = 0):
        self.calls += 1
        payload = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        return schema.model_validate(payload)


class AttachmentHierarchyTest(unittest.TestCase):
    def test_llm_profile_builds_six_level_attachment_tree(self) -> None:
        items = [
            item(1, "附件11", outline=2),
            item(2, "科技部门驻场外包考核细则", centered=True, bold=True),
            item(3, "第一条 总则", outline=3),
            item(4, "一、考核内容", outline=4),
            item(5, "（一）考勤考核", outline=5),
            item(6, "1、迟到", outline=6),
            item(7, "（1）首次迟到", outline=7),
            item(8, "具体处理内容。"),
        ]
        node = make_node(
            "attachments/att_011",
            "attachment_section",
            "附件11",
            items,
            0,
            len(items),
            None,
            "attachments",
        )
        response = {
            "segments": [
                {
                    "start_anchor": "p_0002",
                    "document_title": {
                        "anchor": "p_0002",
                        "title": "科技部门驻场外包考核细则",
                        "level": 1,
                    },
                    "level_rules": [
                        {"number_family": "article", "level": 2},
                        {"number_family": "cn_comma", "level": 3},
                        {"number_family": "cn_paren", "level": 4},
                        {"number_family": "arabic_comma", "level": 5},
                        {"number_family": "arabic_paren", "level": 6},
                    ],
                    "additional_headings": [],
                }
            ]
        }

        roots = infer_attachment_children(node, items, FakeClient([response]), None, split_long_nodes=False)

        self.assertIsNotNone(roots)
        current = roots[0]
        self.assertEqual(current.title, "科技部门驻场外包考核细则")
        for expected_level in range(1, 7):
            self.assertEqual(current.level, expected_level)
            if expected_level < 6:
                self.assertEqual(len(current.children), 1)
                current = current.children[0]

    def test_profile_rule_applies_to_all_continuous_candidates(self) -> None:
        items = [
            item(1, "附件1", outline=2),
            item(2, "内部管理细则", centered=True, bold=True),
            item(3, "1、第一项"),
            item(4, "2、第二项"),
            item(5, "3、第三项"),
        ]
        node = make_node("attachments/att_001", "attachment_section", "附件1", items, 0, len(items), None, "attachments")
        response = {
            "segments": [
                {
                    "start_anchor": "p_0002",
                    "document_title": {"anchor": "p_0002", "title": "内部管理细则", "level": 1},
                    "level_rules": [{"number_family": "arabic_comma", "level": 2}],
                    "additional_headings": [],
                }
            ]
        }

        roots = infer_attachment_children(node, items, FakeClient([response]), None, split_long_nodes=False)

        self.assertEqual([child.title for child in roots[0].children], ["1、第一项", "2、第二项", "3、第三项"])

    def test_required_numbered_family_must_have_rule(self) -> None:
        items = [
            item(1, "附件12", outline=2),
            item(2, "附件12.1", outline=3),
            item(3, "人员考核评级评分标准", centered=True, bold=True),
        ]
        node = make_node("attachments/att_012", "attachment_section", "附件12", items, 0, len(items), None, "attachments")
        invalid = {
            "segments": [
                {
                    "start_anchor": "p_0002",
                    "document_title": None,
                    "level_rules": [],
                    "additional_headings": [],
                }
            ]
        }
        client = FakeClient([invalid])

        roots = infer_attachment_children(node, items, client, None, split_long_nodes=False)

        self.assertIsNone(roots)
        self.assertEqual(client.calls, 3)

    def test_outline_nine_is_not_a_required_heading_signal(self) -> None:
        items = [
            item(1, "附件1", outline=2),
            item(2, "正文句子", outline=9),
            item(3, "一、真实标题", outline=3),
        ]

        candidates = collect_attachment_candidates(items, 1, len(items))
        by_anchor = {candidate.anchor: candidate for candidate in candidates}

        self.assertFalse(by_anchor["p_0002"].required)
        self.assertFalse(any(signal.startswith("outline:") for signal in by_anchor["p_0002"].signals))
        self.assertTrue(by_anchor["p_0003"].required)


if __name__ == "__main__":
    unittest.main()
