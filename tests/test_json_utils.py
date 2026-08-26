import json
import unittest

from pydantic import BaseModel

from agents.json_utils import chat_until_valid_json, extract_json


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


if __name__ == "__main__":
    unittest.main()
