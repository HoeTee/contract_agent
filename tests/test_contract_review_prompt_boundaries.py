import unittest

from agents.prompts.cn_prompts import REFLECTOR_SYSTEM_PROMPT, SUB_AGENT_BASE_PROMPT


class ContractReviewPromptBoundaryTests(unittest.TestCase):
    def test_sub_agent_prompt_defines_attachment_and_external_data_boundaries(self):
        required_terms = [
            "正文与附件分开审查",
            "正文附件清单",
            "所有附件标题",
            "兜底条款",
            "未接入工商、涉诉、知识产权、法人主体、授权信息、法律法规知识库",
            "工商数据",
            "独立法人",
            "援引法律法规是否现行有效",
            '"not_applicable"',
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, SUB_AGENT_BASE_PROMPT)

    def test_reflector_prompt_preserves_valid_not_applicable_for_external_data_checks(self):
        required_terms = [
            "外部数据或法律知识库",
            "应当 PASS",
            "工商、涉诉、知识产权、独立法人、法律法规有效性",
            "一概返回 not_applicable",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, REFLECTOR_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
