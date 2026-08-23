from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PROJECT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from docxindex.detection.heading_profiles import (
    compile_heading_profile,
    default_heading_profiles,
    select_heading_profile,
)
from docxindex.detection.number_patterns import infer_number_pattern
from docxindex.indexing.config import IndexingConfig
from docxindex.schema import BodyItem


def item(index: int, text: str) -> BodyItem:
    return BodyItem(
        kind="p",
        anchor=f"p_{index:04d}",
        body_child_index=index,
        text=text,
        xml_path=f"/document/body/p[{index}]",
    )


class HeadingProfileTest(unittest.TestCase):
    def test_number_examples_are_generalized(self) -> None:
        article = infer_number_pattern("第二条 合同金额")
        comma = infer_number_pattern("2、增值服务")

        self.assertEqual(article.kind, "article")
        self.assertEqual(article.marker, "第二条")
        self.assertEqual(comma.kind, "arabic_comma")
        self.assertEqual(comma.marker, "2、")

    def test_multiple_examples_enable_multiple_number_forms(self) -> None:
        profile = compile_heading_profile(
            "variant",
            ["一、合作背景"],
            ["（一）通信业务合作", "（3）新技术合作"],
            ["1. 基础服务", "2、增值服务"],
        )

        self.assertEqual(profile.level_for("（二）金融业务合作"), 2)
        self.assertEqual(profile.level_for("（4）其他合作"), 2)
        self.assertEqual(profile.level_for("3. 服务要求"), 3)
        self.assertEqual(profile.level_for("4、交付要求"), 3)

    def test_profile_selection_uses_valid_hierarchy(self) -> None:
        items = [
            item(1, "一、合作背景"),
            item(2, "（一）基本原则"),
            item(3, "1. 合作事项"),
            item(4, "二、合作内容"),
        ]

        selected = select_heading_profile(items, default_heading_profiles())

        self.assertEqual(selected.profile.name, "variant_1")
        self.assertEqual(selected.level_counts, {1: 2, 2: 1, 3: 1})
        self.assertEqual(selected.orphan_count, 0)

    def test_profile_order_prioritizes_primary_when_it_has_a_heading_sequence(self) -> None:
        items = [
            item(1, "第一条 合同内容"),
            item(2, "一、服务范围"),
            item(3, "（一）硬件服务"),
            item(4, "1. 设备要求"),
            item(5, "二、服务期限"),
            item(6, "第二条 合同金额"),
        ]

        selected = select_heading_profile(items, default_heading_profiles())

        self.assertEqual(selected.profile.name, "primary")

    def test_project_config_contains_profiles_without_selection(self) -> None:
        config = IndexingConfig.from_sources(PROJECT_DIR / "config.yaml")

        self.assertEqual(list(config.heading.profiles), ["primary", "variant_1"])
        self.assertFalse(hasattr(config.heading, "selection"))
        self.assertEqual([profile.name for profile in config.heading.compile_profiles()], ["primary", "variant_1"])

    def test_ambiguous_level_examples_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ambiguous example"):
            compile_heading_profile(
                "invalid",
                ["一、一级"],
                ["二、二级"],
                ["1. 三级"],
            )


if __name__ == "__main__":
    unittest.main()
