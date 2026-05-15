"""
SummarizerAgent produces the opening comment for the annotated DOCX.
"""

import json

from agents.base_agent import Agent
from agents.json_utils import chat_until_valid_json
from agents.prompts.cn_prompts import SUMMARIZER_SYSTEM_PROMPT
from agents.schemas import SummaryOutput


SUMMARY_EXPECTED_JSON = """
{
  "overall_comment": "总体审查总结",
  "priority_comments": [
    "优先修改建议1",
    "优先修改建议2"
  ]
}
"""


class SummarizerAgent(Agent):
    """Summarizes structured review issues for the DOCX opening comment."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt=SUMMARIZER_SYSTEM_PROMPT,
            name="Summarizer",
            **kwargs,
        )

    async def compile_summary_comment(self, results: list[dict]) -> dict:
        """Generate the concise opening DOCX summary comment."""
        issues = []
        for result in results:
            for issue in result.get("issues", []):
                issues.append(
                    {
                        "section": result.get("section", ""),
                        "criterion_id": result.get("criterion_id", ""),
                        "criterion": result.get("criterion", ""),
                        "risk_level": issue.get("risk_level", ""),
                        "quoted_text": issue.get("quoted_text", ""),
                        "comment_text": issue.get("comment_text", ""),
                    }
                )

        prompt_payload = {
            "criteria_count": len(results),
            "issue_count": len(issues),
            "issues": issues,
        }
        prompt = (
            "请根据以下结构化审查问题，生成写入 Word 开头批注的简短总结：\n"
            + json.dumps(prompt_payload, ensure_ascii=False, indent=2)
        )
        parsed, _ = await chat_until_valid_json(
            self,
            prompt,
            SummaryOutput,
            SUMMARY_EXPECTED_JSON,
        )
        return parsed

    async def compile_report(self, results: list[dict]) -> dict:
        """Backward-compatible wrapper for callers not yet renamed."""
        return await self.compile_summary_comment(results)
