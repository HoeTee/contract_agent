from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from agents.prompts.cn_prompts import _REQUIRED_PROMPTS, load_prompts


class PromptConfigTests(unittest.TestCase):
    def _write_yaml(self, data: object) -> Path:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "cn_prompts.yaml"
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return path

    def test_bundled_prompt_yaml_defines_non_empty_required_prompts(self) -> None:
        path = Path(__file__).resolve().parents[1] / "agents" / "prompts" / "cn_prompts.yaml"

        prompts = load_prompts(path)

        self.assertEqual(tuple(prompts), _REQUIRED_PROMPTS)
        self.assertTrue(all(value.strip() for value in prompts.values()))

    def test_load_prompts_rejects_missing_prompt(self) -> None:
        path = self._write_yaml({name: "prompt" for name in _REQUIRED_PROMPTS[:-1]})

        with self.assertRaisesRegex(RuntimeError, _REQUIRED_PROMPTS[-1]):
            load_prompts(path)

    def test_load_prompts_rejects_invalid_yaml(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "cn_prompts.yaml"
        path.write_text("invalid: [", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "Invalid prompt YAML"):
            load_prompts(path)


if __name__ == "__main__":
    unittest.main()
