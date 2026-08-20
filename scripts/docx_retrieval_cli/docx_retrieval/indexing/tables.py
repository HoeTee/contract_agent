from __future__ import annotations

from docx_retrieval.schema import BodyItem, DocumentNode

from .node_factory import make_node
from .summaries import make_summary
from .token_budget import estimate_tokens

TABLE_CHUNK_TARGET_TOKENS = 6000
TABLE_INLINE_MAX_TOKENS = 10000


def attach_table_nodes(
    parent: DocumentNode,
    items: list[BodyItem],
    start: int,
    end: int,
    *,
    inline_max_tokens: int = TABLE_INLINE_MAX_TOKENS,
    chunk_target_tokens: int = TABLE_CHUNK_TARGET_TOKENS,
) -> None:
    """Attach each body-level table to the deepest structural node that contains it."""
    owner_counts: dict[str, int] = {}
    for index in range(start, end):
        item = items[index]
        if item.kind != "tbl":
            continue
        owner = _deepest_owner(parent, index)
        owner_counts[owner.node_id] = owner_counts.get(owner.node_id, 0) + 1
        table_number = owner_counts[owner.node_id]
        node = make_node(
            f"{owner.node_id}/table_{table_number:03d}",
            "table",
            f"{owner.title} / 表格{table_number}",
            items,
            index,
            index + 1,
            (owner.level + 1) if owner.level is not None else None,
            owner.node_id,
            evidence=["ooxml_table"],
            include_tables=True,
        )
        node.table_id = item.anchor
        node.mapping_ref = f"table_store.json#{item.anchor}"
        _split_large_table(node, item, inline_max_tokens, chunk_target_tokens)
        owner.children.append(node)
        owner.children.sort(key=lambda value: (value.start_index is None, value.start_index or 0, value.node_id))


def collect_table_map(items: list[BodyItem]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in items:
        if item.kind != "tbl" or not item.table_mapping:
            continue
        mapping = dict(item.table_mapping)
        mapping["table_id"] = item.anchor
        mapping["body_child_index"] = item.body_child_index
        mapping["retrieval_anchor"] = item.anchor
        mapping["raw_text"] = item.raw_text or ""
        result[item.anchor] = mapping
    return result


def _deepest_owner(node: DocumentNode, item_index: int) -> DocumentNode:
    for child in node.children:
        if child.node_type == "table":
            continue
        if child.source_start is None or child.source_end is None:
            continue
        if child.source_start <= item_index < child.source_end:
            return _deepest_owner(child, item_index)
    return node


def _split_large_table(
    node: DocumentNode,
    item: BodyItem,
    inline_max_tokens: int,
    chunk_target_tokens: int,
) -> None:
    if node.token_estimate <= inline_max_tokens or not item.table_mapping:
        return
    mapping = item.table_mapping
    rows = list(mapping.get("row_markdown") or [])
    if not rows:
        return

    table_comment = f"<!-- table_id: {item.anchor} -->\n"
    header = rows[0]
    columns = int(mapping.get("columns") or 1)
    separator = "| " + " | ".join("---" for _ in range(columns)) + " |\n"
    prefix = table_comment + header + separator
    data_rows = rows[1:]
    chunks: list[tuple[int, int, str]] = []
    chunk_start = 2
    chunk_rows: list[str] = []
    chunk_tokens = estimate_tokens(prefix)
    current_row = 2

    for row_text in data_rows:
        row_tokens = estimate_tokens(row_text)
        if chunk_rows and chunk_tokens + row_tokens > chunk_target_tokens:
            chunks.append((chunk_start, current_row - 1, prefix + "".join(chunk_rows)))
            chunk_start = current_row
            chunk_rows = []
            chunk_tokens = estimate_tokens(prefix)
        chunk_rows.append(row_text)
        chunk_tokens += row_tokens
        current_row += 1
    if chunk_rows or not data_rows:
        chunks.append((chunk_start, max(chunk_start, current_row - 1), prefix + "".join(chunk_rows)))

    node.text = ""
    for row_start, row_end, text in chunks:
        child = DocumentNode(
            node_id=f"{node.node_id}/rows_{row_start:04d}_{row_end:04d}",
            parent_id=node.node_id,
            node_type="table_chunk",
            level=(node.level + 1) if node.level is not None else None,
            title=f"{node.title} / 第{row_start}-{row_end}行",
            text=text,
            summary=make_summary(text),
            start_anchor=node.start_anchor,
            end_anchor=node.end_anchor,
            start_index=node.start_index,
            end_index=node.end_index,
            token_estimate=estimate_tokens(text),
            confidence_evidence=["table_row_chunk"],
            table_id=item.anchor,
            mapping_ref=node.mapping_ref,
            row_start=row_start,
            row_end=row_end,
        )
        node.children.append(child)
