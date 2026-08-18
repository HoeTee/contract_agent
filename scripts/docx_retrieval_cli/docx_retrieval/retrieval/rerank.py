from __future__ import annotations

import json
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

from docx_retrieval.indexing import estimate_tokens
from docx_retrieval.llm import LLMClient
from docx_retrieval.llm.cache import JsonlCache, cache_key, text_hash
from docx_retrieval.llm.schemas import RerankResponse

RERANK_PROMPT_VERSION = "docx_rerank_v2"


def rerank_matches(
    index: dict[str, Any],
    query: str,
    candidates: list[dict[str, Any]],
    client: LLMClient,
    input_tokens: int,
    cache_dir: Path | None,
    concurrency: int = 10,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    candidate_view = _fit_candidates(index, candidates, input_tokens)
    if not candidate_view:
        return []
    payload = json.dumps(candidate_view, ensure_ascii=False)
    cache = JsonlCache(cache_dir / "llm_rerank.jsonl" if cache_dir else None)
    key = cache_key(RERANK_PROMPT_VERSION, client.settings.model, query, text_hash(payload))
    cached = cache.get(key)
    if cached is None:
        limiter = BoundedSemaphore(max(1, concurrency))
        with limiter:
            response = client.complete_model(_rerank_prompt(query, payload), RerankResponse)
        cached = response.model_dump(mode="json")
        cache.set(key, cached)

    allowed = {item["node_id"] for item in candidate_view}
    by_id = {item.get("node_id"): item for item in candidates}
    ranked = []
    seen = set()
    for item in cached.get("nodes") or []:
        node_id = str(item.get("node_id") or "").strip()
        if not node_id or node_id not in allowed or node_id in seen:
            continue
        merged = dict(by_id[node_id])
        merged["rerank_score"] = float(item.get("score") or 0.0)
        merged["rerank_reason"] = str(item.get("reason") or "").strip()
        ranked.append(merged)
        seen.add(node_id)

    for item in candidates:
        node_id = item.get("node_id")
        if node_id and node_id not in seen:
            merged = dict(item)
            merged["rerank_score"] = None
            merged["rerank_reason"] = ""
            ranked.append(merged)
    return ranked


def _fit_candidates(index: dict[str, Any], candidates: list[dict[str, Any]], input_tokens: int) -> list[dict[str, Any]]:
    nodes = {node.get("node_id"): node for node in index.get("nodes") or []}
    result = []
    used = 0
    for candidate in candidates:
        node_id = candidate.get("node_id")
        node = nodes.get(node_id) or {}
        item = {
            "node_id": node_id,
            "sources": candidate.get("sources") or [candidate.get("source")],
            "title": node.get("title") or candidate.get("title"),
            "summary": node.get("summary") or candidate.get("summary"),
            "node_type": node.get("node_type") or candidate.get("node_type"),
            "token_estimate": node.get("token_estimate") or candidate.get("token_estimate"),
            "vector_score": candidate.get("vector_score") or candidate.get("score"),
        }
        tokens = estimate_tokens(json.dumps(item, ensure_ascii=False))
        if result and used + tokens > input_tokens:
            break
        result.append(item)
        used += tokens
    return result


def _rerank_prompt(query: str, candidates_json: str) -> str:
    return f"""你正在对 DOCX 合同检索候选 node 做相关性重排序。

审查问题：
{query}

候选 node：
{candidates_json}

重排序规则：
- 只允许返回候选列表中真实存在的 node_id。
- 优先选择能够直接支撑审查问题判断的 node。
- 如果父 node 和更具体的子 node 都相关，优先选择更具体的子 node。
- 可以保留跨章节判断所需的多个 node。
- score 使用 0 到 1，1 表示最相关。

输出规范：
- 必须只返回一个合法 JSON object。
- 不要返回 Markdown。
- 不要返回解释。
- 不要添加 schema 以外的字段。
- JSON 必须严格符合：
{{
  "nodes": [
    {{"node_id": "body/sec_001", "score": 0.95, "reason": "选择原因"}}
  ]
}}"""
