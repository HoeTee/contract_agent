from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from docxindex.llm.schemas import RouteResponse, RouteStep
from docxindex.retrieval import RouteConfig
from docxindex.retrieval.region import region_matches
from docxindex.retrieval.route import load_criteria
from docxindex.retrieval.rule import rule_matches
from docxindex.retrieval.scan import scan_matches
from docxindex.retrieval.title import title_matches


class RouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = {
            "top_regions": {"frontmatter": "frontmatter", "body": "body", "tail": "tail"},
            "nodes": [
                self.node("frontmatter", "合同首部", "签订日期：2026年1月1日", 1, 2),
                self.node("body", "正文", "第一条 合同期限\n期限三年", 3, 5, ["body/sec_001"]),
                self.node("body/sec_001", "第一条 合同期限", "期限三年", 3, 5),
                self.node("tail", "合同末尾", "以下无正文", 6, 6),
            ],
            "structure_tree": [
                self.node("frontmatter", "合同首部", "", 1, 2),
                self.node(
                    "body",
                    "正文",
                    "",
                    3,
                    5,
                    [self.node("body/sec_001", "第一条 合同期限", "", 3, 5)],
                ),
                self.node("tail", "合同末尾", "", 6, 6),
            ],
            "anchor_map": {
                "p_0004": {
                    "body_child_index": 4,
                    "type": "p",
                    "text": "期限三年",
                    "node_id": "body/sec_001",
                }
            },
        }

    @staticmethod
    def node(node_id, title, text, start, end, children=None):
        return {
            "node_id": node_id,
            "title": title,
            "text": text,
            "summary": text,
            "node_type": "body" if node_id == "body" else "section",
            "start_index": start,
            "end_index": end,
            "start_anchor": f"p_{start:04d}",
            "end_anchor": f"p_{end:04d}",
            "token_estimate": 10,
            "children": children or [],
            "nodes": children or [],
        }

    def test_criteria_source_contains_all_items(self) -> None:
        config = RouteConfig.load()
        criteria = load_criteria(config.criteria, config.expected_criteria_count)
        self.assertEqual(list(criteria), list(range(1, 19)))
        self.assertIn("支付方式", criteria[6])

    def test_title_requires_terms_unless_all_titles(self) -> None:
        self.assertEqual(title_matches(self.index, RouteStep(method="title")), [])
        matches = title_matches(self.index, RouteStep(method="title", terms=["合同期限"]))
        self.assertEqual([item["node_id"] for item in matches], ["body/sec_001"])

    def test_region_rule_and_scan_have_distinct_scope(self) -> None:
        region = region_matches(self.index, RouteStep(method="region", regions=["frontmatter"]), [])
        self.assertEqual([item["node_id"] for item in region], ["frontmatter"])
        rule = rule_matches(self.index, RouteStep(method="rule", terms=["期限三年"]))
        self.assertEqual([item["node_id"] for item in rule], ["body/sec_001/match_p_0004"])
        scan = scan_matches(self.index)
        self.assertEqual([item["node_id"] for item in scan], ["body/sec_001/scan_p_0004"])

    def test_route_schema_can_compose_methods(self) -> None:
        response = RouteResponse.model_validate(
            {"steps": [{"method": "region", "regions": ["frontmatter"]}, {"method": "rule", "terms": ["合同期限"]}]}
        )
        self.assertEqual([step.method for step in response.steps], ["region", "rule"])

    def test_route_schema_flattens_valid_params_wrapper(self) -> None:
        response = RouteResponse.model_validate(
            {"steps": [{"method": "scan", "params": {}, "description": "全文扫描"}], "fallback": False}
        )
        self.assertEqual(response.steps[0].method, "scan")


if __name__ == "__main__":
    unittest.main()
