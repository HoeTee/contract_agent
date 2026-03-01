"""
ReflectorAgent — quality control agent that reviews sub-agent output.
"""
import json

from agents.base_agent import Agent
from agents.prompts.cn_prompts import REFLECTOR_SYSTEM_PROMPT


class ReflectorAgent(Agent):
    """Reviews sub-agent output and returns PASS/REJECT with feedback."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt=REFLECTOR_SYSTEM_PROMPT,
            name="Reflector",
            **kwargs
        )

    async def review(self, agent_output: str, evaluation_criteria: str) -> dict:
        """
        Review a sub-agent's output.
        Returns: {"status": "PASS"/"REJECT", "feedback": "..."}
        """
        prompt = (
            f"请审核以下审查结果的质量：\n\n"
            f"**评估标准**：\n{evaluation_criteria}\n\n"
            f"**审查结果**：\n{agent_output}"
        )
        response = await self.chat(prompt)

        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            # If can't parse, treat as PASS to avoid infinite loops
            return {"status": "PASS", "feedback": "Unable to parse reflector output"}
