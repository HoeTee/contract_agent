import asyncio
import contextlib
from mcp.server.fastmcp import FastMCP
from pydantic_settings import BaseSettings
from pydantic import Field
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import hashlib
import httpx
import io
import json
import os
import sys
import tempfile

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
from tools.document.file_parser import FileParser
from tools.document.report_generator import ReportGenerator
from tools.retrieval.pageindex.page_index_md import md_to_tree
from tools.retrieval.llamaindex import build_llamaindex_env_error, load_llamaindex_rag

# LLM config for pageindex_search
import openai
API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")
LLM_NAME = os.getenv("LLM_NAME", "qwen-plus")
ENABLE_MCP_WEB_TOOLS = os.getenv("ENABLE_MCP_WEB_TOOLS")
PARSE_FILE_WITH_MINERU = os.getenv("PARSE_FILE_WITH_MINERU")


def env_bool(val):
    return str(val).lower() in ("1", "true", "yes")


def _load_mineru_parser():
    from tools.document.parsers.mineru_pdf_parser import parse_file_with_mineru

    return parse_file_with_mineru

class Settings(BaseSettings):
    USER_AGENT: str = Field(default="docs-app/1.0", alias="USER_AGENT")
    SERPER_URL: str = Field(default="https://google.serper.dev/search", alias="SERPER_URL")
    SERPER_API_KEY: str = Field(default=os.getenv("SERPER_API_KEY"), alias="SERPER_API_KEY")


mcp = FastMCP("docs-server")
settings = Settings()
PAGEINDEX_TREE_CACHE_DIR = os.path.join(PROJECT_ROOT, "RAG_persist", "pageindex_tree")
_pageindex_tree_cache: dict[str, str] = {}


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


# @mcp.tool()
async def read_url(url: str) -> str:
    """
    Visit a URL and read its full text content.
    """
    return str(await fetch_url(url))

if env_bool(ENABLE_MCP_WEB_TOOLS):
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
            parse_file_with_mineru = _load_mineru_parser()
            content = await parse_file_with_mineru(file_path)
        except Exception as e:
            return f"Error parsing file: {str(e)}"
        
        filename = os.path.basename(file_path)
        return f"File '{filename}' ingested. Content:\n\n{content}"
    else:
        try:
            content = FileParser.parse_file(file_path)
            filename = os.path.basename(file_path)
            return f"File '{filename}' ingested. Content:\n\n{content}"
        except Exception as e:
            return f"Error parsing file: {str(e)}"

