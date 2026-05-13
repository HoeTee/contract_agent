from mcp.server.fastmcp import FastMCP
from pydantic import Field
from pydantic_settings import BaseSettings
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from contextlib import redirect_stdout
import httpx
import json
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
from offline_bootstrap import configure_offline_tiktoken

configure_offline_tiktoken(PROJECT_ROOT)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from tools.document.file_parser import FileParser
from tools.document.report_generator import ReportGenerator
from tools.retrieval.index_retriever import IndexRetriever


API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")
LLM_NAME = os.getenv("LLM_NAME", "qwen-plus")
ENABLE_MCP_WEB_TOOLS = os.getenv("ENABLE_MCP_WEB_TOOLS")
PARSE_FILE_WITH_MINERU = os.getenv("PARSE_FILE_WITH_MINERU")


def env_bool(val):
    return str(val).lower() in ("1", "true", "yes")


class Settings(BaseSettings):
    USER_AGENT: str = Field(default="docs-app/1.0", alias="USER_AGENT")
    SERPER_URL: str = Field(default="https://google.serper.dev/search", alias="SERPER_URL")
    SERPER_API_KEY: str = Field(default=os.getenv("SERPER_API_KEY"), alias="SERPER_API_KEY")


mcp = FastMCP("docs-server")
settings = Settings()
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
)
if os.getenv("CONTRACT_RETRIEVAL_MODE") == "llamaindex":
    index_retriever._get_contract_llamaindex_engine()


# ============ Web Search ============

async def search_web(query: str) -> dict | None:
    if not settings.SERPER_API_KEY:
        return {"error": "SERPER_API_KEY is not configured.", "organic": []}
    headers = {
        "X-API-KEY": settings.SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = json.dumps({"q": query, "page": 1})
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                settings.SERPER_URL,
                headers=headers,
                data=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            return {"organic": []}


async def fetch_url(url: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url,
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": settings.USER_AGENT},
            )
            soup = BeautifulSoup(response.text, "html.parser")
            return soup.get_text()
        except httpx.TimeoutException:
            return "Timeout error"


async def web_search(query: str) -> str:
    """
    Search Google via Serper. Returns top results with titles, links, snippets.
    """
    results = await search_web(query)
    if results and results.get("error"):
        return f"Web search unavailable: {results['error']}"
    if not results or "organic" not in results:
        return "No results found."
    formatted = "Search Results:\n"
    for idx, item in enumerate(results["organic"][:5]):
        formatted += f"{idx + 1}. {item.get('title')}\n"
        formatted += f"   Link: {item.get('link')}\n"
        formatted += f"   Snippet: {item.get('snippet')}\n\n"
    return formatted


async def read_url(url: str) -> str:
    """
    Visit a URL and read its full text content.
    """
    return str(await fetch_url(url))


mcp.tool()(web_search)
mcp.tool()(read_url)


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
async def generate_final_report(
    content_json: str,
    contract_name: str,
    elapsed_seconds: float = None,
    contract_path: str = None,
    results_json: str = None,
) -> str:
    """
    Generate MD, annotated DOCX, and PDF reports from markdown content.
    DOCX: only generated when the source contract is a DOCX. The export is a
    cleaned contract copy with review comments.
    PDF: renders the markdown report through Pandoc + xelatex.
    Returns paths to all three generated files.
    """
    try:
        results = json.loads(results_json) if results_json else None
        # MCP stdio reserves stdout for JSON-RPC frames. Report generation can
        # invoke libraries that print progress, so route incidental text away
        # from stdout while the tool runs.
        with redirect_stdout(sys.stderr):
            paths = ReportGenerator.generate_report(
                content_json,
                contract_name,
                elapsed_seconds=elapsed_seconds,
                contract_path=contract_path,
                results=results,
            )
        errors = paths.pop("errors", {}) if isinstance(paths, dict) else {}
        lines = ["Reports generated successfully:"]
        for fmt, path in paths.items():
            status = path if path else "FAILED"
            lines.append(f"  {fmt.upper()}: {status}")
        for fmt, message in errors.items():
            lines.append(f"  {fmt.upper()}_ERROR: {message}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error generating report: {str(e)}"


# ============ Retrieval Tools ============

@mcp.tool()
async def build_pageindex_tree(markdown_content: str) -> str:
    """
    Build a PageIndex tree structure from markdown content.
    Returns tree JSON with node IDs, summaries, and text.
    """
    return await index_retriever.build_pageindex_tree(markdown_content)


@mcp.tool()
async def pageindex_search(query: str, tree_json: str) -> str:
    """
    Search a PageIndex tree for sections relevant to a query.
    Uses two-stage LLM reasoning and returns relevant node texts.
    """
    return await index_retriever.pageindex_search(query, tree_json)


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


async def institutional_search(query: str) -> str:
    """
    Search the persistent institutional-document index for relevant policy passages.
    The index is maintained manually via scripts/build_institutional_index.py.
    """
    return await index_retriever.search_institutional_index(query)


mcp.tool()(llamaindex_build_index)
mcp.tool()(llamaindex_search)
mcp.tool()(institutional_search)


if __name__ == "__main__":
    mcp.run()
