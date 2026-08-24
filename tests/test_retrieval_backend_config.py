from __future__ import annotations

import sys
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock

from config import CONFIG_PATH, LOGGING_ENABLED, RETRIEVAL_BACKEND
from endpoints.review import task_store
from loggers.trace_logger import TraceLogger
from tools.retrieval.docxindex_retriever import _format_anchor_context


DOCXINDEX_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "docxindex"
if str(DOCXINDEX_ROOT) not in sys.path:
    sys.path.insert(0, str(DOCXINDEX_ROOT))

from docxindex.indexing.config import IndexingConfig
from docxindex.retrieval import RetrievalConfig, RouteConfig


class RetrievalBackendConfigTests(unittest.TestCase):
    def test_root_config_defines_supported_backend_and_docxindex_sections(self) -> None:
        self.assertIn(RETRIEVAL_BACKEND, {"llamaindex", "docxindex"})
        self.assertGreater(RetrievalConfig.from_sources(CONFIG_PATH).input_tokens, 0)
        self.assertGreater(IndexingConfig.from_sources(CONFIG_PATH).paragraph.chunk_target_tokens, 0)
        self.assertTrue(RouteConfig.load(CONFIG_PATH).criteria.is_file())

    def test_docxindex_context_uses_report_compatible_anchor_ids(self) -> None:
        index = {
            "anchor_map": {
                "p_0001": {
                    "body_child_index": 1,
                    "type": "p",
                    "text": "第一条 自动编号文本",
                    "raw_text": "自动编号文本",
                },
                "tbl_0001": {
                    "body_child_index": 2,
                    "type": "tbl",
                    "text": "名称\t金额",
                    "raw_text": "名称\t金额",
                },
            }
        }
        result = _format_anchor_context(
            index,
            [{"title": "合同价款", "start_index": 1, "end_index": 2}],
        )
        self.assertIn("xml_anchor_type: paragraph", result)
        self.assertIn("xml_anchor_id: path:body/p1", result)
        self.assertIn("xml_anchor_type: table", result)
        self.assertIn("xml_anchor_id: path:body/tbl2", result)
        self.assertIn("自动编号文本", result)


class UnifiedLoggingSwitchTests(unittest.TestCase):
    def test_task_log_paths_and_trace_share_one_switch(self) -> None:
        self.assertEqual(task_store.should_write_task_file("logs"), bool(LOGGING_ENABLED))
        with patch("loggers.trace_logger.LOGGING_ENABLED", False):
            self.assertIsNone(TraceLogger("trace.json").path)
        with patch("loggers.trace_logger.LOGGING_ENABLED", True):
            self.assertEqual(TraceLogger("trace.json").path, Path("trace.json"))


class MCPRetrievalToolTests(unittest.TestCase):
    def test_mcp_exposes_legacy_backend_tools_and_configured_facade(self) -> None:
        from mcp_service.server.server import mcp

        names = {tool.name for tool in asyncio.run(mcp.list_tools())}
        self.assertTrue(
            {
                "llamaindex_build_index",
                "llamaindex_search",
                "docxindex_build_index",
                "docxindex_search",
                "contract_build_index",
                "contract_search",
            }.issubset(names)
        )

    def test_configured_facade_dispatches_to_docxindex(self) -> None:
        from mcp_service.server import server

        build = AsyncMock(return_value='{"status":"built_temporary_index"}')
        search = AsyncMock(return_value="context")
        with (
            patch.object(server, "RETRIEVAL_BACKEND", "docxindex"),
            patch.object(server, "docxindex_build_index", build),
            patch.object(server, "docxindex_search", search),
        ):
            self.assertIn(
                "built_temporary_index",
                asyncio.run(server.contract_build_index("contract.docx")),
            )
            self.assertEqual(asyncio.run(server.contract_search("query")), "context")
        build.assert_awaited_once_with("contract.docx", None)
        search.assert_awaited_once_with("query", None)


if __name__ == "__main__":
    unittest.main()