@mcp.tool()
async def generate_final_report(
    content_json: str,
    contract_name: str,
    elapsed_seconds: float = None,
    contract_path: str = None,
    results_json: str = None,
) -> str:
    """
    Generate MD, DOCX, and PDF reports from markdown content.
    DOCX: copies original contract and adds review comments as annotations.
    PDF: renders markdown with optimized CSS for Chinese text and tables.
    Returns paths to all three generated files.
    """
    try:
        # Parse results JSON if provided
        results = None
        if results_json:
            results = json.loads(results_json)
        
        paths = ReportGenerator.generate_report(
            content_json, contract_name,
            elapsed_seconds=elapsed_seconds,
            contract_path=contract_path,
            results=results,
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
    summary_token_threshold = 200
    cache_key = hashlib.sha256(
        json.dumps(
            {
                "markdown_hash": hashlib.sha256(markdown_content.encode("utf-8")).hexdigest(),
                "model": LLM_NAME,
                "summary_token_threshold": summary_token_threshold,
                "with_node_summary": True,
                "with_node_text": True,
                "with_node_id": True,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    cache_path = os.path.join(PAGEINDEX_TREE_CACHE_DIR, f"{cache_key}.json")

    try:
        if cache_key in _pageindex_tree_cache:
            return _pageindex_tree_cache[cache_key]

        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_tree_json = f.read()
            _pageindex_tree_cache[cache_key] = cached_tree_json
            return cached_tree_json

        # Write markdown to temp file (md_to_tree needs a file path)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(markdown_content)
            tmp_path = f.name

        try:
            tree = await md_to_tree(
                tmp_path,
                if_thinning=False,
                if_add_node_summary="yes",
                summary_token_threshold=summary_token_threshold,
                if_add_node_text="yes",
                if_add_node_id="yes",
                model=LLM_NAME
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        tree_json = json.dumps(tree, ensure_ascii=False, indent=2)
        os.makedirs(PAGEINDEX_TREE_CACHE_DIR, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(tree_json)
        _pageindex_tree_cache[cache_key] = tree_json
        return tree_json
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error building tree: {str(e)}"


# ── Shared LLM helper for tree search ──────────────────────

SINGLE_STAGE_THRESHOLD = 20  # Use single-stage search if total nodes <= this


def _collect_all_nodes(tree):
    """Build a flat node_id -> node map from the tree."""
    node_map = {}
    def _walk(nodes):
        if isinstance(nodes, dict):
            if "node_id" in nodes:
                node_map[nodes["node_id"]] = nodes
            for key in ("structure", "nodes", "children"):
                if key in nodes:
                    _walk(nodes[key])
        elif isinstance(nodes, list):
            for n in nodes:
                _walk(n)
    _walk(tree)
    return node_map


def _get_children(node):
    """Return the direct child list of a tree node."""
    for key in ("structure", "nodes", "children"):
        children = node.get(key)
        if children:
            return children if isinstance(children, list) else [children]
    return []


def _summarize_node(node):
    """Extract a lightweight summary dict (no text, no deep children)."""
    return {
        "node_id": node.get("node_id", ""),
        "title": node.get("title", ""),
        "summary": node.get("summary", node.get("prefix_summary", "")),
        "has_children": bool(_get_children(node)),
    }


async def _llm_select_nodes(query: str, candidates: list[dict]) -> list[str]:
    """Ask LLM to select relevant node IDs from a candidate list."""
    prompt = f"""你是一个文档检索助手。根据查询问题，从以下节点列表中选出所有可能包含答案的节点。

查询问题：{query}

节点列表：
{json.dumps(candidates, indent=2, ensure_ascii=False)}

请直接返回 JSON，不要输出其他内容：
{{
    "thinking": "<你的分析过程>",
    "node_list": ["node_id_1", "node_id_2"]
}}"""

    client = openai.AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    response = await client.chat.completions.create(
        model=LLM_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        top_p=0.01,
        seed=42,
    )
    result_text = response.choices[0].message.content
    token_usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }

    if "```json" in result_text:
        result_text = result_text.split("```json")[1].split("```")[0]
    parsed = json.loads(result_text.strip())
    return parsed.get("node_list", []), token_usage


@mcp.tool()
async def pageindex_search(query: str, tree_json: str) -> str:
    """
    Search a PageIndex tree for sections relevant to a query.
    Uses two-stage LLM reasoning: first select top-level sections by summary,
    then drill down into children of selected sections.
    Returns relevant node texts.
    """
    try:
        tree = json.loads(tree_json)
        node_map = _collect_all_nodes(tree)
        total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        def _acc_tokens(usage):
            for k in total_tokens:
                total_tokens[k] += usage.get(k, 0)

        # Small document: single-stage (original behavior)
        if len(node_map) <= SINGLE_STAGE_THRESHOLD:
            candidates = [_summarize_node(n) for n in node_map.values()]
            selected_ids, usage = await _llm_select_nodes(query, candidates)
            _acc_tokens(usage)
        else:
            # Stage 1: select from top-level nodes
            top_level = tree if isinstance(tree, list) else _get_children(tree)
            if not top_level:
                top_level = [tree]
            top_candidates = [_summarize_node(n) for n in top_level]
            stage1_ids, usage1 = await _llm_select_nodes(query, top_candidates)
            _acc_tokens(usage1)

            # Stage 2: for each selected top-level node, drill into children
            selected_ids = []
            for tid in stage1_ids:
                parent = node_map.get(tid)
                if not parent:
                    continue
                children = _get_children(parent)
                if not children:
                    # Leaf node — select directly
                    selected_ids.append(tid)
                    continue
                # Ask LLM to pick among children
                child_candidates = [_summarize_node(c) for c in children if isinstance(c, dict)]
                if not child_candidates:
                    selected_ids.append(tid)
                    continue
                stage2_ids, usage2 = await _llm_select_nodes(query, child_candidates)
                _acc_tokens(usage2)
                selected_ids.extend(stage2_ids)
                # Also include parent if it has its own text
                if parent.get("text"):
                    selected_ids.append(tid)

        # Deduplicate while preserving order
        seen = set()
        unique_ids = []
        for nid in selected_ids:
            if nid not in seen:
                seen.add(nid)
                unique_ids.append(nid)

        # Extract text from matched nodes
        relevant_texts = []
        for nid in unique_ids:
            if nid in node_map and "text" in node_map[nid]:
                title = node_map[nid].get("title", "")
                relevant_texts.append(f"## {title}\n{node_map[nid]['text']}")

        if not relevant_texts:
            return json.dumps({
                "result": "No relevant sections found.",
                "token_usage": total_tokens,
            }, ensure_ascii=False)

        return json.dumps({
            "result": "\n\n---\n\n".join(relevant_texts),
            "token_usage": total_tokens,
        }, ensure_ascii=False)

    except Exception as e:
        return f"Error in pageindex search: {str(e)}"


# ============ LlamaIndex Tools ============

_llamaindex_engine = None  # Lazy singleton


def _get_llamaindex_engine():
    """Lazily initialize the LlamaIndex RAG engine."""
    global _llamaindex_engine
    if _llamaindex_engine is None:
        try:
            LlamaIndexRAG = load_llamaindex_rag()
        except Exception as e:
            raise build_llamaindex_env_error(e) from e

        _llamaindex_engine = LlamaIndexRAG(
            persist_dir=os.path.join(PROJECT_ROOT, "RAG_persist", "index"),
            manifest_path=os.path.join(PROJECT_ROOT, "RAG_persist", "manifest.json"),
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
    return _llamaindex_engine

def warmup_llamaindex_engine() -> None:
    """Force lzy LlamaIndex initialization during backend startup."""
    _get_llamaindex_engine()

async def llamaindex_build_index(markdown_content: str) -> str:
    """
    Build a LlamaIndex vector index from markdown content.
    Returns index metadata JSON (status, doc_hash, num_nodes).
    Uses embedding model to vectorize document chunks.
    """
    try:
        engine = _get_llamaindex_engine()
        sink = io.StringIO()
        def _build_index() -> str:
            # Keep MCP stdio stdout untouched; only suppress noisy stderr from
            # tqdm/http clients while the index is building.
            with contextlib.redirect_stderr(sink):
                return engine.build_index_from_markdown(markdown_content)

        result = await asyncio.to_thread(_build_index)
        return result
    except Exception as e:
        return json.dumps({"error": str(e)})


async def llamaindex_search(query: str) -> str:
    """
    Search the LlamaIndex vector index for sections relevant to a query.
    Uses embedding similarity + reranking to find the most relevant passages.
    Must call llamaindex_build_index first.
    """
    try:
        engine = _get_llamaindex_engine()
        sink = io.StringIO()
        def _search_index() -> str:
            # Keep MCP stdio stdout untouched; only suppress noisy stderr from
            # tqdm/http clients while searching.
            with contextlib.redirect_stderr(sink):
                return engine.search(query)

        result = await asyncio.to_thread(_search_index)
        return result
    except Exception as e:
        return f"Error in LlamaIndex search: {str(e)}"


mcp.tool()(llamaindex_build_index)
mcp.tool()(llamaindex_search)


if __name__ == "__main__":
    mcp.run()
