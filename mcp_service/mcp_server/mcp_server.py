from mcp.server.fastmcp import FastMCP
from contextlib import redirect_stdout
import json
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from tools.document.file_parser import FileParser
from tools.document.report_generator import ReportGenerator
from tools.retrieval.index_retriever import IndexRetriever
from loggers.model_event_context import reset_model_event_path, set_model_event_path
from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBED_API_KEY,
    EMBED_BASE_URL,
    EMBED_NAME,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_ENABLE_THINKING,
    LLM_NAME,
    RERANK_API_KEY,
    RERANK_BASE_URL,
    RERANK_ENDPOINT_FORMAT,
    RERANK_NAME,
    RERANK_TOP_N,
    SIMILARITY_TOP_K,
)


mcp = FastMCP("docs-server")
index_retriever = IndexRetriever(
    project_root=PROJECT_ROOT,
    llm_api_key=LLM_API_KEY,
    llm_base_url=LLM_BASE_URL,
    llm_name=LLM_NAME,
    llm_enable_thinking=LLM_ENABLE_THINKING,
    embed_api_key=EMBED_API_KEY,
    embed_base_url=EMBED_BASE_URL,
    embed_name=EMBED_NAME,
    rerank_api_key=RERANK_API_KEY,
    rerank_base_url=RERANK_BASE_URL,
    rerank_endpoint_format=RERANK_ENDPOINT_FORMAT,
    rerank_name=RERANK_NAME,
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    similarity_top_k=SIMILARITY_TOP_K,
    rerank_top_n=RERANK_TOP_N,
)
index_retriever._get_contract_llamaindex_engine()


# ============ Document Tools ============

@mcp.tool()
async def ingest_file(file_path: str) -> str:
    """
    Parse a DOCX file, return full markdown content.
    """
    if os.path.splitext(file_path)[1].lower() != ".docx":
        return "Error parsing file: only .docx files are supported"
    try:
        content = FileParser.parse_file(file_path)
    except Exception as e:
        return f"Error parsing file: {str(e)}"

    filename = os.path.basename(file_path)
    return f"File '{filename}' ingested. Content:\n\n{content}"


@mcp.tool()
async def generate_markdown_report(
    content_json: str,
    contract_name: str,
    elapsed_seconds: float = None,
) -> str:
    """Generate only a markdown report."""
    try:
        with redirect_stdout(sys.stderr):
            path = ReportGenerator.generate_markdown_report(
                content_json,
                contract_name,
                elapsed_seconds=elapsed_seconds,
            )
        return json.dumps({"md": path}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def generate_docx_report(
    contract_name: str,
    contract_path: str,
    results_json: str | list,
    summary_sections_json: str | dict | None = None,
    output_dir: str | None = None,
    output_path: str | None = None,
) -> str:
    """Generate only the annotated original-contract DOCX."""
    try:
        if not output_dir and not output_path:
            return json.dumps({"error": "output_dir or output_path is required"}, ensure_ascii=False)

        results = json.loads(results_json) if isinstance(results_json, str) else results_json
        summary_sections = (
            json.loads(summary_sections_json)
            if isinstance(summary_sections_json, str) and summary_sections_json
            else summary_sections_json
        )
        with redirect_stdout(sys.stderr):
            path = ReportGenerator.generate_docx_report(
                contract_name=contract_name,
                contract_path=contract_path,
                results=results,
                summary_sections=summary_sections,
                output_dir=output_dir,
                output_path=output_path,
            )
        if not path:
            return json.dumps({"error": "DOCX report generation failed."}, ensure_ascii=False)
        return json.dumps({"docx": path}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def generate_pdf_report(
    content_json: str,
    contract_name: str,
    elapsed_seconds: float = None,
) -> str:
    """Generate only a PDF report."""
    try:
        with redirect_stdout(sys.stderr):
            path = ReportGenerator.generate_pdf_report(
                content_json,
                contract_name,
                elapsed_seconds=elapsed_seconds,
            )
        return json.dumps({"pdf": path}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============ Retrieval Tools ============

async def llamaindex_build_index(docx_path: str, api_events_path: str | None = None) -> str:
    """
    Build a temporary in-memory LlamaIndex index for the current contract.
    This does not persist contract vectors to RAG_persist.
    """
    token = set_model_event_path(api_events_path)
    try:
        return await index_retriever.build_contract_llamaindex_index(docx_path)
    finally:
        reset_model_event_path(token)


async def llamaindex_search(query: str, api_events_path: str | None = None) -> str:
    """
    Search the temporary in-memory LlamaIndex index for the current contract.
    Must call llamaindex_build_index first in the same workflow run.
    """
    token = set_model_event_path(api_events_path)
    try:
        return await index_retriever.search_contract_llamaindex(query)
    finally:
        reset_model_event_path(token)


mcp.tool()(llamaindex_build_index)
mcp.tool()(llamaindex_search)


if __name__ == "__main__":
    mcp.run()
