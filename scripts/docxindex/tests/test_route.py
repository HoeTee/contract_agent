from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from docxindex.llm.schemas import RouteResponse, RouteStep
from docxindex.retrieval import RouteConfig
from docxindex.retrieval.region import region_matches
from docxindex.retrieval.route import _titles, load_criteria
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
        self.assertEqual([item["node_id"] for item in scan], ["scan/batch_001"])
        self.assertEqual(scan[0]["start_anchor"], "p_0004")

    def test_scan_batches_keep_contiguous_anchor_ranges(self) -> None:
        self.index["anchor_map"]["p_0005"] = {
            "body_child_index": 5,
            "type": "p",
            "text": "第二段扫描内容",
            "node_id": "body/sec_001",
        }

        scan = scan_matches(self.index, batch_tokens=1)

        self.assertEqual([item["node_id"] for item in scan], ["scan/batch_001", "scan/batch_002"])
        self.assertEqual((scan[1]["start_anchor"], scan[1]["end_anchor"]), ("p_0005", "p_0005"))

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

    def test_route_schema_normalizes_model_parameter_variants(self) -> None:
        response = RouteResponse.model_validate(
            {
                "steps": [
                    {
                        "method": "region",
                        "params": {
                            "regions": ["body/sec_005/l2_003", "body/sec_006/l2_002"],
                            "check_keywords": ["project owner"],
                        },
                        "condition": {"depends_on_step": 0},
                    }
                ]
            }
        )
        self.assertEqual(response.steps[0].regions, ["body"])
        self.assertEqual(response.steps[0].terms, ["project owner"])

    def test_route_schema_normalizes_region_aliases(self) -> None:
        response = RouteResponse.model_validate(
            {
                "steps": [
                    {
                        "method": "region",
                        "params": {
                            "target": "body",
                            "context_title": "payment terms",
                        },
                    }
                ]
            }
        )
        self.assertEqual(response.steps[0].regions, ["body"])
        self.assertEqual(response.steps[0].terms, ["payment terms"])

    def test_route_schema_ignores_non_executable_model_params(self) -> None:
        response = RouteResponse.model_validate(
            {
                "steps": [
                    {
                        "method": "region",
                        "params": {
                            "target": "body",
                            "filter_by_title": True,
                            "context_source": "previous step",
                        },
                    }
                ]
            }
        )
        self.assertEqual(response.steps[0].regions, ["body"])

    def test_route_schema_ignores_top_level_model_explanations(self) -> None:
        response = RouteResponse.model_validate(
            {
                "steps": [{"method": "join", "slots": ["body", "attachments"]}],
                "fallback": False,
                "join": {"slots": ["body", "attachments"]},
                "reason": "compare both regions",
            }
        )
        self.assertEqual(response.steps[0].method, "join")

    def test_route_schema_normalizes_top_level_keyword_alias(self) -> None:
        response = RouteResponse.model_validate(
            {
                "steps": [
                    {
                        "method": "title",
                        "all_titles": True,
                        "check_keywords": ["违约责任"],
                    }
                ]
            }
        )
        self.assertEqual(response.steps[0].terms, ["违约责任"])

    def test_hybrid_is_an_explicit_route_method(self) -> None:
        response = RouteResponse.model_validate({"steps": [{"method": "hybrid"}], "fallback": True})
        self.assertEqual(response.steps[0].method, "hybrid")

    def test_region_terms_limit_body_to_matching_title(self) -> None:
        matches = region_matches(
            self.index,
            RouteStep(method="region", regions=["body"], terms=["合同期限"]),
            [],
        )
        self.assertEqual([item["node_id"] for item in matches], ["body/sec_001"])

    def test_route_title_catalog_includes_structure_metadata(self) -> None:
        catalog = _titles(self.index["structure_tree"])
        section = next(item for item in catalog if item["node_id"] == "body/sec_001")
        self.assertEqual(section["region"], "body")
        self.assertEqual(section["parent_id"], "body")

    def test_route_title_catalog_omits_deep_attachment_headings(self) -> None:
        deep_heading = self.node("attachments/att_001/h1_001", "deep heading", "", 4, 4)
        attachment = self.node("attachments/att_001", "attachment 1", "", 3, 4, [deep_heading])
        parent = self.node("attachments/parent", "attachments", "", 2, 4, [attachment])
        root = self.node("attachments", "attachments root", "", 1, 4, [parent])

        catalog = _titles([root])

        self.assertIn("attachment 1", [item["title"] for item in catalog])
        self.assertNotIn("deep heading", [item["title"] for item in catalog])


if __name__ == "__main__":
    unittest.main()
