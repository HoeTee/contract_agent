from __future__ import annotations

from docxindex.detection import heading_level, heading_score
from docxindex.detection.heading_profiles import CompiledHeadingProfile
from docxindex.schema import BodyItem, DocumentNode

from .node_factory import make_node
from .splitter import split_long_leaves
from .token_budget import PARAGRAPH_CHUNK_TARGET_TOKENS, PARAGRAPH_SPLIT_THRESHOLD_TOKENS


def build_hierarchy_for_range(
    items: list[BodyItem],
    start: int,
    end: int,
    parent_id: str,
    node_prefix: str,
    heading_profile: CompiledHeadingProfile | None = None,
    split_long_nodes: bool = True,
    paragraph_split_threshold_tokens: int = PARAGRAPH_SPLIT_THRESHOLD_TOKENS,
    paragraph_chunk_target_tokens: int = PARAGRAPH_CHUNK_TARGET_TOKENS,
) -> list[DocumentNode]:
    root_nodes: list[DocumentNode] = []
    stack: list[tuple[int, DocumentNode, int]] = []
    heading_positions: list[tuple[int, int]] = []
    sibling_counts: dict[tuple[str, int], int] = {}
    for index in range(start, end):
        level = heading_level(items[index], heading_profile)
        if level is not None:
            heading_positions.append((index, level))

    for pos, (index, level) in enumerate(heading_positions):
        next_index = end
        for future_index, future_level in heading_positions[pos + 1 :]:
            if future_level <= level:
                next_index = future_index
                break
        item = items[index]
        while stack and stack[-1][0] >= level:
            stack.pop()
        local_parent = stack[-1][1].node_id if stack else parent_id
        key = (local_parent, level)
        sibling_counts[key] = sibling_counts.get(key, 0) + 1
        count = sibling_counts[key]
        node_id = f"{node_prefix}/sec_{count:03d}" if level == 1 and not stack else f"{local_parent}/l{level}_{count:03d}"
        score, evidence = heading_score(item, level)
        node = make_node(node_id, "section", item.text, items, index, next_index, level, local_parent, score, evidence)
        if stack:
            stack[-1][1].children.append(node)
        else:
            root_nodes.append(node)
        stack.append((level, node, index))

    if split_long_nodes:
        split_long_leaves(
            root_nodes,
            items,
            paragraph_split_threshold_tokens,
            paragraph_chunk_target_tokens,
        )
    return root_nodes


def flatten_nodes(nodes: list[DocumentNode]) -> list[DocumentNode]:
    result = []
    for node in nodes:
        result.append(node)
        result.extend(flatten_nodes(node.children))
    return result
