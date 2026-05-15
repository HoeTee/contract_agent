"""
PlannerAgent parses criteria markdown into structured review tasks.
"""

from agents.base_agent import Agent
from agents.json_utils import chat_until_valid_json
from agents.prompts.cn_prompts import PLANNER_SYSTEM_PROMPT
from agents.schemas import PlannerOutput


PLANNER_EXPECTED_JSON = """
{
  "criteria": [
    {
      "id": "C1",
      "section": "原文大类标题",
      "criterion": "原文审查标准",
      "check_points": ["原文检查点"]
    }
  ]
}
"""


class PlannerAgent(Agent):
    """Extracts and structures review criteria into actionable tasks."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            name="Planner",
            **kwargs,
        )

    async def design_tasks(self, criteria_markdown: str) -> dict:
        """
        Parse criteria text into structured JSON tasks.
        Returns: {"criteria": [{"id", "section", "criterion", "check_points"}, ...]}
        """
        prompt = f"请将以下审查标准整理为结构化的审查任务列表：\n\n{criteria_markdown}"
        parsed, _ = await chat_until_valid_json(
            self,
            prompt,
            PlannerOutput,
            PLANNER_EXPECTED_JSON,
        )
        return parsed
