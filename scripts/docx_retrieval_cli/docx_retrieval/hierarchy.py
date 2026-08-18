from __future__ import annotations

from .heading_detector import heading_level, heading_score
from .node_factory import make_node
from .schema import BodyItem, Node
from .splitter import split_long_leaves


def build_hierarchy_for_range(
    items: list[BodyItem],
    start: int,
    end: int,
    parent_id: str,
    node_prefix: str,
    use_cn_comma_as_level1: bool = False,
) -> list[Node]:
    root_nodes: list[Node] = []
    stack: list[tuple[int, Node, int]] = []
    heading_positions: list[tuple[int, int]] = []
    sibling_counts: dict[tuple[str, int], int] = {}
    for index in range(start, end):
        level = heading_level(items[index], use_cn_comma_as_level1)
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

    split_long_leaves(root_nodes, items)
    return root_nodes


def flatten_nodes(nodes: list[Node]) -> list[Node]:
    result = []
    for node in nodes:
        result.append(node)
        result.extend(flatten_nodes(node.children))
    return result
