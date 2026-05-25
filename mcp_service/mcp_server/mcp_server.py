from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from contextlib import redirect_stdout
import json
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from tools.document.file_parser import FileParser
from tools.document.report_generator import ReportGenerator
from tools.retrieval.index_retriever import IndexRetriever


API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")
LLM_NAME = os.getenv("LLM_NAME", "qwen-plus")
PARSE_FILE_WITH_MINERU = os.getenv("PARSE_FILE_WITH_MINERU")


def env_bool(val):
    return str(val).lower() in ("1", "true", "yes")


mcp = FastMCP("docs-server")
index_retriever = IndexRetriever(
    project_root=PROJECT_ROOT,
    llm_api_key=API_KEY,
    llm_base_url=BASE_URL,
    llm_name=LLM_NAME,
    embed_api_key=os.getenv("EMBED_API_KEY", API_KEY),
    embed_base_url=os.getenv("EMBED_BASE_URL", BASE_URL),
    embed_name=os.getenv("EMBED_NAME", "text-embedding-v4"),
    rerank_api_key=os.getenv("RERANK_API_KEY"),
    rerank_base_url=os.getenv("RERANK_BASE_URL"),
    rerank_name=os.getenv("RERANK_NAME"),
    chunk_size=int(os.getenv("CHUNK_SIZE", "512")),
    chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
    similarity_top_k=int(os.getenv("SIMILARITY_TOP_K", "5")),
    rerank_top_n=int(os.getenv("RERANK_TOP_N", "3")),
)
index_retriever._get_contract_llamaindex_engine()


# ============ Document Tools ============

@mcp.tool()
async def ingest_file(file_path: str) -> str:
    """
    Parse a DOCX/PDF/TXT file, return full markdown content.
    """
    if env_bool(PARSE_FILE_WITH_MINERU):
        try:
            content = await FileParser.parse_file_with_mineru(file_path)
        except Exception as e:
            return f"Error parsing file: {str(e)}"
    else:
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

async def llamaindex_build_index(markdown_content: str) -> str:
    """
    Build a temporary in-memory LlamaIndex index for the current contract.
    This does not persist contract vectors to RAG_persist.
    """
    return await index_retriever.build_contract_llamaindex_index(markdown_content)


async def llamaindex_search(query: str) -> str:
    """
    Search the temporary in-memory LlamaIndex index for the current contract.
    Must call llamaindex_build_index first in the same workflow run.
    """
    return await index_retriever.search_contract_llamaindex(query)


mcp.tool()(llamaindex_build_index)
mcp.tool()(llamaindex_search)


if __name__ == "__main__":
    mcp.run()
