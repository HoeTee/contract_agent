"""
PlannerAgent — parses criteria markdown into structured tasks.
"""
import json

from agents.base_agent import Agent
from agents.prompts.cn_prompts import PLANNER_SYSTEM_PROMPT


class PlannerAgent(Agent):
    """Extracts and structures review criteria into actionable tasks."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            name="Planner",
            **kwargs
        )

    async def design_tasks(self, criteria_markdown: str) -> dict:
        """
        Parse criteria text into structured JSON tasks.
        Returns: {"criteria": [{"id", "section", "criterion", "check_points"}, ...]}
        """
        prompt = f"请将以下审查标准整理为结构化的审查任务列表：\n\n{criteria_markdown}"
        response = await self.chat(prompt)

        # Parse JSON from response — multiple fallbacks
        text = response.strip()
        # Try ```json ... ``` first
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try extracting first { to last }
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(response[start:end])
                except json.JSONDecodeError:
                    pass
            print(f"[Planner] Warning: Failed to parse JSON, returning raw text")
            print(f"[Planner] Raw response (first 500 chars): {response[:500]}")
            return {"criteria": [], "raw": response}
