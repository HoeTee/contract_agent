from __future__ import annotations

from docx_retrieval.detection import attachment_starts, heading_level, heading_score, is_plain_label, is_visual_title
from docx_retrieval.schema import BodyItem, DocumentNode

from .node_factory import make_node
from .splitter import split_long_leaf
from .tables import attach_table_nodes


def build_attachment_children(
    items: list[BodyItem],
    start: int,
    end: int,
    parent_id: str,
    split_long_nodes: bool = True,
) -> list[DocumentNode]:
    nodes: list[DocumentNode] = []
    candidate_positions = []
    for position, index in enumerate(range(start, end)):
        item = items[index]
        if heading_level(item) is not None:
            candidate_positions.append((index, "heading", heading_level(item)))
        elif is_visual_title(item, items[index + 1 : end], position):
            candidate_positions.append((index, "visual_title", None))
        elif is_plain_label(item):
            candidate_positions.append((index, "plain_label", None))

    for pos, (index, kind, level) in enumerate(candidate_positions):
        next_index = candidate_positions[pos + 1][0] if pos + 1 < len(candidate_positions) else end
        title = items[index].text
        node_type = kind
        score, evidence = heading_score(items[index], level, inside_attachment=True)
        evidence.append(kind)
        node = make_node(
            f"{parent_id}/{kind}_{pos + 1:03d}",
            node_type,
            title,
            items,
            index,
            next_index,
            level,
            parent_id,
            score,
            evidence,
        )
        if split_long_nodes:
            split_long_leaf(node, items, index, next_index)
        nodes.append(node)
    return nodes


def build_attachments(
    items: list[BodyItem],
    start: int,
    end: int,
    parent_id: str,
    split_long_nodes: bool = True,
    table_inline_max_tokens: int = 10000,
    table_chunk_target_tokens: int = 6000,
) -> list[DocumentNode]:
    starts = attachment_starts(items, start, end)
    nodes = []
    for pos, attach_start in enumerate(starts):
        attach_end = starts[pos + 1] if pos + 1 < len(starts) else end
        item = items[attach_start]
        score, evidence = heading_score(item, None, inside_attachment=True)
        evidence.append("attachment_section")
        node = make_node(
            f"attachments/att_{pos + 1:03d}",
            "attachment_section",
            item.text,
            items,
            attach_start,
            attach_end,
            None,
            parent_id,
            score,
            evidence,
        )
        node.children = build_attachment_children(items, attach_start + 1, attach_end, node.node_id, split_long_nodes)
        attach_table_nodes(
            node,
            items,
            attach_start + 1,
            attach_end,
            inline_max_tokens=table_inline_max_tokens,
            chunk_target_tokens=table_chunk_target_tokens,
        )
        nodes.append(node)
    return nodes
