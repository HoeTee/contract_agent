from __future__ import annotations

from tools.docxindex.schema import BodyItem, DocumentNode

from .node_factory import make_node
from .token_budget import PARAGRAPH_CHUNK_TARGET_TOKENS, PARAGRAPH_SPLIT_THRESHOLD_TOKENS, estimate_tokens


def split_long_leaf(
    node: DocumentNode,
    items: list[BodyItem],
    start: int,
    end: int,
    split_threshold_tokens: int = PARAGRAPH_SPLIT_THRESHOLD_TOKENS,
    chunk_target_tokens: int = PARAGRAPH_CHUNK_TARGET_TOKENS,
) -> None:
    if node.token_estimate <= split_threshold_tokens or node.children:
        return

    chunks = []
    chunk_start = start
    chunk_tokens = 0
    chunk_index = 1
    for index in range(start, end):
        item_tokens = 0 if items[index].kind == "tbl" else estimate_tokens(items[index].text)
        should_flush = chunk_tokens > 0 and chunk_tokens + item_tokens > chunk_target_tokens and index > chunk_start
        if should_flush:
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


def split_long_leaves(
    nodes: list[DocumentNode],
    items: list[BodyItem],
    split_threshold_tokens: int = PARAGRAPH_SPLIT_THRESHOLD_TOKENS,
    chunk_target_tokens: int = PARAGRAPH_CHUNK_TARGET_TOKENS,
) -> None:
    for node in nodes:
        split_long_leaves(node.children, items, split_threshold_tokens, chunk_target_tokens)
        if node.children:
            continue
        if node.source_start is None or node.source_end is None:
            continue
        split_long_leaf(
            node,
            items,
            node.source_start,
            node.source_end,
            split_threshold_tokens,
            chunk_target_tokens,
        )
