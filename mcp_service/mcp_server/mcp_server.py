from mcp.server.fastmcp import FastMCP
from pydantic_settings import BaseSettings
from pydantic import Field
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import httpx
import json
import os
import sys
import tempfile

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
from tools.document_tools import FileParser, ReportGenerator

# Add PageIndex to path
PAGEINDEX_ROOT = os.path.join(PROJECT_ROOT, "tools", "PageIndex-main")
sys.path.insert(0, PAGEINDEX_ROOT)
from pageindex.page_index_md import md_to_tree

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# LLM config for pageindex_search
import openai
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")
LLM_NAME = os.getenv("LLM_NAME", "qwen-plus")


class Settings(BaseSettings):
    USER_AGENT: str = Field(default="docs-app/1.0", alias="USER_AGENT")
    SERPER_URL: str = Field(default="https://google.serper.dev/search", alias="SERPER_URL")
    SERPER_API_KEY: str = Field(default=os.getenv("SERPER_API_KEY"), alias="SERPER_API_KEY")


mcp = FastMCP("docs-server")
settings = Settings()


# ============ Web Search ============

async def search_web(query: str) -> dict | None:
    headers = {
        "X-API-KEY": settings.SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    payload = json.dumps({"q": query, "page": 1})
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                settings.SERPER_URL, headers=headers,
                data=payload, timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            return {"organic": []}


async def fetch_url(url: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url, timeout=30.0, follow_redirects=True,
                headers={"User-Agent": settings.USER_AGENT}
            )
            soup = BeautifulSoup(response.text, "html.parser")
            return soup.get_text()
        except httpx.TimeoutException:
            return "Timeout error"


# @mcp.tool()
async def web_search(query: str) -> str:
    """
    Search Google via Serper. Returns top results with titles, links, snippets.
    """
    results = await search_web(query)
    if not results or "organic" not in results:
        return "No results found."
    formatted = "Search Results:\n"
    for idx, item in enumerate(results["organic"][:5]):
        formatted += f"{idx+1}. {item.get('title')}\n"
        formatted += f"   Link: {item.get('link')}\n"
        formatted += f"   Snippet: {item.get('snippet')}\n\n"
    return formatted


@mcp.tool()
async def read_url(url: str) -> str:
    """
    Visit a URL and read its full text content.
    """
    return str(await fetch_url(url))


# ============ Document Tools ============

@mcp.tool()
async def ingest_docx(file_path: str) -> str:
    """
    Parse a DOCX/PDF/TXT file, return full markdown content.
    """
    content = FileParser.parse_file(file_path)
    if content.startswith("Error"):
        return content
    filename = os.path.basename(file_path)
    return f"File '{filename}' ingested. Content:\n\n{content}"


@mcp.tool()
async def generate_final_report(
    content_json: str,
    contract_name: str,
    elapsed_seconds: float = None,
) -> str:
    """
    Generate MD, DOCX, and PDF reports from markdown content.
    Returns paths to all three generated files.
    """
    try:
        paths = ReportGenerator.generate_report(
            content_json, contract_name, elapsed_seconds=elapsed_seconds
        )
        lines = ["Reports generated successfully:"]
        for fmt, path in paths.items():
            status = path if path else "FAILED"
            lines.append(f"  {fmt.upper()}: {status}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error generating report: {str(e)}"


# ============ PageIndex Tools ============

@mcp.tool()
async def build_pageindex_tree(markdown_content: str) -> str:
    """
    Build a PageIndex tree structure from markdown content. 
    Returns tree JSON with node IDs, summaries, and text.
    """
    try:
        # Write markdown to temp file (md_to_tree needs a file path)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(markdown_content)
            tmp_path = f.name

        tree = await md_to_tree(
            tmp_path,
            if_thinning=False,
            if_add_node_summary="yes",
            summary_token_threshold=200,
            if_add_node_text="yes",
            if_add_node_id="yes",
            model=LLM_NAME
        )
        os.unlink(tmp_path)
        return json.dumps(tree, ensure_ascii=False, indent=2)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error building tree: {str(e)}"


@mcp.tool()
async def pageindex_search(query: str, tree_json: str) -> str:
    """
    Search a PageIndex tree for sections relevant to a query. 
    Uses LLM reasoning to identify and return relevant node texts.
    """
    try:
        tree = json.loads(tree_json)

        # Build a node_id -> node map for text extraction
        node_map = {}
        def _collect_nodes(nodes):
            if isinstance(nodes, dict):
                if "node_id" in nodes:
                    node_map[nodes["node_id"]] = nodes
                if "structure" in nodes:
                    _collect_nodes(nodes["structure"])
                if "nodes" in nodes:
                    _collect_nodes(nodes["nodes"])
            elif isinstance(nodes, list):
                for n in nodes:
                    _collect_nodes(n)
        _collect_nodes(tree)

        # Build tree without text for the search prompt
        def _strip_text(obj):
            if isinstance(obj, dict):
                return {k: _strip_text(v) for k, v in obj.items() if k != "text"}
            elif isinstance(obj, list):
                return [_strip_text(i) for i in obj]
            return obj

        tree_no_text = _strip_text(tree)

        search_prompt = f"""
        You are given a question and a tree structure of a document.
        Each node contains a node id, node title, and a corresponding summary.
        Your task is to find all nodes that are likely to contain the answer to the question.

        Question: {query}

        Document tree structure:
        {json.dumps(tree_no_text, indent=2, ensure_ascii=False)}

        Please reply in the following JSON format:
        {{
            "thinking": "<Your thinking process on which nodes are relevant>",
            "node_list": ["node_id_1", "node_id_2"]
        }}
        Directly return the final JSON structure. Do not output anything else.
        """

        client = openai.OpenAI(api_key=API_KEY, base_url=BASE_URL)
        response = client.chat.completions.create(
            model=LLM_NAME,
            messages=[{"role": "user", "content": search_prompt}],
            temperature=0,
            top_p=0.01,
            seed=42,
        )
        result_text = response.choices[0].message.content

        # Parse node list from response
        # Strip ```json ... ``` if present
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        result = json.loads(result_text.strip())
        node_ids = result.get("node_list", [])

        # Extract text from matched nodes
        relevant_texts = []
        for nid in node_ids:
            if nid in node_map and "text" in node_map[nid]:
                title = node_map[nid].get("title", "")
                relevant_texts.append(f"## {title}\n{node_map[nid]['text']}")

        if not relevant_texts:
            return "No relevant sections found."

        return "\n\n---\n\n".join(relevant_texts)

    except Exception as e:
        return f"Error in pageindex search: {str(e)}"

if __name__ == "__main__":
    mcp.run()
