from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docx_retrieval.indexing import estimate_tokens
from docx_retrieval.llm import LLMClient
from docx_retrieval.llm.cache import JsonlCache, cache_key, text_hash

QUERY_PROMPT_VERSION = "docx_query_v1"
STRUCTURE_QUERY_BUDGET_TOKENS = 18000


def llm_query(index: dict[str, Any], queries: list[str], client: LLMClient, cache_dir: Path | None) -> list[dict[str, Any]]:
    cache = JsonlCache(cache_dir / "llm_query.jsonl" if cache_dir else None)
    structure_view = _fit_structure(index["structure_tree"])
    results = []
    for query in queries:
        payload = json.dumps(structure_view, ensure_ascii=False)
        key = cache_key(QUERY_PROMPT_VERSION, client.settings.model, query, text_hash(payload))
        cached = cache.get(key)
        if cached is None:
            cached = client.complete_json(_query_prompt(query, payload))
            cache.set(key, cached)
        for item in cached.get("nodes") or []:
            node_id = str(item.get("node_id") or "").strip()
            node = _node_by_id(index, node_id)
            if not node:
                continue
            results.append(
                {
                    "query": query,
                    "match_type": "llm_structure",
                    "node_id": node_id,
                    "title": node.get("title"),
                    "summary": node.get("summary"),
                    "start_anchor": node.get("start_anchor"),
                    "end_anchor": node.get("end_anchor"),
                    "reason": str(item.get("reason") or "").strip(),
                }
            )
    return results


def _fit_structure(structure_tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = _compact_structure(structure_tree)
    if estimate_tokens(json.dumps(compact, ensure_ascii=False)) <= STRUCTURE_QUERY_BUDGET_TOKENS:
        return compact
    return _drop_deep_children(compact, max_depth=2)


def _compact_structure(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for node in nodes:
        item = {
            "node_id": node.get("node_id"),
            "title": node.get("title"),
            "node_type": node.get("node_type"),
            "summary": node.get("summary"),
            "token_estimate": node.get("token_estimate"),
        }
        if node.get("children"):
            item["children"] = _compact_structure(node["children"])
        compact.append(item)
    return compact


def _drop_deep_children(nodes: list[dict[str, Any]], max_depth: int, depth: int = 0) -> list[dict[str, Any]]:
    result = []
    for node in nodes:
        item = {key: value for key, value in node.items() if key != "children"}
        if depth < max_depth and node.get("children"):
            item["children"] = _drop_deep_children(node["children"], max_depth, depth + 1)
        result.append(item)
    return result


def _node_by_id(index: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for node in index["nodes"]:
        if node.get("node_id") == node_id:
            return node
    return None


def _query_prompt(query: str, structure_json: str) -> str:
    return f"""你正在从 DOCX 合同结构索引中选择与审查问题最相关的 node。

审查问题：
{query}

结构树：
{structure_json}

要求：
- 只能返回结构树中真实存在的 node_id。
- 优先返回标题或摘要直接相关的 node。
- 如果需要跨章节比较，可以返回多个 node。
- 不要返回整篇正文 body，除非没有更具体的 node。
- 最多返回 8 个 node。

只返回 JSON：
{{
  "nodes": [
    {{"node_id": "body/sec_001", "reason": "选择原因"}}
  ]
}}"""
