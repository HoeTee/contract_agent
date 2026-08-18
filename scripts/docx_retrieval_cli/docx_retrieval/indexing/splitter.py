from __future__ import annotations

from docx_retrieval.schema import BodyItem, DocumentNode

from .node_factory import make_node
from .token_budget import NODE_HARD_LIMIT_TOKENS, NODE_SOFT_LIMIT_TOKENS, NODE_TARGET_TOKENS, estimate_tokens


def split_long_leaf(node: DocumentNode, items: list[BodyItem], start: int, end: int) -> None:
    if node.token_estimate <= NODE_SOFT_LIMIT_TOKENS or node.children:
        return

    chunks = []
    chunk_start = start
    chunk_tokens = 0
    chunk_index = 1
    for index in range(start, end):
        item_tokens = estimate_tokens(items[index].text)
        should_flush = chunk_tokens >= NODE_TARGET_TOKENS and index > chunk_start
        hard_flush = chunk_tokens + item_tokens > NODE_HARD_LIMIT_TOKENS and index > chunk_start
        if should_flush or hard_flush:
            chunks.append((chunk_start, index))
            chunk_start = index
            chunk_tokens = 0
        chunk_tokens += item_tokens
    if chunk_start < end:
        chunks.append((chunk_start, end))

    if len(chunks) <= 1:
        return

    for chunk_start, chunk_end in chunks:
        child = make_node(
            f"{node.node_id}/chunk_{chunk_index:03d}",
            "chunk",
            f"{node.title} / chunk {chunk_index}",
            items,
            chunk_start,
            chunk_end,
            None,
            node.node_id,
            score=node.confidence_score,
            evidence=node.confidence_evidence + ["token_chunk"],
        )
        node.children.append(child)
        chunk_index += 1


def split_long_leaves(nodes: list[DocumentNode], items: list[BodyItem]) -> None:
    for node in nodes:
        split_long_leaves(node.children, items)
        if node.children:
            continue
        if node.source_start is None or node.source_end is None:
            continue
        split_long_leaf(node, items, node.source_start, node.source_end)
