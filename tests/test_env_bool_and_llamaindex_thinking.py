import importlib
import os
import unittest
from unittest.mock import patch


class EnvBoolTests(unittest.TestCase):
    def setUp(self):
        os.environ["ENABLE_WORKFLOW_LOGS"] = "True"
        import config

        self.config = importlib.reload(config)

    def tearDown(self):
        for name in ["BOOL_TEST", "ENABLE_WORKFLOW_LOGS"]:
            os.environ.pop(name, None)

    def test_env_bool_accepts_case_insensitive_values_and_defaults(self):
        os.environ["BOOL_TEST"] = "False"
        self.assertFalse(self.config.env_bool("BOOL_TEST", True))

        os.environ["BOOL_TEST"] = "True"
        self.assertTrue(self.config.env_bool("BOOL_TEST", False))

        os.environ["BOOL_TEST"] = ""
        self.assertIsNone(self.config.env_bool("BOOL_TEST", None))

        os.environ.pop("BOOL_TEST")
        self.assertTrue(self.config.env_bool("BOOL_TEST", True))

    def test_llm_enable_thinking_is_tri_state(self):
        os.environ["LLM_ENABLE_THINKING"] = "False"
        config = importlib.reload(self.config)
        self.assertFalse(config.LLM_ENABLE_THINKING)

        os.environ["LLM_ENABLE_THINKING"] = ""
        config = importlib.reload(self.config)
        self.assertIsNone(config.LLM_ENABLE_THINKING)


class LlamaIndexThinkingTests(unittest.TestCase):
    def _build_rag_and_capture_llm_kwargs(self, llm_enable_thinking):
        from tools.retrieval.llamaindex.rag_engine import LlamaIndexRAG

        captured = {}

        def fake_openai_like(**kwargs):
            captured["llm_kwargs"] = kwargs
            return object()

        class FakeSettings:
            pass

        with (
            patch("tools.retrieval.llamaindex.rag_engine.Settings", FakeSettings),
            patch("tools.retrieval.llamaindex.rag_engine.OpenAILike", side_effect=fake_openai_like),
            patch("tools.retrieval.llamaindex.rag_engine.OpenAILikeEmbedding", return_value=object()),
        ):
            LlamaIndexRAG(
                persist_dir="",
                llm_api_key="llm-key",
                llm_base_url="https://example.invalid/v1",
                llm_name="qwen3.6-27b",
                llm_enable_thinking=llm_enable_thinking,
                embed_api_key="embed-key",
                embed_base_url="https://example.invalid/v1",
                embed_name="text-embedding-v4",
            )

        return captured["llm_kwargs"]

    def test_llamaindex_rag_passes_enable_thinking_to_openai_like(self):
        llm_kwargs = self._build_rag_and_capture_llm_kwargs(False)
        self.assertEqual(
            {"extra_body": {"enable_thinking": False}},
            llm_kwargs["additional_kwargs"],
        )

    def test_llamaindex_rag_omits_extra_body_when_enable_thinking_unset(self):
        llm_kwargs = self._build_rag_and_capture_llm_kwargs(None)
        self.assertEqual({}, llm_kwargs["additional_kwargs"])


if __name__ == "__main__":
    unittest.main()
