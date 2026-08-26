import json
import unittest

from pydantic import BaseModel

from agents.json_utils import chat_until_valid_json, extract_json
from agents.schemas import SummaryContentOutput, SummaryOutput


class QuotedTextOutput(BaseModel):
    quoted_text: str


class StaticAgent:
    name = "StaticAgent"

    def __init__(self, output: str) -> None:
        self.output = output
        self.calls = 0

    async def chat(self, prompt: str) -> str:
        self.calls += 1
        return self.output


class SequenceAgent:
    name = "SequenceAgent"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls = 0

    async def chat(self, prompt: str) -> str:
        output = self.outputs[self.calls]
        self.calls += 1
        return output


class JsonUtilsTests(unittest.IsolatedAsyncioTestCase):
    async def test_literal_tab_reaches_pydantic_without_model_retry(self) -> None:
        agent = StaticAgent('{"quoted_text": "cell 1\tcell 2"}')

        parsed, raw_output = await chat_until_valid_json(
            agent,
            "return JSON",
            QuotedTextOutput,
            '{"quoted_text": "string"}',
        )

        self.assertEqual(parsed, {"quoted_text": "cell 1\tcell 2"})
        self.assertEqual(raw_output, agent.output)
        self.assertEqual(agent.calls, 1)

    def test_disallowed_control_character_remains_invalid(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            extract_json('{"quoted_text": "cell 1\u0000cell 2"}')

    def test_unrelated_json_syntax_error_remains_invalid(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            extract_json('{"quoted_text": }')

    async def test_final_attempt_can_keep_structurally_valid_long_content(self) -> None:
        long_comment = "长" * 201
        output = json.dumps(
            {"overall_comment": long_comment, "priority_comments": []},
            ensure_ascii=False,
        )
        agent = StaticAgent(output)

        parsed, raw_output = await chat_until_valid_json(
            agent,
            "return concise JSON",
            SummaryOutput,
            '{"overall_comment": "short", "priority_comments": []}',
            final_attempt_schema=SummaryContentOutput,
        )

        self.assertEqual(
            parsed,
            {"overall_comment": long_comment, "priority_comments": []},
        )
        self.assertEqual(raw_output, output)
        self.assertEqual(agent.calls, 3)

    async def test_final_attempt_does_not_keep_malformed_json(self) -> None:
        long_output = json.dumps(
            {"overall_comment": "长" * 201, "priority_comments": []},
            ensure_ascii=False,
        )
        agent = SequenceAgent(
            [
                long_output,
                long_output,
                '{"overall_comment": }',
            ]
        )

        with self.assertRaises(ValueError):
            await chat_until_valid_json(
                agent,
                "return concise JSON",
                SummaryOutput,
                '{"overall_comment": "short", "priority_comments": []}',
                final_attempt_schema=SummaryContentOutput,
            )

        self.assertEqual(agent.calls, 3)


if __name__ == "__main__":
    unittest.main()
