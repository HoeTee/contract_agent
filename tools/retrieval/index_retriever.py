from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import json
import os
import tempfile

import openai

from tools.retrieval.llamaindex import build_llamaindex_env_error, load_llamaindex_rag
from tools.retrieval.pageindex.page_index_md import md_to_tree


SINGLE_STAGE_THRESHOLD = 20


class IndexRetriever:
    """Facade over the project's PageIndex and LlamaIndex retrieval strategies."""

    def __init__(
        self,
        *,
        project_root: str,
        llm_api_key: str | None,
        llm_base_url: str | None,
        llm_name: str,
        embed_api_key: str | None,
        embed_base_url: str | None,
        embed_name: str,
        rerank_api_key: str | None,
        rerank_base_url: str | None,
        rerank_name: str | None,
    ) -> None:
        self.project_root = project_root
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_name = llm_name
        self.embed_api_key = embed_api_key
        self.embed_base_url = embed_base_url
        self.embed_name = embed_name
        self.rerank_api_key = rerank_api_key
        self.rerank_base_url = rerank_base_url
        self.rerank_name = rerank_name
        self.pageindex_tree_cache_dir = os.path.join(
            self.project_root,
            "RAG_persist",
            "pageindex_tree",
        )
        self._pageindex_tree_cache: dict[str, str] = {}
        self._llamaindex_engine = None

    async def build_pageindex_tree(self, markdown_content: str) -> str:
        """Build or load a cached PageIndex tree from markdown content."""
        summary_token_threshold = 200
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "markdown_hash": hashlib.sha256(markdown_content.encode("utf-8")).hexdigest(),
                    "model": self.llm_name,
                    "summary_token_threshold": summary_token_threshold,
                    "with_node_summary": True,
                    "with_node_text": True,
                    "with_node_id": True,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        cache_path = os.path.join(self.pageindex_tree_cache_dir, f"{cache_key}.json")

        try:
            if cache_key in self._pageindex_tree_cache:
                return self._pageindex_tree_cache[cache_key]

            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_tree_json = f.read()
                self._pageindex_tree_cache[cache_key] = cached_tree_json
                return cached_tree_json

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                delete=False,
                encoding="utf-8",
            ) as f:
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
                    model=self.llm_name,
                )
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            tree_json = json.dumps(tree, ensure_ascii=False, indent=2)
            os.makedirs(self.pageindex_tree_cache_dir, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(tree_json)
            self._pageindex_tree_cache[cache_key] = tree_json
            return tree_json
        except Exception as e:
            import traceback

            traceback.print_exc()
            return f"Error building tree: {str(e)}"

    async def pageindex_search(self, query: str, tree_json: str) -> str:
        """Search a PageIndex tree for sections relevant to a query."""
        try:
            tree = json.loads(tree_json)
            node_map = self._collect_all_nodes(tree)
            total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            def _acc_tokens(usage: dict[str, int]) -> None:
                for key in total_tokens:
                    total_tokens[key] += usage.get(key, 0)

            if len(node_map) <= SINGLE_STAGE_THRESHOLD:
                candidates = [self._summarize_node(node) for node in node_map.values()]
                selected_ids, usage = await self._llm_select_nodes(query, candidates)
                _acc_tokens(usage)
            else:
                top_level = tree if isinstance(tree, list) else self._get_children(tree)
                if not top_level:
                    top_level = [tree]
                top_candidates = [self._summarize_node(node) for node in top_level]
                stage1_ids, usage1 = await self._llm_select_nodes(query, top_candidates)
                _acc_tokens(usage1)

                selected_ids: list[str] = []
                for node_id in stage1_ids:
                    parent = node_map.get(node_id)
                    if not parent:
                        continue
                    children = self._get_children(parent)
                    if not children:
                        selected_ids.append(node_id)
                        continue

                    child_candidates = [
                        self._summarize_node(child)
                        for child in children
                        if isinstance(child, dict)
                    ]
                    if not child_candidates:
                        selected_ids.append(node_id)
                        continue

                    stage2_ids, usage2 = await self._llm_select_nodes(query, child_candidates)
                    _acc_tokens(usage2)
                    selected_ids.extend(stage2_ids)
                    if parent.get("text"):
                        selected_ids.append(node_id)

            seen: set[str] = set()
            unique_ids: list[str] = []
            for node_id in selected_ids:
                if node_id not in seen:
                    seen.add(node_id)
                    unique_ids.append(node_id)

            relevant_texts: list[str] = []
            for node_id in unique_ids:
                if node_id in node_map and "text" in node_map[node_id]:
                    title = node_map[node_id].get("title", "")
                    relevant_texts.append(f"## {title}\n{node_map[node_id]['text']}")

            if not relevant_texts:
                return json.dumps(
                    {
                        "result": "No relevant sections found.",
                        "token_usage": total_tokens,
                    },
                    ensure_ascii=False,
                )

            return json.dumps(
                {
                    "result": "\n\n---\n\n".join(relevant_texts),
                    "token_usage": total_tokens,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return f"Error in pageindex search: {str(e)}"

    def warmup_llamaindex_engine(self) -> None:
        """Force LlamaIndex initialization during backend startup."""
        self._get_llamaindex_engine()

    async def build_llamaindex_index(self, markdown_content: str) -> str:
        """Build a LlamaIndex vector index from markdown content."""
        try:
            engine = self._get_llamaindex_engine()
            sink = io.StringIO()

            def _build_index() -> str:
                with contextlib.redirect_stderr(sink):
                    return engine.build_index_from_markdown(markdown_content)

            return await asyncio.to_thread(_build_index)
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def search_llamaindex(self, query: str) -> str:
        """Search the loaded LlamaIndex vector index."""
        try:
            engine = self._get_llamaindex_engine()
            sink = io.StringIO()

            def _search_index() -> str:
                with contextlib.redirect_stderr(sink):
                    return engine.search(query)

            return await asyncio.to_thread(_search_index)
        except Exception as e:
            return f"Error in LlamaIndex search: {str(e)}"

    def _get_llamaindex_engine(self):
        """Lazily initialize the LlamaIndex RAG engine."""
        if self._llamaindex_engine is None:
            try:
                llamaindex_rag = load_llamaindex_rag()
            except Exception as e:
                raise build_llamaindex_env_error(e) from e

            self._llamaindex_engine = llamaindex_rag(
                persist_dir=os.path.join(self.project_root, "RAG_persist", "index"),
                manifest_path=os.path.join(self.project_root, "RAG_persist", "manifest.json"),
                llm_api_key=self.llm_api_key,
                llm_base_url=self.llm_base_url,
                llm_name=self.llm_name,
                embed_api_key=self.embed_api_key,
                embed_base_url=self.embed_base_url,
                embed_name=self.embed_name,
                rerank_api_key=self.rerank_api_key,
                rerank_base_url=self.rerank_base_url,
                rerank_name=self.rerank_name,
            )
        return self._llamaindex_engine

    def _collect_all_nodes(self, tree) -> dict[str, dict]:
        """Build a flat node_id -> node map from the tree."""
        node_map: dict[str, dict] = {}

        def _walk(nodes) -> None:
            if isinstance(nodes, dict):
                if "node_id" in nodes:
                    node_map[nodes["node_id"]] = nodes
                for key in ("structure", "nodes", "children"):
                    if key in nodes:
                        _walk(nodes[key])
            elif isinstance(nodes, list):
                for node in nodes:
                    _walk(node)

        _walk(tree)
        return node_map

    def _get_children(self, node: dict) -> list[dict]:
        """Return the direct child list of a tree node."""
        for key in ("structure", "nodes", "children"):
            children = node.get(key)
            if children:
                return children if isinstance(children, list) else [children]
        return []

    def _summarize_node(self, node: dict) -> dict[str, str | bool]:
        """Extract a lightweight summary dict for LLM routing."""
        return {
            "node_id": node.get("node_id", ""),
            "title": node.get("title", ""),
            "summary": node.get("summary", node.get("prefix_summary", "")),
            "has_children": bool(self._get_children(node)),
        }

    async def _llm_select_nodes(
        self,
        query: str,
        candidates: list[dict],
    ) -> tuple[list[str], dict[str, int]]:
        """Ask the LLM to select relevant node IDs from the candidate list."""
        prompt = f"""You are a document retrieval assistant.
Given the query, select all node IDs that may contain the answer.

Query:
{query}

Candidate nodes:
{json.dumps(candidates, indent=2, ensure_ascii=False)}

Return JSON only:
{{
  "thinking": "<brief reasoning>",
  "node_list": ["node_id_1", "node_id_2"]
}}"""

        client = openai.AsyncOpenAI(api_key=self.llm_api_key, base_url=self.llm_base_url)
        response = await client.chat.completions.create(
            model=self.llm_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            top_p=0.01,
            seed=42,
        )
        result_text = response.choices[0].message.content or ""
        token_usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        parsed = json.loads(result_text.strip())
        return parsed.get("node_list", []), token_usage
