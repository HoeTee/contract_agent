from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import datetime

import openai

from tools.retrieval.llamaindex import build_llamaindex_env_error, load_llamaindex_rag
from tools.retrieval.pageindex.page_index_md import md_to_tree
from tools.document.file_parser import FileParser


SINGLE_STAGE_THRESHOLD = 20


class IndexRetriever:
    """Facade over contract PageIndex retrieval and institutional RAG."""

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
        self._contract_llamaindex_engine = None
        self._institutional_engine = None
        self.institutional_docs_dir = os.path.join(
            self.project_root,
            os.getenv("INSTITUTIONAL_DOCS_DIR", os.path.join("docs", "institutional_docs")),
        )
        self.institutional_index_dir = os.path.join(
            self.project_root,
            "RAG_persist",
            "institutional_index",
        )
        self.institutional_manifest_path = os.path.join(
            self.project_root,
            "RAG_persist",
            "institutional_manifest.json",
        )

    async def build_pageindex_tree(self, markdown_content: str) -> str:
        """Build a transient PageIndex tree from markdown content."""
        summary_token_threshold = 200

        try:
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

            return json.dumps(tree, ensure_ascii=False, indent=2)
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

    async def build_contract_llamaindex_index(self, markdown_content: str) -> str:
        """Build a temporary in-memory LlamaIndex contract index for this run."""
        try:
            engine = self._get_contract_llamaindex_engine()
            node_count = await asyncio.to_thread(
                engine.build_temporary_index_from_text,
                markdown_content,
                "current_contract",
            )
            return json.dumps(
                {"status": "built_temporary_index", "num_nodes": node_count},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    async def search_contract_llamaindex(self, query: str) -> str:
        """Search the temporary in-memory contract LlamaIndex."""
        try:
            engine = self._get_contract_llamaindex_engine()
            return await asyncio.to_thread(engine.search, query, "合同检索结果")
        except Exception as e:
            return f"Error in contract LlamaIndex search: {str(e)}"

    async def build_institutional_index(self) -> str:
        """Incrementally update the persistent institutional-document index."""
        print("[institutional-index] Loading index state...")
        engine = self._get_institutional_engine()
        engine.load_or_create_index()

        print("[institutional-index] Scanning institutional documents...")
        manifest = self._read_institutional_manifest()
        current_files = self._scan_institutional_files()
        previous_files = manifest.get("files", {})

        added = [path for path in current_files if path not in previous_files]
        modified = [
            path for path, meta in current_files.items()
            if path in previous_files and meta["sha256"] != previous_files[path]["sha256"]
        ]
        deleted = [path for path in previous_files if path not in current_files]
        unchanged_count = len(current_files) - len(added) - len(modified)
        print(
            "[institutional-index] "
            f"files={len(current_files)} added={len(added)} "
            f"modified={len(modified)} deleted={len(deleted)} unchanged={unchanged_count}"
        )

        for relative_path in deleted:
            print(f"[institutional-index] deleting: {relative_path}")
            engine.delete_ref_doc(previous_files[relative_path]["doc_id"])

        parser_name = "mineru" if self._parse_with_mineru() else "local"
        print(f"[institutional-index] parser={parser_name}")
        node_counts: dict[str, int] = {}
        for relative_path in modified:
            print(f"[institutional-index] updating: {relative_path}")
            engine.delete_ref_doc(previous_files[relative_path]["doc_id"])
            node_counts[relative_path] = await self._insert_institutional_file(
                engine,
                relative_path,
                current_files[relative_path]["sha256"],
                parser_name,
            )
            print(f"[institutional-index] nodes={node_counts[relative_path]} file={relative_path}")

        for relative_path in added:
            print(f"[institutional-index] adding: {relative_path}")
            node_counts[relative_path] = await self._insert_institutional_file(
                engine,
                relative_path,
                current_files[relative_path]["sha256"],
                parser_name,
            )
            print(f"[institutional-index] nodes={node_counts[relative_path]} file={relative_path}")

        print("[institutional-index] Persisting index...")
        engine.persist()
        next_files = {
            path: previous_files[path]
            for path in previous_files
            if path in current_files and path not in modified
        }
        for relative_path, meta in current_files.items():
            if relative_path in added or relative_path in modified:
                next_files[relative_path] = {
                    "sha256": meta["sha256"],
                    "doc_id": self._institutional_doc_id(relative_path),
                    "parser": parser_name,
                    "node_count": node_counts[relative_path],
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }

        next_manifest = {
            "source_dir": os.path.relpath(self.institutional_docs_dir, self.project_root),
            "embedding_model": self.embed_name,
            "chunk_size": 512,
            "chunk_overlap": 100,
            "files": dict(sorted(next_files.items())),
        }
        os.makedirs(os.path.dirname(self.institutional_manifest_path), exist_ok=True)
        with open(self.institutional_manifest_path, "w", encoding="utf-8") as f:
            json.dump(next_manifest, f, ensure_ascii=False, indent=2)
        print("[institutional-index] Manifest updated.")

        return json.dumps(
            {
                "status": "updated",
                "added": added,
                "modified": modified,
                "deleted": deleted,
                "unchanged_count": unchanged_count,
                "total_files": len(current_files),
            },
            ensure_ascii=False,
        )

    async def search_institutional_index(self, query: str) -> str:
        """Search the persistent institutional-document index."""
        try:
            engine = self._get_institutional_engine()
            return await asyncio.to_thread(engine.search, query)
        except Exception as e:
            return f"Error in institutional search: {str(e)}"

    def _get_institutional_engine(self):
        """Lazily initialize the institutional LlamaIndex engine."""
        if self._institutional_engine is None:
            try:
                llamaindex_rag = load_llamaindex_rag()
            except Exception as e:
                raise build_llamaindex_env_error(e) from e

            self._institutional_engine = llamaindex_rag(
                persist_dir=self.institutional_index_dir,
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
        return self._institutional_engine

    def _get_contract_llamaindex_engine(self):
        """Lazily initialize the temporary contract LlamaIndex engine."""
        if self._contract_llamaindex_engine is None:
            try:
                llamaindex_rag = load_llamaindex_rag()
            except Exception as e:
                raise build_llamaindex_env_error(e) from e

            self._contract_llamaindex_engine = llamaindex_rag(
                persist_dir="",
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
        return self._contract_llamaindex_engine

    def _read_institutional_manifest(self) -> dict:
        if not os.path.exists(self.institutional_manifest_path):
            return {"files": {}}
        with open(self.institutional_manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _scan_institutional_files(self) -> dict[str, dict[str, str]]:
        supported_suffixes = {".docx", ".pdf", ".md", ".txt"}
        files: dict[str, dict[str, str]] = {}
        for root, _, filenames in os.walk(self.institutional_docs_dir):
            for filename in filenames:
                path = os.path.join(root, filename)
                if os.path.splitext(filename)[1].lower() not in supported_suffixes:
                    continue
                relative_path = os.path.relpath(path, self.institutional_docs_dir).replace(os.sep, "/")
                files[relative_path] = {"sha256": self._file_sha256(path)}
        return dict(sorted(files.items()))

    async def _insert_institutional_file(
        self,
        engine,
        relative_path: str,
        source_hash: str,
        parser_name: str,
    ) -> int:
        absolute_path = os.path.join(self.institutional_docs_dir, relative_path)
        if parser_name == "mineru":
            content = await FileParser.parse_file_with_mineru(absolute_path)
        else:
            content = FileParser.parse_file(absolute_path)
        return await asyncio.to_thread(
            engine.insert_text,
            content=content,
            relative_path=relative_path,
            doc_id=self._institutional_doc_id(relative_path),
            source_hash=source_hash,
            parser=parser_name,
        )

    @staticmethod
    def _file_sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _institutional_doc_id(relative_path: str) -> str:
        return f"institutional:{relative_path}"

    @staticmethod
    def _parse_with_mineru() -> bool:
        return str(os.getenv("PARSE_FILE_WITH_MINERU")).lower() in ("1", "true", "yes", "on")

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
