"""
ReflectorAgent validates sub-agent review quality.
"""

from agents.base_agent import Agent
from agents.json_utils import chat_until_valid_json
from agents.prompts.cn_prompts import REFLECTOR_SYSTEM_PROMPT
from agents.schemas import ReflectorOutput


REFLECTOR_EXPECTED_JSON = """
{
  "status": "PASS 或 REJECT",
  "feedback": "如果 REJECT，写明需要修正的问题；如果 PASS，可为空字符串"
}
"""


class ReflectorAgent(Agent):
    """Reviews sub-agent output and returns PASS/REJECT with feedback."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt=REFLECTOR_SYSTEM_PROMPT,
            name="Reflector",
            **kwargs,
        )

    async def review(self, agent_output: str, evaluation_criteria: str) -> dict:
        """
        Review a sub-agent's output.
        Returns: {"status": "PASS"/"REJECT", "feedback": "..."}
        """
        prompt = (
            "请审核以下审查结果的质量：\n\n"
            f"评估标准：\n{evaluation_criteria}\n\n"
            f"审查结果：\n{agent_output}"
        )
        parsed, _ = await chat_until_valid_json(
            self,
            prompt,
            ReflectorOutput,
            REFLECTOR_EXPECTED_JSON,
        )
        return parsed
