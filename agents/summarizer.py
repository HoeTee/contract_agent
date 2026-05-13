"""
SummarizerAgent produces the report overview and priority advice from
structured review issues.
"""
import json

from agents.base_agent import Agent
from agents.prompts.cn_prompts import SUMMARIZER_SYSTEM_PROMPT


class SummarizerAgent(Agent):
    """Summarizes structured review issues for the final report."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt=SUMMARIZER_SYSTEM_PROMPT,
            name="Summarizer",
            **kwargs
        )

    async def compile_report(self, results: list[dict]) -> dict[str, str]:
        """Generate only the overview and priority advice sections."""
        issues = []
        for result in results:
            for issue in result["issues"]:
                issues.append(
                    {
                        "section": result["section"],
                        "criterion_id": result["criterion_id"],
                        "criterion": result["criterion"],
                        "risk_level": issue["risk_level"],
                        "clause_location": issue["clause_location"],
                        "issue_summary": issue["issue_summary"],
                        "conclusion": issue["conclusion"],
                        "institutional_basis": issue["institutional_basis"],
                        "suggestion": issue["suggestion"],
                    }
                )

        prompt_payload = {
            "criteria_count": len(results),
            "issue_count": len(issues),
            "issues": issues,
        }
        response = await self.chat(
            "请根据以下结构化审查问题摘要，生成报告概要和优先处理建议：\n"
            + json.dumps(prompt_payload, ensure_ascii=False, indent=2)
        )
        return json.loads(response)
