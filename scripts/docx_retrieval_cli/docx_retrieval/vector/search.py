from __future__ import annotations

import math
from typing import Any

from .client import EmbeddingClient
from .schema import VectorIndex


def vector_search(
    document_index: dict[str, Any],
    vector_index: VectorIndex,
    query: str,
    client: EmbeddingClient,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    query_embedding = client.embed([query])[0]
    nodes = {node.get("node_id"): node for node in document_index.get("nodes") or []}
    scored = []
    for item in vector_index.items:
        score = cosine_similarity(query_embedding, item.embedding)
        node = nodes.get(item.node_id) or {}
        scored.append(
            {
                "query": query,
                "match_type": "vector",
                "score": score,
                "node_id": item.node_id,
                "title": node.get("title") or item.metadata.title,
                "summary": node.get("summary"),
                "start_anchor": node.get("start_anchor") or item.metadata.start_anchor,
                "end_anchor": node.get("end_anchor") or item.metadata.end_anchor,
                "node_type": node.get("node_type") or item.metadata.node_type,
                "token_estimate": node.get("token_estimate") or item.metadata.token_estimate,
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
